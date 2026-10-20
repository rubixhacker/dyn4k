import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time
import unittest
from unittest import mock

import independent_linux_observer as observer


class IndependentLinuxObserverTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path.home())
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "archive.bin"
        self.archive.write_bytes(b"independent observer test archive")

    def args(self, name="capture", expect=None, script=None):
        if expect is None:
            expect = ["core=/usr/bin/true", "facade=/usr/bin/echo"]
        if script is None:
            script = ('import subprocess; '
                      'subprocess.run(["/usr/bin/true"], check=True); '
                      'subprocess.run(["/usr/bin/echo", "observed"], check=True)')
        return argparse.Namespace(output=str(self.root / name),
                                  candidate_sha="7458ae264a79ce3e6e36fd625afda0fd246be843",
                                  lane="local:observer:test", runtime_identity="linux-x86_64-local",
                                  mode="debug", archive=str(self.archive),
                                  build_executable=None,
                                  artifact=[f"core={self.archive}", f"facade={self.archive}"],
                                  expect=expect, timeout=5, argv=[sys.executable, "-c", script])

    def capture(self, name="capture"):
        args = self.args(name)
        witness = observer.capture(args)
        return Path(args.output), witness

    def rows(self, root):
        return [json.loads(line) for line in (root / "events.jsonl").read_bytes().splitlines()]

    def rechain(self, root, rows):
        head = observer.ZERO
        for sequence, row in enumerate(rows, 1):
            row["seq"] = sequence
            row["previous_sha256"] = head
            row.pop("sha256", None)
            head = hashlib.sha256(observer._json_bytes(row)).hexdigest()
            row["sha256"] = head
        (root / "events.jsonl").write_bytes(b"".join(observer._json_bytes(row) + b"\n"
                                                     for row in rows))

    def test_two_short_lived_children_have_live_images_and_exits(self):
        root, witness = self.capture()
        self.assertEqual("OBSERVED_UNSIGNED", witness["status"])
        self.assertEqual("unqualified", witness["qualification"])
        self.assertEqual(3, witness["coverage"]["processes"])
        self.assertEqual(0, witness["coverage"]["lost_events"])
        self.assertEqual({"core", "facade"}, set(witness["processes"]))
        self.assertEqual(observer._sha_file("/usr/bin/true"),
                         witness["processes"]["core"]["executable_sha256"])
        self.assertEqual(observer._sha_file("/usr/bin/echo"),
                         witness["processes"]["facade"]["executable_sha256"])
        self.assertTrue(all(item["start_ticks"] > 0 for item in witness["processes"].values()))
        self.assertTrue(all(item["exit_code"] == 0 for item in witness["processes"].values()))
        self.assertEqual(witness, observer.verify(root))

    def test_nested_fork_exec_tree_has_causal_parent(self):
        script = ('import os,sys\n'
                  'pid=os.fork()\n'
                  'if pid==0:\n'
                  ' os.execv(sys.executable,[sys.executable,"-c",'
                  '"import subprocess; subprocess.run([\\"/usr/bin/echo\\",'
                  '\\"nested\\"],check=True)"])\n'
                  'os.waitpid(pid,0)\n')
        args = self.args("tree", [f"core={sys.executable}", "facade=/usr/bin/echo"], script)
        witness = observer.capture(args)
        self.assertEqual(witness["processes"]["core"]["pid"],
                         witness["processes"]["facade"]["parent_pid"])
        self.assertGreaterEqual(witness["coverage"]["images"], 5)
        self.assertEqual(witness, observer.verify(args.output))

    def test_selected_build_child_contains_selected_executions(self):
        script = ('import subprocess; '
                  'subprocess.run(["/bin/sh", "-c", '
                  '"/usr/bin/true; /usr/bin/echo nested-build; :"], check=True)')
        args = self.args("selected-build", script=script)
        args.build_executable = "/bin/sh"
        witness = observer.capture(args)
        self.assertNotEqual(witness["build"]["pid"],
                            next(row["root_pid"] for row in self.rows(Path(args.output))
                                 if row["kind"] == "run"))
        self.assertEqual(observer._sha_file(Path("/bin/sh").resolve()),
                         witness["build"]["executable_sha256"])
        self.assertTrue(all(process["parent_pid"] == witness["build"]["pid"]
                            for process in witness["processes"].values()))
        self.assertEqual(witness, observer.verify(args.output))

    def test_build_only_launcher_change_fails_after_live_execution(self):
        launcher = self.root / "changing-launcher.sh"
        launcher.write_text('#!/bin/sh\nprintf x >> "$0"\nexit 0\n')
        launcher.chmod(0o700)
        args = self.args("changed-launcher", expect=[])
        args.argv = [str(launcher)]
        args.build_executable = "/bin/sh"
        args.launcher_script = str(launcher)
        args.build_only = True
        with self.assertRaisesRegex(observer.ObservationError,
                                    "launcher changed across observed execution"):
            observer.capture(args)
        self.assertFalse((Path(args.output) / "witness.json").exists())

    def test_generated_child_image_is_selected_from_stopped_exec(self):
        generated = self.root / "generated-true"
        script = (f'import os,shutil,subprocess; p={str(generated)!r}; '
                  'shutil.copyfile("/usr/bin/true", p); os.chmod(p, 0o700); '
                  'subprocess.run([p], check=True); '
                  'subprocess.run(["/usr/bin/echo", "generated"], check=True)')
        args = self.args("generated", ["facade=/usr/bin/echo"], script)
        args.generated_expect = [f"core={generated}"]
        witness = observer.capture(args)
        self.assertEqual(observer._sha_file(generated),
                         witness["processes"]["core"]["executable_sha256"])
        self.assertEqual(witness, observer.verify(args.output))

    def test_generated_child_wrong_path_fails_closed(self):
        args = self.args("generated-wrong", ["facade=/usr/bin/echo"])
        args.generated_expect = [f"core={self.root / 'missing-true'}"]
        with self.assertRaisesRegex(observer.ObservationError,
                                    "expected executable was not observed: core"):
            observer.capture(args)
        self.assertFalse((Path(args.output) / "witness.json").exists())

    def test_disappeared_exit_stop_waits_for_terminal_status_only(self):
        with mock.patch.object(observer, "_ptrace",
                               side_effect=ProcessLookupError(errno.ESRCH, "already exited")):
            observer._continue_tracee(31, observer.EVENT_EXIT, signal.SIGTRAP)
            with self.assertRaises(ProcessLookupError):
                observer._continue_tracee(31, observer.EVENT_CLONE, signal.SIGTRAP)

    def test_route_process_limit_fails_closed_and_is_replayed(self):
        args = self.args("too-many-processes")
        args.max_processes = 2
        with self.assertRaisesRegex(observer.ObservationError, "excessive traced child"):
            observer.capture(args)
        self.assertFalse((Path(args.output) / "witness.json").exists())
        root, _ = self.capture("limit-replay")
        rows = self.rows(root)
        rows[0]["limits"]["processes"] = 2
        self.rechain(root, rows)
        with self.assertRaisesRegex(observer.ObservationError, "excessive process creation"):
            observer.verify(root)

    def test_route_limit_above_hard_ceiling_is_rejected_before_launch(self):
        args = self.args("invalid-route-limit")
        args.max_processes = observer.MAX_PROCESSES + 1
        with self.assertRaisesRegex(observer.ObservationError, "limit is invalid"):
            observer.capture(args)
        self.assertFalse(Path(args.output).exists())

    def test_event_limit_below_retained_trace_floor_is_rejected_before_launch(self):
        for value in (1, 2, observer.DEFAULT_EVENTS - 1):
            with self.subTest(value=value):
                args = self.args(f"small-event-limit-{value}")
                args.max_events = value
                with self.assertRaisesRegex(observer.ObservationError, "limit is invalid"):
                    observer.capture(args)
                self.assertFalse(Path(args.output).exists())

    def test_log_byte_limit_below_retained_trace_floor_is_rejected_before_launch(self):
        for value in (1, 1000, observer.DEFAULT_LOG_BYTES - 1):
            with self.subTest(value=value):
                args = self.args(f"small-log-limit-{value}")
                args.max_log_bytes = value
                with self.assertRaisesRegex(observer.ObservationError, "limit is invalid"):
                    observer.capture(args)
                self.assertFalse(Path(args.output).exists())

    def test_event_writer_keeps_terminal_slots_and_bytes(self):
        count_log = observer.EventLog(self.root / "count-reserve", event_limit=4)
        try:
            count_log.add("run")
            count_log.add("spawn")
            with self.assertRaisesRegex(observer.ObservationError, "event limit exceeded"):
                count_log.add("image")
            count_log.add("error", message="event limit exceeded")
            count_log.add("end", result="failed", lost_events=1)
        finally:
            count_log.close()
        self.assertEqual(["run", "spawn", "error", "end"],
                         [row["kind"] for row in self.rows(count_log.root)])

        byte_log = observer.EventLog(self.root / "byte-reserve", byte_limit=8192)
        try:
            byte_log.add("run")
            while True:
                try:
                    byte_log.add("sample", payload="x" * 128)
                except observer.ObservationError as error:
                    self.assertIn("byte limit exceeded", str(error))
                    break
            byte_log.add("error", message="byte limit exceeded")
            byte_log.add("end", result="failed", lost_events=1)
        finally:
            byte_log.close()
        self.assertEqual(["error", "end"],
                         [row["kind"] for row in self.rows(byte_log.root)[-2:]])

    def test_build_argv_marker_skips_preflight_interpreter(self):
        script = ('import subprocess; '
                  'subprocess.run(["/bin/sh", "-c", "/usr/bin/true"], check=True); '
                  'subprocess.run(["/bin/sh", "-c", '
                  '"/usr/bin/true; /usr/bin/echo selected; :", "build-marker"], check=True)')
        args = self.args("build-marker", script=script)
        args.build_executable = "/bin/sh"
        args.build_argv_contains = ["build-marker"]
        witness = observer.capture(args)
        self.assertIn("build-marker", witness["build"]["argv"])
        self.assertEqual(witness, observer.verify(args.output))

    def test_changed_event_byte_is_rejected(self):
        root, _ = self.capture()
        path = root / "events.jsonl"
        raw = path.read_bytes()
        path.write_bytes(raw.replace(b"local:observer:test", b"focal:observer:test", 1))
        with self.assertRaisesRegex(observer.ObservationError, "changed event bytes"):
            observer.verify(root)

    def test_missing_event_is_rejected(self):
        root, _ = self.capture()
        path = root / "events.jsonl"
        lines = path.read_bytes().splitlines(keepends=True)
        path.write_bytes(b"".join(lines[:3] + lines[4:]))
        with self.assertRaisesRegex(observer.ObservationError, "gap"):
            observer.verify(root)

    def test_wrong_pid_start_identity_is_rejected_after_rechain(self):
        root, _ = self.capture()
        rows = self.rows(root)
        image = next(row for row in rows if row["kind"] == "image")
        image["start_ticks"] += 1
        self.rechain(root, rows)
        with self.assertRaisesRegex(observer.ObservationError, "wrong PID-start"):
            observer.verify(root)

    def test_lost_event_counter_is_rejected_after_rechain(self):
        root, _ = self.capture()
        rows = self.rows(root)
        rows[-1]["lost_events"] = 1
        self.rechain(root, rows)
        with self.assertRaisesRegex(observer.ObservationError, "lost events"):
            observer.verify(root)

    def test_unobserved_child_image_is_rejected_after_rechain(self):
        root, _ = self.capture()
        rows = self.rows(root)
        child = next(row["pid"] for row in rows if row["kind"] == "spawn" and
                     row["origin"] != "traceme")
        rows = [row for row in rows if not (row["kind"] == "image" and row["pid"] == child)]
        self.rechain(root, rows)
        with self.assertRaisesRegex(observer.ObservationError, "without a captured image"):
            observer.verify(root)

    def test_post_execution_directory_archive_matches_central_digest(self):
        import independent_gates

        archive = self.root / "produced-archive"
        script = (f'import pathlib,subprocess; p=pathlib.Path({str(archive)!r}); '
                  'p.mkdir(); (p/"receipt.json").write_text("{}"); '
                  'subprocess.run(["/usr/bin/true"],check=True); '
                  'subprocess.run(["/usr/bin/echo","archive"],check=True)')
        args = self.args("archive-capture", script=script)
        args.archive = str(archive)
        witness = observer.capture(args)
        self.assertEqual(independent_gates.archive_digest(archive), witness["archive_sha256"])
        self.assertEqual(witness, observer.verify(args.output))

    def test_regular_file_archive_over_byte_limit_is_rejected(self):
        archive = self.root / "large-regular-archive"
        archive.write_bytes(b"ab")
        with mock.patch.object(observer, "MAX_ARCHIVE_BYTES", 1):
            with self.assertRaisesRegex(observer.ObservationError, "archive byte limit"):
                observer._archive_digest(archive)
        with mock.patch.object(observer, "MAX_ARCHIVE_BYTES", 2):
            self.assertEqual(hashlib.sha256(b"ab").hexdigest(),
                             observer._archive_digest(archive))

    def test_preflight_input_over_byte_limit_is_rejected(self):
        args = self.args("large-preflight")
        with mock.patch.object(observer, "MAX_INPUT_BYTES", 1):
            with self.assertRaisesRegex(observer.ObservationError, "input byte limit"):
                observer.capture(args)
        self.assertFalse(Path(args.output).exists())

    def test_slow_preflight_read_obeys_whole_capture_timeout(self):
        args = self.args("slow-preflight")
        args.timeout = 0.02
        original = observer._sha_file
        delayed = False

        def slow_once(*call_args, **call_kwargs):
            nonlocal delayed
            if not delayed:
                delayed = True
                time.sleep(0.4)
            return original(*call_args, **call_kwargs)

        started = time.monotonic()
        with mock.patch.object(observer, "_sha_file", side_effect=slow_once):
            with self.assertRaisesRegex(observer.ObservationError, "trace timeout"):
                observer.capture(args)
        self.assertLess(time.monotonic() - started, 0.3)
        self.assertFalse(Path(args.output).exists())

    def test_blocked_wall_clock_signal_is_rejected(self):
        args = self.args("blocked-timer")
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        try:
            with self.assertRaisesRegex(observer.ObservationError, "timer signal is blocked"):
                observer.capture(args)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
        self.assertFalse(Path(args.output).exists())

    def test_live_image_over_byte_limit_fails_closed(self):
        args = self.args("large-image")
        with mock.patch.object(observer, "MAX_IMAGE_BYTES", 1):
            with self.assertRaisesRegex(observer.ObservationError, "process image byte limit"):
                observer.capture(args)
        rows = self.rows(Path(args.output))
        self.assertEqual("error", rows[-2]["kind"])
        self.assertFalse((Path(args.output) / "witness.json").exists())

    def test_slow_live_image_read_obeys_whole_capture_timeout(self):
        args = self.args("slow-image")
        args.timeout = 0.02
        original = os.read
        delayed = False

        def slow_once(fd, size):
            nonlocal delayed
            if size == 1024 * 1024 and not delayed:
                delayed = True
                time.sleep(0.4)
            return original(fd, size)

        started = time.monotonic()
        with mock.patch.object(observer.os, "read", side_effect=slow_once):
            with self.assertRaisesRegex(observer.ObservationError, "trace timeout"):
                observer.capture(args)
        self.assertLess(time.monotonic() - started, 0.3)
        rows = self.rows(Path(args.output))
        self.assertEqual("error", rows[-2]["kind"])
        self.assertFalse((Path(args.output) / "witness.json").exists())

    def test_wrong_expected_executable_fails_with_error_event(self):
        args = self.args("wrong-image", ["core=/usr/bin/false", "facade=/usr/bin/echo"])
        with self.assertRaisesRegex(observer.ObservationError,
                                    "expected executable was not observed: core"):
            observer.capture(args)
        self.assertFalse((Path(args.output) / "witness.json").exists())
        self.assertIn("expected executable was not observed: core",
                      self.rows(Path(args.output))[-2]["message"])

    def test_symlink_hardlink_and_traversal_outputs_are_rejected(self):
        root, _ = self.capture()
        shortcut = self.root / "shortcut"
        shortcut.symlink_to(root, target_is_directory=True)
        with self.assertRaisesRegex(observer.ObservationError, "symbolic"):
            observer.verify(shortcut)
        with self.assertRaisesRegex(observer.ObservationError, "traversal"):
            observer.verify(root / ".." / root.name)
        hardlink = self.root / "witness-hardlink.json"
        os.link(root / "witness.json", hardlink)
        with self.assertRaisesRegex(observer.ObservationError, "hardlinked"):
            observer.verify(root)
        hardlink.unlink()
        copy = self.root / "witness-copy.json"
        shutil.copyfile(root / "witness.json", copy)
        (root / "witness.json").unlink()
        (root / "witness.json").symlink_to(copy)
        with self.assertRaisesRegex(observer.ObservationError, "symbolic"):
            observer.verify(root)

    def test_denied_trace_is_recorded_and_fails_closed(self):
        args = self.args("denied")
        original = observer._ptrace

        def denied(request, pid, data=0):
            if request == observer.PTRACE_TRACEME:
                raise OSError(errno.EPERM, "trace permission denied")
            return original(request, pid, data)

        with mock.patch.object(observer, "_ptrace", side_effect=denied):
            with self.assertRaisesRegex(observer.ObservationError, "PermissionError"):
                observer.capture(args)
        rows = self.rows(Path(args.output))
        self.assertEqual("error", rows[-2]["kind"])
        self.assertIn("trace permission denied", rows[-2]["message"])
        self.assertEqual("failed", rows[-1]["result"])
        self.assertFalse((Path(args.output) / "witness.json").exists())

    def test_kernel_denied_trace_control_fails_closed(self):
        if os.uname().machine != "x86_64":
            self.skipTest("ptrace syscall number in this control is x86_64 specific")
        args = self.args("kernel-denied")
        original = observer._launch

        class Filter(ctypes.Structure):
            _fields_ = (("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                        ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32))

        class Program(ctypes.Structure):
            _fields_ = (("length", ctypes.c_ushort),
                        ("filters", ctypes.POINTER(Filter)))

        def deny_ptrace(argv, pipe):
            libc = ctypes.CDLL(None, use_errno=True)
            filters = (Filter * 4)(Filter(0x20, 0, 0, 0),
                                   Filter(0x15, 0, 1, 101),
                                   Filter(0x06, 0, 0, 0x00050000 | errno.EPERM),
                                   Filter(0x06, 0, 0, 0x7fff0000))
            program = Program(len(filters), filters)
            if (libc.prctl(38, 1, 0, 0, 0) != 0 or
                    libc.prctl(22, 2, ctypes.byref(program)) != 0):
                os.write(pipe, f"seccomp setup failed: {ctypes.get_errno()}".encode())
                os._exit(125)
            original(argv, pipe)

        with mock.patch.object(observer, "_launch", side_effect=deny_ptrace):
            with self.assertRaisesRegex(observer.ObservationError, "Operation not permitted"):
                observer.capture(args)
        rows = self.rows(Path(args.output))
        self.assertEqual("error", rows[-2]["kind"])
        self.assertIn("Operation not permitted", rows[-2]["message"])
        self.assertEqual(1, rows[-1]["lost_events"])
        self.assertFalse((Path(args.output) / "witness.json").exists())


if __name__ == "__main__":
    unittest.main()
