import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import linux_observed_klib as route


class LinuxObservedKlibTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.launcher = self.root / "gradle"
        self.launcher.write_bytes(b"#!/bin/sh\nexec \"$JAVA_HOME/bin/java\" \"$@\"\n")
        self.selection = {"gradle": str(self.launcher), "lane":
                          "linuxX64:Linux x64:current:debug-g",
                          "launcher_sha256": hashlib.sha256(self.launcher.read_bytes()).hexdigest(),
                          "toolchain": {"java_sha256": "a" * 64}}
        self.build = {"pid": 31, "executable_path": "/jdk/bin/java",
                      "executable_sha256": "a" * 64,
                      "argv": ["/jdk/bin/java", "org.gradle.launcher.GradleMain",
                               "qualificationEvidence", self.selection["lane"]]}
        self.rows = [
            {"kind": "image", "pid": 30, "seq": 1,
             "argv": ["/bin/sh", str(self.launcher)],
             "executable_path": "/bin/sh", "executable_sha256": "b" * 64},
            {"kind": "image", "pid": 31, "seq": 2,
             "argv": ["/bin/sh", str(self.launcher)],
             "executable_path": "/bin/sh", "executable_sha256": "b" * 64},
            {"kind": "image", "pid": 31, "seq": 3,
             "argv": self.build["argv"], "executable_path": "/jdk/bin/java",
             "executable_sha256": "a" * 64},
        ]

    def bind_fixture_launcher(self, rows, build):
        if sys.platform == "linux":
            return route._launcher_binding(rows, build, self.selection)
        with mock.patch.object(route, "_sha", side_effect=lambda path: hashlib.sha256(
                Path(path).read_bytes()).hexdigest()):
            return route._launcher_binding(rows, build, self.selection)

    def test_portable_source_manifest_inventory(self):
        builds = route.klib.consumer_builds(2)
        repository = Path(__file__).resolve().parents[2]
        self.assertEqual(9, len(builds))
        self.assertTrue(all((repository / path).is_file() for path in builds))
        self.assertEqual({"linuxX64:Linux x64:current:debug-g",
                          "linuxX64:Linux x64:current:optimized-opt"}, route.LANES)

    def test_linux_fd_seal_rejects_symbolic_launcher(self):
        if sys.platform != "linux":
            self.skipTest("Linux O_CLOEXEC and O_NOFOLLOW file sealing unavailable")
        self.assertEqual(self.selection["launcher_sha256"], route._sha(self.launcher))
        shortcut = self.root / "launcher-link"
        shortcut.symlink_to(self.launcher)
        with self.assertRaises(OSError):
            route._sha(shortcut)

    def test_launcher_requires_same_pid_shell_then_selected_java(self):
        script, image = self.bind_fixture_launcher(self.rows, self.build)
        self.assertEqual(31, script["pid"])
        self.assertEqual(3, image["seq"])
        with self.assertRaisesRegex(ValueError, "script-to-Java"):
            self.bind_fixture_launcher([self.rows[0], self.rows[2]], self.build)

    def test_launcher_rejects_wrong_task_and_changed_script(self):
        changed = dict(self.build, argv=["/jdk/bin/java", "--version"])
        with self.assertRaisesRegex(ValueError, "task argv"):
            self.bind_fixture_launcher(self.rows, changed)
        self.launcher.write_bytes(b"#!/bin/sh\nexec /usr/bin/false\n")
        with self.assertRaisesRegex(ValueError, "script-to-Java"):
            self.bind_fixture_launcher(self.rows, self.build)

    def test_record_rejects_changed_bytes_and_hardlinks(self):
        record = self.root / "record.json"
        record.write_bytes(route._json({"status": "OBSERVED_UNSIGNED"}))
        self.assertEqual("OBSERVED_UNSIGNED", route._read(record)["status"])
        record.write_text(json.dumps({"status": "OBSERVED_UNSIGNED"}, indent=2))
        with self.assertRaisesRegex(ValueError, "noncanonical"):
            route._read(record)
        record.write_bytes(route._json({"status": "OBSERVED_UNSIGNED"}))
        os.link(record, self.root / "record-hardlink.json")
        with self.assertRaisesRegex(ValueError, "one regular file"):
            route._read(record)

    def test_public_replay_reselects_source_and_tools(self):
        (self.root / "selection.json").write_bytes(route._json({
            "candidate_sha": "a" * 40, "lane": self.selection["lane"],
            "staging": "/stage", "gradle": str(self.launcher), "node": "/node",
            "java_home": "/jdk", "gradle_user_home": "/gradle-cache",
            "konan_data_dir": "/konan"}))
        (self.root / "record.json").write_bytes(route._json({"status": "OBSERVED_UNSIGNED"}))
        with mock.patch.object(route, "_selection", return_value={"different": True}) as selected, \
                mock.patch.object(route, "_derive", side_effect=AssertionError("reached archive")):
            with self.assertRaisesRegex(ValueError, "selection differs"):
                route.verify(self.root, self.root)
        selected.assert_called_once_with(self.root, "a" * 40, self.selection["lane"],
                                         "/stage", str(self.launcher), "/node", "/jdk",
                                         "/gradle-cache", "/konan")

    def test_capture_command_wires_reviewed_source_producer_to_observer(self):
        candidate = "a" * 40
        staging = self.root / "stage"
        staging.mkdir()
        args = argparse.Namespace(repository="/var/home/stewart/Workspace/dyn4k-port-linux-observed-klib-112",
                                  candidate_sha=candidate, lane=self.selection["lane"],
                                  staging=str(staging), output=str(self.root / "route"),
                                  gradle=str(self.launcher), node="/usr/local/bin/node",
                                  java_home=str(self.root), gradle_user_home=str(self.root),
                                  konan_data_dir=str(self.root), android_home=str(self.root),
                                  tmpdir=str(self.root), timeout=90)
        selection = {"repository": args.repository, "candidate_sha": candidate,
                     "lane": args.lane, "staging": str(staging),
                     "gradle": args.gradle, "node": args.node,
                     "java_home": args.java_home, "gradle_user_home": args.gradle_user_home,
                     "konan_data_dir": args.konan_data_dir, "runtime_identity": "fixture",
                     "mode": "debug-g", "java_tool_options": "-XX:ActiveProcessorCount=2",
                     "staged_artifacts": {"dyn4k-core": "b" * 64, "dyn4k": "c" * 64}}
        with mock.patch.object(route, "_selection", return_value=selection), \
                mock.patch.object(route.subprocess, "run",
                                  return_value=argparse.Namespace(returncode=0)) as launched, \
                mock.patch.object(route, "_derive", return_value={"status": "OBSERVED_UNSIGNED"}):
            self.assertEqual("OBSERVED_UNSIGNED", route.capture(args)["status"])
        command = launched.call_args.args[0]
        self.assertIn("full_klib_consumer.py", " ".join(command))
        self.assertIn("run", command)
        self.assertEqual(2, command.count("--expect-generated"))
        self.assertEqual(2, command.count("--artifact"))
        self.assertIn("--max-processes", command)
        self.assertEqual("1024", command[command.index("--max-processes") + 1])
        self.assertEqual("-XX:ActiveProcessorCount=2",
                         launched.call_args.kwargs["env"]["JAVA_TOOL_OPTIONS"])
        self.assertEqual("fixture", route._read(self.root / "route/selection.json")
                         ["runtime_identity"])


if __name__ == "__main__":
    unittest.main()
