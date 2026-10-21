import copy
import hashlib
import io
import json
import os
import struct
import subprocess
import tempfile
import unittest
import warnings
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

import actual_arithmetic
import capture_actual
from actual_arithmetic import CaptureRejected, expected_case_ids, verify_capture
from test_rotation_marker import bits, marker


def xml_for(lines, method="captureGeometry"):
    output = "\n".join(lines) + "\n"
    return (f'<testsuite tests="1" skipped="0" failures="0" errors="0">'
            f'<testcase classname="portable.ProspectiveArithmeticTest" name="{method}[jvm]"/>'
            f'<system-out>{escape(output)}</system-out></testsuite>').encode()


def fixture():
    operation = marker()
    operation["method"] = "geometryCollisionBoundaryAndScale"
    case_id = "geometry-boundary-s0-o0-d0"
    operation.update(case_id=case_id, step=1, body_id="b0")
    identity = ["3ff0000000000000", "0000000000000000"]
    state_body = {"id": "b0", "transform": {"getCost": 1.0, "getSint": 0.0}}
    rows = [
        "NUMERICAL_JSON " + json.dumps({"kind": "inputs", "id": case_id,
                                        "steps": 1,
                                        "setup": {"bodies": [{"id": "b0"}]},
                                        "initial": {"bodies": [state_body]}}),
        "PROSPECTIVE_ROTATION_JSON " + json.dumps(operation),
        "NUMERICAL_JSON " + json.dumps({"kind": "state", "id": case_id,
                                        "step": 1, "order": 0,
                                        "state": {"bodies": [state_body]}}),
        "PROSPECTIVE_BINDING_JSON " + json.dumps({
            "kind": "body-step", "case_id": case_id, "step": 1,
            "bodies": [{"body_id": "b0", "calls": 1,
                        "pre": identity, "post": identity}],
            "temporary_calls": 0}),
        "NUMERICAL_JSON " + json.dumps({"kind": "case-end", "id": case_id,
                                        "steps": 1}),
    ]
    return rows


def focused_wheel_fixture():
    case_id = "joint-Wheel-active"
    rows = fixture()
    for index in (0, 2, 4):
        row = json.loads(rows[index].split(" ", 1)[1])
        row["id"] = case_id
        if index == 0:
            row["setup"]["bodies"].append({"id": "b1"})
            second = copy.deepcopy(row["initial"]["bodies"][0])
            second["id"] = "b1"
            row["initial"]["bodies"].append(second)
        elif index == 2:
            second = copy.deepcopy(row["state"]["bodies"][0])
            second["id"] = "b1"
            row["state"]["bodies"].append(second)
        rows[index] = "NUMERICAL_JSON " + json.dumps(row)
    original = json.loads(rows[1].split(" ", 1)[1])
    calls = []
    for sequence, (body_id, branch, token) in enumerate((
            ("b1", "integrate", 1), ("b0", "joint", 0),
            ("b1", "joint", 1))):
        call = copy.deepcopy(original)
        call.update(method="everyJointWithInitialAndApplicableActiveModes",
                    case_id=case_id, body_id=body_id, branch=branch,
                    sequence=sequence, target_token=token,
                    angle_bits=bits(0.0), trig=[bits(1.0), bits(0.0)])
        calls.append("PROSPECTIVE_ROTATION_JSON " + json.dumps(call))
    rows[1:2] = calls
    binding = json.loads(rows[5].split(" ", 1)[1])
    binding["case_id"] = case_id
    binding["bodies"][0]["calls"] = 1
    binding["bodies"].append({"body_id": "b1", "calls": 2,
                              "pre": [bits(1.0), bits(0.0)],
                              "post": [bits(1.0), bits(0.0)]})
    rows[5] = "PROSPECTIVE_BINDING_JSON " + json.dumps(binding)
    return rows


