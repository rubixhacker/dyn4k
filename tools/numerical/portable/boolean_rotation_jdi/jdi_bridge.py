import ast
import hashlib
import io
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import zipfile
from decimal import Decimal

if __package__:
    from .loaded_code import verify_probe_code
    from .witness import read_probe_events
else:
    from loaded_code import verify_probe_code
    from witness import read_probe_events


JDK21 = Path("/tmp/dyn4k-tools/jdk21")
JSPAWNHELPER = JDK21 / "lib/jspawnhelper"
JSPAWNHELPER_SHA256 = "e3101d3a580c9ae6e973acbf2e861855e93ebceb0bbd8e5fa3ddf6abbf6fd63d"
FORK_LAUNCH_OPTION = "-Djdk.lang.Process.launchMechanism=FORK"
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


def compile_helper(source, temporary_root, environment=None, jdk_home=None):
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
    jdk = Path(jdk_home if jdk_home is not None else
               os.environ.get("DYN4K_JDI_JDK_HOME", str(JDK21)))
    environment = os.environ.copy() if environment is None else dict(environment)
    environment.pop("OLLAMA_API_KEY", None)
    environment["JAVA_HOME"] = str(jdk)
    supplied_tmp = Path(environment.get("TMPDIR", ""))
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


def _worker_thread_ids(workers, root, *, shared=False, timed_events=None,
                       births=None):
    parents = {}
    if timed_events is None:
        records = ((parent, None, line) for parent, trace in workers.items()
                   for line in trace.splitlines())
    else:
        records = ((int(tid), stamp, call) for stamp, tid, _, call in timed_events)
    for parent, stamp, line in records:
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
        shares_files = "CLONE_FILES" in names
        parents[identity] = (parent, same_process, shares_files)
        if births is not None:
            if stamp is None:
                raise EvidenceRejected("JDI thread birth time is missing")
            births[identity] = (parent, stamp)
    if set(parents) != set(workers) - {root}:
        raise EvidenceRejected("JDI worker trace has an unrelated descendant")
    threads = {root}
    pending = [root]
    seen = {root}
    while pending:
        parent = pending.pop()
        for child, (owner, same_process, shares_files) in parents.items():
            if owner != parent:
                continue
            if child in seen:
                raise EvidenceRejected("JDI worker clone chain is cyclic")
            seen.add(child)
            pending.append(child)
            if (shares_files if shared else same_process) and parent in threads:
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


def _verify_fork_child_prelude(worker, java_index, worker_pid, protected_paths):
    if (type(protected_paths) is not set or not protected_paths or
            any(type(path) is not str or not path.startswith("/")
                for path in protected_paths)):
        raise EvidenceRejected("JDI version 6 fork prelude scope differs")
    targets = set()
    directory_fd = None
    stat_done = False
    directory_closed = False
    final_option = False
    opened = re.compile(
        r'openat\(AT_FDCWD(?:<[^<>]+>)?, "/proc/self/fd", '
        r'O_RDONLY\|O_NONBLOCK\|O_CLOEXEC\|O_DIRECTORY\) = '
        r'([0-9]+)</proc/' + str(worker_pid) + r'/fd>$')
    duplicate = re.compile(
        r'dup2\(([0-9]+)<pipe:\[([0-9]+)\]>, ([0-3])'
        r'(?:<.*>)?\) = \3<pipe:\[\2\]>$')
    for _, index, call in worker:
        if index >= java_index:
            break
        if any(('"' + path + '"') in call or ('<' + path + '>') in call
               for path in protected_paths):
            raise EvidenceRejected("JDI version 6 fork prelude used protected input")
        closed = re.fullmatch(r'close\(([0-9]+)(?:<.*>)?\) = 0$', call)
        if closed is not None:
            fd = int(closed[1])
            if fd < 4 or final_option:
                raise EvidenceRejected("JDI version 6 fork descriptor close differs")
            if directory_fd == fd:
                if not stat_done or directory_closed:
                    raise EvidenceRejected("JDI version 6 fork directory lifetime differs")
                directory_closed = True
            continue
        copied = duplicate.fullmatch(call)
        if copied is not None:
            source, _, target = copied.groups()
            if (int(source) < 4 or int(target) in targets or
                    directory_fd is not None or final_option):
                raise EvidenceRejected("JDI version 6 fork descriptor mapping differs")
            targets.add(int(target))
            continue
        directory = opened.fullmatch(call)
        if directory is not None:
            if targets != {0, 1, 2, 3} or directory_fd is not None:
                raise EvidenceRejected("JDI version 6 fork directory open differs")
            directory_fd = int(directory[1])
            if directory_fd < 4:
                raise EvidenceRejected("JDI version 6 fork directory descriptor differs")
            continue
        if (directory_fd is not None and not stat_done and
                re.fullmatch(r'fstat\(' + str(directory_fd) + r'</proc/' +
                             str(worker_pid) + r'/fd>, \{.*S_IFDIR.*\}\) = 0$', call)):
            stat_done = True
            continue
        if (directory_closed and not final_option and
                re.fullmatch(r'fcntl\(3<pipe:\[[0-9]+\]>, F_SETFD, FD_CLOEXEC\) = 0$',
                             call)):
            final_option = True
            continue
        raise EvidenceRejected("JDI version 6 fork prelude operation differs")
    if targets != {0, 1, 2, 3} or not directory_closed or not final_option:
        raise EvidenceRejected("JDI version 6 fork prelude is incomplete")


