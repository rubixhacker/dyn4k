package org.dyn4j.world

import org.dyn4j.geometry.RotationOperationTap

internal object ToiAcceptedResetTap {
    fun record(first: Any, second: Any, time: Double, secondDynamic: Boolean) {
        RotationOperationTap.recordToi(first, second, time, secondDynamic)
    }
}
