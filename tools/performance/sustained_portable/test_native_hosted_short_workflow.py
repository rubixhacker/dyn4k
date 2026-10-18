import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest


WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/performance-native-host-short.yml"
RUNNER = Path(__file__).with_name("native_hosted_short_runner.py")
RAW_LIMIT = 64 * 1024 * 1024
RUN_EXPRESSION_LIMIT = 21000
WINDOWS_GRADLE_STDOUT_8FA = base64.b64decode(
    "DQotLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0NCkdyYWRsZSA5LjUu"
    "MA0KLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQoNCkJ1aWxkIHRp"
    "bWU6ICAgIDIwMjYtMDQtMjggMTI6MDU6MzAgVVRDDQpSZXZpc2lvbjogICAgICAzZmUxMTdkNjhmMzkwNzc5MGYzODA5ZjEyMWFh"
    "MzYzMDNhOTE1MWY4DQoNCktvdGxpbjogICAgICAgIDIuMy4yMA0KR3Jvb3Z5OiAgICAgICAgNC4wLjI5DQpBbnQ6ICAgICAgICAg"
    "ICBBcGFjaGUgQW50KFRNKSB2ZXJzaW9uIDEuMTAuMTUgY29tcGlsZWQgb24gQXVndXN0IDI1IDIwMjQNCkxhdW5jaGVyIEpWTTog"
    "IDIxLjAuMTIuMSAoRWNsaXBzZSBBZG9wdGl1bSAyMS4wLjEyLjErMS1MVFMpDQpEYWVtb24gSlZNOiAgICBDOlxob3N0ZWR0b29s"
    "Y2FjaGVcd2luZG93c1xKYXZhX1RlbXVyaW4tSG90c3BvdF9qZGtcMjEuMC4xMi0xMDEuMFx4NjQgKG5vIERhZW1vbiBKVk0gc3Bl"
    "Y2lmaWVkLCB1c2luZyBjdXJyZW50IEphdmEgaG9tZSkNCk9TOiAgICAgICAgICAgIFdpbmRvd3MgU2VydmVyIDIwMjUgMTAuMCBh"
    "bWQ2NA0KDQo=")


def run_expression_upper_bounds(source):
    lines = source.splitlines()
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)run:\s*(.*)$", lines[index])
        if match is None:
            index += 1
            continue
        line_number = index + 1
        value = match.group(2)
        if not value:
            index += 1
            continue
        if value.startswith(("|", ">")):
            key_indent = len(match.group(1))
            block = []
            index += 1
            while index < len(lines):
                line = lines[index]
                if line.strip() and len(line) - len(line.lstrip()) <= key_indent:
                    break
                block.append(line)
                index += 1
            content_indent = min((len(line) - len(line.lstrip())
                                  for line in block if line.strip()), default=key_indent + 1)
            yield line_number, sum(len(line[content_indent:]) + 1 for line in block)
        else:
            yield line_number, len(value)
            index += 1


class WorkflowExpressionLimit(unittest.TestCase):
    def test_native_run_is_below_limit_and_all_workflows_are_audited(self):
        workflows = sorted(WORKFLOW.parent.glob("*.yml")) + sorted(WORKFLOW.parent.glob("*.yaml"))
        self.assertTrue(workflows)
        checked = 0
        violations = []
        for workflow in workflows:
            for line, upper_bound in run_expression_upper_bounds(workflow.read_text()):
                checked += 1
                if workflow == WORKFLOW:
                    self.assertLess(upper_bound, RUN_EXPRESSION_LIMIT)
                if upper_bound >= RUN_EXPRESSION_LIMIT:
                    violations.append((workflow.name, line, upper_bound))
        self.assertGreater(checked, 0)
        self.assertEqual(violations, [])


def workflow_nodes():
    tree = ast.parse(RUNNER.read_text(), filename=str(RUNNER))
    raw = next(node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == "raw_file")
    sidecar = next((node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "sidecar_bytes"), None)
    routes = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                  and node.target.id == "api")
    receipt = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.Expr) and "route-result.json" in ast.unparse(node))
    gradle = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.If) and len(node.body) == 1
                  and isinstance(node.body[0], ast.Raise)
                  and "selected Gradle is not 9.5.0" in ast.unparse(node.body[0]))
    guard = next(node for node in ast.walk(tree)
                 if isinstance(node, ast.If) and len(node.body) == 1
                 and isinstance(node.body[0], ast.Raise)
                 and "one or more Native host controls failed" in ast.unparse(node.body[0]))
    return raw, sidecar, routes, receipt, gradle, guard


