package io.github.rubixhacker.harness.android

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Path
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * `tools/android-runtime/test_provenance.py`.
 *
 * The Android app compiles copies of the shared JVM consumer sources. Only one pinned adaptation is
 * allowed, and every copy must map back to the exact original it came from.
 */
val GeneratedConsumerProvenanceContract by testSuite {
    test("android copy accepts only pinned version table adaptation") {
        val source = "if (\"1.8\".equals(version)) return null;\n".encodeToByteArray()
        val expected = (
            "if (\"1.8\".equals(version)) return null;\n" +
                "        if (\"0.9\".equals(version)) return " +
                "\"Attempt to invoke virtual method 'java.lang.String " +
                "java.lang.Class.getName()' on a null object reference\";\n"
            ).encodeToByteArray()
        assertContentEquals(
            expected,
            PrepareContract.androidConsumerSource("CollisionModelConsumer", source),
        )
        assertContentEquals(source, PrepareContract.androidConsumerSource("GeometryConsumer", source))
        for (invalid in listOf(
            "class CollisionModelConsumer {}\n".encodeToByteArray(),
            source + source,
        )) {
            val failure = assertFailsWith<IllegalArgumentException> {
                PrepareContract.androidConsumerSource("CollisionModelConsumer", invalid)
            }
            assertTrue(failure.message!!.contains("Android consumer version table"))
        }
    }

    test("rejects changed generated copy") {
        withTempDirectory { root ->
            val originals = linkedMapOf<String, JsonPrimitive>()
            val generated = linkedMapOf<String, JsonObject>()
            for (name in PrepareContract.CONSUMERS) {
                val sourceRelative = "dyn4k-core/src/jvmConsumer/java/$name.java"
                val copyRelative = "consumers/android-runtime/app/build/generated/consumer-java/$name.java"
                val source = writeFile(
                    root,
                    sourceRelative,
                    "class ${Path.of("$name.java").fileName.toString().removeSuffix(".java")} {}\n" +
                        if (name == "CollisionModelConsumer") {
                            "if (\"1.8\".equals(version)) return null;\n"
                        } else {
                            ""
                        },
                )
                val copy = writeBytes(
                    root,
                    copyRelative,
                    PrepareContract.androidConsumerSource(
                        Path.of("$name.java").fileName.toString().removeSuffix(".java"),
                        source.toFile().readBytes(),
                    ),
                )
                originals[sourceRelative] = JsonPrimitive(sha256(source))
                generated[copyRelative] = buildJsonObject {
                    put("source", JsonPrimitive(sourceRelative))
                    put("sha256", JsonPrimitive(sha256(copy)))
                }
            }
            val manifest = buildJsonObject {
                put("consumer_sources", JsonObject(originals))
                put("generated_consumer_sources", JsonObject(generated))
            }
            assertEquals(generated, AndroidFiles.verifyConsumerSources(root, manifest))
            val changed = root.resolve(generated.keys.first())
            changed.toFile().writeBytes(changed.toFile().readBytes() + "\n".encodeToByteArray())
            val failure = assertFailsWith<IllegalArgumentException> {
                AndroidFiles.verifyConsumerSources(root, manifest)
            }
            assertTrue(failure.message!!.contains("generated consumer source changed"))
        }
    }

    test("rejects unlisted generated java source") {
        withTempDirectory { root ->
            writeFile(
                root,
                "consumers/android-runtime/app/build/generated/consumer-java/Extra.java",
                "class Extra {}\n",
            )
            val manifest = buildJsonObject {
                put("consumer_sources", buildJsonObject { })
                put("generated_consumer_sources", buildJsonObject { })
            }
            val failure = assertFailsWith<IllegalArgumentException> {
                AndroidFiles.verifyConsumerSources(root, manifest)
            }
            assertTrue(failure.message!!.contains("generated consumer source set"))
        }
    }

    test("rejects generated copy mapped to another original") {
        withTempDirectory { root ->
            val originals = linkedMapOf<String, JsonPrimitive>()
            val generated = linkedMapOf<String, JsonObject>()
            val same = "if (\"1.8\".equals(version)) return null;\n".encodeToByteArray()
            val digest = sha256(same)
            for (name in PrepareContract.CONSUMERS) {
                val simple = Path.of("$name.java").fileName.toString().removeSuffix(".java")
                val sourceRelative = "dyn4k-core/src/jvmConsumer/java/$name.java"
                val copyRelative = "consumers/android-runtime/app/build/generated/consumer-java/$name.java"
                writeBytes(root, sourceRelative, same)
                val copy = writeBytes(
                    root,
                    copyRelative,
                    PrepareContract.androidConsumerSource(simple, same),
                )
                originals[sourceRelative] = JsonPrimitive(digest)
                generated[copyRelative] = buildJsonObject {
                    put("source", JsonPrimitive(sourceRelative))
                    put("sha256", JsonPrimitive(sha256(copy)))
                }
            }
            val first = generated.keys.elementAt(0)
            val second = generated.keys.elementAt(1)
            val forged = generated.toMutableMap()
            forged[first] = buildJsonObject {
                put("source", generated.getValue(second).getValue("source"))
                put("sha256", generated.getValue(first).getValue("sha256"))
            }
            val manifest = buildJsonObject {
                put("consumer_sources", JsonObject(originals))
                put("generated_consumer_sources", JsonObject(forged))
            }
            val failure = assertFailsWith<IllegalArgumentException> {
                AndroidFiles.verifyConsumerSources(root, manifest)
            }
            assertTrue(failure.message!!.contains("mapping"))
        }
    }
}
