import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from actual_arithmetic import (CaptureRejected, assess_focused_wheel,
                               expected_case_ids, focused_wheel_stream,
                               make_capture_receipt, verify_capture_receipt,
                               _portable_classes_archive)


ROOT = Path(__file__).resolve().parents[3]
PORTABLE = Path(__file__).resolve().parent
JDK21 = Path("/tmp/dyn4k-tools/jdk21")
STAGED_JAR = (ROOT / "build/staging-repository/io/github/rubixhacker/"
              "dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar")
XML = PORTABLE / "build/test-results/jvmTest/TEST-portable.ProspectiveArithmeticTest.xml"
ENVIRONMENT_SENTINEL = "DYN4K_CAPTURE_ENV_SENTINEL=portable-capture-check"
GENERATED_ROOTS = (
    ".gradle", ".kotlin", "build",
    "dyn4k-core/.gradle", "dyn4k-core/.kotlin", "dyn4k-core/build",
    "tools/numerical/portable/.gradle", "tools/numerical/portable/.kotlin",
    "tools/numerical/portable/build", "tools/numerical/portable/__pycache__",
    "tools/numerical/portable/kotlin-js-store",
)


def reject_environment_trace(trace_path):
    trace_path = Path(trace_path)
    try:
        contains_sentinel = ENVIRONMENT_SENTINEL.encode() in trace_path.read_bytes()
    except OSError:
        try:
            trace_path.unlink()
        except FileNotFoundError:
            raise CaptureRejected("process trace is missing") from None
        except OSError:
            raise CaptureRejected("process trace could not be removed") from None
        raise CaptureRejected("process trace is unavailable") from None
    if contains_sentinel:
        trace_path.unlink()
        raise CaptureRejected("process trace exposed the environment")


def git(*args):
    return subprocess.run(("git", *args), cwd=ROOT, check=True,
                          capture_output=True).stdout


def clean_source():
    if git("--no-replace-objects", "status", "--porcelain",
           "--untracked-files=all").strip():
        raise CaptureRejected("target source is not clean")
    ignored = git("--no-replace-objects", "ls-files", "--others", "--ignored",
                  "--exclude-standard", "--full-name", "-z").split(b"\0")
    for name in ignored:
        if not name:
            continue
        relative = os.fsdecode(name)
        if not any(relative.startswith(root + "/") for root in GENERATED_ROOTS):
            raise CaptureRejected("ignored file outside exact generated roots")
    return git("--no-replace-objects", "rev-parse", "HEAD").decode().strip()


