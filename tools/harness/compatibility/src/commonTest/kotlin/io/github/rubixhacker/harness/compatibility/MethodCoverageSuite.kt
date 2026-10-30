package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

private val coverage = Vectors.methodCoverage

private fun arrays(vararg values: JsonElement): JsonArray = JsonArray(values.toList())

private fun methodRowsDigest(rows: List<MethodCoverage.MethodRow>): String = Sha256.of(
    CanonicalJson.render(
        JsonArray(
            rows.map {
                arrays(
                    JsonPrimitive(it.owner),
                    JsonPrimitive(it.name),
                    JsonPrimitive(it.descriptor),
                    JsonPrimitive(it.coveredInstructions),
                    JsonPrimitive(it.totalInstructions),
                )
            },
        ),
    ),
)

private fun dispatchDigest(inventory: MethodCoverage.DispatchInventory): String = Sha256.of(
    CanonicalJson.render(
        buildJsonObject {
            put(
                "classes",
                JsonArray(
                    inventory.classes.entries.map { (name, row) ->
                        arrays(
                            JsonPrimitive(name),
                            JsonPrimitive(row.access),
                            JsonPrimitive(row.parent),
                            JsonArray(row.interfaces.map(::JsonPrimitive)),
                        )
                    },
                ),
            )
            put(
                "methods",
                JsonArray(
                    inventory.methods.entries.map { (key, access) ->
                        arrays(
                            JsonPrimitive(key.owner),
                            JsonPrimitive(key.name),
                            JsonPrimitive(key.descriptor),
                            JsonPrimitive(access),
                        )
                    },
                ),
            )
            put(
                "opcodes",
                JsonArray(
                    inventory.opcodes.entries.map { (key, codes) ->
                        arrays(
                            JsonPrimitive(key.owner),
                            JsonPrimitive(key.name),
                            JsonPrimitive(key.descriptor),
                            JsonArray(codes.map(::JsonPrimitive)),
                        )
                    },
                ),
            )
            put(
                "invokes",
                JsonArray(
                    inventory.invokes.entries.map { (key, rows) ->
                        arrays(
                            JsonPrimitive(key.owner),
                            JsonPrimitive(key.name),
                            JsonPrimitive(key.descriptor),
                            JsonArray(
                                rows.map {
                                    arrays(
                                        JsonPrimitive(it.opcode),
                                        JsonPrimitive(it.targetOwner),
                                        JsonPrimitive(it.targetName),
                                        JsonPrimitive(it.targetDescriptor),
                                    )
                                },
                            ),
                        )
                    },
                ),
            )
        },
    ),
)

/**
 * The pure half of `method_coverage.py`: the receipt path guard and the parsing and inventory gates
 * that `analyze` and `dispatch_inventory` apply to the helper output.
 *
 * `test_method_coverage.py` drives `check` over the pinned corpus, instrumented execution archive,
 * and JDKs, all of which stay with the unported host half.
 */
val MethodCoverageContract by testSuite {
    test("method receipt paths match the recorded safety") {
        for (case in coverage.array("safe_path").map { it.jsonObject }) {
            val recorded = case.obj("result")
            val error = recorded["error"]
            if (error == null) {
                assertEquals(
                    recorded.str("ok"),
                    MethodCoverage.safePath("root", case.str("name")).removePrefix("root/"),
                    case.str("name"),
                )
            } else {
                val thrown = assertFailsWith<IllegalArgumentException>(case.str("name")) {
                    MethodCoverage.safePath("root", case.str("name"))
                }
                assertEquals(error.jsonPrimitive.content, thrown.message, case.str("name"))
            }
        }
    }

    test("analyze reproduces the recorded method inventory") {
        val section = coverage.obj("analyze")
        val text = buildString {
            for (index in 0 until 3000) {
                append("o${index % 7}\tm$index\t()V\t${index % 5}\t5\n")
            }
        }
        assertEquals(section.str("text_sha256"), Sha256.of(text))
        val rows = MethodCoverage.analyzeOutput(text)
        assertEquals(section.int("rows_count"), rows.size)
        assertEquals(section.str("rows_sha256"), methodRowsDigest(rows))
    }

    test("a short method inventory is rejected") {
        val section = coverage.obj("analyze_short")
        val thrown = assertFailsWith<IllegalArgumentException> {
            MethodCoverage.analyzeOutput(section.str("text"))
        }
        assertEquals(section.str("error"), thrown.message)
    }

    test("dispatch inventory reproduces the recorded classfile rows") {
        val section = coverage.obj("dispatch_generated")
        val text = buildString {
            for (index in 0 until 200) {
                append("C\torg.dyn4j.C$index\t$index\tjava.lang.Object\tjava.io.Serializable\n")
            }
            for (index in 0 until 3000) {
                append("M\torg.dyn4j.C${index % 200}\tm$index\t()V\t${index % 4}\n")
            }
            for (index in 0 until 3000) {
                val codes = if (index % 3 == 0) "" else "18,21"
                append("O\torg.dyn4j.C${index % 200}\tm$index\t()V\t$codes\n")
            }
        }
        assertEquals(section.str("text_sha256"), Sha256.of(text))
        val inventory = MethodCoverage.dispatchInventoryOutput(text)
        assertEquals(section.int("classes_count"), inventory.classes.size)
        assertEquals(section.int("methods_count"), inventory.methods.size)
        assertEquals(section.int("opcodes_count"), inventory.opcodes.size)
        val firstClass = inventory.classes.getValue("org.dyn4j.C0")
        val recordedFirst = section.array("first_class")
        assertEquals(recordedFirst[0].jsonPrimitive.content.toInt(), firstClass.access)
        assertEquals(recordedFirst[1].jsonPrimitive.content, firstClass.parent)
        assertEquals(
            recordedFirst[2].jsonArray.map { it.jsonPrimitive.content },
            firstClass.interfaces,
        )
        assertEquals(
            section.array("last_method").map { it.jsonPrimitive.content },
            inventory.methods.keys.last().let { listOf(it.owner, it.name, it.descriptor) } +
                inventory.methods.values.last().toString(),
        )
        assertEquals(
            section.array("first_opcodes").map { it.jsonPrimitive.content.toInt() },
            inventory.opcodes.values.first(),
        )
        assertEquals(
            section.array("second_opcodes").map { it.jsonPrimitive.content.toInt() },
            inventory.opcodes.values.elementAt(1),
        )
        assertEquals(section.str("sha256"), dispatchDigest(inventory))
    }

    test("malformed dispatch rows fail with the recorded message") {
        for (case in coverage.array("dispatch_errors").map { it.jsonObject }) {
            val thrown = assertFailsWith<IllegalArgumentException>(case.str("text")) {
                MethodCoverage.dispatchInventoryOutput(case.str("text"))
            }
            assertEquals(case.obj("result").str("error"), thrown.message, case.str("text"))
        }
    }
}
