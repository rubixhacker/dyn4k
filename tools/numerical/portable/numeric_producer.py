"""Focused JVM numeric producer capture, seal, and independent raw replay."""
import argparse
import hashlib
import io
import json
import os
import platform
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import unquote, urlparse

from receipt import Rejected, digest, exact, _pairs, _reject_nonfinite
from numeric_producer_trace import Unbound, verify_transport, verify_stable_input, quoted, STRING
from numeric_class_witness import build_agent, read_witness, SCHEMA as WITNESS_SCHEMA

SCHEMA = "portable-binary64-probe-receipt/2"
METHOD = "geometryCollisionBoundaryAndScale"
CLASS = "portable.NumericProbeMatrixTest"
FIXTURE = "dd104a7e018b9d0bd77c9af14e929699d68f29fa4ac8179a5bd7d98bdc87d9ce"
ROOT = Path(__file__).resolve().parents[3]
PORTABLE = Path(__file__).resolve().parent
WRAPPER = "tools/numerical/portable/src/jvmTest/kotlin/portable/NumericProbeMatrixTest.kt"
WRAPPER_SHA256 = "6e9d5a3436f2d10f0a40606a21b8cafafb548f8911e993725b2fda97f12a260a"
OBSERVER = "tools/numerical/portable/class_witness/NumericClassWitness.java"
OBSERVER_SHA256 = "493d57d0635c6c5b519b6009250df0d82d0d97e0b065aa80160fe053b20d8983"
KEYS = {"schema", "candidate_commit", "source_sha256", "fixture_source_sha256",
        "trace_sha256", "primary_receipt_sha256", "geometry_case_sha256", "artifact_sha256",
        "runtime", "selected_test", "probe", "files", "proof"}
PROOF_KEYS = {"worker_pid", "parent_pids", "worker_argv_sha256", "worker_exit",
              "runtime_executable_sha256", "classpath_sha256", "class_archive_sha256",
              "provider_origins", "mirror_writer_tid", "mirror_fd", "mirror_destination",
              "mirror_sha256", "xml_sha256", "gradle_log_sha256", "trace_manifest_sha256",
              "class_witness"}
REQUIRED = {"gradle.log", "selected.xml", "mirror.log", "compiled-classes.zip",
            "runtime-version.log", "trace-command.json", "source.tar",
            "worker-arguments.log", "class-load.log", "classpath-inventory.json",
            "class-witness-agent.jar", "class-witness.log"}
MAX_MEMBER = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_TRACE_MEMBER = 512 * 1024 * 1024
MAX_CAPTURE_TOTAL = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 1040
SYSCALLS = ("process,open,openat,openat2,close,close_range,dup,dup2,dup3,fcntl,"
            "read,pread64,readv,preadv,lseek,fstat,newfstatat,statx,"
            "write,writev,pwrite64,pwritev,sendfile,copy_file_range,splice,mmap,munmap,rename,renameat,renameat2,unlink,unlinkat,truncate,ftruncate")


def trace_arguments():
    return ["-ff", "-ttt", "-yy", "-e", "abbrev=!fstat,newfstatat,statx",
            "-s", "131072", "-e", "trace=" + SYSCALLS]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject_nonfinite)
    except (ValueError, UnicodeError) as error:
        raise Rejected("numeric producer JSON is malformed") from error


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def captured_file_identity(path):
    status = Path(path).stat()
    return {"device_major": os.major(status.st_dev),
            "device_minor": os.minor(status.st_dev),
            "inode": status.st_ino, "size": status.st_size}


def verify_sidecar_identity(sidecar, lane, artifact):
    fields = {"host", "os", "machine", "executable", "executable_sha256",
              "version", "dependency_sha256"}
    require(isinstance(sidecar, dict) and set(sidecar) == fields and
            all(type(sidecar[field]) is str and sidecar[field] for field in fields) and
            all(sidecar[field] == lane.get(field) for field in fields) and
            sidecar["host"] == "jvm" and sidecar["dependency_sha256"] == digest(artifact),
            "sidecar runtime identity differs from full lane")


def verify_output(mirror, xml, cases):
    from prospective_compare import PROBE_VALUES, _represented_gap
    try:
        suite = ET.fromstring(xml)
    except ET.ParseError as error:
        raise Rejected("numeric producer XML is malformed") from error
    require(suite.tag == "testsuite" and all(suite.get(key) == value for key, value in
            (("tests", "1"), ("skipped", "0"), ("failures", "0"), ("errors", "0"))),
            "numeric producer selected test did not succeed")
    tests = suite.findall("testcase")
    require(len(tests) == 1 and tests[0].get("classname") == CLASS and
            tests[0].get("name") == METHOD + "[jvm]" and not list(tests[0]),
            "numeric producer selected test identity differs")
    outputs = suite.findall("system-out")
    require(len(outputs) == 1 and (outputs[0].text or "").encode() == mirror,
            "numeric producer XML and mirror differ")
    lines = mirror.splitlines(keepends=True)
    markers = [line[len(b"NUMERICAL_PROBE_JSON "):] for line in lines
               if line.startswith(b"NUMERICAL_PROBE_JSON ")]
    require(len(markers) == 1, "numeric producer probe marker count differs")
    probe = decode(markers[0])
    require(exact(probe, PROBE_VALUES), "numeric producer probe arithmetic or Boolean type differs")
    providers = [decode(line[len(b"NUMERICAL_PROVIDER_JSON "):]) for line in lines
                 if line.startswith(b"NUMERICAL_PROVIDER_JSON ")]
    require(len(providers) == 1 and set(providers[0]) == {"classpath", "effective_classpath", "providers"},
            "numeric producer provider marker differs")
    slices, headers, order = {}, {}, []
    for line in lines:
        require(line.endswith(b"\n"), "numeric producer output line is truncated")
        if line.startswith(b"NUMERICAL_JSON "):
            raw = line[len(b"NUMERICAL_JSON "):]
            row = decode(raw)
            case = row.get("id")
            require(case in cases, "numeric producer case inventory differs")
            if row.get("kind") == "inputs":
                require(case not in headers, "numeric producer duplicate case")
                headers[case] = row
                order.append(case)
            require(order and order[-1] == case, "numeric producer case ordering differs")
            slices.setdefault(case, []).append(raw)
        else:
            require(line.startswith((b"NUMERICAL_PROBE_JSON ", b"NUMERICAL_PROVIDER_JSON ")),
                    "numeric producer unknown output record")
    from run import method_case_ids
    require(order == method_case_ids(METHOD) and len(order) == 75,
            "numeric producer original case inventory differs")
    for case, rows in slices.items():
        require(b"".join(rows) == cases[case], "numeric producer full-lane case bytes differ")
    for origin, name in ((0, "OriginZero"), (3, "PositiveMillion"), (4, "NegativeMillion")):
        header = headers[f"geometry-boundary-s1-o{origin}-d3"]
        value = header["input"].get("signedZero")
        require(type(value) is float and struct.pack(">d", value).hex() == "8000000000000000",
                "numeric producer signed-zero input differs")
        gap, _ = _represented_gap(header)
        require(struct.pack(">d", gap).hex() == probe[f"boundary{name}GapBits"],
                "numeric producer represented geometry gap differs")
    return probe, providers[0]


