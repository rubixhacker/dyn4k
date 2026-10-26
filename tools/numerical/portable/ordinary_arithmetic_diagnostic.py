import argparse
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
import zlib
from urllib.parse import unquote, urlparse

from actual_arithmetic import CaptureRejected, verify_capture
import actual_arithmetic
import actual_output_v6
import actual_trace
from actual_trace import (
    ENVIRONMENT_SENTINEL, FORBIDDEN_ENVIRONMENT_KEY, MAX_READER_BYTES,
    V6_RAW_MAX_BYTES, V6_RAW_MAX_MEMBERS, TraceRejected,
    trace_exposes_environment, validate_version6_raw_archive,
)
from boolean_rotation_jdi import jdi_bridge
from boolean_rotation_jdi.loaded_code import verify_probe_code
from capture_actual import (
    ROOT, PORTABLE, JDK21, STAGED_JAR, CaptureBudget, child_environment,
    clean_source, gradle_test_command, reserve_boolean_jdi_port,
    selected_worker_pid, socket_owner,
)
from numeric_producer import captured_file_identity
from numeric_producer_trace import (
    _events, quoted, select_worker_exec, successful_execve,
    verify_stable_input,
)


SCHEMA = "ordinary-arithmetic-diagnostic/1"
METHOD = "captureLongMotion"
CASE = "long-free-60"
CAP = 64
RSS_CEILING_KIB = 10 * 1024 * 1024
REQUIRED_ROLES = frozenset({"gradle", "worker", "helper", "tracer", "observer"})
CALLER = "org.dyn4j.dynamics.AbstractPhysicsBody.integratePosition$lambda$0"
HEX64 = re.compile(r"[0-9a-f]{16}\Z")
LIFECYCLE = ("attach", "armed", "class-prepared", "first-entry", "cap-entry-reached",
             "exits-drained", "requests-disabled", "event-set-resumed",
             "disposed", "detach-complete")
SOURCE_MEMBERS = (
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/geometry/Transform.kt",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/geometry/RotationOperationTap.kt",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/AbstractPhysicsBody.kt",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/collision/CollisionBody.kt",
    "tools/numerical/portable/build.gradle.kts",
    "tools/numerical/portable/cases.py",
    "tools/numerical/portable/src/commonMain/kotlin/portable/ProspectiveOperationMarker.kt",
    "tools/numerical/portable/src/commonMain/kotlin/portable/NumericalRecorder.kt",
    "tools/numerical/portable/src/commonTest/kotlin/portable/PortableMatrixTest.kt",
    "tools/numerical/portable/src/commonTest/kotlin/portable/ProspectiveArithmeticTest.kt",
    "tools/numerical/portable/ordinary_arithmetic_jdi/OrdinaryArithmeticProbe.java",
    "tools/numerical/portable/ordinary_arithmetic_diagnostic.py",
)


class DiagnosticRejected(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise DiagnosticRejected(message)


def validate_request(method, call_cap):
    _require(method == METHOD and type(call_cap) is int and call_cap == CAP,
             "original long-motion selector or call cap differs")


def _privacy(raw, binary=False):
    if ENVIRONMENT_SENTINEL in raw or FORBIDDEN_ENVIRONMENT_KEY in raw:
        raise DiagnosticRejected("diagnostic evidence exposed the environment")
    stripped = raw.lstrip()
    if not binary and (stripped.startswith(b"{") or
                       re.match(rb'\[\s*(?:\[|\{|")', stripped)):
        lines = raw.splitlines()
        for line in lines:
            _json_privacy(line)
        return
    if not binary and stripped.startswith(b"<"):
        _xml_privacy(raw)
        return
    inspected = (b"\n".join(re.findall(rb"[\x20-\x7e]{4,}", raw))
                 if binary else raw)
    try:
        if trace_exposes_environment(inspected):
            raise DiagnosticRejected("diagnostic evidence exposed the environment")
    except TraceRejected as error:
        raise DiagnosticRejected("diagnostic privacy decoding failed") from error


def _decoded_privacy(value):
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str):
            raw = item.encode("utf-8")
            if ENVIRONMENT_SENTINEL in raw or FORBIDDEN_ENVIRONMENT_KEY in raw:
                raise DiagnosticRejected("diagnostic evidence exposed the environment")


def _json_privacy(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_unique_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(
                               DiagnosticRejected("nonfinite diagnostic JSON")))
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        if isinstance(error, DiagnosticRejected):
            raise
        raise DiagnosticRejected("diagnostic JSON is malformed") from error
    _decoded_privacy(value)
    return value


def _xml_privacy(raw):
    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, RecursionError) as error:
        raise DiagnosticRejected("diagnostic XML is malformed") from error
    for element in root.iter():
        for value in (element.text, element.tail, *element.attrib.keys(),
                      *element.attrib.values()):
            if value is not None:
                _decoded_privacy(value)
        if element.tag == "system-out" and element.text:
            for line in element.text.splitlines():
                for prefix in ("NUMERICAL_JSON ", "PROSPECTIVE_ROTATION_JSON "):
                    if line.startswith(prefix):
                        _json_privacy(line[len(prefix):].encode("utf-8"))


def check_retained(raw, kind):
    _require(type(raw) is bytes and kind in {
        "raw", "binary", "trace", "zip", "trace_zip", "report", "jsonl"},
             "diagnostic retained input differs")
    _require(len(raw) <= (V6_RAW_MAX_BYTES if kind in {"trace", "trace_zip"}
                          else MAX_READER_BYTES), "diagnostic raw reader bound")
    if kind in {"report", "jsonl"}:
        if ENVIRONMENT_SENTINEL in raw or FORBIDDEN_ENVIRONMENT_KEY in raw:
            raise DiagnosticRejected("diagnostic evidence exposed the environment")
    elif kind in {"zip", "trace_zip"}:
        if ENVIRONMENT_SENTINEL in raw or FORBIDDEN_ENVIRONMENT_KEY in raw:
            raise DiagnosticRejected("diagnostic evidence exposed the environment")
    else:
        _privacy(raw, binary=kind in {"binary", "zip", "trace_zip"})
    if kind == "report":
        _json_privacy(raw)
    if kind == "jsonl":
        _require(raw.endswith(b"\n"), "diagnostic JSON line stream is incomplete")
        for line in raw.splitlines():
            _json_privacy(line)
    if kind in {"zip", "trace_zip"}:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = archive.namelist()
                _require(bool(names) and len(names) <= V6_RAW_MAX_MEMBERS and
                         len(names) == len(set(names)) and
                         all(not name.startswith("/") and ".." not in name.split("/")
                             for name in names),
                         "diagnostic ZIP inventory differs")
                limit = (V6_RAW_MAX_BYTES if kind == "trace_zip" else MAX_READER_BYTES)
                _require(sum(item.file_size for item in archive.infolist()) <=
                         limit, "diagnostic ZIP decoded bound")
                for item in archive.infolist():
                    _require(item.file_size <= limit and
                             not item.is_dir(), "diagnostic ZIP member bound")
                if kind == "trace_zip":
                    validate_version6_raw_archive(raw, archive)
                for item in archive.infolist():
                    with archive.open(item) as stream:
                        member = stream.read(item.file_size + 1)
                    _require(len(member) == item.file_size,
                             "diagnostic ZIP member decoded size differs")
                    if item.filename.endswith((".json", ".jsonl")):
                        for line in member.splitlines() if item.filename.endswith(
                                ".jsonl") else (member,):
                            _json_privacy(line)
                    elif item.filename.endswith(".xml"):
                        _xml_privacy(member)
                    else:
                        _privacy(member, binary=item.filename.endswith(
                            (".class", ".bin", ".jar")))
        except (OSError, EOFError, OverflowError, zipfile.BadZipFile,
                zlib.error, RuntimeError, ValueError, TraceRejected) as error:
            if isinstance(error, DiagnosticRejected):
                raise
            raise DiagnosticRejected("diagnostic ZIP is malformed") from error
    return raw


def _number(value):
    _require(re.fullmatch(r"(?:0|[1-9][0-9]*)", value) is not None,
             "diagnostic event integer differs")
    return int(value)


def verify_events(raw, markers, caller_index, loader_id):
    check_retained(raw, "raw")
    _require(type(markers) is list and len(markers) >= CAP and
             type(caller_index) is int and caller_index >= 0 and
             type(loader_id) is int and loader_id > 0 and
             raw.endswith(b"\n"), "diagnostic prefix input differs")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError as error:
        raise DiagnosticRejected("diagnostic event encoding differs") from error
    _require(len(lines) == CAP, "diagnostic cap or exit count differs")
    threads = set()
    receivers = set()
    durations = []
    for ordinal, (line, marker) in enumerate(zip(lines, markers)):
        fields = line.split("\t")
        _require(len(fields) == 14 and type(marker) is dict,
                 "diagnostic event format differs")
        observed = [_number(field) for field in fields[:3]]
        site = _number(fields[11])
        caller_loader = _number(fields[12])
        duration = _number(fields[13])
        _require(observed[0] == ordinal and observed[1] > 0 and
                 observed[2] > 0 and site == caller_index and
                 caller_loader == loader_id and duration > 0 and
                 fields[10] == CALLER and all(HEX64.fullmatch(value)
                 for value in fields[3:10]),
                 "diagnostic call order, identity or bits differ")
        _require(marker.get("sequence") == ordinal + 1 and
                 marker.get("step") == ordinal + 1 and
                 marker.get("case_id", CASE) == CASE and
                 marker.get("body_id") == "b0" and
                 marker.get("kind") == "rotate" and
                 marker.get("source") == "pivot" and
                 marker.get("pre") == fields[3:5] and
                 marker.get("trig") == fields[5:7] and
                 marker.get("post") == fields[7:9] and
                 marker.get("angle_bits") == fields[9],
                 "diagnostic marker order or raw bits differ")
        threads.add(observed[1])
        receivers.add(observed[2])
        durations.append(duration)
    _require(len(threads) == len(receivers) == 1,
             "diagnostic source thread or receiver differs")
    ordered = sorted(durations)
    return {"matched_calls": CAP, "thread_id": next(iter(threads)),
            "receiver_id": next(iter(receivers)), "service_ns": {
                "p50": ordered[31], "p95": ordered[60], "max": ordered[-1]}}


