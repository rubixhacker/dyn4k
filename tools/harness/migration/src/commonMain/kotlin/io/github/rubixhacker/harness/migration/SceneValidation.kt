package io.github.rubixhacker.harness.migration

import kotlinx.serialization.json.Json

/**
 * The observed-scene checks of `tools/migration/validate_scene.py`.
 *
 * The Python module reads one observer log, parses its `OBS_JSON` lines, and evaluates the same
 * ordered list of checks per scene. This object holds that contract; the JVM entry point supplies
 * the file reads.
 */
object SceneValidation {
    /** Expected body counts per scene, in the order `SCENES` records them. */
    val SCENES = linkedMapOf(
        "Tracking" to 9L,
        "Pyramid" to 121L,
        "Crank" to 4L,
        "Billiards" to 21L,
        "Truck" to 35L,
    )

    /** `json.loads` accepts `NaN` and `Infinity`, so the observer reader must too. */
    private val json = Json {
        allowSpecialFloatingPointValues = true
        isLenient = false
    }

    /** `validate_scene.body`. */
    fun body(sample: PyValue, index: Int): PyValue = sample.get("bodies").at(index)

    /** `validate_scene.truck_motor_bounds`, or null when the phases cannot be established. */
    fun truckMotorBounds(samples: List<PyValue>): PyValue? = try {
        val active = samples.map { sample ->
            pyIterate(sample.get("joints")).any { !pyEquals(it.get("motorSpeed"), pyInt(0)) }
        }
        val firstDrive = (1 until samples.size).firstOrNull { active[it] && !active[it - 1] }
            ?: throw NoSuchElementException()
        val firstBrake = (firstDrive + 1 until samples.size)
            .firstOrNull { !active[it] && active[it - 1] }
            ?: throw NoSuchElementException()
        fun state(index: Int): PyValue {
            val sample = samples[index]
            return pyMap(
                "nanos" to sample.get("nanos"),
                "steps" to sample.get("steps"),
                "chassis_x" to body(sample, 2).get("x"),
                "chassis_vx" to body(sample, 2).get("vx"),
            )
        }
        var maxGap: PyValue? = null
        var largest = 0.0
        for (index in 1 until samples.size) {
            val gap = pySubtract(samples[index].get("nanos"), samples[index - 1].get("nanos"))
            val size = pyNumberValue(gap)
            if (maxGap == null || size > largest) {
                largest = size
                maxGap = gap
            }
        }
        val gap = maxGap ?: throw MigrationFailure("max() iterable argument is empty")
        pyMap(
            "clock_domain" to pyText(
                "observer JVM System.nanoTime; not subtracted from host camera clock",
            ),
            "drive_transition" to pyList(state(firstDrive - 1), state(firstDrive)),
            "brake_transition" to pyList(state(firstBrake - 1), state(firstBrake)),
            "max_snapshot_gap_ns" to gap,
            "brake_index" to pyInt(firstBrake),
        )
    } catch (error: NoSuchElementException) {
        null
    } catch (error: PyKeyError) {
        null
    } catch (error: PyIndexError) {
        null
    } catch (error: PyTypeError) {
        null
    } catch (error: MigrationFailure) {
        null
    }

    /** Splits an observer log into parsed samples and parse-error descriptions. */
    fun parseObserverLog(logText: String): Pair<List<PyValue>, List<String>> {
        val samples = mutableListOf<PyValue>()
        val errors = mutableListOf<String>()
        for ((index, line) in logText.split('\n').withIndex()) {
            if (!line.startsWith("OBS_JSON ")) continue
            val payload = line.removePrefix("OBS_JSON ")
            try {
                samples.add(pyFromJson(json.parseToJsonElement(payload)))
            } catch (error: IllegalArgumentException) {
                errors.add("line ${index + 1}: ${error.message}")
            }
        }
        return samples to errors
    }