def class_map(raw):
    require(len(raw) <= MAX_MEMBER, "compiled class archive exceeds budget")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            require(names and names == sorted(set(names)) and len(names) <= 4096,
                    "compiled class inventory differs")
            require(sum(item.file_size for item in archive.infolist()) <= MAX_MEMBER,
                    "compiled class expansion exceeds budget")
            result = {}
            for item in archive.infolist():
                require(re.fullmatch(r"(?:main|test)/[A-Za-z0-9_$/]+\.class", item.filename) and
                        item.compress_type == zipfile.ZIP_STORED and
                        item.date_time == (1980, 1, 1, 0, 0, 0),
                        "compiled class archive is not canonical")
                result[item.filename] = archive.read(item)
    except zipfile.BadZipFile as error:
        raise Rejected("compiled class archive is malformed") from error
    require({"test/portable/NumericProbeMatrixTest.class", "test/portable/PortableMatrixTest.class",
             "main/portable/NumericalRecorder.class"} <= set(result),
            "compiled fixture payload is incomplete")
    return result


def verify_call_edge(raw):
    from pulley_jdi_v2 import Reader
    reader = Reader(raw)
    require(reader.u4() == 0xCAFEBABE, "wrapper class magic differs")
    reader.take(4)
    count, index, pool = reader.u2(), 1, {}
    while index < count:
        tag = reader.u1()
        if tag == 1:
            pool[index] = (tag, reader.take(reader.u2()).decode("utf-8", "surrogateescape"))
        elif tag in (7, 8, 16, 19, 20):
            pool[index] = (tag, reader.u2())
        elif tag in (9, 10, 11, 12, 17, 18):
            pool[index] = (tag, reader.u2(), reader.u2())
        elif tag in (3, 4):
            reader.take(4)
        elif tag in (5, 6):
            reader.take(8)
            index += 1
        elif tag == 15:
            reader.take(3)
        else:
            raise Rejected("wrapper constant pool differs")
        index += 1
    def name(index):
        return pool[index][1]
    reader.take(6)
    reader.take(2 * reader.u2())
    for _ in range(reader.u2()):
        reader.take(6)
        for _ in range(reader.u2()):
            reader.take(2)
            reader.take(reader.u4())
    selected = []
    for _ in range(reader.u2()):
        reader.take(2)
        method, signature = name(reader.u2()), name(reader.u2())
        for _ in range(reader.u2()):
            attribute, body = name(reader.u2()), reader.take(reader.u4())
            if method == METHOD and signature == "()V" and attribute == "Code":
                code_reader = Reader(body)
                code_reader.take(4)
                selected.append(code_reader.take(code_reader.u4()))
    require(len(selected) == 1, "compiled selected method differs")
    code, cursor, calls = selected[0], 0, []
    sizes = {**dict.fromkeys((16, 18, *range(21, 26), *range(54, 59), 169, 188), 2),
             **dict.fromkeys((17, 19, 20, 132, *range(153, 169), *range(178, 185),
                              187, 189, 192, 193, 198, 199), 3),
             185: 5, 186: 5, 197: 4, 200: 5, 201: 5}
    while cursor < len(code):
        opcode = code[cursor]
        require(opcode not in (170, 171, 196), "selected wrapper control flow is unsupported")
        size = sizes.get(opcode, 1)
        require(cursor + size <= len(code), "wrapper bytecode is truncated")
        if opcode in (182, 183, 184):
            reference = pool[struct.unpack(">H", code[cursor + 1:cursor + 3])[0]]
            if reference[0] == 10:
                owner = name(pool[reference[1]][1])
                signature_entry = pool[reference[2]]
                if (owner, name(signature_entry[1]), name(signature_entry[2])) == (
                        "portable/PortableMatrixTest", METHOD, "()V"):
                    calls.append(cursor)
        cursor += size
    require(len(calls) == 1, "compiled original fixture direct call count differs")
    return calls[0]


def inventory(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "raw directory is absent or linked")
    result, ordinary, total = {}, 0, 0
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "raw evidence is linked")
        if path.is_dir():
            continue
        require(path.is_file(), "raw evidence is not regular")
        size = path.stat().st_size
        relative = path.relative_to(directory).as_posix()
        ordinary, total = _raw_budget(relative, size, ordinary, total)
        require(len(result) < MAX_MEMBERS, "raw evidence budget exceeded")
        result[path.relative_to(directory).as_posix()] = {"size": size, "sha256": digest(path)}
    return result


def _raw_budget(name, size, ordinary, total):
    trace = re.fullmatch(r"process/trace\.[1-9][0-9]*", name) is not None
    ordinary += 0 if trace else size
    total += size
    require(size <= (MAX_TRACE_MEMBER if trace else MAX_MEMBER) and
            ordinary <= MAX_TOTAL and total <= MAX_CAPTURE_TOTAL,
            "raw evidence budget exceeded")
    return ordinary, total


def load_raw(directory, expected):
    require(isinstance(expected, dict) and expected and len(expected) <= MAX_MEMBERS,
            "raw inventory is malformed")
    ordinary, total = 0, 0
    for name, entry in expected.items():
        require(type(name) is str and not Path(name).is_absolute() and
                ".." not in Path(name).parts and isinstance(entry, dict) and
                set(entry) == {"size", "sha256"} and type(entry["size"]) is int and
                0 <= entry["size"] and
                re.fullmatch(r"[0-9a-f]{64}", str(entry["sha256"])),
                "raw member declaration is malformed")
        ordinary, total = _raw_budget(name, entry["size"], ordinary, total)
    require(inventory(directory) == expected, "raw inventory or digest differs")
    require({path.relative_to(directory).as_posix() for path in Path(directory).rglob("*")
             if path.is_dir()} == {"process"}, "raw directory set differs")
    names = set(expected)
    process = {name for name in names if re.fullmatch(r"process/trace\.[1-9][0-9]*", name)}
    transport = names & {"worker-classpath.txt", "direct-classpath.json"}
    require(len(transport) == 1 and process and names == REQUIRED | process | transport,
            "raw member set differs")
    raw = {name: (Path(directory) / name).read_bytes() for name in names}
    require(all(sha(raw[name]) == expected[name]["sha256"] and
                len(raw[name]) == expected[name]["size"] for name in names),
            "raw file changed while reading")
    return raw


