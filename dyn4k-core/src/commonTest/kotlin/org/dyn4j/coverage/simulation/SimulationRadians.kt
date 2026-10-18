package org.dyn4j.coverage.simulation

internal fun simulationRadians(degrees: Double): Double = degrees / 180.0 * kotlin.math.PI
internal fun simulationRadians(degrees: Int): Double = simulationRadians(degrees.toDouble())