class SourceArchiveTest(unittest.TestCase):
    COMMIT = "cd21a4bd7d6731a096597f97966db9e02b9de448"
    CANONICAL_SHA256 = "7958113412c14be8e106706a77871eba4dc8c4e1335c38fd01c7b9e18d26e12d"

    @staticmethod
    def git_setting(value):
        return patch.dict(os.environ, {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.autocrlf",
            "GIT_CONFIG_VALUE_0": value,
        })

    def canonical_source(self):
        result = subprocess.run(("git", "-c", "core.autocrlf=false",
                                 "--no-replace-objects", "archive", "--format=tar",
                                 self.COMMIT), cwd=actual_arithmetic._ROOT,
                                capture_output=True, check=True)
        self.assertEqual(hashlib.sha256(result.stdout).hexdigest(),
                         self.CANONICAL_SHA256)
        return result.stdout

    def test_archive_is_canonical_under_both_checkout_settings(self):
        for setting in ("false", "true"):
            with self.subTest(core_autocrlf=setting), self.git_setting(setting):
                archive = actual_arithmetic._source_archive(self.COMMIT)
                self.assertEqual(hashlib.sha256(archive).hexdigest(),
                                 self.CANONICAL_SHA256)

    def test_receipt_source_check_rejects_changed_raw_archive(self):
        source = self.canonical_source()
        files = {name: b"fixture" for name in actual_arithmetic._RECEIPT_FILES}
        files["source"] = source
        class ReachedLocalBinaryCheck(Exception):
            pass
        with self.git_setting("true"), patch.object(
                actual_arithmetic, "_check_local_binaries",
                side_effect=ReachedLocalBinaryCheck):
            with self.assertRaises(ReachedLocalBinaryCheck):
                actual_arithmetic.make_capture_receipt(
                    files, "captureGeometry", self.COMMIT, [],
                    actual_arithmetic._PINNED_JAVA)
            changed = bytearray(source)
            changed[1024] ^= 1
            files["source"] = bytes(changed)
            with self.assertRaisesRegex(CaptureRejected,
                                        "source archive differs from candidate commit"):
                actual_arithmetic.make_capture_receipt(
                    files, "captureGeometry", self.COMMIT, [],
                    actual_arithmetic._PINNED_JAVA)

    def test_archive_rejects_non_exact_commit_pins_before_git(self):
        with patch.object(actual_arithmetic.subprocess, "run",
                          side_effect=AssertionError("git was invoked")) as run:
            for pin in ("HEAD", self.COMMIT[:12], self.COMMIT.upper(),
                        self.COMMIT + "0", "-" + self.COMMIT):
                with self.subTest(pin=pin), self.assertRaises(CaptureRejected):
                    actual_arithmetic._source_archive(pin)
            run.assert_not_called()


