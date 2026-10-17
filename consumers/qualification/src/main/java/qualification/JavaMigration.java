package qualification;

import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector2;

public final class JavaMigration {
    public static void run() {
        Transform transform = new Transform();
        transform.translate(2.0, -1.0);
        Vector2 value = transform.getTransformed(new Vector2(3.0, 4.0));
        if (value.x != 5.0 || value.y != 3.0) {
            throw new AssertionError("staged Java transform result");
        }
    }
}
