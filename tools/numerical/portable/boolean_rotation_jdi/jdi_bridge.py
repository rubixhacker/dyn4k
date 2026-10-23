import ast
import io
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import zipfile

if __package__:
    from .loaded_code import verify_probe_code
    from .witness import read_probe_events
else:
    from loaded_code import verify_probe_code
    from witness import read_probe_events


JDK21 = Path("/tmp/dyn4k-tools/jdk21")
BODY_METHOD = "integratePosition$lambda$0"
JOINT_METHOD = "solvePositionConstraints"


class EvidenceRejected(ValueError):
    pass


def verify_loader_bridge(raw, transform_id, agent_id, focus):
    try:
        rows = raw.decode("ascii").splitlines(keepends=True)
        names = ("transform", "observed", "agent", "label", "ordinal",
                 "provider_count")
        if len(rows) != len(names) or any(not row.endswith("\n") for row in rows):
            raise EvidenceRejected("JDI loader bridge inventory differs")
        fields = [row[:-1].split("\t") for row in rows]
        if any(len(row) != 2 or row[0] != name
               for row, name in zip(fields, names)):
            raise EvidenceRejected("JDI loader bridge fields differ")
        values = [row[1] for row in fields]
        ids = [int(value) for value in values[:3]]
        ordinal = int(values[4])
        if (type(transform_id) is not int or type(agent_id) is not int or
                not isinstance(focus, dict) or
                ids != [transform_id, transform_id, agent_id] or
                transform_id < 0 or agent_id <= 0 or
                values[3] != focus.get("loader") or
                ordinal != focus.get("ordinal") or
                values[5] != "1" or
                (transform_id == 0) != (values[3] == "bootstrap")):
            raise EvidenceRejected("JDI loader object or witness relationship differs")
        return {"status": "MATCHED_JDI_LOADER_OBJECT", "loader_object_id": transform_id,
                "agent_loader_object_id": agent_id, "observer_label": values[3],
                "definition_ordinal": ordinal}
    except (UnicodeError, ValueError, TypeError) as error:
        if isinstance(error, EvidenceRejected):
            raise
        raise EvidenceRejected("JDI loader bridge is malformed") from error


def _method(text, name):
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines)
              if re.match(r"^  (?:public|protected|private) .*\b" +
                          re.escape(name) + r"\(", line)]
    if len(starts) != 1:
        raise EvidenceRejected("caller method inventory differs")
    start = starts[0]
    end = next((index for index in range(start + 1, len(lines))
                if re.match(r"^  (?:public|protected|private) ", lines[index])),
               len(lines))
    return lines[start:end]


def _rotation_calls(lines):
    try:
        code_end = next(index for index, line in enumerate(lines)
                        if line.strip() == "LineNumberTable:")
    except StopIteration as error:
        raise EvidenceRejected("caller line table is missing") from error
    starts = []
    for line in lines[code_end + 1:]:
        match = re.match(r"\s+line (\d+): (\d+)$", line)
        if match is None:
            break
        starts.append((int(match.group(2)), int(match.group(1))))
    if not starts or starts != sorted(starts):
        raise EvidenceRejected("caller line table differs")
    calls = []
    for line in lines[:code_end]:
        match = re.match(r"\s+(\d+): invoke(?:virtual|interface) .*"
                         r"(?:Method|InterfaceMethod) (?:[^ ]*\.)?rotateAboutCenter:\(D\)V$",
                         line)
        if match:
            offset = int(match.group(1))
            source_lines = [source for bci, source in starts if bci <= offset]
            if not source_lines:
                raise EvidenceRejected("caller has no source line")
            calls.append((offset, source_lines[-1]))
    return calls


def parse_call_sites(body_disassembly, joint_disassembly):
    body = _rotation_calls(_method(body_disassembly, BODY_METHOD))
    joint = _rotation_calls(_method(joint_disassembly, JOINT_METHOD))
    if (len(body) != 1 or body[0][1] != 264 or len(joint) != 4 or
            [line for _, line in joint] != [250, 251, 267, 269]):
        raise EvidenceRejected("focused caller source locations differ")
    return [body[0][0], joint[2][0], joint[3][0]]


