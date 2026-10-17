package example;

import org.dyn4j.geometry.Vector2;

public final class Main {
    public static void main(String[] args) {
        Vector2 value = new Vector2(3.0, 4.0);
        if (value.getMagnitude() != 5.0) {
            throw new AssertionError("Vector magnitude differs");
        }
        System.out.println("Named module consumer passed");
    }
}
