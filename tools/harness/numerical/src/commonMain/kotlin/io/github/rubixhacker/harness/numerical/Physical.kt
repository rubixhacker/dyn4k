package io.github.rubixhacker.harness.numerical

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlin.math.abs

/**
 * `physical`: the diagnostic analytical and represented-geometry checks over a portable trace.
 *
 * `sleep_wake_rows` reads the approved phase schedule and ceilings from the fixture catalog, so
 * the catalog entries are a parameter rather than a module-level file read.
 */
object Physical {
    /** `tools/numerical/compare.load_fixture`: the profile merged with the fixture entry. */
    fun loadFixture(catalog: JsonObject, key: String): JsonObject {
        val item = (catalog["fixtures"] as JsonArray)
            .map { it as JsonObject }
            .firstOrNull { it["key"]?.stringOrNull() == key }
            ?: throw NoSuchElementException("no fixture: $key")
        val profile = (catalog["profiles"] as JsonObject)[item.getValue("profile").stringOrNull()]
            as JsonObject
        val merged = LinkedHashMap<String, JsonElement>(profile)
        merged.putAll(item)
        merged["baseline_source_revision"] = catalog["baseline_source_revision"] ?: JsonPrimitive("")
        merged["baseline_jar_sha256"] = catalog["baseline_jar_sha256"] ?: JsonPrimitive("")
        return JsonObject(merged)
    }

    /** `tools/numerical/physical.depth_for_state`. */
    internal fun depthForState(state: JsonObject): Fraction {
        val bodies = state["bodies"] as? JsonArray
            ?: throw Rejected("floor or square identity differs")
        val ids = bodies.map { (it as JsonObject)["id"]?.stringOrNull() }
        if (bodies.size != 2 || ids != listOf("b0", "b1")) {
            throw Rejected("floor or square identity differs")
        }
        val floor = (bodies[0] as JsonObject)["transform"] as JsonObject
        val square = (bodies[1] as JsonObject)["transform"] as JsonObject
        if (floor["getCost"]?.numberOrNull() != 1.0 ||
            floor["getSint"]?.numberOrNull() != 0.0 ||
            !sameNumbers(floor["getTranslation"], listOf(0.0, -0.25))
        ) {
            throw Rejected("fixed floor pose differs")
        }
        val translation = square["getTranslation"] as JsonArray
        val x = translation[0].numberOrNull()!!
        val y = translation[1].numberOrNull()!!
        val cosine = square["getCost"].numberOrNull()!!
        val sine = square["getSint"].numberOrNull()!!
        val extent = (Fraction.ofDouble(abs(cosine)).abs() + Fraction.ofDouble(abs(sine)).abs())
            .div(Fraction.of(2))
        if ((Fraction.ofDouble(abs(x)) + extent) > Fraction.of(10)) {
            throw Rejected("square leaves finite floor span")
        }
        val depth = extent - Fraction.ofDouble(y)
        return if (depth >= Fraction.of(0)) depth else Fraction.of(0)
    }

    private fun sameNumbers(value: JsonElement?, expected: List<Double>): Boolean {
        val array = value as? JsonArray ?: return false
        if (array.size != expected.size) return false
        return expected.indices.all { array[it].numberOrNull() == expected[it] }
    }

