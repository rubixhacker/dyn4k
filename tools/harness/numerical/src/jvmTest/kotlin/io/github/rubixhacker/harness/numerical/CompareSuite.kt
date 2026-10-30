package io.github.rubixhacker.harness.numerical

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

private fun JsonObject.at(path: List<String>, value: JsonElement): JsonObject {
    if (path.isEmpty()) return value as JsonObject
    val head = path.first()
    val child = getValue(head)
    return with(
        head,
        if (path.size == 1) value else (child as JsonObject).at(path.drop(1), value),
    )
}

private fun List<JsonObject>.replace(index: Int, value: JsonObject): List<JsonObject> =
    mapIndexed { position, row -> if (position == index) value else row }

private fun scenario(block: ComparatorScenario.() -> Unit) {
    val harness = ComparatorScenario()
    try {
        harness.block()
    } finally {
        harness.close()
    }
}

internal fun repositoryRoot(): java.nio.file.Path {
    var candidate: java.nio.file.Path? = java.nio.file.Path.of("").toAbsolutePath()
    while (candidate != null) {
        if (java.nio.file.Files.isRegularFile(candidate.resolve(FIXTURE_CATALOG))) return candidate
        candidate = candidate.parent
    }
    error("cannot find the repository root above ${java.nio.file.Path.of("").toAbsolutePath()}")
}

private val FIXTURE_CATALOG = "tools/numerical/fixtures.json"

private fun loadFixture(key: String): LinkedHashMap<String, JsonElement> {
    val catalog = kotlinx.serialization.json.Json.parseToJsonElement(
        java.nio.file.Files.readString(repositoryRoot().resolve(FIXTURE_CATALOG)),
    ) as JsonObject
    return LinkedHashMap(Compare.loadFixture(catalog, key))
}

private fun configured(): LinkedHashMap<String, JsonElement> = loadFixture("configured-30-r1")

