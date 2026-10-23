import json
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from actual_capture_receipt import (FILE_NAMES, FocusedRejected,
                                    _expected_classes, _xml_mirror,
                                    load_version6_archive, verify_existing)
from prospective_compare import verify_arithmetic_captures
from receipt import Rejected


class FocusedReplayTest(unittest.TestCase):
    def test_full_mirror_requires_order_and_final_newline(self):
        xml = (b'<testsuite><system-out>first\nsecond\n'
               b'</system-out></testsuite>')
        self.assertEqual(_xml_mirror({"xml": xml, "mirror": b"first\nsecond\n"}),
                         hashlib.sha256(b"first\nsecond\n").hexdigest())
        for changed in (b"second\nfirst\n", b"first\nsecond", b"first\nSECOND\n"):
            with self.subTest(mirror=changed), self.assertRaises(FocusedRejected):
                _xml_mirror({"xml": xml, "mirror": changed})

    def test_duplicate_compiled_provider_and_engine_shadow_fail(self):
        def packed(entries):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for name, value in sorted(entries):
                    item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    item.compress_type = zipfile.ZIP_STORED
                    archive.writestr(item, value)
            return output.getvalue()

        artifact = packed([("org/dyn4j/geometry/Transform.class", b"engine")])
        base = [("main/portable/NumericalRecorder.class", b"recorder"),
                ("test/portable/NumericProbeMatrixTest.class", b"probe"),
                ("test/portable/PortableMatrixTest.class", b"matrix")]
        good = packed(base + [("test/portable/Fixture.class", b"fixture")])
        expected, _ = _expected_classes({"portable_classes": good,
                                         "artifact": artifact})
        self.assertEqual(expected["org/dyn4j/geometry/Transform"], b"engine")
        for duplicate in (
                [("test/portable/Fixture.class", b"fixture"),
                 ("main/portable/Fixture.class", b"shadow")],
                [("test/org/dyn4j/geometry/Transform.class", b"shadow")]):
            with self.subTest(duplicate=duplicate), self.assertRaises(FocusedRejected):
                _expected_classes({"portable_classes": packed(base + duplicate),
                                   "artifact": artifact})

    def test_public_replay_compares_exact_case_after_validated_whole_lane(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            archive = root / "capture"
            lane = root / "jvm"
            baseline = root / "baseline"
            attestation = root / "attestation.json"
            for path in (archive, lane / "cases", baseline):
                path.mkdir(parents=True)
            attestation.write_text("{}")
            case = b'{"id":"joint-Revolute-LimitsEnabled-false"}\n'
            name = "joint-Revolute-LimitsEnabled-false.jsonl"
            (archive / name).write_bytes(case)
            (lane / "cases" / name).write_bytes(case)
            (archive / "receipt.json").write_bytes(b"receipt\n")
            (lane / "receipt.json").write_text(json.dumps({
                "candidate_commit": "a" * 40,
                "artifact_sha256": {"target": "b" * 64},
                "runtime": {"executable_sha256": "c" * 64}}))
            focused = {"candidate_commit": "a" * 40,
                       "source_archive_sha256": "d" * 64,
                       "artifact_sha256": "b" * 64,
                       "runtime_sha256": "c" * 64,
                       "case_sha256": hashlib.sha256(case).hexdigest()}
            with patch("actual_capture_receipt.compare_host", return_value={
                    "status": "FAILED_PHYSICAL",
                    "candidate_source_sha256": "d" * 64}) as whole, \
                    patch("actual_capture_receipt.replay_version6",
                          return_value=focused), \
                    patch("actual_capture_receipt.comparison_coverage",
                          return_value={"frozen_case_ids": ["frozen"]}):
                result = verify_existing(archive, lane, baseline, attestation)
            self.assertEqual(result["qualification"], "UNPASSED")
            self.assertEqual(result["whole_lane_status"], "FAILED_PHYSICAL")
            self.assertIsNone(whole.call_args.kwargs["arithmetic_captures"])
            (lane / "cases" / name).write_bytes(case + b" ")
            with patch("actual_capture_receipt.compare_host", return_value={
                    "status": "FAILED_PHYSICAL",
                    "candidate_source_sha256": "d" * 64}), \
                    patch("actual_capture_receipt.replay_version6",
                          return_value=focused), \
                    patch("actual_capture_receipt.comparison_coverage",
                          return_value={"frozen_case_ids": ["frozen"]}):
                with self.assertRaises(FocusedRejected):
                    verify_existing(archive, lane, baseline, attestation)

    def test_version6_inventory_and_old_status_forgery_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            for name in FILE_NAMES.values():
                (root / name).write_bytes(b"raw")
            (root / "worker-class-load-41.log").write_bytes(b"class")
            (root / "worker-arguments-41.log").write_bytes(b"arguments")
            receipt = root / "receipt.json"
            receipt.write_text('{"schema":"portable-arithmetic-capture-receipt/5",'
                               '"status":"PASSED_FOCUSED_METHOD_EVIDENCE"}')
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)
            receipt.write_text('{"schema":"portable-arithmetic-capture-receipt/6",'
                               '"schema":"portable-arithmetic-capture-receipt/6"}')
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)
            receipt.write_text('{"schema":"portable-arithmetic-capture-receipt/6"}')
            self.assertEqual(load_version6_archive(root)[0]["schema"],
                             "portable-arithmetic-capture-receipt/6")
            (root / "extra.txt").write_bytes(b"extra")
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)
            (root / "extra.txt").unlink()
            (root / "mirror.log").unlink()
            (root / "mirror.log").symlink_to(root / "capture.xml")
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)

    def test_boolean_only_root_still_fails_global_method_inventory(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            (root / "captureRevoluteLimitsFalse").mkdir()
            with self.assertRaisesRegex(Rejected, "method inventory"):
                verify_arithmetic_captures(root, root, "a" * 40,
                                           "b" * 64, "c" * 64)

    def test_public_replay_validates_whole_lane_first_without_capture_override(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            archive = root / "capture"
            lane = root / "jvm"
            baseline = root / "baseline"
            attestation = root / "attestation.json"
            for path in (archive, lane, baseline):
                path.mkdir()
            attestation.write_text("{}")
            (lane / "receipt.json").write_text(json.dumps({
                "candidate_commit": "a" * 40, "artifact_sha256": {"target": "b" * 64},
                "runtime": {"executable_sha256": "c" * 64}}))
            order = []

            def whole(*args, **kwargs):
                order.append("whole")
                self.assertIsNone(kwargs["arithmetic_captures"])
                return {"candidate_source_sha256": "d" * 64,
                        "operation_binding": "UNPASSED_NOT_EXECUTED"}

            def focused(*args, **kwargs):
                order.append("focused")
                return {"candidate_commit": "a" * 40,
                        "source_archive_sha256": "d" * 64,
                        "artifact_sha256": "b" * 64,
                        "runtime_sha256": "c" * 64,
                        "case_sha256": "e" * 64}

            with patch("actual_capture_receipt.compare_host", side_effect=whole), \
                    patch("actual_capture_receipt.replay_version6", side_effect=focused), \
                    patch("actual_capture_receipt.comparison_coverage",
                          return_value={"frozen_case_ids": ["frozen"]}):
                with self.assertRaises(FocusedRejected):
                    verify_existing(archive, lane, baseline, attestation)
            self.assertEqual(order, ["whole", "focused"])


if __name__ == "__main__":
    unittest.main()
