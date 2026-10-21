import copy
import hashlib
import unittest
from unittest.mock import patch

import external_rotation_binding as external
from actual_arithmetic import CaptureRejected
from test_actual_arithmetic import synthetic_rotation_premise_lines, xml_for


class SyntheticExternalBindingTest(unittest.TestCase):
    def setUp(self):
        self.files = {"xml": xml_for(synthetic_rotation_premise_lines(),
                                      "captureRotationPremises"),
                      "artifact": b"synthetic-artifact", "source": b"synthetic-source",
                      "runtime": b"synthetic-runtime"}
        records = list(external._records(self.files, "captureRotationPremises"))
        trace = b"".join(row[3] for row in records)
        self.receipt = {"candidate_commit": "a" * 40, "worker_pid": "42",
                        "summary": {"trace_sha256": hashlib.sha256(trace).hexdigest()}}
        self.method = "captureRotationPremises"

    def test_source_schedule_binds_all_synthetic_cases(self):
        with patch.object(external, "_load", return_value=(self.receipt,
                                                           self.files, self.method)):
            bundle = external.produce("synthetic", "synthetic")
            result = external.replay("synthetic", "synthetic", bundle)
            self.assertEqual(len(result), 5)
            self.assertEqual({row["status"] for row in result.values()},
                             {"PASSED_ARITHMETIC"})
            self.assertEqual({row["qualification"] for row in result.values()},
                             {"UNPASSED"})
            for case_id in bundle["bindings"]:
                binding = bundle["bindings"][case_id]
                self.assertEqual(binding["expected_calls"], [{
                    "step": 1, "body_id": "b0", "kind": "rotate",
                    "branch": "fixture", "input_kind": "angle"}])
            for field, value in (("producer_process", "pid:43"),
                                 ("target_source_sha256", "0" * 64),
                                 ("artifact_sha256", "0" * 64),
                                 ("trace_sha256", "0" * 64),
                                 ("audit_schema", "portable-rotation-audit/1"),
                                 ("allowed_evaluations", ["fused"])):
                changed = copy.deepcopy(bundle)
                changed["bindings"]["rotation-premise-mode"][field] = value
                with self.subTest(field=field), self.assertRaises(CaptureRejected):
                    external.replay("synthetic", "synthetic", changed)
            for field, value in (("branch", "joint"), ("body_id", "b1"),
                                 ("step", 2), ("kind", "lerp-reset")):
                changed = copy.deepcopy(bundle)
                changed["bindings"]["rotation-premise-mode"]["expected_calls"][0][field] = value
                with self.subTest(field=field), self.assertRaises(CaptureRejected):
                    external.replay("synthetic", "synthetic", changed)
            missing = copy.deepcopy(bundle)
            del missing["bindings"]["rotation-premise-mode"]
            with self.assertRaises(CaptureRejected):
                external.replay("synthetic", "synthetic", missing)

    def test_changed_verified_process_or_worker_trace_rejects(self):
        with patch.object(external, "_load", return_value=(self.receipt,
                                                           self.files, self.method)):
            bundle = external.produce("synthetic", "synthetic")
        changed_receipt = copy.deepcopy(self.receipt)
        changed_receipt["worker_pid"] = "43"
        with patch.object(external, "_load", return_value=(changed_receipt,
                                                           self.files, self.method)):
            with self.assertRaises(CaptureRejected):
                external.replay("synthetic", "synthetic", bundle)
        changed_receipt = copy.deepcopy(self.receipt)
        changed_receipt["summary"]["trace_sha256"] = "0" * 64
        with patch.object(external, "_load", return_value=(changed_receipt,
                                                           self.files, self.method)):
            with self.assertRaises(CaptureRejected):
                external.replay("synthetic", "synthetic", bundle)


if __name__ == "__main__":
    unittest.main()
