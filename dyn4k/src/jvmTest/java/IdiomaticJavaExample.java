import org.dyn4j.dynamics.Body;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.MassType;

public final class IdiomaticJavaExample {
    private IdiomaticJavaExample() {}

    public static Body createBody() {
        Body body = new Body();
        body.addFixture(new Circle(0.5));
        body.setMass(MassType.NORMAL);
        body.getLinearVelocity().x = 2.0;
        return body;
    }
}
