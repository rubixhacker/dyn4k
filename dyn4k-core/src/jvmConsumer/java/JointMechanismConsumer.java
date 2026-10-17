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
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Vector2;

public class JointMechanismConsumer {
    private static final class Pair {
        final Body a = body(-0.4, 0.1, 0.2, 0.4, -0.2, 0.7);
        final Body b = body(0.9, 0.4, -0.3, -0.3, 0.5, -0.4);
    }

    private static Body body(double x, double y, double angle, double vx, double vy, double omega) {
        Body body = new Body();
        body.addFixture(new Circle(0.25));
        body.setMass(MassType.NORMAL);
        body.translate(x, y);
        body.rotate(angle);
        body.setLinearVelocity(vx, vy);
        body.setAngularVelocity(omega);
        body.setLinearDamping(0.0);
        body.setAngularDamping(0.0);
        return body;
    }

    private static Vector2 midpoint(Pair pair) {
        return pair.a.getWorldCenter().sum(pair.b.getWorldCenter()).multiply(0.5);
    }

    private static void trace(String name, Pair pair, Joint<Body> joint) {
        Settings settings = new Settings();
        TimeStep step = new TimeStep(1.0 / 60.0);
        for (int i = 0; i < 12; i++) {
            if (i > 0) step.update(i % 3 == 0 ? 1.0 / 120.0 : 1.0 / 60.0);
            joint.initializeConstraints(step, settings);
            for (int j = 0; j < 8; j++) joint.solveVelocityConstraints(step, settings);
            pair.a.integratePosition(step, settings);
            pair.b.integratePosition(step, settings);
            for (int j = 0; j < 4; j++) joint.solvePositionConstraints(step, settings);
            Vector2 force = joint.getReactionForce(step.getInverseDeltaTime());
            double torque = joint.getReactionTorque(step.getInverseDeltaTime());
            double ax = pair.a.getWorldCenter().x;
            double ay = pair.a.getWorldCenter().y;
            double ar = pair.a.getTransform().getRotationAngle();
            double bx = pair.b.getWorldCenter().x;
            double by = pair.b.getWorldCenter().y;
            double br = pair.b.getTransform().getRotationAngle();
            if (!Double.isFinite(force.x) || !Double.isFinite(force.y) || !Double.isFinite(torque)
                    || !Double.isFinite(ax) || !Double.isFinite(ay) || !Double.isFinite(ar)
                    || !Double.isFinite(bx) || !Double.isFinite(by) || !Double.isFinite(br)) {
                throw new AssertionError("nonfinite " + name + " step " + i);
            }
            System.out.printf(Locale.ROOT,
                    "JOINT_MECHANISM,%s,%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g%n",
                    name, i, force.x, force.y, torque, ax, ay, ar, bx, by, br);
        }
    }

