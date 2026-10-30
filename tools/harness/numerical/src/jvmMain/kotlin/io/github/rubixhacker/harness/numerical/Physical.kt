package io.github.rubixhacker.harness.numerical

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.nio.file.Path

/** `tools/numerical/physical.audit_physical`: the baseline audit, then the depth comparison. */
object PhysicalHost {
    fun auditPhysical(fixture: JsonObject, reference: Path): JsonObject {
        val baseline = CompareHost.auditReference(fixture, reference)
        if (baseline["status"]?.stringOrNull() != "PASSED") {
            return buildJsonObject {
                put("status", "INVALID")
                put("reason", baseline["reason"] ?: JsonPrimitive(""))
            }
        }
        return Physical.auditRows(fixture, TraceFiles.recordsOf(reference))
    }
}
