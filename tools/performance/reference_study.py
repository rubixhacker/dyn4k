import argparse
from bisect import bisect_left
import csv
import hashlib
import hmac
import json
from pathlib import Path
import shutil

from sustained_archive import (FROZEN_MANIFEST_SHA256, canonical,
                               comparison_control_keys, frozen_policy,
                               require, require_external_key, signature)


SOURCE_COMMIT = "bb7d5cf7671f96a13449a5e0c3d65ff44d4b4975"
VERSION = "reference-study-v3"
LEGACY_VERSION = "reference-study-v2"
PHASES = ("feasibility", "source", "model_holdout", "confirmation")
IDENTITY_FILES = ("artifact", "probe", "runtime", "image")
RAW_FILES = ("series", "environment", "monitor")
V3_RAW_FILES = RAW_FILES + ("observer", "source_receipt", "build_receipt",
                            "provider", "clock_origin", "measure_clock",
                            "warmup_clock", "run_receipt", "staged_core",
                            "staged_kotlin")
CONTROL_ROUTES = {"dyn4j_6_0_0_jvm": "baseline",
                  "row_reference_self": "direct_kotlin",
                  "direct_kotlin_self": "direct_kotlin",
                  "compatibility_self": "compatibility"}
PAIR_ORDER = (("a", "b"), ("b", "a"), ("a", "b"))
CONTROL_KEYS = frozenset({"row_id", "control_id", "route", "host_id", "boot_id"} |
                         {name + "_path" for name in IDENTITY_FILES})
CAPTURE_IDENTITY_KEYS = frozenset({"phase", "key", "control_id", "row_id", "route",
                                   "host_id", "boot_id", "pair", "side", "order",
                                   "process_id", "run_id", "os_pid", "process_start_id",
                                   "started_ns", "ended_ns", "invalid_reason", "stop_reason"} |
                                  {name + "_sha256" for name in IDENTITY_FILES})


def raw_files(version):
    require(version in (VERSION, LEGACY_VERSION), "unknown study archive version")
    return V3_RAW_FILES if version == VERSION else RAW_FILES


def capture_keys(version):
    return CAPTURE_IDENTITY_KEYS | {name + "_path" for name in raw_files(version)}


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


def policy_context(version=VERSION):
    policy = frozen_policy()
    keys = comparison_control_keys(policy)
    return {"manifest_sha256": FROZEN_MANIFEST_SHA256,
            "source_commit": SOURCE_COMMIT, "version": version,
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
    require(isinstance(protocol, dict) and isinstance(protocol.get("context"), dict),
            "missing study context")
    context, allowed = policy_context(protocol["context"].get("version"))
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
        if context["version"] == VERSION:
            require(assignment_key.split("|")[3] == "timing",
                    "version 3 requires a timing raw schema")
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
        exact_keys(control, {"row_id", "control_id", "route", "host_id", "boot_id"} |
                   {name + "_path" for name in IDENTITY_FILES} |
                   {name + "_sha256" for name in IDENTITY_FILES}, "control")
        identity = (control["row_id"], control["control_id"])
        require(identity in needed and identity not in actual,
                "missing, extra, or duplicate control")
        require(control["route"] == CONTROL_ROUTES[control["control_id"]],
                "control route differs")
        require(isinstance(control["host_id"], str) and control["host_id"].strip(),
                "missing control host")
        require(isinstance(control["boot_id"], str) and control["boot_id"].strip(),
                "missing control boot identity")
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
    require(isinstance(plan, dict), "study plan must be an object")
    version = plan.get("archive_version", VERSION)
    raw_files(version)
    exact_keys(plan, {"source_commit", "assignments", "controls"} |
               ({"archive_version"} if "archive_version" in plan else set()), "study plan")
    require(plan["source_commit"] == SOURCE_COMMIT, "study source differs")
    require(isinstance(plan["controls"], list), "controls must be a list")
    context, _ = policy_context(version)
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


def v3_json(root, capture, name):
    value = load_unique_json(root / capture[name + "_path"])
    require(isinstance(value, dict), f"{name} must be a JSON object")
    return value


def v3_csv(root, capture, name, header):
    with (root / capture[name + "_path"]).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == header, f"{name} header differs")
        rows = list(reader)
    require(rows and all(set(row) == set(header) and None not in row.values()
                         for row in rows), f"{name} rows differ")
    return rows


