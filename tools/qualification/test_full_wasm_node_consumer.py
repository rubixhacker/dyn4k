import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

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

    def test_public_archive_digest_rejects_changed_bytes_and_symbolic_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory)
            (archive / "receipt.json").write_bytes(b"sealed receipt")
            (archive / "raw.log").write_bytes(b"original method events")
            original = route.archive_digest(archive)
            (archive / "raw.log").write_bytes(b"changed method events")
            self.assertNotEqual(route.archive_digest(archive), original)
            (archive / "raw.log").unlink()
            (archive / "raw.log").symlink_to(archive / "receipt.json")
            with self.assertRaisesRegex(ValueError, "symbolic"):
                route.archive_digest(archive)


if __name__ == "__main__":
    unittest.main()
