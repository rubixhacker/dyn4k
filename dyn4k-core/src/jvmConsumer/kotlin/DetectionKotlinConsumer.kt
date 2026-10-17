import org.dyn4j.collision.broadphase.BruteForceBroadphase
import org.dyn4j.collision.broadphase.AABBProducer
import org.dyn4j.collision.broadphase.BroadphaseFilter
import org.dyn4j.collision.continuous.ConservativeAdvancement
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.narrowphase.CircleDetector
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.collision.narrowphase.SingleTypedFallbackCondition
import org.dyn4j.collision.narrowphase.convexClassOf
import org.dyn4j.collision.narrowphase.declareConvexSupertype
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Polygon
import org.dyn4j.geometry.Rectangle
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

private class CustomRectangle : Rectangle(2.0, 1.0)

fun main() {
    val custom = declareConvexSupertype(CustomRectangle::class, Rectangle::class)
    check(SingleTypedFallbackCondition(convexClassOf(Polygon::class), false)
        .isMatch(custom, convexClassOf(Circle::class)))
    val first = Circle(1.0)
    val second = Circle(1.0)
    val origin = Transform()
    val overlap = Transform().apply { translate(1.5, 0.0) }
    val penetration = Penetration()
    check(CircleDetector.detect(first, origin, second, overlap, penetration))
    check(penetration.getDepth() == 0.5)
    val far = Transform().apply { translate(3.0, 0.0) }
    val separation = Separation()
    check(Gjk().distance(first, origin, second, far, separation))
    check(separation.getDistance() == 1.0)

    val producer = object : AABBProducer<AABB> {
        override fun compute(item: AABB): AABB = item.copy()
        override fun compute(item: AABB, result: AABB) { result.set(item) }
    }
    val filter = object : BroadphaseFilter<AABB> {
        override fun isAllowed(first: AABB?, second: AABB?) = first !== second
    }
    val broadphase = BruteForceBroadphase(filter, producer)
    broadphase.add(AABB(0.0, 0.0, 2.0, 2.0))
    broadphase.add(AABB(1.0, 1.0, 3.0, 3.0))
    check(broadphase.detect().size == 1)

    val toi = TimeOfImpact()
    check(ConservativeAdvancement().getTimeOfImpact(
        first, origin, Vector2(4.0, 0.0), 0.0,
        second, Transform().apply { translate(4.0, 0.0) }, Vector2(), 0.0, toi
    ))
    check(kotlin.math.abs(toi.getTime() - 0.5) < 1e-8)
}
