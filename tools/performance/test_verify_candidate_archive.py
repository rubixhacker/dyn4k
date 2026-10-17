import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from measure import sha256
from verify_candidate_archive import verify


ARCHIVE = Path(__file__).resolve().parents[2] / "docs/research/performance-candidate-v3"


class ArchiveVerificationTest(unittest.TestCase):
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
                rows[2][channel] = "-1"
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

    def test_forged_source_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / "archive"
            shutil.copytree(ARCHIVE, copied)
            identity_file = copied / "candidate-identity-at-pilot.json"
            identity = json.loads(identity_file.read_text())
            identity["source_commit"] = "0" * 40
            original = next(path for path in identity["sha256"] if path.endswith("/BaselinePilot.java"))
            identity["sha256"]["/tmp/dyn4k-review-missing/BaselinePilot.java"] = identity["sha256"].pop(original)
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
            with self.assertRaisesRegex(ValueError, "source|commit|missing"):
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
