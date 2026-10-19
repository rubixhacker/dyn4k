import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import full_klib_adapter as adapter
import full_klib_consumer
import independent_gates


REPOSITORY = Path(__file__).resolve().parents[2]
CANDIDATE = "d629b9e388db08b3c7e24b22ff853ac387b951ce"
EVIDENCE = os.environ.get("DYN4K_KLIB_EVIDENCE_ROOT")
LANES = {
    "linuxX64:Linux x64:current:debug-g": (
        "native", "linuxx64", "9e84cd8c31a382598fd734f2d043dc69d5afc43102e7b125f4eabbfa4b18c7a1"),
    "js:Node.js:current:development": (
        "js", "js", "3aa17d2e02a8d3f5de38f5bbec57e41de80e18686d37b3f8f5c6107f855a1f6c"),
}
RUNTIME = ("Linux 7.2.9-ogc3.1.fc44.x86_64 x86_64 | "
           'openjdk version "21.0.12.1" 2026-08-18 LTS | v26.10.0')


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence(lane_id):
    root = Path(EVIDENCE)
    name, variant, digest = LANES[lane_id]
    archive = root / f"full-staged-klib-112-sol-{name}-d629-transported"
    trusted = json.loads((root / f"full-staged-klib-112-sol-trusted-{name}-toolchain.json")
                         .read_bytes())
    stage = root / "full-staged-klib-112-sol-stage-copy"
    hashes = {module: _sha(full_klib_consumer.staged_binary(stage, module, variant))
              for module in full_klib_consumer.MODULES}
    expected = {
        "expected_artifact_hashes": hashes,
        "expected_runtime_identity": RUNTIME,
        "expected_archive_digests": {"staged-consumer": digest},
        "expected_klib_toolchain": trusted,
        "expected_klib_executables": {
            "gradle": "/tmp/dyn4k-tools/gradle-9.5.0/bin/gradle",
            "node": "/usr/local/bin/node",
        },
    }
    manifest, selected = full_klib_consumer.contract(REPOSITORY, lane_id)
    ids = [case["id"] for case in selected["cases"]]
    generic = independent_gates.evaluate_gate(
        "staged-consumer", archive, CANDIDATE, lane_id, manifest["lanes"][lane_id],
        REPOSITORY, hashes, RUNTIME, digest, manifest=manifest)
    if generic["status"] != "PASSED":
        raise AssertionError(f"retained generic KLIB gate failed: {generic}")
    return archive, expected, ids, generic, hashes


