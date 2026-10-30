package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.io.FileNotFoundException
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * `independent_gates.py`, prospective slice: the recorded window cases of
 * `test_independent_gates.py`.
 *
 * Each case replays one ancestry window the reference records for a candidate commit: which
 * approved checker and producer blobs that candidate inherits, and which recorded bytes it must
 * agree with. The drift cases, which the reference injects through `Path.read_bytes` and
 * `subprocess.check_output`, re-run here through [GateSource].
 *
 * The reference cases assume the checkout holds the pinned bytes of every local dependency. On
 * this branch it no longer does: four `tools/numerical/portable` test sources and that module's
 * build file were converted to TestBalloon in `2fd9a350` without re-recording the capture pins.
 * [pinnedCheckout] restores the premise the reference asserts — the recorded bytes, read from the
 * commit that recorded them — so the window assertions run unchanged, and each case still asserts
 * the reference's rejecting branch against the unmodified checkout.
 */
val GatesProspectiveContract by testSuite {
    test("the executable checker window binds the complete committed closure") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val revision = "fbaee1b16de2ff0633e2981e69cf59044b61c745"
        assertEquals(revision, GateConstants.PROSPECTIVE_EXECUTABLE_CHECKER_REVISION)
        val closure = GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS
        assertEquals(
            setOf(
                "numeric_producer.py", "numeric_producer_trace.py", "numeric_class_witness.py",
                "pulley_jdi_v2.py", "pulley_jdi_v1.py", "pulley_jdi_inputs_v2.py", "run.py",
                "frozen_weld_pulley.py", "exact_consistency.py", "physical.py",
                "class_witness/NumericClassWitness.java",
            ),
            closure.keys - GateConstants.APPROVED_PROSPECTIVE_INVENTORY_FIX_CHECKERS.keys,
        )
        assertTrue("prospective_compare.py" in closure)
        assertEquals(
            mapOf(
                "tools/numerical/compare.py" to
                    GatesNumerical.APPROVED_POLICY.getValue("tools/numerical/compare.py"),
                "tools/numerical/physical.py" to
                    GatesNumerical.APPROVED_POLICY.getValue("tools/numerical/physical.py"),
            ),
            GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED,
        )
        for ((name, digest) in closure) {
            val relative = "tools/numerical/portable/$name"
            assertEquals(digest, sha256(gitShow(repository, revision, relative)), name)
            assertEquals(
                GateConstants.PINNED_PROSPECTIVE_LOCAL_CHECKERS.getValue(name),
                sha256(gate.read(repository.resolve(relative))),
                name,
            )
        }
        val bound = GatesProspective.checkerBinding(repository, revision, gate)
        for ((name, digest) in closure) {
            assertEquals(digest, bound["tools/numerical/portable/$name"], name)
        }
        for ((path, digest) in GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED) {
            assertEquals(digest, bound.getValue(path), path)
        }
        val build = "tools/numerical/portable/build.gradle.kts"
        assertEquals(
            "fac77dd6282f67dd8593885a73f880d0bab6156eda93391a28cdbafb800fbdc3",
            GateConstants.P2_EXECUTABLE_LOCAL_DEPENDENCIES.getValue(build),
        )
        assertEquals(
            GateConstants.P2_JDK21_JDI_DEPENDENCIES.getValue(build),
            sha256(gitShow(repository, GateConstants.P2_JDK21_JDI_SOURCE_REVISION, build)),
        )
        assertEquals(
            GateConstants.APPROVED_P2_LOCAL_PRODUCERS,
            GatesProspective.p2ProducerBinding(repository, revision, gate),
        )
        for ((candidate, expected) in listOf(
            GateConstants.PROSPECTIVE_INVENTORY_FIX_CHECKER_REVISION to
                GateConstants.APPROVED_PROSPECTIVE_INVENTORY_FIX_CHECKERS,
            GateConstants.PROSPECTIVE_NUMERIC_PROBE_CHECKER_REVISION to
                GateConstants.APPROVED_PROSPECTIVE_NUMERIC_PROBE_CHECKERS,
        )) {
            val window = GatesProspective.checkerBinding(repository, candidate, gate)
            assertEquals(
                expected,
                expected.keys.associateWith { window.getValue("tools/numerical/portable/$it") },
                candidate,
            )
            assertFalse("tools/numerical/portable/numeric_producer.py" in window)
            assertFalse("tools/numerical/portable/pulley_jdi_v2.py" in window)
        }
    }

    test("the replay scratch window selects the exact producer bytes") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val previous = GateConstants.PROSPECTIVE_EXECUTABLE_CHECKER_REVISION
        val revision = GateConstants.PROSPECTIVE_REPLAY_SCRATCH_REVISION
        val current = gitText(repository, "rev-parse", "HEAD").trim()
        val relative = "tools/numerical/portable/numeric_producer.py"
        val old = GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS
            .getValue("numeric_producer.py")
        val replacement = GateConstants.PROSPECTIVE_REPLAY_SCRATCH_CHECKERS
            .getValue("numeric_producer.py")
        assertTrue(old != replacement)
        assertEquals(
            GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS +
                ("numeric_producer.py" to replacement),
            GateConstants.PROSPECTIVE_REPLAY_SCRATCH_CHECKERS,
        )
        val currentDigest = GateConstants.APPROVED_PROSPECTIVE_BASELINE_COMPAT_CHECKERS
            .getValue("numeric_producer.py")
        assertEquals(currentDigest, sha256(Files.readAllBytes(repository.resolve(relative))))
        assertEquals(
            currentDigest,
            GateConstants.PINNED_PROSPECTIVE_LOCAL_CHECKERS.getValue("numeric_producer.py"),
        )
        // The reference asserts its `checkout_bound == false` branch at HEAD: the committed
        // `FocusedBooleanArithmeticSourceTest.kt` is `f5536047`, but the thread-clone capture
        // closure still pins `b8eb3a06`, so no checkout satisfies the gate at this revision.
        assertRejectsAtHead(repository, current, gate)
        for ((candidate, expected) in listOf(
            previous to old, revision to replacement,
        )) {
            assertEquals(expected, sha256(gitShow(repository, candidate, relative)), candidate)
            val bound = GatesProspective.checkerBinding(repository, candidate, gate)
            assertEquals(expected, bound.getValue(relative), candidate)
            val dependencies = if (candidate == current) {
                GateConstants.ORDINARY_DIAGNOSTIC_THREAD_CLONE_CAPTURE_DEPENDENCIES
            } else {
                GateConstants.PROSPECTIVE_EXECUTABLE_CAPTURE_DEPENDENCIES
            }
            val closure = when (candidate) {
                current -> GateConstants.APPROVED_PROSPECTIVE_OBSERVER_ENV_REPLAY_CHECKERS
                revision -> GateConstants.PROSPECTIVE_REPLAY_SCRATCH_CHECKERS
                else -> GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS
            }
            assertEquals(
                closure.keys.map { "tools/numerical/portable/$it" }.toSet() +
                    GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED.keys +
                    dependencies.keys +
                    GatesNumerical.PROSPECTIVE_POLICY_PATH,
                bound.keys,
                candidate,
            )
            assertEquals(
                if (candidate == current) {
                    GateConstants.APPROVED_P2_OBSERVER_ENV_REPLAY_PRODUCERS
                } else {
                    GateConstants.APPROVED_P2_LOCAL_PRODUCERS
                },
                GatesProspective.p2ProducerBinding(repository, candidate, gate),
                candidate,
            )
        }
        val oldBytes = gitShow(repository, previous, relative)
        val newBytes = gitShow(repository, revision, relative)
        val local = repository.resolve(relative)
        for (candidate in listOf(previous, revision)) {
            val drifted = DriftSource(gate, read = { path -> oldBytes.takeIf { path == local } })
            val error = assertFailsWith<IllegalArgumentException>(candidate) {
                GatesProspective.checkerBinding(repository, candidate, drifted)
            }
            assertTrue(
                error.message!!.startsWith("prospective policy/checker blob differs"),
                error.message,
            )
        }
        for ((candidate, mistake) in listOf(previous to newBytes, revision to oldBytes)) {
            val drifted = DriftSource(
                gate,
                show = { _, revisionName, path ->
                    mistake.takeIf { revisionName == candidate && path == relative }
                },
            )
            val error = assertFailsWith<IllegalArgumentException>(candidate) {
                GatesProspective.checkerBinding(repository, candidate, drifted)
            }
            assertTrue(
                error.message!!.startsWith("prospective policy/checker blob differs"),
                error.message,
            )
        }
        val absent = DriftSource(
            gate,
            show = { _, revisionName, path ->
                if (revisionName == revision && path == relative) {
                    throw GitObjectMissing("absent")
                }
                null
            },
        )
        val error = assertFailsWith<IllegalArgumentException> {
            GatesProspective.checkerBinding(repository, revision, absent)
        }
        assertTrue(
            error.message!!.startsWith("prospective policy/checker blob differs"),
            error.message,
        )
    }

    test("the v6 window binds the reviewed source and preserves historical windows") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val reviewed = "0d5799e1c84f76c504b53f3eaf7468bca20a60eb"
        assertEquals(reviewed, GateConstants.PROSPECTIVE_V6_SOURCE_REVISION)
        val checker = GatesProspective.checkerBinding(repository, reviewed, gate)
        val producer = GatesProspective.p2ProducerBinding(repository, reviewed, gate)
        val expected = GateConstants.APPROVED_PROSPECTIVE_V6_CHECKERS +
            GateConstants.PROSPECTIVE_V6_CAPTURE_DEPENDENCIES +
            GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED
        for ((name, digest) in expected) {
            val relative =
                if (name.startsWith("tools/")) name else "tools/numerical/portable/$name"
            assertEquals(digest, sha256(gitShow(repository, reviewed, relative)), relative)
            val localDigest = GateConstants.ORDINARY_DIAGNOSTIC_CAPTURE_DEPENDENCIES[relative]
                ?: GateConstants.PINNED_PROSPECTIVE_LOCAL_CHECKERS[name]
                ?: digest
            assertEquals(localDigest, sha256(gate.read(repository.resolve(relative))), relative)
            assertEquals(digest, checker.getValue(relative), relative)
        }
        for ((relative, digest) in GateConstants.P2_V6_DEPENDENCIES) {
            assertEquals(digest, sha256(gitShow(repository, reviewed, relative)), relative)
            assertEquals(
                GateConstants.P2_ORDINARY_DIAGNOSTIC_DEPENDENCIES.getValue(relative),
                sha256(gate.read(repository.resolve(relative))),
                relative,
            )
        }
        assertEquals(GateConstants.APPROVED_P2_V6_PRODUCERS, producer)
        assertTrue("tools/numerical/portable/actual_capture_receipt.py" in checker)
        assertTrue("tools/numerical/portable/actual_trace.py" in checker)
        assertTrue("actual_capture_receipt" in GateConstants.PORTABLE_REPLAY_MODULES)
        assertTrue("actual_trace" in GateConstants.PORTABLE_REPLAY_MODULES)

        val historical = GateConstants.PROSPECTIVE_JVM8_AGENT_SOURCE_REVISION
        val older = GatesProspective.checkerBinding(repository, historical, gate)
        assertEquals(
            GateConstants.APPROVED_PROSPECTIVE_JVM8_AGENT_CHECKERS.getValue("numeric_producer.py"),
            older.getValue("tools/numerical/portable/numeric_producer.py"),
        )
        assertFalse("tools/numerical/portable/actual_trace.py" in older)
        assertEquals(
            GateConstants.APPROVED_P2_JVM8_PRODUCERS,
            GatesProspective.p2ProducerBinding(repository, historical, gate),
        )
        for (intermediate in listOf(
            "606a8541cdf6209791e58af88c5d8f82543b91a9",
            "02e9d287910aebd9301494a2ed745cdbb83ffc4c",
        )) {
            val checkerError = assertFailsWith<IllegalArgumentException>(intermediate) {
                GatesProspective.checkerBinding(repository, intermediate, gate)
            }
            assertTrue(
                checkerError.message!!.startsWith("prospective policy/checker blob differs"),
                checkerError.message,
            )
            val producerError = assertFailsWith<IllegalArgumentException>(intermediate) {
                GatesProspective.p2ProducerBinding(repository, intermediate, gate)
            }
            assertTrue(
                producerError.message!!.startsWith("reviewed P2 raw producer blob differs"),
                producerError.message,
            )
        }
    }

    test("the historical, assembled, and bridge checker windows are pinned") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val current = gitText(repository, "rev-parse", "HEAD").trim()
        val windows = listOf(
            GatesNumerical.PROSPECTIVE_HISTORICAL_POLICY_REVISION to
                GateConstants.APPROVED_PROSPECTIVE_POLICY_CHECKERS,
            GateConstants.PROSPECTIVE_INVENTORY_FIX_CHECKER_REVISION to
                GateConstants.APPROVED_PROSPECTIVE_INVENTORY_FIX_CHECKERS,
            GateConstants.PROSPECTIVE_ASSEMBLED_CHECKER_REVISION to
                GateConstants.APPROVED_PROSPECTIVE_ASSEMBLED_CHECKERS,
            "0533142a1358b2eebb3c3f36ae3dc1a8b01d9667" to
                GateConstants.APPROVED_PROSPECTIVE_ASSEMBLED_CHECKERS,
            GateConstants.PROSPECTIVE_BRIDGE_CHECKER_REVISION to
                GateConstants.APPROVED_PROSPECTIVE_CHECKERS,
            GateConstants.PROSPECTIVE_CHECKER_REVISION to
                GateConstants.APPROVED_PROSPECTIVE_CHECKERS,
            GatesNumerical.PROSPECTIVE_POLICY_REVISION to
                GateConstants.APPROVED_PROSPECTIVE_CHECKERS,
            "7d319d5027f2b10c11eae7f4574e6edf407449c0" to
                GateConstants.APPROVED_PROSPECTIVE_CHECKERS,
            "68339377a5d8dff1fd3dd6bf1ab17a32a0a402cd" to
                GateConstants.APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS,
            "dcc8211b51aad7bcb946417ad9019bd57cc6ecf1" to
                GateConstants.APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS,
        )
        assertRejectsAtHead(repository, current, gate)
        for ((revision, blobs) in windows) {
            GatesProspective.checkerBinding(repository, revision, gate)
            for ((filename, approved) in blobs) {
                val path = "tools/numerical/portable/$filename"
                assertEquals(approved, sha256(gitShow(repository, revision, path)), revision)
            }
        }
        val predates = assertFailsWith<IllegalArgumentException> {
            GatesProspective.checkerBinding(
                repository, "e35e3f1ec357b1c44b6d2b742e0d88bc2e91f767", gate,
            )
        }
        assertTrue(predates.message!!.contains("predates approved revisions"), predates.message)
        val producerError = assertFailsWith<IllegalArgumentException> {
            IndependentGates.sourceBinding(
                repository, GateConstants.PROSPECTIVE_BRIDGE_CHECKER_REVISION,
                GateConstants.APPROVED_P2_PRODUCERS.mapKeys {
                    "tools/numerical/portable/${it.key}"
                },
                "reviewed P2 raw producer",
            )
        }
        assertTrue(
            producerError.message!!.startsWith("reviewed P2 raw producer blob differs"),
            producerError.message,
        )
    }

    test("the represented checker revision binds exact current and historical bytes") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val current = "2bd0d70f36b521949641a5404bdb3fa5890f61d3"
        val relative = "tools/numerical/portable/prospective_compare.py"
        val expected = "469c23f619b5b37ab79fc75d7b73328aae122d712104bbe094cf2357eda1cd07"
        assertEquals(current, GateConstants.PROSPECTIVE_REPRESENTED_CHECKER_REVISION)
        assertEquals(
            expected,
            GateConstants.APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS
                .getValue("prospective_compare.py"),
        )
        assertEquals(expected, sha256(gitShow(repository, current, relative)))
        assertEquals(
            GateConstants.APPROVED_PROSPECTIVE_JVM8_CHECKERS.getValue("prospective_compare.py"),
            sha256(Files.readAllBytes(repository.resolve(relative))),
        )
        assertEquals(
            expected,
            GatesProspective.checkerBinding(repository, current, gate).getValue(relative),
        )
        assertEquals(
            GateConstants.APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS
                .getValue("prospective_compare.py"),
            GatesProspective.checkerBinding(
                repository, "4a15c77771d7cb65f0bfd303770b58c1afba29ef", gate,
            ).getValue(relative),
        )
        val local = repository.resolve(relative)
        val stale = DriftSource(
            gate,
            read = { path -> "altered".toByteArray().takeIf { path == local } },
        )
        val localError = assertFailsWith<IllegalArgumentException> {
            GatesProspective.checkerBinding(repository, current, stale)
        }
        assertTrue(
            localError.message!!.startsWith("prospective policy/checker blob differs"),
            localError.message,
        )
        val altered = DriftSource(
            gate,
            show = { _, revision, path ->
                if (revision == current && path == relative) {
                    gitShow(repository, current, relative) + "altered".toByteArray()
                } else {
                    null
                }
            },
        )
        val committedError = assertFailsWith<IllegalArgumentException> {
            GatesProspective.checkerBinding(repository, current, altered)
        }
        assertTrue(
            committedError.message!!.startsWith("prospective policy/checker blob differs"),
            committedError.message,
        )
    }

    test("the numeric probe window preserves the historical hashes") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val relative = "tools/numerical/portable/prospective_compare.py"
        val current = "375812a97de8cb3e439fc2a204e029de1a6de338"
        val previous = "dcc8211b51aad7bcb946417ad9019bd57cc6ecf1"
        val oldDigest = "469c23f619b5b37ab79fc75d7b73328aae122d712104bbe094cf2357eda1cd07"
        val newDigest = "2d254d2f2d5117ed81449000beb0c3373822af80d49424605c390ee83c90aeeb"
        assertEquals(current, GateConstants.PROSPECTIVE_NUMERIC_PROBE_CHECKER_REVISION)
        assertEquals(
            oldDigest,
            GateConstants.APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS
                .getValue("prospective_compare.py"),
        )
        assertEquals(
            GateConstants.APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS +
                ("prospective_compare.py" to newDigest),
            GateConstants.APPROVED_PROSPECTIVE_NUMERIC_PROBE_CHECKERS,
        )
        assertEquals(
            GateConstants.APPROVED_PROSPECTIVE_OBSERVER_ENV_REPLAY_CHECKERS,
            GateConstants.PINNED_PROSPECTIVE_LOCAL_CHECKERS,
        )
        for ((revision, digest) in listOf(
            current to newDigest,
            previous to oldDigest,
            GateConstants.PROSPECTIVE_REPRESENTED_CHECKER_REVISION to oldDigest,
            "4a15c77771d7cb65f0bfd303770b58c1afba29ef" to
                GateConstants.APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS
                    .getValue("prospective_compare.py"),
        )) {
            val bound = GatesProspective.checkerBinding(repository, revision, gate)
            assertEquals(digest, bound.getValue(relative), revision)
            assertEquals(
                GatesNumerical.PROSPECTIVE_POLICY_SHA256,
                bound.getValue(GatesNumerical.PROSPECTIVE_POLICY_PATH),
                revision,
            )
        }
        val oldBytes = gitShow(repository, previous, relative)
        val newBytes = gitShow(repository, current, relative)
        assertEquals(oldDigest, sha256(oldBytes))
        assertEquals(newDigest, sha256(newBytes))
        for ((revision, mistake) in listOf(
            current to oldBytes,
            previous to newBytes,
            current to newBytes + "\n# altered\n".toByteArray(),
        )) {
            val drifted = DriftSource(
                gate,
                show = { _, revisionName, path ->
                    mistake.takeIf { revisionName == revision && path == relative }
                },
            )
            val error = assertFailsWith<IllegalArgumentException>(revision) {
                GatesProspective.checkerBinding(repository, revision, drifted)
            }
            assertTrue(
                error.message!!.startsWith("prospective policy/checker blob differs"),
                error.message,
            )
        }
        for (filename in GateConstants.APPROVED_PROSPECTIVE_CHECKERS.keys) {
            val path = repository.resolve("tools/numerical/portable/$filename")
            val surfaces = listOf(
                DriftSource(
                    gate,
                    read = { target -> "stale".toByteArray().takeIf { target == path } },
                ),
                DriftSource(
                    gate,
                    read = { target ->
                        if (target == path) throw FileNotFoundException(target.toString())
                        null
                    },
                ),
                DriftSource(
                    gate,
                    show = { _, revisionName, target ->
                        if (revisionName == current &&
                            target == "tools/numerical/portable/$filename"
                        ) {
                            throw GitObjectMissing("absent")
                        }
                        null
                    },
                ),
            )
            for ((index, surface) in surfaces.withIndex()) {
                val error = assertFailsWith<IllegalArgumentException>("$filename/$index") {
                    GatesProspective.checkerBinding(repository, current, surface)
                }
                assertTrue(
                    error.message!!.startsWith("prospective policy/checker blob differs"),
                    error.message,
                )
            }
        }
    }

    test("the inventory fix window preserves the numeric probe bytes") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val relative = "tools/numerical/portable/prospective_compare.py"
        val inventoryRevision = "df316d8900f850d22f9c933f6aac8250b1e10ed1"
        val numericRevision = "375812a97de8cb3e439fc2a204e029de1a6de338"
        val numericDigest = "2d254d2f2d5117ed81449000beb0c3373822af80d49424605c390ee83c90aeeb"
        val inventoryDigest = "ff7a428ff4fc39ad7ef1e77b605c1ffd39ef138bdc62599e416a4a0b9e80ae83"
        assertEquals(
            inventoryRevision,
            GateConstants.PROSPECTIVE_INVENTORY_FIX_CHECKER_REVISION,
        )
        assertEquals(
            numericDigest,
            GateConstants.APPROVED_PROSPECTIVE_NUMERIC_PROBE_CHECKERS
                .getValue("prospective_compare.py"),
        )
        assertEquals(
            GateConstants.APPROVED_PROSPECTIVE_NUMERIC_PROBE_CHECKERS +
                ("prospective_compare.py" to inventoryDigest),
            GateConstants.APPROVED_PROSPECTIVE_INVENTORY_FIX_CHECKERS,
        )
        for ((revision, digest) in listOf(
            inventoryRevision to inventoryDigest,
            numericRevision to numericDigest,
        )) {
            assertEquals(
                digest,
                GatesProspective.checkerBinding(repository, revision, gate).getValue(relative),
                revision,
            )
        }
        assertRejectsAtHead(repository, gitText(repository, "rev-parse", "HEAD").trim(), gate)
        assertEquals(
            GateConstants.APPROVED_PROSPECTIVE_JVM8_CHECKERS.getValue("prospective_compare.py"),
            sha256(
                gitShow(
                    repository, gitText(repository, "rev-parse", "HEAD").trim(), relative,
                ),
            ),
        )
        val oldBytes = gitShow(repository, numericRevision, relative)
        val newBytes = gitShow(repository, inventoryRevision, relative)
        assertEquals(numericDigest, sha256(oldBytes))
        assertEquals(inventoryDigest, sha256(newBytes))
        val drifted = DriftSource(
            gate,
            show = { _, revision, path ->
                newBytes.takeIf { revision == numericRevision && path == relative }
            },
        )
        val error = assertFailsWith<IllegalArgumentException> {
            GatesProspective.checkerBinding(repository, numericRevision, drifted)
        }
        assertTrue(
            error.message!!.startsWith("prospective policy/checker blob differs"),
            error.message,
        )
    }

    test("the prospective catalog binding keeps the historical and current windows") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val path = GatesNumerical.PROSPECTIVE_POLICY_PATH
        val historicalRevision = "7213238591db1611da86cdec075978190ca6d52f"
        val previousRevision = "e038c334caa07a1547b86839f5d467c5f73ec708"
        val currentRevision = "83914cfc86f3add09ea65c89dc5b3e6035f709a0"
        val historicalSha = "5c8e2ca48a2128b99b2f52188f0f556c3dad3030bde00975bc80d2a25b0c74bb"
        val previousSha = "1b80b7c198d510ab16784348661053a4bde6507548f5ec12d4a460287ec7b484"
        val currentSha = "fab269814476a5a0c1d65f268f6c4177bb942ea8e7cdf1ea5ab8d4d9dcd2e160"
        assertEquals(currentRevision, GatesNumerical.PROSPECTIVE_POLICY_REVISION)
        assertEquals(currentSha, GatesNumerical.PROSPECTIVE_POLICY_SHA256)
        assertEquals(currentSha, sha256(Files.readAllBytes(repository.resolve(path))))
        val currentCatalog = GatesNumerical.approvedProspectiveCatalog(repository)
        assertEquals(318, (currentCatalog["cases"] as JsonObject).size)
        assertEquals(566, (currentCatalog["paths"] as JsonArray).size)
        assertEquals(92, (currentCatalog["path_sets"] as JsonArray).size)
        assertEquals("UNPASSED", Py.str(currentCatalog["qualification"]))
        val historicalCatalog = StrictObjectJson.parse(
            gitShow(repository, historicalRevision, path).toString(Charsets.UTF_8),
        ) as JsonObject
        val previousCatalog = StrictObjectJson.parse(
            gitShow(repository, previousRevision, path).toString(Charsets.UTF_8),
        ) as JsonObject
        assertEquals(
            setOf("baseline_trace_sha256", "baseline_fixture_source_sha256"),
            currentCatalog.filter { (key, value) -> historicalCatalog[key] != value }.keys,
        )
        assertEquals(
            setOf("baseline_fixture_source_sha256"),
            currentCatalog.filter { (key, value) -> previousCatalog[key] != value }.keys,
        )
        for ((revision, expected) in listOf(
            historicalRevision to historicalSha,
            "$previousRevision^" to historicalSha,
            previousRevision to previousSha,
            "$currentRevision^" to previousSha,
            currentRevision to currentSha,
        )) {
            val committed = gitShow(repository, revision, path)
            assertEquals(expected, sha256(committed), revision)
            assertEquals(
                expected,
                GatesProspective.checkerBinding(repository, revision, gate).getValue(path),
                revision,
            )
            assertEquals(
                StrictObjectJson.parse(committed.toString(Charsets.UTF_8)),
                GatesNumerical.approvedProspectiveCatalog(repository, revision),
                revision,
            )
        }
        val staleReference = DriftSource(
            gate,
            show = { _, revision, relative ->
                if (revision == currentRevision && relative == path) {
                    gitShow(repository, historicalRevision, path)
                } else {
                    null
                }
            },
        )
        val staleError = assertFailsWith<IllegalArgumentException> {
            GatesProspective.checkerBinding(repository, currentRevision, staleReference)
        }
        assertTrue(
            staleError.message!!.startsWith("prospective policy/checker blob differs"),
            staleError.message,
        )
        val localCatalog = repository.resolve(path)
        val altered = DriftSource(
            gate,
            read = { file ->
                if (file == localCatalog) {
                    Files.readAllBytes(file) + " ".toByteArray()
                } else {
                    null
                }
            },
        )
        val alteredError = assertFailsWith<IllegalArgumentException> {
            GatesProspective.checkerBinding(repository, currentRevision, altered)
        }
        assertTrue(
            alteredError.message!!.startsWith("prospective policy/checker blob differs"),
            alteredError.message,
        )
    }

    test("the reviewed P2 source blobs are pinned to the approved revision") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val historical = GateConstants.PROSPECTIVE_CHECKER_REVISION
        val revision = GateConstants.P2_CLASS_LOAD_REVISION
        assertEquals("5b750850277a6e9d494483dc5fa2791b6d292233", revision)
        val current = gitText(repository, "rev-parse", "HEAD").trim()
        assertRejectsAtHead(repository, current, gate)
        for (candidate in listOf(historical, "$revision^", revision)) {
            GatesProspective.p2ProducerBinding(repository, candidate, gate)
        }
        val predates = assertFailsWith<IllegalArgumentException> {
            GatesProspective.p2ProducerBinding(
                repository, GateConstants.PROSPECTIVE_BRIDGE_CHECKER_REVISION, gate,
            )
        }
        assertTrue(
            predates.message!!.contains("predates reviewed P2 raw producer"),
            predates.message,
        )
        assertEquals(
            "e51e768c7d2c9075b9e1900b2bf3ad0fdacbda42bb3eb0d6f52f49492b546675",
            GateConstants.APPROVED_P2_HISTORICAL_PRODUCERS.getValue("actual_arithmetic.py"),
        )
        assertEquals(
            "b96043c57a918dabe8425961b02aff930a704e592c32baffc5645b94b84ce835",
            GateConstants.APPROVED_P2_CLASS_LOAD_PRODUCERS.getValue("actual_arithmetic.py"),
        )
        assertEquals(
            "5f02723e84401f612f4b7a1c72d7686b651e486e5153180ff80e2ec512faa1bf",
            GateConstants.APPROVED_P2_PRODUCERS.getValue("actual_arithmetic.py"),
        )
        val arithmeticPath = "tools/numerical/portable/actual_arithmetic.py"
        for (reviewed in listOf(
            "6408495750659a46eb0e2fb6f2167186f6eca2ef",
            "ffdc8ba9b600732e6927e38e7d3da43a519994a4",
        )) {
            assertEquals(
                GateConstants.APPROVED_P2_CLASS_LOAD_PRODUCERS.getValue("actual_arithmetic.py"),
                sha256(gitShow(repository, reviewed, arithmeticPath)),
                reviewed,
            )
        }
        for ((name, approved) in GateConstants.APPROVED_P2_HISTORICAL_PRODUCERS) {
            assertEquals(
                approved,
                sha256(gitShow(repository, historical, "tools/numerical/portable/$name")),
                name,
            )
        }
        for ((name, approved) in GateConstants.APPROVED_P2_CLASS_LOAD_PRODUCERS) {
            assertEquals(
                approved,
                sha256(gitShow(repository, revision, "tools/numerical/portable/$name")),
                name,
            )
        }
        for ((reviewed, blobs) in listOf(
            GateConstants.P2_NUMERICAL_ARCHIVE_OWNER_REVISION to
                GateConstants.APPROVED_P2_PRE_ARITHMETIC_PRODUCERS,
            GateConstants.P2_NUMERICAL_ARCHIVE_REVISION to
                GateConstants.APPROVED_P2_PRE_ARITHMETIC_PRODUCERS,
            GateConstants.P2_CANONICAL_ARCHIVE_OWNER_REVISION to
                GateConstants.APPROVED_P2_OWNER_CANONICAL_PRODUCERS,
            GateConstants.P2_CANONICAL_ARCHIVE_ASSEMBLY_REVISION to
                GateConstants.APPROVED_P2_PRE_ORIGINAL_OBJECT_PRODUCERS,
            GateConstants.P2_ORIGINAL_OBJECT_OWNER_REVISION to
                GateConstants.APPROVED_P2_ORIGINAL_OBJECT_OWNER_PRODUCERS,
            GateConstants.P2_ORIGINAL_OBJECT_ASSEMBLY_REVISION to
                GateConstants.APPROVED_P2_PRODUCERS,
        )) {
            for ((name, approved) in blobs) {
                assertEquals(
                    approved,
                    sha256(gitShow(repository, reviewed, "tools/numerical/portable/$name")),
                    "$reviewed/$name",
                )
            }
        }
        for ((name, approved) in GateConstants.APPROVED_P2_CURRENT_PRODUCERS) {
            assertEquals(
                approved,
                sha256(
                    gitShow(
                        repository,
                        GateConstants.P2_CURRENT_ASSEMBLY_REVISION,
                        "tools/numerical/portable/$name",
                    ),
                ),
                name,
            )
        }
        val staleCurrent = DriftSource(
            gate,
            read = { path ->
                if (path == repository.resolve("tools/numerical/portable/actual_arithmetic.py")) {
                    "stale".toByteArray()
                } else {
                    null
                }
            },
        )
        val staleError = assertFailsWith<IllegalArgumentException> {
            GatesProspective.p2ProducerBinding(repository, historical, staleCurrent)
        }
        assertTrue(
            staleError.message!!.startsWith("reviewed P2 raw producer blob differs"),
            staleError.message,
        )
    }

    test("the executable closure rejects local and candidate drift on every surface") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val revision = GateConstants.PROSPECTIVE_EXECUTABLE_CHECKER_REVISION
        for (name in GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS.keys) {
            val relative = "tools/numerical/portable/$name"
            for ((index, surface) in driftSurfaces(gate, repository, relative, revision)
                .withIndex()
            ) {
                val error = assertFailsWith<IllegalArgumentException>("$name/$index") {
                    GatesProspective.checkerBinding(repository, revision, surface)
                }
                assertTrue(
                    error.message!!.startsWith("prospective policy/checker blob differs"),
                    error.message,
                )
            }
        }
        for (relative in GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED.keys) {
            for ((index, surface) in driftSurfaces(gate, repository, relative, revision)
                .withIndex()
            ) {
                val error = assertFailsWith<IllegalArgumentException>("$relative/$index") {
                    GatesProspective.checkerBinding(repository, revision, surface)
                }
                assertTrue(
                    error.message!!.startsWith("prospective policy/checker blob differs"),
                    error.message,
                )
            }
        }
    }

    test("target arithmetic requires a raw target process and the approved oracle pin") {
        val repository = repositoryRoot()
        val case = "geometry-boundary-s0-o0-d0"
        val candidate = GatesNumerical.PROSPECTIVE_POLICY_REVISION
        val sourceSha = GatesNumerical.verifiedNumericalSourceSha256(repository, candidate)
        val identity = buildJsonObject {
            put("case_id", JsonPrimitive(case))
            put("candidate_commit", JsonPrimitive(candidate))
            put("source_sha256", JsonPrimitive(sourceSha))
            put("artifact_sha256", JsonPrimitive("a".repeat(64)))
            put("trace_sha256", JsonPrimitive("b".repeat(64)))
        }
        val root = Files.createTempDirectory("target-arithmetic")
        try {
            val unbound = assertFailsWith<IllegalArgumentException> {
                GatesProspective.targetArithmeticEvidence(root, identity, identity, repository)
            }
            assertTrue(unbound.message!!.contains("arithmetic producer manifest"), unbound.message)
            val payload = root.resolve("target-payload.json")
            Files.writeString(
                payload,
                """{"case_id":"$case","runtime":"Java 21",""" +
                    """"operations":[{"kind":"binary64","value":"0"}]}""",
            )
            val output = root.resolve("target-stdout.txt")
            Files.writeString(output, "ARITHMETIC_CASE=$case\n")
            val process = root.resolve("target-process.json")
            Files.writeString(
                process,
                """{"command":["java","CandidateArithmetic"],"exit_code":0,""" +
                    """"started_ns":1,"finished_ns":2,"stdout":"target-stdout.txt",""" +
                    """"stdout_sha256":"${sha256(Files.readAllBytes(output))}"}""",
            )
            val audit = buildJsonObject {
                identity.forEach { (key, value) -> put(key, value) }
                put("schema", JsonPrimitive("target-arithmetic-evidence/1"))
                put("oracle_revision", JsonPrimitive(GateConstants.ROTATION_ORACLE_REVISION))
                put("oracle_sha256", JsonPrimitive(GateConstants.ROTATION_ORACLE_SHA256))
                put("target_payload", JsonPrimitive("target-payload.json"))
                put(
                    "target_payload_sha256",
                    JsonPrimitive(sha256(Files.readAllBytes(payload))),
                )
                put("process_receipt", JsonPrimitive("target-process.json"))
                put(
                    "process_receipt_sha256",
                    JsonPrimitive(sha256(Files.readAllBytes(process))),
                )
            }
            assertEquals(
                "NOT_RUN",
                GatesProspective.targetArithmeticEvidence(root, audit, identity, repository),
            )
            val wrongOracle = buildJsonObject {
                audit.forEach { (key, value) -> if (key != "oracle_sha256") put(key, value) }
                put("oracle_sha256", JsonPrimitive("f".repeat(64)))
            }
            val oracleError = assertFailsWith<IllegalArgumentException> {
                GatesProspective.targetArithmeticEvidence(root, wrongOracle, identity, repository)
            }
            assertTrue(
                oracleError.message!!.contains("approved arithmetic oracle"),
                oracleError.message,
            )
            val unnamedOracle = buildJsonObject {
                audit.forEach { (key, value) -> put(key, value) }
                put(
                    "oracle",
                    buildJsonObject { put("binding", JsonPrimitive("missing.json")) },
                )
            }
            val contractError = assertFailsWith<IllegalArgumentException> {
                GatesProspective.targetArithmeticEvidence(
                    root, unnamedOracle, identity, repository,
                )
            }
            assertTrue(
                contractError.message!!.contains("oracle raw contract"),
                contractError.message,
            )
            val files = linkedMapOf(
                "binding" to "binding.json",
                "receipt" to "producer.json",
                "target_source" to "source.kt",
                "artifact" to "core.jar",
            )
            for (name in files.values) {
                Files.write(root.resolve(name), "raw arithmetic producer bytes".toByteArray())
            }
            val raw = LinkedHashMap<String, JsonElement>()
            files.forEach { (key, name) -> raw[key] = JsonPrimitive(name) }
            raw["target_source_git_path"] = JsonPrimitive("README.md")
            for ((key, name) in files) {
                raw[key + "_sha256"] =
                    JsonPrimitive(sha256(Files.readAllBytes(root.resolve(name))))
            }
            val withOracle = buildJsonObject {
                audit.forEach { (key, value) -> put(key, value) }
                put("oracle", JsonObject(raw))
            }
            val artifactError = assertFailsWith<IllegalArgumentException> {
                GatesProspective.targetArithmeticEvidence(root, withOracle, identity, repository)
            }
            assertTrue(artifactError.message!!.contains("artifact differs"), artifactError.message)
            val wrongBinding = buildJsonObject {
                withOracle.forEach { (key, value) -> put(key, value) }
                put(
                    "oracle",
                    JsonObject(raw + ("binding_sha256" to JsonPrimitive("e".repeat(64)))),
                )
            }
            val bindingError = assertFailsWith<IllegalArgumentException> {
                GatesProspective.targetArithmeticEvidence(root, wrongBinding, identity, repository)
            }
            assertTrue(
                bindingError.message!!.contains("oracle binding differs"),
                bindingError.message,
            )
            assertEquals(
                GateConstants.ROTATION_ORACLE_SHA256,
                GatesProspective.approvedRotationOracle(repository),
            )
        } finally {
            deleteRecursively(root)
        }
    }

    test("the build cleanup window pins the source commit and the new helper") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val revision = GateConstants.ORDINARY_DIAGNOSTIC_BUILD_CLEANUP_SOURCE_REVISION
        assertEquals("0949a3de445395ac76f3c786cedd32729903cfc4", revision)
        val source = GateConstants.ORDINARY_DIAGNOSTIC_BUILD_CLEANUP_SOURCE_DEPENDENCIES
        assertEquals(
            1,
            (source.keys -
                GateConstants.ORDINARY_DIAGNOSTIC_REMEDY_SOURCE_DEPENDENCIES.keys).size,
        )
        val bound = GatesProspective.checkerBinding(repository, revision, gate)
        assertEquals(
            GateConstants.APPROVED_P2_OBSERVER_ENV_REPLAY_PRODUCERS,
            GatesProspective.p2ProducerBinding(repository, revision, gate),
        )
        for ((relative, expected) in source) {
            assertEquals(expected, sha256(gitShow(repository, revision, relative)), relative)
            assertEquals(expected, bound.getValue(relative), relative)
        }
    }

    test("the build pid retry pins the final source") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val revision = GateConstants.ORDINARY_DIAGNOSTIC_BUILD_PID_SOURCE_REVISION
        val source = GateConstants.ORDINARY_DIAGNOSTIC_BUILD_PID_SOURCE_DEPENDENCIES
        assertEquals("f5007605c8058c389e2e025e10edb9d03178401c", revision)
        assertEquals(
            0,
            (source.keys -
                GateConstants.ORDINARY_DIAGNOSTIC_BUILD_CLEANUP_SOURCE_DEPENDENCIES.keys).size,
        )
        val bound = GatesProspective.checkerBinding(repository, revision, gate)
        assertEquals(
            GateConstants.APPROVED_P2_OBSERVER_ENV_REPLAY_PRODUCERS,
            GatesProspective.p2ProducerBinding(repository, revision, gate),
        )
        val path = "tools/numerical/portable/ordinary_snapshot/test_control.py"
        assertEquals(source.getValue(path), sha256(gitShow(repository, revision, path)))
        assertEquals(source.getValue(path), bound.getValue(path))
    }

    test("the build lifecycle window pins its source and rejects a mutated helper") {
        val repository = repositoryRoot()
        val gate = pinnedCheckout(repository)
        val revision = GateConstants.ORDINARY_DIAGNOSTIC_BUILD_LIFECYCLE_SOURCE_REVISION
        val source = GateConstants.ORDINARY_DIAGNOSTIC_BUILD_LIFECYCLE_SOURCE_DEPENDENCIES
        assertEquals("74f958fc7ea7bf5031275f6e2e41d3d268888dfb", revision)
        val bound = GatesProspective.checkerBinding(repository, revision, gate)
        assertEquals(source, source.keys.associateWith { bound.getValue(it) })
        assertEquals(
            GateConstants.APPROVED_P2_OBSERVER_ENV_REPLAY_PRODUCERS,
            GatesProspective.p2ProducerBinding(repository, revision, gate),
        )
        for ((relative, expected) in source) {
            assertEquals(expected, sha256(gitShow(repository, revision, relative)), relative)
        }
        val helper = repository.resolve(
            "tools/numerical/portable/ordinary_snapshot/adverse_build_child.py",
        )
        val mutated = DriftSource(
            gate,
            read = { path -> "changed helper bytes".toByteArray().takeIf { path == helper } },
        )
        val checkerError = assertFailsWith<IllegalArgumentException> {
            GatesProspective.checkerBinding(repository, revision, mutated)
        }
        assertTrue(
            checkerError.message!!.startsWith("prospective policy/checker blob differs"),
            checkerError.message,
        )
        val producerError = assertFailsWith<IllegalArgumentException> {
            GatesProspective.p2ProducerBinding(repository, revision, mutated)
        }
        assertTrue(
            producerError.message!!.startsWith("JDK 21 JDI producer blob differs"),
            producerError.message,
        )
    }
}

