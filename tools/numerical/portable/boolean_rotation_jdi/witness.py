import re
from pathlib import Path


CASE = "joint-Revolute-LimitsEnabled-false"
SCHEMA = "boolean-rotation-jdi/1"
INTEGRATE = "org.dyn4j.dynamics.AbstractPhysicsBody.integratePosition$lambda$0"
POINT = "org.dyn4j.dynamics.joint.RevoluteJoint.solvePositionConstraints"
HEX64 = re.compile(r"[0-9a-f]{16}\Z")


def _result(status, calls_checked=0):
    return {"status": status, "qualification": "UNPASSED",
            "calls_checked": calls_checked}


def _bits(value):
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _pair(value):
    return isinstance(value, list) and len(value) == 2 and all(_bits(x) for x in value)


def read_probe_events(output, expected_count):
    output = Path(output)
    complete = (output / "complete.txt").read_text().splitlines()
    if (len(complete) != 3 or complete[0] != "vm-death" or
            int(complete[2]) != expected_count or expected_count <= 0):
        raise ValueError("Incomplete JDI observation")
    calls = []
    for line in (output / "events.tsv").read_text().splitlines():
        fields = line.split("\t")
        if len(fields) != 12:
            raise ValueError("Malformed JDI event")
        ordinal, thread, receiver = (int(value) for value in fields[:3])
        caller_index = int(fields[11])
        values = fields[3:10]
        if (ordinal != len(calls) or thread <= 0 or receiver <= 0 or
                caller_index < 0 or not all(_bits(value) for value in values)):
            raise ValueError("Changed JDI event sequence")
        calls.append({"ordinal": ordinal, "thread": thread, "receiver": receiver,
                      "method": "rotatePivotObserved", "pre": fields[3:5],
                      "trig": fields[5:7], "post": fields[7:9],
                      "angle_bits": fields[9], "caller": fields[10],
                      "caller_code_index": caller_index})
    if len(calls) != expected_count:
        raise ValueError("Incomplete JDI event inventory")
    return calls


def verify_stream(witness, expected):
    if not isinstance(witness, dict) or witness.get("schema") != SCHEMA:
        return _result("FAILED_SCHEMA")
    if not isinstance(expected, dict):
        return _result("FAILED_IDENTITY")
    for field in ("pid", "case_id", "source_sha256", "jar_sha256",
                  "loaded_code_sha256", "marker_sha256"):
        if witness.get(field) != expected.get(field):
            return _result("FAILED_IDENTITY")
    if witness.get("case_id") != CASE or type(witness.get("pid")) is not int or witness["pid"] <= 0:
        return _result("FAILED_IDENTITY")
    for field in ("source_sha256", "jar_sha256", "loaded_code_sha256", "marker_sha256"):
        value = witness.get(field)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            return _result("FAILED_IDENTITY")
    calls, markers = witness.get("calls"), expected.get("markers")
    if not isinstance(calls, list) or not isinstance(markers, list) or len(calls) != 1800 or len(markers) != 1800:
        return _result("FAILED_COVERAGE")
    sites = expected.get("caller_code_indices")
    if (not isinstance(sites, list) or len(sites) != 3 or
            any(type(site) is not int or site < 0 for site in sites) or
            len(set(sites)) != 3):
        return _result("UNPASSED_SOURCE_CALL_SITE")
    if len(calls) != len(markers):
        return _result("FAILED_COVERAGE")
    body_receivers = {}
    threads = set()
    for index, (call, marker) in enumerate(zip(calls, markers)):
        if not isinstance(call, dict) or not isinstance(marker, dict):
            return _result("FAILED_COVERAGE", index)
        body, branch, caller = (
            ("b1", "integrate", INTEGRATE),
            ("b0", None, POINT),
            ("b1", None, POINT),
        )[index % 3]
        if (type(call.get("ordinal")) is not int or call["ordinal"] != index or
                type(marker.get("step")) is not int or marker["step"] != index // 3 + 1 or
                marker.get("body_id") != body or marker.get("branch") != branch or
                marker.get("kind") != "rotate"):
            return _result("FAILED_COVERAGE", index)
        if (call.get("method") != "rotatePivotObserved" or call.get("caller") != caller or
                call.get("caller_code_index") != sites[index % 3]):
            return _result("FAILED_SOURCE_SITE", index)
        receiver, thread = call.get("receiver"), call.get("thread")
        if (type(receiver) is not int or receiver <= 0 or
                type(thread) is not int or thread <= 0):
            return _result("FAILED_SOURCE_SITE", index)
        threads.add(thread)
        old_receiver = body_receivers.setdefault(body, receiver)
        if old_receiver != receiver or (len(body_receivers) == 2 and
                                        body_receivers["b0"] == body_receivers["b1"]):
            return _result("FAILED_SOURCE_SITE", index)
        for field in ("pre", "trig", "post"):
            if not _pair(call.get(field)) or not _pair(marker.get(field)) or call[field] != marker[field]:
                return _result("FAILED_ARITHMETIC", index)
        if not _bits(call.get("angle_bits")) or call["angle_bits"] != marker.get("angle_bits"):
            return _result("FAILED_ARITHMETIC", index)
        if index % 3 and (int(call["angle_bits"], 16) & 0x7fffffffffffffff):
            return _result("FAILED_ARITHMETIC", index)
    if len(threads) != 1:
        return _result("FAILED_COVERAGE", 1800)
    return _result("UNPASSED_WORKER_BINDING", 1800)
