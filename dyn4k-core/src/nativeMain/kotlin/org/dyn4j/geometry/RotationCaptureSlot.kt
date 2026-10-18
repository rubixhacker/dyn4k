package org.dyn4j.geometry

@kotlin.native.concurrent.ThreadLocal
internal actual object RotationCaptureSlot {
    actual var current: RotationOperationTap.Capture? = null
}
