import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from actual_arithmetic import (CaptureRejected, expected_case_ids,
                               make_capture_receipt, verify_capture_receipt)


ROOT = Path(__file__).resolve().parents[3]
PORTABLE = Path(__file__).resolve().parent
JDK21 = Path("/tmp/dyn4k-tools/jdk21")
STAGED_JAR = (ROOT / "build/staging-repository/io/github/rubixhacker/"
              "dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar")
XML = PORTABLE / "build/test-results/jvmTest/TEST-portable.ProspectiveArithmeticTest.xml"


def git(*args):
    return subprocess.run(("git", *args), cwd=ROOT, check=True,
                          capture_output=True).stdout


def clean_source():
    if git("status", "--porcelain", "--untracked-files=all").strip():
        raise CaptureRejected("target source is not clean")
    return git("rev-parse", "HEAD").decode().strip()


def run_capture(method, output):
    if method not in expected_case_ids():
        raise CaptureRejected("unknown arithmetic producer method")
    output = Path(output).resolve()
    if output.exists():
        raise CaptureRejected("capture output already exists")
    commit = clean_source()
    output.mkdir(parents=True)
    temporary = output / "tmp"
    temporary.mkdir()
    environment = os.environ.copy()
    environment["JAVA_HOME"] = str(JDK21)
    environment["TMPDIR"] = str(temporary)
    if not (JDK21 / "bin/java").is_file():
        raise CaptureRejected("pinned JDK21 is unavailable")
    with (output / "source.tar").open("xb") as archive:
        subprocess.run(("git", "archive", "--format=tar", "HEAD"), cwd=ROOT,
                       stdout=archive, check=True)
    stage_command = [str(ROOT / "gradlew"),
                     ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
                     ":dyn4k-core:publishJvmPublicationToStagingRepository",
                     "--rerun-tasks", "--no-daemon", "--console=plain", "--offline"]
    with (output / "stage.log").open("xb") as log:
        stage = subprocess.run(stage_command, cwd=ROOT, env=environment,
                               stdout=log, stderr=subprocess.STDOUT, check=False)
    if stage.returncode or not STAGED_JAR.is_file():
        raise CaptureRejected("pinned source publication failed")
    shutil.copyfile(STAGED_JAR, output / "artifact.jar")
    command = ["strace", "-f", "-s", "16384", "-e", "trace=execve",
               "-o", str(output / "execve.log"), str(ROOT / "gradlew"),
               "jvmTest", "--tests", f"portable.ProspectiveArithmeticTest.{method}",
               f"-PportableRepository={ROOT / 'build/staging-repository'}",
               "--rerun-tasks", "--no-daemon", "--console=plain", "--offline", "--info"]
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
    if target.returncode or not XML.is_file() or not worker_arguments.is_file():
        raise CaptureRejected("executed arithmetic target method failed")
    shutil.copyfile(XML, output / "capture.xml")
    if clean_source() != commit:
        raise CaptureRejected("target source changed during capture")
    runtime_path = JDK21 / "bin/java"
    shutil.copyfile(runtime_path, output / "runtime-java")
    files = {key: (output / name).read_bytes() for key, name in {
        "xml": "capture.xml", "stage_log": "stage.log", "gradle_log": "gradle.log",
        "execve_log": "execve.log", "artifact": "artifact.jar",
        "runtime": "runtime-java", "source": "source.tar",
        "worker_classpath": "worker-classpath.txt"}.items()}
    if hashlib.sha256(files["artifact"]).hexdigest() != hashlib.sha256(
            STAGED_JAR.read_bytes()).hexdigest() or \
            hashlib.sha256(files["runtime"]).hexdigest() != hashlib.sha256(
                runtime_path.read_bytes()).hexdigest():
        raise CaptureRejected("copied producer artifact differs")
    receipt = make_capture_receipt(files, method, commit,
                                   expected_case_ids()[method], str(runtime_path))
    verify_capture_receipt(receipt, files, method, commit,
                           expected_case_ids()[method], str(runtime_path))
    (output / "receipt.json").write_text(json.dumps(receipt, sort_keys=True,
                                                     indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=tuple(expected_case_ids()), required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = run_capture(arguments.method, arguments.output)
    print(json.dumps({"candidate_commit": result["candidate_commit"],
                      **result["summary"]}, sort_keys=True))
