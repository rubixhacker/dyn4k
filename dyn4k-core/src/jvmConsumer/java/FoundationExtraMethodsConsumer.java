import org.dyn4j.geometry.Rotation;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector2;

public final class FoundationExtraMethodsConsumer {
    private static final class RotationExtension extends Rotation {
        RotationExtension() { this.cost = 0.0; this.sint = 1.0; }

        public String costValue() { return "rotation cost"; }
        public String sintValue() { return "rotation sint"; }
        @Override public double getCost() { return 17.0; }
        @Override public double getSint() { return 19.0; }
        double rawCost() { return this.cost; }
        double rawSint() { return this.sint; }
    }

    private static final class TransformExtension extends Transform {
        TransformExtension() { this.cost = 0.0; this.sint = 1.0; }

        public String costValue() { return "transform cost"; }
        public String sintValue() { return "transform sint"; }
        @Override public double getCost() { return 23.0; }
        @Override public double getSint() { return 29.0; }
        double rawCost() { return this.cost; }
        double rawSint() { return this.sint; }
    }

    public static void main(String[] args) {
        RotationExtension rotation = new RotationExtension();
        TransformExtension transform = new TransformExtension();

        if (!"rotation costrotation sinttransform costtransform sint".equals(
            rotation.costValue() + rotation.sintValue() + transform.costValue() + transform.sintValue()))
            throw new AssertionError("unrelated Java helpers");
        if (rotation.rawCost() != 0.0 || rotation.rawSint() != 1.0 ||
            transform.rawCost() != 0.0 || transform.rawSint() != 1.0)
            throw new AssertionError("protected fields");
        if (((Rotation) rotation).getCost() != 17.0 || ((Rotation) rotation).getSint() != 19.0 ||
            ((Transform) transform).getCost() != 23.0 || ((Transform) transform).getSint() != 29.0)
            throw new AssertionError("getter overrides");

        Vector2 turned = new Vector2(1.0, 0.0).rotate(rotation);
        if (turned.x != 0.0 || turned.y != 1.0)
            throw new AssertionError("rotation uses protected values");
        Rotation fromTransform = Rotation.of(transform);
        if (fromTransform.getCost() != 0.0 || fromTransform.getSint() != 1.0)
            throw new AssertionError("rotation factory uses protected values");
        Transform destination = new Transform();
        destination.rotate(rotation);
        Vector2 transformed = destination.getTransformedR(new Vector2(1.0, 0.0));
        if (transformed.x != 0.0 || transformed.y != 1.0)
            throw new AssertionError("transform uses protected values");

        System.out.println("FoundationExtraMethodsConsumer: 6 checks passed");
    }
}
