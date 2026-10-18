import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import receipt


ROOT = Path(__file__).resolve().parents[4]
QUALITY = Path(__file__).with_name("nominal_quality.py")
RUNNER = Path(__file__).resolve().parents[1] / "run.py"


def run_command(command, environment, log):
    with Path(log).open("x") as stream:
        return subprocess.run(command, cwd=ROOT, env=environment,
                              stdout=stream, stderr=subprocess.STDOUT, check=False).returncode


def produce(args):
    commit = receipt.clean_commit()
    jdk = Path(args.jdk_home).resolve()
    java = jdk / "bin/java"
    if not java.is_file():
        raise ValueError("pinned JDK executable is unavailable")
    version = subprocess.run((str(java), "-version"), capture_output=True, text=True,
                             check=True).stderr
    if 'version "21.' not in version:
        raise ValueError("nominal producer needs JDK 21")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    temporary = output / "tmp"
    temporary.mkdir()
    environment = dict(os.environ, JAVA_HOME=str(jdk), TMPDIR=str(temporary))
    environment["PATH"] = str(jdk / "bin") + os.pathsep + environment.get("PATH", "")
    build = [str(ROOT / "gradlew"), "--offline", "--no-daemon", "--console=plain",
             ":dyn4k-core:publishJvmPublicationToStagingRepository"]
    if run_command(build, environment, output / "build.log"):
        raise ValueError("current-source staged JAR build failed; see build.log")
    if not receipt.ARTIFACT.is_file():
        raise ValueError("staged JVM JAR is unavailable after build")
    trace_dir = output / "capture"
    capture = [sys.executable, str(RUNNER), "--fixture", "nominal-free-motion",
               "--reference", str(Path(args.reference).resolve()), "--output", str(trace_dir)]
    capture_exit = run_command(capture, environment, output / "capture.log")
    if capture_exit:
        raise ValueError(f"nominal Java capture/comparison exited {capture_exit}; see capture.log")
    trace = trace_dir / "L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz"
    quality = [sys.executable, str(QUALITY), "--fixture", "nominal-free-motion",
               "--trace", str(trace), "--receipt", str(trace_dir / "receipt.json"),
               "--reference", str(Path(args.reference).resolve()), "--jdk-home", str(jdk),
               "--output", str(output / "quality")]
    quality_exit = run_command(quality, environment, output / "quality.log")
    if quality_exit not in (0, 2):
        raise ValueError(f"nominal physical verification exited {quality_exit}; see quality.log")
    physical = json.loads((output / "quality/result.json").read_text())
    comparison = json.loads((trace_dir / "comparison.json").read_text())
    if comparison["status"] != "PASSED":
        raise ValueError("nominal frozen comparison is not passed")
    result = {"status": physical["status"], "scope": physical["scope"],
              "candidate_commit": commit, "artifact_sha256": physical["artifact_sha256"],
              "trace_sha256": physical["trace_sha256"], "states": physical["counts"]["state"],
              "events": physical["events_checked"], "quality_exit": quality_exit,
              "comparison_status": comparison["status"], "output": str(output)}
    with (output / "producer_result.json").open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description="Build and capture the receipt-bound nominal JVM physical case")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--jdk-home", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = produce(args)
    except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        result = {"status": "INVALID", "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PHYSICAL_PASSED" else
                     2 if result["status"] in ("PHYSICAL_FAILED", "UNPASSED_PREMISE") else 1)


if __name__ == "__main__":
    main()
