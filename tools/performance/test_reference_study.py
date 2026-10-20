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
                                 "pair": pair, "side": side, "order": order,
                                 "process_id": f"study-process-{serial}",
                                 "run_id": f"study-run-{serial}", "os_pid": 1000 + serial,
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
        self.seal(rows, success=False)
        rows = self.captures(("source", "model_holdout"))
        rows[6]["series_path"] = rows[0]["series_path"]
        self.seal(rows, success=False)
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