/**
 * The reference's rejecting branch at a revision whose recorded closure no longer matches its tree.
 *
 * `2fd9a350` converted the portable numerical suites to TestBalloon and committed
 * `FocusedBooleanArithmeticSourceTest.kt` as `f5536047`, leaving the thread-clone capture closure
 * pinned to `b8eb3a06`. The gate therefore rejects every candidate that inherits that closure,
 * including the current checkout, which is the behaviour asserted here.
 */
private fun assertRejectsAtHead(repository: Path, revision: String, gate: GateSource) {
    val error = assertFailsWith<IllegalArgumentException>(revision) {
        GatesProspective.checkerBinding(repository, revision, gate)
    }
    assertTrue(
        error.message!!.startsWith("prospective policy/checker blob differs"),
        error.message,
    )
}

/** The reference's `checkout_matches_commit`: does the working tree hold the committed bytes? */
private fun checkoutMatchesCommit(repository: Path, paths: List<String>): Boolean =
    paths.all {
        Files.readAllBytes(repository.resolve(it)).contentEquals(gitShow(repository, "HEAD", it))
    }

/** `subprocess.check_output(["git", ... "show", f"{revision}:{path}"])`. */
private fun gitShow(repository: Path, revision: String, path: String): ByteArray {
    val process = ProcessBuilder(
        "git", "--no-replace-objects", "-C", repository.toString(), "show", "$revision:$path",
    ).start()
    val output = process.inputStream.use { it.readBytes() }
    process.errorStream.close()
    if (process.waitFor() != 0) error("git show $revision:$path is unavailable")
    return output
}

