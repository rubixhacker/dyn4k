import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

from actual_arithmetic import (CaptureRejected, assess_focused_wheel,
                               expected_case_ids, focused_wheel_stream,
                               make_capture_receipt, verify_capture_receipt,
                               _portable_classes_archive,
                               _FOCUSED_BOOLEAN_METHOD,
                               _FOCUSED_BOOLEAN_REFERENCE_SHA256)
from boolean_rotation_jdi import jdi_bridge


ROOT = Path(__file__).resolve().parents[3]
PORTABLE = Path(__file__).resolve().parent
JDK21 = Path("/tmp/dyn4k-tools/jdk21")
STAGED_JAR = (ROOT / "build/staging-repository/io/github/rubixhacker/"
              "dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar")
ENVIRONMENT_SENTINEL = "DYN4K_CAPTURE_ENV_SENTINEL=portable-capture-check"
GENERATED_ROOTS = (
    ".gradle", ".kotlin", "build",
    "dyn4k-core/.gradle", "dyn4k-core/.kotlin", "dyn4k-core/build",
    "tools/numerical/portable/.gradle", "tools/numerical/portable/.kotlin",
    "tools/numerical/portable/build", "tools/numerical/portable/__pycache__",
    "tools/numerical/portable/kotlin-js-store",
)


def boolean_jdwp_option(port):
    if type(port) is not int or not 1 <= port <= 65535:
        raise CaptureRejected("Boolean JDI port differs")
    return ("-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,"
            f"address=127.0.0.1:{port}")


def trace_syscalls(method, helper=False):
    if helper:
        if method != _FOCUSED_BOOLEAN_METHOD:
            raise CaptureRejected("JDI helper method differs")
        return "trace=execve,execveat,clone,clone3,connect,openat,write,writev,close"
    if method == _FOCUSED_BOOLEAN_METHOD:
        return "trace=execve,execveat,clone,clone3,bind,listen,write,writev,sendto,sendmsg"
    if method in ("captureWheelActive", "captureRotationPremises"):
        return "trace=execve,clone,clone3,write,writev,sendto,sendmsg"
    return "trace=execve"


def executed_process_lines(pid, raw, method):
    if type(pid) is not str or not pid.isdecimal() or type(raw) is not bytes:
        raise CaptureRejected("process trace identity differs")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise CaptureRejected("process trace encoding differs") from error
    return [f"{pid} {line}" for line in lines
            if line.startswith("execve(") or
            (method == _FOCUSED_BOOLEAN_METHOD and line.startswith("execveat("))]


def socket_owner(proc_root, pid, port):
    if type(pid) is not int or pid <= 0:
        return False
    try:
        rows = (Path(proc_root) / "net/tcp").read_text().splitlines()[1:]
        matching = [parts[9] for row in rows if (parts := row.split()) and
                    len(parts) > 9 and parts[1] == f"0100007F:{port:04X}" and
                    parts[3] == "0A"]
        if len(matching) != 1:
            return False
        sockets = [os.readlink(path) for path in (Path(proc_root) / str(pid) / "fd").iterdir()]
        return sockets.count(f"socket:[{matching[0]}]") == 1
    except (OSError, ValueError):
        return False


def reserve_boolean_jdi_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def selected_worker_pid(trace_prefix):
    selected = []
    for path in Path(trace_prefix).parent.glob(Path(trace_prefix).name + ".*"):
        pid = path.name.removeprefix(Path(trace_prefix).name + ".")
        if not pid.isdecimal():
            raise CaptureRejected("worker trace PID differs")
        if any(line.startswith("execve(") and "GradleWorkerMain" in line and
               line.endswith(" = 0") for line in path.read_text(errors="replace").splitlines()):
            selected.append(int(pid))
    if len(selected) > 1:
        raise CaptureRejected("selected JDI worker is ambiguous")
    return selected[0] if selected else None


def stop_capture_process(process):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=5)


def _file_sizes(*roots):
    sizes = {}
    for root in roots:
        for path in Path(root).rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                sizes[path] = path.stat().st_size
            except OSError:
                # skip transient files deleted during an active build
                pass
    return sizes


