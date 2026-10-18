import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

import capture
import native_host_capture


class PortableCaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(capture.MANIFEST.read_text())
        cls.scenario = capture.scenario_from_manifest(
            cls.manifest, "separated.default.small.30hz.direct_kotlin")
        cls.hashes = {"core": "a" * 64, "kotlin": "b" * 64}
        cls.source = "c" * 40
        cls.producer_tree = "e" * 40
        cls.nonce = "d" * 32

    def protocol(self):
        scenario = self.scenario
        lines = [
            ["PROVIDER", scenario["api"], self.source, self.hashes["core"],
             self.hashes["kotlin"], scenario["id"], "development", self.nonce],
            ["RESOLUTION", "1", "64"],
            ["LINK", self.source, self.producer_tree],
            ["CONSTRUCTION", "100", "0"],
            ["CLOCK", "warmup", "0", "1", "3"],
            ["RESET", "after_warmup", "1"],
            ["CLOCK", "measure", "0", "4", "10"],
            ["STEP", "0", "6", "2", "0", "100", "0", "100",
             "75.0", "0.0", "0", "0", "0", "0", "0", "0"],
            ["RUN", scenario["api"], "timing", "1", "1", "10", "1",
             "memory_attribution_missing", "plateau_missing", "unpassed"],
            ["COMPLETE", self.nonce],
        ]
        return ("\n".join("DYN4K\t" + "\t".join(row) for row in lines) + "\n").encode()

    def validate(self, payload):
        return capture.validate_protocol(
            payload, self.scenario, self.source, self.producer_tree, self.hashes,
            "development", self.nonce, 1, 1, "timing")

    def test_manifest_rejects_baseline_and_unknown_scenario(self):
        with self.assertRaisesRegex(ValueError, "requires direct_kotlin or compatibility"):
            capture.scenario_from_manifest(
                self.manifest, "separated.default.small.30hz.baseline")
        with self.assertRaisesRegex(ValueError, "no unique scenario"):
            capture.scenario_from_manifest(self.manifest, "missing")

    def test_complete_protocol_preserves_raw_clock_and_activity(self):
        clocks, steps, provider, run = self.validate(self.protocol())
        self.assertEqual(clocks["measure"], [(0, 4, 10)])
        self.assertEqual(int(steps[0][7]), 100)
        self.assertEqual(provider[1], "direct_kotlin")
        self.assertEqual(run[-1], "unpassed")

    def test_rejects_substituted_provider(self):
        payload = self.protocol().replace(b"\taaaaaaaaaa", b"\teeeeeeeeee")
        with self.assertRaisesRegex(ValueError, "provider"):
            self.validate(payload)

    def test_rejects_missing_reset_and_truncated_clock(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "RESET"):
            self.validate(payload.replace(b"DYN4K\tRESET\tafter_warmup\t1\n", b""))
        with self.assertRaisesRegex(ValueError, "CLOCK"):
            self.validate(payload.replace(b"DYN4K\tCLOCK\tmeasure\t0\t4\t10\n", b""))

    def test_rejects_fake_activity_or_performance_pass(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "fixture activity"):
            self.validate(payload.replace(b"\t100\t0\t100\t75.0", b"\t1\t0\t100\t75.0"))
        with self.assertRaisesRegex(ValueError, "unfinished evidence"):
            self.validate(payload.replace(b"\tplateau_missing\tunpassed", b"\tplateau_missing\tpassed"))

    def test_rejects_phase_swap_and_run_activity_mismatch(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "warmup clock"):
            self.validate(payload.replace(b"CLOCK\twarmup", b"CLOCK\tother")
                          .replace(b"CLOCK\tmeasure", b"CLOCK\twarmup")
                          .replace(b"CLOCK\tother", b"CLOCK\tmeasure"))
        with self.assertRaisesRegex(ValueError, "activity count"):
            self.validate(payload.replace(b"\t10\t1\tmemory_attribution",
                                          b"\t10\t0\tmemory_attribution"))

    def test_rejects_wrong_source_before_process_launch(self):
        request = SimpleNamespace(target="linuxX64", mode="timing",
                                  steps=1, warmup=0, build="development",
                                  scenario=self.scenario["id"], source_sha=self.source)
        with self.assertRaisesRegex(ValueError, "source SHA"):
            capture.capture(request)
        with self.assertRaisesRegex(ValueError, "absolute regular file"):
            capture.required_file("relative.klib", "core")

    def test_native_host_and_process_image_fail_closed(self):
        wrong_host = "linuxArm64" if capture.sys.platform == "win32" else "mingwX64"
        with self.assertRaisesRegex(ValueError, "matching Native host"):
            capture.require_native_host(wrong_host)
        with self.assertRaisesRegex(ValueError, "observed process image"):
            capture.require_process_image(None, "a" * 64)
        with self.assertRaisesRegex(ValueError, "observed process image"):
            capture.require_process_image({"sha256": "b" * 64}, "a" * 64)
        capture.require_process_image({"sha256": "a" * 64}, "a" * 64)

    def test_native_host_selects_only_resolved_target_artifacts(self):
        inventory = {"resolved_artifacts": [
            {"module": "example:dyn4k-core-linuxarm64:1", "path": "/core.klib"},
            {"module": "example:dyn4k-linuxarm64:1", "path": "/kotlin.klib"},
        ]}
        self.assertEqual(native_host_capture.selected_artifact(inventory, "dyn4k-core"),
                         "/core.klib")
        self.assertEqual(native_host_capture.selected_artifact(inventory, "dyn4k"),
                         "/kotlin.klib")
        inventory["resolved_artifacts"].append(inventory["resolved_artifacts"][0])
        with self.assertRaisesRegex(ValueError, "one resolved dyn4k-core"):
            native_host_capture.selected_artifact(inventory, "dyn4k-core")

    def test_rejects_nonfinite_and_negative_physical_diagnostics(self):
        payload = self.protocol()
        for replacement in (b"NaN", b"Infinity", b"-1.0"):
            with self.subTest(replacement=replacement), self.assertRaisesRegex(ValueError, "physical activity"):
                self.validate(payload.replace(b"75.0", replacement))

    def test_rejects_negative_or_unsampled_pair_counts(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "sampled pair"):
            self.validate(payload.replace(b"\t0\t0\t0\nDYN4K\tRUN",
                                          b"\t-99\t0\t0\nDYN4K\tRUN"))
        additional = payload.replace(
            b"DYN4K\tRUN", b"DYN4K\tCLOCK\tmeasure\t1\t11\t13\n"
            b"DYN4K\tSTEP\t1\t2\t1\t0\t100\t0\t100\t75.0\t0.0\t0\t0\t0\t0\t0\t0\n"
            b"DYN4K\tCLOCK\tmeasure\t2\t14\t16\n"
            b"DYN4K\tSTEP\t2\t2\t1\t0\t100\t0\t100\t75.0\t0.0\t0\t0\t0\t0\t0\t0\nDYN4K\tRUN")
        additional = additional.replace(b"\ttiming\t1\t1\t10\t1", b"\ttiming\t3\t1\t18\t3")
        with self.assertRaisesRegex(ValueError, "unsampled pair"):
            capture.validate_protocol(additional, self.scenario, self.source, self.producer_tree, self.hashes,
                                      "development", self.nonce, 3, 1, "timing")

    def test_rejects_cross_phase_clock_reversal_and_clock_after_step(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "measure clock"):
            self.validate(payload.replace(b"\tmeasure\t0\t4\t10", b"\tmeasure\t0\t1\t7")
                          .replace(b"STEP\t0\t6", b"STEP\t0\t6"))
        clock = b"DYN4K\tCLOCK\tmeasure\t0\t4\t10\n"
        activity = b"DYN4K\tSTEP\t0\t6\t2\t0\t100\t0\t100\t75.0\t0.0\t0\t0\t0\t0\t0\t0\n"
        with self.assertRaisesRegex(ValueError, "expected CLOCK"):
            self.validate(payload.replace(clock + activity, activity + clock))

    def test_rejects_missing_family_joints_and_extra_bodies(self):
        joint = dict(self.scenario, id="joint.angle_free.small.30hz.direct_kotlin",
                     family="joint", variant="angle_free", dynamic_bodies=50)
        payload = self.protocol().replace(self.scenario["id"].encode(), joint["id"].encode())
        payload = payload.replace(b"CONSTRUCTION\t100\t0", b"CONSTRUCTION\t100\t0")
        with self.assertRaisesRegex(ValueError, "construction"):
            capture.validate_protocol(payload, joint, self.source, self.producer_tree, self.hashes,
                                      "development", self.nonce, 1, 1, "timing")
        payload = payload.replace(b"CONSTRUCTION\t100\t0", b"CONSTRUCTION\t100\t50")
        payload = payload.replace(b"STEP\t0\t6\t2\t0\t100\t0\t100",
                                  b"STEP\t0\t6\t2\t0\t100\t0\t50")
        with self.assertRaisesRegex(ValueError, "fixture activity"):
            capture.validate_protocol(payload, joint, self.source, self.producer_tree, self.hashes,
                                      "development", self.nonce, 1, 1, "timing")
        with self.assertRaisesRegex(ValueError, "fixture activity"):
            self.validate(self.protocol().replace(b"\t100\t0\t100\t75.0",
                                                 b"\t101\t0\t100\t75.0"))

    def test_rejects_missing_calibration_link_and_completion(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "resolution calibration"):
            self.validate(payload.replace(b"RESOLUTION\t1\t64", b"RESOLUTION\t0\t64"))
        with self.assertRaisesRegex(ValueError, "linked producer identity"):
            self.validate(payload.replace(b"LINK\t" + self.source.encode(),
                                          b"LINK\t" + b"f" * 40))
        with self.assertRaisesRegex(ValueError, "COMPLETE"):
            self.validate(payload.replace(b"DYN4K\tCOMPLETE\t" + self.nonce.encode() + b"\n", b""))

    def test_build_inventory_binds_resolved_and_staged_bytes(self):
        source = subprocess.check_output(["git", "-C", str(capture.ROOT), "rev-parse", "HEAD"],
                                         text=True).strip()
        tracked = subprocess.check_output(
            ["git", "-C", str(capture.ROOT), "ls-tree", "-r", "--name-only", "HEAD",
             "consumers/performance/portable", "tools/performance/sustained_portable"],
            text=True).splitlines()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / name for name in ("entry.js", "core.klib", "kotlin.klib",
                                               "resolved-core.klib", "resolved-kotlin.klib")]
            for path, value in zip(paths, (b"entry", b"core", b"kotlin", b"core", b"kotlin")):
                path.write_bytes(value)
            harness, core, kotlin, resolved_core, resolved_kotlin = paths
            bundle = {harness.name: capture.digest(harness)}
            inventory = {
                "format": "portable-build-inventory-v1", "target": "js",
                "build": "development", "source_sha": source,
                "producer_tree": capture.source_tree(), "gradle": "9.5.0", "kgp": "2.4.20",
                "manifest_sha256": capture.digest(capture.MANIFEST),
                "harness": str(harness), "bundle_sha256": bundle,
                "source_files": {name: capture.digest(capture.ROOT / name) for name in tracked},
                "resolved_artifacts": [
                    {"module": "example:dyn4k-core-js:1", "path": str(resolved_core),
                     "sha256": capture.digest(resolved_core)},
                    {"module": "example:dyn4k-js:1", "path": str(resolved_kotlin),
                     "sha256": capture.digest(resolved_kotlin)},
                ],
            }
            receipt = root / "inventory.json"
            receipt.write_text(json.dumps(inventory))
            capture.validate_inventory(receipt, "js", "development", source,
                                       capture.source_tree(), capture.MANIFEST, harness,
                                       core, kotlin, bundle)
            bad_bundle = {harness.name: "0" * 64}
            with self.assertRaisesRegex(ValueError, "source, build, or bundle"):
                capture.validate_inventory(receipt, "js", "development", source,
                                           capture.source_tree(), capture.MANIFEST, harness,
                                           core, kotlin, bad_bundle)
            inventory.update(target="linuxX64", compile_configuration="linuxX64CompileKlibraries",
                             compiler_mode="debug", link_task="linkDebugExecutableLinuxX64")
            receipt.write_text(json.dumps(inventory))
            capture.validate_inventory(receipt, "linuxX64", "development", source,
                                       capture.source_tree(), capture.MANIFEST, harness,
                                       core, kotlin, bundle)
            inventory["compiler_mode"] = "release"
            receipt.write_text(json.dumps(inventory))
            with self.assertRaisesRegex(ValueError, "source, build, or bundle"):
                capture.validate_inventory(receipt, "linuxX64", "development", source,
                                           capture.source_tree(), capture.MANIFEST, harness,
                                           core, kotlin, bundle)
            inventory.update(target="js", compiler_mode="debug")
            receipt.write_text(json.dumps(inventory))
            core.write_bytes(b"substituted")
            with self.assertRaisesRegex(ValueError, "Gradle-resolved build input"):
                capture.validate_inventory(receipt, "js", "development", source,
                                           capture.source_tree(), capture.MANIFEST, harness,
                                           core, kotlin, bundle)
            with self.assertRaisesRegex(ValueError, "source, build, or bundle"):
                capture.validate_inventory(receipt, "js", "development", "f" * 40,
                                           capture.source_tree(), capture.MANIFEST, harness,
                                           core, kotlin, bundle)


if __name__ == "__main__":
    unittest.main()
