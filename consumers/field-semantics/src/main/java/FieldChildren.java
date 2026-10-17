import org.dyn4j.Reference;
import org.dyn4j.geometry.Matrix22;
import org.dyn4j.geometry.Matrix33;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.geometry.Vector3;

public final class FieldChildren {
    public static final class Vector2Child extends Vector2 {
        public Vector2Child() { super(4.0, 2.0); }
        public double getX() { return x * 2.0; }
        public void setX(double next) { x = next * 3.0; }
        public double readBean() { return getX(); }
    }
    public static final class Vector3Child extends Vector3 {
        public Vector3Child() { super(4.0, 2.0, 1.0); }
        public double getZ() { return z * 2.0; }
        public void setZ(double next) { z = next * 3.0; }
        public double readBean() { return getZ(); }
    }
    public static final class Matrix22Child extends Matrix22 {
        public Matrix22Child() { super(); m00 = 4.0; }
        public double getM00() { return m00 * 2.0; }
        public void setM00(double next) { m00 = next * 3.0; }
        public double readBean() { return getM00(); }
    }
    public static final class Matrix33Child extends Matrix33 {
        public Matrix33Child() { super(); m22 = 4.0; }
        public double getM22() { return m22 * 2.0; }
        public void setM22(double next) { m22 = next * 3.0; }
        public double readBean() { return getM22(); }
    }
    public static final class ReferenceChild extends Reference<String> {
        public ReferenceChild() { super("raw"); }
        public String getValue() { return value + "-bean"; }
        public void setValue(String next) { value = next + "-bean"; }
        public String readBean() { return getValue(); }
    }

    public static void main(String[] args) {
        Vector2Child vector2 = new Vector2Child();
        if (vector2.x != 4.0) throw new AssertionError("Vector2 field read");
        vector2.x = 7.0;
        if (vector2.x != 7.0 || vector2.readBean() != 14.0) throw new AssertionError("Vector2 field write");

        Vector3Child vector3 = new Vector3Child();
        if (vector3.z != 1.0) throw new AssertionError("Vector3 field read");
        vector3.z = 7.0;
        if (vector3.z != 7.0 || vector3.readBean() != 14.0) throw new AssertionError("Vector3 field write");

        Matrix22Child matrix22 = new Matrix22Child();
        if (matrix22.m00 != 4.0) throw new AssertionError("Matrix22 field read");
        matrix22.m00 = 7.0;
        if (matrix22.m00 != 7.0 || matrix22.readBean() != 14.0) throw new AssertionError("Matrix22 field write");

        Matrix33Child matrix33 = new Matrix33Child();
        if (matrix33.m22 != 4.0) throw new AssertionError("Matrix33 field read");
        matrix33.m22 = 7.0;
        if (matrix33.m22 != 7.0 || matrix33.readBean() != 14.0) throw new AssertionError("Matrix33 field write");

        ReferenceChild reference = new ReferenceChild();
        if (!"raw".equals(reference.value)) throw new AssertionError("Reference field read");
        reference.value = "next";
        if (!"next".equals(reference.value) || !"next-bean".equals(reference.readBean())) {
            throw new AssertionError("Reference field write");
        }
        System.out.println("FieldChildren: 15 Java field and bean checks passed");
    }
}
