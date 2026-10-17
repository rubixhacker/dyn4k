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
}
