import ast
from collections import Counter
import hashlib
import io
import json
import os
import re
import struct
import subprocess
import tarfile
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.parsers import expat

from cases import declared_cases
from rotation_oracle import REVOLUTE_LIMITS_FALSE_CONTEXT, verify_operation_marker
from orthogonality import source_rotation_cap, validate_rotation_audit
from prospective_compare import compare_policy_case, load_policy_catalog
from boolean_rotation_jdi import (jdi_bridge, source_guard as jdi_source_guard,
                                  witness as jdi_witness)


class CaptureRejected(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CaptureRejected("duplicate target JSON field")
        result[key] = value
    return result


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
    "captureWheelActive": "everyJointWithInitialAndApplicableActiveModes",
    "captureRotationPremises": "captureRotationPremises",
    "captureRevoluteLimitsFalse": "independentJointBooleanModes",
    "captureJointBooleanModes": "independentJointBooleanModes",
    "captureJointNumericModes": "independentJointNumericAndLimitModes",
    "captureAngleFailure": "baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure",
    "captureCcd": "continuousCollisionCasesAtFrozenRates",
    "captureLongMotion": "longRunningFreeMotionInvariantScene",
}

_FOCUSED_WHEEL_STEP_CALLS = (("b1", "integrate"), ("b0", "joint"),
                             ("b1", "joint"))
_ROTATION_PREMISES = (
    ("rotation-premise-mode", "bfd0cd683f9d3fea", "3feee0a3e97da062",
     "4001c867da8b78fc"),
    ("rotation-premise-zero", "3ff0000000000000", "0000000000000000",
     "0000000000000000"),
    ("rotation-premise-negative-zero", "3ff0000000000000", "8000000000000000",
     "8000000000000000"),
    ("rotation-premise-tiny-angle", "3ff0000000000000", "0000000000000000",
     "0000000000000001"),
    ("rotation-premise-subnormal-product", "0000000000000001",
     "0000000000000000", "0000000000000000"),
)
_FOCUSED_BOOLEAN_CASE = "joint-Revolute-LimitsEnabled-false"
_FOCUSED_BOOLEAN_METHOD = "captureRevoluteLimitsFalse"
_FOCUSED_BOOLEAN_CLASS = "portable.RevoluteLimitsFalseCaptureTest"
_FOCUSED_BOOLEAN_STEP_CALLS = (("b1", "integrate"), ("b0", None), ("b1", None))
_FOCUSED_BOOLEAN_INPUT_SHA256 = "8966b3e0f34f2a6d442cb3b8348f4ea262186b9cd80daa5b8a7c58dbf8d8da17"
_FOCUSED_BOOLEAN_REFERENCE_SHA256 = "80c4e6c5133953eb7dd480e34b2d51a244b9c02d1d9f1d367d7b6cbf8eed2f36"
_FOCUSED_BOOLEAN_SOURCE_SHA256 = "d7a8467eb390a4c0db1544472fdb092420933470c879880f23ac64c2e43ff881"
_WITNESS_PREFIXES = (b"NUMERICAL_JSON ", b"PROSPECTIVE_ROTATION_JSON ",
                     b"PROSPECTIVE_BINDING_JSON ")
_WITNESS_WRITE = re.compile(r'^write\((\d+), ("(?:\\.|[^"\\])*"), (\d+)\)\s+= (\d+)$')


def _require_focused_wheel_step_calls(markers, step):
    expected = [(step, (step - 1) * 3 + index, body_id, branch, "rotate")
                for index, (body_id, branch) in enumerate(_FOCUSED_WHEEL_STEP_CALLS)]
    observed = [(marker.get("step"), marker.get("sequence"), marker.get("body_id"),
                 marker.get("branch"), marker.get("kind")) for marker in markers]
    if observed != expected:
        raise CaptureRejected("focused Wheel source call schedule differs")


def _require_focused_boolean_step_calls(markers, step):
    expected = [(step, (step - 1) * 3 + index, body_id, branch, "rotate")
                for index, (body_id, branch) in enumerate(_FOCUSED_BOOLEAN_STEP_CALLS)]
    observed = [(marker.get("step"), marker.get("sequence"), marker.get("body_id"),
                 marker.get("branch"), marker.get("kind")) for marker in markers]
    if observed != expected:
        raise CaptureRejected("focused Boolean source call schedule differs")


def expected_case_ids(include_focused=False):
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
    inventory = [case_id for method, ids in result.items()
                 if method not in ("captureWheelActive", "captureRotationPremises",
                                  _FOCUSED_BOOLEAN_METHOD)
                 for case_id in ids]
    if len(inventory) != 332 or len(set(inventory)) != 332:
        raise CaptureRejected("prospective wrapper inventory differs")
    if include_focused:
        result["captureWheelActive"] = ["joint-Wheel-active"]
        result["captureRotationPremises"] = [row[0] for row in _ROTATION_PREMISES]
    else:
        del result["captureWheelActive"]
        del result["captureRotationPremises"]
    del result[_FOCUSED_BOOLEAN_METHOD]
    return result


def verify_rotation_premise_capture(xml, expected_ids):
    if expected_ids != [row[0] for row in _ROTATION_PREMISES]:
        raise CaptureRejected("rotation premise case inventory differs")
    try:
        document = ET.fromstring(xml)
        cases = document.findall("testcase")
        outputs = document.findall("system-out")
        if document.tag != "testsuite" or len(cases) != 1 or \
                cases[0].get("classname") != "portable.RotationPremiseFixtureTest" or \
                not cases[0].get("name", "").startswith("captureRotationPremises") or \
                len(outputs) != 1 or outputs[0].text is None or \
                cases[0].find("failure") is not None or \
                cases[0].find("skipped") is not None:
            raise CaptureRejected("rotation premise target test differs")
        lines = outputs[0].text.splitlines()
        if len(lines) != 4 * len(_ROTATION_PREMISES):
            raise CaptureRejected("rotation premise output count differs")
        trace = []
        arithmetic = []
        for index, (case_id, cost, sint, angle) in enumerate(_ROTATION_PREMISES):
            group = lines[index * 4:index * 4 + 4]
            if [line.split(" ", 1)[0] for line in group] != [
                    "NUMERICAL_JSON", "PROSPECTIVE_ROTATION_JSON",
                    "NUMERICAL_JSON", "NUMERICAL_JSON"]:
                raise CaptureRejected("rotation premise record order differs")
            inputs, marker, state, ending = [json.loads(
                line.split(" ", 1)[1], object_pairs_hook=_unique_object,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    CaptureRejected(f"nonfinite rotation premise token: {value}")))
                for line in group]
            if inputs.get("kind") != "inputs" or inputs.get("id") != case_id or \
                    inputs.get("steps") != 1 or \
                    inputs.get("setup") != {"bodies": [{"id": "b0"}]} or \
                    state.get("kind") != "state" or state.get("id") != case_id or \
                    state.get("step") != 1 or ending != {
                        "kind": "case-end", "id": case_id, "steps": 1}:
                raise CaptureRejected("rotation premise trace identity differs")
            initial = inputs.get("initial", {}).get("bodies", [])
            observed = state.get("state", {}).get("bodies", [])
            if len(initial) != 1 or len(observed) != 1 or \
                    initial[0].get("id") != "b0" or observed[0].get("id") != "b0" or \
                    any(struct.pack(">d", initial[0]["transform"][key]).hex() != value
                        for key, value in (("getCost", cost), ("getSint", sint))) or \
                    marker.get("case_id") != case_id or marker.get("method") != \
                    "captureRotationPremises" or marker.get("sequence") != 0 or \
                    marker.get("target_token") != 0 or marker.get("step") != 1 or \
                    marker.get("body_id") != "b0" or marker.get("branch") != "fixture" or \
                    marker.get("source") != "origin" or marker.get("kind") != "rotate" or \
                    marker.get("angle_bits") != angle or marker.get("pre") != [cost, sint] or \
                    any(struct.pack(">d", observed[0]["transform"][key]).hex() != value
                        for key, value in zip(("getCost", "getSint"), marker["post"])):
                raise CaptureRejected("rotation premise source binding differs")
            status = verify_operation_marker(marker,
                ("strict", "fma_left", "fma_right", "fused"))["status"]
            if status != "PASSED_ARITHMETIC":
                raise CaptureRejected("rotation premise arithmetic differs")
            arithmetic.append(status)
            trace.extend(line.split(" ", 1)[1] + "\n" for line in
                         (group[0], group[2], group[3]))
        return {"status": "VERIFIED_FIXTURE_EXECUTION", "qualification": "UNPASSED",
                "cases": len(_ROTATION_PREMISES), "steps": len(_ROTATION_PREMISES),
                "operations_verified": sum(status == "PASSED_ARITHMETIC"
                                           for status in arithmetic),
                "operation_statuses": dict(zip(expected_ids, arithmetic)),
                "selected_resets": 0, "trace_sha256": _sha("".join(trace).encode())}
    except (ET.ParseError, UnicodeError, TypeError, KeyError, IndexError,
            OverflowError, struct.error, ValueError) as error:
        if isinstance(error, CaptureRejected):
            raise
        raise CaptureRejected("rotation premise output is malformed") from error


