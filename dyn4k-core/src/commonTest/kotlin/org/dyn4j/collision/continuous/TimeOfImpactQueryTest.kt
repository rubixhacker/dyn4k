package org.dyn4j.collision.continuous

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.narrowphase.DistanceDetector
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

class TimeOfImpactQueryTest {
    @Test
    fun movingCirclesReachContactAtHalfStep() {
        val result = TimeOfImpact()
        val separation = result.getSeparation()
        val detector = ConservativeAdvancement()
        assertTrue(detector.getTimeOfImpact(
            Circle(1.0), Transform(), Vector2(4.0, 0.0), 0.0,
            Circle(1.0), Transform().also { it.translate(4.0, 0.0) }, Vector2(), 0.0,
            result
        ))
        assertEquals(0.5, result.getTime(), 1e-8)
        assertSame(separation, result.getSeparation())
    }

    @Test
    fun injectedDistanceDetectorRunsBeforeMotionBounds() {
        var calls = 0
        val detector = object : DistanceDetector {
            override fun distance(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, separation: Separation): Boolean {
                calls++
                return false
            }
        }
        val advancement = ConservativeAdvancement(detector)
        assertEquals(false, advancement.getTimeOfImpact(
            Circle(1.0), Transform(), Vector2(), 0.0,
            Circle(1.0), Transform(), Vector2(), 0.0, TimeOfImpact()
        ))
        assertEquals(1, calls)
    }
}
