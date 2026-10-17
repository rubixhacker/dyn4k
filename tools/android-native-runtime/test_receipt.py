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
            receipt = {
                "source_sha": "a" * 40,
                "variant": "debug",
                "artifacts": artifacts,
                "executable": {"path": str(executable), "sha256": digest(executable), "abi": "x86_64"},
                "guest": {"serial": "emulator-5558", "api": "37", "fingerprint": "example/test", "primary_abi": "x86_64", "boot_completed": "1", "avd_name": "dyn4k_api37_play_x64"},
                "process": {"command": ["adb", "-P", "5038", "-s", "emulator-5558", "shell", "/data/local/tmp/dyn4k-native-debug"], "stdout": "".join(f"ASSERT {label}\n" for label in labels) + "NATIVE_RESULT PASS 6\n", "stderr": "", "exit_code": 0},
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
            }
            for name, change in adverse.items():
                with self.subTest(name=name):
                    invalid = copy.deepcopy(receipt)
                    change(invalid)
                    with self.assertRaises(ValueError):
                        validate_receipt(invalid, "a" * 40)


if __name__ == "__main__":
    unittest.main()
