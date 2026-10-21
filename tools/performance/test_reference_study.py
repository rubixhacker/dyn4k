import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sustained_archive import comparison_control_keys, frozen_policy, signature


SCRIPT = Path(__file__).with_name("reference_study.py")
SOURCE = "bb7d5cf7671f96a13449a5e0c3d65ff44d4b4975"


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ReferenceStudyCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "study"
        self.key = self.root / "operator.key"
        self.key.write_bytes(b"independent-study-operator-key-" * 2)
        self.key_id = sorted(k for k in comparison_control_keys(frozen_policy())
                             if k.startswith("absolute_timing|js.node|"))[0]
        self.control_id = "row_reference_self"
        self.identities = {}
        for name in ("artifact", "probe", "runtime", "image"):
            path = self.root / name
            path.write_bytes((name + "-fixed-study-input").encode())
            self.identities[name] = str(path)
        self.plan = {
            "source_commit": SOURCE,
            "assignments": [{"phase": "source", "key": self.key_id,
                             "controls": [self.control_id]}],
            "controls": [{"row_id": "js.node", "control_id": self.control_id,
                          "route": "direct_kotlin", "host_id": "synthetic-host",
                          "boot_id": "synthetic-boot",
                          **{name + "_path": path for name, path in self.identities.items()}}],
        }

    def cli(self, command, *args, success=True):
        env = os.environ.copy()
        env.pop("OLLAMA_API_KEY", None)
        completed = subprocess.run([sys.executable, str(SCRIPT), command, *map(str, args)],
                                   text=True, capture_output=True, env=env)
        self.assertEqual(completed.returncode == 0, success, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def create(self):
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(self.plan))
        return self.cli("create", "--archive", self.archive, "--plan", plan_path,
                        "--trusted-key", self.key)

    def captures(self, phases=("source",)):
        rows = []
        for phase in phases:
            for pair, sides in enumerate((("a", "b"), ("b", "a"), ("a", "b")), 1):
                for order, side in enumerate(sides, 1):
                    serial = len(rows) + 1
                    files = {}
                    for kind in ("series", "environment", "monitor"):
                        path = self.root / f"{kind}-{serial}.json"
                        path.write_text(json.dumps({"kind": kind, "serial": serial,
                                                    "phase": phase}))
                        files[kind + "_path"] = str(path)
                    rows.append({"phase": phase, "key": self.key_id,
                                 "control_id": self.control_id, "row_id": "js.node",
                                 "route": "direct_kotlin", "host_id": "synthetic-host",
                                 "boot_id": "synthetic-boot",
                                 "pair": pair, "side": side, "order": order,
                                 "process_id": f"study-process-{serial}",
                                 "run_id": f"study-run-{serial}", "os_pid": 1000 + serial,
                                 "process_start_id": f"os-start-{serial}",
                                 "started_ns": 1000000 + serial * 10000,
                                 "ended_ns": 1000500 + serial * 10000,
                                 "invalid_reason": None, "stop_reason": "completed",
                                 **{name + "_sha256": digest(Path(path).read_bytes())
                                    for name, path in self.identities.items()},
                                 **files})
        return rows

    def seal(self, rows, success=True):
        capture_path = self.root / "captures.json"
        capture_path.write_text(json.dumps(rows))
        return self.cli("seal", "--archive", self.archive,
                        "--captures", capture_path, "--trusted-key", self.key,
                        success=success)

    def verify(self, success=True):
        return self.cli("verify", "--archive", self.archive, "--trusted-key", self.key,
                        "--expected-source-commit", SOURCE, success=success)

    def resign_index(self, index):
        index["signature"] = signature(index, self.key.read_bytes())
        (self.archive / "archive.json").write_text(json.dumps(index))

    def test_signed_public_positive_is_still_unpassed_and_relocatable(self):
        self.create()
        self.seal(self.captures())
        moved = self.root / "relocated"
        self.archive.rename(moved)
        self.archive = moved
        result = self.verify()
        self.assertEqual(result["study"], "structurally_verified")
        self.assertEqual(result["qualification"], "unpassed")
        self.assertEqual(result["validated_reference_rows"], 0)
        self.assertEqual(result["numeric_limits"], "not_approved")

    def test_four_declared_phases_verify_without_qualifying_a_row(self):
        phases = ("feasibility", "source", "model_holdout", "confirmation")
        self.plan["assignments"] = [{"phase": phase, "key": self.key_id,
                                     "controls": [self.control_id]} for phase in phases]
        self.create()
        result = self.seal(self.captures(phases))
        self.assertEqual(result["declared_assignments"], 4)
        self.assertEqual(result["validated_reference_rows"], 0)

    def test_identical_zero_series_environment_and_monitor_across_phases(self):
        self.plan["assignments"].append({"phase": "model_holdout", "key": self.key_id,
                                         "controls": [self.control_id]})
        self.create()
        rows = self.captures(("source", "model_holdout"))
        for row in rows:
            Path(row["series_path"]).write_bytes(b"0\n")
            Path(row["environment_path"]).write_bytes(b"same environment\n")
            Path(row["monitor_path"]).write_bytes(b"same monitor\n")
        result = self.seal(rows)
        self.assertEqual(result["qualification"], "unpassed")
        self.assertEqual(result["validated_reference_rows"], 0)
        self.assertEqual(result["numeric_limits"], "not_approved")
        self.assertEqual(self.verify()["study"], "structurally_verified")
        captures = json.loads((self.archive / "archive.json").read_text())["captures"]
        for kind in ("series", "environment", "monitor"):
            self.assertEqual(len({row[kind + "_sha256"] for row in captures}), 1)
            self.assertEqual(len({row[kind + "_path"] for row in captures}), len(captures))

    def test_resigned_index_rejects_raw_path_collision_with_equal_bytes(self):
        self.create()
        self.seal(self.captures())
        index = json.loads((self.archive / "archive.json").read_text())
        first, second = index["captures"][:2]
        second["series_path"] = first["series_path"]
        second["series_sha256"] = first["series_sha256"]
        self.resign_index(index)
        self.assertIn("raw archive path reused", self.verify(success=False)["reason"])

    def test_resigned_index_rejects_control_or_protocol_file_as_raw(self):
        for target in ("protocol", "control"):
            with self.subTest(target=target):
                self.archive = self.root / f"alias-{target}"
                self.create()
                self.seal(self.captures())
                index = json.loads((self.archive / "archive.json").read_text())
                if target == "protocol":
                    path = "protocol.json"
                    raw = self.archive / path
                else:
                    control = json.loads((self.archive / "protocol.json").read_text())["controls"][0]
                    path = control["artifact_path"]
                    raw = self.archive / path
                index["captures"][0]["series_path"] = path
                index["captures"][0]["series_sha256"] = digest(raw.read_bytes())
                self.resign_index(index)
                self.assertIn("capture raw path must be under raw/",
                              self.verify(success=False)["reason"])

    def test_resigned_index_rejects_raw_hardlink_to_control_or_other_capture(self):
        for target in ("control", "capture"):
            with self.subTest(target=target):
                self.archive = self.root / f"hardlink-{target}"
                self.create()
                self.seal(self.captures())
                index = json.loads((self.archive / "archive.json").read_text())
                if target == "control":
                    control = json.loads((self.archive / "protocol.json").read_text())["controls"][0]
                    source = self.archive / control["artifact_path"]
                else:
                    source = self.archive / index["captures"][0]["series_path"]
                alias = self.archive / "raw" / f"linked-{target}.bin"
                os.link(source, alias)
                index["captures"][1]["series_path"] = str(alias.relative_to(self.archive))
                index["captures"][1]["series_sha256"] = digest(source.read_bytes())
                self.resign_index(index)
                self.assertIn("raw archive path reused",
                              self.verify(success=False)["reason"])

    def test_accepts_repeated_series_within_distinct_source_processes(self):
        self.create()
        rows = self.captures()
        Path(rows[1]["series_path"]).write_bytes(Path(rows[0]["series_path"]).read_bytes())
        self.assertEqual(self.seal(rows)["study"], "structurally_verified")

    def test_accepts_equal_series_across_feasibility_and_source(self):
        self.plan["assignments"].insert(0, {"phase": "feasibility", "key": self.key_id,
                                            "controls": [self.control_id]})
        self.create()
        rows = self.captures(("feasibility", "source"))
        rows[6]["series_path"] = rows[0]["series_path"]
        self.assertEqual(self.seal(rows)["study"], "structurally_verified")

    def test_accepts_equal_monitor_bytes_across_distinct_processes(self):
        self.create()
        rows = self.captures()
        rows[1]["monitor_path"] = rows[0]["monitor_path"]
        self.assertEqual(self.seal(rows)["study"], "structurally_verified")

    def test_repeated_environment_identity_remains_valid(self):
        self.plan["assignments"].append({"phase": "model_holdout", "key": self.key_id,
                                         "controls": [self.control_id]})
        self.create()
        rows = self.captures(("source", "model_holdout"))
        for row in rows[1:]:
            row["environment_path"] = rows[0]["environment_path"]
        result = self.seal(rows)
        self.assertEqual(result["study"], "structurally_verified")
        self.assertEqual(result["qualification"], "unpassed")

    def test_rejects_overlapping_same_host_pid_intervals(self):
        self.create()
        rows = self.captures()
        rows[1]["os_pid"] = rows[0]["os_pid"]
        rows[1]["started_ns"] = rows[0]["started_ns"] + 1
        rows[1]["ended_ns"] = rows[0]["ended_ns"] + 1
        self.assertIn("overlapping observed host/PID intervals",
                      self.seal(rows, success=False)["reason"])

    def test_allows_nonoverlapping_same_host_pid_intervals(self):
        self.create()
        rows = self.captures()
        rows[1]["os_pid"] = rows[0]["os_pid"]
        self.assertEqual(self.seal(rows)["study"], "structurally_verified")

    def test_rejects_unsigned_duplicate_index_key(self):
        self.create()
        self.seal(self.captures())
        index_path = self.archive / "archive.json"
        original = index_path.read_text()
        index_path.write_text(original.replace("{", '{"captures":[],', 1))
        self.assertIn("duplicate JSON key", self.verify(success=False)["reason"])

    def test_rejects_unsigned_nested_duplicate_index_key(self):
        self.create()
        self.seal(self.captures())
        index_path = self.archive / "archive.json"
        original = index_path.read_text()
        index_path.write_text(original.replace('"route": "direct_kotlin"',
                                               '"route": "baseline", "route": "direct_kotlin"',
                                               1))
        self.assertIn("duplicate JSON key", self.verify(success=False)["reason"])

    def test_rejects_wrong_index_hmac(self):
        self.create()
        self.seal(self.captures())
        index_path = self.archive / "archive.json"
        index = json.loads(index_path.read_text())
        index["signature"] = "0" * 64
        index_path.write_text(json.dumps(index))
        self.assertIn("archive.json signature differs",
                      self.verify(success=False)["reason"])

    def test_requires_declared_boot_and_process_start(self):
        self.create()
        rows = self.captures()
        rows[0]["boot_id"] = "another-boot"
        self.assertIn("capture route, host, or boot differs",
                      self.seal(rows, success=False)["reason"])
        rows = self.captures()
        rows[0]["process_start_id"] = ""
        self.assertIn("invalid process identity or interval",
                      self.seal(rows, success=False)["reason"])
        rows = self.captures()
        del rows[0]["boot_id"]
        self.assertIn("capture input keys differ",
                      self.seal(rows, success=False)["reason"])

    def test_rejects_duplicate_signed_protocol_key_before_seal(self):
        self.create()
        protocol_path = self.archive / "protocol.json"
        original = protocol_path.read_text()
        protocol_path.write_text(original.replace("{", '{"controls":[],', 1))
        self.assertIn("duplicate JSON key",
                      self.seal(self.captures(), success=False)["reason"])

    def test_resigned_archive_rejects_reused_process_start_and_overlapping_pid(self):
        for mutation in ("process_start", "interval"):
            with self.subTest(mutation=mutation):
                self.archive = self.root / f"signed-{mutation}"
                self.create()
                self.seal(self.captures())
                index = json.loads((self.archive / "archive.json").read_text())
                first, second = index["captures"][:2]
                if mutation == "process_start":
                    second["os_pid"] = first["os_pid"]
                    second["process_start_id"] = first["process_start_id"]
                else:
                    second["os_pid"] = first["os_pid"]
                    second["started_ns"] = first["started_ns"] + 1
                    second["ended_ns"] = first["ended_ns"] + 1
                self.resign_index(index)
                reason = self.verify(success=False)["reason"]
                self.assertIn("reused declared process identity" if mutation == "process_start" else
                              "overlapping observed host/PID intervals", reason)

    def test_accepts_unique_key_canonical_signed_json(self):
        self.create()
        protocol_path = self.archive / "protocol.json"
        protocol_path.write_text(json.dumps(json.loads(protocol_path.read_text()),
                                            sort_keys=True, separators=(",", ":")))
        self.seal(self.captures())
        index_path = self.archive / "archive.json"
        index_path.write_text(json.dumps(json.loads(index_path.read_text()),
                                         sort_keys=True, separators=(",", ":")))
        result = self.verify()
        self.assertEqual(result["study"], "structurally_verified")
        self.assertEqual(result["qualification"], "unpassed")

    def test_rejects_wrong_assignment_route_artifact_and_unbalanced_order(self):
        for mutation in (lambda r: r[0].update(key="absolute_timing|wrong"),
                         lambda r: r[0].update(route="baseline"),
                         lambda r: r[0].update(artifact_sha256="0" * 64),
                         lambda r: r[0].update(order=2),
                         lambda r: r[0].update(control_id="dyn4j_6_0_0_jvm")):
            with self.subTest(mutation=mutation):
                self.archive = self.root / f"archive-{id(mutation)}"
                self.create()
                rows = self.captures()
                mutation(rows)
                self.seal(rows, success=False)

    def test_rejects_missing_file_and_rehashed_forged_raw_bytes(self):
        self.create()
        self.seal(self.captures())
        index = json.loads((self.archive / "archive.json").read_text())
        raw = self.archive / index["captures"][0]["series_path"]
        raw.write_bytes(b"forged")
        self.verify(success=False)

    def test_rejects_empty_raw_stream(self):
        self.create()
        rows = self.captures()
        Path(rows[0]["series_path"]).write_bytes(b"")
        self.seal(rows, success=False)

    def test_signed_archive_rejects_semantically_wrong_row_and_raw_digest(self):
        self.create()
        self.seal(self.captures())
        index = json.loads((self.archive / "archive.json").read_text())
        index["captures"][0]["row_id"] = "jvm.java"
        self.resign_index(index)
        self.verify(success=False)
        index["captures"][0]["row_id"] = "js.node"
        index["captures"][0]["series_sha256"] = "f" * 64
        self.resign_index(index)
        self.verify(success=False)

    def test_signed_archive_rejects_missing_sidecar_and_reused_process(self):
        self.create()
        self.seal(self.captures())
        index = json.loads((self.archive / "archive.json").read_text())
        sidecar = self.archive / index["captures"][0]["monitor_path"]
        sidecar.unlink()
        self.verify(success=False)
        sidecar.write_text(json.dumps({"kind": "monitor", "serial": 1,
                                      "phase": "source"}))
        index["captures"][1]["process_id"] = index["captures"][0]["process_id"]
        self.resign_index(index)
        self.verify(success=False)

    def test_signed_archive_rejects_late_protocol_resign(self):
        self.create()
        self.seal(self.captures())
        protocol = json.loads((self.archive / "protocol.json").read_text())
        protocol["assignments"][0]["controls"] = ["dyn4j_6_0_0_jvm"]
        protocol["signature"] = signature(protocol, self.key.read_bytes())
        (self.archive / "protocol.json").write_text(json.dumps(protocol))
        self.verify(success=False)

    def test_rejects_cross_phase_reuse_and_numeric_limit(self):
        self.plan["assignments"].append({"phase": "model_holdout", "key": self.key_id,
                                         "controls": [self.control_id]})
        self.create()
        rows = self.captures(("source", "model_holdout"))
        rows[6]["process_id"] = rows[0]["process_id"]
        self.assertIn("duplicate or missing process_id", self.seal(rows, success=False)["reason"])
        rows = self.captures(("source", "model_holdout"))
        rows[6]["os_pid"] = rows[0]["os_pid"]
        rows[6]["process_start_id"] = rows[0]["process_start_id"]
        self.assertIn("reused declared process identity",
                      self.seal(rows, success=False)["reason"])
        rows = self.captures(("source", "model_holdout"))
        rows[0]["noise_upper_ratio_max"] = 9
        self.seal(rows, success=False)

    def test_rejects_late_protocol_or_threshold_edit(self):
        self.create()
        protocol = json.loads((self.archive / "protocol.json").read_text())
        protocol["assignments"][0]["controls"] = ["dyn4j_6_0_0_jvm"]
        (self.archive / "protocol.json").write_text(json.dumps(protocol))
        self.seal(self.captures(), success=False)

    def test_rejects_incomplete_declared_key_and_invalid_reason(self):
        self.create()
        self.seal(self.captures()[:-1], success=False)
        rows = self.captures()
        rows[0]["invalid_reason"] = "monitor lost"
        self.seal(rows, success=False)

    def test_rejects_unpinned_dyn4j_baseline_artifact(self):
        baseline_key = sorted(k for k in comparison_control_keys(frozen_policy())
                              if k.startswith("jvm_vs_dyn4j|jvm.java|"))[0]
        self.plan["assignments"] = [{"phase": "source", "key": baseline_key,
                                     "controls": ["dyn4j_6_0_0_jvm"]}]
        self.plan["controls"][0].update(row_id="jvm.java",
                                        control_id="dyn4j_6_0_0_jvm", route="baseline")
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(self.plan))
        self.cli("create", "--archive", self.archive, "--plan", plan_path,
                 "--trusted-key", self.key, success=False)


if __name__ == "__main__":
    unittest.main()