def verify_worker_launch_v6(events, worker_pid, *, focused=True,
                            launcher_sha256=None, protected_paths=None):
    from numeric_producer_trace import WORKER_MAIN, java_entry_point, successful_execve

    worker = [(stamp, index, call) for stamp, tid, index, call in events
              if tid == str(worker_pid)]
    executions = [(stamp, index, successful_execve(call))
                  for stamp, index, call in worker
                  if call.startswith(("execve(", "execveat(")) and call.endswith(" = 0")]
    if (not executions or any(row[2] is None for row in executions) or
            any(call.startswith("execveat(") and call.endswith(" = 0")
                for _, _, call in worker)):
        raise EvidenceRejected("JDI version 6 worker execution differs")
    java_at, java_index, java = executions[-1]
    entry = java_entry_point(java[1])
    if (java[0] != str(JDK21 / "bin/java") or
            entry is None or
            (entry != ("class", WORKER_MAIN, len(java[1]) - 2)
             if focused else entry[:2] != ("class", "Main"))):
        raise EvidenceRejected("JDI version 6 selected Java execution differs")
    if len(executions) == 1:
        if java_index != 0:
            if not focused:
                raise EvidenceRejected("JDI version 6 Java start differs")
            _verify_fork_child_prelude(worker, java_index, worker_pid,
                                       protected_paths)
        return java_at, java_index
    if (not focused or len(executions) != 2 or
            type(protected_paths) is not set or not protected_paths or
            any(type(path) is not str or not path.startswith("/")
                for path in protected_paths) or
            launcher_sha256 != JSPAWNHELPER_SHA256):
        raise EvidenceRejected("JDI version 6 launcher inventory differs")
    _, launch_index, launcher = executions[0]
    try:
        current_sha256 = hashlib.sha256(JSPAWNHELPER.read_bytes()).hexdigest()
    except OSError as error:
        raise EvidenceRejected("JDI version 6 pinned launcher is unavailable") from error
    if (launch_index != 0 or launch_index >= java_index or
            launcher[0] != str(JSPAWNHELPER) or
            len(launcher[1]) != 3 or launcher[1][0] != str(JSPAWNHELPER) or
            re.fullmatch(r"[0-9]+(?:\.[0-9]+)+(?:\+[0-9]+-LTS)?", launcher[1][1]) is None or
            re.fullmatch(r"[0-9]+:[0-9]+:[0-9]+", launcher[1][2]) is None or
            current_sha256 != launcher_sha256):
        raise EvidenceRejected("JDI version 6 pinned launcher differs")
    socket_calls = ("socket(", "socketpair(", "bind(", "listen(", "accept(",
                    "accept4(", "connect(", "shutdown(", "sendto(", "recvfrom(",
                    "sendmsg(", "recvmsg(", "getsockname(", "getpeername(")
    process_calls = ("clone(", "clone3(", "fork(", "vfork(", "unshare(", "setns(")
    pathname_calls = ("open(", "openat(", "openat2(", "stat(", "lstat(",
                      "newfstatat(", "statx(", "rename(", "renameat(",
                      "renameat2(", "unlink(", "unlinkat(", "truncate(")
    for _, index, call in worker:
        if index >= java_index:
            break
        if index == launch_index:
            continue
        if (call.startswith(socket_calls + process_calls) or
                any("<" + path + ">" in call for path in protected_paths) or
                call.startswith(pathname_calls) and
                any('"' + path + '"' in call for path in protected_paths)):
            raise EvidenceRejected("JDI version 6 launcher supplied protected evidence")
    return java_at, java_index


