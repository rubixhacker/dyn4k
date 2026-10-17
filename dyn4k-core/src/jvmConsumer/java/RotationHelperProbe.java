import org.dyn4j.geometry.Rotation;
import org.dyn4j.geometry.Transform;

public final class RotationHelperProbe {
    static final class CustomRotation extends Rotation {
        public double costValue() { return 0.25; }
        public double sintValue() { return 0.75; }
    }

    static final class CustomTransform extends Transform {
        public double costValue() { return 0.25; }
        public double sintValue() { return 0.75; }
    }

    public static void main(String[] args) {
        Transform transformed = new Transform();
        transformed.rotate(new CustomRotation());
        Rotation copied = Rotation.of(new CustomTransform());
        System.out.println("transform=" + transformed.getCost() + "," + transformed.getSint());
        System.out.println("rotation=" + copied.getCost() + "," + copied.getSint());
        if (transformed.getCost() != 1.0 || transformed.getSint() != 0.0
                || copied.getCost() != 1.0 || copied.getSint() != 0.0) {
            throw new AssertionError("Subclass helper changed engine state");
        }
    }
}