def environment(scratch):
    result = os.environ.copy()
    for key in ("OLLAMA_API_KEY", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS",
                "CLASSPATH", "JAVA_OPTS", "GRADLE_OPTS"):
        result.pop(key, None)
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    result["TMPDIR"] = str(scratch)
    result["JAVA_TOOL_OPTIONS"] = "-Djava.io.tmpdir=" + str(scratch) + " -XX:-UsePerfData"
    return result


def bounded_command(command, cwd, scratch, log, seconds=600, env=None):
    from capture_actual import CaptureBudget, run_bounded_process
    active = []
    budget = CaptureBudget(Path(scratch), Path(scratch), (Path(cwd) / "build",),
                           limit_bytes=1800 * 1024 * 1024, seconds=seconds)
    result = run_bounded_process(command, cwd, env or environment(scratch), log,
                                 budget, active)
    require(result == 0, "numeric producer child process failed")


def compile_source(source, repository, scratch):
    scratch = Path(scratch)
    checkout = scratch / "source"
    checkout.mkdir()
    try:
        with tarfile.open(fileobj=io.BytesIO(source), mode="r:") as archive:
            members = archive.getmembers()
            require(len(members) <= 30000 and sum(item.size for item in members) <= MAX_TOTAL,
                    "source archive exceeds budget")
            for member in members:
                require(not member.name.startswith("/") and ".." not in Path(member.name).parts and
                        (member.isfile() or member.isdir()), "source archive member differs")
            archive.extractall(checkout, filter="data")
    except tarfile.TarError as error:
        raise Rejected("source archive is malformed") from error
    command = [str(checkout / "gradlew"), "-p", str(checkout / "tools/numerical/portable"),
               "compileKotlinJvm", "compileTestKotlinJvm", "--offline", "--no-daemon",
               "--rerun-tasks", "--console=plain", "--max-workers=2",
               "-Pkotlin.compiler.execution.strategy=in-process",
               "-PportableRepository=" + str(repository)]
    bounded_command(command, checkout, scratch, scratch / "recompile.log")
    return archive_classes(checkout / "tools/numerical/portable/build/classes/kotlin/jvm")


def archive_classes(root):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for source_set in ("main", "test"):
            for path in sorted((Path(root) / source_set).rglob("*.class")):
                require(not path.is_symlink(), "compiled payload is linked")
                entry = zipfile.ZipInfo(path.relative_to(root).as_posix(), (1980, 1, 1, 0, 0, 0))
                archive.writestr(entry, path.read_bytes())
    return output.getvalue()


def _source(raw, commit, expected_sha):
    from actual_arithmetic import _source_archive
    source = raw["source.tar"]
    require(sha(source) == expected_sha and source == _source_archive(commit),
            "numeric producer committed source differs")
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:") as archive:
        entry = archive.extractfile(WRAPPER)
        require(entry is not None and sha(entry.read()) == WRAPPER_SHA256,
                "numeric producer reviewed wrapper source differs")
        observer = archive.extractfile(OBSERVER)
        require(observer is not None and sha(observer.read()) == OBSERVER_SHA256,
                "numeric producer reviewed observer source differs")
    return source


def _startup(traces, raw):
    calls = [line for value in traces.values() for line in value.decode().splitlines()
             if " execve(" in line and "GradleWorkerMain" in line and line.endswith(" = 0")]
    require(len(calls) == 1, "numeric producer worker invocation differs")
    match = re.search(r'execve\((' + STRING + r'), \[(.*)\], .*\) = 0$', calls[0])
    require(match is not None and "..." not in match[2], "worker argv is truncated")
    require(re.fullmatch(STRING + r"(?:, " + STRING + r")*", match[2]) is not None,
            "worker argument list is malformed")
    argv = [quoted(item).decode() for item in re.findall(STRING, match[2])]
    executable = quoted(match[1]).decode()
    response_paths = [token[1:] for token in argv if token.startswith("@")]
    if response_paths:
        require(len(response_paths) == 1 and "worker-classpath.txt" in raw and
                "direct-classpath.json" not in raw, "worker response transport differs")
        response = raw["worker-classpath.txt"]
        require(len(response) <= 65536 and b"\x00" not in response and b"#" not in response,
                "worker response grammar differs")
        tokens = []
        for argument in argv:
            tokens.extend(shlex.split(response.decode()) if argument.startswith("@") else [argument])
        response_path = response_paths[0]
    else:
        require("direct-classpath.json" in raw and decode(raw["direct-classpath.json"]) == argv,
                "direct worker argv differs")
        tokens, response_path, response = argv, None, None
    require(not any(token.startswith("@") for token in tokens), "nested response file is unsupported")
    classpaths = [tokens[index + 1] for index, token in enumerate(tokens[:-1])
                  if token in ("-cp", "-classpath", "--class-path")]
    require(len(classpaths) == 1, "worker startup classpath is ambiguous")
    return executable, argv, classpaths[0], response_path, response, tokens


def _providers(raw, observation, startup, payload, artifact, class_root, worker):
    from actual_arithmetic import _inspect_worker_classpath
    require(observation["classpath"] == startup, "executed startup classpath differs")
    maps = {source_set: {name.split("/", 1)[1]: sha(data) for name, data in payload.items()
                        if name.startswith(source_set + "/")} for source_set in ("main", "test")}
    effective = observation["effective_classpath"]
    entries = _inspect_worker_classpath(effective, artifact, class_root, maps)
    origins = observation["providers"]
    required = {CLASS: class_root / "test", "portable.PortableMatrixTest": class_root / "test",
                "portable.NumericalRecorder": class_root / "main",
                "org.dyn4j.dynamics.Body": artifact, "org.dyn4j.geometry.Geometry": artifact}
    require(set(origins) == set(required), "actual provider inventory differs")
    loaded = {}
    for line in raw["class-load.log"].decode().splitlines():
        match = re.fullmatch(r"\[([0-9]+)\]\[info\]\[class,load\] ([^ ]+) source: (.*)", line)
        require(match is not None and match[1] == worker, "class-load worker identity differs")
        if match[2] in required:
            require(match[2] not in loaded, "duplicate selected class provider")
            loaded[match[2]] = match[3]
    require(loaded == origins, "loaded and executed provider origins differ")
    for name, location in origins.items():
        url = urlparse(location)
        require(url.scheme == "file" and not url.netloc and not url.query and not url.fragment and
                Path(unquote(url.path)).resolve() == required[name].resolve(),
                "actual class provider differs")
    return entries, origins


