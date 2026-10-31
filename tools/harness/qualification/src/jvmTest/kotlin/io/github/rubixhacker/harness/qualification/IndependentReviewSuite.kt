package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.FileTime
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** `test_independent_gates.py`'s two shared constants. */
private const val REVIEW_BASE = "e35e3f1ec357b1c44b6d2b742e0d88bc2e91f767"
private const val REVIEW_LANE = "jvm:Java:minimum:no-optimize"

private fun deleteTreeQuietly(root: Path) {
    if (!Files.exists(root)) return
    Files.walk(root).use { walk ->
        walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
    }
}

private fun writeJson(path: Path, value: JsonElement) {
    Files.writeString(path, value.toString())
}

private fun sha256(path: Path): String = Sha256.of(Files.readAllBytes(path))

/**
 * `test_review_requires_two_distinct_raw_sol_sessions_and_resolved_findings`: the
 * `independent-review` route through `evaluate`, with the reference's own fixture and the same
 * ordered accept/reject assertions.
 */
val IndependentReviewSuite by testSuite {
    test("the review gate requires two distinct raw Sol sessions and resolved findings") {
        val repository = repositoryRoot()
        val manifest = IndependentGates.loadApprovedManifest(repository)
        val root = Files.createTempDirectory("independent-review")
        try {
            val started = System.currentTimeMillis() * 1_000_000 - 1_000_000
            val finished = System.currentTimeMillis() * 1_000_000 + 1_000_000
            val hashes = mapOf("dyn4k-core" to "a".repeat(64), "dyn4k" to "b".repeat(64))
            val scope = LinkedHashMap<String, JsonElement>()
            scope["candidate_sha"] = JsonPrimitive(REVIEW_BASE)
            scope["target"] = JsonPrimitive("source")
            scope["runtime"] = JsonPrimitive("codex")
            scope["runtime_identity"] = JsonPrimitive("review CLI")
            scope["artifact_hashes"] = JsonObject(emptyMap())
            scope["producer_manifest_hashes"] = JsonObject(emptyMap())
            val receipt = LinkedHashMap<String, JsonElement>()
            receipt["schema"] = JsonPrimitive(1)
            receipt["status"] = JsonPrimitive("PASSED")
            receipt["candidate_sha"] = JsonPrimitive(REVIEW_BASE)
            receipt["source_tree"] = JsonPrimitive(
                reviewGit(repository, "rev-parse", "$REVIEW_BASE^{tree}"),
            )
            receipt["lane"] = JsonPrimitive(REVIEW_LANE)
            receipt["target"] = JsonPrimitive("jvm")
            receipt["runtime"] = JsonPrimitive("Java")
            receipt["version"] = JsonPrimitive("minimum")
            receipt["configuration"] = JsonPrimitive("no-optimize")
            receipt["runtime_identity"] = JsonPrimitive("review CLI")
            receipt["artifact_hashes"] = JsonObject(emptyMap())
            receipt["producer_scope"] = JsonObject(scope)
            receipt["process"] = buildJsonObject {
                put("command", JsonArray(listOf(JsonPrimitive("codex"), JsonPrimitive("exec"), JsonPrimitive("review"))))
                put("exit_code", JsonPrimitive(0))
                put("started_ns", JsonPrimitive(started))
                put("finished_ns", JsonPrimitive(finished))
            }

            var lastReason = ""
            fun write() {
                val files = Files.list(root).use { stream ->
                    stream.filter { it.fileName.toString() != "receipt.json" }.toList()
                }
                val manifests = LinkedHashMap<String, JsonElement>()
                for (kind in listOf("standards", "spec")) {
                    val report = root.resolve("$kind.json")
                    if (Files.isRegularFile(report)) {
                        manifests["$kind.json"] = JsonPrimitive(sha256(report))
                    }
                }
                scope["producer_manifest_hashes"] = JsonObject(manifests)
                receipt["producer_scope"] = JsonObject(scope)
                for (file in files) {
                    Files.setLastModifiedTime(
                        file,
                        FileTime.from(started + 1_000_000, TimeUnit.NANOSECONDS),
                    )
                }
                receipt["files"] = JsonArray(
                    files.map { file ->
                        buildJsonObject {
                            put("path", JsonPrimitive(file.fileName.toString()))
                            put("sha256", JsonPrimitive(sha256(file)))
                            put(
                                "mtime_ns",
                                JsonPrimitive(
                                    Files.getLastModifiedTime(file).to(TimeUnit.NANOSECONDS),
                                ),
                            )
                        }
                    },
                )
                writeJson(root.resolve("receipt.json"), JsonObject(receipt))
            }

            fun status(laneId: String = REVIEW_LANE, laneHashes: Map<String, String> = hashes,
                runtime: String = "review CLI", producerScope: JsonElement = JsonObject(scope),
            ): String {
                val archiveDigests = buildJsonObject {
                    put("independent-review", JsonPrimitive(ArchiveScan.digest(root)))
                }
                val scopes = buildJsonObject { put("independent-review", producerScope) }
                val result = GatesAggregate.evaluate(
                    manifest, REVIEW_BASE, laneId,
                    mapOf("independent-review" to root), repository,
                    laneHashes, runtime, archiveDigests,
                    expectedProducerScopes = scopes,
                )
                lastReason = Py.str((result["gates"] as JsonObject)
                    .getValue("independent-review").let { (it as JsonObject)["reason"] }) ?: ""
                return Py.str((result["gates"] as JsonObject).getValue("independent-review")
                    .let { (it as JsonObject)["status"] })!!
            }

            fun writeSession(kind: String, sessionId: String, findings: JsonArray) {
                val reviewed = if (kind == "standards") {
                    listOf("AGENTS.md", "docs/agents/writing.md")
                } else {
                    listOf(
                        "docs/specs/complete-port.md",
                        "docs/planning/acceptance-implementation.md",
                    )
                }
                val assessment =
                    "Reviewed the exact final head against the required source and acceptance obligations."
                val report = buildJsonObject {
                    put("review_kind", JsonPrimitive(kind))
                    put("candidate_sha", JsonPrimitive(REVIEW_BASE))
                    put("model", JsonPrimitive("gpt-6-sol"))
                    put("session_id", JsonPrimitive(sessionId))
                    put("verdict", JsonPrimitive("PASSED"))
                    put("findings", findings)
                    put("assessment", JsonPrimitive(assessment))
                    put("reviewed_paths", JsonArray(reviewed.map { JsonPrimitive(it) }))
                }
                writeJson(root.resolve("$kind.json"), report)
                val raw = buildJsonObject {
                    put("kind", JsonPrimitive("independent-review-result"))
                    put("review_kind", JsonPrimitive(kind))
                    put("candidate_sha", JsonPrimitive(REVIEW_BASE))
                    put("verdict", JsonPrimitive("PASSED"))
                    put("findings", findings)
                    put("assessment", JsonPrimitive(assessment))
                    put("reviewed_paths", JsonArray(reviewed.map { JsonPrimitive(it) }))
                }
                val messages = listOf(
                    buildJsonObject {
                        put("type", JsonPrimitive("session_meta"))
                        put("payload", buildJsonObject { put("id", JsonPrimitive(sessionId)) })
                    },
                    buildJsonObject {
                        put("type", JsonPrimitive("turn_context"))
                        put("payload", buildJsonObject { put("model", JsonPrimitive("gpt-6-sol")) })
                    },
                    buildJsonObject {
                        put("type", JsonPrimitive("response_item"))
                        put(
                            "payload",
                            buildJsonObject {
                                put("type", JsonPrimitive("message"))
                                put("role", JsonPrimitive("assistant"))
                                put(
                                    "content",
                                    JsonArray(
                                        listOf(
                                            buildJsonObject {
                                                put("type", JsonPrimitive("output_text"))
                                                put("text", JsonPrimitive(raw.toString()))
                                            },
                                        ),
                                    ),
                                )
                            },
                        )
                    },
                )
                Files.writeString(
                    root.resolve("$kind.jsonl"),
                    messages.joinToString("\n") + "\n",
                )
            }

            writeSession("standards", "session-a", JsonArray(emptyList()))
            write()
            assertEquals("FAILED", status(), lastReason)
            writeSession("spec", "session-b", JsonArray(emptyList()))
            write()
            assertEquals("PASSED", status(), lastReason)
            Files.writeString(
                root.resolve("spec.jsonl"),
                buildJsonObject {
                    put("type", JsonPrimitive("response_item"))
                    put(
                        "payload",
                        buildJsonObject {
                            put(
                                "findings",
                                JsonArray(
                                    listOf(
                                        buildJsonObject {
                                            put("id", JsonPrimitive("hidden-p1"))
                                            put("severity", JsonPrimitive("P1"))
                                        },
                                    ),
                                ),
                            )
                        },
                    )
                }.toString() + "\n",
                java.nio.file.StandardOpenOption.APPEND,
            )
            write()
            assertEquals("FAILED", status(), lastReason)
            val finding = LinkedHashMap<String, JsonElement>()
            finding["id"] = JsonPrimitive("finding-1")
            finding["severity"] = JsonPrimitive("P1")
            finding["description"] = JsonPrimitive("resolve a defect")
            writeSession("spec", "session-b", JsonArray(listOf(JsonObject(finding))))
            write()
            assertEquals("FAILED", status(), lastReason)
            finding["resolution"] = buildJsonObject {
                put("status", JsonPrimitive("RESOLVED"))
                put("candidate_sha", JsonPrimitive(REVIEW_BASE))
                put("evidence", JsonPrimitive("README.md"))
                put(
                    "evidence_sha256",
                    JsonPrimitive(
                        Sha256.of(
                            reviewGitBytes(repository, "show", "$REVIEW_BASE:README.md"),
                        ),
                    ),
                )
            }
            writeSession("spec", "session-b", JsonArray(listOf(JsonObject(finding))))
            write()
            assertEquals("PASSED", status(), lastReason)
            receipt["lane"] = JsonNull
            write()
            val nativeLane = "linuxX64:Linux x64:minimum:debug-g"
            val nativeHashes = mapOf("dyn4k-core" to "c".repeat(64), "dyn4k" to "d".repeat(64))
            assertEquals(
                "PASSED",
                status(nativeLane, nativeHashes, "native runner"),
                lastReason,
            )
            val wrongManifestScope = JsonObject(
                LinkedHashMap(scope).apply {
                    this["producer_manifest_hashes"] = buildJsonObject {
                        put("spec.json", JsonPrimitive("e".repeat(64)))
                    }
                },
            )
            assertEquals(
                "FAILED",
                status(nativeLane, nativeHashes, "native runner", wrongManifestScope),
            )
            receipt["lane"] = JsonPrimitive(REVIEW_LANE)
            write()
            val wrongScope = JsonObject(
                LinkedHashMap(scope).apply { this["target"] = JsonPrimitive("jvm") },
            )
            assertEquals("FAILED", status(producerScope = wrongScope), lastReason)
            writeJson(
                root.resolve("spec.json"),
                buildJsonObject {
                    put("review_kind", JsonPrimitive("spec"))
                    put("candidate_sha", JsonPrimitive(REVIEW_BASE))
                    put("model", JsonPrimitive("gpt-6-sol"))
                    put("session_id", JsonPrimitive("session-b"))
                    put("verdict", JsonPrimitive("PASSED"))
                    put("findings", JsonArray(emptyList()))
                },
            )
            write()
            assertEquals("FAILED", status(), lastReason)
        } finally {
            deleteTreeQuietly(root)
        }
    }

    test("an external unavailability observation must be bound to the lane") {
        val repository = repositoryRoot()
        val manifest = IndependentGates.loadApprovedManifest(repository)
        val root = Files.createTempDirectory("independent-unavailable")
        try {
            val receipt = LinkedHashMap<String, JsonElement>()
            receipt["schema"] = JsonPrimitive(1)
            receipt["status"] = JsonPrimitive("UNAVAILABLE")
            receipt["candidate_sha"] = JsonPrimitive(REVIEW_BASE)
            receipt["lane"] = JsonPrimitive(REVIEW_LANE)
            receipt["reason"] = JsonPrimitive("no physical device attached")
            receipt["observed_by"] = JsonPrimitive("device-lab")
            receipt["observed_at_ns"] = JsonPrimitive(System.currentTimeMillis() * 1_000_000)
            fun result(gate: String): String {
                val value = GatesAggregate.evaluate(
                    manifest, REVIEW_BASE, REVIEW_LANE, mapOf(gate to root), repository,
                )
                return Py.str(((value["gates"] as JsonObject).getValue(gate) as JsonObject)["status"])!!
            }
            writeJson(root.resolve("receipt.json"), JsonObject(receipt))
            assertEquals("UNAVAILABLE", result("physical-correctness"))
            receipt["lane"] = JsonPrimitive("other")
            writeJson(root.resolve("receipt.json"), JsonObject(receipt))
            assertEquals("FAILED", result("physical-correctness"))
            assertEquals("FAILED", result("migration-journeys"))
        } finally {
            deleteTreeQuietly(root)
        }
    }
}

private fun reviewGit(repository: Path, vararg arguments: String): String =
    String(reviewGitBytes(repository, *arguments)).trim()

private fun reviewGitBytes(repository: Path, vararg arguments: String): ByteArray {
    val process = ProcessBuilder(
        listOf("git", "--no-replace-objects", "-C", repository.toString()) + arguments,
    ).start()
    val stdout = process.inputStream.readBytes()
    process.errorStream.readBytes()
    check(process.waitFor() == 0) { "git ${arguments.joinToString(" ")} failed" }
    return stdout
}

/** Assert one recorded gate reason starts with the reference's message. */
internal fun assertReasonStartsWith(reason: String?, prefix: String) {
    assertTrue(reason != null && reason.startsWith(prefix), reason ?: "null")
}
