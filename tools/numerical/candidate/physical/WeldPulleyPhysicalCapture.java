import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.TimeStep;
import org.dyn4j.dynamics.joint.PulleyJoint;
import org.dyn4j.dynamics.joint.WeldJoint;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.PhysicsWorld;
import org.dyn4j.world.World;
import org.dyn4j.world.listener.StepListenerAdapter;

public final class WeldPulleyPhysicalCapture {
    private static final String STEP_SECONDS = "1/60";
    private static final int STEPS = 36000;

    private WeldPulleyPhysicalCapture() {}

    private static String value(double number) {
        if (!Double.isFinite(number)) throw new IllegalStateException("nonfinite baseline state");
        return Double.toString(number);
    }

    private static String vector(Vector2 vector) {
        return "[" + value(vector.x) + "," + value(vector.y) + "]";
    }

    private static String body(String id, Body body, boolean rotation) {
        String result = "{\"id\":\"" + id + "\",\"center\":" + vector(body.getWorldCenter());
        if (rotation) {
            result += ",\"angle\":" + value(body.getTransform().getRotationAngle())
                    + ",\"cost\":" + value(body.getTransform().getCost())
                    + ",\"sint\":" + value(body.getTransform().getSint());
        }
        return result + "}";
    }

    private static void run(String name, World<Body> world, Body first, Body second,
                            WeldJoint<Body> weld, PulleyJoint<Body> pulley,
                            String declarationHash, String captureHash, String jarHash,
                            String candidateCommit, Path trace) throws Exception {
        PrintWriter output = new PrintWriter(Files.newBufferedWriter(trace, StandardOpenOption.CREATE_NEW));
        output.println("{\"kind\":\"inputs\",\"case\":\"" + name
                + "\",\"declaration_sha256\":\"" + declarationHash
                + "\",\"capture_sha256\":\"" + captureHash
                + "\",\"source_revision\":\"" + candidateCommit
                + "\",\"jar_sha256\":\"" + jarHash
                + "\",\"step_seconds\":\"" + STEP_SECONDS
                + "\",\"steps\":" + STEPS + "}");
        int[] currentStep = {0};
        world.setUpdateRequired(false);
        world.addStepListener(new StepListenerAdapter<Body>() {
            private void event(int order, String method) {
                output.println("{\"kind\":\"event\",\"step\":" + currentStep[0]
                        + ",\"order\":" + order + ",\"callback\":\"" + method + "\"}");
            }

            @Override public void begin(TimeStep step, PhysicsWorld<Body, ?> source) {
                event(0, "begin");
            }

            @Override public void updatePerformed(TimeStep step, PhysicsWorld<Body, ?> source) {
                event(99, "updatePerformed");
            }

            @Override public void postSolve(TimeStep step, PhysicsWorld<Body, ?> source) {
                event(1, "postSolve");
            }

            @Override public void end(TimeStep step, PhysicsWorld<Body, ?> source) {
                event(2, "end");
            }
        });
        for (int step = 1; step <= STEPS; step++) {
            currentStep[0] = step;
            world.step(1, 1.0 / 60.0);
            String bodies;
            String joint;
            if (weld != null) {
                bodies = "[" + body("ground", first, true) + "," + body("member", second, true) + "]";
                joint = "{\"type\":\"WeldJoint\",\"spring\":" + weld.isSpringEnabled()
                        + ",\"limits\":" + weld.isLimitsEnabled()
                        + ",\"frequency\":" + value(weld.getSpringFrequency())
                        + ",\"dampingRatio\":" + value(weld.getSpringDampingRatio())
                        + ",\"lowerLimit\":" + value(weld.getLowerLimit())
                        + ",\"upperLimit\":" + value(weld.getUpperLimit())
                        + ",\"anchor1\":" + vector(weld.getAnchor1())
                        + ",\"anchor2\":" + vector(weld.getAnchor2())
                        + ",\"referenceAngle\":" + value(weld.getLimitsReferenceAngle()) + "}";
            } else {
                bodies = "[" + body("left", first, false) + "," + body("right", second, false) + "]";
                joint = "{\"type\":\"PulleyJoint\",\"slack\":" + pulley.isSlackEnabled()
                        + ",\"ratio\":" + value(pulley.getRatio())
                        + ",\"length\":" + value(pulley.getLength())
                        + ",\"pulleyAnchor1\":" + vector(pulley.getPulleyAnchor1())
                        + ",\"pulleyAnchor2\":" + vector(pulley.getPulleyAnchor2())
                        + ",\"anchor1\":" + vector(pulley.getAnchor1())
                        + ",\"anchor2\":" + vector(pulley.getAnchor2()) + "}";
            }
            output.println("{\"kind\":\"state\",\"step\":" + step
                    + ",\"state\":{\"bodies\":" + bodies + ",\"joint\":" + joint + "}}");
            if (output.checkError()) throw new IllegalStateException("candidate capture output failed");
        }
        output.close();
        if (output.checkError()) throw new IllegalStateException("candidate capture output failed");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 6) throw new IllegalArgumentException("trace case declarationHash captureHash artifactHash candidateCommit");
        Path trace = Path.of(args[0]).toAbsolutePath();
        Files.createDirectories(trace.getParent());
        RuntimeStamp.write(trace.getParent(), World.class, WeldPulleyPhysicalCapture.class);
        String name = args[1];
        World<Body> world = new World<>();
        world.setGravity(new Vector2(0, -9.8));
        if (name.equals("weld-spring-equal")) {
            Body fixed = new Body();
            fixed.addFixture(Geometry.createRectangle(10, 0.5)).setFriction(0);
            fixed.setMass(MassType.INFINITE);
            fixed.setLinearDamping(0);
            fixed.setAngularDamping(0);
            Body member = new Body();
            member.addFixture(Geometry.createRectangle(1, 0.5)).setFriction(0);
            member.setMass(MassType.NORMAL);
            member.translate(0, 2);
            member.setLinearVelocity(2, 0);
            member.applyForce(new Vector2(0, -10), new Vector2(0.5, 2));
            member.setLinearDamping(0);
            member.setAngularDamping(0);
            world.addBody(fixed);
            world.addBody(member);
            WeldJoint<Body> joint = new WeldJoint<>(fixed, member, new Vector2(-0.5, 2));
            joint.setSpringEnabled(true);
            joint.setSpringDamperEnabled(true);
            joint.setSpringFrequency(8);
            joint.setSpringDampingRatio(0.3);
            joint.setLimitsEnabled(0, 0);
            world.addJoint(joint);
            run(name, world, fixed, member, joint, null, args[2], args[3], args[4], args[5], Path.of(args[0]));
        } else if (name.equals("pulley-taut")) {
            Body left = new Body();
            Body right = new Body();
            for (Body body : new Body[] {left, right}) {
                body.addFixture(Geometry.createCircle(0.5)).setFriction(0);
                body.setMass(MassType.NORMAL);
                body.setLinearDamping(0);
                body.setAngularDamping(0);
            }
            left.translate(-1, 0);
            right.translate(1, 0);
            right.setLinearVelocity(0, 2);
            world.addBody(left);
            world.addBody(right);
            PulleyJoint<Body> joint = new PulleyJoint<>(left, right,
                    new Vector2(-1, 1), new Vector2(1, 1),
                    new Vector2(-1, 0), new Vector2(1, 0));
            joint.setSlackEnabled(false);
            world.addJoint(joint);
            run(name, world, left, right, null, joint, args[2], args[3], args[4], args[5], Path.of(args[0]));
        } else {
            throw new IllegalArgumentException("unknown physical case");
        }
    }
}