def verify_lifecycle(raw):
    check_retained(raw, "raw")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError as error:
        raise DiagnosticRejected("diagnostic lifecycle encoding differs") from error
    _require(raw.endswith(b"\n") and len(lines) == len(LIFECYCLE),
             "diagnostic detach inventory differs")
    times = []
    for line, expected in zip(lines, LIFECYCLE):
        fields = line.split("\t")
        _require(len(fields) == 2 and fields[0] == expected,
                 "diagnostic detach order differs")
        times.append(_number(fields[1]))
    _require(all(start < end for start, end in zip(times, times[1:])),
             "diagnostic helper clock moved backwards")
    return {"attach_ns": times[0], "class_prepare_ns": times[2],
            "first_entry_ns": times[3], "cap_entry_reached_ns": times[4],
            "exits_drained_ns": times[5],
            "detach_complete_ns": times[-1],
            "helper_local_phases_ns": {
                "attach_to_prepare": times[2] - times[0],
                "prepare_to_first_entry": times[3] - times[2],
                "first_to_cap": times[4] - times[3],
                "cap_to_detach": times[-1] - times[4]}}


def verify_resource_samples(samples, required_roles=REQUIRED_ROLES):
    _require(type(samples) is list and bool(samples) and
             type(required_roles) in {set, frozenset},
             "diagnostic resource sample inventory differs")
    observed_roles = set()
    missing = False
    peak = 0
    previous = -1
    retained = []
    for sample in samples:
        _require(type(sample) is dict and set(sample) == {"time_ns", "phase", "pids"} and
                 sample["phase"] in {"stage", "target", "observer"} and
                 type(sample["time_ns"]) is int and sample["time_ns"] > previous and
                 type(sample["pids"]) is list and sample["pids"],
                 "diagnostic resource sample time differs")
        previous = sample["time_ns"]
        pids = {}
        for row in sample["pids"]:
            _require(type(row) is dict and set(row) == {"pid", "roles", "rss_kib",
                    "parent_pid", "group_pid", "session_pid", "start_ticks",
                    "affinity", "command_sha256"} and
                     type(row["pid"]) is int and row["pid"] > 0 and
                     type(row["parent_pid"]) is int and row["parent_pid"] >= 0 and
                     type(row["group_pid"]) is int and row["group_pid"] > 0 and
                     type(row["session_pid"]) is int and row["session_pid"] > 0 and
                     type(row["start_ticks"]) is int and row["start_ticks"] > 0 and
                     type(row["affinity"]) is list and bool(row["affinity"]) and
                     all(type(cpu) is int and cpu >= 0 for cpu in row["affinity"]) and
                     row["affinity"] == sorted(set(row["affinity"])) and
                     type(row["command_sha256"]) is str and
                     re.fullmatch(r"[0-9a-f]{64}", row["command_sha256"]) is not None and
                     type(row["roles"]) is list and row["roles"] and
                     all(role in required_roles for role in row["roles"]) and
                     (row["rss_kib"] is None or
                      type(row["rss_kib"]) is int and row["rss_kib"] >= 0),
                     "diagnostic owned PID sample differs")
            prior = pids.setdefault(row["pid"], row)
            _require(prior == row, "diagnostic PID has conflicting samples")
        observed_roles.update(role for row in pids.values() for role in row["roles"])
        if any(row["rss_kib"] is None for row in pids.values()):
            missing = True
        total = sum(row["rss_kib"] or 0 for row in pids.values())
        peak = max(peak, total)
        retained.append({"time_ns": previous, "phase": sample["phase"], "aggregate_kib":
                         None if missing else total,
                         "pids": sorted(pids.values(), key=lambda row: row["pid"])})
    status = ("RSS_BOUND" if peak > RSS_CEILING_KIB else
              "UNAVAILABLE" if missing or not required_roles <= observed_roles else
              "OBSERVED_UNDER_CEILING")
    return {"status": status, "peak_aggregate_kib": peak if not missing else None,
            "roles_observed": sorted(observed_roles), "samples": retained,
            "physical_containment": "UNPROVED"}


def verify_case_output(xml, case, exit_code):
    check_retained(xml, "raw")
    check_retained(case, "raw")
    _require(exit_code == 0, "diagnostic target did not exit normally")
    try:
        root = ET.fromstring(xml)
        testcases = root.findall("testcase")
        outputs = root.findall("system-out")
        _require(len(testcases) == len(outputs) == 1 and
                 testcases[0].get("name") in {METHOD, METHOD + "[jvm]"} and
                 testcases[0].get("classname") == "portable.ProspectiveArithmeticTest" and
                 not testcases[0].findall("failure") and
                 not testcases[0].findall("error") and
                 not testcases[0].findall("skipped") and
                 outputs[0].text is not None,
                 "diagnostic original JVM test output differs")
        extracted = _case_lines(outputs[0].text)
        _require(extracted == case, "diagnostic case bytes differ from XML")
        summary = verify_capture(xml, METHOD, [CASE], reset_order="post")
        _require(summary.get("steps") == 36000 and summary.get("cases") == 1,
                 "diagnostic case step count differs")
        return {"case_sha256": hashlib.sha256(case).hexdigest(),
                "xml_sha256": hashlib.sha256(xml).hexdigest(),
                "summary": summary}
    except (ET.ParseError, UnicodeError, CaptureRejected) as error:
        if isinstance(error, DiagnosticRejected):
            raise
        raise DiagnosticRejected("diagnostic original case output is incomplete") from error


def _write_checked(path, raw, kind="raw"):
    if kind == "raw" and Path(path).suffix in {".json", ".jsonl"}:
        kind = "report" if Path(path).suffix == ".json" else "jsonl"
    check_retained(raw, kind)
    with Path(path).open("xb") as stream:
        stream.write(raw)


def _read_checked(path, kind="raw"):
    path = Path(path)
    if kind == "raw" and path.suffix in {".json", ".jsonl"}:
        kind = "report" if path.suffix == ".json" else "jsonl"
    _require(path.is_file() and not path.is_symlink(),
             "diagnostic retained file is missing or replaced")
    limit = V6_RAW_MAX_BYTES if kind in {"trace", "trace_zip"} else MAX_READER_BYTES
    _require(path.stat().st_size <= limit, "diagnostic retained file exceeds reader bound")
    return check_retained(path.read_bytes(), kind)


def _zip_checked(members, kind="zip"):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as writer:
        for name, raw in sorted(members.items()):
            _require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.$/-]+", name)
                     is not None and ".." not in name.split("/"),
                     "diagnostic ZIP member name differs")
            check_retained(raw, "trace" if kind == "trace_zip" else
                           "binary" if name.endswith((".class", ".bin", ".jar"))
                           else "raw")
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            writer.writestr(entry, raw)
    return check_retained(archive.getvalue(), kind)


def _source_archive():
    return _zip_checked({name: (ROOT / name).read_bytes()
                         for name in SOURCE_MEMBERS})


def _verify_source_archive(raw, commit, environment):
    check_retained(raw, "zip")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        _require(set(archive.namelist()) == set(SOURCE_MEMBERS),
                 "diagnostic source archive inventory differs")
        for name in SOURCE_MEMBERS:
            source = subprocess.run(("git", "--no-replace-objects", "show",
                                     commit + ":" + name), cwd=ROOT,
                                    env=environment, capture_output=True,
                                    timeout=30, check=False)
            _require(source.returncode == 0 and archive.read(name) == source.stdout,
                     "diagnostic archived source differs from commit")


def verify_worker_classpath(response, classes_archive, expected_manifest=None,
                            staged_jar=STAGED_JAR, class_root=None):
    check_retained(response, "raw")
    check_retained(classes_archive, "zip")
    class_root = (ROOT / "tools/numerical/portable/build/classes/kotlin/jvm"
                  if class_root is None else Path(class_root))
    try:
        arguments = response.decode("utf-8").splitlines()
        _require(len(arguments) == 2 and arguments[0] == "-cp",
                 "diagnostic worker response format differs")
        with zipfile.ZipFile(io.BytesIO(classes_archive)) as archive:
            names = archive.namelist()
            _require(all(name.startswith(("main/", "test/")) and
                         name.endswith(".class") for name in names),
                     "diagnostic portable class inventory differs")
            providers = {
                source_set: {name.removeprefix(source_set + "/"):
                             hashlib.sha256(archive.read(name)).hexdigest()
                             for name in names if name.startswith(source_set + "/portable/")}
                for source_set in ("main", "test")}
        manifest = actual_arithmetic._inspect_worker_classpath(
            arguments[1], Path(staged_jar), class_root, providers)
        if expected_manifest is not None:
            _require(manifest == expected_manifest,
                     "diagnostic worker classpath snapshot differs")
        return manifest
    except (UnicodeError, OSError, zipfile.BadZipFile, CaptureRejected) as error:
        if isinstance(error, DiagnosticRejected):
            raise
        raise DiagnosticRejected("diagnostic worker classpath differs") from error


def compile_helper(source, scratch, environment):
    _require(type(source) is bytes and source and Path(scratch).is_dir(),
             "diagnostic helper source or scratch differs")
    classes = Path(scratch) / "ordinary-jdi-classes"
    classes.mkdir()
    java = Path(scratch) / "OrdinaryArithmeticProbe.java"
    _write_checked(java, source)
    jdi_bridge._require_jdk21_javac(JDK21 / "bin/javac", environment)
    command = (str(JDK21 / "bin/javac"), "--add-modules", "jdk.jdi",
               "-J-Djava.io.tmpdir=" + environment["TMPDIR"],
               "-d", str(classes), str(java))
    completed = subprocess.run(command, cwd=PORTABLE, env=environment,
                               capture_output=True, timeout=30, check=False)
    _require(completed.returncode == 0,
             "pinned ordinary JDI helper compilation failed")
    names = sorted(path.name for path in classes.glob("OrdinaryArithmeticProbe*.class"))
    _require(names and set(classes.rglob("*.class")) ==
             {classes / name for name in names},
             "ordinary JDI helper class inventory differs")
    return classes, _zip_checked({name: (classes / name).read_bytes()
                                  for name in names})


