package io.github.rubixhacker.harness.compatibility

import io.github.rubixhacker.harness.contract.CanonicalJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * The ledger declaration signature normalisation and declaration probe used by the JVM signature
 * inventory, ported from `tools/compatibility/execution_probe.py`.
 *
 * [ledgerSignature] and [declarations] are pure. [signature] runs `javap`; the host half lives in
 * `ExecutionProbeHost`.
 */
object ExecutionProbe {
    val DECLARATION_FLAGS = listOf(
        "ACC_PUBLIC",
        "ACC_PROTECTED",
        "ACC_BRIDGE",
        "ACC_SYNTHETIC",
    )

    /** One declaration as the ledger records it: its signature text and its declaration flags. */
    data class DeclaredMember(val signature: String, val flags: List<String>)

    /** Removes the `final` modifier from a static initializer or method declaration. */
    fun ledgerSignature(signature: String): String {
        val index = signature.indexOf("; descriptor: ")
        val declaration: String
        val marker: String
        val descriptor: String
        if (index < 0) {
            declaration = signature
            marker = ""
            descriptor = ""
        } else {
            declaration = signature.substring(0, index)
            marker = "; descriptor: "
            descriptor = signature.substring(index + marker.length)
        }
        val normalised = if (marker.isNotEmpty() && "(" in declaration && " static " in declaration) {
            declaration.replaceFirst(STATIC_FINAL, "")
        } else {
            declaration
        }
        return normalised + marker + descriptor
    }

    /**
     * Reads the plain and verbose `javap` output of one type and returns its header plus the
     * declaration map the ledger keys on `(name, descriptor)`.
     */
    fun declarations(
        plain: String,
        verbose: String,
        oracle: SurfaceOracle,
    ): Pair<String, Map<Pair<String, String>, DeclaredMember>> {
        val headerLine = pySplitLines(plain).map { it.trim() }.firstOrNull { it.endsWith("{") }
            ?: throw IllegalArgumentException("type header missing from plain javap output")
        val api = oracle.surface(verbose) ?: return headerLine to emptyMap()
        val records = oracle.memberInventory(verbose).second
        val classFile = linkedMapOf<Pair<String, String>, JsonObject>()
        for (record in records) {
            val key = record.textOrNull("name").orEmpty() to record.textOrNull("descriptor").orEmpty()
            if (key in classFile) {
                throw IllegalArgumentException("duplicate class-file member: ${pythonTuple(key)}")
            }
            classFile[key] = record
        }
        val members = linkedMapOf<Pair<String, String>, DeclaredMember>()
        for ((key, signatures) in api.second) {
            if (signatures.isEmpty()) {
                throw IllegalArgumentException("member signatures missing: ${pythonTuple(key)}")
            }
            for (signature in signatures) {
                val index = signature.indexOf("; descriptor: ")
                if (index < 0 || index + "; descriptor: ".length >= signature.length) {
                    throw IllegalArgumentException("member descriptor missing: $signature")
                }
                val descriptor = signature.substring(index + "; descriptor: ".length)
                val record = classFile[key.first to descriptor]
                val declaration = record?.textOrNull("declaration").orEmpty()
                if (record == null ||
                    ledgerSignature(signature) !=
                    ledgerSignature(declaration.replace(Regex("\\s+"), " ") + " descriptor: " + descriptor)
                ) {
                    throw IllegalArgumentException(
                        "strict surface differs from class-file member: $signature",
                    )
                }
                val memberKey = key.first to (if ("(" in descriptor) descriptor else "")
                if (memberKey in members) {
                    throw IllegalArgumentException("duplicate declaration: ${pythonTuple(memberKey)}")
                }
                members[memberKey] = DeclaredMember(
                    ledgerSignature(signature),
                    DECLARATION_FLAGS.filter { it in record.stringList("flags") },
                )
            }
        }
        for (record in records) {
            val flags = record.stringList("flags")
            if ("ACC_BRIDGE" !in flags ||
                ("ACC_PUBLIC" !in flags && "ACC_PROTECTED" !in flags)
            ) {
                continue
            }
            val key = record.textOrNull("name").orEmpty() to record.textOrNull("descriptor").orEmpty()
            if (key in members) {
                throw IllegalArgumentException("duplicate declaration: ${pythonTuple(key)}")
            }
            val signature = record.textOrNull("declaration").orEmpty().replace(Regex("\\s+"), " ")
            members[key] = DeclaredMember(
                ledgerSignature("$signature descriptor: ${key.second}"),
                DECLARATION_FLAGS.filter { it in flags },
            )
        }
        return headerLine to members
    }

    /** The `signature` probe result, built by [ExecutionProbeHost.signature]. */
    fun signatureResult(
        plainCommand: List<String>,
        verboseCommand: List<String>,
        plainStdout: String,
        plainStderr: String,
        plainExit: Int,
        verboseStdout: String,
        verboseStderr: String,
        verboseExit: Int,
        matched: Boolean,
    ): JsonObject {
        val cases = if (matched) 1 else 0
        val failures = if (matched) 0 else 1
        val rawStdout = CanonicalJson.render(
            buildJsonObject {
                put("plain", JsonPrimitive(plainStdout))
                put("verbose", JsonPrimitive(verboseStdout))
            },
        )
        val rawStderr = CanonicalJson.render(
            buildJsonObject {
                put("plain", JsonPrimitive(plainStderr))
                put("verbose", JsonPrimitive(verboseStderr))
            },
        )
        val output = rawStdout + "\nACTUAL_TESTS=$cases\nFAILURES=$failures\nIGNORED=0\n"
        return buildJsonObject {
            put(
                "command",
                kotlinx.serialization.json.JsonArray(
                    listOf(
                        kotlinx.serialization.json.JsonArray(plainCommand.map(::JsonPrimitive)),
                        kotlinx.serialization.json.JsonArray(verboseCommand.map(::JsonPrimitive)),
                    ),
                ),
            )
            put("expected_cases", JsonPrimitive(1))
            put("actual_executed_cases", JsonPrimitive(cases))
            put("failures", JsonPrimitive(failures))
            put("ignored", JsonPrimitive(0))
            put("process_exit_code", JsonPrimitive(if (plainExit != 0) plainExit else verboseExit))
            put("raw_stdout", JsonPrimitive(rawStdout))
            put("raw_stderr", JsonPrimitive(rawStderr))
            put("output", JsonPrimitive(output))
        }
    }

    private val STATIC_FINAL = Regex("\\bfinal ")

    private fun kotlinx.serialization.json.JsonObject.stringList(key: String): List<String> =
        this[key].arrayOrNull()?.mapNotNull { it.textOrNull() } ?: emptyList()
}

/** Renders a tuple the way Python prints it, e.g. `('name', '()V')`. */
internal fun pythonTuple(values: Pair<String, String>): String {
    fun quote(value: String): String =
        "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    return "(${quote(values.first)}, ${quote(values.second)})"
}