def verify_startup_log(raw, worker, startup, agent=None, witness=None,
                       mirror=None, arguments_log=None, class_load_log=None):
    prefix = f"[{worker}][info][arguments] "
    lines = raw.decode().splitlines()
    require(len(lines) == 5 and all(line.startswith(prefix) for line in lines),
            "worker startup log PID or record count differs")
    rows = [line[len(prefix):] for line in lines]
    require(rows[0] == "VM Arguments:" and rows[1].startswith("jvm_args: ") and
            rows[2].startswith("java_command: worker.org.gradle.process.internal.worker.GradleWorkerMain ") and
            rows[3] == "java_class_path (initial): " + startup and rows[4] == "Launcher Type: SUN_STANDARD",
            "worker executed startup arguments differ")
    flags = rows[1][len("jvm_args: "):].split()
    if agent is None:
        require(not any(option in rows[1] for option in (
            "-javaagent", "-agentlib", "-agentpath", "-Xbootclasspath", "--patch-module",
            "-Djava.system.class.loader", "-XX:SharedArchiveFile")),
            "worker startup injects another code provider")
        return
    required = "-javaagent:" + str(agent) + "=" + str(witness)
    require(flags.count(required) == 1 and
            flags.count("-XX:+DisableAttachMechanism") == 1 and
            flags.count("-Xshare:off") == 1,
            "worker class witness startup guard differs")
    prefixes = ("-Djava.io.tmpdir=", "-Xlog:arguments=info:file=",
                "-Dorg.gradle.internal.worker.tmpdir=", "-Dportable.numericProbeMirror=",
                "-Xlog:class+load=info:file=")
    allowed = {required, "-XX:+DisableAttachMechanism", "-Xshare:off", "-XX:-UsePerfData",
               "-Xmx512m", "-Dfile.encoding=UTF-8", "-Duser.country",
               "-Duser.language=en", "-Duser.variant", "-ea"}
    require(all(flag in allowed or flag.startswith(prefixes) for flag in flags) and
            len(flags) == len(set(flags)), "worker startup contains an unknown or repeated option")
    for expected in ("-Dportable.numericProbeMirror=" + mirror if mirror else None,
                     "-Xlog:arguments=info:file=" + arguments_log +
                     ":pid,level,tags:filecount=0" if arguments_log else None,
                     "-Xlog:class+load=info:file=" + class_load_log +
                     ":pid,level,tags:filecount=0" if class_load_log else None):
        if expected is not None:
            require(flags.count(expected) == 1, "worker observed output option differs")


def verify_witness_loaders(definitions, loaded, helper):
    critical = {"portable/NumericProbeMatrixTest", "portable/PortableMatrixTest",
                "portable/NumericalRecorder"}
    names = {row["name"] for row in definitions}
    require(critical <= names and names == set(loaded) and
            any(name.startswith("org/dyn4j/") for name in names) and helper and
            all(row["loader"] == "system" for row in definitions),
            "class witness focused worker loader relationship differs")


def _witness(raw, source, metadata, traces, worker, payload, artifact, class_root,
             classpath_entries, executable, scratch):
    agent_path = Path(metadata["agent_path"])
    witness_path = Path(metadata["witness_path"])
    require(agent_path.is_absolute() and witness_path.is_absolute() and
            agent_path.name == "class-witness-agent.jar" and
            witness_path.name == "class-witness.log" and
            agent_path.parent == witness_path.parent and
            metadata["agent_sha256"] == sha(raw["class-witness-agent.jar"]),
            "class witness captured path or JAR differs")
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:") as archive:
        entry = archive.extractfile(OBSERVER)
        require(entry is not None, "class witness committed source is absent")
        java_source = entry.read()
    compiler = Path(executable).parents[1]
    require(compiler.resolve() == Path("/tmp/dyn4k-tools/jdk21").resolve(),
            "class witness compiler runtime differs")
    rebuilt = build_agent(java_source, compiler, scratch / "witness-rebuilt.jar",
                          scratch / "witness-compile")
    require(rebuilt == raw["class-witness-agent.jar"],
            "class witness complete JAR differs from committed source")
    input_proof = verify_stable_input(traces, str(agent_path), metadata["agent_identity"],
                                      worker, rebuilt)
    output_proof = verify_transport(traces, str(witness_path), raw["class-witness.log"],
                                    mirror_identity=metadata["witness_identity"],
                                    shared_writers=True)
    require(output_proof["worker_pid"] == worker,
            "class witness worker differs")
    expected = {name.split("/", 1)[1].removesuffix(".class"): data
                for name, data in payload.items()}
    origins = {name: class_root / source_set for source_set in ("main", "test")
               for name in (entry.split("/", 1)[1].removesuffix(".class") for entry in payload
                            if entry.startswith(source_set + "/"))}
    with zipfile.ZipFile(artifact) as engine:
        for name in engine.namelist():
            if name.startswith("org/dyn4j/") and name.endswith(".class"):
                require(name.removesuffix(".class") not in expected,
                        "class witness duplicate expected provider")
                expected[name.removesuffix(".class")] = engine.read(name)
                origins[name.removesuffix(".class")] = artifact
    result = read_witness(raw["class-witness.log"], expected)
    witnessed = {row["name"] for row in result["definitions"]}
    required = {"portable/NumericProbeMatrixTest", "portable/PortableMatrixTest",
                "portable/NumericalRecorder"}
    require(required <= witnessed, "class witness critical definition is absent")
    loaded = {}
    helper = {}
    for line in raw["class-load.log"].decode().splitlines():
        match = re.fullmatch(r"\[([0-9]+)\]\[info\]\[class,load\] ([^ ]+) source: (.*)", line)
        require(match is not None and match[1] == worker, "class witness load record differs")
        name = match[2].replace(".", "/")
        if name.startswith("dyn4k/witness/"):
            require(name not in helper, "duplicate class witness helper load")
            helper[name] = match[3]
        elif name.startswith(("portable/", "org/dyn4j/")) and "$$Lambda/" not in name:
            require(name in expected and name not in loaded,
                    "class witness loaded provider inventory differs")
            loaded[name] = match[3]
    require(set(loaded) == witnessed, "class witness callbacks and successful loads differ")
    with zipfile.ZipFile(io.BytesIO(rebuilt)) as jar:
        helpers = {name.removesuffix(".class") for name in jar.namelist()
                   if name.endswith(".class")}
    require(set(helper) == helpers, "class witness helper class inventory differs")
    verify_witness_loaders(result["definitions"], loaded, helper)
    for entry in classpath_entries:
        path = Path(entry["path"])
        if path.is_dir():
            shadow = (path / "dyn4k/witness").exists()
        else:
            with zipfile.ZipFile(path) as dependency:
                shadow = any(name.startswith("dyn4k/witness/")
                             for name in dependency.namelist())
        require(not shadow, "class witness helper shadow differs")
    for name, location in {**loaded, **helper}.items():
        expected_path = agent_path if name in helper else origins[name]
        url = urlparse(location)
        require(url.scheme == "file" and not url.netloc and not url.query and not url.fragment
                and Path(unquote(url.path)).resolve() == expected_path.resolve(),
                "class witness successful load provider differs")
    for row in result["definitions"]:
        location = urlparse(row["origin"])
        require(location.scheme == "file" and not location.netloc and
                not location.query and not location.fragment and
                Path(unquote(location.path)).resolve() == origins[row["name"]].resolve(),
                "class witness callback provider differs")
    for entry in raw["class-load.log"].decode().splitlines():
        if "[class,redefine]" in entry or "[class,retransform]" in entry:
            raise Rejected("class witness later definition differs")
    return {"schema": WITNESS_SCHEMA, "source_sha256": sha(java_source),
            "agent_sha256": sha(rebuilt), "witness_sha256": result["sha256"],
            "definition_count": len(witnessed),
            "definition_inventory_sha256": sha(encoded(result["definitions"])),
            "helper_provider": agent_path.as_uri(), "input_reads": input_proof["reads"],
            "writer_tids": output_proof["writer_tids"],
            "writer_fd": output_proof["mirror_fd"],
            "destination": output_proof["mirror_destination"]}


