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
    if receipt.get("schema") != 1 or receipt.get("status") != "DIAGNOSTIC_PASSED":
        raise ValueError("receipt status or schema differs")
    if receipt.get("source_sha") != expected_sha or not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("source SHA differs")
    if not re.fullmatch(r"[0-9a-f]{40}", str(receipt.get("source_tree", ""))):
        raise ValueError("source tree is absent")
    variant = receipt.get("variant")
    if variant not in ("debug", "optimized"):
        raise ValueError("unknown native variant")
    report = receipt.get("dependency_report") or {}
    report_path = Path(report.get("path", ""))
    if not report_path.is_file() or sha256(report_path) != report.get("sha256"):
        raise ValueError("dependency report is absent or changed")
    graph = report_path.read_text()
    for module in ("dyn4k-core", "dyn4k"):
        if f"io.github.rubixhacker:{module}-androidnativex64:0.1.0-alpha.1" not in graph:
            raise ValueError(f"staged dependency is absent: {module}")
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
            or guest.get("boot_completed") != "1" or guest.get("api") != "37"
            or not guest.get("fingerprint") or guest.get("avd_name") != "dyn4k_api37_play_x64"):
        raise ValueError("guest identity is incomplete or wrong ABI")
    deployment = receipt.get("deployment") or {}
    if deployment.get("remote_sha256") != record.get("sha256") or deployment.get("chmod_exit_code") != 0:
        raise ValueError("deployed executable differs")
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
    for stream in ("stdout", "stderr"):
        raw_path = Path(process.get(f"{stream}_path", ""))
        if (not raw_path.is_file() or not isinstance(process.get(stream), str)
                or raw_path.read_text() != process[stream]
                or sha256(raw_path) != process.get(f"{stream}_sha256")):
            raise ValueError(f"raw {stream} differs")
    lines = stdout.splitlines()
    expected = [f"ASSERT {name}" for name in ASSERTIONS] + [f"NATIVE_RESULT PASS {len(ASSERTIONS)}"]
    if lines != expected or receipt.get("assertion_count") != len(ASSERTIONS):
        raise ValueError("native assertions are absent or differ")
    return len(ASSERTIONS)
