import hashlib
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from receipt import validate_receipt


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReceiptTests(unittest.TestCase):
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
            labels = ("facade_body", "body_count", "world_step", "contact_begin", "contact_solve", "contact_present")
            dependency_report = root / "dependencies.txt"
            dependency_report.write_text("io.github.rubixhacker:dyn4k-core-androidnativex64:0.1.0-alpha.1\nio.github.rubixhacker:dyn4k-androidnativex64:0.1.0-alpha.1\n")
            stdout = "".join(f"ASSERT {label}\n" for label in labels) + "NATIVE_RESULT PASS 6\n"
            stdout_path = root / "stdout.txt"
            stdout_path.write_text(stdout)
            stderr_path = root / "stderr.txt"
            stderr_path.write_text("")
            receipt = {
                "schema": 1,
                "status": "DIAGNOSTIC_PASSED",
                "source_sha": "a" * 40,
                "source_tree": "b" * 40,
                "variant": "debug",
                "dependency_report": {"path": str(dependency_report), "sha256": digest(dependency_report)},
                "artifacts": artifacts,
                "executable": {"path": str(executable), "sha256": digest(executable), "abi": "x86_64"},
                "guest": {"serial": "emulator-5558", "api": "37", "fingerprint": "example/test", "primary_abi": "x86_64", "boot_completed": "1", "avd_name": "dyn4k_api37_play_x64"},
                "deployment": {"remote_sha256": digest(executable), "chmod_exit_code": 0},
                "process": {"command": ["adb", "-P", "5038", "-s", "emulator-5558", "shell", "/data/local/tmp/dyn4k-native-debug"], "stdout": stdout, "stderr": "", "exit_code": 0,
                            "stdout_path": str(stdout_path), "stdout_sha256": digest(stdout_path), "stderr_path": str(stderr_path), "stderr_sha256": digest(stderr_path)},
                "assertion_count": 6,
            }
            self.assertEqual(6, validate_receipt(receipt, "a" * 40))

            adverse = {
                "missing executable": lambda item: item["executable"].update(path=str(root / "missing.kexe")),
                "wrong ABI": lambda item: item["executable"].update(abi="arm64-v8a"),
                "wrong executable hash": lambda item: item["executable"].update(sha256="0" * 64),
                "wrong KLIB hash": lambda item: item["artifacts"]["dyn4k"].update(sha256="0" * 64),
                "no output": lambda item: item["process"].update(stdout=""),
                "no assertions": lambda item: item["process"].update(stdout="NATIVE_RESULT PASS 0\n", assertion_count=0),
                "nonzero exit": lambda item: item["process"].update(exit_code=1),
                "missing dependency report": lambda item: item.pop("dependency_report"),
                "wrong raw output hash": lambda item: item["process"].update(stdout_sha256="0" * 64),
                "missing deployment": lambda item: item.pop("deployment"),
            }
            for name, change in adverse.items():
                with self.subTest(name=name):
                    invalid = copy.deepcopy(receipt)
                    change(invalid)
                    with self.assertRaises(ValueError):
                        validate_receipt(invalid, "a" * 40)


if __name__ == "__main__":
    unittest.main()
