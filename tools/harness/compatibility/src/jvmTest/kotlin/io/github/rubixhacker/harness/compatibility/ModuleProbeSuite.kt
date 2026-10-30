package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.createDirectories
import kotlin.io.path.writeText
import kotlin.test.assertEquals

private val probeVectors = Vectors.moduleProbe

/**
 * `module_probe.descriptor`, driven against a synthetic modular JAR built from the recorded vector.
 *
 * The recorded descriptor output never names the JAR path, so the vector replays unchanged wherever
 * it runs. `provider_check` and `probe` are exercised by the recorded `passed` flags in their own
 * reports; the pinned named-module consumer needs the staged `org.dyn4j` JAR.
 */
val ModuleProbeContract by testSuite {
    test("module descriptor matches the recorded output") {
        val directory = Files.createTempDirectory("dyn4k-module-probe-")
        try {
            val packages = directory.resolve("packages")
            for (name in probeVectors.array("placeholder_packages").map { it.jsonPrimitive.content }) {
                val target = packages.resolve(name.replace('.', '/'))
                target.createDirectories()
                target.resolve("Placeholder.java").writeText(
                    "package $name; public final class Placeholder {}\n",
                    StandardCharsets.UTF_8,
                )
            }
            val module = directory.resolve("module-info.java")
            module.writeText(probeVectors.str("module_source"), StandardCharsets.UTF_8)
            val classes = directory.resolve("classes")
            classes.createDirectories()
            val sources = Files.walk(packages).use { stream ->
                stream.filter { it.toString().endsWith(".java") }.map { it.toString() }.toList()
            }
            Processes.run(
                listOf("javac", "--release", "9", "-d", classes.toString(), module.toString()) + sources,
                check = true,
            )
            val jar = directory.resolve("dyn4j.jar")
            Processes.run(
                listOf("jar", "--create", "--file", jar.toString(), "-C", classes.toString(), "."),
                check = true,
            )
            assertEquals(
                probeVectors.obj("descriptor"),
                ModuleProbe.descriptor(jar.toString()),
            )
        } finally {
            deleteTree(directory)
        }
    }

    test("provider check counts org.dyn4j entries and their hashes") {
        val directory = Files.createTempDirectory("dyn4k-provider-check-")
        try {
            val classes = directory.resolve("classes")
            classes.createDirectories()
            val jar = directory.resolve("empty.jar")
            Processes.run(
                listOf("jar", "--create", "--file", jar.toString(), "-C", classes.toString(), "."),
                check = true,
            )
            val missing = ModuleProbe.providerCheck(jar.toString(), emptyList(), null)
            assertEquals("expected org.dyn4j provider missing", missing.textOrNull("reason"))
            assertEquals("false", missing.textOrNull("passed"))
            assertEquals(
                "expected org.dyn4j provider missing",
                ModuleProbe.providerCheck(jar.toString(), emptyList(), "a".repeat(64))
                    .textOrNull("reason"),
            )
        } finally {
            deleteTree(directory)
        }
    }
}
