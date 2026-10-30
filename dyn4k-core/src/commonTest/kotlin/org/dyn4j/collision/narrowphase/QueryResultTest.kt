package org.dyn4j.collision.narrowphase

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertFailsWith
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Polygon
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Rectangle
import org.dyn4j.geometry.Triangle
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Geometry

val QueryResultTest by testSuite {
    test("typeOnlyFallbackMatchesBuiltInSubclassBeforeObservingInstance") { QueryResultTestFixture().run { typeOnlyFallbackMatchesBuiltInSubclassBeforeObservingInstance() } }
    test("typeOnlyFallbackMatchesTriangleBeforeObservingInstance") { QueryResultTestFixture().run { typeOnlyFallbackMatchesTriangleBeforeObservingInstance() } }
    test("declaredCustomTypeMatchesTransitiveSupertypeBeforeObservingInstance") { QueryResultTestFixture().run { declaredCustomTypeMatchesTransitiveSupertypeBeforeObservingInstance() } }
    test("selfSupertypeDeclarationIsRejectedWithoutChangingFallbackMatches") { QueryResultTestFixture().run { selfSupertypeDeclarationIsRejectedWithoutChangingFallbackMatches() } }
    test("falseBuiltInReverseDeclarationIsRejectedWithoutChangingFallbackMatches") { QueryResultTestFixture().run { falseBuiltInReverseDeclarationIsRejectedWithoutChangingFallbackMatches() } }
    test("falseCustomReverseDeclarationIsRejectedWithoutChangingFallbackMatches") { QueryResultTestFixture().run { falseCustomReverseDeclarationIsRejectedWithoutChangingFallbackMatches() } }
    test("nonCyclicCustomClaimIsTrustedWhileRuntimeMatchUsesActualInstance") { QueryResultTestFixture().run { nonCyclicCustomClaimIsTrustedWhileRuntimeMatchUsesActualInstance() } }
    test("runtimeSubtypeUsesKClassInstanceCheckWithoutDeclaration") { QueryResultTestFixture().run { runtimeSubtypeUsesKClassInstanceCheckWithoutDeclaration() } }
    test("resultSetAndShiftKeepExposedVectorIdentity") { QueryResultTestFixture().run { resultSetAndShiftKeepExposedVectorIdentity() } }
    test("circleQueriesPreserveDirectedResultsAndUntouchedMisses") { QueryResultTestFixture().run { circleQueriesPreserveDirectedResultsAndUntouchedMisses() } }
    test("minkowskiSupportRestoresCallerDirection") { QueryResultTestFixture().run { minkowskiSupportRestoresCallerDirection() } }
    test("gjkUsesInjectedPenetrationSolverForNonCircleShapes") { QueryResultTestFixture().run { gjkUsesInjectedPenetrationSolverForNonCircleShapes() } }
    test("satReportsOverlapAndStrictContainment") { QueryResultTestFixture().run { satReportsOverlapAndStrictContainment() } }
    test("typedFallbackInvokesSelectedDetector") { QueryResultTestFixture().run { typedFallbackInvokesSelectedDetector() } }
    test("nonStrictFallbackMatchesRuntimeSubtypeOnEveryTarget") { QueryResultTestFixture().run { nonStrictFallbackMatchesRuntimeSubtypeOnEveryTarget() } }
    test("gjkRaycastReportsDirectedSquareEntry") { QueryResultTestFixture().run { gjkRaycastReportsDirectedSquareEntry() } }
}

