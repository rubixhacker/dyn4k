package io.github.rubixhacker.harness.performance

/** `tools/performance/candidate_pilot.py`: pilot state identity and metadata separation. */
object CandidatePilot {
    /** The channels that identify a simulated scene's state, independent of timing. */
    val stateFields: List<String> = listOf(
        "body_count", "joint_count", "awake_count", "linear_speed_sum_m_per_s",
        "angular_speed_sum_rad_per_s", "contact_begins", "contact_ends", "toi_events",
        "broadphase_candidates", "active_contact_pairs", "active_contact_points",
    )

    /** `candidate_pilot.state_checksum`: digests the scene state channels of a raw step table. */
    fun stateChecksum(text: String): String {
        val digest = Sha256Stream()
        for (row in Csv.parse(text).rows) {
            val line = stateFields.joinToString(",") { row.required(it) } + "\n"
            digest.update(line.encodeToByteArray())
        }
        return digest.hexDigest()
    }

    /**
     * `candidate_pilot.clean_warmup`: splits a warm-up stream into its `#key=value` metadata and
     * its CSV body, and proves the metadata names the process that produced it.
     */
    fun cleanWarmup(text: String, api: String, processPid: Long): Pair<Map<String, Long>, String> {
        val metadata = linkedMapOf<String, Long>()
        val lines = mutableListOf<String>()
        // `str.splitlines` recognises a lone carriage return as a line boundary as well.
        for (line in splitLines(text)) {
            if (line.startsWith("#")) {
                val separator = line.indexOf('=', 1)
                if (separator < 0) throw IllegalArgumentException("malformed warm-up marker: $line")
                metadata[line.substring(1, separator)] =
                    line.substring(separator + 1).toLongOrNull()
                        ?: throw IllegalArgumentException("malformed warm-up marker: $line")
            } else {
                lines.add(line)
            }
        }
        val marker = when (api) {
            "direct_kotlin" -> 1L
            "compatibility" -> 2L
            else -> null
        }
        if (marker != null &&
            (metadata["process_pid"] != processPid || metadata["route_marker"] != marker)
        ) {
            throw IllegalArgumentException("plateau route or process identity differs from the launcher")
        }
        return metadata to (lines.joinToString("\n") + "\n")
    }

    /**
     * `candidate_pilot.select_scenarios`: resolves `family.variant` names against the frozen
     * manifest, defaulting to the pilot list.
     */
    fun selectScenarios(names: List<String>): List<Pair<String, String>> {
        if (names.isEmpty()) return Measure.pilot
        val variants = PerformanceManifest.scenarios()
            .map { it.str("family") to it.str("variant") }
            .toSet()
        val selected = mutableListOf<Pair<String, String>>()
        for (name in names) {
            val matches = variants.filter { (family, variant) -> name == "$family.$variant" }
            if (matches.size != 1) throw IllegalArgumentException("unknown frozen workload: $name")
            selected.add(matches.first())
        }
        return selected
    }

    /** `str.splitlines`, which treats `\r`, `\n`, and `\r\n` as boundaries and drops a final one. */
    fun splitLines(text: String): List<String> {
        val lines = mutableListOf<String>()
        val current = StringBuilder()
        var index = 0
        while (index < text.length) {
            val char = text[index]
            when (char) {
                '\r' -> {
                    lines.add(current.toString())
                    current.setLength(0)
                    index += if (index + 1 < text.length && text[index + 1] == '\n') 2 else 1
                }
                '\n' -> {
                    lines.add(current.toString())
                    current.setLength(0)
                    index += 1
                }
                else -> {
                    current.append(char)
                    index += 1
                }
            }
        }
        if (current.isNotEmpty()) lines.add(current.toString())
        return lines
    }
}
