import static org.dyn4j.dynamics.ContinuousDetectionMode.*;
import static extra.Names.*;

public final class AddedStaticMethod {
    public static void main(String[] args) {
        if (!"existing consumer method".equals(getEntries())) {
            throw new AssertionError();
        }
    }
}
