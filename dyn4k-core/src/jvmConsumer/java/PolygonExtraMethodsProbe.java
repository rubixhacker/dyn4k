import org.dyn4j.geometry.Vector2;
import org.dyn4j.geometry.simplify.VertexClusterReduction;

public final class PolygonExtraMethodsProbe {
    private static final class Extension extends VertexClusterReduction {
        Extension() { super(0.1); }

        public String getClusterTolerance() { return "extension"; }
    }

    private static final class SameSignatureExtension extends VertexClusterReduction {
        SameSignatureExtension() { super(0.25); }

        public double getClusterTolerance() { return 9.0; }
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
        SameSignatureExtension sameSignature = new SameSignatureExtension();
        if (sameSignature.getClusterTolerance() != 9.0) {
            throw new AssertionError("same-signature helper");
        }
        if (!inheritedToleranceUnaffected(sameSignature)) {
            throw new AssertionError("subclass helper changed inherited tolerance read");
        }
        if (sameSignature.simplify(points).length != 4) {
            throw new AssertionError("same-signature inherited simplification");
        }
        System.out.println("PolygonExtraMethodsProbe: 5 checks passed");
    }

    private static boolean inheritedToleranceUnaffected(SameSignatureExtension extension) {
        try {
            java.lang.reflect.Method getter =
                VertexClusterReduction.class.getDeclaredMethod("getClusterTolerance");
            return ((Double) getter.invoke(extension)).doubleValue() == 0.25;
        } catch (NoSuchMethodException baselineHasNoGetter) {
            return true;
        } catch (ReflectiveOperationException failure) {
            throw new AssertionError(failure);
        }
    }
}