def _proof(raw, receipt, cases, artifacts, scratch):
    source = _source(raw, receipt["candidate_commit"], receipt["source_sha256"])
    payload = class_map(raw["compiled-classes.zip"])
    verify_call_edge(payload["test/portable/NumericProbeMatrixTest.class"])
    probe, observation = verify_output(raw["mirror.log"], raw["selected.xml"], cases)
    require(exact(probe, receipt["probe"]), "receipt probe differs from executed marker")
    metadata = decode(raw["trace-command.json"])
    require(isinstance(metadata, dict) and set(metadata) == {
        "command", "tracer", "tracer_version", "trace_arguments", "exit", "mirror", "class_root",
        "arguments_log", "class_load_log", "seconds", "bytes", "members", "compiled_before_sha256",
        "compiled_after_sha256", "mirror_identity", "sidecar_runtime", "agent_path",
        "witness_path", "agent_identity", "witness_identity", "agent_sha256"},
            "trace command schema differs")
    require(type(metadata["exit"]) is int and metadata["exit"] == 0 and
            metadata["seconds"] == 900 and metadata["bytes"] == MAX_CAPTURE_TOTAL and
            metadata["members"] == MAX_MEMBERS and
            metadata["compiled_before_sha256"] == metadata["compiled_after_sha256"] ==
            sha(raw["compiled-classes.zip"]), "capture exit, budget, or compiled payload differs")
    mirror_identity = metadata["mirror_identity"]
    require(isinstance(mirror_identity, dict) and set(mirror_identity) ==
            {"device_major", "device_minor", "inode", "size"} and
            all(type(value) is int and value >= 0 for value in mirror_identity.values()) and
            mirror_identity["size"] == len(raw["mirror.log"]),
            "original captured mirror identity is malformed")
    for name, raw_name in (("agent_identity", "class-witness-agent.jar"),
                           ("witness_identity", "class-witness.log")):
        identity = metadata[name]
        require(isinstance(identity, dict) and set(identity) ==
                {"device_major", "device_minor", "inode", "size"} and
                all(type(value) is int and value >= 0 for value in identity.values()) and
                identity["size"] == len(raw[raw_name]),
                "class witness captured file identity is malformed")
    traces = {name.split(".")[-1]: data for name, data in raw.items() if name.startswith("process/")}
    executable, argv, startup, response_path, response, tokens = _startup(traces, raw)
    runtime = receipt["runtime"]
    require(executable == runtime.get("executable") and Path(executable).is_file() and
            digest(executable) == runtime.get("executable_sha256"), "worker runtime executable differs")
    proof = verify_transport(traces, metadata["mirror"], raw["mirror.log"], response_path,
                             response, mirror_identity=mirror_identity)
    require(proof["parent_pids"], "worker ancestry does not reach traced invocation")
    root = proof["parent_pids"][-1]
    require(any(line.endswith(" +++ exited with 0 +++") for line in traces[root].decode().splitlines()),
            "traced Gradle root did not exit successfully")
    command = metadata["command"]
    require(isinstance(command, list) and all(type(item) is str for item in command),
            "capture command type differs")
    selectors = [command[index + 1] for index, token in enumerate(command[:-1]) if token == "--tests"]
    require(selectors == [CLASS + "." + METHOD] and command[0] == str(ROOT / "gradlew") and
            "jvmTest" in command and "--rerun-tasks" in command and "--no-daemon" in command and
            "-PportableRepository=" + str(ROOT / "build/staging-repository") in command and
            "-PportableNumericProbeMirror=" + metadata["mirror"] in command and
            "-PportableClassWitnessAgent=" + metadata["agent_path"] in command and
            "-PportableClassWitnessOutput=" + metadata["witness_path"] in command,
            "capture command or selected task differs")
    require(any("execve(" + json.dumps(command[0]) + ", " + json.dumps(command) + ", " in line and
                line.endswith(" = 0") for line in traces[root].decode().splitlines()),
            "traced root invocation differs")
    require(metadata["trace_arguments"] == trace_arguments(), "tracer invocation differs")
    verify_startup_log(raw["worker-arguments.log"], proof["worker_pid"], startup,
                       metadata["agent_path"], metadata["witness_path"], metadata["mirror"],
                       metadata["arguments_log"].replace(proof["worker_pid"], "%p"),
                       metadata["class_load_log"].replace(proof["worker_pid"], "%p"))
    require(all(tokens.count(option) == 1 for option in (
                "-javaagent:" + metadata["agent_path"] + "=" + metadata["witness_path"],
                "-XX:+DisableAttachMechanism", "-Xshare:off")),
            "traced worker guard arguments differ")
    for field, file in (("arguments_log", "worker-arguments.log"), ("class_load_log", "class-load.log")):
        verify_transport(traces, metadata[field], raw[file], exclusive=False, ordered=False)
    from run import _java_version_line
    version = subprocess.CompletedProcess([], 0, raw["runtime-version.log"].decode(), "")
    require(_java_version_line(version) == runtime.get("version"),
            "sidecar runtime version differs from lane")
    verify_sidecar_identity(metadata["sidecar_runtime"], runtime, artifacts["target"])
    require(metadata["sidecar_runtime"]["executable"] == executable and
            metadata["sidecar_runtime"]["executable_sha256"] == digest(executable),
            "sidecar worker executable differs")
    require("BUILD SUCCESSFUL" in raw["gradle.log"].decode(), "Gradle success record is absent")
    class_root = Path(metadata["class_root"])
    require(class_root == PORTABLE / "build/classes/kotlin/jvm", "compiled provider root differs")
    require(archive_classes(class_root) == raw["compiled-classes.zip"],
            "current compiled payload differs")
    entries, origins = _providers(raw, observation, startup, payload, Path(artifacts["target"]),
                                  class_root, proof["worker_pid"])
    require(exact(decode(raw["classpath-inventory.json"]), entries),
            "captured effective classpath bytes changed")
    require(all(any(entry["path"] == item for entry in entries) for item in startup.split(os.pathsep)),
            "startup classpath entry absent from effective classpath")
    # Replay recompilation from the committed archive, never from a receipt assertion.
    rebuilt = compile_source(source, ROOT / "build/staging-repository", scratch)
    require(class_map(rebuilt) == payload, "independent deterministic recompilation differs")
    proof["class_witness"] = _witness(raw, source, metadata, traces, proof["worker_pid"],
                                      payload, Path(artifacts["target"]), class_root,
                                      entries, executable, scratch)
    proof.update({"runtime_executable_sha256": digest(executable),
                  "classpath_sha256": sha(encoded(entries)),
                  "class_archive_sha256": sha(raw["compiled-classes.zip"]),
                  "provider_origins": origins, "xml_sha256": sha(raw["selected.xml"]),
                  "gradle_log_sha256": sha(raw["gradle.log"]),
                  "trace_manifest_sha256": sha(encoded({tid: sha(data) for tid, data in traces.items()}))})
    return proof


