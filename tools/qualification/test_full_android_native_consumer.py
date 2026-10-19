import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import full_android_native_consumer as route
import independent_gates


REPOSITORY = Path(__file__).resolve().parents[2]


class AndroidNativeConsumerTests(unittest.TestCase):
    def test_public_verifier_rejects_resealed_provenance_and_path_aliases(self):
        source_name = os.environ.get("DYN4K_FULL_ANDROID_NATIVE_ARCHIVE")
        if not source_name:
            self.skipTest("set DYN4K_FULL_ANDROID_NATIVE_ARCHIVE to a retained live archive")
        source = Path(source_name)
        receipt = json.loads((source / "receipt.json").read_bytes())
        lane = receipt["lane"]
        serial = json.loads((source / "guest.json").read_bytes())["serial"]

        def rejected(archive, reason):
            with patch.object(route, "guest_query", side_effect=AssertionError("live replay reached")):
                with self.assertRaisesRegex(ValueError, reason):
                    route.verify(REPOSITORY, receipt["candidate_sha"], lane, archive,
                                 independent_gates.archive_digest(archive),
                                 receipt["artifact_hashes"], receipt["runtime_identity"],
                                 receipt["executable_hashes"], receipt["toolchain"],
                                 Path("/home/stewart/Android/Sdk/platform-tools/adb"),
                                 serial, Path(archive).parent / "unused-replay")

        with tempfile.TemporaryDirectory(dir=os.environ.get("DYN4K_FULL_ANDROID_NATIVE_TMPDIR")) as directory:
            root = Path(directory)
            alias = root / "archive-link"
            alias.symlink_to(source, target_is_directory=True)
            with self.subTest("root symlink"):
                rejected(alias, "archive root is a symlink")
            for name, relative, replacement in (
                ("forged-gradle", "process/gradle.stdout",
                 b"> Task :core:linkDebugTestAndroidNativeX64\n"
                 b"> Task :facade:linkDebugTestAndroidNativeX64\nBUILD SUCCESSFUL\n"),
                ("forged-push", "process/core-push.stderr", b"1 file pushed\n"),
                ("forged-guest-stderr", "process/core-guest.stderr", b"guest failed\n"),
                ("forged-remote-hash", "process/core-remote-hash.stdout",
                 receipt["executable_hashes"]["core"].encode() + b"  /data/local/tmp/foreign\n"),
            ):
                target = root / name
                shutil.copytree(source, target, copy_function=shutil.copy2)
                file = target / relative
                mtime = file.stat().st_mtime_ns
                file.write_bytes(replacement)
                os.utime(file, ns=(mtime, mtime))
                changed = json.loads((target / "receipt.json").read_bytes())
                next(item for item in changed["files"] if item["path"] == relative)["sha256"] = route.digest(file)
                (target / "receipt.json").write_bytes(route.encoded(changed) + b"\n")
                with self.subTest(name):
                    rejected(target, {"forged-gradle": "gradle process output digest",
                                      "forged-push": "core-push process output digest",
                                      "forged-guest-stderr": "core-guest process output digest",
                                      "forged-remote-hash": "core-remote-hash process output digest"}[name])
            for name, key, value, reason in (
                ("wrong-gradle-argv", "command", ["/bin/true"],
                 "gradle command, exit, path, or window"),
                ("wrong-gradle-tool", "gradle_sha256", "0" * 64,
                 "original link inputs, outputs, or tool differ"),
            ):
                target = root / name
                shutil.copytree(source, target, copy_function=shutil.copy2)
                file = target / "build.json"
                build = json.loads(file.read_bytes())
                if key == "command":
                    build["process"][key] = value
                else:
                    build[key] = value
                mtime = file.stat().st_mtime_ns
                file.write_bytes(route.encoded(build) + b"\n")
                os.utime(file, ns=(mtime, mtime))
                changed = json.loads((target / "receipt.json").read_bytes())
                next(item for item in changed["files"] if item["path"] == "build.json")["sha256"] = route.digest(file)
                (target / "receipt.json").write_bytes(route.encoded(changed) + b"\n")
                with self.subTest(name):
                    rejected(target, reason)
            for name, operation, key, value in (
                ("failed-push", "push", "exit_code", 1),
                ("wrong-chmod", "chmod", "command", ["/bin/false"]),
                ("reordered-proof", "remote_hash", "started_ns", 1),
            ):
                target = root / name
                shutil.copytree(source, target, copy_function=shutil.copy2)
                file = target / "runtime.json"
                runtime = json.loads(file.read_bytes())
                runtime["core"]["operations"][operation][key] = value
                mtime = file.stat().st_mtime_ns
                file.write_bytes(route.encoded(runtime) + b"\n")
                os.utime(file, ns=(mtime, mtime))
                changed = json.loads((target / "receipt.json").read_bytes())
                next(item for item in changed["files"] if item["path"] == "runtime.json")["sha256"] = route.digest(file)
                (target / "receipt.json").write_bytes(route.encoded(changed) + b"\n")
                with self.subTest(name):
                    rejected(target, {"push": "core-push command, exit, path, or window",
                                      "chmod": "core-chmod command, exit, path, or window",
                                      "remote_hash": "core-remote-hash command, exit, path, or window"}[operation])
            hardlinked = root / "hardlinked"
            shutil.copytree(source, hardlinked, copy_function=shutil.copy2)
            file = hardlinked / "process/core-push.stdout"
            outside = root / "external-link"
            file.replace(outside)
            os.link(outside, file)
            with self.subTest("external hardlink"):
                rejected(hardlinked, "hardlinked raw file")

    def test_transport_package_restores_nanosecond_archive_metadata(self):
        source_name = os.environ.get("DYN4K_FULL_ANDROID_NATIVE_ARCHIVE")
        if not source_name:
            self.skipTest("set DYN4K_FULL_ANDROID_NATIVE_ARCHIVE to a retained live archive")
        source = Path(source_name)
        archive_digest = independent_gates.archive_digest(source)
        with tempfile.TemporaryDirectory(dir=os.environ.get("DYN4K_FULL_ANDROID_NATIVE_TMPDIR")) as directory:
            root = Path(directory)
            package = root / "transport.zip"
            target = root / "restored"
            self.assertEqual(route.pack(source, archive_digest, package), route.digest(package))
            self.assertEqual(route.unpack(package, target, archive_digest), target)
            self.assertEqual(independent_gates.archive_digest(target), archive_digest)
            self.assertEqual(route.authenticate(target, archive_digest)["lane"],
                             json.loads((source / "receipt.json").read_bytes())["lane"])

    def test_api21_public_verifier_rejects_resealed_pull_and_installed_bytes(self):
        source_name = os.environ.get("DYN4K_FULL_ANDROID_NATIVE_API21_ARCHIVE")
        if not source_name:
            self.skipTest("set DYN4K_FULL_ANDROID_NATIVE_API21_ARCHIVE to a retained live archive")
        source = Path(source_name)
        receipt = json.loads((source / "receipt.json").read_bytes())
        self.assertEqual(receipt["api"], 21)
        serial = json.loads((source / "guest.json").read_bytes())["serial"]

        def failed_pull(raw):
            runtime = json.loads(raw)
            runtime["core"]["operations"]["pull"]["exit_code"] = 1
            return route.encoded(runtime) + b"\n"

        with tempfile.TemporaryDirectory(dir=os.environ.get("DYN4K_FULL_ANDROID_NATIVE_TMPDIR")) as directory:
            for name, relative, mutate, reason in (
                ("pull-path", "runtime.json", lambda raw: raw.replace(
                    b'"installed/core.kexe"', b'"installed/foreign.kexe"', 1),
                 "pulled API 21 guest executable hash differs"),
                ("failed-pull", "runtime.json", failed_pull,
                 "core-pull command, exit, path, or window"),
                ("pulled-bytes", "installed/core.kexe", lambda raw: raw + b"forged",
                 "pulled API 21 guest executable hash differs"),
            ):
                target = Path(directory) / name
                shutil.copytree(source, target, copy_function=shutil.copy2)
                file = target / relative
                mtime = file.stat().st_mtime_ns
                file.write_bytes(mutate(file.read_bytes()))
                os.utime(file, ns=(mtime, mtime))
                changed = json.loads((target / "receipt.json").read_bytes())
                next(item for item in changed["files"] if item["path"] == relative)["sha256"] = route.digest(file)
                (target / "receipt.json").write_bytes(route.encoded(changed) + b"\n")
                with self.subTest(name), patch.object(route, "guest_query", side_effect=AssertionError("live replay reached")):
                    with self.assertRaisesRegex(ValueError, reason):
                        route.verify(REPOSITORY, receipt["candidate_sha"], receipt["lane"],
                                     target, independent_gates.archive_digest(target),
                                     receipt["artifact_hashes"], receipt["runtime_identity"],
                                     receipt["executable_hashes"], receipt["toolchain"],
                                     Path("/home/stewart/Android/Sdk/platform-tools/adb"),
                                     serial, Path(directory) / "unused-replay")

    def test_all_sixteen_approved_lanes_have_distinct_abi_and_mode(self):
        manifest = route.approved_manifest(REPOSITORY)
        lanes = route.lanes(manifest)
        self.assertEqual(len(lanes), 16)
        self.assertEqual({route.route(lane)["abi"] for lane in lanes},
                         {"armeabi-v7a", "arm64-v8a", "x86", "x86_64"})
        self.assertEqual({route.route(lane)["api"] for lane in lanes}, {21, 37})
        self.assertEqual({route.route(lane)["link"] for lane in lanes},
                         {"Debug", "Release"})

    def test_original_guest_rows_require_one_pass_per_selected_method(self):
        expected = {"dyn4k-core:a.B#one": ("a.B", "one"),
                    "dyn4k-core:a.B#two": ("a.B", "two")}
        raw = (b"[==========] Running 2 tests from 1 test cases.\n"
               b"[ RUN      ] a.B.one\n[       OK ] a.B.one (1 ms)\n"
               b"[ RUN      ] a.B.two\n[       OK ] a.B.two (2 ms)\n"
               b"[==========] 2 tests from 1 test cases ran. (3 ms total)\n"
               b"[  PASSED  ] 2 tests.\n")
        ids, xml = route.parse_guest(raw, expected)
        self.assertEqual(ids, list(expected))
        self.assertIn(b'dyn4k-core:a.B#one', xml)
        api21_ids, api21_xml = route.parse_guest(raw.replace(b"\n", b"\r\n"), expected)
        self.assertEqual(api21_ids, ids)
        self.assertEqual(api21_xml, xml)
        for altered in (raw.replace(b"one (1 ms)", b"two (1 ms)"),
                        raw.replace(b"[       OK ] a.B.two (2 ms)", b""),
                        raw.replace(b"[       OK ] a.B.two", b"[  FAILED  ] a.B.two"),
                        raw.replace(b"[  PASSED  ] 2", b"[  PASSED  ] 1")):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                route.parse_guest(altered, expected)

    def test_guest_and_executable_must_match_lane(self):
        lane = "androidNativeX64:Android Native x86_64:current:debug-g"
        selected = route.route(lane)
        guest = {"api": "37", "primary_abi": "x86_64", "abi_list": "x86_64,x86",
                 "boot_completed": "1", "serial": "emulator-5558", "pid": "123",
                 "fingerprint": "google/test"}
        route.check_guest(selected, guest)
        for key, value in (("api", "21"), ("primary_abi", "x86"),
                           ("serial", "emulator-5560"), ("pid", "")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                route.check_guest(selected, {**guest, key: value})
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "test.kexe"
            binary.write_bytes(b"linked")
            with self.assertRaisesRegex(ValueError, "ELF"):
                route.check_executable(binary, selected)

    def test_mode_and_provider_graph_cannot_substitute_another_binary(self):
        selected = route.route("androidNativeX64:Android Native x86_64:current:optimized-opt")
        command = route.build_command(Path("/source"), Path("/staging"),
                                      Path("/archive"), Path("/work"),
                                      Path("/gradle"), selected,
                                      {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64})
        self.assertIn(":core:linkReleaseTestAndroidNativeX64", command)
        self.assertIn(":facade:linkReleaseTestAndroidNativeX64", command)
        self.assertNotIn(":core:linkDebugTestAndroidNativeX64", command)
        self.assertEqual(route.build_program(Path("/work"), "core", selected),
                         Path("/work/core/bin/androidNativeX64/releaseTest/test.kexe"))
        components = ["io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1",
                      "io.github.rubixhacker:dyn4k:0.1.0-alpha.1",
                      "io.github.rubixhacker:dyn4k-core-androidnativex64:0.1.0-alpha.1",
                      "io.github.rubixhacker:dyn4k-androidnativex64:0.1.0-alpha.1"]
        artifacts = [{"component": components[2], "sha256": "a" * 64, "size": 1},
                     {"component": components[3], "sha256": "b" * 64, "size": 1}]
        rows = [{"project": module, "configuration": "androidNativeX64TestCompileKlibraries",
                 "components": components, "artifacts": artifacts}
                for module in ("core", "facade")]
        graph = {"compile": rows}
        hashes = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
        self.assertTrue(route.verify_graph(graph, selected["target"], hashes))
        for altered in (lambda value: value["compile"][0]["components"].append(
                            "org.dyn4j:dyn4j:6.0.0"),
                        lambda value: value["compile"][1]["artifacts"][0].update(
                            sha256="c" * 64),
                        lambda value: value["compile"][0]["artifacts"].append(
                            value["compile"][0]["artifacts"][0])):
            changed = copy.deepcopy(graph)
            altered(changed)
            with self.assertRaises(ValueError):
                route.verify_graph(changed, selected["target"], hashes)

    def test_api21_hashes_pulled_installed_binary(self):
        lane = "androidNativeX64:Android Native x86_64:minimum:debug-g"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "linked.kexe"
            binary.write_bytes(b"linked binary")
            seen = []

            def device(command, **kwargs):
                seen.append(command)
                if "pull" in command:
                    Path(command[-1]).write_bytes(binary.read_bytes())
                output = (b"QUALIFICATION_LANE=" + lane.encode() +
                          b"\nQUALIFICATION_GUEST_PID=123\n") if "-c" in command else b""
                return {"command": command, "exit_code": 0, "stdout": output,
                        "stderr": b"", "started_ns": 1, "finished_ns": 2}

            with patch.object(route, "checked", side_effect=device):
                record = route.run_guest("/adb", "emulator-5560", "/data/local/tmp/test",
                                         binary, lane, root, "core")
            self.assertEqual(record["installed_path"], "installed/core.kexe")
            self.assertEqual((root / record["installed_path"]).read_bytes(), binary.read_bytes())
            self.assertTrue(any("pull" in command for command in seen))
            self.assertFalse(any("sha256sum" in command for command in seen))


if __name__ == "__main__":
    unittest.main()
