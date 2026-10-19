import org.dyn4j.geometry.Ellipse;
import org.dyn4j.geometry.HalfEllipse;
import org.dyn4j.geometry.Interval;
import org.dyn4j.geometry.Matrix22;
import org.dyn4j.geometry.Matrix33;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector2;

public final class GeometrySubclassDispatch {
    static final class Mapped extends Transform {
        public double getTransformedX(Vector2 v) { return 777; }
        public double getTransformedY(Vector2 v) { return 888; }
        public void getTransformed(Vector2 v, Vector2 d) { d.x = 777; d.y = 888; }
        public void getInverseTransformed(Vector2 v, Vector2 d) { d.x = 777; d.y = 888; }
        public void getTransformedR(Vector2 v, Vector2 d) { d.x = 777; d.y = 888; }
        public void getInverseTransformedR(Vector2 v, Vector2 d) { d.x = 777; d.y = 888; }
        public void lerp(Transform end, double alpha, Transform result) {
            result.setTranslation(777, 888);
        }
    }

    static final class CopyTransform extends Transform {
        public Transform copy() {
            Transform result = new Transform();
            result.setTranslation(100, 200);
            return result;
        }
    }

    static final class TranslationTransform extends Transform {
        public void setTranslation(double x, double y) { super.setTranslation(77, 88); }
    }

    static final class MoveTransform extends Transform {
        public void translate(double x, double y) { super.translate(77, 88); }
    }

    static final class EllipseArea extends Ellipse {
        EllipseArea() { super(4, 2); }
        public double getArea() { return 100; }
    }

    static final class HalfEllipseArea extends HalfEllipse {
        HalfEllipseArea() { super(4, 2); }
        public double getArea() { return 100; }
        public double getHeight() { return 777; }
    }

    static final class IntervalCopy extends Interval {
        IntervalCopy() { super(1, 3); }
        public Interval copy() { return new Interval(100, 200); }
    }

    static final class MatrixCopy extends Matrix33 {
        MatrixCopy() { super(2, 0, 0, 0, 3, 0, 0, 0, 4); }
        public Matrix33 copy() { return new Matrix33(100, 0, 0, 0, 100, 0, 0, 0, 100); }
    }

    static final class Matrix22Copy extends Matrix22 {
        public Matrix22 copy() { return new Matrix22(10, 0, 0, 10); }
    }

    static String vector(Vector2 v) { return v.x + "," + v.y; }
    static String interval(Interval i) { return i.getMin() + "," + i.getMax(); }
    static String matrix(Matrix33 m) {
        return m.m00 + "," + m.m01 + "," + m.m02 + "," + m.m10 + "," + m.m11 + "," + m.m12
            + "," + m.m20 + "," + m.m21 + "," + m.m22;
    }
    static void emit(String name, Object value) { System.out.println(name + "=" + value); }

    static void provider(Class<?> type) {
        emit("provider." + type.getSimpleName(), type.getProtectionDomain().getCodeSource().getLocation());
    }

    public static void main(String[] args) {
        provider(Transform.class);
        provider(Ellipse.class);
        provider(HalfEllipse.class);
        provider(Interval.class);
        provider(Matrix33.class);
        provider(Matrix22.class);

        Mapped t = new Mapped();
        Vector2 v = new Vector2(3, 4);
        t.transformX(v);
        emit("transform_x", vector(v));
        v = new Vector2(3, 4);
        t.transformY(v);
        emit("transform_y", vector(v));
        v = new Vector2(3, 4);
        t.transform(v);
        emit("transform", vector(v));
        v = new Vector2(3, 4);
        t.inverseTransform(v);
        emit("inverse_transform", vector(v));
        v = new Vector2(3, 4);
        t.transformR(v);
        emit("transform_r", vector(v));
        v = new Vector2(3, 4);
        t.inverseTransformR(v);
        emit("inverse_transform_r", vector(v));
        emit("get_transformed", vector(t.getTransformed(new Vector2(3, 4))));
        emit("get_inverse_transformed", vector(t.getInverseTransformed(new Vector2(3, 4))));
        emit("get_transformed_r", vector(t.getTransformedR(new Vector2(3, 4))));
        emit("get_inverse_transformed_r", vector(t.getInverseTransformedR(new Vector2(3, 4))));
        Vector2 destination = new Vector2();
        t.getTransformed(new Vector2(3, 4), destination);
        emit("destination_transformed_control", vector(destination));
        t.getInverseTransformed(new Vector2(3, 4), destination);
        emit("destination_inverse_control", vector(destination));
        t.getTransformedR(new Vector2(3, 4), destination);
        emit("destination_rotation_control", vector(destination));
        t.getInverseTransformedR(new Vector2(3, 4), destination);
        emit("destination_inverse_rotation_control", vector(destination));

        Transform end = new Transform();
        end.setTranslation(10, 20);
        t.lerp(end, 0.5);
        emit("transform_lerp", vector(t.getTranslation()));
        emit("lerped_end", vector(new Mapped().lerped(end, 0.5).getTranslation()));
        emit("lerped_delta", vector(new CopyTransform().lerped(new Vector2(10, 20), 0, 0.5).getTranslation()));
        TranslationTransform translation = new TranslationTransform();
        translation.setTranslation(new Vector2(1, 2));
        emit("set_translation_vector_control", vector(translation.getTranslation()));
        MoveTransform move = new MoveTransform();
        move.lerp(new Vector2(10, 20), 0, 0.5);
        emit("lerp_delta_translate_control", vector(move.getTranslation()));

        emit("ellipse_mass", new EllipseArea().createMass(2).getMass());
        HalfEllipseArea half = new HalfEllipseArea();
        emit("half_ellipse_mass", half.createMass(2).getMass());
        emit("half_ellipse_height_string", half.toString().contains("|Height=777.0]"));
        emit("interval_expanded", interval(new IntervalCopy().getExpanded(2)));
        emit("interval_shrink", interval(new IntervalCopy().getExpanded(-8)));
        emit("matrix_transpose", matrix(new MatrixCopy().getTranspose()));
        emit("matrix_invert", matrix(new MatrixCopy().invert()));
        emit("matrix_multiply", matrix(new MatrixCopy().multiply(new Matrix33().identity())));
        Matrix33 self = new Matrix33(1, 2, 3, 4, 5, 6, 7, 8, 9);
        self.multiply(self);
        emit("matrix_self_multiply_control", matrix(self));
        emit("matrix_copy_sum_control", new MatrixCopy().sum(new Matrix33()).m00);
        emit("matrix_copy_inverse_control", new MatrixCopy().getInverse().m00);
        emit("matrix22_copy_control", new Matrix22Copy().sum(new Matrix22()).m00);
    }
}
