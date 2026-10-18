package org.dyn4j.geometry

import kotlin.math.sqrt
import kotlin.experimental.ExperimentalNativeApi
import kotlin.native.OsFamily
import kotlin.native.Platform

@OptIn(ExperimentalNativeApi::class)
internal actual fun nearestSqrt(value: Double): Double {
    if (value == 0.0 || value == Double.POSITIVE_INFINITY) return value
    val candidate = sqrt(value)
    if (Platform.osFamily != OsFamily.WINDOWS || value < 0.0 || value.isNaN()) return candidate
    return nearestSqrtFromCandidate(value, candidate)
}