class CaptureBudget:
    def __init__(self, output, temporary, generated_roots, *,
                 limit_bytes=1800 * 1024 * 1024, seconds=1200):
        self.output = Path(output)
        self.temporary = Path(temporary)
        self.generated_roots = tuple(Path(root) for root in generated_roots)
        self.initial = _file_sizes(*self.generated_roots)
        self.limit_bytes = limit_bytes
        self.deadline = time.monotonic() + seconds

    def check(self, extra_bytes=0):
        if time.monotonic() > self.deadline:
            raise CaptureRejected("focused capture timed out")
        generated = _file_sizes(*self.generated_roots)
        growth = sum(max(size - self.initial.get(path, 0), 0)
                     for path, size in generated.items())
        total = sum(_file_sizes(self.output, self.temporary).values()) + growth
        if total + extra_bytes >= self.limit_bytes:
            raise CaptureRejected("new capture output exceeded the bounded budget")
        return total


@contextmanager
def capture_watchdog(seconds):
    previous = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def expired(signum, frame):
        raise CaptureRejected("focused capture timed out")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous)


def run_bounded_process(command, cwd, environment, output_path, budget, active,
                        combine_stderr=True):
    with Path(output_path).open("xb") as stream:
        process = subprocess.Popen(
            command, cwd=cwd, env=environment, stdout=stream,
            stderr=subprocess.STDOUT if combine_stderr else subprocess.DEVNULL,
            start_new_session=True)
        active.append(process)
        try:
            while process.poll() is None:
                budget.check()
                time.sleep(0.1)
            budget.check()
        except Exception:
            stop_capture_process(process)
            active.remove(process)
            raise
        stop_capture_process(process)
        active.remove(process)
    return process.returncode


def child_environment():
    environment = os.environ.copy()
    environment.pop("OLLAMA_API_KEY", None)
    return environment


def reject_environment_trace(trace_path):
    trace_path = Path(trace_path)
    try:
        contains_sentinel = ENVIRONMENT_SENTINEL.encode() in trace_path.read_bytes()
    except OSError:
        try:
            trace_path.unlink()
        except FileNotFoundError:
            raise CaptureRejected("process trace is missing") from None
        except OSError:
            raise CaptureRejected("process trace could not be removed") from None
        raise CaptureRejected("process trace is unavailable") from None
    if contains_sentinel:
        trace_path.unlink()
        raise CaptureRejected("process trace exposed the environment")


def git(*args):
    return subprocess.run(("git", *args), cwd=ROOT, check=True,
                          capture_output=True, env=child_environment()).stdout


def clean_source():
    if git("--no-replace-objects", "status", "--porcelain",
           "--untracked-files=all").strip():
        raise CaptureRejected("target source is not clean")
    ignored = git("--no-replace-objects", "ls-files", "--others", "--ignored",
                  "--exclude-standard", "--full-name", "-z").split(b"\0")
    for name in ignored:
        if not name:
            continue
        relative = os.fsdecode(name)
        if not any(relative.startswith(root + "/") for root in GENERATED_ROOTS):
            raise CaptureRejected("ignored file outside exact generated roots")
    return git("--no-replace-objects", "rev-parse", "HEAD").decode().strip()


def archive_file_names(method, worker_log, worker_argument_log=None):
    names = {
        "source.tar", "stage.log", "artifact.jar", "gradle.log",
        "worker-classpath.txt", "execve.log", "capture.xml",
        "portable-classes.zip", "runtime-java", "receipt.json",
        Path(worker_log).name,
    }
    if method in ("captureWheelActive", "captureRotationPremises"):
        names.add("worker-write-traces.zip")
    if method == "captureWheelActive":
        names.update(("joint-Wheel-active.jsonl", "focused-assessment.json"))
    elif method == _FOCUSED_BOOLEAN_METHOD:
        if worker_argument_log is None:
            raise CaptureRejected("worker argument log is missing")
        names.update(("worker-write-traces.zip", "joint-Revolute-LimitsEnabled-false.jsonl",
                      "reference-case.jsonl", Path(worker_argument_log).name,
                      "jdi-helper-classes.zip", "jdi-evidence.zip",
                      "jdi-helper-traces.zip", "jdi-transport.json"))
    return names


