import org.dyn4j.geometry.Vector2;

public final class Vector2NormalizationConsumer {
    private static final long X_BITS = 0x3fe3333333333334L;
    private static final long Y_BITS = 0x3fe999999999999aL;

    public static void main(String[] args) {
        Vector2 vector = new Vector2(3.0, 4.0);
        if (vector.normalize() != 5.0 || bits(vector.x) != X_BITS || bits(vector.y) != Y_BITS)
            throw new AssertionError("normalize reciprocal order");

        Vector2 source = new Vector2(3.0, 4.0);
        Vector2 copy = source.getNormalized();
        if (copy == source || bits(copy.x) != X_BITS || bits(copy.y) != Y_BITS || source.x != 3.0)
            throw new AssertionError("getNormalized reciprocal order and identity");

        OverriddenMagnitude overridden = new OverriddenMagnitude();
        if (overridden.normalize() != 5.0 || overridden.calls != 0 || bits(overridden.x) != X_BITS)
            throw new AssertionError("normalize bypasses virtual magnitude");

        OverriddenMagnitude sourceWithOverride = new OverriddenMagnitude();
        Vector2 virtualCopy = sourceWithOverride.getNormalized();
        if (sourceWithOverride.calls != 1 || bits(virtualCopy.x) != 0x3fd3333333333334L ||
            bits(virtualCopy.y) != 0x3fd999999999999aL || sourceWithOverride.x != 3.0)
            throw new AssertionError("getNormalized uses virtual magnitude");

        System.out.println("Vector2NormalizationConsumer: 4 checks passed");
    }

    private static long bits(double value) { return Double.doubleToRawLongBits(value); }

    private static final class OverriddenMagnitude extends Vector2 {
        int calls;

        OverriddenMagnitude() { super(3.0, 4.0); }

        @Override public double getMagnitude() { calls++; return 10.0; }
    }
}
