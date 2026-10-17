package io.github.rubixhacker.dyn4k;

import org.dyn4j.geometry.Vector2;

public class VectorAccessorExtension extends Vector2 {
    public VectorAccessorExtension(double x, double y) {
        super(x, y);
    }

    public double getX() {
        return this.x * 2.0;
    }

    public void setX(double value) {
        this.x = value * 3.0;
    }

    public double readBeanX() { return getX(); }
    public void writeBeanX(double value) { setX(value); }

    public static void main(String[] args) {
        VectorAccessorExtension value = new VectorAccessorExtension(4.0, 2.0);
        if (value.x != 4.0 || value.getX() != 8.0) {
            throw new AssertionError("Field and custom getter must remain separate");
        }
        value.setX(2.0);
        if (value.x != 6.0) {
            throw new AssertionError("Custom setter did not run");
        }
        System.out.println("VectorAccessorExtension passed");
    }
}
