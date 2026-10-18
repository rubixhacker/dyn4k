import hashlib
import json
import re
from pathlib import Path
from xml.parsers import expat

from cases import declared_cases
from rotation_oracle import verify_operation_marker


class CaptureRejected(ValueError):
    pass


_WRAPPERS = {
    "captureGeometry": "geometryCollisionBoundaryAndScale",
    "captureFreeMotion": "freeMotionForcesDampingAndRestitution",
    "captureDefaultContacts": "defaultContactsFrictionSleepAndWake",
    "captureConfigured30Repeat1": "configured30Repeat1",
    "captureConfigured30Repeat2": "configured30Repeat2",
    "captureConfigured60Repeat1": "configured60Repeat1",
    "captureConfigured60Repeat2": "configured60Repeat2",
    "captureConfigured120Repeat1": "configured120Repeat1",
    "captureConfigured120Repeat2": "configured120Repeat2",
    "captureJoints": "everyJointWithInitialAndApplicableActiveModes",
    "captureJointBooleanModes": "independentJointBooleanModes",
    "captureJointNumericModes": "independentJointNumericAndLimitModes",
    "captureAngleFailure": "baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure",
    "captureCcd": "continuousCollisionCasesAtFrozenRates",
    "captureLongMotion": "longRunningFreeMotionInvariantScene",
}


def expected_case_ids():
    result = {method: [] for method in _WRAPPERS}
    for case in declared_cases():
        case_id = case["id"]
        family = case["family"]
        source = case["input"]
        if family == "geometry-collision":
            method = "captureGeometry"
        elif family == "free-motion":
            method = "captureFreeMotion"
        elif case_id.startswith("contacts-default-"):
            method = "captureDefaultContacts"
        elif case_id.startswith("contacts-configured-"):
            outer_hz = source["outerHz"]
            repetition = source["repetition"]
            method = f"captureConfigured{outer_hz}Repeat{repetition}"
        elif family == "ccd":
            method = "captureCcd"
        elif case["profile"] == "frozen-weld-pulley" or "mode" in source:
            method = "captureJoints"
        elif "variant" in source and "field" in source:
            method = "captureJointBooleanModes"
        elif "field" in source or "limits" in source:
            method = "captureJointNumericModes"
        elif case["profile"] == "baseline-failed":
            method = "captureAngleFailure"
        elif case_id == "long-free-60":
            method = "captureLongMotion"
        else:
            raise CaptureRejected(f"unmapped case: {case_id}")
        result[method].append(case_id)
    inventory = [case_id for ids in result.values() for case_id in ids]
    if len(inventory) != 332 or len(set(inventory)) != 332:
        raise CaptureRejected("prospective wrapper inventory differs")
    return result


