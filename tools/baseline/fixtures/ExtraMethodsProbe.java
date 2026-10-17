import org.dyn4j.collision.narrowphase.Epa;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.Force;
import org.dyn4j.geometry.Rotation;
import org.dyn4j.geometry.simplify.VertexClusterReduction;
import org.dyn4j.world.World;
import org.dyn4j.world.result.DetectResult;
import org.dyn4j.dynamics.BodyFixture;

public final class ExtraMethodsProbe {
    static final class Detector extends Epa {
        public String maxIterationsField() { return "detector"; }
    }

    static final class Simulation extends World<Body> {
        public String settingsField() { return "world"; }
    }

    static final class Simplifier extends VertexClusterReduction {
        Simplifier() { super(0.1); }
        public String getClusterTolerance() { return "simplifier"; }
    }

    static final class Turn extends Rotation {
        public String costValue() { return "rotation"; }
    }

    static final class AppliedForce extends Force {
        public String rawForce$io_github_rubixhacker_dyn4k_core() { return "force"; }
    }

    static final class Detection extends DetectResult<Body, BodyFixture> {
        public String bodyField() { return "result"; }
    }

    public static void main(String[] args) {
        String actual = new Detector().maxIterationsField()
            + new Simulation().settingsField()
            + new Simplifier().getClusterTolerance()
            + new Turn().costValue()
            + new AppliedForce().rawForce$io_github_rubixhacker_dyn4k_core()
            + new Detection().bodyField();
        if (!actual.equals("detectorworldsimplifierrotationforceresult")) {
            throw new AssertionError(actual);
        }
        System.out.println("Six extension helpers passed");
    }
}