def _decode_json(raw):
    check_retained(raw, "report")
    return _json_privacy(raw)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate diagnostic JSON key")
        result[key] = value
    return result


def _report_bytes(report):
    encoded = (json.dumps(report, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False) + "\n").encode("utf-8")
    check_retained(encoded, "report")
    _decode_json(encoded)
    return encoded


def _archive_members(raw, required):
    check_retained(raw, "zip")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            _require(set(names) == required and len(names) == len(required),
                     "diagnostic evidence inventory differs")
            return {name: archive.read(name) for name in names}
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise DiagnosticRejected("diagnostic evidence archive is malformed") from error


def _markers(xml):
    try:
        output = ET.fromstring(xml).findall("system-out")
        _require(len(output) == 1 and output[0].text is not None,
                 "diagnostic marker output differs")
        lines = [line.removeprefix("PROSPECTIVE_ROTATION_JSON ")
                 for line in output[0].text.splitlines()
                 if line.startswith("PROSPECTIVE_ROTATION_JSON ")]
        markers = [_decode_json(line.encode()) for line in lines]
        _require(len(markers) >= CAP and all(type(row) is dict for row in markers),
                 "diagnostic marker prefix is incomplete")
        return markers
    except (ET.ParseError, UnicodeError) as error:
        raise DiagnosticRejected("diagnostic marker XML is malformed") from error


def _source_site(artifact, environment):
    with tempfile.TemporaryDirectory(dir=environment["TMPDIR"]) as directory:
        jar = Path(directory) / "artifact.jar"
        _write_checked(jar, artifact, "zip")
        command = (str(JDK21 / "bin/javap"), "-classpath", str(jar),
                   "-c", "-l", "-p", "org.dyn4j.dynamics.AbstractPhysicsBody")
        result = subprocess.run(command, env=environment, capture_output=True,
                                timeout=30, check=False)
    _require(result.returncode == 0, "pinned source caller disassembly failed")
    try:
        method = jdi_bridge._method(result.stdout.decode(),
                                    "integratePosition$lambda$0")
        sites = jdi_bridge._rotation_calls(method)
    except (UnicodeError, jdi_bridge.EvidenceRejected) as error:
        raise DiagnosticRejected("diagnostic source caller differs") from error
    _require(len(sites) == 1 and sites[0][1] == 264,
             "diagnostic source pivot site differs")
    return sites[0][0]


def _verify_loaded(raw, artifact, environment):
    try:
        with zipfile.ZipFile(io.BytesIO(artifact)) as jar:
            class_bytes = jar.read("org/dyn4j/geometry/Transform.class")
        with tempfile.TemporaryDirectory(dir=environment["TMPDIR"]) as directory:
            output = Path(directory)
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = archive.namelist()
                fixed = {"attach-ready.tsv", "cap-reached.tsv", "class.txt", "constant-pool.bin",
                         "events.tsv", "lifecycle.tsv", "methods.tsv"}
                _require(fixed <= set(names) and len(names) == len(set(names)) and
                         all(name in fixed or re.fullmatch(r"method-[0-9]+\.bin", name)
                             for name in names), "diagnostic JDI inventory differs")
                for name in names:
                    _write_checked(output / name, archive.read(name),
                                   "binary" if name.endswith(".bin") else "raw")
            result = verify_probe_code(output, class_bytes,
                                       "org.dyn4j.geometry.Transform")
            _require(result["status"] == "MATCHED_JDI_LOADED_CODE",
                     "diagnostic loaded code differs from artifact")
            cap = (output / "cap-reached.tsv").read_text().splitlines()
            _require(len(cap) == 1 and re.fullmatch(r"64\t[1-9][0-9]*", cap[0])
                     is not None, "diagnostic cap milestone differs")
            lifecycle = verify_lifecycle((output / "lifecycle.tsv").read_bytes())
            _require(lifecycle["cap_entry_reached_ns"] <=
                     int(cap[0].split("\t")[1]) < lifecycle["exits_drained_ns"],
                     "diagnostic cap acknowledgment time differs")
            attach = (output / "attach-ready.tsv").read_text().splitlines()
            _require(len(attach) == 1 and
                     attach[0] == "attached\t" + str(lifecycle["attach_ns"]),
                     "diagnostic attach milestone differs")
            return {"events": _read_checked(output / "events.tsv"),
                    "lifecycle": _read_checked(output / "lifecycle.tsv"),
                    "loader_object_id": int((output / "class.txt").read_text()
                                            .splitlines()[2]),
                    "loaded_class_sha256": hashlib.sha256(class_bytes).hexdigest()}
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        if isinstance(error, DiagnosticRejected):
            raise
        raise DiagnosticRejected("diagnostic loaded evidence is malformed") from error


def _source_identity(files, commit, environment):
    _require(type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit)
             is not None, "diagnostic source commit differs")
    resolved = subprocess.run(("git", "--no-replace-objects", "rev-parse", "HEAD"),
                              cwd=ROOT, env=environment, capture_output=True,
                              timeout=30, check=False)
    _require(resolved.returncode == 0 and resolved.stdout.decode().strip() == commit,
             "diagnostic running source revision differs")
    _verify_source_archive(files["source.zip"], commit, environment)
    fixture = ("tools/numerical/portable/src/commonTest/kotlin/portable/"
               "PortableMatrixTest.kt")
    wrapper = ("tools/numerical/portable/src/commonTest/kotlin/portable/"
               "ProspectiveArithmeticTest.kt")
    for name in (fixture, wrapper):
        current = subprocess.run(("git", "--no-replace-objects", "show",
                                  commit + ":" + name), cwd=ROOT,
                                 env=environment, capture_output=True,
                                 timeout=30, check=False)
        old = subprocess.run(("git", "--no-replace-objects", "show",
                              "89d5ea42187e993c1de8e5595707e12442cddb65:" + name),
                             cwd=ROOT, env=environment, capture_output=True,
                             timeout=30, check=False)
        _require(current.returncode == old.returncode == 0 and
                 current.stdout == old.stdout,
                 "diagnostic original fixture or selector changed")
    _require(files["artifact.jar"] == STAGED_JAR.read_bytes() and
             files["runtime-java"] == (JDK21 / "bin/java").read_bytes() and
             files["portable-classes.zip"] == actual_arithmetic._portable_classes_archive(),
             "diagnostic staged artifact or runtime changed")


def _stage_identity(files, metadata):
    expected = [str(ROOT / "gradlew"),
        ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
        ":dyn4k-core:publishJvmPublicationToStagingRepository", "--rerun-tasks",
        "--no-daemon", "--console=plain", "--offline", "--max-workers=1",
        "-Pkotlin.compiler.execution.strategy=in-process"]
    _require(metadata.get("stage_command") == expected and
             b"BUILD SUCCESSFUL" in files["stage.log"] and
             metadata.get("artifact_identity") == captured_file_identity(STAGED_JAR) and
             metadata.get("runtime_identity") ==
             captured_file_identity(JDK21 / "bin/java"),
             "diagnostic staged source or runtime identity differs")


def _process_group(process):
    _require(process is not None and process.poll() is None and
             os.getpgid(process.pid) == process.pid,
             "diagnostic owned process group differs")
    return process.pid


def _stop_owned(processes):
    def still_owned(group):
        for path in Path("/proc").iterdir():
            if not path.name.isdecimal():
                continue
            try:
                raw = (path / "stat").read_text()
                fields = raw[raw.rfind(")") + 2:].split()
                if int(fields[2]) == int(fields[3]) == group:
                    return True
            except (OSError, ValueError, IndexError):
                continue
        return False

    for process in reversed(processes):
        if not still_owned(process.pid):
            continue
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        deadline = time.monotonic() + 5
        while still_owned(process.pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        if still_owned(process.pid):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _proc_identity(pid):
    raw = (Path("/proc") / str(pid) / "stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    return {"pid": pid, "parent_pid": int(fields[1]),
            "group_pid": int(fields[2]), "session_pid": int(fields[3]),
            "start_ticks": int(fields[19]),
            "affinity": sorted(os.sched_getaffinity(pid))}


def _owned_sample(groups, phase, worker_pid=None):
    pids = []
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            raw = (path / "stat").read_text()
            fields = raw[raw.rfind(")") + 2:].split()
            group = int(fields[2])
            pid = int(path.name)
        except (OSError, ValueError, IndexError):
            continue
        if group not in groups.values():
            continue
        try:
            identity = _proc_identity(pid)
            command = (path / "cmdline").read_bytes()
            status = (path / "status").read_text()
        except (OSError, ValueError, IndexError) as error:
            raise DiagnosticRejected("UNAVAILABLE") from error
        match = re.search(r"^VmRSS:\s+([0-9]+) kB$", status, re.M)
        if pid == group:
            role = "tracer"
        elif group == groups.get("helper"):
            role = "helper" if b"OrdinaryArithmeticProbe" in command else "tracer"
        elif group == groups.get("observer"):
            role = "observer" if b"ordinary-diagnostic-observer" in command else "tracer"
        elif pid == worker_pid:
            role = "worker"
        elif any(token in command for token in
                 (b"GradleDaemon", b"gradlew", b"GradleWorkerMain")):
            role = "gradle"
        else:
            role = "tracer"
        pids.append({**identity, "roles": [role],
                     "command_sha256": hashlib.sha256(command).hexdigest(),
                     "rss_kib": int(match[1]) if match else None})
    return {"time_ns": time.monotonic_ns(), "phase": phase,
            "pids": sorted(pids, key=lambda row: row["pid"])}


def _trace_archive(prefix):
    prefix = Path(prefix)
    paths = sorted(prefix.parent.glob(prefix.name + ".*"))
    _require(paths, "diagnostic raw process trace is missing")
    members = {}
    for path in paths:
        pid = path.name.removeprefix(prefix.name + ".")
        _require(re.fullmatch(r"[1-9][0-9]*", pid) is not None,
                 "diagnostic raw trace PID differs")
        members["trace." + pid] = _read_checked(path, "trace")
    return _zip_checked(members, "trace_zip")


def _seal_existing(source, target, kind="raw"):
    _write_checked(target, _read_checked(source, kind), kind)


def _pin_child(cpus):
    os.sched_setaffinity(0, cpus)


def _run_capture_process(command, cwd, environment, log, budget,
                         samples, active, cpus, *, deadline=None):
    with Path(log).open("xb") as stream:
        process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True,
                                   preexec_fn=lambda: _pin_child(cpus))
        active.append(process)
        group = _process_group(process)
        began = time.monotonic_ns()
        identity = _proc_identity(process.pid)
        next_budget = 0
        while process.poll() is None:
            now = time.monotonic_ns()
            if now >= next_budget:
                budget.check()
                next_budget = now + 250000000
            if deadline is not None and time.monotonic_ns() - began > deadline:
                raise DiagnosticRejected("TIME_BOUND")
            sample = _owned_sample({"gradle": group}, "stage")
            if sample["pids"]:
                _sample_bound(sample)
                samples.append(sample)
            time.sleep(0.1)
        budget.check()
        _read_checked(log)
        _require(process.returncode == 0, "diagnostic source stage failed")
        active.remove(process)
        return began, time.monotonic_ns(), identity


