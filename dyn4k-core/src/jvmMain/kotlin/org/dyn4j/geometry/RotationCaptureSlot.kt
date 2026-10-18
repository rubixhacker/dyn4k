package org.dyn4j.geometry

internal actual object RotationCaptureSlot {
    private val local = ThreadLocal<RotationOperationTap.Capture?>()
    actual var current: RotationOperationTap.Capture?
        get() = local.get()
        set(value) {
            if (value == null) local.remove() else local.set(value)
        }
}