class CaptureArchiveTest(unittest.TestCase):
    def test_success_archive_rejects_nonworker_trace_and_environment_text(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as scratch:
            output = Path(scratch)
            worker_log = output / "worker-class-load-42.log"
            for name in capture_actual.archive_file_names("captureWheelActive", worker_log):
                if name != "worker-write-traces.zip":
                    (output / name).write_bytes(b"safe")
            with zipfile.ZipFile(output / "worker-write-traces.zip", "w") as archive:
                archive.writestr("trace.42", b"safe")
            capture_actual.verify_archive_inventory(output, "captureWheelActive", worker_log)

            trace = output / "worker-write-trace.41"
            trace.write_bytes(b'write(2, "DYN4K_CAPTURE_ENV_SENTINEL=portable-capture-check", 53) = 53\n')
            with self.assertRaisesRegex(CaptureRejected, "archive inventory differs"):
                capture_actual.verify_archive_inventory(output, "captureWheelActive", worker_log)
            trace.unlink()

            log = output / "gradle.log"
            log.write_bytes(b"DYN4K_CAPTURE_ENV_SENTINEL=portable-capture-check")
            with self.assertRaisesRegex(CaptureRejected, "archive exposed the environment"):
                capture_actual.verify_archive_inventory(output, "captureWheelActive", worker_log)
            log.write_bytes(b"safe")

            with zipfile.ZipFile(output / "worker-write-traces.zip", "w") as archive:
                archive.writestr("trace.42", b"OLLAMA_API_KEY=redacted")
            with self.assertRaisesRegex(CaptureRejected, "archive exposed the environment"):
                capture_actual.verify_archive_inventory(output, "captureWheelActive", worker_log)
            with zipfile.ZipFile(output / "worker-write-traces.zip", "w") as archive:
                archive.writestr("trace.42", b"safe")

            (output / "unexpected").mkdir()
            with self.assertRaisesRegex(CaptureRejected, "archive inventory differs"):
                capture_actual.verify_archive_inventory(output, "captureWheelActive", worker_log)


class ActualArithmeticTest(unittest.TestCase):
    def test_accepted_selection_after_resets_matches_callback_and_targets(self):
        rows = fixture()
        case_id = "geometry-boundary-s0-o0-d0"
        identity = [bits(1.0), bits(0.0)]
        second = {"id": "b1", "transform": {"getCost": 1.0, "getSint": 0.0}}
        inputs = json.loads(rows[0].split(" ", 1)[1])
        inputs["setup"]["bodies"].append({"id": "b1"})
        inputs["initial"]["bodies"].append(second)
        rows[0] = "NUMERICAL_JSON " + json.dumps(inputs)
        state = json.loads(rows[2].split(" ", 1)[1])
        state["state"]["bodies"].append(second)
        state["order"] = 1
        rows[2] = "NUMERICAL_JSON " + json.dumps(state)
        receipt = json.loads(rows[3].split(" ", 1)[1])
        receipt["bodies"].append({"body_id": "b1", "calls": 0,
                                  "pre": identity, "post": identity})
        rows[3] = "PROSPECTIVE_BINDING_JSON " + json.dumps(receipt)
        operation = json.loads(rows[1].split(" ", 1)[1])
        operation.update(kind="lerp-reset", source="direct", raw=[None, None],
                         trig=identity, post=identity, angle_bits=bits(0.0),
                         alpha_bits=bits(0.5), start_angle_bits=bits(0.0),
                         end_angle_bits=bits(0.0), diff_bits=bits(0.0),
                         start=identity, end=identity)
        rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(operation)
        callback = {"kind": "event", "id": case_id, "step": 1, "order": 0,
                    "name": "toi.payload.bodies",
                    "payload": {"bodies": [0, 1], "time": 0.5}}
        selection = {"kind": "toi-accepted", "case_id": case_id, "step": 1,
                     "body_ids": ["b0", "b1"], "reset_body_ids": ["b0"],
                     "time_bits": bits(0.5)}
        rows.insert(1, "NUMERICAL_JSON " + json.dumps(callback))
        rows.insert(3, "PROSPECTIVE_BINDING_JSON " + json.dumps(selection))
        expected = [case_id]
        result = verify_capture(xml_for(rows), "captureGeometry", expected)
        self.assertEqual(result["selected_resets"], 1)
        self.assertEqual(result["body_step_receipts"], 2)
        self.assertEqual(verify_capture(xml_for(rows), "captureGeometry", expected,
                                        "post")["selected_resets"], 1)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(rows), "captureGeometry", expected, "pre")
        for changed in (rows[:3] + rows[4:],
                        [*rows[:3], rows[3].replace(bits(0.5), bits(0.25)),
                         *rows[4:]]):
            with self.assertRaises(CaptureRejected):
                verify_capture(xml_for(changed), "captureGeometry", expected)

    def test_zero_call_body_step_is_required_and_matches_state(self):
        rows = fixture()
        rows.pop(1)
        receipt = json.loads(rows[2].split(" ", 1)[1])
        receipt["bodies"][0]["calls"] = 0
        rows[2] = "PROSPECTIVE_BINDING_JSON " + json.dumps(receipt)
        expected = ["geometry-boundary-s0-o0-d0"]
        result = verify_capture(xml_for(rows), "captureGeometry", expected)
        self.assertEqual(result["operations_verified"], 0)
        self.assertEqual(result["body_step_receipts"], 1)
        for changed in (rows[:2] + rows[3:],
                        [*rows[:2], rows[2].replace('"calls": 0', '"calls": 1'),
                         rows[3]]):
            with self.assertRaises(CaptureRejected):
                verify_capture(xml_for(changed), "captureGeometry", expected)

    def test_temporary_operation_is_counted_without_body_identity(self):
        rows = fixture()
        operation = json.loads(rows[1].split(" ", 1)[1])
        operation["body_id"] = None
        rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(operation)
        receipt = json.loads(rows[3].split(" ", 1)[1])
        receipt["bodies"][0]["calls"] = 0
        receipt["temporary_calls"] = 1
        rows[3] = "PROSPECTIVE_BINDING_JSON " + json.dumps(receipt)
        result = verify_capture(xml_for(rows), "captureGeometry",
                                ["geometry-boundary-s0-o0-d0"])
        self.assertEqual(result["temporary_operations"], 1)
        receipt["temporary_calls"] = 0
        rows[3] = "PROSPECTIVE_BINDING_JSON " + json.dumps(receipt)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(rows), "captureGeometry",
                           ["geometry-boundary-s0-o0-d0"])

    def test_listener_callback_alone_cannot_select_reset(self):
        rows = fixture()
        callback = {"kind": "event", "id": "geometry-boundary-s0-o0-d0",
                    "step": 1, "order": 0, "name": "toi.payload.bodies",
                    "payload": {"bodies": [0, 0], "time": 0.5}}
        selection = {"kind": "toi-accepted", "case_id": "geometry-boundary-s0-o0-d0",
                     "step": 1, "body_ids": ["b0", "b0"],
                     "reset_body_ids": ["b0"], "time_bits": "3fe0000000000000"}
        rows.insert(1, "NUMERICAL_JSON " + json.dumps(callback))
        rows.insert(2, "PROSPECTIVE_BINDING_JSON " + json.dumps(selection))
        state = json.loads(rows[4].split(" ", 1)[1])
        state["order"] = 1
        rows[4] = "NUMERICAL_JSON " + json.dumps(state)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(rows), "captureGeometry",
                           ["geometry-boundary-s0-o0-d0"])
        selection["time_bits"] = "3fd0000000000000"
        rows[2] = "PROSPECTIVE_BINDING_JSON " + json.dumps(selection)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(rows), "captureGeometry",
                           ["geometry-boundary-s0-o0-d0"])

    def test_same_target_chain_rejects_reordered_operations(self):
        rows = fixture()
        first = json.loads(rows[1].split(" ", 1)[1])
        second = copy.deepcopy(first)
        second["sequence"] = 1
        second["angle_bits"] = struct.pack(">d", 1e-16).hex()
        second["trig"] = [struct.pack(">d", 1.0).hex(), second["angle_bits"]]
        second["raw"] = second["trig"][:]
        second["post"] = second["trig"][:]
        second["case_id"] = first["case_id"]
        second["step"] = first["step"]
        second["body_id"] = first["body_id"]
        rows.insert(2, "PROSPECTIVE_ROTATION_JSON " + json.dumps(second))
        receipt = json.loads(rows[4].split(" ", 1)[1])
        receipt["bodies"][0]["calls"] = 2
        receipt["bodies"][0]["post"] = second["post"]
        rows[4] = "PROSPECTIVE_BINDING_JSON " + json.dumps(receipt)
        state = json.loads(rows[3].split(" ", 1)[1])
        state["state"]["bodies"][0]["transform"]["getSint"] = 1e-16
        rows[3] = "NUMERICAL_JSON " + json.dumps(state)
        expected = ["geometry-boundary-s0-o0-d0"]
        self.assertEqual(verify_capture(xml_for(rows), "captureGeometry", expected)
                         ["operations_verified"], 2)
        first["sequence"] = 1
        second["sequence"] = 0
        rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(second)
        rows[2] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(first)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(rows), "captureGeometry", expected)

    def test_bound_case_step_and_body_must_match_trace(self):
        rows = fixture()
        operation = json.loads(rows[1].split(" ", 1)[1])
        rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(operation)
        expected = ["geometry-boundary-s0-o0-d0"]
        bound = verify_capture(xml_for(rows), "captureGeometry", expected)
        self.assertEqual(bound["operations_verified"], 1)
        self.assertEqual(bound["body_bound_operations"], 1)
        for field, value in (("case_id", "other"), ("step", 2), ("body_id", "b9")):
            changed = copy.deepcopy(operation)
            changed[field] = value
            rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(changed)
            with self.subTest(field=field), self.assertRaises(CaptureRejected):
                verify_capture(xml_for(rows), "captureGeometry", expected)

    def test_case_inventory_is_complete(self):
        mapping = expected_case_ids(include_focused=True)
        self.assertEqual(mapping["captureWheelActive"], ["joint-Wheel-active"])
        self.assertNotIn("captureWheelActive", expected_case_ids())
        full = {name: ids for name, ids in mapping.items()
                if name != "captureWheelActive"}
        self.assertEqual(len(full), 15)
        self.assertEqual(sum(map(len, full.values())), 332)
        self.assertEqual(len(mapping["captureJoints"]), 24)
        self.assertEqual(len(mapping["captureCcd"]), 12)
        self.assertEqual(len(set().union(*(set(ids) for ids in full.values()))), 332)
        self.assertEqual(len(set().union(*(set(ids) for ids in full.values())) -
                             {case for ids in full.values() for case in ids
                              if case.startswith("contacts-") or case == "long-free-60" or
                              case.startswith("P-JINT-")}), 318)

    def test_public_capture_seam_verifies_binding_without_case_qualification(self):
        result = verify_capture(xml_for(fixture()), "captureGeometry",
                                ["geometry-boundary-s0-o0-d0"])
        self.assertEqual(result["status"], "VERIFIED_ARITHMETIC_BINDING")
        self.assertEqual(result["qualification"], "UNPASSED")
        self.assertEqual(result["cases"], 1)
        self.assertEqual(result["operations_verified"], 1)
        self.assertEqual(result["steps"], 1)

    def test_focused_wheel_route_rejects_missing_changed_and_reordered_calls(self):
        case_id = "joint-Wheel-active"
        rows = focused_wheel_fixture()

        def check(candidate):
            return verify_capture(xml_for(candidate, "captureWheelActive"),
                                  "captureWheelActive", [case_id])

        self.assertEqual(check(rows)["qualification"], "UNPASSED")
        with self.assertRaises(CaptureRejected):
            check([rows[0], *rows[2:]])
        for field, value in (("raw", [bits(0.5), bits(0.0)]),
                             ("sequence", 1), ("method", "captureJoints"),
                             ("branch", None)):
            changed = copy.deepcopy(rows)
            marker = json.loads(changed[1].split(" ", 1)[1])
            marker[field] = value
            changed[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(marker)
            with self.subTest(field=field), self.assertRaises(CaptureRejected):
                check(changed)
        with self.assertRaises(CaptureRejected):
            check([rows[0], rows[4], *rows[1:4], *rows[5:]])

    def test_focused_wheel_adapter_keeps_synthetic_output_unpassed(self):
        rows = fixture()
        xml = xml_for(rows, "captureWheelActive")
        trace, markers = actual_arithmetic.focused_wheel_stream(xml)
        self.assertEqual(len(trace.splitlines()), 3)
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["raw"], marker()["raw"])
        with self.assertRaisesRegex(CaptureRejected, "target receipt or process exit"):
            actual_arithmetic.assess_focused_wheel(
                {"exit_code": 1}, {"xml": xml}, "a" * 40,
                "/tmp/dyn4k-tools/jdk21/bin/java", "unused", "unused")
        changed = copy.deepcopy(markers)
        changed[0].update(body_id="b0", kind="lerp-reset")
        with self.assertRaisesRegex(CaptureRejected, "reset needs a separate source audit"):
            actual_arithmetic._wheel_rotation_audit(changed)

    def test_focused_wheel_requires_zero_call_and_source_branch_order(self):
        case_id = "joint-Wheel-active"
        rows = focused_wheel_fixture()

        def check(candidate):
            return verify_capture(xml_for(candidate, "captureWheelActive"),
                                  "captureWheelActive", [case_id])

        self.assertEqual(check(rows)["operations_verified"], 3)
        omitted = copy.deepcopy(rows)
        omitted.pop(2)
        last = json.loads(omitted[2].split(" ", 1)[1])
        last["sequence"] = 1
        omitted[2] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(last)
        receipt = json.loads(omitted[4].split(" ", 1)[1])
        receipt["bodies"][0]["calls"] = 0
        omitted[4] = "PROSPECTIVE_BINDING_JSON " + json.dumps(receipt)
        with self.assertRaisesRegex(CaptureRejected, "source call schedule differs"):
            check(omitted)
        wrong_branch = copy.deepcopy(rows)
        first = json.loads(wrong_branch[1].split(" ", 1)[1])
        first["branch"] = "contact"
        wrong_branch[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(first)
        with self.assertRaisesRegex(CaptureRejected, "source call schedule differs"):
            check(wrong_branch)

    def test_worker_write_witness_requires_actual_worker_stream(self):
        xml = xml_for(focused_wheel_fixture(), "captureWheelActive")
        output = ET.fromstring(xml).find("system-out").text.encode()
        worker = ('execve("/tmp/dyn4k-tools/jdk21/bin/java", '
                  '["GradleWorkerMain"], 0x0) = 0\nclone(0) = 43\n').encode()
        execution = b'42 ' + worker.splitlines()[0] + b'\n'

        def archive(stream=output, source=worker, child="43", extras=(),
                    omit_child=False):
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w") as traces:
                traces.writestr("trace.42", source)
                if not omit_child:
                    traces.writestr("trace." + child,
                                    f'write(51, {json.dumps(stream.decode())}, '
                                    f'{len(stream)}) = {len(stream)}\n')
                for name, content in extras:
                    traces.writestr(name, content)
            return payload.getvalue()

        result = actual_arithmetic.verify_worker_write_witness(
            archive(), xml, "42", execution)
        self.assertEqual(result["status"], "PASSED_KERNEL_WORKER_WRITES")
        self.assertEqual(result["operation_lines"], 3)
        at = b'execveat(AT_FDCWD, "/jdk/java", ["java"], 0x0, 0) = -1 ENOENT\n'
        with self.assertRaises(CaptureRejected):
            actual_arithmetic.verify_worker_write_witness(
                archive(source=worker + at), xml, "42", execution,
                complete_exec=True)
        full_log = execution + b"42 " + at
        self.assertEqual(actual_arithmetic.verify_worker_write_witness(
            archive(source=worker + at), xml, "42", full_log,
            complete_exec=True)["status"], "PASSED_KERNEL_WORKER_WRITES")
        with self.assertRaises(CaptureRejected):
            actual_arithmetic.verify_worker_write_witness(
                archive(source=worker), xml, "42", full_log,
                complete_exec=True)
        with self.assertRaises(CaptureRejected):
            actual_arithmetic.verify_worker_write_witness(
                archive(source=worker + at), xml, "42", full_log + b"42 " + at,
                complete_exec=True)
        for changed, source, child, payload, pid in (
                (output.replace(b"PROSPECTIVE_ROTATION_JSON ", b"REMOVED_", 1), worker,
                 "43", xml, "42"),
                (output, worker.replace(b"clone(0) = 43", b"clone(0) = 44"),
                 "43", xml, "42"),
                (output, worker, "43", xml.replace(b"NUMERICAL_JSON ",
                                                    b"NUMERIC_CHANGED ", 1), "42"),
                (output, worker, "43", xml, "99")):
            with self.assertRaises(CaptureRejected):
                actual_arithmetic.verify_worker_write_witness(
                    archive(changed, source, child), payload, pid, execution)
        for changed in (archive(omit_child=True), archive(child="44")):
            with self.assertRaisesRegex(CaptureRejected,
                                        "worker write child trace is missing"):
                actual_arithmetic.verify_worker_write_witness(
                    changed, xml, "42", execution)
        for name in ("trace.999999", "trace.043", "trace.43"):
            with self.subTest(extra_member=name), warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with self.assertRaisesRegex(CaptureRejected,
                                            "worker write trace inventory differs"):
                    actual_arithmetic.verify_worker_write_witness(
                        archive(extras=((name, b"unrelated trace\n"),)),
                        xml, "42", execution)

    def test_missing_extra_reordered_and_wrong_method_fail(self):
        original = fixture()
        expected = ["geometry-boundary-s0-o0-d0"]
        for rows in (original[:-1], original + original[-1:],
                     [original[1], original[0], *original[2:]]):
            with self.subTest(rows=rows):
                with self.assertRaises(CaptureRejected):
                    verify_capture(xml_for(rows), "captureGeometry", expected)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(original, "captureJoints"), "captureGeometry", expected)
        changed = copy.deepcopy(original)
        changed[1] = changed[1].replace('"sequence": 0', '"sequence": 1')
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(changed), "captureGeometry", expected)
        changed = copy.deepcopy(original)
        changed[1] = changed[1].replace('"body_id": "b0"',
                                        '"body_id": "b0", "body_id": "b0"')
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(changed), "captureGeometry", expected)
        changed = copy.deepcopy(original)
        state = json.loads(changed[2].split(" ", 1)[1])
        state["order"] = 2
        changed[2] = "NUMERICAL_JSON " + json.dumps(state)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(changed), "captureGeometry", expected)
        changed = copy.deepcopy(original)
        changed.insert(2, "NUMERICAL_JSON " + json.dumps({
            "kind": "unknown", "id": expected[0], "step": 1, "order": 0}))
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(changed), "captureGeometry", expected)

    def test_adverse_operation_and_nonfinite_fail(self):
        rows = fixture()
        operation = json.loads(rows[1].split(" ", 1)[1])
        operation["raw"][0] = "7ff0000000000000"
        rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(operation)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(rows), "captureGeometry",
                           ["geometry-boundary-s0-o0-d0"])


if __name__ == "__main__":
    unittest.main()
