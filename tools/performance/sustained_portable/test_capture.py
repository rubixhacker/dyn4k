import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

import capture
import native_host_capture
import host_image_adverse


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
        with self.assertRaisesRegex(ValueError, "unobserved"):
            capture.require_process_image(None, "a" * 64)
        with self.assertRaisesRegex(ValueError, "unobserved"):
            capture.require_process_image({"identity_kind": "reported_path_only", "sha256": "a" * 64},
                                          "a" * 64)
        with self.assertRaisesRegex(ValueError, "observed process image"):
            capture.require_process_image({"identity_kind": "mapped_executable", "sha256": "b" * 64},
                                          "a" * 64)
        capture.require_process_image({"identity_kind": "mapped_executable", "sha256": "a" * 64},
                                      "a" * 64)

    def test_native_host_selects_only_resolved_target_artifacts(self):
        inventory = {"resolved_artifacts": [
            {"module": capture.native_module("dyn4k-core", "linuxArm64"), "path": "/core.klib"},
            {"module": capture.native_module("dyn4k", "linuxArm64"), "path": "/kotlin.klib"},
        ]}
        self.assertEqual(native_host_capture.selected_artifact(inventory, "dyn4k-core", "linuxArm64"),
                         "/core.klib")
        self.assertEqual(native_host_capture.selected_artifact(inventory, "dyn4k", "linuxArm64"),
                         "/kotlin.klib")
        inventory["resolved_artifacts"].append(inventory["resolved_artifacts"][0])
        with self.assertRaisesRegex(ValueError, "exactly two"):
            native_host_capture.selected_artifact(inventory, "dyn4k-core", "linuxArm64")

    def test_publication_receipt_rejects_resealed_source_archive(self):
        label, target = "dyn4k-core", "linuxX64"
        module = "dyn4k-core-linuxx64"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "io/github/rubixhacker" / module / capture.ARTIFACT_VERSION
            directory.mkdir(parents=True)
            stem = f"{module}-{capture.ARTIFACT_VERSION}"
            klib = directory / f"{stem}.klib"
            klib.write_bytes(b"staged bytes")
            metadata = directory / f"{stem}.module"
            sources = directory / f"{stem}-sources.jar"
            source_root = capture.ROOT / label / "src"
            entries = {str(path.relative_to(source_root)).replace("/kotlin/", "/"): path
                       for path in source_root.rglob("*.kt")
                       if path.relative_to(source_root).parts[0] in ("commonMain", "nativeMain",
                                                                    "linuxMain", "linuxX64Main")}
            with zipfile.ZipFile(sources, "w") as archive:
                for name, path in entries.items():
                    archive.write(path, name)
            document = {
                "component": {"url": f"../../{label}/{capture.ARTIFACT_VERSION}/"
                              f"{label}-{capture.ARTIFACT_VERSION}.module",
                              "group": capture.ARTIFACT_GROUP, "module": label,
                              "version": capture.ARTIFACT_VERSION,
                              "attributes": {"org.gradle.status": "release"}},
                "variants": [{"name": "linuxX64ApiElements-published",
                              "files": [{"url": klib.name, "sha256": capture.digest(klib)}]},
                             {"name": "linuxX64SourcesElements-published",
                              "files": [{"url": sources.name,
                                         "sha256": capture.digest(sources)}]}],
            }
            metadata.write_text(json.dumps(document))
            for path in (klib, metadata, sources):
                path.with_name(path.name + ".sha256").write_text(capture.digest(path))
            self.assertTrue(capture.validate_publication(root, label, target,
                                                         capture.digest(klib))["source_archive_matches_checkout"])
            name = next(iter(entries))
            with zipfile.ZipFile(sources, "w") as archive:
                for entry, path in entries.items():
                    archive.writestr(entry, b"substituted" if entry == name else path.read_bytes())
            sources.with_name(sources.name + ".sha256").write_text(capture.digest(sources))
            document["variants"][1]["files"][0]["sha256"] = capture.digest(sources)
            metadata.write_text(json.dumps(document))
            metadata.with_name(metadata.name + ".sha256").write_text(capture.digest(metadata))
            with self.assertRaisesRegex(ValueError, "source bytes"):
                capture.validate_publication(root, label, target, capture.digest(klib))

    def test_host_deadline_retains_raw_and_process_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            archive.mkdir()
            inventory = root / "inventory.json"
            inventory.write_text("{}\n")
            command = [sys.executable, "-u", "-c",
                       "import sys,time; print('raw',flush=True); "
                       "print('error',file=sys.stderr,flush=True); time.sleep(30)"]
            execution, stdout, stderr = capture.run_process(command, archive, inventory, b"", 0.2)
            self.assertEqual(execution["termination"], "host_deadline")
            self.assertNotEqual(execution["exit_code"], 0)
            self.assertEqual(stdout, (archive / "stdout.raw").read_bytes())
            self.assertEqual(stderr, (archive / "stderr.raw").read_bytes())
            self.assertIn(b"raw", stdout)
            self.assertIn(b"error", stderr)
            self.assertEqual((archive / "build-inventory.json").read_bytes(), inventory.read_bytes())
            self.assertEqual(json.loads((archive / "execution.json").read_text())["pid"],
                             execution["pid"])

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux capture timeout control")
    def test_capture_timeout_writes_unpassed_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "debugExecutable" / "probe.kexe"
            executable.parent.mkdir()
            shutil.copy2(sys.executable, executable)
            core, kotlin, inventory = (root / name for name in ("core.klib", "kotlin.klib",
                                                                 "inventory.json"))
            core.write_bytes(b"core")
            kotlin.write_bytes(b"kotlin")
            inventory.write_text("{}\n")
            source = subprocess.check_output(["git", "-C", str(capture.ROOT), "rev-parse", "HEAD"],
                                             text=True).strip()
            request = SimpleNamespace(target="linuxX64", mode="timing", steps=1, warmup=0,
                                      build="development", scenario=self.scenario["id"],
                                      source_sha=source, runtime=str(executable),
                                      harness=str(executable), core=str(core), kotlin=str(kotlin),
                                      inventory=str(inventory), archive=root / "archive",
                                      host_timeout_seconds=0.2, publication_root=root)
            actual_check = capture.subprocess.check_output
            actual_run = capture.run_process
            def check(command, **kwargs):
                return "" if "status" in command else actual_check(command, **kwargs)
            def hang(command, archive, receipt, stdin, deadline):
                script = "import sys,time; print('raw',flush=True); " \
                         "print('error',file=sys.stderr,flush=True); time.sleep(30)"
                return actual_run([sys.executable, "-u", "-c", script], archive, receipt,
                                  stdin, deadline)
            with mock.patch.object(capture.subprocess, "check_output", side_effect=check), \
                 mock.patch.object(capture, "validate_inventory", return_value={
                     "gradle": "9.5.0", "kgp": "2.4.20",
                     "compile_configuration": "linuxX64CompileKlibraries"}), \
                 mock.patch.object(capture, "run_process", side_effect=hang):
                with self.assertRaisesRegex(ValueError, "host deadline"):
                    capture.capture(request)
            record = json.loads((request.archive / "capture.json").read_text())
            self.assertEqual(record["termination"], "host_deadline")
            self.assertEqual(record["qualification"], "unpassed")
            self.assertIn(b"raw", (request.archive / "stdout.raw").read_bytes())
            self.assertIn(b"error", (request.archive / "stderr.raw").read_bytes())
            self.assertEqual((request.archive / "build-inventory.json").read_bytes(), b"{}\n")

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux mapped executable control")
    def test_path_swap_keeps_linux_proc_image_bytes(self):
        result = host_image_adverse.path_swap_control()
        self.assertEqual(result["swap"], "applied")
        self.assertEqual(result["mapped_image_identity"], "matched_original")

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
            inventory["resolved_artifacts"][1]["module"] = capture.native_module("dyn4k", "linuxX64")
            for module in ("example:dyn4k-core-linuxx64:1",
                           capture.native_module("dyn4k-core", "linuxArm64"),
                           "io.github.rubixhacker:dyn4k-core-linuxx64:wrong"):
                inventory["resolved_artifacts"][0]["module"] = module
                receipt.write_text(json.dumps(inventory))
                with self.subTest(module=module), self.assertRaisesRegex(ValueError, "coordinates"):
                    capture.validate_inventory(receipt, "linuxX64", "development", source,
                                               capture.source_tree(), capture.MANIFEST, harness,
                                               core, kotlin, bundle, root)
            inventory["resolved_artifacts"][0]["module"] = capture.native_module("dyn4k-core", "linuxArm64")
            inventory["resolved_artifacts"][1]["module"] = capture.native_module("dyn4k", "linuxArm64")
            receipt.write_text(json.dumps(inventory))
            with self.assertRaisesRegex(ValueError, "coordinates"):
                capture.validate_inventory(receipt, "linuxX64", "development", source,
                                           capture.source_tree(), capture.MANIFEST, harness,
                                           core, kotlin, bundle, root)
            inventory["resolved_artifacts"][0]["module"] = capture.native_module("dyn4k-core", "linuxX64")
            inventory["resolved_artifacts"][1]["module"] = capture.native_module("dyn4k", "linuxX64")
            receipt.write_text(json.dumps(inventory))
            with self.assertRaisesRegex(ValueError, "not a KLIB"):
                capture.validate_inventory(receipt, "linuxX64", "development", source,
                                           capture.source_tree(), capture.MANIFEST, harness,
                                           core, kotlin, bundle, root)
            inventory.update(target="js", compiler_mode="debug")
            inventory["resolved_artifacts"][0]["module"] = "example:dyn4k-core-js:1"
            inventory["resolved_artifacts"][1]["module"] = "example:dyn4k-js:1"
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