def verify_capture(xml, method, expected_ids=None):
    if method not in _WRAPPERS:
        raise CaptureRejected("unknown producer method")
    if expected_ids is None:
        expected_ids = expected_case_ids()[method]
    if not isinstance(expected_ids, list) or len(set(expected_ids)) != len(expected_ids):
        raise CaptureRejected("expected case inventory differs")
    expected_method = _WRAPPERS[method]
    trace_hash = hashlib.sha256()
    operation_hash = hashlib.sha256()
    parser = expat.ParserCreate()
    suite = None
    testcases = []
    inside_output = False
    line_buffer = ""
    active = None
    ids = []
    state_count = 0
    total_steps = 0
    operations = 0
    body_bound_operations = 0
    pair_inputs_unbound = 0
    sequence = 0
    last_main = {}

    def record(line):
        nonlocal active, state_count, total_steps, operations
        nonlocal pair_inputs_unbound, sequence, body_bound_operations
        if not line:
            return
        if line.startswith("NUMERICAL_JSON "):
            raw = line.removeprefix("NUMERICAL_JSON ")
            trace_hash.update((raw + "\n").encode())
            try:
                row = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
                    CaptureRejected(f"nonfinite trace token: {value}")))
            except (TypeError, ValueError) as error:
                raise CaptureRejected("invalid numerical trace row") from error
            if type(row) is not dict or type(row.get("id")) is not str:
                raise CaptureRejected("trace row identity differs")
            if row.get("kind") == "inputs":
                if active is not None or len(ids) >= len(expected_ids) or \
                        row["id"] != expected_ids[len(ids)] or \
                        type(row.get("steps")) is not int or row["steps"] < 1 or \
                        type(row.get("startStep", 0)) is not int:
                    raise CaptureRejected("case header or order differs")
                active = row
                state_count = 0
                last_main.clear()
                ids.append(row["id"])
            elif active is None or row["id"] != active["id"]:
                raise CaptureRejected("trace row outside declared case")
            elif row.get("kind") == "state":
                state_count += 1
                if type(row.get("step")) is not int or \
                        row["step"] != active.get("startStep", 0) + state_count:
                    raise CaptureRejected("state step order differs")
            elif row.get("kind") == "case-end":
                if type(row.get("steps")) is not int or \
                        row["steps"] != active["steps"] or \
                        state_count != active["steps"]:
                    raise CaptureRejected("case step coverage differs")
                total_steps += state_count
                active = None
            return
        if not line.startswith("PROSPECTIVE_ROTATION_JSON "):
            raise CaptureRejected("unexpected producer output")
        raw = line.removeprefix("PROSPECTIVE_ROTATION_JSON ")
        operation_hash.update((raw + "\n").encode())
        try:
            marker = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
                CaptureRejected(f"nonfinite operation token: {value}")))
        except (TypeError, ValueError) as error:
            raise CaptureRejected("invalid operation JSON") from error
        if active is None or marker.get("method") != expected_method or \
                marker.get("sequence") != sequence:
            raise CaptureRejected("operation case, method, or sequence differs")
        if marker.get("case_id") is not None:
            if marker["case_id"] != active["id"] or \
                    type(marker.get("step")) is not int or \
                    not active.get("startStep", 0) + 1 <= marker["step"] <= \
                    active.get("startStep", 0) + active["steps"]:
                raise CaptureRejected("operation case or step binding differs")
            if marker.get("body_id") is not None:
                bodies = active.get("setup", {}).get("bodies", [])
                if type(bodies) is not list or marker["body_id"] not in [
                        body.get("id") for body in bodies if type(body) is dict]:
                    raise CaptureRejected("operation body binding differs")
                body_bound_operations += 1
        outcome = verify_operation_marker(marker)
        if outcome["status"] == "UNPASSED_INPUT_ORIGIN":
            pair_inputs_unbound += 1
        elif outcome["status"] != "PASSED_ARITHMETIC":
            raise CaptureRejected(f"operation arithmetic differs: {outcome}")
        if marker["source"] != "vector-lerp":
            token = marker["target_token"]
            if token in last_main and marker["pre"] != last_main[token]:
                raise CaptureRejected("same-target operation chain differs")
            last_main[token] = marker["post"]
        sequence += 1
        operations += 1

    def start(name, attrs):
        nonlocal suite, inside_output
        if name == "testsuite":
            if suite is not None:
                raise CaptureRejected("multiple target suites")
            suite = attrs
        elif name == "testcase":
            testcases.append(attrs)
        elif name == "system-out":
            if inside_output:
                raise CaptureRejected("multiple system outputs")
            inside_output = True

    def end(name):
        nonlocal inside_output
        if name == "system-out":
            if line_buffer.strip():
                raise CaptureRejected("unterminated target output")
            inside_output = False

    def characters(chunk):
        nonlocal line_buffer
        if inside_output:
            line_buffer += chunk
            while "\n" in line_buffer:
                line, line_buffer = line_buffer.split("\n", 1)
                record(line)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = characters
    try:
        if isinstance(xml, (str, Path)):
            with Path(xml).open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    parser.Parse(chunk, False)
                parser.Parse(b"", True)
        elif type(xml) is bytes:
            parser.Parse(xml, True)
        else:
            raise CaptureRejected("invalid XML source")
    except expat.ExpatError as error:
        raise CaptureRejected("invalid target XML") from error
    if suite is None or any(suite.get(key) != value for key, value in
                            (("tests", "1"), ("skipped", "0"),
                             ("failures", "0"), ("errors", "0"))) or \
            len(testcases) != 1 or \
            testcases[0].get("classname") != "portable.ProspectiveArithmeticTest" or \
            testcases[0].get("name") not in (method, f"{method}[jvm]") or \
            active is not None or ids != expected_ids:
        raise CaptureRejected("target method or case inventory differs")
    return {"status": "UNPASSED_TARGET_BINDING", "qualification": "UNPASSED",
            "method": method, "cases": len(ids), "steps": total_steps,
            "operations_verified": operations,
            "body_bound_operations": body_bound_operations,
            "pair_inputs_unbound": pair_inputs_unbound,
            "trace_sha256": trace_hash.hexdigest(),
            "operations_sha256": operation_hash.hexdigest()}