    /**
     * `validate_scene.checks_for`.
     *
     * [timeline] returns the Truck timeline verdict, or null when no evidence directory is given,
     * which the Python module records as the fixed `timeline directory missing` failure.
     */
    fun checksFor(
        scene: String,
        logText: String,
        inputText: String,
        samples: List<PyValue>,
        parseErrors: List<String>,
        timeline: (() -> Pair<Boolean, String>)? = null,
    ): List<PyValue> {
        val checks = mutableListOf<PyValue>()
        fun check(name: String, result: Boolean?, evidence: String = "") {
            val status = when (result) {
                null -> "skipped"
                true -> "passed"
                false -> "failed"
            }
            checks.add(
                pyMap(
                    "id" to pyText(name),
                    "status" to pyText(status),
                    "evidence" to pyText(evidence),
                ),
            )
        }
        fun whenSamples(name: String, predicate: () -> Boolean, evidence: String = "") {
            try {
                check(name, if (samples.isNotEmpty()) predicate() else null, evidence)
            } catch (error: PyKeyError) {
                check(name, false, error.message ?: "")
            } catch (error: PyIndexError) {
                check(name, false, error.message ?: "")
            } catch (error: PyTypeError) {
                check(name, false, error.message ?: "")
            } catch (error: MigrationFailure) {
                check(name, false, error.message ?: "")
            }
        }

        check("log_present", logText.isNotEmpty())
        check("snapshots_present", samples.size >= 2, "snapshots=${samples.size}")
        check("snapshots_parseable", parseErrors.isEmpty(), "parse_errors=${parseErrors.size}")
        check("input_record_present", inputText.isNotEmpty() && "scene=$scene" in inputText)
        check("no_error_diagnostics", !DIAGNOSTIC.containsMatchIn(logText))
        check("clean_game_loop_shutdown", "OBSERVER_SHUTDOWN joined=true disposed=true" in logText)

        fun completeAndFinite(): Boolean {
            for (sample in samples) {
                if (!pyEquals(sample.get("scene"), pyText(scene))) return false
                val bodies = sample.get("bodies")
                val joints = sample.get("joints")
                if (!pyEquals(sample.get("bodyCount"), pyInt(pyLength(bodies)))) return false
                if (!pyEquals(sample.get("jointCount"), pyInt(pyLength(joints)))) return false
                if (!pyEquals(
                        pyList(pyIterate(bodies).map { it.get("i") }),
                        pyRange(integerValue(sample.get("bodyCount"))),
                    )
                ) {
                    return false
                }
                if (!pyEquals(
                        pyList(pyIterate(joints).map { it.get("i") }),
                        pyRange(integerValue(sample.get("jointCount"))),
                    )
                ) {
                    return false
                }
                if (pyCompare(sample.get("threadId"), pyInt(1), "<=") <= 0 || !sample.get("ccdMode").truthy()) {
                    return false
                }
                for (key in listOf(
                    "begin", "persist", "end", "toiCalls", "toiHits", "toiListenerHits", "resets", "steps",
                )) {
                    val value = sample.get(key)
                    if (!isInstanceInt(value) || pyCompare(value, pyInt(0), "<") < 0) return false
                }
                val stepDt = sample.get("stepDt")
                if (!finiteValue(stepDt) || pyCompare(stepDt, pyInt(0), "<") < 0) return false
                for (item in pyIterate(bodies)) {
                    if (item.get("rest") !is PyValue.Bool) return false
                    for (key in listOf("x", "y", "vx", "vy")) {
                        if (!finiteValue(item.get(key))) return false
                    }
                }
                for (item in pyIterate(joints)) {
                    if (!item.get("type").truthy()) return false
                    for (key in listOf("motorSpeed", "translation")) {
                        if (!finiteValue(item.get(key))) return false
                    }
                }
            }
            return true
        }

        whenSamples("complete_finite_snapshots", ::completeAndFinite)
        whenSamples("one_game_loop_thread", {
            pyIterate(PyValue.Seq(samples)).map { pyHashKey(it.get("threadId")) }.toSet().size == 1
        })
        whenSamples("time_progressed", {
            samples.zipWithNext().all { (a, b) -> pyCompare(b.get("nanos"), a.get("nanos"), ">") > 0 }
        })
        whenSamples("steps_progressed", {
            samples.size >= 2 &&
                pyCompare(samples.last().get("steps"), samples.first().get("steps"), ">") > 0 &&
                samples.zipWithNext().all { (a, b) -> pyCompare(b.get("steps"), a.get("steps"), ">=") >= 0 }
        })
        whenSamples("step_duration_valid", {
            pyCompare(samples.last().get("stepDt"), pyInt(0), ">") > 0 &&
                samples.filter { pyCompare(it.get("steps"), pyInt(0), ">") > 0 }
                    .all { pyCompare(it.get("stepDt"), pyInt(0), ">") > 0 }
        })
        whenSamples("expected_bodies", {
            val expected = SCENES.getValue(scene)
            samples.all { pyEquals(it.get("bodyCount"), pyInt(expected)) }
        })

        when (scene) {
            "Tracking" -> {
                whenSamples("contact_begin", { pyCompare(samples.last().get("begin"), pyInt(0), ">") > 0 })
                whenSamples("contact_persist", { pyCompare(samples.last().get("persist"), pyInt(0), ">") > 0 })
                whenSamples("contact_end", { pyCompare(samples.last().get("end"), pyInt(0), ">") > 0 })
                check("sample_contact_listener", "BEGIN:" in logText && "END:" in logText)
                check("contact_toggle_input", "key c" in inputText)
            }
            "Pyramid" -> {
                whenSamples("picking_joint", {
                    samples.any { pyEquals(it.get("jointCount"), pyInt(1)) }
                })
                whenSamples("drag_moved_body", {
                    samples.any {
                        pyEquals(it.get("jointCount"), pyInt(1)) &&
                            !pyEquals(body(it, 60).get("x"), body(samples[0], 60).get("x"))
                    }
                })
                whenSamples("reset_observed", {
                    samples.any {
                        pyCompare(it.get("resets"), pyInt(0), ">") > 0 &&
                            pyEquals(it.get("jointCount"), pyInt(0))
                    }
                })
                check("drag_and_reset_inputs", "drag left mouse" in inputText && "key r" in inputText)
            }
            "Crank" -> {
                whenSamples("four_joints", {
                    samples.all { pyEquals(it.get("jointCount"), pyInt(4)) }
                })
                whenSamples("joint_types", {
                    val types = pyIterate(samples[0].get("joints")).map { pyHashKey(it.get("type")) }
                    types.toSet() == setOf(pyHashKey(pyText("RevoluteJoint")), pyHashKey(pyText("PrismaticJoint")))
                })
                whenSamples("piston_motion", {
                    pyIterate(PyValue.Seq(samples)).map { pyHashKey(body(it, 3).get("y")) }.toSet().size > 1
                })
            }
            "Billiards" -> {
                val shotIndex = (1 until samples.size).firstOrNull { index ->
                    samples.subList(0, index).any { body(it, 5).get("rest").truthy() } &&
                        !body(samples[index], 5).get("rest").truthy() &&
                        !pyEquals(body(samples[index], 5).get("vx"), pyInt(0))
                }
                whenSamples("shot_moved_cue", { shotIndex != null })
                whenSamples("rack_collision", {
                    shotIndex != null && samples.drop(shotIndex + 1).any { item ->
                        pyCompare(item.get("begin"), samples[shotIndex].get("begin"), ">") > 0 &&
                            (6 until 21).any {
                                !pyEquals(body(item, it).get("x"), body(samples[0], it).get("x"))
                            }
                    }
                })
                whenSamples("balls_settled", {
                    shotIndex != null && samples.drop(shotIndex + 1).any { item ->
                        pyCompare(item.get("toiHits"), samples[shotIndex].get("toiHits"), ">") > 0 &&
                            (5 until 21).all { body(item, it).get("rest").truthy() }
                    }
                })
                whenSamples("ccd_detector_calls", {
                    pyCompare(samples.last().get("toiCalls"), pyInt(0), ">") > 0
                })
                whenSamples("ccd_detector_hits", {
                    shotIndex != null &&
                        pyCompare(samples.last().get("toiHits"), samples[shotIndex].get("toiHits"), ">") > 0
                })
                whenSamples("ccd_listener_hits", {
                    shotIndex != null &&
                        pyCompare(
                            samples.last().get("toiListenerHits"),
                            samples[shotIndex].get("toiListenerHits"),
                            ">",
                        ) > 0
                })
                whenSamples("ccd_enabled", {
                    samples.all { !pyEquals(it.get("ccdMode"), pyText("NONE")) }
                })
                check("cue_input", listOf("keydown plus", "keydown s", "keyup s").all { it in inputText })
            }
            "Truck" -> {
                val verdict = timeline?.invoke() ?: (false to "timeline directory missing")
                check("truck_timeline", verdict.first, verdict.second)
                whenSamples("no_camera_pick_joint", {
                    samples.all { pyEquals(it.getOrNull("maxJointCount") ?: PyValue.Null, pyInt(2)) }
                })
                val bounds = truckMotorBounds(samples)
                check(
                    "truck_motor_phase_bounds",
                    bounds != null && listOf("drive_transition", "brake_transition").all { key ->
                        val window = bounds.get(key)
                        val span = pySubtract(window.at(1).get("nanos"), window.at(0).get("nanos"))
                        pyCompare(span, pyInt(0), ">") > 0 &&
                            pyCompare(span, pyInt(300_000_000), "<=") <= 0
                    },
                )
                fun brakeWindowSlowed(): Boolean {
                    if (bounds == null) return false
                    val brakeIndex = integerValue(bounds.get("brake_index"))
                    val start = samples[brakeIndex]
                    val later = samples.drop(brakeIndex + 1).firstOrNull {
                        val gap = pySubtract(it.get("nanos"), start.get("nanos"))
                        pyCompare(gap, pyInt(900_000_000), ">=") >= 0 &&
                            pyCompare(gap, pyInt(1_200_000_000), "<=") <= 0
                    }
                    return later != null &&
                        pyCompare(
                            pyAbsolute(body(later, 2).get("vx")),
                            pyAbsolute(body(start, 2).get("vx")),
                            "<",
                        ) < 0
                }
                whenSamples("brake_window_speed_reduced", ::brakeWindowSlowed)
                whenSamples("wheel_joints", {
                    samples.all { sample ->
                        pyEquals(sample.get("jointCount"), pyInt(2)) &&
                            pyIterate(sample.get("joints")).all {
                                pyEquals(it.get("type"), pyText("WheelJoint"))
                            }
                    }
                })
                whenSamples("drive_motor", {
                    samples.any { sample ->
                        pyIterate(sample.get("joints")).any {
                            !pyEquals(it.get("motorSpeed"), pyInt(0))
                        }
                    }
                })
                whenSamples("brake_motor", {
                    samples.any { sample ->
                        pyIterate(sample.get("joints")).any {
                            !pyEquals(it.get("motorSpeed"), pyInt(0))
                        }
                    } && pyIterate(samples.last().get("joints")).all {
                        pyEquals(it.get("motorSpeed"), pyInt(0))
                    }
                })
                whenSamples("chassis_moved", {
                    !pyEquals(body(samples.last(), 2).get("x"), body(samples[0], 2).get("x"))
                })
                whenSamples("ramp_crossed", {
                    val xs = samples.map { body(it, 2).get("x") }
                    pyCompare(xs.minWith(Comparator(::pyCompareValues)), pyInt(0), "<") < 0 &&
                        pyCompare(xs.maxWith(Comparator(::pyCompareValues)), pyInt(0), ">") > 0
                })
                whenSamples("brake_reduced_speed", {
                    val last = pyAbsolute(body(samples.last(), 2).get("vx"))
                    val largest = samples.maxOf { pyNumberValue(pyAbsolute(body(it, 2).get("vx"))) }
                    pyNumberValue(last) < largest
                })
                whenSamples("suspension_moved", {
                    samples.drop(1).any { item ->
                        pyCompare(body(item, 2).get("x"), pyInt(0), ">") > 0 &&
                            pyIterate(item.get("joints")).any { joint ->
                                val index = integerValue(joint.get("i"))
                                !pyEquals(
                                    joint.get("translation"),
                                    samples[0].get("joints").at(index).get("translation"),
                                )
                            }
                    }
                })
                whenSamples("cargo_moved", {
                    !pyEquals(body(samples.last(), 10).get("x"), body(samples[0], 10).get("x")) &&
                        samples.drop(1).any { item ->
                            pyCompare(body(item, 2).get("x"), pyInt(0), ">") > 0 &&
                                !pyEquals(body(item, 10).get("y"), body(samples[0], 10).get("y"))
                        }
                })
                whenSamples("ccd_disabled", {
                    samples.all {
                        pyEquals(it.get("ccdMode"), pyText("NONE")) &&
                            pyEquals(it.get("toiHits"), pyInt(0))
                    }
                })
                check("drive_and_brake_inputs", "keydown Right" in inputText && "key s" in inputText)
            }
        }
        return checks
    }

