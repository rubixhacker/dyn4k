package io.github.rubixhacker.harness.android

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

private const val FULL_CASE = "dyn4k-core:org.dyn4j.CoreTest#works"
private const val FULL_CONSUMER =
    "external-kotlin:io.github.rubixhacker.dyn4k.full.FullKotlinJourney#run"

private val FULL_RAW = listOf(
    "INSTRUMENTATION_STATUS: class=io.github.rubixhacker.dyn4k.full.FullJourneyTest",
    "INSTRUMENTATION_STATUS: test=allInstalledCases",
    "INSTRUMENTATION_STATUS: numtests=1",
    "INSTRUMENTATION_STATUS_CODE: 1",
    "INSTRUMENTATION_STATUS: dyn4k_case=$FULL_CASE",
    "INSTRUMENTATION_STATUS: dyn4k_status=PASSED",
    "INSTRUMENTATION_STATUS_CODE: 0",
    "INSTRUMENTATION_STATUS: dyn4k_case=$FULL_CONSUMER",
    "INSTRUMENTATION_STATUS: dyn4k_status=PASSED",
    "INSTRUMENTATION_STATUS_CODE: 0",
    "INSTRUMENTATION_STATUS: class=io.github.rubixhacker.dyn4k.full.FullJourneyTest",
    "INSTRUMENTATION_STATUS: test=allInstalledCases",
    "INSTRUMENTATION_STATUS: numtests=1",
    "INSTRUMENTATION_STATUS_CODE: 0",
    "INSTRUMENTATION_RESULT: stream=",
    "OK (1 test)",
    "INSTRUMENTATION_CODE: -1",
    "",
).joinToString("\n")

private const val FULL_PACKAGE = "io.github.rubixhacker.dyn4k.full"

/** `complete_graph` from the Python suite, with provider paths supplied per coordinate. */
private fun completeGraph(providers: Map<String, String>): String {
    val rows = mutableListOf("DYN4K_BUILD_JDK javaHome=/tmp/dyn4k-tools/jdk21 javaVersion=21 gradleVersion=9.5.0")
    for (variant in listOf("debug", "release")) {
        rows += "DYN4K_GRAPH_BEGIN $variant"
        rows += RunFullContract.GRAPH_COMPONENTS.sorted().map { "DYN4K_GRAPH_COMPONENT $variant $it" }
        rows += RunFullContract.GRAPH_EDGES.sorted().map { "DYN4K_GRAPH_EDGE $variant $it" }
        rows += RunFullContract.GRAPH_ARTIFACTS.sorted().map {
            "DYN4K_GRAPH_ARTIFACT $variant $it ${providers[it] ?: "/unused.jar"}"
        }
        rows += "DYN4K_GRAPH_END $variant 11 15 9"
    }
    return rows.joinToString("\n") + "\n"
}

/**
 * `tools/android-runtime/test_full_evidence.py`.
 *
 * The full installed route combines the umbrella instrumentation transcript with the runtime identity,
 * the resolved provider graph, the R8 transformation, and the build identity. Each of those is a
 * separate way for a receipt to be wrong.
 */
