package org.dyn4j.geometry

object RotationOperationTap {
    data class Call(
        val target: Transform,
        val kind: String,
        val source: String,
        val preCost: Double,
        val preSint: Double,
        val trigCost: Double,
        val trigSint: Double,
        val rawCost: Double?,
        val rawSint: Double?,
        val postCost: Double,
        val postSint: Double,
        val angleBits: Long? = null,
        val alpha: Double? = null,
        val startAngle: Double? = null,
        val endAngle: Double? = null,
        val difference: Double? = null,
        val startCost: Double? = null,
        val startSint: Double? = null,
        val endCost: Double? = null,
        val endSint: Double? = null,
    )

    var listener: ((Call) -> Unit)? = null
}
