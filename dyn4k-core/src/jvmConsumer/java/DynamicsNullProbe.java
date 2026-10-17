import org.dyn4j.dynamics.Body;
import org.dyn4j.geometry.Convex;

public class DynamicsNullProbe {
    public static void main(String[] args) {
        try {
            new Body().addFixture((Convex) null);
            System.out.println("NO_EXCEPTION");
        } catch (RuntimeException exception) {
            System.out.println(exception.getClass().getName() + ": " + exception.getMessage());
        }
    }
}