def verify_capture(xml, method, expected_ids=None, reset_order="either"):
    if method not in _WRAPPERS:
        raise CaptureRejected("unknown producer method")
    if reset_order not in {"pre", "post", "either"}:
        raise CaptureRejected("unknown accepted reset order")
    if expected_ids is None:
        expected_ids = ([_FOCUSED_BOOLEAN_CASE] if method == _FOCUSED_BOOLEAN_METHOD
                        else expected_case_ids(method in (
                            "captureWheelActive", "captureRotationPremises"))[method])
    if not isinstance(expected_ids, list) or len(set(expected_ids)) != len(expected_ids):
        raise CaptureRejected("expected case inventory differs")
    if method == "captureRotationPremises":
        return verify_rotation_premise_capture(xml, expected_ids)
    expected_method = _WRAPPERS[method]
    trace_hash = hashlib.sha256()
    operation_hash = hashlib.sha256()
    binding_hash = hashlib.sha256()
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
    target_bodies = {}
    step_operations = []
    step_receipted = False
    last_receipt_step = 0
    prior_pairs = []
    state_pairs = []
    toi_events = []
    used_toi_events = set()
    pending_resets = []
    unclaimed_resets = []
    body_step_receipts = 0
    temporary_operations = 0
    selected_resets = 0
    trace_order = {}

    def pair_from_trace(body):
        transform = body["transform"]
        return [struct.pack(">d", transform[key]).hex()
                for key in ("getCost", "getSint")]

    def body_ids():
        bodies = active.get("setup", {}).get("bodies", [])
        if type(bodies) is not list or not bodies or \
                [body.get("id") for body in bodies] != [
                    f"b{index}" for index in range(len(bodies))]:
            raise CaptureRejected("body inventory differs")
        return [body["id"] for body in bodies]

    def record(line):
        nonlocal active, state_count, total_steps, operations
        nonlocal pair_inputs_unbound, sequence, body_bound_operations
        nonlocal step_receipted, last_receipt_step, prior_pairs, state_pairs, body_step_receipts
        nonlocal temporary_operations, selected_resets
        if not line:
            return
        if line.startswith("NUMERICAL_JSON "):
            if unclaimed_resets:
                raise CaptureRejected("reset lacks adjacent source selection")
            raw = line.removeprefix("NUMERICAL_JSON ")
            trace_hash.update((raw + "\n").encode())
            try:
                row = json.loads(raw, object_pairs_hook=_unique_object,
                                 parse_constant=lambda value: (_ for _ in ()).throw(
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
                if method == _FOCUSED_BOOLEAN_METHOD and (
                        row["steps"] != 600 or
                        _sha((raw + "\n").encode()) != _FOCUSED_BOOLEAN_INPUT_SHA256):
                    raise CaptureRejected("focused Boolean input header differs")
                active = row
                state_count = 0
                last_main.clear()
                target_bodies.clear()
                trace_order.clear()
                step_operations.clear()
                toi_events.clear()
                used_toi_events.clear()
                pending_resets.clear()
                unclaimed_resets.clear()
                step_receipted = False
                last_receipt_step = 0
                body_ids()
                prior_pairs = [pair_from_trace(body) for body in
                               row["initial"]["bodies"]]
                ids.append(row["id"])
            elif active is None or row["id"] != active["id"]:
                raise CaptureRejected("trace row outside declared case")
            elif row.get("kind") not in {"event", "action", "instrumented-callback",
                                         "state", "endpoint", "case-end"}:
                raise CaptureRejected("unexpected candidate trace kind")
            elif row.get("kind") != "case-end":
                expected_step = active.get("startStep", 0) + state_count + \
                    (0 if row["kind"] == "endpoint" else 1)
                if type(row.get("step")) is not int or row["step"] != expected_step or \
                        type(row.get("order")) is not int or \
                        row["order"] != trace_order.get(expected_step, -1) + 1:
                    raise CaptureRejected("candidate trace step or order differs")
                trace_order[expected_step] = row["order"]
            if row.get("kind") == "state":
                if state_count and last_receipt_step != state_count:
                    raise CaptureRejected("missing prior body-step receipt")
                state_count += 1
                if type(row.get("step")) is not int or \
                        row["step"] != active.get("startStep", 0) + state_count:
                    raise CaptureRejected("state step order differs")
                state_pairs = [pair_from_trace(body) for body in row["state"]["bodies"]]
                if len(state_pairs) != len(body_ids()):
                    raise CaptureRejected("state body inventory differs")
                step_receipted = False
            elif row.get("kind") == "event" and row.get("name") == "toi.payload.bodies":
                toi_events.append(row)
            elif row.get("kind") == "case-end":
                if type(row.get("steps")) is not int or \
                        row["steps"] != active["steps"] or \
                        state_count != active["steps"] or \
                        last_receipt_step != state_count or \
                        pending_resets or unclaimed_resets:
                    raise CaptureRejected("case step coverage differs")
                total_steps += state_count
                active = None
            return
        if line.startswith("PROSPECTIVE_BINDING_JSON "):
            raw = line.removeprefix("PROSPECTIVE_BINDING_JSON ")
            binding_hash.update((raw + "\n").encode())
            try:
                binding = json.loads(raw, object_pairs_hook=_unique_object,
                                     parse_constant=lambda value: (_ for _ in ()).throw(
                    CaptureRejected(f"nonfinite binding token: {value}")))
            except (TypeError, ValueError) as error:
                raise CaptureRejected("invalid binding JSON") from error
            if active is None or type(binding) is not dict or \
                    binding.get("case_id") != active["id"]:
                raise CaptureRejected("binding case differs")
            if binding.get("kind") == "toi-accepted":
                if set(binding) != {"kind", "case_id", "step", "body_ids",
                                    "reset_body_ids", "time_bits"} or \
                        binding["step"] != active.get("startStep", 0) + state_count + 1 or \
                pending_resets or type(binding["time_bits"]) is not str:
                    raise CaptureRejected("accepted TOI selection differs")
                names = body_ids()
                pair = binding["body_ids"]
                resets = binding["reset_body_ids"]
                if type(pair) is not list or len(pair) != 2 or \
                        any(name not in names for name in pair) or \
                        resets not in ([pair[0]], pair):
                    raise CaptureRejected("accepted TOI body pair differs")
                matching = [index for index, event in enumerate(toi_events)
                            if index not in used_toi_events and
                            event.get("step") == binding["step"] and
                            event.get("payload", {}).get("bodies") ==
                            [names.index(name) for name in pair] and
                            type(event.get("payload", {}).get("time")) is float and
                            struct.pack(">d", event["payload"]["time"]).hex() ==
                            binding["time_bits"]]
                if not matching:
                    raise CaptureRejected("accepted TOI callback differs")
                used_toi_events.add(matching[-1])
                expected = [(name, binding["time_bits"]) for name in resets]
                if unclaimed_resets:
                    if reset_order == "pre":
                        raise CaptureRejected("accepted TOI source order differs")
                    observed = [(call["body_id"], call["alpha_bits"])
                                for call in unclaimed_resets]
                    if observed != expected:
                        raise CaptureRejected("accepted TOI reset call differs")
                    unclaimed_resets.clear()
                else:
                    if reset_order == "post":
                        raise CaptureRejected("accepted TOI source order differs")
                    pending_resets.extend(expected)
                selected_resets += len(resets)
            elif binding.get("kind") == "body-step":
                if set(binding) != {"kind", "case_id", "step", "bodies",
                                    "temporary_calls"} or step_receipted or \
                        binding["step"] != active.get("startStep", 0) + state_count or \
                        state_count < 1 or pending_resets or unclaimed_resets:
                    raise CaptureRejected("body-step receipt order differs")
                receipts = binding["bodies"]
                names = body_ids()
                if type(receipts) is not list or len(receipts) != len(names):
                    raise CaptureRejected("body-step inventory differs")
                if method == "captureWheelActive":
                    _require_focused_wheel_step_calls(step_operations, binding["step"])
                elif method == _FOCUSED_BOOLEAN_METHOD:
                    _require_focused_boolean_step_calls(step_operations, binding["step"])
                for index, receipt in enumerate(receipts):
                    calls = [call for call in step_operations
                             if call["body_id"] == names[index]]
                    if type(receipt) is not dict or set(receipt) != \
                            {"body_id", "calls", "pre", "post"} or \
                            receipt["body_id"] != names[index] or \
                            type(receipt["calls"]) is not int or \
                            receipt["calls"] != len(calls) or \
                            receipt["pre"] != prior_pairs[index] or \
                            receipt["post"] != state_pairs[index] or \
                            (calls and (calls[0]["pre"] != receipt["pre"] or
                                        calls[-1]["post"] != receipt["post"])) or \
                            (not calls and receipt["pre"] != receipt["post"]):
                        raise CaptureRejected("body-step operation chain differs")
                temporary = [call for call in step_operations
                             if call["body_id"] is None]
                if type(binding["temporary_calls"]) is not int or \
                        binding["temporary_calls"] != len(temporary):
                    raise CaptureRejected("temporary operation count differs")
                temporary_operations += len(temporary)
                body_step_receipts += len(receipts)
                step_operations.clear()
                prior_pairs = state_pairs
                step_receipted = True
                last_receipt_step = state_count
            else:
                raise CaptureRejected("unknown binding kind")
            return
        if not line.startswith("PROSPECTIVE_ROTATION_JSON "):
            raise CaptureRejected("unexpected producer output")
        raw = line.removeprefix("PROSPECTIVE_ROTATION_JSON ")
        operation_hash.update((raw + "\n").encode())
        try:
            marker = json.loads(raw, object_pairs_hook=_unique_object,
                                parse_constant=lambda value: (_ for _ in ()).throw(
                CaptureRejected(f"nonfinite operation token: {value}")))
        except (TypeError, ValueError) as error:
            raise CaptureRejected("invalid operation JSON") from error
        if active is None or marker.get("method") != expected_method or \
                marker.get("sequence") != sequence:
            raise CaptureRejected("operation case, method, or sequence differs")
        if marker.get("case_id") != active["id"] or \
                marker.get("step") != active.get("startStep", 0) + state_count + 1 or \
                marker.get("body_id") not in (None, *body_ids()):
            raise CaptureRejected("operation case, step, or body binding differs")
        if step_receipted:
            step_receipted = False
        if method in ("captureWheelActive", _FOCUSED_BOOLEAN_METHOD) and \
                marker["body_id"] is not None and \
                marker.get("branch") not in ("integrate", "joint", "contact"):
            if not (method == _FOCUSED_BOOLEAN_METHOD and
                    marker.get("branch") is None):
                raise CaptureRejected("focused source branch is unbound")
        if marker["body_id"] is not None:
            body_bound_operations += 1
            token = marker["target_token"]
            if token in target_bodies and target_bodies[token] != marker["body_id"]:
                raise CaptureRejected("target changed body identity")
            if any(body == marker["body_id"] and target != token
                   for target, body in target_bodies.items()):
                raise CaptureRejected("body changed target identity")
            target_bodies[token] = marker["body_id"]
        elif marker["target_token"] in target_bodies:
            raise CaptureRejected("body target reported as temporary")
        if pending_resets:
            expected_body, expected_time = pending_resets.pop(0)
            if marker["kind"] != "lerp-reset" or \
                    marker["body_id"] != expected_body or \
                    marker["alpha_bits"] != expected_time:
                raise CaptureRejected("accepted TOI reset call differs")
        elif marker["kind"] == "lerp-reset":
            unclaimed_resets.append(marker)
        elif unclaimed_resets:
            raise CaptureRejected("reset lacks adjacent source selection")
        outcome = verify_operation_marker(
            marker, source_context=REVOLUTE_LIMITS_FALSE_CONTEXT
            if method == _FOCUSED_BOOLEAN_METHOD else None)
        if outcome["status"] == "UNPASSED_INPUT_ORIGIN":
            pair_inputs_unbound += 1
        elif outcome["status"] != "PASSED_ARITHMETIC":
            raise CaptureRejected(f"operation arithmetic differs: {outcome}")
        if marker["body_id"] is not None:
            token = marker["target_token"]
            if token in last_main and marker["pre"] != last_main[token]:
                raise CaptureRejected("same-target operation chain differs")
            last_main[token] = marker["post"]
        step_operations.append(marker)
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
    except (KeyError, IndexError, TypeError, OverflowError, struct.error) as error:
        raise CaptureRejected("malformed target trace or marker") from error
    if suite is None or any(suite.get(key) != value for key, value in
                            (("tests", "1"), ("skipped", "0"),
                             ("failures", "0"), ("errors", "0"))) or \
            len(testcases) != 1 or \
            testcases[0].get("classname") != (_FOCUSED_BOOLEAN_CLASS if
                method == _FOCUSED_BOOLEAN_METHOD else
                "portable.ProspectiveArithmeticTest") or \
            testcases[0].get("name") not in (method, f"{method}[jvm]") or \
            active is not None or ids != expected_ids:
        raise CaptureRejected("target method or case inventory differs")
    if body_step_receipts == 0:
        raise CaptureRejected("empty body-step inventory")
    if method == _FOCUSED_BOOLEAN_METHOD and (
            len(ids) != 1 or total_steps != 600 or operations != 1800 or
            body_bound_operations != 1800 or body_step_receipts != 1200 or
            temporary_operations or selected_resets):
        raise CaptureRejected("focused Boolean operation coverage differs")
    status = ("UNPASSED_SOURCE_CALL_SITE" if method == _FOCUSED_BOOLEAN_METHOD
              else "UNPASSED_INPUT_ORIGIN" if pair_inputs_unbound else
              "VERIFIED_ARITHMETIC_BINDING")
    return {"status": status, "qualification": "UNPASSED",
            "method": method, "cases": len(ids), "steps": total_steps,
            "operations_verified": operations,
            "body_bound_operations": body_bound_operations,
            "body_step_receipts": body_step_receipts,
            "temporary_operations": temporary_operations,
            "selected_resets": selected_resets,
            "pair_inputs_unbound": pair_inputs_unbound,
            "trace_sha256": trace_hash.hexdigest(),
            "operations_sha256": operation_hash.hexdigest(),
            "binding_sha256": binding_hash.hexdigest()}


_RECEIPT_FILES = {"xml", "stage_log", "gradle_log", "execve_log", "artifact", "runtime",
                  "source", "worker_classpath", "worker_class_load", "portable_classes"}
_ROOT = Path(__file__).resolve().parents[3]
_STAGED_JAR = (_ROOT / "build/staging-repository/io/github/rubixhacker/"
               "dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar")
_PINNED_JAVA = "/tmp/dyn4k-tools/jdk21/bin/java"
_AUDITED_ENGINE_CLASSES = {
    "org/dyn4j/geometry/Transform.class",
    "org/dyn4j/geometry/RotationOperationTap.class",
    "org/dyn4j/geometry/RotationCaptureSlot.class",
    "org/dyn4j/world/AbstractPhysicsWorld.class",
    "org/dyn4j/world/ToiAcceptedResetTap.class",
}
_TOI_RESET_CLASS = "org/dyn4j/world/ToiAcceptedResetTap.class"
_PORTABLE_CLASS_MEMBER = re.compile(r"(?:^|/)portable/(?:[^/]+/)*[^/]+\.class$")
_WHEEL_RECORDER_CLASSES = frozenset({
    "portable/NumericalRecorder$capture$collisions$1.class",
    "portable/NumericalRecorder$capture$contacts$1.class",
    "portable/NumericalRecorder$capture$steps$1.class",
    "portable/NumericalRecorder$capture$timeOfImpact$1.class",
    "portable/NumericalRecorder$json$$inlined$sortedBy$1.class",
})
_FIXTURE_CLASSES = frozenset({
    "portable/RotationPremiseFixtureTest.class",
    "portable/RotationPremiseFixtureTest$SeededTransform.class",
    "portable/RotationPremiseFixtureTest$PremiseInput.class",
})
_FIXTURE_CLASS_MEMBER = re.compile(
    r"(?:^|/)portable/RotationPremiseFixtureTest(?:\$[^/]*)?\.class$")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _source_archive(commit):
    if type(commit) is not str or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise CaptureRejected("candidate commit identity differs")
    environment = os.environ.copy()
    environment.pop("OLLAMA_API_KEY", None)
    result = subprocess.run(("git", "-c", "core.autocrlf=false",
                             "--no-replace-objects", "archive", "--format=tar",
                             commit),
                            cwd=_ROOT, env=environment, capture_output=True, check=False)
    if result.returncode:
        raise CaptureRejected("candidate commit archive unavailable")
    return result.stdout


def _verify_boolean_source(source):
    name = ("tools/numerical/portable/src/jvmTest/kotlin/portable/"
            "RevoluteLimitsFalseCaptureTest.kt")
    try:
        with tarfile.open(fileobj=io.BytesIO(source), mode="r:") as archive:
            entries = [entry for entry in archive if entry.name == name]
            if len(entries) != 1 or not entries[0].isfile():
                raise CaptureRejected("focused Boolean source inventory differs")
            member = archive.extractfile(entries[0])
            if member is None or _sha(member.read()) != _FOCUSED_BOOLEAN_SOURCE_SHA256:
                raise CaptureRejected("focused Boolean source schedule differs")
    except (OSError, tarfile.TarError) as error:
        raise CaptureRejected("focused Boolean source archive is malformed") from error


def _portable_classes_archive():
    archive = io.BytesIO()
    class_root = _ROOT / "tools/numerical/portable/build/classes/kotlin/jvm"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as classes:
        for source_set in ("main", "test"):
            directory = class_root / source_set
            for class_file in sorted(directory.rglob("*.class")):
                name = f"{source_set}/{class_file.relative_to(directory)}"
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_STORED
                classes.writestr(entry, class_file.read_bytes())
    return archive.getvalue()


def _check_local_binaries(files, runtime_executable):
    try:
        if files["artifact"] != _STAGED_JAR.read_bytes() or \
                files["runtime"] != Path(runtime_executable).read_bytes():
            raise CaptureRejected("local artifact or runtime differs")
        if files["portable_classes"] != _portable_classes_archive():
            raise CaptureRejected("local portable class archive differs")
        class_root = _ROOT / "tools/numerical/portable/build/classes/kotlin/jvm"
        with zipfile.ZipFile(io.BytesIO(files["portable_classes"])) as classes:
            for name in classes.namelist():
                if classes.read(name) != (class_root / name).read_bytes():
                    raise CaptureRejected("local portable class differs")
            actual_names = {f"{source_set}/{path.relative_to(class_root / source_set)}"
                            for source_set in ("main", "test")
                            for path in (class_root / source_set).rglob("*.class")}
            if set(classes.namelist()) != actual_names:
                raise CaptureRejected("local portable class inventory differs")
    except (OSError, zipfile.BadZipFile) as error:
        raise CaptureRejected("local binary evidence unavailable") from error


def _inspect_worker_classpath(value, staged_jar, class_root, portable_classes=None):
    entries = value.split(":")
    staged = str(staged_jar)
    if not entries or len(entries) != len(set(entries)) or \
            entries.count(staged) != 1 or any(not path.startswith("/") for path in entries):
        raise CaptureRejected("worker classpath identity differs")
    required_dirs = {str(class_root / "main"), str(class_root / "test")}
    if not required_dirs <= set(entries):
        raise CaptureRejected("executed worker classpath omits portable classes")
    evidence = []
    for name in entries:
        path = Path(name)
        try:
            if path.is_dir():
                files = sorted(item for item in path.rglob("*") if item.is_file())
                digest = hashlib.sha256()
                providers = []
                portable_providers = []
                for item in files:
                    relative = item.relative_to(path).as_posix()
                    content = item.read_bytes()
                    digest.update(relative.encode() + b"\0" + _sha(content).encode() + b"\n")
                    if relative.startswith("org/dyn4j/") and relative.endswith(".class"):
                        providers.append(relative)
                    if _PORTABLE_CLASS_MEMBER.search(relative):
                        portable_providers.append((relative, _sha(content)))
                fingerprint = digest.hexdigest()
            elif path.is_file():
                data = path.read_bytes()
                fingerprint = _sha(data)
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    members = archive.namelist()
                    providers = [member for member in members if member.endswith(".class") and
                                 (member.startswith("org/dyn4j/") or
                                  "/org/dyn4j/" in member)]
                    portable_providers = [(member, _sha(archive.read(member)))
                                          for member in members
                                          if _PORTABLE_CLASS_MEMBER.search(member)]
                    if "META-INF/MANIFEST.MF" in members and re.search(
                            rb"(?im)^Class-Path:\s*\S", archive.read("META-INF/MANIFEST.MF")):
                        raise CaptureRejected("worker archive has an indirect classpath")
            else:
                raise CaptureRejected("worker classpath entry unavailable")
        except (OSError, zipfile.BadZipFile) as error:
            raise CaptureRejected("worker classpath entry unavailable") from error
        if name == staged:
            if not _AUDITED_ENGINE_CLASSES <= set(providers):
                raise CaptureRejected("staged JAR omits audited engine classes")
        elif providers:
            raise CaptureRejected("worker classpath shadows the staged engine")
        if portable_classes is not None:
            source_set = next((source_set for source_set in ("main", "test")
                               if name == str(class_root / source_set)), None)
            if source_set is None:
                if portable_providers:
                    raise CaptureRejected("worker classpath shadows compiled portable classes")
            elif dict(portable_providers) != portable_classes[source_set] or \
                    len(portable_providers) != len(portable_classes[source_set]):
                raise CaptureRejected("compiled portable class provider differs")
        evidence.append({"path": name, "sha256": fingerprint})
    return evidence


def _verify_worker_class_load(raw, worker_pid, require_toi_reset, method,
                              portable_classes):
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise CaptureRejected("worker class-load encoding differs") from error
    audited = {name.removesuffix(".class").replace("/", ".")
               for name in _AUDITED_ENGINE_CLASSES}
    if method == "captureRotationPremises":
        required = {name.removesuffix(".class").replace("/", ".") for name in (
            "org/dyn4j/geometry/Transform.class",
            "org/dyn4j/geometry/RotationOperationTap.class",
            "org/dyn4j/geometry/RotationCaptureSlot.class")}
    else:
        required = audited if require_toi_reset else audited - {
            _TOI_RESET_CLASS.removesuffix(".class").replace("/", ".")}
    observed = {}
    portable_sources = {name: source_set for source_set, names in
                        portable_classes.items() for name in names}
    portable_observed = set()
    dynamic_observed = set()
    dynamic_owners = set()
    for line in lines:
        record = re.fullmatch(r"\[([0-9]+)\]\[info\]\[class,load\] "
                              r"([^ ]+) source: (.+)", line)
        if record is None or record.group(1) != worker_pid:
            raise CaptureRejected("worker class-load PID or format differs")
        name, location = record.group(2, 3)
        if name.startswith("portable."):
            if "$$Lambda/" in name:
                owner = name.split("$$Lambda/", 1)[0]
                if owner.replace(".", "/") + ".class" not in portable_sources or \
                        location != owner:
                    raise CaptureRejected("portable lambda source differs")
                if name in dynamic_observed:
                    raise CaptureRejected("duplicate portable lambda class-load record")
                dynamic_observed.add(name)
                dynamic_owners.add(owner.replace(".", "/") + ".class")
                continue
            member = name.replace(".", "/") + ".class"
            source_set = portable_sources.get(member)
            if source_set is None or member in portable_observed:
                raise CaptureRejected("portable worker class-load inventory differs")
            source_root = (_ROOT / "tools/numerical/portable/build/classes/"
                           "kotlin/jvm" / source_set)
            source = urlparse(location)
            if source.scheme != "file" or source.netloc or source.query or \
                    source.fragment or Path(unquote(source.path)).resolve() != \
                    source_root.resolve():
                raise CaptureRejected("portable class loaded outside compiled classes")
            portable_observed.add(member)
            continue
        if name not in audited:
            continue
        if name in observed:
            raise CaptureRejected("duplicate audited worker class-load record")
        source = urlparse(location)
        if source.scheme != "file" or source.netloc or source.query or \
                source.fragment or Path(unquote(source.path)).resolve() != \
                _STAGED_JAR.resolve():
            raise CaptureRejected("audited worker class loaded outside staged JAR")
        observed[name] = location
    if not required <= set(observed):
        raise CaptureRejected("audited worker class-load inventory differs")
    if not dynamic_owners <= portable_observed:
        raise CaptureRejected("portable lambda owner was not loaded")
    if method == "captureRotationPremises":
        required_portable = _FIXTURE_CLASSES | {"portable/ProspectiveOperationMarker.class"}
    else:
        required_portable = {"portable/NumericalRecorder.class"}
        required_portable.add("portable/RevoluteLimitsFalseCaptureTest.class" if
                              method == _FOCUSED_BOOLEAN_METHOD else
                              "portable/ProspectiveArithmeticTest.class")
        if method != _FOCUSED_BOOLEAN_METHOD:
            required_portable.add("portable/PortableMatrixTest.class")
    if method in ("captureWheelActive", _FOCUSED_BOOLEAN_METHOD):
        required_portable |= _WHEEL_RECORDER_CLASSES
    if not required_portable <= portable_observed:
        raise CaptureRejected("required portable worker class-load inventory differs")
    return observed


def _check_process(files, runtime_executable, method, jdi_port=None):
    if runtime_executable != _PINNED_JAVA:
        raise CaptureRejected("runtime executable identity differs")
    try:
        log = files["gradle_log"].decode()
        executions = files["execve_log"].decode()
        stage = files["stage_log"].decode()
        worker_classpath = files["worker_classpath"].decode()
    except UnicodeError as error:
        raise CaptureRejected("process log encoding differs") from error
    process_lines = [line for line in log.splitlines()
                     if "Starting process 'Gradle Test Executor" in line]
    if len(process_lines) != 1 or \
            f"Command: {runtime_executable} " not in process_lines[0] or \
            "GradleWorkerMain" not in process_lines[0] or \
            "BUILD SUCCESSFUL" not in log or "BUILD SUCCESSFUL" not in stage:
        raise CaptureRejected("Gradle target process evidence differs")
    pattern = re.compile(r'^([0-9]+) execve\("' + re.escape(runtime_executable) +
                         r'",.*GradleWorkerMain.*\)\s+=\s+0$')
    worker_lines = [(match.group(1), line) for line in executions.splitlines()
                    if (match := pattern.fullmatch(line))]
    if len(worker_lines) != 1:
        raise CaptureRejected("executed JVM worker identity differs")
    worker_pid, worker_line = worker_lines[0]
    if jdi_port is not None:
        if method != _FOCUSED_BOOLEAN_METHOD or type(jdi_port) is not int or \
                not 1 <= jdi_port <= 65535:
            raise CaptureRejected("JDI target identity differs")
        option = ("-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,"
                  f"address=127.0.0.1:{jdi_port}")
        if worker_line.count(f'"{option}"') != 1 or \
                process_lines[0].count(option) != 1:
            raise CaptureRejected("executed JDI worker option differs")
    log_paths = re.findall(r'"-Xlog:class\+load=info:file='
                           r'(/[^"\r\n:]+/worker-class-load-%p\.log)'
                           r':pid,level,tags:filecount=0"', worker_line)
    if len(log_paths) != 1 or not Path(log_paths[0]).parent.resolve().is_relative_to(
            Path.home().resolve()) or \
            f"-Xlog:class+load=info:file={log_paths[0]}:pid,level,tags:filecount=0" \
            not in process_lines[0]:
        raise CaptureRejected("executed worker class-load option differs")
    target_class = (_FOCUSED_BOOLEAN_CLASS if method == _FOCUSED_BOOLEAN_METHOD
                    else "portable.RotationPremiseFixtureTest"
                    if method == "captureRotationPremises"
                    else "portable.ProspectiveArithmeticTest")
    capture_invocations = [line for line in executions.splitlines()
                           if f'execve("{_ROOT / "gradlew"}"' in line and
                           f'"{target_class}.{method}"' in line and
                           f'"-PportableWorkerClassLoadLog={log_paths[0]}"' in line and
                           line.endswith(" = 0")]
    if len(capture_invocations) != 1:
        raise CaptureRejected("executed capture method or worker log differs")
    if jdi_port is not None and any(
            capture_invocations[0].count(value) != 1 for value in (
                f'"-PportableBooleanJdiPort={jdi_port}"',
                f'"-PportableBooleanJdiMethod={_FOCUSED_BOOLEAN_METHOD}"')):
        raise CaptureRejected("executed JDI method selector differs")
    arguments = worker_classpath.splitlines()
    if len(arguments) != 2 or arguments[0] != "-cp" or \
            str(_STAGED_JAR) not in arguments[1].split(":"):
        raise CaptureRejected("executed worker classpath omits staged engine")
    class_root = _ROOT / "tools/numerical/portable/build/classes/kotlin/jvm"
    try:
        with zipfile.ZipFile(io.BytesIO(files["portable_classes"])) as classes:
            entries = classes.namelist()
            names = set(entries)
            if not {"main/portable/NumericalRecorder.class",
                    "test/" + target_class.replace(".", "/") + ".class",
                    "test/portable/PortableMatrixTest.class"} <= names or \
                    len(entries) != len(names) or \
                    any(not name.startswith(("main/", "test/")) or
                        not name.endswith(".class") for name in entries) or \
                    classes.testzip() is not None:
                raise CaptureRejected("portable test payload differs")
            if method == "captureRotationPremises" and {
                    name.removeprefix("test/") for name in names
                    if name.startswith("test/") and _FIXTURE_CLASS_MEMBER.search(name)
            } != _FIXTURE_CLASSES:
                raise CaptureRejected("compiled fixture class inventory differs")
            portable_classes = {
                source_set: {name.removeprefix(source_set + "/"): _sha(classes.read(name))
                             for name in names if name.startswith(source_set + "/portable/")}
                for source_set in ("main", "test")}
            if portable_classes["main"].keys() & portable_classes["test"].keys():
                raise CaptureRejected("compiled portable class identity is ambiguous")
    except (zipfile.BadZipFile, OSError) as error:
        raise CaptureRejected("portable test payload differs") from error
    classpath_evidence = _inspect_worker_classpath(
        arguments[1], _STAGED_JAR, class_root, portable_classes)
    response_file = re.search(r"@(/[^\s]+gradle-worker-classpath[^\s]+txt)", log)
    if response_file is None or f'"@{response_file.group(1)}"' not in executions:
        raise CaptureRejected("executed worker classpath evidence differs")
    return classpath_evidence, worker_pid, log_paths[0], portable_classes


def verify_worker_write_witness(archive, xml, worker_pid, execve_log,
                                complete_exec=False):
    try:
        if type(complete_exec) is not bool:
            raise CaptureRejected("worker process trace mode differs")
        with zipfile.ZipFile(io.BytesIO(archive)) as traces:
            names = traces.namelist()
            if not names or len(names) > 1024 or len(names) != len(set(names)) or any(
                    re.fullmatch(r"trace\.[1-9][0-9]*", name) is None for name in names):
                raise CaptureRejected("worker write trace inventory differs")
            records = {name.removeprefix("trace."): traces.read(name) for name in names}
        if sum(map(len, records.values())) > 128 * 1024 * 1024 or \
                worker_pid not in records:
            raise CaptureRejected("worker write trace identity differs")
        decoded = {pid: raw.decode("utf-8") for pid, raw in records.items()}
        witnessed_execs = sorted(f"{pid} {line}" for pid, content in decoded.items()
                                 for line in content.splitlines()
                                 if line.startswith("execve(") or
                                 (complete_exec and line.startswith("execveat(")))
        log_lines = execve_log.decode("utf-8").splitlines()
        if complete_exec:
            logged_worker = []
            for line in log_lines:
                pid, separator, call = line.partition(" ")
                if pid in decoded:
                    if not separator or not call.startswith(("execve(", "execveat(")):
                        raise CaptureRejected("worker process log inventory differs")
                    logged_worker.append(line)
            if witnessed_execs != sorted(logged_worker):
                raise CaptureRejected("worker process log inventory differs")
        elif not set(witnessed_execs) <= set(log_lines):
            raise CaptureRejected("worker write process trace differs")
        worker_calls = [line for line in decoded[worker_pid].splitlines()
                        if line.startswith("execve(") and "GradleWorkerMain" in line and
                        line.endswith(" = 0")]
        if len(worker_calls) != 1:
            raise CaptureRejected("worker write process identity differs")
        descendants = {worker_pid}
        pending = [worker_pid]
        while pending:
            parent = pending.pop()
            for line in decoded[parent].splitlines():
                if not line.startswith(("clone(", "clone3(")):
                    continue
                child = re.search(r"\)\s+= ([1-9][0-9]*)$", line)
                if child is None:
                    continue
                pid = child.group(1)
                if pid not in decoded:
                    raise CaptureRejected("worker write child trace is missing")
                if pid not in descendants:
                    descendants.add(pid)
                    pending.append(pid)
        if set(decoded) != descendants:
            raise CaptureRejected("worker write trace inventory differs")
        document = ET.fromstring(xml)
        outputs = document.findall("system-out")
        if len(outputs) != 1 or outputs[0].text is None:
            raise CaptureRejected("worker write XML output differs")
        expected = [line.encode() for line in outputs[0].text.splitlines() if line]
        if not expected or any(not line.startswith(_WITNESS_PREFIXES)
                               for line in expected):
            raise CaptureRejected("worker write XML lines differ")
        streams = []
        for pid in descendants:
            per_fd = {}
            bad_write = False
            for line in decoded[pid].splitlines():
                if line.startswith("write("):
                    match = _WITNESS_WRITE.fullmatch(line)
                    if match is None:
                        bad_write = True
                        continue
                    fd, literal, requested, written = match.groups()
                    payload = ast.literal_eval("b" + literal)
                    if len(payload) != int(requested) or int(requested) != int(written):
                        bad_write = True
                    per_fd.setdefault(fd, []).append(payload)
                elif any(prefix.decode() in line for prefix in _WITNESS_PREFIXES):
                    raise CaptureRejected("worker wrote an unparsed operation record")
            for fd, writes in per_fd.items():
                stream = b"".join(writes)
                if any(prefix in stream for prefix in _WITNESS_PREFIXES):
                    if bad_write:
                        raise CaptureRejected("worker write call is incomplete")
                    streams.append((pid, fd, stream))
        if len(streams) != 1:
            raise CaptureRejected("worker operation writer is ambiguous")
        thread_pid, fd, stream = streams[0]
        observed = []
        for line in stream.split(b"\n"):
            positions = [line.find(prefix) for prefix in _WITNESS_PREFIXES
                         if prefix in line]
            if len(positions) > 1:
                raise CaptureRejected("worker write line contains multiple records")
            if positions:
                observed.append(line[positions[0]:])
        if observed != expected:
            raise CaptureRejected("worker write stream differs from XML")
        return {"status": "PASSED_KERNEL_WORKER_WRITES", "worker_pid": worker_pid,
                "writer_thread_pid": thread_pid, "writer_fd": fd,
                "lines": len(observed),
                "operation_lines": sum(line.startswith(_WITNESS_PREFIXES[1])
                                       for line in observed),
                "stream_sha256": _sha(b"\n".join(observed) + b"\n")}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError,
            zipfile.BadZipFile, SyntaxError) as error:
        if isinstance(error, CaptureRejected):
            raise
        raise CaptureRejected("worker write witness is malformed") from error


def _verify_kernel_class_load_writes(archive, class_load_log, worker_pid):
    pattern = re.compile(rb"\[" + worker_pid.encode() +
                         rb"\]\[info\]\[class,load\] [^ \r\n]+ source: [^\r\n]+")
    try:
        expected = class_load_log.splitlines(keepends=True)
        if not expected or any(not line.endswith(b"\n") or
                               pattern.fullmatch(line[:-1]) is None for line in expected):
            raise CaptureRejected("kernel class-load write log differs")
        if len(expected) != len(set(expected)):
            raise CaptureRejected("duplicate kernel class-load record")
        observed = []
        descriptors = set()
        writers = set()
        streams = {}
        stream_records = Counter()
        with zipfile.ZipFile(io.BytesIO(archive)) as traces:
            for name in traces.namelist():
                pid = name.removeprefix("trace.")
                for line in traces.read(name).decode("utf-8").splitlines():
                    if not line.startswith("write("):
                        if "[class,load]" in line:
                            raise CaptureRejected("kernel class-load write is untrusted")
                        continue
                    match = _WITNESS_WRITE.fullmatch(line)
                    if match is None:
                        raise CaptureRejected("kernel class-load write is incomplete")
                    fd, literal, requested, written = match.groups()
                    payload = ast.literal_eval("b" + literal)
                    if type(payload) is not bytes or len(payload) != int(requested) or \
                            int(requested) != int(written):
                        raise CaptureRejected("kernel class-load write is incomplete")
                    stream = (pid, fd)
                    streams.setdefault(stream, []).append(payload)
                    if b"[class,load]" not in payload:
                        continue
                    if not payload.endswith(b"\n") or payload.count(b"\n") != 1 or \
                            pattern.fullmatch(payload[:-1]) is None:
                        raise CaptureRejected("kernel class-load write is incomplete")
                    observed.append(payload[:-1])
                    descriptors.add(fd)
                    writers.add(pid)
                    stream_records[stream] += 1
        if any(b"".join(writes).count(b"[class,load]") != stream_records[stream]
               for stream, writes in streams.items()):
            raise CaptureRejected("kernel class-load write is untrusted")
        if len(descriptors) != 1 or Counter(line[:-1] for line in expected) != \
                Counter(observed):
            raise CaptureRejected("kernel class-load write membership differs")
        return {"status": "MATCHED_COMPLETE_WRITES_UNBOUND_DESTINATION",
                "records": len(observed), "writer_threads": len(writers)}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError,
            zipfile.BadZipFile, SyntaxError) as error:
        if isinstance(error, CaptureRejected):
            raise
        raise CaptureRejected("kernel class-load write witness is malformed") from error