    /** `tools/numerical/physical.phases_for_fixture`. */
    fun phasesForFixture(fixture: JsonObject): List<Triple<String, Int, Int>> {
        val phases = when {
            fixture.containsKey("physical_phases_steps") ->
                fixture.getValue("physical_phases_steps") as JsonArray
            fixture.containsKey("physical_phases_inner_steps") ->
                fixture.getValue("physical_phases_inner_steps") as JsonArray
            fixture.containsKey("physical_phases_by_hz") -> {
                val hz = fixture.getValue("id").stringOrNull().orEmpty().substringAfterLast("hz")
                (fixture.getValue("physical_phases_by_hz") as JsonObject)
                    .getValue(hz) as JsonArray
            }
            else -> throw Rejected("no approved physical phase schedule")
        }
        val schedule = phases.map {
            val entry = it as JsonArray
            Triple(
                entry[0].stringOrNull().orEmpty(),
                entry[1].intOrNull()!!,
                entry[2].intOrNull()!!,
            )
        }
        val ceilings = fixture["physical_phase_ceilings_m"] as? JsonObject
        var current = 1
        for ((name, first, last) in schedule) {
            if (first != current || last < first || ceilings?.containsKey(name) != true) {
                throw Rejected("physical phase schedule has a gap")
            }
            current = last + 1
        }
        if (current - 1 != (fixture["counts"] as JsonObject)["state"]?.intOrNull()) {
            throw Rejected("physical phase schedule does not cover every state")
        }
        return schedule
    }

    private val MAXIMA_KEYS = listOf(
        "positionX_m", "positionY_m", "rotation_rad", "energy",
        "momentumX", "momentumY", "angularMomentumCenter",
    )

    /** `physical.nominal_free` over the trace lines. */
    fun nominalFree(lines: List<String>, expectedSteps: Int = 36000): JsonObject {
        var checked = 0
        val maxima = LinkedHashMap<String, Double>()
        MAXIMA_KEYS.forEach { maxima[it] = 0.0 }
        var initial: Triple<Double, JsonArray, Double>? = null
        val failures = ArrayList<JsonObject>()
        var failureCount = 0
        try {
            for (row in records(lines, allowTaggedNonfinite = true)) {
                if (row["kind"]?.stringOrNull() != "state" ||
                    row["id"]?.stringOrNull() != "long-free-60"
                ) {
                    continue
                }
                checked += 1
                val step = row.getValue("step").intOrNull()!!
                val bodies = ((row["state"] as JsonObject)["bodies"] as JsonArray)
                if (bodies.size != 1) throw Rejected("too many values to unpack")
                val body = bodies[0] as JsonObject
                val momentum = body["linearMomentum"] as JsonArray
                if (initial == null) {
                    initial = Triple(
                        body.getValue("kineticEnergy").numberOrNull()!!,
                        momentum,
                        body.getValue("angularMomentumCenter").numberOrNull()!!,
                    )
                }
                val start = initial!!
                val expectedTime = step / 60.0
                val center = body["worldCenter"] as JsonArray
                val dx = abs(center[0].numberOrNull()!! - 0.25 * expectedTime)
                val dy = abs(center[1].numberOrNull()!! + 0.125 * expectedTime)
                val dr = abs(
                    body.getValue("rotationIncrementSum").numberOrNull()!! - 0.5 * expectedTime,
                )
                val energy = abs(body.getValue("kineticEnergy").numberOrNull()!! - start.first)
                val momentumX = abs(momentum[0].numberOrNull()!! - start.second[0].numberOrNull()!!)
                val momentumY = abs(momentum[1].numberOrNull()!! - start.second[1].numberOrNull()!!)
                val angular = abs(
                    body.getValue("angularMomentumCenter").numberOrNull()!! - start.third,
                )
                maxima["positionX_m"] = maxOf(maxima.getValue("positionX_m"), dx)
                maxima["positionY_m"] = maxOf(maxima.getValue("positionY_m"), dy)
                maxima["rotation_rad"] = maxOf(maxima.getValue("rotation_rad"), dr)
                maxima["energy"] = maxOf(maxima.getValue("energy"), energy)
                maxima["momentumX"] = maxOf(maxima.getValue("momentumX"), momentumX)
                maxima["momentumY"] = maxOf(maxima.getValue("momentumY"), momentumY)
                maxima["angularMomentumCenter"] =
                    maxOf(maxima.getValue("angularMomentumCenter"), angular)
                if (dx > 1e-10 || dy > 1e-10 || dr > 6e-8 ||
                    !sameNumbers(body["velocity"], listOf(0.25, -0.125)) ||
                    body["angularVelocity"]?.numberOrNull() != 0.5 ||
                    maxima.values.any { !it.isFinite() }
                ) {
                    failureCount += 1
                    if (failures.size < 20) {
                        failures.add(
                            buildJsonObject {
                                put("step", step)
                                put("positionX_m", dx)
                                put("positionY_m", dy)
                                put("rotation_rad", dr)
                            },
                        )
                    }
                }
            }
        } catch (error: Rejected) {
            failures.add(reason(error))
        } catch (error: NoSuchElementException) {
            failures.add(reason(error))
        } catch (error: ClassCastException) {
            failures.add(reason(error))
        } catch (error: IllegalArgumentException) {
            failures.add(reason(error))
        } catch (error: NullPointerException) {
            failures.add(reason(error))
        }
        if (checked != expectedSteps) {
            failures.add(
                buildJsonObject {
                    put("reason", "expected $expectedSteps long-free states; executed $checked")
                },
            )
        }
        return buildJsonObject {
            put("status", if (failures.isEmpty()) "PASSED" else "FAILED")
            put("checked", checked)
            put("failed_samples", failureCount)
            put(
                "maxima",
                buildJsonObject { maxima.forEach { (name, value) -> put(name, value) } },
            )
            put(
                "first_failures",
                buildJsonArray { failures.take(20).forEach { add(it) } },
            )
            put(
                "scope",
                "diagnostic analytical free-motion checks; frozen input parity is separate",
            )
        }
    }

