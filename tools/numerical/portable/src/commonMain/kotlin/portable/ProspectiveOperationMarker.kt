package portable

import org.dyn4j.geometry.RotationOperationTap

internal object ProspectiveOperationMarker {
    private fun hex(value: Double): String =
        value.toBits().toULong().toString(16).padStart(16, '0')

    private fun optional(value: Double?): String =
        if (value == null) "null" else "\"${hex(value)}\""

    private fun bits(value: Long?): String =
        if (value == null) "null" else
            "\"${value.toULong().toString(16).padStart(16, '0')}\""

    private fun name(value: String?): String = if (value == null) "null" else "\"$value\""

    fun encode(capture: RotationOperationTap.Capture, call: RotationOperationTap.Call): String {
        val target = capture.targetToken(call.target)
        return "{\"schema\":\"portable-rotation-op/2\",\"method\":\"${capture.method}\"," +
            "\"sequence\":${capture.nextSequence()},\"target_token\":$target," +
            "\"case_id\":${name(call.caseId)},\"step\":${call.step}," +
            "\"body_id\":${name(call.bodyId)}," +
            "\"kind\":\"${call.kind}\",\"source\":\"${call.source}\"," +
            "\"pre\":[\"${hex(call.preCost)}\",\"${hex(call.preSint)}\"]," +
            "\"trig\":[\"${hex(call.trigCost)}\",\"${hex(call.trigSint)}\"]," +
            "\"raw\":[${optional(call.rawCost)},${optional(call.rawSint)}]," +
            "\"post\":[\"${hex(call.postCost)}\",\"${hex(call.postSint)}\"]," +
            "\"angle_bits\":${bits(call.angleBits)}," +
            "\"alpha_bits\":${optional(call.alpha)}," +
            "\"start_angle_bits\":${optional(call.startAngle)}," +
            "\"end_angle_bits\":${optional(call.endAngle)}," +
            "\"diff_bits\":${optional(call.difference)}," +
            "\"start\":[${optional(call.startCost)},${optional(call.startSint)}]," +
            "\"end\":[${optional(call.endCost)},${optional(call.endSint)}]}"
    }
}