def _verify_worker_argument_log(raw, response, archive, worker_pid):
    try:
        prefix = f"[{worker_pid}][info][arguments] "
        lines = raw.decode("utf-8").splitlines(keepends=True)
        if len(lines) != 5 or any(not line.endswith("\n") or
                                  not line.startswith(prefix) for line in lines):
            raise CaptureRejected("worker argument log PID or format differs")
        records = [line[len(prefix):-1] for line in lines]
        fields = ("VM Arguments:", "jvm_args: ", "java_command: ",
                  "java_class_path (initial): ", "Launcher Type: ")
        if any(not record.startswith(field) for record, field in zip(records, fields)) or \
                records[0] != fields[0] or \
                not records[2].startswith(
                    fields[2] + "worker.org.gradle.process.internal.worker.GradleWorkerMain") or \
                records[4] != "Launcher Type: SUN_STANDARD":
            raise CaptureRejected("worker startup argument record differs")
        options = re.findall(r"-Xlog:arguments=info:file="
                             r"(/[^\s:]+/worker-arguments-%p\.log)"
                             r":pid,level,tags:filecount=0(?=\s|$)", records[1])
        if len(options) != 1 or records[1].count("-Xlog:arguments=") != 1 or \
                not Path(options[0]).parent.resolve().is_relative_to(
                Path.home().resolve()):
            raise CaptureRejected("worker startup logging option differs")
        response_lines = response.decode("utf-8").splitlines()
        if len(response_lines) != 2 or response_lines[0] != "-cp" or \
                records[3].removeprefix(fields[3]) != response_lines[1]:
            raise CaptureRejected("effective worker classpath differs from response")
        streams = {}
        tagged_streams = set()
        with zipfile.ZipFile(io.BytesIO(archive)) as traces:
            for name in traces.namelist():
                if re.fullmatch(r"trace\.[1-9][0-9]*", name) is None:
                    raise CaptureRejected("worker argument trace member differs")
                pid = name.removeprefix("trace.")
                for line in traces.read(name).decode("utf-8").splitlines():
                    if not line.startswith("write("):
                        if "[arguments]" in line:
                            raise CaptureRejected("untrusted worker argument text")
                        continue
                    match = _WITNESS_WRITE.fullmatch(line)
                    if match is None:
                        if "[arguments]" in line:
                            raise CaptureRejected("worker argument write is incomplete")
                        continue
                    fd, literal, requested, written = match.groups()
                    payload = ast.literal_eval("b" + literal)
                    if type(payload) is not bytes or len(payload) != int(requested) or \
                            int(requested) != int(written):
                        if b"[arguments]" in payload:
                            raise CaptureRejected("worker argument write is incomplete")
                        continue
                    identity = (pid, fd)
                    streams.setdefault(identity, []).append(payload)
                    if b"[arguments]" in payload:
                        tagged_streams.add(identity)
        matches = [(identity, values) for identity, values in streams.items()
                   if b"".join(values) == raw]
        if len(matches) != 1 or tagged_streams != {matches[0][0]}:
            raise CaptureRejected("worker argument kernel writes differ")
        (writer_pid, writer_fd), writes = matches[0]
        return {"status": "MATCHED_INITIAL_CLASSPATH_WRITES_UNBOUND_DESTINATION",
                "writer_thread_pid": writer_pid, "writer_fd": writer_fd,
                "writes": len(writes), "records": len(lines),
                "log_pattern": options[0], "log_sha256": _sha(raw)}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError,
            zipfile.BadZipFile, SyntaxError) as error:
        if isinstance(error, CaptureRejected):
            raise
        raise CaptureRejected("worker argument log witness is malformed") from error


