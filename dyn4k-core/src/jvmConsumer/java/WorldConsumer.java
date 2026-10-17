import java.util.Iterator;
import java.util.List;
import java.util.Locale;

import org.dyn4j.collision.CollisionItem;
import org.dyn4j.collision.CollisionPair;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.dynamics.TimeStep;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.MassType;
import org.dyn4j.world.PhysicsWorld;
import org.dyn4j.world.World;
import org.dyn4j.world.WorldCollisionData;
import org.dyn4j.world.listener.ContactListenerAdapter;
import org.dyn4j.world.listener.StepListenerAdapter;
import org.dyn4j.dynamics.contact.Contact;
import org.dyn4j.dynamics.contact.SolvedContact;

public final class WorldConsumer {
    private static final class CountingWorld extends World<Body> {
        int created;

        @Override
        protected WorldCollisionData<Body> createCollisionData(CollisionPair<CollisionItem<Body, BodyFixture>> pair) {
            created++;
            return super.createCollisionData(pair);
        }
    }

    private static Body body(double y, boolean dynamic) {
        Body body = new Body();
        body.addFixture(Geometry.createSquare(1.0));
        body.translate(0.0, y);
        if (dynamic) body.setMass(MassType.NORMAL);
        return body;
    }

    public static void main(String[] args) {
        final CountingWorld world = new CountingWorld();
        final Body floor = new Body();
        floor.addFixture(Geometry.createRectangle(20.0, 1.0));
        floor.translate(0.0, -0.5);
        final Body box = body(3.0, true);
        final StringBuilder events = new StringBuilder();
        final int[] counts = new int[4];

        world.addStepListener(new StepListenerAdapter<Body>() {
            @Override
            public void begin(TimeStep step, PhysicsWorld<Body, ?> source) {
                if (counts[0] == 0) events.append('B');
                counts[0]++;
            }

            @Override
            public void end(TimeStep step, PhysicsWorld<Body, ?> source) {
                if (counts[1] == 0) events.append('E');
                counts[1]++;
            }
        });
        world.addContactListener(new ContactListenerAdapter<Body>() {
            @Override
            public void begin(org.dyn4j.world.ContactCollisionData<Body> collision, Contact contact) {
                if (counts[2] == 0) events.append('C');
                counts[2]++;
            }

            @Override
            public void postSolve(org.dyn4j.world.ContactCollisionData<Body> collision, SolvedContact contact) {
                counts[3]++;
            }
        });

        List<Body> view = world.getBodies();
        world.addBody(floor);
        world.addBody(box);
        if (view.size() != 2 || view.get(1) != box) throw new AssertionError("live body view");
        try {
            view.clear();
            throw new AssertionError("mutable body view");
        } catch (UnsupportedOperationException expected) {
        }

        world.step(120);
        if (counts[0] != 120 || counts[1] != 120 || counts[2] < 1 || counts[3] < 1) {
            throw new AssertionError("missing step or contact callbacks");
        }
        if (world.created < 1 || box.getTransform().getTranslationY() >= 3.0) {
            throw new AssertionError("factory or falling body");
        }
        Iterator<Body> iterator = world.getBodyIterator();
        while (iterator.hasNext()) {
            if (iterator.next() == box) iterator.remove();
        }
        if (view.size() != 1 || world.containsBody(box)) throw new AssertionError("iterator removal");
        try {
            world.addBody(null);
            throw new AssertionError("null body accepted");
        } catch (NullPointerException expected) {
        }
        try {
            world.getBody(-1);
            throw new AssertionError("negative body index accepted");
        } catch (IndexOutOfBoundsException expected) {
        }
        try {
            world.getBodyIterator().remove();
            throw new AssertionError("iterator removal before next accepted");
        } catch (IllegalStateException expected) {
        }

        System.out.printf(Locale.ROOT, "WORLD_TRACE,%.17g,%.17g,%d,%d,%d,%d,%s%n",
                box.getTransform().getTranslationY(), box.getLinearVelocity().y,
                counts[0], counts[1], counts[2], counts[3], events);
        System.out.println("WorldConsumer OK");
    }
}
