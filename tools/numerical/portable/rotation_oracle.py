import ctypes
import ctypes.util
import hashlib
import json
import math
import re
import struct
from fractions import Fraction


SOURCE_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
MPFR_VERSION = "4.2.2"
_TRIG_ERROR = 2.0 ** -52
_PI = struct.unpack(">d", bytes.fromhex("400921fb54442d18"))[0]
_TWO_PI = struct.unpack(">d", bytes.fromhex("401921fb54442d18"))[0]
_HEX = re.compile(r"[0-9a-f]{16}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_BINDING_FIELDS = {"producer_process", "producer_command", "artifact_sha256",
                   "runtime_id", "target_source_sha256", "operation_source_revision",
                   "trace_sha256", "payload_sha256", "receipt_sha256", "audit_sha256",
                   "manifest_sha256",
                   "expected_calls", "body_step_receipts", "accepted_toi_resets",
                   "accepted_toi_events",
                   "reset_start_rotations", "reset_end_rotations", "pair_inputs",
                   "allowed_evaluations"}
_EVALUATIONS = ("strict", "fma_left", "fma_right", "fused")


class _MPFRNumber(ctypes.Structure):
    _fields_ = [("precision", ctypes.c_long), ("sign", ctypes.c_int),
                ("exponent", ctypes.c_long), ("limbs", ctypes.c_void_p)]


class _MPFR:
    def __init__(self):
        path = ctypes.util.find_library("mpfr")
        if path is None:
            raise RuntimeError("GNU MPFR is unavailable")
        self.lib = ctypes.CDLL(path)
        self.lib.mpfr_get_version.restype = ctypes.c_char_p
        self.version = self.lib.mpfr_get_version().decode("ascii")
        if self.version != MPFR_VERSION:
            raise RuntimeError("GNU MPFR 4.2.2 is required")
        self.library = path
        self.lib.mpfr_init2.argtypes = [ctypes.POINTER(_MPFRNumber), ctypes.c_long]
        self.lib.mpfr_clear.argtypes = [ctypes.POINTER(_MPFRNumber)]
        self.lib.mpfr_set_d.argtypes = [ctypes.POINTER(_MPFRNumber), ctypes.c_double,
                                      ctypes.c_int]
        self.lib.mpfr_get_d.argtypes = [ctypes.POINTER(_MPFRNumber), ctypes.c_int]
        self.lib.mpfr_get_d.restype = ctypes.c_double
        self.lib.mpfr_add_d.argtypes = [ctypes.POINTER(_MPFRNumber),
                                       ctypes.POINTER(_MPFRNumber), ctypes.c_double,
                                       ctypes.c_int]
        self.lib.mpfr_sub_d.argtypes = self.lib.mpfr_add_d.argtypes
        self.lib.mpfr_cmp.argtypes = [ctypes.POINTER(_MPFRNumber),
                                     ctypes.POINTER(_MPFRNumber)]
        self.lib.mpfr_cmp.restype = ctypes.c_int
        for name in ("sin", "cos", "acos"):
            getattr(self.lib, "mpfr_" + name).argtypes = [ctypes.POINTER(_MPFRNumber),
                                                          ctypes.POINTER(_MPFRNumber),
                                                          ctypes.c_int]

    def interval(self, operation, value):
        source, lower, upper = (_MPFRNumber() for _ in range(3))
        for number in (source, lower, upper):
            self.lib.mpfr_init2(ctypes.byref(number), 320)
        try:
            self.lib.mpfr_set_d(ctypes.byref(source), value, 0)
            function = getattr(self.lib, "mpfr_" + operation)
            function(ctypes.byref(lower), ctypes.byref(source), 3)
            function(ctypes.byref(upper), ctypes.byref(source), 2)
            return (self.lib.mpfr_get_d(ctypes.byref(lower), 3),
                    self.lib.mpfr_get_d(ctypes.byref(upper), 2))
        finally:
            for number in (source, lower, upper):
                self.lib.mpfr_clear(ctypes.byref(number))

    def within_error(self, operation, argument, observed, error):
        source, lower, upper, target, left, right = (_MPFRNumber() for _ in range(6))
        numbers = (source, lower, upper, target, left, right)
        for number in numbers:
            self.lib.mpfr_init2(ctypes.byref(number), 320)
        try:
            self.lib.mpfr_set_d(ctypes.byref(source), argument, 0)
            self.lib.mpfr_set_d(ctypes.byref(target), observed, 0)
            function = getattr(self.lib, "mpfr_" + operation)
            function(ctypes.byref(lower), ctypes.byref(source), 3)
            function(ctypes.byref(upper), ctypes.byref(source), 2)
            lower_binary64 = self.lib.mpfr_get_d(ctypes.byref(lower), 3)
            if observed == 0 and math.copysign(1.0, observed) != math.copysign(
                    1.0, lower_binary64):
                return False
            self.lib.mpfr_sub_d(ctypes.byref(left), ctypes.byref(target), error, 2)
            self.lib.mpfr_add_d(ctypes.byref(right), ctypes.byref(target), error, 3)
            return (self.lib.mpfr_cmp(ctypes.byref(left), ctypes.byref(lower)) <= 0 and
                    self.lib.mpfr_cmp(ctypes.byref(upper), ctypes.byref(right)) <= 0)
        finally:
            for number in numbers:
                self.lib.mpfr_clear(ctypes.byref(number))