_JDI_FILES = {"jdi_helper_classes", "jdi_evidence", "jdi_helper_traces",
              "jdi_transport"}


def _verify_boolean_jdi(files, summary, worker_pid):
    try:
        transport = json.loads(files["jdi_transport"], object_pairs_hook=_unique_object)
        if type(transport) is not dict or set(transport) != {
                "schema", "port", "worker_pid", "helper_pid", "helper_classes_path",
                "output_path", "temp_path", "live_socket_owner"} or \
                transport["schema"] != "boolean-jdi-transport/1" or \
                transport["worker_pid"] != int(worker_pid) or \
                transport["live_socket_owner"] is not True:
            raise CaptureRejected("JDI transport declaration differs")
        port = transport["port"]
        helper_pid = transport["helper_pid"]
        paths = [transport[name] for name in (
            "helper_classes_path", "output_path", "temp_path")]
        if any(type(path) is not str or not Path(path).is_absolute() or
               not Path(path).resolve().is_relative_to(Path.home().resolve())
               for path in paths):
            raise CaptureRejected("JDI transport path differs")
        with tarfile.open(fileobj=io.BytesIO(files["source"]), mode="r:") as source:
            name = "tools/numerical/portable/boolean_rotation_jdi/RotationJdiProbe.java"
            required = {name, *jdi_source_guard.PINNED_FILES}
            members = {key: [] for key in required}
            for member in source:
                if member.name in members:
                    members[member.name].append(member)
            if any(len(entries) != 1 or not entries[0].isfile()
                   for entries in members.values()):
                raise CaptureRejected("JDI helper source differs")
            for path, digest in jdi_source_guard.PINNED_FILES.items():
                entry = source.extractfile(members[path][0])
                if entry is None or _sha(entry.read()) != digest:
                    raise CaptureRejected("JDI source call schedule differs")
            member = source.extractfile(members[name][0])
            if member is None:
                raise CaptureRejected("JDI helper source is unavailable")
            helper_source = member.read()
        temporary_root = Path(os.environ.get("TMPDIR", ""))
        if not temporary_root.is_absolute() or not temporary_root.resolve().is_relative_to(
                Path.home().resolve()):
            raise CaptureRejected("JDI verifier temporary root differs")
        with tempfile.TemporaryDirectory(dir=temporary_root) as scratch:
            _, compiled = jdi_bridge.compile_helper(helper_source, Path(scratch))
            if compiled != files["jdi_helper_classes"]:
                raise CaptureRejected("JDI helper binary differs from source")
        with zipfile.ZipFile(io.BytesIO(files["artifact"])) as artifact:
            class_name = "org.dyn4j.geometry.Transform"
            class_path = class_name.replace(".", "/") + ".class"
            if artifact.namelist().count(class_path) != 1:
                raise CaptureRejected("JDI engine class inventory differs")
            class_bytes = artifact.read(class_path)
        _, markers = focused_wheel_stream(files["xml"])
        observation = jdi_bridge.verify_jdi_archive(
            files["jdi_evidence"], class_bytes, class_name, 1800, markers)
        writes = jdi_bridge.verify_jdi_file_writes(
            files["jdi_helper_traces"], files["jdi_evidence"], paths[1])
        argv = [str(jdi_bridge.JDK21 / "bin/java"), "--add-modules", "jdk.jdi",
                "-Djava.io.tmpdir=" + paths[2], "-cp", paths[0],
                "RotationJdiProbe", "attach", paths[1], "127.0.0.1",
                str(port), class_name, "1800", "600"]
        process = jdi_bridge.verify_jdi_transport(
            files["worker_write_traces"], files["jdi_helper_traces"],
            port, int(worker_pid), helper_pid, argv)
        sites = jdi_bridge.derive_call_sites(files["artifact"])
        identity = {"schema": jdi_witness.SCHEMA, "pid": int(worker_pid),
                    "case_id": _FOCUSED_BOOLEAN_CASE,
                    "source_sha256": _sha(files["source"]),
                    "jar_sha256": _sha(files["artifact"]),
                    "loaded_code_sha256": _sha(class_bytes),
                    "marker_sha256": summary["operations_sha256"],
                    "calls": observation["calls"]}
        result = jdi_witness.verify_stream(identity, {
            **{key: identity[key] for key in (
                "pid", "case_id", "source_sha256", "jar_sha256",
                "loaded_code_sha256", "marker_sha256")},
            "markers": markers, "caller_code_indices": sites})
        if result != {"status": "UNPASSED_WORKER_BINDING",
                      "qualification": "UNPASSED", "calls_checked": 1800}:
            raise CaptureRejected("JDI source operation stream differs")
        return {"status": "MATCHED_JDI_SOURCE_STREAM_UNPASSED_RUNTIME_ORIGIN",
                "qualification": "UNPASSED", "calls_checked": 1800,
                "source_sites": sites,
                "artifact_class_sha256": observation["artifact_class_sha256"],
                "helper_classes_sha256": _sha(compiled),
                "event_archive_sha256": _sha(files["jdi_evidence"]),
                "transport_status": process["status"],
                "file_write_status": writes["status"]}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError,
            tarfile.TarError, zipfile.BadZipFile, jdi_bridge.EvidenceRejected) as error:
        if isinstance(error, CaptureRejected):
            raise
        raise CaptureRejected("JDI source or process evidence differs") from error