/** `test_compare.py`, the comparison engine's own suite. */
val CompareContract by testSuite {
    test("approved components and wrap pass at the inclusive limit") {
        lateinit var outcome: JsonObject
        scenario {
            rows = rows.replace(
                1,
                rows[1].at(
                    listOf("payload"),
                    JsonArray(
                        listOf(
                            (rows[1].array("payload")[0] as JsonObject)
                                .with("velocity", numbers(1.05, -2.05)),
                        ),
                    ),
                ),
            )
            rows = rows.replace(
                2,
                rows[2].at(
                    listOf("state"),
                    rows[2].obj("state")
                        .with("position", numbers(2.11, 3.12))
                        .with(
                            "normal",
                            numbers(0.9999875000260416, 0.004999979166692708),
                        )
                        .with("angle", JsonPrimitive(-3.141592653589793)),
                ),
            )
            writeCandidate(rows)
            outcome = result()
        }
        assertEquals("PASSED", outcome["status"]?.stringOrNull())
    }

    test("scalar, vector and unwrapped limits fail") {
        data class Mutation(val path: String, val value: JsonElement)
        val mutations = listOf(
            Mutation("position", numbers(2.0, 3.14)),
            Mutation("sum", JsonPrimitive(9.02)),
            Mutation("normal", numbers(-1.0, 0.0)),
            Mutation("normal", numbers(1.002, 0.0)),
            Mutation("normal", numbers(0.9998, 0.02)),
        )
        for (mutation in mutations) {
            var status: String? = null
            scenario {
                rows = rows.replace(
                    2,
                    rows[2].at(
                        listOf("state"),
                        rows[2].obj("state").with(mutation.path, mutation.value),
                    ),
                )
                writeCandidate(rows)
                status = result()["status"]?.stringOrNull()
            }
            assertEquals("FAILED", status, mutation.path)
        }
    }

    test("an equal non-unit normal still fails") {
        var status: String? = null
        scenario {
            rows = rows.replace(
                2,
                rows[2].at(
                    listOf("state"),
                    rows[2].obj("state").with("normal", numbers(1.002, 0.0)),
                ),
            )
            writeReference(rows)
            writeCandidate(rows)
            status = result()["status"]?.stringOrNull()
        }
        assertEquals("FAILED", status)
    }

    test("direct callback channels use their approved units") {
        for ((name, value) in listOf(
            "getPoint" to numbers(0.02, 0.0),
            "getDepth" to JsonPrimitive(0.12),
            "getNormalImpulse" to JsonPrimitive(0.27),
        )) {
            var status: String? = null
            scenario {
                val payload = (rows[1].array("payload")[0] as JsonObject).with(name, value)
                rows = rows.replace(
                    1,
                    rows[1].with("payload", JsonArray(listOf(payload))),
                )
                writeCandidate(rows)
                status = result()["status"]?.stringOrNull()
            }
            assertEquals("FAILED", status, name)
        }
    }

    test("a missing, nonfinite, unknown or misordered record fails closed") {
        val mutations = listOf<(List<JsonObject>) -> List<JsonObject>>(
            { current ->
                current.replace(2, current[2].at(listOf("state"), current[2].obj("state").without("sum")))
            },
            { current ->
                current.replace(
                    2,
                    current[2].at(
                        listOf("state"),
                        current[2].obj("state").with("sum", JsonPrimitive(Double.NaN)),
                    ),
                )
            },
            { current ->
                current.replace(
                    2,
                    current[2].at(
                        listOf("state"),
                        current[2].obj("state").with("unknown", JsonPrimitive(1.0)),
                    ),
                )
            },
            { current -> current.replace(1, current[1].with("method", JsonPrimitive("end"))) },
            { current -> current.filterIndexed { index, _ -> index != 1 } },
        )
        for (mutation in mutations) {
            var status: String? = null
            scenario {
                rows = mutation(rows)
                writeCandidate(rows)
                status = result()["status"]?.stringOrNull()
            }
            assertNotEquals("PASSED", status)
        }
    }

    test("swapped callbacks fail even when the counts match") {
        scenario {
            val second = rows[1].with("order", JsonPrimitive(1)).with("method", JsonPrimitive("end"))
            rows = rows.toMutableList().apply { add(2, second) }
            fixture["counts"] = parseRow("""{"inputs":1,"event":2,"state":1}""")
            writeReference(rows)
            var candidate = rows.toMutableList().apply { set(1, rows[2]); set(2, rows[1]) }
            writeCandidate(candidate)
            assertEquals("FAILED", result()["status"]?.stringOrNull())
            candidate = candidate.toMutableList().apply {
                set(1, get(1).with("order", JsonPrimitive(0)))
                set(2, get(2).with("order", JsonPrimitive(1)))
            }
            writeCandidate(candidate)
            assertEquals("FAILED", result()["status"]?.stringOrNull())
        }
    }

    test("identity, count and skip differences fail closed") {
        scenario {
            writeCandidate(rows, counts = parseRow("""{"inputs":1,"event":1,"state":2}"""))
            assertEquals("FAILED", result()["status"]?.stringOrNull())
            writeCandidate(rows)
            for ((key, value) in listOf<Pair<String, JsonElement>>(
                "source_sha256" to JsonPrimitive("e".repeat(64)),
                "artifact_sha256" to JsonPrimitive("e".repeat(64)),
                "candidate_commit" to JsonPrimitive("0".repeat(40)),
                "reference_source_revision" to JsonPrimitive("0".repeat(40)),
                "reference_artifact_sha256" to JsonPrimitive("0".repeat(64)),
                "reference_trace_sha256" to JsonPrimitive("0".repeat(64)),
                "skipped" to JsonPrimitive(1),
            )) {
                writeReceipt(mapOf(key to value))
                assertEquals("FAILED", result()["status"]?.stringOrNull(), "$key -> ${result()}")
                writeCandidate(rows)
            }
        }
    }

    test("identical reference bytes still need a candidate receipt") {
        scenario {
            writeCandidate(rows)
            assertEquals("PASSED", result()["status"]?.stringOrNull())
            java.nio.file.Files.delete(receiptPath())
            val outcome = result()
            assertEquals("FAILED", outcome["status"]?.stringOrNull())
            assertTrue(outcome["reason"]?.stringOrNull().orEmpty().contains("No such file"))
        }
    }

    test("a reference hash or empty suite difference fails closed") {
        scenario {
            assertEquals("PASSED", auditReference()["status"]?.stringOrNull(), auditReference().toString())
            val bad = root.resolve("bad.jsonl.gz")
            java.nio.file.Files.write(
                bad,
                java.nio.file.Files.readAllBytes(referencePath()) + byteArrayOf('x'.code.toByte()),
            )
            assertEquals(
                "FAILED",
                CompareHost.auditReference(JsonObject(fixture), bad)["status"]?.stringOrNull(),
            )
            writeReference(listOf(rows[0]))
            assertEquals("FAILED", auditReference()["status"]?.stringOrNull())
            fixture["counts"] = parseRow("""{"inputs":1}""")
            writeCandidate(listOf(rows[0]))
            assertEquals("FAILED", result()["status"]?.stringOrNull())
        }
    }

    test("an outer endpoint must copy the matching inner state") {
        scenario {
            rows = rows + parseRow(
                """{"kind":"outer-endpoint","step":1,"outerStep":1,""" +
                    """"state":{"position":[2.0,3.0],"normal":[1.0,0.0],""" +
                    """"angle":3.141592653589793,"sum":9.0}}""",
            )
            fixture["counts"] = parseRow("""{"inputs":1,"event":1,"state":1,"outer-endpoint":1}""")
            fixture["inner_per_outer"] = JsonPrimitive(1)
            writeReference(rows)
            assertEquals("PASSED", auditReference()["status"]?.stringOrNull())
            rows = rows.replace(
                3,
                rows[3].at(listOf("state", "position"), numbers(999.0, 3.0)),
            )
            writeReference(rows)
            assertEquals("FAILED", auditReference()["status"]?.stringOrNull())
        }
    }

    test("endpoint copies reject boolean aliases, wrong indices and a missing group") {
        scenario {
            fixture["counts"] = parseRow("""{"inputs":1,"state":1,"outer-endpoint":1}""")
            fixture["inner_per_outer"] = JsonPrimitive(1)
            var endpointRows = listOf(
                parseRow("""{"kind":"inputs","id":"sample","dt":0.5}"""),
                parseRow("""{"kind":"state","step":1,"state":{"x":0.0}}"""),
                parseRow("""{"kind":"outer-endpoint","step":1,"outerStep":1,"state":{"x":-0.0}}"""),
            )
            fun audit(changed: List<JsonObject>): Map<String, Int> =
                Compare.checkCounts(
                    CompareHost.recordsOfBytes(encoded(changed)),
                    JsonObject(fixture),
                    reference = false,
                ).also { assertEquals(1, it["outer-endpoint"]) }

            audit(endpointRows)
            for ((field, value) in listOf(
                "state" to parseRow("""{"x":false}"""),
                "state" to parseRow("""{"x":0.001}"""),
                "step" to JsonPrimitive(2),
                "step" to JsonPrimitive(true),
                "outerStep" to JsonPrimitive(2),
                "outerStep" to JsonPrimitive(true),
            )) {
                val changed = endpointRows.toMutableList()
                changed[2] = changed[2].with(field, value)
                val failure = assertFailsWith<Rejected> { audit(changed) }
                assertTrue(
                    failure.message.orEmpty().contains("outer endpoint does not copy"),
                    "$field=$value",
                )
            }
            for (field in listOf("step", "outerStep")) {
                val changed = endpointRows.toMutableList()
                changed[2] = changed[2].without(field)
                val failure = assertFailsWith<Rejected> { audit(changed) }
                assertTrue(failure.message.orEmpty().contains("outer endpoint does not copy"))
                endpointRows = endpointRows.replace(2, endpointRows[2].with(field, JsonPrimitive(1)))
            }
            for (value in listOf(JsonPrimitive(2), JsonPrimitive(true), JsonNull)) {
                val changed = if (value is JsonNull) {
                    endpointRows.replace(1, endpointRows[1].without("step"))
                } else {
                    endpointRows.replace(1, endpointRows[1].with("step", value))
                }
                val failure = assertFailsWith<Rejected> { audit(changed) }
                assertEquals("missing or reordered state", failure.message)
            }
            for (group in listOf(JsonNull, JsonPrimitive(0), JsonPrimitive(true), JsonPrimitive(-1))) {
                if (group is JsonNull) {
                    fixture.remove("inner_per_outer")
                } else {
                    fixture["inner_per_outer"] = group
                }
                val failure = assertFailsWith<Rejected> { audit(endpointRows) }
                assertTrue(failure.message.orEmpty().contains("outer endpoint does not copy"))
            }
        }
    }

    test("endpoint indices are relative to the start step") {
        scenario {
            fixture["counts"] = parseRow("""{"inputs":1,"state":2,"outer-endpoint":1}""")
            fixture["start_step"] = JsonPrimitive(10)
            fixture["inner_per_outer"] = JsonPrimitive(2)
            val endpointRows = listOf(
                parseRow("""{"kind":"inputs","id":"sample","dt":0.5}"""),
                parseRow("""{"kind":"state","step":11,"state":{"x":0.0}}"""),
                parseRow("""{"kind":"state","step":12,"state":{"x":0.0}}"""),
                parseRow("""{"kind":"outer-endpoint","step":12,"outerStep":1,"state":{"x":-0.0}}"""),
            )
            assertEquals(
                1,
                Compare.checkCounts(
                    CompareHost.recordsOfBytes(encoded(endpointRows)),
                    JsonObject(fixture),
                    reference = false,
                )["outer-endpoint"],
            )
            val swapped = endpointRows.toMutableList().apply { set(2, endpointRows[3]); set(3, endpointRows[2]) }
            val failure = assertFailsWith<Rejected> {
                Compare.checkCounts(
                    CompareHost.recordsOfBytes(encoded(swapped)),
                    JsonObject(fixture),
                    reference = false,
                )
            }
            assertTrue(failure.message.orEmpty().contains("outer endpoint does not copy"))
        }
    }

    test("a duplicate endpoint cannot claim the next outer step") {
        scenario {
            fixture["counts"] = parseRow("""{"inputs":1,"state":2,"outer-endpoint":2}""")
            fixture["inner_per_outer"] = JsonPrimitive(1)
            val first = parseRow("""{"kind":"state","step":1,"state":{"x":0.0}}""")
            val endpoint = parseRow("""{"kind":"outer-endpoint","step":1,"outerStep":1,"state":{"x":-0.0}}""")
            val duplicateRows = listOf(
                parseRow("""{"kind":"inputs","id":"sample","dt":0.5}"""),
                first,
                endpoint,
                endpoint,
                parseRow("""{"kind":"state","step":2,"state":{"x":0.0}}"""),
            )
            val failure = assertFailsWith<Rejected> {
                Compare.checkCounts(
                    CompareHost.recordsOfBytes(encoded(duplicateRows)),
                    JsonObject(fixture),
                    reference = false,
                )
            }
            assertTrue(failure.message.orEmpty().contains("outer endpoint does not copy"))
        }
    }

    test("exact represented geometry uses the phase ceiling") {
        scenario {
            fixture["physical_phase_ceilings_m"] = parseRow("""{"rest-before":0.001}""")
            fixture["physical_phases_steps"] = parseJson("""[["rest-before",1,1]]""")
            rows = listOf(
                parseRow("""{"kind":"inputs","id":"sample","dt":0.5}"""),
                parseRow(
                    """{"kind":"state","step":1,"state":{"bodies":[""" +
                        """{"id":"b0","transform":{"getCost":1.0,"getSint":0.0,""" +
                        """"getTranslation":[0.0,-0.25]}},""" +
                        """{"id":"b1","transform":{"getCost":1.0,"getSint":0.0,""" +
                        """"getTranslation":[0.0,0.5]}}]}}""",
                ),
            )
            fixture["counts"] = parseRow("""{"inputs":1,"state":1}""")
            writeReference(rows)
            assertEquals(
                "PHYSICAL_PASSED",
                PhysicalHost.auditPhysical(JsonObject(fixture), referencePath())["status"]?.stringOrNull(),
            )
            rows = rows.replace(
                1,
                rows[1].at(
                    listOf("state", "bodies"),
                    (rows[1].obj("state").array("bodies")).let { bodies ->
                        val second = (bodies[1] as JsonObject).at(
                            listOf("transform", "getTranslation"),
                            numbers(0.0, 0.49),
                        )
                        bodies.with(1, second)
                    },
                ),
            )
            writeReference(rows)
            assertEquals(
                "PHYSICAL_FAILED",
                PhysicalHost.auditPhysical(JsonObject(fixture), referencePath())["status"]?.stringOrNull(),
            )
        }
    }

    test("a translation alias must match within the same run") {
        scenario {
            fixture["family"] = JsonPrimitive("free-motion")
            fixture["check_translation_aliases"] = JsonPrimitive(true)
            val body = parseRow(
                """{"id":"b0","transform":{"getTranslation":[2.0,3.0],""" +
                    """"getTranslationX":2.0,"getTranslationY":3.0}}""",
            )
            rows = rows.replace(2, rows[2].at(listOf("state"), parseRow("""{"bodies":[]}""").with("bodies", JsonArray(listOf(body)))))
            writeReference(rows)
            assertEquals("PASSED", auditReference()["status"]?.stringOrNull())
            rows = rows.replace(
                2,
                rows[2].at(
                    listOf("state", "bodies"),
                    JsonArray(
                        listOf(
                            body.at(listOf("transform", "getTranslationX"), JsonPrimitive(2.01)),
                        ),
                    ),
                ),
            )
            writeReference(rows)
            assertEquals("FAILED", auditReference()["status"]?.stringOrNull())
        }
    }

    test("configured TOI fields use the selected limits") {
        scenario {
            val selected = configured()
            fixture["rules"] = JsonArray(
                (selected.getValue("rules") as JsonArray).filter {
                    (it as JsonObject)["path"]?.stringOrNull().orEmpty()
                        .startsWith("event.payload[].getTime") ||
                        (it as JsonObject)["path"]?.stringOrNull().orEmpty()
                            .startsWith("event.payload[].separation.")
                },
            )
            fixture["exact_numeric"] = parseJson(
                """["inputs.dt","event.step","event.order","state.step"]""",
            )
            val toi = parseRow(
                """{"getTime":0.5,"separation":{"getDistance":0.2,"getPoint1":[1.0,2.0],""" +
                    """"getPoint2":[3.0,4.0],"getNormal":[1.0,0.0]}}""",
            )
            rows = rows.replace(1, rows[1].with("payload", JsonArray(listOf(toi))))
            rows = rows.replace(2, rows[2].with("state", parseRow("""{"bodies":[]}""")))
            writeReference(rows)
            writeCandidate(rows)
            assertEquals("PASSED", result()["status"]?.stringOrNull())
            for ((field, value) in listOf(
                "getTime" to JsonPrimitive(0.500002),
                "getDistance" to JsonPrimitive(0.2002),
                "getPoint1" to numbers(1.0002, 2.0),
                "getPoint2" to numbers(3.0, 4.0002),
                "getNormal" to numbers(-1.0, 0.0),
                "getNormal" to numbers(1.000003, 0.0),
                "getNormal" to numbers(0.0, 0.0),
            )) {
                val altered = if (field == "getTime") {
                    rows.replace(
                        1,
                        rows[1].with("payload", JsonArray(listOf(toi.with(field, value)))),
                    )
                } else {
                    val separation = toi.obj("separation").with(
                        field,
                        value,
                    )
                    rows.replace(
                        1,
                        rows[1].with(
                            "payload",
                            JsonArray(listOf(toi.with("separation", separation))),
                        ),
                    )
                }
                writeCandidate(altered)
                assertEquals("FAILED", result()["status"]?.stringOrNull(), "$field=$value")
            }
        }
    }

    test("fixed floor callback velocities remain zero") {
        scenario {
            val selected = configured()
            fixture["callback_fixed_body_id"] = JsonPrimitive("b0")
            fixture["rules"] = JsonArray(
                (selected.getValue("rules") as JsonArray).filter {
                    (it as JsonObject)["path"]?.stringOrNull().orEmpty()
                        .startsWith("event.payload[].velocity") ||
                        (it as JsonObject)["path"]?.stringOrNull().orEmpty()
                            .startsWith("event.payload[].angularVelocity")
                },
            )
            val payload = parseRow(
                """{"body1":"b0","body2":"b1","velocity1":[0.0,0.0],""" +
                    """"velocity2":[0.0,0.0],"angularVelocity1":0.0,"angularVelocity2":0.0}""",
            )
            rows = rows.replace(1, rows[1].with("payload", JsonArray(listOf(payload))))
            rows = rows.replace(2, rows[2].with("state", parseRow("""{"bodies":[]}""")))
            writeReference(rows)
            writeCandidate(rows)
            assertEquals("PASSED", result()["status"]?.stringOrNull())
            for ((field, value) in listOf(
                "velocity1" to numbers(0.0005, 0.0),
                "angularVelocity1" to JsonPrimitive(0.0005),
            )) {
                val altered = rows.replace(
                    1,
                    rows[1].with("payload", JsonArray(listOf(payload.with(field, value)))),
                )
                writeCandidate(altered)
                val outcome = result()
                assertEquals("FAILED", outcome["status"]?.stringOrNull(), field)
                assertTrue(
                    outcome["reason"]?.stringOrNull().orEmpty()
                        .contains("fixed callback body velocity"),
                )
            }
        }
    }

    test("a nominal moving b0 uses the approved rotation limit") {
        scenario {
            fixture.clear()
            fixture.putAll(loadFixture("nominal-free-motion"))
            fixture["counts"] = parseRow("""{"inputs":1,"event":1,"state":1}""")
            fixture["reference"] = parseRow("""{"file":"reference.jsonl.gz"}""")
            rows = listOf(
                parseRow("""{"kind":"inputs","id":"${fixture.getValue("id").stringOrNull()}"}"""),
                parseRow(
                    """{"kind":"event","step":1,"order":0,"listener":"StepListener",""" +
                        """"method":"begin","payload":[]}""",
                ),
                parseRow(
                    """{"kind":"state","step":1,"state":{"bodies":[{"id":"b0",""" +
                        """"velocity":[0.25,-0.125],"angularVelocity":0.5,""" +
                        """"rotationIncrementSum":0.008333333333327246}]}}""",
                ),
            )
            writeReference(rows)
            var candidate = rows.replace(
                2,
                rows[2].at(
                    listOf("state", "bodies"),
                    JsonArray(
                        listOf(
                            ((rows[2].obj("state").array("bodies"))[0] as JsonObject).with(
                                "rotationIncrementSum",
                                JsonPrimitive(0.008333333333327244),
                            ),
                        ),
                    ),
                ),
            )
            writeCandidate(candidate)
            var outcome = result()
            assertEquals("PASSED", outcome["status"]?.stringOrNull(), outcome.toString())
            candidate = candidate.replace(
                2,
                candidate[2].at(
                    listOf("state", "bodies"),
                    JsonArray(
                        listOf(
                            ((candidate[2].obj("state").array("bodies"))[0] as JsonObject).with(
                                "rotationIncrementSum",
                                JsonPrimitive(0.008333333333327244 + 2e-7),
                            ),
                        ),
                    ),
                ),
            )
            writeCandidate(candidate)
            outcome = result()
            assertEquals("FAILED", outcome["status"]?.stringOrNull(), outcome.toString())
            assertTrue(outcome["reason"]?.stringOrNull().orEmpty().contains("numeric limit exceeded"))
        }
    }

    test("the sleep/wake fixed floor b0 stays exact") {
        for (key in listOf("configured-30-r1", "default-sleep-30")) {
            scenario {
                fixture.clear()
                fixture.putAll(loadFixture(key))
                fixture["counts"] = parseRow("""{"inputs":1,"event":1,"state":1}""")
                fixture["reference"] = parseRow("""{"file":"reference.jsonl.gz"}""")
                rows = listOf(
                    parseRow("""{"kind":"inputs","id":"${fixture.getValue("id").stringOrNull()}"}"""),
                    parseRow(
                        """{"kind":"event","step":1,"order":0,"listener":"StepListener",""" +
                            """"method":"begin","payload":[]}""",
                    ),
                    parseRow(
                        """{"kind":"state","step":1,"state":{"bodies":[{"id":"b0",""" +
                            """"rotationIncrementSum":0.0}]}}""",
                    ),
                )
                writeReference(rows)
                val candidate = rows.replace(
                    2,
                    rows[2].at(
                        listOf("state", "bodies"),
                        JsonArray(
                            listOf(
                                ((rows[2].obj("state").array("bodies"))[0] as JsonObject).with(
                                    "rotationIncrementSum",
                                    JsonPrimitive(1e-5),
                                ),
                            ),
                        ),
                    ),
                )
                writeCandidate(candidate)
                var outcome = result()
                assertEquals("FAILED", outcome["status"]?.stringOrNull(), key)
                assertTrue(outcome["reason"]?.stringOrNull().orEmpty().contains("fixed floor differs"))
                if (key == "configured-30-r1") {
                    fixture.remove("callback_fixed_body_id")
                    outcome = result()
                    assertEquals("FAILED", outcome["status"]?.stringOrNull())
                    assertTrue(
                        outcome["reason"]?.stringOrNull().orEmpty()
                            .contains("fixed floor role is missing"),
                    )
                }
            }
        }
    }

    test("the configured floor uses the declared b1 role") {
        scenario {
            fixture.clear()
            fixture.putAll(loadFixture("configured-30-r1"))
            fixture["callback_fixed_body_id"] = JsonPrimitive("b1")
            fixture["counts"] = parseRow("""{"inputs":1,"event":1,"state":1}""")
            fixture["reference"] = parseRow("""{"file":"reference.jsonl.gz"}""")
            rows = listOf(
                parseRow("""{"kind":"inputs","id":"${fixture.getValue("id").stringOrNull()}"}"""),
                parseRow(
                    """{"kind":"event","step":1,"order":0,"listener":"StepListener",""" +
                        """"method":"begin","payload":[]}""",
                ),
                parseRow(
                    """{"kind":"state","step":1,"state":{"bodies":[""" +
                        """{"id":"b0","rotationIncrementSum":0.0},""" +
                        """{"id":"b1","rotationIncrementSum":0.0}]}}""",
                ),
            )
            writeReference(rows)
            fun candidate(b0: Double, b1: Double): List<JsonObject> = rows.replace(
                2,
                rows[2].at(
                    listOf("state", "bodies"),
                    JsonArray(
                        listOf(
                            parseRow("""{"id":"b0","rotationIncrementSum":$b0}"""),
                            parseRow("""{"id":"b1","rotationIncrementSum":$b1}"""),
                        ),
                    ),
                ),
            )
            writeCandidate(candidate(1e-5, 0.0))
            var outcome = result()
            assertEquals("PASSED", outcome["status"]?.stringOrNull(), outcome.toString())
            writeCandidate(candidate(1.1e-4, 0.0))
            outcome = result()
            assertEquals("FAILED", outcome["status"]?.stringOrNull())
            assertTrue(outcome["reason"]?.stringOrNull().orEmpty().contains("numeric limit exceeded"))
            writeCandidate(candidate(1e-5, 1e-18))
            outcome = result()
            assertEquals("FAILED", outcome["status"]?.stringOrNull())
            assertTrue(outcome["reason"]?.stringOrNull().orEmpty().contains("fixed floor differs"))
        }
    }

    test("an outer endpoint uses the inner state budget") {
        scenario {
            rows = rows.replace(2, rows[2].with("state", parseRow("""{"position":[2.0,3.0]}""")))
            rows = rows + parseRow(
                """{"kind":"outer-endpoint","step":1,"outerStep":1,"state":{"position":[2.0,3.0]}}""",
            )
            fixture["counts"] = parseRow("""{"inputs":1,"event":1,"state":1,"outer-endpoint":1}""")
            fixture["inner_per_outer"] = JsonPrimitive(1)
            val exact = ArrayList<JsonElement>(fixture.getValue("exact_numeric") as JsonArray)
            exact.add(JsonPrimitive("outer-endpoint.step"))
            exact.add(JsonPrimitive("outer-endpoint.outerStep"))
            fixture["exact_numeric"] = JsonArray(exact)
            writeReference(rows)
            var altered = rows.replace(2, rows[2].at(listOf("state", "position"), numbers(2.05, 3.0)))
                .replace(3, rows[3].at(listOf("state", "position"), numbers(2.05, 3.0)))
            writeCandidate(altered)
            assertEquals("PASSED", result()["status"]?.stringOrNull())
            altered = rows.replace(2, rows[2].at(listOf("state", "position"), numbers(2.2, 3.0)))
                .replace(3, rows[3].at(listOf("state", "position"), numbers(2.2, 3.0)))
            writeCandidate(altered)
            assertEquals("FAILED", result()["status"]?.stringOrNull())
        }
    }

    test("static fixture values are exact and force is zero") {
        scenario {
            val selected = configured()
            fixture["exact_numeric"] = JsonArray(
                (selected.getValue("exact_numeric") as JsonArray).toList() +
                    listOf(JsonPrimitive("inputs.dt")),
            )
            fixture["zero_numeric"] = selected.getValue("zero_numeric")
            rows = rows.replace(
                1,
                rows[1].with(
                    "payload",
                    JsonArray(
                        listOf(
                            parseRow("""{"getFriction":0.5,"shape":{"getRadius":0.7071067811865476}}"""),
                        ),
                    ),
                ),
            )
            rows = rows.replace(
                2,
                rows[2].with(
                    "state",
                    parseRow(
                        """{"bodies":[{"id":"b1","force":[0.0,0.0],"torque":0.0}]}""",
                    ),
                ),
            )
            writeReference(rows)
            writeCandidate(rows)
            assertEquals("PASSED", result()["status"]?.stringOrNull())
            val mutations = listOf<Pair<String, (List<JsonObject>) -> List<JsonObject>>>(
                "getFriction" to { current ->
                    current.replace(
                        1,
                        current[1].with(
                            "payload",
                            JsonArray(
                                listOf(
                                    parseRow(
                                        """{"getFriction":0.6,"shape":{"getRadius":0.7071067811865476}}""",
                                    ),
                                ),
                            ),
                        ),
                    )
                },
                "getRadius" to { current ->
                    current.replace(
                        1,
                        current[1].with(
                            "payload",
                            JsonArray(listOf(parseRow("""{"getFriction":0.5,"shape":{"getRadius":0.8}}"""))) ,
                        ),
                    )
                },
                "force" to { current ->
                    current.replace(
                        2,
                        current[2].with(
                            "state",
                            parseRow("""{"bodies":[{"id":"b1","force":[0.01,0.0],"torque":0.0}]}"""),
                        ),
                    )
                },
                "torque" to { current ->
                    current.replace(
                        2,
                        current[2].with(
                            "state",
                            parseRow("""{"bodies":[{"id":"b1","force":[0.0,0.0],"torque":0.01}]}"""),
                        ),
                    )
                },
            )
            for ((name, mutation) in mutations) {
                writeCandidate(mutation(rows))
                assertEquals("FAILED", result()["status"]?.stringOrNull(), name)
            }
        }
    }

    test("the previous transform and the wake snapshot inherit the primary limits") {
        scenario {
            val selected = configured()
            fixture["rules"] = selected.getValue("rules")
            fixture["exact_numeric"] = parseJson(
                """["inputs.dt","event.step","event.order","state.step",""" +
                    """"instrumented-callback.step","instrumented-callback.order"]""",
            )
            val body = parseRow(
                """{"id":"b1","transform":{"getTranslation":[1.0,2.0],""" +
                    """"getRotationAngle":0.1},"previousTransform":{"getTranslation":[0.9,2.0],""" +
                    """"getRotationAngle":0.09},"velocity":[0.0,0.0],"angularVelocity":0.0}""",
            )
            rows = rows.replace(1, rows[1].with("payload", JsonArray(emptyList())))
            rows = rows.replace(
                2,
                rows[2].with("state", parseRow("""{"bodies":[]}""").with("bodies", JsonArray(listOf(body)))),
            )
            rows = rows + parseRow(
                """{"kind":"instrumented-callback","step":1,"order":0,"event":"before-wake",""" +
                    """"values":[{"bodies":[]}]}""",
            ).with("values", JsonArray(listOf(parseRow("""{"bodies":[]}""").with("bodies", JsonArray(listOf(body))))))
            fixture["counts"] = parseRow(
                """{"inputs":1,"event":1,"state":1,"instrumented-callback":1}""",
            )
            writeReference(rows)
            val bumped = body.at(listOf("previousTransform", "getTranslation"), numbers(0.90005, 2.0))
                .at(listOf("previousTransform", "getRotationAngle"), JsonPrimitive(0.09005))
            var altered = rows.replace(
                2,
                rows[2].with("state", rows[2].obj("state").with("bodies", JsonArray(listOf(bumped)))),
            )
            altered = altered.replace(
                3,
                altered[3].with(
                    "values",
                    JsonArray(
                        listOf(
                            parseRow("""{"bodies":[]}""").with("bodies", JsonArray(listOf(bumped))),
                        ),
                    ),
                ),
            )
            writeCandidate(altered)
            assertEquals("PASSED", result()["status"]?.stringOrNull())
            val far = bumped.at(listOf("previousTransform", "getTranslation"), numbers(0.9002, 2.0))
            altered = altered.replace(
                3,
                altered[3].with(
                    "values",
                    JsonArray(
                        listOf(
                            parseRow("""{"bodies":[]}""").with("bodies", JsonArray(listOf(far))),
                        ),
                    ),
                ),
            )
            writeCandidate(altered)
            assertEquals("FAILED", result()["status"]?.stringOrNull())
        }
    }

    test("the matrix getter uses component limits and aliases") {
        scenario {
            val selected = configured()
            fixture["rules"] = selected.getValue("rules")
            fixture["check_translation_aliases"] = JsonPrimitive(true)
            rows = rows.replace(1, rows[1].with("payload", JsonArray(emptyList())))
            val transform = parseRow(
                """{"getCost":1.0,"getSint":0.0,"getTranslation":[1.0,2.0],""" +
                    """"getTranslationX":1.0,"getTranslationY":2.0,""" +
                    """"getValues":[1.0,-0.0,1.0,0.0,1.0,2.0]}""",
            )
            rows = rows.replace(
                2,
                rows[2].with(
                    "state",
                    parseRow("""{"bodies":[]}""").with(
                        "bodies",
                        JsonArray(listOf(parseRow("""{"id":"b1","transform":{}}""").with("transform", transform))),
                    ),
                ),
            )
            writeReference(rows)
            var altered = rows.replace(
                2,
                rows[2].at(
                    listOf("state", "bodies"),
                    JsonArray(
                        listOf(
                            parseRow("""{"id":"b1","transform":{}}""").with(
                                "transform",
                                transform.with("getTranslation", numbers(1.00005, 2.0))
                                    .with("getTranslationX", JsonPrimitive(1.00005))
                                    .with(
                                        "getValues",
                                        (transform.getValue("getValues") as JsonArray)
                                            .with(2, JsonPrimitive(1.00005)),
                                    ),
                            ),
                        ),
                    ),
                ),
            )
            writeCandidate(altered)
            var outcome = result()
            assertEquals("UNPASSED", outcome["status"]?.stringOrNull(), outcome.toString())
            assertTrue(
                !(outcome.getValue("unpassed_channels") as JsonArray)
                    .map { it.stringOrNull() }
                    .contains("state.state.bodies[].transform.getValues[]"),
            )
            altered = rows.replace(
                2,
                rows[2].at(
                    listOf("state", "bodies"),
                    JsonArray(
                        listOf(
                            parseRow("""{"id":"b1","transform":{}}""").with(
                                "transform",
                                transform.with("getTranslation", numbers(1.00005, 2.0))
                                    .with("getTranslationX", JsonPrimitive(1.00005))
                                    .with(
                                        "getValues",
                                        (transform.getValue("getValues") as JsonArray)
                                            .with(2, JsonPrimitive(1.02)),
                                    ),
                            ),
                        ),
                    ),
                ),
            )
            writeCandidate(altered)
            assertEquals("FAILED", result()["status"]?.stringOrNull())
        }
    }

    test("the wake getter formula rejects a changed subtraction") {
        scenario {
            val selected = configured()
            fixture["rules"] = selected.getValue("rules")
            fixture["derived_rules"] = selected.getValue("derived_rules")
            fixture["check_translation_aliases"] = JsonPrimitive(true)
            fixture["exact_numeric"] = parseJson(
                """["inputs.dt","event.step","event.order","state.step",""" +
                    """"instrumented-callback.step","instrumented-callback.order"]""",
            )
            val body = parseRow(
                """{"id":"b1","transform":{"getTranslation":[1.0,2.0],""" +
                    """"getTranslationX":1.0,"getTranslationY":2.0,"getRotationAngle":0.2},""" +
                    """"previousTransform":{"getTranslation":[0.9,2.0],"getTranslationX":0.9,""" +
                    """"getTranslationY":2.0,"getRotationAngle":0.1},"angularVelocity":1.0,""" +
                    """"properties":{"getChangeInPosition":[0.09999999999999998,0.0],""" +
                    """"getChangeInOrientation":0.1}}""",
            )
            rows = rows.replace(1, rows[1].with("payload", JsonArray(emptyList())))
            rows = rows.replace(2, rows[2].with("state", parseRow("""{"bodies":[]}""")))
            rows = rows + parseRow(
                """{"kind":"instrumented-callback","step":1,"order":0,"event":"before-wake",""" +
                    """"values":[{"bodies":[]}]}""",
            ).with(
                "values",
                JsonArray(listOf(parseRow("""{"bodies":[]}""").with("bodies", JsonArray(listOf(body))))),
            )
            fixture["counts"] = parseRow(
                """{"inputs":1,"event":1,"state":1,"instrumented-callback":1}""",
            )
            writeReference(rows)
            writeCandidate(rows)
            assertEquals("PASSED", result()["status"]?.stringOrNull())
            val properties = body.obj("properties")
            var altered = rows.replace(
                3,
                rows[3].with(
                    "values",
                    JsonArray(
                        listOf(
                            parseRow("""{"bodies":[]}""").with(
                                "bodies",
                                JsonArray(
                                    listOf(
                                        body.with(
                                            "properties",
                                            properties.with(
                                                "getChangeInPosition",
                                                numbers(0.09999999999999998 + 0.00001, 0.0),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            )
            writeCandidate(altered)
            assertEquals("FAILED", result()["status"]?.stringOrNull())
            altered = rows.replace(
                3,
                rows[3].with(
                    "values",
                    JsonArray(
                        listOf(
                            parseRow("""{"bodies":[]}""").with(
                                "bodies",
                                JsonArray(
                                    listOf(
                                        body.with(
                                            "properties",
                                            properties.with(
                                                "getChangeInOrientation",
                                                JsonPrimitive(0.10001),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            )
            writeCandidate(altered)
            assertEquals("FAILED", result()["status"]?.stringOrNull())
            writeReference(altered)
            assertEquals("FAILED", auditReference()["status"]?.stringOrNull())
        }
    }

    test("the wake snapshot static fields keep exact identity") {
        scenario {
            val selected = configured()
            fixture["exact_numeric"] = selected.getValue("exact_numeric")
            val snapshot = parseRow(
                """{"bodies":[{"id":"b1","fixtures":[{"getDensity":1.0,""" +
                    """"shape":{"getRadius":0.7071067811865476}}],""" +
                    """"properties":{"getMass":{"getInertia":0.16666666666666666}}}]}""",
            )
            rows = rows + parseRow(
                """{"kind":"instrumented-callback","step":1,"order":0,"event":"before-wake",""" +
                    """"values":[{"bodies":[]}]}""",
            ).with("values", JsonArray(listOf(snapshot)))
            fixture["counts"] = parseRow(
                """{"inputs":1,"event":1,"state":1,"instrumented-callback":1}""",
            )
            writeReference(rows)
            writeCandidate(rows)
            assertEquals("PASSED", result()["status"]?.stringOrNull())
            val alteredSnapshot = snapshot.at(
                listOf("bodies"),
                JsonArray(
                    listOf(
                        (snapshot.getValue("bodies") as JsonArray)[0].let { it as JsonObject }.at(
                            listOf("properties", "getMass", "getInertia"),
                            JsonPrimitive(0.16666666666666666 + 0.00001),
                        ),
                    ),
                ),
            )
            writeCandidate(
                rows.replace(
                    3,
                    rows[3].with("values", JsonArray(listOf(alteredSnapshot))),
                ),
            )
            assertEquals("FAILED", result()["status"]?.stringOrNull())
        }
    }

    test("a wake orientation branch change fails closed") {
        scenario {
            val selected = configured()
            fixture["rules"] = selected.getValue("rules")
            fixture["derived_rules"] = selected.getValue("derived_rules")
            fixture["exact_numeric"] = parseJson(
                """["inputs.dt","event.step","event.order","state.step",""" +
                    """"instrumented-callback.step","instrumented-callback.order"]""",
            )
            fixture["check_translation_aliases"] = JsonPrimitive(true)
            val change = (0.2 - (-0.00004 + 2 * Math.PI)) + 2 * Math.PI
            val body = parseRow(
                """{"id":"b1","transform":{"getTranslation":[0.0,0.0],""" +
                    """"getTranslationX":0.0,"getTranslationY":0.0,"getRotationAngle":0.2},""" +
                    """"previousTransform":{"getTranslation":[0.0,0.0],"getTranslationX":0.0,""" +
                    """"getTranslationY":0.0,"getRotationAngle":-0.00004},""" +
                    """"angularVelocity":1.0,"properties":{"getChangeInPosition":[0.0,0.0],""" +
                    """"getChangeInOrientation":$change}}""",
            )
            rows = rows.replace(1, rows[1].with("payload", JsonArray(emptyList())))
            rows = rows.replace(2, rows[2].with("state", parseRow("""{"bodies":[]}""")))
            rows = rows + parseRow(
                """{"kind":"instrumented-callback","step":1,"order":0,"event":"before-wake",""" +
                    """"values":[{"bodies":[]}]}""",
            ).with(
                "values",
                JsonArray(listOf(parseRow("""{"bodies":[]}""").with("bodies", JsonArray(listOf(body))))),
            )
            fixture["counts"] = parseRow(
                """{"inputs":1,"event":1,"state":1,"instrumented-callback":1}""",
            )
            writeReference(rows)
            val changed = body.at(
                listOf("previousTransform", "getRotationAngle"),
                JsonPrimitive(0.00004),
            ).with("properties", body.obj("properties").with("getChangeInOrientation", JsonPrimitive(0.2 - 0.00004)))
            writeCandidate(
                rows.replace(
                    3,
                    rows[3].with(
                        "values",
                        JsonArray(
                            listOf(
                                parseRow("""{"bodies":[]}""").with("bodies", JsonArray(listOf(changed))),
                            ),
                        ),
                    ),
                ),
            )
            assertTrue(
                result()["reason"]?.stringOrNull().orEmpty().contains("branch differs"),
            )
        }
    }

    test("stored sine requires norm and component enclosures") {
        scenario {
            val selected = configured()
            fixture["rules"] = selected.getValue("rules")
            fixture["derived_rules"] = selected.getValue("derived_rules")
            rows = rows.replace(1, rows[1].with("payload", JsonArray(emptyList())))
            val transform = parseRow(
                """{"getCost":1.0,"getSint":0.0,"getRotationAngle":0.0}""",
            )
            rows = rows.replace(
                2,
                rows[2].with(
                    "state",
                    parseRow("""{"bodies":[]}""").with(
                        "bodies",
                        JsonArray(listOf(parseRow("""{"id":"b1","transform":{}}""").with("transform", transform))),
                    ),
                ),
            )
            writeReference(rows)
            writeCandidate(rows)
            var outcome = result()
            assertEquals("PASSED", outcome["status"]?.stringOrNull())
            assertEquals(0, (outcome.getValue("unpassed_channels") as JsonArray).size)
            fun candidate(sine: JsonElement, cost: JsonElement = JsonPrimitive(1.0)): List<JsonObject> =
                rows.replace(
                    2,
                    rows[2].at(
                        listOf("state", "bodies"),
                        JsonArray(
                            listOf(
                                parseRow("""{"id":"b1","transform":{}}""").with(
                                    "transform",
                                    transform.with("getSint", sine).with("getCost", cost),
                                ),
                            ),
                        ),
                    ),
                )
            writeCandidate(candidate(JsonPrimitive(0.00005)))
            assertEquals("PASSED", result()["status"]?.stringOrNull())
            writeCandidate(candidate(JsonPrimitive(0.0), JsonPrimitive(0.999)))
            assertEquals("FAILED", result()["status"]?.stringOrNull())
            writeCandidate(candidate(JsonPrimitive(0.9)))
            outcome = result()
            assertEquals("FAILED", outcome["status"]?.stringOrNull())
            assertTrue(outcome["reason"]?.stringOrNull().orEmpty().contains("norm"))
        }
    }

    test("sine and matrix reject out-of-bound or invalid values") {
        scenario {
            val selected = configured()
            fixture["rules"] = selected.getValue("rules")
            fixture["derived_rules"] = selected.getValue("derived_rules")
            fixture["check_translation_aliases"] = JsonPrimitive(true)
            rows = rows.replace(1, rows[1].with("payload", JsonArray(emptyList())))
            val transform = parseRow(
                """{"getCost":1.0,"getSint":0.0,"getRotationAngle":0.0,""" +
                    """"getTranslation":[1.0,2.0],"getTranslationX":1.0,"getTranslationY":2.0,""" +
                    """"getValues":[1.0,-0.0,1.0,0.0,1.0,2.0]}""",
            )
            rows = rows.replace(
                2,
                rows[2].with(
                    "state",
                    parseRow("""{"bodies":[]}""").with(
                        "bodies",
                        JsonArray(listOf(parseRow("""{"id":"b1","transform":{}}""").with("transform", transform))),
                    ),
                ),
            )
            writeReference(rows)
            writeCandidate(rows)
            assertEquals("PASSED", result()["status"]?.stringOrNull())
            for (value in listOf(0.001, Double.POSITIVE_INFINITY, Double.NaN)) {
                val changed = transform.with("getSint", JsonPrimitive(value))
                    .with(
                        "getValues",
                        (transform.getValue("getValues") as JsonArray)
                            .with(1, JsonPrimitive(-value))
                            .with(3, JsonPrimitive(value)),
                    )
                writeCandidate(
                    rows.replace(
                        2,
                        rows[2].at(
                            listOf("state", "bodies"),
                            JsonArray(
                                listOf(
                                    parseRow("""{"id":"b1","transform":{}}""").with("transform", changed),
                                ),
                            ),
                        ),
                    ),
                )
                assertEquals("FAILED", result()["status"]?.stringOrNull(), "sine=$value")
            }
            val alias = transform.with(
                "getValues",
                (transform.getValue("getValues") as JsonArray).with(3, JsonPrimitive(0.00005)),
            )
            writeCandidate(
                rows.replace(
                    2,
                    rows[2].at(
                        listOf("state", "bodies"),
                        JsonArray(
                            listOf(parseRow("""{"id":"b1","transform":{}}""").with("transform", alias)),
                        ),
                    ),
                ),
            )
            assertEquals("FAILED", result()["status"]?.stringOrNull())
            assertTrue(result()["reason"]?.stringOrNull().orEmpty().contains("matrix getter alias"))
        }
    }

    test("the same-run matrix alias accepts zero sign and rejects a nonzero difference") {
        scenario {
            val selected = configured()
            fixture["rules"] = selected.getValue("rules")
            fixture["derived_rules"] = selected.getValue("derived_rules")
            fixture["exact_numeric"] = selected.getValue("exact_numeric")
            fixture["zero_numeric"] = selected.getValue("zero_numeric")
            fixture["check_translation_aliases"] = JsonPrimitive(true)
            rows = rows.replace(1, rows[1].with("payload", JsonArray(emptyList())))
            val transform = parseRow(
                """{"getCost":1.0,"getSint":0.0,"getRotationAngle":0.0,""" +
                    """"getTranslation":[1.0,2.0],"getTranslationX":1.0,"getTranslationY":2.0,""" +
                    """"getValues":[1.0,-0.0,1.0,0.0,1.0,2.0]}""",
            )
            rows = rows.replace(
                2,
                rows[2].with(
                    "state",
                    parseRow("""{"bodies":[]}""").with(
                        "bodies",
                        JsonArray(listOf(parseRow("""{"id":"b1","transform":{}}""").with("transform", transform))),
                    ),
                ),
            )
            writeReference(rows)
            writeCandidate(rows)
            assertEquals("PASSED", result()["status"]?.stringOrNull(), result().toString())
            fun candidate(second: Double): List<JsonObject> = rows.replace(
                2,
                rows[2].at(
                    listOf("state", "bodies"),
                    JsonArray(
                        listOf(
                            parseRow("""{"id":"b1","transform":{}}""").with(
                                "transform",
                                transform.with(
                                    "getValues",
                                    (transform.getValue("getValues") as JsonArray)
                                        .with(1, JsonPrimitive(second)),
                                ),
                            ),
                        ),
                    ),
                ),
            )
            writeCandidate(candidate(0.0))
            assertEquals("PASSED", result()["status"]?.stringOrNull())
            writeCandidate(candidate(0.001))
            assertEquals("FAILED", result()["status"]?.stringOrNull())
            assertTrue(result()["reason"]?.stringOrNull().orEmpty().contains("matrix getter alias"))
        }
    }

    test("snapshot duplicate getters compare finite numeric values") {
        val state = parseRow(
            """{"bodies":[{"id":"b1","force":[-0.0,0.0],"properties":{"getForce":[0.0,-0.0]},""" +
                """"transform":{"getTranslation":[0.0,0.0],"getTranslationX":-0.0,""" +
                """"getTranslationY":0.0,"getCost":1.0,"getSint":0.0,""" +
                """"getValues":[1.0,0.0,0.0,-0.0,1.0,0.0]}}]}""",
        )
        Compare.checkSnapshot(state)
        val changed = state.at(
            listOf("bodies"),
            JsonArray(
                listOf(
                    (state.getValue("bodies") as JsonArray)[0].let { it as JsonObject }.at(
                        listOf("properties", "getForce"),
                        numbers(0.01, -0.0),
                    ),
                ),
            ),
        )
        val failure = assertFailsWith<Rejected> { Compare.checkSnapshot(changed) }
        assertEquals("body getter alias differs: getForce", failure.message)
    }

    test("an explicit nominal cosine cap keeps precedence") {
        scenario {
            fixture["rules"] = parseJson(
                """[{"path":"state.state.bodies[].transform.getCost","metric":"scalar",""" +
                    """"absolute":1e-10,"relative":0,"unit":"dimensionless"},""" +
                    """{"path":"state.state.bodies[].transform.getRotationAngle",""" +
                    """"metric":"orientation","absolute":1e-7,"relative":0,"unit":"rad"}]""",
            )
            rows = rows.replace(1, rows[1].with("payload", JsonArray(emptyList())))
            val transform = parseRow(
                """{"getCost":${kotlin.math.cos(0.3)},"getRotationAngle":0.3}""",
            )
            rows = rows.replace(
                2,
                rows[2].with(
                    "state",
                    parseRow("""{"bodies":[]}""").with(
                        "bodies",
                        JsonArray(listOf(parseRow("""{"id":"b1","transform":{}}""").with("transform", transform))),
                    ),
                ),
            )
            writeReference(rows)
            val altered = transform.with(
                "getCost",
                JsonPrimitive(kotlin.math.cos(0.30000001)),
            ).with("getRotationAngle", JsonPrimitive(0.30000001))
            writeCandidate(
                rows.replace(
                    2,
                    rows[2].at(
                        listOf("state", "bodies"),
                        JsonArray(
                            listOf(parseRow("""{"id":"b1","transform":{}}""").with("transform", altered)),
                        ),
                    ),
                ),
            )
            assertEquals("FAILED", result()["status"]?.stringOrNull())
        }
    }
}
