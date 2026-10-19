import hashlib
import json
import subprocess
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

import collection
import independent_gates


ROOT = Path(__file__).resolve().parents[2]
HEAD = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                               text=True).strip()


class CollectionTests(unittest.TestCase):
    def test_empty_collection_keeps_all_lanes_not_run_without_signature(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "collection"
            result = collection.collect(ROOT, HEAD, [], output)
            self.assertEqual("NOT_RUN", result["status"])
            self.assertEqual("MISSING", result["independent_signature"])
            self.assertEqual(112, result["required_lanes"])
            self.assertEqual(set(collection.REQUIRED), set(result["missing_artifacts"]))
            self.assertEqual([
                "all 112 exact-source common gate archives and runtime identities",
                "independently audited archive digests and 21-target artifact hashes",
                "complete candidate manifest bound to a verified staged audit",
                "exact staged repository bytes available to the public qualifier",
                "detached Ed25519 audit signature and pinned trusted public-key fingerprint",
            ], result["external_inputs_required"])
            inputs = json.loads((output / "assembly-inputs.json").read_text())
            self.assertEqual(112, len(inputs))
            self.assertTrue(all(value == {"archives": {}} for value in inputs.values()))
            self.assertTrue(collection.verify_collection(ROOT, HEAD, [], output))
            candidate = json.loads((output / "candidate-manifest-inputs.json").read_text())
            self.assertEqual("INCOMPLETE", candidate["status"])
            self.assertTrue(all(value["runtime_identity"] is None
                                for value in candidate["lanes"].values()))

    def test_wrong_sha_and_duplicate_route_are_failed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrong = "0" * 40 if HEAD != "0" * 40 else "1" * 40
            bad = root / f"full-ci-{wrong}"
            bad.mkdir()
            (bad / "raw.log").write_text("failed exact-source producer\n")
            result = collection.collect(ROOT, HEAD, [(bad.name, bad)], root / "wrong")
            self.assertEqual("FAILED", result["status"])
            self.assertIn("candidate", result["artifacts"][0]["reason"])
            self.assertEqual(collection.digest(bad / "raw.log"),
                             result["artifacts"][0]["files"]["raw.log"])
            self.assertIn("full-ci", result["missing_artifacts"])
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            name = f"duplicate-provider-{HEAD}"
            duplicated = collection.collect(ROOT, HEAD, [(name, first), (name, second)],
                                            root / "duplicate")
            self.assertEqual("FAILED", duplicated["status"])
            self.assertIn("duplicate producer artifact route",
                          duplicated["artifacts"][1]["reason"])

    def test_forged_pass_cannot_enter_unsigned_map(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / f"duplicate-provider-{HEAD}"
            artifact.mkdir()
            (artifact / "receipt.json").write_text(json.dumps(
                {"schema": 1, "candidate_sha": HEAD,
                 "source_tree": collection.source_tree(ROOT, HEAD), "status": "PASSED"}))
            result = collection.collect(ROOT, HEAD, [(artifact.name, artifact)],
                                        root / "collection")
            self.assertEqual("FAILED", result["status"])
            self.assertIn("inventory", result["artifacts"][0]["reason"])
            inputs = json.loads((root / "collection/assembly-inputs.json").read_text())
            self.assertEqual({"duplicate-provider": str(artifact.resolve())},
                             inputs["jvm:Java:current:default"]["archives"])
            self.assertTrue(all(value == {"archives": {}} for lane, value in inputs.items()
                                if lane != "jvm:Java:current:default"))
            assembly = independent_gates.evaluate_assembly(
                independent_gates.load_approved_manifest(ROOT), HEAD, inputs, ROOT)
            self.assertEqual("FAILED", assembly["status"])
            self.assertEqual("FAILED", assembly["lane_results"]["jvm:Java:current:default"]
                             ["gates"]["duplicate-provider"]["status"])
            self.assertFalse(assembly["qualify_adapter"])

    def test_missing_external_signature_keeps_audit_ingestion_not_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "collection"
            collection.collect(ROOT, HEAD, [], output)
            external = root / "external"
            external.mkdir()
            (external / "audit.json").write_text(json.dumps(
                {"schema": 1, "candidate_sha": HEAD, "status": "PASSED"}))
            result = collection.ingest_external(ROOT, HEAD, [], output, external,
                                                trusted_key_sha256="a" * 64)
            self.assertEqual("NOT_RUN", result["status"])
            self.assertIn("audit.sig", result["missing_external_inputs"])
            self.assertFalse((output / "signed-runtime-matrix.json").exists())

    def test_retained_failed_route_and_changed_raw_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / f"duplicate-provider-{HEAD}"
            artifact.mkdir()
            raw = artifact / "task.log"
            raw.write_text("BUILD FAILED\n")
            started, finished = time.time_ns() - 1_000_000_000, time.time_ns() + 1_000_000_000
            receipt = {"schema": 1, "status": "FAILED", "candidate_sha": HEAD,
                       "source_tree": collection.source_tree(ROOT, HEAD),
                       "process": {"command": ["./gradlew", "verifySingleProvider"],
                                   "exit_code": 1, "started_ns": started,
                                   "finished_ns": finished, "stdout": "task.log"},
                       "files": [{"path": "task.log",
                                  "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                                  "mtime_ns": raw.stat().st_mtime_ns}]}
            (artifact / "receipt.json").write_text(json.dumps(receipt))
            output = root / "collection"
            result = collection.collect(ROOT, HEAD, [(artifact.name, artifact)], output)
            self.assertEqual("FAILED", result["status"])
            self.assertNotIn("reason", result["artifacts"][0])
            self.assertTrue(raw.is_file())
            self.assertTrue(collection.verify_collection(ROOT, HEAD,
                                                         [(artifact.name, artifact)], output))
            raw.write_text("changed raw output\n")
            with self.assertRaisesRegex(ValueError, "raw artifact bytes differ"):
                collection.verify_collection(ROOT, HEAD, [(artifact.name, artifact)], output)
            changed = collection.collect(ROOT, HEAD, [(artifact.name, artifact)],
                                         root / "changed")
            self.assertIn("raw file hash differs", changed["artifacts"][0]["reason"])

    def test_altered_transport_archive_is_failed_and_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / f"full-ci-{HEAD}"
            artifact.mkdir()
            packed = artifact / f"full-ci-{HEAD}.tar.gz"
            with tarfile.open(packed, "w:gz") as archive:
                pass
            sidecar = artifact / f"full-ci-{HEAD}.sha256"
            sidecar.write_text(f"{collection.digest(packed)}  {packed.name}\n")
            before = root / "before"
            collection.collect(ROOT, HEAD, [(artifact.name, artifact)], before)
            packed.write_bytes(packed.read_bytes() + b"altered")
            with self.assertRaisesRegex(ValueError, "raw artifact bytes differ"):
                collection.verify_collection(ROOT, HEAD, [(artifact.name, artifact)], before)
            result = collection.collect(ROOT, HEAD, [(artifact.name, artifact)],
                                        root / "after")
            self.assertEqual("FAILED", result["status"])
            self.assertIn("archive bytes differ", result["artifacts"][0]["reason"])
            self.assertTrue(packed.is_file())

    def test_workflow_runs_after_producers_and_retains_raw_results(self):
        workflow = (ROOT / ".github/workflows/qualification.yml").read_text()
        self.assertIn("needs: [staged-jvm-and-linux, hosted-publications, hosted-native, safari-browser]",
                      workflow)
        for command in ("actions/download-artifact@v4", "collection.py --verify",
                        "independent_gates.py", "qualify.py record",
                        "duplicate_provider.py", "qualification-central-${{ github.sha }}"):
            self.assertIn(command, workflow)
        self.assertIn("if: always()", workflow)

    def test_workflow_download_survives_replay_setup_failure(self):
        workflow = (ROOT / ".github/workflows/qualification.yml").read_text()
        central = workflow.split("  central-qualification-collection:\n", 1)[1]

        def assert_download_contract(job):
            download = job.index("      - name: Download every retained producer artifact\n")
            next_step = job.index("      - ", download + 1)
            download_step = job[download:next_step]
            self.assertIn("        if: always()\n", download_step)
            self.assertIn("        id: raw_download\n", download_step)
            self.assertIn("        continue-on-error: true\n", download_step)
            for fallible in ("      - uses: actions/checkout@v4\n",
                             "      - uses: actions/setup-java@v4\n",
                             "      - uses: gradle/actions/setup-gradle@v4\n",
                             "      - name: Provision pinned upstream source for raw replay\n"):
                self.assertLess(download, job.index(fallible))
            self.assertIn("DYN4K_DOWNLOAD_OUTCOME: ${{ steps.raw_download.outcome }}", job)
            self.assertIn("test \"$DYN4K_DOWNLOAD_OUTCOME\" = success", job)
            self.assertIn("download=%s", job)
            self.assertIn("::error::Producer artifact download failed or was skipped", job)

        assert_download_contract(central)
        download = central.index("      - name: Download every retained producer artifact\n")
        next_step = central.index("      - ", download + 1)
        download_step = central[download:next_step]
        without_condition = central.replace(
            download_step, download_step.replace("        if: always()\n", ""))
        with self.assertRaises(AssertionError):
            assert_download_contract(without_condition)
        after_fetch = central.replace(download_step, "").replace(
            "      - name: Collect and independently enumerate 112 lanes\n",
            download_step + "      - name: Collect and independently enumerate 112 lanes\n")
        with self.assertRaises(AssertionError):
            assert_download_contract(after_fetch)


if __name__ == "__main__":
    unittest.main()