def make_capture_receipt(files, method, commit, expected_ids, runtime_executable):
    requires_writes = method in ("captureWheelActive", "captureRotationPremises",
                                 _FOCUSED_BOOLEAN_METHOD)
    required_files = _RECEIPT_FILES | ({"worker_write_traces"}
                                     if requires_writes else set())
    jdi_files = (set(files) & _JDI_FILES) if type(files) is dict else set()
    if jdi_files and (method != _FOCUSED_BOOLEAN_METHOD or jdi_files != _JDI_FILES):
        raise CaptureRejected("JDI receipt inventory differs")
    if method == _FOCUSED_BOOLEAN_METHOD:
        required_files |= {"worker_arguments", "reference_case", "candidate_case"}
        required_files |= jdi_files
    if type(files) is not dict or set(files) != required_files or \
            any(type(value) is not bytes or not value for value in files.values()) or \
            type(commit) is not str or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise CaptureRejected("receipt input identity differs")
    if files["source"] != _source_archive(commit):
        raise CaptureRejected("source archive differs from candidate commit")
    if method == _FOCUSED_BOOLEAN_METHOD:
        _verify_boolean_source(files["source"])
    _check_local_binaries(files, runtime_executable)
    jdi_transport = None
    if jdi_files:
        try:
            jdi_transport = json.loads(files["jdi_transport"],
                                       object_pairs_hook=_unique_object)
            if type(jdi_transport) is not dict:
                raise CaptureRejected("JDI transport declaration differs")
        except (UnicodeError, TypeError, ValueError) as error:
            raise CaptureRejected("JDI transport declaration differs") from error
    classpath_evidence, worker_pid, log_path, portable_classes = _check_process(
        files, runtime_executable, method,
        jdi_port=jdi_transport.get("port") if jdi_transport else None)
    reset_order = ("pre" if commit == "fe4d63cb7f08cea304e5691f2f2ebc23379db6b0"
                   else "post")
    summary = verify_capture(files["xml"], method, expected_ids, reset_order)
    if method == _FOCUSED_BOOLEAN_METHOD:
        if expected_ids != [_FOCUSED_BOOLEAN_CASE] or \
                _sha(files["reference_case"]) != _FOCUSED_BOOLEAN_REFERENCE_SHA256 or \
                load_policy_catalog()["cases"][_FOCUSED_BOOLEAN_CASE]["sha256"] != \
                _FOCUSED_BOOLEAN_REFERENCE_SHA256 or \
                focused_wheel_stream(files["xml"])[0] != files["candidate_case"] or \
                _sha(files["candidate_case"]) != summary["trace_sha256"]:
            raise CaptureRejected("focused Boolean indexed reference differs")
    worker_sources = _verify_worker_class_load(
        files["worker_class_load"], worker_pid, summary["selected_resets"] > 0,
        method, portable_classes)
    receipt = {"schema": ("portable-arithmetic-capture-receipt/5" if jdi_files
                          else "portable-arithmetic-capture-receipt/4" if
                          method == _FOCUSED_BOOLEAN_METHOD else
                          "portable-arithmetic-capture-receipt/3"),
            "candidate_commit": commit, "method": method, "exit_code": 0,
            "runtime_executable": runtime_executable,
            "source_archive_sha256": _sha(files["source"]),
            "artifact_sha256": _sha(files["artifact"]),
            "runtime_sha256": _sha(files["runtime"]),
            "xml_sha256": _sha(files["xml"]),
            "stage_log_sha256": _sha(files["stage_log"]),
            "gradle_log_sha256": _sha(files["gradle_log"]),
            "execve_log_sha256": _sha(files["execve_log"]),
            "worker_classpath_sha256": _sha(files["worker_classpath"]),
            "worker_class_load_sha256": _sha(files["worker_class_load"]),
            "portable_classes_sha256": _sha(files["portable_classes"]),
            "worker_classpath_entries": classpath_evidence,
            "worker_pid": worker_pid,
            "worker_class_load_pattern": log_path,
            "worker_class_load_sources": worker_sources,
            "summary": summary}
    if requires_writes:
        witness = verify_worker_write_witness(files["worker_write_traces"],
                                              files["xml"], worker_pid,
                                              files["execve_log"],
                                              complete_exec=bool(jdi_files))
        receipt["worker_write_traces_sha256"] = _sha(files["worker_write_traces"])
        receipt["external_xml_witness"] = witness
        summary["external_xml_witness"] = witness["status"]
    if method == _FOCUSED_BOOLEAN_METHOD:
        argument_witness = _verify_worker_argument_log(
            files["worker_arguments"], files["worker_classpath"],
            files["worker_write_traces"], worker_pid)
        receipt["worker_arguments_sha256"] = _sha(files["worker_arguments"])
        receipt["reference_case_sha256"] = _sha(files["reference_case"])
        receipt["candidate_case_sha256"] = _sha(files["candidate_case"])
        receipt["worker_argument_witness"] = argument_witness
        summary["effective_classpath_witness"] = argument_witness["status"]
        if jdi_files:
            jdi_witness = _verify_boolean_jdi(files, summary, worker_pid)
            for name in _JDI_FILES:
                receipt[name + "_sha256"] = _sha(files[name])
            receipt["jdi_external_witness"] = jdi_witness
            summary["jdi_external_witness"] = jdi_witness["status"]
    return receipt


