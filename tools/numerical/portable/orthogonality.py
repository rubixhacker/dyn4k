import math
import re
import struct
from fractions import Fraction
from functools import lru_cache


_SCALE = 10 ** 100
_U = Fraction(1, 2 ** 53)
_Q = 2 * _U
_GAMMA3 = 3 * _U / (1 - 3 * _U)
_JOINT_CAPS = {"Angle": 7, "Distance": 7, "Friction": 5,
               "Motor": 5, "Pin": 5, "Prismatic": 7,
               "Pulley": 7, "Revolute": 9, "Weld": 11, "Wheel": 9}


def source_rotation_cap(case):
    family = case["family"]
    if family in ("geometry-collision", "ccd"):
        return 5
    if family == "free-motion":
        return 1 if case["id"] == "motion-forces-60" else 5
    if family == "joints-limits-motors":
        return _JOINT_CAPS[case["input"]["jointType"]]
    raise ValueError(f"unknown prospective rotation source: {case['id']}")


def _sqrt_bounds(value):
    numerator = value.numerator * _SCALE * _SCALE
    denominator = value.denominator
    floor = math.isqrt(numerator // denominator)
    lower = Fraction(floor, _SCALE)
    upper = lower if floor * floor * denominator == numerator else Fraction(floor + 1, _SCALE)
    return lower, upper


def _ceil_fraction(value):
    return -(-value.numerator // value.denominator)


@lru_cache(maxsize=1)
def _limits():
    sqrt2_upper = _sqrt_bounds(Fraction(2))[1]
    delta_upper = 4 * sqrt2_upper * _U + 8 * _U * _U
    a_upper = _sqrt_bounds(1 + delta_upper)[1] * (1 + sqrt2_upper * _GAMMA3)
    b_lower = _sqrt_bounds(1 - delta_upper)[0] * (1 - sqrt2_upper * _GAMMA3)
    a_scaled = _ceil_fraction(a_upper * _SCALE)
    b_scaled = b_lower.numerator * _SCALE // b_lower.denominator
    upper_power = lower_power = _SCALE
    limits = []
    for _ in range(6601):
        positive = (1 + _GAMMA3) * Fraction(upper_power, _SCALE) - 1
        negative = 1 - (1 - _GAMMA3) * Fraction(lower_power, _SCALE)
        limits.append(_ceil_fraction(max(positive, negative) / _Q))
        upper_power = (upper_power * a_scaled * a_scaled + _SCALE ** 2 - 1) // _SCALE ** 2
        lower_power = lower_power * b_scaled * b_scaled // _SCALE ** 2
    return tuple(limits)


def orthogonality_ulps(rotations):
    if type(rotations) is not int or rotations < 0 or rotations > 6600:
        raise ValueError("rotation cap is outside the approved domain")
    return _limits()[rotations]


@lru_cache(maxsize=1)
def direct_reset_ulps():
    delta_upper = 4 * _sqrt_bounds(Fraction(2))[1] * _U + 8 * _U * _U
    positive = (1 + _GAMMA3) * (1 + delta_upper) - 1
    negative = 1 - (1 - _GAMMA3) * (1 - delta_upper)
    return _ceil_fraction(max(positive, negative) / _Q)


def _binary64(bits):
    if type(bits) is not str or re.fullmatch(r"[0-9a-f]{16}", bits) is None:
        raise ValueError("rotation audit has invalid binary64 bits")
    value = struct.unpack(">d", bytes.fromhex(bits))[0]
    if not math.isfinite(value):
        raise ValueError("rotation audit has a nonfinite value")
    return value


def _pair(bits):
    if not isinstance(bits, list) or len(bits) != 2:
        raise ValueError("rotation audit pair is incomplete")
    return tuple(_binary64(value) for value in bits)


def _state_pair(transform):
    values = tuple(transform[key] for key in ("getCost", "getSint"))
    if any(type(value) not in (int, float) for value in values):
        raise ValueError("rotation audit state has an invalid number")
    values = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("rotation audit state is nonfinite")
    return tuple(struct.pack(">d", value).hex() for value in values)


def _bits(value):
    return struct.pack(">d", value).hex()


def _source_angle(pair):
    c, s = pair
    if not -1.0 <= c <= 1.0:
        raise ValueError("rotation audit source angle cosine differs")
    acos = math.acos(c)
    return acos if s >= 0.0 else -acos


def _source_angle_agrees(recorded_bits, pair):
    recorded = _binary64(recorded_bits)
    expected = _source_angle(pair)
    if expected == 0.0:
        return recorded_bits == _bits(expected)
    return abs(recorded - expected) <= 8 * math.ulp(max(abs(recorded),
                                                         abs(expected), 1.0))


def _trig_agrees(angle, trig):
    if angle == 0.0:
        return _bits(trig[0]) == _bits(1.0) and _bits(trig[1]) == _bits(angle)
    return all(abs(observed - expected) <= 16 * math.ulp(1.0)
               for observed, expected in zip(trig, (math.cos(angle), math.sin(angle))))


def _validate_rotate(call, pre, trig, post):
    required = {"sequence", "step", "body_id", "kind", "branch", "input_kind",
                "pre", "trig", "raw", "post", "clamp"}
    if call.get("input_kind") == "angle":
        required.add("angle_bits")
    elif call.get("input_kind") == "pair":
        required.add("rotation_input")
    if set(call) != required or call["branch"] not in ("integrate", "joint", "contact"):
        raise ValueError("rotation audit source branch differs")
    if call["input_kind"] == "angle":
        if not _trig_agrees(_binary64(call["angle_bits"]), trig):
            raise ValueError("rotation audit angle and trig pair differ")
    elif call["rotation_input"] != call["trig"]:
        raise ValueError("rotation audit pair input differs")
    if abs(trig[0] * trig[0] + trig[1] * trig[1] - 1.0) > direct_reset_ulps() * float(_Q):
        raise ValueError("rotation audit trig-pair norm differs")
    raw = _pair(call["raw"])
    clamp = call["clamp"]
    if not isinstance(clamp, list) or len(clamp) != 2 or any(type(x) is not bool for x in clamp):
        raise ValueError("rotation audit clamp markers differ")
    for index in (0, 1):
        a = Fraction.from_float(pre[index if index == 0 else 1]) * Fraction.from_float(trig[0])
        b = (Fraction.from_float(pre[1 if index == 0 else 0]) *
             Fraction.from_float(trig[1]))
        if any(0 < abs(term) < Fraction(1, 2 ** 1022) for term in (a, b)):
            raise ValueError("rotation audit subnormal product premise is unproved")
        ideal = a - b if index == 0 else a + b
        if 0 < abs(ideal) < Fraction(1, 2 ** 1022):
            raise ValueError("rotation audit subnormal sum premise is unproved")
        observed = Fraction.from_float(raw[index])
        if abs(observed - ideal) > _GAMMA3 * (abs(a) + abs(b)):
            raise ValueError("rotation audit orientation rounding differs")
        first = (pre[0] * trig[0] if index == 0 else pre[1] * trig[0])
        second = (pre[1] * trig[1] if index == 0 else pre[0] * trig[1])
        source_raw = first - second if index == 0 else first + second
        if (source_raw == 0.0 or raw[index] == 0.0) and \
                call["raw"][index] != _bits(source_raw):
            raise ValueError("rotation audit signed zero raw differs")
        was_clamped = raw[index] < -1.0 or raw[index] > 1.0
        expected_bits = (_bits(-1.0) if raw[index] < -1.0 else
                         _bits(1.0) if raw[index] > 1.0 else call["raw"][index])
        if clamp[index] is not was_clamped or call["post"][index] != expected_bits:
            raise ValueError("rotation audit clamp result differs")


def _validate_reset(call, trig, post):
    if set(call) != {"sequence", "step", "body_id", "kind", "branch", "pre", "trig",
                     "post", "alpha_bits", "start_angle_bits", "end_angle_bits",
                     "diff_bits", "angle_bits", "end_rotation"} or call["branch"] != "toi":
        raise ValueError("rotation audit direct reset branch differs")
    alpha = _binary64(call["alpha_bits"])
    start = _binary64(call["start_angle_bits"])
    end = _binary64(call["end_angle_bits"])
    _binary64(call["diff_bits"])
    angle = _binary64(call["angle_bits"])
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("rotation audit lerp alpha differs")
    if not _source_angle_agrees(call["start_angle_bits"], _pair(call["pre"])) or \
            not _source_angle_agrees(call["end_angle_bits"], _pair(call["end_rotation"])):
        raise ValueError("rotation audit lerp source angle differs")
    diff = end - start
    if diff < -math.pi:
        diff += 2.0 * math.pi
    if diff > math.pi:
        diff -= 2.0 * math.pi
    if call["diff_bits"] != _bits(diff) or \
            call["angle_bits"] != _bits(diff * alpha + start):
        raise ValueError("rotation audit lerp angle arithmetic differs")
    if not _trig_agrees(angle, trig):
        raise ValueError("rotation audit lerp angle and trig pair differ")
    if call["post"] != call["trig"]:
        raise ValueError("rotation audit direct trig reset differs")
    if abs(post[0] * post[0] + post[1] * post[1] - 1.0) > direct_reset_ulps() * float(_Q):
        raise ValueError("rotation audit direct trig norm differs")


def validate_rotation_audit(audit, case, header, states, rotation_cap):
    if not isinstance(audit, dict) or set(audit) != {
            "schema", "case_id", "operation_model_revision", "declared_calls",
            "accepted_toi_resets", "calls"} or \
            audit["schema"] != "portable-rotation-audit/2" or \
            audit["case_id"] != case["id"] or \
            audit["operation_model_revision"] != "058bf6d982a0fb89b54050f929f6ea9dae53b714" or \
            type(audit["declared_calls"]) is not int or \
            not isinstance(audit["calls"], list) or \
            any(not isinstance(call, dict) for call in audit["calls"]) or \
            audit["declared_calls"] != len(audit["calls"]):
        raise ValueError("rotation audit identity or call count differs")
    initial = header["initial"]["bodies"]
    body_ids = [body["id"] for body in header["setup"]["bodies"]]
    if len(body_ids) != len(initial) or len(body_ids) != len(set(body_ids)):
        raise ValueError("rotation audit body inventory differs")
    accepted = audit["accepted_toi_resets"]
    if not isinstance(accepted, list) or any(
            not isinstance(item, list) or len(item) != 2 or
            type(item[0]) is not int or item[0] < 1 or item[0] > case["steps"] or
            item[1] not in body_ids for item in accepted):
        raise ValueError("rotation audit TOI branch declaration differs")
    chain = {body_id: _state_pair(body["transform"])
             for body_id, body in zip(body_ids, initial)}
    calls = audit["calls"]
    position = 0
    resets = []
    for step in range(1, case["steps"] + 1):
        counts = {body_id: 0 for body_id in body_ids}
        while position < len(calls) and calls[position].get("step") == step:
            call = calls[position]
            if type(call.get("sequence")) is not int or call["sequence"] != position or \
                    type(call.get("step")) is not int or \
                    call.get("body_id") not in chain or call.get("pre") != list(chain[call["body_id"]]):
                raise ValueError("rotation audit call sequence or input differs")
            pre = _pair(call["pre"])
            trig = _pair(call["trig"])
            post = _pair(call["post"])
            if call.get("kind") == "rotate":
                counts[call["body_id"]] += 1
                if counts[call["body_id"]] > rotation_cap:
                    raise ValueError("rotation audit source cap exceeded")
                _validate_rotate(call, pre, trig, post)
            elif call.get("kind") == "lerp-reset":
                resets.append([step, call["body_id"]])
                _validate_reset(call, trig, post)
            else:
                raise ValueError("rotation audit operation differs")
            chain[call["body_id"]] = tuple(call["post"])
            position += 1
        if step not in states or {body["id"] for body in states[step]["bodies"]} != set(body_ids):
            raise ValueError("rotation audit state inventory differs")
        for body in states[step]["bodies"]:
            if _state_pair(body["transform"]) != chain[body["id"]]:
                raise ValueError("rotation audit state chain differs")
    if position != len(calls) or resets != accepted:
        raise ValueError("rotation audit call or TOI reset coverage differs")