def run_capture(method, output, reference_case=None):
    if method not in expected_case_ids(include_focused=True):
        raise CaptureRejected("unknown arithmetic producer method")
    if method == "captureWheelActive" and reference_case is None:
        raise CaptureRejected("focused Wheel reference is required")
    output = Path(output).resolve()
    if output.exists():
        raise CaptureRejected("capture output already exists")
    commit = clean_source()
    output.mkdir(parents=True)
    temporary = output / "tmp"
    temporary.mkdir()
    environment = os.environ.copy()
    environment.pop("OLLAMA_API_KEY", None)
    environment["JAVA_HOME"] = str(JDK21)
    environment["TMPDIR"] = str(temporary)
    environment["JAVA_TOOL_OPTIONS"] = f"-Djava.io.tmpdir={temporary}"
    environment["DYN4K_CAPTURE_ENV_SENTINEL"] = "portable-capture-check"
    if not (JDK21 / "bin/java").is_file():
        raise CaptureRejected("pinned JDK21 is unavailable")
    with (output / "source.tar").open("xb") as archive:
        subprocess.run(("git", "--no-replace-objects", "-c", "core.autocrlf=false", "archive",
                        "--format=tar", commit), cwd=ROOT,
                       stdout=archive, check=True)
    stage_command = [str(ROOT / "gradlew"),
                     ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
                     ":dyn4k-core:publishJvmPublicationToStagingRepository",
                     "--rerun-tasks", "--no-daemon", "--console=plain", "--offline",
                     "-Pkotlin.compiler.execution.strategy=in-process"]
    with (output / "stage.log").open("xb") as log:
        stage = subprocess.run(stage_command, cwd=ROOT, env=environment,
                               stdout=log, stderr=subprocess.STDOUT, check=False)
    if stage.returncode or not STAGED_JAR.is_file():
        raise CaptureRejected("pinned source publication failed")
    shutil.copyfile(STAGED_JAR, output / "artifact.jar")
    class_load_pattern = output / "worker-class-load-%p.log"
    command = ["strace", "-f", "-s", "16384", "-e", "trace=execve",
               "-o", str(output / "execve.log"), str(ROOT / "gradlew"),
               "jvmTest", "--tests", f"portable.ProspectiveArithmeticTest.{method}",
               f"-PportableRepository={ROOT / 'build/staging-repository'}",
               f"-PportableWorkerClassLoadLog={class_load_pattern}",
               "--rerun-tasks", "--no-daemon", "--console=plain", "--offline", "--info",
               "-Pkotlin.compiler.execution.strategy=in-process"]
    worker_arguments = output / "worker-classpath.txt"
    with (output / "gradle.log").open("xb") as log:
        target = subprocess.Popen(command, cwd=PORTABLE, env=environment,
                                  stdout=log, stderr=subprocess.STDOUT)
        while target.poll() is None:
            if not worker_arguments.exists():
                output_text = (output / "gradle.log").read_text(errors="replace")
                matches = re.findall(r"@(/[^\s]+gradle-worker-classpath[^\s]+txt)",
                                     output_text)
                if matches and Path(matches[-1]).is_file():
                    shutil.copyfile(matches[-1], worker_arguments)
            time.sleep(0.02)
    reject_environment_trace(output / "execve.log")
    if target.returncode or not XML.is_file() or not worker_arguments.is_file():
        raise CaptureRejected("executed arithmetic target method failed")
    worker_lines = [line for line in (output / "execve.log").read_text().splitlines()
                    if f'execve("{JDK21 / "bin/java"}"' in line and
                    "GradleWorkerMain" in line and line.endswith(" = 0")]
    if len(worker_lines) != 1:
        raise CaptureRejected("executed JVM worker identity differs")
    worker_pid = worker_lines[0].split(" ", 1)[0]
    if not worker_pid.isdecimal():
        raise CaptureRejected("executed JVM worker PID differs")
    worker_log = Path(str(class_load_pattern).replace("%p", worker_pid))
    if not worker_log.is_file():
        raise CaptureRejected("executed JVM worker class-load log missing")
    shutil.copyfile(XML, output / "capture.xml")
    with (output / "portable-classes.zip").open("xb") as classes:
        classes.write(_portable_classes_archive())
    if clean_source() != commit:
        raise CaptureRejected("target source changed during capture")
    runtime_path = JDK21 / "bin/java"
    shutil.copyfile(runtime_path, output / "runtime-java")
    files = {key: (output / name).read_bytes() for key, name in {
        "xml": "capture.xml", "stage_log": "stage.log", "gradle_log": "gradle.log",
        "execve_log": "execve.log", "artifact": "artifact.jar",
        "runtime": "runtime-java", "source": "source.tar",
        "worker_classpath": "worker-classpath.txt",
        "portable_classes": "portable-classes.zip"}.items()}
    files["worker_class_load"] = worker_log.read_bytes()
    if hashlib.sha256(files["artifact"]).hexdigest() != hashlib.sha256(
            STAGED_JAR.read_bytes()).hexdigest() or \
            hashlib.sha256(files["runtime"]).hexdigest() != hashlib.sha256(
                runtime_path.read_bytes()).hexdigest():
        raise CaptureRejected("copied producer artifact differs")
    receipt = make_capture_receipt(files, method, commit,
                                   expected_case_ids(include_focused=True)[method], str(runtime_path))
    verify_capture_receipt(receipt, files, method, commit,
                           expected_case_ids(include_focused=True)[method], str(runtime_path))
    (output / "receipt.json").write_text(json.dumps(receipt, sort_keys=True,
                                                     indent=2) + "\n")
    if method == "captureWheelActive":
        trace, _ = focused_wheel_stream(files["xml"])
        case_path = output / "joint-Wheel-active.jsonl"
        case_path.write_bytes(trace)
        assessment = assess_focused_wheel(receipt, files, commit, str(runtime_path),
                                          reference_case, case_path)
        (output / "focused-assessment.json").write_text(
            json.dumps(assessment, sort_keys=True, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=tuple(expected_case_ids(include_focused=True)),
                        required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-case", type=Path)
    arguments = parser.parse_args()
    result = run_capture(arguments.method, arguments.output, arguments.reference_case)
    print(json.dumps({"candidate_commit": result["candidate_commit"],
                      **result["summary"]}, sort_keys=True))
