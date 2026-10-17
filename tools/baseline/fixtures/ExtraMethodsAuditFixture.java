import org.dyn4j.collision.broadphase.BroadphaseDetectorDecoratorAdapter;
import org.dyn4j.collision.continuous.ConservativeAdvancement;
import org.dyn4j.collision.continuous.TimeOfImpact;
import org.dyn4j.collision.manifold.Manifold;
import org.dyn4j.collision.manifold.ManifoldPoint;
import org.dyn4j.collision.narrowphase.Gjk;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.geometry.AABB;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.Transform;

final class ExtraMethodsAuditFixture {
    static final class Search extends Gjk {
        public String maxDetectIterationsField() { return "search"; }
    }

    static final class Advance extends ConservativeAdvancement {
        public String distanceEpsilonField() { return "advance"; }
    }

    static final class Contact extends Manifold {
        public String appendPointDirect$io_github_rubixhacker_dyn4k_core(ManifoldPoint point) {
            return "contact";
        }
    }

    static final class Impact extends TimeOfImpact {
        public String timeField() { return "impact"; }
    }

    static final class Box extends AABB {
        Box() { super(1.0); }
        public String getMinXField() { return "box"; }
    }

    static final class Pose extends Transform {
        public String sintValue() { return "pose"; }
    }

    static final class Decorator extends BroadphaseDetectorDecoratorAdapter<Object> {
        Decorator() { super(null); }
        public String getDetector() { return "decorator"; }
    }

    static final class Fixture extends BodyFixture {
        Fixture() { super(new Circle(1.0)); }
        public String rawDensity$io_github_rubixhacker_dyn4k_core() { return "fixture"; }
    }

    public static void main(String[] args) {
        String actual = new Search().maxDetectIterationsField()
            + new Advance().distanceEpsilonField()
            + new Contact().appendPointDirect$io_github_rubixhacker_dyn4k_core(null)
            + new Impact().timeField()
            + new Box().getMinXField()
            + new Pose().sintValue()
            + new Decorator().getDetector()
            + new Fixture().rawDensity$io_github_rubixhacker_dyn4k_core();
        if (!"searchadvancecontactimpactboxposedecoratorfixture".equals(actual)) {
            throw new AssertionError(actual);
        }
        System.out.println("Eight additional helpers passed");
    }
}
