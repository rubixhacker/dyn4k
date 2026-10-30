package io.github.rubixhacker.harness.performance

import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/** `tools/performance/reference_study.py`: the signed reference-study archive and its rules. */
object ReferenceStudy {
    const val SOURCE_COMMIT: String = "bb7d5cf7671f96a13449a5e0c3d65ff44d4b4975"
    const val VERSION: String = "reference-study-v3"
    const val LEGACY_VERSION: String = "reference-study-v2"

    val phases: List<String> = listOf("feasibility", "source", "model_holdout", "confirmation")
    val identityFiles: List<String> = listOf("artifact", "probe", "runtime", "image")
    val rawFiles: List<String> = listOf("series", "environment", "monitor")
    val v3RawFiles: List<String> = rawFiles + listOf(
        "observer", "source_receipt", "build_receipt", "provider", "clock_origin",
        "measure_clock", "warmup_clock", "run_receipt", "staged_core", "staged_kotlin",
    )
    val controlRoutes: Map<String, String> = mapOf(
        "dyn4j_6_0_0_jvm" to "baseline",
        "row_reference_self" to "direct_kotlin",
        "direct_kotlin_self" to "direct_kotlin",
        "compatibility_self" to "compatibility",
    )
    val pairOrder: List<List<String>> = listOf(
        listOf("a", "b"),
        listOf("b", "a"),
        listOf("a", "b"),
    )

    val controlKeys: Set<String> = setOf("row_id", "control_id", "route", "host_id", "boot_id") +
        identityFiles.map { it + "_path" }

    val captureIdentityKeys: Set<String> = setOf(
        "phase", "key", "control_id", "row_id", "route", "host_id", "boot_id", "pair", "side",
        "order", "process_id", "run_id", "os_pid", "process_start_id", "started_ns", "ended_ns",
        "invalid_reason", "stop_reason",
    ) + identityFiles.map { it + "_sha256" }

    /** `reference_study.raw_files`: which sidecars an archive version carries. */
    fun rawFilesFor(version: String?): List<String> {
        if (version != VERSION && version != LEGACY_VERSION) {
            throw IllegalArgumentException("unknown study archive version")
        }
        return if (version == VERSION) v3RawFiles else rawFiles
    }

    /** `reference_study.capture_keys`: the fields one capture input must carry. */
    fun captureKeys(version: String?): Set<String> =
        captureIdentityKeys + rawFilesFor(version).map { it + "_path" }

    /** `reference_study.absolute_source_path`: a recorded control source must be an absolute path. */
    fun absoluteSourcePath(value: String?): Boolean {
        if (value.isNullOrEmpty()) return false
        if (value.startsWith("/")) return true
        if (value.startsWith("\\\\")) return true
        return value.length >= 3 && value[0].isLetter() && value[1] == ':' &&
            (value[2] == '\\' || value[2] == '/')
    }

    fun shaBytes(data: ByteArray): String = Sha256.of(data)

    fun exactKeys(value: JsonElement?, expected: Set<String>, label: String) {
        val keys = (value as? JsonObject)?.keys
        if (keys == null || keys != expected) throw IllegalArgumentException("$label keys differ")
    }

    fun hexDigest(value: JsonElement?, label: String) {
        val text = (value as? JsonPrimitive)?.takeIf { it.isString }?.content
        if (text == null || text.length != 64 || !text.all { it in "0123456789abcdef" }) {
            throw IllegalArgumentException("invalid $label")
        }
    }

    /**
     * `reference_study.policy_context`: the frozen context a protocol is signed against. The
     * checked-in manifest bytes and the tool's own digest are supplied by the caller.
     */
    fun policyContext(
        version: String,
        manifestBytes: ByteArray,
        toolDigest: String,
    ): Pair<JsonObject, Set<String>> {
        val policy = SustainedArchive.frozenPolicy(manifestBytes)
        val keys = SustainedArchive.comparisonControlKeys(policy)
        val context = buildJsonObject {
            put("manifest_sha256", SustainedArchive.FROZEN_MANIFEST_SHA256)
            put("source_commit", SOURCE_COMMIT)
            put("version", version)
            put("baseline_jar_sha256", policy.str("baseline_jar_sha256"))
            put("assignment_inventory_sha256", shaBytes(SustainedArchive.canonical(JsonArray(keys.sorted().map { JsonPrimitive(it) }))))
            put("assignment_count", keys.size)
            put("tool_sha256", toolDigest)
        }
        return context to keys
    }

