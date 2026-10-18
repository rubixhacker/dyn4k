import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


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
                    "build_type": "debug",
                    "app_package": capture.APP_ID, "test_package": capture.TEST_ID,
                    "evidence_authority": capture.EVIDENCE_AUTHORITY,
                    "provider_class": "org.dyn4j.world.World", "provider_loader_matches_target": True,
                    "pid": 123,
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

    def test_rejects_wrong_installed_build_configuration(self):
        rows = self.records()
        rows[0]["build_type"] = "release"
        with self.assertRaisesRegex(ValueError, "identity"):
            capture.validate_records(rows, self.scenario, self.source, self.nonce, 21,
                                     "x86_64", "guest/build/1", 2, 1,
                                     "c" * 64, "d" * 64, "e" * 64, "f" * 64)

    def test_r8_provider_name_accepts_actual_mapping_and_rejects_second_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            mapping = Path(temp) / "mapping.txt"
            mapping.write_text("org.dyn4j.world.World -> q2:\n")
            self.assertEqual(capture.provider_name(mapping, "release"), "q2")
        rows = self.records()
        rows[0]["build_type"] = "release"
        rows[0]["provider_class"] = "q2"
        rows[0]["provider_loader_matches_target"] = True
        capture.validate_records(rows, self.scenario, self.source, self.nonce, 21,
                                 "x86_64", "guest/build/1", 2, 1,
                                 "c" * 64, "d" * 64, "e" * 64, "f" * 64,
                                 "release", "q2")
        rows[0]["provider_class"] = "org.dyn4j.world.World"
        with self.assertRaisesRegex(ValueError, "identity"):
            capture.validate_records(rows, self.scenario, self.source, self.nonce, 21,
                                     "x86_64", "guest/build/1", 2, 1,
                                     "c" * 64, "d" * 64, "e" * 64, "f" * 64,
                                     "release", "q2")

    def test_rejects_inert_separated_engine(self):
        rows = self.records()
        for row in rows:
            if row["type"] == "step":
                row["awake"] = 0
                row["linear_speed"] = 0.0
            if row["type"] == "run":
                row["active_steps"] = 0
        with self.assertRaisesRegex(ValueError, "activity|separated"):
            capture.validate_records(rows, self.scenario, self.source, self.nonce, 21,
                                     "x86_64", "guest/build/1", 2, 1,
                                     "c" * 64, "d" * 64, "e" * 64, "f" * 64)

    def test_rejects_separated_speed_below_source_initial_velocity(self):
        rows = self.records()
        rows[6]["linear_speed"] = 1.0
        with self.assertRaisesRegex(ValueError, "activity|separated"):
            capture.validate_records(rows, self.scenario, self.source, self.nonce, 21,
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

    def test_timeout_receipt_indexes_partial_instrumentation(self):
        class TimedOutProcess:
            returncode = -9

            def communicate(self, timeout=None):
                if timeout is not None:
                    raise subprocess.TimeoutExpired("instrument", timeout)
                return b"partial instrumentation bytes", None

            def kill(self):
                pass

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp)
            report = {"raw": {}}
            with self.assertRaisesRegex(RuntimeError, "timeout"):
                capture.collect_instrumentation(TimedOutProcess(), archive, report, 1, 100)
            self.assertEqual((archive / "instrumentation.raw").read_bytes(),
                             b"partial instrumentation bytes")
            self.assertEqual(report["raw"]["instrumentation"]["sha256"],
                             capture.sha(archive / "instrumentation.raw"))
            self.assertTrue(report["raw"]["instrumentation"]["timed_out"])
            self.assertEqual(report["raw"]["instrumentation"]["exit_code"], -9)

    def test_runtime_graph_keeps_all_artifacts_and_rejects_second_world(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            core = root / "core.aar"
            facade = root / "facade.aar"
            stdlib = root / "stdlib.jar"
            annotations = root / "annotations.jar"
            with io.BytesIO() as data:
                with ZipFile(data, "w") as jar:
                    jar.writestr("org/dyn4j/world/World.class", b"engine")
                with ZipFile(core, "w") as aar:
                    aar.writestr("classes.jar", data.getvalue())
            with io.BytesIO() as data:
                with ZipFile(data, "w") as jar:
                    jar.writestr("io/github/rubixhacker/dyn4k/Facade.class", b"facade")
                with ZipFile(facade, "w") as aar:
                    aar.writestr("classes.jar", data.getvalue())
            with ZipFile(stdlib, "w") as jar:
                jar.writestr("kotlin/Unit.class", b"stdlib")
            with ZipFile(annotations, "w") as jar:
                jar.writestr("org/jetbrains/annotations/NotNull.class", b"annotation")
            records = [
                "DYN4K_GRAPH_COMPONENT project:app",
                "DYN4K_GRAPH_COMPONENT io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1",
                "DYN4K_GRAPH_COMPONENT io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1",
                "DYN4K_GRAPH_COMPONENT org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
                "DYN4K_GRAPH_COMPONENT org.jetbrains:annotations:13.0",
                "DYN4K_GRAPH_EDGE project:app io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1",
                f"DYN4K_GRAPH_ARTIFACT io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1 {core}",
                f"DYN4K_GRAPH_ARTIFACT io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1 {facade}",
                f"DYN4K_GRAPH_ARTIFACT org.jetbrains.kotlin:kotlin-stdlib:2.4.20 {stdlib}",
                f"DYN4K_GRAPH_ARTIFACT org.jetbrains:annotations:13.0 {annotations}",
            ]
            log = "\n".join(f"{record.split(' ', 1)[0]} {scope} {record.split(' ', 1)[1]}"
                            for scope in ("app", "test") for record in records)
            staged = {"dyn4k-core-android": capture.sha(core),
                      "dyn4k-android": capture.sha(facade)}
            graph = capture.parse_dependency_graph(log, staged)
            self.assertEqual(len(graph["app"]["artifacts"]), 4)
            self.assertEqual(len(graph["test"]["artifacts"]), 4)
            self.assertIn("org.jetbrains:annotations:13.0", graph["app"]["components"])
            self.assertEqual(next(item["sha256"] for item in graph["app"]["artifacts"]
                                  if item["coordinate"] == "org.jetbrains.kotlin:kotlin-stdlib:2.4.20"),
                             capture.sha(stdlib))
            with ZipFile(stdlib, "w") as jar:
                jar.writestr("org/dyn4j/world/World.class", b"second provider")
            with self.assertRaisesRegex(ValueError, "provider"):
                capture.parse_dependency_graph(log, staged)


if __name__ == "__main__":
    unittest.main()
