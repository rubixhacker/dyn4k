import java.util.Arrays;
import java.util.List;
import java.util.Locale;

import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.Settings;
import org.dyn4j.dynamics.TimeStep;
import org.dyn4j.dynamics.joint.AngleJoint;
import org.dyn4j.dynamics.joint.DistanceJoint;
import org.dyn4j.dynamics.joint.FrictionJoint;
import org.dyn4j.dynamics.joint.Joint;
import org.dyn4j.dynamics.joint.MotorJoint;
import org.dyn4j.dynamics.joint.PinJoint;
import org.dyn4j.dynamics.joint.PrismaticJoint;
import org.dyn4j.dynamics.joint.PulleyJoint;
import org.dyn4j.dynamics.joint.RevoluteJoint;
import org.dyn4j.dynamics.joint.WeldJoint;
import org.dyn4j.dynamics.joint.WheelJoint;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Vector2;

public class JointConsumer {
    private static final class ExposedDistance extends DistanceJoint<Body> {
        ExposedDistance(Body a, Body b, Vector2 anchor1, Vector2 anchor2) {
            super(a, b, anchor1, anchor2);
        }

        double restDistanceFromProtectedField() {
            return this.restDistance;
        }

        double unmodifiedRestDistance() {
            return super.getRestDistance();
        }

        @Override
        public double getRestDistance() {
            return super.getRestDistance() + 1.0;
        }
    }

    private static Body body() {
        Body body = new Body();
        body.addFixture(Geometry.createCircle(0.5), 1.0, 0.2, 0.0);
        body.setMass(MassType.NORMAL);
        return body;
    }

    public static void main(String[] args) {
        Body a = body();
        Body b = body();
        b.translate(1.0, 0.0);
        Vector2 first = new Vector2(0.0, 0.0);
        Vector2 second = new Vector2(1.0, 0.0);

        AngleJoint<Body> angle = new AngleJoint<>(a, b);
        angle.setLimits(-0.5, 0.5);
        angle.setLimitsEnabled(true);

        DistanceJoint<Body> distance = new DistanceJoint<>(a, b, first, second);
        distance.setSpringFrequency(8.0);
        distance.setSpringDampingRatio(0.3);
        distance.setSpringEnabled(true);
        distance.setSpringDamperEnabled(true);
        distance.setRestDistance(0.5);
        distance.setLimits(0.5, 0.75);
        distance.setLimitsEnabled(true);

        PinJoint<Body> pin = new PinJoint<>(a, first);
        pin.setSpringFrequency(8.0);
        pin.setSpringEnabled(true);

        PrismaticJoint<Body> prismatic = new PrismaticJoint<>(a, b, first, new Vector2(1.0, 0.0));
        prismatic.setMotorEnabled(true);
        prismatic.setMotorSpeed(1.0);
        prismatic.setMaximumMotorForce(10.0);
        prismatic.setMaximumMotorForceEnabled(true);
        prismatic.setLimits(-0.5, 0.5);
        prismatic.setLimitsEnabled(true);

        PulleyJoint<Body> pulley = new PulleyJoint<>(a, b,
                new Vector2(0.0, 2.0), new Vector2(1.0, 2.0), first, second);
        pulley.setRatio(1.5);

        RevoluteJoint<Body> revolute = new RevoluteJoint<>(a, b, first);
        revolute.setMotorEnabled(true);
        revolute.setMotorSpeed(1.0);
        revolute.setMaximumMotorTorque(10.0);
        revolute.setMaximumMotorTorqueEnabled(true);
        revolute.setLimits(-0.5, 0.5);
        revolute.setLimitsEnabled(true);

        WeldJoint<Body> weld = new WeldJoint<>(a, b, first);
        weld.setSpringFrequency(8.0);
        weld.setSpringEnabled(true);

        WheelJoint<Body> wheel = new WheelJoint<>(a, b, first, new Vector2(1.0, 0.0));
        wheel.setSpringFrequency(8.0);
        wheel.setSpringEnabled(true);
        wheel.setMotorEnabled(true);
        wheel.setMotorSpeed(1.0);

        List<Joint<Body>> joints = Arrays.asList(
                angle, distance, new FrictionJoint<>(a, b, first), new MotorJoint<>(a, b), pin,
                prismatic, pulley, revolute, weld, wheel);
        TimeStep step = new TimeStep(1.0 / 60.0);
        Settings settings = new Settings();
        for (Joint<Body> joint : joints) {
            if (joint.getBodyCount() < 1 || joint.getBodies().size() != joint.getBodyCount()) {
                throw new AssertionError("body count: " + joint.getClass().getSimpleName());
            }
            if (joint.getBody(0) != a || !joint.isMember(a)) {
                throw new AssertionError("body identity: " + joint.getClass().getSimpleName());
            }
            joint.initializeConstraints(step, settings);
            joint.solveVelocityConstraints(step, settings);
            joint.solvePositionConstraints(step, settings);
            Vector2 force = joint.getReactionForce(step.getInverseDeltaTime());
            double torque = joint.getReactionTorque(step.getInverseDeltaTime());
            if (!Double.isFinite(force.x) || !Double.isFinite(force.y) || !Double.isFinite(torque)) {
                throw new AssertionError("non-finite reaction: " + joint.getClass().getSimpleName());
            }
            System.out.printf(Locale.ROOT, "JOINT_TRACE,%s,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g%n",
                    joint.getClass().getSimpleName(), force.x, force.y, torque,
                    a.getWorldCenter().x, a.getWorldCenter().y, a.getTransform().getRotationAngle());
            if (joint.copy() == joint) {
                throw new AssertionError("copy identity: " + joint.getClass().getSimpleName());
            }
        }

        ExposedDistance exposed = new ExposedDistance(a, b, first, second);
        DistanceJoint<Body> dispatched = exposed;
        if (exposed.restDistanceFromProtectedField() != exposed.unmodifiedRestDistance()
                || dispatched.getRestDistance() != exposed.unmodifiedRestDistance() + 1.0) {
            throw new AssertionError("protected state");
        }
        try {
            distance.getBodies().clear();
            throw new AssertionError("mutable body view");
        } catch (UnsupportedOperationException expected) {
        }
        try {
            distance.getBodyIterator().remove();
            throw new AssertionError("mutable body iterator");
        } catch (UnsupportedOperationException expected) {
        }
        try {
            distance.getBody(-1);
            throw new AssertionError("negative body index");
        } catch (IndexOutOfBoundsException expected) {
        }
        try {
            new DistanceJoint<Body>(null, b, first, second);
            throw new AssertionError("null body accepted");
        } catch (NullPointerException expected) {
        }
        System.out.println("JointConsumer OK: " + joints.size() + " concrete joints");
    }
}