def _allocation_ready(path, require_local_cpus=False):
    if path is None:
        return False
    try:
        allocation = _decode_json(_read_checked(path, "report"))
    except (OSError, DiagnosticRejected):
        return False
    cpus = allocation.get("cpu_set") if type(allocation) is dict else None
    return (type(allocation) is dict and
            allocation.get("schema") == "ordinary-arithmetic-resource-allocation/1" and
            allocation.get("diagnostic_runtime_allocation") == "SCHEDULED" and
            type(allocation.get("available_memory_kib")) is int and
            allocation["available_memory_kib"] > 0 and
            allocation.get("other_tasks_preserved") is True and
            type(cpus) is list and bool(cpus) and
            all(type(cpu) is int and cpu >= 0 for cpu in cpus) and
            len(cpus) == len(set(cpus)) and
            (not require_local_cpus or set(cpus) <= os.sched_getaffinity(0)))


def _sample_bound(sample):
    seen = {}
    for row in sample["pids"]:
        prior = seen.setdefault(row["pid"], row)
        _require(prior == row, "diagnostic sampled PID changed within one sample")
    if sum(row["rss_kib"] or 0 for row in seen.values()) > RSS_CEILING_KIB:
        raise DiagnosticRejected("RSS_BOUND")


def _typed_status(error):
    message = str(error)
    if message in {"TIME_BOUND", "BYTE_BOUND", "RSS_BOUND",
                   "DETACH_UNACKNOWLEDGED", "CAP_SEQUENCE_UNBOUND",
                   "UNAVAILABLE", "TARGET_FAILED", "INDEPENDENT_REPLAY_FAILED"}:
        return message
    if "timed out" in message:
        return "TIME_BOUND"
    if "bounded budget" in message or "reader bound" in message:
        return "BYTE_BOUND"
    if "JDI" in message or "detach" in message or "transport" in message:
        return "DETACH_UNACKNOWLEDGED"
    return "TARGET_FAILED"


def _replay_failure(error):
    if isinstance(error, DiagnosticRejected) and str(error) in {
            "UNAVAILABLE", "RSS_BOUND", "TIME_BOUND", "BYTE_BOUND",
            "CAP_SEQUENCE_UNBOUND"}:
        return error
    return DiagnosticRejected("INDEPENDENT_REPLAY_FAILED")


def _extract_case(xml):
    try:
        output = ET.fromstring(xml).findall("system-out")
        _require(len(output) == 1 and output[0].text is not None,
                 "diagnostic original XML output is missing")
        return _case_lines(output[0].text)
    except ET.ParseError as error:
        raise DiagnosticRejected("diagnostic original XML is malformed") from error


def _case_lines(text):
    return b"".join((line[len("NUMERICAL_JSON "):]+"\n").encode()
                    for line in text.splitlines()
                    if line.startswith("NUMERICAL_JSON "))


def _observer_command(paths):
    source = ("import hashlib,os,sys,time\n"
              "assert len(sys.argv)==5\n"
              "for path in sys.argv[1:]:\n"
              " fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)\n"
              " try:\n"
              "  with os.fdopen(fd,'rb',closefd=False) as stream:\n"
              "   for block in iter(lambda:stream.read(1048576),b''):hashlib.sha256(block).digest()\n"
              " finally:os.close(fd)\n"
              "tag='ordinary-diagnostic-observer'\n"
              "time.sleep(0.5)\n")
    return (sys.executable, "-B", "-I", "-c", source, *map(str, paths))


def _worker_descendants(raw_traces, worker_pid):
    descendants = {str(worker_pid)}
    pending = [str(worker_pid)]
    while pending:
        parent = pending.pop()
        _require(parent in raw_traces, "diagnostic worker trace is missing")
        for line in raw_traces[parent].decode("utf-8").splitlines():
            match = re.search(r"(?:clone|clone3|fork|vfork)\(.*\) = ([1-9][0-9]*)$",
                              line)
            if match and match[1] not in descendants:
                descendants.add(match[1])
                pending.append(match[1])
    return {"trace." + pid: raw_traces[pid] for pid in descendants}


def _helper_pid(raw_traces):
    selected = []
    for pid, raw in raw_traces.items():
        if any(" execve(" in line and "OrdinaryArithmeticProbe" in line and
               line.endswith(" = 0") for line in raw.decode("utf-8").splitlines()):
            selected.append(int(pid))
    _require(len(selected) == 1, "diagnostic selected helper is ambiguous")
    return selected[0]


def _collect_raw_files(output, scratch, xml, class_pattern, argument_pattern,
                       trace_prefix, helper_prefix, observer_prefix, helper_output,
                       worker_pid, budget):
    try:
        source_xml = _read_checked(xml)
    except DiagnosticRejected:
        if Path(xml).is_file() and not Path(xml).is_symlink():
            retained = Path(scratch) / "rejected-original-capture.xml"
            if not retained.exists():
                os.replace(xml, retained)
                retained.chmod(0o600)
        raise
    _write_checked(output / "capture.xml", source_xml)
    _write_checked(output / (CASE + ".jsonl"), _extract_case(source_xml))
    class_log = Path(str(class_pattern).replace("%p", str(worker_pid)))
    argument_log = Path(str(argument_pattern).replace("%p", str(worker_pid)))
    _seal_existing(class_log, output / "worker-class-load.log")
    _seal_existing(argument_log, output / "worker-arguments.log")
    all_raw = _trace_archive(trace_prefix)
    _write_checked(output / "all-process-traces.zip", all_raw, "trace_zip")
    with zipfile.ZipFile(io.BytesIO(all_raw)) as archive:
        raw_map = {name[6:]: archive.read(name) for name in archive.namelist()}
    worker_raw = _zip_checked(_worker_descendants(raw_map, worker_pid), "trace_zip")
    _write_checked(output / "worker-traces.zip", worker_raw, "trace_zip")
    helper_raw = _trace_archive(helper_prefix)
    _write_checked(output / "helper-traces.zip", helper_raw, "trace_zip")
    observer_raw = _trace_archive(observer_prefix)
    _write_checked(output / "observer-traces.zip", observer_raw, "trace_zip")
    with zipfile.ZipFile(io.BytesIO(helper_raw)) as archive:
        helper_map = {name[6:]: archive.read(name) for name in archive.namelist()}
    helper_pid = _helper_pid(helper_map)
    jdi_members = {}
    for path in helper_output.iterdir():
        _require(path.is_file() and not path.is_symlink(),
                 "diagnostic JDI output changed")
        jdi_members[path.name] = _read_checked(path)
    _require(_read_checked(helper_output.parent / "progress.tsv") ==
             jdi_members["events.tsv"],
             "diagnostic last complete observation differs")
    _write_checked(output / "jdi-evidence.zip", _zip_checked(jdi_members), "zip")
    executions = []
    for pid, raw in raw_map.items():
        for line in raw.decode("utf-8").splitlines():
            if " execve(" in line or " execveat(" in line:
                executions.append(pid + " " + line.split(" ", 1)[1])
    _write_checked(output / "execve.log",
                   ("\n".join(sorted(executions)) + "\n").encode())
    budget.check()
    return helper_pid, class_log, argument_log


