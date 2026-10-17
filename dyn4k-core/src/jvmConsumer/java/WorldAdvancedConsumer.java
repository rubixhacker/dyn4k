import java.util.List;
import java.util.Locale;

import org.dyn4j.collision.continuous.ConservativeAdvancement;
import org.dyn4j.collision.continuous.TimeOfImpact;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.Settings;
import org.dyn4j.dynamics.TimeStep;
import org.dyn4j.dynamics.contact.ContactConstraint;
import org.dyn4j.dynamics.contact.SequentialImpulses;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.ContactCollisionData;
import org.dyn4j.world.World;
import org.dyn4j.world.listener.ContactListenerAdapter;
import org.dyn4j.world.listener.TimeOfImpactListenerAdapter;

public final class WorldAdvancedConsumer {
    private static final class CountingDetector extends ConservativeAdvancement {
        int calls;

        @Override
        public boolean getTimeOfImpact(Convex convex1, Transform transform1, Vector2 dp1, double da1,
                Convex convex2, Transform transform2, Vector2 dp2, double da2,
                double t1, double t2, TimeOfImpact toi) {
            calls++;
            return super.getTimeOfImpact(convex1, transform1, dp1, da1,
                    convex2, transform2, dp2, da2, t1, t2, toi);
        }
    }

    private static final class CountingSolver extends SequentialImpulses<Body> {
        int calls;

        @Override
        public void initialize(List<ContactConstraint<Body>> constraints, TimeStep step, Settings settings) {
            calls++;
            super.initialize(constraints, step, settings);
        }
    }

    public static void main(String[] args) {
        World<Body> world = new World<>();
        world.setGravity(0.0, 0.0);
        Body wall = new Body();
        wall.addFixture(Geometry.createRectangle(0.5, 20.0));
        wall.translate(0.0, 0.0);
        Body bullet = new Body();
        bullet.addFixture(Geometry.createCircle(0.25));
        bullet.setMass(MassType.NORMAL);
        bullet.setBullet(true);
        bullet.translate(-5.0, 0.0);
        bullet.setLinearVelocity(600.0, 0.0);
        CountingDetector detector = new CountingDetector();
        CountingSolver solver = new CountingSolver();
        final int[] callbacks = new int[4];
        world.setTimeOfImpactDetector(detector);
        world.setContactConstraintSolver(solver);
        world.addTimeOfImpactListener(new TimeOfImpactListenerAdapter<Body>() {
            @Override
            public boolean collision(Body body1, Body body2, TimeOfImpact toi) {
                callbacks[0]++;
                return true;
            }
        });
        world.addContactListener(new ContactListenerAdapter<Body>() {
            @Override
            public void collision(ContactCollisionData<Body> collision) {
                callbacks[1]++;
                if (world.getBodyCount() != 2 || !world.containsBody(bullet)) {
                    throw new AssertionError("callback re-entry");
                }
            }

            @Override
            public void begin(ContactCollisionData<Body> collision, org.dyn4j.dynamics.contact.Contact contact) {
                callbacks[2]++;
            }

            @Override
            public void postSolve(ContactCollisionData<Body> collision, org.dyn4j.dynamics.contact.SolvedContact contact) {
                callbacks[3]++;
            }
        });
        world.addBody(wall);
        world.addBody(bullet);
        world.step(4);
        double x = bullet.getTransform().getTranslationX();
        if (detector.calls < 1 || callbacks[0] < 1 || x > 0.5) {
            throw new AssertionError("CCD journey: " + detector.calls + ", " + callbacks[0] + ", " + x);
        }
        if (callbacks[1] < 1 || callbacks[2] < 1 || callbacks[3] < 1 || solver.calls < 1) {
            throw new AssertionError("contact solver or callback journey");
        }
        System.out.printf(Locale.ROOT, "WORLD_CCD_TRACE,%.17g,%d,%d,%d,%d,%d,%d%n",
                x, detector.calls, solver.calls, callbacks[0], callbacks[1], callbacks[2], callbacks[3]);
        System.out.println("WorldAdvancedConsumer OK");
    }
}
