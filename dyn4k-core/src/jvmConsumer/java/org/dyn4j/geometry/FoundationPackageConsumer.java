package org.dyn4j.geometry;

public final class FoundationPackageConsumer {
    public static void main(String[] args) {
        Rotation rotation = new Rotation();
        if (rotation.rotate(0.0, 1.0) != rotation) throw new AssertionError("rotation identity");
        if (rotation.dot(new Vector2(1.0, 0.0)) != 0.0) throw new AssertionError("rotation dot");
        if (rotation.cross(new Vector2(1.0, 0.0)) != -1.0) throw new AssertionError("rotation cross");
        Rotation copy = rotation.getRotated45Helper(1.0, 0.0);
        if (copy == rotation || Math.abs(copy.getCost() - Math.sqrt(0.5)) > 1e-12)
            throw new AssertionError("rotation copy");
        if (rotation.rotate45Helper(1.0, 0.0) != rotation) throw new AssertionError("rotation helper");

        Vector2 vector = new Vector2(1.0, 0.0);
        if (vector.rotate(0.0, 1.0) != vector || Math.abs(vector.y - 1.0) > 1e-12)
            throw new AssertionError("vector origin");
        if (vector.rotate(0.0, -1.0, 1.0, 1.0) != vector || Math.abs(vector.x - 1.0) > 1e-12 || Math.abs(vector.y - 2.0) > 1e-12)
            throw new AssertionError("vector point");
        if (Vector2.X_AXIS.x != 1.0 || Vector2.Y_AXIS.y != 1.0 ||
            Vector2.INV_X_AXIS.x != -1.0 || Vector2.INV_Y_AXIS.y != -1.0)
            throw new AssertionError("axes");

        Transform transform = new Transform();
        transform.translate(2.0, 0.0);
        transform.rotate(0.0, 1.0);
        if (Math.abs(transform.getTranslationX()) > 1e-12 || Math.abs(transform.getTranslationY() - 2.0) > 1e-12)
            throw new AssertionError("transform origin");
        transform.rotate(0.0, -1.0, 1.0, 1.0);
        if (Math.abs(transform.getTranslationX() - 2.0) > 1e-12 || Math.abs(transform.getTranslationY() - 2.0) > 1e-12)
            throw new AssertionError("transform point");

        CountingRotation countingRotation = new CountingRotation();
        countingRotation.rotate(Math.PI / 2.0);
        if (countingRotation.calls != 1) throw new AssertionError("rotation dispatch");
        CountingVector countingVector = new CountingVector();
        countingVector.rotate(Math.PI / 2.0);
        if (countingVector.calls != 1) throw new AssertionError("vector dispatch");
        CountingTransform countingTransform = new CountingTransform();
        countingTransform.rotate(Math.PI / 2.0);
        if (countingTransform.calls != 1) throw new AssertionError("transform dispatch");
        System.out.println("FoundationPackageConsumer: 14 checks passed");
    }

    private static final class CountingRotation extends Rotation {
        int calls;
        @Override Rotation rotate(double c, double s) { calls++; return super.rotate(c, s); }
    }

    private static final class CountingVector extends Vector2 {
        int calls;
        @Override Vector2 rotate(double c, double s) { calls++; return super.rotate(c, s); }
    }

    private static final class CountingTransform extends Transform {
        int calls;
        @Override void rotate(double c, double s) { calls++; super.rotate(c, s); }
    }
}
