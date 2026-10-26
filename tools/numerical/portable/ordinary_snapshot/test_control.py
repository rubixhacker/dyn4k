import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from ordinary_snapshot.control import SnapshotIncomplete, SnapshotOwnedProcesses
from ordinary_arithmetic_diagnostic import _pidfd_exited, _proc_identity, check_retained
import ordinary_arithmetic_diagnostic as diagnostic


class NativeSnapshotControlTest(unittest.TestCase):
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
        for mode in ("fast", "nested", "group_escape", "parent_exit",
                     "nonleader", "nonleader_hold", "vfork", "clone3",
                     "held_child", "drain_child", "untraced"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(
                    dir=os.environ["TMPDIR"]) as directory:
                scratch = Path(directory)
                owned = SnapshotOwnedProcesses(scratch, scratch, _proc_identity,
                                               _pidfd_exited, check_retained)
                environment = owned.prepare("stage", os.environ)
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
                    traces, raw_events = diagnostic._raw_events(
                        diagnostic._trace_archive(trace))
                    if mode == "untraced":
                        with self.assertRaisesRegex(diagnostic.DiagnosticRejected,
                                                    "UNAVAILABLE"):
                            diagnostic._verify_spawn_births(
                                traces, raw_events, owned.births["stage"])
                    else:
                        self.assertIsNone(failure, getattr(failure, "detail", None))
                        self.assertEqual(process.returncode, 0, stderr)
                        diagnostic._verify_spawn_births(
                            traces, raw_events, owned.births["stage"])
                        owned.stop({"stage"})
                        self.assertGreaterEqual(len(owned.births["stage"]), 1)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=3)
                    owned.close()

    def test_held_process_has_exact_live_identity_and_resumes(self):
        binary = os.environ.get("DYN4K_PRIVATE_STRACE")
        if not binary:
            self.skipTest("private tracer path is not provided")
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            scratch = Path(directory)
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
                self.assertGreaterEqual(len(held["live_tgids"]), 2)
                owned.resume()
                deadline = time.monotonic() + 3
                while process.poll() is None and time.monotonic() < deadline:
                    owned.pump({"stage"})
                    time.sleep(0.005)
                stdout, stderr = process.communicate(timeout=3)
                self.assertEqual((process.returncode, stdout, stderr), (0, b"", b""))
                owned.stop({"stage"})
                self.assertTrue((scratch / "ptrace-events.jsonl").is_file())
                self.assertTrue((scratch / "snapshot-controls.jsonl").is_file())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)
                owned.close()


if __name__ == "__main__":
    unittest.main()
