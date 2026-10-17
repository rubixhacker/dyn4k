import java.util.Iterator;
import java.util.List;
import java.util.ConcurrentModificationException;
import org.dyn4j.Unsafe;
import org.dyn4j.UnitConversion;
import org.dyn4j.collision.AbstractCollisionBody;
import org.dyn4j.collision.AxisAlignedBounds;
import org.dyn4j.collision.BasicCollisionItem;
import org.dyn4j.collision.BasicCollisionPair;
import org.dyn4j.collision.CategoryFilter;
import org.dyn4j.collision.CollisionBody;
import org.dyn4j.collision.Filter;
import org.dyn4j.collision.Fixture;
import org.dyn4j.collision.FixtureModificationHandler;
import org.dyn4j.collision.TypeFilter;
import org.dyn4j.exception.CopyException;
import org.dyn4j.geometry.AABB;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Vector2;

public final class CollisionModelConsumer {
    private static int checks;

    private static void check(boolean condition) {
        if (!condition) throw new AssertionError("collision check " + (checks + 1));
        checks++;
    }

    private static class RootFilter extends TypeFilter {}
    private static class ChildFilter extends RootFilter {}
    private static class OtherFilter extends TypeFilter {}

    private static class ExposedFixture extends Fixture {
        ExposedFixture(Convex shape) { super(shape); }
        ExposedFixture(ExposedFixture other) { super(other); }
        @Override public ExposedFixture copy() { return new ExposedFixture(this); }
        Filter protectedFilter() { return this.filter; }
    }

    private static class BadFixture extends Fixture {
        BadFixture(Convex shape) { super(shape); }
    }

    private static class Body extends AbstractCollisionBody<Fixture> {
        Body() { super(); }
        Body(Body other) { super(other); }
        @Override public Fixture addFixture(Convex shape) {
            Fixture fixture = new Fixture(shape);
            addFixture(fixture);
            return fixture;
        }
        @Override public Vector2 getLocalCenter() { return new Vector2(); }
        @Override public Body copy() { return new Body(this); }
        int protectedCount() { return this.fixtures.size(); }
        boolean protectedEnabled() { return this.enabled; }
        void updateRadius() { setRotationDiscRadius(new Vector2()); }
    }

    private static class SubstitutingBody extends Body {
        final Fixture replacement = new Fixture(new Circle(2.0));
        SubstitutingBody() { super(); }
        SubstitutingBody(SubstitutingBody other) { super(other); }
        @Override public Fixture getFixture(int index) { return replacement; }
        @Override public SubstitutingBody copy() { return new SubstitutingBody(this); }
    }

    public static void main(String[] args) {
        RootFilter root = new RootFilter();
        ChildFilter child = new ChildFilter();
        check(root.isAllowed(child));
        check(child.isAllowed(root));
        check(!root.isAllowed(new OtherFilter()));
        check(!root.isAllowed(null));
        check(root.toString().equals("TypeFilter[ClassName=" + RootFilter.class.getName() + "]"));
        check(Filter.DEFAULT_FILTER.isAllowed(root));

        CategoryFilter a = new CategoryFilter(1, 2);
        CategoryFilter b = new CategoryFilter(2, 1);
        check(a.isAllowed(b) && b.isAllowed(a));
        check(!a.isAllowed(new CategoryFilter(4, 1)));
        check(a.copy().equals(a) && a.copy() != a);

        ExposedFixture fixture = new ExposedFixture(new Circle(1.0));
        fixture.setFilter(a);
        fixture.setSensor(true);
        fixture.setUserData("not copied");
        ExposedFixture fixtureCopy = Unsafe.copy(fixture);
        check(fixtureCopy != fixture && fixtureCopy.getShape() != fixture.getShape());
        check(fixtureCopy.protectedFilter() != fixture.protectedFilter());
        check(fixtureCopy.isSensor() && fixtureCopy.getUserData() == null);
        try {
            Unsafe.copy(new BadFixture(new Circle(1.0)));
            throw new AssertionError("missing CopyException");
        } catch (CopyException expected) {
            check(expected.getMessage().contains(BadFixture.class.getName()));
        }
        check(new CopyException(BadFixture.class, Fixture.class).getMessage().contains(Fixture.class.getName()));

        Body body = new Body();
        StringBuilder events = new StringBuilder();
        body.setFixtureModificationHandler(new FixtureModificationHandler<Fixture>() {
            public void onFixtureAdded(Fixture fixture) { events.append('A'); }
            public void onFixtureRemoved(Fixture fixture) { events.append('R'); }
            public void onAllFixturesRemoved() { events.append('X'); }
        });
        List<Fixture> view = body.getFixtures();
        body.addFixture(fixture);
        check(view.size() == 1 && view.get(0) == fixture);
        check(body.protectedCount() == 1 && body.protectedEnabled());
        try { view.clear(); throw new AssertionError("mutable view"); }
        catch (UnsupportedOperationException expected) { checks++; }
        Iterator<Fixture> iterator = body.getFixtureIterator();
        check(iterator.next() == fixture);
        iterator.remove();
        check(view.isEmpty() && events.toString().equals("AR"));
        body.addFixture(new Circle(1.0));
        body.setOwner("owner");
        body.setUserData("data");
        body.updateRadius();
        check(body.getRotationDiscRadius() == 1.0);
        CollisionBody<Fixture> copied = body.copy();
        check(copied.getOwner() == null && copied.getUserData() == null);
        check(copied.getFixture(0) != body.getFixture(0));
        check(copied.getFixtureModificationHandler() == null);
        check(body.removeAllFixtures().size() == 1 && view.isEmpty());
        check(events.toString().equals("ARAX"));

        SubstitutingBody substituting = new SubstitutingBody();
        substituting.addFixture(new Circle(1.0));
        check(substituting.copy().getFixtures().get(0).getShape().getRadius(new Vector2()) == 2.0);

        Body changing = new Body();
        changing.addFixture(new Circle(1.0));
        Iterator<Fixture> viewIterator = changing.getFixtures().iterator();
        changing.addFixture(new Circle(2.0));
        try { viewIterator.next(); throw new AssertionError("missing ConcurrentModificationException"); }
        catch (ConcurrentModificationException expected) { checks++; }

        AxisAlignedBounds bounds = new AxisAlignedBounds(4, 4);
        check(bounds.isOutside(new AABB(3, 3, 4, 4)));
        bounds.translate(3, 3);
        check(!bounds.isOutside(new AABB(3, 3, 4, 4)));
        check(bounds.copy().getBounds().equals(bounds.getBounds()));
        check(new BasicCollisionPair<>("a", "b").equals(new BasicCollisionPair<>("b", "a")));
        try {
            new BasicCollisionPair<Object>(null, "x").equals(new BasicCollisionPair<Object>(null, "x"));
            throw new AssertionError("missing NullPointerException");
        } catch (NullPointerException expected) { checks++; }
        BasicCollisionItem<Body, Fixture> nullItem = new BasicCollisionItem<>(null, null);
        check(nullItem.getBody() == null && nullItem.getFixture() == null);
        check(new BasicCollisionItem<>(body, fixture).copy().getBody() == body);
        check(UnitConversion.feetToMeters(1.0) == 0.0254 * 12.0);
        System.out.println("collision consumer checks=" + checks);
    }
}
