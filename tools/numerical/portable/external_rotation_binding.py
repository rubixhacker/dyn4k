import argparse
import hashlib
import io
import json
import struct
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

import actual_arithmetic as actual
import capture_actual
from cases import declared_cases
from orthogonality import source_rotation_cap
from rotation_oracle import SOURCE_REVISION, verify_rotation_arithmetic


_WHEEL_COMMIT = "7d319d5027f2b10c11eae7f4574e6edf407449c0"
_SOURCE_PINS = {
    "captureWheelActive": {
        "tools/numerical/portable/src/commonTest/kotlin/portable/ProspectiveArithmeticTest.kt":
            "b95cf31b47b1b7f1c8a05d3b6b91fa17d059e7f7d4380ff6a81cb69f4839ca8d",
        "tools/numerical/portable/src/commonTest/kotlin/portable/PortableMatrixTest.kt":
            "9354ab929281c8e9750476c632673d455214e3dac702a2bab9718dffe1287457",
    },
    "captureRotationPremises": {
        "tools/numerical/portable/src/jvmTest/kotlin/portable/RotationPremiseFixtureTest.kt":
            "ea960ab2a11aa5175c18cd14d13b59e96d285b28d1784a024a89ac207a479390",
    },
}
_COMMON_SOURCE_PINS = {
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/geometry/RotationOperationTap.kt":
        "9833fdecc356581fbe549b5388f342458c66727bbc5244f03a6dd9285cf2e517",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/geometry/Transform.kt":
        "ec22ca59049bbe090f381f133a43d7e1e72b3b220960ec751c3f278b7b280747",
}
_WHEEL_STEP_CALLS = (("b1", "integrate"), ("b0", "joint"), ("b1", "joint"))
_FIXTURE_IDS = (
    "rotation-premise-mode", "rotation-premise-zero",
    "rotation-premise-negative-zero",
    "rotation-premise-tiny-angle", "rotation-premise-subnormal-product",
)
_MODES = ["strict", "fma_left", "fma_right", "fused"]
_FILES = {
    "xml": "capture.xml", "stage_log": "stage.log", "gradle_log": "gradle.log",
    "execve_log": "execve.log", "artifact": "artifact.jar",
    "runtime": "runtime-java", "source": "source.tar",
    "worker_classpath": "worker-classpath.txt",
    "portable_classes": "portable-classes.zip",
    "worker_write_traces": "worker-write-traces.zip",
}
_MANIFEST_FIELDS = (
    "expected_calls", "body_step_receipts", "accepted_toi_resets",
    "accepted_toi_events", "reset_start_rotations", "reset_end_rotations",
    "pair_inputs", "allowed_evaluations", "audit_schema",
)
_RECEIPT_FIELDS = (
    "producer_process", "producer_command", "artifact_sha256",
    "target_source_sha256", "runtime_id", "trace_sha256",
    "payload_sha256", "audit_sha256", "manifest_sha256",
    "operation_source_revision", "audit_schema",
)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _source_pins(source, method):
    pins = _COMMON_SOURCE_PINS | _SOURCE_PINS[method]
    try:
        with tarfile.open(fileobj=io.BytesIO(source)) as archive:
            for path, digest in pins.items():
                member = archive.getmember(path)
                if not member.isfile() or _sha(archive.extractfile(member).read()) != digest:
                    raise actual.CaptureRejected("reviewed operation source differs")
    except (tarfile.TarError, KeyError, OSError, AttributeError) as error:
        raise actual.CaptureRejected("reviewed operation source is unavailable") from error


