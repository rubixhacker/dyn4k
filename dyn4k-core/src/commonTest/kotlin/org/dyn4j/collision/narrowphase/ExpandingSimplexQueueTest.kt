package org.dyn4j.collision.narrowphase

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlin.test.assertFalse
import org.dyn4j.geometry.Rectangle
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

val ExpandingSimplexQueueTest by testSuite {
    test("equalDistanceEdgesFollowPinnedQueueRemovalOrder") { ExpandingSimplexQueueTestFixture().run { equalDistanceEdgesFollowPinnedQueueRemovalOrder() } }
    test("unorderedDistancesCompareEqualToFiniteDistances") { ExpandingSimplexQueueTestFixture().run { unorderedDistancesCompareEqualToFiniteDistances() } }
    test("signedZeroProjectionRemainsAnEqualDistanceTie") { ExpandingSimplexQueueTestFixture().run { signedZeroProjectionRemainsAnEqualDistanceTie() } }
    test("rectanglePairKeepsPinnedGjkNormalThroughContainmentAndOverlap") { ExpandingSimplexQueueTestFixture().run { rectanglePairKeepsPinnedGjkNormalThroughContainmentAndOverlap() } }
}

private class ExpandingSimplexQueueTestFixture  {
fun equalDistanceEdgesFollowPinnedQueueRemovalOrder() {
        val bottomLeft = Vector2(-1.0, -1.0)
        val bottomRight = Vector2(1.0, -1.0)
        val topRight = Vector2(1.0, 1.0)
        val topLeft = Vector2(-1.0, 1.0)
        val simplex = ExpandingSimplex(listOf(bottomLeft, bottomRight, topRight, topLeft))

        assertSame(bottomLeft, simplex.getClosestEdge().point1)
        simplex.expand(Vector2(0.0, -1.0))
        assertEquals(5, simplex.size())
        assertSame(topLeft, simplex.getClosestEdge().point1)
    }

fun unorderedDistancesCompareEqualToFiniteDistances() {
        val finite = ExpandingSimplexEdge(Vector2(1.0, 0.0), Vector2(1.0, 1.0), 1)
        val unordered = ExpandingSimplexEdge(Vector2(Double.NaN, 0.0), Vector2(1.0, 0.0), 1)

        assertEquals(0, unordered.compareTo(finite))
        assertEquals(0, finite.compareTo(unordered))
    }

fun signedZeroProjectionRemainsAnEqualDistanceTie() {
        val negativeZero = ExpandingSimplexEdge(Vector2(-0.0, -0.0), Vector2(1.0, -0.0), 1)
        val positiveZero = ExpandingSimplexEdge(Vector2(0.0, 0.0), Vector2(1.0, 0.0), 1)

        assertEquals(0, negativeZero.compareTo(positiveZero))
        assertEquals(0, positiveZero.compareTo(negativeZero))
    }

fun rectanglePairKeepsPinnedGjkNormalThroughContainmentAndOverlap() {
        val large = Rectangle(1.0, 1.0)
        val small = Rectangle(0.5, 0.5)
        val first = Transform()
        val second = Transform()
        val result = Penetration()
        val detector = Gjk()

        assertTrue(detector.detect(large, first, small, second, result))
        assertEquals(-1.0, result.getNormal().x, 1e-3)
        assertEquals(0.0, result.getNormal().y, 1e-3)
        assertEquals(0.75, result.getDepth(), 1e-3)
        result.clear()
        assertTrue(detector.detect(small, second, large, first, result))
        assertEquals(-1.0, result.getNormal().x, 1e-3)
        assertEquals(0.0, result.getNormal().y, 1e-3)
        assertEquals(0.75, result.getDepth(), 1e-3)

        first.translate(-0.5, 0.0)
        result.clear()
        assertTrue(detector.detect(large, first, small, second, result))
        assertEquals(1.0, result.getNormal().x, 1e-3)
        assertEquals(0.0, result.getNormal().y, 1e-3)
        assertEquals(0.25, result.getDepth(), 1e-3)
        result.clear()
        assertTrue(detector.detect(small, second, large, first, result))
        assertEquals(-1.0, result.getNormal().x, 1e-3)
        assertEquals(0.0, result.getNormal().y, 1e-3)
        assertEquals(0.25, result.getDepth(), 1e-3)

        first.translate(-0.3, 0.0)
        result.clear()
        assertFalse(detector.detect(large, first, small, second, result))
        assertFalse(detector.detect(small, second, large, first, result))
    }
}