def _birth_shape(call):
    match = re.fullmatch(r'(clone|clone3|fork|vfork)\((.*)\) = ([1-9][0-9]*)', call)
    if match is None:
        raise EvidenceRejected("JDI version 6 Gradle birth record differs")
    kind, arguments, _ = match.groups()
    if kind == "fork" and not arguments:
        return "process"
    flag = re.search(r'\bflags=([A-Z0-9_|]+)', arguments)
    if flag is None or arguments.count("flags=") != 1:
        raise EvidenceRejected("JDI version 6 Gradle birth flags differ")
    flags = set(flag[1].split("|"))
    thread = {"CLONE_VM", "CLONE_FS", "CLONE_FILES", "CLONE_SIGHAND",
              "CLONE_THREAD", "CLONE_SYSVSEM", "CLONE_SETTLS",
              "CLONE_PARENT_SETTID", "CLONE_CHILD_CLEARTID"}
    process = {"CLONE_CHILD_CLEARTID", "CLONE_CHILD_SETTID", "SIGCHLD"}
    if (kind == "clone3" and len(flags) == len(thread) and flags == thread and
            re.search(r'\bexit_signal=0(?:[,}])', arguments)):
        return "thread"
    if kind == "clone" and len(flags) == len(process) and flags == process:
        return "process"
    raise EvidenceRejected("JDI version 6 Gradle birth shape differs")


