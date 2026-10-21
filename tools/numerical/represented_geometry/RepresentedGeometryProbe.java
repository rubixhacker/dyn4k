import org.dyn4j.collision.narrowphase.Gjk;
import org.dyn4j.collision.narrowphase.Penetration;
import org.dyn4j.collision.narrowphase.Sat;
import org.dyn4j.collision.narrowphase.Separation;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.Transform;

public final class RepresentedGeometryProbe {
    private static final double SCALE = 0.01;
    private static final double[][] ORIGINS = {
        {1000.0, 1000.0}, {-1000.0, 1000.0},
        {1000000.0, -1000000.0}, {-1000000.0, 1000000.0}
    };

    private RepresentedGeometryProbe() { }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    private static String bits(double value) {
        return Long.toHexString(Double.doubleToRawLongBits(value));
    }

    public static void main(String[] args) {
        require(args.length == 0, "This probe takes no arguments");
        for (int originIndex = 0; originIndex < ORIGINS.length; originIndex++) {
            double ox = ORIGINS[originIndex][0];
            double oy = ORIGINS[originIndex][1];
            for (int sign : new int[] {-1, 1}) {
                String direction = sign < 0 ? "negative" : "positive";
                String id = "geometry-represented-v1-s0-o" + (originIndex + 1) + "-" + direction;
                double neutral = ox + SCALE * 1.5;
                double center = Math.nextAfter(neutral,
                    sign < 0 ? Double.NEGATIVE_INFINITY : Double.POSITIVE_INFINITY);
                double gap = (center - ox) - SCALE * 1.5;
                require(center != neutral, id + ": center did not move");
                require(sign * gap > 0.0, id + ": represented gap has the wrong sign");

                Convex first = Geometry.createCircle(SCALE);
                Convex second = Geometry.createCircle(SCALE * 0.5);
                Transform a = new Transform();
                Transform b = new Transform();
                a.translate(ox, oy);
                b.translate(center, oy);
                require(a.getTranslationX() == ox && b.getTranslationX() == center,
                    id + ": API changed the represented center");

                Penetration satDepth = new Penetration();
                Penetration gjkDepth = new Penetration();
                Separation separation = new Separation();
                boolean sat = new Sat().detect(first, a, second, b, satDepth);
                boolean gjk = new Gjk().detect(first, a, second, b, gjkDepth);
                boolean separated = new Gjk().distance(first, a, second, b, separation);
                System.out.println("{\"id\":\"" + id + "\",\"input\":{\"originX\":" + ox
                    + ",\"originY\":" + oy + ",\"scale\":" + SCALE
                    + ",\"direction\":\"" + direction + "\",\"neutral\":" + neutral
                    + ",\"center\":" + center + ",\"gap\":" + gap
                    + ",\"neutralBits\":\"" + bits(neutral) + "\",\"centerBits\":\""
                    + bits(center) + "\"},\"result\":{\"sat\":" + sat
                    + ",\"satDepth\":" + satDepth.getDepth() + ",\"gjk\":" + gjk
                    + ",\"gjkDepth\":" + gjkDepth.getDepth() + ",\"separated\":"
                    + separated + ",\"distance\":" + separation.getDistance() + "}}");
            }
        }
    }
}
