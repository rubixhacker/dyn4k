import io
import json
import os
from pathlib import Path
import select
import re
import shutil
import subprocess
import signal
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import uuid
import zipfile

from ordinary_snapshot.control import SnapshotIncomplete, SnapshotOwnedProcesses
from ordinary_snapshot.build_tracer import build as build_tracer, run as run_build_command
from ordinary_arithmetic_diagnostic import _pidfd_exited, _proc_identity, check_retained
import ordinary_arithmetic_diagnostic as diagnostic


class NativeAttempt:
    def __init__(self, label):
        self.label = label
        self.directory = None
        self.scratch = None

    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"])
        self.scratch = Path(self.directory.name)
        return self

    def capture(self, stdout, stderr):
        (self.scratch / "stdout.raw").write_bytes(stdout)
        (self.scratch / "stderr.raw").write_bytes(stderr)

    def __exit__(self, error_type, error, traceback):
        try:
            if error_type is not None:
                root = Path(os.environ.get("DYN4K_NATIVE_FAILURES",
                                           Path.cwd() / "ordinary-snapshot-native-failures"))
                target = root / f"{self.label}-{uuid.uuid4().hex}"
                target.mkdir(parents=True, mode=0o700)
                for path in self.scratch.iterdir():
                    if (path.name.startswith("trace.") or path.name in
                            {"ptrace-events.jsonl", "snapshot-controls.jsonl",
                             "stdout.raw", "stderr.raw"}):
                        shutil.copyfile(path, target / path.name)
                (target / "outcome.json").write_text(json.dumps({
                    "status": "FAILED", "error_type": error_type.__name__,
                    "error": str(error), "files": sorted(item.name for item in
                                                         target.iterdir())}) + "\n")
                print(f"native attempt retained: {target}", file=sys.stderr)
        finally:
            self.directory.cleanup()
        return False