def verify_capture_receipt(receipt, files, method, commit, expected_ids,
                           runtime_executable):
    if type(receipt) is not dict or type(receipt.get("exit_code")) is not int or \
            receipt["exit_code"] != 0:
        raise CaptureRejected("target receipt or process exit differs")
    expected = make_capture_receipt(files, method, commit, expected_ids,
                                    runtime_executable)
    if receipt != expected:
        raise CaptureRejected("target receipt identity or captured bytes differ")
    summary = dict(expected["summary"])
    if method in ("captureWheelActive", _FOCUSED_BOOLEAN_METHOD):
        # The receipt check binds every ZIP member to the worker process tree.
        # Write matching does not identify the descriptor destination.
        summary["kernel_class_load_write_witness"] = _verify_kernel_class_load_writes(
            files["worker_write_traces"], files["worker_class_load"],
            expected["worker_pid"])
    if method == _FOCUSED_BOOLEAN_METHOD:
        summary["effective_classpath_witness"] = _verify_worker_argument_log(
            files["worker_arguments"], files["worker_classpath"],
            files["worker_write_traces"], expected["worker_pid"])["status"]
    summary["operation_record_status"] = summary["status"]
    summary["dynamic_class_load_status"] = "UNBOUND"
    if summary["status"] == "VERIFIED_ARITHMETIC_BINDING":
        summary["status"] = "UNPASSED_DYNAMIC_CLASS_LOAD"
    return summary


