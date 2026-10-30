package io.github.rubixhacker.harness.qualification

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `capture_karma_context`'s pure half: the ten `CONTEXT_*` bounds as one substitutable value, the
 * inventory document, the two byte ladders, and the enumeration and sampler predicates.
 *
 * The reference reads the bounds from module globals, and its tests patch them
 * (`mock.patch.object(safari_yarn_lock, "CONTEXT_MAX_FILES", 1)`). A JVM constant cannot be
 * patched, so [SafariContextBounds] carries the same ten values as a parameter with the production
 * defaults; every limit the scan applies and every limit the inventory advertises comes from it.
 *
 * The filesystem walk itself is [SafariContext]'s job (jvmMain).
 */
class SafariContextBounds(
    val files: Int = SafariYarnLockRules.CONTEXT_MAX_FILES,
    val fileBytes: Int = SafariYarnLockRules.CONTEXT_MAX_FILE_BYTES,
    val totalBytes: Int = SafariYarnLockRules.CONTEXT_MAX_TOTAL_BYTES,
    val entries: Int = SafariYarnLockRules.CONTEXT_MAX_ENTRIES,
    val depth: Int = SafariYarnLockRules.CONTEXT_MAX_DEPTH,
    val seconds: Int = SafariYarnLockRules.CONTEXT_MAX_SECONDS,
    val launches: Int = SafariYarnLockRules.CONTEXT_MAX_LAUNCHES,
    val rawEntries: Int = SafariYarnLockRules.CONTEXT_MAX_RAW_ENTRIES,
    val uploadBytes: Int = SafariYarnLockRules.CONTEXT_MAX_UPLOAD_BYTES,
    val inventoryBytes: Int = SafariYarnLockRules.CONTEXT_MAX_INVENTORY_BYTES,
) {
    /** The `limits` object the inventory advertises, in the reference's own key order. */
    fun limits(): List<Pair<String, Int>> = listOf(
        "files" to files,
        "file_bytes" to fileBytes,
        "total_bytes" to totalBytes,
        "upload_bytes" to uploadBytes,
        "inventory_bytes" to inventoryBytes,
        "raw_entries" to rawEntries,
        "entries" to entries,
        "depth" to depth,
        "seconds" to seconds,
        "launches" to launches,
    )
}

/**
 * The `inventory` dictionary `capture_karma_context` builds, appends to, and writes to
 * `inventory.json`.
 *
 * `record` is the reference's nested function of the same name: the one place that decides whether
 * a recorded entry leaves the scan incomplete. The counters are read back out of the document, as
 * the reference reads them, so a byte budget is computed from what was actually recorded.
 */
