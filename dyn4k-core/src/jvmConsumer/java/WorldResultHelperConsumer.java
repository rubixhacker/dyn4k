import org.dyn4j.collision.narrowphase.Penetration;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.geometry.Circle;
import org.dyn4j.world.result.ConvexDetectResult;
import org.dyn4j.world.result.DetectResult;

public final class WorldResultHelperConsumer {
    private static final class DifferentDetect extends DetectResult<Body, BodyFixture> {
        public String bodyField() { return body == getBody() ? "body" : "wrong body"; }
        public String setBodyField(Body value) { body = value; return "set body"; }
        public String fixtureField() { return fixture == getFixture() ? "fixture" : "wrong fixture"; }
        public String setFixtureField(BodyFixture value) { fixture = value; return "set fixture"; }
    }

    private static final class SameDetect extends DetectResult<Body, BodyFixture> {
        public Body bodyField() { return body; }
        public void setBodyField(Body value) { body = value; }
        public BodyFixture fixtureField() { return fixture; }
        public void setFixtureField(BodyFixture value) { fixture = value; }
    }

    private static final class DifferentConvex extends ConvexDetectResult<Body, BodyFixture> {
        public String penetrationField() {
            return penetration == getPenetration() ? "penetration" : "wrong penetration";
        }
    }

    private static final class SameConvex extends ConvexDetectResult<Body, BodyFixture> {
        public Penetration penetrationField() { return penetration; }
    }

    public static void main(String[] args) {
        if (args.length != 1) throw new IllegalArgumentException("different, same, convex-different, convex-same");
        Body body = new Body();
        BodyFixture fixture = body.addFixture(new Circle(0.5));
        switch (args[0]) {
            case "different": {
                DifferentDetect result = new DifferentDetect();
                if (!"set body".equals(result.setBodyField(body)) ||
                        !"set fixture".equals(result.setFixtureField(fixture)) ||
                        !"body".equals(result.bodyField()) ||
                        !"fixture".equals(result.fixtureField()) ||
                        result.getBody() != body || result.getFixture() != fixture) {
                    throw new AssertionError("different-return dispatch or protected state");
                }
                break;
            }
            case "same": {
                SameDetect result = new SameDetect();
                result.setBodyField(body);
                result.setFixtureField(fixture);
                if (result.bodyField() != body || result.fixtureField() != fixture ||
                        result.getBody() != body || result.getFixture() != fixture) {
                    throw new AssertionError("same-return dispatch or protected state");
                }
                break;
            }
            case "convex-different": {
                DifferentConvex result = new DifferentConvex();
                if (!"penetration".equals(result.penetrationField())) {
                    throw new AssertionError("different-return penetration dispatch");
                }
                break;
            }
            case "convex-same": {
                SameConvex result = new SameConvex();
                if (result.penetrationField() != result.getPenetration()) {
                    throw new AssertionError("same-return penetration dispatch");
                }
                break;
            }
            default: throw new IllegalArgumentException(args[0]);
        }
        System.out.println("RESULT_HELPERS_OK," + args[0]);
    }
}
