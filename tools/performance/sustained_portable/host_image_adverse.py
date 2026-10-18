import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import capture
import host_image


class AdverseStepError(ValueError):
    def __init__(self, stage, error):
        super().__init__(f"{stage}: {error}")
        self.stage = stage


def checked(stage, action):
    try:
        return action()
    except (OSError, ValueError) as error:
        raise AdverseStepError(stage, error) from error


def path_swap_control(receipt=None):
    if receipt is None:
        receipt = {}
    if sys.platform == "win32":
        source = Path(os.environ["SystemRoot"]) / "System32" / "ping.exe"
        arguments = ["-t", "127.0.0.1"]
    else:
        source = Path("/bin/sleep")
        arguments = ["10"]
    with tempfile.TemporaryDirectory(prefix="dyn4k-image-adverse-", dir=Path.home()) as temporary:
        executable = Path(temporary) / source.name
        moved = Path(temporary) / ("original-" + source.name)
        checked("copy_image", lambda: shutil.copyfile(source, executable))
        if os.name == "posix":
            checked("make_executable", lambda: os.chmod(executable, 0o700))
        original_sha = checked("hash_image", lambda: capture.digest(executable))
        receipt.update({"host": sys.platform, "control_image_source": str(source),
                        "original_sha256": original_sha,
                        "control_image_size": executable.stat().st_size,
                        "swap": "unattempted",
                        "mapped_image_identity": "unobserved"})
        process = checked("launch_image", lambda: subprocess.Popen(
            [str(executable), *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        receipt["pid"] = process.pid
        try:
            time.sleep(0.1)
            if process.poll() is not None:
                raise ValueError("adverse executable exited before path swap")
            receipt["before"] = checked("observe_before", lambda:
                                        capture.observed_process_image(process.pid, executable))
            checked("validate_before", lambda:
                    capture.require_process_image(receipt["before"], original_sha))
            try:
                os.replace(executable, moved)
                executable.write_bytes(b"DYN4K_PATH_SWAP_DECOY")
                receipt["swap"] = "applied"
            except OSError as error:
                receipt["swap"] = "blocked_by_os"
                receipt["swap_error"] = str(error)
            selected = moved if receipt["swap"] == "applied" else executable
            receipt["after"] = checked("observe_after", lambda:
                                       capture.observed_process_image(process.pid, selected))
            reported_path = receipt["after"].get("path")
            if reported_path is None:
                receipt["reported_path_sha256_after"] = None
                receipt["path_error"] = receipt["after"].get("path_error") or \
                    "diagnostic process path unavailable"
            else:
                if not isinstance(reported_path, str) or not reported_path:
                    raise ValueError("invalid diagnostic process path")
                try:
                    receipt["reported_path_sha256_after"] = capture.digest(Path(reported_path))
                except OSError:
                    receipt["reported_path_sha256_after"] = None
            try:
                capture.require_process_image(receipt["after"], original_sha)
                receipt["mapped_image_identity"] = "matched_original"
            except ValueError as error:
                receipt["mapped_image_identity"] = "mismatched"
                receipt["identity_error"] = str(error)
        finally:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)
            receipt["exit_code"] = process.returncode
            try:
                capture.observed_process_image(process.pid, moved if receipt["swap"] == "applied"
                                               else executable)
                receipt["stale_pid"] = "incorrectly_observed"
            except (OSError, ValueError):
                receipt["stale_pid"] = "rejected"
        return receipt


def main():
    parser = argparse.ArgumentParser(description="Probe a live host image path swap")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_absolute() or args.output.exists():
        parser.error("output must be a new absolute path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = {}
    try:
        result = path_swap_control(partial)
    except (OSError, ValueError) as error:
        result = {**partial, "host": sys.platform, "swap": "unavailable", "error": str(error),
                  "mapped_image_identity": "unobserved"}
        if isinstance(error, AdverseStepError):
            result["error_stage"] = error.stage
            if isinstance(error.__cause__, host_image.PECodeMismatch):
                result["pe_mismatch"] = error.__cause__.detail
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if result["mapped_image_identity"] != "matched_original" or result.get("stale_pid") != "rejected" or \
            result["swap"] not in ("applied", "blocked_by_os"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