    /** `validate_scene.main`'s result object. */
    fun result(
        scene: String,
        logText: String,
        inputText: String,
        samples: List<PyValue>,
        parseErrors: List<String>,
        timeline: (() -> Pair<Boolean, String>)? = null,
    ): PyValue {
        val checks = checksFor(scene, logText, inputText, samples, parseErrors, timeline)
        val result = linkedMapOf<String, PyValue>(
            "scene" to pyText(scene),
            "expected_checks" to pyInt(checks.size),
            "executed_checks" to pyInt(checks.count { !pyEquals(it.get("status"), pyText("skipped")) }),
            "passed_checks" to pyInt(checks.count { pyEquals(it.get("status"), pyText("passed")) }),
            "failed_checks" to pyInt(checks.count { pyEquals(it.get("status"), pyText("failed")) }),
            "unexecuted_checks" to pyInt(checks.count { pyEquals(it.get("status"), pyText("skipped")) }),
            "samples" to pyInt(samples.size),
            "checks" to pyList(checks),
            "parse_errors" to pyList(parseErrors.map(::pyText)),
            "visual_review_status" to pyText("UNREVIEWED"),
        )
        if (scene == "Truck") {
            result["truck_motor_bounds"] = truckMotorBounds(samples) ?: PyValue.Null
        }
        return PyValue.Map(result)
    }

