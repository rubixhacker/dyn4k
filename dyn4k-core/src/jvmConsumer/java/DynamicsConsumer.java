import java.util.List;
import java.util.Iterator;
import java.util.ConcurrentModificationException;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.dynamics.Force;
import org.dyn4j.dynamics.Torque;
import org.dyn4j.dynamics.TimeStep;
import org.dyn4j.dynamics.Settings;
import org.dyn4j.collision.FixtureModificationHandler;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Mass;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.geometry.AABB;
import org.dyn4j.exception.ArgumentNullException;

public class DynamicsConsumer {
    private static final class ProbeBody extends Body {
        int fixtureDispatch;
        int massDispatch;
        int wakeDispatch;
        int centerCalls;

        @Override
        public Vector2 getLocalCenter() {
            centerCalls++;
            return super.getLocalCenter();
        }

        @Override
        public BodyFixture addFixture(Convex shape, double density, double friction, double restitution) {
            fixtureDispatch++;
            return super.addFixture(shape, density, friction, restitution);
        }

        @Override
        public ProbeBody setMass(MassType type) {
            massDispatch++;
            super.setMass(type);
            return this;
        }

        @Override
        public void setAtRest(boolean value) {
            wakeDispatch++;
            super.setAtRest(value);
        }

        List<Force> forces() { return forces; }
        List<Torque> torques() { return torques; }
        Vector2 forceField() { return force; }
        ProbeBody copyProbe() { return new ProbeBody(this); }
        private ProbeBody(ProbeBody other) { super(other); }
        ProbeBody() { super(); }
    }

    private static final class PersistentForce extends Force {
        double lastElapsed;
        PersistentForce(Vector2 force) { super(force); }
        @Override public boolean isComplete(double elapsed) { lastElapsed = elapsed; return false; }
    }

    private static final class OverriddenStep extends TimeStep {
        OverriddenStep(double dt) { super(dt); }
        @Override public double getDeltaTime() { return 10.0; }
    }

    private static final class OverriddenSettings extends Settings {
        int setCalls;
        @Override public void set(Settings settings) { setCalls++; super.set(settings); }
    }

    private static final class ThresholdSettings extends Settings {
        final StringBuilder calls = new StringBuilder();
        @Override public double getMaximumAtRestLinearVelocitySquared() {
            calls.append('L');
            return super.getMaximumAtRestLinearVelocitySquared();
        }
        @Override public double getMaximumAtRestAngularVelocity() {
            calls.append('A');
            return super.getMaximumAtRestAngularVelocity();
        }
    }

    private static final class SpecialFixture extends BodyFixture {
        int massCalls;
        SpecialFixture(Convex shape) { super(shape); }
        @Override public Mass createMass() { massCalls++; return super.createMass(); }
    }

    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        ProbeBody body = new ProbeBody();
        List<BodyFixture> fixtures = body.getFixtures();
        BodyFixture fixture = body.addFixture(new Circle(1.0));
        require(body.fixtureDispatch == 1, "fixture overload dispatch");
        require(fixtures.get(0) == fixture, "live fixture view");
        body.setMass(MassType.NORMAL);
        body.updateMass();
        require(body.massDispatch == 2, "mass dispatch");
        PersistentForce force = new PersistentForce(new Vector2(2.0, 3.0));
        body.applyForce(force);
        require(body.forces().get(0) == force, "force identity");
        force.getForce().x = 4.0;
        require(body.getAccumulatedForce().x == 4.0, "force mutation");
        body.integrateVelocity(new Vector2(), new TimeStep(0.5), new Settings());
        require(force.lastElapsed == 0.5, "force callback");
        require(body.forces().get(0) == force, "persistent force");
        require(body.getForce().x == 4.0, "integrated force");
        require(body.forceField() != body.getForce(), "force snapshot");
        body.setAtRest(true);
        body.applyImpulse(new Vector2(1.0, 0.0));
        require(!body.isAtRest(), "impulse wake");
        require(body.wakeDispatch > 0, "wake dispatch");
        require(body.copyProbe().getFixture(0) != fixture, "fixture copy");
        Iterator<BodyFixture> fixtureIterator = fixtures.iterator();
        body.addFixture(new Circle(0.5));
        try {
            fixtureIterator.next();
            throw new AssertionError("fixture iterator did not fail fast");
        } catch (ConcurrentModificationException expected) {
            require(fixtures.size() == 2, "fixture view did not remain live");
        }
        ProbeBody fixtureBody = new ProbeBody();
        SpecialFixture special = new SpecialFixture(new Circle(1.0));
        fixtureBody.addFixture(special);
        fixtureBody.setMass(MassType.NORMAL);
        require(special.massCalls == 1, "fixture createMass dispatch");
        fixtureBody.setAtRest(true);
        fixtureBody.setFixtureModificationHandler(new FixtureModificationHandler<BodyFixture>() {
            @Override public void onFixtureAdded(BodyFixture added) {
                require(fixtureBody.isAtRest(), "fixture callback must precede wake");
            }
            @Override public void onFixtureRemoved(BodyFixture removed) { }
            @Override public void onAllFixturesRemoved() { }
        });
        fixtureBody.addFixture(new Circle(0.5));
        require(!fixtureBody.isAtRest(), "fixture addition wake");
        ProbeBody timingBody = new ProbeBody();
        timingBody.addFixture(new Circle(1.0));
        timingBody.setMass(MassType.NORMAL);
        timingBody.applyForce(new Vector2(1.0, 0.0));
        timingBody.integrateVelocity(new Vector2(), new OverriddenStep(0.25), new Settings());
        require(timingBody.getLinearVelocity().x < 1.0, "timestep field access");
        OverriddenSettings settings = new OverriddenSettings();
        settings.reset();
        require(settings.setCalls == 0, "settings reset dispatch");
        ThresholdSettings thresholds = new ThresholdSettings();
        timingBody.setLinearVelocity(10.0, 0.0);
        timingBody.updateAtRestTime(new TimeStep(0.1), thresholds);
        require("LA".contentEquals(thresholds.calls), "rest threshold getter order");
        ProbeBody empty = new ProbeBody();
        empty.integrateVelocity(null, null, null);
        AABB sweep = new AABB(1.0, 1.0, 2.0, 2.0);
        empty.computeSweptAABB(null, null, sweep);
        require(sweep.getWidth() == 0.0, "empty swept bounds");
        ProbeBody swept = new ProbeBody();
        swept.addFixture(new Circle(1.0));
        try {
            swept.computeSweptAABB(swept.getTransform(), null, sweep);
            throw new AssertionError("null final transform accepted");
        } catch (NullPointerException expected) {
            require(swept.centerCalls == 2, "swept bounds evaluation order");
        }
        try {
            empty.addFixture((Convex) null, 1.0, 0.2, 0.0);
            throw new AssertionError("null shape accepted");
        } catch (ArgumentNullException expected) {
            require("convex cannot be null".equals(expected.getMessage()), "null shape diagnostic");
        }
        System.out.println("DYNAMICS_CONSUMER_OK");
    }
}
