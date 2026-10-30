package io.github.rubixhacker.harness.android

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

private const val NATIVE_GRAPH =
    "androidNativeX64CompileKlibraries - Compile classpath\n" +
        "+--- org.jetbrains.kotlin:kotlin-stdlib:2.4.20\n" +
        "+--- io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1\n" +
        "|    \\--- io.github.rubixhacker:dyn4k-core-androidnativex64:0.1.0-alpha.1\n" +
        "\\--- io.github.rubixhacker:dyn4k:0.1.0-alpha.1\n" +
        "     \\--- io.github.rubixhacker:dyn4k-androidnativex64:0.1.0-alpha.1\n"

private const val STAGE_LOG =
    "> Task :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository\n" +
        "> Task :dyn4k:publishKotlinMultiplatformPublicationToStagingRepository\n" +
        "> Task :dyn4k-core:publishAndroidNativeX64PublicationToStagingRepository\n" +
        "> Task :dyn4k:publishAndroidNativeX64PublicationToStagingRepository\n" +
        "BUILD SUCCESSFUL\n"

private const val LINK_LOG =
    "> Task :linkDebugExecutableAndroidNativeX64\n" +
        "> Task :linkReleaseExecutableAndroidNativeX64\n" +
        "BUILD SUCCESSFUL\n"

private fun elfHeader(): ByteArray {
    val elf = ByteArray(64)
    elf[0] = 0x7f
    elf[1] = 'E'.code.toByte()
    elf[2] = 'L'.code.toByte()
    elf[3] = 'F'.code.toByte()
    elf[4] = 2
    elf[5] = 1
    elf[18] = 62
    elf[19] = 0
    return elf
}

/**
 * `tools/android-native-runtime/test_receipt.py`.
 *
 * A native receipt is accepted only when every recorded byte still agrees with the checkout: the staged
 * KLIBs, the executable, both build logs, the dependency report, the guest identity, and the pins.
 */