    private val DIAGNOSTIC = Regex("Shouldn't happen|Exception|Error")
}

private fun isInstanceInt(value: PyValue): Boolean = value is PyValue.Int || value is PyValue.Bool

private fun finiteValue(value: PyValue): Boolean = when (value) {
    is PyValue.Int -> true
    is PyValue.Bool -> true
    is PyValue.Real -> value.value.isFinite()
    else -> throw PyTypeError("must be real number, not ${value.typeName}")
}

private fun integerValue(value: PyValue): Int = when (value) {
    is PyValue.Int -> value.value.toInt()
    is PyValue.Bool -> if (value.value) 1 else 0
    else -> throw PyTypeError("'${value.typeName}' object cannot be interpreted as an integer")
}

internal fun pySubtract(left: PyValue, right: PyValue): PyValue = when {
    left is PyValue.Int && right is PyValue.Int -> pyInt(left.value - right.value)
    else -> pyReal(pyNumberValue(left) - pyNumberValue(right))
}

internal fun pyAbsolute(value: PyValue): PyValue = when (value) {
    is PyValue.Int -> if (value.value < 0) pyInt(-value.value) else value
    is PyValue.Real -> pyReal(kotlin.math.abs(value.value))
    is PyValue.Bool -> pyInt(if (value.value) 1 else 0)
    else -> throw PyTypeError("bad operand type for abs(): '${value.typeName}'")
}

internal fun pyNumberValue(value: PyValue): Double = when (value) {
    is PyValue.Int -> value.value.toDouble()
    is PyValue.Real -> value.value
    is PyValue.Bool -> if (value.value) 1.0 else 0.0
    else -> throw PyTypeError("must be real number, not ${value.typeName}")
}

internal fun pyCompareValues(left: PyValue, right: PyValue): Int = pyCompare(left, right, "<")
