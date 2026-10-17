import org.dyn4j.collision.continuous.ConservativeAdvancement;
import org.dyn4j.collision.continuous.TimeOfImpact;
import org.dyn4j.collision.broadphase.CollisionBodyBroadphaseFilter;
import org.dyn4j.collision.manifold.ClippingManifoldSolver;
import org.dyn4j.collision.manifold.Manifold;
import org.dyn4j.collision.manifold.ManifoldPoint;
import org.dyn4j.collision.manifold.ManifoldPointId;
import org.dyn4j.collision.narrowphase.CircleDetector;
import org.dyn4j.collision.narrowphase.Epa;
import org.dyn4j.collision.narrowphase.FallbackNarrowphaseDetector;
import org.dyn4j.collision.narrowphase.Gjk;
import org.dyn4j.collision.narrowphase.MinkowskiPenetrationSolver;
import org.dyn4j.collision.narrowphase.MinkowskiSum;
import org.dyn4j.collision.narrowphase.Penetration;
import org.dyn4j.collision.narrowphase.Separation;
import org.dyn4j.collision.narrowphase.TypedFallbackCondition;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector2;
import java.util.ArrayList;
import java.util.List;

public final class DetectionConsumer {
    private static final class ExtendedPenetration extends Penetration {
        int setterCalls;
        double fieldDepth() { return depth; }
        Vector2 fieldNormal() { return normal; }
        @Override public void setDepth(double value) { setterCalls++; super.setDepth(value); }
    }
    private static final class CircleFallback extends TypedFallbackCondition {
        @Override public boolean isMatch(Class<? extends Convex> first, Class<? extends Convex> second) {
            return first == Circle.class || second == Circle.class;
        }
    }
    private static final class ExtendedManifold extends Manifold {
        ExtendedManifold(Vector2 normal, List<ManifoldPoint> points) { super(normal, points); }
    }

    private static void require(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        Circle first = new Circle(1.0);
        Circle second = new Circle(1.0);
        Transform origin = new Transform();
        Transform overlap = new Transform();
        overlap.translate(1.5, 0.0);
        ExtendedPenetration penetration = new ExtendedPenetration();
        Vector2 originalNormal = penetration.getNormal();
        require(CircleDetector.detect(first, origin, second, overlap, penetration), "circle collision");
        require(penetration.getNormal() == originalNormal, "normal identity");
        require(penetration.fieldNormal() == originalNormal, "protected normal");
        require(penetration.fieldDepth() == 0.5, "protected depth");
        require(penetration.setterCalls == 0, "direct field write");
        Separation separation = new Separation();
        Transform far = new Transform();
        far.translate(3.0, 0.0);
        require(new Gjk().distance(first, origin, second, far, separation), "distance");
        require(separation.getDistance() == 1.0, "distance amount");
        Manifold manifold = new Manifold();
        require(new ClippingManifoldSolver().getManifold(penetration, first, origin, second, overlap, manifold), "manifold");
        require(manifold.getPoints().size() == 1, "contact count");
        require(ManifoldPointId.DISTANCE.copy() == ManifoldPointId.DISTANCE, "distance id");
        TimeOfImpact toi = new TimeOfImpact();
        Transform impactStart = new Transform();
        impactStart.translate(4, 0);
        require(new ConservativeAdvancement().getTimeOfImpact(first, origin, new Vector2(4, 0), 0,
            second, impactStart, new Vector2(), 0, toi), "time of impact");
        require(Math.abs(toi.getTime() - 0.5) < 1e-8, "impact fraction");
        require(!new CollisionBodyBroadphaseFilter<org.dyn4j.collision.CollisionBody<?>>()
            .isAllowed(null, null), "null filter pair");
        List<ManifoldPoint> points = new ArrayList<ManifoldPoint>();
        points.add(new ManifoldPoint(ManifoldPointId.DISTANCE));
        ExtendedManifold extended = new ExtendedManifold(new Vector2(1, 0), points);
        extended.setPoints(points);
        require(extended.getPoints() != points && extended.getPoints().size() == 1, "manifold copy input");
        extended.getPoints().clear();
        require(extended.getPoints().isEmpty(), "manifold live result");
        MinkowskiPenetrationSolver solver = new MinkowskiPenetrationSolver() {
            @Override public void getPenetration(List<Vector2> simplex, MinkowskiSum sum, Penetration result) {
                new Epa().getPenetration(simplex, sum, result);
            }
        };
        new Gjk(solver);
        FallbackNarrowphaseDetector fallback = new FallbackNarrowphaseDetector(new Gjk(), new Gjk());
        fallback.addCondition(new CircleFallback());
        require(fallback.getConditionCount() == 1 && fallback.isFallbackRequired(first, second), "typed fallback");
    }
}