class SafariContextInventory(
    private val candidateSha: String,
    private val bounds: SafariContextBounds,
) {
    val values: MutableMap<String, JsonElement> = LinkedHashMap()
    val inputs: MutableList<JsonObject> = mutableListOf()

    /** The reference's nonlocal `incomplete` flag. */
    var incomplete: Boolean = false
        private set

    init {
        values["schema"] = JsonPrimitive(1)
        values["candidate_sha"] = JsonPrimitive(candidateSha)
        values["qualified"] = JsonPrimitive(false)
        values["status"] = JsonPrimitive(SafariContextRules.INCOMPLETE)
        values["limits"] = JsonObject(
            LinkedHashMap(bounds.limits().associate { it.first to JsonPrimitive(it.second) }),
        )
        values["entries_seen"] = JsonPrimitive(0)
        values["matched_files"] = JsonPrimitive(0)
        values["copied_files"] = JsonPrimitive(0)
        values["copied_bytes"] = JsonPrimitive(0)
        values["upload_data_bytes"] = JsonPrimitive(0)
    }

    /** `record`: one `inputs` entry, and the completeness consequence of writing it. */
    fun record(
        path: String,
        status: String,
        reason: String,
        details: Map<String, JsonElement> = emptyMap(),
    ) {
        val entry = LinkedHashMap<String, JsonElement>()
        entry["path"] = JsonPrimitive(path)
        entry["status"] = JsonPrimitive(status)
        entry["reason"] = JsonPrimitive(reason)
        entry.putAll(details)
        inputs.add(JsonObject(entry))
        if (SafariContextRules.recordIsIncomplete(status, reason)) incomplete = true
    }

    fun counter(key: String): Long = Py.int(values[key])

    fun add(key: String, delta: Long) {
        values[key] = JsonPrimitive(counter(key) + delta)
    }

    /** `CONTEXT_MAX_TOTAL_BYTES - copied_bytes`, as the scan's per-file budget sees it. */
    fun totalRemaining(): Long = bounds.totalBytes.toLong() - counter("copied_bytes")

    /** `CONTEXT_MAX_UPLOAD_BYTES - CONTEXT_MAX_INVENTORY_BYTES - upload_data_bytes`, clamped. */
    fun uploadRemaining(): Long =
        bounds.uploadBytes.toLong() - bounds.inventoryBytes.toLong() - counter("upload_data_bytes")

    /** Python's `min(total - copied, upload - inventory - data)`, unclamped. */
    fun fileRemaining(): Long = minOf(totalRemaining(), uploadRemaining())

    private fun document(): JsonObject {
        val document = LinkedHashMap(values)
        document["inputs"] = JsonArray(inputs.toList())
        return JsonObject(document)
    }

    /**
     * The bytes written to `inventory.json`: `json.dumps(inventory, indent=2, sort_keys=True)` plus
     * a newline, trimmed of its tail entries until it fits, and then a hard bound.
     */
    fun encode(): String {
        var encoded = PyJson.renderSorted(document()) + "\n"
        var omitted = 0L
        while (encoded.length > bounds.inventoryBytes && inputs.isNotEmpty()) {
            inputs.removeAt(inputs.size - 1)
            omitted += 1
            values["status"] = JsonPrimitive(SafariContextRules.INCOMPLETE)
            values["inventory_entries_omitted"] = JsonPrimitive(omitted)
            encoded = PyJson.renderSorted(document()) + "\n"
        }
        if (encoded.length > bounds.inventoryBytes) {
            throw IllegalArgumentException("Safari context inventory exceeds its byte bound")
        }
        return encoded
    }
}

/** The pure predicates and byte ladders of `capture_karma_context`. */
object SafariContextRules {
    const val COMPLETE = "CONTEXT_COMPLETE"
    const val INCOMPLETE = "CONTEXT_INCOMPLETE"

    /** The reference reads files in 64 KiB chunks so the deadline is checked while copying. */
    const val CHUNK_BYTES = 64 * 1024

    /** `fnmatch.fnmatchcase(name, "*karma*.js")`: a literal dot, not the regex wildcard. */
    private val KARMA_NAME = Regex(".*karma.*\\.js", RegexOption.DOT_MATCHES_ALL)

    /** `re.fullmatch(r"launch-[0-9]+\.txt", name)`. */
    private val LAUNCH_NAME = Regex("launch-[0-9]+\\.txt")

    /** The accepted `launch-outcome-<pid>.txt` shapes, including the pending-open one. */
    private val OUTCOME = Regex("(?:open_state=finished\\n)?open_exit=\\d+\\n")

    fun isKarmaConfigName(name: String): Boolean = KARMA_NAME.matches(name)

    fun isLaunchName(name: String): Boolean = LAUNCH_NAME.matches(name)

    /** `launch.removeprefix("launch-").removesuffix(".txt")`. */
    fun launchPid(name: String): String = name.removePrefix("launch-").removeSuffix(".txt")

