import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
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
    except (OSError, ValueError, RuntimeError) as error:
        raise AdverseStepError(stage, error) from error


def bounded_bytes(value):
    return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest(),
            "hex": value[:128].hex(), "truncated": len(value) > 128}


def public_upload_roots():
    runner_temp = os.environ.get("RUNNER_TEMP")
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if not runner_temp or not workspace:
        if runner_temp or workspace or os.environ.get("GITHUB_ACTIONS") == "true":
            raise ValueError("both RUNNER_TEMP and GITHUB_WORKSPACE are required on hosted runs")
        return {}
    if not Path(runner_temp).is_absolute() or not Path(workspace).is_absolute():
        raise ValueError("public upload root inputs must be absolute")
    return {
        "native_host_evidence": (Path(runner_temp) / "performance-native-host-short").resolve(),
        "staging_repository": (Path(workspace) / "build" / "staging-repository").resolve(),
    }


def path_swap_control(receipt=None, control_image=None, control_sha256=None,
                      control_source_sha=None):
    if receipt is None:
        receipt = {}
    task_owned = control_image is not None
    if task_owned:
        if not (isinstance(control_sha256, str) and
                re.fullmatch(r"[0-9a-f]{64}", control_sha256) and
                isinstance(control_source_sha, str) and
                re.fullmatch(r"[0-9a-f]{40}", control_source_sha)):
            raise AdverseStepError("select_control_image", ValueError(
                "task-owned control requires an exact executable and source SHA"))
        source = checked("select_control_image", lambda: Path(control_image).resolve(strict=True))
        expected_name = ("dyn4k-performance-portable.exe" if sys.platform == "win32"
                         else "dyn4k-performance-portable.kexe")
        if source.name != expected_name or not source.is_file():
            raise AdverseStepError("select_control_image", ValueError(
                "task-owned control requires the selected Native executable"))
        receipt.update({"control_image_source": str(source),
                        "control_source_sha": control_source_sha,
                        "selected_inventory_sha256": control_sha256})
        if checked("validate_image_hash", lambda: capture.digest(source)) != control_sha256:
            raise AdverseStepError("validate_image_hash", ValueError(
                "selected Native executable differs from build inventory"))
        arguments = ["--image-control-hold", control_source_sha]
    elif sys.platform == "win32":
        raise AdverseStepError("select_control_image", ValueError(
            "Windows path swap requires the inventory-selected Native executable"))
    else:
        source = Path("/bin/sleep")
        arguments = ["10"]
    roots = checked("resolve_public_upload_roots", public_upload_roots)
    home = checked("select_private_directory", lambda: Path.home().resolve())
    with checked("create_private_directory", lambda: tempfile.TemporaryDirectory(
            prefix="dyn4k-image-adverse-", dir=home)) as temporary:
        private = checked("resolve_private_directory", lambda: Path(temporary).resolve(strict=True))
        relations = {name: "overlap" if private.is_relative_to(root) or root.is_relative_to(private)
                     else "disjoint" for name, root in roots.items()}
        receipt.update({"private_directory": str(private),
                        "public_upload_roots": {name: str(root) for name, root in roots.items()},
                        "public_upload_root_relation": relations})
        if "overlap" in relations.values():
            raise AdverseStepError("validate_private_directory", ValueError(
                "private executable directory overlaps a public upload root"))
        if task_owned:
            selected_dir = private / "selected"
            moved_dir = private / "original"
            selected_dir.mkdir()
            executable = selected_dir / source.name
            moved = moved_dir / source.name
            receipt["swap_method"] = "directory_rename"
        else:
            executable = private / source.name
            moved = private / ("original-" + source.name)
            receipt["swap_method"] = "file_rename"
        checked("copy_image", lambda: shutil.copyfile(source, executable))
        if os.name == "posix":
            checked("make_executable", lambda: os.chmod(executable, 0o700))
        original_sha = checked("hash_image", lambda: capture.digest(executable))
        if task_owned and original_sha != control_sha256:
            raise AdverseStepError("verify_private_copy", ValueError(
                "private Native executable copy differs from build inventory"))
        receipt.update({"host": sys.platform, "control_image_source": str(source),
                        "original_sha256": original_sha,
                        "control_image_size": executable.stat().st_size,
                        "swap": "unattempted",
                        "mapped_image_identity": "unobserved"})
        process = checked("launch_image", lambda: subprocess.Popen(
            [str(executable), *arguments], stdin=subprocess.PIPE if task_owned else None,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        receipt["pid"] = process.pid
        try:
            if task_owned:
                ready = {}
                def read_ready():
                    try:
                        ready["line"] = process.stdout.readline(129)
                    except (OSError, ValueError) as error:
                        ready["error"] = str(error)
                reader = threading.Thread(target=read_ready, daemon=True)
                reader.start()
                reader.join(timeout=3)
                if reader.is_alive():
                    receipt["control_ready_error"] = "readiness deadline exceeded"
                    raise AdverseStepError("wait_control_ready", ValueError(
                        "Native control did not report readiness before deadline"))
                if "error" in ready:
                    receipt["control_ready_error"] = ready["error"]
                    raise AdverseStepError("wait_control_ready", ValueError(
                        "Native control readiness read failed"))
                line = ready.get("line")
                if not isinstance(line, bytes):
                    receipt["control_ready_error"] = "readiness was not bytes"
                    raise AdverseStepError("wait_control_ready", ValueError(
                        "Native control readiness was not bytes"))
                receipt["control_ready_record"] = bounded_bytes(line)
                expected = f"DYN4K_IMAGE_CONTROL_READY\t{control_source_sha}".encode()
                if line not in (expected + b"\n", expected + b"\r\n"):
                    receipt["control_ready_error"] = (
                        "readiness exceeds 128 bytes" if len(line) > 128 else
                        "empty readiness" if not line else
                        "readiness differs from exact LF/CRLF source record")
                    raise AdverseStepError("wait_control_ready", ValueError(
                        "Native control readiness differs from selected source"))
                receipt["control_ready"] = "source_matched"
            else:
                time.sleep(0.1)
            if process.poll() is not None:
                raise ValueError("adverse executable exited before path swap")
            receipt["before"] = checked("observe_before", lambda:
                                        capture.observed_process_image(process.pid, executable))
            checked("validate_before", lambda:
                    capture.require_process_image(receipt["before"], original_sha))
            if task_owned:
                try:
                    os.replace(selected_dir, moved_dir)
                except OSError as error:
                    receipt["swap"] = "blocked_by_os"
                    receipt["swap_error"] = str(error)
                else:
                    checked("create_decoy_directory", selected_dir.mkdir)
                    checked("write_decoy", lambda: executable.write_bytes(b"DYN4K_PATH_SWAP_DECOY"))
                    receipt["swap"] = "applied"
            else:
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
            receipt["pre_cleanup_exit_code"] = process.poll()
            process.terminate()
            try:
                stdout_tail, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout_tail, stderr = process.communicate(timeout=3)
            if task_owned:
                receipt["control_stdout_tail"] = bounded_bytes(stdout_tail)
                receipt["control_stderr"] = bounded_bytes(stderr)
                if receipt.get("control_ready") == "source_matched" and (stdout_tail or stderr):
                    receipt["control_ready"] = "unexpected_output"
                    receipt["control_ready_error"] = "output followed the readiness record"
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
    parser.add_argument("--control-image", type=Path)
    parser.add_argument("--control-sha256")
    parser.add_argument("--control-source-sha")
    args = parser.parse_args()
    if not args.output.is_absolute() or args.output.exists():
        parser.error("output must be a new absolute path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = {}
    try:
        result = path_swap_control(partial, args.control_image, args.control_sha256,
                                   args.control_source_sha)
    except (OSError, ValueError) as error:
        result = {**partial, "host": sys.platform, "swap": "unavailable", "error": str(error),
                  "mapped_image_identity": "unobserved"}
        if isinstance(error, AdverseStepError):
            result["error_stage"] = error.stage
            if isinstance(error.__cause__, host_image.PECodeMismatch):
                result["pe_mismatch"] = error.__cause__.detail
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if (args.control_image and result.get("control_ready") != "source_matched") or \
            result["mapped_image_identity"] != "matched_original" or result.get("stale_pid") != "rejected" or \
            result["swap"] not in (("applied",) if args.control_image else
                                   ("applied", "blocked_by_os")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
