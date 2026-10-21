import argparse
from bisect import bisect_left
import hashlib
import hmac
import json
from pathlib import Path
import shutil

from sustained_archive import (FROZEN_MANIFEST_SHA256, canonical,
                               comparison_control_keys, frozen_policy,
                               require, require_external_key, signature)


SOURCE_COMMIT = "bb7d5cf7671f96a13449a5e0c3d65ff44d4b4975"
VERSION = "reference-study-v1"
PHASES = ("feasibility", "source", "model_holdout", "confirmation")
IDENTITY_FILES = ("artifact", "probe", "runtime", "image")
RAW_FILES = ("series", "environment", "monitor")
CONTROL_ROUTES = {"dyn4j_6_0_0_jvm": "baseline",
                  "row_reference_self": "direct_kotlin",
                  "direct_kotlin_self": "direct_kotlin",
                  "compatibility_self": "compatibility"}
PAIR_ORDER = (("a", "b"), ("b", "a"), ("a", "b"))
CONTROL_KEYS = frozenset({"row_id", "control_id", "route", "host_id"} |
                         {name + "_path" for name in IDENTITY_FILES})
CAPTURE_KEYS = frozenset({"phase", "key", "control_id", "row_id", "route",
                          "host_id", "pair", "side", "order", "process_id", "run_id",
                          "os_pid", "started_ns", "ended_ns", "invalid_reason",
                          "stop_reason"} |
                         {name + "_sha256" for name in IDENTITY_FILES} |
                         {name + "_path" for name in RAW_FILES})


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_keys(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected),
            f"{label} keys differ")


def hex_digest(value, label):
    require(isinstance(value, str) and len(value) == 64 and
            all(character in "0123456789abcdef" for character in value),
            f"invalid {label}")


def policy_context():
    policy = frozen_policy()
    keys = comparison_control_keys(policy)
    return {"manifest_sha256": FROZEN_MANIFEST_SHA256,
            "source_commit": SOURCE_COMMIT, "version": VERSION,
            "baseline_jar_sha256": policy["baseline_jar_sha256"],
            "assignment_inventory_sha256": sha_bytes(canonical(sorted(keys))),
            "assignment_count": len(keys),
            "tool_sha256": sha_file(__file__)}, keys


def controls_for(key):
    comparison, row_id, _, _, _, _ = key.split("|")
    if comparison == "jvm_vs_dyn4j":
        require(row_id == "jvm.java", "dyn4j comparison outside JVM")
        return ["dyn4j_6_0_0_jvm"]
    if comparison == "shim_vs_direct":
        return ["compatibility_self", "direct_kotlin_self"]
    require(comparison in ("absolute_timing", "absolute_memory"),
            "unrecognized comparison")
    return ["row_reference_self"]


def checked_relative(root, relative, expected_hash):
    require(isinstance(relative, str) and relative and
            not Path(relative).is_absolute() and ".." not in Path(relative).parts,
            "unsafe archived path")
    path = root / relative
    require(path.is_file() and path.stat().st_size > 0 and not path.is_symlink() and
            path.resolve().is_relative_to(root.resolve()), "missing archived bytes")
    hex_digest(expected_hash, "archived digest")
    require(sha_file(path) == expected_hash, "archived bytes differ")
    return path


def unique_object(pairs):
    value = {}
    for name, item in pairs:
        require(name not in value, "duplicate JSON key")
        value[name] = item
    return value


def load_unique_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=unique_object)


def signed_json(root, name, key):
    path = root / name
    require(path.is_file() and not path.is_symlink(), f"missing {name}")
    record = load_unique_json(path)
    require(isinstance(record, dict) and "signature" in record,
            f"missing {name} signature")
    require(hmac.compare_digest(record["signature"], signature(record, key)),
            f"{name} signature differs")
    return record