    /** `reference_study.controls_for`: which controls a comparison needs. */
    fun controlsFor(key: String): List<String> {
        val parts = key.split("|")
        if (parts.size != 6) throw IllegalArgumentException("comparison key differs")
        val comparison = parts[0]
        val rowId = parts[1]
        if (comparison == "jvm_vs_dyn4j") {
            if (rowId != "jvm.java") throw IllegalArgumentException("dyn4j comparison outside JVM")
            return listOf("dyn4j_6_0_0_jvm")
        }
        if (comparison == "shim_vs_direct") {
            return listOf("compatibility_self", "direct_kotlin_self")
        }
        if (comparison != "absolute_timing" && comparison != "absolute_memory") {
            throw IllegalArgumentException("unrecognized comparison")
        }
        return listOf("row_reference_self")
    }

    /** `reference_study.checked_relative`: an archived input must exist, be non-empty, and match its digest. */
    fun checkedRelative(
        files: PerformanceFileSystem,
        root: String,
        relative: String?,
        expectedHash: JsonElement?,
    ): String {
        if (relative.isNullOrEmpty() || PerformancePaths.isAbsolute(relative) ||
            ".." in PerformancePaths.parts(relative)
        ) {
            throw IllegalArgumentException("unsafe archived path")
        }
        val path = PerformancePaths.join(PerformancePaths.normalize(root), relative)
        val size = files.sizeOf(path)
        if (size == null || size <= 0 || !files.isFile(path) || files.isSymlink(path) ||
            !PerformancePaths.isRelativeTo(path, root)
        ) {
            throw IllegalArgumentException("missing archived bytes")
        }
        hexDigest(expectedHash, "archived digest")
        if (Sha256.of(files.readBytes(path)) != expectedHash!!.jsonPrimitive.content) {
            throw IllegalArgumentException("archived bytes differ")
        }
        return path
    }

    /** `reference_study.unique_object`: a JSON object that refuses a repeated key. */
    fun uniqueObject(pairs: List<Pair<String, JsonElement>>): JsonObject {
        val value = LinkedHashMap<String, JsonElement>()
        for ((name, item) in pairs) {
            if (name in value) throw IllegalArgumentException("duplicate JSON key")
            value[name] = item
        }
        return JsonObject(value)
    }