private class QueryResultTestFixture  {
    private class CustomRectangle : Rectangle(2.0, 1.0)
    private class RuntimeRectangle : Rectangle(2.0, 1.0)
    private class CycleRectangle : Rectangle(2.0, 1.0)
    private class MisdeclaredCircle : Circle(1.0)

fun typeOnlyFallbackMatchesBuiltInSubclassBeforeObservingInstance() {
        val polygon = convexClassOf(Polygon::class)
        val rectangle = convexClassOf(Rectangle::class)
        val circle = convexClassOf(Circle::class)
        val condition = SingleTypedFallbackCondition(polygon, false)
        assertEquals(true, condition.isMatch(rectangle, circle))
        assertEquals(false, SingleTypedFallbackCondition(polygon, true).isMatch(rectangle, circle))
        assertEquals(true, PairwiseTypedFallbackCondition(polygon, false, circle, true).isMatch(rectangle, circle))
    }

fun typeOnlyFallbackMatchesTriangleBeforeObservingInstance() {
        val polygon = convexClassOf(Polygon::class)
        val triangle = convexClassOf(Triangle::class)
        val circle = convexClassOf(Circle::class)
        val condition = SingleTypedFallbackCondition(polygon, false)
        assertEquals(true, condition.isMatch(triangle, circle))
        assertEquals(false, SingleTypedFallbackCondition(polygon, true).isMatch(triangle, circle))
        assertEquals(true, PairwiseTypedFallbackCondition(polygon, false, circle, true).isMatch(triangle, circle))

        val instance = Triangle(Vector2(0.0, 0.0), Vector2(1.0, 0.0), Vector2(0.0, 1.0))
        assertEquals(true, condition.isMatch(instance, Circle(1.0)))
    }

fun declaredCustomTypeMatchesTransitiveSupertypeBeforeObservingInstance() {
        val custom = declareConvexSupertype(CustomRectangle::class, Rectangle::class)
        val polygon = convexClassOf(Polygon::class)
        val circle = convexClassOf(Circle::class)
        assertEquals(true, SingleTypedFallbackCondition(polygon, false).isMatch(custom, circle))
        assertEquals(false, SingleTypedFallbackCondition(polygon, true).isMatch(custom, circle))
        assertEquals(true, PairwiseTypedFallbackCondition(polygon, false, circle, true).isMatch(custom, circle))
    }

fun selfSupertypeDeclarationIsRejectedWithoutChangingFallbackMatches() {
        val error = assertFailsWith<IllegalArgumentException> {
            declareConvexSupertype(Circle::class, Circle::class)
        }
        assertEquals("A convex type cannot be its own supertype", error.message)
        val circle = convexClassOf(Circle::class)
        val polygon = convexClassOf(Polygon::class)
        assertEquals(false, SingleTypedFallbackCondition(polygon, false).isMatch(circle, circle))
        assertEquals(false, SingleTypedFallbackCondition(polygon, false).isMatch(Circle(1.0), Circle(1.0)))
    }

fun falseBuiltInReverseDeclarationIsRejectedWithoutChangingFallbackMatches() {
        val error = assertFailsWith<IllegalArgumentException> {
            declareConvexSupertype(Polygon::class, Rectangle::class)
        }
        assertEquals("A convex supertype declaration would create a cycle", error.message)
        val triangleError = assertFailsWith<IllegalArgumentException> {
            declareConvexSupertype(Polygon::class, Triangle::class)
        }
        assertEquals("A convex supertype declaration would create a cycle", triangleError.message)
        val rectangle = convexClassOf(Rectangle::class)
        val polygon = convexClassOf(Polygon::class)
        assertEquals(false, SingleTypedFallbackCondition(rectangle, false).isMatch(polygon, convexClassOf(Circle::class)))
        val polygonInstance = Polygon(Vector2(0.0, 0.0), Vector2(1.0, 0.0), Vector2(0.0, 1.0))
        assertEquals(false, SingleTypedFallbackCondition(rectangle, false).isMatch(polygonInstance, Circle(1.0)))
    }

fun falseCustomReverseDeclarationIsRejectedWithoutChangingFallbackMatches() {
        val custom = declareConvexSupertype(CycleRectangle::class, Rectangle::class)
        val error = assertFailsWith<IllegalArgumentException> {
            declareConvexSupertype(Rectangle::class, CycleRectangle::class)
        }
        assertEquals("A convex supertype declaration would create a cycle", error.message)
        val rectangle = convexClassOf(Rectangle::class)
        val condition = SingleTypedFallbackCondition(custom, false)
        assertEquals(false, condition.isMatch(rectangle, convexClassOf(Circle::class)))
        assertEquals(false, condition.isMatch(Rectangle(2.0, 1.0), Circle(1.0)))
        assertEquals(true, SingleTypedFallbackCondition(rectangle, false).isMatch(custom, convexClassOf(Circle::class)))
    }

fun nonCyclicCustomClaimIsTrustedWhileRuntimeMatchUsesActualInstance() {
        declareConvexSupertype(MisdeclaredCircle::class, Polygon::class)
        val polygon = convexClassOf(Polygon::class)
        val condition = SingleTypedFallbackCondition(polygon, false)
        assertEquals(false, condition.isMatch(MisdeclaredCircle(), Circle(1.0)))
    }

fun runtimeSubtypeUsesKClassInstanceCheckWithoutDeclaration() {
        val polygon = convexClassOf(Polygon::class)
        val condition = SingleTypedFallbackCondition(polygon, false)
        assertEquals(true, condition.isMatch(RuntimeRectangle(), Circle(1.0)))
    }

fun resultSetAndShiftKeepExposedVectorIdentity() {
        val penetration = Penetration()
        val normal = penetration.getNormal()
        penetration.setNormal(Vector2(1.0, 0.0))
        penetration.setDepth(0.5)
        assertSame(normal, penetration.getNormal())
        assertEquals(0.5, penetration.getDepth())
        penetration.shift(Vector2(2.0, 3.0))
        assertEquals(Vector2(1.0, 0.0), normal)

        val separation = Separation()
        val point1 = separation.getPoint1()
        val point2 = separation.getPoint2()
        separation.setPoint1(Vector2(1.0, 2.0))
        separation.setPoint2(Vector2(3.0, 4.0))
        separation.shift(Vector2(2.0, 3.0))
        assertSame(point1, separation.getPoint1())
        assertSame(point2, separation.getPoint2())
        assertEquals(Vector2(3.0, 5.0), point1)
        assertEquals(Vector2(5.0, 7.0), point2)

        val raycast = Raycast()
        val hit = raycast.getPoint()
        raycast.setPoint(Vector2(1.0, 2.0))
        raycast.shift(Vector2(2.0, 3.0))
        assertSame(hit, raycast.getPoint())
        assertEquals(Vector2(3.0, 5.0), hit)
        assertNotSame(hit, raycast.copy().getPoint())
    }

fun circleQueriesPreserveDirectedResultsAndUntouchedMisses() {
        val first = Circle(1.0)
        val second = Circle(1.0)
        val atOrigin = Transform()
        val overlapping = Transform().also { it.translate(1.5, 0.0) }
        val penetration = Penetration()
        val normal = penetration.getNormal()
        assertEquals(true, CircleDetector.detect(first, atOrigin, second, overlapping, penetration))
        assertSame(normal, penetration.getNormal())
        assertEquals(Vector2(1.0, 0.0), normal)
        assertEquals(0.5, penetration.getDepth())
        val far = Transform().also { it.translate(3.0, 0.0) }
        assertEquals(false, CircleDetector.detect(first, atOrigin, second, far, penetration))
        assertEquals(0.5, penetration.getDepth())

        val separation = Separation()
        assertEquals(true, CircleDetector.distance(first, atOrigin, second, far, separation))
        assertEquals(Vector2(1.0, 0.0), separation.getNormal())
        assertEquals(1.0, separation.getDistance())
        assertEquals(Vector2(1.0, 0.0), separation.getPoint1())
        assertEquals(Vector2(2.0, 0.0), separation.getPoint2())

        val raycast = Raycast()
        val ray = Ray(Vector2(-3.0, 0.0), Vector2(1.0, 0.0))
        assertEquals(true, CircleDetector.raycast(ray, 0.0, first, atOrigin, raycast))
        assertEquals(Vector2(-1.0, 0.0), raycast.getPoint())
        assertEquals(Vector2(-1.0, 0.0), raycast.getNormal())
        assertEquals(2.0, raycast.getDistance())
    }

fun minkowskiSupportRestoresCallerDirection() {
        val direction = Vector2(1.0, 0.0)
        val sum = MinkowskiSum(Circle(1.0), Transform(), Circle(2.0), Transform())
        assertEquals(Vector2(3.0, 0.0), sum.getSupportPoint(direction))
        assertEquals(Vector2(1.0, 0.0), direction)
        val support = sum.getSupportPoints(direction)
        assertEquals(Vector2(1.0, 0.0), support.getSupportPoint1())
        assertEquals(Vector2(-2.0, 0.0), support.getSupportPoint2())
        assertEquals(Vector2(3.0, 0.0), support.getPoint())
        assertEquals(Vector2(1.0, 0.0), direction)
    }

fun gjkUsesInjectedPenetrationSolverForNonCircleShapes() {
        var calls = 0
        val solver = object : MinkowskiPenetrationSolver {
            override fun getPenetration(simplex: List<Vector2>, minkowskiSum: MinkowskiSum, penetration: Penetration) {
                calls++
                penetration.setNormal(Vector2(1.0, 0.0))
                penetration.setDepth(0.5)
            }
        }
        val gjk = Gjk(solver)
        val square = Geometry.createSquare(2.0)
        val shifted = Transform().also { it.translate(1.0, 0.0) }
        val result = Penetration()
        assertEquals(true, gjk.detect(square, Transform(), square, shifted, result))
        assertEquals(1, calls)
        assertEquals(Vector2(1.0, 0.0), result.getNormal())
        assertEquals(0.5, result.getDepth())
    }

fun satReportsOverlapAndStrictContainment() {
        val sat = Sat()
        val small = Geometry.createSquare(1.0)
        val large = Geometry.createSquare(4.0)
        val containment = Containment()
        assertEquals(true, sat.contains(small, Transform(), large, Transform(), containment))
        assertEquals(true, containment.isAContainedInB())
        assertEquals(false, containment.isBContainedInA())
        val overlap = Penetration()
        assertEquals(true, sat.detect(small, Transform(), large, Transform(), overlap))
        assertEquals(false, sat.detect(small, Transform(), large, Transform().also { it.translate(5.0, 0.0) }))
    }

fun typedFallbackInvokesSelectedDetector() {
        var primaryCalls = 0
        var fallbackCalls = 0
        val primary = object : NarrowphaseDetector {
            override fun detect(convex1: org.dyn4j.geometry.Convex, transform1: Transform,
                convex2: org.dyn4j.geometry.Convex, transform2: Transform, penetration: Penetration): Boolean {
                primaryCalls++
                return false
            }
            override fun detect(convex1: org.dyn4j.geometry.Convex, transform1: Transform,
                convex2: org.dyn4j.geometry.Convex, transform2: Transform): Boolean {
                primaryCalls++
                return false
            }
        }
        val fallback = object : NarrowphaseDetector {
            override fun detect(convex1: org.dyn4j.geometry.Convex, transform1: Transform,
                convex2: org.dyn4j.geometry.Convex, transform2: Transform, penetration: Penetration): Boolean {
                fallbackCalls++
                return true
            }
            override fun detect(convex1: org.dyn4j.geometry.Convex, transform1: Transform,
                convex2: org.dyn4j.geometry.Convex, transform2: Transform): Boolean {
                fallbackCalls++
                return true
            }
        }
        val detector = FallbackNarrowphaseDetector(primary, fallback)
        detector.addCondition(SingleTypedFallbackCondition(convexClassOf(Circle::class)))
        assertEquals(true, detector.detect(Circle(1.0), Transform(), Geometry.createSquare(1.0), Transform()))
        assertEquals(1, fallbackCalls)
        assertEquals(0, primaryCalls)
        assertEquals(false, detector.detect(Geometry.createSquare(1.0), Transform(), Geometry.createSquare(1.0), Transform()))
        assertEquals(1, primaryCalls)
    }

fun nonStrictFallbackMatchesRuntimeSubtypeOnEveryTarget() {
        val base = convexClassOf(org.dyn4j.geometry.Convex::class)
        val circle = Circle(1.0)
        val polygon = Geometry.createSquare(1.0)
        val single = SingleTypedFallbackCondition(base, false)
        assertEquals(true, single.isMatch(circle, polygon))
        val pair = PairwiseTypedFallbackCondition(base, false, convexClassOf(Circle::class), true)
        assertEquals(true, pair.isMatch(polygon, circle))
        assertEquals(true, pair.isMatch(circle, polygon))
    }

fun gjkRaycastReportsDirectedSquareEntry() {
        val result = Raycast()
        val ray = Ray(Vector2(-3.0, 0.1), Vector2(1.0, 0.0))
        assertEquals(true, Gjk().raycast(ray, 10.0, Geometry.createSquare(1.0), Transform(), result))
        assertEquals(2.5, result.getDistance(), 1e-8)
        assertEquals(-1.0, result.getNormal().x, 1e-8)
        assertEquals(0.0, result.getNormal().y, 1e-8)
    }
}