    /** Python's `str()` of a JSON scalar, as the phase ceilings are recorded. */
    private fun pythonText(value: JsonElement): String =
        value.stringOrNull() ?: if (value.isIntegerLiteral()) {
            value.intOrNull()?.toString() ?: value.numberOrNull().toString()
        } else {
            io.github.rubixhacker.harness.contract.CanonicalJson.pythonFloat(
                value.numberOrNull()!!,
            )
        }

    private fun reason(error: Exception): JsonObject = buildJsonObject {
        put("reason", error.message.orEmpty())
    }

    fun defaultKeys(): List<String> =
        listOf(30, 60, 120).map { "default-sleep-$it" } +
            listOf(30, 60, 120).flatMap { hz -> listOf(1, 2).map { "configured-$hz-r$it" } }

    /** `physical.sleep_wake_rows` over already-parsed records and merged fixtures. */
    fun sleepWakeRows(
        rows: List<JsonObject>,
        keys: List<String>? = null,
        fixtures: Map<String, JsonObject>,
    ): JsonObject {
        val usedKeys = keys ?: defaultKeys()
        val reports = LinkedHashMap<String, LinkedHashMap<String, JsonElement>>()
        val maxima = LinkedHashMap<String, Fraction>()
        val positions = LinkedHashMap<String, Int>()
        val schedules = LinkedHashMap<String, List<Triple<String, Int, Int>>>()
        try {
            for (key in usedKeys) {
                val fixture = fixtures[key] ?: throw NoSuchElementException("no fixture: $key")
                schedules[key] = phasesForFixture(fixture)
                reports[key] = linkedMapOf(
                    "status" to JsonPrimitive("NOT_RUN"),
                    "states" to JsonPrimitive(0),
                    "failed" to JsonPrimitive(0),
                    "first_failure" to kotlinx.serialization.json.JsonNull,
                    "maximum_depth_m" to JsonPrimitive("0"),
                )
                positions[key] = 0
                maxima[key] = Fraction.of(0)
            }
            for (row in rows) {
                if (row["kind"]?.stringOrNull() != "state") continue
                val caseId = row["id"]?.stringOrNull().orEmpty()
                val key = when {
                    caseId.startsWith("contacts-default-") ->
                        "default-sleep-" + caseId.substringAfterLast("-")
                    caseId.startsWith("contacts-configured-") ->
                        caseId.removePrefix("contacts-")
                    else -> null
                } ?: continue
                val report = reports[key] ?: continue
                val step = row.getValue("step").intOrNull()!!
                if (step != (report.getValue("states").intOrNull() ?: 0) + 1) {
                    throw Rejected("$key: missing physical state")
                }
                val schedule = schedules.getValue(key)
                var position = positions.getValue(key)
                while (step > schedule[position].third) position += 1
                positions[key] = position
                val phase = schedule[position].first
                val depth = depthForState(row.getValue("state") as JsonObject)
                val ceiling = Fraction.ofDecimalString(
                    pythonText(
                        (fixtures.getValue(key).getValue("physical_phase_ceilings_m") as JsonObject)
                            .getValue(phase),
                    ),
                )
                report["states"] = JsonPrimitive((report.getValue("states").intOrNull() ?: 0) + 1)
                if (depth > maxima.getValue(key)) maxima[key] = depth
                if (depth > ceiling) {
                    report["failed"] = JsonPrimitive((report.getValue("failed").intOrNull() ?: 0) + 1)
                    if (report.getValue("first_failure") is kotlinx.serialization.json.JsonNull) {
                        report["first_failure"] = buildJsonObject {
                            put("step", step)
                            put("phase", phase)
                            put("depth_m", depth.toString())
                            put("ceiling_m", ceiling.toString())
                        }
                    }
                }
            }
            for ((key, report) in reports) {
                report["maximum_depth_m"] = JsonPrimitive(maxima.getValue(key).toString())
                if (report.getValue("states").intOrNull() !=
                    (fixtures.getValue(key).getValue("counts") as JsonObject)
                        ["state"]?.intOrNull()
                ) {
                    report["status"] = JsonPrimitive("INVALID")
                    report["reason"] = JsonPrimitive("physical state count differs")
                } else {
                    report["status"] = JsonPrimitive(
                        if ((report.getValue("failed").intOrNull() ?: 0) != 0) {
                            "PHYSICAL_FAILED"
                        } else {
                            "PHYSICAL_PASSED"
                        },
                    )
                }
            }
        } catch (error: Rejected) {
            return invalid(error, reports, maxima)
        } catch (error: NoSuchElementException) {
            return invalid(error, reports, maxima)
        } catch (error: IndexOutOfBoundsException) {
            return invalid(error, reports, maxima)
        } catch (error: IllegalArgumentException) {
            return invalid(error, reports, maxima)
        } catch (error: NullPointerException) {
            return invalid(error, reports, maxima)
        } catch (error: ClassCastException) {
            return invalid(error, reports, maxima)
        } catch (error: ArithmeticException) {
            return invalid(error, reports, maxima)
        }
        val overall = when {
            reports.values.any { it.getValue("status").stringOrNull() == "INVALID" } -> "INVALID"
            reports.values.any { it.getValue("status").stringOrNull() == "PHYSICAL_FAILED" } ->
                "PHYSICAL_FAILED"
            else -> "PHYSICAL_PASSED"
        }
        return buildJsonObject {
            put("status", overall)
            put("scope", "APPROVED_REPRESENTED_GEOMETRY_DIAGNOSTIC")
            put(
                "cases",
                buildJsonObject { reports.forEach { (key, value) -> put(key, JsonObject(value)) } },
            )
            put("qualification", "UNPASSED")
        }
    }

    private fun invalid(
        error: Exception,
        reports: Map<String, LinkedHashMap<String, JsonElement>>,
        maxima: Map<String, Fraction>,
    ): JsonObject {
        for ((key, report) in reports) {
            report["maximum_depth_m"] = JsonPrimitive(maxima.getValue(key).toString())
        }
        return buildJsonObject {
            put("status", "INVALID")
            put("reason", error.message.orEmpty())
            put(
                "cases",
                buildJsonObject { reports.forEach { (key, value) -> put(key, JsonObject(value)) } },
            )
            put("qualification", "UNPASSED")
        }
    }
}