def capture(output, allocation):
    output = Path(output).resolve()
    _require(output.is_absolute() and output != Path.home() and
             output.is_relative_to(Path.home().resolve()) and not output.exists(),
             "diagnostic output must be a new private home directory")
    output.mkdir(mode=0o700)
    if not _allocation_ready(allocation, require_local_cpus=True):
        report = {"schema": SCHEMA, "status": "NOT_SCHEDULED_RESOURCE",
                  "qualification": "UNPASSED", "method": METHOD, "case_id": CASE,
                  "call_cap": CAP, "runtime": "NOT_RUN"}
        _write_checked(output / "diagnostic.json", _report_bytes(report), "report")
        return report
    _seal_existing(allocation, output / "allocation.json", "report")
    reserved = _decode_json(_read_checked(output / "allocation.json", "report"))
    cpus = frozenset(reserved["cpu_set"])
    _require(cpus and cpus <= os.sched_getaffinity(0),
             "diagnostic allocated CPUs are unavailable")
    active = []
    samples = []
    private = Path(tempfile.mkdtemp(prefix="ordinary-diagnostic-",
                                    dir=os.environ["TMPDIR"]))
    private.chmod(0o700)
    generated = [ROOT / name for name in (
        "build", "dyn4k-core/build", "tools/numerical/portable/build")]
    budget = CaptureBudget(output, private, generated,
                           limit_bytes=1800 * 1024 * 1024, seconds=1200)
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    def expire_capture(_signum, _frame):
        raise DiagnosticRejected("TIME_BOUND")
    signal.signal(signal.SIGALRM, expire_capture)
    signal.setitimer(signal.ITIMER_REAL, 1200)
    metadata = None
    try:
        commit = clean_source(focused=True)
        environment = child_environment(focused=True)
        _write_checked(output / "source.zip", _source_archive(), "zip")
        environment["TMPDIR"] = str(Path(os.environ["TMPDIR"]).resolve())
        environment["JAVA_HOME"] = str(JDK21)
        environment["JAVA_TOOL_OPTIONS"] = (
            "-Djava.io.tmpdir=" + environment["TMPDIR"] + " " +
            jdi_bridge.FORK_LAUNCH_OPTION)
        _require((JDK21 / "bin/java").is_file() and
                 (JDK21 / "bin/javac").is_file(),
                 "pinned JDK 21 is unavailable")
        stage_command = [str(ROOT / "gradlew"),
            ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
            ":dyn4k-core:publishJvmPublicationToStagingRepository", "--rerun-tasks",
            "--no-daemon", "--console=plain", "--offline", "--max-workers=1",
            "-Pkotlin.compiler.execution.strategy=in-process"]
        stage_start, stage_end, stage_root = _run_capture_process(
            stage_command, ROOT, environment, private / "stage.log", budget,
            samples, active, cpus, deadline=900 * 1000000000)
        _seal_existing(private / "stage.log", output / "stage.log")
        _require(STAGED_JAR.is_file(), "diagnostic staged artifact is unavailable")
        _seal_existing(STAGED_JAR, output / "artifact.jar", "zip")
        artifact_identity = captured_file_identity(STAGED_JAR)
        _seal_existing(JDK21 / "bin/java", output / "runtime-java", "binary")
        runtime_identity = captured_file_identity(JDK21 / "bin/java")
        _write_checked(output / "portable-classes.zip",
                       actual_arithmetic._portable_classes_archive(), "zip")
        classes, compiled = compile_helper(
            (PORTABLE / "ordinary_arithmetic_jdi/OrdinaryArithmeticProbe.java").read_bytes(),
            private, environment)
        _write_checked(output / "jdi-helper-classes.zip", compiled, "zip")
        port = reserve_boolean_jdi_port()
        class_pattern = private / "worker-class-load-%p.log"
        argument_pattern = private / "worker-arguments-%p.log"
        helper_output = private / "jdi-output"
        helper_prefix = private / "helper-trace"
        trace_prefix = private / "process-trace"
        observer_prefix = private / "observer-trace"
        environment["JAVA_TOOL_OPTIONS"] += (
            f" -Xlog:arguments=info:file={argument_pattern}:pid,level,tags:filecount=0")
        tracer = ["strace", *actual_trace.rich_trace_arguments(),
                  "-o", str(trace_prefix)]
        command = gradle_test_command(tracer, "portable.ProspectiveArithmeticTest",
                                      METHOD, class_pattern)
        command.extend((f"-PportableOrdinaryJdiPort={port}",
                        f"-PportableOrdinaryJdiMethod={METHOD}", "--max-workers=1"))
        xml = (PORTABLE / "build/test-results/jvmTest/"
               "TEST-portable.ProspectiveArithmeticTest.xml")
        target_start = time.monotonic_ns()
        with (private / "gradle.log").open("xb") as stream:
            target = subprocess.Popen(command, cwd=PORTABLE, env=environment,
                                      stdout=stream, stderr=subprocess.STDOUT,
                                      start_new_session=True,
                                      preexec_fn=lambda: _pin_child(cpus))
            active.append(target)
            target_group = _process_group(target)
            target_root = _proc_identity(target.pid)
            worker_pid = None
            response_path = None
            response_identity = None
            helper = None
            helper_command = None
            socket_ready_at = None
            attach_observed_at = None
            cap_observed_at = None
            helper_exit_at = None
            worker_observed_at = None
            next_sample = 0
            next_budget = 0
            while target.poll() is None:
                now = time.monotonic_ns()
                if now >= next_budget:
                    budget.check()
                    next_budget = now + 250000000
                if now - target_start > 900 * 1000000000:
                    raise DiagnosticRejected("TIME_BOUND")
                if now >= next_sample:
                    groups = {"gradle": target_group}
                    if helper is not None and helper.poll() is None:
                        groups["helper"] = helper.pid
                    sample = _owned_sample(groups, "target", worker_pid)
                    if sample["pids"]:
                        _sample_bound(sample)
                        samples.append(sample)
                    next_sample = now + 100000000
                if response_path is None:
                    content = (private / "gradle.log").read_text(errors="replace")
                    matches = re.findall(r"@(/[^\s]+gradle-worker-classpath[^\s]+txt)",
                                         content)
                    if matches and Path(matches[-1]).is_file():
                        response_path = Path(matches[-1])
                        response_identity = captured_file_identity(response_path)
                        _seal_existing(response_path, output / "worker-classpath.txt")
                if worker_pid is None:
                    worker_pid = selected_worker_pid(trace_prefix, version6=True)
                    if worker_pid is not None:
                        worker_observed_at = now
                if (worker_pid is not None and helper is None and
                        socket_owner(Path("/proc"), worker_pid, port)):
                    socket_ready_at = now
                    helper_command = ["strace", *actual_trace.rich_trace_arguments(),
                        "-o", str(helper_prefix), str(JDK21 / "bin/java"),
                        "--add-modules", "jdk.jdi",
                        "-Djava.io.tmpdir=" + environment["TMPDIR"],
                        "-cp", str(classes), "OrdinaryArithmeticProbe", "attach",
                        str(helper_output), "127.0.0.1", str(port), "600"]
                    with (private / "helper.log").open("xb") as helper_log:
                        helper = subprocess.Popen(helper_command, cwd=PORTABLE,
                            env=environment, stdout=helper_log,
                            stderr=subprocess.STDOUT, start_new_session=True,
                            preexec_fn=lambda: _pin_child(cpus))
                        active.append(helper)
                        _process_group(helper)
                        helper_root = _proc_identity(helper.pid)
                if helper is not None:
                    if attach_observed_at is None and (
                            helper_output / "attach-ready.tsv").is_file():
                        attach_observed_at = now
                    if cap_observed_at is None and (
                            helper_output / "cap-reached.tsv").is_file():
                        cap_observed_at = now
                    if (cap_observed_at is not None and helper.poll() is None and
                            now - cap_observed_at > 10 * 1000000000):
                        raise DiagnosticRejected("DETACH_UNACKNOWLEDGED")
                    if helper.poll() is not None and helper_exit_at is None:
                        helper_exit_at = now
                        if helper.returncode != 0:
                            failure = (private / "helper.log").read_text(
                                errors="replace")
                            if any(reason in failure for reason in (
                                    "Excess pivot entry", "Unpaired pivot exit",
                                    "Incomplete cap sequence", "CAP_SEQUENCE_UNBOUND")):
                                raise DiagnosticRejected("CAP_SEQUENCE_UNBOUND")
                        _require(helper.returncode == 0 and cap_observed_at is not None,
                                 "DETACH_UNACKNOWLEDGED")
                time.sleep(0.02)
        target_exit_at = time.monotonic_ns()
        _require(target.returncode == 0 and helper is not None and
                 helper.poll() == 0 and helper_exit_at is not None and
                 worker_pid is not None and response_path is not None and
                 xml.is_file(), "TARGET_FAILED")
        active.remove(target)
        active.remove(helper)
        _seal_existing(private / "gradle.log", output / "gradle.log")
        _seal_existing(private / "helper.log", output / "helper.log")
        classpath = verify_worker_classpath(
            _read_checked(output / "worker-classpath.txt"),
            _read_checked(output / "portable-classes.zip", "zip"))
        _write_checked(output / "worker-classpath.json",
                       _report_bytes(classpath), "report")
        observer_command = ["strace", *actual_trace.rich_trace_arguments(),
            "-o", str(observer_prefix), *_observer_command((
                xml, Path(str(class_pattern).replace("%p", str(worker_pid))),
                Path(str(argument_pattern).replace("%p", str(worker_pid))),
                helper_output / "lifecycle.tsv"))]
        observer_start = time.monotonic_ns()
        with (private / "observer.log").open("xb") as stream:
            observer = subprocess.Popen(observer_command, cwd=PORTABLE,
                env=environment, stdout=stream, stderr=subprocess.STDOUT,
                start_new_session=True,
                preexec_fn=lambda: _pin_child(cpus))
            active.append(observer)
            observer_group = _process_group(observer)
            observer_root = _proc_identity(observer.pid)
            while observer.poll() is None:
                budget.check()
                sample = _owned_sample({"observer": observer_group}, "observer")
                if sample["pids"]:
                    _sample_bound(sample)
                    samples.append(sample)
                time.sleep(0.05)
        _require(observer.returncode == 0, "diagnostic output observer failed")
        active.remove(observer)
        observer_exit = time.monotonic_ns()
        _seal_existing(private / "observer.log", output / "observer.log")
        helper_pid, class_log, argument_log = _collect_raw_files(
            output, private, xml, class_pattern, argument_pattern,
            trace_prefix, helper_prefix, observer_prefix, helper_output,
            worker_pid, budget)
        _require(clean_source(focused=True) == commit,
                 "diagnostic source changed during execution")
        _require(captured_file_identity(STAGED_JAR) == artifact_identity and
                 captured_file_identity(JDK21 / "bin/java") == runtime_identity and
                 STAGED_JAR.read_bytes() == (output / "artifact.jar").read_bytes(),
                 "diagnostic staged input changed during execution")
        samples_raw = b"".join(_report_bytes(sample) for sample in samples)
        _write_checked(output / "resource-samples.jsonl", samples_raw)
        metadata = {"schema": "ordinary-arithmetic-capture/1",
            "candidate_commit": commit, "method": METHOD, "case_id": CASE,
            "call_cap": CAP, "port": port, "worker_pid": worker_pid,
            "stage_command": stage_command,
            "artifact_identity": artifact_identity,
            "runtime_identity": runtime_identity,
            "helper_pid": helper_pid, "gradle_root_pid": target.pid,
            "helper_root_pid": helper.pid, "observer_root_pid": observer.pid,
            "launch_roots": {"stage": stage_root, "target": target_root,
                             "helper": helper_root, "observer": observer_root},
            "command": command, "helper_command": helper_command,
            "observer_command": observer_command,
            "helper_output_path": str(helper_output),
            "helper_classes_path": str(classes),
            "response_path": str(response_path),
            "response_identity": response_identity,
            "xml_path": str(xml), "xml_identity": captured_file_identity(xml),
            "class_log_path": str(class_log),
            "class_log_identity": captured_file_identity(class_log),
            "argument_log_path": str(argument_log),
            "argument_log_identity": captured_file_identity(argument_log),
            "helper_class_identity": captured_file_identity(
                classes / "OrdinaryArithmeticProbe.class"),
            "target_exit_code": target.returncode,
            "helper_exit_code": helper.returncode,
            "observer_exit_code": observer.returncode,
            "supervisor_milestones_ns": {
                "stage_start": stage_start, "stage_end": stage_end,
                "gradle_start": target_start,
                "worker_observed": worker_observed_at,
                "socket_ready": socket_ready_at,
                "attach_observed": attach_observed_at,
                "cap_observed": cap_observed_at,
                "helper_exit": helper_exit_at,
                "target_exit": target_exit_at,
                "observer_start": observer_start,
                "observer_exit": observer_exit}}
        _write_checked(output / "metadata.json", _report_bytes(metadata), "report")
        try:
            report = verify_archive(output, compare_report=False)
        except Exception as error:
            failure = _replay_failure(error)
            if failure is error:
                raise
            raise failure from error
        _write_checked(output / "diagnostic.json", _report_bytes(report), "report")
        return report
    except Exception as error:
        _stop_owned(active)
        report = {"schema": SCHEMA, "status": _typed_status(error),
                  "qualification": "UNPASSED", "method": METHOD,
                  "case_id": CASE, "call_cap": CAP, "runtime": "INCOMPLETE",
                  "last_complete_observation": _last_complete_observation(private,
                                                                           output)}
        if not (output / "diagnostic.json").exists():
            _write_checked(output / "diagnostic.json", _report_bytes(report), "report")
        return report
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer != (0.0, 0.0):
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def _last_complete_observation(private, output):
    path = Path(private) / "progress.tsv"
    if not path.is_file() or path.is_symlink():
        return None
    try:
        _require(path.stat().st_size <= MAX_READER_BYTES,
                 "diagnostic progress exceeds reader bound")
        last = None
        for ordinal, line in enumerate(path.read_bytes().splitlines(keepends=True)):
            if ordinal >= CAP or not line.endswith(b"\n"):
                break
            try:
                check_retained(line, "raw")
                fields = line.decode("ascii").removesuffix("\n").split("\t")
                _require(len(fields) == 14 and fields[0] == str(ordinal) and
                         all(_number(fields[index]) >= 0 for index in
                             (1, 2, 11, 12, 13)) and
                         all(HEX64.fullmatch(fields[index]) for index in
                             range(3, 10)) and fields[10] == CALLER,
                         "diagnostic progress row differs")
            except (DiagnosticRejected, UnicodeError):
                break
            last = (ordinal, line)
        if last is None:
            return None
        name = "last-complete-observation.tsv"
        _write_checked(Path(output) / name, last[1])
        return {"ordinal": last[0], "file": name,
                "sha256": hashlib.sha256(last[1]).hexdigest()}
    except (DiagnosticRejected, UnicodeError, OSError):
        return None


