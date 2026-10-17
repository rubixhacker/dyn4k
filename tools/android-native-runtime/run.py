import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from receipt import ASSERTIONS, elf_abi, sha256, validate_receipt


VERSION = "0.1.0-alpha.1"
MODULES = ("dyn4k-core", "dyn4k")


def command(argv, *, check=True):
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise ValueError(f"command failed ({result.returncode}): {argv}: {result.stderr.strip()}")
    return result


def git(root, *args):
    return command(["git", "-C", str(root), *args]).stdout.strip()


def staged_klibs(staging):
    records = {}
    for module in MODULES:
        publication = f"{module}-androidnativex64"
        path = staging / "io/github/rubixhacker" / publication / VERSION / f"{publication}-{VERSION}.klib"
        if not path.is_file():
            raise ValueError(f"missing staged KLIB: {path}")
        records[module] = {"path": str(path.resolve()), "sha256": sha256(path)}
    return records


def query_guest(adb):
    devices = command(adb[:3] + ["devices", "-l"]).stdout
    lines = [line for line in devices.splitlines() if line.startswith("emulator-")]
    if len(lines) != 1 or lines[0].split()[:2] != ["emulator-5558", "device"]:
        raise ValueError(f"isolated ADB server has unexpected devices: {lines}")
    def prop(name):
        return command(adb + ["shell", "getprop", name]).stdout.strip()
    return {
        "serial": "emulator-5558",
        "avd_name": prop("ro.boot.qemu.avd_name"),
        "api": prop("ro.build.version.sdk"),
        "fingerprint": prop("ro.build.fingerprint"),
        "primary_abi": prop("ro.product.cpu.abi"),
        "abi_list": prop("ro.product.cpu.abilist"),
        "boot_completed": prop("sys.boot_completed"),
        "devices_output": devices,
    }


def run(args):
    root = args.source_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt = {"schema": 1, "status": "UNPASSED", "variant": args.variant,
               "started_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        if git(root, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError("source worktree is not clean")
        receipt["source_sha"] = git(root, "rev-parse", "HEAD")
        receipt["source_tree"] = git(root, "rev-parse", "HEAD^{tree}")
        report = args.dependency_report.resolve()
        graph = report.read_text()
        for module in MODULES:
            if f"io.github.rubixhacker:{module}:{VERSION}" not in graph:
                raise ValueError(f"consumer did not resolve staged {module}")
        if "org.dyn4j:dyn4j:" in graph:
            raise ValueError("consumer resolved the baseline provider")
        receipt["dependency_report"] = {"path": str(report), "sha256": sha256(report)}
        receipt["artifacts"] = staged_klibs(args.staging.resolve())
        executable = args.executable.resolve()
        if not executable.is_file():
            raise ValueError(f"missing native executable: {executable}")
        receipt["executable"] = {"path": str(executable), "sha256": sha256(executable),
                                 "abi": elf_abi(executable)}
        adb = [str(args.adb.resolve()), "-P", "5038", "-s", "emulator-5558"]
        receipt["guest"] = query_guest(adb)
        if receipt["guest"]["avd_name"] != "dyn4k_api37_play_x64":
            raise ValueError("ADB guest is not the isolated task AVD")
        if receipt["guest"]["primary_abi"] != "x86_64":
            raise ValueError("ADB guest primary ABI is not x86_64")
        remote = f"/data/local/tmp/dyn4k-native-{args.variant}"
        push = command(adb + ["push", str(executable), remote])
        chmod = command(adb + ["shell", "chmod", "700", remote])
        remote_hash = command(adb + ["shell", "sha256sum", remote]).stdout.split()[0]
        if remote_hash != receipt["executable"]["sha256"]:
            raise ValueError("deployed executable hash differs")
        receipt["deployment"] = {"push_command": adb + ["push", str(executable), remote],
                                 "push_stdout": push.stdout, "push_stderr": push.stderr,
                                 "chmod_exit_code": chmod.returncode, "remote_sha256": remote_hash}
        process_command = adb + ["shell", remote]
        process = command(process_command, check=False)
        stdout_path = output / "stdout.txt"
        stderr_path = output / "stderr.txt"
        stdout_path.write_text(process.stdout)
        stderr_path.write_text(process.stderr)
        receipt["process"] = {"command": process_command, "stdout": process.stdout,
                              "stderr": process.stderr, "exit_code": process.returncode,
                              "stdout_path": str(stdout_path), "stdout_sha256": sha256(stdout_path),
                              "stderr_path": str(stderr_path), "stderr_sha256": sha256(stderr_path)}
        receipt["assertion_count"] = sum(process.stdout.splitlines().count(f"ASSERT {label}") for label in ASSERTIONS)
        receipt["assertion_count"] = validate_receipt(receipt, receipt["source_sha"])
        receipt["status"] = "DIAGNOSTIC_PASSED"
    except (OSError, ValueError, IndexError, KeyError) as error:
        receipt["error"] = str(error)
    receipt["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    (output / "result.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: receipt.get(key) for key in ("status", "source_sha", "variant", "assertion_count", "error")}, sort_keys=True))
    return 0 if receipt["status"] == "DIAGNOSTIC_PASSED" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--dependency-report", type=Path, required=True)
    parser.add_argument("--variant", choices=("debug", "optimized"), required=True)
    parser.add_argument("--adb", type=Path, default=Path("/home/stewart/Android/Sdk/platform-tools/adb"))
    parser.add_argument("--output", type=Path, required=True)
    sys.exit(run(parser.parse_args()))