def write_signed(root, name, record, key):
    record["signature"] = signature(record, key)
    target = root / name
    temporary = root / (name + ".tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    temporary.replace(target)


def validate_protocol(protocol, root):
    context, allowed = policy_context()
    exact_keys(protocol, {"signature", "assignments", "controls", "context"}, "protocol")
    require(protocol["context"] == context, "frozen study context differs")
    assignments = protocol["assignments"]
    require(isinstance(assignments, list) and assignments, "empty assignment inventory")
    seen = set()
    needed = set()
    for assignment in assignments:
        exact_keys(assignment, {"phase", "key", "controls"}, "assignment")
        phase, assignment_key = assignment["phase"], assignment["key"]
        require(phase in PHASES and assignment_key in allowed,
                "assignment outside frozen protocol")
        require(assignment["controls"] == controls_for(assignment_key),
                "comparison control assignment differs")
        pair = (phase, assignment_key)
        require(pair not in seen, "duplicate assignment")
        seen.add(pair)
        row = assignment_key.split("|")[1]
        needed.update((row, control) for control in assignment["controls"])
    controls = protocol["controls"]
    require(isinstance(controls, list), "controls must be a list")
    actual = set()
    for control in controls:
        exact_keys(control, {"row_id", "control_id", "route", "host_id"} |
                   {name + "_path" for name in IDENTITY_FILES} |
                   {name + "_sha256" for name in IDENTITY_FILES}, "control")
        identity = (control["row_id"], control["control_id"])
        require(identity in needed and identity not in actual,
                "missing, extra, or duplicate control")
        require(control["route"] == CONTROL_ROUTES[control["control_id"]],
                "control route differs")
        require(isinstance(control["host_id"], str) and control["host_id"],
                "missing control host")
        for name in IDENTITY_FILES:
            checked_relative(root, control[name + "_path"],
                             control[name + "_sha256"])
        if control["control_id"] == "dyn4j_6_0_0_jvm":
            require(control["artifact_sha256"] ==
                    context["baseline_jar_sha256"], "dyn4j baseline artifact differs")
        actual.add(identity)
    require(actual == needed, "control inventory incomplete")
    return {(item["phase"], item["key"]): item for item in assignments}, {
        (item["row_id"], item["control_id"]): item for item in controls}


def create_archive(root, plan, key, key_path):
    require(not root.exists(), "study archive already exists")
    exact_keys(plan, {"source_commit", "assignments", "controls"}, "study plan")
    require(plan["source_commit"] == SOURCE_COMMIT, "study source differs")
    require(isinstance(plan["controls"], list), "controls must be a list")
    context, _ = policy_context()
    root.mkdir(parents=True)
    copied = []
    for ordinal, control in enumerate(plan["controls"]):
        exact_keys(control, CONTROL_KEYS, "control input")
        record = {name: value for name, value in control.items()
                  if name not in {item + "_path" for item in IDENTITY_FILES}}
        for name in IDENTITY_FILES:
            source = Path(control[name + "_path"])
            require(source.is_file() and source.resolve() != key_path.resolve() and
                    sha_file(source) != sha_bytes(key),
                    "missing control input or trusted key used as input")
            relative = f"inputs/{ordinal}-{name}.bin"
            destination = root / relative
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, destination)
            record[name + "_path"] = relative
            record[name + "_sha256"] = sha_file(destination)
        copied.append(record)
    protocol = {"context": context, "assignments": plan["assignments"],
                "controls": copied}
    write_signed(root, "protocol.json", protocol, key)
    validate_protocol(signed_json(root, "protocol.json", key), root)
    return {"study": "protocol_frozen", "qualification": "unpassed",
            "declared_assignments": len(plan["assignments"])}