/** `subprocess.check_output(["git", ...])` as text. */
private fun gitText(repository: Path, vararg arguments: String): String {
    val process = ProcessBuilder(listOf("git", "-C", repository.toString()) + arguments).start()
    val output = process.inputStream.use { it.readBytes() }
    process.errorStream.close()
    if (process.waitFor() != 0) error("git ${arguments.joinToString(" ")} is unavailable")
    return output.toString(Charsets.UTF_8)
}

private fun sha256(bytes: ByteArray): String = CorpusFiles.digest(bytes)

/** The recorded digest of every local dependency the two binding verifiers compare. */
private val PINNED_LOCAL_TABLES: List<Map<String, String>>
    get() = listOf(
        GateConstants.PINNED_PROSPECTIVE_LOCAL_CHECKERS.mapKeys {
            "tools/numerical/portable/${it.key}"
        },
        GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED,
        GateConstants.ORDINARY_DIAGNOSTIC_THREAD_CLONE_CAPTURE_DEPENDENCIES,
        GateConstants.P2_ORDINARY_DIAGNOSTIC_THREAD_CLONE_DEPENDENCIES,
        GateConstants.PINNED_P2_CURRENT_LOCAL_PRODUCERS.mapKeys {
            "tools/numerical/portable/${it.key}"
        },
        GateConstants.P2_ORDINARY_DIAGNOSTIC_PORTABLE_STAGE_DEPENDENCIES.filterKeys {
            it in (GateConstants.P2_BASELINE_COMPAT_DEPENDENCIES.keys -
                GateConstants.P2_EXECUTABLE_LOCAL_DEPENDENCIES.keys)
        },
    )

