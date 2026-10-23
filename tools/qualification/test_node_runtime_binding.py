import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import full_corpus


ROOT = Path(__file__).resolve().parents[2]


class NodeRuntimeSelectionTest(unittest.TestCase):
    def test_real_js_runner_selects_core_group_and_empty_runner_does_not(self):
        payload = ROOT / "build/js/packages/dyn4k-dyn4k-core-test/kotlin/dyn4k-dyn4k-core-test.js"
        runner = ROOT / "build/js/node_modules/kotlin-web-helpers/dist/kotlin-test-nodejs-runner.js"
        command = ["/cached/node", str(ROOT / "build/js/node_modules/mocha/bin/mocha.js"),
                   str(payload), "--require", str(runner)]
        self.assertEqual(("core-jsNode", payload),
                         full_corpus.node_group_for_argv(ROOT, command))
        observed_command = [command[0], "--experimental-wasm-modules", *command[1:]]
        self.assertEqual(("core-jsNode", payload),
                         full_corpus.node_group_for_argv(ROOT, observed_command))
        empty = command[:-1] + [str(runner).replace("nodejs-runner", "nodejs-empty-runner")]
        self.assertIsNone(full_corpus.node_group_for_argv(ROOT, empty))
        self.assertIsNone(full_corpus.node_group_for_argv(ROOT,
                          ["/cached/node", "--version"]))
        sibling = [part.replace("dyn4k-dyn4k-core-test", "dyn4k-dyn4k-test")
                   for part in command]
        self.assertEqual("jsNode", full_corpus.node_group_for_argv(ROOT, sibling)[0])

    def test_wasm_runner_selects_exact_target_and_rejects_dry_run(self):
        for module, prefix in (("dyn4k-core", "core-"), ("dyn4k", "")):
            for host, relative in (
                    ("wasmJsNode", f"build/wasm/packages/dyn4k-{module}-test/static/runUnitTests.mjs"),
                    ("wasmWasiNode", f"{module}/build/compileSync/wasmWasi/test/"
                                     "testDevelopmentExecutable/kotlin/static/runUnitTests.mjs")):
                payload = ROOT / relative
                argv = ["/cached/node", str(payload)]
                with self.subTest(group=prefix + host):
                    self.assertEqual((prefix + host, payload),
                                     full_corpus.node_group_for_argv(ROOT, argv))
                    self.assertIsNone(full_corpus.node_group_for_argv(
                        ROOT, [*argv, "--dryRun"]))


@unittest.skipUnless(os.name == "posix" and Path("/proc/self/exe").exists(),
                     "requires Linux process observation")
