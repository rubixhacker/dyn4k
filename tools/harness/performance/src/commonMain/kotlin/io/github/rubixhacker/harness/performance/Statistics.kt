package io.github.rubixhacker.harness.performance

import kotlin.math.ceil
import kotlin.math.floor

/**
 * A JSON number that keeps Python's distinction between an `int` and a `float`.
 *
 * `statistics.median` returns an `int` for an odd count and a `float` for an even count, and a
 * receipt that records `1300` where the reference records `1300.0` is a different byte sequence.
 */
sealed interface PythonNumber {
    fun toJson(): kotlinx.serialization.json.JsonPrimitive

    data class Integer(val value: Long) : PythonNumber {
        override fun toJson(): kotlinx.serialization.json.JsonPrimitive =
            kotlinx.serialization.json.JsonPrimitive(value)
    }

    data class Floating(val value: Double) : PythonNumber {
        override fun toJson(): kotlinx.serialization.json.JsonPrimitive =
            kotlinx.serialization.json.JsonPrimitive(value)
    }

    companion object {
        /** The median of [values] as Python reports it, preserving int-ness for an odd count. */
        fun medianOf(values: List<Long>): PythonNumber {
            val median = PerformanceStatistics.medianOfLongs(values)
            return if (PerformanceStatistics.medianIsInteger(values)) Integer(median.toLong()) else Floating(median)
        }
    }
}

/** The statistics helpers the analysis modules share, with Python's numeric behaviour. */
object PerformanceStatistics {
    /**
     * `statistics.median`: the middle element for an odd count and the mean of the two middle
     * elements for an even count, which Python always reports as a float.
     */
    fun median(values: List<Double>): Double {
        require(values.isNotEmpty()) { "no median for empty data" }
        val ordered = values.sorted()
        val middle = ordered.size / 2
        return if (ordered.size % 2 == 1) ordered[middle] else (ordered[middle - 1] + ordered[middle]) / 2.0
    }

    /**
     * `statistics.median` over integers. Python returns an `int` for an odd count and a `float`
     * for an even count; the analysis output depends on which one it is.
     */
    fun medianIsInteger(values: List<Long>): Boolean = values.size % 2 == 1

    fun medianOfLongs(values: List<Long>): Double {
        require(values.isNotEmpty()) { "no median for empty data" }
        val ordered = values.sorted()
        val middle = ordered.size / 2
        return if (ordered.size % 2 == 1) {
            ordered[middle].toDouble()
        } else {
            (ordered[middle - 1].toDouble() + ordered[middle].toDouble()) / 2.0
        }
    }

    /** `analyze.percentile`: the element at `ceil(len * fraction) - 1`, clamped at zero. */
    fun percentile(values: List<Long>, fraction: Double): Long {
        require(values.isNotEmpty()) { "no percentile for empty data" }
        val ordered = values.sorted()
        val position = maxOf(0, ceil(ordered.size.toDouble() * fraction).toInt() - 1)
        return ordered[position]
    }

    fun percentile(values: List<Double>, fraction: Double): Double {
        require(values.isNotEmpty()) { "no percentile for empty data" }
        val ordered = values.sorted()
        val position = maxOf(0, ceil(ordered.size.toDouble() * fraction).toInt() - 1)
        return ordered[position]
    }

    /** `measure.summary`'s integer percentile: `(len * p + 99) // 100 - 1`. */
    fun wholePercentile(times: List<Long>, percent: Int): Long {
        val position = maxOf(0, (times.size.toLong() * percent + 99) / 100 - 1)
        return times[position.toInt()]
    }

    /** `math.ceil(0.9 * count)` as the activity checks compute it. */
    fun ceilFraction(fraction: Double, count: Int): Long = ceil(fraction * count).toLong()

    /** `math.floor(0.2 * count)` as the settle check computes it. */
    fun floorFraction(fraction: Double, count: Int): Long = floor(fraction * count).toLong()
}
