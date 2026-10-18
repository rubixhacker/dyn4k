package org.dyn4j.geometry

object RotationOperationTap {
    sealed interface Observation {
        data class Rotation(val call: Call) : Observation
        data class ToiAccepted(val first: Any, val second: Any,
                               val time: Double, val secondDynamic: Boolean) : Observation
    }

    class Capture internal constructor(val method: String) {
        private val observations = mutableListOf<Observation>()
        private val targets = mutableMapOf<Transform, Int>()
        private var sequence = 0
        private var expectedWorld: Any? = null
        private var worldDepth = 0
        private var worldSteps = 0
        private var failed = false

        fun drain(): List<Observation> {
            if (worldDepth != 0) {
                failed = true
                return emptyList()
            }
            check(!failed) { "diagnostic observation failed" }
            val result = observations.toList()
            observations.clear()
            return result
        }

        fun nextSequence(): Int = sequence++

        fun targetToken(target: Transform): Int = targets.getOrPut(target) { targets.size }

        fun captureStep(world: Any, step: () -> Unit) {
            check(!failed && expectedWorld == null && observations.isEmpty()) {
                "diagnostic capture has pending observations"
            }
            expectedWorld = world
            worldSteps = 0
            try {
                step()
            } finally {
                expectedWorld = null
            }
            check(!failed && worldDepth == 0 && worldSteps == 1) {
                "diagnostic world step was not isolated"
            }
        }

        internal fun beginWorldStep(world: Any) {
            if (expectedWorld != null) {
                if (worldDepth != 0 || world !== expectedWorld) failed = true
                worldDepth++
                worldSteps++
            }
        }

        internal fun endWorldStep() {
            if (expectedWorld != null) worldDepth--
        }

        internal fun add(observation: Observation) {
            if (expectedWorld != null && worldDepth != 1) {
                failed = true
            } else {
                observations.add(observation)
            }
        }

        internal fun invalidate() { failed = true }

        internal fun requireHealthy() {
            check(!failed && worldDepth == 0) { "diagnostic observation failed" }
        }
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

    fun currentCapture(): Capture? = RotationCaptureSlot.current

    fun <T> capture(method: String, block: (Capture) -> T): T {
        val previous = RotationCaptureSlot.current
        val current = Capture(method)
        RotationCaptureSlot.current = current
        try {
            val result = block(current)
            current.requireHealthy()
            return result
        } finally {
            RotationCaptureSlot.current = previous
        }
    }

    internal fun record(rotation: () -> Call) {
        val capture = RotationCaptureSlot.current ?: return
        try {
            capture.add(Observation.Rotation(rotation()))
        } catch (_: Throwable) {
            capture.invalidate()
        }
    }

    internal fun recordToi(first: Any, second: Any, time: Double, secondDynamic: Boolean) {
        val capture = RotationCaptureSlot.current ?: return
        try {
            capture.add(Observation.ToiAccepted(first, second, time, secondDynamic))
        } catch (_: Throwable) {
            capture.invalidate()
        }
    }
}

internal expect object RotationCaptureSlot {
    var current: RotationOperationTap.Capture?
}