def verify_gradle_fork_parent_v6(events, worker_pid, root_pid):
    from numeric_producer_trace import (DAEMON_MAIN, WORKER_MAIN,
                                        java_entry_point, successful_execve)

    if type(worker_pid) is not int or type(root_pid) is not int or min(
            worker_pid, root_pid) <= 0 or worker_pid == root_pid:
        raise EvidenceRejected("JDI version 6 Gradle ancestry differs")
    births = {}
    first = {}
    records = {}
    for stamp, tid, index, call in events:
        owner = int(tid)
        first.setdefault(owner, stamp)
        records.setdefault(owner, []).append((stamp, index, call))
        if not call.startswith(("clone(", "clone3(", "fork(", "vfork(")):
            continue
        child = re.search(r"\) = ([1-9][0-9]*)$", call)
        if child is None:
            continue
        created = int(child[1])
        if created in births:
            raise EvidenceRejected("JDI version 6 Gradle child is ambiguous")
        births[created] = (owner, stamp, index, call)
    lineage = []
    current = worker_pid
    while current != root_pid:
        if current in lineage or current not in births or current not in first:
            raise EvidenceRejected("JDI version 6 Gradle ancestry differs")
        lineage.append(current)
        parent, created_at, _, _ = births[current]
        if created_at > first[current] or parent not in records:
            raise EvidenceRejected("JDI version 6 Gradle child preceded creation")
        current = parent
    lineage.append(root_pid)
    leaders = {root_pid: root_pid}
    processes = []
    for child in reversed(lineage[:-1]):
        parent, _, _, call = births[child]
        shape = _birth_shape(call)
        leaders[child] = leaders[parent] if shape == "thread" else child
        if shape == "process":
            processes.append(child)
    if len(processes) != 2 or processes[-1] != worker_pid:
        raise EvidenceRejected("JDI version 6 Gradle daemon ancestry differs")
    daemon_pid = processes[0]
    executions = {}
    for owner in lineage:
        rows = [(stamp, index, successful_execve(call))
                for stamp, index, call in records[owner]
                if call.startswith(("execve(", "execveat(")) and
                call.endswith(" = 0")]
        if any(program is None for _, _, program in rows):
            raise EvidenceRejected("JDI version 6 Gradle execution differs")
        executions[owner] = rows
        if owner not in (root_pid, daemon_pid, worker_pid) and rows:
            raise EvidenceRejected("JDI version 6 Gradle thread image changed")
    root_exec = executions[root_pid]
    if (len(root_exec) != 2 or
            not root_exec[0][2][0].endswith("/gradlew") or
            root_exec[1][2][0] != str(JDK21 / "bin/java") or
            (root_main := java_entry_point(root_exec[1][2][1])) is None or
            root_main[0] != "jar" or
            root_main[1] != str(Path(root_exec[0][2][0]).parent /
                                "gradle/wrapper/gradle-wrapper.jar")):
        raise EvidenceRejected("JDI version 6 Gradle root image differs")
    daemon_exec = executions[daemon_pid]
    if (len(daemon_exec) != 1 or
            daemon_exec[0][2][0] != str(JDK21 / "bin/java") or
            (daemon_main := java_entry_point(daemon_exec[0][2][1])) is None or
            daemon_main[:2] != ("class", DAEMON_MAIN) or
            daemon_exec[0][2][1][daemon_main[2] + 1:] != ("9.5.0",) or
            any(value.startswith("@") for value in daemon_exec[0][2][1][:daemon_main[2]])):
        raise EvidenceRejected("JDI version 6 Gradle daemon image differs")
    worker_exec = executions[worker_pid]
    if (len(worker_exec) != 1 or
            worker_exec[0][2][0] != str(JDK21 / "bin/java") or
            java_entry_point(worker_exec[0][2][1]) != (
                "class", WORKER_MAIN, len(worker_exec[0][2][1]) - 2)):
        raise EvidenceRejected("JDI version 6 Gradle worker image differs")
    for parent, image in ((root_pid, root_exec[1]), (daemon_pid, daemon_exec[0])):
        child = lineage[lineage.index(parent) - 1]
        birth_owner, created_at, created_index, _ = births[child]
        if (image[0] > created_at or
                image[0] == created_at and
                (birth_owner != parent or image[1] >= created_index)):
            raise EvidenceRejected("JDI version 6 Gradle image started too late")
        image_cutoff = births[daemon_pid if parent == root_pid else worker_pid][1]
        members = {parent}
        while True:
            added = set()
            for sibling, (owner, stamp, _, call) in births.items():
                if (owner not in members or sibling in members or
                        stamp > image_cutoff or "CLONE_THREAD" not in call):
                    continue
                if _birth_shape(call) != "thread":
                    raise EvidenceRejected("JDI version 6 Gradle thread sharing differs")
                added.add(sibling)
            if not added:
                break
            members.update(added)
        for member in members - {parent}:
            if any(stamp <= image_cutoff and call.startswith(("execve(", "execveat("))
                   and call.endswith(" = 0")
                   for stamp, _, call in records.get(member, ())):
                raise EvidenceRejected("JDI version 6 Gradle sibling image changed")
    return daemon_pid