def _load(archive, source_root):
    archive = Path(archive)
    source_root = Path(source_root).resolve()
    receipt = json.loads((archive / "receipt.json").read_bytes(),
                         object_pairs_hook=actual._unique_object)
    method = receipt["method"]
    if method not in _SOURCE_PINS or (method == "captureWheelActive" and
                                      receipt["candidate_commit"] != _WHEEL_COMMIT):
        raise actual.CaptureRejected("external binding source route differs")
    worker_logs = list(archive.glob("worker-class-load-*.log"))
    if len(worker_logs) != 1:
        raise actual.CaptureRejected("external binding worker log differs")
    capture_actual.verify_archive_inventory(archive, method, worker_logs[0])
    files = {key: (archive / name).read_bytes() for key, name in _FILES.items()}
    files["worker_class_load"] = worker_logs[0].read_bytes()
    _source_pins(files["source"], method)
    expected = (["joint-Wheel-active"] if method == "captureWheelActive"
                else list(_FIXTURE_IDS))
    prior_root, prior_jar = actual._ROOT, actual._STAGED_JAR
    try:
        actual._ROOT = source_root
        actual._STAGED_JAR = (source_root / "build/staging-repository/io/github/rubixhacker/"
                              "dyn4k-core-jvm/0.1.0-alpha.1/"
                              "dyn4k-core-jvm-0.1.0-alpha.1.jar")
        summary = actual.verify_capture_receipt(
            receipt, files, method, receipt["candidate_commit"], expected,
            receipt["runtime_executable"])
    finally:
        actual._ROOT, actual._STAGED_JAR = prior_root, prior_jar
    if summary["external_xml_witness"] != "PASSED_KERNEL_WORKER_WRITES":
        raise actual.CaptureRejected("external worker witness is unpassed")
    return receipt, files, method


def _fixture_call(marker):
    raw = [struct.unpack(">d", bytes.fromhex(value))[0] for value in marker["raw"]]
    return ({key: marker[key] for key in (
        "step", "body_id", "kind", "branch", "pre", "trig", "raw", "post")}
        | {"sequence": 0, "input_kind": "angle", "angle_bits": marker["angle_bits"],
           "clamp": [value < -1.0 or value > 1.0 for value in raw]})


def _records(files, method):
    if method == "captureWheelActive":
        trace, markers = actual.focused_wheel_stream(files["xml"])
        audit = actual._wheel_rotation_audit(markers)
        case = next(case for case in declared_cases()
                    if case["id"] == "joint-Wheel-active")
        rows = [json.loads(line) for line in trace.splitlines()]
        yield (case, rows[0], {row["step"]: row["state"] for row in rows
                              if row["kind"] == "state"}, trace, audit,
               source_rotation_cap(case))
        return
    outputs = ET.fromstring(files["xml"]).findall("system-out")
    if len(outputs) != 1 or outputs[0].text is None:
        raise actual.CaptureRejected("rotation fixture XML output differs")
    lines = outputs[0].text.splitlines()
    if len(lines) != 4 * len(_FIXTURE_IDS):
        raise actual.CaptureRejected("rotation fixture output count differs")
    for index, case_id in enumerate(_FIXTURE_IDS):
        group = lines[4 * index:4 * index + 4]
        marker = json.loads(group[1].removeprefix("PROSPECTIVE_ROTATION_JSON "),
                            object_pairs_hook=actual._unique_object)
        rows = [json.loads(group[position].removeprefix("NUMERICAL_JSON "),
                           object_pairs_hook=actual._unique_object)
                for position in (0, 2, 3)]
        trace = b"".join(group[position].split(" ", 1)[1].encode() + b"\n"
                         for position in (0, 2, 3))
        audit = {"schema": "portable-rotation-audit/2", "case_id": case_id,
                 "operation_model_revision": SOURCE_REVISION, "declared_calls": 1,
                 "accepted_toi_resets": [], "calls": [_fixture_call(marker)]}
        yield {"id": case_id, "steps": 1}, rows[0], {1: rows[1]["state"]}, \
            trace, audit, 1


def _schedule(method, case):
    if method == "captureWheelActive":
        if case["id"] != "joint-Wheel-active" or case["steps"] != 600:
            raise actual.CaptureRejected("reviewed Wheel schedule differs")
        return ([{"step": step, "body_id": body, "kind": "rotate",
                  "branch": branch, "input_kind": "angle"}
                 for step in range(1, 601) for body, branch in _WHEEL_STEP_CALLS],
                [[step, body] for step in range(1, 601) for body in ("b0", "b1")])
    if case.get("steps") != 1 or case.get("id") not in _FIXTURE_IDS:
        raise actual.CaptureRejected("reviewed fixture schedule differs")
    return ([{"step": 1, "body_id": "b0", "kind": "rotate",
              "branch": "fixture", "input_kind": "angle"}], [[1, "b0"]])