def _validate_proof(proof):
    require(isinstance(proof, dict) and set(proof) == PROOF_KEYS,
            "numeric producer proof schema differs")
    pid = lambda value: type(value) is str and re.fullmatch(r"[1-9][0-9]*", value) is not None
    digests = ("worker_argv_sha256", "runtime_executable_sha256", "classpath_sha256",
               "class_archive_sha256", "mirror_sha256", "xml_sha256",
               "gradle_log_sha256", "trace_manifest_sha256")
    providers = {CLASS, "portable.PortableMatrixTest", "portable.NumericalRecorder",
                 "org.dyn4j.dynamics.Body", "org.dyn4j.geometry.Geometry"}
    require(pid(proof["worker_pid"]) and type(proof["parent_pids"]) is list and
            proof["parent_pids"] and all(pid(value) for value in proof["parent_pids"]) and
            len(set(proof["parent_pids"])) == len(proof["parent_pids"]) and
            proof["worker_pid"] not in proof["parent_pids"] and
            type(proof["worker_exit"]) is int and proof["worker_exit"] == 0 and
            pid(proof["mirror_writer_tid"]) and type(proof["mirror_fd"]) is str and
            re.fullmatch(r"[0-9]+", proof["mirror_fd"]) is not None and
            type(proof["mirror_destination"]) is str and
            Path(proof["mirror_destination"]).is_absolute() and
            isinstance(proof["provider_origins"], dict) and
            set(proof["provider_origins"]) == providers and
            all(type(value) is str and value.startswith("file:/")
                for value in proof["provider_origins"].values()) and
            all(type(proof[field]) is str and re.fullmatch(r"[0-9a-f]{64}", proof[field])
                for field in digests), "numeric producer proof field differs")
    witness = proof["class_witness"]
    require(isinstance(witness, dict) and set(witness) == {
                "schema", "source_sha256", "agent_sha256", "witness_sha256",
                "definition_count", "definition_inventory_sha256", "helper_provider",
                "input_reads", "writer_tids", "writer_fd", "destination"} and
            witness["schema"] == WITNESS_SCHEMA and
            all(type(witness[field]) is str and re.fullmatch(r"[0-9a-f]{64}", witness[field])
                for field in ("source_sha256", "agent_sha256", "witness_sha256",
                              "definition_inventory_sha256")) and
            type(witness["definition_count"]) is int and witness["definition_count"] >= 3 and
            type(witness["input_reads"]) is int and witness["input_reads"] > 0 and
            type(witness["helper_provider"]) is str and witness["helper_provider"].startswith("file:/") and
            type(witness["writer_tids"]) is list and witness["writer_tids"] and
            all(pid(value) for value in witness["writer_tids"]) and
            witness["writer_tids"] == sorted(set(witness["writer_tids"])) and
            type(witness["writer_fd"]) is str and
            re.fullmatch(r"[0-9]+", witness["writer_fd"]) is not None and
            type(witness["destination"]) is str and Path(witness["destination"]).is_absolute(),
            "class witness proof field differs")