class GrowingFile:
    def __init__(self, size=0):
        self.size = size
        self.read_bytes = 0
        self.remaining = RAW_LIMIT + 1024 * 1024

    def is_file(self):
        return True

    def stat(self):
        return SimpleNamespace(st_size=self.size, st_dev=1, st_ino=1,
                               st_mtime_ns=1, st_ctime_ns=1)

    def open(self, mode):
        if mode != "rb":
            raise AssertionError(mode)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, size):
        count = min(size, self.remaining)
        self.remaining -= count
        self.read_bytes += count
        return b"x" * count


class UnreadableFile(GrowingFile):
    def open(self, mode):
        raise OSError("injected raw read failure")


class HostedRawFileContract(unittest.TestCase):
    def setUp(self):
        (self.raw_node, self.sidecar_node, self.route_node, self.receipt_node,
         self.gradle_node, self.guard_node) = workflow_nodes()
        self.scope = {"hashlib": hashlib, "json": json, "Path": Path, "sys": sys}
        functions = [self.raw_node] + ([self.sidecar_node] if self.sidecar_node else [])
        exec(compile(ast.Module(body=functions, type_ignores=[]),
                     str(RUNNER), "exec"), self.scope)

    def test_growing_zero_size_file_has_bounded_incomplete_hash(self):
        growing = GrowingFile()
        result = self.scope["raw_file"](growing)
        self.assertEqual(growing.read_bytes, 1)
        self.assertEqual(result["status"], "changed_during_hash")
        self.assertNotIn("sha256", result)
        oversized = GrowingFile(RAW_LIMIT + 1)
        self.assertEqual(self.scope["raw_file"](oversized)["status"], "hash_size_limit")
        self.assertEqual(oversized.read_bytes, 0)

    def test_growing_memory_sidecar_has_bounded_incomplete_snapshot(self):
        growing = GrowingFile()
        with self.assertRaisesRegex(ValueError, "changed during read"):
            self.scope["sidecar_bytes"](growing)
        self.assertEqual(growing.read_bytes, 1)
        oversized = GrowingFile(8 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "exceeds read limit"):
            self.scope["sidecar_bytes"](oversized)
        self.assertEqual(oversized.read_bytes, 0)

    def test_failed_cleanup_keeps_second_route_and_unpassed_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            growing = GrowingFile()
            unreadable = UnreadableFile()
            actual_raw_file = self.scope["raw_file"]
            labels = []

            def routed_raw_file(path):
                if path.parent.name == "direct_kotlin" and path.name == "stdout.raw":
                    return actual_raw_file(growing)
                if path.parent.name == "compatibility" and path.name == "stderr.raw":
                    return actual_raw_file(unreadable)
                return actual_raw_file(path)

            route = {"qualification": "unpassed", "commands": {}, "scenarios": {},
                     "memory_scenarios": {}}

            def execute(label, argv, timeout):
                labels.append(label)
                archive = argv[argv.index("--archive") + 1]
                archive.mkdir(parents=True)
                (archive / "stdout.raw").write_bytes(b"raw-out")
                (archive / "stderr.raw").write_bytes(b"raw-err")
                route["commands"][label] = {"termination": "deadline_tree_unverified",
                                            "error": "timeout", "exit_code": -9}
                return False, None, None

            self.scope.update(raw_file=routed_raw_file, execute=execute,
                              evidence=evidence, route=route, root=WORKFLOW.parents[2],
                              inventory=evidence / "inventory.json", staging=evidence / "stage",
                              target="macosArm64", build="development", sha="local-control")
            exec(compile(ast.Module(body=[self.route_node], type_ignores=[]),
                         str(RUNNER), "exec"), self.scope)
            self.scope["image_control"] = False
            with self.assertRaisesRegex(RuntimeError, "Native host controls failed"):
                exec(compile(ast.Module(body=[self.guard_node], type_ignores=[]),
                             str(RUNNER), "exec"), self.scope)
            exec(compile(ast.Module(body=[self.receipt_node], type_ignores=[]),
                         str(RUNNER), "exec"), self.scope)
            self.assertEqual(labels, ["captures/direct_kotlin-command",
                                      "captures/memory/direct_kotlin-command",
                                      "captures/compatibility-command",
                                      "captures/memory/compatibility-command"])
            persisted = json.loads((evidence / "route-result.json").read_text())
            self.assertEqual(persisted["qualification"], "unpassed")
            self.assertEqual(len(persisted["scenarios"]), 2)
            self.assertEqual(len(persisted["memory_scenarios"]), 2)
            direct = json.loads((evidence / "captures/direct_kotlin-failure.json").read_text())
            compatibility = json.loads((evidence / "captures/compatibility-failure.json").read_text())
            memory_direct = json.loads((evidence / "captures/memory/direct_kotlin-failure.json").read_text())
            memory_compatibility = json.loads((evidence / "captures/memory/compatibility-failure.json").read_text())
            self.assertEqual(direct["raw"]["stdout.raw"]["status"], "changed_during_hash")
            self.assertEqual(compatibility["raw"]["stderr.raw"]["status"], "unreadable")
            self.assertEqual(direct["raw"]["stderr.raw"], {
                "bytes": 7, "sha256": hashlib.sha256(b"raw-err").hexdigest()})
            for receipt in (direct, compatibility, memory_direct, memory_compatibility):
                self.assertEqual(receipt["qualification"], "unpassed")
                self.assertEqual(receipt["raw_collection"], "incomplete")
            self.assertEqual(memory_direct["mode"], "memory")
            self.assertEqual(memory_compatibility["mode"], "memory")
            self.assertEqual(growing.read_bytes, 2)

    def test_memory_commands_and_unavailable_probe_preserve_both_api_routes(self):
        source = WORKFLOW.read_text()
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("  push:", source)
        self.assertIn("if: always()", source)
        self.assertIn('run: python -B "$GITHUB_WORKSPACE/tools/performance/sustained_portable/native_hosted_short_runner.py"', source)
        self.assertNotIn("python -B - <<'PY'", source)
        self.assertIn('if Path(__file__).resolve() != selected_runner:', RUNNER.read_text())
        self.assertIn("macos-26", source)
        self.assertIn("windows-2025", source)
        self.assertIn("Xcode_26.4.1", source)
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            route = {"qualification": "unpassed", "commands": {}, "scenarios": {},
                     "memory_scenarios": {}}
            calls = []

            def execute(label, argv, timeout):
                calls.append((label, argv, timeout))
                archive = argv[argv.index("--archive") + 1]
                archive.mkdir(parents=True)
                (archive / "stdout.raw").write_bytes(b"producer output")
                (archive / "stderr.raw").write_bytes(b"")
                (archive / "capture.json").write_text("{}")
                route["commands"][label] = {"exit_code": 0, "termination": "natural"}
                if "--mode" in argv and argv[argv.index("--mode") + 1] == "memory":
                    api = "direct_kotlin" if "direct_kotlin" in label else "compatibility"
                    status = "unavailable_or_partial" if api == "direct_kotlin" else "observed_diagnostic"
                    (archive / "execution.json").write_text(json.dumps({
                        "pid": 123, "raw_collection": "selected_process_exited",
                        "termination": "natural", "exit_code": 0,
                        "stdout_sha256": hashlib.sha256(b"producer output").hexdigest(),
                        "stderr_sha256": hashlib.sha256(b"").hexdigest()}))
                    (archive / "rss.json").write_text(json.dumps({
                        "pid": 123, "status": status,
                        "samples": [] if api == "direct_kotlin" else [[1, 4096]],
                        "errors": [{"error": "probe denied"}] if api == "direct_kotlin" else []}))
                    (archive / "run.json").write_text(json.dumps({
                        "mode": "memory", "qualification": "unpassed"}))
                    (archive / "rss.csv").write_text(
                        "monotonic_ns,resident_bytes\n" +
                        ("1,4096\n" if api == "compatibility" else ""))
                    (archive / "heap.csv").write_text("stage,retained_heap_bytes,gc_epoch\n")
                    (archive / "capture.json").write_text(json.dumps({
                        "mode": "memory", "source_sha": "local-control", "target": "macosArm64",
                        "build": "development", "scenario": {"api": api}, "pid": 123,
                        "process_image_identity": "observed", "observed_image": {"pid": 123},
                        "execution_sha256": hashlib.sha256((archive / "execution.json").read_bytes()).hexdigest(),
                        "rss_observation": {"status": status,
                                            "samples": 0 if api == "direct_kotlin" else 1,
                                            "rss_json_sha256": hashlib.sha256(
                                                (archive / "rss.json").read_bytes()).hexdigest()},
                        "managed_heap_observation": {
                            "status": "observed_kotlin_heap_after_collection", "stages": 3,
                            "heap_csv_sha256": hashlib.sha256(
                                (archive / "heap.csv").read_bytes()).hexdigest()}}))
                return True, None, None

            self.scope.update(evidence=evidence, route=route, execute=execute,
                              root=WORKFLOW.parents[2], inventory=evidence / "inventory.json",
                              staging=evidence / "stage", target="macosArm64",
                              build="development", sha="local-control", image_control=True)
            exec(compile(ast.Module(body=[self.route_node], type_ignores=[]),
                         str(RUNNER), "exec"), self.scope)
            with self.assertRaisesRegex(RuntimeError, "Native host controls failed"):
                exec(compile(ast.Module(body=[self.guard_node], type_ignores=[]),
                             str(RUNNER), "exec"), self.scope)
            self.assertEqual([label for label, _, _ in calls], [
                "captures/direct_kotlin-command", "captures/memory/direct_kotlin-command",
                "captures/compatibility-command", "captures/memory/compatibility-command"])
            for label, argv, timeout in calls:
                self.assertEqual(timeout, 120)
                self.assertEqual(argv[argv.index("--mode") + 1],
                                 "memory" if "/memory/" in label else "timing")
                self.assertEqual(argv[argv.index("--steps") + 1], "30")
                self.assertEqual(argv[argv.index("--warmup") + 1], "3")
                self.assertEqual(argv[argv.index("--inventory") + 1], evidence / "inventory.json")
                self.assertEqual(argv[argv.index("--publication-root") + 1], evidence / "stage")
            self.assertTrue(all(row["exit_zero"] for row in route["scenarios"].values()))
            self.assertEqual(route["memory_scenarios"]["direct_kotlin"]["status"],
                             "unavailable_or_partial")
            self.assertEqual(route["memory_scenarios"]["compatibility"]["status"],
                             "observed_diagnostic")
            failure = json.loads((evidence / "captures/memory/direct_kotlin-failure.json").read_text())
            self.assertEqual(failure["qualification"], "unpassed")
            self.assertEqual(failure["raw_collection"], "selected_process_exited")
            self.assertEqual(failure["result"]["status"], "unavailable_or_partial")
            self.assertFalse((evidence / "captures/memory/compatibility-failure.json").exists())

    def test_each_host_and_build_selects_separate_bounded_memory_commands(self):
        for target in ("macosArm64", "mingwX64"):
            for build in ("development", "optimized"):
                with self.subTest(target=target, build=build), tempfile.TemporaryDirectory() as directory:
                    evidence = Path(directory)
                    route = {"qualification": "unpassed", "commands": {}, "scenarios": {},
                             "memory_scenarios": {}}
                    calls = []

                    def execute(label, argv, timeout):
                        calls.append((label, argv, timeout))
                        argv[argv.index("--archive") + 1].mkdir(parents=True)
                        route["commands"][label] = {"exit_code": 1, "error": "injected"}
                        return False, None, None

                    self.scope.update(evidence=evidence, route=route, execute=execute,
                                      root=WORKFLOW.parents[2], inventory=evidence / "inventory.json",
                                      staging=evidence / "stage", target=target, build=build,
                                      sha="local-control", image_control=False)
                    exec(compile(ast.Module(body=[self.route_node], type_ignores=[]),
                                 str(RUNNER), "exec"), self.scope)
                    self.assertEqual(len(calls), 4)
                    for label, argv, timeout in calls:
                        self.assertEqual(timeout, 120)
                        self.assertEqual(argv[argv.index("--target") + 1], target)
                        self.assertEqual(argv[argv.index("--build") + 1], build)
                        self.assertEqual(argv[argv.index("--mode") + 1],
                                         "memory" if "/memory/" in label else "timing")
                    self.assertEqual(len(route["memory_scenarios"]), 2)

    def test_gradle_pin_accepts_exact_retained_windows_stdout(self):
        raw = WINDOWS_GRADLE_STDOUT_8FA
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "6fec462855c154c098721f24957d78e23fc154eaf1550b3b1b1eadbbc0312f16")
        self.assertEqual(len(raw), 608)
        self.assertIn(b"Gradle 9.5.0\r\n", raw)

        def accepts(output):
            scope = {"gradle": output.decode(errors="replace"), "re": re}
            try:
                exec(compile(ast.Module(body=[self.gradle_node], type_ignores=[]),
                             str(RUNNER), "exec"), scope)
            except RuntimeError as error:
                self.assertEqual(str(error), "selected Gradle is not 9.5.0")
                return False
            return True

        self.assertTrue(accepts(raw))
        self.assertTrue(accepts(raw.replace(b"\r\n", b"\n")))
        self.assertTrue(accepts(raw.replace(b"\r\n", b"\r")))
        for bad in (b"Gradle 9.5.0-rc-1\r\n", b"Gradle 9.5.0+vendor\r\n",
                    b"Gradle 9.5.1\r\n", b"Gradle 9.6.0\r\n"):
            self.assertFalse(accepts(raw.replace(b"Gradle 9.5.0\r\n", bad)))
        self.assertFalse(accepts(raw + b"Gradle 9.6.0\r\n"))
