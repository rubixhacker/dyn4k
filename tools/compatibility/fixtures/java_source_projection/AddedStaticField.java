import static org.dyn4j.geometry.Vector2.*;
import static extra.Names.*;

public final class AddedStaticField {
    public static void main(String[] args) {
        if (!"existing consumer field".equals(Companion)) {
            throw new AssertionError();
        }
    }
}