class FullKlibAdapterTests(unittest.TestCase):
    def test_rejects_unsupported_lane_before_public_dispatch(self):
        with patch.object(full_klib_consumer, "verify") as public:
            with self.assertRaisesRegex(ValueError, "does not cover lane"):
                adapter.verify_staged_consumer(
                    REPOSITORY, CANDIDATE, "js:browser:current:development", [],
                    "/unused", {"status": "PASSED"}, {}, {})
            public.assert_not_called()

    def test_rejects_generic_result_mismatch(self):
        lane = "js:Node.js:current:development"
        with patch.object(full_klib_consumer, "contract") as contract, \
                patch.object(independent_gates, "archive_digest", return_value="a" * 64), \
                patch.object(adapter, "_trusted_toolchain", return_value=({}, Path("/node"))), \
                patch.object(full_klib_consumer, "verify", return_value={"status": "PASSED"}):
            contract.return_value = (None, {"cases": [{"id": "case"}]})
            expected = {"expected_artifact_hashes": {"dyn4k-core": "b" * 64,
                                                     "dyn4k": "c" * 64},
                        "expected_runtime_identity": "runtime",
                        "expected_archive_digests": {"staged-consumer": "a" * 64}}
            with self.assertRaisesRegex(ValueError, "differs from independent gate"):
                adapter.verify_staged_consumer(
                    REPOSITORY, CANDIDATE, lane, ["case"], "/archive",
                    {"status": "PASSED", "archive_sha256": "wrong"}, expected,
                    expected["expected_artifact_hashes"])

    @unittest.skipUnless(EVIDENCE, "requires retained full KLIB archives")
    def test_real_linux_and_node_signed_input_replay(self):
        for lane in LANES:
            with self.subTest(lane=lane):
                archive, expected, ids, generic, hashes = _evidence(lane)
                self.assertEqual(independent_gates.archive_digest(archive),
                                 expected["expected_archive_digests"]["staged-consumer"])
                result = adapter.verify_staged_consumer(
                    REPOSITORY, CANDIDATE, lane, ids, archive, generic, expected, hashes)
                self.assertEqual(result, generic)
                self.assertEqual(result["selected_cases"], 2523)

    @unittest.skipUnless(EVIDENCE, "requires retained full KLIB archives")
    def test_real_archive_rejects_incomplete_and_wrong_audit(self):
        lane = "js:Node.js:current:development"
        archive, expected, ids, generic, hashes = _evidence(lane)
        changes = (
            ("missing runtime", lambda item: item.pop("expected_runtime_identity"),
             "runtime or archive digest is incomplete"),
            ("wrong runtime", lambda item: item.update(expected_runtime_identity="wrong"),
             "runtime identity differs"),
            ("wrong archive digest", lambda item: item["expected_archive_digests"].update(
                {"staged-consumer": "0" * 64}), "archive digest differs"),
            ("missing toolchain", lambda item: item.pop("expected_klib_toolchain"),
             "toolchain identity is incomplete"),
            ("wrong Node hash", lambda item: item["expected_klib_toolchain"].update(
                node_sha256="0" * 64), "Node executable SHA-256 differs"),
        )
        for name, change, error in changes:
            with self.subTest(name=name):
                altered = copy.deepcopy(expected)
                change(altered)
                with self.assertRaisesRegex(ValueError, error):
                    adapter.verify_staged_consumer(
                        REPOSITORY, CANDIDATE, lane, ids, archive, generic, altered, hashes)
        with self.assertRaisesRegex(ValueError, "different approved case suite"):
            adapter.verify_staged_consumer(
                REPOSITORY, CANDIDATE, lane, ids[:-1], archive, generic, expected, hashes)
        with self.assertRaisesRegex(ValueError, "audited target"):
            adapter.verify_staged_consumer(
                REPOSITORY, CANDIDATE, lane, ids, archive, generic, expected,
                {**hashes, "dyn4k": "0" * 64})

    @unittest.skipUnless(EVIDENCE, "requires retained full KLIB archives")
    def test_real_archive_rejects_wrong_supported_lane(self):
        node_lane = "js:Node.js:current:development"
        native_lane = "linuxX64:Linux x64:current:debug-g"
        node_archive, expected, ids, generic, hashes = _evidence(node_lane)
        native_archive, _, _, _, _ = _evidence(native_lane)
        self.assertNotEqual(node_archive, native_archive)
        altered = copy.deepcopy(expected)
        altered["expected_archive_digests"]["staged-consumer"] = (
            independent_gates.archive_digest(native_archive))
        with self.assertRaisesRegex(ValueError, "receipt differs from exact approved"):
            adapter.verify_staged_consumer(
                REPOSITORY, CANDIDATE, node_lane, ids, native_archive, generic,
                altered, hashes)

    @unittest.skipUnless(EVIDENCE, "requires retained full KLIB archives")
    def test_resealed_changed_bundle_cannot_execute_node(self):
        lane = "js:Node.js:current:development"
        archive, expected, ids, generic, hashes = _evidence(lane)
        with tempfile.TemporaryDirectory(prefix="dyn4k-klib-adapter-") as temporary:
            changed = Path(temporary) / "archive"
            shutil.copytree(archive, changed, copy_function=shutil.copy2)
            receipt = json.loads((changed / "receipt.json").read_bytes())
            program = next((changed / "runtime/bundle/core").glob("*-core-test.js"))
            program.write_bytes(program.read_bytes() + b"\nchanged bundle\n")
            row = next(item for item in receipt["files"]
                       if item["path"] == program.relative_to(changed).as_posix())
            os.utime(program, ns=(row["mtime_ns"], row["mtime_ns"]))
            row["sha256"] = _sha(program)
            (changed / "receipt.json").write_bytes(full_klib_consumer.encoded(receipt) + b"\n")
            altered = copy.deepcopy(expected)
            altered["expected_archive_digests"]["staged-consumer"] = (
                independent_gates.archive_digest(changed))
            actual_run = subprocess.run

            def guarded_run(command, *args, **kwargs):
                if "--test" in command:
                    raise AssertionError("transported Node bundle executed")
                return actual_run(command, *args, **kwargs)

            with patch.object(subprocess, "run", side_effect=guarded_run) as observed:
                with self.assertRaisesRegex(ValueError, "Node runtime process differs"):
                    adapter.verify_staged_consumer(
                        REPOSITORY, CANDIDATE, lane, ids, changed, generic, altered, hashes)
                self.assertFalse(any("--test" in call.args[0]
                                     for call in observed.call_args_list))


if __name__ == "__main__":
    unittest.main()
