package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

private fun jvmTemp(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("full-jvm-consumer")
    try {
        block(root)
    } finally {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}

private fun caseItem(id: String, module: String): JsonObject = buildJsonObject {
    put("id", JsonPrimitive(id))
    put("classname", JsonPrimitive("a.B"))
    put("method", JsonPrimitive("method"))
    put("module", JsonPrimitive(module))
    put(
        "source",
        buildJsonObject {
            put("path", JsonPrimitive("p.kt"))
            put("sha256", JsonPrimitive("a".repeat(64)))
        },
    )
}

/** `test_full_jvm_consumer.py`'s portable cases: identity, tables, reports, and proofs. */
val FullJvmConsumerSuite by testSuite {
    test("unknown lanes are rejected") {
        assertFailsWith<IllegalArgumentException> {
            FullJvmConsumerRules.laneParts("jvm:Java:current:other")
        }
        assertFailsWith<IllegalArgumentException> {
            FullJvmConsumer.prepare(Path.of("/missing"), "a".repeat(40), Path.of("/missing"), "bogus")
        }
    }

    test("all four lanes parse to version and configuration") {
        assertEquals(
            listOf("minimum" to "no-optimize", "minimum" to "default",
                "current" to "no-optimize", "current" to "default"),
            FullJvmConsumerRules.LANES.map { FullJvmConsumerRules.laneParts(it) },
        )
    }

    test("the approved contract shape is 2,526 cases") {
        val cases = buildList {
            for (index in 0 until 2465) add(caseItem("dyn4k-core:a.B#m$index", "dyn4k-core"))
            for (index in 0 until 61) add(caseItem("dyn4k:f.B#m$index", "dyn4k"))
        }
        FullJvmConsumerRules.requireContract(buildJsonObject { put("cases", JsonArray(cases)) })
        assertFailsWith<IllegalArgumentException> {
            FullJvmConsumerRules.requireContract(buildJsonObject { put("cases", JsonArray(emptyList())) })
        }
        assertFailsWith<IllegalArgumentException> {
            FullJvmConsumerRules.requireContract(
                buildJsonObject { put("cases", JsonArray(cases.dropLast(1))) },
            )
        }
    }

    test("compiler flags match the recorded modes") {
        assertEquals(emptyList(), FullJvmConsumerRules.jvmFlags("default"))
        assertEquals(listOf("-Xno-optimize"), FullJvmConsumerRules.jvmFlags("no-optimize"))
        assertFailsWith<IllegalArgumentException> { FullJvmConsumerRules.jvmFlags("optimized") }
    }

    test("input bytes carry the inventory and both case tables") {
        val cases = listOf(
            buildJsonObject {
                put("id", JsonPrimitive("dyn4k-core:b.A#z"))
                put("classname", JsonPrimitive("b.A"))
                put("method", JsonPrimitive("z"))
                put("module", JsonPrimitive("dyn4k-core"))
            },
            buildJsonObject {
                put("id", JsonPrimitive("dyn4k-core:a.B#method"))
                put("classname", JsonPrimitive("a.B"))
                put("method", JsonPrimitive("method"))
                put("module", JsonPrimitive("dyn4k-core"))
            },
            buildJsonObject {
                put("id", JsonPrimitive("dyn4k:f.C#go"))
                put("classname", JsonPrimitive("f.C"))
                put("method", JsonPrimitive("go"))
                put("module", JsonPrimitive("dyn4k"))
            },
        )
        val sources = mapOf("b.kt" to "b".repeat(64), "a.kt" to "a".repeat(64))
        val inputs = FullJvmConsumer.inputBytes(cases, sources, FullJvmConsumer.LANE)
        assertEquals(
            "a.kt\t${"a".repeat(64)}\nb.kt\t${"b".repeat(64)}\n",
            String(inputs.getValue("source-inventory.tsv"), Charsets.UTF_8),
        )
        assertEquals(
            "dyn4k-core:a.B#method\ta.B\tmethod\ndyn4k-core:b.A#z\tb.A\tz\n",
            String(inputs.getValue("core-cases.tsv"), Charsets.UTF_8),
        )
        assertEquals(
            "dyn4k:f.C#go\tf.C\tgo\n",
            String(inputs.getValue("facade-cases.tsv"), Charsets.UTF_8),
        )
        assertTrue(String(inputs.getValue("lane-script"), Charsets.UTF_8).contains("qualification project differs"))
    }

    test("approved identities accept both TestBalloon and JUnit shapes") {
        assertEquals("a.B" to "method", JunitIdentity.normalized("a.B", "method"))
        assertEquals("a.B" to "method", JunitIdentity.normalized("suite_a.B", "method[jvm]"))
        assertEquals("pkg.Suite" to "test", JunitIdentity.normalized("suite_pkg.Suite", "test[linuxX64]"))
        assertEquals("a.B", JunitIdentity.normalizedClass("suite_a.B"))
    }

    test("the normalized report must carry the raw result unchanged") {
        val raw = ("<testsuite tests=\"1\" failures=\"0\" errors=\"0\" skipped=\"0\" time=\"1\">" +
            "<testcase classname=\"a.B\" name=\"method\" time=\"1\"/></testsuite>").toByteArray()
        val normalized = ("<testsuite tests=\"1\" failures=\"0\" errors=\"0\" skipped=\"0\" time=\"1\">" +
            "<testcase classname=\"a.B\" name=\"method\" time=\"1\" id=\"core:a.B#method\"/>" +
            "</testsuite>").toByteArray()
        val selected = mapOf(("a.B" to "method") to "core:a.B#method")
        assertEquals(listOf("core:a.B#method"), FullJvmConsumer.sameReport(raw, normalized, selected))
        assertFailsWith<IllegalArgumentException> {
            FullJvmConsumer.sameReport(
                raw,
                String(normalized, Charsets.UTF_8).replace("core:a.B", "core:x.B").toByteArray(),
                selected,
            )
        }
        assertFailsWith<IllegalArgumentException> {
            FullJvmConsumer.sameReport(
                raw,
                String(normalized, Charsets.UTF_8).replace("time=\"1\"", "time=\"2\"").toByteArray(),
                selected,
            )
        }
    }

    test("both worker launches are proven") {
        jvmTemp { checkout ->
            val runtime = checkout.resolve("bin/java").toString()
            fun launch(id: String, module: String) =
                "Starting process 'Gradle Test Executor $id'. Working directory: " +
                    checkout.resolve("${FullJvmConsumerRules.CONSUMER}/$module") +
                    " Command: $runtime -cp libs " +
                    "worker.org.gradle.process.internal.worker.GradleWorkerMain " +
                    "'Gradle Test Executor $id'"
            val good = "> Task :core:test\n${launch("1", "core")}\n" +
                "> Task :facade:test\n${launch("2", "facade")}\n"
            FullJvmConsumer.testWorkerProof(good, checkout, runtime)
            assertFailsWith<IllegalArgumentException> {
                FullJvmConsumer.testWorkerProof(launch("1", "core"), checkout, runtime)
            }
            assertFailsWith<IllegalArgumentException> {
                FullJvmConsumer.testWorkerProof(good.replace(runtime, "/other/bin/java"), checkout, runtime)
            }
            assertFailsWith<IllegalArgumentException> {
                FullJvmConsumer.testWorkerProof(
                    "${launch("1", "core")}\n${launch("2", "facade")}\n> Task :core:test\n> Task :facade:test\n",
                    checkout,
                    runtime,
                )
            }
        }
    }

    test("the replay tail fails closed naming the Python module") {
        jvmTemp { root ->
            val missing = root.resolve("missing")
            val error = assertFailsWith<IllegalArgumentException> {
                FullJvmConsumer.verify(missing, root, "a".repeat(40), emptyMap())
            }
            assertEquals("full JVM archive is missing or symbolic", error.message)
            val empty = root.resolve("empty")
            Files.createDirectories(empty)
            val identity = assertFailsWith<IllegalArgumentException> {
                FullJvmConsumer.verify(empty, root, "a".repeat(40), emptyMap())
            }
            assertEquals("full JVM archive identity differs", identity.message)
            val digest = assertFailsWith<IllegalArgumentException> {
                FullJvmConsumer.modePublication(empty, "a".repeat(40), "default", emptyMap(), "0".repeat(64))
            }
            assertEquals("independent JVM mode publication digest differs", digest.message)
            val replay = assertFailsWith<IllegalArgumentException> {
                UnportedJvmReplay.replay(empty, "a".repeat(40), "default")
            }
            assertTrue((replay.message ?: "").contains("compiler_modes.py"))
            assertFailsWith<IllegalArgumentException> { FullJvmConsumer.run() }
            assertEquals(1, FullJvmConsumerCli.run(arrayOf("run")))
            assertEquals(1, FullJvmConsumerCli.run(arrayOf("prepare")))
            assertEquals(2, FullJvmConsumerCli.run(arrayOf("bogus")))
            assertEquals(2, FullJvmConsumerCli.run(emptyArray()))
        }
    }
}
