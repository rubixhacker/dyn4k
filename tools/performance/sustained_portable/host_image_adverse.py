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


def path_swap_control():
    if sys.platform == "win32":
        source = Path(os.environ["SystemRoot"]) / "System32" / "ping.exe"
        arguments = ["-t", "127.0.0.1"]
    else:
        source = Path("/bin/sleep")
        arguments = ["10"]
    with tempfile.TemporaryDirectory(prefix="dyn4k-image-adverse-") as temporary:
        executable = Path(temporary) / source.name
        moved = Path(temporary) / ("original-" + source.name)
        shutil.copy2(source, executable)
        original_sha = capture.digest(executable)
        process = subprocess.Popen([str(executable), *arguments], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        receipt = {"host": sys.platform, "pid": process.pid,
                   "original_sha256": original_sha, "swap": "unattempted",
                   "mapped_image_identity": "unobserved"}
        try:
            time.sleep(0.1)
            if process.poll() is not None:
                raise ValueError("adverse executable exited before path swap")
            receipt["before"] = capture.observed_process_image(process.pid)
            try:
                os.replace(executable, moved)
                executable.write_bytes(b"DYN4K_PATH_SWAP_DECOY")
                receipt["swap"] = "applied"
            except OSError as error:
                receipt["swap"] = "unavailable"
                receipt["swap_error"] = str(error)
            receipt["after"] = capture.observed_process_image(process.pid)
            reported = Path(receipt["after"]["path"])
            try:
                receipt["reported_path_sha256_after"] = capture.digest(reported)
            except OSError:
                receipt["reported_path_sha256_after"] = None
            if receipt["after"]["identity_kind"] == "mapped_executable":
                receipt["mapped_image_identity"] = (
                    "matched_original" if receipt["after"]["sha256"] == original_sha
                    else "mismatched")
        finally:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)
            receipt["exit_code"] = process.returncode
        return receipt


def main():
    parser = argparse.ArgumentParser(description="Probe a live host image path swap")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_absolute() or args.output.exists():
        parser.error("output must be a new absolute path")
    try:
        result = path_swap_control()
    except (OSError, ValueError) as error:
        result = {"host": sys.platform, "swap": "unavailable", "error": str(error),
                  "mapped_image_identity": "unobserved"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if result["swap"] != "applied" or result["mapped_image_identity"] == "mismatched":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
