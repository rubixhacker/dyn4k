package io.github.rubixhacker.harness.migration

/**
 * The plain-run admission checks of `tools/migration/validate_plain.py`.
 *
 * The Python module reads one evidence directory holding logs, a launch record, and frames. This
 * object holds the ordered checks and the exact evidence text; the JVM adapter supplies the reads.
 */
object PlainValidation {
    val SCENES = linkedSetOf("Tracking", "Pyramid", "Crank", "Billiards", "Truck")

    val EXPECTED = linkedMapOf(
        "Tracking" to 10,
        "Pyramid" to 10,
        "Crank" to 9,
        "Billiards" to 9,
        "Truck" to 19,
    )

    val INPUT_MARKERS = linkedMapOf(
        "Tracking" to listOf("key c"),
        "Pyramid" to listOf("drag left mouse", "key r"),
        "Crank" to listOf("observe motor motion"),
        "Billiards" to listOf("keydown plus", "keydown s", "keyup s"),
        "Truck" to listOf("keydown Right", "key s"),
    )

    /**
     * `validate_plain.validate`.
     *
     * [readPng] returns the frame record `{"width", "height", "sha256"}` or null when the file is
     * missing or does not decode. [timeline] answers the Truck timeline rule.
     */
    fun validate(
        scene: String,
        applicationLog: String,
        inputsLog: String,
        launchText: String,
        termination: PyValue,
        readPng: (String) -> PyValue?,
        timeline: () -> Pair<Boolean, String>,
    ): PyValue {
        val checks = mutableListOf<PyValue>()
        fun check(name: String, passed: Boolean, evidence: String = "") {
            checks.add(
                pyMap(
                    "id" to pyText(name),
                    "status" to pyText(if (passed) "passed" else "failed"),
                    "evidence" to pyText(evidence),
                ),
            )
        }

        check("original_main_recorded", "main=org.dyn4j.samples.$scene" in launchText)
        val classpath = launchText.split('\n')
            .firstOrNull { it.startsWith("classpath=") }
            ?.substringAfter("classpath=") ?: ""
        check(
            "plain_classpath",
            classpath.isNotEmpty() && listOf("/work/classes:", "SceneObserver", "HookWeaver", "javassist")
                .none { it in classpath },
            classpath,
        )
        check("application_initialized", "Controls:" in applicationLog)
        check("no_application_error", !DIAGNOSTIC.containsMatchIn(applicationLog))
        check(
            "input_recorded",
            "scene=$scene" in inputsLog &&
                INPUT_MARKERS.getValue(scene).all { it in inputsLog },
        )
        val closeRequested = termination.getOrNull("close_requested")
        val exitedAfterClose = termination.getOrNull("exited_after_close")
        val forcedTermination = termination.getOrNull("forced_termination")
        val exitCode = termination.getOrNull("exit_code")
        check(
            "controlled_close",
            closeRequested is PyValue.Bool && closeRequested.value &&
                exitedAfterClose is PyValue.Bool && exitedAfterClose.value &&
                forcedTermination is PyValue.Bool && !forcedTermination.value &&
                exitCode != null && pyEquals(exitCode, pyInt(0)),
        )

        val frames = linkedMapOf<String, PyValue>()
        for (name in listOf("initial", "after-input", "late")) {
            val frame = readPng("$name.png")
            frames[name] = frame ?: PyValue.Null
            check(
                "${name}_frame",
                frame != null && frameValid(frame),
                if (frame != null) pythonRepr(frame) else "missing or invalid PNG",
            )
        }
        if (scene == "Tracking") {
            check("own_contact_listener", "BEGIN:" in applicationLog && "END:" in applicationLog)
        }
        if (scene == "Pyramid") {
            val frame = readPng("interaction.png")
            frames["interaction"] = frame ?: PyValue.Null
            check("interaction_frame", frame != null && frameValid(frame))
        }
        if (scene == "Truck") {
            for (name in TruckTimeline.FRAMES) {
                if (frames.containsKey(name)) continue
                val frame = readPng("$name.png")
                frames[name] = frame ?: PyValue.Null
                check("${name}_frame", frame != null && frameValid(frame))
            }
            val verdict = timeline()
            check("truck_timeline", verdict.first, verdict.second)
        }
        val failed = checks.count { pyEquals(it.get("status"), pyText("failed")) }
        return pyMap(
            "scene" to pyText(scene),
            "mode" to pyText("plain-original-main"),
            "expected" to pyInt(checks.size),
            "executed" to pyInt(checks.size),
            "failed" to pyInt(failed),
            "unexecuted" to pyInt(0),
            "passed" to pyInt(checks.size - failed),
            "checks" to pyList(checks),
            "frames" to PyValue.Map(frames),
            "visual_review_status" to pyText("UNREVIEWED"),
            "visual_physics_review" to pyText(
                "reported separately; frame presence is not physics evidence",
            ),
        )
    }

    /**
     * `validate_plain.main`'s `--summary` object over the five scene directories.
     *
     * [readScene] returns the parsed `plain-validation.json` for one scene, or null when the file
     * is absent or malformed, which the Python module treats as an empty result.
     */
    fun summary(readScene: (String) -> PyValue?): PyValue {
        val scenes = linkedMapOf<String, PyValue>()
        for (scene in SCENES.sortedWith(io.github.rubixhacker.harness.contract.CanonicalJson::compareCodePoints)) {
            val result = readScene(scene) as? PyValue.Map
            val executed = result?.entries?.get("executed") ?: pyInt(0)
            scenes[scene] = pyMap(
                "expected" to pyInt(EXPECTED.getValue(scene)),
                "executed" to executed,
                "failed" to (result?.entries?.get("failed") ?: pyInt(0)),
                "unexecuted" to pySubtract(pyInt(EXPECTED.getValue(scene)), executed),
            )
        }
        val totals = linkedMapOf<String, PyValue>()
        for (key in listOf("expected", "executed", "failed", "unexecuted")) {
            totals[key] = pyInt(
                scenes.values.sumOf { pyNumberValue(it.get(key)).toLong() },
            )
        }
        return pyMap(
            "mode" to pyText("plain-original-main"),
            "scenes" to PyValue.Map(scenes),
            "totals" to PyValue.Map(totals),
        )
    }

    private fun frameValid(frame: PyValue): Boolean =
        pyEquals(frame.get("width"), pyInt(TruckTimeline.PNG_WIDTH)) &&
            pyEquals(frame.get("height"), pyInt(TruckTimeline.PNG_HEIGHT))

    private val DIAGNOSTIC = Regex("Shouldn't happen|Exception|Error")
}