def v3_digest(value, label):
    hex_digest(value, label)
    return value


def validate_v3_capture(root, capture, control):
    observer = v3_json(root, capture, "observer")
    environment = v3_json(root, capture, "environment")
    monitor = v3_json(root, capture, "monitor")
    source = v3_json(root, capture, "source_receipt")
    build = v3_json(root, capture, "build_receipt")
    provider = v3_json(root, capture, "provider")
    origin = v3_json(root, capture, "clock_origin")
    run = v3_json(root, capture, "run_receipt")
    exact_keys(source, {"capture", "raw_sha256", "source_commit",
                        "staged_core_sha256", "staged_kotlin_sha256",
                        "command", "classpath"}, "source receipt")
    require(source["source_commit"] == SOURCE_COMMIT and
            source["capture"] == {key: capture[key] for key in CAPTURE_IDENTITY_KEYS},
            "source receipt capture or source differs")
    others = set(V3_RAW_FILES) - {"source_receipt"}
    exact_keys(source["raw_sha256"], others, "source raw inventory")
    require(all(source["raw_sha256"][name] == capture[name + "_sha256"]
                for name in others), "source receipt raw digest differs")
    observed_keys = {"host_id", "boot_id", "os_pid", "process_start_id",
                     "process_id", "run_id", "started_ns", "ended_ns"}
    exact_keys(observer, observed_keys | {"observed_command", "observed_environment",
                                         "image", "exit_code"}, "observer")
    require(all(observer[name] == capture[name] for name in observed_keys) and
            type(observer["exit_code"]) is int and observer["exit_code"] == 0,
            "observer process or exit differs")
    image = observer["image"]
    exact_keys(image, {"pid", "sha256", "executable_path", "method", "observed_ns"},
               "observed image")
    start, end = capture["started_ns"], capture["ended_ns"]
    require(image["pid"] == capture["os_pid"] and
            image["sha256"] == control["image_sha256"] and
            type(image["observed_ns"]) is int and
            start <= image["observed_ns"] < end and
            isinstance(image["method"], str) and image["method"].strip() and
            isinstance(image["executable_path"], str) and image["executable_path"],
            "observed image identity or interval differs")
    command = observer["observed_command"]
    require(isinstance(command, list) and command and
            all(isinstance(arg, str) and arg for arg in command) and
            command[0] == image["executable_path"] and source["command"] == command,
            "observed command differs")
    observed_env = observer["observed_environment"]
    require(isinstance(observed_env, dict) and
            observed_env.get("DYN4K_CLOCK_NONCE") == capture["run_id"] and
            observed_env.get("DYN4K_SOURCE_COMMIT") == SOURCE_COMMIT,
            "observed launch nonce or source differs")
    classpath = source["classpath"]
    require(isinstance(classpath, list), "source classpath differs")
    for entry in classpath:
        exact_keys(entry, {"path", "sha256"}, "classpath entry")
        require(isinstance(entry["path"], str) and entry["path"],
                "source classpath path differs")
        v3_digest(entry["sha256"], "classpath digest")
    allowed_classpath = {control["artifact_sha256"], control["probe_sha256"],
                         source["staged_core_sha256"], source["staged_kotlin_sha256"]}
    require(all(entry["sha256"] in allowed_classpath for entry in classpath),
            "unbound classpath entry")
    if "-cp" in command:
        require(command.count("-cp") == 1 and command.index("-cp") + 1 < len(command),
                "observed classpath differs")
        value = command[command.index("-cp") + 1]
        separator = ";" if ";" in value else ":"
        require([entry["path"] for entry in classpath] == value.split(separator) and
                {control["artifact_sha256"], control["probe_sha256"]} <=
                {entry["sha256"] for entry in classpath},
                "observed classpath or control bytes differ")
        if capture["control_id"] == "dyn4j_6_0_0_jvm":
            require([entry["sha256"] for entry in classpath] ==
                    [control["probe_sha256"], control["artifact_sha256"]],
                    "baseline classpath differs")
    else:
        require(not classpath and capture["row_id"] != "jvm.java",
                "missing JVM classpath")
    exact_keys(monitor, {"host_id", "boot_id", "os_pid", "process_start_id",
                         "launch_nonce", "started_ns", "ended_ns", "samples"}, "monitor")
    require(all(monitor[name] == capture[name] for name in
                ("host_id", "boot_id", "os_pid", "process_start_id", "started_ns", "ended_ns")) and
            monitor["launch_nonce"] == capture["run_id"] and
            isinstance(monitor["samples"], list) and monitor["samples"],
            "monitor process or nonce differs")
    previous = start
    for sample in monitor["samples"]:
        exact_keys(sample, {"clock_ns", "os_pid", "process_start_id", "rss_bytes"},
                   "monitor sample")
        stamp = sample["clock_ns"]
        require(type(stamp) is int and previous <= stamp < end and
                sample["os_pid"] == capture["os_pid"] and
                sample["process_start_id"] == capture["process_start_id"] and
                type(sample["rss_bytes"]) is int and sample["rss_bytes"] >= 0,
                "monitor sample outside observed process")
        previous = stamp
    require(all(environment.get(name) == capture[name] for name in
                ("host_id", "boot_id", "os_pid", "process_start_id")) and
            environment.get("launch_nonce") == capture["run_id"] and
            environment.get("observer") == observer,
            "environment observer or process differs")
    for name in IDENTITY_FILES:
        require(environment.get(name + "_sha256") == control[name + "_sha256"],
                f"environment {name} differs")
    for name in ("series", "monitor", "provider", "clock_origin"):
        require(environment.get(name + "_sha256") == capture[name + "_sha256"],
                f"environment {name} receipt differs")
    require(build.get("source_commit") == SOURCE_COMMIT and
            build.get("runtime_sha256") == control["runtime_sha256"],
            "build source or runtime differs")
    artifact_field = "baseline_sha256" if capture["control_id"] == "dyn4j_6_0_0_jvm" else "artifact_sha256"
    probe_field = "harness_sha256" if capture["control_id"] == "dyn4j_6_0_0_jvm" else "probe_sha256"
    require(build.get(artifact_field) == control["artifact_sha256"] and
            build.get(probe_field) == control["probe_sha256"] and
            build.get("image_sha256", control["runtime_sha256"]) == control["image_sha256"],
            "build control or image receipt differs")
    for kind in ("core", "kotlin"):
        value = v3_digest(source["staged_" + kind + "_sha256"], "staged artifact")
        require(build.get("staged_" + kind + "_sha256") == value and
                environment.get("staged_" + kind + "_sha256") == value and
                capture["staged_" + kind + "_sha256"] == value,
                "staged artifact receipt differs")
    require(provider.get("pid") == capture["os_pid"] and
            provider.get("source_commit") == SOURCE_COMMIT and
            provider.get("runtime_sha256") == control["runtime_sha256"] and
            provider.get("artifact_sha256") == {
                "core": source["staged_core_sha256"],
                "kotlin": source["staged_kotlin_sha256"]},
            "loaded provider process, source, or stage differs")
    if capture["control_id"] == "dyn4j_6_0_0_jvm":
        require(provider.get("api") == "baseline" and
                provider.get("baseline_sha256") == control["artifact_sha256"] and
                provider.get("loaded_core_sha256") == control["artifact_sha256"] and
                provider.get("loaded_harness_sha256") == control["probe_sha256"] and
                provider.get("loaded_adapter_sha256") == control["probe_sha256"] and
                provider.get("loaded_kotlin_sha256") is None,
                "baseline loaded provider differs")
    else:
        require(provider.get("run_id") == capture["run_id"] and
                provider.get("loaded_artifact_sha256") == control["artifact_sha256"] and
                provider.get("loaded_probe_sha256") == control["probe_sha256"],
                "loaded provider control differs")
    require(origin.get("pid") == capture["os_pid"] and
            origin.get("nonce") == capture["run_id"] and
            type(origin.get("runtime_ns")) is int and
            start <= origin["runtime_ns"] <= end,
            "runtime clock origin differs")
    series = v3_csv(root, capture, "series", ["step", "elapsed_ns"])
    measured = v3_csv(root, capture, "measure_clock", ["step", "begin_ns", "end_ns"])
    warmup = v3_csv(root, capture, "warmup_clock", ["warmup_step", "begin_ns", "end_ns"])
    assignment_mode = capture["key"].split("|")[3]
    require(len(series) == len(measured) and
            run.get("status") == "complete" and
            run.get("sample_count") == len(series) and
            run.get("warmup_count") == len(warmup) and
            run.get("mode") == assignment_mode == "timing" and
            run.get("api") == ("baseline" if capture["control_id"] == "dyn4j_6_0_0_jvm"
                               else capture["route"]),
            "run receipt or series count differs")
    previous = origin["runtime_ns"]
    for index, row in enumerate(warmup):
        begin, finish = int(row["begin_ns"]), int(row["end_ns"])
        require(int(row["warmup_step"]) == index and
                previous <= begin < finish <= end,
                "warm-up clock outside observed process")
        previous = finish
    for index, (sample, clock) in enumerate(zip(series, measured)):
        begin, finish = int(clock["begin_ns"]), int(clock["end_ns"])
        require(int(sample["step"]) == index and int(clock["step"]) == index and
                previous <= begin < finish <= end and
                int(sample["elapsed_ns"]) == finish - begin,
                "measured series clock outside observed process")
        previous = finish


