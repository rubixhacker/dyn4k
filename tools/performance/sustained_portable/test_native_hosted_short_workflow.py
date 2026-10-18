import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest


WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/performance-native-host-short.yml"
RAW_LIMIT = 64 * 1024 * 1024


def workflow_nodes():
    source = WORKFLOW.read_text()
    body = source.split("          python -B - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
    tree = ast.parse("\n".join(line[10:] for line in body.splitlines()) + "\n")
    raw = next(node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == "raw_file")
    routes = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                  and node.target.id == "api")
    receipt = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.Expr) and "route-result.json" in ast.unparse(node))
    return raw, routes, receipt


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
        self.raw_node, self.route_node, self.receipt_node = workflow_nodes()
        self.scope = {"hashlib": hashlib, "json": json, "Path": Path, "sys": sys}
        exec(compile(ast.Module(body=[self.raw_node], type_ignores=[]),
                     str(WORKFLOW), "exec"), self.scope)

    def test_growing_zero_size_file_has_bounded_incomplete_hash(self):
        growing = GrowingFile()
        result = self.scope["raw_file"](growing)
        self.assertEqual(growing.read_bytes, 1)
        self.assertEqual(result["status"], "changed_during_hash")
        self.assertNotIn("sha256", result)
        oversized = GrowingFile(RAW_LIMIT + 1)
        self.assertEqual(self.scope["raw_file"](oversized)["status"], "hash_size_limit")
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

            route = {"qualification": "unpassed", "commands": {}, "scenarios": {}}

            def execute(label, argv, timeout):
                labels.append(label)
                archive = evidence / "captures" / label.split("/")[1].split("-")[0]
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
                         str(WORKFLOW), "exec"), self.scope)
            exec(compile(ast.Module(body=[self.receipt_node], type_ignores=[]),
                         str(WORKFLOW), "exec"), self.scope)
            self.assertEqual(labels, ["captures/direct_kotlin-command",
                                      "captures/compatibility-command"])
            persisted = json.loads((evidence / "route-result.json").read_text())
            self.assertEqual(persisted["qualification"], "unpassed")
            self.assertEqual(len(persisted["scenarios"]), 2)
            direct = json.loads((evidence / "captures/direct_kotlin-failure.json").read_text())
            compatibility = json.loads((evidence / "captures/compatibility-failure.json").read_text())
            self.assertEqual(direct["raw"]["stdout.raw"]["status"], "changed_during_hash")
            self.assertEqual(compatibility["raw"]["stderr.raw"]["status"], "unreadable")
            self.assertEqual(direct["raw"]["stderr.raw"], {
                "bytes": 7, "sha256": hashlib.sha256(b"raw-err").hexdigest()})
            for receipt in (direct, compatibility):
                self.assertEqual(receipt["qualification"], "unpassed")
                self.assertEqual(receipt["raw_collection"], "incomplete")
            self.assertEqual(growing.read_bytes, 1)
