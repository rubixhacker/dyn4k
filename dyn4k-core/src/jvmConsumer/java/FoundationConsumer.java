import org.dyn4j.geometry.Matrix22;
import org.dyn4j.geometry.Rotation;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.geometry.Vector3;
import org.dyn4j.Copyable;

public final class FoundationConsumer {
    public static void main(String[] args) {
        Vector2 point = new Vector2(3.0, 4.0);
        if (Math.abs(point.getMagnitude() - 5.0) > 1e-12) throw new AssertionError("magnitude");
        point.x = 6.0;
        Transform transform = new Transform();
        transform.translate(2.0, -1.0);
        Vector2 moved = transform.getTransformed(point);
        if (moved.x != 8.0 || moved.y != 3.0) throw new AssertionError("transform");
        Vector2 rotated = new Vector2(1.0, 0.0).rotate(Rotation.rotation90());
        if (Math.abs(rotated.x) > 1e-12 || Math.abs(rotated.y - 1.0) > 1e-12) throw new AssertionError("rotation");
        Vector2 solved = new Matrix22(2.0, 0.0, 0.0, 4.0).solve(new Vector2(6.0, 8.0));
        if (solved.x != 3.0 || solved.y != 2.0) throw new AssertionError("matrix");
        if (new Vector3(1.0, 2.0, 3.0).getMagnitudeSquared() != 14.0) throw new AssertionError("vector3");
        Copyable<Vector2> copyable = point;
        if (copyable.copy() == point) throw new AssertionError("copy identity");
        if (Math.abs(Vector2.create(2.0, 0.0).x - 2.0) > 1e-12) throw new AssertionError("static vector");
        ExposedTransform exposed = new ExposedTransform();
        exposed.moveProtected(9.0, 7.0);
        if (exposed.getTranslationX() != 9.0 || exposed.getTranslationY() != 7.0)
            throw new AssertionError("protected transform");
        ExposedRotation protectedRotation = new ExposedRotation();
        if (protectedRotation.getSint() != 1.0) throw new AssertionError("protected rotation");
        Rotation overridingRotation = new OverrideRotation();
        if (overridingRotation.getCost() != 3.0 || overridingRotation.getSint() != 3.0)
            throw new AssertionError("rotation virtual dispatch");
        Transform overridingTransform = new OverrideTransform();
        if (overridingTransform.getCost() != 3.0 || overridingTransform.getSint() != 3.0)
            throw new AssertionError("transform virtual dispatch");
        try {
            new Matrix22((double[]) null);
            throw new AssertionError("missing null exception");
        } catch (NullPointerException expected) {
            if (!"values cannot be null".equals(expected.getMessage()))
                throw new AssertionError("null exception message", expected);
        }
        System.out.println("FoundationConsumer: 12 checks passed");
    }

    private static final class ExposedTransform extends Transform {
        void moveProtected(double x, double y) { this.x = x; this.y = y; }
    }

    private static final class ExposedRotation extends Rotation {
        ExposedRotation() { super(0.0, 1.0); }
        @Override public double getCost() { return super.getCost(); }
    }

    private static final class OverrideRotation extends Rotation {
        @Override public double getCost() { return this.cost + 2.0; }
        @Override public double getSint() { return this.sint + 3.0; }
    }

    private static final class OverrideTransform extends Transform {
        @Override public double getCost() { return this.cost + 2.0; }
        @Override public double getSint() { return this.sint + 3.0; }
    }
}
