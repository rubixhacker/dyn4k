import java.lang.reflect.InvocationTargetException;
import org.dyn4j.calibration.Bridge;

/** Executes the exact manifest-named upstream methods; originals retain all assertions. */
public final class UpstreamCases {
    private static final String[][] CASES = {
        {"collision.shapes.CircleCircleTest", "detectSat", "detectGjk"},
        {"dynamics.AbstractPhysicsBodyTest", "integrateVelocity", "integratePosition"},
        {"simulation.ForceSimulationTest", "applyTimed"},
        {"simulation.TorqueSimulationTest", "applyTimed"},
        {"collision.continuous.ConservativeAdvancementTest", "afterMidPoint", "beforeMidPoint"},
        {"simulation.AngleJointSimulationTest", "simpleLinkage", "withLimitsHitUpper", "withLimitsHitLower"},
        {"simulation.DistanceJointSimulationTest", "fixedDistance", "limits", "upperLimitWithSpring", "lowerLimitWithSpring", "limitsWithSpring", "springOnly", "springWithMaxForce"},
        {"simulation.FrictionJointSimulationTest", "simulationWithLargeForceTorqueMaximums", "simulationWithLowForceTorqueMaximums"},
        {"simulation.MotorJointSimulationTest", "simple"},
        {"simulation.PinJointSimulationTest", "fixedLinearVelocity", "noSpringDamper"},
        {"simulation.PrismaticJointSimulationTest", "noLimitsNoMotor", "limits", "motorWithAndWithoutLimits", "springOnly"},
        {"simulation.PulleyJointSimulationTest", "simpleLinkage", "withAndWithoutSlack"},
        {"simulation.RevoluteJointSimulationTest", "noLimitsNoMotor", "limits", "motorWithAndWithoutLimits"},
        {"simulation.WeldJointSimulationTest", "standard", "softConstraint", "softConstraintWithLimitsLower", "softConstraintWithLimitsUpper"},
        {"simulation.WheelJointSimulationTest", "noLimitsNoMotor", "limitsOnly", "springDamperWithLimits", "motorOnly"}
    };
    public static void run() throws ReflectiveOperationException {
        for (String[] row : CASES) {
            Class<?> cls = Class.forName("org.dyn4j." + row[0]);
            for (int i = 1; i < row.length; i++) {
                Object instance = cls.getConstructor().newInstance();
                Bridge.id = "U-" + cls.getSimpleName() + "." + row[i];
                if (!Capture.accepts(Bridge.id)) continue;
                Bridge.record("upstream-method-start", "058bf6d982a0fb89b54050f929f6ea9dae53b714", row[0], row[i]);
                try {
                    try { cls.getMethod("setup").invoke(instance); }
                    catch (NoSuchMethodException noSetup) { /* No @Before fixture in this source class. */ }
                    cls.getMethod(row[i]).invoke(instance);
                    Bridge.record("upstream-assertions", "PASS");
                } catch (InvocationTargetException e) {
                    Bridge.record("upstream-assertions", "FAIL", e.getCause().toString());
                    throw e;
                }
            }
        }
    }
}
