package org.dyn4j.geometry

object RotationOperationTap {
    sealed interface Observation {
        data class Rotation(val call: Call) : Observation
        data class ToiAccepted(val first: Any, val second: Any,
                               val time: Double, val secondDynamic: Boolean) : Observation
    }

    class Capture private constructor() {
        val method: String get() = error("baseline operation tap is unavailable")

        fun drain(): List<Observation> = error("baseline operation tap is unavailable")
        fun nextSequence(): Int = error("baseline operation tap is unavailable")
        fun targetToken(target: Transform): Int = error("baseline operation tap is unavailable")
        fun captureStep(world: Any, step: () -> Unit): Unit =
            error("baseline operation tap is unavailable")
    }

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
        val caseId: String? = null,
        val step: Int? = null,
        val bodyId: String? = null,
    )

    fun currentCapture(): Capture? = null
}