def derive_call_sites(artifact):
    temporary_root = Path(os.environ.get("TMPDIR", ""))
    if not temporary_root.is_absolute() or not temporary_root.resolve().is_relative_to(
            Path.home().resolve()):
        raise EvidenceRejected("JDI temporary root is not home-backed")
    environment = os.environ.copy()
    environment.pop("OLLAMA_API_KEY", None)
    environment["JAVA_HOME"] = str(JDK21)
    environment["TMPDIR"] = str(temporary_root)
    with tempfile.TemporaryDirectory(dir=temporary_root) as scratch:
        jar = Path(scratch) / "candidate.jar"
        jar.write_bytes(artifact)
        output = []
        for name in ("org.dyn4j.dynamics.AbstractPhysicsBody",
                     "org.dyn4j.dynamics.joint.RevoluteJoint"):
            run = subprocess.run((str(JDK21 / "bin/javap"), "-classpath", str(jar),
                                  "-c", "-l", "-p", name), env=environment,
                                 capture_output=True, timeout=30, check=False)
            if run.returncode:
                raise EvidenceRejected("pinned caller disassembly failed")
            try:
                output.append(run.stdout.decode("utf-8"))
            except UnicodeError as error:
                raise EvidenceRejected("caller disassembly encoding differs") from error
    return parse_call_sites(*output)