def validate_captures(root, protocol, captures):
    assignments, controls = validate_protocol(protocol, root)
    require(isinstance(captures, list), "captures must be a list")
    expected = {(phase, assignment_key, control_id, pair, side)
                for (phase, assignment_key), assignment in assignments.items()
                for control_id in assignment["controls"]
                for pair, sides in enumerate(PAIR_ORDER, 1) for side in sides}
    actual = set()
    process_ids = set()
    run_ids = set()
    process_intervals = {}
    process_raw_hashes = {"series": set(), "monitor": set()}
    for capture in captures:
        exact_keys(capture, CAPTURE_KEYS | {name + "_sha256" for name in RAW_FILES},
                   "capture")
        phase, assignment_key = capture["phase"], capture["key"]
        require((phase, assignment_key) in assignments, "capture assignment differs")
        row_id = assignment_key.split("|")[1]
        require(capture["row_id"] == row_id, "capture row differs")
        control_id = capture["control_id"]
        require(control_id in assignments[(phase, assignment_key)]["controls"],
                "capture control differs")
        control = controls[(row_id, control_id)]
        require(capture["route"] == control["route"] and
                capture["host_id"] == control["host_id"], "capture route or host differs")
        for name in IDENTITY_FILES:
            require(capture[name + "_sha256"] == control[name + "_sha256"],
                    f"capture {name} differs")
        pair, side, order = capture["pair"], capture["side"], capture["order"]
        require(type(pair) is int and 1 <= pair <= len(PAIR_ORDER) and
                side in ("a", "b") and type(order) is int and order in (1, 2) and
                PAIR_ORDER[pair - 1][order - 1] == side,
                "A/A side or order differs")
        slot = (phase, assignment_key, control_id, pair, side)
        require(slot in expected and slot not in actual, "duplicate or unexpected pair side")
        actual.add(slot)
        for id_key, seen in (("process_id", process_ids), ("run_id", run_ids)):
            value = capture[id_key]
            require(isinstance(value, str) and value and value not in seen,
                    f"duplicate or missing {id_key}")
            seen.add(value)
        require(type(capture["os_pid"]) is int and capture["os_pid"] > 0 and
                type(capture["started_ns"]) is int and
                type(capture["ended_ns"]) is int and
                0 <= capture["started_ns"] < capture["ended_ns"],
                "invalid process identity or interval")
        process_key = (capture["host_id"], capture["os_pid"])
        intervals = process_intervals.setdefault(process_key, [])
        start, end = capture["started_ns"], capture["ended_ns"]
        position = bisect_left(intervals, (start, end))
        require((position == 0 or intervals[position - 1][1] <= start) and
                (position == len(intervals) or end <= intervals[position][0]),
                "overlapping observed host/PID intervals")
        intervals.insert(position, (start, end))
        require(capture["invalid_reason"] is None and
                capture["stop_reason"] == "completed",
                "invalid or stopped study capture")
        for name in RAW_FILES:
            checked_relative(root, capture[name + "_path"],
                             capture[name + "_sha256"])
            if name in process_raw_hashes:
                raw_hash = capture[name + "_sha256"]
                require(raw_hash not in process_raw_hashes[name],
                        f"reused {name} bytes across process captures")
                process_raw_hashes[name].add(raw_hash)
    require(actual == expected, "declared assignment pair inventory incomplete")
    return len(assignments)


def seal_archive(root, inputs, key, key_path):
    require(not (root / "archive.json").exists(), "study archive already sealed")
    protocol = signed_json(root, "protocol.json", key)
    validate_protocol(protocol, root)
    require(isinstance(inputs, list), "captures input must be a list")
    captures = []
    for ordinal, item in enumerate(inputs):
        exact_keys(item, CAPTURE_KEYS, "capture input")
        record = {name: value for name, value in item.items()
                  if name not in {entry + "_path" for entry in RAW_FILES}}
        for name in RAW_FILES:
            source = Path(item[name + "_path"])
            require(source.is_file() and source.resolve() != key_path.resolve() and
                    sha_file(source) != sha_bytes(key),
                    "missing raw source or trusted key used as input")
            relative = f"raw/{ordinal}-{name}.bin"
            destination = root / relative
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, destination)
            record[name + "_path"] = relative
            record[name + "_sha256"] = sha_file(destination)
        captures.append(record)
    validate_captures(root, protocol, captures)
    index = {"protocol_sha256": sha_file(root / "protocol.json"),
             "captures": captures}
    write_signed(root, "archive.json", index, key)
    return verify_archive(root, key, SOURCE_COMMIT)


def verify_archive(root, key, expected_source_commit):
    require(expected_source_commit == SOURCE_COMMIT, "expected source differs")
    protocol = signed_json(root, "protocol.json", key)
    index = signed_json(root, "archive.json", key)
    exact_keys(index, {"signature", "protocol_sha256", "captures"}, "archive")
    require(index["protocol_sha256"] == sha_file(root / "protocol.json"),
            "late protocol change")
    count = validate_captures(root, protocol, index["captures"])
    return {"study": "structurally_verified", "qualification": "unpassed",
            "declared_assignments": count, "validated_reference_rows": 0,
            "numeric_limits": "not_approved"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("create", "seal", "verify"))
    parser.add_argument("--archive", required=True)
    parser.add_argument("--trusted-key", required=True)
    parser.add_argument("--plan")
    parser.add_argument("--captures")
    parser.add_argument("--expected-source-commit")
    args = parser.parse_args()
    try:
        root = Path(args.archive)
        require_external_key(args.trusted_key, [root])
        key_path = Path(args.trusted_key)
        key = key_path.read_bytes()
        require(len(key) >= 32, "trusted key is too short")
        if args.command == "create":
            require(args.plan, "create requires a plan")
            result = create_archive(root, load_unique_json(args.plan), key, key_path)
        elif args.command == "seal":
            require(args.captures, "seal requires captures")
            result = seal_archive(root, load_unique_json(args.captures), key,
                                  key_path)
        else:
            require(args.expected_source_commit, "verify requires expected source")
            result = verify_archive(root, key, args.expected_source_commit)
        print(json.dumps(result, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"qualification": "unpassed", "reason": str(exc)},
                         sort_keys=True))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
