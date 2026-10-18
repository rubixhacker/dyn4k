package org.dyn4j.coverage.collision.shapes.a

import kotlin.math.abs
import kotlin.math.PI
import kotlin.test.assertTrue

internal fun radians(degrees: Double): Double = degrees / 180.0 * PI

internal fun assertFiniteClose(expected: Double, actual: Double, tolerance: Double) {
    assertTrue(expected.isFinite() && actual.isFinite() && tolerance.isFinite(),
        "Expected finite comparison: expected=$expected actual=$actual tolerance=$tolerance")
    assertTrue(abs(expected - actual) <= tolerance,
        "Expected $expected +/- $tolerance, got $actual")
}
