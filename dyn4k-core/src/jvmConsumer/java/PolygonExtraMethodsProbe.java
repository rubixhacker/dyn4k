import org.dyn4j.geometry.Vector2;
import org.dyn4j.geometry.simplify.VertexClusterReduction;

public final class PolygonExtraMethodsProbe {
    private static final class Extension extends VertexClusterReduction {
        Extension() { super(0.1); }

        public String getClusterTolerance() { return "extension"; }
    }

    public static void main(String[] args) {
        Extension extension = new Extension();
        if (!"extension".equals(extension.getClusterTolerance())) {
            throw new AssertionError("subclass helper name");
        }
        Vector2[] points = {
            new Vector2(0, 0), new Vector2(2, 0),
            new Vector2(2, 2), new Vector2(0, 2)
        };
        if (extension.simplify(points).length != 4) {
            throw new AssertionError("subclass simplification");
        }
        System.out.println("PolygonExtraMethodsProbe: 2 checks passed");
    }
}
