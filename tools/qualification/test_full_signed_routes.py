import hashlib
import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import full_signed_routes
import independent_gates


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = independent_gates.load_approved_manifest(ROOT)
HASHES = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
CANDIDATE = "9cd6868512836a3eb8192d9abc387427705e94b4"


class SignedRouteTests(unittest.TestCase):
    def test_approved_matrix_has_one_dedicated_route_per_lane(self):
        table = full_signed_routes.route_table(ROOT)
        self.assertEqual(set(table), set(MANIFEST["lanes"]))
        self.assertEqual(Counter(table.values()), full_signed_routes.COUNTS)

    def _receipt(self, lane, runtime):
        selected = independent_gates.consumer_contract(MANIFEST, lane)
        return {"schema": 1, "status": "PASSED", "candidate_sha": CANDIDATE,
                "lane": lane, "consumer_group": "full-suite",
                "consumer_contract_sha256": independent_gates.digest(selected),
                "artifact_hashes": dict(HASHES), "runtime_identity": runtime,
                **{key: MANIFEST["lanes"][lane][key] for key in
                   ("target", "runtime", "version", "configuration")}}

    def _archive(self, base, receipt):
        archive = base / "archive"
        archive.mkdir()
        (archive / "receipt.json").write_text(json.dumps(receipt))
        return archive

    def _witness(self, base, expected, lane, runtime, mode, executables,
                 build_executable):
        witness = {"schema": "independent-execution-witness/1",
                   "candidate_sha": CANDIDATE, "lane": lane,
                   "archive_sha256": "c" * 64, "runtime_identity": runtime,
                   "mode": mode, "executables": executables,
                   "staged_artifacts": HASHES, "auditor": "independent test",
                   "build": {"executable_sha256": build_executable, "pid": 10,
                             "exit_code": 0, "started_ns": 1, "finished_ns": 2},
                   "processes": {name: {"executable_sha256": value, "pid": index + 1,
                                        "exit_code": 0, "started_ns": 1,
                                        "finished_ns": 2}
                                 for index, (name, value) in enumerate(executables.items())}}
        path = base / "witness.json"
        path.write_text(json.dumps(witness))
        expected["expected_execution_witness"] = {
            "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_wasm_signed_mapping_replays_and_rejects_changed_identity(self):
        lane = "wasmJs:Node.js:current:development"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            binary = base / "node"
            binary.write_bytes(b"node executable")
            identity = {"family": "Node.js", "role": "current", "version": "v26.12.0",
                        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                        "path": str(binary), "host": "test host arch"}
            runtime = "wasm-node-v1:" + independent_gates.digest(identity)
            receipt = self._receipt(lane, identity)
            archive = self._archive(base, receipt)
            expected = {"expected_artifact_hashes": HASHES,
                        "expected_runtime_identity": runtime,
                        "expected_archive_digests": {"staged-consumer": "c" * 64},
                        "expected_wasm_runtime": identity,
                        "expected_wasm_runtime_binary": str(binary)}
            public = {"status": "PASSED", "selected_methods": 2523,
                      "archive_digest": "c" * 64}
            with patch.object(full_signed_routes, "_source"), patch.object(
                    full_signed_routes, "_selected", return_value=[None] * 2523), patch.object(
                    full_signed_routes.platform, "system", return_value="test"), patch.object(
                    full_signed_routes.platform, "release", return_value="host"), patch.object(
                    full_signed_routes.platform, "machine", return_value="arch"), patch(
                    "full_wasm_node_consumer.runtime_preflight",
                    return_value={"status": "PASSED", "version": "v26.12.0",
                                  "sha256": identity["sha256"], "path": str(binary)}), patch(
                    "full_wasm_node_consumer.verify", return_value=public) as verify:
                self.assertEqual(full_signed_routes.verify(
                    ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, "c" * 64), public)
                self.assertTrue(verify.call_args.kwargs["replay"])
                expected["expected_runtime_identity"] = "wasm-node-v1:" + "0" * 64
                with self.assertRaisesRegex(ValueError, "signed staged consumer identity"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, "c" * 64)

    def test_native_host_signed_selection_rejects_mode_and_swapped_module(self):
        lane = "linuxArm64:Linux ARM64:current:debug-g"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            gradle, python = base / "gradle", base / "python"
            gradle.write_bytes(b"gradle")
            python.write_bytes(b"python")
            java = base / "jdk/bin/java"
            native = base / "native/bin/kotlinc-native"
            compiler = base / "native/konan/lib/kotlin-native-compiler-embeddable.jar"
            for path in (java, native, compiler):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(path.name.encode())
            toolchain = {"gradle_executable": str(gradle),
                         "gradle_sha256": hashlib.sha256(gradle.read_bytes()).hexdigest(),
                         "python_executable": str(python),
                         "python_sha256": hashlib.sha256(python.read_bytes()).hexdigest(),
                         "java_home": str(base / "jdk"),
                         "java_sha256": hashlib.sha256(java.read_bytes()).hexdigest(),
                         "native_home": str(base / "native"),
                         "native_sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
                         "native_compiler_sha256": hashlib.sha256(
                             compiler.read_bytes()).hexdigest()}
            host = {"system": "Linux"}
            runtime = "d" * 64
            receipt = self._receipt(lane, runtime)
            receipt["host"] = host
            archive = self._archive(base, receipt)
            expected = {"expected_artifact_hashes": HASHES,
                        "expected_runtime_identity": runtime,
                        "expected_archive_digests": {"staged-consumer": "c" * 64},
                        "expected_native_selection": {"lane": lane},
                        "expected_native_toolchain": toolchain,
                        "expected_native_host": host}
            (archive / "runtime").mkdir()
            products = {"core": {"sha256": "d" * 64},
                        "facade": {"sha256": "e" * 64}}
            (archive / "runtime/products.json").write_text(json.dumps(products))
            expected["expected_native_host_executables"] = {
                name: product["sha256"] for name, product in products.items()}
            self._witness(base, expected, lane, runtime, "debug-g",
                          expected["expected_native_host_executables"],
                          toolchain["gradle_sha256"])
            public = {"status": "PASSED", "selected_cases": 2523,
                      "archive_sha256": "c" * 64}
            with patch.object(full_signed_routes, "_source"), patch.object(
                    full_signed_routes, "_selected", return_value=[None] * 2523), patch(
                    "full_native_host_consumer.digest", return_value=runtime), patch(
                    "full_native_host_consumer.validate_host"), patch(
                    "full_native_host_consumer.verify", return_value=public):
                self.assertEqual(full_signed_routes.verify(
                    ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, "c" * 64), public)
                receipt["configuration"] = "optimized-opt"
                (archive / "receipt.json").write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError, "mode differs"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, "c" * 64)
                receipt["configuration"] = "debug-g"
                receipt["artifact_hashes"]["dyn4k"] = "0" * 64
                (archive / "receipt.json").write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError, "audited artifacts"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, "c" * 64)

    def test_android_native_signed_guest_rejects_wrong_guest(self):
        lane = "androidNativeX64:Android Native x86_64:current:debug-g"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            adb = base / "adb"
            adb.write_bytes(b"adb")
            java, gradle = base / "java", base / "gradle"
            java.write_bytes(b"java")
            gradle.write_bytes(b"gradle")
            guest = {"api": 37, "abi": "x86_64"}
            runtime = independent_gates.digest(guest)
            receipt = self._receipt(lane, runtime)
            receipt["guest_record"] = "guest.json"
            archive = self._archive(base, receipt)
            (archive / "guest.json").write_text(json.dumps(guest))
            expected = {"expected_artifact_hashes": HASHES,
                        "expected_runtime_identity": runtime,
                        "expected_archive_digests": {"staged-consumer": "c" * 64},
                        "expected_android_native_guest": guest,
                        "expected_android_native_toolchain": {
                            "adb_sha256": hashlib.sha256(adb.read_bytes()).hexdigest(),
                            "java_sha256": hashlib.sha256(java.read_bytes()).hexdigest(),
                            "gradle_sha256": hashlib.sha256(gradle.read_bytes()).hexdigest()},
                        "expected_android_native_executable_paths": {
                            "java": str(java), "gradle": str(gradle), "adb": str(adb)},
                        "expected_android_native_executables": {
                            "core": "d" * 64, "facade": "e" * 64},
                        "expected_android_native_adb": str(adb),
                        "expected_android_native_serial": "emulator-5554",
                        "expected_android_native_replay_output": str(base / "replay")}
            self._witness(base, expected, lane, runtime, "debug-g",
                          expected["expected_android_native_executables"],
                          expected["expected_android_native_toolchain"]["gradle_sha256"])
            public = {"status": "PASSED", "selected_cases": 2523,
                      "archive_sha256": "c" * 64}
            with patch.object(full_signed_routes, "_source"), patch.object(
                    full_signed_routes, "_selected", return_value=[None] * 2523), patch(
                    "full_android_native_consumer.verify", return_value=public):
                self.assertEqual(full_signed_routes.verify(
                    ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, "c" * 64), public)
                (archive / "guest.json").write_text(json.dumps({"api": 21, "abi": "x86_64"}))
                with self.assertRaisesRegex(ValueError, "guest"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, "c" * 64)

    def test_apple_signed_device_rejects_current_on_minimum_os(self):
        lane = "iosArm64:iOS physical ARM64:current:debug-g"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            device = {"model": "iPhone", "os": "iOS", "version": "26.0", "udid": "device"}
            runtime = "iPhone | iOS 26.0 | device"
            receipt = self._receipt(lane, runtime)
            receipt["device"] = device
            archive = self._archive(base, receipt)
            expected = {"expected_artifact_hashes": HASHES,
                        "expected_runtime_identity": runtime,
                        "expected_archive_digests": {"staged-consumer": "c" * 64},
                        "expected_apple_device": device,
                        "expected_apple_device_toolchain": {"xcode": "Xcode 26.4.1"}}
            binaries = {name: base / name for name in ("java", "gradle", "xcrun", "xcodebuild")}
            for name, path in binaries.items():
                path.write_bytes(name.encode())
            expected["expected_apple_device_toolchain"].update({
                "java_sha256": hashlib.sha256(binaries["java"].read_bytes()).hexdigest(),
                "gradle_sha256": hashlib.sha256(binaries["gradle"].read_bytes()).hexdigest()})
            expected["expected_apple_device_executable_paths"] = {
                name: str(path) for name, path in binaries.items()}
            expected["expected_apple_device_executable_hashes"] = {
                name: hashlib.sha256(binaries[name].read_bytes()).hexdigest()
                for name in ("xcrun", "xcodebuild")}
            selection = {"schema": 1, "roles": {
                target: {"minimum": minimum, "current": current,
                         "minimum_source": "https://support.apple.com/100100",
                         "current_source": "https://support.apple.com/100100"}
                for target, minimum, current in (
                    ("iosArm64", "15.8.8", "26.0"),
                    ("tvosArm64", "15.6", "26.0"),
                    ("watchosArm64", "8.8.2", "26.0"),
                    ("watchosDeviceArm64", "26.6", "27.0"))}}
            os_roles = base / "os-roles.json"
            os_roles.write_text(json.dumps(selection))
            expected["expected_apple_os_roles"] = {
                "path": str(os_roles),
                "sha256": hashlib.sha256(os_roles.read_bytes()).hexdigest()}
            public = {"status": "PASSED", "selected_cases": 2523,
                      "archive_sha256": "c" * 64}
            with patch.object(full_signed_routes, "_source"), patch.object(
                    full_signed_routes, "_selected", return_value=[None] * 2523), patch(
                    "full_apple_device_consumer.verify", return_value=public):
                self.assertEqual(full_signed_routes.verify(
                    ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, "c" * 64), public)
                with self.assertRaisesRegex(ValueError, "OS role selection"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              {k: v for k, v in expected.items()
                                               if k != "expected_apple_os_roles"},
                                              HASHES, runtime, "c" * 64)
                device["version"] = "15.0"
                expected["expected_runtime_identity"] = "iPhone | iOS 15.0 | device"
                receipt["runtime_identity"] = expected["expected_runtime_identity"]
                (archive / "receipt.json").write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError, "independently selected"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive, expected,
                                              HASHES, expected["expected_runtime_identity"], "c" * 64)

    def test_additional_browser_signed_bundle_rejects_changed_route(self):
        lane = "js:Firefox:current:development"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            browser, java, gradle = (base / name for name in ("firefox", "java", "gradle"))
            for path in (browser, java, gradle):
                path.write_bytes(path.name.encode())
            runtime = "Linux test x86_64"
            receipt = self._receipt(lane, runtime)
            receipt["staged_hashes"] = dict(HASHES)
            toolchain = {"browser": str(browser), "browser_sha256": hashlib.sha256(
                browser.read_bytes()).hexdigest(), "java_home": str(base),
                "java_sha256": __import__("full_browser_consumer").JAVA_SHA256,
                "gradle": str(gradle), "gradle_sha256": __import__(
                    "full_browser_consumer").GRADLE_SHA256,
                "kgp_version": "2.4.20", "gradle_version": "9.5.0"}
            receipt["toolchain"] = toolchain
            archive = self._archive(base, receipt)
            bundles = {}
            for short in ("core", "facade"):
                folder = archive / short
                folder.mkdir()
                for name in ("karma-selected.js", "linked-executable.js"):
                    (folder / name).write_bytes(short.encode())
                selected_sha = hashlib.sha256(short.encode()).hexdigest()
                bundles[short] = {"karma_selected_js": selected_sha,
                                  "linked_executable_js": selected_sha}
            expected = {"expected_artifact_hashes": HASHES,
                        "expected_runtime_identity": runtime,
                        "expected_archive_digests": {"staged-consumer": "c" * 64},
                        "expected_browser_toolchain": toolchain,
                        "expected_browser_bundles": bundles}
            public = {"status": "PASSED", "lane": lane, "selected_cases": 2523,
                      "archive_sha256": "c" * 64, "candidate_sha": CANDIDATE}
            with patch.object(full_signed_routes, "_source"), patch.object(
                    full_signed_routes, "_file"), patch.object(
                    full_signed_routes, "_selected", return_value=[None] * 2523), patch(
                    "independent_gates.archive_digest", return_value="c" * 64), patch(
                    "full_browser_consumer.runtime_pin"), patch(
                    "full_browser_consumer.verify", return_value=public):
                self.assertEqual(full_signed_routes.verify_browser(
                    ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, "c" * 64), public)
                receipt["lane"] = "js:Firefox:minimum:development"
                (archive / "receipt.json").write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError, "browser candidate, route"):
                    full_signed_routes.verify_browser(ROOT, CANDIDATE, lane, archive,
                                                      expected, HASHES, runtime, "c" * 64)

    def test_forged_unavailability_and_changed_member_fail_closed(self):
        lane = "iosArm64:iOS physical ARM64:minimum:debug-g"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            receipt = {"schema": 1, "status": "UNAVAILABLE", "candidate_sha": CANDIDATE,
                       "lane": lane, "reason": "made up"}
            archive = self._archive(base, receipt)
            digest = independent_gates.archive_digest(archive)
            expected = {"expected_unavailability": None}
            result = independent_gates.evaluate_gate(
                "staged-consumer", archive, CANDIDATE, lane, MANIFEST["lanes"][lane],
                ROOT, HASHES, "device", digest, manifest=MANIFEST,
                expected_signed_lane=expected)
            self.assertEqual(result["status"], "FAILED")
            expected["expected_unavailability"] = receipt
            (archive / "changed.bin").write_bytes(b"changed")
            result = independent_gates.evaluate_gate(
                "staged-consumer", archive, CANDIDATE, lane, MANIFEST["lanes"][lane],
                ROOT, HASHES, "device", digest, manifest=MANIFEST,
                expected_signed_lane=expected)
            self.assertEqual(result["status"], "FAILED")

    def test_signed_native_klib_witness_rejects_changed_executable(self):
        lane = "linuxX64:Linux x64:current:optimized-opt"
        with tempfile.TemporaryDirectory() as temporary:
            expected = {}
            binaries = {"core": "d" * 64, "facade": "e" * 64}
            self._witness(Path(temporary), expected, lane, "Linux current", "optimized-opt",
                          binaries, "f" * 64)
            self.assertEqual(full_signed_routes.execution_witness(
                expected, CANDIDATE, lane, "c" * 64, "Linux current", "optimized-opt",
                binaries, HASHES, "f" * 64)["executables"], binaries)
            with self.assertRaisesRegex(ValueError, "signed route"):
                full_signed_routes.execution_witness(
                    expected, CANDIDATE, lane, "c" * 64, "Linux current",
                    "optimized-opt", {"core": "0" * 64, "facade": "e" * 64},
                    HASHES, "f" * 64)

    def test_signed_not_run_stays_not_run_and_hardlink_fails(self):
        lane = "iosArm64:iOS physical ARM64:minimum:debug-g"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            receipt = {"schema": 1, "status": "NOT_RUN", "candidate_sha": CANDIDATE,
                       "lane": lane, "reason": "no device launched"}
            archive = self._archive(base, receipt)
            digest = independent_gates.archive_digest(archive)
            expected = {"expected_not_run": receipt}
            result = independent_gates.evaluate_gate(
                "staged-consumer", archive, CANDIDATE, lane, MANIFEST["lanes"][lane],
                ROOT, HASHES, "device", digest, manifest=MANIFEST,
                expected_signed_lane=expected)
            self.assertEqual(result["status"], "NOT_RUN")
            outside = base / "outside.bin"
            outside.write_bytes(b"untrusted")
            os.link(outside, archive / "member.bin")
            result = independent_gates.evaluate_gate(
                "staged-consumer", archive, CANDIDATE, lane, MANIFEST["lanes"][lane],
                ROOT, HASHES, "device", digest, manifest=MANIFEST,
                expected_signed_lane=expected)
            self.assertEqual(result["status"], "FAILED")

    def test_retained_wasm_browser_has_distinct_signed_files_and_assets(self):
        archive = Path("/var/home/stewart/dyn4k-evidence/session-control/"
                       "full-browser-other-20-sol-wasm-chromium-current-development-attempt4")
        if not (archive / "core/selected-bundle.json").is_file():
            self.skipTest("retained Wasm browser archive is absent")
        bundles = {}
        for short in ("core", "facade"):
            folder = archive / short
            bundles[short] = {
                "karma_selected_js": hashlib.sha256(
                    (folder / "karma-selected.js").read_bytes()).hexdigest(),
                "linked_executable_js": hashlib.sha256(
                    (folder / "linked-executable.js").read_bytes()).hexdigest(),
                "linked_executable_wasm": hashlib.sha256(
                    (folder / "linked-executable.wasm").read_bytes()).hexdigest(),
                "assets": {item["name"]: item["sha256"] for item in
                           json.loads((folder / "selected-bundle.json").read_text())["assets"]}}
            self.assertNotEqual(bundles[short]["karma_selected_js"],
                                bundles[short]["linked_executable_js"])
        full_signed_routes._browser_bundle_bytes(archive, bundles, True)
        changed = json.loads(json.dumps(bundles))
        changed["core"]["linked_executable_wasm"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "browser.*bytes"):
            full_signed_routes._browser_bundle_bytes(archive, changed, True)
        changed = json.loads(json.dumps(bundles))
        name = next(iter(changed["facade"]["assets"]))
        changed["facade"]["assets"][name] = "0" * 64
        with self.assertRaisesRegex(ValueError, "browser.*bytes"):
            full_signed_routes._browser_bundle_bytes(archive, changed, True)

    def test_signed_unavailable_requires_bound_receipt_only_observation(self):
        lane = "iosArm64:iOS physical ARM64:minimum:debug-g"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            receipt = {"schema": 1, "status": "UNAVAILABLE", "candidate_sha": CANDIDATE,
                       "lane": lane, "reason": "device not attached",
                       "observed_by": "independent runner", "observed_at_ns": 123}
            archive = self._archive(base, receipt)
            def result():
                digest = independent_gates.archive_digest(archive)
                return independent_gates.evaluate_gate(
                    "staged-consumer", archive, CANDIDATE, lane, MANIFEST["lanes"][lane],
                    ROOT, HASHES, "device", digest, manifest=MANIFEST,
                    expected_signed_lane={"expected_unavailability": receipt.copy()})["status"]
            self.assertEqual(result(), "UNAVAILABLE")
            for key, bad in (("candidate_sha", "0" * 40), ("lane", "wrong-lane"),
                             ("schema", 2), ("reason", " "), ("observed_by", ""),
                             ("observed_at_ns", 0)):
                original = receipt[key]
                receipt[key] = bad
                (archive / "receipt.json").write_text(json.dumps(receipt))
                self.assertEqual(result(), "FAILED", key)
                receipt[key] = original
                (archive / "receipt.json").write_text(json.dumps(receipt))
            (archive / "extra.txt").write_text("not receipt only")
            self.assertEqual(result(), "FAILED")

    def test_browser_response_requires_independently_captured_body(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive = base / "archive"
            responses = {}
            witness = {"responses": {}, "processes": {}}
            for short in ("core", "facade"):
                folder = archive / short
                (folder / "assets").mkdir(parents=True)
                (folder / "assets/test.wasm").write_bytes(short.encode())
                (folder / "selected-bundle.json").write_text(json.dumps({
                    "browser_id": short + "-browser",
                    "assets": [{"name": "test.wasm", "sha256": hashlib.sha256(
                        short.encode()).hexdigest()}]}))
                observed = base / f"observed-{short}.wasm"
                observed.write_bytes(short.encode())
                responses[short] = [{"name": "test.wasm",
                                     "url": f"http://127.0.0.1:9876/{short}/test.wasm",
                                     "status": 200,
                                     "sha256": hashlib.sha256(short.encode()).hexdigest(),
                                     "body_path": str(observed), "observed_at_ns": 5,
                                     "browser_id": short + "-browser"}]
                witness["processes"][short] = {"started_ns": 1, "finished_ns": 10,
                                                 "pid": 123}
            witness["responses"] = json.loads(json.dumps(responses))
            full_signed_routes._browser_response_proof(archive, responses, witness)
            (base / "observed-core.wasm").unlink()
            with self.assertRaisesRegex(ValueError, "observed.*body"):
                full_signed_routes._browser_response_proof(archive, responses, witness)
            (base / "observed-core.wasm").write_bytes(b"forged")
            with self.assertRaisesRegex(ValueError, "observed.*body"):
                full_signed_routes._browser_response_proof(archive, responses, witness)
            (base / "observed-core.wasm").write_bytes(b"core")
            witness["responses"]["core"][0]["status"] = 404
            with self.assertRaisesRegex(ValueError, "independent witness"):
                full_signed_routes._browser_response_proof(archive, responses, witness)
            witness["responses"]["core"][0]["status"] = 200
            responses["core"][0]["url"] = "http://127.0.0.1:9876/core/other.wasm"
            witness["responses"]["core"][0]["url"] = responses["core"][0]["url"]
            with self.assertRaisesRegex(ValueError, "HTTP response observation"):
                full_signed_routes._browser_response_proof(archive, responses, witness)

    def test_wasm_browser_signed_route_requires_response_capture(self):
        import full_browser_consumer

        lane = "wasmJs:Chromium:current:development"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = "Linux test x86_64"
            receipt = self._receipt(lane, runtime)
            receipt["staged_hashes"] = dict(HASHES)
            toolchain = {"browser": str(base / "chromium"),
                         "browser_sha256": "d" * 64, "java_home": str(base),
                         "java_sha256": full_browser_consumer.JAVA_SHA256,
                         "gradle": str(base / "gradle"),
                         "gradle_sha256": full_browser_consumer.GRADLE_SHA256,
                         "kgp_version": "2.4.20", "gradle_version": "9.5.0"}
            receipt["toolchain"] = toolchain
            archive = self._archive(base, receipt)
            bundles, responses, executables = {}, {}, {}
            for short in ("core", "facade"):
                folder = archive / short
                (folder / "assets").mkdir(parents=True)
                files = {"karma-selected.js": (short + " selected").encode(),
                         "linked-executable.js": (short + " linked").encode(),
                         "linked-executable.wasm": (short + " wasm").encode(),
                         "assets/test.wasm": (short + " wasm").encode()}
                for name, data in files.items():
                    (folder / name).write_bytes(data)
                sha = {name: hashlib.sha256(data).hexdigest()
                       for name, data in files.items()}
                bundles[short] = {"karma_selected_js": sha["karma-selected.js"],
                                  "linked_executable_js": sha["linked-executable.js"],
                                  "linked_executable_wasm": sha["linked-executable.wasm"],
                                  "assets": {"test.wasm": sha["assets/test.wasm"]}}
                executables[short] = sha["linked-executable.js"]
                (folder / "selected-bundle.json").write_text(json.dumps({
                    "browser_id": short + "-browser",
                    "assets": [{"name": "test.wasm", "sha256": sha["assets/test.wasm"]}]}))
                body = base / f"captured-{short}.wasm"
                body.write_bytes(files["assets/test.wasm"])
                responses[short] = [{"name": "test.wasm",
                                     "url": f"http://127.0.0.1:9876/{short}/test.wasm",
                                     "status": 200, "sha256": sha["assets/test.wasm"],
                                     "body_path": str(body), "observed_at_ns": 2,
                                     "browser_id": short + "-browser"}]
            expected = {"expected_artifact_hashes": HASHES,
                        "expected_runtime_identity": runtime,
                        "expected_archive_digests": {"staged-consumer": "c" * 64},
                        "expected_browser_toolchain": toolchain,
                        "expected_browser_bundles": bundles,
                        "expected_browser_responses": responses}
            self._witness(base, expected, lane, runtime, "development", executables,
                          toolchain["gradle_sha256"])
            witness_path = Path(expected["expected_execution_witness"]["path"])
            witness = json.loads(witness_path.read_bytes())
            witness["responses"] = responses
            witness_path.write_text(json.dumps(witness))
            expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                witness_path.read_bytes()).hexdigest()
            public = {"status": "PASSED", "lane": lane, "selected_cases": 2523,
                      "archive_sha256": "c" * 64, "candidate_sha": CANDIDATE}
            with patch.object(full_signed_routes, "_source"), patch.object(
                    full_signed_routes, "_file"), patch.object(
                    full_signed_routes, "_selected", return_value=[None] * 2523), patch(
                    "independent_gates.archive_digest", return_value="c" * 64), patch(
                    "full_browser_consumer.runtime_pin"), patch(
                    "full_browser_consumer.verify", return_value=public):
                self.assertEqual(full_signed_routes.verify_browser(
                    ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, "c" * 64),
                    public)
                (base / "captured-core.wasm").unlink()
                with self.assertRaisesRegex(ValueError, "observed.*body"):
                    full_signed_routes.verify_browser(
                        ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, "c" * 64)

    def test_klib_schema2_requires_observed_lane_marker(self):
        lane = "js:Node.js:current:production"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "stdout.txt").write_text(
                "[LIFECYCLE] [org.gradle.api.Task] > Task :core:compileTestKotlinJs\n"
                "BUILD SUCCESSFUL\n")
            process = {"command": ["/tmp/gradle", lane], "stdout": "stdout.txt",
                       "exit_code": 0}
            with self.assertRaisesRegex(ValueError, "lane execution marker"):
                independent_gates._process_proof(root, process, "staged-consumer", lane,
                                                 {"schema": 2})
            (root / "stdout.txt").write_text(
                f"[QUIET] [system.out] QUALIFICATION_LANE={lane}\n"
                "[LIFECYCLE] [org.gradle.api.Task] > Task :core:compileTestKotlinJs\n"
                "BUILD SUCCESSFUL\n")
            self.assertEqual(independent_gates._process_proof(
                root, process, "staged-consumer", lane, {"schema": 2}), "gradle")

    def test_retained_klib_schema2_raw_archive_reaches_public_boundary(self):
        archive = Path("/var/home/stewart/dyn4k-evidence/session-control/"
                       "full-klib-27f-repair-sol-js-production-6f8e051d-transported")
        if not (archive / "receipt.json").is_file():
            self.skipTest("retained KLIB archive is absent")
        receipt = json.loads((archive / "receipt.json").read_bytes())
        lane = receipt["lane"]
        digest = independent_gates.archive_digest(archive)
        result = independent_gates.evaluate_gate(
            "staged-consumer", archive, receipt["candidate_sha"], lane,
            MANIFEST["lanes"][lane], ROOT, receipt["artifact_hashes"],
            receipt["runtime_identity"], digest, manifest=MANIFEST)
        self.assertEqual(result["status"], "PASSED", result["reason"])
        self.assertEqual(result["selected_cases"], 2523)


if __name__ == "__main__":
    unittest.main()