    /**
     * The sidecars a raw launch context must hold: the three fixed host snapshots plus seven per
     * launch, in the reference's order.
     */
    fun requiredSidecars(launches: List<String>): List<String> {
        val required = mutableListOf("session-after.txt", "process-after.txt", "host-outcome.txt")
        for (launch in launches) {
            val pid = launchPid(launch)
            required.addAll(
                listOf(
                    launch,
                    "process-$pid.txt",
                    "redirect-$pid.html",
                    "open-$pid.stdout",
                    "open-$pid.stderr",
                    "sample-state-$pid.txt",
                    "launch-outcome-$pid.txt",
                ),
            )
        }
        return required
    }

    /** The raw-context names the launcher did not produce; the reference skips each one. */
    fun unexpectedSidecars(names: List<String>, required: List<String>): List<String> =
        names.filter { it !in required }

    /**
     * `status` of a copied configuration: `truncated` when fewer bytes than the source were kept.
     */
    fun copyStatus(retained: Long, original: Long): String =
        if (retained < original) "truncated" else "copied"

    /**
     * The reason of a scanned configuration. `perFileLimit` is the reference's
     * `CONTEXT_MAX_FILE_BYTES <= remaining`, which decides whether a truncation is the per-file
     * bound or the total budget.
     */
    fun copyReason(status: String, perFileLimit: Boolean): String = when {
        status == "truncated" && perFileLimit -> "per_file_byte_limit"
        status == "truncated" -> "total_byte_limit"
        else -> "copied"
    }

    /**
     * The reason of a copied sidecar. A truncated sidecar never claims the total budget: its only
     * budgets are the per-file bound and the upload bound the inventory itself sets aside.
     */
    fun sidecarReason(status: String, perFileLimit: Boolean): String = when {
        status == "truncated" && perFileLimit -> "per_file_byte_limit"
        status == "truncated" -> "upload_byte_limit"
        else -> "copied"
    }

    /**
     * The reference's `record` consequence: a failed or truncated entry, or a reason that is
     * neither a clean copy nor the one exclusion it tolerates, leaves the scan incomplete.
     */
    fun recordIsIncomplete(status: String, reason: String): Boolean =
        status == "failed" || status == "truncated" ||
            (reason != "copied" && reason != "excluded_node_modules")

    /** `[line for line in process if line.startswith("sample=")] == ["sample=1"..."sample=5"]`. */
    fun samplesComplete(lines: List<String>): Boolean =
        lines.filter { it.startsWith("sample=") } == (1..5).map { "sample=$it" }

    /** `sample-state-<pid>.txt` must record a finished, successful sampler. */
    fun samplerStateComplete(lines: List<String>): Boolean =
        lines == listOf("samples_completed=5", "sampler_exit=0")

    /** `host-outcome.txt` must record a clean session and process exit. */
    fun hostOutcomeComplete(lines: List<String>): Boolean =
        lines == listOf("session_exit=0", "process_exit=0")

    /** A launch outcome the scan accepts as finished: pending-open, or finished/exited. */
    fun outcomeAccepted(text: String): Boolean = pendingOpen(text) || OUTCOME.matches(text)

    /** `outcome_text == "open_state=pending\n"`. */
    fun pendingOpen(text: String): Boolean = text == "open_state=pending\n"

    /**
     * Python's `str.splitlines()`: every line boundary the reference recognises. The sampler text
     * is read with `errors="replace"`, so this is a `str` split, not a byte split.
     */
    fun splitLines(text: String): List<String> {
        val lines = mutableListOf<String>()
        val current = StringBuilder()
        var index = 0
        while (index < text.length) {
            val char = text[index]
            val breaks = char == '\n' || char == '\r' || char == '\u000B' || char == '\u000C' ||
                char == '\u001C' || char == '\u001D' || char == '\u001E' ||
                char == '\u0085' || char == '\u2028' || char == '\u2029'
            if (breaks) {
                lines.add(current.toString())
                current.setLength(0)
                if (char == '\r' && index + 1 < text.length && text[index + 1] == '\n') index++
            } else {
                current.append(char)
            }
            index++
        }
        if (current.isNotEmpty()) lines.add(current.toString())
        return lines
    }
}
