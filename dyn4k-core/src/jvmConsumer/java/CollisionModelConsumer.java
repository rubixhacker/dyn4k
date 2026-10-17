import java.util.Iterator;
import java.util.List;
import java.util.ConcurrentModificationException;
import org.dyn4j.Unsafe;
import org.dyn4j.UnitConversion;
import org.dyn4j.collision.AbstractCollisionBody;
import org.dyn4j.collision.AbstractBounds;
import org.dyn4j.collision.AbstractCollisionItem;
import org.dyn4j.collision.AbstractCollisionPair;
import org.dyn4j.collision.AxisAlignedBounds;
import org.dyn4j.collision.BasicCollisionItem;
import org.dyn4j.collision.BasicCollisionPair;
import org.dyn4j.collision.CategoryFilter;
import org.dyn4j.collision.CollisionBody;
import org.dyn4j.collision.CollisionItem;
import org.dyn4j.collision.Filter;
import org.dyn4j.collision.Fixture;
import org.dyn4j.collision.FixtureModificationHandler;
import org.dyn4j.collision.TypeFilter;
import org.dyn4j.exception.CopyException;
import org.dyn4j.exception.ArgumentNullException;
import org.dyn4j.geometry.AABB;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Transform;
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
        double updateRadiusWith(Vector2 center) { setRotationDiscRadius(center); return this.radius; }
        Iterator<Fixture> protectedIterator() { return this.fixtures.iterator(); }
        List<Fixture> protectedSubList() { return this.fixtures.subList(0, 1); }
    }

    private static class SubstitutingBody extends Body {
        final Fixture replacement = new Fixture(new Circle(2.0));
        SubstitutingBody() { super(); }
        SubstitutingBody(SubstitutingBody other) { super(other); }
        @Override public Fixture getFixture(int index) { return replacement; }
        @Override public SubstitutingBody copy() { return new SubstitutingBody(this); }
    }

    private static class NullAwareBounds extends AbstractBounds {
        boolean sawNull;
        NullAwareBounds() { super((Vector2) null); }
        @Override public void translate(Vector2 vector) {
            if (vector == null) sawNull = true;
            else super.translate(vector);
        }
        @Override public boolean isOutside(CollisionBody<?> body) { return false; }
        @Override public boolean isOutside(AABB aabb) { return false; }
        @Override public boolean isOutside(AABB aabb, Transform transform, Fixture fixture) { return false; }
        @Override public NullAwareBounds copy() { return new NullAwareBounds(); }
    }

    private static class ObservedItem implements CollisionItem<Body, Fixture> {
        private final String tag;
        private final StringBuilder calls;
        ObservedItem(String tag, StringBuilder calls) { this.tag = tag; this.calls = calls; }
        @Override public Body getBody() { calls.append(tag).append("body,"); return null; }
        @Override public Fixture getFixture() { calls.append(tag).append("fixture,"); return null; }
        @Override public CollisionItem<Body, Fixture> copy() { return this; }
    }

    private static class HashToken {
        private final StringBuilder calls;
        HashToken(StringBuilder calls) { this.calls = calls; }
        @Override public int hashCode() { calls.append("first,"); return 7; }
    }

    private static class MutatingFixture extends Fixture {
        private final Body body;
        private boolean added;
        MutatingFixture(Body body) { super(new Circle(1.0)); this.body = body; }
        @Override public Convex getShape() {
            if (!added) { added = true; body.addFixture(new Circle(2.0)); }
            return super.getShape();
        }
    }

    private static Body mutationBody() {
        Body body = new Body();
        body.addFixture(new MutatingFixture(body));
        return body;
    }

    private static class NullAcceptingCircle extends Circle {
        NullAcceptingCircle() { super(1.0); }
        @Override public boolean contains(Vector2 point, Transform transform) { return point == null; }
        @Override public double getRadius(Vector2 center) {
            return center == null ? 3.0 : super.getRadius(center);
        }
        @Override public void computeAABB(Transform transform, AABB result) {
            if (transform == null) result.set(new AABB(-3.0, -3.0, 3.0, 3.0));
            else super.computeAABB(transform, result);
        }
    }

    private static Body nullPointBody() {
        Body body = new Body();
        body.addFixture(new NullAcceptingCircle());
        return body;
    }

    public static void main(String[] args) {
        RootFilter root = new RootFilter();
        check(new NullAwareBounds().sawNull);
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
        try { body.addFixture((Fixture) null); throw new AssertionError("null fixture accepted"); }
        catch (ArgumentNullException expected) { check("fixture cannot be null".equals(expected.getMessage())); }
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
        List<Fixture> subList = changing.getFixtures().subList(0, 1);
        changing.addFixture(new Circle(4.0));
        try { subList.get(0); throw new AssertionError("missing fixture view sublist CME"); }
        catch (ConcurrentModificationException expected) { checks++; }
        Iterator<Fixture> protectedIterator = changing.protectedIterator();
        changing.addFixture(new Circle(3.0));
        try { protectedIterator.next(); throw new AssertionError("missing protected iterator CME"); }
        catch (ConcurrentModificationException expected) { checks++; }
        List<Fixture> protectedSubList = changing.protectedSubList();
        changing.addFixture(new Circle(5.0));
        try { protectedSubList.get(0); throw new AssertionError("missing protected sublist CME"); }
        catch (ConcurrentModificationException expected) { checks++; }
        List<Fixture> nestedView = changing.getFixtures().subList(0, 1).subList(0, 1);
        Iterator<Fixture> protectedSubIterator = changing.protectedSubList().iterator();
        changing.addFixture(new Circle(6.0));
        try { nestedView.get(0); throw new AssertionError("missing nested view CME"); }
        catch (ConcurrentModificationException expected) { checks++; }
        try { protectedSubIterator.next(); throw new AssertionError("missing protected sublist iterator CME"); }
        catch (ConcurrentModificationException expected) { checks++; }
        Body editable = new Body();
        editable.addFixture(new Circle(1.0));
        List<Fixture> editableSubList = editable.protectedSubList();
        Fixture inserted = new Fixture(new Circle(2.0));
        editableSubList.add(inserted);
        check(editableSubList.size() == 2 && editable.getFixture(1) == inserted);
        Iterator<Fixture> staleSubIterator = editableSubList.iterator();
        editableSubList.remove(0);
        try { staleSubIterator.next(); throw new AssertionError("missing edited sublist iterator CME"); }
        catch (ConcurrentModificationException expected) { checks++; }

        Body empty = new Body();
        check(empty.getFixture((Vector2)null) == null);
        check(empty.getFixtures((Vector2)null).isEmpty());
        check(empty.removeFixture((Vector2)null) == null);
        check(empty.removeFixtures((Vector2)null).isEmpty());
        check(!empty.contains(null));
        Body nullRejecting = new Body();
        nullRejecting.addFixture(new Circle(1.0));
        try { nullRejecting.getFixture((Vector2)null); throw new AssertionError("missing null point failure"); }
        catch (NullPointerException expected) { checks++; }
        try { nullRejecting.getFixtures((Vector2)null); throw new AssertionError("missing null point list failure"); }
        catch (NullPointerException expected) { checks++; }
        Body nullGet = nullPointBody();
        check(nullGet.getFixture((Vector2)null) == nullGet.getFixture(0));
        Body nullGetMany = nullPointBody();
        check(nullGetMany.getFixtures((Vector2)null).size() == 1);
        check(nullPointBody().contains(null));
        Body nullRemove = nullPointBody();
        check(nullRemove.removeFixture((Vector2)null) != null && nullRemove.getFixtureCount() == 0);
        Body nullRemoveMany = nullPointBody();
        check(nullRemoveMany.removeFixtures((Vector2)null).size() == 1 && nullRemoveMany.getFixtureCount() == 0);
        check(nullPointBody().updateRadiusWith(null) == 3.0);
        check(nullPointBody().createAABB((Transform)null).equals(new AABB(-3.0, -3.0, 3.0, 3.0)));
        AABB nullTransformResult = new AABB(0.0, 0.0, 0.0, 0.0);
        nullPointBody().computeAABB(null, nullTransformResult);
        check(nullTransformResult.equals(new AABB(-3.0, -3.0, 3.0, 3.0)));
        check(empty.updateRadiusWith(null) == 0.0);
        check(empty.createAABB((Transform)null).equals(new AABB(0.0, 0.0, 0.0, 0.0)));
        AABB emptyResult = new AABB(1.0, 1.0, 2.0, 2.0);
        empty.computeAABB(null, emptyResult);
        check(emptyResult.equals(new AABB(0.0, 0.0, 0.0, 0.0)));

        StringBuilder calls = new StringBuilder();
        check(AbstractCollisionItem.equals(new ObservedItem("A", calls), new ObservedItem("B", calls)));
        check(calls.toString().equals("Bbody,Abody,Bfixture,Afixture,"));

        AxisAlignedBounds bounds = new AxisAlignedBounds(4, 4);
        check(bounds.isOutside(new AABB(3, 3, 4, 4)));
        bounds.translate(3, 3);
        check(!bounds.isOutside(new AABB(3, 3, 4, 4)));
        check(bounds.copy().getBounds().equals(bounds.getBounds()));
        check(new BasicCollisionPair<>("a", "b").equals(new BasicCollisionPair<>("b", "a")));
        StringBuilder hashCalls = new StringBuilder();
        try {
            AbstractCollisionPair.getHashCode(new HashToken(hashCalls), null);
            throw new AssertionError("missing pair hash NPE");
        } catch (NullPointerException expected) { checks++; }
        check(hashCalls.toString().equals("first,"));
        Body queried = mutationBody();
        check(queried.getFixture(new Vector2(5.0, 5.0)) == null && queried.getFixtureCount() == 2);
        Body queriedMany = mutationBody();
        check(queriedMany.getFixtures(new Vector2(5.0, 5.0)).isEmpty() && queriedMany.getFixtureCount() == 2);
        Body contained = mutationBody();
        check(!contained.contains(new Vector2(5.0, 5.0)) && contained.getFixtureCount() == 2);
        Body radiusBody = mutationBody();
        radiusBody.updateRadius();
        check(radiusBody.getRotationDiscRadius() == 1.0 && radiusBody.getFixtureCount() == 2);
        Body aabbBody = mutationBody();
        check(aabbBody.createAABB().equals(new AABB(-1.0, -1.0, 1.0, 1.0)) && aabbBody.getFixtureCount() == 2);
        hashCalls.setLength(0);
        final StringBuilder fixtureHashCalls = hashCalls;
        Body hashBody = new Body() {
            @Override public int hashCode() { fixtureHashCalls.append("body,"); return 3; }
        };
        Fixture hashFixture = new Fixture(new Circle(1.0)) {
            @Override public int hashCode() { fixtureHashCalls.append("fixture,"); return 5; }
        };
        try {
            AbstractCollisionPair.getHashCode(hashBody, hashFixture, null, hashFixture);
            throw new AssertionError("missing body pair hash NPE");
        } catch (NullPointerException expected) { checks++; }
        check(hashCalls.toString().equals("body,fixture,"));
        hashCalls.setLength(0);
        try {
            new BasicCollisionPair<Object>(new HashToken(hashCalls), null).hashCode();
            throw new AssertionError("missing basic pair hash NPE");
        } catch (NullPointerException expected) { checks++; }
        check(hashCalls.toString().equals("first,"));
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