def focused_wheel_stream(xml):
    try:
        document = ET.fromstring(xml)
        outputs = document.findall("system-out")
        if len(outputs) != 1 or outputs[0].text is None:
            raise CaptureRejected("focused Wheel output is missing")
        lines = outputs[0].text.splitlines()
        trace = b"".join((line.removeprefix("NUMERICAL_JSON ") + "\n").encode()
                         for line in lines if line.startswith("NUMERICAL_JSON "))
        markers = [json.loads(line.removeprefix("PROSPECTIVE_ROTATION_JSON "),
                              object_pairs_hook=_unique_object)
                   for line in lines if line.startswith("PROSPECTIVE_ROTATION_JSON ")]
        return trace, markers
    except (ET.ParseError, UnicodeError, TypeError, ValueError) as error:
        raise CaptureRejected("focused Wheel stream is malformed") from error


def _wheel_rotation_audit(markers):
    calls = []
    for marker in markers:
        if marker["body_id"] is None:
            continue
        if marker["kind"] != "rotate":
            raise CaptureRejected("focused Wheel reset needs a separate source audit")
        raw = [struct.unpack(">d", bytes.fromhex(value))[0] for value in marker["raw"]]
        call = {key: marker[key] for key in
                ("step", "body_id", "kind", "branch", "pre", "trig", "raw", "post")}
        call.update(sequence=len(calls),
                    clamp=[value < -1.0 or value > 1.0 for value in raw])
        if marker["angle_bits"] is None:
            call.update(input_kind="pair", rotation_input=marker["trig"])
        else:
            call.update(input_kind="angle", angle_bits=marker["angle_bits"])
        calls.append(call)
    if len(markers) != 600 * len(_FOCUSED_WHEEL_STEP_CALLS):
        raise CaptureRejected("focused Wheel source call schedule differs")
    for step in range(1, 601):
        start = (step - 1) * len(_FOCUSED_WHEEL_STEP_CALLS)
        _require_focused_wheel_step_calls(
            markers[start:start + len(_FOCUSED_WHEEL_STEP_CALLS)], step)
    return {"schema": "portable-rotation-audit/2", "case_id": "joint-Wheel-active",
            "operation_model_revision": "058bf6d982a0fb89b54050f929f6ea9dae53b714",
            "declared_calls": len(calls), "accepted_toi_resets": [], "calls": calls}