_mpfr = None


def _interval(operation, value):
    global _mpfr
    if _mpfr is None:
        _mpfr = _MPFR()
    return _mpfr.interval(operation, value)


def _within_error(operation, argument, observed, error):
    global _mpfr
    if _mpfr is None:
        _mpfr = _MPFR()
    return _mpfr.within_error(operation, argument, observed, error)


def _bits(value):
    return struct.pack(">d", value).hex()


def _binary64(value):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ValueError("invalid binary64 encoding")
    decoded = struct.unpack(">d", bytes.fromhex(value))[0]
    if not math.isfinite(decoded):
        raise ValueError("nonfinite binary64 field")
    return decoded


def _pair(value):
    if type(value) is not list or len(value) != 2:
        raise ValueError("incomplete binary64 pair")
    return (_binary64(value[0]), _binary64(value[1]))


def trig_interval(angle_bits):
    angle = _binary64(angle_bits)
    return (_interval("cos", angle), _interval("sin", angle))


def _verify_trig(angle_bits, trig):
    angle = _binary64(angle_bits)
    if angle == 0:
        expected = [1.0, angle]
        if [_bits(value) for value in trig] != [_bits(value) for value in expected]:
            raise ValueError("zero-angle trig special case differs")
        return
    for operation, observed in zip(("cos", "sin"), trig):
        if not _within_error(operation, angle, observed, _TRIG_ERROR):
            raise ValueError("trig exceeds approved absolute 2u error")


def _signed_product(a, b, rounded):
    value = Fraction.from_float(a) * Fraction.from_float(b)
    negative_zero = value == 0 and math.copysign(1.0, a) != math.copysign(1.0, b)
    if rounded:
        result = a * b
        return Fraction.from_float(result), result == 0 and math.copysign(1.0, result) < 0
    return value, negative_zero


def _rounded_sum(left, right, subtract=False):
    a, a_negative = left
    b, b_negative = right
    if subtract:
        b, b_negative = -b, not b_negative
    total = a + b
    if total:
        return float(total)
    return -0.0 if a == b == 0 and a_negative and b_negative else 0.0


def _component_values(a, b, c, d, subtract):
    results = {}
    for mode, (left_exact, right_exact) in zip(
            _EVALUATIONS, ((False, False), (True, False),
                           (False, True), (True, True))):
        left = _signed_product(a, b, not left_exact)
        right = _signed_product(c, d, not right_exact)
        results[mode] = _bits(_rounded_sum(left, right, subtract))
    return results


def _state_pair(transform):
    values = []
    for key in ("getCost", "getSint"):
        value = transform[key]
        if type(value) not in (float, int) or not math.isfinite(value) or abs(value) > 1:
            raise ValueError("invalid transform state")
        values.append(_bits(float(value)))
    return values


def _source_angle_matches(rotation, observed):
    cost, sint = rotation
    if not -1.0 <= cost <= 1.0 or not -1.0 <= sint <= 1.0:
        raise ValueError("rotation component outside source domain")
    negative = sint < 0
    if cost == 1.0:
        return _bits(observed) == _bits(-0.0 if negative else 0.0)
    if observed == 0 or abs(observed) > _PI or (observed < 0) != negative:
        return False
    lower, upper = _interval("acos", cost)
    if lower != upper and math.nextafter(lower, math.inf) != upper:
        raise RuntimeError("acos one-ulp bracket is unresolved")
    error = upper - lower if lower != upper else math.ulp(lower)
    return _within_error("acos", cost, abs(observed), error)


