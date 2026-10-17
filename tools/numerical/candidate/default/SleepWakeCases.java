import java.nio.file.Path;
import java.util.Map;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.World;

public final class SleepWakeCases {
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--help")) {
            System.out.println("Usage: SleepWakeCases NEW_OUTPUT_DIRECTORY");
            return;
        }
        if (args.length != 1) throw new IllegalArgumentException("Use --help");
        Capture.open(Path.of(args[0]), "");
        try {
            for (int hz : new int[]{30, 60, 120}) run(hz);
        } finally {
            Capture.close();
        }
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

    private static void run(int hz) {
        World<Body> world = new World<>();
        world.setGravity(0, -9.8);
        body(world, 20, 0.5, -0.25, true);
        Body target = body(world, 1, 1, 0.51, false);
        boolean[] prerequisite = {true};
        Capture.run("S-sleep-wake-hz" + hz, world, 600 * hz, 1.0 / hz, 1, 0, 0, step -> {
            int completed = step - 1;
            if (completed >= 299 * hz && completed <= 300 * hz) {
                prerequisite[0] &= target.isAtRest();
            }
            if (step == 300 * hz + 1) {
                Capture.record(Capture.current, "before-wake", Capture.state(world, 1.0 / hz, false));
                Capture.action("impulse=(1,0) at center; sleepingBefore=" + target.isAtRest()
                    + "; precedingSecondAsleep=" + prerequisite[0]);
                target.applyImpulse(new Vector2(1, 0), target.getWorldCenter());
                Capture.record(Capture.current, "after-wake", Capture.state(world, 1.0 / hz, false));
                Capture.query(Capture.current, Map.of("sleepPrerequisite", prerequisite[0],
                    "awakeImmediatelyAfterImpulse", !target.isAtRest(), "actionStep", step));
            }
        });
    }
}
