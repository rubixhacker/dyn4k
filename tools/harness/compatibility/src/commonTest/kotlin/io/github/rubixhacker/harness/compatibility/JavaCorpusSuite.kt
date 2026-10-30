package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals

private val corpus = Vectors.javaCorpus

private fun identities(): List<Pair<String, String>> =
    corpus.array("identities").map {
        it.jsonArray[0].jsonPrimitive.content to it.jsonArray[1].jsonPrimitive.content
    }

/**
 * `java_corpus.normalized_cases`, the collapse of repeated parameterised runs onto one case
 * identity per parameter. `read_xml` supplies these identities from JUnit XML in the Python module;
 * the XML reader itself needs an XML parser and stays with the unported host half.
 */
val JavaCorpusContract by testSuite {
    test("parameterized cases collapse to the recorded identities") {
        val observed = JavaCorpus.normalizedCases(identities())
        val recorded = corpus.array("normalized").map {
            Triple(
                it.jsonArray[0].jsonPrimitive.content,
                it.jsonArray[1].jsonPrimitive.content,
                it.jsonArray[2].jsonPrimitive.content.toInt(),
            )
        }
        assertEquals(recorded.size, observed.size)
        assertEquals(
            recorded.associate { (owner, name, count) -> (owner to name) to count },
            observed,
        )
        assertEquals(
            corpus.str("normalized_sha256"),
            Sha256.of(
                CanonicalJson.render(
                    JsonArray(
                        observed.entries.sortedWith(
                            Comparator { left, right ->
                                val byOwner = CanonicalJson.compareCodePoints(
                                    left.key.first,
                                    right.key.first,
                                )
                                if (byOwner != 0) {
                                    byOwner
                                } else {
                                    CanonicalJson.compareCodePoints(left.key.second, right.key.second)
                                }
                            },
                        )
                            .map { (key, count) ->
                                JsonArray(
                                    listOf(
                                        JsonPrimitive(key.first),
                                        JsonPrimitive(key.second),
                                        JsonPrimitive(count),
                                    ),
                                )
                            },
                    ),
                ),
            ),
        )
        assertEquals(
            mapOf(
                "org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest" to 25,
                "org.dyn4j.collision.broadphase.CollisionItemBroadphaseTest" to 29,
            ),
            JavaCorpus.PARAMETER_CLASSES,
        )
        assertEquals(
            """([^\[]+)\[([^@\]]+)@([0-9a-fA-F]+)\]""",
            JavaCorpus.PARAMETER_PATTERN.pattern,
        )
    }

    test("malformed and incomplete case inventories are rejected") {
        for (name in listOf("malformed", "bad_pattern", "short")) {
            val case = corpus.obj(name)
            val mutation = case.obj("mutation")
            val changed = when (mutation.str("kind")) {
                "replace-first-name" -> {
                    val original = identities()
                    listOf(original.first().first to mutation.str("name")) + original.drop(1)
                }
                "drop-last" -> identities().dropLast(1)
                else -> error("unknown recorded mutation: ${mutation.str("kind")}")
            }
            assertRecordedOutcome(case.obj("result")) {
                JavaCorpus.normalizedCases(changed)
            }
        }
    }
}