class LiveNodeObservationTest(unittest.TestCase):
    def test_selected_test_process_is_observed_while_alive(self):
        node = shutil.which("node")
        self.assertIsNotNone(node)
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            observations = repository / "observations"
            observations.mkdir(mode=0o700)
            started_ns = time.time_ns()
            payload = repository / ("dyn4k-core/build/compileSync/wasmWasi/test/"
                                    "testDevelopmentExecutable/kotlin/static/runUnitTests.mjs")
            payload.parent.mkdir(parents=True)
            payload.write_text("process.stdout.write('ran');\n")
            env = os.environ.copy()
            env["NODE_OPTIONS"] = "--require=" + str(ROOT / full_corpus.NODE_PROBE_PATH)
            env["DYN4K_NODE_OBSERVATION_DIR"] = str(observations)
            process = subprocess.Popen([node, str(payload)], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                requests = []
                while not requests and time.monotonic() < deadline:
                    requests = list(observations.glob("*.json"))
                    time.sleep(0.01)
                self.assertEqual(1, len(requests))
                start_ticks = full_corpus.independent_linux_observer._stat(
                    process.pid)["start_ticks"]
                row = full_corpus.observe_node_request(
                    repository, requests[0], process.pid, start_ticks, started_ns)
                self.assertEqual("core-wasmWasiNode", row["group_id"])
                self.assertEqual("v" + subprocess.check_output(
                    [node, "--version"], text=True).strip().removeprefix("v"),
                    row["version"])
                self.assertEqual(process.pid, row["pid"])
                self.assertEqual(start_ticks, row["start_ticks"])
                (observations / requests[0].name.replace(".json", ".ack")).write_text(row["nonce"])
                output, errors = process.communicate(timeout=5)
                self.assertEqual(0, process.returncode, errors.decode())
                self.assertEqual(b"ran", output)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_six_group_replay_rejects_process_and_raw_evidence_mutations(self):
        node = shutil.which("node")
        self.assertIsNotNone(node)
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            probe = repository / full_corpus.NODE_PROBE_PATH
            probe.parent.mkdir(parents=True)
            shutil.copy2(ROOT / full_corpus.NODE_PROBE_PATH, probe)
            observations = repository / "observations"
            observations.mkdir(mode=0o700)
            started_ns = time.time_ns()
            rows = []
            parent_pid = os.getpid()
            parent_start = full_corpus.independent_linux_observer._stat(
                parent_pid)["start_ticks"]
            for group_id in sorted(full_corpus.NODE_GROUPS):
                module = "dyn4k-core" if group_id.startswith("core-") else "dyn4k"
                host = group_id.removeprefix("core-")
                if host == "jsNode":
                    script = repository / "build/js/node_modules/mocha/bin/mocha.js"
                    script.parent.mkdir(parents=True, exist_ok=True)
                    script.write_text("process.stdout.write('ran');\n")
                    payload = repository / (f"build/js/packages/dyn4k-{module}-test/"
                                            f"kotlin/dyn4k-{module}-test.js")
                    runner = repository / ("build/js/node_modules/kotlin-web-helpers/"
                                           "dist/kotlin-test-nodejs-runner.js")
                    runner.parent.mkdir(parents=True, exist_ok=True)
                    runner.write_text("module.exports = {};\n")
                    argv = [node, "--experimental-wasm-modules", str(script),
                            str(payload), "--require", str(runner)]
                elif host == "wasmJsNode":
                    payload = repository / (f"build/wasm/packages/dyn4k-{module}-test/"
                                            "static/runUnitTests.mjs")
                    argv = [node, str(payload)]
                else:
                    payload = repository / (f"{module}/build/compileSync/wasmWasi/test/"
                                            "testDevelopmentExecutable/kotlin/static/runUnitTests.mjs")
                    argv = [node, str(payload)]
                payload.parent.mkdir(parents=True, exist_ok=True)
                payload.write_text("process.stdout.write('ran');\n")
                env = os.environ.copy()
                env["NODE_OPTIONS"] = "--require=" + str(probe)
                env["DYN4K_NODE_OBSERVATION_DIR"] = str(observations)
                process = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
                try:
                    deadline = time.monotonic() + 5
                    request = observations / "missing.json"
                    while time.monotonic() < deadline:
                        matches = list(observations.glob(f"{process.pid}-*.json"))
                        if matches:
                            request = matches[0]
                            break
                        time.sleep(0.01)
                    self.assertTrue(request.exists(), group_id)
                    row = full_corpus.observe_node_request(repository, request,
                        parent_pid, parent_start, started_ns)
                    self.assertEqual(group_id, row["group_id"])
                    ack = observations / request.name.replace(".json", ".ack")
                    ack.write_text(row["nonce"])
                    row["ack_sha256"] = full_corpus.digest(ack.read_bytes())
                    output, errors = process.communicate(timeout=5)
                    self.assertEqual(0, process.returncode, errors.decode())
                    self.assertEqual(b"ran", output)
                    rows.append(row)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
            finished_ns = time.time_ns()
            reports = {group: {f"{group}.xml": "a" * 64}
                       for group in full_corpus.NODE_GROUPS}
            for row in rows:
                row["report_sha256"] = full_corpus.canonical_digest(
                    reports[row["group_id"]])
            binding = {"schema": 2, "observation_platform": "linux",
                       "node_probe_sha256": full_corpus.digest(probe.read_bytes()),
                       "node_observation_dir": str(observations),
                       "gradle_pid": parent_pid, "gradle_start_ticks": parent_start,
                       "node_observations": rows, "reports": reports}

            def problems(changed):
                return full_corpus.node_observation_problems(
                    repository, repository, changed, started_ns, finished_ns)

            self.assertEqual([], problems(binding))
            self.assertEqual([], full_corpus.node_observation_problems(
                Path(os.path.relpath(repository)), Path(os.path.relpath(repository)),
                binding, started_ns, finished_ns))
            mutants = (
                ("missing", lambda value: value["node_observations"].pop()),
                ("duplicate", lambda value: value["node_observations"].append(
                    copy.deepcopy(value["node_observations"][0]))),
                ("wrong group", lambda value: value["node_observations"][0].update(
                    group_id="core-jvm")),
                ("wrong task", lambda value: value["node_observations"][0].update(
                    task=":dyn4k:jsNodeTest")),
                ("stale", lambda value: value["node_observations"][0].update(
                    observed_ns=started_ns - 1)),
                ("wrong pid", lambda value: value["node_observations"][0].update(
                    pid=1)),
                ("wrong version", lambda value: value["node_observations"][0].update(
                    version="v0.0.0")),
                ("changed runtime bytes", lambda value: value["node_observations"][0].update(
                    executable_sha256="0" * 64)),
                ("unrelated version process", lambda value: value["node_observations"][0].update(
                    argv=[node, "--version"])),
                ("mismatched raw group", lambda value: value["node_observations"][0].update(
                    report_sha256="0" * 64)),
            )
            for label, mutate in mutants:
                with self.subTest(label=label):
                    changed = copy.deepcopy(binding)
                    mutate(changed)
                    self.assertTrue(problems(changed), label)
            first = rows[0]
            raw = observations / first["request_name"]
            original = raw.read_bytes()
            try:
                forged = json.loads(original)
                forged["version"] = "v0.0.0"
                raw.write_text(json.dumps(forged))
                self.assertTrue(problems(binding))
            finally:
                raw.write_bytes(original)
            payload = repository / first["payload_path"]
            original = payload.read_bytes()
            try:
                payload.write_bytes(b"changed")
                self.assertTrue(problems(binding))
            finally:
                payload.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
import copy