def _read_samples(raw):
    check_retained(raw, "raw")
    _require(raw.endswith(b"\n"), "diagnostic sample stream is incomplete")
    return [_decode_json(line) for line in raw.splitlines()]


def _read_archive(output, compare_report):
    output = Path(output)
    required = {"artifact.jar", "runtime-java", "portable-classes.zip",
        "source.zip", "worker-classpath.json",
        "jdi-helper-classes.zip", "stage.log", "gradle.log", "helper.log",
        "observer.log", "capture.xml", CASE + ".jsonl", "worker-classpath.txt",
        "worker-class-load.log", "worker-arguments.log", "execve.log",
        "all-process-traces.zip", "worker-traces.zip", "helper-traces.zip",
        "observer-traces.zip", "jdi-evidence.zip", "resource-samples.jsonl",
        "metadata.json", "allocation.json"}
    expected = required | ({"diagnostic.json"} if compare_report else set())
    _require(output.is_dir() and not output.is_symlink() and
             {path.name for path in output.iterdir()} == expected,
             "diagnostic archive inventory differs")
    kinds = {"artifact.jar": "zip", "portable-classes.zip": "zip",
             "source.zip": "zip", "worker-classpath.json": "report",
             "runtime-java": "binary",
             "jdi-helper-classes.zip": "zip", "jdi-evidence.zip": "zip",
             "all-process-traces.zip": "trace_zip",
             "worker-traces.zip": "trace_zip", "helper-traces.zip": "trace_zip",
             "observer-traces.zip": "trace_zip", "metadata.json": "report",
             "allocation.json": "report",
             "diagnostic.json": "report"}
    return {name: _read_checked(output / name, kinds.get(name, "raw"))
            for name in expected}