def _verify_rotate(call, pre, trig, allowed_evaluations, pair_input):
    fields = {"sequence", "step", "body_id", "kind", "branch", "input_kind",
              "pre", "trig", "raw", "post", "clamp"}
    if call.get("input_kind") == "angle":
        fields.add("angle_bits")
        _verify_trig(call["angle_bits"], trig)
    elif call.get("input_kind") == "pair":
        fields.add("rotation_input")
        if pair_input is None:
            raise RuntimeError("independent Rotation pair input is unavailable")
        if any(abs(value) > 1 for value in _pair(call["rotation_input"])):
            raise ValueError("rotation pair outside source component range")
        if call["rotation_input"] != call["trig"] or call["rotation_input"] != pair_input:
            raise ValueError("rotation pair input differs")
    else:
        raise ValueError("unknown rotation input")
    if set(call) != fields or call["branch"] not in ("integrate", "joint", "contact"):
        raise ValueError("rotate record shape differs")
    raw = _pair(call["raw"])
    if type(call["clamp"]) is not list or len(call["clamp"]) != 2 or any(
            type(marker) is not bool for marker in call["clamp"]):
        raise ValueError("invalid clamp markers")
    candidates = (_component_values(trig[0], pre[0], trig[1], pre[1], True),
                  _component_values(trig[1], pre[0], trig[0], pre[1], False))
    observed = []
    for index in (0, 1):
        modes = [mode for mode in allowed_evaluations
                 if candidates[index][mode] == call["raw"][index]]
        if not modes:
            raise ValueError("raw two-product sum outside source envelope")
        observed.append(modes)
        expected = min(1.0, max(-1.0, raw[index]))
        if call["clamp"][index] != (raw[index] < -1.0 or raw[index] > 1.0):
            raise ValueError("clamp marker differs")
        if call["post"][index] != _bits(expected):
            raise ValueError("clamped orientation differs")
    return observed


