import argparse
import errno
import json
from pathlib import Path
import subprocess
import sys
import time

import capture
import native_memory


def selected_artifact(inventory, module, target):
    return capture.native_artifacts(inventory, target)[module]["path"]


def sample_native_resident(process, stop, interval_seconds=0.02, platform_name=None):
    platform_name = platform_name or sys.platform
    samples = []
    errors = []
    while process.poll() is None and not stop.is_set():
        timestamp = time.monotonic_ns()
        try:
            samples.append((timestamp, native_memory.read_rss_bytes(process.pid)))
        except (OSError, ValueError) as error:
            row = {"monotonic_ns": timestamp,
                   "error_observed_monotonic_ns": time.monotonic_ns(),
                   "error": str(error), "errno": getattr(error, "errno", None)}
            if (platform_name == "darwin" and isinstance(error, OSError)
                    and error.errno == errno.ESRCH):
                deadline = time.monotonic() + min(interval_seconds, 0.05)
                while process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.001)
                exit_code = process.poll()
                if exit_code is not None:
                    row.update(classification="terminal_esrch_exit_confirmed",
                               exit_observed_monotonic_ns=time.monotonic_ns(),
                               exit_code=exit_code)
                    errors.append(row)
                    break
            errors.append(row)
        stop.wait(interval_seconds)
    terminal = (len(errors) == 1 and
                errors[0].get("classification") == "terminal_esrch_exit_confirmed" and
                errors[0]["exit_code"] == 0)
    method = {"linux": "procfs_statm_resident", "darwin": "proc_pidinfo_task_resident",
              "win32": "GetProcessMemoryInfo_working_set"}.get(
                  "linux" if platform_name.startswith("linux") else platform_name)
    return {"pid": process.pid, "method": method, "samples": samples,
            "errors": errors,
            "status": "observed_diagnostic" if samples and (not errors or terminal)
                      else "unavailable_or_partial"}


def main():
    parser = argparse.ArgumentParser(description="Capture one Native host producer run")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--publication-root", type=Path, required=True)
    parser.add_argument("--source-link-receipt", type=Path)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--target", choices=sorted(capture.NATIVE_HOST_TARGETS), required=True)
    parser.add_argument("--build", choices=("development", "optimized"), required=True)
    parser.add_argument("--mode", choices=("timing", "memory"), default="timing")
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--warmup", type=int, required=True)
    parser.add_argument("--host-timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()
    try:
        inventory_path = capture.required_file(str(args.inventory), "build inventory")
        inventory = json.loads(inventory_path.read_text())
        if inventory.get("target") != args.target or inventory.get("build") != args.build:
            raise ValueError("selected Native inventory target or build differs")
        harness = inventory["harness"]
        command = [sys.executable, str(Path(capture.__file__).resolve()),
                   "--archive", str(args.archive), "--inventory", str(inventory_path),
                   "--publication-root", str(args.publication_root),
                   "--scenario", args.scenario, "--target", args.target,
                   "--build", args.build, "--source-sha", inventory["source_sha"],
                   "--mode", args.mode,
                   "--runtime", harness, "--harness", harness,
                   "--core", selected_artifact(inventory, "dyn4k-core", args.target),
                   "--kotlin", selected_artifact(inventory, "dyn4k", args.target),
                   "--steps", str(args.steps), "--warmup", str(args.warmup),
                   "--host-timeout-seconds", str(args.host_timeout_seconds)]
        if args.source_link_receipt is not None:
            command += ["--source-link-receipt", str(args.source_link_receipt)]
        if args.mode != "memory" or sys.platform != "darwin":
            raise SystemExit(subprocess.call(command))
        if Path(capture.__file__).resolve() != Path(__file__).resolve().with_name("capture.py"):
            raise ValueError("selected capture adapter differs from checked-out source")
        original_argv = sys.argv
        original_sampler = native_memory.sample_while_alive
        try:
            sys.argv = command[1:]
            native_memory.sample_while_alive = sample_native_resident
            capture.main()
        finally:
            native_memory.sample_while_alive = original_sampler
            sys.argv = original_argv
    except (KeyError, ValueError, OSError) as error:
        parser.exit(1, f"qualification: unpassed; {error}\n")


if __name__ == "__main__":
    main()
