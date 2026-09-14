import java.util.Locale;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.Settings;
import org.dyn4j.dynamics.TimeStep;
import org.dyn4j.dynamics.joint.AngleJoint;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.MassType;
import org.dyn4j.world.World;

/** Standalone dyn4j 6.0.0 negative-ratio reproduction; does not use Capture. */
public final class NegativeRatioProbe {
    public static void main(String[] args) {
        if (args.length > 0 && args[0].equals("--help")) {
            System.out.println("Usage: NegativeRatioProbe [world|constraints|cold|positive]\nDefault world preserves approved P-J-Angle-ratio-limits-off--1.0 inputs. Other modes are diagnostic controls only.");
            return;
        }
        String mode=args.length == 0 ? "world" : args[0];
        if (args.length > 1 || !java.util.Set.of("world","constraints","cold","positive").contains(mode)) {
            System.err.println("Unknown mode; use --help"); System.exit(2);
        }
        World<Body> world=new World<>(); world.setGravity(World.ZERO_GRAVITY);
        Body a=body(), b=body(); b.translate(0,2); b.setAngularVelocity(-Math.toRadians(30));
        world.addBody(a); world.addBody(b);
        AngleJoint<Body> joint=new AngleJoint<>(a,b); joint.setLimitsEnabled(false); joint.setRatio(mode.equals("positive") ? 1 : -1); world.addJoint(joint);
        if(mode.equals("cold")) world.getSettings().setWarmStartingEnabled(false);
        System.out.println("mode="+mode+" ratio="+joint.getRatio()+" warmStart="+world.getSettings().isWarmStartingEnabled()+" inverseInertia="+a.getMass().getInverseInertia()+" velocityIterations="+world.getSettings().getVelocityConstraintSolverIterations());
        if(mode.equals("constraints")) {
            TimeStep time=new TimeStep(1.0/60); Settings settings=world.getSettings();
            joint.initializeConstraints(time,settings); print(0,a,b,joint);
            for(int i=1;i<=10;i++){joint.solveVelocityConstraints(time,settings);print(i,a,b,joint);}
            return;
        }
        for(int step=1;step<=600;step++) {
            world.step(1,1.0/60);
            double torque=joint.getReactionTorque(60);
            if(step<=3 || step>=168 && step<=172) print(step,a,b,joint);
            String[] names={"body0.angularVelocity","body1.angularVelocity","body0.angle","body1.angle","joint.reactionTorque"};
            double[] values={a.getAngularVelocity(),b.getAngularVelocity(),a.getTransform().getRotationAngle(),b.getTransform().getRotationAngle(),torque};
            boolean failed=false;
            for(int i=0;i<values.length;i++) if(!Double.isFinite(values[i])) {System.out.println("FIRST_NONFINITE_AFTER_STEP="+step+" quantity="+names[i]+" value="+values[i]);failed=true;}
            if(failed) {System.exit(1);}
        }
        System.out.println("FINITE_600_STEPS");
    }
    private static Body body(){Body b=new Body();b.addFixture(Geometry.createCircle(0.5)).setFriction(0);b.setMass(MassType.NORMAL);b.setLinearDamping(0);b.setAngularDamping(0);return b;}
    private static void print(int step,Body a,Body b,AngleJoint<Body> joint){
        System.out.printf(Locale.ROOT,"step=%d w0=%.17g w1=%.17g residual=%.17g torque=%.17g angle0=%.17g angle1=%.17g%n",step,a.getAngularVelocity(),b.getAngularVelocity(),b.getAngularVelocity()-joint.getRatio()*a.getAngularVelocity(),joint.getReactionTorque(60),a.getTransform().getRotationAngle(),b.getTransform().getRotationAngle());
    }
}
