import copy
import gzip
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

from weld_pulley_quality import audit_quality


def packed(rows):
    return b"".join(json.dumps(row, separators=(",", ":"), allow_nan=True).encode() + b"\n" for row in rows)


class WeldPulleyQualitySeamTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.declaration = {
            "baseline_source_revision": "f" * 40,
            "baseline_jar_sha256": "a" * 64,
            "step_seconds": "1/60",
            "steps_per_case": 2,
            "phases": [["excitation", 1, 1], ["long-run", 2, 2]],
            "cases": {
                "weld-spring-equal": {"metrics": {"anchor_gap_m": {"absolute_limit": "0.01", "relative_limit": "0"}, "angular_error_rad": {"absolute_limit": "0.017453292519943295", "relative_limit": "0"}}},
                "pulley-taut": {"metrics": {"absolute_rope_error_m": {"absolute_limit": "0.01", "relative_limit": "0"}}},
            },
        }
        self.manifest = {"declaration_sha256": "d" * 64, "capture_sha256": "c" * 64, "baseline_jar_sha256": "a" * 64, "baseline_source_revision": "f" * 40, "cases": {}}

    def rows(self, case):
        header = {"kind": "inputs", "case": case, "declaration_sha256": "d" * 64,
                  "capture_sha256": "c" * 64, "source_revision": "f" * 40,
                  "jar_sha256": "a" * 64, "step_seconds": "1/60", "steps": 2}
        if case == "weld-spring-equal":
            state = {"bodies": [{"id": "ground", "center": [0, 0], "angle": 0, "cost": 1, "sint": 0},
                                {"id": "member", "center": [0, 2], "angle": 0, "cost": 1, "sint": 0}],
                     "joint": {"type": "WeldJoint", "spring": True, "limits": True,
                               "frequency": 8, "dampingRatio": 0.3, "lowerLimit": 0,
                               "upperLimit": 0, "anchor1": [-0.5, 2], "anchor2": [-0.5, 2],
                               "referenceAngle": 0}}
        else:
            state = {"bodies": [{"id": "left", "center": [-1, 0]}, {"id": "right", "center": [1, 0]}],
                     "joint": {"type": "PulleyJoint", "slack": False, "ratio": 1, "length": 2,
                               "pulleyAnchor1": [-1, 1], "pulleyAnchor2": [1, 1],
                               "anchor1": [-1, 0], "anchor2": [1, 0]}}
        rows = [header]
        for step in (1, 2):
            rows += [{"kind": "event", "step": step, "order": order, "callback": callback}
                     for order, callback in enumerate(("begin", "postSolve", "end"))]
            rows.append({"kind": "state", "step": step, "state": copy.deepcopy(state)})
        return rows

    def write(self, case, rows):
        data = packed(rows)
        path = self.root / f"{case}.jsonl.gz"
        path.write_bytes(gzip.compress(data, mtime=0))
        self.manifest["cases"][case] = {"file": path.name,
            "gzip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "stream_sha256": hashlib.sha256(data).hexdigest(),
            "input_sha256": hashlib.sha256(data.splitlines()[0]).hexdigest(),
            "counts": {"inputs": 1, "event": 6, "state": 2}}
        return path

    def audit(self, case, rows):
        return audit_quality(self.declaration, self.manifest, case, self.write(case, rows))

    def test_both_baseline_shapes_pass_with_inclusive_limits(self):
        for case in self.declaration["cases"]:
            with self.subTest(case=case):
                self.assertEqual("PHYSICAL_PASSED", self.audit(case, self.rows(case))["status"])

    def test_out_of_bound_weld_anchor_and_angle_fail(self):
        rows = self.rows("weld-spring-equal")
        rows[-1]["state"]["joint"]["anchor2"][1] = 2.011
        rows[-1]["state"]["bodies"][1]["center"][1] = 2.011
        self.assertEqual("PHYSICAL_FAILED", self.audit("weld-spring-equal", rows)["status"])
        rows = self.rows("weld-spring-equal")
        rows[-1]["state"]["bodies"][1]["angle"] = 0.02
        self.assertEqual("PHYSICAL_FAILED", self.audit("weld-spring-equal", rows)["status"])

    def test_reported_zero_cannot_hide_over_limit_stored_rotation(self):
        for radians in (0.04, -0.04):
            with self.subTest(radians=radians):
                rows = self.rows("weld-spring-equal")
                cosine, sine = math.cos(radians), math.sin(radians)
                moving = rows[-1]["state"]["bodies"][1]
                moving.update(center=[-0.5 + 0.5 * cosine, 2 + 0.5 * sine],
                              angle=0, cost=cosine, sint=sine)
                result = self.audit("weld-spring-equal", rows)
                self.assertEqual("PHYSICAL_FAILED", result["status"])
                self.assertEqual(1, result["metrics"]["angular_error_rad"]["failed"])
                self.assertEqual(0, result["metrics"]["anchor_gap_m"]["failed"])

    def test_represented_rotation_uses_the_fixed_one_degree_limit(self):
        for radians, expected in ((0.017, "PHYSICAL_PASSED"),
                                  (-0.017, "PHYSICAL_PASSED"),
                                  (0.018, "PHYSICAL_FAILED"),
                                  (-0.018, "PHYSICAL_FAILED")):
            with self.subTest(radians=radians):
                rows = self.rows("weld-spring-equal")
                cosine, sine = math.cos(radians), math.sin(radians)
                rows[-1]["state"]["bodies"][1].update(
                    center=[-0.5 + 0.5 * cosine, 2 + 0.5 * sine],
                    angle=0, cost=cosine, sint=sine)
                self.assertEqual(expected, self.audit("weld-spring-equal", rows)["status"])

    def test_stored_rotation_quadrants_and_signed_zero(self):
        for cosine, sine, expected in ((-1, 0, "PHYSICAL_FAILED"),
                                        (-1, -0.0, "PHYSICAL_FAILED"),
                                        (0, 1, "PHYSICAL_FAILED"),
                                        (0, -1, "PHYSICAL_FAILED"),
                                        (0.5, 0.5, "PHYSICAL_FAILED"),
                                        (0.2, 0.5, "PHYSICAL_FAILED"),
                                        (-0.2, 0.5, "PHYSICAL_FAILED"),
                                        (1, -0.0, "PHYSICAL_PASSED")):
            with self.subTest(cosine=cosine, sine=sine):
                rows = self.rows("weld-spring-equal")
                rows[-1]["state"]["bodies"][1].update(
                    center=[-0.5 + 0.5 * cosine, 2 + 0.5 * sine],
                    angle=0, cost=cosine, sint=sine)
                self.assertEqual(expected, self.audit("weld-spring-equal", rows)["status"])

    def test_bad_stored_rotation_rejects_even_with_matching_anchor(self):
        for cosine, sine in ((0, 0), (1.001, 0), (1, 1.001),
                             (float("nan"), 0), (1, float("inf"))):
            with self.subTest(cosine=cosine, sine=sine):
                rows = self.rows("weld-spring-equal")
                rows[-1]["state"]["bodies"][1].update(
                    center=[0, 2], angle=0, cost=cosine, sint=sine)
                self.assertEqual("INVALID", self.audit("weld-spring-equal", rows)["status"])

    def test_out_of_bound_pulley_extension_and_compression_fail(self):
        for offset in (-0.02, 0.02):
            rows = self.rows("pulley-taut")
            rows[-1]["state"]["joint"]["anchor2"][1] = offset
            rows[-1]["state"]["bodies"][1]["center"][1] = offset
            with self.subTest(offset=offset):
                self.assertEqual("PHYSICAL_FAILED", self.audit("pulley-taut", rows)["status"])

    def test_missing_nonfinite_wrong_identity_alias_and_callback_fail_closed(self):
        mutations = [
            lambda r: r.pop(),
            lambda r: r[-1]["state"]["joint"].pop("anchor2"),
            lambda r: r[-1]["state"].update(unbounded=1.0),
            lambda r: r[-1]["state"]["joint"].update(unbounded=1.0),
            lambda r: r[-1]["state"]["joint"]["anchor2"].__setitem__(1, float("inf")),
            lambda r: r[-1]["state"]["joint"]["anchor2"].__setitem__(0, -0.25),
            lambda r: r[-1]["state"]["bodies"][0].update(id="wrong"),
            lambda r: r[1].update(callback="end"),
            lambda r: r[1].update(order=1),
            lambda r: r[0].update(jar_sha256="0" * 64),
        ]
        for mutate in mutations:
            rows = self.rows("weld-spring-equal")
            mutate(rows)
            with self.subTest(mutation=mutate):
                self.assertEqual("INVALID", self.audit("weld-spring-equal", rows)["status"])

    def test_wrong_frozen_hash_or_empty_suite_fails_closed(self):
        case = "pulley-taut"
        rows = self.rows(case)
        path = self.write(case, rows)
        self.manifest["cases"][case]["stream_sha256"] = "0" * 64
        self.assertEqual("INVALID", audit_quality(self.declaration, self.manifest, case, path)["status"])
        self.manifest["cases"][case]["stream_sha256"] = hashlib.sha256(packed(rows)).hexdigest()
        self.assertEqual("INVALID", self.audit(case, [rows[0]])["status"])

    def test_frozen_baseline_and_actual_state_out_of_limit(self):
        root = Path(__file__).resolve().parent
        declaration = json.loads((root / "weld-pulley-physical-declaration.json").read_text())
        manifest = json.loads((root / "weld-pulley-physical-manifest.json").read_text())
        for case in ("weld-spring-equal", "pulley-taut"):
            with self.subTest(case=case):
                reference = root / "references" / manifest["cases"][case]["file"]
                self.assertEqual("PHYSICAL_PASSED", audit_quality(declaration, manifest, case, reference)["status"])
                rows = [json.loads(line) for line in gzip.decompress(reference.read_bytes()).splitlines()]
                state = rows[4]["state"]
                state["bodies"][1]["center"][1] += 0.02
                state["joint"]["anchor2"][1] += 0.02
                altered = packed(rows)
                path = self.root / reference.name
                path.write_bytes(gzip.compress(altered, mtime=0))
                selected = copy.deepcopy(manifest)
                selected["cases"][case]["gzip_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                selected["cases"][case]["stream_sha256"] = hashlib.sha256(altered).hexdigest()
                selected["cases"][case]["input_sha256"] = hashlib.sha256(altered.splitlines()[0]).hexdigest()
                self.assertEqual("PHYSICAL_FAILED", audit_quality(declaration, selected, case, path)["status"])


if __name__ == "__main__":
    unittest.main()
