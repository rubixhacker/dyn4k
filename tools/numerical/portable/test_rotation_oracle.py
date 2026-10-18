import copy
import ctypes
import ctypes.util
import hashlib
import json
import math
import struct
import unittest
from decimal import Decimal, localcontext
from fractions import Fraction

from rotation_oracle import trig_interval, verify_rotation_arithmetic


def bits(value):
    return struct.pack(">d", value).hex()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def audit_digest(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def receipt_for(binding):
    keys = ("producer_process", "producer_command", "artifact_sha256",
            "target_source_sha256", "runtime_id", "trace_sha256",
            "payload_sha256", "audit_sha256", "manifest_sha256",
            "operation_source_revision")
    receipt = {key: binding[key] for key in keys}
    receipt["exit_code"] = 0
    return json.dumps(receipt, sort_keys=True).encode()


def trace_for(case, header, states):
    rows = [{"kind": "inputs", "id": case["id"], "steps": case["steps"],
             **header}]
    rows += case.get("trace_events", [])
    rows += [{"kind": "state", "id": case["id"], "step": step,
              "state": states[step]} for step in range(1, case["steps"] + 1)]
    rows.append({"kind": "case-end", "id": case["id"], "steps": case["steps"]})
    return b"".join(json.dumps(row).encode() + b"\n" for row in rows)


def manifest_digest(binding):
    fields = ("expected_calls", "body_step_receipts", "accepted_toi_resets",
              "accepted_toi_events",
              "reset_start_rotations", "reset_end_rotations", "pair_inputs",
              "allowed_evaluations")
    return audit_digest({key: binding[key] for key in fields})


class RotationOracleTest(unittest.TestCase):
    def fixture(self):
        one = [bits(1.0), bits(0.0)]
        call = {"sequence": 0, "step": 1, "body_id": "b0", "kind": "rotate",
                "branch": "integrate", "input_kind": "angle", "angle_bits": bits(0.0),
                "pre": one[:], "trig": one[:], "raw": one[:], "post": one[:],
                "clamp": [False, False]}
        audit = {"schema": "portable-rotation-audit/1", "case_id": "one",
                 "operation_model_revision": "058bf6d982a0fb89b54050f929f6ea9dae53b714",
                 "declared_calls": 1, "accepted_toi_resets": [], "calls": [call]}
        transform = {"getCost": 1.0, "getSint": 0.0}
        case = {"id": "one", "steps": 1}
        header = {"setup": {"bodies": [{"id": "b0"}]},
                  "initial": {"bodies": [{"transform": transform}]}}
        states = {1: {"bodies": [{"id": "b0", "transform": transform}]}}
        trace = trace_for(case, header, states)
        payload = json.dumps(audit).encode()
        artifact = b"artifact"
        source = b"source"
        binding = {"producer_process": "pid:41 exit:0", "producer_command": "target-test",
                   "artifact_sha256": digest(artifact), "runtime_id": "jvm:test",
                   "target_source_sha256": digest(source),
                   "operation_source_revision": audit["operation_model_revision"],
                   "trace_sha256": digest(trace), "payload_sha256": digest(payload),
                   "audit_sha256": audit_digest(audit),
                   "expected_calls": [{"step": 1, "body_id": "b0", "kind": "rotate",
                                       "branch": "integrate", "input_kind": "angle"}],
                   "body_step_receipts": [[1, "b0"]], "accepted_toi_resets": [],
                   "accepted_toi_events": {},
                   "reset_start_rotations": {}, "reset_end_rotations": {},
                   "pair_inputs": {},
                   "allowed_evaluations": ["strict"]}
        binding["manifest_sha256"] = manifest_digest(binding)
        receipt = receipt_for(binding)
        binding["receipt_sha256"] = digest(receipt)
        return audit, case, header, states, binding, trace, payload, receipt, artifact, source

    def verify(self, data, *, refresh_hash=True):
        audit, case, header, states, binding, trace, payload, receipt, artifact, source = data
        if refresh_hash:
            binding["audit_sha256"] = audit_digest(audit)
            payload = json.dumps(audit).encode()
            binding["payload_sha256"] = digest(payload)
            binding["manifest_sha256"] = manifest_digest(binding)
            trace = trace_for(case, header, states)
            binding["trace_sha256"] = digest(trace)
            receipt = receipt_for(binding)
            binding["receipt_sha256"] = digest(receipt)
        return verify_rotation_arithmetic(audit, case, header, states, 5,
                                          binding=binding, trace_bytes=trace,
                                          payload_bytes=payload, receipt_bytes=receipt,
                                          artifact_bytes=artifact, source_bytes=source)

    def test_missing_external_binding_is_unpassed_then_exact_zero_passes(self):
        data = self.fixture()
        self.assertEqual(verify_rotation_arithmetic(*data[:4], 5)["status"], "UNPASSED")
        self.assertEqual(self.verify(data)["status"], "PASSED_ARITHMETIC")

    def test_manifest_and_identity_must_be_external_and_complete(self):
        for field in ("producer_process", "producer_command", "artifact_sha256",
                      "runtime_id", "target_source_sha256", "trace_sha256",
                      "payload_sha256", "receipt_sha256", "expected_calls",
                      "body_step_receipts", "allowed_evaluations"):
            data = self.fixture()
            data[4].pop(field)
            with self.subTest(field=field):
                self.assertEqual(self.verify(data, refresh_hash=False)["status"], "UNPASSED")
        data = self.fixture()
        data[4]["expected_calls"] = []
        self.assertEqual(self.verify(data)["status"], "FAILED_COVERAGE")
        data = self.fixture()
        data[4]["body_step_receipts"] = []
        self.assertEqual(self.verify(data)["status"], "FAILED_COVERAGE")
        data = self.fixture()
        data[4]["body_step_receipts"] *= 2
        self.assertEqual(self.verify(data)["status"], "FAILED_COVERAGE")
        data = self.fixture()
        data[0]["calls"][0]["sequence"] = 1
        self.assertEqual(self.verify(data)["status"], "FAILED_COVERAGE")
        data = self.fixture()
        data[0]["calls"] = []
        data[0]["declared_calls"] = 0
        self.assertEqual(self.verify(data)["status"], "FAILED_COVERAGE")
        data = self.fixture()
        data[0]["calls"][0]["angle_bits"] = bits(1.0)
        self.assertEqual(self.verify(data, refresh_hash=False)["status"], "FAILED_IDENTITY")
        for slot in (5, 6, 7, 8, 9):
            data = list(self.fixture())
            data[slot] += b"stale"
            with self.subTest(stale_byte_slot=slot):
                self.assertEqual(self.verify(data, refresh_hash=False)["status"],
                                 "FAILED_IDENTITY")
        changed = list(self.fixture())
        changed[6] = b'{"schema":"different"}'
        changed[4]["payload_sha256"] = digest(changed[6])
        changed[7] = receipt_for(changed[4])
        changed[4]["receipt_sha256"] = digest(changed[7])
        self.assertEqual(self.verify(changed, refresh_hash=False)["status"],
                         "FAILED_IDENTITY")
        data = self.fixture()
        data[3][1]["bodies"][0]["transform"]["getCost"] = math.nextafter(1.0, 0.0)
        self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")

    def test_angle_and_trig_are_bounded_independently(self):
        data = self.fixture()
        data[0]["calls"][0]["angle_bits"] = bits(math.pi / 2)
        self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")
        data = self.fixture()
        data[0]["calls"][0]["trig"][0] = bits(1.0 - math.ulp(1.0))
        self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")
        for angle in (0.0, -0.0, 1e-300, 0.75, -0.75, 1e300):
            with self.subTest(angle=angle):
                c, s = trig_interval(bits(angle))
                self.assertLessEqual(c[0], c[1])
                self.assertLessEqual(s[0], s[1])
                if angle == 0.0 and math.copysign(1, angle) < 0:
                    self.assertEqual(bits(s[0]), bits(-0.0))
        data = self.fixture()
        call = data[0]["calls"][0]
        call["angle_bits"] = bits(1e300)
        intervals = trig_interval(call["angle_bits"])
        call["trig"] = [bits(intervals[0][0]), bits(intervals[1][0])]
        call["raw"] = call["trig"][:]
        call["post"] = call["trig"][:]
        data[3][1]["bodies"][0]["transform"] = {
            "getCost": intervals[0][0], "getSint": intervals[1][0]}
        self.assertEqual(self.verify(data)["status"], "PASSED_ARITHMETIC")
        call["trig"][0] = bits(math.nextafter(intervals[0][0], -math.inf))
        self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")

    def test_signed_zero_subnormal_and_one_ulp_mutation(self):
        data = self.fixture()
        data[0]["calls"][0]["raw"][1] = bits(-0.0)
        data[0]["calls"][0]["post"][1] = bits(-0.0)
        data[3][1]["bodies"][0]["transform"]["getSint"] = -0.0
        self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")
        data = self.fixture()
        data[0]["calls"][0]["angle_bits"] = bits(math.ulp(0.0))
        data[0]["calls"][0]["trig"][1] = bits(math.ulp(0.0))
        data[0]["calls"][0]["raw"][1] = bits(math.ulp(0.0))
        data[0]["calls"][0]["post"][1] = bits(math.ulp(0.0))
        data[3][1]["bodies"][0]["transform"] = {"getCost": 1.0, "getSint": math.ulp(0.0)}
        self.assertEqual(self.verify(data)["status"], "PASSED_ARITHMETIC")
        data[0]["calls"][0]["raw"][1] = bits(2 * math.ulp(0.0))
        self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")
        data = self.fixture()
        data[0]["calls"][0]["angle_bits"] = bits(-0.0)
        data[0]["calls"][0]["trig"][1] = bits(-0.0)
        self.assertEqual(self.verify(data)["status"], "PASSED_ARITHMETIC")

    def test_subnormal_angle_rejects_wrong_sign_zero_both_ways(self):
        for angle, wrong_zero in ((math.ulp(0.0), -0.0),
                                  (-math.ulp(0.0), 0.0)):
            data = self.fixture()
            call = data[0]["calls"][0]
            call["angle_bits"] = bits(angle)
            call["trig"][1] = bits(wrong_zero)
            with self.subTest(angle_bits=call["angle_bits"]):
                self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")

    def test_approved_absolute_two_u_trig_boundary(self):
        data = self.fixture()
        call = data[0]["calls"][0]
        call["angle_bits"] = bits(0.75)
        cosine, sine = trig_interval(call["angle_bits"])
        permitted = sine[0] + 2.0 ** -52
        call["trig"] = [bits(cosine[0]), bits(permitted)]
        call["raw"] = call["trig"][:]
        call["post"] = call["trig"][:]
        data[3][1]["bodies"][0]["transform"] = {
            "getCost": cosine[0], "getSint": permitted}
        self.assertEqual(self.verify(data)["status"], "PASSED_ARITHMETIC")
        rejected = math.nextafter(permitted, math.inf)
        call["trig"][1] = bits(rejected)
        call["raw"][1] = bits(rejected)
        call["post"][1] = bits(rejected)
        data[3][1]["bodies"][0]["transform"]["getSint"] = rejected
        self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")

    def test_exact_tie_and_clamp_from_pair_rotation(self):
        data = self.fixture()
        audit, _, header, states, binding, *_ = data
        call = audit["calls"][0]
        small = 2.0 ** -27
        lower = Fraction.from_float(math.nextafter(1.0, 0.0))
        self.assertEqual(2 * (Fraction(1) - Fraction(1, 2 ** 54)), lower + 1)
        call["input_kind"] = "pair"
        call.pop("angle_bits")
        call["rotation_input"] = [bits(1.0), bits(small)]
        call["trig"] = call["rotation_input"][:]
        call["pre"] = [bits(1.0), bits(small)]
        call["raw"] = [bits(1.0), bits(2 * small)]
        call["post"] = call["raw"][:]
        header["initial"]["bodies"][0]["transform"] = {"getCost": 1.0,
                                                        "getSint": small}
        states[1]["bodies"][0]["transform"] = {"getCost": 1.0,
                                                "getSint": 2 * small}
        binding["expected_calls"][0]["input_kind"] = "pair"
        binding["pair_inputs"] = {"0": call["rotation_input"][:]}
        self.assertEqual(self.verify(data)["status"], "PASSED_ARITHMETIC")
        call["raw"][0] = bits(math.nextafter(1.0, 0.0))
        self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")

        data = self.fixture()
        audit, _, header, states, binding, *_ = data
        call = audit["calls"][0]
        small = 2.0 ** -26
        call["input_kind"] = "pair"
        call.pop("angle_bits")
        call["rotation_input"] = [bits(1.0), bits(-small)]
        call["trig"] = call["rotation_input"][:]
        call["pre"] = [bits(1.0), bits(small)]
        call["raw"] = [bits(1.0 + 2.0 ** -52), bits(0.0)]
        call["post"] = [bits(1.0), bits(0.0)]
        call["clamp"] = [True, False]
        header["initial"]["bodies"][0]["transform"] = {"getCost": 1.0,
                                                        "getSint": small}
        binding["expected_calls"][0]["input_kind"] = "pair"
        binding["pair_inputs"] = {"0": call["rotation_input"][:]}
        self.assertEqual(self.verify(data)["status"], "PASSED_ARITHMETIC")
        call["clamp"][0] = False
        self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")

    def test_fma_and_forced_reassociation_need_declared_mode(self):
        data = self.fixture()
        audit, _, header, states, binding, *_ = data
        call = audit["calls"][0]
        pre = [float.fromhex("-0x1.0cd683f9d3feap-2"),
               float.fromhex("0x1.ee0a3e97da062p-1")]
        trig = [float.fromhex("-0x1.36b190dd3c693p-1"),
                float.fromhex("0x1.96f4d3d0bd5bep-1")]
        call["angle_bits"] = bits(float.fromhex("0x1.1c867da8b78fcp+1"))
        call["pre"] = [bits(value) for value in pre]
        call["trig"] = [bits(value) for value in trig]
        call["raw"] = ["bfe371ccdd630997", "bfe96a2de45f0e24"]
        library = ctypes.CDLL(ctypes.util.find_library("m"))
        library.fma.argtypes = [ctypes.c_double] * 3
        library.fma.restype = ctypes.c_double
        self.assertEqual(bits(library.fma(trig[0], pre[0], -(trig[1] * pre[1]))),
                         call["raw"][0])
        with localcontext() as context:
            context.prec = 200
            combined = (Decimal.from_float(trig[0]) * Decimal.from_float(pre[0]) -
                        Decimal.from_float(trig[1]) * Decimal.from_float(pre[1]))
            self.assertEqual(bits(float(combined)), call["raw"][0])
        call["post"] = call["raw"][:]
        header["initial"]["bodies"][0]["transform"] = dict(zip(
            ("getCost", "getSint"), pre))
        states[1]["bodies"][0]["transform"] = dict(zip(
            ("getCost", "getSint"), (struct.unpack(">d", bytes.fromhex(x))[0]
                                       for x in call["post"])))
        self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")
        binding["allowed_evaluations"] = ["fused"]
        result = self.verify(data)
        self.assertEqual(result["status"], "PASSED_ARITHMETIC", result)
        self.assertIn("fused", result["matching_evaluations"][0][0])
        call["raw"][0] = "bfe371ccdd630998"
        self.assertEqual(self.verify(data)["status"], "FAILED_ARITHMETIC")

    def test_lerp_source_relations_and_reset_manifest(self):
        data = self.fixture()
        audit, case, _, states, binding, *_ = data
        one = [bits(1.0), bits(0.0)]
        states[1]["bodies"][0]["previousTransform"] = {
            "getCost": 1.0, "getSint": 0.0}
        case["trace_events"] = [{"kind": "event", "id": "one", "step": 1,
                                 "order": 0, "name": "toi.payload.bodies",
                                 "payload": {"bodies": [0, 0], "time": 0.5,
                                             "distance": 0.0}}]
        audit["calls"][0] = {"sequence": 0, "step": 1, "body_id": "b0",
                             "kind": "lerp-reset", "branch": "toi", "pre": one,
                             "trig": one, "post": one, "alpha_bits": bits(0.5),
                             "start_angle_bits": bits(0.0), "end_angle_bits": bits(0.0),
                             "diff_bits": bits(0.0), "angle_bits": bits(0.0)}
        audit["accepted_toi_resets"] = [[1, "b0"]]
        binding["expected_calls"] = [{"step": 1, "body_id": "b0", "kind": "lerp-reset",
                                      "branch": "toi"}]
        binding["accepted_toi_resets"] = [[1, "b0"]]
        binding["accepted_toi_events"] = {"0": {"step": 1, "order": 0,
                                                "body_id": "b0",
                                                "accepted": True,
                                                "alpha_bits": bits(0.5)}}
        binding["reset_start_rotations"] = {"0": one}
        binding["reset_end_rotations"] = {"0": one}
        self.assertEqual(self.verify(data)["status"], "PASSED_ARITHMETIC")
        acos_case = copy.deepcopy(data)
        acos_case[4]["reset_start_rotations"] = {"0": [bits(0.0), bits(1.0)]}
        acos_case[3][1]["bodies"][0]["previousTransform"] = {
            "getCost": 0.0, "getSint": 1.0}
        acos_case[1]["trace_events"][0]["payload"]["time"] = 1.0
        acos_case[4]["accepted_toi_events"]["0"]["alpha_bits"] = bits(1.0)
        acos_case[0]["calls"][0]["alpha_bits"] = bits(1.0)
        for angle, status in ((math.pi / 2, "PASSED_ARITHMETIC"),
                              (math.nextafter(math.pi / 2, math.inf),
                               "PASSED_ARITHMETIC"),
                              (math.nextafter(math.nextafter(math.pi / 2, math.inf),
                                              math.inf), "FAILED_ARITHMETIC")):
            acos_case[0]["calls"][0]["start_angle_bits"] = bits(angle)
            acos_case[0]["calls"][0]["diff_bits"] = bits(-angle)
            with self.subTest(acos_angle_bits=bits(angle)):
                self.assertEqual(self.verify(acos_case)["status"], status)
        changed = copy.deepcopy(data)
        changed[4]["allowed_evaluations"] = ["fma_left"]
        self.assertEqual(self.verify(changed)["status"], "FAILED_ARITHMETIC")
        changed = copy.deepcopy(data)
        changed[4]["reset_start_rotations"] = {"0": [bits(-1.0), bits(0.0)]}
        changed[0]["calls"][0].update(alpha_bits=bits(1.0),
                                       start_angle_bits=bits(math.pi),
                                       diff_bits=bits(-math.pi))
        changed[4]["accepted_toi_events"]["0"]["alpha_bits"] = bits(1.0)
        changed[1]["trace_events"][0]["payload"]["time"] = 1.0
        self.assertEqual(self.verify(changed)["status"], "FAILED_ARITHMETIC")
        changed[3][1]["bodies"][0]["previousTransform"] = {
            "getCost": -1.0, "getSint": 0.0}
        self.assertEqual(self.verify(changed)["status"], "PASSED_ARITHMETIC")
        wrong_time = copy.deepcopy(data)
        wrong_time[1]["trace_events"][0]["payload"]["time"] = 0.75
        wrong_time[4]["accepted_toi_events"]["0"]["alpha_bits"] = bits(0.75)
        wrong_time[0]["calls"][0]["alpha_bits"] = bits(0.25)
        self.assertEqual(self.verify(wrong_time)["status"], "FAILED_ARITHMETIC")
        missing_previous = copy.deepcopy(data)
        missing_previous[3][1]["bodies"][0].pop("previousTransform")
        self.assertEqual(self.verify(missing_previous)["status"], "UNPASSED")
        missing_event = copy.deepcopy(data)
        missing_event[4]["accepted_toi_events"].clear()
        self.assertEqual(self.verify(missing_event)["status"], "UNPASSED")
        missing_time = copy.deepcopy(data)
        missing_time[1]["trace_events"].clear()
        self.assertEqual(self.verify(missing_time)["status"], "UNPASSED")
        wrapped = copy.deepcopy(data)
        before = [bits(-1.0), bits(-math.ulp(0.0))]
        start_pair = [bits(-1.0), bits(math.ulp(0.0))]
        sine = trig_interval(bits(math.pi))[1][0]
        wrapped[0]["calls"][0].update(
            pre=before, alpha_bits=bits(1.0), start_angle_bits=bits(math.pi),
            end_angle_bits=bits(-math.pi), diff_bits=bits(0.0),
            angle_bits=bits(math.pi), trig=[bits(-1.0), bits(sine)],
            post=[bits(-1.0), bits(sine)])
        wrapped[2]["initial"]["bodies"][0]["transform"] = {
            "getCost": -1.0, "getSint": -math.ulp(0.0)}
        wrapped[3][1]["bodies"][0]["transform"] = {
            "getCost": -1.0, "getSint": sine}
        wrapped[4]["reset_start_rotations"] = {"0": start_pair}
        wrapped[4]["reset_end_rotations"] = {"0": before}
        wrapped[4]["accepted_toi_events"]["0"]["alpha_bits"] = bits(1.0)
        wrapped[1]["trace_events"][0]["payload"]["time"] = 1.0
        wrapped[3][1]["bodies"][0]["previousTransform"] = {
            "getCost": -1.0, "getSint": math.ulp(0.0)}
        self.assertEqual(self.verify(wrapped)["status"], "PASSED_ARITHMETIC")
        for field, value in (("alpha_bits", bits(2.0)), ("diff_bits", bits(1.0)),
                             ("angle_bits", bits(1.0)), ("end_angle_bits", bits(1.0))):
            changed = copy.deepcopy(data)
            changed[0]["calls"][0][field] = value
            with self.subTest(field=field):
                self.assertEqual(self.verify(changed)["status"], "FAILED_ARITHMETIC")
        changed = copy.deepcopy(data)
        changed[0]["accepted_toi_resets"] = []
        self.assertEqual(self.verify(changed)["status"], "FAILED_COVERAGE")

    def test_interval_encloses_independent_rational_taylor(self):
        x = Fraction(3, 4)
        term = x
        sine = x
        for k in range(1, 80):
            term *= -x * x / ((2 * k) * (2 * k + 1))
            sine += term
        tail = abs(term * x * x / (160 * 161))
        lo, hi = trig_interval(bits(0.75))[1]
        self.assertLessEqual(Fraction.from_float(lo), sine - tail)
        self.assertGreaterEqual(Fraction.from_float(hi), sine + tail)
        allowed = Fraction.from_float(lo + 2.0 ** -52)
        rejected = Fraction.from_float(math.nextafter(float(allowed), math.inf))
        self.assertLessEqual(allowed - (sine - tail), Fraction(1, 2 ** 52))
        self.assertGreater(rejected - (sine + tail), Fraction(1, 2 ** 52))


if __name__ == "__main__":
    unittest.main()