def verify(lane, commit, source_sha256, trace_sha256, artifacts, runtime, *, scratch=None):
    lane = Path(lane)
    receipt_path = lane / "numeric-probe-receipt.json"
    require(receipt_path.is_file() and not receipt_path.is_symlink() and
            receipt_path.stat().st_size <= 1024 * 1024, "numeric producer receipt is absent or linked")
    receipt = decode(receipt_path.read_bytes())
    require(isinstance(receipt, dict) and set(receipt) == KEYS and receipt["schema"] == SCHEMA,
            "numeric producer receipt schema differs")
    require(receipt["candidate_commit"] == commit and receipt["source_sha256"] == source_sha256 and
            receipt["fixture_source_sha256"] == FIXTURE, "numeric producer source identity differs")
    require(receipt["trace_sha256"] == trace_sha256 and
            receipt["primary_receipt_sha256"] == digest(lane / "receipt.json"),
            "numeric producer full-lane receipt differs")
    require(receipt["artifact_sha256"] == {name: digest(path) for name, path in artifacts.items()} and
            receipt["runtime"] == runtime, "numeric producer artifact or runtime differs")
    require(receipt["selected_test"] == {"class": CLASS, "method": METHOD,
            "task": "jvmTest", "host": "jvm"} and lane.name == "jvm",
            "numeric producer selected identity differs")
    require(type(runtime.get("method_executions")) is int and runtime["method_executions"] == 15,
            "numeric producer lane is not complete")
    from run import method_case_ids
    from cases import declared_cases
    all_ids = {case["id"] for case in declared_cases()}
    require(len(all_ids) == 332 and {path.stem for path in (lane / "cases").glob("*.jsonl")} == all_ids,
            "numeric producer full 332-case lane is absent")
    cases = {case: (lane / "cases" / (case + ".jsonl")).read_bytes() for case in method_case_ids(METHOD)}
    require(receipt["geometry_case_sha256"] == {case: sha(raw) for case, raw in cases.items()},
            "numeric producer geometry slice digest differs")
    _validate_proof(receipt["proof"])
    raw = load_raw(lane / "numeric-probe", receipt["files"])
    if scratch is None:
        scratch = Path(tempfile.mkdtemp(prefix="numeric-replay-", dir=lane.parent)) / "rebuild"
    scratch = Path(scratch).resolve()
    require(scratch.is_relative_to(Path.home().resolve()) and not scratch.exists(),
            "numeric producer replay scratch must be a new home-backed directory")
    scratch.mkdir(parents=True)
    try:
        proof = _proof(raw, receipt, cases, artifacts, scratch)
    except Unbound as error:
        raise Rejected("sealed numeric producer proof cannot be replayed: " + str(error)) from error
    require(exact(proof, receipt["proof"]), "numeric producer recomputed proof differs")
    require(inventory(lane / "numeric-probe") == receipt["files"], "raw evidence changed during replay")
    return {"status": "PASSED_BOUND_PRODUCER", "proof": proof["class_witness"]}