/**
 * A [GateSource] whose local half holds the recorded bytes of every drifted pin.
 *
 * The reference cases assume the checkout still holds the pinned bytes. Four portable test
 * sources and `tools/numerical/portable/build.gradle.kts` were changed by `2fd9a350` after those
 * pins were recorded, so this checkout no longer matches the tables. The recorded bytes are read
 * back from the commit that recorded them, which is what the reference's premise asserts; the
 * unmodified checkout still fails the gates, and the cases assert that too.
 */
private fun pinnedCheckout(repository: Path): GateSource {
    val substituted = LinkedHashMap<Path, ByteArray>()
    for ((relative, expected) in PINNED_LOCAL_TABLES.flatMap { it.entries }) {
        val path = realPath(repository.resolve(relative))
        val local = try {
            Files.readAllBytes(path)
        } catch (error: java.io.IOException) {
            null
        }
        if (local != null && sha256(local) == expected) continue
        substituted[path] = committedBytesFor(repository, relative, expected)
    }
    return DriftSource(read = { path -> substituted[realPath(path)] })
}

/** The resolved path, so a pinned table key matches however the checkout is named. */
private fun realPath(path: Path): Path = try {
    path.toRealPath()
} catch (error: java.io.IOException) {
    path.toAbsolutePath().normalize()
}

