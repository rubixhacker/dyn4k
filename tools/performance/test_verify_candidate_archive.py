import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import verify_candidate_archive as verifier
from candidate_runner import API, CORE, FLAGS, check_route, source_trees
from measure import sha256
from verify_candidate_archive import audit_raw_archive, verify


ARCHIVE = Path(__file__).resolve().parents[2] / "docs/research/performance-candidate-v4"
SUPERSEDED = (ARCHIVE.with_name("performance-candidate-v2"),
              ARCHIVE.with_name("performance-candidate-v3"))
HISTORICAL_FILES = {
    "candidate-identity-at-pilot.json": "2268581c6ce00d8c7354034f305e8cac61d29f1bbd88d7ad2538fbe710025a23",
    "fixture-revision.json": "652b11b921e29ee252ed9ca0c90222e7f2b37c66103e3cb3f5cdaf3f47f86d87",
    "provider-identity.json": "1aecf77f93105b4b6e265f0a738472838930982b90e87acb9507ccc1ee0443f8",
    "negative-controls/negative-controls.json": "55fce6c5671204f9f382fb8c56469e8d9e8218aee63e3ea7f7182fda14f9318b",
}


class HistoricalArchiveBoundaryTest(unittest.TestCase):
    def test_raw_archive_audit_preserves_old_source_identity(self):
        report = audit_raw_archive(ARCHIVE)
        self.assertEqual("raw_hashes_verified", report["archive_audit"])
        self.assertEqual("unpassed", report["qualification"])
        self.assertEqual(135, report["raw_files"])
        self.assertEqual({"pilot": 36, "noise": 3, "memory": 3, "plateau": 3}, report["runs"])

    def test_old_archive_is_not_current_source_evidence(self):
        identity = json.loads((ARCHIVE / "candidate-identity-at-pilot.json").read_text())
        self.assertNotEqual(identity["source_trees"], source_trees("HEAD"))
        with self.assertRaisesRegex(ValueError, "source trees differ from the exact commit"):
            verify(ARCHIVE)

    def test_raw_archive_audit_rejects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / "archive"
            shutil.copytree(ARCHIVE, copied)
            index = json.loads((copied / "pilot/evidence.json").read_text())
            raw = copied / "pilot" / index["results"][0]["raw"]
            raw.write_bytes(raw.read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "raw file hash differs"):
                audit_raw_archive(copied)

    def test_raw_archive_audit_rejects_rewritten_raw_and_index(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / "archive"
            shutil.copytree(ARCHIVE, copied)
            index_path = copied / "pilot/evidence.json"
            index = json.loads(index_path.read_text())
            item = index["results"][0]
            raw = copied / "pilot" / item["raw"]
            raw.write_bytes(raw.read_bytes() + b"\n")
            item["raw_sha256"] = sha256(raw)
            index_path.write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, "pilot evidence index hash differs"):
                audit_raw_archive(copied)

    def test_unverifiable_older_archives_remain_unpassed(self):
        for archive in SUPERSEDED:
            with self.subTest(archive=archive.name):
                result = subprocess.run(
                    [sys.executable, "-B", str(Path(__file__).with_name("verify_candidate_archive.py")),
                     str(archive)], capture_output=True, text=True,
                )
                self.assertEqual(1, result.returncode)
                report = json.loads(result.stdout)
                self.assertEqual("unavailable", report["archive_audit"])
                self.assertEqual("unpassed", report["qualification"])


class CurrentSourceIdentityGuardTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        staging = Path(folder.name) / "staging"
        self.core = staging / CORE
        api = staging / API
        for path in (self.core, api):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(path.name.encode())
        routes = {"direct_kotlin": [api, self.core], "compatibility": [self.core]}
        java = shutil.which("java")
        if java is None:
            raise AssertionError("Java runtime is unavailable for identity guard tests")
        version = subprocess.run([java, "-version"], capture_output=True, check=True).stderr.decode().strip()
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=verifier.ROOT, text=True).strip()
        source_hashes = {str(verifier.ROOT / relative): verifier.hash_path(verifier.ROOT / relative)
                         for relative in verifier.SOURCE_FILES}
        artifact_hashes = {str(path): verifier.hash_path(path) for path in (self.core, api)}
        self.identity = {
            "schema": 1,
            "qualification": "unpassed",
            "source_commit": commit,
            "source_trees": source_trees("HEAD"),
            "staging_repository": str(staging),
            "java": str(Path(java).resolve()),
            "java_version": version,
            "java_flags": FLAGS,
            "entrypoints": {"direct_kotlin": "performance.DirectPilotKt",
                            "compatibility": "BaselinePilot"},
            "paths": {name: [str(path) for path in paths] for name, paths in routes.items()},
            "absent_classpath_paths": [],
            "sha256": source_hashes | artifact_hashes,
        }
        for name, replacement in (
            ("STAGING", staging),
            ("read_paths", lambda: routes),
            ("check_route", lambda route, paths: check_route(route, paths, staging)),
        ):
            active = patch.object(verifier, name, replacement)
            active.start()
            self.addCleanup(active.stop)
        verifier.verify_identity(self.identity)

    def test_production_guard_rejects_source_revision_substitution(self):
        substituted = self.identity | {"source_commit": "9ce41f7cc7cfc0a7c7991b02335c5e285159f58d"}
        with self.assertRaisesRegex(ValueError, "source trees differ from the exact commit"):
            verifier.verify_identity(substituted)

    def test_production_guard_rejects_changed_jar_bytes(self):
        self.core.write_bytes(self.core.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "artifact or classpath hash differs"):
            verifier.verify_identity(self.identity)

    def test_production_guard_rejects_forged_jar_hash(self):
        substituted = self.identity | {"sha256": self.identity["sha256"] | {str(self.core): "0" * 64}}
        with self.assertRaisesRegex(ValueError, "artifact or classpath hash differs"):
            verifier.verify_identity(substituted)


def write_identity(copied, identity):
    identity_file = copied / "candidate-identity-at-pilot.json"
    identity_file.write_text(json.dumps(identity))
    digest = sha256(identity_file)
    for name in ("pilot", "noise", "memory", "plateau"):
        path = copied / name / "evidence.json"
        evidence = json.loads(path.read_text())
        evidence["candidate_identity"] = identity
        evidence["candidate_identity_sha256"] = digest
        path.write_text(json.dumps(evidence))
    for name in ("provider-identity.json", "negative-controls/negative-controls.json"):
        path = copied / name
        data = json.loads(path.read_text())
        data["candidate_identity_sha256"] = digest
        path.write_text(json.dumps(data))


class ArchiveVerificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name, expected in HISTORICAL_FILES.items():
            if sha256(ARCHIVE / name) != expected:
                raise AssertionError(f"historical test fixture changed: {name}")
        cls.identity = json.loads((ARCHIVE / "candidate-identity-at-pilot.json").read_text())
        cls.revision = json.loads((ARCHIVE / "fixture-revision.json").read_text())
        cls.provider = json.loads((ARCHIVE / "provider-identity.json").read_text())
        cls.controls = json.loads((ARCHIVE / "negative-controls/negative-controls.json").read_text())
        if audit_raw_archive(ARCHIVE)["archive_audit"] != "raw_hashes_verified":
            raise AssertionError("historical raw archive is unavailable")
        historical_root = Path(cls.identity["staging_repository"]).parent.parent
        for relative in verifier.SOURCE_FILES:
            result = subprocess.run(
                ["git", "show", f"{cls.identity['source_commit']}:{relative}"],
                cwd=ARCHIVE, capture_output=True, check=True,
            )
            recorded = cls.identity["sha256"][str(historical_root / relative)]
            if hashlib.sha256(result.stdout).hexdigest() != recorded:
                raise AssertionError(f"historical source blob differs: {relative}")

    def setUp(self):
        def pinned_identity(observed):
            if observed.get("source_commit") != self.identity["source_commit"]:
                raise ValueError("historical source commit differs")
            if observed.get("sha256") != self.identity["sha256"]:
                raise ValueError("historical source or artifact hashes differ")
            if observed != self.identity:
                raise ValueError("historical source or artifact identity differs")

        for name, replacement in (
            ("verify_identity", pinned_identity),
            ("expected_record", lambda identity, digest: self.revision),
            ("probe_routes", lambda identity, digest: self.provider),
            ("evaluate_controls", lambda pilot, out, identity, digest: self.controls),
        ):
            active = patch.object(verifier, name, replacement)
            active.start()
            self.addCleanup(active.stop)

    def test_unmodified_historical_snapshot_is_parseable(self):
        self.assertEqual("unpassed", verify(ARCHIVE)["qualification"])

    def test_missing_ccd_fixture_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / "archive"
            shutil.copytree(ARCHIVE, copied)
            (copied / "fixture-revision.json").unlink(missing_ok=True)
            with self.assertRaisesRegex(ValueError, "fixture revision"):
                verify(copied)

    def test_changed_ccd_fixture_hash_or_source_is_rejected(self):
        for field in ("fixture_sha256", "direct_fixture_sha256"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                copied = Path(folder) / "archive"
                shutil.copytree(ARCHIVE, copied)
                path = copied / "fixture-revision.json"
                revision = json.loads(path.read_text())
                revision[field] = "0" * 64
                path.write_text(json.dumps(revision))
                with self.assertRaisesRegex(ValueError, "fixture revision"):
                    verify(copied)

    def test_nonpositive_or_reused_process_pid_is_rejected(self):
        for replacement in (0, -1, "baseline"):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as folder:
                copied = Path(folder) / "archive"
                shutil.copytree(ARCHIVE, copied)
                index = copied / "pilot/evidence.json"
                evidence = json.loads(index.read_text())
                item = next(result for result in evidence["results"]
                            if result["family"] == "separated" and result["api"] == "direct_kotlin"
                            and result["mode"] == "timing")
                old_pid = item["process_pid"]
                if replacement == "baseline":
                    new_pid = next(result["process_pid"] for result in evidence["results"]
                                   if result["family"] == "separated" and result["api"] == "baseline"
                                   and result["mode"] == "timing")
                else:
                    new_pid = replacement
                item["process_pid"] = new_pid
                stderr = copied / "pilot" / item["stderr_raw"]
                stderr.write_text(stderr.read_text().replace(f"#process_pid={old_pid}",
                                                             f"#process_pid={new_pid}"))
                item["stderr_sha256"] = sha256(stderr)
                index.write_text(json.dumps(evidence))
                analysis = copied / "analysis.json"
                derived = json.loads(analysis.read_text())
                for group in derived["pilot"].values():
                    for route in group.values():
                        if route["process_pid"] == old_pid:
                            route["process_pid"] = new_pid
                analysis.write_text(json.dumps(derived))
                with self.assertRaisesRegex(ValueError, "process PID"):
                    verify(copied)

    def test_failed_or_misidentified_provider_is_rejected(self):
        for change in ("exit_code", "core_sha256", "api_sha256"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                copied = Path(folder) / "archive"
                shutil.copytree(ARCHIVE, copied)
                path = copied / "provider-identity.json"
                provider = json.loads(path.read_text())
                route = provider["routes"]["direct_kotlin"]
                route[change] = 1 if change == "exit_code" else "0" * 64
                path.write_text(json.dumps(provider))
                with self.assertRaisesRegex(ValueError, "provider"):
                    verify(copied)

    def test_named_controls_and_bound_inputs_are_required(self):
        for change in ("renamed", "accepted_reason", "source_sha256", "core_artifact_sha256"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                copied = Path(folder) / "archive"
                shutil.copytree(ARCHIVE, copied)
                path = copied / "negative-controls/negative-controls.json"
                controls = json.loads(path.read_text())
                if change == "renamed":
                    controls["controls"]["wrong_name"] = controls["controls"].pop("empty_scene")
                elif change == "accepted_reason":
                    controls["controls"]["empty_scene"]["reason"] = "negative control was accepted"
                else:
                    controls[change] = "0" * 64
                path.write_text(json.dumps(controls))
                with self.assertRaisesRegex(ValueError, "negative control"):
                    verify(copied)

    def test_negative_timing_channels_are_rejected(self):
        for channel in ("mutation_ns", "lateness_ns", "allocation_bytes"):
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as folder:
                copied = Path(folder) / "archive"
                shutil.copytree(ARCHIVE, copied)
                index = copied / "pilot/evidence.json"
                evidence = json.loads(index.read_text())
                item = next(result for result in evidence["results"]
                            if result["family"] == "separated" and result["api"] == "baseline"
                            and result["mode"] == "timing")
                raw = copied / "pilot" / item["raw"]
                with raw.open(newline="") as stream:
                    reader = csv.DictReader(stream)
                    fields = reader.fieldnames
                    rows = list(reader)
                rows[2][channel] = "-2" if channel == "allocation_bytes" else "-1"
                with raw.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
                item["raw_sha256"] = sha256(raw)
                index.write_text(json.dumps(evidence))
                with self.assertRaisesRegex(ValueError, channel):
                    verify(copied)

    def test_negative_plateau_collection_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / "archive"
            shutil.copytree(ARCHIVE, copied)
            index = copied / "plateau/evidence.json"
            evidence = json.loads(index.read_text())
            item = evidence["results"][0]
            raw = copied / "plateau" / item["raw"]
            with raw.open(newline="") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                rows = list(reader)
            rows[50]["collection_count"] = "-1"
            with raw.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            item["raw_sha256"] = sha256(raw)
            index.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, "collection_count"):
                verify(copied)

    def test_stalled_plateau_collection_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / "archive"
            shutil.copytree(ARCHIVE, copied)
            index = copied / "plateau/evidence.json"
            evidence = json.loads(index.read_text())
            item = evidence["results"][0]
            raw = copied / "plateau" / item["raw"]
            with raw.open(newline="") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                rows = list(reader)
            rows[50]["collection_count"] = rows[49]["collection_count"]
            with raw.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            item["raw_sha256"] = sha256(raw)
            index.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, "collection_count"):
                verify(copied)

    def test_altered_hashed_retained_heap_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / "archive"
            shutil.copytree(ARCHIVE, copied)
            index = copied / "memory/evidence.json"
            evidence = json.loads(index.read_text())
            item = evidence["results"][0]
            raw = copied / "memory" / item["stderr_raw"]
            original = f"#retained_heap_world_alive_bytes={item['retained_heap_world_alive_bytes']}"
            raw.write_text(raw.read_text().replace(original, "#retained_heap_world_alive_bytes=1"))
            item["stderr_sha256"] = sha256(raw)
            index.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, "retained_heap_world_alive_bytes"):
                verify(copied)

    def test_altered_retained_heap_summary_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / "archive"
            shutil.copytree(ARCHIVE, copied)
            index = copied / "memory/evidence.json"
            evidence = json.loads(index.read_text())
            evidence["results"][0]["retained_heap_world_alive_bytes"] = 1
            index.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, "retained_heap_world_alive_bytes"):
                verify(copied)

    def test_forged_source_and_artifact_identity_is_rejected(self):
        for case in ("missing_commit", "missing_source", "altered_artifact"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                copied = Path(folder) / "archive"
                shutil.copytree(ARCHIVE, copied)
                identity = json.loads((copied / "candidate-identity-at-pilot.json").read_text())
                if case == "missing_commit":
                    identity["source_commit"] = "0" * 40
                elif case == "missing_source":
                    original = next(path for path in identity["sha256"]
                                    if path.endswith("/BaselinePilot.java"))
                    identity["sha256"]["/tmp/dyn4k-review-missing/BaselinePilot.java"] = (
                        identity["sha256"].pop(original))
                else:
                    artifact = next(path for path in identity["sha256"]
                                    if path.endswith("/dyn4k-core-jvm-0.1.0-alpha.1.jar"))
                    identity["sha256"][artifact] = "0" * 64
                write_identity(copied, identity)
                with self.assertRaisesRegex(ValueError, "source|commit|artifact"):
                    verify(copied)

    def test_altered_indexed_median_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / "archive"
            shutil.copytree(ARCHIVE, copied)
            index = copied / "pilot/evidence.json"
            evidence = json.loads(index.read_text())
            evidence["results"][0]["median_step_ns"] = 1
            index.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, "median_step_ns"):
                verify(copied)


if __name__ == "__main__":
    unittest.main()
