import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import reference_study_producer as producer


SOURCE = Path(__file__).with_name("reference_study_producer.py")
JDK = Path("/tmp/dyn4k-tools/jdk21")
GRADLE = Path("/tmp/dyn4k-tools/gradle-9.5.0/bin/gradle")
BASELINE = Path("/tmp/dyn4k-performance-dyn4j-6.0.0.jar")


class ReferenceStudyProducerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(dir=Path.home())
        cls.root = Path(cls.temporary.name)
        cls.output = cls.root / "production"
        cls.key = cls.root / "operator.key"
        cls.key.write_bytes(b"independent-reference-study-test-key-" * 2)
        cls.env = os.environ.copy()
        cls.env.pop("OLLAMA_API_KEY", None)
        cls.env.update(JAVA_HOME=str(JDK), TMPDIR=str(cls.root),
                       JAVA_TOOL_OPTIONS=f"-Djava.io.tmpdir={cls.root}",
                       PYTHONDONTWRITEBYTECODE="1")
        cls.keyed_env = dict(cls.env, OLLAMA_API_KEY="synthetic-reference-study-key")
        cls.result = subprocess.run(
            [sys.executable, str(SOURCE), "capture", "--output-root", str(cls.output),
             "--trusted-key", str(cls.key), "--java", str(JDK / "bin/java"),
             "--javac", str(JDK / "bin/javac"), "--gradle", str(GRADLE),
             "--baseline", str(BASELINE), "--seconds", "1", "--warmup-seconds", "1"],
            env=cls.keyed_env, capture_output=True, text=True, timeout=240)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_real_frozen_pair_set_keeps_unpassed(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        result = json.loads(self.result.stdout)
        self.assertEqual(result["study"], "structurally_verified")
        self.assertEqual(result["qualification"], "unpassed")
        self.assertEqual(result["validated_reference_rows"], 0)
        captures = json.loads((self.output / "captures.json").read_text())
        self.assertEqual([(row["pair"], row["side"], row["order"]) for row in captures],
                         [(1, "a", 1), (1, "b", 2), (2, "b", 1),
                          (2, "a", 2), (3, "a", 1), (3, "b", 2)])
        self.assertEqual(len({(row["boot_id"], row["os_pid"], row["process_start_id"])
                              for row in captures}), 6)
        self.assertEqual(len({row["run_id"] for row in captures}), 6)
        for ordinal, row in enumerate(captures):
            series = (self.output / row["series_path"]).read_text()
            self.assertEqual(len(series.splitlines()), 31)
            self.assertTrue(series.startswith("step,elapsed_ns,"))
            monitor = json.loads((self.output / row["monitor_path"]).read_text())
            self.assertEqual(monitor["os_pid"], row["os_pid"])
            self.assertEqual(monitor["process_start_id"], row["process_start_id"])
            self.assertTrue(monitor["samples"])
            self.assertEqual(monitor["launch_nonce"], row["run_id"])
        audit = subprocess.run([sys.executable, str(SOURCE), "audit", "--output-root",
                                str(self.output), "--trusted-key", str(self.key)],
                               env=self.env, capture_output=True, text=True)
        self.assertEqual(audit.returncode, 0, audit.stdout + audit.stderr)
        marker = self.keyed_env["OLLAMA_API_KEY"].encode()
        self.assertFalse(any(marker in path.read_bytes()
                             for path in self.output.rglob("*") if path.is_file()))

    def test_distinct_real_java_processes_can_emit_identical_zero_series(self):
        from reference_study_producer import observe_process

        source = self.root / "ZeroSeries.java"
        source.write_text("public class ZeroSeries { public static void main(String[] a) "
                          "throws Exception { if (System.getenv(\"OLLAMA_API_KEY\") != null) "
                          "throw new Error(\"ambient key leaked\"); "
                          "System.out.println(0); Thread.sleep(200); } }")
        subprocess.run([str(JDK / "bin/javac"), str(source)], check=True, env=self.env)
        command = [str(JDK / "bin/java"), "-cp", str(self.root), "ZeroSeries"]
        digest = hashlib.sha256((JDK / "bin/java").read_bytes()).hexdigest()
        observed = [observe_process(command, self.keyed_env, self.root / f"zero-{index}",
                                    f"zero-{index}", digest, timeout=5)
                    for index in (1, 2)]
        self.assertEqual([(self.root / f"zero-{index}" / "series.csv").read_bytes()
                          for index in (1, 2)], [b"0\n", b"0\n"])
        self.assertNotEqual(observed[0]["process_id"], observed[1]["process_id"])
        self.assertNotEqual(observed[0]["os_pid"], observed[1]["os_pid"])

    def test_helper_children_strip_synthetic_key(self):
        seen = []

        def fake_run(command, **kwargs):
            seen.append(kwargs.get("env"))
            output = "tree\n" if command[0] == "git" else "{}"
            return subprocess.CompletedProcess(command, 0, output, "")

        with mock.patch.dict(os.environ, {"OLLAMA_API_KEY": self.keyed_env["OLLAMA_API_KEY"]}), \
                mock.patch.object(producer.subprocess, "run", side_effect=fake_run):
            producer.source_trees("HEAD")
            producer.run_checked(["helper"], self.root, self.keyed_env,
                                 self.root / "helper.stdout", self.root / "helper.stderr", 1)
            producer.study_cli("verify", self.root, self.key)
        self.assertEqual(len(seen), 4)
        self.assertTrue(all(value is not None and "OLLAMA_API_KEY" not in value
                            for value in seen))

    def observe_fake_process(self, name, command_read, rss_read,
                             environment_read=None, image_read=None, start_read=None,
                             timeout=1):
        command = [str(JDK / "bin/java"), "fixture"]
        state = {"exited": False}

        class Process:
            pid = 12345

            def poll(self):
                return 0 if state["exited"] else None

            def wait(self):
                return 0

            def kill(self):
                state["exited"] = True

        def read_command(pid):
            return command_read(command, state)

        def read_rss(pid):
            return rss_read(state)

        def read_environment(pid):
            if environment_read is not None:
                return environment_read(state)
            return {"DYN4K_CLOCK_NONCE": "nonce"}

        def read_image(pid):
            if image_read is not None:
                return image_read(command, state)
            return {"sha256": "image", "executable_path": command[0]}

        def read_start(pid):
            return start_read(state) if start_read is not None else 11

        with mock.patch.object(producer.subprocess, "Popen", return_value=Process()), \
                mock.patch.object(producer, "host_identity", return_value=("host", "boot")), \
                mock.patch.object(producer, "observe_process_image", side_effect=read_image), \
                mock.patch.object(producer, "process_start_ticks", side_effect=read_start), \
                mock.patch.object(producer, "process_command", side_effect=read_command), \
                mock.patch.object(producer, "process_environment",
                                  side_effect=read_environment), \
                mock.patch.object(producer, "process_rss_bytes", side_effect=read_rss):
            return producer.observe_process(command, self.keyed_env, self.root / name,
                                            "nonce", "image", timeout=timeout)

    def test_nonempty_command_mismatch_before_exit_is_rejected_without_argv(self):
        calls = 0

        def command_read(command, state):
            nonlocal calls
            calls += 1
            if calls == 2:
                state["exited"] = True
                return [*command, self.keyed_env["OLLAMA_API_KEY"]]
            return command

        with self.assertRaises(ValueError) as caught:
            self.observe_fake_process("mismatched-command", command_read,
                                      lambda state: 1024)
        self.assertTrue(str(caught.exception) == "observed process command differs")
        self.assertFalse(self.keyed_env["OLLAMA_API_KEY"] in str(caught.exception))

    def test_nonempty_mismatch_rejects_before_terminal_environment_loss(self):
        calls = 0

        def command_read(command, state):
            nonlocal calls
            calls += 1
            if calls == 2:
                state["mismatch"] = True
                state["exited"] = True
                return [*command, self.keyed_env["OLLAMA_API_KEY"]]
            return command

        def environment_read(state):
            if state.get("mismatch"):
                raise FileNotFoundError("procfs environment vanished")
            return {"DYN4K_CLOCK_NONCE": "nonce"}

        with self.assertRaises(ValueError) as caught:
            self.observe_fake_process("mismatch-before-env", command_read,
                                      lambda state: 1024, environment_read=environment_read)
        self.assertTrue(str(caught.exception) == "observed process command differs")
        self.assertFalse(self.keyed_env["OLLAMA_API_KEY"] in str(caught.exception))

    def test_wrong_image_after_complete_sample_rejects_before_exit(self):
        calls = 0

        def image_read(command, state):
            nonlocal calls
            calls += 1
            if calls == 2:
                state["exited"] = True
                return {"sha256": "wrong", "executable_path": command[0]}
            return {"sha256": "image", "executable_path": command[0]}

        with self.assertRaises(ValueError) as caught:
            self.observe_fake_process("wrong-image-after-sample",
                                      lambda command, state: command,
                                      lambda state: 1024, image_read=image_read)
        self.assertTrue(str(caught.exception) == "observed process image differs")

    def test_startup_image_retry_is_bounded_and_requires_complete_sample(self):
        calls = 0

        def transient_image(command, state):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"sha256": "startup", "executable_path": command[0]}
            return {"sha256": "image", "executable_path": command[0]}

        def exit_after_sample(state):
            state["exited"] = True
            return 1024

        observation = self.observe_fake_process("startup-image-retry",
                                                lambda command, state: command,
                                                exit_after_sample, image_read=transient_image)
        self.assertEqual(observation["process_start_id"], "11")
        self.assertEqual(calls, 2)

        def always_wrong(command, state):
            return {"sha256": "startup", "executable_path": command[0]}

        with self.assertRaises(ValueError):
            self.observe_fake_process("startup-image-timeout",
                                      lambda command, state: command,
                                      lambda state: 1024, image_read=always_wrong,
                                      timeout=0.03)

    def test_public_cli_rejects_invalid_arguments_without_echo(self):
        marker = self.keyed_env["OLLAMA_API_KEY"]
        common = [sys.executable, str(SOURCE), "audit", "--output-root", str(self.output),
                  "--trusted-key", str(self.key)]
        for name, extra in (("unknown", ["--unknown", marker]),
                            ("invalid-seconds", ["--seconds", marker])):
            with self.subTest(name=name):
                result = subprocess.run([*common, *extra], env=self.env,
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(marker in result.stdout or marker in result.stderr)

    def test_empty_terminal_command_recovers_only_after_complete_sample(self):
        calls = 0

        def command_read(command, state):
            nonlocal calls
            calls += 1
            if calls == 2:
                state["exited"] = True
                return []
            return command

        observation = self.observe_fake_process("empty-terminal-command", command_read,
                                                lambda state: 1024)
        self.assertEqual(observation["process_start_id"], "11")

    def test_changed_start_id_rejects_before_terminal_empty_command(self):
        reads = 0

        def read_start(state):
            nonlocal reads
            reads += 1
            return 11 if reads == 1 else 12

        def terminal_command(command, state):
            if reads == 2:
                state["exited"] = True
                return []
            return command

        with self.assertRaises(ValueError) as caught:
            self.observe_fake_process("changed-start-empty-command", terminal_command,
                                      lambda state: 1024, start_read=read_start)
        self.assertTrue(str(caught.exception) ==
                        "process start identity changed during observation")

    def test_changed_start_id_rejects_before_terminal_missing_environment(self):
        reads = 0

        def read_start(state):
            nonlocal reads
            reads += 1
            return 11 if reads == 1 else 12

        def terminal_environment(state):
            if reads == 2:
                state["exited"] = True
                raise FileNotFoundError("procfs environment vanished")
            return {"DYN4K_CLOCK_NONCE": "nonce"}

        with self.assertRaises(ValueError) as caught:
            self.observe_fake_process("changed-start-missing-environment",
                                      lambda command, state: command, lambda state: 1024,
                                      environment_read=terminal_environment,
                                      start_read=read_start)
        self.assertTrue(str(caught.exception) ==
                        "process start identity changed during observation")

    def test_same_start_id_allows_genuine_terminal_disappearance(self):
        reads = 0

        def read_start(state):
            nonlocal reads
            reads += 1
            return 11

        def terminal_command(command, state):
            if reads == 2:
                state["exited"] = True
                return []
            return command

        observation = self.observe_fake_process("same-start-terminal-command",
                                                terminal_command, lambda state: 1024,
                                                start_read=read_start)
        self.assertEqual(observation["process_start_id"], "11")

        reads = 0

        def terminal_environment(state):
            if reads == 2:
                state["exited"] = True
                raise FileNotFoundError("procfs environment vanished")
            return {"DYN4K_CLOCK_NONCE": "nonce"}

        observation = self.observe_fake_process("same-start-terminal-environment",
                                                lambda command, state: command,
                                                lambda state: 1024,
                                                environment_read=terminal_environment,
                                                start_read=read_start)
        self.assertEqual(observation["process_start_id"], "11")

    def test_terminal_missing_rss_recovers_but_live_missing_rss_fails(self):
        calls = 0

        def terminal_rss(state):
            nonlocal calls
            calls += 1
            if calls == 2:
                state["exited"] = True
                raise ValueError("process RSS observation is unavailable")
            return 1024

        observation = self.observe_fake_process("terminal-rss", lambda command, state: command,
                                                terminal_rss)
        self.assertEqual(observation["process_start_id"], "11")

        def live_missing(state):
            raise ValueError("process RSS observation is unavailable")

        with self.assertRaises(ValueError):
            self.observe_fake_process("live-rss", lambda command, state: command,
                                      live_missing)

    def test_terminal_procfs_disappearance_requires_prior_sample_and_exit(self):
        for name, exits, prior_sample in (("terminal-procfs", True, True),
                                          ("live-procfs", False, True),
                                          ("no-sample-procfs", True, False)):
            with self.subTest(name=name):
                calls = 0

                def command_read(command, state):
                    nonlocal calls
                    calls += 1
                    if calls == 2 or not prior_sample:
                        state["exited"] = exits
                        raise FileNotFoundError("procfs disappeared")
                    return command

                if exits and prior_sample:
                    observation = self.observe_fake_process(name, command_read,
                                                            lambda state: 1024)
                    self.assertEqual(observation["process_start_id"], "11")
                else:
                    with self.assertRaises(ValueError):
                        self.observe_fake_process(name, command_read,
                                                  lambda state: 1024)

    def test_dirty_engine_harness_and_build_inputs_fail_before_staging(self):
        repo = self.root / "source-guard"
        for relative in ("dyn4k-core/Engine.kt", "dyn4k/Api.kt",
                         "tools/performance/sustained_jvm/SustainedPilot.java",
                         "tools/performance/sustained_jvm/SustainedSidecars.java",
                         "gradle/wrapper/gradle-wrapper.properties", "gradle.properties",
                         "build.gradle.kts", "settings.gradle.kts"):
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("frozen\n")
        (repo / ".gitignore").write_text("local.properties\n")
        subprocess.run(["git", "init", "-q", str(repo)], check=True, env=self.env)
        subprocess.run(["git", "add", "."], cwd=repo, check=True, env=self.env)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "frozen"], cwd=repo, check=True, env=self.env)
        frozen = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                                capture_output=True, text=True, env=self.env).stdout.strip()
        real_run = subprocess.run
        source_child_envs = []

        def record_source_child(*args, **kwargs):
            source_child_envs.append(kwargs.get("env"))
            return real_run(*args, **kwargs)

        with mock.patch.dict(os.environ,
                             {"OLLAMA_API_KEY": self.keyed_env["OLLAMA_API_KEY"]}), \
                mock.patch.object(producer.subprocess, "run", side_effect=record_source_child):
            producer.check_frozen_inputs(repo, frozen)
        self.assertTrue(source_child_envs)
        self.assertTrue(all(value is not None and "OLLAMA_API_KEY" not in value
                            for value in source_child_envs))
        for relative in ("dyn4k-core/Engine.kt",
                         "tools/performance/sustained_jvm/SustainedPilot.java",
                         "gradle.properties", "dyn4k/new.kt", "gradle/new.toml",
                         "buildSrc/new.gradle.kts", "local.properties"):
            with self.subTest(relative=relative):
                path = repo / relative
                original = path.read_bytes() if path.exists() else None
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("changed\n")
                with self.assertRaises(ValueError):
                    producer.check_frozen_inputs(repo, frozen)
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)
                producer.check_frozen_inputs(repo, frozen)
        (repo / "dyn4k-core/Engine.kt").write_text("changed\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, env=self.env)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "changed"], cwd=repo, check=True, env=self.env)
        with self.assertRaises(ValueError):
            producer.check_frozen_inputs(repo, frozen)

    def test_audit_rejects_mismatched_external_provenance(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        from reference_study_producer import audit_output

        cases = (
            ("monitor_pid", "monitor", "os_pid", 999999),
            ("monitor_start", "monitor", "process_start_id", "wrong-start"),
            ("monitor_nonce", "monitor", "launch_nonce", "wrong-run"),
            ("monitor_clock", "monitor", "ended_ns", 1),
            ("environment_artifact", "environment", "artifact_sha256", "0" * 64),
            ("environment_image", "environment", "image_sha256", "0" * 64),
            ("capture_pid", "capture", "os_pid", 999999),
            ("capture_process", "capture", "process_id", "REUSE_FIRST"),
        )
        for name, target, field, value in cases:
            with self.subTest(name=name):
                copy = self.root / name
                shutil.copytree(self.output, copy)
                captures = json.loads((copy / "captures.json").read_text())
                if target == "capture":
                    if value == "REUSE_FIRST":
                        captures[1][field] = captures[0][field]
                    else:
                        captures[0][field] = value
                    (copy / "captures.json").write_text(json.dumps(captures))
                else:
                    path = copy / captures[0][target + "_path"]
                    data = json.loads(path.read_text())
                    data[field] = value
                    path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    audit_output(copy, self.key)


if __name__ == "__main__":
    unittest.main()