def _verify_reset(call, pre, trig, start_rotation, end_rotation,
                  allowed_evaluations):
    fields = {"sequence", "step", "body_id", "kind", "branch", "pre", "trig",
              "post", "alpha_bits", "start_angle_bits", "end_angle_bits",
              "diff_bits", "angle_bits"}
    if set(call) != fields or call["branch"] != "toi":
        raise ValueError("lerp reset record shape differs")
    alpha = _binary64(call["alpha_bits"])
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("TOI alpha outside source interval")
    start = _binary64(call["start_angle_bits"])
    end = _binary64(call["end_angle_bits"])
    if list(end_rotation) != call["pre"] or not _source_angle_matches(
            _pair(start_rotation), start) or not _source_angle_matches(
                _pair(end_rotation), end):
        raise ValueError("source angle differs")
    diff = end - start
    if diff < -_PI:
        diff += _TWO_PI
    if diff > _PI:
        diff -= _TWO_PI
    if call["diff_bits"] != _bits(diff):
        raise ValueError("shortest angle difference differs")
    strict = _bits(diff * alpha + start)
    fused = _bits(_rounded_sum(_signed_product(diff, alpha, False),
                              (Fraction.from_float(start),
                               start == 0 and math.copysign(1.0, start) < 0)))
    matching = [mode for mode, result in (("strict", strict), ("fused", fused))
                if mode in allowed_evaluations and call["angle_bits"] == result]
    if not matching:
        raise ValueError("lerp angle arithmetic differs")
    _verify_trig(call["angle_bits"], trig)
    if call["post"] != call["trig"]:
        raise ValueError("direct-trig reset differs")
    return matching


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _audit_bytes(audit):
    return json.dumps(audit, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _manifest_bytes(binding):
    fields = ("expected_calls", "body_step_receipts", "accepted_toi_resets",
              "accepted_toi_events",
              "reset_start_rotations", "reset_end_rotations", "pair_inputs",
              "allowed_evaluations")
    return _audit_bytes({key: binding[key] for key in fields})


def _trace_matches(trace_bytes, case, header, states):
    try:
        rows = [json.loads(line) for line in trace_bytes.splitlines() if line.strip()]
        inputs = [row for row in rows if row["kind"] == "inputs"]
        endings = [row for row in rows if row["kind"] == "case-end"]
        observed = [row for row in rows if row["kind"] == "state"]
        if len(inputs) != 1 or len(endings) != 1 or len(observed) != case["steps"] or \
                rows[0]["kind"] != "inputs" or rows[-1]["kind"] != "case-end" or \
                any(row["id"] != case["id"] for row in rows):
            return False
        if inputs[0]["id"] != case["id"] or inputs[0]["steps"] != case["steps"] or \
                endings[0]["id"] != case["id"] or endings[0]["steps"] != case["steps"]:
            return False
        if _audit_bytes({key: inputs[0][key] for key in ("initial", "setup")}) != \
                _audit_bytes({key: header[key] for key in ("initial", "setup")}):
            return False
        if [row["step"] for row in observed] != list(range(1, case["steps"] + 1)):
            return False
        return all(row["id"] == case["id"] and
                   _audit_bytes(row["state"]) == _audit_bytes(states[row["step"]])
                   for row in observed)
    except (ValueError, TypeError, KeyError, IndexError, UnicodeError):
        return False


def _verify_reset_provenance(call, binding, states, trace_bytes, body_ids):
    sequence = str(call["sequence"])
    event = binding["accepted_toi_events"].get(sequence)
    start_pair = binding["reset_start_rotations"].get(sequence)
    if event is None or start_pair is None:
        raise RuntimeError("accepted TOI call or previous rotation is unavailable")
    if type(event) is not dict or set(event) != {
            "step", "order", "body_id", "alpha_bits", "accepted"} or \
            event["accepted"] is not True or \
            type(event["step"]) is not int or event["step"] != call["step"] or \
            type(event["order"]) is not int or \
            event["body_id"] != call["body_id"]:
        raise ValueError("accepted TOI event binding differs")
    _binary64(event["alpha_bits"])
    if call["alpha_bits"] != event["alpha_bits"]:
        raise ValueError("lerp alpha differs from accepted TOI call")
    body_state = next((body for body in states[call["step"]]["bodies"]
                       if body["id"] == call["body_id"]), None)
    if body_state is None or "previousTransform" not in body_state:
        raise RuntimeError("recorded previous transform is unavailable")
    if _state_pair(body_state["previousTransform"]) != start_pair:
        raise ValueError("lerp start differs from recorded previous transform")
    rows = [json.loads(line) for line in trace_bytes.splitlines() if line.strip()]
    matches = [row for row in rows if row["kind"] == "event" and
               row.get("step") == event["step"] and row.get("order") == event["order"] and
               row.get("name") in ("toi.payload.bodies", "toi.payload.fixtures")]
    if len(matches) != 1:
        raise RuntimeError("accepted TOI time is unavailable in trace")
    payload = matches[0].get("payload")
    if type(payload) is not dict or type(payload.get("time")) is not float or \
            not math.isfinite(payload["time"]) or \
            type(payload.get("bodies")) is not list or \
            any(type(index) is not int or index < 0 or index >= len(body_ids)
                for index in payload["bodies"]) or \
            body_ids.index(call["body_id"]) not in payload["bodies"] or \
            _bits(payload["time"]) != event["alpha_bits"]:
        raise ValueError("accepted TOI time or body differs from trace")


def _verify_binding(audit, binding, trace_bytes, payload_bytes, receipt_bytes,
                    artifact_bytes, source_bytes):
    if type(binding) is not dict or not _BINDING_FIELDS <= set(binding):
        return "UNPASSED"
    if any(type(binding[key]) is not str or not binding[key] for key in
           ("producer_process", "producer_command", "runtime_id")):
        return "UNPASSED"
    if any(type(binding[key]) is not str or _SHA.fullmatch(binding[key]) is None
           for key in ("artifact_sha256", "target_source_sha256", "trace_sha256",
                       "payload_sha256", "receipt_sha256", "audit_sha256",
                       "manifest_sha256")):
        return "UNPASSED"
    if not all(type(value) is bytes and value for value in
               (trace_bytes, payload_bytes, receipt_bytes, artifact_bytes,
                source_bytes)):
        return "UNPASSED"
    if any(type(binding[key]) is not expected for key, expected in
           (("expected_calls", list), ("body_step_receipts", list),
            ("accepted_toi_events", dict),
            ("accepted_toi_resets", list), ("reset_start_rotations", dict),
            ("reset_end_rotations", dict),
            ("allowed_evaluations", list), ("pair_inputs", dict))):
        return "UNPASSED"
    if not binding["allowed_evaluations"] or any(
            type(mode) is not str or mode not in _EVALUATIONS
            for mode in binding["allowed_evaluations"]) or len(set(
                binding["allowed_evaluations"])) != len(binding["allowed_evaluations"]):
        return "UNPASSED"
    if binding["operation_source_revision"] != SOURCE_REVISION or any(
            binding[key] != _digest(value) for key, value in
            (("trace_sha256", trace_bytes), ("payload_sha256", payload_bytes),
             ("receipt_sha256", receipt_bytes), ("audit_sha256", _audit_bytes(audit)),
             ("artifact_sha256", artifact_bytes),
             ("target_source_sha256", source_bytes),
             ("manifest_sha256", _manifest_bytes(binding)))):
        return "FAILED_IDENTITY"
    try:
        payload = json.loads(payload_bytes)
        receipt = json.loads(receipt_bytes)
    except (ValueError, UnicodeError):
        return "FAILED_IDENTITY"
    try:
        if _audit_bytes(payload) != _audit_bytes(audit):
            return "FAILED_IDENTITY"
    except (TypeError, ValueError):
        return "FAILED_IDENTITY"
    fields = {"producer_process", "producer_command", "exit_code", "artifact_sha256",
              "target_source_sha256", "runtime_id", "trace_sha256", "payload_sha256",
              "audit_sha256", "manifest_sha256", "operation_source_revision"}
    if type(receipt) is not dict or set(receipt) != fields or \
            type(receipt["exit_code"]) is not int or receipt["exit_code"] != 0 or any(
                receipt[key] != binding[key] for key in fields - {"exit_code"}):
        return "FAILED_IDENTITY"
    return None


def verify_rotation_arithmetic(audit, case, header, states, rotation_cap, *,
                               binding=None, trace_bytes=None, payload_bytes=None,
                               receipt_bytes=None, artifact_bytes=None,
                               source_bytes=None):
    try:
        identity = _verify_binding(audit, binding, trace_bytes, payload_bytes,
                                   receipt_bytes, artifact_bytes, source_bytes)
        if identity:
            return {"status": identity, "reason": "external binding missing or stale"}
        if not _trace_matches(trace_bytes, case, header, states):
            return {"status": "FAILED_IDENTITY", "reason": "trace/header/state mismatch"}
        if type(audit) is not dict or set(audit) != {
                "schema", "case_id", "operation_model_revision", "declared_calls",
                "accepted_toi_resets", "calls"}:
            raise ValueError("audit schema differs")
        if audit["schema"] != "portable-rotation-audit/1" or audit["case_id"] != case["id"] or \
                audit["operation_model_revision"] != SOURCE_REVISION:
            return {"status": "FAILED_IDENTITY", "reason": "audit source or case differs"}
        if type(case["steps"]) is not int or case["steps"] < 1 or \
                type(rotation_cap) is not int or rotation_cap < 0:
            raise ValueError("case or source cap differs")
        bodies = [body["id"] for body in header["setup"]["bodies"]]
        initial = header["initial"]["bodies"]
        if len(bodies) != len(set(bodies)) or len(bodies) != len(initial) or not bodies or \
                any(type(body) is not str or not body for body in bodies):
            raise ValueError("body inventory differs")
        expected_steps = [[step, body] for step in range(1, case["steps"] + 1)
                          for body in bodies]
        if binding["body_step_receipts"] != expected_steps or any(
                type(row) is not list or len(row) != 2 or type(row[0]) is not int or
                type(row[1]) is not str for row in binding["body_step_receipts"]) or \
                any(type(step) is not int for step in states) or \
                set(states) != set(range(1, case["steps"] + 1)):
            return {"status": "FAILED_COVERAGE", "reason": "body-step receipt differs"}
        calls = audit["calls"]
        if type(calls) is not list or type(audit["declared_calls"]) is not int or \
                audit["declared_calls"] != len(calls) or \
                len(binding["expected_calls"]) != len(calls):
            return {"status": "FAILED_COVERAGE", "reason": "call count differs"}
        chain = {body: _state_pair(state["transform"])
                 for body, state in zip(bodies, initial)}
        resets = []
        observed_modes = []
        reset_modes = []
        position = 0
        for step in range(1, case["steps"] + 1):
            counts = dict.fromkeys(bodies, 0)
            while position < len(calls) and calls[position].get("step") == step:
                call = calls[position]
                manifest = binding["expected_calls"][position]
                fields = {"step", "body_id", "kind", "branch"}
                if call.get("kind") == "rotate":
                    fields.add("input_kind")
                actual = {key: call.get(key) for key in manifest}
                if type(call.get("sequence")) is not int or call["sequence"] != position or \
                        type(call.get("step")) is not int or type(manifest) is not dict or \
                        set(manifest) != fields or actual != manifest or \
                        call.get("body_id") not in chain:
                    return {"status": "FAILED_COVERAGE", "reason": "call manifest differs"}
                body = call["body_id"]
                if call.get("pre") != chain[body]:
                    raise ValueError("pre-state chain differs")
                pre, trig = _pair(call["pre"]), _pair(call["trig"])
                _pair(call["post"])
                if call.get("kind") == "rotate":
                    counts[body] += 1
                    if counts[body] > rotation_cap:
                        raise ValueError("source rotation cap exceeded")
                    observed_modes.append(_verify_rotate(
                        call, pre, trig, binding["allowed_evaluations"],
                        binding["pair_inputs"].get(str(position))))
                elif call.get("kind") == "lerp-reset":
                    resets.append([step, body])
                    _verify_reset_provenance(call, binding, states, trace_bytes, bodies)
                    end = binding["reset_end_rotations"].get(str(position))
                    start = binding["reset_start_rotations"].get(str(position))
                    if start is None or end is None:
                        return {"status": "UNPASSED", "reason": "lerp source binding missing"}
                    reset_modes.append(_verify_reset(
                        call, pre, trig, start, end, binding["allowed_evaluations"]))
                else:
                    raise ValueError("unknown source operation")
                chain[body] = call["post"]
                position += 1
            observed = states[step]["bodies"]
            if len(observed) != len(bodies) or [row["id"] for row in observed] != bodies:
                return {"status": "FAILED_COVERAGE", "reason": "state body inventory differs"}
            if any(_state_pair(row["transform"]) != chain[row["id"]] for row in observed):
                raise ValueError("target state outside operation envelope")
        if position != len(calls) or resets != audit["accepted_toi_resets"] or \
                resets != binding["accepted_toi_resets"] or \
                set(binding["reset_end_rotations"]) != {
                    str(i) for i, call in enumerate(calls) if call["kind"] == "lerp-reset"} or \
                set(binding["reset_start_rotations"]) != {
                    str(i) for i, call in enumerate(calls) if call["kind"] == "lerp-reset"} or \
                set(binding["accepted_toi_events"]) != {
                    str(i) for i, call in enumerate(calls) if call["kind"] == "lerp-reset"} or \
                set(binding["pair_inputs"]) != {
                    str(i) for i, call in enumerate(calls) if call["kind"] == "rotate"
                    and call["input_kind"] == "pair"}:
            return {"status": "FAILED_COVERAGE", "reason": "call or reset coverage differs"}
        return {"status": "PASSED_ARITHMETIC", "qualification": "UNPASSED",
                "matching_evaluations": observed_modes,
                "matching_lerp_evaluations": reset_modes}
    except RuntimeError as error:
        return {"status": "UNPASSED", "reason": str(error)}
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        return {"status": "FAILED_ARITHMETIC", "reason": str(error)}


_MARKER_FIELDS = {"schema", "method", "sequence", "target_token", "kind",
                  "source", "branch", "pre", "trig", "raw", "post", "angle_bits",
                  "alpha_bits", "start_angle_bits", "end_angle_bits",
                  "diff_bits", "start", "end", "case_id", "step", "body_id"}


def verify_operation_marker(marker, allowed_evaluations=("strict",)):
    try:
        if type(marker) is not dict or set(marker) != _MARKER_FIELDS or \
                marker["schema"] != "portable-rotation-op/2" or \
                type(marker["method"]) is not str or not marker["method"] or \
                type(marker["sequence"]) is not int or marker["sequence"] < 0 or \
                type(marker["target_token"]) is not int or marker["target_token"] < 0:
            raise ValueError("operation marker identity or shape differs")
        if marker["case_id"] is None:
            if marker["step"] is not None or marker["body_id"] is not None:
                raise ValueError("partial operation case binding")
        elif type(marker["case_id"]) is not str or not marker["case_id"] or \
                type(marker["step"]) is not int or marker["step"] < 1 or \
                (marker["body_id"] is not None and
                 (type(marker["body_id"]) is not str or not marker["body_id"])):
            raise ValueError("operation case binding shape differs")
        if marker["branch"] not in (None, "integrate", "joint", "contact"):
            raise ValueError("operation source branch differs")
        if type(allowed_evaluations) not in (tuple, list) or \
                not allowed_evaluations or any(mode not in _EVALUATIONS
                                                for mode in allowed_evaluations):
            raise ValueError("arithmetic evaluation premise differs")
        pre, trig, post = (_pair(marker[key]) for key in ("pre", "trig", "post"))
        if marker["kind"] == "rotate":
            if marker["source"] not in ("origin", "pivot", "vector-lerp") or \
                    any(marker[key] is not None for key in ("alpha_bits",
                        "start_angle_bits", "end_angle_bits", "diff_bits")) or \
                    marker["start"] != [None, None] or marker["end"] != [None, None]:
                raise ValueError("rotate source marker differs")
            raw = _pair(marker["raw"])
            angle = marker["angle_bits"]
            call = {"sequence": marker["sequence"], "step": 1, "body_id": "b0",
                    "kind": "rotate", "branch": marker["branch"] or "integrate",
                    "pre": marker["pre"],
                    "trig": marker["trig"], "raw": marker["raw"],
                    "post": marker["post"],
                    "clamp": [value < -1.0 or value > 1.0 for value in raw]}
            if angle is None:
                call.update(input_kind="pair", rotation_input=marker["trig"])
                pair = marker["trig"]
            else:
                _binary64(angle)
                call.update(input_kind="angle", angle_bits=angle)
                pair = None
            modes = _verify_rotate(call, pre, trig, allowed_evaluations, pair)
            return {"status": "PASSED_ARITHMETIC" if angle is not None else
                    "UNPASSED_INPUT_ORIGIN", "qualification": "UNPASSED",
                    "matching_evaluations": modes}
        if marker["kind"] != "lerp-reset" or marker["source"] != "direct" or \
                marker["raw"] != [None, None]:
            raise ValueError("unknown operation or reset shape")
        start_pair, end_pair = (_pair(marker[key]) for key in ("start", "end"))
        alpha = _binary64(marker["alpha_bits"])
        start = _binary64(marker["start_angle_bits"])
        end = _binary64(marker["end_angle_bits"])
        if not 0.0 <= alpha <= 1.0 or \
                not _source_angle_matches(start_pair, start) or \
                not _source_angle_matches(end_pair, end):
            raise ValueError("direct reset source angle or alpha differs")
        difference = end - start
        if difference < -_PI:
            difference += _TWO_PI
        if difference > _PI:
            difference -= _TWO_PI
        if marker["diff_bits"] != _bits(difference):
            raise ValueError("direct reset shortest difference differs")
        strict = _bits(difference * alpha + start)
        fused = _bits(_rounded_sum(_signed_product(difference, alpha, False),
                                  (Fraction.from_float(start),
                                   start == 0 and math.copysign(1.0, start) < 0)))
        modes = [mode for mode, result in (("strict", strict), ("fused", fused))
                 if mode in allowed_evaluations and marker["angle_bits"] == result]
        if not modes:
            raise ValueError("direct reset angle arithmetic differs")
        _verify_trig(marker["angle_bits"], trig)
        if marker["post"] != marker["trig"]:
            raise ValueError("direct reset trig result differs")
        return {"status": "PASSED_ARITHMETIC", "qualification": "UNPASSED",
                "matching_evaluations": modes}
    except RuntimeError as error:
        return {"status": "UNPASSED", "reason": str(error)}
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        return {"status": "FAILED_ARITHMETIC", "reason": str(error)}