def capture(output, scratch):
    from actual_arithmetic import _source_archive
    from capture_actual import CaptureBudget, stop_capture_process
    from run import clean_identity, method_command
    output, scratch = Path(output).resolve(), Path(scratch).resolve()
    require(not output.exists() and not scratch.exists() and
            output.is_relative_to(Path.home().resolve()) and
            scratch.is_relative_to(Path.home().resolve()), "capture paths must be new and home-backed")
    commit, source_sha = clean_identity()
    output.mkdir(parents=True, mode=0o700)
    output.chmod(0o700)
    scratch.mkdir(parents=True)
    (output / "process").mkdir()
    env = environment(scratch)
    build = [str(ROOT / "gradlew"), "-p", str(PORTABLE), "compileKotlinJvm", "compileTestKotlinJvm",
             "--rerun-tasks", "--offline", "--no-daemon", "--console=plain", "--max-workers=2",
             "-Pkotlin.compiler.execution.strategy=in-process",
             "-PportableRepository=" + str(ROOT / "build/staging-repository")]
    bounded_command(build, ROOT, scratch, scratch / "compile.log", env=env)
    class_root = PORTABLE / "build/classes/kotlin/jvm"
    before = archive_classes(class_root)
    class_map(before)
    (output / "compiled-classes.zip").write_bytes(before)
    source = _source_archive(commit)
    require(sha(source) == source_sha, "capture source archive differs")
    (output / "source.tar").write_bytes(source)
    agent = output / "class-witness-agent.jar"
    witness = output / "class-witness.log"
    build_agent((PORTABLE / "class_witness/NumericClassWitness.java").read_bytes(),
                Path(os.environ["JAVA_HOME"]), agent, scratch / "witness-compile")
    agent_identity = captured_file_identity(agent)
    agent_sha = digest(agent)
    mirror = output / "mirror.log"
    argument_pattern = scratch / "arguments-%p.log"
    class_pattern = scratch / "classes-%p.log"
    env["JAVA_TOOL_OPTIONS"] += (
        " -Xlog:arguments=info:file=" + str(argument_pattern) + ":pid,level,tags:filecount=0")
    command, _ = method_command("jvm", METHOD, output)
    command[command.index("--tests") + 1] = CLASS + "." + METHOD
    command += ["--offline", "--max-workers=2", "-Pkotlin.compiler.execution.strategy=in-process",
                "-PportableNumericProbeMirror=" + str(mirror),
                "-PportableWorkerClassLoadLog=" + str(class_pattern),
                "-PportableClassWitnessAgent=" + str(agent),
                "-PportableClassWitnessOutput=" + str(witness)]
    tracer = shutil.which("strace")
    require(tracer is not None, "strace is unavailable")
    version = subprocess.run([tracer, "--version"], env=env, capture_output=True,
                             check=True, timeout=10).stdout.decode()
    tracer_arguments = trace_arguments()
    invocation = [tracer, *tracer_arguments, "-o", str(output / "process/trace"), *command]
    budget = CaptureBudget(output, scratch, (PORTABLE / "build",),
                           limit_bytes=MAX_CAPTURE_TOTAL, seconds=900)
    response_source = None
    with (output / "gradle.log").open("xb") as log:
        process = subprocess.Popen(invocation, cwd=ROOT, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while process.poll() is None:
                budget.check()
                require(len(list(output.rglob("*"))) <= MAX_MEMBERS, "capture member budget exceeded")
                for trace in (output / "process").glob("trace.*"):
                    require(trace.stat().st_size <= MAX_TRACE_MEMBER, "capture trace member exceeds budget")
                    for line in trace.read_text(errors="strict").splitlines():
                        if "GradleWorkerMain" in line and "execve(" in line:
                            matches = re.findall(r'"@([^" ]+)"', line)
                            if matches and Path(matches[0]).is_file():
                                require(len(matches) == 1, "multiple worker response files")
                                data = Path(matches[0]).read_bytes()
                                require(len(data) <= 65536, "worker response exceeds budget")
                                retained = output / "worker-classpath.txt"
                                if retained.exists():
                                    require(retained.read_bytes() == data and response_source == matches[0],
                                            "live response file changed")
                                else:
                                    retained.write_bytes(data)
                                    response_source = matches[0]
                time.sleep(0.1)
            budget.check()
        finally:
            stop_capture_process(process)
    require(process.returncode == 0, "focused selected invocation failed")
    require(captured_file_identity(agent) == agent_identity and digest(agent) == agent_sha and
            witness.is_file(), "class witness agent input or output changed")
    after = archive_classes(class_root)
    require(after == before, "compiled payload changed during selected invocation")
    traces = {path.name.split(".")[-1]: path.read_bytes() for path in (output / "process").glob("trace.*")}
    calls = [(tid, line) for tid, data in traces.items() for line in data.decode().splitlines()
             if " execve(" in line and "GradleWorkerMain" in line and line.endswith(" = 0")]
    require(len(calls) == 1, "selected worker count differs")
    worker, call = calls[0]
    invocation_match = re.search(r'execve\((' + STRING + r'), \[(.*)\], .*\) = 0$', call)
    require(invocation_match is not None, "selected worker arguments unavailable")
    executable = quoted(invocation_match[1]).decode()
    argv = [quoted(value).decode() for value in re.findall(STRING, invocation_match[2])]
    if not any(value.startswith("@") for value in argv):
        (output / "direct-classpath.json").write_bytes(encoded(argv))
    require((output / "worker-classpath.txt").exists() or
            (output / "direct-classpath.json").exists(), "live response capture missed worker")
    for source_path, name in ((PORTABLE / "build/test-results/jvmTest" / ("TEST-" + CLASS + ".xml"),
                              "selected.xml"),
                             (Path(str(argument_pattern).replace("%p", worker)), "worker-arguments.log"),
                             (Path(str(class_pattern).replace("%p", worker)), "class-load.log")):
        require(source_path.is_file() and source_path.stat().st_size <= MAX_MEMBER,
                "required selected worker raw output unavailable")
        shutil.copyfile(source_path, output / name)
    from run import artifacts
    retained = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
    _, _, startup, _, _, _ = _startup(traces, retained)
    observations = [decode(line[len(b"NUMERICAL_PROVIDER_JSON "):])
                    for line in retained["mirror.log"].splitlines()
                    if line.startswith(b"NUMERICAL_PROVIDER_JSON ")]
    require(len(observations) == 1, "capture provider observation is missing")
    entries, _ = _providers(retained, observations[0], startup, class_map(before),
                            artifacts("jvm")["target"], class_root, worker)
    (output / "classpath-inventory.json").write_bytes(encoded(entries))
    bounded_command([executable, "-version"], ROOT, scratch, output / "runtime-version.log", 10)
    from run import _java_version_line
    version_output = (output / "runtime-version.log").read_text()
    runtime_version = _java_version_line(subprocess.CompletedProcess([], 0, version_output, ""))
    dependency = artifacts("jvm")["target"]
    sidecar_runtime = {"host": "jvm", "os": platform.platform(),
                       "machine": platform.machine(), "executable": executable,
                       "executable_sha256": digest(executable), "version": runtime_version,
                       "dependency_sha256": digest(dependency)}
    metadata = {"command": command, "tracer": tracer, "tracer_version": version,
                "trace_arguments": tracer_arguments, "exit": process.returncode,
                "mirror": str(mirror), "class_root": str(class_root),
                "arguments_log": str(argument_pattern).replace("%p", worker),
                "class_load_log": str(class_pattern).replace("%p", worker),
                "seconds": 900, "bytes": MAX_CAPTURE_TOTAL, "members": MAX_MEMBERS,
                "compiled_before_sha256": sha(before), "compiled_after_sha256": sha(after),
                "mirror_identity": captured_file_identity(mirror),
                "sidecar_runtime": sidecar_runtime,
                "agent_path": str(agent), "witness_path": str(witness),
                "agent_identity": agent_identity,
                "witness_identity": captured_file_identity(witness),
                "agent_sha256": agent_sha}
    (output / "trace-command.json").write_bytes(encoded(metadata))
    load_raw(output, inventory(output))
    require(clean_identity() == (commit, source_sha), "source changed during capture")
    return {"candidate_commit": commit, "source_sha256": source_sha, "files": inventory(output)}


def seal(captured, lane, baseline, attestation, scratch):
    from run import artifacts, clean_identity
    from prospective_compare import compare_host
    from run import comparison_coverage
    lane, captured = Path(lane), Path(captured)
    require(lane.name == "jvm" and not (lane / "numeric-probe-receipt.json").exists() and
            not (lane / "numeric-probe").exists(), "numeric producer lane is already sealed")
    # The full comparator validates source, artifacts, runtime, reference, and 332-case coverage.
    compare_host(baseline, lane, comparison_coverage()["frozen_case_ids"], attestation)
    primary = decode((lane / "receipt.json").read_bytes())
    commit, source_sha = clean_identity()
    from run import method_case_ids
    cases = {case: (lane / "cases" / (case + ".jsonl")).read_bytes() for case in method_case_ids(METHOD)}
    files = inventory(captured)
    raw = load_raw(captured, files)
    metadata = decode(raw["trace-command.json"])
    require(isinstance(metadata, dict) and
            metadata.get("mirror_identity") == captured_file_identity(captured / "mirror.log"),
            "original captured mirror file identity differs")
    probe, _ = verify_output(raw["mirror.log"], raw["selected.xml"], cases)
    receipt = {"schema": SCHEMA, "candidate_commit": commit, "source_sha256": source_sha,
               "fixture_source_sha256": FIXTURE, "trace_sha256": primary["trace_sha256"],
               "primary_receipt_sha256": digest(lane / "receipt.json"),
               "geometry_case_sha256": {case: sha(data) for case, data in cases.items()},
               "artifact_sha256": primary["artifact_sha256"], "runtime": primary["runtime"],
               "selected_test": {"class": CLASS, "method": METHOD, "task": "jvmTest", "host": "jvm"},
               "probe": probe, "files": files}
    scratch = Path(scratch).resolve()
    require(not scratch.exists() and scratch.is_relative_to(Path.home().resolve()),
            "seal scratch must be new and home-backed")
    scratch.mkdir(parents=True)
    receipt["proof"] = _proof(raw, receipt, cases, artifacts("jvm"), scratch)
    require(inventory(captured) == files, "capture changed during seal")
    shutil.copytree(captured, lane / "numeric-probe")
    require(inventory(lane / "numeric-probe") == files, "sealed copy differs")
    with (lane / "numeric-probe-receipt.json").open("xb") as stream:
        stream.write(encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--output", type=Path, required=True)
    capture_parser.add_argument("--scratch", type=Path, required=True)
    seal_parser = commands.add_parser("seal")
    seal_parser.add_argument("--captured", type=Path, required=True)
    seal_parser.add_argument("--lane", type=Path, required=True)
    seal_parser.add_argument("--baseline", type=Path, required=True)
    seal_parser.add_argument("--attestation", type=Path, required=True)
    seal_parser.add_argument("--scratch", type=Path, required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--lane", type=Path, required=True)
    verify_parser.add_argument("--baseline", type=Path, required=True)
    verify_parser.add_argument("--attestation", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "capture":
        result = capture(args.output, args.scratch)
    elif args.mode == "seal":
        result = seal(args.captured, args.lane, args.baseline, args.attestation, args.scratch)
    else:
        from prospective_compare import compare_host
        from run import comparison_coverage
        result = compare_host(args.baseline, args.lane, comparison_coverage()["frozen_case_ids"], args.attestation)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