val NativeReceiptContract by testSuite {
    test("runner accepts only the trusted adb argument") {
        assertEquals(
            NativeReceipt.TRUSTED_ADB,
            NativeReceiptHost.validatedAdbArgument(Path.of(NativeReceipt.TRUSTED_ADB)),
        )
        assertFailsWith<IllegalArgumentException> {
            NativeReceiptHost.validatedAdbArgument(Path.of("/tmp/adb"))
        }
    }

    test("staged native process is accepted") {
        withTempDirectory { root ->
            val artifacts = linkedMapOf<String, JsonObject>()
            for (module in listOf("dyn4k-core", "dyn4k")) {
                val path = writeBytes(root, "$module-androidnativex64.klib", module.encodeToByteArray())
                artifacts[module] = buildJsonObject {
                    put("path", JsonPrimitive(posix(path)))
                    put("sha256", JsonPrimitive(sha256(path)))
                }
            }
            val executable = writeBytes(root, "journey.kexe", elfHeader())
            val replacementKlib = writeBytes(
                root,
                "dyn4k-core-substitute.klib",
                "forged core".encodeToByteArray(),
            )
            val replacementExecutable = writeBytes(
                root,
                "journey-substitute.kexe",
                elfHeader() + "forged executable".encodeToByteArray(),
            )
            val labels = NativeReceipt.ASSERTIONS
            val dependencyReport = writeFile(root, "dependencies.txt", NATIVE_GRAPH)
            val stageLog = writeFile(root, "stage.log", STAGE_LOG)
            val linkLog = writeFile(root, "link.log", LINK_LOG)
            val forgedLog = writeFile(root, "forged-stage.log", "BUILD SUCCESSFUL\n")
            val extraReports = linkedMapOf<String, Path>()
            for ((name, line) in listOf(
                "project" to "+--- project :extra\n",
                "baseline" to "+--- org.dyn4j:dyn4j:6.0.0\n",
                "unapproved" to "+--- com.example:other:1.0\n",
            )) {
                extraReports[name] = writeFile(root, "dependencies-$name.txt", NATIVE_GRAPH + line)
            }
            val stdout = labels.joinToString("") { "ASSERT $it\n" } + "NATIVE_RESULT PASS ${labels.size}\n"
            val stdoutPath = writeFile(root, "stdout.txt", stdout)
            val stderrPath = writeFile(root, "stderr.txt", "")
            val forgedStdoutPath = writeFile(root, "forged-stdout.txt", stdout + "ASSERT injected\n")
            val guestValues = linkedMapOf(
                "ro.boot.qemu.avd_name" to "dyn4k_api37_play_x64",
                "ro.build.version.sdk" to "37",
                "ro.build.fingerprint" to NativeReceipt.EXPECTED_FINGERPRINT,
                "ro.product.cpu.abi" to "x86_64",
                "ro.product.cpu.abilist" to "x86_64,arm64-v8a",
                "sys.boot_completed" to "1",
            )
            val pinPath = writeFile(
                root,
                "tools/android-native-runtime/pins.json",
                buildJsonObject {
                    put("schema", JsonPrimitive(1))
                    put("adb_sha256", JsonPrimitive(NativeReceipt.TRUSTED_ADB_SHA256))
                    put("guest_fingerprint", JsonPrimitive(NativeReceipt.EXPECTED_FINGERPRINT))
                    put(
                        "artifacts",
                        JsonObject(artifacts.mapValues { (_, record) -> record.getValue("sha256") }),
                    )
                    put(
                        "executables",
                        buildJsonObject {
                            put("debug", JsonPrimitive(sha256(executable)))
                            put("optimized", JsonPrimitive(sha256(executable)))
                        },
                    )
                }.toString(),
            )
            runGit(root, "init", "-q")
            runGit(root, "add", "tools/android-native-runtime/pins.json")
            runGit(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-q", "-m", "pin fixture")
            val sourceSha = runGit(root, "rev-parse", "HEAD").trim()
            val sourceTree = runGit(root, "rev-parse", "HEAD^{tree}").trim()
            val dependencyCommand = listOf(
                "${posix(root)}/gradlew",
                "-p",
                "${posix(root)}/consumers/android-native-runtime",
                "--no-daemon",
                "--console=plain",
                "-PstagingRepository=${posix(root)}/build/staging-repository",
                "dependencies",
                "--configuration",
                "androidNativeX64CompileKlibraries",
            )
            val observations = buildJsonObject {
                for ((property, value) in guestValues) {
                    put(
                        property,
                        buildJsonObject {
                            put(
                                "command",
                                JsonArray(
                                    listOf(
                                        NativeReceipt.TRUSTED_ADB, "-P", "5038", "-s",
                                        "emulator-5558", "shell", "getprop", property,
                                    ).map { JsonPrimitive(it) },
                                ),
                            )
                            put("stdout", JsonPrimitive("$value\n"))
                            put("stderr", JsonPrimitive(""))
                            put("exit_code", JsonPrimitive(0))
                        },
                    )
                }
            }
            val receipt = buildJsonObject {
                put("schema", JsonPrimitive(1))
                put("status", JsonPrimitive("DIAGNOSTIC_PASSED"))
                put("source_sha", JsonPrimitive(sourceSha))
                put("source_tree", JsonPrimitive(sourceTree))
                put("pin_manifest_sha256", JsonPrimitive(sha256(pinPath)))
                put("variant", JsonPrimitive("debug"))
                put(
                    "tooling",
                    buildJsonObject {
                        put("adb_path", JsonPrimitive(NativeReceipt.TRUSTED_ADB))
                        put("adb_sha256", JsonPrimitive(NativeReceipt.TRUSTED_ADB_SHA256))
                    },
                )
                put(
                    "build_evidence",
                    buildJsonObject {
                        put("stage", buildJsonObject {
                            put("path", JsonPrimitive(posix(stageLog)))
                            put("sha256", JsonPrimitive(sha256(stageLog)))
                        })
                        put("link", buildJsonObject {
                            put("path", JsonPrimitive(posix(linkLog)))
                            put("sha256", JsonPrimitive(sha256(linkLog)))
                        })
                    },
                )
                put(
                    "dependency_report",
                    buildJsonObject {
                        put("path", JsonPrimitive(posix(dependencyReport)))
                        put("sha256", JsonPrimitive(sha256(dependencyReport)))
                        put("command", JsonArray(dependencyCommand.map { JsonPrimitive(it) }))
                        put("exit_code", JsonPrimitive(0))
                    },
                )
                put("artifacts", JsonObject(artifacts))
                put(
                    "executable",
                    buildJsonObject {
                        put("path", JsonPrimitive(posix(executable)))
                        put("sha256", JsonPrimitive(sha256(executable)))
                        put("abi", JsonPrimitive("x86_64"))
                    },
                )
                put(
                    "guest",
                    buildJsonObject {
                        put("serial", JsonPrimitive("emulator-5558"))
                        put("api", JsonPrimitive("37"))
                        put("fingerprint", JsonPrimitive(NativeReceipt.EXPECTED_FINGERPRINT))
                        put("primary_abi", JsonPrimitive("x86_64"))
                        put("abi_list", JsonPrimitive("x86_64,arm64-v8a"))
                        put("boot_completed", JsonPrimitive("1"))
                        put("avd_name", JsonPrimitive("dyn4k_api37_play_x64"))
                        put("observations", observations)
                    },
                )
                put(
                    "deployment",
                    buildJsonObject {
                        put("remote_sha256", JsonPrimitive(sha256(executable)))
                        put("chmod_exit_code", JsonPrimitive(0))
                    },
                )
                put(
                    "process",
                    buildJsonObject {
                        put(
                            "command",
                            JsonArray(
                                listOf(
                                    NativeReceipt.TRUSTED_ADB, "-P", "5038", "-s", "emulator-5558",
                                    "shell", "/data/local/tmp/dyn4k-native-debug",
                                ).map { JsonPrimitive(it) },
                            ),
                        )
                        put("stdout", JsonPrimitive(stdout))
                        put("stderr", JsonPrimitive(""))
                        put("exit_code", JsonPrimitive(0))
                        put("stdout_path", JsonPrimitive(posix(stdoutPath)))
                        put("stdout_sha256", JsonPrimitive(sha256(stdoutPath)))
                        put("stderr_path", JsonPrimitive(posix(stderrPath)))
                        put("stderr_sha256", JsonPrimitive(sha256(stderrPath)))
                    },
                )
                put("assertion_count", JsonPrimitive(labels.size))
            }
            assertEquals(
                buildJsonObject {
                    put("status", JsonPrimitive("CONSISTENCY_ONLY"))
                    put("assertions", JsonPrimitive(labels.size))
                },
                NativeReceiptHost.validateReceipt(receipt, sourceSha, root),
            )

            val adverse = linkedMapOf<String, (MutableMap<String, JsonElement>) -> Unit>(
                "missing executable" to { item ->
                    nested(
                        item,
                        listOf("executable", "path"),
                        JsonPrimitive(posix(root.resolve("missing.kexe"))),
                    )
                },
                "wrong ABI" to { item ->
                    nested(item, listOf("executable", "abi"), JsonPrimitive("arm64-v8a"))
                },
                "wrong executable hash" to { item ->
                    nested(item, listOf("executable", "sha256"), JsonPrimitive("0".repeat(64)))
                },
                "wrong KLIB hash" to { item ->
                    val artifacts = (item.getValue("artifacts") as JsonObject).toMutableMap()
                    artifacts["dyn4k"] = withEntry(
                        artifacts.getValue("dyn4k") as JsonObject,
                        "sha256",
                        JsonPrimitive("0".repeat(64)),
                    )
                    item["artifacts"] = JsonObject(artifacts)
                },
                "no output" to { item -> nested(item, listOf("process", "stdout"), JsonPrimitive("")) },
                "no assertions" to { item ->
                    nested(item, listOf("process", "stdout"), JsonPrimitive("NATIVE_RESULT PASS 0\n"))
                    item["assertion_count"] = JsonPrimitive(0)
                },
                "self-consistent forged stdout" to { item ->
                    val process = (item.getValue("process") as JsonObject).toMutableMap()
                    process["stdout"] = JsonPrimitive(forgedStdoutPath.toFile().readText())
                    process["stdout_path"] = JsonPrimitive(posix(forgedStdoutPath))
                    process["stdout_sha256"] = JsonPrimitive(sha256(forgedStdoutPath))
                    item["process"] = JsonObject(process)
                },
                "nonzero exit" to { item ->
                    nested(item, listOf("process", "exit_code"), JsonPrimitive(1))
                },
                "missing dependency report" to { item -> item.remove("dependency_report") },
                "wrong raw output hash" to { item ->
                    nested(item, listOf("process", "stdout_sha256"), JsonPrimitive("0".repeat(64)))
                },
                "missing deployment" to { item -> item.remove("deployment") },
                "forged ADB command" to { item ->
                    val process = (item.getValue("process") as JsonObject).toMutableMap()
                    val command = JsonObject(process).arrayOrNull("command")!!.toMutableList()
                    command[0] = JsonPrimitive("/tmp/adb")
                    process["command"] = JsonArray(command)
                    item["process"] = JsonObject(process)
                },
                "wrong guest fingerprint" to { item ->
                    nested(item, listOf("guest", "fingerprint"), JsonPrimitive("made-up/other-guest"))
                },
                "missing guest observations" to { item ->
                    val guest = (item.getValue("guest") as JsonObject).toMutableMap()
                    guest.remove("observations")
                    item["guest"] = JsonObject(guest)
                },
                "forged guest query" to { item ->
                    nestedObservation(item, "ro.build.fingerprint", 0, JsonPrimitive("/tmp/adb"))
                },
                "changed guest query output" to { item ->
                    nestedObservation(item, "ro.product.cpu.abi", null, JsonPrimitive("arm64-v8a\n"))
                },
                "wrong source tree" to { item -> item["source_tree"] = JsonPrimitive("0".repeat(40)) },
                "self-consistent substituted KLIB" to { item ->
                    val artifacts = (item.getValue("artifacts") as JsonObject).toMutableMap()
                    artifacts["dyn4k-core"] = buildJsonObject {
                        put("path", JsonPrimitive(posix(replacementKlib)))
                        put("sha256", JsonPrimitive(sha256(replacementKlib)))
                    }
                    item["artifacts"] = JsonObject(artifacts)
                },
                "self-consistent substituted executable" to { item ->
                    val executableRecord = (item.getValue("executable") as JsonObject).toMutableMap()
                    executableRecord["path"] = JsonPrimitive(posix(replacementExecutable))
                    executableRecord["sha256"] = JsonPrimitive(sha256(replacementExecutable))
                    item["executable"] = JsonObject(executableRecord)
                    nested(
                        item,
                        listOf("deployment", "remote_sha256"),
                        JsonPrimitive(sha256(replacementExecutable)),
                    )
                },
                "extra project dependency" to { item ->
                    nestedReport(item, extraReports.getValue("project"))
                },
                "baseline provider dependency" to { item ->
                    nestedReport(item, extraReports.getValue("baseline"))
                },
                "unapproved provider dependency" to { item ->
                    nestedReport(item, extraReports.getValue("unapproved"))
                },
                "forged dependency command" to { item ->
                    val report = (item.getValue("dependency_report") as JsonObject).toMutableMap()
                    val command = JsonObject(report).arrayOrNull("command")!!.toMutableList()
                    command[0] = JsonPrimitive("/tmp/gradlew")
                    report["command"] = JsonArray(command)
                    item["dependency_report"] = JsonObject(report)
                },
                "failed dependency command" to { item ->
                    nested(item, listOf("dependency_report", "exit_code"), JsonPrimitive(1))
                },
                "forged ADB image hash" to { item ->
                    nested(item, listOf("tooling", "adb_sha256"), JsonPrimitive("0".repeat(64)))
                },
                "forged ADB image path" to { item ->
                    nested(item, listOf("tooling", "adb_path"), JsonPrimitive("/tmp/adb"))
                },
                "changed stage log hash" to { item ->
                    val evidence = (item.getValue("build_evidence") as JsonObject).toMutableMap()
                    evidence["stage"] = withEntry(
                        evidence.getValue("stage") as JsonObject,
                        "sha256",
                        JsonPrimitive("0".repeat(64)),
                    )
                    item["build_evidence"] = JsonObject(evidence)
                },
                "self-consistent forged stage log" to { item ->
                    val evidence = (item.getValue("build_evidence") as JsonObject).toMutableMap()
                    evidence["stage"] = buildJsonObject {
                        put("path", JsonPrimitive(posix(forgedLog)))
                        put("sha256", JsonPrimitive(sha256(forgedLog)))
                    }
                    item["build_evidence"] = JsonObject(evidence)
                },
                "altered pin manifest digest" to { item ->
                    item["pin_manifest_sha256"] = JsonPrimitive("0".repeat(64))
                },
            )
            for ((name, change) in adverse) {
                val invalid = deepCopyReceipt(receipt)
                change(invalid)
                assertFailsWith<IllegalArgumentException>(name) {
                    NativeReceiptHost.validateReceipt(JsonObject(invalid), sourceSha, root)
                }
            }

            // A receipt that rewrites the working pin file is still rejected: the committed pins win.
            val workingPins = FullHost.parseJson(pinPath.toFile().readBytes()).toMutableMap()
            val workingArtifacts = (workingPins.getValue("artifacts") as JsonObject).toMutableMap()
            workingArtifacts["dyn4k-core"] = JsonPrimitive(sha256(replacementKlib))
            workingPins["artifacts"] = JsonObject(workingArtifacts)
            val workingExecutables = (workingPins.getValue("executables") as JsonObject).toMutableMap()
            workingExecutables["debug"] = JsonPrimitive(sha256(replacementExecutable))
            workingPins["executables"] = JsonObject(workingExecutables)
            pinPath.toFile().writeText(JsonObject(workingPins).toString())
            val forgedReceipt = deepCopyReceipt(receipt)
            forgedReceipt["pin_manifest_sha256"] = JsonPrimitive(sha256(pinPath))
            val forgedArtifacts = (forgedReceipt.getValue("artifacts") as JsonObject).toMutableMap()
            forgedArtifacts["dyn4k-core"] = buildJsonObject {
                put("path", JsonPrimitive(posix(replacementKlib)))
                put("sha256", JsonPrimitive(sha256(replacementKlib)))
            }
            forgedReceipt["artifacts"] = JsonObject(forgedArtifacts)
            val forgedExecutable = (forgedReceipt.getValue("executable") as JsonObject).toMutableMap()
            forgedExecutable["path"] = JsonPrimitive(posix(replacementExecutable))
            forgedExecutable["sha256"] = JsonPrimitive(sha256(replacementExecutable))
            forgedReceipt["executable"] = JsonObject(forgedExecutable)
            nested(
                forgedReceipt,
                listOf("deployment", "remote_sha256"),
                JsonPrimitive(sha256(replacementExecutable)),
            )
            assertFailsWith<IllegalArgumentException> {
                NativeReceiptHost.validateReceipt(JsonObject(forgedReceipt), sourceSha, root)
            }
        }
    }
}

/** Replaces one field of the nested object at [path]. */
internal fun nested(
    item: MutableMap<String, JsonElement>,
    path: List<String>,
    value: JsonElement,
) {
    fun replace(current: JsonObject, index: Int): JsonObject {
        val map = current.toMutableMap()
        if (index == path.size - 1) {
            map[path[index]] = value
        } else {
            map[path[index]] = replace(map.getValue(path[index]) as JsonObject, index + 1)
        }
        return JsonObject(map)
    }
    replace(JsonObject(item), 0).forEach { (key, element) -> item[key] = element }
}

/** Rewrites one observation command argument or its output. */
internal fun nestedObservation(
    item: MutableMap<String, JsonElement>,
    property: String,
    index: Int?,
    value: JsonElement,
) {
    val guest = (item.getValue("guest") as JsonObject).toMutableMap()
    val observations = (guest.getValue("observations") as JsonObject).toMutableMap()
    val observation = (observations.getValue(property) as JsonObject).toMutableMap()
    if (index == null) {
        observation["stdout"] = value
    } else {
        val command = JsonObject(observation).arrayOrNull("command")!!.toMutableList()
        command[index] = value
        observation["command"] = JsonArray(command)
    }
    observations[property] = JsonObject(observation)
    guest["observations"] = JsonObject(observations)
    item["guest"] = JsonObject(guest)
}

private fun nestedReport(item: MutableMap<String, JsonElement>, path: Path) {
    val report = (item.getValue("dependency_report") as JsonObject).toMutableMap()
    report["path"] = JsonPrimitive(posix(path))
    report["sha256"] = JsonPrimitive(sha256(path))
    item["dependency_report"] = JsonObject(report)
}

/** `copy.deepcopy` of a receipt map. */
internal fun deepCopyReceipt(value: Map<String, JsonElement>): MutableMap<String, JsonElement> =
    value.mapValuesTo(LinkedHashMap()) { (_, element) -> deepCopyElement(element) }

internal fun deepCopyElement(element: JsonElement): JsonElement = when (element) {
    is JsonObject -> JsonObject(element.mapValues { (_, value) -> deepCopyElement(value) })
    is JsonArray -> JsonArray(element.map { deepCopyElement(it) })
    is JsonNull -> JsonNull
    else -> element
}

private fun withEntry(objectValue: JsonObject, key: String, value: JsonElement): JsonObject =
    JsonObject(objectValue.toMutableMap().apply { put(key, value) })
