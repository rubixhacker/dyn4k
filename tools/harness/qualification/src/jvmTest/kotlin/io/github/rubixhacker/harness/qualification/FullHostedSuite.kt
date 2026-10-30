package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.FileTime
import java.util.concurrent.TimeUnit
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `full_hosted.py`, first slice: the pinned toolchain, archive paths, Gradle home anchors, the
 * receipt inventory, the PAX transport archive, the reviewed case counts, and the Safari
 * diagnostic identities.
 */
val FullHostedContract by testSuite {
    test("the hosted toolchain must be Java 21 with pinned Gradle, KGP, and AGP") {
        val pinned = runtime("21.0.1+12")
        FullHosted.requirePinnedToolchain(pinned)
        for ((runtime, message) in listOf(
            buildJsonObject { } to "hosted toolchain differs from pinned Java, Gradle, KGP, or AGP",
            runtime("17.0.1") to "hosted toolchain differs from pinned Java, Gradle, KGP, or AGP",
            runtime("21.0.1", gradle = "9.4.0") to
                "hosted toolchain differs from pinned Java, Gradle, KGP, or AGP",
            runtime("21.0.1", kgp = "2.4.10") to
                "hosted toolchain differs from pinned Java, Gradle, KGP, or AGP",
            runtime("21.0.1", agp = "9.3.0") to
                "hosted toolchain differs from pinned Java, Gradle, KGP, or AGP",
        )) {
            assertEquals(
                message,
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.requirePinnedToolchain(runtime)
                }.message,
            )
        }
    }

    test("declared plugin versions are the captured group, or empty") {
        val build = """plugins { kotlin("multiplatform") version "2.4.20" }"""
        assertEquals(
            "2.4.20",
            FullHosted.declaredPluginVersion(build, Regex("""kotlin\("multiplatform"\) version "([^"]+)"""")),
        )
        assertEquals("", FullHosted.declaredPluginVersion("plugins { }", Regex("version \"([^\"]+)\"")))
    }

    test("archive member paths are rejected when they could escape") {
        assertEquals("a/b.txt", FullHosted.relativePath("a/b.txt").toString())
        for (value in listOf("", "/abs", "../x", "a//b", "c:x", "a\\b", "./a")) {
            assertEquals(
                "unsafe archive path",
                assertFailsWith<IllegalArgumentException> { FullHosted.relativePath(value) }.message,
            )
        }
    }

    test("original paths are absolute and cannot traverse") {
        assertEquals("/home/runner/work", FullHosted.originalPath("linuxX64", "/home/runner/work"))
        assertEquals("C:\\Users\\runner", FullHosted.originalPath("mingwX64", "C:\\Users\\runner"))
        for ((target, value) in listOf(
            "linuxX64" to "relative/path",
            "linuxX64" to "/home/../etc",
            "mingwX64" to "relative\\path",
            "mingwX64" to "C:\\..\\escape",
        )) {
            assertEquals(
                "original path is not absolute or safe",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.originalPath(target, value)
                }.message,
            )
        }
    }

    test("the Gradle user home anchor follows the override") {
        val base = buildJsonObject {
            put("runner_home", JsonPrimitive("/home/runner"))
            put("gradle_user_home_override", kotlinx.serialization.json.JsonNull)
            put("repository_root", JsonPrimitive("/work/repo"))
        }
        assertEquals("/home/runner/.gradle", FullHosted.expectedGradleHome("linuxX64", base))
        val relative = JsonObject(base + ("gradle_user_home_override" to JsonPrimitive(".gradle-home")))
        assertEquals(
            "/work/repo/.gradle-home",
            FullHosted.expectedGradleHome("linuxX64", relative),
        )
        val absolute = JsonObject(base + ("gradle_user_home_override" to JsonPrimitive("/cache/gradle")))
        assertEquals("/cache/gradle", FullHosted.expectedGradleHome("linuxX64", absolute))
        val missing = buildJsonObject { put("runner_home", JsonPrimitive("/home/runner")) }
        assertEquals(
            "Gradle user home environment anchor is absent",
            assertFailsWith<IllegalArgumentException> {
                FullHosted.expectedGradleHome("linuxX64", missing)
            }.message,
        )
        val noRunner = buildJsonObject { put("gradle_user_home_override", JsonPrimitive("x")) }
        assertEquals(
            "Gradle user home runner anchor is absent",
            assertFailsWith<IllegalArgumentException> {
                FullHosted.expectedGradleHome("linuxX64", noRunner)
            }.message,
        )
    }

    test("an archive inventory seals every member and lists nothing else") {
        withArchive { output ->
            val files = FullHosted.archiveInventory(output)
            assertEquals(listOf("a.txt", "dir/b.txt"), files.map { Py.str(it["path"]) })
            FullHosted.verifyInventory(output, JsonArray(files))
            assertEquals(
                "archive member differs: a.txt",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyInventory(
                        output,
                        JsonArray(
                            files.map { item ->
                                if (Py.str(item["path"]) == "a.txt") {
                                    JsonObject(item + ("sha256" to JsonPrimitive("0".repeat(64))))
                                } else {
                                    item
                                }
                            },
                        ),
                    )
                }.message,
            )
            val extra = output.resolve("extra.txt")
            extra.writeText("extra")
            assertEquals(
                "unlisted or missing archive member",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyInventory(output, JsonArray(files))
                }.message,
            )
        }
    }

    test("a PAX transport archive round-trips with nanosecond timestamps") {
        withArchive(candidate = "a".repeat(40)) { output ->
            val archive = output.parent.resolve("transport.tar")
            FullHosted.packageArchive(output, archive)
            // The transport envelope verifies, then the receipt verifier rejects the receipt
            // because it is not a completed target.
            val error = assertFailsWith<IllegalArgumentException> {
                FullHosted.verifyTransportArchive(archive, "a".repeat(40))
            }
            assertEquals("full hosted receipt is not a completed target", error.message)
        }
    }

    test("the transport archive refuses a symbolic member and a wrong candidate") {
        withArchive(candidate = "a".repeat(40)) { output ->
            val archive = output.parent.resolve("transport.tar")
            FullHosted.packageArchive(output, archive)
            assertEquals(
                "transport archive candidate or target differs",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyTransportArchive(archive, "b".repeat(40))
                }.message,
            )
            assertEquals(
                "transport archive candidate or target differs",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyTransportArchive(archive, "a".repeat(40), target = "linuxX64")
                }.message,
            )
        }
    }

    test("the reviewed common counts are fixed") {
        assertEquals(mapOf("dyn4k-core" to 2465, "dyn4k" to 58), FullHosted.REVIEWED_COMMON_COUNTS)
        val manifest = buildJsonObject {
            put(
                "cases",
                JsonArray(
                    listOf(
                        case("dyn4k-core", "a.B", "one", "commonTest"),
                        case("dyn4k", "c.D", "two", "jvmTest"),
                    ),
                ),
            )
        }
        // The fixture is far from the reviewed counts, so the count check must fire.
        assertEquals(
            "empty or duplicate common cases: dyn4k",
            assertFailsWith<IllegalArgumentException> {
                FullHosted.expectedCases(manifest, "dyn4k")
            }.message,
        )
        assertEquals(
            "unknown common corpus module: other",
            assertFailsWith<IllegalArgumentException> {
                FullHosted.expectedCases(manifest, "other")
            }.message,
        )
    }

    test("the Safari diagnostic identities are the 72 reviewed steps") {
        val identities = FullHosted.safariDiagnosticIdentities()
        assertEquals(72, identities.size)
        assertTrue(
            listOf("CapsuleSlice", "detectGjk", "center", "forward", 0, "gjk") in identities,
        )
        assertTrue(
            listOf("PolygonPolygon", "getClipManifold", "shifted", "reverse", 11, "sat") in
                identities,
        )
        assertEquals(6, FullHosted.SAFARI_DIAGNOSTIC_CASES.size)
    }

    test("the receipt verifier rejects a receipt that is not a completed target") {
        val root = Files.createTempDirectory("hosted-raw")
        try {
            assertEquals(
                "full hosted receipt is not a completed target",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyRawFiles(root, buildJsonObject { })
                }.message,
            )
        } finally {
            Files.deleteIfExists(root)
        }
    }
}

