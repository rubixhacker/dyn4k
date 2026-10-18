import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).with_name("capture.py")
spec = importlib.util.spec_from_file_location("capture", MODULE)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class CaptureControls(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((capture.ROOT / "docs/research/performance-manifest-v1.json").read_text())
        self.scenario = "separated.default.small.60hz.direct_kotlin"
        self.source = "a" * 40
        self.nonce = "b" * 32

    def records(self):
        identity = {"schema": 1, "type": "identity", "nonce": self.nonce,
                    "scenario": self.scenario, "source_commit": self.source,
                    "fixture_sha256": "c" * 64, "manifest_sha256": "d" * 64,
                    "core_aar_sha256": "e" * 64, "kotlin_aar_sha256": "f" * 64,
                    "app_package": capture.APP_ID, "test_package": capture.TEST_ID,
                    "provider_class": "org.dyn4j.world.World", "pid": 123,
                    "api_level": 21, "abi": "x86_64", "fingerprint": "guest/build/1"}
        rows = [identity, {"schema": 1, "type": "construction", "phase": "warmup",
                           "bodies": 100, "joints": 0},
                {"schema": 1, "type": "clock", "phase": "warmup", "step": 0,
                 "begin_ns": 100, "end_ns": 130},
                {"schema": 1, "type": "reset", "after_warmup": 1,
                 "warmup_world_id": 1, "measure_world_id": 2},
                {"schema": 1, "type": "construction", "phase": "measure",
                 "bodies": 100, "joints": 0}]
        for step in range(2):
            begin = 200 + step * 100
            rows += [{"schema": 1, "type": "clock", "phase": "measure", "step": step,
                      "begin_ns": begin, "end_ns": begin + 30},
                     {"schema": 1, "type": "step", "step": step, "begin_ns": begin,
                      "end_ns": begin + 30, "duration_ns": 30, "mutate_ns": 2,
                      "late_ns": 0, "bodies": 100, "joints": 0,
                      "awake": 100, "linear_speed": 75.0, "angular_speed": 0.0,
                      "contact_begins": 0, "contact_ends": 0, "toi_events": 0,
                      "broad_pairs": 0, "contact_pairs": 0, "contact_points": 0}]
        rows += [{"schema": 1, "type": "run", "steps": 2, "warmup_steps": 1,
                  "active_steps": 2, "wall_ns": 200, "qualification": "unpassed"}]
        return rows

    def test_rejects_wrong_order_and_zero_clock(self):
        rows = self.records()
        capture.validate_records(rows, self.scenario, self.source, self.nonce, 21,
                                 "x86_64", "guest/build/1", 2, 1,
                                 "c" * 64, "d" * 64, "e" * 64, "f" * 64)
        altered = [dict(row) for row in rows]
        altered[7]["step"] = 0
        with self.assertRaisesRegex(ValueError, "order|step"):
            capture.validate_records(altered, self.scenario, self.source, self.nonce, 21,
                                     "x86_64", "guest/build/1", 2, 1,
                                     "c" * 64, "d" * 64, "e" * 64, "f" * 64)
        altered = [dict(row) for row in rows]
        altered[2]["end_ns"] = 100
        with self.assertRaisesRegex(ValueError, "clock"):
            capture.validate_records(altered, self.scenario, self.source, self.nonce, 21,
                                     "x86_64", "guest/build/1", 2, 1,
                                     "c" * 64, "d" * 64, "e" * 64, "f" * 64)

    def test_rejects_substituted_identity_and_missing_reset(self):
        rows = self.records()
        altered = [dict(row) for row in rows]
        altered[0]["core_aar_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "identity"):
            capture.validate_records(altered, self.scenario, self.source, self.nonce, 21,
                                     "x86_64", "guest/build/1", 2, 1,
                                     "c" * 64, "d" * 64, "e" * 64, "f" * 64)
        with self.assertRaisesRegex(ValueError, "reset|order"):
            capture.validate_records(rows[:3] + rows[4:], self.scenario, self.source,
                                     self.nonce, 21, "x86_64", "guest/build/1", 2, 1,
                                     "c" * 64, "d" * 64, "e" * 64, "f" * 64)

    def test_rejects_empty_or_wrong_construction(self):
        rows = self.records()
        for count in (0, 101):
            altered = [dict(row) for row in rows]
            altered[1]["bodies"] = count
            altered[4]["bodies"] = count
            for sample in (6, 8):
                altered[sample]["bodies"] = count
            with self.assertRaisesRegex(ValueError, "construction|fixture"):
                capture.validate_records(altered, self.scenario, self.source, self.nonce, 21,
                                         "x86_64", "guest/build/1", 2, 1,
                                         "c" * 64, "d" * 64, "e" * 64, "f" * 64)

    def test_rejects_baseline_stress_and_wrong_size(self):
        for scenario in ["separated.default.small.60hz.baseline",
                         "separated.default.stress.60hz.direct_kotlin",
                         "separated.default.medium.60hz.direct_kotlin"]:
            with self.assertRaises(ValueError):
                capture.select_case(self.manifest, scenario, 100)
        self.assertEqual(capture.select_case(self.manifest, self.scenario, 100)["dynamic_bodies"], 100)

    def test_rejects_existing_archive_without_overwriting_raw(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "capture"
            archive.mkdir()
            (archive / "raw.txt").write_text("failed evidence")
            with self.assertRaises(FileExistsError):
                capture.create_archive(archive)
            self.assertEqual((archive / "raw.txt").read_text(), "failed evidence")


if __name__ == "__main__":
    unittest.main()
