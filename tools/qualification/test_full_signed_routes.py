import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import py_compile
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import full_browser_consumer
import full_native_host_consumer
import full_signed_routes
import independent_audit_producer
import independent_gates
import independent_linux_observer
import qualify


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = independent_gates.load_approved_manifest(ROOT)
HASHES = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
CANDIDATE = "9cd6868512836a3eb8192d9abc387427705e94b4"


class SignedRouteTests(unittest.TestCase):
    def _small_observer_capture(self, base):
        archive = base / "observer-archive.bin"
        archive.write_bytes(b"source control")
        output = base / "observer-capture"
        args = argparse.Namespace(candidate_sha=CANDIDATE, lane="local:source:control",
            runtime_identity="local", mode="debug", archive=str(archive),
            build_executable="/usr/bin/true", launcher_script=None,
            build_only=True, build_argv_contains=[], artifact=[], expect=[],
            generated_expect=[], timeout=20, output=str(output),
            max_processes=256, max_events=4096, max_log_bytes=8 * 1024 * 1024,
            argv=["/usr/bin/true"])
        independent_linux_observer.capture(args)
        return output

    def test_native_cross_executes_exact_candidate_observer_source(self):
        path = Path(independent_linux_observer.__file__).resolve()
        current = path.read_bytes()
        with patch.object(full_signed_routes.subprocess, "check_output",
                          return_value=current):
            verifier = full_signed_routes._observer_source(ROOT, CANDIDATE)
        self.assertIsNot(verifier, independent_linux_observer.verify)
        self.assertEqual(Path(verifier.__code__.co_filename).resolve(), path)
        with tempfile.TemporaryDirectory() as temporary:
            capture = self._small_observer_capture(Path(temporary))
            self.assertEqual(verifier(capture)["status"], "OBSERVED_UNSIGNED")
            alternate = {}
            exec(compile("def verify(*args, **kwargs): return {'status': 'FORGED'}",
                         str(path), "exec"), alternate)
            with patch.object(independent_linux_observer, "verify", alternate["verify"]):
                with patch.object(full_signed_routes.subprocess, "check_output",
                                  return_value=current):
                    verifier = full_signed_routes._observer_source(ROOT, CANDIDATE)
                self.assertEqual(verifier(capture)["status"], "OBSERVED_UNSIGNED")
                self.assertEqual(independent_linux_observer.verify(capture)["status"],
                                 "FORGED")
            shadow = SimpleNamespace(__file__=str(Path(temporary) / path.name),
                __spec__=SimpleNamespace(origin=str(Path(temporary) / path.name)),
                verify=alternate["verify"])
            with patch.dict(sys.modules, {"independent_linux_observer": shadow}), patch.object(
                    full_signed_routes.subprocess, "check_output", return_value=current):
                verifier = full_signed_routes._observer_source(ROOT, CANDIDATE)
                self.assertEqual(verifier(capture)["status"], "OBSERVED_UNSIGNED")
        with patch.object(full_signed_routes.subprocess, "check_output",
                          return_value=current + b"\n"):
            with self.assertRaisesRegex(ValueError, "observer source differs"):
                full_signed_routes._observer_source(ROOT, CANDIDATE)

    def test_native_cross_ignores_altered_timestamp_observer_cache(self):
        current = Path(independent_linux_observer.__file__).read_bytes()
        altered = current.replace(b"if witness != reconstructed:",
                                  b"if witness == reconstructed:", 1)
        self.assertNotEqual(altered, current)
        self.assertEqual(len(altered), len(current))
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            source = repository / "tools/qualification/independent_linux_observer.py"
            source.parent.mkdir(parents=True)
            source.write_bytes(altered)
            original = source.stat()
            py_compile.compile(str(source), doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
            source.write_bytes(current)
            os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
            spec = importlib.util.spec_from_file_location("cached_observer_control", source)
            cached = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cached)
            self.assertEqual(source.read_bytes(), current)
            self.assertEqual(Path(cached.__file__).resolve(), source)
            self.assertEqual(Path(cached.verify.__code__.co_filename).resolve(), source)
            with patch.object(full_signed_routes.subprocess, "check_output",
                              return_value=current):
                verifier = full_signed_routes._observer_source(repository, CANDIDATE)
            self.assertNotEqual(cached.verify.__code__.co_code,
                                verifier.__code__.co_code)
            retained = self._small_observer_capture(repository)
            with self.assertRaisesRegex(ValueError, "witness differs"):
                cached.verify(retained)
            self.assertEqual(verifier(retained)["status"], "OBSERVED_UNSIGNED")

    def test_native_cross_rejects_observed_alternate_java_with_forged_argv(self):
        java = Path("/home/linuxbrew/.linuxbrew/opt/openjdk@21/bin/java")
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            alternate = base / "alternate-jdk/bin/java"
            alternate.parent.mkdir(parents=True)
            shutil.copy2(java, alternate)
            (alternate.parent.parent / "lib").symlink_to(java.parent.parent.resolve() / "lib",
                                                         target_is_directory=True)
            self.assertEqual(hashlib.sha256(java.read_bytes()).digest(),
                             hashlib.sha256(alternate.read_bytes()).digest())
            archive = base / "archive.bin"
            archive.write_bytes(b"observer path control")
            output = base / "observer"
            script = ("import os,sys; null=os.open(os.devnull,os.O_WRONLY); "
                      "os.dup2(null,1); os.dup2(null,2); environment=os.environ.copy(); "
                      "environment['LD_LIBRARY_PATH']=sys.argv[3]; "
                      "os.execve(sys.argv[1],[sys.argv[2],'-version'],environment)")
            args = argparse.Namespace(candidate_sha=CANDIDATE, lane="local:path:control",
                runtime_identity="local", mode="debug", archive=str(archive),
                build_executable=str(alternate), launcher_script=None,
                build_only=True, build_argv_contains=[], artifact=[], expect=[],
                generated_expect=[], timeout=20, output=str(output),
                max_processes=256, max_events=4096, max_log_bytes=8 * 1024 * 1024,
                argv=[sys.executable, "-c", script, str(alternate), str(java),
                      str(java.resolve().parent.parent / "lib")])
            independent_linux_observer.capture(args)
            observed, rows = independent_linux_observer.verify(output,
                                                                 include_events=True)
            run = rows[0]
            image = next(row for row in rows if row["kind"] == "image"
                         and row.get("origin") == "exec"
                         and row.get("pid") == observed["build"]["pid"]
                         and row["executable_path"] == str(alternate))
            self.assertEqual(image["argv"][0], str(java))
            self.assertEqual(run["build"]["path"], str(alternate))
            with self.assertRaisesRegex(ValueError, "pinned Java process image"):
                full_signed_routes._cross_java_path(run, observed, image, str(java))

    def test_native_cross_real_launcher_observation_and_relocated_replay(self):
        lane = "linuxArm64:Linux ARM64:current:debug-g"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive = base / "archive"
            build = archive / "build"
            (build / "runtime").mkdir(parents=True)
            staged = {name: base / (name + ".klib") for name in ("dyn4k-core", "dyn4k")}
            for name, path in staged.items():
                path.write_bytes(name.encode())
            hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                      for name, path in staged.items()}
            products, executables = {}, {}
            for short in ("core", "facade"):
                product = build / "runtime" / (short + ".program")
                product.write_bytes(short.encode())
                sha = hashlib.sha256(product.read_bytes()).hexdigest()
                products[short] = {"archive": "runtime/" + short + ".program",
                                   "sha256": sha}
                executables[short] = sha
            java_home = Path("/home/linuxbrew/.linuxbrew/opt/openjdk@21")
            java = java_home / "bin/java"
            self.assertTrue(java.is_file())
            gradle = base / "gradlew"
            gradle.write_text("#!/bin/sh\nexec " + str(java) + " -version \"$@\"\n")
            gradle.chmod(0o700)
            toolchain = {"gradle_executable": str(gradle),
                         "gradle_sha256": hashlib.sha256(gradle.read_bytes()).hexdigest(),
                         "java_home": str(java_home),
                         "java_sha256": hashlib.sha256(java.read_bytes()).hexdigest(),
                         "java_version": 'openjdk version "21.0.12"',
                         "gradle_version": "Gradle 9.5.0", "kgp_version": "2.4.20",
                         "native_version": "Kotlin/Native: 2.4.20",
                         "python_executable": str(Path(sys.executable).resolve()),
                         "python_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
                         "native_home": str(base / "native"),
                         "native_sha256": "a" * 64,
                         "native_compiler_sha256": "b" * 64}
            build_host = {"system": "Linux", "machine": "x86_64"}
            selection = {"lane": lane, "role": "current", "system": "Linux",
                         "machine": "aarch64", "os_version": "6.17.0", "libc": "2.39"}
            host = {key: value for key, value in selection.items()
                    if key not in ("lane", "role")}
            runtime = full_native_host_consumer.digest(
                full_native_host_consumer.encoded(host))
            contract_sha = independent_gates.digest(
                independent_gates.consumer_contract(MANIFEST, lane))
            build_receipt = {"schema": 2, "status": "COMPILED_ONLY",
                             "phase": "linux-x64-cross-build", "candidate_sha": CANDIDATE,
                             "lane": lane, "source_tree": "e" * 40,
                             "consumer_contract_sha256": contract_sha,
                             "artifact_hashes": hashes,
                             "artifact_hash_provenance": "audited",
                             "build_host": build_host, "toolchain": toolchain,
                             "products": products, "selected_cases": 2523}
            config = base / "producer-config.json"
            config.write_text(json.dumps({"receipt": build_receipt,
                                          "build": str(build), "gradle": str(gradle)}))
            producer = base / "small-producer.py"
            producer.write_text(
                "import json, os, pathlib, subprocess, sys, time\n"
                "data = json.loads(pathlib.Path(sys.argv[1]).read_text())\n"
                "command = [data['gradle'], 'qualificationEvidence']\n"
                "started = time.time_ns()\n"
                "with open(os.devnull, 'wb') as output:\n"
                "    child = subprocess.Popen(command, stdout=output, stderr=output)\n"
                "    result = child.wait()\n"
                "finished = time.time_ns()\n"
                "if result: raise SystemExit(result)\n"
                "receipt = data['receipt']\n"
                "receipt['process'] = {'command': command, 'pid': child.pid,\n"
                "    'parent_pid': os.getpid(), 'started_ns': started,\n"
                "    'finished_ns': finished}\n"
                "(pathlib.Path(data['build']) / 'receipt.json').write_text(json.dumps(receipt))\n")
            observed_root = base / "observer"
            args = argparse.Namespace(candidate_sha=CANDIDATE, lane=lane,
                runtime_identity=runtime, mode="debug-g", archive=str(build),
                build_executable=str(java), launcher_script=str(gradle),
                build_only=True, build_argv_contains=[], artifact=[
                    name + "=" + str(path) for name, path in staged.items()],
                expect=[], generated_expect=[], timeout=20, output=str(observed_root),
                max_processes=256, max_events=4096, max_log_bytes=8 * 1024 * 1024,
                argv=[sys.executable, str(producer), str(config)])
            observed = independent_linux_observer.capture(args)
            self.assertNotEqual(toolchain["gradle_sha256"],
                                observed["build"]["executable_sha256"])
            observed, rows = independent_linux_observer.verify(observed_root,
                                                                 include_events=True)
            self.assertEqual(rows[0]["build"]["requested_path"], str(java))
            self.assertEqual(rows[0]["build"]["path"], str(java.resolve()))
            self.assertEqual(rows[0]["build"]["path"],
                             observed["build"]["executable_path"])
            full_signed_routes._cross_java_path(rows[0], observed,
                next(row for row in rows if row["kind"] == "image"
                     and row.get("origin") == "exec"
                     and row.get("pid") == observed["build"]["pid"]
                     and row["executable_path"] == rows[0]["build"]["path"]),
                str(java))
            build_receipt = json.loads((build / "receipt.json").read_text())
            build_digest = independent_gates.archive_digest(build)
            methods = [case["id"] for case in
                       independent_gates.consumer_contract(MANIFEST, lane)["cases"]]
            processes = {short: {"exit_code": 0, "pid": index + 1,
                                 "started_ns": 1, "finished_ns": 2,
                                 "observed_process": {"pid": index + 1}}
                         for index, short in enumerate(("core", "facade"))}
            receipt = {"schema": 3, "status": "PASSED", "candidate_sha": CANDIDATE,
                       "lane": lane, "source_tree": "e" * 40,
                       "artifact_hashes": hashes, "artifact_hash_provenance": "audited",
                       "build_archive_sha256": build_digest, "build_host": build_host,
                       "runtime_host": host, "runtime_host_after": host,
                       "selection": selection, "selected_cases": 2523,
                       "method_order": methods, "processes": processes}
            (archive / "receipt.json").write_text(json.dumps(receipt))
            digest = independent_gates.archive_digest(archive)
            shell = next(row for row in rows if row["kind"] == "image"
                         and row.get("origin") == "exec"
                         and row.get("pid") == build_receipt["process"]["pid"]
                         and row["executable_sha256"] != toolchain["java_sha256"])
            shell_exit = next(row for row in rows if row["kind"] == "exit"
                              and row.get("pid") == shell["pid"])
            signed_witness = {**observed, "archive_sha256": digest,
                "executables": executables,
                "launcher": {"script_path": str(gradle),
                             "script_sha256": toolchain["gradle_sha256"],
                             "command": build_receipt["process"]["command"],
                             "pid": shell["pid"],
                             "parent_pid": build_receipt["process"]["parent_pid"],
                             "executable_path": shell["executable_path"],
                             "executable_sha256": shell["executable_sha256"],
                             "started_ns": shell["observed_at_ns"],
                             "finished_ns": shell_exit["observed_at_ns"]},
                "processes": {short: {"pid": index + 1,
                    "executable_sha256": executables[short], "exit_code": 0,
                    "started_ns": 1, "finished_ns": 2,
                    "started_wall_ns": 1, "finished_wall_ns": 2}
                    for index, short in enumerate(("core", "facade"))}}
            witness_file = base / "signed-witness.json"
            witness_file.write_text(json.dumps(signed_witness))
            expected = {"expected_artifact_hashes": hashes,
                "expected_runtime_identity": runtime,
                "expected_archive_digests": {"staged-consumer": digest},
                "expected_native_selection": selection, "expected_native_host": host,
                "expected_native_build_host": build_host,
                "expected_native_toolchain": toolchain,
                "expected_native_build_archive_sha256": build_digest,
                "expected_native_build_executables": executables,
                "expected_build_launcher_image": {
                    "path": shell["executable_path"],
                    "sha256": shell["executable_sha256"]},
                "expected_native_build_observer": {"path": str(observed_root),
                    "events_sha256": hashlib.sha256((observed_root / "events.jsonl").read_bytes()).hexdigest(),
                    "witness_sha256": hashlib.sha256((observed_root / "witness.json").read_bytes()).hexdigest()},
                "expected_execution_witness": {"path": str(witness_file),
                    "sha256": hashlib.sha256(witness_file.read_bytes()).hexdigest()}}
            public = {"status": "PASSED", "lane": lane, "candidate_sha": CANDIDATE,
                      "archive_sha256": digest, "selected_cases": 2523,
                      "artifact_hash_provenance": "audited",
                      "complete_selected_suite": True}
            gradle.unlink()
            check_output = full_signed_routes.subprocess.check_output
            observer_source = Path(independent_linux_observer.__file__).read_bytes()
            def candidate_source(command, **kwargs):
                if command[-1] == (CANDIDATE + ":tools/qualification/"
                                   "independent_linux_observer.py"):
                    return observer_source
                return check_output(command, **kwargs)
            with patch.object(full_signed_routes, "_source"), patch.object(
                    full_signed_routes.subprocess, "check_output",
                    side_effect=candidate_source), patch(
                    "full_native_host_consumer.verify_cross_run", return_value=public):
                self.assertEqual(full_signed_routes.verify(
                    ROOT, CANDIDATE, lane, archive, expected, hashes, runtime, digest), public)
                original_witness = witness_file.read_bytes()
                for section, key, value in (
                        ("build", "pid", 99),
                        ("build", "executable_sha256", toolchain["gradle_sha256"]),
                        ("launcher", "script_sha256", "0" * 64),
                        ("launcher", "command", [str(gradle), "wrong-task"]),
                        ("launcher", "parent_pid", 99),
                        ("core", "finished_wall_ns", 3)):
                    changed = json.loads(original_witness)
                    record = (changed["processes"][section] if section == "core"
                              else changed[section])
                    record[key] = value
                    witness_file.write_text(json.dumps(changed))
                    expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                        witness_file.read_bytes()).hexdigest()
                    with self.assertRaises(ValueError):
                        full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                                  expected, hashes, runtime, digest)
                changed = json.loads(original_witness)
                del changed["processes"]["core"]
                witness_file.write_text(json.dumps(changed))
                expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                    witness_file.read_bytes()).hexdigest()
                with self.assertRaises(ValueError):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, hashes, runtime, digest)
                witness_file.write_bytes(original_witness)
                expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                    original_witness).hexdigest()
                for key, value in (("gradle_sha256", "0" * 64),
                                   ("java_sha256", "0" * 64)):
                    changed = expected["expected_native_toolchain"]
                    expected["expected_native_toolchain"] = {**changed, key: value}
                    with self.assertRaises(ValueError):
                        full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                                  expected, hashes, runtime, digest)
                    expected["expected_native_toolchain"] = changed
                binding = expected.pop("expected_native_build_observer")
                with self.assertRaisesRegex(ValueError, "observer is missing"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, hashes, runtime, digest)
                expected["expected_native_build_observer"] = binding
                expected["expected_native_build_observer"] = {
                    **binding, "events_sha256": "0" * 64}
                with self.assertRaisesRegex(ValueError, "observer.*bytes differ"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, hashes, runtime, digest)
                expected["expected_native_build_observer"] = binding
                expected["expected_build_launcher_image"] = {
                    **expected["expected_build_launcher_image"], "sha256": "0" * 64}
                with self.assertRaisesRegex(ValueError, "launcher process witness"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, hashes, runtime, digest)
                expected["expected_build_launcher_image"]["sha256"] = shell["executable_sha256"]
                relocated = base / "relocated"
                shutil.copytree(archive, relocated)
                relocated_observer = base / "relocated-observer"
                shutil.copytree(observed_root, relocated_observer)
                relocated_witness = base / "relocated-witness.json"
                shutil.copy2(witness_file, relocated_witness)
                expected["expected_native_build_observer"] = {
                    **binding, "path": str(relocated_observer)}
                expected["expected_execution_witness"] = {
                    **expected["expected_execution_witness"],
                    "path": str(relocated_witness)}
                self.assertEqual(independent_gates.archive_digest(relocated), digest)
                expected["expected_archive_digests"]["staged-consumer"] = digest
                self.assertEqual(full_signed_routes.verify(
                    ROOT, CANDIDATE, lane, relocated, expected, hashes, runtime, digest), public)
                with patch.object(independent_linux_observer, "verify",
                                  side_effect=AssertionError("imported verifier used")):
                    self.assertEqual(full_signed_routes.verify(
                        ROOT, CANDIDATE, lane, relocated, expected, hashes, runtime, digest),
                        public)

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
                 build_executable, archive_digest="c" * 64):
        if not expected:
            toolchain = {"gradle_sha256": "f" * 64}
            script = str(base / "gradle")
        elif "expected_native_toolchain" in expected:
            toolchain = expected["expected_native_toolchain"]
            script = toolchain["gradle_executable"]
        elif "expected_android_native_toolchain" in expected:
            toolchain = expected["expected_android_native_toolchain"]
            script = expected["expected_android_native_executable_paths"]["gradle"]
        else:
            toolchain = expected["expected_browser_toolchain"]
            script = toolchain["gradle"]
        if expected:
            self.assertNotEqual(build_executable, toolchain["gradle_sha256"])
        command = [script, "qualificationEvidence"]
        expected["expected_build_launcher_image"] = {
            "path": "/usr/bin/bash", "sha256": "f" * 64}
        witness = {"schema": "independent-execution-witness/1",
                   "candidate_sha": CANDIDATE, "lane": lane,
                   "archive_sha256": archive_digest, "runtime_identity": runtime,
                   "mode": mode, "executables": executables,
                   "staged_artifacts": HASHES, "auditor": "independent test",
                   "build": {"executable_sha256": build_executable, "pid": 10,
                             "exit_code": 0, "started_ns": 1, "finished_ns": 2},
                   "launcher": {"script_path": script,
                                "script_sha256": toolchain["gradle_sha256"],
                                "command": command, "pid": 10, "parent_pid": 9,
                                "executable_path": "/usr/bin/bash",
                                "executable_sha256": "f" * 64,
                                "started_ns": 1, "finished_ns": 2},
                   "processes": {name: {"executable_sha256": value, "pid": index + 1,
                                        "exit_code": 0, "started_ns": 1,
                                        "finished_ns": 2, "started_wall_ns": 1,
                                        "finished_wall_ns": 2}
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
            receipt["process"] = {"command": [str(gradle), "qualificationEvidence"]}
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
                          toolchain["java_sha256"])
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
                             "process": {"pid": 10, "parent_pid": 9,
                                         "command": [str(paths["gradle"]),
                                                     "qualificationEvidence"],
                                         "started_ns": 1, "finished_ns": 2},
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
                       "processes": {short: {"exit_code": 0, "pid": index + 1,
                                             "started_ns": 1, "finished_ns": 2,
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
                        "expected_native_build_observer": {"path": str(base / "observer"),
                            "events_sha256": "f" * 64, "witness_sha256": "f" * 64},
                        "expected_native_build_executables": executables}
            self._witness(base, expected, lane, runtime, "debug-g", executables,
                          toolchain["java_sha256"], digest)
            public = {"status": "PASSED", "lane": lane, "candidate_sha": CANDIDATE,
                      "archive_sha256": digest, "selected_cases": 2523,
                      "artifact_hash_provenance": "audited",
                      "complete_selected_suite": True}
            for path in paths.values():
                path.unlink()
            with patch.object(full_signed_routes, "_source"), patch.object(
                    full_signed_routes, "_cross_build_observer"), patch(
                    "full_native_host_consumer.verify", side_effect=AssertionError(
                        "cross route used ordinary verifier")), patch(
                    "full_native_host_consumer.verify_cross_run", return_value=public) as cross_verify:
                self.assertEqual(full_signed_routes.verify(
                    ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime, digest), public)
                cross_verify.assert_called_once_with(
                    archive, ROOT, CANDIDATE, lane, HASHES, selection, digest,
                    build_digest, toolchain)
                signed_witness = expected.pop("expected_execution_witness")
                with self.assertRaisesRegex(ValueError, "process witness is missing"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                expected["expected_execution_witness"] = signed_witness
                witness_path = Path(signed_witness["path"])
                original_witness = witness_path.read_bytes()
                witness_path.write_bytes(original_witness + b" ")
                with self.assertRaisesRegex(ValueError, "witness bytes differ"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                witness_path.write_bytes(original_witness)
                changed_witness = json.loads(original_witness)
                changed_witness["processes"]["core"]["pid"] = 99
                witness_path.write_text(json.dumps(changed_witness))
                signed_witness["sha256"] = hashlib.sha256(witness_path.read_bytes()).hexdigest()
                with self.assertRaisesRegex(ValueError, "cross.*process witness"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                witness_path.write_bytes(original_witness)
                signed_witness["sha256"] = hashlib.sha256(original_witness).hexdigest()
                for section, field, value, reason in (
                        ("core", "finished_wall_ns", 3, "cross.*process witness"),
                        ("core", "executable_sha256", "0" * 64,
                         "process witness lacks observed execution")):
                    changed_witness = json.loads(original_witness)
                    record = (changed_witness["build"] if section == "build" else
                              changed_witness["processes"][section])
                    record[field] = value
                    witness_path.write_text(json.dumps(changed_witness))
                    signed_witness["sha256"] = hashlib.sha256(
                        witness_path.read_bytes()).hexdigest()
                    with self.assertRaisesRegex(ValueError, reason):
                        full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                                  expected, HASHES, runtime, digest)
                changed_witness = json.loads(original_witness)
                changed_witness["candidate_sha"] = "0" * 40
                witness_path.write_text(json.dumps(changed_witness))
                signed_witness["sha256"] = hashlib.sha256(witness_path.read_bytes()).hexdigest()
                with self.assertRaisesRegex(ValueError, "process witness differs from signed route"):
                    full_signed_routes.verify(ROOT, CANDIDATE, lane, archive,
                                              expected, HASHES, runtime, digest)
                witness_path.write_bytes(original_witness)
                signed_witness["sha256"] = hashlib.sha256(original_witness).hexdigest()
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
            receipt["process"] = {"command": [str(binaries["gradle"]),
                                               "qualificationEvidence"]}
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
                          toolchain["java_sha256"])
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
                          expected["expected_android_native_toolchain"]["java_sha256"])
            (archive / "build.json").write_text(json.dumps({"process": {
                "command": [str(gradle), "qualificationEvidence"]}}))
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
            receipt["process"] = {"graph": {"command": [toolchain["gradle"],
                                                        "qualificationEvidence"]}}
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

    def test_signed_launcher_grandchild_requires_complete_ancestry(self):
        lane = "linuxX64:Linux x64:current:debug-g"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            script = str(base / "gradlew")
            java_sha = "a" * 64
            expected = {"expected_native_toolchain": {
                "gradle_executable": script, "gradle_sha256": "b" * 64}}
            executables = {"core": "c" * 64, "facade": "d" * 64}
            self._witness(base, expected, lane, "Linux current", "debug-g",
                          executables, java_sha)
            path = Path(expected["expected_execution_witness"]["path"])
            witness = json.loads(path.read_text())
            witness["build"].update({"pid": 12, "parent_pid": 11})
            witness["build_ancestry"] = [
                {"pid": 12, "parent_pid": 11}, {"pid": 11, "parent_pid": 10}]
            path.write_text(json.dumps(witness))
            expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                path.read_bytes()).hexdigest()
            launcher = full_signed_routes._launcher(script, "b" * 64,
                                                      [script, "qualificationEvidence"])
            self.assertEqual(full_signed_routes.execution_witness(
                expected, CANDIDATE, lane, "c" * 64, "Linux current", "debug-g",
                executables, HASHES, java_sha, launcher=launcher)["build"]["pid"], 12)
            witness["build_ancestry"][1]["parent_pid"] = 99
            path.write_text(json.dumps(witness))
            expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "ancestry"):
                full_signed_routes.execution_witness(
                    expected, CANDIDATE, lane, "c" * 64, "Linux current", "debug-g",
                    executables, HASHES, java_sha, launcher=launcher)

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

    def test_schema5_signed_firefox_and_safari_body_execution_controls(self):
        candidate = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        for family, role, runtime in (("Firefox", "current", "Linux test x86_64"),
                                      ("Firefox", "minimum", "Linux test x86_64"),
                                      ("Safari", "current", "Darwin test arm64")):
            for target in ("js", "wasmJs"):
                with self.subTest(family=family, role=role, target=target), tempfile.TemporaryDirectory() as tmp:
                    base = Path(tmp)
                    archive = base / "archive"
                    archive.mkdir()
                    responses, receipt = self._http_fixture(archive, target == "wasmJs")
                    lane = f"{target}:{family}:{role}:development"
                    receipt.update({"schema": 5, "status": "PASSED", "candidate_sha": candidate,
                                    "lane": lane, "runtime_identity": runtime,
                                    "staged_hashes": HASHES,
                                    "consumer_contract_sha256": independent_gates.digest(
                                        independent_gates.consumer_contract(MANIFEST, lane))})
                    selected_browser = base / ("firefox" if family == "Firefox" else "Safari")
                    selected_browser.write_bytes(b"synthetic selected browser")
                    selected_sha = hashlib.sha256(selected_browser.read_bytes()).hexdigest()
                    firefox_image = base / "firefox-bin"
                    if family == "Firefox":
                        firefox_image.write_bytes(b"synthetic distinct firefox-bin image")
                    collector_bytes = (full_browser_consumer.original(
                        ROOT, candidate, full_browser_consumer.FIREFOX_WITNESS)
                        if family == "Firefox" else None)
                    collector_sha = (hashlib.sha256(collector_bytes).hexdigest()
                                     if collector_bytes is not None else None)
                    toolchain = {"browser": str(selected_browser),
                                 "browser_sha256": selected_sha,
                                 "java_home": str(base),
                                 "java_sha256": full_browser_consumer.expected_java_sha256(
                                     runtime.split()[0], family),
                                 "gradle": str(base / "gradle"),
                                 "gradle_sha256": full_browser_consumer.GRADLE_SHA256,
                                 "kgp_version": "2.4.20", "gradle_version": "9.5.0"}
                    receipt["toolchain"] = toolchain
                    bundles = {}
                    consumption = {}
                    external = base / "observed"
                    external.mkdir()
                    for index, short in enumerate(("core", "facade")):
                        folder = archive / short
                        receipt["modules"][short]["finished_ns"] = 100
                        pid = 100 + index
                        image = firefox_image if family == "Firefox" and short == "core" else selected_browser
                        image_sha = hashlib.sha256(image.read_bytes()).hexdigest()
                        (folder / "browser-launches.jsonl").write_text(json.dumps({
                            "pid": pid, "process_executable": str(image),
                            "process_sha256": image_sha,
                            "selected_binary": str(selected_browser),
                            "selected_sha256": selected_sha}) + "\n")
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
                        session = {"kind": "session", "browser_pid": pid}
                        if family == "Firefox":
                            session.update({"source_path": str(ROOT / full_browser_consumer.FIREFOX_WITNESS),
                                            "source_sha256": collector_sha})
                        rows = [session]
                        observed = []
                        for item in responses[short]["responses"]:
                            body = (folder / item["body_path"]).read_bytes()
                            outside = external / f"{short}-{item['ordinal']}.body"
                            outside.write_bytes(body)
                            rows.append({"url": f"http://localhost:9876{item['url']}",
                                         "browser_pid": pid, "request_ns": 11,
                                         "response_ns": 16, "finished_ns": 17,
                                         "body_size": item["size"],
                                         "body_sha256": item["sha256"]})
                            if family == "Firefox" and role == "minimum":
                                copied = folder / "safari-browser-bodies" / f"{item['ordinal']:04d}.body"
                                copied.parent.mkdir(exist_ok=True)
                                copied.write_bytes(body)
                                rows[-1]["body_path"] = copied.relative_to(folder).as_posix()
                            observed.append({"url": item["url"], "size": item["size"],
                                             "body_sha256": item["sha256"],
                                             "body_path": str(outside),
                                             "request_ns": 11, "response_ns": 16,
                                             "finished_ns": 17})
                        name = ("firefox-bidi.jsonl" if family == "Firefox" and role == "current" else
                                "safari-browser-responses.jsonl")
                        (folder / name).write_text("\n".join(json.dumps(row) for row in rows) + "\n")
                        if family == "Firefox" and role == "minimum":
                            navigation = {"target_url": "http://localhost:9876/?id=1",
                                          "bootstrap_url": "http://localhost:9876/__dyn4k_bootstrap",
                                          "navigation_requested_ns": 11,
                                          "navigation_result_ns": 12,
                                          "bidi_socket_inode": "123"}
                            bidi = {"kind": "session", "browser_pid": pid,
                                    "bidi_browser_pid": pid,
                                    "browser_token": "synthetic-token",
                                    "redirect_sha256": "c" * 64,
                                    "source_path": str(ROOT / full_browser_consumer.FIREFOX_WITNESS),
                                    "source_sha256": collector_sha, **navigation}
                            session.update({"target_url": navigation["target_url"],
                                            "browser_token": bidi["browser_token"],
                                            "redirect_sha256": bidi["redirect_sha256"],
                                            "started_ns": 13})
                            (folder / name).write_text("\n".join(json.dumps(row)
                                for row in rows) + "\n")
                            (folder / "firefox-bidi.jsonl").write_text(json.dumps(bidi) + "\n")
                        consumption[short] = {"protocol": ("bidi-service-worker"
                                              if family == "Firefox" and role == "minimum" else
                                              "bidi" if family == "Firefox" else "service-worker"),
                                              "clock": "unix-epoch-ns",
                                              "browser_pid": pid, "browser_sha256": image_sha,
                                              "process_executable": str(image),
                                              "started_ns": 10, "finished_ns": 90,
                                              "responses": observed}
                        if family == "Firefox" and role == "minimum":
                            consumption[short]["navigation"] = navigation
                    (archive / "receipt.json").write_text(json.dumps(receipt))
                    digest = independent_gates.archive_digest(archive)
                    sources = ((full_browser_consumer.FIREFOX_WITNESS,
                                full_browser_consumer.SAFARI_WITNESS,
                                full_browser_consumer.SAFARI_WORKER,
                                full_browser_consumer.SAFARI_BOOTSTRAP,
                                full_browser_consumer.SAFARI_OBSERVER)
                               if family == "Firefox" and role == "minimum" else
                               (full_browser_consumer.FIREFOX_WITNESS,) if family == "Firefox" else
                               (full_browser_consumer.SAFARI_WITNESS,
                                     full_browser_consumer.SAFARI_WORKER,
                                     full_browser_consumer.SAFARI_BOOTSTRAP,
                                     full_browser_consumer.SAFARI_OBSERVER))
                    witness = {"schema": "independent-browser-execution-witness/2",
                               "candidate_sha": candidate, "lane": lane,
                               "archive_sha256": digest, "runtime_identity": runtime,
                               "mode": "development", "staged_artifacts": HASHES,
                               "browser_sha256": selected_sha, "family": family,
                               "source_sha256": {name: hashlib.sha256(
                                   full_browser_consumer.original(ROOT, candidate, name)
                                   ).hexdigest() for name in sources},
                               "auditor": "synthetic test key", "responses": responses,
                               "browser_consumption": consumption}
                    witness_path = base / "independent-witness.json"
                    expected = {"expected_artifact_hashes": HASHES,
                                "expected_runtime_identity": runtime,
                                "expected_archive_digests": {"staged-consumer": digest},
                                "expected_browser_toolchain": toolchain,
                                "expected_browser_bundles": bundles,
                                "expected_browser_responses": responses}
                    def seal():
                        witness_path.write_text(json.dumps(witness))
                        expected["expected_execution_witness"] = {
                            "path": str(witness_path),
                            "sha256": hashlib.sha256(witness_path.read_bytes()).hexdigest()}
                    seal()
                    public = {"status": "PASSED", "lane": lane, "selected_cases": 2523,
                              "archive_sha256": digest, "candidate_sha": candidate}
                    actual_file = full_signed_routes._file
                    with (patch.object(full_signed_routes, "_source"),
                          patch.object(full_signed_routes, "_file", side_effect=lambda path, sha, label:
                              Path(path) if label in ("browser", "JDK 21", "Gradle") else
                              actual_file(path, sha, label)),
                          patch("full_browser_consumer.runtime_pin"),
                          patch("full_browser_consumer.verify", return_value=public) as public_verify):
                        self.assertEqual(full_signed_routes.verify_browser(
                            ROOT, candidate, lane, archive, expected, HASHES, runtime, digest), public)
                        expected["expected_build_launcher_image"] = {
                            "path": "/usr/bin/false", "sha256": "b" * 64}
                        with self.assertRaisesRegex(ValueError, "unused.*launcher"):
                            full_signed_routes.verify_browser(
                                ROOT, candidate, lane, archive, expected, HASHES,
                                runtime, digest)
                        del expected["expected_build_launcher_image"]
                        gate = independent_gates.evaluate_gate(
                            "staged-consumer", archive, candidate, lane, MANIFEST["lanes"][lane],
                            ROOT, HASHES, runtime, digest, manifest=MANIFEST,
                            expected_signed_lane=expected)
                        self.assertEqual(gate["status"], "PASSED", gate)
                        relocated = base / "physically-copied-archive"
                        shutil.copytree(archive, relocated, copy_function=shutil.copy2)
                        self.assertEqual(independent_gates.archive_digest(relocated), digest)
                        copied_gate = independent_gates.evaluate_gate(
                            "staged-consumer", relocated, candidate, lane,
                            MANIFEST["lanes"][lane], ROOT, HASHES, runtime, digest,
                            manifest=MANIFEST, expected_signed_lane=expected)
                        self.assertEqual(copied_gate["status"], "PASSED", copied_gate)
                        self.assertEqual(public_verify.call_args.args[3], relocated)
                        if target == "js" or family == "Firefox" and role == "minimum":
                            all_hashes = {name: (HASHES if name == target else {
                                module: hashlib.sha256(f"synthetic:{name}:{module}".encode())
                                    .hexdigest() for module in qualify.MODULES})
                                for name in qualify.matrix_targets()}
                            staged = {"candidate_sha": candidate, "status": "PASSED",
                                      "artifacts": [{"path": qualify.target_binary_path(module, name),
                                                     "sha256": value}
                                                    for name, pair in all_hashes.items()
                                                    for module, value in pair.items()]}
                            candidate_manifest = {
                                "candidate_sha": candidate,
                                "suite_manifest_sha256": independent_gates.digest(MANIFEST),
                                "audit_manifest_sha256": qualify.manifest_digest(staged),
                                "lanes": {name: {"artifact_hashes": all_hashes[spec["target"]],
                                                 "runtime_identity": runtime if name == lane else
                                                 f"synthetic:{name}"}
                                          for name, spec in MANIFEST["lanes"].items()}}
                            observations = {"schema": 1, "candidate_sha": candidate,
                                            "lanes": {name: {"archives": {}, "signed_fields": {}}
                                                      for name in MANIFEST["lanes"]}}
                            observations["lanes"][lane] = {
                                "archives": {"staged-consumer": str(archive)},
                                "signed_fields": {key: value for key, value in expected.items()
                                                  if key.startswith("expected_browser_") or
                                                  key == "expected_execution_witness"}}
                            inputs = []
                            for name, value in (("candidate", candidate_manifest),
                                                ("staged", staged),
                                                ("observations", observations)):
                                path = base / f"{name}.json"
                                path.write_text(json.dumps(value))
                                inputs.append(path)
                            with (patch("qualify.require_clean_checkout"),
                                  patch("qualify.verify_audit_against_staging")):
                                prepared = independent_audit_producer.prepare(
                                    ROOT, candidate, *inputs, base / "prepared", "f" * 64)
                            audit = json.loads((prepared / "audit.json").read_bytes())
                            self.assertEqual(audit["preflight_results"][lane]["gates"][
                                "staged-consumer"], "PASSED")
                            self.assertEqual(audit["lanes"][lane]["expected_execution_witness"],
                                             expected["expected_execution_witness"])
                        hardlink = base / "hardlinked-witness.json"
                        os.link(witness_path, hardlink)
                        expected["expected_execution_witness"]["path"] = str(hardlink)
                        with self.assertRaisesRegex(ValueError, "witness is absent or inside"):
                            full_signed_routes.verify_browser(ROOT, candidate, lane,
                                archive, expected, HASHES, runtime, digest)
                        hardlink.unlink()
                        expected["expected_execution_witness"]["path"] = str(witness_path)
                        if family == "Firefox":
                            self.assertNotEqual(consumption["core"]["browser_sha256"], selected_sha)
                            self.assertEqual(consumption["facade"]["browser_sha256"], selected_sha)
                            process_sha = consumption["core"]["browser_sha256"]
                            witness["browser_sha256"] = process_sha
                            seal()
                            with self.assertRaisesRegex(ValueError, "execution witness differs"):
                                full_signed_routes.verify_browser(ROOT, candidate, lane,
                                    archive, expected, HASHES, runtime, digest)
                            witness["browser_sha256"] = selected_sha
                            seal()
                            consumption["core"]["browser_sha256"] = selected_sha
                            seal()
                            with self.assertRaisesRegex(ValueError, "process differs"):
                                full_signed_routes.verify_browser(ROOT, candidate, lane,
                                    archive, expected, HASHES, runtime, digest)
                            consumption["core"]["browser_sha256"] = process_sha
                            seal()
                            process_path = consumption["core"]["process_executable"]
                            consumption["core"]["process_executable"] = str(selected_browser)
                            seal()
                            with self.assertRaisesRegex(ValueError, "process differs"):
                                full_signed_routes.verify_browser(ROOT, candidate, lane,
                                    archive, expected, HASHES, runtime, digest)
                            consumption["core"]["process_executable"] = process_path
                            seal()
                            source_repo = base / "tampered-source"
                            live_collector = source_repo / full_browser_consumer.FIREFOX_WITNESS
                            live_collector.parent.mkdir(parents=True)
                            live_collector.write_bytes(collector_bytes + b"\ntampered\n")
                            tampered_archive = base / "tampered-collector-archive"
                            shutil.copytree(archive, tampered_archive, copy_function=shutil.copy2)
                            for module in ("core", "facade"):
                                record = tampered_archive / module / "firefox-bidi.jsonl"
                                lines = record.read_text().splitlines()
                                declaration = json.loads(lines[0])
                                declaration["source_path"] = str(live_collector)
                                declaration["source_sha256"] = collector_sha
                                record.write_text("\n".join([json.dumps(declaration), *lines[1:]]) + "\n")
                            self.assertEqual(json.loads((tampered_archive /
                                "core/firefox-bidi.jsonl").read_text().splitlines()[0])[
                                    "source_sha256"], collector_sha)
                            with patch.object(full_browser_consumer, "original",
                                              return_value=collector_bytes):
                                with self.assertRaisesRegex(ValueError, "live Firefox collector"):
                                    full_signed_routes.schema5_browser_witness(
                                        source_repo, expected, candidate, lane, digest,
                                        runtime, HASHES, toolchain, tampered_archive, receipt)
                        if family == "Firefox" and role == "minimum":
                            navigation = consumption["core"]["navigation"]
                            for key, wrong in (("target_url", "http://localhost:9876/wrong"),
                                               ("navigation_result_ns", 91),
                                               ("bidi_socket_inode", "456")):
                                prior = navigation[key]
                                navigation[key] = wrong
                                seal()
                                with self.assertRaisesRegex(ValueError, "navigation differs"):
                                    full_signed_routes.verify_browser(ROOT, candidate, lane,
                                        archive, expected, HASHES, runtime, digest)
                                navigation[key] = prior
                            seal()
                            prior = witness["source_sha256"][full_browser_consumer.SAFARI_WORKER]
                            witness["source_sha256"][full_browser_consumer.SAFARI_WORKER] = "0" * 64
                            seal()
                            with self.assertRaisesRegex(ValueError, "execution witness differs"):
                                full_signed_routes.verify_browser(ROOT, candidate, lane,
                                    archive, expected, HASHES, runtime, digest)
                            witness["source_sha256"][full_browser_consumer.SAFARI_WORKER] = prior
                            seal()
                            worker_repo = base / "tampered-worker-source"
                            for name in sources:
                                destination = worker_repo / name
                                destination.parent.mkdir(parents=True, exist_ok=True)
                                destination.write_bytes(full_browser_consumer.original(
                                    ROOT, candidate, name))
                            (worker_repo / full_browser_consumer.SAFARI_WORKER).write_bytes(
                                b"tampered worker despite archived committed digest")
                            committed_source = full_browser_consumer.original
                            with patch.object(full_browser_consumer, "original",
                                side_effect=lambda _repository, selected, name:
                                    committed_source(ROOT, selected, name)):
                                with self.assertRaisesRegex(ValueError, "live Firefox collector"):
                                    full_signed_routes.schema5_browser_witness(
                                        worker_repo, expected, candidate, lane, digest,
                                        runtime, HASHES, toolchain, archive, receipt)
                            copied_body = archive / "core/safari-browser-bodies/0000.body"
                            original_body = copied_body.read_bytes()
                            body_stat = copied_body.stat()
                            copied_body.write_bytes(b"changed service-worker body")
                            with self.assertRaisesRegex(ValueError, "body or interval differs"):
                                full_signed_routes.schema5_browser_witness(
                                    ROOT, expected, candidate, lane, digest,
                                    runtime, HASHES, toolchain, archive, receipt)
                            copied_body.write_bytes(original_body)
                            os.utime(copied_body, ns=(body_stat.st_atime_ns, body_stat.st_mtime_ns))
                            worker_rows = archive / "core/safari-browser-responses.jsonl"
                            original_rows = worker_rows.read_bytes()
                            worker_stat = worker_rows.stat()
                            changed = [json.loads(line) for line in original_rows.splitlines()]
                            changed[0]["target_url"] = "http://localhost:9876/wrong"
                            worker_rows.write_text("\n".join(json.dumps(row) for row in changed) + "\n")
                            with self.assertRaisesRegex(ValueError, "navigation differs"):
                                full_signed_routes.schema5_browser_witness(
                                    ROOT, expected, candidate, lane, digest,
                                    runtime, HASHES, toolchain, archive, receipt)
                            worker_rows.write_bytes(original_rows)
                            os.utime(worker_rows, ns=(worker_stat.st_atime_ns, worker_stat.st_mtime_ns))
                            bidi_rows = archive / "core/firefox-bidi.jsonl"
                            original_bidi = bidi_rows.read_bytes()
                            bidi_stat = bidi_rows.stat()
                            changed_bidi = json.loads(original_bidi)
                            changed_bidi["bidi_browser_pid"] += 1
                            bidi_rows.write_text(json.dumps(changed_bidi) + "\n")
                            with self.assertRaisesRegex(ValueError, "navigation differs"):
                                full_signed_routes.schema5_browser_witness(
                                    ROOT, expected, candidate, lane, digest,
                                    runtime, HASHES, toolchain, archive, receipt)
                            bidi_rows.write_bytes(original_bidi)
                            os.utime(bidi_rows, ns=(bidi_stat.st_atime_ns, bidi_stat.st_mtime_ns))
                        for field, wrong in (("family", "Chromium"), ("lane", "wrong"),
                                             ("source_sha256", {})):
                            prior = witness[field]
                            witness[field] = wrong
                            seal()
                            with self.assertRaisesRegex(ValueError, "execution witness differs"):
                                full_signed_routes.verify_browser(ROOT, candidate, lane,
                                    archive, expected, HASHES, runtime, digest)
                            witness[field] = prior
                        seal()
                        prior = consumption["core"]["protocol"]
                        consumption["core"]["protocol"] = "cdp"
                        seal()
                        with self.assertRaisesRegex(ValueError, "process differs"):
                            full_signed_routes.verify_browser(ROOT, candidate, lane,
                                archive, expected, HASHES, runtime, digest)
                        consumption["core"]["protocol"] = prior
                        seal()
                        prior_pid = consumption["core"]["browser_pid"]
                        consumption["core"]["browser_pid"] = 999
                        seal()
                        with self.assertRaisesRegex(ValueError, "process differs"):
                            full_signed_routes.verify_browser(ROOT, candidate, lane,
                                archive, expected, HASHES, runtime, digest)
                        consumption["core"]["browser_pid"] = prior_pid
                        removed = consumption["core"]["responses"].pop()
                        seal()
                        with self.assertRaisesRegex(ValueError, "process differs"):
                            full_signed_routes.verify_browser(ROOT, candidate, lane,
                                archive, expected, HASHES, runtime, digest)
                        consumption["core"]["responses"].append(removed)
                        seal()
                        signed_sha = expected["expected_execution_witness"]["sha256"]
                        expected["expected_execution_witness"]["sha256"] = "0" * 64
                        with self.assertRaisesRegex(ValueError, "signed bytes"):
                            full_signed_routes.verify_browser(ROOT, candidate, lane,
                                archive, expected, HASHES, runtime, digest)
                        expected["expected_execution_witness"]["sha256"] = signed_sha
                        outside = Path(consumption["core"]["responses"][0]["body_path"])
                        outside.write_bytes(b"wrong")
                        with self.assertRaisesRegex(ValueError, "body or interval differs"):
                            full_signed_routes.verify_browser(ROOT, candidate, lane,
                                archive, expected, HASHES, runtime, digest)
                        outside.unlink()
                        with self.assertRaisesRegex(ValueError, "body or interval differs"):
                            full_signed_routes.verify_browser(ROOT, candidate, lane,
                                archive, expected, HASHES, runtime, digest)

    def test_schema5_rejects_hardlinked_external_witness_before_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = base / "archive"
            archive.mkdir()
            witness = base / "witness.json"
            witness.write_text("{}")
            linked = base / "linked-witness.json"
            os.link(witness, linked)
            expected = {"expected_execution_witness": {
                "path": str(linked), "sha256": hashlib.sha256(linked.read_bytes()).hexdigest()}}
            candidate = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            with self.assertRaisesRegex(ValueError, "witness is absent or inside"):
                full_signed_routes.schema5_browser_witness(
                    ROOT, expected, candidate, "js:Safari:current:development", "b" * 64,
                    "Darwin test arm64", HASHES, {}, archive, {})

    def test_schema5_pins_live_firefox_collector_before_archived_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository = base / "repository"
            archive = base / "archive"
            folder = archive / "core"
            folder.mkdir(parents=True)
            committed = (ROOT / full_browser_consumer.FIREFOX_WITNESS).read_bytes()
            declared = hashlib.sha256(committed).hexdigest()
            collector = repository / full_browser_consumer.FIREFOX_WITNESS
            collector.parent.mkdir(parents=True)
            collector.write_bytes(committed + b"\ntampered\n")
            (folder / "firefox-bidi.jsonl").write_text(json.dumps({
                "kind": "session", "source_path": str(collector),
                "source_sha256": declared}) + "\n")
            self.assertEqual(json.loads((folder / "firefox-bidi.jsonl").read_text())[
                "source_sha256"], declared)
            witness = base / "witness.json"
            witness.write_text("{}")
            expected = {"expected_execution_witness": {
                "path": str(witness), "sha256": hashlib.sha256(witness.read_bytes()).hexdigest()}}
            with patch.object(full_browser_consumer, "original", return_value=committed):
                with self.assertRaisesRegex(ValueError, "live Firefox collector"):
                    full_signed_routes.schema5_browser_witness(
                        repository, expected, "a" * 40,
                        "js:Firefox:current:development", "b" * 64,
                        "Linux test x86_64", HASHES, {}, archive, {})

    def test_retained_firefox_minimum_original_and_relocated_public_replay(self):
        repository = Path("/var/home/stewart/Workspace/dyn4k-port-firefox-minimum-observer-20261020")
        base = Path("/var/home/stewart/dyn4k-evidence/session-control/firefox-minimum")
        browser = Path("/tmp/dyn4k-browser-wasi-tools/firefox-120/firefox/firefox")
        if not repository.is_dir() or not browser.is_file() or not (
                base / "js-min-dev-839-relocated/receipt.json").is_file():
            self.skipTest("retained Firefox minimum replay inputs are absent")
        candidate = "839589d508a74258d5a14433621ff202f6a56444"
        browser_sha = "74b442bb10d62f01e80eeae8fee96fd98ecb1d414cf283b2fcef80410d827750"
        routes = (
            ("js", "js-min-dev-839-attempt2", "js-min-dev-839-relocated",
             "5485d99f04e940e4f4109127513e0c0374879ec369a69536bf982deae7b5a1e0",
             {"dyn4k-core": "3ba3a41448928c38e3e16e8752d7b2338468bf0157a2bdfa70d71b0b9e8f757f",
              "dyn4k": "35f7be108fa3ae439ed025cece421e1ff9e7c3020eb47770a068bd1eeb4e8a53"}),
            ("wasmJs", "wasm-min-dev-839-attempt1", "wasm-min-dev-839-relocated",
             "0e18d29b28f055faed55888757cb6223e0463645b79ebe0b411f0a641dec5db2",
             {"dyn4k-core": "1adb166d23fc006159a3d16376c016a7b6560e1465c15bec252b5b7c68ed29a9",
              "dyn4k": "3d7b8fb339a4e60955c64be394edb225ee46b6cda52edc50dd735399f05442c0"}),
        )
        for target, original, relocated, digest, hashes in routes:
            lane = f"{target}:Firefox:minimum:development"
            for name in (original, relocated):
                with self.subTest(archive=name):
                    archive = base / name
                    self.assertEqual(independent_gates.archive_digest(archive), digest)
                    self.assertEqual(full_browser_consumer.verify(
                        repository, candidate, lane, archive, digest, browser,
                        hashes, browser_sha),
                        {"status": "PASSED", "lane": lane, "selected_cases": 2523,
                         "archive_sha256": digest, "candidate_sha": candidate})

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
        with self.assertRaisesRegex(ValueError, "public producer or central verifier (absent|differs from candidate)"):
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
                    expected["expected_build_launcher_image"] = {
                        "path": "/usr/bin/false", "sha256": "b" * 64}
                    with self.assertRaisesRegex(ValueError, "unused.*launcher"):
                        full_signed_routes.verify_browser(
                            ROOT, CANDIDATE, lane, archive, expected, HASHES,
                            runtime, "c" * 64)
                    del expected["expected_build_launcher_image"]
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
            receipt["process"] = {"graph": {"command": [toolchain["gradle"],
                                                        "qualificationEvidence"]}}
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
                          toolchain["java_sha256"])
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
                launcher_image = expected.pop("expected_build_launcher_image")
                with self.assertRaisesRegex(ValueError, "signed launcher process image"):
                    full_signed_routes.verify_browser(
                        ROOT, CANDIDATE, lane, archive, expected, HASHES, runtime,
                        "c" * 64)
                expected["expected_build_launcher_image"] = launcher_image
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
