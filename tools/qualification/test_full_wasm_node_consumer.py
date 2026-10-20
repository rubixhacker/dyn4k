import sys
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import full_wasm_node_consumer as route


class FullWasmNodeConsumerTests(unittest.TestCase):
    def test_exact_candidate_preserves_approved_source_method_order(self):
        repository = Path(__file__).resolve().parents[2]
        candidate = subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
        lane = "wasmJs:Node.js:current:development"
        selected = route.contract(repository, lane)
        content = route.input_bytes(repository, candidate, lane)
        self.assertEqual(len(content["core-cases.tsv"].splitlines()), 2465)
        self.assertEqual(len(content["facade-cases.tsv"].splitlines()), 58)
        self.assertEqual(__import__("json").loads(content["source-method-order.json"]),
                         [row["id"] for row in selected["cases"]])

    def test_all_approved_nonbrowser_wasm_lanes_are_distinct(self):
        self.assertEqual(len(route.LANES), 12)
        self.assertEqual(set(route.LANES), {
            f"{target}:{runtime}:{role}:{mode}"
            for target, runtimes in (("wasmJs", ("Node.js",)),
                                     ("wasmWasi", ("Node.js", "Wasmtime")))
            for runtime in runtimes for role in ("minimum", "current")
            for mode in ("development", "production")
        })

    def test_teamcity_events_require_order_and_exact_original_outcomes(self):
        selected = {("a.B", "one"): "dyn4k-core:a.B#one",
                    ("a.B", "two"): "dyn4k-core:a.B#two"}
        raw = ("##teamcity[testSuiteStarted name='a']\n"
               "##teamcity[testSuiteStarted name='B']\n"
               "##teamcity[testStarted name='one']\n"
               "##teamcity[testFinished name='one']\n"
               "##teamcity[testStarted name='two']\n"
               "##teamcity[testFinished name='two']\n"
               "##teamcity[testSuiteFinished name='B']\n"
               "##teamcity[testSuiteFinished name='a']\n").encode()
        self.assertEqual(route.parse_events(raw, selected), list(selected.values()))
        for changed in (raw.replace(b"testFinished name='one'", b"testFinished name='two'"),
                        raw.replace(b"testStarted name='two'", b"testStarted name='one'"),
                        raw.replace(b"testFinished name='two'", b"testFailed name='two'"),
                        raw[:-len(b"##teamcity[testSuiteFinished name='a']\n")]):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                route.parse_events(changed, selected)

    def test_absent_minimum_runtime_is_not_run(self):
        result = route.runtime_preflight(
            "wasmWasi:Wasmtime:minimum:development", Path("/missing/wasmtime"))
        self.assertEqual(result["status"], "NOT_RUN")
        self.assertEqual(result["reason"], "selected runtime executable is absent")
        self.assertEqual(result["expected_version"], "37.0.3")
        self.assertEqual(result["selected_path"], str(Path("/missing/wasmtime")))

    def test_runtime_roles_require_candidate_patch_not_only_major(self):
        versions = (
            ("wasmJs:Node.js:current:development", "v26.2.0", "FAILED"),
            ("wasmJs:Node.js:current:development", "v26.12.0", "PASSED"),
            ("wasmWasi:Node.js:minimum:development", "v24.16.0", "FAILED"),
            ("wasmWasi:Node.js:minimum:development", "v24.22.0", "PASSED"),
            ("wasmWasi:Wasmtime:current:development", "wasmtime 46.0.1", "FAILED"),
            ("wasmWasi:Wasmtime:current:development", "wasmtime 49.0.3", "PASSED"),
        )
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "runtime"
            executable.write_bytes(b"selected runtime bytes")
            for lane, version, status in versions:
                with self.subTest(lane=lane, version=version), patch.object(
                        route.subprocess, "run", return_value=subprocess.CompletedProcess(
                            [str(executable), "--version"], 0, version)):
                    self.assertEqual(route.runtime_preflight(lane, executable)["status"], status)
            changed = Path(directory) / "changed-runtime"
            changed.write_bytes(b"different runtime bytes")
            with patch.object(route.subprocess, "run", return_value=subprocess.CompletedProcess(
                    [str(executable), "--version"], 0, "v26.12.0")):
                first = route.runtime_preflight("wasmJs:Node.js:current:development", executable)
                second = route.runtime_preflight("wasmJs:Node.js:current:development", changed)
            self.assertEqual(first["version"], second["version"])
            self.assertNotEqual(first["sha256"], second["sha256"])

    def test_public_archive_digest_rejects_changed_bytes_and_symbolic_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory)
            (archive / "receipt.json").write_bytes(b"sealed receipt")
            (archive / "raw.log").write_bytes(b"original method events")
            original = route.archive_digest(archive)
            (archive / "raw.log").write_bytes(b"changed method events")
            self.assertNotEqual(route.archive_digest(archive), original)
            (archive / "raw.log").write_bytes(b"original method events")
            (archive / "bundle.mjs").write_bytes(b"original linked bundle")
            with_bundle = route.archive_digest(archive)
            (archive / "bundle.mjs").write_bytes(b"changed linked bundle")
            self.assertNotEqual(route.archive_digest(archive), with_bundle)
            (archive / "raw.log").unlink()
            (archive / "raw.log").symlink_to(archive / "receipt.json")
            with self.assertRaisesRegex(ValueError, "symbolic"):
                route.archive_digest(archive)

    def test_public_archive_digest_rejects_external_hardlink_before_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            archive.mkdir()
            (archive / "receipt.json").write_bytes(b"receipt")
            outside = root / "mutable-external-bundle.wasm"
            outside.write_bytes(b"external bytes")
            linked = archive / "bundle.wasm"
            os.link(outside, linked)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("read before hardlink rejection")):
                with self.assertRaisesRegex(ValueError, "hardlink"):
                    route.archive_digest(archive)

    def test_public_verify_cannot_pass_when_replay_is_omitted(self):
        result = route.verify(Path("/missing/archive"), Path("/missing/repository"),
                              "a" * 40, "wasmWasi:Wasmtime:minimum:development",
                              {"dyn4k-core": "b" * 64, "dyn4k": "c" * 64},
                              "d" * 64, Path("/missing/wasmtime"), replay=False)
        self.assertEqual(result["status"], "NOT_RUN")
        self.assertIn("replay", result["reason"])

    def test_gradle_proof_rejects_forged_success_without_executed_linked_tasks(self):
        lane = "wasmWasi:Wasmtime:minimum:development"
        tasks = [":core:compileTestDevelopmentExecutableKotlinWasmWasi",
                 ":facade:compileTestDevelopmentExecutableKotlinWasmWasi"]
        graph = "a" * 64
        valid = (f"QUALIFICATION_LANE={lane}\n"
                 f"QUALIFICATION_PROVIDER_GRAPH_SHA256={graph}\n"
                 + "".join(f"> Task {task}\n" for task in tasks)
                 + "BUILD SUCCESSFUL in 1s\n4 actionable tasks: 4 executed\n")
        route.verify_gradle_output(valid, lane, graph, tasks)
        forged = valid.replace(f"> Task {tasks[0]}\n", f"> Task {tasks[0]} SKIPPED\n")
        with self.assertRaisesRegex(ValueError, "linked Wasm test task"):
            route.verify_gradle_output(forged, lane, graph, tasks)
        forged = valid.replace("BUILD SUCCESSFUL in 1s", "warning: BUILD SUCCESSFUL in 1s")
        with self.assertRaisesRegex(ValueError, "Gradle success"):
            route.verify_gradle_output(forged, lane, graph, tasks)

    def test_missing_runtime_does_not_hide_wrong_candidate_checkout(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                route, "git", return_value=b"f" * 40):
            with self.assertRaisesRegex(ValueError, "head differs"):
                route.run(Path("/source"), "0" * 40,
                          "wasmJs:Node.js:minimum:development",
                          Path(directory) / "stage", Path(directory) / "archive",
                          Path("/missing/gradle"), Path("/missing/node"),
                          {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64})


if __name__ == "__main__":
    unittest.main()
