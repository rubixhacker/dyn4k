import ast
import hashlib
import io
import json
import re
import struct
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.parsers import expat

from cases import declared_cases
from rotation_oracle import verify_operation_marker
from orthogonality import source_rotation_cap, validate_rotation_audit
from prospective_compare import compare_policy_case, load_policy_catalog


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
    "captureJointBooleanModes": "independentJointBooleanModes",
    "captureJointNumericModes": "independentJointNumericAndLimitModes",
    "captureAngleFailure": "baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure",
    "captureCcd": "continuousCollisionCasesAtFrozenRates",
    "captureLongMotion": "longRunningFreeMotionInvariantScene",
}

_FOCUSED_WHEEL_STEP_CALLS = (("b1", "integrate"), ("b0", "joint"),
                             ("b1", "joint"))
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
                 if method != "captureWheelActive" for case_id in ids]
    if len(inventory) != 332 or len(set(inventory)) != 332:
        raise CaptureRejected("prospective wrapper inventory differs")
    if include_focused:
        result["captureWheelActive"] = ["joint-Wheel-active"]
    else:
        del result["captureWheelActive"]
    return result


def verify_capture(xml, method, expected_ids=None, reset_order="either"):
    if method not in _WRAPPERS:
        raise CaptureRejected("unknown producer method")
    if reset_order not in {"pre", "post", "either"}:
        raise CaptureRejected("unknown accepted reset order")
    if expected_ids is None:
        expected_ids = expected_case_ids(method == "captureWheelActive")[method]
    if not isinstance(expected_ids, list) or len(set(expected_ids)) != len(expected_ids):
        raise CaptureRejected("expected case inventory differs")
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
        if method == "captureWheelActive" and marker["body_id"] is not None and \
                marker.get("branch") not in ("integrate", "joint", "contact"):
            raise CaptureRejected("focused Wheel source branch is unbound")
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
        outcome = verify_operation_marker(marker)
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
            testcases[0].get("classname") != "portable.ProspectiveArithmeticTest" or \
            testcases[0].get("name") not in (method, f"{method}[jvm]") or \
            active is not None or ids != expected_ids:
        raise CaptureRejected("target method or case inventory differs")
    if body_step_receipts == 0:
        raise CaptureRejected("empty body-step inventory")
    return {"status": "VERIFIED_ARITHMETIC_BINDING" if not pair_inputs_unbound
            else "UNPASSED_INPUT_ORIGIN", "qualification": "UNPASSED",
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


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _source_archive(commit):
    if type(commit) is not str or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise CaptureRejected("candidate commit identity differs")
    result = subprocess.run(("git", "-c", "core.autocrlf=false",
                             "--no-replace-objects", "archive", "--format=tar",
                             commit),
                            cwd=_ROOT, capture_output=True, check=False)
    if result.returncode:
        raise CaptureRejected("candidate commit archive unavailable")
    return result.stdout


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
    required_portable = {"portable/ProspectiveArithmeticTest.class",
                         "portable/PortableMatrixTest.class",
                         "portable/NumericalRecorder.class"}
    if method == "captureWheelActive":
        required_portable |= _WHEEL_RECORDER_CLASSES
    if not required_portable <= portable_observed:
        raise CaptureRejected("required portable worker class-load inventory differs")
    return observed


def _check_process(files, runtime_executable, method):
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
    log_paths = re.findall(r'"-Xlog:class\+load=info:file='
                           r'(/[^"\r\n:]+/worker-class-load-%p\.log)'
                           r':pid,level,tags:filecount=0"', worker_line)
    if len(log_paths) != 1 or not Path(log_paths[0]).parent.resolve().is_relative_to(
            Path.home().resolve()) or \
            f"-Xlog:class+load=info:file={log_paths[0]}:pid,level,tags:filecount=0" \
            not in process_lines[0]:
        raise CaptureRejected("executed worker class-load option differs")
    capture_invocations = [line for line in executions.splitlines()
                           if f'execve("{_ROOT / "gradlew"}"' in line and
                           f'"portable.ProspectiveArithmeticTest.{method}"' in line and
                           f'"-PportableWorkerClassLoadLog={log_paths[0]}"' in line and
                           line.endswith(" = 0")]
    if len(capture_invocations) != 1:
        raise CaptureRejected("executed capture method or worker log differs")
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
                    "test/portable/ProspectiveArithmeticTest.class",
                    "test/portable/PortableMatrixTest.class"} <= names or \
                    len(entries) != len(names) or \
                    any(not name.startswith(("main/", "test/")) or
                        not name.endswith(".class") for name in entries) or \
                    classes.testzip() is not None:
                raise CaptureRejected("portable test payload differs")
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


def verify_worker_write_witness(archive, xml, worker_pid, execve_log):
    try:
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
        witnessed_execve = sorted(f"{pid} {line}" for pid, content in decoded.items()
                                  for line in content.splitlines()
                                  if line.startswith("execve("))
        if not set(witnessed_execve) <= set(execve_log.decode("utf-8").splitlines()):
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


def make_capture_receipt(files, method, commit, expected_ids, runtime_executable):
    required_files = _RECEIPT_FILES | ({"worker_write_traces"}
                                     if method == "captureWheelActive" else set())
    if type(files) is not dict or set(files) != required_files or \
            any(type(value) is not bytes or not value for value in files.values()) or \
            type(commit) is not str or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise CaptureRejected("receipt input identity differs")
    if files["source"] != _source_archive(commit):
        raise CaptureRejected("source archive differs from candidate commit")
    _check_local_binaries(files, runtime_executable)
    classpath_evidence, worker_pid, log_path, portable_classes = _check_process(
        files, runtime_executable, method)
    reset_order = ("pre" if commit == "fe4d63cb7f08cea304e5691f2f2ebc23379db6b0"
                   else "post")
    summary = verify_capture(files["xml"], method, expected_ids, reset_order)
    worker_sources = _verify_worker_class_load(
        files["worker_class_load"], worker_pid, summary["selected_resets"] > 0,
        method, portable_classes)
    receipt = {"schema": "portable-arithmetic-capture-receipt/3",
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
    if method == "captureWheelActive":
        witness = verify_worker_write_witness(files["worker_write_traces"],
                                              files["xml"], worker_pid,
                                              files["execve_log"])
        receipt["worker_write_traces_sha256"] = _sha(files["worker_write_traces"])
        receipt["external_xml_witness"] = witness
        summary["external_xml_witness"] = witness["status"]
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