def _raw_events(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        traces = {name[6:]: archive.read(name) for name in archive.namelist()}
    normalized, aborted = actual_trace.normalize_rich_traces(traces)
    _require(not aborted, "diagnostic raw process call is incomplete")
    return normalized, _events(normalized, ())


def _verify_worker_raw_subset(all_archive, worker_archive, worker_pid):
    check_retained(all_archive, "trace_zip")
    check_retained(worker_archive, "trace_zip")
    with zipfile.ZipFile(io.BytesIO(all_archive)) as archive:
        raw_all = {name[6:]: archive.read(name) for name in archive.namelist()}
    with zipfile.ZipFile(io.BytesIO(worker_archive)) as archive:
        raw_worker = {name: archive.read(name) for name in archive.namelist()}
    _require(raw_worker == _worker_descendants(raw_all, worker_pid),
             "diagnostic worker raw subset differs from complete trace")


def _prove_worker(files, metadata, all_traces, all_events):
    selected = select_worker_exec(all_traces, str(JDK21 / "bin/java"))
    _require(selected[0] == str(metadata["worker_pid"]),
             "diagnostic selected worker differs")
    executions = sorted(f"{tid} {call}" for _, tid, _, call in all_events
                        if call.startswith(("execve(", "execveat(")))
    _require(files["execve.log"] == ("\n".join(executions) + "\n").encode(),
             "diagnostic projected executions differ")
    command = metadata["command"]
    _require(type(command) is list and command[:1] == ["strace"] and
             command.count("--tests") == 1 and
             command[command.index("--tests") + 1] ==
             "portable.ProspectiveArithmeticTest." + METHOD and
             command.count("-PportableOrdinaryJdiMethod=" + METHOD) == 1 and
             command.count("-PportableOrdinaryJdiPort=" + str(metadata["port"])) == 1 and
             command.count("--max-workers=1") == 1 and
             all(command.count(flag) == 1 for flag in
                 ("--offline", "--no-daemon", "--rerun-tasks")),
             "diagnostic selected Gradle command differs")
    gradle_argv = tuple(command[command.index(str(ROOT / "gradlew")):])
    root_pids = [tid for _, tid, _, call in all_events
                 if call.startswith("execve(") and call.endswith(" = 0") and
                 successful_execve(call) == (str(ROOT / "gradlew"), gradle_argv)]
    _require(len(root_pids) == 1,
             "diagnostic Gradle execution differs")
    jdi_bridge.verify_gradle_fork_parent_v6(
        all_events, int(selected[0]), int(root_pids[0]))
    _verify_worker_raw_subset(files["all-process-traces.zip"],
                              files["worker-traces.zip"], metadata["worker_pid"])
    _require("@" + metadata["response_path"] in selected[2],
             "diagnostic worker response path differs")
    verify_stable_input(all_traces, metadata["response_path"],
                        metadata["response_identity"], selected[0],
                        files["worker-classpath.txt"], selected[1:])
    verify_worker_classpath(
        files["worker-classpath.txt"], files["portable-classes.zip"],
        _decode_json(files["worker-classpath.json"]))
    class_log = files["worker-class-load.log"].decode("utf-8")
    for class_name in ("org.dyn4j.geometry.Transform",
                       "org.dyn4j.dynamics.AbstractPhysicsBody"):
        loaded = [line for line in class_log.splitlines() if
                  class_name + " source:" in line]
        location = urlparse(loaded[0].rsplit(" source: ", 1)[-1]) if loaded else None
        _require(len(loaded) == 1 and
                 loaded[0].startswith("[" + selected[0] + "][info][class,load] ") and
                 location is not None and location.scheme == "file" and
                 not location.netloc and not location.query and not location.fragment and
                 Path(unquote(location.path)).resolve() == STAGED_JAR.resolve(),
                 "diagnostic selected loaded class provider differs")
    _require(b"-agentlib:jdwp=" in files["worker-arguments.log"] and
             ("127.0.0.1:" + str(metadata["port"])).encode() in
             files["worker-arguments.log"],
             "diagnostic effective worker arguments differ")
    worker = actual_trace.checked_projection(files["worker-traces.zip"],
        {metadata["response_path"], metadata["class_log_path"],
         metadata["argument_log_path"]}, version6_raw=True)
    witness = actual_arithmetic.verify_worker_write_witness(
        worker["legacy_zip"], files["capture.xml"], selected[0],
        files["execve.log"], complete_exec=True)
    _require(witness["status"] == "PASSED_KERNEL_WORKER_WRITES",
             "diagnostic worker output writer differs")
    return selected, witness


def _prove_helper(files, metadata, environment, worker):
    helper_source = (PORTABLE / "ordinary_arithmetic_jdi/OrdinaryArithmeticProbe.java")
    source_at_commit = subprocess.run(("git", "--no-replace-objects", "show",
        metadata["candidate_commit"] + ":" + str(helper_source.relative_to(ROOT))),
        cwd=ROOT, env=environment, capture_output=True, timeout=30, check=False)
    _require(source_at_commit.returncode == 0 and
             source_at_commit.stdout == helper_source.read_bytes(),
             "diagnostic helper source differs from commit")
    with tempfile.TemporaryDirectory(dir=environment["TMPDIR"]) as directory:
        _, compiled = compile_helper(source_at_commit.stdout, directory, environment)
    _require(compiled == files["jdi-helper-classes.zip"],
             "diagnostic executed helper class bytes differ")
    loaded = _verify_loaded(files["jdi-evidence.zip"], files["artifact.jar"],
                            environment)
    _require(loaded["loader_object_id"] > 0,
             "diagnostic loaded class loader is unavailable")
    site = _source_site(files["artifact.jar"], environment)
    markers = _markers(files["capture.xml"])
    prefix = verify_events(loaded["events"], markers, site,
                           loaded["loader_object_id"])
    lifecycle = verify_lifecycle(loaded["lifecycle"])
    argv = metadata["helper_command"]
    _require(type(argv) is list and argv[:1] == ["strace"] and
             str(JDK21 / "bin/java") in argv and
             argv[-5:] == ["attach", metadata["helper_output_path"],
                          "127.0.0.1", str(metadata["port"]), "600"],
             "diagnostic helper command differs")
    selected_argv = argv[argv.index(str(JDK21 / "bin/java")):]
    transport = jdi_bridge.verify_jdi_transport_v6(
        files["worker-traces.zip"], files["helper-traces.zip"],
        metadata["port"], metadata["worker_pid"], metadata["helper_pid"],
        selected_argv, launcher_sha256=jdi_bridge.JSPAWNHELPER_SHA256,
        protected_paths={metadata["response_path"], metadata["class_log_path"],
                         metadata["argument_log_path"]}, ordinary_diagnostic=True)
    with zipfile.ZipFile(io.BytesIO(files["jdi-evidence.zip"])) as archive:
        output_paths = {str(Path(metadata["helper_output_path"]) / name)
                        for name in archive.namelist()}
    helper = actual_trace.checked_projection(files["helper-traces.zip"],
        output_paths | {str(Path(metadata["helper_classes_path"]) /
                        "OrdinaryArithmeticProbe.class")},
        strict_outputs=output_paths, version6_raw=True)
    writes = jdi_bridge.verify_jdi_file_writes(
        helper["legacy_zip"], files["jdi-evidence.zip"],
        metadata["helper_output_path"])
    _require(writes["status"] == "MATCHED_JDI_FILE_WRITES_UNPASSED_LOADER",
             "diagnostic helper output writer differs")
    with zipfile.ZipFile(io.BytesIO(compiled)) as archive:
        main_class = archive.read("OrdinaryArithmeticProbe.class")
    helper_traces, _ = _raw_events(files["helper-traces.zip"])
    verify_stable_input(helper_traces,
        str(Path(metadata["helper_classes_path"]) / "OrdinaryArithmeticProbe.class"),
        metadata["helper_class_identity"], str(metadata["helper_pid"]),
        main_class, (selected_argv[0], tuple(selected_argv)),
        require_full_read=True)
    return prefix, lifecycle, transport


def _prove_file_writer(traces, events, root, path, data, identity, role):
    shared = actual_output_v6._shared_threads(traces, str(root), events)
    scoped = {pid: traces[pid] for pid in shared}
    scoped_events = [row for row in events if row[1] in shared]
    return actual_output_v6.prove_file_lifetime(
        scoped, scoped_events, str(root), path, data, identity, role)


def _prove_outputs(files, metadata, all_traces, all_events):
    worker = metadata["worker_pid"]
    class_writer = _prove_file_writer(all_traces, all_events, worker,
        metadata["class_log_path"], files["worker-class-load.log"],
        metadata["class_log_identity"], "worker_class_load")
    argument_writer = _prove_file_writer(all_traces, all_events, worker,
        metadata["argument_log_path"], files["worker-arguments.log"],
        metadata["argument_log_identity"], "worker_arguments")
    daemon = []
    for pid, raw in all_traces.items():
        if any(" execve(" in line and "GradleDaemon" in line and
               line.endswith(" = 0") for line in raw.decode().splitlines()):
            daemon.append(pid)
    _require(len(daemon) == 1, "diagnostic XML writer process is ambiguous")
    xml_writer = _prove_file_writer(all_traces, all_events, daemon[0],
        metadata["xml_path"], files["capture.xml"],
        metadata["xml_identity"], "worker_arguments")
    return {"xml": xml_writer, "class_load": class_writer,
            "arguments": argument_writer}


def _prove_observer(files, metadata):
    traces, events = _raw_events(files["observer-traces.zip"])
    argv = metadata["observer_command"]
    _require(type(argv) is list and argv[:1] == ["strace"] and
             sys.executable in argv and
             argv[argv.index(sys.executable):] == list(_observer_command((
                 metadata["xml_path"], metadata["class_log_path"],
                 metadata["argument_log_path"],
                 str(Path(metadata["helper_output_path"]) / "lifecycle.tsv")))),
             "diagnostic observer command differs")
    selected = [pid for pid, raw in traces.items() if any(
        " execve(" in line and "ordinary-diagnostic-observer" in line and
        line.endswith(" = 0") for line in raw.decode().splitlines())]
    _require(len(selected) == 1 and files["observer.log"] == b"" and
             any(tid == selected[0] and call == "+++ exited with 0 +++"
                 for _, tid, _, call in events),
             "diagnostic output observer did not finish")
    selected_exec = (sys.executable, tuple(_observer_command((
        metadata["xml_path"], metadata["class_log_path"],
        metadata["argument_log_path"],
        str(Path(metadata["helper_output_path"]) / "lifecycle.tsv")))))
    for path, identity, data in (
        (metadata["xml_path"], metadata["xml_identity"], files["capture.xml"]),
        (metadata["class_log_path"], metadata["class_log_identity"],
         files["worker-class-load.log"]),
        (metadata["argument_log_path"], metadata["argument_log_identity"],
         files["worker-arguments.log"])):
        verify_stable_input(traces, path, identity, selected[0], data,
                            selected_exec, require_full_read=True)
    return {"pid": int(selected[0]), "files_read": 3}


def _worker_progress_after_close(worker_traces, closed_at):
    traces, events = _raw_events(worker_traces)
    buffers = {}
    for stamp, tid, _, call in events:
        if stamp <= Decimal(closed_at) or not call.startswith("write("):
            continue
        match = re.fullmatch(r'write\(([0-9]+)<[^>]+>, ("(?:\\.|[^"\\])*"), '
                             r'[0-9]+\) = [0-9]+', call)
        if match is None:
            continue
        payload = quoted(match[2])
        key = (tid, match[1])
        pending = buffers.get(key, b"") + payload
        lines = pending.split(b"\n")
        buffers[key] = lines.pop()
        for line in lines:
            if b"NUMERICAL_JSON " not in line:
                continue
            raw = line[line.index(b"NUMERICAL_JSON ") + len(b"NUMERICAL_JSON "):]
            row = _decode_json(raw)
            if (type(row) is dict and row.get("kind") == "state" and
                    type(row.get("step")) is int and row["step"] > CAP):
                return {"step": row["step"], "raw_stamp": str(stamp),
                        "writer_tid": int(tid)}
    raise DiagnosticRejected("diagnostic worker continuation after detach is unproved")


def _resource_ownership(samples, metadata, files, allocation):
    roots = metadata.get("launch_roots")
    cpus = allocation.get("cpu_set")
    _require(type(roots) is dict and set(roots) ==
             {"stage", "target", "helper", "observer"} and
             type(cpus) is list and bool(cpus),
             "diagnostic resource launch inventory differs")
    for phase, root in roots.items():
        _require(type(root) is dict and set(root) ==
                 {"pid", "parent_pid", "group_pid", "session_pid",
                  "start_ticks", "affinity"},
                 "diagnostic resource launch identity differs")
        expected = (root["pid"] if phase == "stage" else
                    metadata.get({"target": "gradle_root_pid",
                                  "helper": "helper_root_pid",
                                  "observer": "observer_root_pid"}[phase]))
        _require(
                 root["pid"] == root["group_pid"] == root["session_pid"] == expected and
                 type(root["start_ticks"]) is int and root["start_ticks"] > 0 and
                 root["affinity"] == sorted(cpus),
                 "diagnostic resource launch identity differs")
    trace_sets = {}
    for phase, name in (("target", "all-process-traces.zip"),
                        ("helper", "helper-traces.zip"),
                        ("observer", "observer-traces.zip")):
        with zipfile.ZipFile(io.BytesIO(files[name])) as archive:
            trace_sets[phase] = {int(item.filename[6:]) for item in archive.infolist()}
    _require(metadata["worker_pid"] in trace_sets["target"] and
             metadata["helper_pid"] in trace_sets["helper"],
             "diagnostic selected resource trace differs")
    observer_traces, _ = _raw_events(files["observer-traces.zip"])
    observer_processes = [int(pid) for pid, raw in observer_traces.items()
        if any(" execve(" in line and "ordinary-diagnostic-observer" in line and
               line.endswith(" = 0") for line in raw.decode("utf-8").splitlines())]
    _require(len(observer_processes) == 1,
             "diagnostic selected observer resource identity differs")
    seen = {}
    moments = metadata["supervisor_milestones_ns"]
    intervals = {"stage": (moments["stage_start"], moments["stage_end"]),
                 "target": (moments["gradle_start"], moments["target_exit"]),
                 "observer": (moments["observer_start"], moments["observer_exit"])}
    for sample in samples:
        phase = sample["phase"]
        _require(intervals[phase][0] <= sample["time_ns"] <= intervals[phase][1],
                 "diagnostic resource sample is outside its process lifetime")
        members = {row["pid"]: row for row in sample["pids"]}
        for row in sample["pids"]:
            pid = row["pid"]
            group = row["group_pid"]
            owner = ("stage" if phase == "stage" else
                     "observer" if phase == "observer" else
                     "helper" if group == roots["helper"]["pid"] else "target")
            root = roots[owner]
            parent = members.get(row["parent_pid"])
            _require(group == root["pid"] and
                     row["session_pid"] == root["pid"] and
                     row["start_ticks"] >= root["start_ticks"] and
                     (pid == root["pid"] or parent is not None and
                      parent["start_ticks"] <= row["start_ticks"] and
                      parent["group_pid"] == group) and
                     set(row["affinity"]) <= set(cpus) and
                     (pid == root["pid"] and
                      row["start_ticks"] == root["start_ticks"] or
                      pid != root["pid"] and
                      (owner == "stage" or pid in trace_sets[owner])),
                     "diagnostic sampled PID ownership differs")
            identity = (row["start_ticks"], row["parent_pid"], group,
                        row["session_pid"], row["command_sha256"])
            _require(pid not in seen or seen[pid] == identity,
                     "diagnostic sampled PID identity changed")
            seen[pid] = identity
            roles = set(row["roles"])
            allowed = ({"gradle", "tracer"} if owner in {"stage", "target"}
                       else {"helper", "tracer"} if owner == "helper"
                       else {"observer", "tracer"})
            _require(len(roles) == 1 and
                     roles <= allowed | ({"worker"} if owner == "target" else set()) and
                     ("worker" not in roles or pid == metadata["worker_pid"]) and
                     ("helper" not in roles or pid == metadata["helper_pid"]) and
                     ("observer" not in roles or owner == "observer" and
                      pid == observer_processes[0]),
                     "diagnostic sampled PID role differs")


def _resource_evidence(samples, metadata, files, allocation):
    result = verify_resource_samples(samples)
    _resource_ownership(samples, metadata, files, allocation)
    if result["status"] != "OBSERVED_UNDER_CEILING":
        raise DiagnosticRejected(result["status"])
    peaks = {role: None for role in REQUIRED_ROLES}
    pid_peaks = {}
    for sample in result["samples"]:
        for row in sample["pids"]:
            if row["rss_kib"] is not None:
                key = str(row["pid"])
                previous = pid_peaks.get(key, {"rss_kib": 0, "roles": []})
                pid_peaks[key] = {
                    "rss_kib": max(previous["rss_kib"], row["rss_kib"]),
                    "roles": sorted(set(previous["roles"]) | set(row["roles"]))}
        for role in REQUIRED_ROLES:
            members = [row for row in sample["pids"] if role in row["roles"]]
            if members and all(row["rss_kib"] is not None for row in members):
                current = sum(row["rss_kib"] for row in members)
                peaks[role] = max(peaks[role] or 0, current)
    _require(all(value is not None for value in peaks.values()),
             "diagnostic role RSS measurement is unavailable")
    return {"sampled_aggregate_peak_kib": result["peak_aggregate_kib"],
            "observed_role_peak_kib": dict(sorted(peaks.items())),
            "observed_pid_peak_kib": dict(sorted(pid_peaks.items())),
            "samples": result["samples"],
            "physical_containment": "UNPROVED"}


def _supervisor_phases(metadata):
    moments = metadata["supervisor_milestones_ns"]
    order = ("stage_start", "stage_end", "gradle_start", "worker_observed",
             "socket_ready", "attach_observed", "cap_observed", "helper_exit",
             "target_exit", "observer_start", "observer_exit")
    poll_observations = {("worker_observed", "socket_ready"),
                         ("socket_ready", "attach_observed"),
                         ("attach_observed", "cap_observed"),
                         ("cap_observed", "helper_exit")}
    _require(type(moments) is dict and set(moments) == set(order) and
             all(type(moments[name]) is int and moments[name] > 0
                 for name in order) and
             all(moments[left] <= moments[right] if
                 (left, right) in poll_observations else
                 moments[left] < moments[right]
                 for left, right in zip(order, order[1:])),
             "diagnostic supervisor clock or process order differs")
    _require(moments["helper_exit"] - moments["cap_observed"] <=
             10 * 1000000000,
             "diagnostic detach grace elapsed")
    return {"gradle_start_to_worker_observed_ns":
                moments["worker_observed"] - moments["gradle_start"],
            "socket_ready_to_attach_observed_ns":
                moments["attach_observed"] - moments["socket_ready"],
            "detach_helper_exit_to_target_exit_ns":
                moments["target_exit"] - moments["helper_exit"],
            "observer_elapsed_ns": moments["observer_exit"] -
                moments["observer_start"]}


def verify_runtime_limits(moments, helper_phases, retained_bytes,
                          observer_archive_bytes):
    _require(type(moments) is dict and type(helper_phases) is dict and
             type(retained_bytes) is int and retained_bytes >= 0 and
             type(observer_archive_bytes) is int and observer_archive_bytes >= 0,
             "diagnostic limit inputs differ")
    _require(moments["observer_exit"] - moments["stage_start"] <=
             1200 * 1000000000 and
             moments["target_exit"] - moments["gradle_start"] <=
             900 * 1000000000 and
             helper_phases["detach_complete_ns"] - helper_phases["attach_ns"] <=
             600 * 1000000000,
             "TIME_BOUND")
    _require(retained_bytes < 1800 * 1024 * 1024 and
             observer_archive_bytes <= 128 * 1024 * 1024,
             "BYTE_BOUND")
    return {"time": "WITHIN_RETAINED_LIMITS", "bytes": "WITHIN_RETAINED_LIMITS"}


def verify_archive(output, compare_report=True):
    files = _read_archive(output, compare_report)
    metadata = _decode_json(files["metadata.json"])
    _require(type(metadata) is dict and
             metadata.get("schema") == "ordinary-arithmetic-capture/1" and
             metadata.get("method") == METHOD and metadata.get("case_id") == CASE and
             metadata.get("call_cap") == CAP and
             all(type(metadata.get(key)) is int and metadata[key] > 0 for key in
                 ("port", "worker_pid", "helper_pid", "gradle_root_pid",
                  "helper_root_pid", "observer_root_pid")) and
             all(metadata.get(key) == 0 for key in
                 ("target_exit_code", "helper_exit_code", "observer_exit_code")),
             "diagnostic capture metadata differs")
    _require(_allocation_ready(Path(output) / "allocation.json"),
             "diagnostic root resource allocation is not scheduled")
    environment = child_environment(focused=True)
    _require(clean_source(focused=True) == metadata["candidate_commit"],
             "diagnostic replay source is not clean")
    _source_identity(files, metadata["candidate_commit"], environment)
    _stage_identity(files, metadata)
    case = verify_case_output(files["capture.xml"], files[CASE + ".jsonl"],
                              metadata["target_exit_code"])
    all_traces, all_events = _raw_events(files["all-process-traces.zip"])
    selected, worker_writes = _prove_worker(files, metadata, all_traces, all_events)
    prefix, lifecycle, transport = _prove_helper(files, metadata,
                                                  environment, selected)
    output_writers = _prove_outputs(files, metadata, all_traces, all_events)
    observer = _prove_observer(files, metadata)
    continuation = _worker_progress_after_close(
        files["worker-traces.zip"], max(transport["helper_closed_at"],
            transport["worker_closed_at"], key=Decimal))
    samples = _read_samples(files["resource-samples.jsonl"])
    allocation = _decode_json(files["allocation.json"])
    resource = _resource_evidence(samples, metadata, files, allocation)
    supervisor = _supervisor_phases(metadata)
    limits = verify_runtime_limits(metadata["supervisor_milestones_ns"],
        lifecycle, sum(len(raw) for name, raw in files.items()
                       if name != "diagnostic.json"),
        len(files["observer-traces.zip"]))
    role_bytes = {
        "worker_xml_case": len(files["capture.xml"]) + len(files[CASE + ".jsonl"]),
        "worker_raw_trace": len(files["worker-traces.zip"]),
        "helper_raw_trace": len(files["helper-traces.zip"]),
        "complete_process_trace": len(files["all-process-traces.zip"]),
        "class_and_argument_logs": len(files["worker-class-load.log"]) +
                                   len(files["worker-arguments.log"]),
        "loaded_code_witness": len(files["jdi-evidence.zip"]),
        "observer_raw_trace": len(files["observer-traces.zip"]),
    }
    raw_files = {name: hashlib.sha256(raw).hexdigest()
                 for name, raw in files.items() if name != "diagnostic.json"}
    file_bytes = {name: len(raw) for name, raw in files.items()
                  if name != "diagnostic.json"}
    report = {"schema": SCHEMA, "status": "DIAGNOSTIC_ONLY",
        "qualification": "UNPASSED", "method": METHOD, "case_id": CASE,
        "call_cap": CAP, "matched_calls": prefix["matched_calls"],
        "candidate_commit": metadata["candidate_commit"],
        "artifact_sha256": raw_files["artifact.jar"],
        "runtime_java_sha256": raw_files["runtime-java"],
        "helper_classes_sha256": raw_files["jdi-helper-classes.zip"],
        "case_sha256": case["case_sha256"], "xml_sha256": case["xml_sha256"],
        "worker_pid": metadata["worker_pid"],
        "helper_pid": metadata["helper_pid"],
        "loader_object_id": _verify_loaded(files["jdi-evidence.zip"],
                              files["artifact.jar"], environment)["loader_object_id"],
        "last_observed_step": CAP, "later_calls": "UNOBSERVED",
        "post_detach_worker_progress": continuation,
        "selected_transport": "BOTH_ENDPOINTS_CLOSED_AFTER_JDI_EXCHANGE",
        "helper_exit": "ZERO_AFTER_DETACH_ACKNOWLEDGMENT",
        "case_output": "COMPLETE_ORIGINAL_36000_STEPS",
        "worker_output_writes": worker_writes["status"],
        "xml_writer_tid": output_writers["xml"]["writer_tid"],
        "observer": observer,
        "supervisor_local_phases_ns": supervisor,
        "helper_local_phases_ns": lifecycle["helper_local_phases_ns"],
        "service_ns": prefix["service_ns"],
        "retained_limits": limits,
        "role_bytes": role_bytes,
        "retained_file_bytes": file_bytes,
        "resource": resource,
        "operation_categories": {name: "UNEXERCISED" for name in
            ("pair_input", "direct_reset", "toi", "subnormal", "zero_product")},
        "instruction_choice": "AMBIGUOUS",
        "numerical_method": "UNPASSED", "public_15_method_gate": "UNPASSED",
        "raw_files_sha256": raw_files}
    encoded = _report_bytes(report)
    if compare_report:
        _require(files["diagnostic.json"] == encoded,
                 "diagnostic report differs from independent replay")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--verify")
    parser.add_argument("--output")
    parser.add_argument("--allocation")
    parser.add_argument("--method", default=METHOD)
    parser.add_argument("--call-cap", type=int, default=CAP)
    args = parser.parse_args(argv)
    validate_request(args.method, args.call_cap)
    _require(args.capture != bool(args.verify), "select one diagnostic action")
    if args.capture:
        _require(args.output is not None, "diagnostic output path is required")
        result = capture(args.output, args.allocation)
    else:
        _require(args.output is None and args.allocation is None,
                 "diagnostic replay accepts only its archive")
        result = verify_archive(args.verify)
    print(json.dumps({"schema": SCHEMA, "status": result["status"],
                      "qualification": "UNPASSED"}, sort_keys=True))
    return result


if __name__ == "__main__":
    try:
        main()
    except DiagnosticRejected as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
