package org.dyn4j.geometry

internal object Math {
    fun toRadians(degrees: Int): Double = toRadians(degrees.toDouble())
    fun toRadians(degrees: Double): Double = degrees / 180.0 * kotlin.math.PI
    fun toDegrees(radians: Double): Double = radians * 180.0 / kotlin.math.PI
    fun toDegrees(radians: Int): Double = toDegrees(radians.toDouble())
    fun nextUp(value: Double): Double = when {
        value.isNaN() || value == Double.POSITIVE_INFINITY -> value
        value == 0.0 -> Double.fromBits(1L)
        value > 0.0 -> Double.fromBits(value.toBits() + 1L)
        else -> Double.fromBits(value.toBits() - 1L)
    }
    fun nextDown(value: Double): Double = when {
        value.isNaN() || value == Double.NEGATIVE_INFINITY -> value
        value == 0.0 -> Double.fromBits(Long.MIN_VALUE + 1L)
        value > 0.0 -> Double.fromBits(value.toBits() - 1L)
        else -> Double.fromBits(value.toBits() + 1L)
    }
    fun hypot(x: Double, y: Double): Double = kotlin.math.hypot(x, y)
}