class NativeSnapshotControlTest(unittest.TestCase):
    def test_timed_out_build_command_reaps_term_ignoring_descendant(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            pidfile = Path(directory) / "child.pid"
            sentinel = subprocess.Popen(["/bin/sleep", "5"])
            handle = None
            observed = []
            def open_child():
                until = time.monotonic() + 3
                while time.monotonic() < until:
                    try:
                        observed.append(os.pidfd_open(int(pidfile.read_text())))
                        return
                    except (FileNotFoundError, ValueError, ProcessLookupError):
                        pass
                    time.sleep(0.001)
            watcher = threading.Thread(target=open_child)
            watcher.start()
            try:
                result = run_build_command([
                    sys.executable, str(Path(__file__).with_name(
                        "adverse_build_child.py")), str(pidfile)],
                    directory, os.environ, 0.3)
                watcher.join(timeout=3)
                handle = observed[0]
                self.assertEqual((result["exit_code"], result["timed_out"]),
                                 (124, True))
                self.assertTrue(select.select([handle], [], [], 0)[0])
                self.assertIsNone(sentinel.poll())
            finally:
                watcher.join(timeout=3)
                if handle is None and observed:
                    handle = observed[0]
                if handle is not None:
                    if not select.select([handle], [], [], 0)[0]:
                        signal.pidfd_send_signal(handle, signal.SIGKILL)
                        self.assertTrue(select.select([handle], [], [], 3)[0])
                    os.close(handle)
                if sentinel.poll() is None:
                    sentinel.kill()
                sentinel.wait(timeout=3)

    def test_completed_build_command_keeps_unrelated_process(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            sentinel = subprocess.Popen(["/bin/sleep", "5"])
            try:
                result = run_build_command([sys.executable, "-c",
                                            "print('complete')"],
                                           directory, os.environ, 3)
                self.assertEqual((result["exit_code"], result["timed_out"],
                                  result["stdout"]), (0, False, b"complete\n"))
                self.assertIsNone(sentinel.poll())
            finally:
                if sentinel.poll() is None:
                    sentinel.kill()
                sentinel.wait(timeout=3)

    def test_native_attempt_retains_injected_failure_after_return(self):
        parent = Path(os.environ.get("DYN4K_NATIVE_FAILURES", os.environ["TMPDIR"]))
        root = parent / f"native-failure-test-{uuid.uuid4().hex}"
        with mock.patch.dict(os.environ, {"DYN4K_NATIVE_FAILURES": str(root)}):
            with self.assertRaisesRegex(RuntimeError, "injected failure"):
                with NativeAttempt("injected") as attempt:
                    (attempt.scratch / "trace.123").write_bytes(b"raw trace\n")
                    (attempt.scratch / "ptrace-events.jsonl").write_bytes(b"birth\n")
                    (attempt.scratch / "snapshot-controls.jsonl").write_bytes(b"freeze\n")
                    attempt.capture(b"raw stdout\n", b"raw stderr\n")
                    raise RuntimeError("injected failure")
            paths = list(root.glob("injected-*/outcome.json"))
            self.assertEqual(len(paths), 1)
            retained = paths[0].parent
            self.assertEqual(json.loads(paths[0].read_text())["status"], "FAILED")
            self.assertEqual((retained / "trace.123").read_bytes(), b"raw trace\n")
            self.assertEqual((retained / "ptrace-events.jsonl").read_bytes(), b"birth\n")
            self.assertEqual((retained / "snapshot-controls.jsonl").read_bytes(), b"freeze\n")
            self.assertEqual((retained / "stdout.raw").read_bytes(), b"raw stdout\n")
            self.assertEqual((retained / "stderr.raw").read_bytes(), b"raw stderr\n")
        if "DYN4K_NATIVE_FAILURES" not in os.environ:
            shutil.rmtree(root)

    def test_native_attempt_success_removes_scratch(self):
        with NativeAttempt("successful") as attempt:
            scratch = attempt.scratch
            (scratch / "toy").write_bytes(b"build output")
            attempt.capture(b"", b"")
        self.assertFalse(scratch.exists())

    def test_timed_out_build_command_kills_compiler_descendant(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            pidfile = Path(directory) / "child.pid"
            program = ("import pathlib,subprocess,sys,time; "
                       "child=subprocess.Popen(['/bin/sleep','5']); "
                       "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); "
                       "time.sleep(5)")
            result = run_build_command([sys.executable, "-c", program,
                                        str(pidfile)], directory, os.environ, 0.3)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["exit_code"], 124)
            child = int(pidfile.read_text())
            try:
                handle = os.pidfd_open(child)
            except ProcessLookupError:
                return
            try:
                self.assertTrue(_pidfd_exited(handle))
            finally:
                os.close(handle)

    def test_private_build_timeout_keeps_record_and_raw_streams(self):
        archive = os.environ.get("DYN4K_STRACE_SOURCE")
        if not archive:
            self.skipTest("pinned source archive path is not provided")
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            output = Path(directory) / "build"
            with self.assertRaisesRegex(RuntimeError, "private strace build failed"):
                build_tracer(archive, output, timeout=3)
            record = json.loads((output / "build-record.json").read_text())
            self.assertEqual(record["status"], "TIMEOUT")
            self.assertGreaterEqual(len(record["commands"]), 1)
            command = record["commands"][-1]
            self.assertEqual(command["exit_code"], 124)
            self.assertTrue(command["timed_out"])
            self.assertTrue(Path(command["stdout_path"]).is_file())
            self.assertTrue(Path(command["stderr_path"]).is_file())

    def test_blocked_read_has_one_hold_deadline(self):
        class Held:
            resumed = False
            def freeze(self, _phase):
                return None
            def resume(self):
                self.resumed = True
        held = Held()
        samples = []
        started = time.monotonic()
        with mock.patch.object(diagnostic, "_owned_sample",
                               side_effect=lambda *_: time.sleep(6)):
            with self.assertRaises(SnapshotIncomplete) as failure:
                diagnostic._take_owned_sample(samples, {}, "stage", None, {}, held)
        self.assertEqual(failure.exception.detail["reason"], "FREEZE_TIMEOUT")
        self.assertLess(time.monotonic() - started, 5.5)
        self.assertTrue(held.resumed)
        self.assertEqual(samples, [])

    def test_cleanup_identity_failure_still_signals_bound_pidfds(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            owners = [subprocess.Popen(["/bin/sleep", "5"]) for _ in range(2)]
            sentinel = subprocess.Popen(["/bin/sleep", "5"])
            owned = SnapshotOwnedProcesses(directory, directory, _proc_identity,
                                           _pidfd_exited, check_retained)
            try:
                for process in owners:
                    identity = _proc_identity(process.pid)
                    owned._bind("stage", process.pid, identity["start_ticks"],
                                None, os.pidfd_open(process.pid))
                failed_pid = owners[-1].pid
                def read_identity(pid):
                    if pid == failed_pid:
                        raise OSError("injected identity failure")
                    return _proc_identity(pid)
                owned.read_identity = read_identity
                with mock.patch.object(owned, "pump"):
                    with self.assertRaises(SnapshotIncomplete) as failure:
                        owned.stop({"stage"})
                self.assertEqual(failure.exception.detail["reason"],
                                 "CLEANUP_IDENTITY")
                self.assertTrue(all(_pidfd_exited(owned.bound[process.pid]["handle"])
                                    for process in owners))
                self.assertIsNone(sentinel.poll())
            finally:
                for process in (*owners, sentinel):
                    if process.poll() is None:
                        process.send_signal(signal.SIGKILL)
                    process.wait(timeout=3)
                owned.close()

    def test_cleanup_changed_numeric_pid_still_uses_bound_pidfd(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            owner = subprocess.Popen(["/bin/sleep", "5"])
            sentinel = subprocess.Popen(["/bin/sleep", "5"])
            owned = SnapshotOwnedProcesses(directory, directory, _proc_identity,
                                           _pidfd_exited, check_retained)
            try:
                identity = _proc_identity(owner.pid)
                owned._bind("stage", owner.pid, identity["start_ticks"], None,
                            os.pidfd_open(owner.pid))
                def changed_identity(pid):
                    current = _proc_identity(pid)
                    return {**current, "start_ticks": current["start_ticks"] + 1}
                owned.read_identity = changed_identity
                with mock.patch.object(owned, "pump"):
                    with self.assertRaises(SnapshotIncomplete) as failure:
                        owned.stop({"stage"})
                self.assertEqual(failure.exception.detail["reason"],
                                 "PID_IDENTITY_CHANGED")
                self.assertTrue(_pidfd_exited(owned.bound[owner.pid]["handle"]))
                self.assertIsNone(sentinel.poll())
            finally:
                for process in (owner, sentinel):
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=3)
                owned.close()

    def test_source_and_binary_changes_reject_before_rebuild(self):
        binary = os.environ.get("DYN4K_PRIVATE_STRACE")
        if not binary:
            self.skipTest("private tracer path is not provided")
        record = json.loads((Path(binary).parents[1] /
                             "build-record.json").read_text())
        archive = os.environ.get("DYN4K_STRACE_SOURCE")
        if not archive:
            self.skipTest("pinned source archive path is not provided")
        archive = Path(archive)
        files = {"strace-source.tar.xz": archive.read_bytes(),
                 "strace-binary": Path(binary).read_bytes(),
                 "strace-build.json": json.dumps(record).encode()}
        self.assertEqual(diagnostic._tracer_identity(
            files, {"tracer_build": record})["binary_sha256"],
            record["binary_sha256"])
        for name in ("strace-source.tar.xz", "strace-binary"):
            with self.subTest(name=name):
                altered = dict(files)
                altered[name] = files[name][:-1] + bytes([files[name][-1] ^ 1])
                with self.assertRaises(diagnostic.DiagnosticRejected):
                    diagnostic._tracer_identity(altered,
                                                {"tracer_build": record})

    def test_journal_control_and_ack_fail_typed(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            owned = SnapshotOwnedProcesses(directory, directory, _proc_identity,
                                           _pidfd_exited, check_retained)
            record = {"phase": "stage", "operation": "FREEZE",
                      "snapshot_id": 1, "wall_ns": time.time_ns()}
            with mock.patch.object(owned, "check_retained",
                                   side_effect=ValueError("private")):
                with self.assertRaises(SnapshotIncomplete) as failure:
                    owned._write("snapshot-controls.jsonl", record)
                self.assertEqual(failure.exception.detail["reason"],
                                 "JOURNAL_WRITE")
            channel = mock.Mock()
            channel.send.side_effect = OSError("control failed")
            owned.channels["stage"] = channel
            with self.assertRaises(SnapshotIncomplete) as failure:
                owned._command("stage", "FREEZE", 1)
            self.assertEqual(failure.exception.detail["reason"], "CONTROL_SEND")
            channel.send.side_effect = None
            channel.sendall.side_effect = OSError("ack failed")
            owned.holds["stage"] = {"id": 1}
            owned.sequences["stage"] = 0
            with self.assertRaises(SnapshotIncomplete) as failure:
                owned._apply("stage", ["RESUMED", "1", "1"], None)
            self.assertEqual(failure.exception.detail["reason"], "ACK_SEND")

    def test_timeout_tracer_error_and_cleanup_survivor_are_incomplete(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            owned = SnapshotOwnedProcesses(directory, directory,
                                           lambda pid: {"start_ticks": 1},
                                           lambda handle: False, check_retained)
            with self.assertRaises(SnapshotIncomplete) as failure:
                owned._receive_wait("stage", time.monotonic() - 1)
            self.assertEqual(failure.exception.detail["reason"],
                             "CONTROL_TIMEOUT")
            with self.assertRaises(SnapshotIncomplete) as failure:
                owned._apply("stage", ["ERROR", "SPAWN_MESSAGE"], None)
            self.assertEqual(failure.exception.detail["reason"],
                             "SPAWN_MESSAGE")
            owned.roots["stage"] = (12345, Path(directory) / "trace")
            owned.bound[12345] = {"phase": "stage", "handle": 99,
                                  "identity": {"start_ticks": 1}}
            owned.threads["stage"] = {12345: {"tgid": 12345}}
            with mock.patch.object(owned, "pump"), mock.patch(
                    "ordinary_snapshot.control.time.monotonic",
                    side_effect=[0, 0, 6, 6, 12]), mock.patch(
                    "ordinary_snapshot.control.time.sleep"), mock.patch(
                    "ordinary_snapshot.control.signal.pidfd_send_signal") as sent:
                with self.assertRaises(SnapshotIncomplete) as failure:
                    owned.stop({"stage"})
            self.assertEqual(failure.exception.detail["reason"],
                             "CLEANUP_SURVIVOR")
            self.assertEqual([call.args[0] for call in sent.call_args_list], [99])

    def test_four_phase_raw_snapshot_replay(self):
        binary = os.environ.get("DYN4K_PRIVATE_STRACE")
        if not binary:
            self.skipTest("private tracer path is not provided")
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            scratch = Path(directory)
            fixture = scratch / "toy"
            subprocess.run(["gcc", "-O2", "-pthread",
                            str(Path(__file__).with_name("toy.c")), "-o",
                            str(fixture)], check=True, timeout=20)
            owned = SnapshotOwnedProcesses(scratch, scratch, _proc_identity,
                                           _pidfd_exited, check_retained)
            roots = {}
            prefixes = {}
            samples = []
            processes = {}
            try:
                for phase, seconds in (("stage", "0.3"), ("target", "0.4"),
                                       ("helper", "0.4"), ("observer", "0.3")):
                    environment = owned.prepare(phase, os.environ)
                    prefix = scratch / f"{phase}-trace"
                    command = [binary, "-f", "-ff", "-ttt", "-e", "trace=process",
                               "-o", str(prefix),
                               *( [str(fixture), "held_child"] if phase == "stage"
                                  else ["/bin/sleep", seconds])]
                    process = subprocess.Popen(command, env=environment,
                                               stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE)
                    processes[phase] = process
                    owned.launch(phase, process, prefix)
                    roots[phase] = _proc_identity(process.pid)
                    prefixes[phase] = prefix
                    if phase == "stage":
                        self._record_snapshot(owned, phase, samples)
                        self._drain_processes(owned, {phase}, processes)
                    if phase == "helper":
                        self._record_snapshot(owned, "target", samples)
                        self._drain_processes(owned, {"target", "helper"}, processes)
                    if phase == "observer":
                        self._record_snapshot(owned, phase, samples)
                        self._drain_processes(owned, {phase}, processes)
                files = {"stage-process-traces.zip":
                         diagnostic._trace_archive(prefixes["stage"]),
                         "all-process-traces.zip":
                         diagnostic._trace_archive(prefixes["target"]),
                         "helper-traces.zip":
                         diagnostic._trace_archive(prefixes["helper"]),
                         "observer-traces.zip":
                         diagnostic._trace_archive(prefixes["observer"]),
                         "ptrace-events.jsonl":
                         (scratch / "ptrace-events.jsonl").read_bytes(),
                         "snapshot-controls.jsonl":
                         (scratch / "snapshot-controls.jsonl").read_bytes()}
                metadata = {"launch_roots": roots,
                            "owned_processes": owned.evidence(),
                            "birth_clock": diagnostic._birth_clock()}
                with mock.patch.object(diagnostic, "_tracer_identity"):
                    owners, inventory = diagnostic._bound_snapshot(
                        samples, metadata, files)
                self.assertEqual(len(owners), 9)
                self.assertEqual(set(inventory), {"stage", "target", "helper",
                                                  "observer"})
                def rejects(candidate_samples, candidate_files):
                    with mock.patch.object(diagnostic, "_tracer_identity"):
                        with self.assertRaises(diagnostic.DiagnosticRejected):
                            diagnostic._bound_snapshot(candidate_samples,
                                                       metadata, candidate_files)
                events = [json.loads(line) for line in
                          files["ptrace-events.jsonl"].splitlines()]
                birth = next(row for row in events if row["kind"] == "BIRTH")
                changed = [dict(row) for row in events]
                changed[events.index(birth)] = {**birth,
                    "fields": [*birth["fields"]]}
                changed[events.index(birth)]["fields"][2] = "1"
                altered = dict(files)
                altered["ptrace-events.jsonl"] = b"".join(
                    json.dumps(row).encode() + b"\n" for row in changed)
                rejects(samples, altered)
                changed[events.index(birth)]["fields"][2] = birth["fields"][2]
                changed[events.index(birth)]["fields"][3] = birth["fields"][1]
                altered["ptrace-events.jsonl"] = b"".join(
                    json.dumps(row).encode() + b"\n" for row in changed)
                rejects(samples, altered)
                changed = [row for row in events if row["kind"] != "EXIT"]
                altered["ptrace-events.jsonl"] = b"".join(
                    json.dumps(row).encode() + b"\n" for row in changed)
                rejects(samples, altered)
                changed_sample = [dict(row) for row in samples]
                changed_sample[0] = {**samples[0],
                                     "wall_end_ns": samples[0]["wall_end_ns"] +
                                     10_000_000_000}
                rejects(changed_sample, files)
                root = roots["stage"]["pid"]
                changed_sample = json.loads(json.dumps(samples))
                next(row for row in changed_sample[0]["pids"]
                     if row["pid"] == root)["start_ticks"] += 1
                rejects(changed_sample, files)
                controls = [json.loads(line) for line in
                            files["snapshot-controls.jsonl"].splitlines()]
                next(row for row in controls if row.get("operation") == "FREEZE")[
                    "wall_ns"] -= 6_000_000_000
                altered = dict(files)
                altered["snapshot-controls.jsonl"] = b"".join(
                    json.dumps(row).encode() + b"\n" for row in controls)
                rejects(samples, altered)
                for index in (8, 9, 10, 11):
                    changed = json.loads(json.dumps(events))
                    changed[events.index(birth)]["fields"][index] = (
                        "3" if index == 11 else "0")
                    altered = dict(files)
                    altered["ptrace-events.jsonl"] = b"".join(
                        json.dumps(row).encode() + b"\n" for row in changed)
                    rejects(samples, altered)
            finally:
                for process in processes.values():
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=3)
                owned.close()

    def _record_snapshot(self, owned, phase, samples):
        snapshot = owned.freeze(phase)
        began = time.time_ns()
        groups = snapshot["live_tgids"]
        owned.validate_sample(groups)
        ended = time.time_ns()
        samples.append({"phase": phase, "snapshot_id": snapshot["snapshot_id"],
                        "held_sequences": snapshot["held_sequences"],
                        "live_tgids": groups, "wall_start_ns": began,
                        "wall_end_ns": ended,
                        "pids": [{"pid": pid, "start_ticks":
                                  _proc_identity(pid)["start_ticks"]}
                                 for pid in groups]})
        owned.resume()

    def _drain_processes(self, owned, phases, processes):
        deadline = time.monotonic() + 3
        while any(processes[phase].poll() is None for phase in phases):
            self.assertLess(time.monotonic(), deadline)
            owned.pump(phases)
            time.sleep(0.005)
        for phase in phases:
            stdout, stderr = processes[phase].communicate(timeout=3)
            self.assertEqual((processes[phase].returncode, stdout, stderr),
                             (0, b"", b""))
        owned.stop(phases)

    def test_fork_exec_thread_and_untraced_modes(self):
        binary = os.environ.get("DYN4K_PRIVATE_STRACE")
        if not binary:
            self.skipTest("private tracer path is not provided")
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as build_dir:
            fixture = Path(build_dir) / "toy"
            source = Path(__file__).with_name("toy.c")
            subprocess.run(["gcc", "-O2", "-pthread", str(source), "-o",
                            str(fixture)], check=True, timeout=20)
            self._run_modes(binary, fixture)

    def _run_modes(self, binary, fixture):
        modes = [(mode, False) for mode in
                 ("fast", "nested", "group_escape", "parent_exit",
                  "nonleader", "nonleader_hold", "vfork", "clone3",
                  "held_child", "drain_child", "untraced", "untraced_live")]
        modes.append(("fast", True))
        for mode, child_first in modes:
            with self.subTest(mode=mode, child_first=child_first), NativeAttempt(
                    f"mode-{mode}-child-first-{int(child_first)}") as attempt:
                scratch = attempt.scratch
                owned = SnapshotOwnedProcesses(scratch, scratch, _proc_identity,
                                               _pidfd_exited, check_retained)
                environment = owned.prepare("stage", os.environ)
                if child_first:
                    environment["DYN4K_TEST_CHILD_FIRST"] = "1"
                trace = scratch / "trace"
                process = subprocess.Popen([binary, "-f", "-ff", "-ttt", "-e",
                                            "trace=process", "-o", str(trace),
                                            fixture, mode], env=environment,
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
                try:
                    owned.launch("stage", process, trace)
                    if mode in {"held_child", "drain_child"}:
                        deadline = time.monotonic() + 3
                        while (not owned.births["stage"] or
                               (mode == "drain_child" and
                                any(row["tgid"] in
                                    {item["tgid"] for item in
                                     owned.threads["stage"].values()}
                                    for row in owned.births["stage"].values()))):
                            self.assertLess(time.monotonic(), deadline)
                            owned.pump({"stage"})
                            time.sleep(0.001)
                        held = owned.freeze("stage")
                        children = {tid for tid, row in owned.births["stage"].items()
                                    if row["tgid"] == tid}
                        self.assertEqual(bool(children & set(held["live_tgids"])),
                                         mode == "held_child")
                        owned.resume()
                    deadline = time.monotonic() + 3
                    failure = None
                    while process.poll() is None and time.monotonic() < deadline:
                        try:
                            owned.pump({"stage"})
                        except Exception as error:
                            failure = error
                            break
                        time.sleep(0.005)
                    stdout, stderr = process.communicate(timeout=3)
                    attempt.capture(stdout, stderr)
                    if (os.environ.get("DYN4K_INJECT_NATIVE_FAILURE") == mode
                            and not child_first):
                        raise RuntimeError("injected native lifecycle failure")
                    traces, raw_events = diagnostic._raw_events(
                        diagnostic._trace_archive(trace))
                    if mode == "nonleader_hold":
                        with zipfile.ZipFile(io.BytesIO(
                                diagnostic._trace_archive(trace))) as archive:
                            members = {name: archive.read(name)
                                       for name in archive.namelist()}
                        former = next(name for name, raw in members.items()
                                      if b"<pid changed to" in raw)
                        members[former], replaced = re.subn(
                            rb" <pid changed to [1-9][0-9]* \.\.\.>",
                            b" <unfinished ...>) = ?", members[former])
                        self.assertEqual(replaced, 1)
                        def variant_archive(rows):
                            buffer = io.BytesIO()
                            with zipfile.ZipFile(buffer, "w") as archive:
                                for name in (former, *(name for name in rows
                                                       if name != former)):
                                    archive.writestr(name, rows[name])
                            return buffer.getvalue()
                        diagnostic._raw_events(variant_archive(members))
                        malformed = dict(members)
                        leader = next(name for name, raw in members.items()
                                      if b"+++ superseded by execve" in raw)
                        malformed[leader] = members[leader].replace(
                            b"+++ superseded by execve", b"+++ unrelated event")
                        with self.assertRaises((diagnostic.DiagnosticRejected,
                                                diagnostic.actual_trace.TraceRejected)):
                            diagnostic._raw_events(variant_archive(malformed))
                    if mode in {"untraced", "untraced_live"}:
                        self.assertEqual(process.returncode, 0, stderr)
                        with self.assertRaisesRegex(diagnostic.DiagnosticRejected,
                                                    "UNAVAILABLE"):
                            diagnostic._verify_spawn_births(
                                traces, raw_events, owned.births["stage"])
                    else:
                        self.assertIsNone(failure, getattr(failure, "detail", None))
                        self.assertEqual(process.returncode, 0, stderr)
                        diagnostic._verify_spawn_births(
                            traces, raw_events, owned.births["stage"])
                        self.assertTrue(all(os.WIFSTOPPED(row["stop_status"])
                                            and row["ppid"] > 0 and
                                            row["boot_ns"] > 0
                                            for row in owned.births["stage"].values()))
                        if mode == "nested":
                            self.assertTrue(any(row["creator_tid"] !=
                                                row["creator_tgid"] and
                                                row["creator_tgid"] == row["ppid"]
                                                for row in owned.births["stage"].values()))
                        if mode == "vfork":
                            self.assertTrue(all(row["shared_vm"] == 1
                                                for row in owned.births["stage"].values()))
                        owned.stop({"stage"})
                        self.assertGreaterEqual(len(owned.births["stage"]), 1)
                finally:
                    if process.poll() is None:
                        process.kill()
                    final_stdout, final_stderr = process.communicate(timeout=3)
                    if not (scratch / "stdout.raw").exists():
                        attempt.capture(final_stdout, final_stderr)
                    owned.close()

    def test_held_process_has_exact_live_identity_and_resumes(self):
        binary = os.environ.get("DYN4K_PRIVATE_STRACE")
        if not binary:
            self.skipTest("private tracer path is not provided")
        with NativeAttempt("held-process") as attempt:
            sentinel = subprocess.Popen(["/bin/sleep", "1"],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
            scratch = attempt.scratch
            owned = SnapshotOwnedProcesses(scratch, scratch, _proc_identity,
                                           _pidfd_exited, check_retained)
            environment = owned.prepare("stage", os.environ)
            trace = scratch / "trace"
            process = subprocess.Popen([binary, "-f", "-ff", "-ttt", "-e",
                                        "trace=process", "-o", str(trace),
                                        "/bin/sleep", "0.2"], env=environment,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            try:
                owned.launch("stage", process, trace)
                try:
                    held = owned.freeze("stage")
                except Exception as error:
                    self.fail(f"freeze: {getattr(error, 'detail', error)}")
                self.assertEqual(set(held["live_tgids"]), set(owned.refresh({"stage"})))
                self.assertIn(process.pid, held["live_tgids"])
                self.assertNotIn(sentinel.pid, held["live_tgids"])
                self.assertGreaterEqual(len(held["live_tgids"]), 2)
                owned.resume()
                deadline = time.monotonic() + 3
                while process.poll() is None and time.monotonic() < deadline:
                    owned.pump({"stage"})
                    time.sleep(0.005)
                stdout, stderr = process.communicate(timeout=3)
                attempt.capture(stdout, stderr)
                self.assertEqual((process.returncode, stdout, stderr), (0, b"", b""))
                owned.stop({"stage"})
                self.assertIsNone(sentinel.poll())
                self.assertTrue((scratch / "ptrace-events.jsonl").is_file())
                self.assertTrue((scratch / "snapshot-controls.jsonl").is_file())
            finally:
                if process.poll() is None:
                    process.kill()
                final_stdout, final_stderr = process.communicate(timeout=3)
                if not (scratch / "stdout.raw").exists():
                    attempt.capture(final_stdout, final_stderr)
                owned.close()
                sentinel.communicate(timeout=3)

    def test_child_born_during_freeze_drain(self):
        binary = os.environ.get("DYN4K_PRIVATE_STRACE")
        if not binary:
            self.skipTest("private tracer path is not provided")
        with NativeAttempt("freeze-drain-birth") as attempt:
            scratch = attempt.scratch
            fixture = scratch / "toy"
            subprocess.run(["gcc", "-O2", "-pthread",
                            str(Path(__file__).with_name("toy.c")), "-o",
                            str(fixture)], check=True, timeout=20)
            owned = SnapshotOwnedProcesses(scratch, scratch, _proc_identity,
                                           _pidfd_exited, check_retained)
            environment = owned.prepare("stage", os.environ)
            environment["DYN4K_TEST_DRAIN_DELAY"] = "1"
            environment["DYN4K_TEST_DRAIN_BIRTH"] = "1"
            trace = scratch / "trace"
            process = subprocess.Popen([binary, "-f", "-ff", "-ttt", "-e",
                                        "trace=process", "-o", str(trace),
                                        str(fixture), "freeze_birth"],
                                       env=environment, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            try:
                owned.launch("stage", process, trace)
                until = time.monotonic() + 0.005
                while time.monotonic() < until:
                    owned.pump({"stage"})
                    time.sleep(0.001)
                held = owned.freeze("stage")
                expected = sorted({process.pid} | {row["tgid"] for row in
                                                    owned.threads["stage"].values()})
                self.assertEqual(held["live_tgids"], expected)
                controls = [json.loads(line) for line in
                            (scratch / "snapshot-controls.jsonl").read_text().splitlines()]
                freeze = next(row["wall_ns"] for row in controls
                              if row.get("operation") == "FREEZE")
                stop = next(row["wall_ns"] for row in controls
                            if row.get("kind") == "HELD")
                births = [json.loads(line) for line in
                          (scratch / "ptrace-events.jsonl").read_text().splitlines()
                          if json.loads(line)["kind"] == "BIRTH"]
                self.assertTrue(any(freeze <= row["wall_ns"] <= stop
                                    for row in births))
                owned.resume()
                deadline = time.monotonic() + 3
                while process.poll() is None and time.monotonic() < deadline:
                    owned.pump({"stage"})
                    time.sleep(0.002)
                stdout, stderr = process.communicate(timeout=3)
                attempt.capture(stdout, stderr)
                traces, raw = diagnostic._raw_events(
                    diagnostic._trace_archive(trace))
                diagnostic._verify_spawn_births(traces, raw,
                                                owned.births["stage"])
                self.assertEqual(process.returncode, 0)
            finally:
                if process.poll() is None:
                    process.kill()
                final_stdout, final_stderr = process.communicate(timeout=3)
                if not (scratch / "stdout.raw").exists():
                    attempt.capture(final_stdout, final_stderr)
                owned.close()

    def test_cleanup_drains_new_bound_child_without_signaling_sentinel(self):
        binary = os.environ.get("DYN4K_PRIVATE_STRACE")
        if not binary:
            self.skipTest("private tracer path is not provided")
        with NativeAttempt("cleanup-drain-child") as attempt:
            scratch = attempt.scratch
            fixture = scratch / "toy"
            subprocess.run(["gcc", "-O2", "-pthread",
                            str(Path(__file__).with_name("toy.c")), "-o",
                            str(fixture)], check=True, timeout=20)
            sentinel = subprocess.Popen(["/bin/sleep", "5"])
            owned = SnapshotOwnedProcesses(scratch, scratch, _proc_identity,
                                           _pidfd_exited, check_retained)
            environment = owned.prepare("stage", os.environ)
            trace = scratch / "trace"
            process = subprocess.Popen([binary, "-f", "-ff", "-ttt", "-e",
                                        "trace=process", "-o", str(trace),
                                        str(fixture), "held_child"],
                                       env=environment, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            try:
                owned.launch("stage", process, trace)
                deadline = time.monotonic() + 3
                while not owned.births["stage"] and time.monotonic() < deadline:
                    owned.pump({"stage"})
                    time.sleep(0.001)
                self.assertTrue(owned.births["stage"])
                try:
                    owned.stop({"stage"})
                except SnapshotIncomplete as error:
                    self.assertIn(error.detail["reason"],
                                  {"TERMINAL_RECORD_MISSING", "CLEANUP_IDENTITY"})
                self.assertTrue(all(_pidfd_exited(row["handle"])
                                    for row in owned.bound.values()))
                self.assertIsNone(sentinel.poll())
            finally:
                if process.poll() is None:
                    process.kill()
                stdout, stderr = process.communicate(timeout=3)
                attempt.capture(stdout, stderr)
                if sentinel.poll() is None:
                    sentinel.kill()
                sentinel.wait(timeout=3)
                owned.close()


if __name__ == "__main__":
    unittest.main()