    public static void main(String[] args) {
        Pair pair = new Pair();
        AngleJoint<Body> angle = new AngleJoint<>(pair.a, pair.b);
        angle.setRatio(1.4);
        angle.setLimits(-0.2, 0.2);
        angle.setLimitsEnabled(true);
        trace("angle-ratio-limit", pair, angle);

        pair = new Pair();
        DistanceJoint<Body> distance = new DistanceJoint<>(pair.a, pair.b,
                pair.a.getWorldCenter(), pair.b.getWorldCenter());
        distance.setRestDistance(0.8);
        distance.setSpringFrequency(8.0);
        distance.setSpringDampingRatio(0.3);
        distance.setSpringEnabled(true);
        distance.setSpringDamperEnabled(true);
        distance.setMaximumSpringForce(12.0);
        distance.setMaximumSpringForceEnabled(true);
        distance.setLimits(0.5, 1.1);
        distance.setLimitsEnabled(true);
        trace("distance-spring-limit-cap", pair, distance);

        pair = new Pair();
        FrictionJoint<Body> friction = new FrictionJoint<>(pair.a, pair.b, midpoint(pair));
        friction.setMaximumForce(5.0);
        friction.setMaximumTorque(2.0);
        trace("friction-cap", pair, friction);

        pair = new Pair();
        MotorJoint<Body> motor = new MotorJoint<>(pair.a, pair.b);
        motor.setLinearTarget(new Vector2(0.2, 0.5));
        motor.setAngularTarget(0.4);
        motor.setCorrectionFactor(0.4);
        motor.setMaximumForce(10.0);
        motor.setMaximumTorque(4.0);
        trace("motor-force-torque-cap", pair, motor);

        pair = new Pair();
        PinJoint<Body> pin = new PinJoint<>(pair.a, pair.a.getWorldCenter());
        pin.setTarget(new Vector2(0.2, 0.7));
        pin.setSpringStiffness(30.0);
        pin.setSpringEnabled(true);
        pin.setSpringDampingRatio(0.2);
        pin.setSpringDamperEnabled(true);
        pin.setMaximumSpringForce(8.0);
        pin.setMaximumSpringForceEnabled(true);
        trace("pin-stiffness-damper-cap", pair, pin);

        pair = new Pair();
        PrismaticJoint<Body> prismatic = new PrismaticJoint<>(pair.a, pair.b,
                midpoint(pair), new Vector2(1.0, 0.2));
        prismatic.setLimits(-0.5, 0.5);
        prismatic.setLimitsEnabled(true);
        prismatic.setMotorEnabled(true);
        prismatic.setMotorSpeed(0.8);
        prismatic.setMaximumMotorForce(6.0);
        prismatic.setMaximumMotorForceEnabled(true);
        prismatic.setSpringFrequency(4.0);
        prismatic.setSpringEnabled(true);
        prismatic.setSpringDampingRatio(0.2);
        prismatic.setSpringDamperEnabled(true);
        trace("prismatic-motor-spring-limit", pair, prismatic);

        pair = new Pair();
        PulleyJoint<Body> pulley = new PulleyJoint<>(pair.a, pair.b,
                new Vector2(-0.4, 2.0), new Vector2(0.9, 2.0),
                pair.a.getWorldCenter(), pair.b.getWorldCenter());
        pulley.setRatio(1.3);
        pulley.setSlackEnabled(true);
        trace("pulley-ratio-slack", pair, pulley);

        pair = new Pair();
        RevoluteJoint<Body> revolute = new RevoluteJoint<>(pair.a, pair.b, midpoint(pair));
        revolute.setLimits(-0.2, 0.2);
        revolute.setLimitsEnabled(true);
        revolute.setMotorEnabled(true);
        revolute.setMotorSpeed(0.5);
        revolute.setMaximumMotorTorque(5.0);
        revolute.setMaximumMotorTorqueEnabled(true);
        trace("revolute-motor-limit", pair, revolute);

        pair = new Pair();
        WeldJoint<Body> weld = new WeldJoint<>(pair.a, pair.b, midpoint(pair));
        weld.setLimits(-0.2, 0.2);
        weld.setLimitsEnabled(true);
        weld.setSpringStiffness(40.0);
        weld.setSpringEnabled(true);
        weld.setSpringDampingRatio(0.2);
        weld.setSpringDamperEnabled(true);
        weld.setMaximumSpringTorque(5.0);
        weld.setMaximumSpringTorqueEnabled(true);
        trace("weld-stiffness-limit-cap", pair, weld);

        pair = new Pair();
        WheelJoint<Body> wheel = new WheelJoint<>(pair.a, pair.b,
                midpoint(pair), new Vector2(1.0, 0.0));
        wheel.setLimits(-0.5, 0.5);
        wheel.setLimitsEnabled(true);
        wheel.setMotorEnabled(true);
        wheel.setMotorSpeed(0.6);
        wheel.setMaximumMotorTorque(4.0);
        wheel.setMaximumMotorTorqueEnabled(true);
        wheel.setSpringFrequency(5.0);
        wheel.setSpringEnabled(true);
        wheel.setSpringDampingRatio(0.2);
        wheel.setSpringDamperEnabled(true);
        wheel.setMaximumSpringForce(5.0);
        wheel.setMaximumSpringForceEnabled(true);
        trace("wheel-motor-spring-limit", pair, wheel);

        System.out.println("JointMechanismConsumer OK: 10 mechanisms, 120 states");
    }
}
