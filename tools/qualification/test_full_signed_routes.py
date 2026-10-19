import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import full_browser_consumer
import full_native_host_consumer
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

    def _http_fixture(self, archive, wasm):
        responses, modules = {}, {}
        for short in ("core", "facade"):
            folder = archive / short
            (folder / "http-sources").mkdir(parents=True)
            (folder / "http-responses").mkdir()
            package = f"dyn4k-full-staged-browser-consumer-{short}-test"
            emitted = "0123456789abcdefabcd.wasm"
            names = ["commons.js", "kotlin-test-karma-runner.123.js", "runtime.js",
                     f"{'load' if wasm else package}.456.js"]
            if wasm:
                names.append(emitted)
            generated = []
            for name in sorted(names):
                data = (short + name).encode()
                (folder / "http-sources" / name).write_bytes(data)
                generated.append({"name": name,
                                  "source_path": f"/tmp/webpack/{short}/{name}",
                                  "size": len(data),
                                  "sha256": hashlib.sha256(data).hexdigest()})
            assets = []
            if wasm:
                (folder / "assets").mkdir()
                data = (short + emitted).encode()
                asset = f"{package}.wasm"
                (folder / "assets" / asset).write_bytes(data)
                (folder / "linked-executable.wasm").write_bytes(data)
                assets = [{"name": asset, "sha256": hashlib.sha256(data).hexdigest()}]
            selected = {"browser_id": short + "-browser", "browser_name": "Chromium",
                        "node_pid": 123, "captured_ns": 17, "complete_ns": 20,
                        "effective_files": [{"pattern": f"/tmp/webpack/{short}/runtime.js"}],
                        "generated": generated}
            if wasm:
                selected["assets"] = assets
            (folder / "selected-bundle.json").write_text(json.dumps(selected))
            observed = []
            for index, name in enumerate(["runtime.js", "commons.js"] +
                                         ([emitted] if wasm else [])):
                data = (short + name).encode()
                (folder / "http-responses" / f"{index:04d}.body").write_bytes(data)
                observed.append({"ordinal": index, "name": name,
                                 "url": f"/absolute/tmp/webpack/{short}/{name}?hash",
                                 "method": "GET", "started_ns": 12 + index,
                                 "finished_ns": 13 + index, "status": 200,
                                 "content_encoding": None, "range": None,
                                 "size": len(data),
                                 "sha256": hashlib.sha256(data).hexdigest(),
                                 "body_path": f"http-responses/{index:04d}.body"})
            responses[short] = {key: selected[key] for key in
                                ("browser_id", "browser_name", "node_pid",
                                 "captured_ns", "complete_ns", "generated")}
            responses[short]["responses"] = observed
            (folder / "http-responses.json").write_text(json.dumps(responses[short]))
            modules[short] = {"started_ns": 10, "finished_ns": 25}
        return responses, {"schema": 3, "modules": modules}

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
                    "full_native_host_consumer.verify_cross_run",
                    side_effect=AssertionError("ordinary route used cross verifier")), patch(
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

    def test_native_cross_run_signed_build_and_execution_route(self):
        lane = "linuxArm64:Linux ARM64:current:debug-g"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            paths = {name: base / relative for name, relative in (
                ("gradle", "gradle"), ("python", "python"),
                ("java", "jdk/bin/java"), ("native", "native/bin/kotlinc-native"),
                ("compiler", "native/konan/lib/kotlin-native-compiler-embeddable.jar"))}
            for name, path in paths.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            toolchain = {"gradle_executable": str(paths["gradle"]),
                         "gradle_sha256": hashlib.sha256(paths["gradle"].read_bytes()).hexdigest(),
                         "gradle_version": "Gradle 9.5.0", "kgp_version": "2.4.20",
                         "python_executable": str(paths["python"]),
                         "python_sha256": hashlib.sha256(paths["python"].read_bytes()).hexdigest(),
                         "java_home": str(paths["java"].parent.parent),
                         "java_version": 'openjdk version "21.0.12"',
                         "java_sha256": hashlib.sha256(paths["java"].read_bytes()).hexdigest(),
                         "native_home": str(base / "native"),
                         "native_version": "Kotlin/Native: 2.4.20",
                         "native_sha256": hashlib.sha256(paths["native"].read_bytes()).hexdigest(),
                         "native_compiler_sha256": hashlib.sha256(
                             paths["compiler"].read_bytes()).hexdigest()}
            selection = {"lane": lane, "role": "current", "system": "Linux",
                         "machine": "aarch64", "os_version": "6.17.0", "libc": "2.39"}
            host = {key: value for key, value in selection.items()
                    if key not in ("lane", "role")}
            build_host = {"system": "Linux", "machine": "x86_64"}
            runtime = full_native_host_consumer.digest(
                full_native_host_consumer.encoded(host))
            archive = base / "archive"
            build = archive / "build"
            (build / "runtime").mkdir(parents=True)
            products = {}
            executables = {}
            for short in ("core", "facade"):
                binary = build / "runtime" / f"{short}.program"
                binary.write_bytes(short.encode())
                sha = hashlib.sha256(binary.read_bytes()).hexdigest()
                products[short] = {"archive": f"runtime/{short}.program", "sha256": sha,
                                   "mode": "debugTest", "elf_class": 64,
                                   "elf_machine": "AArch64"}
                executables[short] = sha
            contract_sha = independent_gates.digest(
                independent_gates.consumer_contract(MANIFEST, lane))
            build_receipt = {"schema": 2, "status": "COMPILED_ONLY",
                             "phase": "linux-x64-cross-build", "candidate_sha": CANDIDATE,
                             "lane": lane, "source_tree": "e" * 40,
                             "consumer_contract_sha256": contract_sha,
                             "artifact_hashes": HASHES,
                             "artifact_hash_provenance": "audited",
                             "build_host": build_host, "toolchain": toolchain,
                             "products": products, "selected_cases": 2523}
            (build / "receipt.json").write_text(json.dumps(build_receipt))
            build_digest = independent_gates.archive_digest(build)
            methods = [case["id"] for case in
                       independent_gates.consumer_contract(MANIFEST, lane)["cases"]]
            receipt = {"schema": 3, "status": "PASSED", "candidate_sha": CANDIDATE,
                       "lane": lane, "source_tree": "e" * 40,
                       "artifact_hashes": HASHES, "artifact_hash_provenance": "audited",
                       "build_archive_sha256": build_digest, "build_host": build_host,
                       "runtime_host": host, "runtime_host_after": host,
                       "selection": selection, "selected_cases": 2523,
                       "method_order": methods,
                       "processes": {short: {"exit_code": 0,
                                             "observed_process": {"pid": index + 1}}
                                     for index, short in enumerate(("core", "facade"))}}
            (archive / "receipt.json").write_text(json.dumps(receipt))
            digest = independent_gates.archive_digest(archive)
            expected = {"expected_artifact_hashes": HASHES,
                        "expected_runtime_identity": runtime,
                        "expected_archive_digests": {"staged-consumer": digest},
                        "expected_native_selection": selection,
                        "expected_native_host": host,
                        "expected_native_build_host": build_host,
                        "expected_native_toolchain": toolchain,
                        "expected_native_build_archive_sha256": build_digest,
                        "expected_native_build_executables": executables}
            public = {"status": "PASSED", "lane": lane, "candidate_sha": CANDIDATE,
                      "archive_sha256": digest, "selected_cases": 2523,
                      "artifact_hash_provenance": "audited",
                      "complete_selected_suite": True}
            for path in paths.values():
                path.unlink()
            with patch.object(full_signed_routes, "_source"), patch(
                    "full_native_host_consumer.verify", side_effect=AssertionError(
                        "cross route used ordinary verifier")), patch(
                    "full_native_host_consumer.verify_cross_run", return_value=public) as cross_verify:
                self.assertEqual(full_signed_routes.verify(
                    ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, digest), public)
                cross_verify.assert_called_once_with(
                    archive, ROOT, CANDIDATE, lane, HASHES, selection, digest,
                    build_digest, toolchain)
                cross_verify.return_value = {**public, "complete_selected_suite": False}
                with self.assertRaisesRegex(ValueError, "public replay differs"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                cross_verify.return_value = public
                expected["expected_native_build_archive_sha256"] = "0" * 64
                with self.assertRaisesRegex(ValueError, "cross build archive"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                expected["expected_native_build_archive_sha256"] = build_digest
                expected["expected_native_host"] = {**host, "machine": "x86_64"}
                with self.assertRaisesRegex(ValueError, "cross runtime host"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                expected["expected_native_host"] = host
                expected["expected_native_build_host"] = {**build_host,
                                                          "machine": "aarch64"}
                with self.assertRaisesRegex(ValueError, "cross runtime host"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                expected["expected_native_build_host"] = build_host
                expected["expected_native_toolchain"] = {**toolchain,
                                                         "java_sha256": "0" * 64}
                with self.assertRaisesRegex(ValueError, "cross build toolchain"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                expected["expected_native_toolchain"] = toolchain
                expected["expected_native_build_executables"] = {**executables,
                                                                  "core": "0" * 64}
                with self.assertRaisesRegex(ValueError, "cross build executable"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                expected["expected_native_build_executables"] = executables
                receipt["method_order"] = []
                (archive / "receipt.json").write_text(json.dumps(receipt))
                digest = independent_gates.archive_digest(archive)
                expected["expected_archive_digests"]["staged-consumer"] = digest
                with self.assertRaisesRegex(ValueError, "cross runtime execution"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                receipt["method_order"] = methods
                (build / "runtime/core.program").write_bytes(b"changed")
                (archive / "receipt.json").write_text(json.dumps(receipt))
                digest = independent_gates.archive_digest(archive)
                expected["expected_archive_digests"]["staged-consumer"] = digest
                with self.assertRaisesRegex(ValueError, "cross build archive"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                self.assertEqual(cross_verify.call_count, 2)

    def test_windows_native_host_uses_signed_windows_toolchain_files(self):
        lane = "mingwX64:Windows x64:current:debug-g"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            binaries = {
                "gradle": base / "gradle",
                "python": base / "python",
                "java": base / "jdk/bin/java.exe",
                "native": base / "native/bin/kotlinc-native.bat",
                "compiler": base / "native/konan/lib/kotlin-native-compiler-embeddable.jar",
            }
            for name, path in binaries.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            self.assertFalse((base / "jdk/bin/java").exists())
            self.assertFalse((base / "native/bin/kotlinc-native").exists())
            toolchain = {"gradle_executable": str(binaries["gradle"]),
                         "gradle_sha256": hashlib.sha256(binaries["gradle"].read_bytes()).hexdigest(),
                         "python_executable": str(binaries["python"]),
                         "python_sha256": hashlib.sha256(binaries["python"].read_bytes()).hexdigest(),
                         "java_home": str(base / "jdk"),
                         "java_sha256": hashlib.sha256(binaries["java"].read_bytes()).hexdigest(),
                         "native_home": str(base / "native"),
                         "native_sha256": hashlib.sha256(binaries["native"].read_bytes()).hexdigest(),
                         "native_compiler_sha256": hashlib.sha256(
                             binaries["compiler"].read_bytes()).hexdigest()}
            selection = {"lane": lane, "role": "current", "system": "Windows",
                         "machine": "AMD64", "os_version": "10.0.26100",
                         "windows_product_type": "client",
                         "windows_product_name": "Windows 11 Pro"}
            host = {key: value for key, value in selection.items()
                    if key not in ("lane", "role")}
            runtime = full_native_host_consumer.digest(
                full_native_host_consumer.encoded(host))
            receipt = self._receipt(lane, runtime)
            receipt["host"] = host
            archive = self._archive(base, receipt)
            expected = {"expected_artifact_hashes": HASHES,
                        "expected_runtime_identity": runtime,
                        "expected_archive_digests": {"staged-consumer": "c" * 64},
                        "expected_native_selection": selection,
                        "expected_native_toolchain": toolchain,
                        "expected_native_host": host}
            products = {"core": {"sha256": "d" * 64},
                        "facade": {"sha256": "e" * 64}}
            (archive / "runtime").mkdir()
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
                    "full_native_host_consumer.verify", return_value=public):
                self.assertEqual(full_signed_routes.verify(
                    ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, "c" * 64), public)
                toolchain["native_sha256"] = "0" * 64
                with self.assertRaisesRegex(ValueError, "Kotlin Native compiler.*bytes differ"):
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
                archived_roles = archive / "os-roles.json"
                archived_roles.write_bytes(os_roles.read_bytes())
                with self.assertRaisesRegex(ValueError, "outside the producer archive"):
                    full_signed_routes.verify(
                        ROOT, CANDIDATE, lane, archive,
                        expected | {"expected_apple_os_roles":
                                    {"path": str(archived_roles),
                                     "sha256": expected["expected_apple_os_roles"]["sha256"]}},
                        HASHES, runtime, "c" * 64)
                alias = base / "parent-alias"
                alias.symlink_to(base, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "symbolic paths"):
                    full_signed_routes.verify(
                        ROOT, CANDIDATE, lane, archive,
                        expected | {"expected_apple_os_roles":
                                    {"path": str(alias / os_roles.name),
                                     "sha256": expected["expected_apple_os_roles"]["sha256"]}},
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

    def test_safari_schema2_receipt_accepts_darwin_jdk_and_rejects_wrong_host(self):
        lane = "js:Safari:current:development"
        runtime = "Darwin 25.5.0 arm64"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            browser = base / "Safari"
            java = base / "jdk/bin/java"
            gradle = base / "gradle"
            for path in (browser, java, gradle):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(path.name.encode())
            toolchain = {"browser": str(browser),
                         "browser_sha256": hashlib.sha256(browser.read_bytes()).hexdigest(),
                         "java_home": str(java.parent.parent),
                         "java_sha256": full_browser_consumer.DARWIN_JAVA_SHA256,
                         "gradle": str(gradle),
                         "gradle_sha256": full_browser_consumer.GRADLE_SHA256,
                         "kgp_version": "2.4.20", "gradle_version": "9.5.0"}
            receipt = {"schema": 2, "status": "PASSED", "candidate_sha": CANDIDATE,
                       "lane": lane, "consumer_contract_sha256": independent_gates.digest(
                           independent_gates.consumer_contract(MANIFEST, lane)),
                       "source_tree": "e" * 40,
                       "source_inventory_sha256": "f" * 64,
                       "consumer_build_sha256": {}, "producer_sha256": "f" * 64,
                       "browser_support_sha256": {},
                       "staged_hashes": dict(HASHES), "runtime_identity": runtime,
                       "toolchain": toolchain, "paths": {}, "process": {},
                       "modules": {}, "lock_observations": {},
                       "row_order_sha256": {}, "files": []}
            self.assertTrue({"target", "runtime", "version", "configuration"}.isdisjoint(receipt))
            archive = self._archive(base, receipt)
            bundles = {}
            for short in ("core", "facade"):
                folder = archive / short
                folder.mkdir()
                (folder / "karma-selected.js").write_bytes(short.encode())
                (folder / "linked-executable.js").write_bytes(short.encode())
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
            self.assertEqual(full_browser_consumer.expected_java_sha256("Darwin", "Safari"),
                             full_browser_consumer.DARWIN_JAVA_SHA256)
            with self.assertRaisesRegex(ValueError, "JDK 21.*bytes differ"):
                full_signed_routes._file(java, toolchain["java_sha256"], "JDK 21")
            with patch.object(full_signed_routes, "_source"), patch.object(
                    full_signed_routes, "_selected", return_value=[None] * 2523), patch.object(
                    full_signed_routes, "_file", side_effect=lambda path, sha, label: Path(path)
                    ) as file_check, patch(
                    "independent_gates.archive_digest", return_value="c" * 64), patch(
                    "full_browser_consumer.runtime_pin"), patch(
                    "full_browser_consumer.verify", return_value=public) as producer_verify:
                self.assertEqual(full_signed_routes.verify_browser(
                    ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, "c" * 64),
                    public)
                file_check.assert_any_call(java, full_browser_consumer.DARWIN_JAVA_SHA256,
                                           "JDK 21")
                producer_verify.assert_called_once()
                toolchain["java_sha256"] = full_browser_consumer.JAVA_SHA256
                receipt["toolchain"] = toolchain
                (archive / "receipt.json").write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError, "browser JDK or Gradle"):
                    full_signed_routes.verify_browser(ROOT, CANDIDATE, lane, archive,
                                                      expected, HASHES, runtime, "c" * 64)
                toolchain["java_sha256"] = full_browser_consumer.DARWIN_JAVA_SHA256
                receipt["runtime_identity"] = "Linux 6.17.0 x86_64"
                expected["expected_runtime_identity"] = receipt["runtime_identity"]
                (archive / "receipt.json").write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError, "selected browser host differs"):
                    full_signed_routes.verify_browser(ROOT, CANDIDATE, lane, archive,
                                                      expected, HASHES, receipt["runtime_identity"],
                                                      "c" * 64)
                receipt["runtime_identity"] = runtime
                receipt["consumer_contract_sha256"] = "0" * 64
                expected["expected_runtime_identity"] = runtime
                (archive / "receipt.json").write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError, "browser candidate, route"):
                    full_signed_routes.verify_browser(ROOT, CANDIDATE, lane, archive,
                                                      expected, HASHES, runtime, "c" * 64)
                producer_verify.assert_called_once()

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

    def test_browser_http_generated_responses_bind_order_source_and_body(self):
        for wasm in (False, True):
            with self.subTest(wasm=wasm), tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / "archive"
                responses, receipt = self._http_fixture(archive, wasm)
                witness = {"responses": json.loads(json.dumps(responses))}
                check = lambda: full_signed_routes._browser_response_proof(
                    archive, responses, witness, receipt, wasm)
                check()
                body = archive / "core/http-responses/0000.body"
                body.write_bytes(b"forged")
                with self.assertRaisesRegex(ValueError, "response body.*bytes differ"):
                    check()
                body.write_bytes(b"coreruntime.js")
                witness["responses"]["core"]["responses"][0]["status"] = 404
                with self.assertRaisesRegex(ValueError, "signed witness"):
                    check()
                witness["responses"] = json.loads(json.dumps(responses))
                original = responses["core"]["responses"][0]["ordinal"]
                responses["core"]["responses"][0]["ordinal"] = 1
                witness["responses"] = json.loads(json.dumps(responses))
                (archive / "core/http-responses.json").write_text(json.dumps(responses["core"]))
                with self.assertRaisesRegex(ValueError, "response order"):
                    check()
                responses["core"]["responses"][0]["ordinal"] = original
                witness["responses"] = json.loads(json.dumps(responses))
                (archive / "core/http-responses.json").write_text(json.dumps(responses["core"]))
                receipt["modules"]["core"]["started_ns"] = 13
                with self.assertRaisesRegex(ValueError, "response order"):
                    check()
                receipt["modules"]["core"]["started_ns"] = 10
                generated = responses["core"]["generated"]
                generated[0]["source_path"] = "/tmp/wrong/commons.js"
                witness["responses"] = json.loads(json.dumps(responses))
                (archive / "core/http-responses.json").write_text(json.dumps(responses["core"]))
                selected = json.loads((archive / "core/selected-bundle.json").read_text())
                selected["generated"] = generated
                (archive / "core/selected-bundle.json").write_text(json.dumps(selected))
                with self.assertRaisesRegex(ValueError, "generated source bytes or mapping"):
                    check()

    def test_schema4_response_proof_binds_generated_js_and_wasm_bytes(self):
        for wasm in (False, True):
            with self.subTest(wasm=wasm), tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / "archive"
                responses, receipt = self._http_fixture(archive, wasm)
                receipt["schema"] = 4
                witness = {"responses": json.loads(json.dumps(responses))}
                check = lambda: full_signed_routes._browser_response_proof(
                    archive, responses, witness, receipt, wasm)
                check()
                generated = archive / "core/http-sources/runtime.js"
                generated.write_bytes(b"changed generated JS")
                with self.assertRaisesRegex(ValueError, "generated source.*bytes differ"):
                    check()
                generated.write_bytes(b"coreruntime.js")
                if wasm:
                    selected = archive / "facade/assets/dyn4k-full-staged-browser-consumer-facade-test.wasm"
                    selected.write_bytes(b"changed Wasm")
                    with self.assertRaisesRegex(ValueError, "selected Wasm.*bytes differ"):
                        check()

    def test_retained_a14_schema4_response_shape_is_historical_only(self):
        root = Path("/var/home/stewart/dyn4k-evidence/root-browser-cdp-a14")
        if not (root / "js-relocated/receipt.json").is_file():
            self.skipTest("retained a14 Chromium archive is absent")
        for name, wasm in (("js-relocated", False), ("wasm-relocated", True)):
            with self.subTest(name=name):
                archive = root / name
                receipt = json.loads((archive / "receipt.json").read_text())
                self.assertEqual("a14af70bd252d18149dac011074af1c08ccfe791",
                                 receipt["candidate_sha"])
                self.assertEqual(4, receipt["schema"])
                responses = {short: json.loads((archive / short / "http-responses.json").read_text())
                             for short in ("core", "facade")}
                full_signed_routes._browser_response_proof(
                    archive, responses, {"responses": responses}, receipt, wasm)

    def test_retained_a14_schema4_archive_rejects_current_source_and_commit(self):
        archive = Path("/var/home/stewart/dyn4k-evidence/root-browser-cdp-a14/js-relocated")
        if not (archive / "receipt.json").is_file():
            self.skipTest("retained a14 Chromium archive is absent")
        receipt = json.loads((archive / "receipt.json").read_text())
        digest = independent_gates.archive_digest(archive)
        expected = {"expected_artifact_hashes": receipt["staged_hashes"],
                    "expected_runtime_identity": receipt["runtime_identity"],
                    "expected_archive_digests": {"staged-consumer": digest},
                    "expected_browser_toolchain": receipt["toolchain"],
                    "expected_browser_bundles": {"core": {}, "facade": {}}}
        with self.assertRaisesRegex(ValueError, "public producer or central verifier absent"):
            full_signed_routes.verify_browser(
                ROOT, receipt["candidate_sha"], receipt["lane"], archive, expected,
                receipt["staged_hashes"], receipt["runtime_identity"], digest)
        current = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        with (patch.object(full_signed_routes, "_source"),
              patch.object(full_signed_routes, "_browser_observer_source")):
            with self.assertRaisesRegex(ValueError, "browser candidate"):
                full_signed_routes.verify_browser(
                    ROOT, current, receipt["lane"], archive, expected,
                    receipt["staged_hashes"], receipt["runtime_identity"], digest)

    def test_schema4_signed_public_route_requires_external_browser_body(self):
        for target in ("js", "wasmJs"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                lane = f"{target}:Chromium:current:development"
                runtime = "Linux test x86_64"
                toolchain = {"browser": str(base / "chromium"), "browser_sha256": "d" * 64,
                             "java_home": str(base),
                             "java_sha256": full_browser_consumer.JAVA_SHA256,
                             "gradle": str(base / "gradle"),
                             "gradle_sha256": full_browser_consumer.GRADLE_SHA256,
                             "kgp_version": "2.4.20", "gradle_version": "9.5.0"}
                receipt = self._receipt(lane, runtime)
                receipt.update({"schema": 4, "staged_hashes": dict(HASHES),
                                "toolchain": toolchain})
                archive = self._archive(base, receipt)
                responses, http_receipt = self._http_fixture(archive, target == "wasmJs")
                receipt["modules"] = http_receipt["modules"]
                (archive / "receipt.json").write_text(json.dumps(receipt))
                bundles, observed = {}, {}
                for index, short in enumerate(("core", "facade")):
                    folder = archive / short
                    selected = (short + " selected").encode()
                    linked = (short + " linked").encode()
                    (folder / "karma-selected.js").write_bytes(selected)
                    (folder / "linked-executable.js").write_bytes(linked)
                    bundles[short] = {"karma_selected_js": hashlib.sha256(selected).hexdigest(),
                                      "linked_executable_js": hashlib.sha256(linked).hexdigest()}
                    if target == "wasmJs":
                        wasm = (folder / "linked-executable.wasm").read_bytes()
                        bundles[short]["linked_executable_wasm"] = hashlib.sha256(wasm).hexdigest()
                        selected_bundle = json.loads((folder / "selected-bundle.json").read_text())
                        bundles[short]["assets"] = {item["name"]: item["sha256"]
                                                    for item in selected_bundle["assets"]}
                    pid = 100 + index
                    (folder / "browser-launches.jsonl").write_text(json.dumps({
                        "pid": pid, "process_sha256": "d" * 64}) + "\n")
                    rows = [{"kind": "session", "browser_pid": pid,
                             "cdp_browser_pid": pid, "target_id": short, "started_ns": 11}]
                    consumed = []
                    for item in responses[short]["responses"]:
                        request_ns = item["started_ns"] - 1
                        response_ns = item["started_ns"] + 1
                        finished_ns = item["finished_ns"] + 1
                        rows.append({"url": f"http://127.0.0.1:9876{item['url']}",
                                     "browser_pid": pid, "target_id": short,
                                     "request_ns": request_ns, "response_ns": response_ns,
                                     "finished_ns": finished_ns,
                                     "body_sha256": item["sha256"], "body_size": item["size"]})
                        consumed.append({"url": item["url"], "body_sha256": item["sha256"],
                                         "size": item["size"], "request_ns": request_ns,
                                         "response_ns": response_ns, "finished_ns": finished_ns})
                    (folder / "chromium-cdp.jsonl").write_text(
                        "\n".join(json.dumps(row) for row in rows) + "\n")
                    observed[short] = {"protocol": "cdp", "clock": "unix-epoch-ns",
                                       "browser_pid": pid, "browser_sha256": "d" * 64,
                                       "started_ns": 11, "finished_ns": 24,
                                       "responses": consumed}
                expected = {"expected_artifact_hashes": HASHES,
                            "expected_runtime_identity": runtime,
                            "expected_archive_digests": {"staged-consumer": "c" * 64},
                            "expected_browser_toolchain": toolchain,
                            "expected_browser_bundles": bundles,
                            "expected_browser_responses": responses}
                witness = {"schema": "independent-browser-execution-witness/1",
                           "candidate_sha": CANDIDATE, "lane": lane,
                           "archive_sha256": "c" * 64, "runtime_identity": runtime,
                           "mode": "development", "staged_artifacts": HASHES,
                           "browser_sha256": "d" * 64,
                           "observer_source_sha256": hashlib.sha256(
                               (ROOT / "tools/qualification/independent_browser_observer.js")
                               .read_bytes()).hexdigest(),
                           "auditor": "independent test key", "responses": responses,
                           "browser_consumption": observed}
                witness_path = base / "witness.json"
                def sign():
                    witness_path.write_text(json.dumps(witness))
                    expected["expected_execution_witness"] = {
                        "path": str(witness_path),
                        "sha256": hashlib.sha256(witness_path.read_bytes()).hexdigest()}
                sign()
                public = {"status": "PASSED", "lane": lane, "selected_cases": 2523,
                          "archive_sha256": "c" * 64, "candidate_sha": CANDIDATE}
                actual_file = full_signed_routes._file
                with (patch.object(full_signed_routes, "_source"),
                      patch.object(full_signed_routes, "_browser_observer_source"),
                      patch.object(full_signed_routes, "_file", side_effect=
                          lambda path, sha, label: Path(path) if label in
                          ("browser", "JDK 21", "Gradle") else actual_file(path, sha, label)),
                      patch.object(full_signed_routes, "_selected", return_value=[None] * 2523),
                      patch("independent_gates.archive_digest", return_value="c" * 64),
                      patch("full_browser_consumer.runtime_pin"),
                      patch("full_browser_consumer.verify", return_value=public)):
                    self.assertEqual(full_signed_routes.verify_browser(
                        ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime,
                        "c" * 64), public)
                    for field, changed in (("candidate_sha", "0" * 40),
                                           ("lane", "wrong-lane"),
                                           ("archive_sha256", "0" * 64),
                                           ("runtime_identity", "Darwin wrong arm64"),
                                           ("browser_sha256", "0" * 64),
                                           ("observer_source_sha256", "0" * 64)):
                        with self.subTest(field=field):
                            original = witness[field]
                            witness[field] = changed
                            sign()
                            with self.assertRaisesRegex(ValueError, "execution witness differs"):
                                full_signed_routes.verify_browser(
                                    ROOT, CANDIDATE, lane, archive, expected, HASHES,
                                    runtime, "c" * 64)
                            witness[field] = original
                    sign()
                    witness["browser_consumption"]["core"]["responses"][0][
                        "body_sha256"] = "0" * 64
                    sign()
                    with self.assertRaisesRegex(ValueError, "independent browser response"):
                        full_signed_routes.verify_browser(
                            ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime,
                            "c" * 64)

    def test_wasm_browser_signed_route_requires_response_capture(self):
        import full_browser_consumer

        lane = "wasmJs:Chromium:current:development"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = "Linux test x86_64"
            receipt = self._receipt(lane, runtime)
            receipt["schema"] = 3
            for key in ("consumer_group", "target", "runtime", "version", "configuration"):
                receipt.pop(key)
            receipt["staged_hashes"] = dict(HASHES)
            toolchain = {"browser": str(base / "chromium"),
                         "browser_sha256": "d" * 64, "java_home": str(base),
                         "java_sha256": full_browser_consumer.JAVA_SHA256,
                         "gradle": str(base / "gradle"),
                         "gradle_sha256": full_browser_consumer.GRADLE_SHA256,
                         "kgp_version": "2.4.20", "gradle_version": "9.5.0"}
            receipt["toolchain"] = toolchain
            archive = self._archive(base, receipt)
            responses, http_receipt = self._http_fixture(archive, True)
            receipt["modules"] = http_receipt["modules"]
            (archive / "receipt.json").write_text(json.dumps(receipt))
            bundles, executables = {}, {}
            for short in ("core", "facade"):
                folder = archive / short
                files = {"karma-selected.js": (short + " selected").encode(),
                         "linked-executable.js": (short + " linked").encode(),
                         "linked-executable.wasm": (short +
                             "0123456789abcdefabcd.wasm").encode()}
                for name, data in files.items():
                    (folder / name).write_bytes(data)
                sha = {name: hashlib.sha256(data).hexdigest()
                       for name, data in files.items()}
                bundles[short] = {"karma_selected_js": sha["karma-selected.js"],
                                  "linked_executable_js": sha["linked-executable.js"],
                                  "linked_executable_wasm": sha["linked-executable.wasm"],
                                  "assets": {item["name"]: item["sha256"] for item in
                                             json.loads((folder / "selected-bundle.json")
                                                        .read_text())["assets"]}}
                executables[short] = sha["linked-executable.js"]
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
            actual_file = full_signed_routes._file
            with patch.object(full_signed_routes, "_source") as source_check, patch.object(
                    full_signed_routes, "_file", side_effect=lambda path, sha, label:
                    Path(path) if label in ("browser", "JDK 21", "Gradle") else
                    actual_file(path, sha, label)), patch.object(
                    full_signed_routes, "_selected", return_value=[None] * 2523), patch(
                    "independent_gates.archive_digest", return_value="c" * 64), patch(
                    "full_browser_consumer.runtime_pin"), patch(
                    "full_browser_consumer.verify", return_value=public):
                self.assertEqual(full_signed_routes.verify_browser(
                    ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, "c" * 64),
                    public)
                source_check.assert_called_once_with(ROOT, CANDIDATE, "browser")
                signed_witness = expected.pop("expected_execution_witness")
                with self.assertRaisesRegex(ValueError, "witness"):
                    full_signed_routes.verify_browser(
                        ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, "c" * 64)
                expected["expected_execution_witness"] = signed_witness
                (archive / "core/http-responses/0000.body").unlink()
                with self.assertRaisesRegex(ValueError, "response body"):
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