_RECEIPT_FILES = {"xml", "stage_log", "gradle_log", "execve_log", "artifact", "runtime",
                  "source"}


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _check_process(files, runtime_executable):
    if type(runtime_executable) is not str or not runtime_executable.startswith("/"):
        raise CaptureRejected("runtime executable identity differs")
    try:
        log = files["gradle_log"].decode()
        executions = files["execve_log"].decode()
        stage = files["stage_log"].decode()
    except UnicodeError as error:
        raise CaptureRejected("process log encoding differs") from error
    process_lines = [line for line in log.splitlines()
                     if "Starting process 'Gradle Test Executor" in line]
    if len(process_lines) != 1 or \
            f"Command: {runtime_executable} " not in process_lines[0] or \
            "GradleWorkerMain" not in process_lines[0] or \
            "BUILD SUCCESSFUL" not in log or "BUILD SUCCESSFUL" not in stage:
        raise CaptureRejected("Gradle target process evidence differs")
    pattern = re.compile(r'\bexecve\("' + re.escape(runtime_executable) +
                         r'",.*GradleWorkerMain.*\)\s+=\s+0$')
    if sum(bool(pattern.search(line)) for line in executions.splitlines()) != 1:
        raise CaptureRejected("executed JVM worker identity differs")


def make_capture_receipt(files, method, commit, expected_ids, runtime_executable):
    if type(files) is not dict or set(files) != _RECEIPT_FILES or \
            any(type(value) is not bytes or not value for value in files.values()) or \
            type(commit) is not str or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise CaptureRejected("receipt input identity differs")
    _check_process(files, runtime_executable)
    summary = verify_capture(files["xml"], method, expected_ids)
    return {"schema": "portable-arithmetic-capture-receipt/1",
            "candidate_commit": commit, "method": method, "exit_code": 0,
            "runtime_executable": runtime_executable,
            "source_archive_sha256": _sha(files["source"]),
            "artifact_sha256": _sha(files["artifact"]),
            "runtime_sha256": _sha(files["runtime"]),
            "xml_sha256": _sha(files["xml"]),
            "stage_log_sha256": _sha(files["stage_log"]),
            "gradle_log_sha256": _sha(files["gradle_log"]),
            "execve_log_sha256": _sha(files["execve_log"]),
            "summary": summary}


def verify_capture_receipt(receipt, files, method, commit, expected_ids,
                           runtime_executable):
    if type(receipt) is not dict or type(receipt.get("exit_code")) is not int or \
            receipt["exit_code"] != 0:
        raise CaptureRejected("target receipt or process exit differs")
    expected = make_capture_receipt(files, method, commit, expected_ids,
                                    runtime_executable)
    if receipt != expected:
        raise CaptureRejected("target receipt identity or captured bytes differ")
    return expected["summary"]