def _external_receipt(binding):
    return _canonical({**{key: binding[key] for key in _RECEIPT_FIELDS},
                       "exit_code": 0})


def _binding(receipt, files, method, case, trace, audit):
    expected_calls, body_steps = _schedule(method, case)
    binding = {
        "audit_schema": "portable-rotation-audit/2",
        "producer_process": "pid:" + receipt["worker_pid"],
        "producer_command": "portable." + ("RotationPremiseFixtureTest" if method ==
            "captureRotationPremises" else "ProspectiveArithmeticTest") + "." + method,
        "runtime_id": "jdk21:" + _sha(files["runtime"]),
        "artifact_sha256": _sha(files["artifact"]),
        "target_source_sha256": _sha(files["source"]),
        "operation_source_revision": SOURCE_REVISION,
        "trace_sha256": _sha(trace), "audit_sha256": _sha(_canonical(audit)),
        "expected_calls": expected_calls, "body_step_receipts": body_steps,
        "accepted_toi_resets": [], "accepted_toi_events": {},
        "reset_start_rotations": {}, "reset_end_rotations": {}, "pair_inputs": {},
        "allowed_evaluations": _MODES[:],
    }
    binding["payload_sha256"] = _sha(_canonical(audit))
    binding["manifest_sha256"] = _sha(_canonical({key: binding[key]
                                                   for key in _MANIFEST_FIELDS}))
    binding["receipt_sha256"] = _sha(_external_receipt(binding))
    return binding


def produce(archive, source_root):
    receipt, files, method = _load(archive, source_root)
    records = list(_records(files, method))
    if _sha(b"".join(row[3] for row in records)) != \
            receipt["summary"]["trace_sha256"]:
        raise actual.CaptureRejected("external binding trace differs from worker XML")
    bindings = {}
    for case, _, _, trace, audit, _ in records:
        bindings[case["id"]] = _binding(receipt, files, method, case, trace, audit)
    return {"schema": "portable-external-rotation-binding/1",
            "candidate_commit": receipt["candidate_commit"],
            "method": method, "bindings": bindings}


def replay(archive, source_root, bundle):
    receipt, files, method = _load(archive, source_root)
    if type(bundle) is not dict or bundle.get("schema") != \
            "portable-external-rotation-binding/1" or \
            bundle.get("candidate_commit") != receipt["candidate_commit"] or \
            bundle.get("method") != method or type(bundle.get("bindings")) is not dict:
        raise actual.CaptureRejected("external binding envelope differs")
    records = list(_records(files, method))
    if _sha(b"".join(row[3] for row in records)) != \
            receipt["summary"]["trace_sha256"]:
        raise actual.CaptureRejected("external binding trace differs from worker XML")
    if set(bundle["bindings"]) != {row[0]["id"] for row in records}:
        raise actual.CaptureRejected("external binding case inventory differs")
    results = {}
    for case, header, states, trace, audit, cap in records:
        binding = bundle["bindings"][case["id"]]
        expected = _binding(receipt, files, method, case, trace, audit)
        if binding != expected:
            raise actual.CaptureRejected("external source schedule or identity differs")
        result = verify_rotation_arithmetic(
            audit, case, header, states, cap, binding=binding, trace_bytes=trace,
            payload_bytes=_canonical(audit), receipt_bytes=_external_receipt(binding),
            artifact_bytes=files["artifact"], source_bytes=files["source"])
        results[case["id"]] = result
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.binding.exists():
        bundle = json.loads(arguments.binding.read_bytes(),
                            object_pairs_hook=actual._unique_object)
    else:
        bundle = produce(arguments.archive, arguments.source_root)
        arguments.binding.write_bytes(json.dumps(bundle, sort_keys=True, indent=2).encode()
                                      + b"\n")
    results = replay(arguments.archive, arguments.source_root, bundle)
    print(json.dumps({"cases": len(results),
                      "statuses": {key: value["status"] for key, value in results.items()},
                      "qualification": "UNPASSED"}, sort_keys=True))
