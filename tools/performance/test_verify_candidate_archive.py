import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from measure import sha256
from verify_candidate_archive import verify


ARCHIVE = Path(__file__).resolve().parents[2] / "docs/research/performance-candidate-v4"
SUPERSEDED = (ARCHIVE.with_name("performance-candidate-v2"),
              ARCHIVE.with_name("performance-candidate-v3"))


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

    def test_unverifiable_old_archive_reports_unavailable(self):
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