val FullInstalledEvidenceContract by testSuite {
    test("current java records version after JAVA_TOOL_OPTIONS notice") {
        val stderr = "Picked up JAVA_TOOL_OPTIONS: -Djava.io.tmpdir=/home/task/tmp\n" +
            "openjdk version \"21.0.12.1\" 2025-07-15 LTS\n"
        val host = object : BuildHost {
            override fun environment(name: String): String =
                if (name == "JAVA_HOME") "/tmp/dyn4k-tools/jdk21" else ""

            override fun isFile(path: String): Boolean = true

            override fun javaVersion(binary: String): String = stderr
        }
        assertEquals(
            "openjdk version \"21.0.12.1\" 2025-07-15 LTS",
            BuildIdentity.currentJava(host).javaVersion,
        )
    }

    test("provider graph rejects wrong coordinates second provider and missing graph") {
        withTempDirectory { root ->
            val providers = linkedMapOf<String, String>()
            val staged = linkedMapOf<String, JsonObject>()
            for (name in listOf("dyn4k-core-android", "dyn4k-android")) {
                val aar = writeBytes(root, "$name.aar", name.encodeToByteArray())
                staged[name] = buildJsonObject { put("sha256", JsonPrimitive(sha256(aar))) }
                providers["io.github.rubixhacker:$name:0.1.0-alpha.1"] = posix(aar)
            }
            val prepared = buildJsonObject { put("staged", JsonObject(staged)) }
            val graph = completeGraph(providers)
            assertEquals(
                setOf("debug", "release"),
                FullHost.validateProviderArtifacts(graph, prepared).keys,
            )
            for (bad in listOf(
                graph.replace(
                    "io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1",
                    "example.invalid:dyn4k-android:9.9.9",
                ),
                graph.replace("DYN4K_GRAPH_COMPONENT debug project:full\n", ""),
                graph.replace("DYN4K_GRAPH_EDGE release project:full junit:junit:4.13.2\n", ""),
                graph.replace("DYN4K_GRAPH_BEGIN release\n", ""),
                graph + "DYN4K_GRAPH_ARTIFACT debug org.dyn4j:dyn4j:6.0.0 /unused.jar\n",
            )) {
                assertFailsWith<IllegalArgumentException> {
                    FullHost.validateProviderArtifacts(bad, prepared)
                }
            }
        }
    }

    test("build jdk rejects wrong home version and missing daemon identity") {
        val good = "Starting process 'Gradle build daemon'. Working directory: " +
            "/tmp/gradle/daemon/9.5.0 Command: /tmp/dyn4k-tools/jdk21/bin/java " +
            "org.gradle.launcher.daemon.bootstrap.GradleDaemon 9.5.0\n" +
            "DYN4K_BUILD_JDK javaHome=/tmp/dyn4k-tools/jdk21 javaVersion=21 " +
            "gradleVersion=9.5.0\nBUILD SUCCESSFUL\n"
        BuildIdentity.validateBuildJdk(good)
        for (bad in listOf(
            good.replace("/tmp/dyn4k-tools/jdk21", "/tmp/jdk25"),
            good.replace("javaVersion=21", "javaVersion=25"),
            good.replace("gradleVersion=9.5.0", "gradleVersion=9.4"),
            good.replace("DYN4K_BUILD_JDK", "MISSING_BUILD_JDK"),
        )) {
            assertFailsWith<IllegalArgumentException> { BuildIdentity.validateBuildJdk(bad) }
        }
        withTempDirectory { root ->
            val daemon = root.resolve("daemon-123.out.log")
            val build = root.resolve("build.log")
            build.toFile().writeText(good + "The daemon log file: $daemon\n")
            daemon.toFile().writeText("DefaultDaemonContext[javaHome=/tmp/jdk25,javaVersion=25]\n")
            val failure = assertFailsWith<IllegalArgumentException> {
                BuildIdentityFiles.buildLogIdentity(build, requireMarker = true)
            }
            assertTrue(failure.message!!.contains("raw Gradle daemon"))
            daemon.toFile().writeText(
                "DefaultDaemonContext[javaHome=/tmp/dyn4k-tools/jdk21," +
                    "javaVersion=21,daemonRegistryDir=/tmp]\n",
            )
            BuildIdentityFiles.buildLogIdentity(build, requireMarker = true)
        }
    }

    test("installed process log requires matching instrumentation pid") {
        val pkg = FULL_PACKAGE
        val log = "I ActivityManager: Start proc 4804:$pkg/u0a241 for added application $pkg\n" +
            "I ActivityManager: Killing 4804:$pkg/u0a241 (adj 0): stop $pkg due to finished inst\n"
        assertEquals("4804", FullEvidence.validateFullProcessLog(log, pkg))
        for (bad in listOf(
            log.replaceFirst("4804:", "4805:"),
            log.replace("finished inst", "crash"),
            log.replace("Start proc", "Started proc"),
            log + log,
        )) {
            val failure = assertFailsWith<IllegalArgumentException> {
                FullEvidence.validateFullProcessLog(bad, pkg)
            }
            assertTrue(failure.message!!.contains("instrumentation process"))
        }
    }

    test("api21 process log requires matching started and finished pid") {
        val pkg = FULL_PACKAGE
        val log = "I/ActivityManager( 1485): Start proc $pkg for activity " +
            "$pkg/.FullActivity: pid=3334 uid=10058 gids={50058} abi=x86\n" +
            "I/ActivityManager( 1485): Killing 3334:$pkg/u0a58 (adj 0): stop $pkg\n" +
            "I/ActivityManager( 1485): Start proc $pkg for added application " +
            "$pkg: pid=3378 uid=10058 gids={50058, 9997} abi=x86\n" +
            "I/ActivityManager( 1485): Force stopping $pkg appid=10058 user=0: finished inst\n" +
            "I/ActivityManager( 1485): Killing 3378:$pkg/u0a58 (adj 0): stop $pkg\n"
        val added = "I/ActivityManager( 1485): Start proc $pkg for added application " +
            "$pkg: pid=3378 uid=10058 gids={50058, 9997} abi=x86\n"
        val service = "I/ActivityManager( 1485): Start proc $pkg for service " +
            "$pkg/.SyncService: pid=3379 uid=10058 gids={50058} abi=arm64-v8a\n"
        val otherActivity = "I/ActivityManager( 1485): Start proc $pkg for activity " +
            "$pkg/.OtherActivity: pid=3379 uid=10058 gids={50058} abi=arm64-v8a\n"
        val external = "I/ActivityManager( 1485): Start proc $pkg.other for service " +
            "$pkg.other/.SyncService: pid=3379 uid=10059 gids={50059} abi=arm64-v8a\n"
        assertEquals("3378", RunFullContract.validateApi21ProcessLog(log, pkg, "x86", "3334"))
        assertEquals(
            "3378",
            RunFullContract.validateApi21ProcessLog(
                log.replace(added, added + external),
                pkg,
                "x86",
                "3334",
            ),
        )
        assertFailsWith<IllegalArgumentException> {
            RunFullContract.validateApi21ProcessLog(log, pkg, "x86", "not-a-pid")
        }
        for (bad in listOf(
            log.replace("pid=3378", "pid=3379"),
            log.replace("finished inst", "crash"),
            log.replace("appid=10058 user=0: finished inst", "appid=10059 user=0: finished inst"),
            log.replace("abi=x86\n", "abi=arm64-v8a\n"),
            log.replace("pid=3334", "pid=3335"),
            log.replace("Killing 3334:$pkg", "Killing 3335:$pkg"),
            log.replace(added, ""),
            log.replace(added, added + added),
            log.replace(added, added.replace("abi=x86", "abi=arm64-v8a") + added),
            log.replace(added, added.replace("pid=3378", "pid=3379") + added),
            log + "I/ActivityManager( 1485): Killing 9999:$pkg/u0a58 (adj 0): crash $pkg\n",
            log + log,
        )) {
            val failure = assertFailsWith<IllegalArgumentException>(bad.takeLast(100)) {
                RunFullContract.validateApi21ProcessLog(bad, pkg, "x86", "3334")
            }
            assertTrue(failure.message!!.contains("instrumentation process"))
        }
        for (extra in listOf(
            service,
            service.replace("pid=3379", "pid=3378").replace("abi=arm64-v8a", "abi=x86"),
            otherActivity,
        )) {
            val failure = assertFailsWith<IllegalArgumentException> {
                RunFullContract.validateApi21ProcessLog(log.replace(added, added + extra), pkg, "x86", "3334")
            }
            assertTrue(failure.message!!.contains("instrumentation process"))
        }
    }

    test("api21 process list requires one exact application pid") {
        val pkg = FULL_PACKAGE
        val header = "USER PID PPID VSIZE RSS WCHAN PC NAME\n"
        val row = "u0_a58 3334 123 540000 32000 ffffffff 00000000 $pkg\n"
        val unrelated = "u0_a59 1111 123 540000 32000 ffffffff 00000000 other.app\n"
        assertEquals("3334", RunFullContract.api21ProcessPid(header + unrelated + row, pkg))
        assertNull(RunFullContract.api21ProcessPid(header + unrelated, pkg, required = false))
        for (bad in listOf(
            "/system/bin/sh: pidof: not found\n",
            header + unrelated,
            header + row + row,
            header + row.replace("3334", "not-a-pid"),
        )) {
            val failure = assertFailsWith<IllegalArgumentException> {
                RunFullContract.api21ProcessPid(bad, pkg)
            }
            assertTrue(failure.message!!.contains("API 21 app process"))
        }
    }

    test("accepts exact case id set") {
        val result = FullEvidence.validateFullInstalled(FULL_RAW, setOf(FULL_CASE, FULL_CONSUMER), 0)
        assertEquals(2, result.portable.passed)
    }

    test("rejects missing extra duplicate skip failure and raw tampering") {
        val variants = listOf(
            FULL_RAW.replace(
                "INSTRUMENTATION_STATUS: dyn4k_case=$FULL_CASE\n" +
                    "INSTRUMENTATION_STATUS: dyn4k_status=PASSED\n" +
                    "INSTRUMENTATION_STATUS_CODE: 0\n",
                "",
            ),
            FULL_RAW.replace("dyn4k_case=$FULL_CASE", "dyn4k_case=forged:Case#works"),
            FULL_RAW.replaceFirst("dyn4k_status=PASSED", "dyn4k_status=SKIPPED"),
            FULL_RAW.replaceFirst("dyn4k_status=PASSED", "dyn4k_status=FAILED"),
            FULL_RAW.replace("OK (1 test)", "OK (2 tests)"),
            FULL_RAW.replace("INSTRUMENTATION_CODE: -1", "INSTRUMENTATION_CODE: 0"),
        )
        for (raw in variants) {
            assertFailsWith<IllegalArgumentException>(raw.takeLast(80)) {
                FullEvidence.validateFullInstalled(raw, setOf(FULL_CASE, FULL_CONSUMER), 0)
            }
        }
        val duplicate = FULL_RAW.replace(
            "INSTRUMENTATION_STATUS: dyn4k_case=$FULL_CONSUMER",
            "INSTRUMENTATION_STATUS: dyn4k_case=$FULL_CASE",
        )
        assertFailsWith<IllegalArgumentException> {
            FullEvidence.validateFullInstalled(duplicate, setOf(FULL_CASE, FULL_CONSUMER), 0)
        }
    }

    test("rejects broad keep or unchanged engine dex") {
        val rules = "-keep class io.github.rubixhacker.dyn4k.full.FullActivity { *; }\n" +
            "-keepclassmembers class org.dyn4j.geometry.Matrix22 " +
            "{ public double normMax(); }\n"
        val mapping = "org.dyn4j.geometry.Vector2 -> a:\norg.dyn4j.dynamics.Body -> b:\n"
        val usage = "org.dyn4j.geometry.Unused\n"
        val debug = setOf(
            "Lorg/dyn4j/geometry/Vector2;", "Lorg/dyn4j/dynamics/Body;", "Lc;",
        )
        val release = setOf("La;", "Lb;")
        FullEvidence.validateFullR8(rules, mapping, usage, debug, release, minimumTransformed = 2)
        val failure = assertFailsWith<IllegalArgumentException> {
            FullEvidence.validateFullR8(
                rules + "-keep class org.dyn4j.** { *; }\n",
                mapping,
                usage,
                debug,
                release,
                minimumTransformed = 2,
            )
        }
        assertTrue(failure.message!!.contains("broad keep"))
        assertFailsWith<IllegalArgumentException> {
            FullEvidence.validateFullR8(rules, mapping, usage, debug, debug, minimumTransformed = 2)
        }
        val cases = listOf(
            Triple(rules + "-keep class org.dyn4j.geometry.Vector2 { *; }\n", mapping, usage),
            Triple(rules, mapping.replace("org.dyn4j.dynamics.Body -> b:\n", ""), usage),
            Triple(rules, mapping, ""),
        )
        for ((badRules, badMapping, badUsage) in cases) {
            assertFailsWith<IllegalArgumentException>(badRules.takeLast(80)) {
                FullEvidence.validateFullR8(
                    badRules,
                    badMapping,
                    badUsage,
                    debug,
                    setOf("La;"),
                    minimumTransformed = 2,
                )
            }
        }
    }

    test("targeted x86 member keep still requires engine transformation") {
        val matrix = "org.dyn4j.coverage.UpstreamMatrix22CoverageTest"
        val rules = "-keep,allowoptimization class $matrix { *; }\n" +
            "-keepclassmembers class org.dyn4j.geometry.Matrix22 " +
            "{ public double normMax(); }\n"
        val mapping = "org.dyn4j.geometry.Vector2 -> a:\norg.dyn4j.dynamics.Body -> b:\n"
        val usage = "org.dyn4j.geometry.Unused\n"
        val debug = setOf(
            "Lorg/dyn4j/geometry/Vector2;", "Lorg/dyn4j/dynamics/Body;", "Lc;",
        )
        val release = setOf("La;", "Lb;")
        assertEquals(
            2,
            FullEvidence.validateFullR8(
                rules, mapping, usage, debug, release, setOf(matrix), minimumTransformed = 2,
            ).transformedEngineClasses.size,
        )
        val withoutMemberRule = rules.replace(
            "-keepclassmembers class org.dyn4j.geometry.Matrix22 " +
                "{ public double normMax(); }\n",
            "",
        )
        val failure = assertFailsWith<IllegalArgumentException> {
            FullEvidence.validateFullR8(
                withoutMemberRule, mapping, usage, debug, release, setOf(matrix),
                minimumTransformed = 2,
            )
        }
        assertTrue(failure.message!!.contains("missing Matrix22 member keep"))
        val cases = listOf(
            rules + "-keep class org.dyn4j.** { *; }\n" to release,
            rules.replace("normMax", "norm*") to release,
            rules + "-keepclassmembers class org.dyn4j.geometry.Matrix22 " +
                "{ public double normMax(); }\n" to release,
            rules + "-keepclassmembers class org.dyn4j.geometry.Matrix22 " +
                "{ public double normInfinity(); }\n" to release,
            rules to debug,
        )
        for ((badRules, badRelease) in cases) {
            assertFailsWith<IllegalArgumentException> {
                FullEvidence.validateFullR8(
                    badRules, mapping, usage, debug, badRelease, setOf(matrix),
                    minimumTransformed = 2,
                )
            }
        }
    }

    test("rejects wrong resolved aar apk and runtime") {
        withTempDirectory { root ->
            val aar = writeBytes(root, "dyn4k-core-android.aar", "staged".encodeToByteArray())
            val facade = writeBytes(root, "dyn4k-android.aar", "facade".encodeToByteArray())
            val prepared = buildJsonObject {
                put(
                    "staged",
                    buildJsonObject {
                        put("dyn4k-core-android", buildJsonObject { put("sha256", JsonPrimitive(sha256(aar))) })
                        put("dyn4k-android", buildJsonObject { put("sha256", JsonPrimitive(sha256(facade))) })
                    },
                )
            }
            val graph = completeGraph(
                mapOf(
                    "io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1" to posix(aar),
                    "io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1" to posix(facade),
                ),
            )
            FullHost.validateProviderArtifacts(graph, prepared)
            aar.toFile().writeBytes("wrong".encodeToByteArray())
            val failure = assertFailsWith<IllegalArgumentException> {
                FullHost.validateProviderArtifacts(graph, prepared)
            }
            assertTrue(failure.message!!.contains("wrong resolved staged AAR"))

            val apk = writeBytes(root, "app.apk", "exact".encodeToByteArray())
            val manifest = root.resolve("prepared.json")
            val jdk = buildJsonObject {
                put("java_home", JsonPrimitive("/tmp/dyn4k-tools/jdk21"))
                put("java_version", JsonPrimitive("21.0.12.1"))
                put("gradle_version", JsonPrimitive("9.5.0"))
            }
            manifest.toFile().writeText("{\"build_jdk\": $jdk}")
            val buildLog = "Starting process 'Gradle build daemon'. Working directory: " +
                "/tmp/gradle/daemon/9.5.0 Command: /tmp/dyn4k-tools/jdk21/bin/java " +
                "org.gradle.launcher.daemon.bootstrap.GradleDaemon 9.5.0\nBUILD SUCCESSFUL\n"
            val logs = buildJsonObject {
                var index = 100
                for (name in listOf("debug", "release", "provider")) {
                    val path = root.resolve("$name.log")
                    val daemon = root.resolve("daemon-$index.out.log")
                    index += 1
                    daemon.toFile().writeText(
                        "DefaultDaemonContext[javaHome=/tmp/dyn4k-tools/jdk21," +
                            "javaVersion=21,daemonRegistryDir=/tmp]\n",
                    )
                    path.toFile().writeText(
                        buildLog + "The daemon log file: $daemon\n" +
                            if (name == "provider") {
                                "DYN4K_BUILD_JDK javaHome=/tmp/dyn4k-tools/jdk21 " +
                                    "javaVersion=21 gradleVersion=9.5.0\n"
                            } else {
                                ""
                            },
                    )
                    put(
                        name,
                        BuildIdentityFiles.buildLogIdentity(path, requireMarker = name == "provider")
                            .toJson(),
                    )
                }
            }
            val receipt = root.resolve("receipt.json")
            receipt.toFile().writeText(
                "{\"candidate_commit\": \"candidate\", \"prepared_sha256\": \"${sha256(manifest)}\", " +
                    "\"build_jdk\": $jdk, \"build_logs\": $logs, " +
                    "\"artifacts\": {\"app-debug-apk\": {\"path\": \"${posix(apk)}\", " +
                    "\"sha256\": \"${sha256(apk)}\"}}}",
            )
            val providerLog = root.resolve("provider.log")
            val seams = { app: Path, provider: Path -> mapOf("app-debug-apk" to apk) }
            FullHost.verifyBuildReceipt(
                root,
                manifest,
                providerLog,
                receipt,
                currentJava = { BuildJdk("/tmp/dyn4k-tools/jdk21", "21.0.12.1", "9.5.0") },
                command = { _, _, _ -> "candidate" },
                buildArtifacts = seams,
            )
            apk.toFile().writeBytes("forged".encodeToByteArray())
            val stale = assertFailsWith<IllegalArgumentException> {
                FullHost.verifyBuildReceipt(
                    root,
                    manifest,
                    providerLog,
                    receipt,
                    currentJava = { BuildJdk("/tmp/dyn4k-tools/jdk21", "21.0.12.1", "9.5.0") },
                    command = { _, _, _ -> "candidate" },
                    buildArtifacts = seams,
                )
            }
            assertTrue(stale.message!!.contains("wrong APK"))

            val identity = linkedMapOf(
                "ro.build.fingerprint" to AndroidCorpus.FINGERPRINTS.getValue("37"),
                "ro.build.version.sdk" to "37",
                "ro.product.cpu.abi" to "x86_64",
            )
            RunFullContract.validateRuntime(identity, "37", "x86_64", "1")
            val forgedIdentity = LinkedHashMap(identity).apply { put("ro.build.fingerprint", "forged") }
            val wrong = assertFailsWith<IllegalArgumentException> {
                RunFullContract.validateRuntime(forgedIdentity, "37", "x86_64", "1")
            }
            assertTrue(wrong.message!!.contains("wrong installed runtime"))
            for ((api, abi, boot) in listOf(
                Triple("36", "x86_64", "1"),
                Triple("37", "arm64-v8a", "1"),
                Triple("37", "x86_64", "0"),
            )) {
                val failure2 = assertFailsWith<IllegalArgumentException> {
                    RunFullContract.validateRuntime(identity, api, abi, boot)
                }
                assertTrue(failure2.message!!.contains("wrong installed runtime"))
            }
        }
    }

    test("api21 runtime requires exact google image and primary abi") {
        for ((abi, fingerprint) in RunFullContract.API21_FINGERPRINTS) {
            val identity = linkedMapOf(
                "ro.build.fingerprint" to fingerprint,
                "ro.build.version.sdk" to "21",
                "ro.product.cpu.abi" to abi,
            )
            RunFullContract.validateRuntime(identity, "21", abi, "1")
            for ((wrong, wrongAbi, boot) in listOf(
                Triple(
                    LinkedHashMap(identity).apply { put("ro.build.fingerprint", "forged") },
                    abi,
                    "1",
                ),
                Triple(identity, "arm64-v8a", "1"),
                Triple(identity, abi, "0"),
            )) {
                val failure = assertFailsWith<IllegalArgumentException>(abi) {
                    RunFullContract.validateRuntime(wrong, "21", wrongAbi, boot)
                }
                assertTrue(failure.message!!.contains("wrong installed runtime"))
            }
        }
    }

    test("cli accepts api21 for full installed route") {
        // The Python test replaces `run_full.run` and asserts the parsed `expected_api` reaches it.
        // The Kotlin equivalent proves the same parse step: a missing prepared manifest is reached.
        val failure = assertFailsWith<java.io.FileNotFoundException> {
            Cli.runFull(
                listOf(
                    "--prepared", "/missing",
                    "--provider-artifacts", "/missing",
                    "--build-receipt", "/missing",
                    "--build-type", "debug",
                    "--expected-api", "21",
                    "--expected-abi", "x86",
                    "--output", "/missing",
                ),
                Path.of("/"),
            ) {}
        }
        assertTrue(failure.message!!.contains("/missing"), failure.message)
    }
}