def capture_case_ids():
    return {**expected_case_ids(include_focused=True),
            _FOCUSED_BOOLEAN_METHOD: ["joint-Revolute-LimitsEnabled-false"]}


def target_test_class(method):
    if method not in capture_case_ids():
        raise CaptureRejected("unknown arithmetic producer method")
    return ("portable.RevoluteLimitsFalseCaptureTest" if
            method == _FOCUSED_BOOLEAN_METHOD else
            "portable.RotationPremiseFixtureTest"
            if method == "captureRotationPremises" else
            "portable.ProspectiveArithmeticTest")


def verify_archive_inventory(output, method, worker_log, worker_argument_log=None):
    output = Path(output)
    expected = archive_file_names(method, worker_log, worker_argument_log)
    actual = {path.name for path in output.iterdir()}
    if actual != expected or any(not path.is_file() or path.is_symlink()
                                 for path in output.iterdir()):
        raise CaptureRejected("archive inventory differs")
    for name in expected - {"source.tar", "worker-write-traces.zip"}:
        raw = (output / name).read_bytes()
        if ENVIRONMENT_SENTINEL.encode() in raw or b"OLLAMA_API_KEY" in raw:
            raise CaptureRejected("archive exposed the environment")
    archives = ({"worker-write-traces.zip"} if method in
                ("captureWheelActive", "captureRotationPremises",
                 _FOCUSED_BOOLEAN_METHOD) else set())
    if method == _FOCUSED_BOOLEAN_METHOD:
        archives |= {"jdi-helper-classes.zip", "jdi-evidence.zip",
                     "jdi-helper-traces.zip"}
    for archive_name in archives:
        try:
            with zipfile.ZipFile(output / archive_name) as archive:
                if archive.testzip() is not None:
                    raise CaptureRejected("archive member differs")
                for name in archive.namelist():
                    raw = archive.read(name)
                    if ENVIRONMENT_SENTINEL.encode() in raw or b"OLLAMA_API_KEY" in raw:
                        raise CaptureRejected("archive exposed the environment")
        except (OSError, zipfile.BadZipFile, RuntimeError, KeyError) as error:
            raise CaptureRejected("worker write archive could not be scanned") from error


def run_capture(method, output, reference_case=None):
    if method not in capture_case_ids():
        raise CaptureRejected("unknown arithmetic producer method")
    if method in ("captureWheelActive", _FOCUSED_BOOLEAN_METHOD) and \
            reference_case is None:
        raise CaptureRejected("focused reference is required")
    output = Path(output).resolve()
    if method == _FOCUSED_BOOLEAN_METHOD and not output.is_relative_to(
            Path.home().resolve()):
        raise CaptureRejected("focused JDI output root is not home-backed")
    if output.exists():
        raise CaptureRejected("capture output already exists")
    commit = clean_source()
    temporary_root = Path(os.environ.get("TMPDIR", Path.home() / ".cache/dyn4k-capture")).resolve()
    if not temporary_root.is_relative_to(Path.home().resolve()):
        raise CaptureRejected("capture temporary root is not home-backed")
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dyn4k-actual-", dir=temporary_root) as scratch:
        if method != _FOCUSED_BOOLEAN_METHOD:
            return _run_capture(method, output, reference_case, commit, Path(scratch))
        generated = tuple(ROOT / name for name in (
            "build", ".gradle", ".kotlin", "dyn4k-core/build",
            "dyn4k-core/.gradle", "dyn4k-core/.kotlin",
            "tools/numerical/portable/build", "tools/numerical/portable/.gradle",
            "tools/numerical/portable/.kotlin"))
        active = []
        previous_tmpdir = os.environ.get("TMPDIR")
        os.environ["TMPDIR"] = scratch
        try:
            with capture_watchdog(1200):
                budget = CaptureBudget(output, Path(scratch), generated)
                try:
                    return _run_capture(method, output, reference_case, commit,
                                        Path(scratch), budget, active)
                finally:
                    for process in active:
                        stop_capture_process(process)
        finally:
            if previous_tmpdir is None:
                os.environ.pop("TMPDIR", None)
            else:
                os.environ["TMPDIR"] = previous_tmpdir