def assess_focused_wheel(receipt, files, commit, runtime_executable,
                         reference_case, candidate_case):
    expected = ["joint-Wheel-active"]
    summary = verify_capture_receipt(receipt, files, "captureWheelActive", commit,
                                     expected, runtime_executable)
    trace, markers = focused_wheel_stream(files["xml"])
    if _sha(trace) != summary["trace_sha256"] or trace != Path(candidate_case).read_bytes():
        raise CaptureRejected("focused Wheel trace differs from sealed output")
    catalog = load_policy_catalog()
    case = next(case for case in declared_cases() if case["id"] == expected[0])
    if _sha(Path(reference_case).read_bytes()) != catalog["cases"][expected[0]]["sha256"]:
        raise CaptureRejected("focused Wheel reference differs from adopted catalog")
    fixed = compare_policy_case(reference_case, candidate_case, case, catalog)
    conditional = compare_policy_case(reference_case, candidate_case, case, catalog,
                                      conditional_diagnostic=True)
    rows = [json.loads(line) for line in trace.splitlines()]
    header = rows[0]
    states = {row["step"]: row["state"] for row in rows if row["kind"] == "state"}
    audit = _wheel_rotation_audit(markers)
    try:
        validate_rotation_audit(audit, case, header, states, source_rotation_cap(case))
        structural = "STRUCTURE_PASSED"
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        structural = "UNPASSED_AUDIT: " + str(error)
    return {"schema": "portable-focused-wheel-assessment/1",
            "candidate_commit": commit, "case_id": expected[0],
            "reference_case_sha256": catalog["cases"][expected[0]]["sha256"],
            "candidate_case_sha256": _sha(trace),
            "receipt_sha256": _sha(json.dumps(receipt, sort_keys=True, indent=2).encode() + b"\n"),
            "operation_count": summary["operations_verified"],
            "body_bound_operations": summary["body_bound_operations"],
            "pair_inputs_unbound": summary["pair_inputs_unbound"],
            "operation_oracle": summary["status"],
            "rotation_audit": structural,
            "fixed_status": fixed["status"], "fixed_failed_step": fixed.get("failed_step"),
            "conditional_status": conditional["status"],
            "external_xml_witness": receipt["external_xml_witness"]["status"],
            "qualification": "UNPASSED"}