def _require_jdk21_javac(javac, environment):
    try:
        run = subprocess.run((str(javac), "-version"), env=environment,
                             capture_output=True, text=True, timeout=10,
                             check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise EvidenceRejected("selected JDI compiler version check failed") from error
    version_lines = [line for line in (run.stdout + "\n" + run.stderr).splitlines()
                     if line.startswith("javac ")]
    if (run.returncode or len(version_lines) != 1 or
            re.fullmatch(r"javac 21(?:\.[0-9]+)*(?:[-+][A-Za-z0-9][A-Za-z0-9._+-]*)?",
                         version_lines[0]) is None):
        raise EvidenceRejected("selected JDI compiler is not JDK 21")


def compile_helper(source, temporary_root):
    temporary_root = Path(temporary_root).resolve()
    if (not temporary_root.is_relative_to(Path.home().resolve()) or
            type(source) is not bytes or not source):
        raise EvidenceRejected("JDI helper source or temporary root differs")
    temporary_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="boolean-jdi-helper-", dir=temporary_root))
    classes = workspace / "classes"
    classes.mkdir()
    java = workspace / "RotationJdiProbe.java"
    java.write_bytes(source)
    jdk = Path(os.environ.get("DYN4K_JDI_JDK_HOME", str(JDK21)))
    environment = os.environ.copy()
    environment.pop("OLLAMA_API_KEY", None)
    environment["JAVA_HOME"] = str(jdk)
    supplied_tmp = Path(os.environ.get("TMPDIR", ""))
    selected_tmp = supplied_tmp if supplied_tmp.is_absolute() and (
        supplied_tmp.resolve().is_relative_to(Path.home().resolve()) and
        len(os.fsencode(str(supplied_tmp))) <= 40) else temporary_root
    environment["TMPDIR"] = str(selected_tmp)
    javac = jdk / "bin/javac"
    _require_jdk21_javac(javac, environment)
    run = subprocess.run((str(javac), "--add-modules", "jdk.jdi",
                          "-J-Djava.io.tmpdir=" + str(selected_tmp),
                          "-d", str(classes), str(java)), env=environment,
                         capture_output=True, timeout=30, check=False)
    if run.returncode:
        raise EvidenceRejected("pinned JDI helper compilation failed")
    files = sorted(classes.glob("RotationJdiProbe*.class"))
    if not files or any(file.is_symlink() for file in files) or \
            set(classes.rglob("*.class")) != set(files):
        raise EvidenceRejected("JDI helper class inventory differs")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for file in files:
            member = zipfile.ZipInfo(file.name, date_time=(1980, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_STORED
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            archive.writestr(member, file.read_bytes())
    return classes, output.getvalue()


def verify_body_map(raw, calls):
    if type(raw) is not bytes or type(calls) is not list or \
            not calls or len(calls) % 3:
        raise EvidenceRejected("JDI body map input differs")
    try:
        rows = raw.decode("ascii").splitlines()
        if len(rows) != 3 or [row.split("\t", 1)[0] for row in rows] != [
                "b0", "b1", "integrated"]:
            raise EvidenceRejected("JDI body map inventory differs")
        values = [row.split("\t") for row in rows]
        if any(len(row) != 2 or re.fullmatch(r"[1-9][0-9]*", row[1]) is None
               for row in values):
            raise EvidenceRejected("JDI body map identity differs")
        b0, b1, integrated = (int(row[1]) for row in values)
        if b0 == b1 or integrated != b1:
            raise EvidenceRejected("JDI body relationship differs")
        for index, call in enumerate(calls):
            if type(call) is not dict or type(call.get("receiver")) is not int or \
                    call["receiver"] != (b0 if index % 3 == 1 else b1):
                raise EvidenceRejected("JDI receiver and source body differ")
    except (UnicodeError, ValueError) as error:
        if isinstance(error, EvidenceRejected):
            raise
        raise EvidenceRejected("JDI body map is malformed") from error
    return {"status": "MATCHED_BODY_RECEIVERS_UNPASSED_LOADER",
            "qualification": "UNPASSED", "calls": len(calls)}


def verify_jdi_archive(raw, class_bytes, class_name, expected_count, markers,
                       agent_bytes=None, focus=None):
    if type(raw) is not bytes or type(class_bytes) is not bytes or \
            type(class_name) is not str or type(expected_count) is not int or \
            type(markers) is not list or len(markers) != expected_count:
        raise EvidenceRejected("JDI archive input identity differs")
    required = {"body-map.tsv", "class.txt", "complete.txt",
                "constant-pool.bin", "events.tsv", "methods.tsv"}
    if agent_bytes is not None:
        required |= {"loader.tsv", "agent-code/class.txt",
                     "agent-code/constant-pool.bin", "agent-code/methods.tsv"}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if (len(names) != len(set(names)) or not required <= set(names) or
                    any(name not in required and
                        re.fullmatch(r"(?:agent-code/)?method-[0-9]+\.bin", name) is None
                        for name in names) or
                    sum(item.file_size for item in archive.infolist()) > 64 * 1024 * 1024 or
                    any(stat.S_ISLNK(item.external_attr >> 16)
                        for item in archive.infolist()) or
                    archive.testzip() is not None):
                raise EvidenceRejected("JDI archive inventory differs")
            temporary_root = Path(os.environ.get("TMPDIR", ""))
            if not temporary_root.is_absolute() or not temporary_root.resolve().is_relative_to(
                    Path.home().resolve()):
                raise EvidenceRejected("JDI temporary root is not home-backed")
            with tempfile.TemporaryDirectory(dir=temporary_root) as scratch:
                output = Path(scratch)
                for name in names:
                    (output / name).parent.mkdir(parents=True, exist_ok=True)
                    (output / name).write_bytes(archive.read(name))
                code = verify_probe_code(output, class_bytes, class_name)
                if code["status"] != "MATCHED_JDI_LOADED_CODE":
                    raise EvidenceRejected("JDI loaded code differs from artifact")
                calls = read_probe_events(output, expected_count)
                verify_body_map((output / "body-map.tsv").read_bytes(), calls)
                if len(calls) != len(markers):
                    raise EvidenceRejected("JDI call and marker counts differ")
                for call, marker in zip(calls, markers):
                    if type(marker) is not dict or any(
                            call[key] != marker.get(key) for key in
                            ("pre", "trig", "post", "angle_bits")):
                        raise EvidenceRejected("JDI operation bits differ from worker marker")
                loader = None
                if agent_bytes is not None:
                    agent_code = verify_probe_code(output / "agent-code", agent_bytes,
                                                   "dyn4k.witness.NumericClassWitness")
                    if agent_code["status"] != "MATCHED_JDI_LOADED_CODE":
                        raise EvidenceRejected("JDI agent provider bytes differ")
                    transform_id = int((output / "class.txt").read_text().splitlines()[2])
                    agent_id = int((output / "agent-code/class.txt").read_text().splitlines()[2])
                    loader = verify_loader_bridge((output / "loader.tsv").read_bytes(),
                                                  transform_id, agent_id, focus)
            return {"status": "MATCHED_JDI_BYTES_UNPASSED_ORIGIN",
                    "qualification": "UNPASSED", "calls": calls,
                    "artifact_class_sha256": code["artifact_class_sha256"],
                    "loader_bridge": loader}
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, RuntimeError,
            KeyError, IndexError) as error:
        if isinstance(error, EvidenceRejected):
            raise
        raise EvidenceRejected("JDI archive is malformed") from error


def _trace_members(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if (not names or len(names) > 1024 or len(names) != len(set(names)) or
                    any(re.fullmatch(r"trace\.[1-9][0-9]*", name) is None
                        for name in names) or
                    sum(item.file_size for item in archive.infolist()) > 128 * 1024 * 1024 or
                    archive.testzip() is not None):
                raise EvidenceRejected("JDI process trace inventory differs")
            return {int(name[6:]): archive.read(name).decode("utf-8") for name in names}
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
        raise EvidenceRejected("JDI process trace archive is malformed") from error


def _helper_descendants(helpers, root):
    descendants = {root}
    pending = [root]
    while pending:
        for line in helpers[pending.pop()].splitlines():
            if not line.startswith(("clone(", "clone3(")):
                continue
            child = re.search(r"\)\s+= ([1-9][0-9]*)$", line)
            if child is None:
                continue
            pid = int(child.group(1))
            if pid not in helpers:
                raise EvidenceRejected("JDI helper child trace is missing")
            if pid not in descendants:
                descendants.add(pid)
                pending.append(pid)
    if descendants != set(helpers):
        raise EvidenceRejected("JDI helper trace has an unrelated process")


def _worker_thread_ids(workers, root):
    parents = {}
    for parent, trace in workers.items():
        for line in trace.splitlines():
            if not line.startswith(("clone(", "clone3(")):
                continue
            child = re.search(r"\)\s+= ([1-9][0-9]*)$", line)
            if child is None:
                continue
            identity = int(child.group(1))
            if identity not in workers or identity in parents or identity == root:
                raise EvidenceRejected("JDI worker clone ancestry differs")
            flags = re.search(r"\bflags=([A-Z_0-9|]+)", line)
            names = set(flags.group(1).split("|")) if flags else set()
            same_process = {"CLONE_THREAD", "CLONE_VM", "CLONE_SIGHAND",
                            "CLONE_FILES"} <= names
            parents[identity] = (parent, same_process)
    if set(parents) != set(workers) - {root}:
        raise EvidenceRejected("JDI worker trace has an unrelated descendant")
    threads = {root}
    pending = [root]
    seen = {root}
    while pending:
        parent = pending.pop()
        for child, (owner, same_process) in parents.items():
            if owner != parent:
                continue
            if child in seen:
                raise EvidenceRejected("JDI worker clone chain is cyclic")
            seen.add(child)
            pending.append(child)
            if same_process and parent in threads:
                threads.add(child)
    if seen != set(workers):
        raise EvidenceRejected("JDI worker clone chain is disconnected")
    return threads


def _successful_exec(line):
    return (line.startswith(("execve(", "execveat(")) and
            re.search(r"\) += 0$", line) is not None)


def verify_jdi_transport(worker_archive, helper_archive, port, worker_pid,
                         helper_pid, expected_argv):
    if (type(port) is not int or not 1 <= port <= 65535 or
            type(worker_pid) is not int or worker_pid <= 0 or
            type(helper_pid) is not int or helper_pid <= 0):
        raise EvidenceRejected("JDI transport identity differs")
    workers = _trace_members(worker_archive)
    helpers = _trace_members(helper_archive)
    if worker_pid not in workers or helper_pid not in helpers:
        raise EvidenceRejected("JDI process trace PID differs")
    worker_threads = _worker_thread_ids(workers, worker_pid)
    leader_lines = workers[worker_pid].splitlines()
    selected = [index for index, line in enumerate(leader_lines)
                if (_successful_exec(line) and
                    line.startswith(f'execve("{JDK21 / "bin/java"}",') and
                    "GradleWorkerMain" in line)]
    if (len(selected) != 1 or
            any(line.startswith(("clone(", "clone3(")) and
                re.search(r"\)\s+= [1-9][0-9]*$", line)
                for line in leader_lines[:selected[0]]) or
            any(_successful_exec(line) for line in leader_lines[selected[0] + 1:]) or
            any(_successful_exec(line) for pid in worker_threads - {worker_pid}
                for line in workers[pid].splitlines())):
        raise EvidenceRejected("JDI worker program identity changed")
    if (type(expected_argv) is not list or
            any(type(value) is not str for value in expected_argv) or
            len(expected_argv) != 14 or
            expected_argv[:7] != [str(JDK21 / "bin/java"), "--add-modules",
                                  "jdk.jdi", expected_argv[3], "-cp",
                                  expected_argv[5], "RotationJdiProbe"] or
            not expected_argv[3].startswith("-Djava.io.tmpdir=") or
            expected_argv[7] != "attach" or expected_argv[9:11] != [
                "127.0.0.1", str(port)] or
            expected_argv[11:] != ["org.dyn4j.geometry.Transform", "1800", "600"] or
            any(not Path(value).is_absolute() or
                not Path(value).resolve().is_relative_to(Path.home().resolve())
                for value in (expected_argv[3].removeprefix("-Djava.io.tmpdir="),
                              expected_argv[5], expected_argv[8]))):
        raise EvidenceRejected("JDI helper command identity differs")
    _helper_descendants(helpers, helper_pid)
    helper_threads = _worker_thread_ids(helpers, helper_pid)
    executions = []
    for pid, trace in helpers.items():
        for line in trace.splitlines():
            if line.startswith("execveat(") and _successful_exec(line):
                raise EvidenceRejected("JDI helper program identity changed")
            if not line.startswith("execve(") or not _successful_exec(line):
                continue
            match = re.fullmatch(r'execve\("([^"\n]+)", (\[[^\n]+\]), .+\) += 0', line)
            if match is None:
                raise EvidenceRejected("JDI helper execution format differs")
            try:
                arguments = ast.literal_eval(match.group(2))
            except (SyntaxError, ValueError) as error:
                raise EvidenceRejected("JDI helper arguments are malformed") from error
            executions.append((pid, match.group(1), arguments))
    if executions != [(helper_pid, str(JDK21 / "bin/java"), expected_argv)]:
        raise EvidenceRejected("JDI helper execution differs")
    bind = re.compile(r'bind\((\d+), \{sa_family=AF_INET, sin_port=htons\('
                      + str(port) + r'\), sin_addr=inet_addr\("127\.0\.0\.1"\)\}, '
                      r'\d+\) += 0$')
    connect_ipv4 = re.compile(
        r'connect\((\d+), \{sa_family=AF_INET, sin_port=htons\('
        + str(port) + r'\), sin_addr=inet_addr\("127\.0\.0\.1"\)\}, '
        r'\d+\) += 0$')
    connect_mapped_ipv4 = re.compile(
        r'connect\((\d+), \{sa_family=AF_INET6, sin6_port=htons\('
        + str(port) + r'\), sin6_flowinfo=htonl\(0\), '
        r'inet_pton\(AF_INET6, "::ffff:127\.0\.0\.1", &sin6_addr\), '
        r'sin6_scope_id=0\}, 28\) += 0$')
    bound = [(pid, index, match.group(1)) for pid, trace in workers.items()
             for index, line in enumerate(trace.splitlines())
             if (match := bind.fullmatch(line))]
    listened = []
    if len(bound) == 1:
        binder, _, fd = bound[0]
        listened = [(pid, index) for pid in worker_threads
                    for index, line in enumerate(workers[pid].splitlines())
                    if re.fullmatch(r'listen\(' + re.escape(fd) +
                                    r', \d+\) += 0$', line)]
    connected = []
    for pid, trace in helpers.items():
        for line in trace.splitlines():
            if not line.startswith("connect(") or re.search(
                    r'\) += -1(?: |$)', line):
                continue
            match = connect_ipv4.fullmatch(line) or connect_mapped_ipv4.fullmatch(line)
            if match is None:
                raise EvidenceRejected("JDI helper connection format differs")
            connected.append((pid, match.group(1)))
    if (len(bound) != 1 or len(listened) != 1 or len(connected) != 1 or
            bound[0][0] not in worker_threads or listened[0][0] != bound[0][0] or
            listened[0][1] <= bound[0][1] or
            connected[0][0] not in helper_threads):
        raise EvidenceRejected("JDI worker socket or helper connection differs")
    return {"status": "MATCHED_JDI_SOCKET_SYSCALLS_UNPASSED_PROCESS",
            "qualification": "UNPASSED", "worker_socket_writer": bound[0][0],
            "worker_socket_listener": bound[0][0], "worker_tgid": worker_pid,
            "helper_connector": connected[0][0], "port": port}


def verify_jdi_file_writes(helper_archive, evidence_archive, output_path):
    output_path = Path(output_path)
    if not output_path.is_absolute() or not output_path.resolve().is_relative_to(
            Path.home().resolve()):
        raise EvidenceRejected("JDI output path differs")
    traces = _trace_members(helper_archive)
    try:
        with zipfile.ZipFile(io.BytesIO(evidence_archive)) as archive:
            names = archive.namelist()
            if not names or len(names) != len(set(names)) or archive.testzip() is not None:
                raise EvidenceRejected("JDI output inventory differs")
            expected = {str(output_path / name): archive.read(name) for name in names}
        observed = {}
        opened = set()
        for trace in traces.values():
            active = {}
            for line in trace.splitlines():
                if line.startswith("openat("):
                    match = re.fullmatch(
                        r'openat\(AT_FDCWD, "([^"\n]+)", '
                        r'O_WRONLY\|O_CREAT\|O_TRUNC(?:\|O_CLOEXEC)?, '
                        r'0?[0-7]+\) = (\d+)', line)
                    if match and match.group(1).startswith(str(output_path) + "/"):
                        path, fd = match.groups()
                        if path not in expected or path in opened or fd in active:
                            raise EvidenceRejected("JDI output provider differs")
                        opened.add(path)
                        active[fd] = [path, []]
                    elif str(output_path) + "/" in line:
                        raise EvidenceRejected("JDI output open is untrusted")
                elif line.startswith(("write(", "writev(")):
                    if line.startswith("writev("):
                        if any(re.match(r'writev\(' + fd + r'[,)]', line)
                               for fd in active):
                            raise EvidenceRejected("JDI output writev is unbound")
                        continue
                    match = re.fullmatch(
                        r'write\((\d+), ("(?:\\.|[^"\\])*"), (\d+)\) += (\d+)', line)
                    if match is None:
                        if any(re.match(r'write\(' + fd + r'[,)]', line)
                               for fd in active):
                            raise EvidenceRejected("JDI output write is incomplete")
                        continue
                    fd, literal, requested, written = match.groups()
                    if fd not in active:
                        continue
                    payload = ast.literal_eval("b" + literal)
                    if type(payload) is not bytes or len(payload) != int(requested) or \
                            int(written) != int(requested):
                        raise EvidenceRejected("JDI output write is incomplete")
                    active[fd][1].append(payload)
                elif line.startswith("close("):
                    match = re.fullmatch(r'close\((\d+)\) += 0', line)
                    if match and match.group(1) in active:
                        path, parts = active.pop(match.group(1))
                        observed[path] = b"".join(parts)
            if active:
                raise EvidenceRejected("JDI output descriptor was not closed")
        if opened != set(expected) or observed != expected:
            raise EvidenceRejected("JDI output kernel writes differ")
        return {"status": "MATCHED_JDI_FILE_WRITES_UNPASSED_LOADER",
                "qualification": "UNPASSED", "files": len(expected)}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            zipfile.BadZipFile, SyntaxError) as error:
        if isinstance(error, EvidenceRejected):
            raise
        raise EvidenceRejected("JDI output write trace is malformed") from error
