import hashlib
import re
from pathlib import Path


ASSERTIONS = (
    "facade_body",
    "body_count",
    "world_step",
    "contact_begin",
    "contact_solve",
    "contact_present",
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def elf_abi(path):
    header = path.read_bytes()[:20]
    if len(header) < 20 or header[:6] != b"\x7fELF\x02\x01":
        raise ValueError("executable is not a 64-bit little-endian ELF")
    if int.from_bytes(header[18:20], "little") != 62:
        raise ValueError("executable is not x86_64")
    return "x86_64"


def validate_receipt(receipt, expected_sha):
    if receipt.get("source_sha") != expected_sha or not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("source SHA differs")
    variant = receipt.get("variant")
    if variant not in ("debug", "optimized"):
        raise ValueError("unknown native variant")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"dyn4k-core", "dyn4k"}:
        raise ValueError("both staged KLIBs are required")
    for module, record in artifacts.items():
        path = Path(record["path"])
        if not path.is_file() or path.suffix != ".klib" or module not in path.name:
            raise ValueError(f"missing staged KLIB: {module}")
        if sha256(path) != record.get("sha256"):
            raise ValueError(f"staged KLIB hash differs: {module}")
    record = receipt.get("executable") or {}
    path = Path(record.get("path", ""))
    if not path.is_file():
        raise ValueError("missing native executable")
    if record.get("sha256") != sha256(path):
        raise ValueError("native executable hash differs")
    if record.get("abi") != elf_abi(path):
        raise ValueError("native executable ABI differs")
    guest = receipt.get("guest") or {}
    if (guest.get("serial") != "emulator-5558" or guest.get("primary_abi") != "x86_64"
            or guest.get("boot_completed") != "1" or not str(guest.get("api", "")).isdigit()
            or not guest.get("fingerprint") or guest.get("avd_name") != "dyn4k_api37_play_x64"):
        raise ValueError("guest identity is incomplete or wrong ABI")
    process = receipt.get("process") or {}
    command = process.get("command")
    remote = f"/data/local/tmp/dyn4k-native-{variant}"
    if (not isinstance(command, list) or len(command) != 7 or Path(command[0]).name != "adb"
            or command[1:] != ["-P", "5038", "-s", "emulator-5558", "shell", remote]):
        raise ValueError("native process command differs")
    if process.get("exit_code") != 0:
        raise ValueError("native process exited nonzero")
    stdout = process.get("stdout")
    if not isinstance(stdout, str) or not stdout:
        raise ValueError("native process produced no output")
    lines = stdout.splitlines()
    expected = [f"ASSERT {name}" for name in ASSERTIONS] + [f"NATIVE_RESULT PASS {len(ASSERTIONS)}"]
    if lines != expected or receipt.get("assertion_count") != len(ASSERTIONS):
        raise ValueError("native assertions are absent or differ")
    return len(ASSERTIONS)