def verify_jdi_transport_v6(worker_archive, helper_archive, port, worker_pid,
                            helper_pid, expected_argv, *, focused=True,
                            launcher_sha256=None, protected_paths=None):
    from actual_trace import normalize_rich_traces
    from numeric_producer_trace import _events, successful_execve

    if (type(port) is not int or not 1 <= port <= 65535 or
            type(worker_pid) is not int or worker_pid <= 0 or
            type(helper_pid) is not int or helper_pid <= 0 or
            type(expected_argv) is not list or len(expected_argv) < 9 or
            any(type(value) is not str for value in expected_argv) or
            (focused and (len(expected_argv) != 14 or
            expected_argv != [str(JDK21 / "bin/java"), "--add-modules", "jdk.jdi",
                              expected_argv[3], "-cp", expected_argv[5],
                              "RotationJdiProbe", "attach", expected_argv[8],
                              "127.0.0.1", str(port),
                              "org.dyn4j.geometry.Transform", "1800", "600"])) or
            (focused and not expected_argv[3].startswith("-Djava.io.tmpdir=")) or
            (focused and any(not Path(value).is_absolute() or
                not Path(value).resolve().is_relative_to(Path.home().resolve())
                for value in (expected_argv[3].removeprefix("-Djava.io.tmpdir="),
                              expected_argv[5], expected_argv[8]))) or
            (not focused and (len(expected_argv) != 13 or
             expected_argv[:4] != [str(JDK21 / "bin/java"), "--add-modules",
                                  "jdk.jdi", expected_argv[3]] or
             not expected_argv[3].startswith("-Djava.io.tmpdir=") or
             expected_argv[4:7] != ["-cp", expected_argv[5],
                                     "RotationJdiProbe"] or
             expected_argv[7:10] != ["attach-loader", expected_argv[8],
                                      "127.0.0.1"] or
             expected_argv[10:] != [str(port), "org.dyn4j.geometry.Transform", "0"]))):
        raise EvidenceRejected("JDI version 6 command identity differs")

    def records(raw):
        original = {str(pid): trace.encode() for pid, trace in _trace_members(raw).items()}
        if any(re.match(rb'[0-9]+\.[0-9]+ <\.\.\. [a-z][a-z0-9_]* resumed>', line)
               for trace in original.values() for line in trace.splitlines()):
            raise EvidenceRejected("JDI version 6 split completion lacks entry time")
        normalized, _ = normalize_rich_traces(original)
        events = _events(normalized, ())
        plain = {int(pid): "\n".join(line.split(" ", 1)[1]
                for line in data.decode().splitlines()) + "\n"
                 for pid, data in normalized.items()}
        return events, plain

    worker_events, workers = records(worker_archive)
    helper_events, helpers = records(helper_archive)
    if worker_pid not in workers or helper_pid not in helpers:
        raise EvidenceRejected("JDI version 6 selected process trace differs")
    worker_births = {}
    worker_threads = _worker_thread_ids(workers, worker_pid,
                                        timed_events=worker_events,
                                        births=worker_births)
    worker_owners = _worker_thread_ids(workers, worker_pid, shared=True,
                                       timed_events=worker_events)
    _helper_descendants(helpers, helper_pid)
    helper_births = {}
    helper_threads = _worker_thread_ids(helpers, helper_pid,
                                        timed_events=helper_events,
                                        births=helper_births)
    helper_owners = _worker_thread_ids(helpers, helper_pid, shared=True,
                                       timed_events=helper_events)

    def check_births(events, births, root):
        for stamp, tid, _, _ in events:
            owner = int(tid)
            bound = stamp
            while owner != root:
                edge = births.get(owner)
                if edge is None or edge[1] > bound:
                    raise EvidenceRejected("JDI version 6 thread birth is unproved")
                owner, bound = edge

    check_births(worker_events, worker_births, worker_pid)
    check_births(helper_events, helper_births, helper_pid)
    verify_worker_launch_v6(worker_events, worker_pid, focused=focused,
                            launcher_sha256=launcher_sha256,
                            protected_paths=protected_paths)
    helper_exec = [(tid, successful_execve(call)) for _, tid, _, call in helper_events
                   if call.startswith(("execve(", "execveat(")) and call.endswith(" = 0")]
    if (len(helper_exec) != 1 or helper_exec[0] != (
                str(helper_pid), (str(JDK21 / "bin/java"), tuple(expected_argv)))):
        raise EvidenceRejected("JDI version 6 selected Java execution differs")

    bind = re.compile(r'bind\((\d+)<(TCP:\[[^]]+\])>, '
                      r'\{sa_family=AF_INET, sin_port=htons\(' + str(port) +
                      r'\), sin_addr=inet_addr\("127\.0\.0\.1"\)\}, 16\) = 0$')
    listen = re.compile(r'listen\((\d+)<TCP:\[127\.0\.0\.1:' + str(port) +
                        r'\]>, [1-9][0-9]*\) = 0$')
    accept = re.compile(r'accept(?:4)?\((\d+)<TCP:\[127\.0\.0\.1:' + str(port) +
                        r'\]>, \{sa_family=AF_INET, sin_port=htons\(([1-9][0-9]*)\), '
                        r'sin_addr=inet_addr\("127\.0\.0\.1"\)\}, '
                        r'\[[0-9]+ => 16\](?:, [^)]*)?\) = (\d+)<(TCP:\['
                        r'127\.0\.0\.1:' + str(port) +
                        r'->127\.0\.0\.1:\2\])>$')
    connect_ipv4 = re.compile(
        r'connect\((\d+)<(TCP:\[[^>]+\])>, \{sa_family=AF_INET, '
        r'sin_port=htons\(' + str(port) +
        r'\), sin_addr=inet_addr\("127\.0\.0\.1"\)\}, 16\) = 0$')
    connect_ipv6 = re.compile(
        r'connect\((\d+)<(TCPv6:\[[^>]+\])>, \{sa_family=AF_INET6, '
        r'sin6_port=htons\(' + str(port) + r'\), sin6_flowinfo=htonl\(0\), '
        r'inet_pton\(AF_INET6, "::ffff:127\.0\.0\.1", &sin6_addr\), '
        r'sin6_scope_id=0\}, 28\) = 0$')
    socket = re.compile(
        r'socket\(AF_INET6?, SOCK_STREAM(?:\|SOCK_(?:CLOEXEC|NONBLOCK))*, '
        r'IPPROTO_(?:TCP|IP)\) = (\d+)<(TCP(?:v6)?:\[[^>]+\])>$')
    binds = [(stamp, int(tid), index, match[1], match[2])
             for stamp, tid, index, call in worker_events
             if int(tid) in worker_threads and (match := bind.fullmatch(call))]
    listens = [(stamp, int(tid), index, match[1])
               for stamp, tid, index, call in worker_events
               if int(tid) in worker_threads and (match := listen.fullmatch(call))]
    accepts = [(stamp, int(tid), index, match.groups())
               for stamp, tid, index, call in worker_events
               if int(tid) in worker_threads and (match := accept.fullmatch(call))]
    connects = [(stamp, int(tid), index, match.groups(), call)
                for stamp, tid, index, call in helper_events
                if int(tid) in helper_threads and
                (match := connect_ipv4.fullmatch(call) or connect_ipv6.fullmatch(call))]
    if any(call.startswith("connect(") and call.endswith(" = 0") and
           connect_ipv4.fullmatch(call) is None and
           connect_ipv6.fullmatch(call) is None
           for _, tid, _, call in helper_events if int(tid) in helper_threads):
        raise EvidenceRejected("JDI version 6 helper connected elsewhere")
    if any(call.startswith("bind(") and call.endswith(" = 0") and
           f"htons({port})" in call and bind.fullmatch(call) is None
           for _, tid, _, call in worker_events if int(tid) in worker_threads):
        raise EvidenceRejected("JDI version 6 worker bound another address")
    if any(call.startswith(("accept(", "accept4(")) and
           re.search(r"\) = [1-9][0-9]*<", call) and
           f"127.0.0.1:{port}" in call and accept.fullmatch(call) is None
           for _, tid, _, call in worker_events if int(tid) in worker_threads):
        raise EvidenceRejected("JDI version 6 accepted socket format differs")
    if len(connects) != 1 or len(accepts) != 1:
        raise EvidenceRejected("JDI version 6 accepted connection differs")
    connected_at, helper_thread, connect_index, (helper_fd, _,), connect_call = connects[0]
    accepted_at, worker_thread, accept_index, (listener_fd, peer_port, accepted_fd,
                                                accepted_token) = accepts[0]
    matching = [(bound_at, bound_tid, bound_index, token)
                for bound_at, bound_tid, bound_index, bound_fd, token in binds
                for _, listen_tid, listen_index, listened_fd in listens
                if bound_fd == listened_fd == listener_fd and
                (bound_tid != listen_tid or bound_index < listen_index) and
                (listen_tid != worker_thread or listen_index < accept_index)]
    if len(matching) != 1:
        raise EvidenceRejected("JDI version 6 selected listener differs")
    bound_at, bound_tid, bound_index, bound_token = matching[0]

    def source(events, threads, fd, token, before):
        before_stamp, before_tid, before_index = before
        found = [(stamp, int(tid)) for stamp, tid, index, call in events
                 if int(tid) in threads and
                 ((int(tid) == before_tid and index < before_index) or
                  (int(tid) != before_tid and stamp < before_stamp)) and
                 (match := socket.fullmatch(call)) and
                 match.groups() == (fd, token)]
        if len(found) != 1:
            raise EvidenceRejected("JDI version 6 socket provider differs")
        return found[0][0]

    def continuous(events, threads, fd, start, end, created_by=None):
        skipped_provider = False
        operand = r'\(' + re.escape(fd) + r'(?=[<,)])'
        for stamp, tid, _, call in events:
            if int(tid) not in threads or not start <= stamp <= end:
                continue
            if (created_by and not skipped_provider and stamp == start and
                    re.match(created_by + r'\(', call) and
                    re.search(r'\) = ' + fd + r'<', call)):
                skipped_provider = True
                continue
            closed_range = re.fullmatch(
                r'close_range\(([0-9]+), ([0-9]+), ([^)]+)\) = 0', call)
            if closed_range and (closed_range[3] != "0" or
                    int(closed_range[1]) <= int(fd) <= int(closed_range[2])):
                raise EvidenceRejected("JDI version 6 socket was closed by range")
            child = (re.match(r'(?:clone|clone3|fork|vfork)\(', call) and
                     re.search(r'\) = [1-9][0-9]*$', call))
            flags = re.search(r'\bflags=([A-Z_0-9|]+)', call) if child else None
            copied = child and (flags is None or
                    "CLONE_FILES" not in flags[1].split("|"))
            aliased = (re.match(r'dup(?:2|3)?' + operand, call) or
                       re.match(r'fcntl' + operand, call) and
                       re.search(r', F_DUPFD(?:_CLOEXEC)?(?:,|\))', call))
            if (copied or aliased and re.search(r'\) = [0-9]+(?:<|$)', call) or
                    call.startswith(("sendmsg(", "recvmsg(")) and
                    "SCM_RIGHTS" in call and re.search(r'\) = [0-9]+$', call)):
                raise EvidenceRejected("JDI version 6 socket reference was copied")
            changed = (
                (re.match(r'(?:close|shutdown)' + operand, call) or
                 re.match(r'close_range\(', call) and closed_range is None) and
                call.endswith(" = 0") or
                re.match(r'(?:dup|dup2|dup3|fcntl|open|openat|openat2|creat|socket|'
                         r'accept|accept4)\(', call) and
                re.search(r'\) = ' + fd + r'(?:<|$)', call) or
                re.match(r'(?:unshare|setns|execve|execveat)\(', call) and
                call.endswith(" = 0"))
            if changed:
                raise EvidenceRejected("JDI version 6 socket descriptor changed")
        if created_by and not skipped_provider:
            raise EvidenceRejected("JDI version 6 socket provider is missing")

    worker_socket_at = source(worker_events, worker_threads, listener_fd,
                              bound_token, (bound_at, bound_tid, bound_index))
    helper_socket_at = source(helper_events, helper_threads, helper_fd,
                              connects[0][3][1],
                              (connected_at, helper_thread, connect_index))
    continuous(worker_events, worker_owners, listener_fd,
               worker_socket_at, accepted_at, created_by="socket")
    continuous(helper_events, helper_owners, helper_fd,
               helper_socket_at, connected_at, created_by="socket")
    family = "TCPv6" if "AF_INET6" in connect_call else "TCP"
    local = "[::ffff:127.0.0.1]" if family == "TCPv6" else "127.0.0.1"
    helper_token = f"{family}:[{local}:{peer_port}->{local}:{port}]"
    helper_name = re.compile(r'getsockname\(' + helper_fd + r'<' +
                             re.escape(helper_token) + r'>, '
                             r'\{sa_family=AF_INET(?:6)?, .*?htons\(' +
                             peer_port + r'\).*?\}, \[[^]]+\]\) = 0$')
    names = [index for _, tid, index, call in helper_events
             if int(tid) == helper_thread and index > connect_index and
             helper_name.fullmatch(call)]
    if not names:
        raise EvidenceRejected("JDI version 6 helper peer differs")

    def handshake(events, fd, token, names):
        found = {}
        for stamp, tid, index, call in events:
            for name in names:
                if re.fullmatch(name + r'\(' + fd + r'<' + re.escape(token) +
                                r'>, "JDWP-Handshake", 14(?:, 0, NULL, '
                                r'(?:NULL|0))?\) = 14', call):
                    if name in found:
                        raise EvidenceRejected("JDI version 6 handshake is ambiguous")
                    found[name] = (stamp, tid, index)
        return found

    worker_io = handshake(worker_events, accepted_fd, accepted_token,
                          ("recvfrom", "sendto"))
    helper_io = handshake(helper_events, helper_fd, helper_token, ("write", "read"))
    if (set(worker_io) != {"recvfrom", "sendto"} or
            set(helper_io) != {"write", "read"} or
            worker_io["recvfrom"][1] != str(worker_thread) or
            worker_io["sendto"][1] != str(worker_thread) or
            helper_io["write"][1] != str(helper_thread) or
            helper_io["read"][1] != str(helper_thread) or
            not accept_index < worker_io["recvfrom"][2] < worker_io["sendto"][2] or
            not connect_index < helper_io["write"][2] < helper_io["read"][2]):
        raise EvidenceRejected("JDI version 6 accepted handshake differs")
    def traffic(events, process_threads, shared_threads, thread, fd, token,
                after_index, after_stamp, send, receive):
        counts = {"send": 0, "receive": 0}
        last = after_stamp
        later_entries = [(index, stamp) for stamp, tid, index, call in events
                         if int(tid) == thread and index > after_index and
                         re.match(r'[a-zA-Z_][a-zA-Z_0-9]*\(', call)]
        phase_entry = min(later_entries)[1] if later_entries else None
        for stamp, tid, index, call in events:
            if "JDWP-Handshake" in call:
                continue
            for direction, names in (("send", send), ("receive", receive)):
                if (re.match(r'(?:' + "|".join(names) + r')\(' + fd + r'<' +
                             re.escape(token) + r'>,', call) and
                        re.search(r'\) = [1-9][0-9]*$', call)):
                    if (int(tid) not in process_threads or
                            int(tid) not in shared_threads or
                            (int(tid) == thread and index <= after_index) or
                            (int(tid) != thread and
                             (phase_entry is None or stamp <= phase_entry))):
                        raise EvidenceRejected(
                            "JDI version 6 packet phase is unproved")
                    counts[direction] += 1
                    last = max(last, stamp)
        return counts, last

    worker_packets, worker_last = traffic(worker_events, worker_threads,
                             worker_owners, worker_thread,
                             accepted_fd, accepted_token,
                             worker_io["sendto"][2], worker_io["sendto"][0],
                             ("sendto", "sendmsg", "write"),
                             ("recvfrom", "recvmsg", "read"))
    helper_packets, helper_last = traffic(helper_events, helper_threads,
                             helper_owners, helper_thread,
                             helper_fd, helper_token,
                             helper_io["read"][2], helper_io["read"][0],
                             ("write", "sendto", "sendmsg"),
                             ("read", "recvfrom", "recvmsg"))
    if (not all(worker_packets.values()) or not all(helper_packets.values())):
        raise EvidenceRejected("JDI version 6 protocol exchange is missing")
    continuous(worker_events, worker_owners, accepted_fd, accepted_at,
               worker_last, created_by="accept(?:4)?")
    continuous(helper_events, helper_owners, helper_fd, connected_at, helper_last)
    return {"status": "PROVED_JDI_RAW_EXCHANGE", "qualification": "UNPASSED",
            "worker_tgid": worker_pid, "worker_thread": worker_thread,
            "listener_fd": int(listener_fd), "accepted_fd": int(accepted_fd),
            "helper_tgid": helper_pid, "helper_thread": helper_thread,
            "helper_fd": int(helper_fd), "peer_port": int(peer_port), "port": port,
            "worker_packets": worker_packets, "helper_packets": helper_packets}


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
