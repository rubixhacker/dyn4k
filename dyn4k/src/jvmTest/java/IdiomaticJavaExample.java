import org.dyn4j.dynamics.Body;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.MassType;
import org.dyn4j.dynamics.TimeStep;
import org.dyn4j.world.PhysicsWorld;
import org.dyn4j.world.listener.StepListenerAdapter;

public final class IdiomaticJavaExample {
    private IdiomaticJavaExample() {}

    public static Body createBody() {
        Body body = new Body();
        body.addFixture(new Circle(0.5));
        body.setMass(MassType.NORMAL);
        body.getLinearVelocity().x = 2.0;
        return body;
    }

    public static StepListenerAdapter<Body> observeBody(final Body expected, final int[] calls) {
        return new StepListenerAdapter<Body>() {
            @Override
            public void begin(TimeStep step, PhysicsWorld<Body, ?> world) {
                if (world.getBody(0) != expected) {
                    throw new AssertionError("Kotlin world changed Java body identity");
                }
                calls[0]++;
            }
        };
    }
}