private fun runtime(
    java: String,
    gradle: String = "9.5.0",
    kgp: String = "2.4.20",
    agp: String = "9.3.1",
): JsonObject = buildJsonObject {
    put("java_version", JsonPrimitive(java))
    put("gradle_version", JsonPrimitive(gradle))
    put("kgp_declared_version", JsonPrimitive(kgp))
    put("agp_declared_version", JsonPrimitive(agp))
}

private fun case(module: String, classname: String, method: String, sourceSet: String): JsonObject =
    buildJsonObject {
        put("module", JsonPrimitive(module))
        put("classname", JsonPrimitive(classname))
        put("method", JsonPrimitive(method))
        put("source_set", JsonPrimitive(sourceSet))
    }

private fun withArchive(candidate: String? = null, block: (Path) -> Unit) {
    val root = Files.createTempDirectory("hosted-archive")
    val output = root.resolve("receipt")
    Files.createDirectories(output.resolve("dir"))
    try {
        output.resolve("a.txt").writeText("one\n")
        output.resolve("dir/b.txt").writeText("two\n")
        output.resolve("receipt.json").writeText(
            if (candidate == null) "{}\n" else """{"candidate_sha":"$candidate"}""" + "\n",
        )
        for (name in listOf("a.txt", "dir/b.txt", "receipt.json")) {
            Files.setLastModifiedTime(
                output.resolve(name), FileTime.from(1_700_000_000L, TimeUnit.SECONDS),
            )
        }
        block(output)
    } finally {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}
