import hashlib
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from receipt import EXPECTED_FINGERPRINT, TRUSTED_ADB, TRUSTED_ADB_SHA256, validate_receipt


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReceiptTests(unittest.TestCase):
    def test_runner_accepts_only_the_trusted_adb_argument(self):
        from receipt import validated_adb_argument

        self.assertEqual(str(TRUSTED_ADB), validated_adb_argument(TRUSTED_ADB))
        with self.assertRaises(ValueError):
            validated_adb_argument(Path("/tmp/adb"))

    def test_staged_native_process_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = {}
            for module in ("dyn4k-core", "dyn4k"):
                path = root / f"{module}-androidnativex64.klib"
                path.write_bytes(module.encode())
                artifacts[module] = {"path": str(path), "sha256": digest(path)}
            executable = root / "journey.kexe"
            elf = bytearray(64)
            elf[:5] = b"\x7fELF\x02"
            elf[5] = 1
            elf[18:20] = (62).to_bytes(2, "little")
            executable.write_bytes(elf)
            replacement_klib = root / "dyn4k-core-substitute.klib"
            replacement_klib.write_bytes(b"forged core")
            replacement_executable = root / "journey-substitute.kexe"
            replacement_executable.write_bytes(bytes(elf) + b"forged executable")
            labels = ("facade_body", "body_count", "world_step", "contact_begin", "contact_solve", "contact_present")
            dependency_report = root / "dependencies.txt"
            graph = (
                "androidNativeX64CompileKlibraries - Compile classpath\n"
                "+--- org.jetbrains.kotlin:kotlin-stdlib:2.4.20\n"
                "+--- io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1\n"
                "|    \\--- io.github.rubixhacker:dyn4k-core-androidnativex64:0.1.0-alpha.1\n"
                "\\--- io.github.rubixhacker:dyn4k:0.1.0-alpha.1\n"
                "     \\--- io.github.rubixhacker:dyn4k-androidnativex64:0.1.0-alpha.1\n"
            )
            dependency_report.write_text(graph)
            stage_log = root / "stage.log"
            stage_log.write_text(
                "> Task :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository\n"
                "> Task :dyn4k:publishKotlinMultiplatformPublicationToStagingRepository\n"
                "> Task :dyn4k-core:publishAndroidNativeX64PublicationToStagingRepository\n"
                "> Task :dyn4k:publishAndroidNativeX64PublicationToStagingRepository\n"
                "BUILD SUCCESSFUL\n")
            link_log = root / "link.log"
            link_log.write_text(
                "> Task :linkDebugExecutableAndroidNativeX64\n"
                "> Task :linkReleaseExecutableAndroidNativeX64\n"
                "BUILD SUCCESSFUL\n")
            forged_log = root / "forged-stage.log"
            forged_log.write_text("BUILD SUCCESSFUL\n")
            extra_reports = {}
            for name, line in (("project", "+--- project :extra\n"),
                               ("baseline", "+--- org.dyn4j:dyn4j:6.0.0\n"),
                               ("unapproved", "+--- com.example:other:1.0\n")):
                path = root / f"dependencies-{name}.txt"
                path.write_text(graph + line)
                extra_reports[name] = path
            stdout = "".join(f"ASSERT {label}\n" for label in labels) + "NATIVE_RESULT PASS 6\n"
            stdout_path = root / "stdout.txt"
            stdout_path.write_text(stdout)
            stderr_path = root / "stderr.txt"
            stderr_path.write_text("")
            forged_stdout_path = root / "forged-stdout.txt"
            forged_stdout_path.write_text(stdout + "ASSERT injected\n")
            guest_values = {
                "ro.boot.qemu.avd_name": "dyn4k_api37_play_x64",
                "ro.build.version.sdk": "37",
                "ro.build.fingerprint": EXPECTED_FINGERPRINT,
                "ro.product.cpu.abi": "x86_64",
                "ro.product.cpu.abilist": "x86_64,arm64-v8a",
                "sys.boot_completed": "1",
            }
            observations = {
                prop: {"command": [str(TRUSTED_ADB), "-P", "5038", "-s", "emulator-5558", "shell", "getprop", prop],
                       "stdout": value + "\n", "stderr": "", "exit_code": 0}
                for prop, value in guest_values.items()
            }
            pin_path = root / "tools/android-native-runtime/pins.json"
            pin_path.parent.mkdir(parents=True)
            pin_path.write_text(json.dumps({
                "schema": 1,
                "adb_sha256": TRUSTED_ADB_SHA256,
                "guest_fingerprint": EXPECTED_FINGERPRINT,
                "artifacts": {module: item["sha256"] for module, item in artifacts.items()},
                "executables": {"debug": digest(executable), "optimized": digest(executable)},
            }))
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "tools/android-native-runtime/pins.json"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-q", "-m", "pin fixture"], check=True)
            source_sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            source_tree = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True).strip()
            dependency_command = [str(root / "gradlew"), "-p", str(root / "consumers/android-native-runtime"),
                                  "--no-daemon", "--console=plain",
                                  f"-PstagingRepository={root / 'build/staging-repository'}",
                                  "dependencies", "--configuration", "androidNativeX64CompileKlibraries"]
            receipt = {
                "schema": 1,
                "status": "DIAGNOSTIC_PASSED",
                "source_sha": source_sha,
                "source_tree": source_tree,
                "pin_manifest_sha256": digest(pin_path),
                "variant": "debug",
                "tooling": {"adb_path": str(TRUSTED_ADB), "adb_sha256": TRUSTED_ADB_SHA256},
                "build_evidence": {
                    "stage": {"path": str(stage_log), "sha256": digest(stage_log)},
                    "link": {"path": str(link_log), "sha256": digest(link_log)},
                },
                "dependency_report": {"path": str(dependency_report), "sha256": digest(dependency_report),
                                      "command": dependency_command, "exit_code": 0},
                "artifacts": artifacts,
                "executable": {"path": str(executable), "sha256": digest(executable), "abi": "x86_64"},
                "guest": {"serial": "emulator-5558", "api": "37", "fingerprint": EXPECTED_FINGERPRINT, "primary_abi": "x86_64", "abi_list": "x86_64,arm64-v8a", "boot_completed": "1", "avd_name": "dyn4k_api37_play_x64", "observations": observations},
                "deployment": {"remote_sha256": digest(executable), "chmod_exit_code": 0},
                "process": {"command": [str(TRUSTED_ADB), "-P", "5038", "-s", "emulator-5558", "shell", "/data/local/tmp/dyn4k-native-debug"], "stdout": stdout, "stderr": "", "exit_code": 0,
                            "stdout_path": str(stdout_path), "stdout_sha256": digest(stdout_path), "stderr_path": str(stderr_path), "stderr_sha256": digest(stderr_path)},
                "assertion_count": 6,
            }
            self.assertEqual({"status": "CONSISTENCY_ONLY", "assertions": 6},
                             validate_receipt(receipt, source_sha, root))

            adverse = {
                "missing executable": lambda item: item["executable"].update(path=str(root / "missing.kexe")),
                "wrong ABI": lambda item: item["executable"].update(abi="arm64-v8a"),
                "wrong executable hash": lambda item: item["executable"].update(sha256="0" * 64),
                "wrong KLIB hash": lambda item: item["artifacts"]["dyn4k"].update(sha256="0" * 64),
                "no output": lambda item: item["process"].update(stdout=""),
                "no assertions": lambda item: item["process"].update(stdout="NATIVE_RESULT PASS 0\n", assertion_count=0),
                "self-consistent forged stdout": lambda item: item["process"].update(stdout=forged_stdout_path.read_text(), stdout_path=str(forged_stdout_path), stdout_sha256=digest(forged_stdout_path)),
                "nonzero exit": lambda item: item["process"].update(exit_code=1),
                "missing dependency report": lambda item: item.pop("dependency_report"),
                "wrong raw output hash": lambda item: item["process"].update(stdout_sha256="0" * 64),
                "missing deployment": lambda item: item.pop("deployment"),
                "forged ADB command": lambda item: item["process"]["command"].__setitem__(0, "/tmp/adb"),
                "wrong guest fingerprint": lambda item: item["guest"].update(fingerprint="made-up/other-guest"),
                "missing guest observations": lambda item: item["guest"].pop("observations"),
                "forged guest query": lambda item: item["guest"]["observations"]["ro.build.fingerprint"]["command"].__setitem__(0, "/tmp/adb"),
                "changed guest query output": lambda item: item["guest"]["observations"]["ro.product.cpu.abi"].update(stdout="arm64-v8a\n"),
                "wrong source tree": lambda item: item.update(source_tree="0" * 40),
                "self-consistent substituted KLIB": lambda item: item["artifacts"]["dyn4k-core"].update(path=str(replacement_klib), sha256=digest(replacement_klib)),
                "self-consistent substituted executable": lambda item: (item["executable"].update(path=str(replacement_executable), sha256=digest(replacement_executable)), item["deployment"].update(remote_sha256=digest(replacement_executable))),
                "extra project dependency": lambda item: item["dependency_report"].update(path=str(extra_reports["project"]), sha256=digest(extra_reports["project"])),
                "baseline provider dependency": lambda item: item["dependency_report"].update(path=str(extra_reports["baseline"]), sha256=digest(extra_reports["baseline"])),
                "unapproved provider dependency": lambda item: item["dependency_report"].update(path=str(extra_reports["unapproved"]), sha256=digest(extra_reports["unapproved"])),
                "forged dependency command": lambda item: item["dependency_report"]["command"].__setitem__(0, "/tmp/gradlew"),
                "failed dependency command": lambda item: item["dependency_report"].update(exit_code=1),
                "forged ADB image hash": lambda item: item["tooling"].update(adb_sha256="0" * 64),
                "forged ADB image path": lambda item: item["tooling"].update(adb_path="/tmp/adb"),
                "changed stage log hash": lambda item: item["build_evidence"]["stage"].update(sha256="0" * 64),
                "self-consistent forged stage log": lambda item: item["build_evidence"]["stage"].update(path=str(forged_log), sha256=digest(forged_log)),
                "altered pin manifest digest": lambda item: item.update(pin_manifest_sha256="0" * 64),
            }
            for name, change in adverse.items():
                with self.subTest(name=name):
                    invalid = copy.deepcopy(receipt)
                    change(invalid)
                    with self.assertRaises(ValueError):
                        validate_receipt(invalid, source_sha, root)

            with self.subTest(name="self-consistent altered working manifest and receipt"):
                working_pins = json.loads(pin_path.read_text())
                working_pins["artifacts"]["dyn4k-core"] = digest(replacement_klib)
                working_pins["executables"]["debug"] = digest(replacement_executable)
                pin_path.write_text(json.dumps(working_pins))
                invalid = copy.deepcopy(receipt)
                invalid["pin_manifest_sha256"] = digest(pin_path)
                invalid["artifacts"]["dyn4k-core"].update(path=str(replacement_klib), sha256=digest(replacement_klib))
                invalid["executable"].update(path=str(replacement_executable), sha256=digest(replacement_executable))
                invalid["deployment"]["remote_sha256"] = digest(replacement_executable)
                with self.assertRaises(ValueError):
                    validate_receipt(invalid, source_sha, root)


if __name__ == "__main__":
    unittest.main()