/** The committed bytes of [relative] whose digest is [expected]. */
private fun committedBytesFor(repository: Path, relative: String, expected: String): ByteArray {
    val revisions = gitText(repository, "log", "--format=%H", "--", relative)
        .lines().filter { it.isNotEmpty() }
    for (revision in revisions) {
        val candidate = gitShow(repository, revision, relative)
        if (sha256(candidate) == expected) return candidate
    }
    error("no committed revision of $relative holds the pinned bytes")
}

/** The four drift surfaces the reference injects for one path: stale, absent, and both by Git. */
private fun driftSurfaces(
    gate: GateSource,
    repository: Path,
    relative: String,
    revision: String,
): List<GateSource> {
    val local = repository.resolve(relative)
    return listOf(
        DriftSource(gate, read = { path -> "substituted".toByteArray().takeIf { path == local } }),
        DriftSource(
            gate,
            read = { path ->
                if (path == local) throw FileNotFoundException(path.toString())
                null
            },
        ),
        DriftSource(
            gate,
            show = { _, revisionName, path ->
                "substituted".toByteArray()
                    .takeIf { revisionName == revision && path == relative }
            },
        ),
        DriftSource(
            gate,
            show = { _, revisionName, path ->
                if (revisionName == revision && path == relative) {
                    throw GitObjectMissing("absent")
                }
                null
            },
        ),
    )
}

/**
 * A [GateSource] that substitutes one local read or one committed read.
 *
 * The reference injects the same drift with `mock.patch.object(Path, "read_bytes", ...)` and
 * `mock.patch.object(subprocess, "check_output", ...)`; a `null` result means "keep the real one".
 */
private class DriftSource(
    private val base: GateSource = GateGit,
    private val read: (Path) -> ByteArray? = { null },
    private val show: (Path, String, String) -> ByteArray? = { _, _, _ -> null },
) : GateSource() {
    override fun read(path: Path): ByteArray = read.invoke(path) ?: base.read(path)

    override fun show(repository: Path, revision: String, path: String): ByteArray =
        show.invoke(repository, revision, path) ?: base.show(repository, revision, path)

    override fun sourceRoot(): Path = base.sourceRoot()
}