def _run_capture(method, output, reference_case, commit, temporary,
                 budget=None, active=None):
    output.mkdir(parents=True)

    def check_budget(extra_bytes=0):
        if budget is not None:
            budget.check(extra_bytes)

    if method == _FOCUSED_BOOLEAN_METHOD:
        try:
            reference = Path(reference_case).read_bytes()
        except OSError as error:
            raise CaptureRejected("focused Boolean indexed reference unavailable") from error
        if hashlib.sha256(reference).hexdigest() != _FOCUSED_BOOLEAN_REFERENCE_SHA256:
            raise CaptureRejected("focused Boolean indexed reference differs")
        (output / "reference-case.jsonl").write_bytes(reference)
        check_budget()
    environment = child_environment()
    environment["JAVA_HOME"] = str(JDK21)
    environment["TMPDIR"] = str(temporary)
    environment["JAVA_TOOL_OPTIONS"] = f"-Djava.io.tmpdir={temporary}"
    environment["DYN4K_CAPTURE_ENV_SENTINEL"] = "portable-capture-check"
    if not (JDK21 / "bin/java").is_file():
        raise CaptureRejected("pinned JDK21 is unavailable")
    source_command = ("git", "--no-replace-objects", "-c", "core.autocrlf=false",
                      "archive", "--format=tar", commit)
    if budget is None:
        with (output / "source.tar").open("xb") as archive:
            subprocess.run(source_command, cwd=ROOT, env=environment,
                           stdout=archive, check=True)
    elif run_bounded_process(source_command, ROOT, environment,
                             output / "source.tar", budget, active,
                             combine_stderr=False):
        raise CaptureRejected("candidate source archive failed")
    if budget is not None:
        budget.check()
    stage_command = [str(ROOT / "gradlew"),
                     ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
                     ":dyn4k-core:publishJvmPublicationToStagingRepository",
                     "--rerun-tasks", "--no-daemon", "--console=plain", "--offline",
                     "-Pkotlin.compiler.execution.strategy=in-process"]
    if budget is None:
        with (output / "stage.log").open("xb") as log:
            stage = subprocess.run(stage_command, cwd=ROOT, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT, check=False)
            stage_code = stage.returncode
    else:
        stage_code = run_bounded_process(stage_command, ROOT, environment,
                                         output / "stage.log", budget, active)
    if stage_code or not STAGED_JAR.is_file():
        raise CaptureRejected("pinned source publication failed")
    if budget is not None:
        budget.check(STAGED_JAR.stat().st_size)
    shutil.copyfile(STAGED_JAR, output / "artifact.jar")
    if budget is not None:
        budget.check()
    class_load_pattern = output / "worker-class-load-%p.log"
    argument_pattern = temporary / "worker-arguments-%p.log"
    jdi_port = None
    jdi_classes = None
    jdi_output = None
    jdi_trace_prefix = None
    if method == _FOCUSED_BOOLEAN_METHOD:
        environment["JAVA_TOOL_OPTIONS"] += (
            f" -Xlog:arguments=info:file={argument_pattern}:"
            "pid,level,tags:filecount=0")
        jdi_port = reserve_boolean_jdi_port()
        jdi_output = temporary / "jdi-output"
        jdi_trace_prefix = temporary / "jdi-helper-trace"
        jdi_classes, helper_zip = jdi_bridge.compile_helper(
            (PORTABLE / "boolean_rotation_jdi/RotationJdiProbe.java").read_bytes(),
            temporary)
        (output / "jdi-helper-classes.zip").write_bytes(helper_zip)
        check_budget()
    if method in ("captureWheelActive", "captureRotationPremises",
                  _FOCUSED_BOOLEAN_METHOD):
        trace_prefix = temporary / "worker-write-trace"
        tracer = ["strace", "-ff", "-s", "65536", "-e",
                  trace_syscalls(method),
                  "-o", str(trace_prefix)]
    else:
        tracer = ["strace", "-f", "-s", "16384", "-e", trace_syscalls(method),
                  "-o", str(output / "execve.log")]
    target_class = target_test_class(method)
    xml = (PORTABLE / "build/test-results/jvmTest" /
           f"TEST-{target_class}.xml")
    command = [*tracer, str(ROOT / "gradlew"),
               "jvmTest", "--tests", f"{target_class}.{method}",
               f"-PportableRepository={ROOT / 'build/staging-repository'}",
               f"-PportableWorkerClassLoadLog={class_load_pattern}",
               "--rerun-tasks", "--no-daemon", "--console=plain", "--offline", "--info",
               "-Pkotlin.compiler.execution.strategy=in-process"]
    if method == _FOCUSED_BOOLEAN_METHOD:
        command.extend((f"-PportableBooleanJdiPort={jdi_port}",
                        f"-PportableBooleanJdiMethod={method}"))
    worker_arguments = output / "worker-classpath.txt"
    helper = None
    live_socket_owner = False
    with (output / "gradle.log").open("xb") as log:
        target = subprocess.Popen(command, cwd=PORTABLE, env=environment,
                                  stdout=log, stderr=subprocess.STDOUT,
                                  start_new_session=True)
        if active is not None:
            active.append(target)
        deadline = time.monotonic() + 900
        next_size_check = time.monotonic()
        try:
            while target.poll() is None:
                if time.monotonic() >= next_size_check:
                    if budget is not None:
                        budget.check()
                    next_size_check = time.monotonic() + 0.25
                if not worker_arguments.exists():
                    output_text = (output / "gradle.log").read_text(errors="replace")
                    matches = re.findall(r"@(/[^\s]+gradle-worker-classpath[^\s]+txt)",
                                         output_text)
                    if matches and Path(matches[-1]).is_file():
                        shutil.copyfile(matches[-1], worker_arguments)
                if method == _FOCUSED_BOOLEAN_METHOD and helper is None:
                    worker = selected_worker_pid(trace_prefix)
                    if worker is not None and socket_owner(Path("/proc"), worker, jdi_port):
                        live_socket_owner = True
                        helper_command = ["strace", "-ff", "-s", "1048576", "-e",
                                          trace_syscalls(method, helper=True),
                                          "-o", str(jdi_trace_prefix),
                                          str(JDK21 / "bin/java"), "--add-modules", "jdk.jdi",
                                          "-Djava.io.tmpdir=" + str(temporary),
                                          "-cp", str(jdi_classes), "RotationJdiProbe",
                                          "attach", str(jdi_output), "127.0.0.1",
                                          str(jdi_port), "org.dyn4j.geometry.Transform",
                                          "1800", "600"]
                        with (temporary / "jdi-helper.log").open("xb") as helper_log:
                            helper = subprocess.Popen(helper_command, cwd=PORTABLE,
                                                      env=environment, stdout=helper_log,
                                                      stderr=subprocess.STDOUT,
                                                      start_new_session=True)
                            if active is not None:
                                active.append(helper)
                if helper is not None and helper.poll() not in (None, 0):
                    raise CaptureRejected("JDI controller failed during target execution")
                if time.monotonic() > deadline:
                    raise CaptureRejected("focused target or JDI worker timed out")
                time.sleep(0.02)
        except Exception:
            stop_capture_process(helper)
            stop_capture_process(target)
            raise
    if active is not None:
        stop_capture_process(target)
        active.remove(target)
    if budget is not None:
        budget.check()
    if method == _FOCUSED_BOOLEAN_METHOD:
        if helper is None or not live_socket_owner:
            raise CaptureRejected("selected JDI worker socket was not observed")
        try:
            helper.wait(timeout=30)
        except subprocess.TimeoutExpired as error:
            stop_capture_process(helper)
            raise CaptureRejected("JDI controller did not finish") from error
        if helper.returncode or not jdi_output.is_dir():
            raise CaptureRejected("JDI controller failed")
        if active is not None:
            stop_capture_process(helper)
            active.remove(helper)
        if budget is not None:
            budget.check()
    if method in ("captureWheelActive", "captureRotationPremises",
                  _FOCUSED_BOOLEAN_METHOD):
        trace_files = sorted(temporary.glob("worker-write-trace.*"))
        if not trace_files:
            raise CaptureRejected("worker write trace is missing")
        raw_traces = {}
        executions = []
        workers = []
        for path in trace_files:
            check_budget()
            raw = path.read_bytes()
            pid = path.name.removeprefix("worker-write-trace.")
            if not pid.isdecimal():
                raise CaptureRejected("worker write trace PID differs")
            raw_traces[pid] = raw
            executions.extend(executed_process_lines(pid, raw, method))
            if any(line.startswith("execve(") and "GradleWorkerMain" in line and
                   line.endswith(" = 0") for line in raw.decode().splitlines()):
                workers.append(pid)
        if len(workers) != 1:
            raise CaptureRejected("worker write trace process differs")
        descendants = {workers[0]}
        pending = workers[:]
        while pending:
            for line in raw_traces[pending.pop()].decode().splitlines():
                if not line.startswith(("clone(", "clone3(")):
                    continue
                child = re.search(r"\)\s+= ([1-9][0-9]*)$", line)
                if child is None:
                    continue
                pid = child.group(1)
                if pid not in raw_traces:
                    raise CaptureRejected("worker write child trace is missing")
                if pid not in descendants:
                    descendants.add(pid)
                    pending.append(pid)
        with zipfile.ZipFile(output / "worker-write-traces.zip", "x") as archive:
            for pid in sorted(descendants, key=int):
                raw = raw_traces[pid]
                if ENVIRONMENT_SENTINEL.encode() in raw or b"OLLAMA_API_KEY" in raw:
                    raise CaptureRejected("worker write trace exposed the environment")
                check_budget(len(raw))
                archive.writestr("trace." + pid, raw)
                check_budget()
        (output / "execve.log").write_text("\n".join(sorted(executions)) + "\n")
        check_budget()
    if method == _FOCUSED_BOOLEAN_METHOD:
        helper_traces = sorted(temporary.glob("jdi-helper-trace.*"))
        helper_pids = []
        if not helper_traces:
            raise CaptureRejected("JDI helper process trace is missing")
        with zipfile.ZipFile(output / "jdi-helper-traces.zip", "x") as archive:
            for path in helper_traces:
                check_budget()
                pid = path.name.removeprefix("jdi-helper-trace.")
                if not pid.isdecimal() or path.is_symlink():
                    raise CaptureRejected("JDI helper trace PID differs")
                raw = path.read_bytes()
                if ENVIRONMENT_SENTINEL.encode() in raw or b"OLLAMA_API_KEY" in raw:
                    raise CaptureRejected("JDI helper trace exposed the environment")
                if any(line.startswith(f'execve("{JDK21 / "bin/java"}"') and
                       line.endswith(" = 0") for line in raw.decode().splitlines()):
                    helper_pids.append(int(pid))
                check_budget(len(raw))
                archive.writestr("trace." + pid, raw)
                check_budget()
        if len(helper_pids) != 1:
            raise CaptureRejected("JDI helper process is ambiguous")
        with zipfile.ZipFile(output / "jdi-evidence.zip", "x") as archive:
            for path in sorted(jdi_output.iterdir()):
                if not path.is_file() or path.is_symlink():
                    raise CaptureRejected("JDI output inventory differs")
                check_budget(path.stat().st_size)
                archive.writestr(path.name, path.read_bytes())
                check_budget()
        transport = {"schema": "boolean-jdi-transport/1", "port": jdi_port,
                     "worker_pid": selected_worker_pid(trace_prefix),
                     "helper_pid": helper_pids[0],
                     "helper_classes_path": str(jdi_classes),
                     "output_path": str(jdi_output), "temp_path": str(temporary),
                     "live_socket_owner": live_socket_owner}
        (output / "jdi-transport.json").write_text(
            json.dumps(transport, sort_keys=True) + "\n")
        check_budget()
    reject_environment_trace(output / "execve.log")
    if target.returncode or not xml.is_file() or not worker_arguments.is_file():
        raise CaptureRejected("executed arithmetic target method failed")
    worker_lines = [line for line in (output / "execve.log").read_text().splitlines()
                    if f'execve("{JDK21 / "bin/java"}"' in line and
                    "GradleWorkerMain" in line and line.endswith(" = 0")]
    if len(worker_lines) != 1:
        raise CaptureRejected("executed JVM worker identity differs")
    worker_pid = worker_lines[0].split(" ", 1)[0]
    if not worker_pid.isdecimal():
        raise CaptureRejected("executed JVM worker PID differs")
    worker_log = Path(str(class_load_pattern).replace("%p", worker_pid))
    if not worker_log.is_file():
        raise CaptureRejected("executed JVM worker class-load log missing")
    worker_argument_log = None
    if method == _FOCUSED_BOOLEAN_METHOD:
        raw_argument_log = Path(str(argument_pattern).replace("%p", worker_pid))
        if not raw_argument_log.is_file():
            raise CaptureRejected("executed JVM worker argument log missing")
        worker_argument_log = output / f"worker-arguments-{worker_pid}.log"
        check_budget(raw_argument_log.stat().st_size)
        shutil.copyfile(raw_argument_log, worker_argument_log)
        check_budget()
    check_budget(xml.stat().st_size)
    shutil.copyfile(xml, output / "capture.xml")
    check_budget()
    with (output / "portable-classes.zip").open("xb") as classes:
        class_archive = _portable_classes_archive()
        check_budget(len(class_archive))
        classes.write(class_archive)
    check_budget()
    if clean_source() != commit:
        raise CaptureRejected("target source changed during capture")
    runtime_path = JDK21 / "bin/java"
    check_budget(runtime_path.stat().st_size)
    shutil.copyfile(runtime_path, output / "runtime-java")
    check_budget()
    files = {key: (output / name).read_bytes() for key, name in {
        "xml": "capture.xml", "stage_log": "stage.log", "gradle_log": "gradle.log",
        "execve_log": "execve.log", "artifact": "artifact.jar",
        "runtime": "runtime-java", "source": "source.tar",
        "worker_classpath": "worker-classpath.txt",
        "portable_classes": "portable-classes.zip"}.items()}
    files["worker_class_load"] = worker_log.read_bytes()
    if method in ("captureWheelActive", "captureRotationPremises",
                  _FOCUSED_BOOLEAN_METHOD):
        files["worker_write_traces"] = (output / "worker-write-traces.zip").read_bytes()
    if method == _FOCUSED_BOOLEAN_METHOD:
        case_path = output / "joint-Revolute-LimitsEnabled-false.jsonl"
        trace, _ = focused_wheel_stream(files["xml"])
        case_path.write_bytes(trace)
        check_budget()
        files["candidate_case"] = trace
        files["reference_case"] = (output / "reference-case.jsonl").read_bytes()
        files["worker_arguments"] = worker_argument_log.read_bytes()
        files.update({key: (output / name).read_bytes() for key, name in {
            "jdi_helper_classes": "jdi-helper-classes.zip",
            "jdi_evidence": "jdi-evidence.zip",
            "jdi_helper_traces": "jdi-helper-traces.zip",
            "jdi_transport": "jdi-transport.json"}.items()})
    if hashlib.sha256(files["artifact"]).hexdigest() != hashlib.sha256(
            STAGED_JAR.read_bytes()).hexdigest() or \
            hashlib.sha256(files["runtime"]).hexdigest() != hashlib.sha256(
                runtime_path.read_bytes()).hexdigest():
        raise CaptureRejected("copied producer artifact differs")
    receipt = make_capture_receipt(files, method, commit,
                                   capture_case_ids()[method], str(runtime_path))
    check_budget()
    verify_capture_receipt(receipt, files, method, commit,
                           capture_case_ids()[method], str(runtime_path))
    check_budget()
    (output / "receipt.json").write_text(json.dumps(receipt, sort_keys=True,
                                                     indent=2) + "\n")
    check_budget()
    if method == "captureWheelActive":
        trace, _ = focused_wheel_stream(files["xml"])
        case_path = output / "joint-Wheel-active.jsonl"
        case_path.write_bytes(trace)
        assessment = assess_focused_wheel(receipt, files, commit, str(runtime_path),
                                          reference_case, case_path)
        (output / "focused-assessment.json").write_text(
            json.dumps(assessment, sort_keys=True, indent=2) + "\n")
    verify_archive_inventory(output, method, worker_log, worker_argument_log)
    check_budget()
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=tuple(capture_case_ids()),
                        required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-case", type=Path)
    arguments = parser.parse_args()
    result = run_capture(arguments.method, arguments.output, arguments.reference_case)
    print(json.dumps({"candidate_commit": result["candidate_commit"],
                      **result["summary"]}, sort_keys=True))
