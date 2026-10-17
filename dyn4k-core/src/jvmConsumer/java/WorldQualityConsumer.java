import java.util.Locale;

import org.dyn4j.dynamics.Body;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Rectangle;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.World;

public final class WorldQualityConsumer {
    private static void run(int rate, boolean configured) {
        World<Body> world = new World<>();
        double h = configured ? 1.0 / 120.0 : 1.0 / rate;
        int group = configured ? 120 / rate : 1;
        world.getSettings().setStepFrequency(h);
        if (configured) {
            world.getSettings().setLinearTolerance(1.0 / 4096.0);
            world.getSettings().setPositionConstraintSolverIterations(8);
        }
        Body floor = new Body();
        floor.addFixture(Geometry.createRectangle(20.0, 1.0));
        floor.translate(0.0, -0.5);
        Body box = new Body();
        Rectangle shape = Geometry.createSquare(1.0);
        box.addFixture(shape);
        box.setMass(MassType.NORMAL);
        box.translate(0.0, 2.0);
        world.addBody(floor);
        world.addBody(box);

        double deepestPenetration = 0.0;
        int contactStates = 0;
        for (int outer = 0; outer < rate * 5; outer++) {
            for (int inner = 0; inner < group; inner++) {
                world.step(1, h);
                double minimumY = Double.POSITIVE_INFINITY;
                for (Vector2 vertex : shape.getVertices()) {
                    double y = box.getTransform().getTransformed(vertex).y;
                    if (y < minimumY) minimumY = y;
                }
                deepestPenetration = Math.max(deepestPenetration, Math.max(0.0, -minimumY));
                if (!world.getContacts(box).isEmpty()) contactStates++;
            }
        }
        if (!Double.isFinite(deepestPenetration) || !Double.isFinite(box.getTransform().getTranslationY())) {
            throw new AssertionError("non-finite quality state");
        }
        System.out.printf(Locale.ROOT, "WORLD_QUALITY,%s,%d,%.17g,%.17g,%.17g,%d,%b%n",
                configured ? "configured" : "default", rate, deepestPenetration,
                box.getTransform().getTranslationY(), box.getLinearVelocity().y,
                contactStates, box.isAtRest());
    }

    public static void main(String[] args) {
        for (int rate : new int[] {30, 60, 120}) {
            run(rate, false);
            run(rate, true);
        }
    }
}
