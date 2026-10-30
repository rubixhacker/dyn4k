package io.github.rubixhacker.harness.migration

import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.PosixFilePermissions
import javax.xml.parsers.DocumentBuilderFactory
import org.w3c.dom.Element

/** XML that Python's `ElementTree.parse` would reject; `journeys.py` lets it propagate. */
class MigrationXmlFailure(message: String) : RuntimeException(message)

/**
 * `tools/migration/journeys.py` over a repository root.
 *
 * The Python module reads `ROOT` from its own path. The Kotlin runner takes the root explicitly so
 * the same code can serve the command line and a generated fixture.
 */
class JourneyRunner(
    private val root: Path,
    private val policy: JourneyPolicy = JourneyPolicy.DEFAULT,
) {
    /** `journeys.git`. */
    fun git(directory: Path, vararg arguments: String): String =
        Processes.run(listOf("git", "-C", directory.toString(), *arguments), check = true).stdout.trim()

    /** `journeys.require_clean_candidate`. */
    fun requireCleanCandidate(expectedCommit: String? = null): String {
        val commit = git(root, "rev-parse", "HEAD")
        if ((expectedCommit != null && commit != expectedCommit) ||
            git(root, "status", "--porcelain=v1", "--untracked-files=all").isNotEmpty()
        ) {
            throw MigrationFailure("candidate worktree changed; exact committed harness required")
        }
        return commit
    }

    /** `journeys.inspect_samples`. */
    fun inspectSamples(samples: Path): PyValue {
        if (git(samples, "rev-parse", "HEAD") != policy.sampleRevision) {
            throw MigrationFailure("sample checkout revision differs from pinned revision")
        }
        if (git(samples, "status", "--porcelain=v1", "--untracked-files=all").isNotEmpty()) {
            throw MigrationFailure("sample checkout changed")
        }
        val paths = pythonSplitlines(git(samples, "ls-files", "--", "*.java"))
        if (paths.size != 42 ||
            paths != paths.sortedWith { left, right ->
                io.github.rubixhacker.harness.contract.CanonicalJson.compareCodePoints(left, right)
            }
        ) {
            throw MigrationFailure("expected 42 sorted tracked Java sources")
        }
        val manifest = buildString {
            for (path in paths) {
                append(MigrationFiles.digest(samples.resolve(path))).append("  ").append(path).append('\n')
            }
        }
        val digest = io.github.rubixhacker.harness.contract.Sha256.of(manifest)
        if (digest != policy.sourceManifestSha256) {
            throw MigrationFailure("sample source manifest changed")
        }
        return pyMap(
            "revision" to pyText(policy.sampleRevision),
            "java_source_count" to pyInt(paths.size),
            "manifest_sha256" to pyText(digest),
            "manifest" to pyText(manifest),
        )
    }

    /** `journeys.raw_evidence_manifest`. */
    fun rawEvidenceManifest(output: Path): String {
        val entries = MigrationFiles.filesBelow(output).map { path ->
            EvidenceFile(
                relative = MigrationFiles.relativePosix(output, path),
                digest = MigrationFiles.digest(path),
                symlink = MigrationFiles.isSymlink(path),
            )
        }
        return JourneyEvidence.rawEvidenceManifest(entries)
    }

    /** `journeys.write_summary`; mutates and returns [report]. */
    fun writeSummary(output: Path, report: PyValue.Map): PyValue.Map {
        val manifest = rawEvidenceManifest(output).toByteArray(StandardCharsets.UTF_8)
        MigrationFiles.writeBytes(output.resolve("evidence.sha256"), manifest)
        report.entries["evidence_manifest_sha256"] =
            pyText(io.github.rubixhacker.harness.contract.Sha256.of(manifest))
        report.entries["evidence_file_count"] =
            pyInt(JourneyEvidence.manifestLineCount(manifest))
        MigrationFiles.writeText(output.resolve("summary.json"), PyJson.prettyLine(report))
        return report
    }

    /** `journeys.verify_evidence`. */
    fun verifyEvidence(output: Path): PyValue {
        val summaryText = MigrationFiles.readTextOrEmpty(output.resolve("summary.json"))
        val report = try {
            pyFromJson(strictJson().parseToJsonElement(summaryText))
        } catch (error: IllegalArgumentException) {
            throw MigrationFailure(pythonJsonError(error))
        }
        val manifest = MigrationFiles.readBytesOrThrow(output.resolve("evidence.sha256"))
        val raw = rawEvidenceManifest(output).toByteArray(StandardCharsets.UTF_8)
        return JourneyEvidence.verifyEvidence(report, manifest, raw)
    }

    /** `journeys.record_unavailable`. */
    fun recordUnavailable(output: Path, reason: String): PyValue.Map {
        Files.createDirectories(output)
        val report = JourneyEvidence.unavailableReport(reason) as PyValue.Map
        return writeSummary(output, report)
    }

    /** `journeys.inspect_artifacts`. */
    fun inspectArtifacts(provider: String, resolved: Path, repository: Path?): PyValue {
        val jars = MigrationFiles.jars(resolved)
        val names = jars.map { it.fileName.toString() }
        if (jars.size != names.toSet().size || jars.isEmpty()) {
            throw MigrationFailure("resolved JAR set is empty or ambiguous")
        }
        val expected = linkedSetOf("jogl-all-2.3.2.jar", "gluegen-rt-2.3.2.jar")
        expected.add(if (provider == "baseline") "dyn4j-6.0.0.jar" else policy.candidateJar)
        if (!names.toSet().containsAll(expected)) {
            val missing = (expected - names.toSet()).sortedWith { left, right ->
                io.github.rubixhacker.harness.contract.CanonicalJson.compareCodePoints(left, right)
            }
            throw MigrationFailure("published dependency missing: ${pythonRepr(pyList(missing.map(::pyText)))}")
        }
        if (provider == "baseline" && names.toSet() != expected) {
            throw MigrationFailure("baseline dependency graph has unexpected JARs")
        }
        if (provider == "candidate" && "dyn4j-6.0.0.jar" in names) {
            throw MigrationFailure("duplicate org.dyn4j provider in candidate graph")
        }
        if (provider == "candidate" &&
            names.any { it.startsWith("dyn4k-core-") && it != policy.candidateJar }
        ) {
            throw MigrationFailure("candidate graph has multiple dyn4k-core artifacts")
        }
        var pom: Path? = null
        var module: Path? = null
        if (provider == "candidate") {
            if (repository == null) throw MigrationFailure("staged repository is required for candidate")
            val stagedJar = repository.resolve("io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1")
                .resolve(policy.candidateJar)
            if (!Files.isRegularFile(stagedJar) ||
                !Files.readAllBytes(stagedJar).contentEquals(
                    Files.readAllBytes(resolved.resolve(policy.candidateJar)),
                )
            ) {
                throw MigrationFailure("candidate JAR differs from staged publication")
            }
            pom = MigrationFiles.withSuffix(stagedJar, ".pom")
            module = MigrationFiles.withSuffix(stagedJar, ".module")
            if (!Files.isRegularFile(pom) || !Files.isRegularFile(module)) {
                throw MigrationFailure("staged publication metadata missing")
            }
            val identity = xmlIdentity(pom)
            if (identity != listOf("io.github.rubixhacker", "dyn4k-core-jvm", "0.1.0-alpha.1")) {
                throw MigrationFailure("staged publication metadata identity differs")
            }
        }
        val observed = mutableListOf<PyValue>()
        for (jar in jars) {
            val name = jar.fileName.toString()
            val digest = MigrationFiles.digest(jar)
            policy.pinnedJars[name]?.let {
                if (digest != it) throw MigrationFailure("$name SHA-256 differs from pinned artifact")
            }
            observed.add(pyMap("name" to pyText(name), "sha256" to pyText(digest)))
        }
        val report = linkedMapOf<String, PyValue>(
            "provider" to pyText(provider),
            "jars" to pyList(observed),
        )
        if (provider == "candidate") {
            report["staged_metadata"] = pyMap(
                "pom_sha256" to pyText(MigrationFiles.digest(pom!!)),
                "module_sha256" to pyText(MigrationFiles.digest(module!!)),
            )
        }
        return PyValue.Map(report)
    }

    /** `journeys.compile_samples`. */
    fun compileSamples(
        provider: String,
        samples: Path,
        resolved: Path,
        repository: Path?,
        output: Path,
        javac: Path,
        timeout: Double = 180.0,
    ): PyValue.Map {
        if (Files.exists(output) && !MigrationFiles.isDirectoryEmpty(output)) {
            throw MigrationFailure("compile output directory is not empty")
        }
        val classes = output.resolve("classes")
        Files.createDirectories(output)
        if (Files.exists(classes)) throw IOException("[Errno 17] File exists: '$classes'")
        Files.createDirectory(classes)
        val report = linkedMapOf<String, PyValue>(
            "provider" to pyText(provider),
            "status" to pyText("FAILED"),
            "exit_code" to PyValue.Null,
            "stage" to pyText("preparation"),
            "reason" to PyValue.Null,
        )
        try {
            val source = inspectSamples(samples)
            val artifacts = inspectArtifacts(provider, resolved, repository)
            val sources = pythonSplitlines(git(samples, "ls-files", "--", "*.java"))
                .map { samples.resolve(it).toString() }
            val jars = (artifacts.get("jars") as PyValue.Seq).items
            val classpath = jars.joinToString(MigrationFiles.pathSeparator()) {
                resolved.resolve((it.get("name") as PyValue.Text).value).toString()
            }
            val command = listOf(javac.toString(), "--release", "8", "-cp", classpath, "-d", classes.toString()) + sources
            report["source_count"] = pyInt((source.get("java_source_count") as PyValue.Int).value)
            report["source_manifest_sha256"] = source.get("manifest_sha256")
            report["artifacts"] = artifacts.get("jars")
            report["command"] = pyList(command.map(::pyText))
            report["stage"] = pyText("compilation")
            val exitCode = subprocessLog(command, output.resolve("javac.log"), timeout)
            report["exit_code"] = pyInt(exitCode)
            if (exitCode != 0) {
                report["reason"] = pyText(if (exitCode == 124) "TIMEOUT" else "javac failed")
            } else {
                report["stage"] = pyText("version")
                val versionLog = output.resolve("javac-version.log")
                val versionExit = subprocessLog(listOf(javac.toString(), "-version"), versionLog, timeout)
                if (versionExit != 0) {
                    report["exit_code"] = pyInt(versionExit)
                    report["reason"] = pyText(
                        if (versionExit == 124) "TIMEOUT" else "javac version failed",
                    )
                } else {
                    report["javac_version"] = pyText(
                        MigrationFiles.readTextOrEmpty(versionLog).trim(),
                    )
                    report["status"] = pyText("PASSED")
                    report["reason"] = PyValue.Null
                }
            }
            report["class_count"] = pyInt(MigrationFiles.countClassFiles(classes))
        } catch (error: IOException) {
            report["reason"] = pyText(error.message ?: error.toString())
            report["class_count"] = pyInt(MigrationFiles.countClassFiles(classes))
        } catch (error: ProcessFailure) {
            report["reason"] = pyText(error.message ?: error.toString())
            report["class_count"] = pyInt(MigrationFiles.countClassFiles(classes))
        } catch (error: MigrationFailure) {
            report["reason"] = pyText(error.message ?: error.toString())
            report["class_count"] = pyInt(MigrationFiles.countClassFiles(classes))
        }
        MigrationFiles.writeText(output.resolve("compile.json"), PyJson.prettyLine(PyValue.Map(report)))
        return PyValue.Map(report)
    }

    /** `journeys.subprocess_log`; a timeout is recorded as exit code 124. */
    fun subprocessLog(command: List<String>, log: Path, timeout: Double = 180.0): Int = try {
        val result = Processes.run(command, timeout)
        MigrationFiles.writeText(log, result.stdout + result.stderr)
        result.exitCode
    } catch (error: ProcessTimeout) {
        MigrationFiles.writeText(log, error.stdout + error.stderr + "\nPROCESS TIMEOUT\n")
        124
    }

    /** `journeys.build_observer`. */
    fun buildObserver(
        plainClasses: Path,
        observedClasses: Path,
        resolved: Path,
        instrumentation: Path,
        javac: Path,
        java: Path,
        log: Path,
        timeout: Double = 180.0,
    ): Int {
        val receipt = log.resolveSibling("observer-build.json")
        val report = linkedMapOf<String, PyValue>(
            "status" to pyText("FAILED"),
            "stage" to pyText("preparation"),
            "exit_code" to PyValue.Null,
            "reason" to PyValue.Null,
            "commands" to pyList(emptyList()),
        )
        val commands = (report["commands"] as PyValue.Seq).items.toMutableList()
        try {
            val javassist = instrumentation.resolve(Journeys.JAVASSIST_JAR)
            if (!Files.isRegularFile(javassist) || MigrationFiles.digest(javassist) != policy.javassistSha256) {
                throw MigrationFailure("Javassist artifact missing or SHA-256 changed")
            }
            MigrationFiles.copyTree(plainClasses, observedClasses)
            val jars = MigrationFiles.jars(resolved)
            val classpath = (listOf(observedClasses.toString()) + jars.map { it.toString() })
                .joinToString(MigrationFiles.pathSeparator())
            val observer = root.resolve(
                "consumers/migration/src/main/java/org/dyn4j/samples/framework/SceneObserver.java",
            )
            val weave = root.resolve("tools/migration/HookWeaver.java")
            val stages = listOf(
                "observer compile" to listOf(
                    javac.toString(), "--release", "8", "-cp", classpath, "-d",
                    observedClasses.toString(), observer.toString(),
                ),
                "weaver compile" to listOf(
                    javac.toString(), "--release", "8", "-cp",
                    listOf(observedClasses.toString(), javassist.toString())
                        .joinToString(MigrationFiles.pathSeparator()),
                    "-d", observedClasses.toString(), weave.toString(),
                ),
                "weave" to listOf(
                    java.toString(), "-cp",
                    listOf(classpath, javassist.toString()).joinToString(MigrationFiles.pathSeparator()),
                    "HookWeaver", observedClasses.toString(),
                ),
            )
            val stream = StringBuilder()
            MigrationFiles.writeText(log, "")
            var failed = false
            for ((stage, command) in stages) {
                report["stage"] = pyText(stage)
                stream.append("$ ").append(command.joinToString(" ")).append('\n')
                MigrationFiles.writeText(log, stream.toString())
                val commandLog = log.resolveSibling("observer-command.log")
                val exitCode = subprocessLog(command, commandLog, timeout)
                stream.append(MigrationFiles.readTextOrEmpty(commandLog)).append('\n')
                Files.deleteIfExists(commandLog)
                MigrationFiles.writeText(log, stream.toString())
                commands.add(
                    pyMap(
                        "stage" to pyText(stage),
                        "command" to pyList(command.map(::pyText)),
                        "exit_code" to pyInt(exitCode),
                    ),
                )
                report["exit_code"] = pyInt(exitCode)
                if (exitCode != 0) {
                    report["reason"] = pyText(if (exitCode == 124) "TIMEOUT" else "$stage failed")
                    failed = true
                    break
                }
            }
            report["commands"] = pyList(commands)
            if (!failed) {
                report["status"] = pyText("PASSED")
                report["reason"] = PyValue.Null
            }
        } catch (error: IOException) {
            report["commands"] = pyList(commands)
            report["reason"] = pyText(error.message ?: error.toString())
            appendLog(log, error.message ?: error.toString())
        } catch (error: MigrationFailure) {
            report["commands"] = pyList(commands)
            report["reason"] = pyText(error.message ?: error.toString())
            appendLog(log, error.message ?: error.toString())
        }
        MigrationFiles.writeText(receipt, PyJson.prettyLine(PyValue.Map(report)))
        val exitCode = (report["exit_code"] as? PyValue.Int)?.value?.toInt()
        return if (pyEquals(report.getValue("status"), pyText("PASSED"))) {
            exitCode ?: 0
        } else {
            exitCode ?: 1
        }
    }

    /** `journeys.podman_scene`. */
    fun podmanScene(
        scene: String,
        mode: String,
        samples: Path,
        resolved: Path,
        classes: Path,
        output: Path,
        jdk: Path,
        image: String,
        cpuset: String? = null,
        timeout: Double = 180.0,
    ): PyValue {
        Files.createDirectories(output)
        val evidence = output.resolve("evidence")
        Files.createDirectory(evidence)
        val tmp = evidence.resolve("tmp")
        Files.createDirectory(
            tmp,
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")),
        )
        val jars = MigrationFiles.jars(resolved)
        val dependencyCp = jars.joinToString(":") { "/work/lib/" + it.fileName }
        val script = if (mode == "plain") "run-plain-scene.sh" else "run-scene.sh"
        val containerClasses = if (mode == "plain") "/work/classes-plain" else "/work/classes"
        val command = mutableListOf(
            "podman", "run", "--rm", "--network=none", "--userns=keep-id",
            "--security-opt", "label=disable",
            "-v", "${samples.toAbsolutePath()}:/work/samples:ro",
            "-v", "${resolved.toAbsolutePath()}:/work/lib:ro",
            "-v", "${root.resolve("tools/migration").toAbsolutePath()}:/work/tools/migration:ro",
            "-v", "${classes.toAbsolutePath()}:$containerClasses:ro",
            "-v", "${evidence.toAbsolutePath()}:/work/evidence:rw",
            "-v", "${jdk.toAbsolutePath()}:/jdk:ro",
            "-e", "DEPENDENCY_CP=$dependencyCp",
            "-e", "PLAIN_EVIDENCE_DIR=/work/evidence",
            "-e", "TMPDIR=/work/evidence/tmp",
        )
        if (cpuset != null) {
            command.addAll(listOf("-e", "MIGRATION_CPUSET=$cpuset", image, "taskset", "-c", cpuset))
        } else {
            command.add(image)
        }
        command.addAll(listOf("bash", "/work/tools/migration/$script", scene))
        if (mode == "observed") {
            command.add(if (scene == "Truck") "18" else "12")
        }
        MigrationFiles.writeText(
            output.resolve("invocation.json"),
            PyJson.prettyLine(pyMap("command" to pyList(command.map(::pyText)))),
        )
        val exitCode = subprocessLog(command, output.resolve("container.log"), timeout)
        val validationPath = evidence.resolve(scene)
            .resolve(if (mode == "plain") "plain-validation.json" else "validation.json")
        val validation = try {
            pyFromJson(strictJson().parseToJsonElement(MigrationFiles.readTextOrEmpty(validationPath)))
        } catch (error: IOException) {
            pyMap()
        } catch (error: IllegalArgumentException) {
            pyMap()
        }
        fun get(key: String, fallback: PyValue?): PyValue =
            if (validation is PyValue.Map && validation.entries.containsKey(key)) {
                validation.entries.getValue(key)
            } else {
                fallback ?: PyValue.Null
            }
        val failed = get("failed", validation.getOrNull("failed_checks"))
        val unexecuted = get("unexecuted", validation.getOrNull("unexecuted_checks"))
        val executed = get("executed", validation.getOrNull("executed_checks") ?: pyInt(0))
        val passed = exitCode == 0 &&
            pyEquals(failed, pyInt(0)) &&
            pyEquals(unexecuted, pyInt(0)) &&
            pyCompare(executed, pyInt(0), ">") > 0
        return pyMap(
            "mode" to pyText(mode),
            "status" to pyText(if (passed) "PASSED" else "FAILED"),
            "exit_code" to pyInt(exitCode),
            "validation" to validation,
            "evidence" to pyText(MigrationFiles.posix(evidence.resolve(scene))),
        )
    }

    /** `journeys.run_all`. */
    fun runAll(
        samples: Path,
        resolvedRoot: Path,
        repository: Path?,
        instrumentation: Path,
        output: Path,
        javac: Path,
        java: Path,
        jdk: Path,
        image: String,
        timeout: Double,
        cpuset: String? = null,
    ): PyValue.Map {
        val commit = requireCleanCandidate()
        val source = inspectSamples(samples)
        if (Files.exists(output) && !MigrationFiles.isDirectoryEmpty(output)) {
            throw MigrationFailure("journey output directory is not empty")
        }
        Files.createDirectories(output)
        var imageId: String? = null
        val preparation = linkedMapOf<String, PyValue>(
            "stage" to pyText("headful image"),
            "status" to pyText("UNAVAILABLE"),
            "reason" to PyValue.Null,
        )
        if (which("podman") == null) {
            preparation["reason"] = pyText("podman executable unavailable")
        } else {
            try {
                val exists = Processes.run(
                    listOf("podman", "image", "exists", image),
                    timeout,
                )
                MigrationFiles.writeText(
                    output.resolve("image-exists.log"),
                    exists.stdout + exists.stderr,
                )
                if (exists.exitCode == 0) {
                    val inspected = Processes.run(
                        listOf("podman", "image", "inspect", "--format", "{{.Id}}", image),
                        timeout,
                    )
                    MigrationFiles.writeText(
                        output.resolve("image-inspect.log"),
                        inspected.stdout + inspected.stderr,
                    )
                    if (inspected.exitCode == 0 && inspected.stdout.trim().isNotEmpty()) {
                        imageId = inspected.stdout.trim()
                        preparation["status"] = pyText("PASSED")
                    } else {
                        preparation["status"] = pyText("FAILED")
                        preparation["reason"] = pyText("headful image inspection failed")
                        preparation["exit_code"] = pyInt(inspected.exitCode)
                    }
                } else {
                    preparation["reason"] = pyText("headful container image unavailable: $image")
                }
            } catch (error: ProcessTimeout) {
                preparation["status"] = pyText("FAILED")
                preparation["reason"] = pyText("TIMEOUT")
                preparation["command"] = pyList(error.command.map(::pyText))
            } catch (error: IOException) {
                preparation["status"] = pyText("FAILED")
                preparation["reason"] = pyText(error.message ?: error.toString())
            }
        }
        MigrationFiles.writeText(
            output.resolve("preparation.json"),
            PyJson.prettyLine(PyValue.Map(preparation)),
        )
        val imageAvailable = pyEquals(preparation.getValue("status"), pyText("PASSED"))
        val cases = mutableListOf<PyValue>()
        for (provider in Journeys.PROVIDERS) {
            val providerOutput = output.resolve(provider)
            Files.createDirectory(providerOutput)
            val resolved = resolvedRoot.resolve(provider)
            val compileReport = try {
                compileSamples(
                    provider, samples, resolved, repository,
                    providerOutput.resolve("compile"), javac, timeout,
                )
            } catch (error: IOException) {
                val failed = pyMap("status" to pyText("FAILED"), "reason" to pyText(error.message ?: ""))
                MigrationFiles.writeText(providerOutput.resolve("compile.json"), PyJson.prettyLine(failed))
                failed
            } catch (error: MigrationFailure) {
                val failed = pyMap("status" to pyText("FAILED"), "reason" to pyText(error.message ?: ""))
                MigrationFiles.writeText(providerOutput.resolve("compile.json"), PyJson.prettyLine(failed))
                failed
            }
            if (!pyEquals(compileReport.get("status"), pyText("PASSED"))) {
                for (scene in Journeys.SCENES) {
                    cases.add(
                        pyMap(
                            "provider" to pyText(provider),
                            "scene" to pyText(scene),
                            "status" to pyText("FAILED"),
                            "reason" to pyText("unchanged Java source compilation failed"),
                        ),
                    )
                }
                continue
            }
            if (!imageAvailable) {
                for (scene in Journeys.SCENES) {
                    cases.add(
                        pyMap(
                            "provider" to pyText(provider),
                            "scene" to pyText(scene),
                            "status" to preparation.getValue("status"),
                            "reason" to preparation.getValue("reason"),
                        ),
                    )
                }
                continue
            }
            val observedClasses = providerOutput.resolve("observer-classes")
            val observerStatus = buildObserver(
                providerOutput.resolve("compile/classes"), observedClasses, resolved,
                instrumentation, javac, java, providerOutput.resolve("observer-build.log"), timeout,
            )
            for (scene in Journeys.SCENES) {
                val plain = podmanScene(
                    scene, "plain", samples, resolved, providerOutput.resolve("compile/classes"),
                    providerOutput.resolve(scene).resolve("plain"), jdk, image, cpuset, timeout,
                )
                val observed = if (observerStatus == 0) {
                    podmanScene(
                        scene, "observed", samples, resolved, observedClasses,
                        providerOutput.resolve(scene).resolve("observed"), jdk, image, cpuset, timeout,
                    )
                } else {
                    pyMap("status" to pyText("FAILED"), "reason" to pyText("observer build failed"))
                }
                cases.add(
                    pyMap(
                        "provider" to pyText(provider),
                        "scene" to pyText(scene),
                        "status" to pyText(
                            if (pyEquals(plain.get("status"), pyText("PASSED")) &&
                                pyEquals(observed.get("status"), pyText("PASSED"))
                            ) {
                                "PASSED"
                            } else {
                                "FAILED"
                            },
                        ),
                        "rendered_acceptance" to pyText(
                            if (scene == "Truck") "UNREVIEWED" else "NOT_APPLICABLE",
                        ),
                        "plain" to plain,
                        "observed" to observed,
                    ),
                )
            }
        }
        try {
            requireCleanCandidate(commit)
        } catch (error: MigrationFailure) {
            MigrationFiles.writeText(
                output.resolve("candidate-check.json"),
                PyJson.prettyLine(pyMap("status" to pyText("FAILED"), "reason" to pyText(error.message ?: ""))),
            )
            throw error
        }
        val finalSource = try {
            val inspected = inspectSamples(samples)
            for (key in listOf("revision", "java_source_count", "manifest_sha256", "manifest")) {
                if (!pyEquals(inspected.get(key), source.get(key))) {
                    throw MigrationFailure("sample source changed during journey execution")
                }
            }
            inspected
        } catch (error: IOException) {
            MigrationFiles.writeText(
                output.resolve("sample-check.json"),
                PyJson.prettyLine(pyMap("status" to pyText("FAILED"), "reason" to pyText(error.message ?: ""))),
            )
            throw error
        } catch (error: ProcessFailure) {
            MigrationFiles.writeText(
                output.resolve("sample-check.json"),
                PyJson.prettyLine(pyMap("status" to pyText("FAILED"), "reason" to pyText(error.message ?: ""))),
            )
            throw error
        } catch (error: MigrationFailure) {
            MigrationFiles.writeText(
                output.resolve("sample-check.json"),
                PyJson.prettyLine(pyMap("status" to pyText("FAILED"), "reason" to pyText(error.message ?: ""))),
            )
            throw error
        }
        MigrationFiles.writeText(
            output.resolve("sample-check.json"),
            PyJson.prettyLine(
                pyMap(
                    "status" to pyText("PASSED"),
                    "revision" to finalSource.get("revision"),
                    "java_source_count" to finalSource.get("java_source_count"),
                    "manifest_sha256" to finalSource.get("manifest_sha256"),
                ),
            ),
        )
        val report = linkedMapOf<String, PyValue>(
            "candidate_commit" to pyText(commit),
            "candidate_worktree_clean" to pyBool(true),
            "container_cpuset_cpus" to (cpuset?.let(::pyText) ?: PyValue.Null),
            "truck_rendered_acceptance" to pyText("UNREVIEWED"),
            "headful_image" to pyText(image),
            "headful_image_id" to (imageId?.let(::pyText) ?: PyValue.Null),
            "source_revision" to source.get("revision"),
            "source_manifest_sha256" to source.get("manifest_sha256"),
            "expected_cases" to pyInt(10),
            "passed_cases" to pyInt(cases.count { pyEquals(it.get("status"), pyText("PASSED")) }),
            "failed_cases" to pyInt(cases.count { pyEquals(it.get("status"), pyText("FAILED")) }),
            "unavailable_cases" to pyInt(cases.count { pyEquals(it.get("status"), pyText("UNAVAILABLE")) }),
            "cases" to pyList(cases),
        )
        writeSummary(output, PyValue.Map(report))
        return PyValue.Map(report)
    }

    private fun appendLog(log: Path, line: String) {
        val existing = MigrationFiles.readTextOrEmpty(log)
        MigrationFiles.writeText(log, existing + line + "\n")
    }

    private fun xmlIdentity(pom: Path): List<String> {
        val document = try {
            val factory = DocumentBuilderFactory.newInstance()
            factory.isNamespaceAware = true
            factory.newDocumentBuilder().parse(pom.toFile())
        } catch (error: Exception) {
            throw MigrationXmlFailure(error.message ?: error.toString())
        }
        val root = document.documentElement
        fun directText(key: String): String? {
            val children = root.childNodes
            for (index in 0 until children.length) {
                val node = children.item(index)
                if (node is Element && node.tagName == key) {
                    val text = node.textContent
                    if (!text.isNullOrEmpty()) return text
                }
            }
            return null
        }
        fun anyText(key: String): String? {
            val nodes = root.getElementsByTagNameNS("*", key)
            for (index in 0 until nodes.length) {
                val text = nodes.item(index).textContent
                if (!text.isNullOrEmpty()) return text
            }
            return null
        }
        return listOf("groupId", "artifactId", "version").map { key ->
            directText(key) ?: anyText(key) ?: ""
        }
    }

    private fun strictJson() = kotlinx.serialization.json.Json {
        allowSpecialFloatingPointValues = true
    }
}
