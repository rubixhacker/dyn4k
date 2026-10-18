import hashlib
import json
import re
import subprocess
from pathlib import Path


ASSERTIONS = (
    "facade_body",
    "body_count",
    "world_step",
    "contact_begin",
    "contact_solve",
    "contact_present",
)
TRUSTED_ADB = Path("/home/stewart/Android/Sdk/platform-tools/adb")
TRUSTED_ADB_SHA256 = "a902be8f45c6c62e76c9efaf6947a0fa747c9cabd89a2ac8e0d16ecb30b3ed01"
EXPECTED_FINGERPRINT = "google/sdk_gphone64_x86_64/emu64xa:17/CE2A.260420.019/15611780:user/release-keys"
GUEST_PROPERTIES = {
    "ro.boot.qemu.avd_name": "avd_name",
    "ro.build.version.sdk": "api",
    "ro.build.fingerprint": "fingerprint",
    "ro.product.cpu.abi": "primary_abi",
    "ro.product.cpu.abilist": "abi_list",
    "sys.boot_completed": "boot_completed",
}
PIN_PATH = "tools/android-native-runtime/pins.json"
ALLOWED_COMPONENTS = {
    "org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
    "io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1",
    "io.github.rubixhacker:dyn4k-core-androidnativex64:0.1.0-alpha.1",
    "io.github.rubixhacker:dyn4k:0.1.0-alpha.1",
    "io.github.rubixhacker:dyn4k-androidnativex64:0.1.0-alpha.1",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trusted_adb():
    if not TRUSTED_ADB.is_file() or sha256(TRUSTED_ADB) != TRUSTED_ADB_SHA256:
        raise ValueError("trusted SDK ADB is missing or changed")
    return str(TRUSTED_ADB)


def validated_adb_argument(candidate):
    adb = trusted_adb()
    if Path(candidate) != TRUSTED_ADB:
        raise ValueError("ADB path differs from the trusted SDK tool")
    return adb


def git_output(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"Git object is unavailable: {args}")
    return result.stdout


def load_pins(root, source_sha):
    raw = git_output(root, "show", f"{source_sha}:{PIN_PATH}")
    pins = json.loads(raw)
    if (pins.get("schema") != 1 or pins.get("adb_sha256") != TRUSTED_ADB_SHA256
            or pins.get("guest_fingerprint") != EXPECTED_FINGERPRINT
            or set(pins.get("artifacts", {})) != {"dyn4k-core", "dyn4k"}
            or set(pins.get("executables", {})) != {"debug", "optimized"}):
        raise ValueError("committed build pin manifest is incomplete")
    return pins, hashlib.sha256(raw).hexdigest()


def dependency_command(root):
    root = Path(root).resolve()
    return [str(root / "gradlew"), "-p", str(root / "consumers/android-native-runtime"),
            "--no-daemon", "--console=plain",
            f"-PstagingRepository={root / 'build/staging-repository'}",
            "dependencies", "--configuration", "androidNativeX64CompileKlibraries"]


def validate_dependency_graph(graph):
    if "project :" in graph or "org.dyn4j:dyn4j" in graph:
        raise ValueError("dependency graph contains a project or baseline provider")
    lines = graph.splitlines()
    headers = [index for index, line in enumerate(lines)
               if line.startswith("androidNativeX64CompileKlibraries -")]
    if len(headers) != 1:
        raise ValueError("native compile dependency graph is absent or duplicated")
    seen = set()
    for line in lines[headers[0] + 1:]:
        if not line.strip():
            break
        match = re.search(r"(?:\+---|\\---)\s+(.+)$", line)
        if not match:
            raise ValueError(f"unrecognized native dependency line: {line}")
        component = match.group(1).removesuffix(" (*)").strip()
        if component not in ALLOWED_COMPONENTS:
            raise ValueError(f"unapproved native dependency: {component}")
        seen.add(component)
    if seen != ALLOWED_COMPONENTS:
        raise ValueError("required staged native dependency is absent")


def elf_abi(path):
    header = path.read_bytes()[:20]
    if len(header) < 20 or header[:6] != b"\x7fELF\x02\x01":
        raise ValueError("executable is not a 64-bit little-endian ELF")
    if int.from_bytes(header[18:20], "little") != 62:
        raise ValueError("executable is not x86_64")
    return "x86_64"


def validate_receipt(receipt, expected_sha, source_root):
    if receipt.get("schema") != 1 or receipt.get("status") != "DIAGNOSTIC_PASSED":
        raise ValueError("receipt status or schema differs")
    if receipt.get("source_sha") != expected_sha or not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("source SHA differs")
    source_tree = git_output(source_root, "rev-parse", f"{expected_sha}^{{tree}}").decode().strip()
    if receipt.get("source_tree") != source_tree:
        raise ValueError("source tree differs from the Git object")
    pins, pin_digest = load_pins(source_root, expected_sha)
    if receipt.get("pin_manifest_sha256") != pin_digest:
        raise ValueError("committed build pin manifest differs")
    variant = receipt.get("variant")
    if variant not in ("debug", "optimized"):
        raise ValueError("unknown native variant")
    if receipt.get("tooling") != {"adb_path": trusted_adb(), "adb_sha256": TRUSTED_ADB_SHA256}:
        raise ValueError("ADB tool path or image hash differs")
    evidence = receipt.get("build_evidence") or {}
    if set(evidence) != {"stage", "link"}:
        raise ValueError("build logs are incomplete")
    required_log_text = {
        "stage": (":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
                  ":dyn4k:publishKotlinMultiplatformPublicationToStagingRepository",
                  ":dyn4k-core:publishAndroidNativeX64PublicationToStagingRepository",
                  ":dyn4k:publishAndroidNativeX64PublicationToStagingRepository"),
        "link": (":linkDebugExecutableAndroidNativeX64", ":linkReleaseExecutableAndroidNativeX64"),
    }
    for name, markers in required_log_text.items():
        log = evidence[name]
        log_path = Path(log.get("path", ""))
        if not log_path.is_file() or sha256(log_path) != log.get("sha256"):
            raise ValueError(f"{name} log is absent or changed")
        content = log_path.read_text()
        if "BUILD SUCCESSFUL" not in content or any(marker not in content for marker in markers):
            raise ValueError(f"{name} log does not show required tasks")
    report = receipt.get("dependency_report") or {}
    if report.get("command") != dependency_command(source_root) or report.get("exit_code") != 0:
        raise ValueError("native dependency command differs or failed")
    report_path = Path(report.get("path", ""))
    if not report_path.is_file() or sha256(report_path) != report.get("sha256"):
        raise ValueError("dependency report is absent or changed")
    graph = report_path.read_text()
    validate_dependency_graph(graph)
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"dyn4k-core", "dyn4k"}:
        raise ValueError("both staged KLIBs are required")
    for module, record in artifacts.items():
        path = Path(record["path"])
        if not path.is_file() or path.suffix != ".klib" or module not in path.name:
            raise ValueError(f"missing staged KLIB: {module}")
        if sha256(path) != record.get("sha256"):
            raise ValueError(f"staged KLIB hash differs: {module}")
        if record["sha256"] != pins["artifacts"][module]:
            raise ValueError(f"staged KLIB differs from committed build pin: {module}")
    record = receipt.get("executable") or {}
    path = Path(record.get("path", ""))
    if not path.is_file():
        raise ValueError("missing native executable")
    if record.get("sha256") != sha256(path):
        raise ValueError("native executable hash differs")
    if record["sha256"] != pins["executables"][variant]:
        raise ValueError("native executable differs from committed build pin")
    if record.get("abi") != elf_abi(path):
        raise ValueError("native executable ABI differs")
    guest = receipt.get("guest") or {}
    if (guest.get("serial") != "emulator-5558" or guest.get("primary_abi") != "x86_64"
            or guest.get("boot_completed") != "1" or guest.get("api") != "37"
            or guest.get("fingerprint") != EXPECTED_FINGERPRINT
            or guest.get("avd_name") != "dyn4k_api37_play_x64"):
        raise ValueError("guest identity is incomplete or wrong ABI")
    observations = guest.get("observations")
    if not isinstance(observations, dict) or set(observations) != set(GUEST_PROPERTIES):
        raise ValueError("guest property observations are incomplete")
    adb = trusted_adb()
    for prop, field in GUEST_PROPERTIES.items():
        observation = observations[prop]
        if (observation.get("command") != [adb, "-P", "5038", "-s", "emulator-5558", "shell", "getprop", prop]
                or observation.get("exit_code") != 0 or observation.get("stderr") != ""
                or not isinstance(observation.get("stdout"), str)
                or observation["stdout"].strip() != guest.get(field)):
            raise ValueError(f"guest property observation differs: {prop}")
    deployment = receipt.get("deployment") or {}
    if deployment.get("remote_sha256") != record.get("sha256") or deployment.get("chmod_exit_code") != 0:
        raise ValueError("deployed executable differs")
    process = receipt.get("process") or {}
    command = process.get("command")
    remote = f"/data/local/tmp/dyn4k-native-{variant}"
    if (not isinstance(command, list) or len(command) != 7 or command[0] != trusted_adb()
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
    return {"status": "CONSISTENCY_ONLY", "assertions": len(ASSERTIONS)}
