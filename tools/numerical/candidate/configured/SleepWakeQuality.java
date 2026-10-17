import java.nio.file.Path;
import java.util.Map;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.World;

public final class SleepWakeQuality {
    static int innerPerOuter(int outerHz) {
        return switch (outerHz) {
            case 30 -> 4;
            case 60 -> 2;
            case 120 -> 1;
            default -> throw new IllegalArgumentException("Outer Hz must be 30, 60 or 120");
        };
    }
    private static Body body(World<Body> world, double width, double height,
                             double y, boolean fixed) {
        Body body = new Body();
        BodyFixture fixture = body.addFixture(Geometry.createRectangle(width, height));
        fixture.setDensity(1);
        fixture.setFriction(0.5);
        fixture.setRestitution(0);
        body.setMass(fixed ? MassType.INFINITE : MassType.NORMAL);
        body.setLinearDamping(0);
        body.setAngularDamping(0);
        body.translate(0, y);
        world.addBody(body);
        return body;
    }
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--check-plan")) {
            for (int hz : new int[]{30, 60, 120}) {
                int group = innerPerOuter(hz), states = 0, endpoints = 0, actions = 0;
                for (int outer = 1; outer <= 600 * hz; outer++) {
                    for (int inner = 1; inner <= group; inner++) {
                        states++;
                        if (states == 36001) {
                            if (outer != 300 * hz + 1 || inner != 1) throw new AssertionError("Action mapping");
                            actions++;
                        }
                        if (inner == group) endpoints++;
                    }
                }
                if (states != 72000 || endpoints != 600 * hz || actions != 1) throw new AssertionError("Grouping");
                System.out.println("PLAN hz=" + hz + " states=" + states + " endpoints=" + endpoints + " actions=" + actions);
            }
            try { innerPerOuter(90); throw new AssertionError("Invalid Hz accepted"); }
            catch (IllegalArgumentException expected) { System.out.println("PLAN invalid Hz rejected; no physics executed"); }
            return;
        }
        if (args.length != 3) throw new IllegalArgumentException("Usage: SleepWakeQuality NEW_OUTPUT_DIRECTORY OUTER_HZ REPETITION; or --check-plan");
        int hz = Integer.parseInt(args[1]), repetition = Integer.parseInt(args[2]);
        innerPerOuter(hz);
        if (repetition != 1 && repetition != 2) throw new IllegalArgumentException("Repetition must be 1 or 2");
        World<Body> world = new World<>();
        world.setGravity(0, -9.8);
        world.getSettings().setLinearTolerance(1.0 / 4096.0);
        world.getSettings().setPositionConstraintSolverIterations(8);
        body(world, 20, 0.5, -0.25, true);
        Body target = body(world, 1, 1, 0.51, false);
        boolean[] prerequisite = {true};
        Capture.open(Path.of(args[0]), "");
        try {
            Capture.runGrouped("Q-sleep-wake-outer" + hz + "-repeat" + repetition, world, hz, repetition, step -> {
                int completed = step - 1;
                if (completed >= 299 * 120 && completed <= 300 * 120) prerequisite[0] &= target.isAtRest();
                if (step == 36001) {
                    Capture.record(Capture.current, "before-wake", Capture.state(world, 1.0 / 120.0, false));
                    Capture.action("impulse=(1,0) at center; sleepingBefore=" + target.isAtRest()
                        + "; precedingSecondAsleep=" + prerequisite[0]);
                    target.applyImpulse(new Vector2(1, 0), target.getWorldCenter());
                    Capture.record(Capture.current, "after-wake", Capture.state(world, 1.0 / 120.0, false));
                    Capture.query(Capture.current, Map.of("sleepPrerequisite", prerequisite[0],
                        "awakeImmediatelyAfterImpulse", !target.isAtRest(), "actionStep", step));
                }
            });
        } finally {
            Capture.close();
        }
    }
}
