package io.github.rubixhacker.harness.numerical

import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Thrown where `rotation_oracle` needs an MPFR interval, which this port does not carry. */
class MpfrNotPorted(facility: String) : UnsupportedOperationException(
    "MPFR is not ported: $facility (the ctypes binding to libmpfr stays with the Python module)",
)

/**
 * `portable/rotation_oracle.py`: the pure half of the rotation arithmetic auditor.
 *
 * The encoding helpers, the digest and manifest helpers, and the binary64 pair readers are
 * ported. Every entry point that needs a certified `cos`/`sin` enclosure, or the class-loading
 * binding that proves which jar produced the audit, throws [MpfrNotPorted] instead of returning an
 * unverified pass.
 */
object RotationOracle {
    const val SOURCE_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
    const val MPFR_VERSION = "4.2.2"

    private val HEX = Regex("[0-9a-f]{16}")
    private val SHA = Regex("[0-9a-f]{64}")

    /** `rotation_oracle._bits`. */
    fun bits(value: Double): String = value.toRawBits().toULong().toString(16).padStart(16, '0')

    /** `rotation_oracle._binary64`. */
    fun binary64(value: JsonElement?): Double {
        val text = value.stringOrNull()
        if (text == null || !HEX.matches(text)) {
            throw IllegalArgumentException("invalid binary64 encoding")
        }
        val decoded = Double.fromBits(text.toULong(16).toLong())
        if (!decoded.isFinite()) throw IllegalArgumentException("nonfinite binary64 field")
        return decoded
    }

    /** `rotation_oracle._pair`. */
    fun pair(value: JsonElement?): Pair<Double, Double> {
        val array = value as? JsonArray
        if (array == null || array.size != 2) {
            throw IllegalArgumentException("incomplete binary64 pair")
        }
        return binary64(array[0]) to binary64(array[1])
    }

    /** `rotation_oracle._state_pair`: the encoded cost and sine of a transform. */
    fun statePair(transform: JsonObject): Pair<String, String> {
        val cost = transform["getCost"]?.numberOrNull()
        val sine = transform["getSint"]?.numberOrNull()
        if (cost == null || sine == null) throw IllegalArgumentException("invalid transform pair")
        return bits(cost) to bits(sine)
    }

    /** `rotation_oracle._digest`: the canonical-JSON digest of a value. */
    fun digest(value: JsonElement): String = Sha256.ofCanonical(value)

    /** `rotation_oracle._manifest_bytes`. */
    fun manifestBytes(value: JsonObject): ByteArray =
        CanonicalJson.render(value).toByteArray(Charsets.UTF_8)

    /** `rotation_oracle._audit_bytes`. */
    fun auditBytes(value: JsonObject): ByteArray =
        CanonicalJson.render(value).toByteArray(Charsets.UTF_8)

    /**
     * `rotation_oracle.trig_interval`: a certified `[cos, sin]` enclosure at 320-bit precision.
     */
    fun trigInterval(angleBits: JsonElement?): Pair<Pair<Double, Double>, Pair<Double, Double>> =
        throw MpfrNotPorted("rotation_oracle.trig_interval")

    /** `rotation_oracle.verify_rotation_arithmetic`. */
    fun verifyRotationArithmetic(
        audit: JsonElement?,
        states: Map<Int, JsonObject>,
        traceBytes: ByteArray,
        payloadBytes: ByteArray,
        receiptBytes: ByteArray,
    ): Nothing = throw MpfrNotPorted("rotation_oracle.verify_rotation_arithmetic")

    /** `rotation_oracle.verify_operation_marker`. */
    fun verifyOperationMarker(marker: JsonElement?): Nothing =
        throw MpfrNotPorted("rotation_oracle.verify_operation_marker")

    /** True when the value is the JSON null the auditor treats as "absent". */
    fun absent(value: JsonElement?): Boolean = value == null || value is JsonNull

    /** The shape of one recorded rotation call, kept so callers can name the fields. */
    val CALL_FIELDS = setOf(
        "sequence", "step", "body_id", "kind", "branch", "pre", "trig",
        "raw", "post", "clamp",
    )

    /** The binary64 pair a call carries, or null when the field is absent. */
    fun pairOrNull(value: JsonElement?): Pair<Double, Double>? =
        if (absent(value)) null else pair(value)
}