    /**
     * `reference_study.validate_protocol`: the frozen context, assignment inventory, and control
     * files must all agree with the approved rule.
     */
    fun validateProtocol(
        protocol: JsonElement?,
        files: PerformanceFileSystem,
        root: String,
        manifestBytes: ByteArray,
        toolDigest: String,
    ): Pair<Map<List<String>, JsonObject>, Map<List<String>, JsonObject>> {
        val record = protocol as? JsonObject
        val contextElement = record?.get("context") as? JsonObject
        if (record == null || contextElement == null) throw IllegalArgumentException("missing study context")
        val version = contextElement["version"]?.let { (it as? JsonPrimitive)?.content }
        val (context, allowed) = policyContext(version ?: VERSION, manifestBytes, toolDigest)
        exactKeys(record, setOf("signature", "assignments", "controls", "context"), "protocol")
        if (contextElement != context) throw IllegalArgumentException("frozen study context differs")
        val assignmentElements = record["assignments"] as? JsonArray
        if (assignmentElements == null || assignmentElements.isEmpty()) {
            throw IllegalArgumentException("empty assignment inventory")
        }
        val seen = mutableSetOf<List<String>>()
        val needed = linkedSetOf<List<String>>()
        for (element in assignmentElements) {
            exactKeys(element, setOf("phase", "key", "controls"), "assignment")
            val assignment = element.jsonObject
            val phase = assignment.str("phase")
            val assignmentKey = assignment.str("key")
            if (phase !in phases || assignmentKey !in allowed) {
                throw IllegalArgumentException("assignment outside frozen protocol")
            }
            if (context.str("version") == VERSION) {
                if (assignmentKey.split("|")[3] != "timing") {
                    throw IllegalArgumentException("version 3 requires a timing raw schema")
                }
            }
            val controls = assignment["controls"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList()
            if (controls != controlsFor(assignmentKey)) {
                throw IllegalArgumentException("comparison control assignment differs")
            }
            val pair = listOf(phase, assignmentKey)
            if (pair in seen) throw IllegalArgumentException("duplicate assignment")
            seen.add(pair)
            val row = assignmentKey.split("|")[1]
            for (control in controls) needed.add(listOf(row, control))
        }
        val controlElements = record["controls"] as? JsonArray
            ?: throw IllegalArgumentException("controls must be a list")
        val actual = mutableSetOf<List<String>>()
        for (element in controlElements) {
            val expectedKeys = setOf("row_id", "control_id", "route", "host_id", "boot_id") +
                identityFiles.map { it + "_path" } +
                identityFiles.map { it + "_sha256" } +
                (if (context.str("version") == VERSION) identityFiles.map { it + "_source_path" } else emptySet())
            exactKeys(element, expectedKeys, "control")
            val control = element.jsonObject
            val identity = listOf(control.str("row_id"), control.str("control_id"))
            if (identity !in needed || identity in actual) {
                throw IllegalArgumentException("missing, extra, or duplicate control")
            }
            if (control.str("route") != controlRoutes[control.str("control_id")]) {
                throw IllegalArgumentException("control route differs")
            }
            if (control.str("host_id").isBlank()) throw IllegalArgumentException("missing control host")
            if (control.str("boot_id").isBlank()) throw IllegalArgumentException("missing control boot identity")
            for (name in identityFiles) {
                checkedRelative(files, root, control.str(name + "_path"), control[name + "_sha256"])
                if (context.str("version") == VERSION) {
                    val sourcePath = control[name + "_source_path"]?.jsonPrimitive?.content
                    if (!absoluteSourcePath(sourcePath)) {
                        throw IllegalArgumentException("control $name source path differs")
                    }
                }
            }
            if (control.str("control_id") == "dyn4j_6_0_0_jvm") {
                if (control["artifact_sha256"]?.jsonPrimitive?.content != context.str("baseline_jar_sha256")) {
                    throw IllegalArgumentException("dyn4j baseline artifact differs")
                }
            }
            actual.add(identity)
        }
        if (actual != needed) throw IllegalArgumentException("control inventory incomplete")
        return assignmentElements.associate {
            val assignment = it.jsonObject
            listOf(assignment.str("phase"), assignment.str("key")) to assignment
        } to controlElements.associate {
            val control = it.jsonObject
            listOf(control.str("row_id"), control.str("control_id")) to control
        }
    }

    /** `reference_study.validate_captures`: the declared pair inventory, process identity, and raw files. */
    fun validateCaptures(
        files: PerformanceFileSystem,
        root: String,
        protocol: JsonElement?,
        captures: JsonElement?,
        manifestBytes: ByteArray,
        toolDigest: String,
    ): Int {
        val (assignments, controls) = validateProtocol(protocol, files, root, manifestBytes, toolDigest)
        val version = (protocol as JsonObject).getValue("context").jsonObject.str("version")
        val kinds = rawFilesFor(version)
        val captureList = captures as? JsonArray ?: throw IllegalArgumentException("captures must be a list")
        val normalizedRoot = PerformancePaths.normalize(root)
        val protectedPaths = mutableListOf(PerformancePaths.join(normalizedRoot, "protocol.json"),
            PerformancePaths.join(normalizedRoot, "archive.json"))
        for (control in controls.values) {
            for (name in identityFiles) {
                protectedPaths.add(PerformancePaths.join(normalizedRoot, control.str(name + "_path")))
            }
        }
        val protectedInodes = protectedPaths.filter { files.isFile(it) }.mapNotNull { files.inode(it) }.toSet()
        val expected = linkedSetOf<List<String>>()
        for ((phaseAndKey, assignment) in assignments) {
            for (controlId in assignment["controls"]!!.jsonArray.map { it.jsonPrimitive.content }) {
                for ((pairIndex, sides) in pairOrder.withIndex()) {
                    for (side in sides) {
                        expected.add(
                            listOf(
                                phaseAndKey[0], phaseAndKey[1], controlId, (pairIndex + 1).toString(), side,
                            ),
                        )
                    }
                }
            }
        }
        val actual = mutableSetOf<List<String>>()
        val processIds = mutableSetOf<String>()
        val runIds = mutableSetOf<String>()
        val declaredProcesses = mutableSetOf<List<String>>()
        val processIntervals = linkedMapOf<List<String>, MutableList<Pair<Long, Long>>>()
        val rawPaths = mutableSetOf<String>()
        val rawInodes = mutableSetOf<String>()
        for (element in captureList) {
            val expectedKeys = captureKeys(version) + kinds.map { it + "_sha256" }
            exactKeys(element, expectedKeys, "capture")
            val capture = element.jsonObject
            val phase = capture.str("phase")
            val assignmentKey = capture.str("key")
            val phaseKey = listOf(phase, assignmentKey)
            if (phaseKey !in assignments) throw IllegalArgumentException("capture assignment differs")
            val rowId = assignmentKey.split("|")[1]
            if (capture.str("row_id") != rowId) throw IllegalArgumentException("capture row differs")
            val controlId = capture.str("control_id")
            if (controlId !in assignments.getValue(phaseKey)["controls"]!!.jsonArray.map { it.jsonPrimitive.content }) {
                throw IllegalArgumentException("capture control differs")
            }
            val control = controls.getValue(listOf(rowId, controlId))
            if (capture.str("route") != control.str("route") ||
                capture.str("host_id") != control.str("host_id") ||
                capture.str("boot_id") != control.str("boot_id")
            ) {
                throw IllegalArgumentException("capture route, host, or boot differs")
            }
            for (name in identityFiles) {
                if (capture[name + "_sha256"]?.jsonPrimitive?.content != control[name + "_sha256"]?.jsonPrimitive?.content) {
                    throw IllegalArgumentException("capture $name differs")
                }
            }
            val pair = capture.long("pair")
            val side = capture.str("side")
            val order = capture.long("order")
            if (pair < 1 || pair > pairOrder.size || side !in setOf("a", "b") ||
                order !in setOf(1L, 2L) || pairOrder[(pair - 1).toInt()][(order - 1).toInt()] != side
            ) {
                throw IllegalArgumentException("A/A side or order differs")
            }
            val slot = listOf(phase, assignmentKey, controlId, pair.toString(), side)
            if (slot !in expected || slot in actual) {
                throw IllegalArgumentException("duplicate or unexpected pair side")
            }
            actual.add(slot)
            for ((idKey, seen) in listOf("process_id" to processIds, "run_id" to runIds)) {
                val value = capture.str(idKey)
                if (value.isBlank() || value in seen) throw IllegalArgumentException("duplicate or missing $idKey")
                seen.add(value)
            }
            val osPid = capture.long("os_pid")
            val started = capture.long("started_ns")
            val ended = capture.long("ended_ns")
            if (osPid <= 0 || capture.str("process_start_id").isBlank() ||
                started < 0 || started >= ended || ended > Long.MAX_VALUE
            ) {
                throw IllegalArgumentException("invalid process identity or interval")
            }
            val processKey = listOf(capture.str("host_id"), capture.str("boot_id"), osPid.toString())
            val processIdentity = processKey + capture.str("process_start_id")
            if (processIdentity in declaredProcesses) {
                throw IllegalArgumentException("reused declared process identity")
            }
            declaredProcesses.add(processIdentity)
            val intervals = processIntervals.getOrPut(processKey) { mutableListOf() }
            val position = intervals.indexOfFirst { it.first > started }.let { if (it < 0) intervals.size else it }
            val before = intervals.getOrNull(position - 1)
            val after = intervals.getOrNull(position)
            if ((before != null && before.second > started) || (after != null && ended > after.first)) {
                throw IllegalArgumentException("overlapping observed host/PID intervals")
            }
            intervals.add(position, started to ended)
            if (capture["invalid_reason"] != JsonNull || capture.str("stop_reason") != "completed") {
                throw IllegalArgumentException("invalid or stopped study capture")
            }
            for (name in kinds) {
                val relative = capture.str(name + "_path")
                if (PerformancePaths.parts(relative).size < 2 ||
                    PerformancePaths.parts(relative).first() != "raw"
                ) {
                    throw IllegalArgumentException("capture raw path must be under raw/")
                }
                val path = checkedRelative(files, root, relative, capture[name + "_sha256"])
                val inode = files.inode(path)
                if (PerformancePaths.normalize(path) in rawPaths ||
                    (inode != null && inode in rawInodes) ||
                    (inode != null && inode in protectedInodes)
                ) {
                    throw IllegalArgumentException("raw archive path reused")
                }
                rawPaths.add(PerformancePaths.normalize(path))
                if (inode != null) rawInodes.add(inode)
            }
            if (version == VERSION) validateV3Capture(files, root, capture, control)
        }
        if (actual != expected) throw IllegalArgumentException("declared assignment pair inventory incomplete")
        return assignments.size
    }

    /**
     * `reference_study.validate_v3_capture`: the twelve sidecar files of a version 3 capture must
     * all describe the one observed process, its stage, and its measured series.
     */
    fun validateV3Capture(
        files: PerformanceFileSystem,
        root: String,
        capture: JsonObject,
        control: JsonObject,
    ) {
        fun json(name: String): JsonObject = v3Json(files, root, capture, name)
        fun csv(name: String, header: List<String>): List<Map<String, String?>> =
            v3Csv(files, root, capture, name, header)

        val observer = json("observer")
        val environment = json("environment")
        val monitor = json("monitor")
        val source = json("source_receipt")
        val build = json("build_receipt")
        val provider = json("provider")
        val origin = json("clock_origin")
        val run = json("run_receipt")
        exactKeys(
            source,
            setOf(
                "capture", "raw_sha256", "source_commit", "staged_core_sha256",
                "staged_kotlin_sha256", "command", "classpath",
            ),
            "source receipt",
        )
        val captureIdentity = buildJsonObject {
            for (key in captureIdentityKeys) if (key in capture) put(key, capture.getValue(key))
        }
        if (source.str("source_commit") != SOURCE_COMMIT || !sameJson(source.getValue("capture"), captureIdentity)) {
            throw IllegalArgumentException("source receipt capture or source differs")
        }
        val others = v3RawFiles.toSet() - "source_receipt"
        exactKeys(source.getValue("raw_sha256"), others, "source raw inventory")
        if (others.any { source.getValue("raw_sha256").jsonObject[it]?.jsonPrimitive?.content != capture[it + "_sha256"]?.jsonPrimitive?.content }) {
            throw IllegalArgumentException("source receipt raw digest differs")
        }
        val observedKeys = listOf(
            "host_id", "boot_id", "os_pid", "process_start_id", "process_id", "run_id",
            "started_ns", "ended_ns",
        )
        exactKeys(
            observer,
            observedKeys.toSet() + setOf("observed_command", "observed_environment", "image", "exit_code"),
            "observer",
        )
        if (!observedKeys.all { sameJson(observer.getValue(it), capture.getValue(it)) } ||
            !isJsonInteger(observer.getValue("exit_code")) ||
            observer.getValue("exit_code").jsonPrimitive.content != "0"
        ) {
            throw IllegalArgumentException("observer process or exit differs")
        }
        val image = observer.getValue("image").jsonObject
        exactKeys(image, setOf("pid", "sha256", "executable_path", "method", "observed_ns"), "observed image")
        val start = capture.long("started_ns")
        val end = capture.long("ended_ns")
        val observedNs = image.getValue("observed_ns")
        val method = image["method"]
        val executable = image["executable_path"]
        val observedAt = (observedNs as? JsonPrimitive)?.takeIf { isJsonInteger(it) }?.content?.toLong()
        if (!sameJson(image.getValue("pid"), capture.getValue("os_pid")) ||
            image["sha256"]?.jsonPrimitive?.content != control["image_sha256"]?.jsonPrimitive?.content ||
            observedAt == null || observedAt < start || observedAt >= end ||
            !isJsonString(method) || method!!.jsonPrimitive.content.isBlank() ||
            !isJsonString(executable) || executable!!.jsonPrimitive.content.isEmpty()
        ) {
            throw IllegalArgumentException("observed image identity or interval differs")
        }
        val command = observer["observed_command"] as? JsonArray
            ?: throw IllegalArgumentException("observed command differs")
        if (command.isEmpty() ||
            !command.all { isJsonString(it) && it.jsonPrimitive.content.isNotEmpty() } ||
            command[0].jsonPrimitive.content != executable.jsonPrimitive.content ||
            source["command"] != command
        ) {
            throw IllegalArgumentException("observed command differs")
        }
        val observedEnvironment = observer["observed_environment"] as? JsonObject
        if (observedEnvironment == null ||
            observedEnvironment.getStringOrNull("DYN4K_CLOCK_NONCE") != capture.str("run_id") ||
            observedEnvironment.getStringOrNull("DYN4K_SOURCE_COMMIT") != SOURCE_COMMIT
        ) {
            throw IllegalArgumentException("observed launch nonce or source differs")
        }
        val classpath = source["classpath"] as? JsonArray
            ?: throw IllegalArgumentException("source classpath differs")
        val commandStrings = command.map { it.jsonPrimitive.content }
        if ("-cp" in commandStrings) {
            if (commandStrings.count { it == "-cp" } != 1) {
                throw IllegalArgumentException("observed classpath differs")
            }
            val position = commandStrings.indexOf("-cp")
            if (position + 1 >= commandStrings.size) {
                throw IllegalArgumentException("observed classpath differs")
            }
            val value = commandStrings[position + 1]
            val separator = if (";" in value) ";" else ":"
            val expected = listOf("probe", "artifact").map {
                buildJsonObject {
                    put("path", control.getValue(it + "_source_path"))
                    put("sha256", control.getValue(it + "_sha256"))
                }
            }
            if (classpath.map { it.jsonObject } != expected ||
                classpath.map { it.jsonObject.str("path") } != value.split(separator)
            ) {
                throw IllegalArgumentException("unbound classpath entry or path")
            }
        } else {
            if (classpath.isNotEmpty() || capture.str("row_id") == "jvm.java") {
                throw IllegalArgumentException("missing JVM classpath")
            }
        }
        exactKeys(
            monitor,
            setOf("host_id", "boot_id", "os_pid", "process_start_id", "launch_nonce", "started_ns",
                "ended_ns", "samples"),
            "monitor",
        )
        val monitorKeys = listOf(
            "host_id", "boot_id", "os_pid", "process_start_id", "started_ns", "ended_ns",
        )
        val samples = monitor["samples"] as? JsonArray
        if (!monitorKeys.all { sameJson(monitor.getValue(it), capture.getValue(it)) } ||
            monitor.getStringOrNull("launch_nonce") != capture.str("run_id") ||
            samples == null || samples.isEmpty()
        ) {
            throw IllegalArgumentException("monitor process or nonce differs")
        }
        var previous = start
        for (element in samples) {
            val sample = element as? JsonObject ?: throw IllegalArgumentException("monitor sample")
            exactKeys(sample, setOf("clock_ns", "os_pid", "process_start_id", "rss_bytes"), "monitor sample")
            val stampElement = sample.getValue("clock_ns")
            if (!isJsonInteger(stampElement)) {
                throw IllegalArgumentException("monitor sample outside observed process")
            }
            val stamp = stampElement.jsonPrimitive.content.toLong()
            val rss = sample.getValue("rss_bytes")
            if (stamp < previous || stamp >= end ||
                !sameJson(sample.getValue("os_pid"), capture.getValue("os_pid")) ||
                sample.str("process_start_id") != capture.str("process_start_id") ||
                !isJsonInteger(rss) || rss.jsonPrimitive.content.toLong() < 0
            ) {
                throw IllegalArgumentException("monitor sample outside observed process")
            }
            previous = stamp
        }
        val environmentKeys = listOf("host_id", "boot_id", "os_pid", "process_start_id")
        if (!environmentKeys.all { sameJson(environment[it], capture.getValue(it)) } ||
            environment.getStringOrNull("launch_nonce") != capture.str("run_id") ||
            !sameJson(environment["observer"], observer)
        ) {
            throw IllegalArgumentException("environment observer or process differs")
        }
        for (name in identityFiles) {
            if (environment[name + "_sha256"]?.jsonPrimitive?.content != control[name + "_sha256"]?.jsonPrimitive?.content) {
                throw IllegalArgumentException("environment $name differs")
            }
        }
        for (name in listOf("series", "monitor", "provider", "clock_origin")) {
            if (environment[name + "_sha256"]?.jsonPrimitive?.content != capture[name + "_sha256"]?.jsonPrimitive?.content) {
                throw IllegalArgumentException("environment $name receipt differs")
            }
        }
        if (build.getStringOrNull("source_commit") != SOURCE_COMMIT ||
            build.getStringOrNull("runtime_sha256") != control.getStringOrNull("runtime_sha256")
        ) {
            throw IllegalArgumentException("build source or runtime differs")
        }
        val baselineControl = capture.str("control_id") == "dyn4j_6_0_0_jvm"
        val artifactField = if (baselineControl) "baseline_sha256" else "artifact_sha256"
        val probeField = if (baselineControl) "harness_sha256" else "probe_sha256"
        val imageField = build["image_sha256"] ?: control.getValue("runtime_sha256")
        if (build.getStringOrNull(artifactField) != control.getStringOrNull("artifact_sha256") ||
            build.getStringOrNull(probeField) != control.getStringOrNull("probe_sha256") ||
            imageField.jsonPrimitive.content != control.getStringOrNull("image_sha256")
        ) {
            throw IllegalArgumentException("build control or image receipt differs")
        }
        for (kind in listOf("core", "kotlin")) {
            val value = source["staged_${kind}_sha256"]
            hexDigest(value, "staged artifact")
            val text = value!!.jsonPrimitive.content
            if (build.getStringOrNull("staged_${kind}_sha256") != text ||
                environment.getStringOrNull("staged_${kind}_sha256") != text ||
                capture.getStringOrNull("staged_${kind}_sha256") != text
            ) {
                throw IllegalArgumentException("staged artifact receipt differs")
            }
        }
        val staged = buildJsonObject {
            put("core", source.getValue("staged_core_sha256"))
            put("kotlin", source.getValue("staged_kotlin_sha256"))
        }
        if (!sameJson(provider["pid"], capture.getValue("os_pid")) ||
            provider.getStringOrNull("source_commit") != SOURCE_COMMIT ||
            provider.getStringOrNull("runtime_sha256") != control.getStringOrNull("runtime_sha256") ||
            !sameJson(provider["artifact_sha256"], staged)
        ) {
            throw IllegalArgumentException("loaded provider process, source, or stage differs")
        }
        if (baselineControl) {
            val valid = provider.getStringOrNull("api") == "baseline" &&
                provider.getStringOrNull("baseline_sha256") == control.getStringOrNull("artifact_sha256") &&
                provider.getStringOrNull("loaded_core_sha256") == control.getStringOrNull("artifact_sha256") &&
                provider.getStringOrNull("loaded_harness_sha256") == control.getStringOrNull("probe_sha256") &&
                provider.getStringOrNull("loaded_adapter_sha256") == control.getStringOrNull("probe_sha256") &&
                provider["loaded_kotlin_sha256"] == JsonNull
            if (!valid) throw IllegalArgumentException("baseline loaded provider differs")
        } else {
            val valid = provider.getStringOrNull("run_id") == capture.str("run_id") &&
                provider.getStringOrNull("loaded_artifact_sha256") == control.getStringOrNull("artifact_sha256") &&
                provider.getStringOrNull("loaded_probe_sha256") == control.getStringOrNull("probe_sha256")
            if (!valid) throw IllegalArgumentException("loaded provider control differs")
        }
        val runtimeNsElement = origin["runtime_ns"]
        val runtimeNs = (runtimeNsElement as? JsonPrimitive)?.takeIf { isJsonInteger(it) }?.content?.toLong()
        if (!sameJson(origin["pid"], capture.getValue("os_pid")) ||
            origin.getStringOrNull("nonce") != capture.str("run_id") ||
            runtimeNs == null || runtimeNs < start || runtimeNs > end
        ) {
            throw IllegalArgumentException("runtime clock origin differs")
        }
        val series = csv("series", listOf("step", "elapsed_ns"))
        val measured = csv("measure_clock", listOf("step", "begin_ns", "end_ns"))
        val warmup = csv("warmup_clock", listOf("warmup_step", "begin_ns", "end_ns"))
        val assignmentMode = capture.str("key").split("|")[3]
        val sampleCount = run["sample_count"]
        val warmupCount = run["warmup_count"]
        if (series.size != measured.size ||
            run.getStringOrNull("status") != "complete" ||
            !isJsonInteger(sampleCount) || !isJsonInteger(warmupCount) ||
            sampleCount!!.jsonPrimitive.content.toLong() != series.size.toLong() ||
            warmupCount!!.jsonPrimitive.content.toLong() != warmup.size.toLong() ||
            run.getStringOrNull("mode") != assignmentMode || assignmentMode != "timing" ||
            run.getStringOrNull("api") != (if (baselineControl) "baseline" else capture.str("route"))
        ) {
            throw IllegalArgumentException("run receipt or series count differs")
        }
        previous = runtimeNs
        for ((index, row) in warmup.withIndex()) {
            val begin = row.channel("begin_ns")
            val finish = row.channel("end_ns")
            if (row.channel("warmup_step") != index.toLong() ||
                previous > begin || begin >= finish || finish > end
            ) {
                throw IllegalArgumentException("warm-up clock outside observed process")
            }
            previous = finish
        }
        for ((index, pair) in series.zip(measured).withIndex()) {
            val (sample, clock) = pair
            val begin = clock.channel("begin_ns")
            val finish = clock.channel("end_ns")
            if (sample.channel("step") != index.toLong() ||
                clock.channel("step") != index.toLong() ||
                previous > begin || begin >= finish || finish > end ||
                sample.channel("elapsed_ns") != finish - begin
            ) {
                throw IllegalArgumentException("measured series clock outside observed process")
            }
            previous = finish
        }
    }

    /** `reference_study.v3_json`: one sidecar parsed with duplicate keys refused. */
    fun v3Json(
        files: PerformanceFileSystem,
        root: String,
        capture: JsonObject,
        name: String,
    ): JsonObject {
        val path = PerformancePaths.join(PerformancePaths.normalize(root), capture.str(name + "_path"))
        val value = StrictJson.load(files.readText(path))
        return value as? JsonObject ?: throw IllegalArgumentException("$name must be a JSON object")
    }

    /** `reference_study.v3_csv`: one sidecar read as CSV with an exact header and no short rows. */
    fun v3Csv(
        files: PerformanceFileSystem,
        root: String,
        capture: JsonObject,
        name: String,
        header: List<String>,
    ): List<Map<String, String?>> {
        val path = PerformancePaths.join(PerformancePaths.normalize(root), capture.str(name + "_path"))
        val table = Csv.parse(files.readText(path))
        if (table.fieldNames != header) throw IllegalArgumentException("$name header differs")
        if (table.rows.isEmpty() ||
            table.rows.any { row -> row.keys != header.toSet() || row.values.any { it == null } }
        ) {
            throw IllegalArgumentException("$name rows differ")
        }
        return table.rows
    }

    fun sameJson(left: JsonElement?, right: JsonElement?): Boolean {
        if (left == null || right == null) return left == right
        return CanonicalJson.render(left) == CanonicalJson.render(right)
    }

    /** `type(value) is int`: a JSON integer, which excludes booleans and fractional numbers. */
    fun isJsonInteger(value: JsonElement?): Boolean {
        val primitive = value as? JsonPrimitive ?: return false
        if (primitive.isString) return false
        val content = primitive.content
        return content != "true" && content != "false" &&
            content.none { it == '.' || it == 'e' || it == 'E' }
    }

    fun isJsonString(value: JsonElement?): Boolean =
        (value as? JsonPrimitive)?.isString == true

    private fun JsonObject.getStringOrNull(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
}

/** `tools/performance/host_capacity_control.py`: the short terminal diagnostic receipt. */
object HostCapacityControl {
    const val SOURCE_PATH: String = "tools/performance/host_capacity_control.py"

    val childSource: String = listOf(
        "import json", "import os", "import sys", "import time", "from pathlib import Path", "",
        "data = bytearray(16 * 1024 * 1024)",
        "for offset in range(0, len(data), 4096):", "    data[offset] = 1",
        "Path(sys.argv[1]).write_text(str(os.getpid()))",
        "print(json.dumps({\"ready_pid\": os.getpid(), \"touched_bytes\": len(data)}), flush=True)",
        "time.sleep(30)", "",
    ).joinToString("\n")

    val fields: Set<String> = setOf(
        "version", "qualification", "status", "error", "source_commit", "tool_sha256",
        "tool_working_sha256", "tool_encoding", "host_system", "host_machine", "host_release",
        "workflow_run_id", "workflow_attempt", "pid", "started_ns", "image_observed_ns",
        "image_method", "image_path", "image_sha256", "expected_runtime_sha256",
        "sample_observed_ns", "sample_bytes", "stop_requested_ns", "stop_dispatched_ns",
        "stop_method", "stop_result", "terminal_observed_ns", "ended_ns", "terminal_exit_code",
        "terminal_wait_status", "terminal_peak_bytes", "terminal_metric_kind", "stdout_sha256",
        "stderr_sha256", "ready_sha256", "child_sha256", "executable_sha256",
    )

    /** `host_capacity_control.signature`: HMAC-SHA256 over the canonical receipt without its signature. */
    fun signature(record: JsonObject, key: ByteArray): String =
        SustainedArchive.signature(record, key)

    /**
     * `host_capacity_control.source_encoding`: proves the executed diagnostic source is the
     * committed blob, either exactly or as a Windows CRLF projection of it.
     */
    fun sourceEncoding(executed: ByteArray, committed: ByteArray): String {
        if (executed.contentEquals(committed)) return "git_exact"
        if (!committed.contains('\r'.code.toByte()) &&
            executed.contentEquals(crlf(committed))
        ) {
            return "git_crlf"
        }
        throw IllegalArgumentException("executed diagnostic source differs from committed bytes")
    }

    private fun crlf(source: ByteArray): ByteArray {
        val output = ArrayList<Byte>(source.size + 16)
        for (byte in source) {
            if (byte == '\n'.code.toByte()) output.add('\r'.code.toByte())
            output.add(byte)
        }
        return output.toByteArray()
    }
}
