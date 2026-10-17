package io.github.rubixhacker.dyn4k;

import org.dyn4j.Reference;
import org.dyn4j.geometry.Matrix22;
import org.dyn4j.geometry.Matrix33;
import org.dyn4j.geometry.Rotation;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector3;

public final class FieldAccessorExtensions {
    private FieldAccessorExtensions() {}

    public static final class Vector3Extension extends Vector3 {
        public double getZ() { return this.z * 2.0; }
        public void setZ(double value) { this.z = value * 3.0; }
        public double readBean() { return getZ(); }
        public void writeBean(double value) { setZ(value); }
    }

    public static final class Matrix22Extension extends Matrix22 {
        public double getM00() { return this.m00 * 2.0; }
        public void setM00(double value) { this.m00 = value * 3.0; }
        public double readBean() { return getM00(); }
        public void writeBean(double value) { setM00(value); }
    }

    public static final class Matrix33Extension extends Matrix33 {
        public double getM22() { return this.m22 * 2.0; }
        public void setM22(double value) { this.m22 = value * 3.0; }
        public double readBean() { return getM22(); }
        public void writeBean(double value) { setM22(value); }
    }

    public static final class ReferenceExtension extends Reference<String> {
        public ReferenceExtension() { super("raw"); }
        public String getValue() { return "bean:" + this.value; }
        public void setValue(String value) { this.value = "stored:" + value; }
        public String readBean() { return getValue(); }
        public void writeBean(String value) { setValue(value); }
    }

    public static final class RotationExtension extends Rotation {
        public double rawCost() { return this.cost; }
        public double getCostField() { return this.cost * 2.0; }
        public void setCostField(double value) { this.cost = value * 3.0; }
        public double readBean() { return getCostField(); }
        public void writeBean(double value) { setCostField(value); }
    }

    public static final class TransformExtension extends Transform {
        public double rawX() { return this.x; }
        public double getX() { return this.x * 2.0; }
        public void setX(double value) { this.x = value * 3.0; }
        public double readBean() { return getX(); }
        public void writeBean(double value) { setX(value); }
    }
}
