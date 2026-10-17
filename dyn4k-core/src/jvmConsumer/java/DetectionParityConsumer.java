import java.util.Random;
import org.dyn4j.collision.continuous.ConservativeAdvancement;
import org.dyn4j.collision.continuous.TimeOfImpact;
import org.dyn4j.collision.manifold.ClippingManifoldSolver;
import org.dyn4j.collision.manifold.Manifold;
import org.dyn4j.collision.narrowphase.Gjk;
import org.dyn4j.collision.narrowphase.Penetration;
import org.dyn4j.collision.narrowphase.Raycast;
import org.dyn4j.collision.narrowphase.Sat;
import org.dyn4j.collision.narrowphase.Separation;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.Ray;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector2;

public final class DetectionParityConsumer {
    private static void print(String key, boolean hit, double... values) {
        StringBuilder row = new StringBuilder(key).append('\t').append(hit);
        if (hit) for (double value : values) row.append('\t').append(value);
        System.out.println(row);
    }

    public static void main(String[] args) {
        Convex[] shapes = {
            Geometry.createCircle(0.7), Geometry.createRectangle(1.1, 0.8),
            Geometry.createSquare(1.3), Geometry.createTriangleAtOrigin(
                new Vector2(-0.8, -0.4), new Vector2(0.7, -0.5), new Vector2(0.1, 0.9))
        };
        Gjk gjk = new Gjk();
        Sat sat = new Sat();
        ClippingManifoldSolver clipping = new ClippingManifoldSolver();
        ConservativeAdvancement advancement = new ConservativeAdvancement();
        Random random = new Random(37);
        for (int i = 0; i < 240; i++) {
            Convex first = shapes[random.nextInt(shapes.length)];
            Convex second = shapes[random.nextInt(shapes.length)];
            Transform tx1 = new Transform();
            Transform tx2 = new Transform();
            tx1.rotate((random.nextDouble() - 0.5) * 2.0);
            tx2.rotate((random.nextDouble() - 0.5) * 2.0);
            tx1.translate((random.nextDouble() - 0.5) * 2.0, (random.nextDouble() - 0.5) * 2.0);
            tx2.translate((random.nextDouble() - 0.5) * 4.0, (random.nextDouble() - 0.5) * 4.0);
            Penetration penetration = new Penetration();
            boolean detected = gjk.detect(first, tx1, second, tx2, penetration);
            print(i + ".gjk.detect", detected, penetration.getDepth(),
                penetration.getNormal().x, penetration.getNormal().y);
            Penetration satPenetration = new Penetration();
            boolean satDetected = sat.detect(first, tx1, second, tx2, satPenetration);
            print(i + ".sat.detect", satDetected, satPenetration.getDepth(),
                satPenetration.getNormal().x, satPenetration.getNormal().y);
            if (detected) {
                Manifold manifold = new Manifold();
                boolean contacts = clipping.getManifold(penetration, first, tx1, second, tx2, manifold);
                print(i + ".manifold", contacts, manifold.getPoints().size(),
                    manifold.getNormal().x, manifold.getNormal().y);
            }
            Separation separation = new Separation();
            boolean separated = gjk.distance(first, tx1, second, tx2, separation);
            print(i + ".gjk.distance", separated, separation.getDistance(),
                separation.getNormal().x, separation.getNormal().y,
                separation.getPoint1().x, separation.getPoint1().y,
                separation.getPoint2().x, separation.getPoint2().y);
            Ray ray = new Ray(new Vector2(-2.5, random.nextDouble() * 2.0 - 1.0),
                new Vector2(1.0, random.nextDouble() * 0.5 - 0.25));
            Raycast raycast = new Raycast();
            boolean rayHit = gjk.raycast(ray, 5.0, second, tx2, raycast);
            print(i + ".gjk.raycast", rayHit, raycast.getDistance(),
                raycast.getPoint().x, raycast.getPoint().y,
                raycast.getNormal().x, raycast.getNormal().y);
            TimeOfImpact toi = new TimeOfImpact();
            boolean impact = advancement.getTimeOfImpact(first, tx1, new Vector2(0.3, 0.1), 0.1,
                second, tx2, new Vector2(-0.5, 0.0), -0.1, toi);
            print(i + ".toi", impact, toi.getTime(), toi.getSeparation().getDistance());
        }
    }
}
