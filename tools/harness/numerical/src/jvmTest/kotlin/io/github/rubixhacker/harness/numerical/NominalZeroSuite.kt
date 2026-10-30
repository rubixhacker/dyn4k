package io.github.rubixhacker.harness.numerical

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.nio.file.Files
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

private fun body(): JsonObject = parseRow(
    """{"force":[0.0,0.0],"torque":0.0,"accumulatedForce":[0.0,0.0],"accumulatedTorque":0.0}""",
)

/** `candidate/test_nominal_zero.py`. */
val NominalZeroContract by testSuite {
    test("the four zero paths reject negative zero, non-zero and missing fields") {
        assertEquals(6, NominalZero.checkBody(body()))
        for ((field, index) in listOf(
            "force" to 0,
            "torque" to null,
            "accumulatedForce" to 1,
            "accumulatedTorque" to null,
        )) {
            for (bad in listOf(
                -0.0,
                Double.NaN,
                Double.POSITIVE_INFINITY,
                Double.NEGATIVE_INFINITY,
                1.0,
                5e-324,
            )) {
                val value = JsonPrimitive(bad)
                val changed = if (index == null) {
                    body().with(field, value)
                } else {
                    body().with(
                        field,
                        (body().getValue(field) as JsonArray).with(index, value),
                    )
                }
                assertFailsWith<Rejected>("$field=$bad") { NominalZero.checkBody(changed) }
            }
            val integer = if (index == null) {
                body().with(field, JsonPrimitive(0))
            } else {
                body().with(field, (body().getValue(field) as JsonArray).with(index, JsonPrimitive(0)))
            }
            assertFailsWith<Rejected>("$field=0") { NominalZero.checkBody(integer) }
            assertFailsWith<Rejected>("$field missing") {
                NominalZero.checkBody(body().without(field))
            }
        }
    }

    test("the nominal rule overlay selects only the four frozen zero paths") {
        val fixture = parseRow(
            """{"key":"nominal-free-motion","rules":[{"path":"position","absolute":1e-10}],""" +
                """"exact_numeric":["inputs.*"]}""",
        )
        val selected = NominalZero.withRules(fixture)
        assertEquals(
            JsonArray(NominalZero.ZERO_PATHS.map { JsonPrimitive(it) }),
            selected.getValue("zero_numeric"),
        )
        assertEquals(fixture.getValue("rules"), selected.getValue("rules"))
        val exact = selected.getValue("exact_numeric") as JsonArray
        assertEquals(fixture.getValue("exact_numeric"), JsonArray(exact.take(1)))
        assertEquals(
            JsonArray(
                listOf(
                    "event.payload[].getDeltaTime",
                    "event.payload[].getPrevousDeltaTime",
                    "event.payload[].getInverseDeltaTime",
                    "event.payload[].getPreviousInverseDeltaTime",
                    "event.payload[].getDeltaTimeRatio",
                ).map { JsonPrimitive(it) },
            ),
            JsonArray(exact.drop(1)),
        )
        assertEquals(false, fixture.containsKey("zero_numeric"))
        assertEquals(selected, NominalZero.withRules(selected))
        val failure = assertFailsWith<Rejected> {
            NominalZero.withRules(
                fixture.with("zero_numeric", parseJson("""["unapproved.path"]""")),
            )
        }
        assertEquals("nominal zero rule scope differs", failure.message)
    }

    test("the candidate comparison rejects negative zero before the numeric comparator") {
        val fixture = parseRow("""{"key":"nominal-free-motion","counts":{"state":1,"event":0}}""")
        val directory = Files.createTempDirectory("nominal-zero")
        try {
            val reference = directory.resolve("reference.jsonl")
            val candidate = directory.resolve("candidate.jsonl")
            val row = parseRow("""{"kind":"state","state":{"bodies":[]}}""").with(
                "state",
                parseRow("""{"bodies":[]}""").with("bodies", JsonArray(listOf(body()))),
            )
            Files.writeString(reference, row.toString() + "\n")
            val negative = row.with(
                "state",
                row.obj("state").with(
                    "bodies",
                    JsonArray(
                        listOf(
                            body().with("force", numbers(-0.0, 0.0)),
                        ),
                    ),
                ),
            )
            Files.writeString(candidate, negative.toString() + "\n")
            val failure = assertFailsWith<Rejected> {
                NominalZeroHost.comparePair(
                    fixture, reference, candidate, directory.resolve("receipt"),
                    "source", "artifact", "commit",
                )
            }
            assertEquals(
                "nominal field is not positive binary64 zero: force",
                failure.message,
            )
            Files.writeString(candidate, Files.readString(reference))
            val result = NominalZeroHost.comparePair(
                fixture, reference, candidate, directory.resolve("receipt"),
                "source", "artifact", "commit",
            )
            val zeroBlocks = result.getValue("nominal_positive_zero") as JsonObject
            assertEquals(
                6,
                (zeroBlocks.getValue("candidate") as JsonObject).int("positive_zero_checks"),
            )
        } finally {
            directory.toFile().deleteRecursively()
        }
    }

    test("every nominal callback getter has the approved exact binary64 value") {
        val values = NominalZero.TIMESTEP_VALUES
        val directory = Files.createTempDirectory("nominal-timestep")
        try {
            val trace = directory.resolve("nominal.jsonl")
            val world = parseRow("""{"world":"L-free-s1.0-o0.0,0.0-hz60"}""")
            for (method in listOf("begin", "updatePerformed", "postSolve", "end")) {
                val step = parseRow("""{"type":"org.dyn4j.dynamics.TimeStep"}""").let { base ->
                    values.fold(base) { current, (field, value) ->
                        current.with(field, JsonPrimitive(value))
                    }
                }
                val row = parseRow(
                    """{"kind":"event","step":1,"order":0,"listener":"StepListener",""" +
                        """"method":"public abstract void org.dyn4j.world.listener.StepListener.""" +
                        method + """(org.dyn4j.dynamics.TimeStep,org.dyn4j.world.PhysicsWorld<T, ?>)",""" +
                        """"payload":[]}""",
                ).with("payload", JsonArray(listOf(step, world)))
                Files.writeString(trace, row.toString() + "\n")
                assertEquals(
                    5,
                    NominalZero.auditTrace(
                        CompareHost.recordsOfBytes((row.toString() + "\n").toByteArray()),
                        0,
                        1,
                    ).int("exact_timestep_checks"),
                )
                val integer = row.with(
                    "payload",
                    JsonArray(
                        listOf(
                            step.with("getInverseDeltaTime", JsonPrimitive(60))
                                .with("getPreviousInverseDeltaTime", JsonPrimitive(60))
                                .with("getDeltaTimeRatio", JsonPrimitive(1)),
                            world,
                        ),
                    ),
                )
                assertEquals(
                    5,
                    NominalZero.auditTrace(
                        CompareHost.recordsOfBytes((integer.toString() + "\n").toByteArray()),
                        0,
                        1,
                    ).int("exact_timestep_checks"),
                )
                for ((field, value) in values) {
                    val changed = row.with(
                        "payload",
                        JsonArray(
                            listOf(
                                step.with(field, JsonPrimitive(Double.fromBits(value.toRawBits() + 1))),
                                world,
                            ),
                        ),
                    )
                    val failure = assertFailsWith<Rejected>("$method/$field") {
                        NominalZero.auditTrace(
                            CompareHost.recordsOfBytes((changed.toString() + "\n").toByteArray()),
                            0,
                            1,
                        )
                    }
                    assertEquals("nominal timestep $field differs", failure.message)
                }
                for (nonfinite in listOf(
                    Double.NaN,
                    Double.POSITIVE_INFINITY,
                    Double.NEGATIVE_INFINITY,
                )) {
                    val changed = row.with(
                        "payload",
                        JsonArray(
                            listOf(step.with("getDeltaTime", JsonPrimitive(nonfinite)), world),
                        ),
                    )
                    assertFailsWith<Rejected> {
                        NominalZero.auditTrace(
                            CompareHost.recordsOfBytes((changed.toString() + "\n").toByteArray()),
                            0,
                            1,
                        )
                    }
                }
                for (wrong in listOf<JsonElement>(JsonPrimitive(true), JsonPrimitive("0.016666666666666666"))) {
                    val changed = row.with(
                        "payload",
                        JsonArray(listOf(step.with("getDeltaTime", wrong), world)),
                    )
                    assertFailsWith<Rejected> {
                        NominalZero.auditTrace(
                            CompareHost.recordsOfBytes((changed.toString() + "\n").toByteArray()),
                            0,
                            1,
                        )
                    }
                }
            }
        } finally {
            directory.toFile().deleteRecursively()
        }
    }

    test("a nominal trace with the wrong callback count fails closed") {
        val failure = assertFailsWith<Rejected> {
            NominalZero.auditTrace(emptyList(), 0, 1)
        }
        assertTrue(failure.message.orEmpty().contains("nominal state or callback count differs"))
    }
}