def validate_captures(root, protocol, captures):
    assignments, controls = validate_protocol(protocol, root)
    version = protocol["context"]["version"]
    kinds = raw_files(version)
    require(isinstance(captures, list), "captures must be a list")
    protected = [root / "protocol.json", root / "archive.json"]
    protected.extend(root / control[name + "_path"] for control in controls.values()
                     for name in IDENTITY_FILES)
    protected_inodes = {(path.stat().st_dev, path.stat().st_ino)
                        for path in protected if path.is_file()}
    expected = {(phase, assignment_key, control_id, pair, side)
                for (phase, assignment_key), assignment in assignments.items()
                for control_id in assignment["controls"]
                for pair, sides in enumerate(PAIR_ORDER, 1) for side in sides}
    actual = set()
    process_ids = set()
    run_ids = set()
    declared_processes = set()
    process_intervals = {}
    raw_paths = set()
    raw_inodes = set()
    for capture in captures:
        exact_keys(capture, capture_keys(version) |
                   {name + "_sha256" for name in kinds},
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
                capture["host_id"] == control["host_id"] and
                capture["boot_id"] == control["boot_id"],
                "capture route, host, or boot differs")
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
            require(isinstance(value, str) and value.strip() and value not in seen,
                    f"duplicate or missing {id_key}")
            seen.add(value)
        require(type(capture["os_pid"]) is int and capture["os_pid"] > 0 and
                isinstance(capture["process_start_id"], str) and
                capture["process_start_id"].strip() and
                type(capture["started_ns"]) is int and
                type(capture["ended_ns"]) is int and
                0 <= capture["started_ns"] < capture["ended_ns"] <= (1 << 63) - 1,
                "invalid process identity or interval")
        process_key = (capture["host_id"], capture["boot_id"], capture["os_pid"])
        process_identity = (*process_key, capture["process_start_id"])
        require(process_identity not in declared_processes,
                "reused declared process identity")
        declared_processes.add(process_identity)
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
        for name in kinds:
            relative = capture[name + "_path"]
            require(isinstance(relative, str) and len(Path(relative).parts) >= 2 and
                    Path(relative).parts[0] == "raw",
                    "capture raw path must be under raw/")
            path = checked_relative(root, relative, capture[name + "_sha256"])
            inode = (path.stat().st_dev, path.stat().st_ino)
            require(path.resolve() not in raw_paths and inode not in raw_inodes and
                    inode not in protected_inodes, "raw archive path reused")
            raw_paths.add(path.resolve())
            raw_inodes.add(inode)
        if version == VERSION:
            validate_v3_capture(root, capture, control)
    require(actual == expected, "declared assignment pair inventory incomplete")
    return len(assignments)


def seal_archive(root, inputs, key, key_path):
    require(not (root / "archive.json").exists(), "study archive already sealed")
    protocol = signed_json(root, "protocol.json", key)
    validate_protocol(protocol, root)
    version = protocol["context"]["version"]
    kinds = raw_files(version)
    require(isinstance(inputs, list), "captures input must be a list")
    captures = []
    for ordinal, item in enumerate(inputs):
        exact_keys(item, capture_keys(version), "capture input")
        record = {name: value for name, value in item.items()
                  if name not in {entry + "_path" for entry in kinds}}
        for name in kinds:
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
