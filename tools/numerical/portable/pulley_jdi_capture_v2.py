import argparse
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

import baseline_capture
from pulley_jdi_v1 import BASELINE_JAR_SHA256, Rejected, _digest, _require
from pulley_jdi_v2 import CONTROLLER, inspect_capture


JDK = Path("/tmp/dyn4k-tools/jdk21")
BASELINE_SOURCE = Path("/tmp/dyn4k-upstream-6.0.0/src/main/java/org/dyn4j/dynamics/joint/PulleyJoint.java")
CANDIDATE_SOURCE = Path(__file__).resolve().parents[3] / "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/joint/PulleyJoint.kt"
FIXTURE_SHA256 = "dd104a7e018b9d0bd77c9af14e929699d68f29fa4ac8179a5bd7d98bdc87d9ce"
BASELINE_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"


def _write_new(path, data):
    with Path(path).open("xb") as output:
        output.write(data)


def _json_new(path, value):
    _write_new(path, (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())


def capture(profile, artifact, classpath_file, output, expected_artifact_sha256):
    _require(profile in ("baseline", "candidate"), "Pulley profile differs")
    _require(baseline_capture.fixture_source_sha256() == FIXTURE_SHA256,
             "frozen fixture source differs")
    artifact = Path(artifact).resolve(strict=True)
    classpath_file = Path(classpath_file).resolve(strict=True)
    output = Path(output)
    _require(output.is_absolute() and not output.exists() and
             str(output.resolve()).startswith(str(Path.home().resolve()) + "/"),
             "capture output is not fresh under home")
    artifact_sha = _digest(artifact)
    _require(artifact_sha == expected_artifact_sha256,
             "requested provider artifact hash differs")
    if profile == "baseline":
        _require(artifact_sha == BASELINE_JAR_SHA256,
                 "pinned baseline artifact differs")
        revision = BASELINE_REVISION
        source = BASELINE_SOURCE
    else:
        repo = Path(__file__).resolve().parents[3]
        environment = {key: value for key, value in os.environ.items()
                       if key != "OLLAMA_API_KEY"}
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, env=environment, text=True).strip()
        _require(not subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo, env=environment),
            "candidate source checkout is dirty")
        source = CANDIDATE_SOURCE
    source_sha = _digest(source)
    classpath = classpath_file.read_text().strip()
    _require(classpath.count(str(artifact)) == 1 and "\n" not in classpath,
             "focused worker classpath does not select one provider")
    output.mkdir(parents=True, exist_ok=False)
    (output / "tmp").mkdir()
    shutil.copyfile(artifact, output / "artifact.jar")
    _require(_digest(output / "artifact.jar") == artifact_sha,
             "copied provider artifact differs")
    classpath = classpath.replace(str(artifact), str(output / "artifact.jar"))
    _write_new(output / "classpath.txt", (classpath + "\n").encode())
    classes = output / "controller-classes"
    classes.mkdir()
    nonce = secrets.token_hex(32)
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("OLLAMA_API_KEY", "JAVA_TOOL_OPTIONS")}
    environment.update({"JAVA_HOME": str(JDK), "PATH": str(JDK / "bin") + os.pathsep +
                        environment.get("PATH", ""), "TMPDIR": str(output / "tmp"),
                        "DYN4K_PULLEY_JDI_V1_OUTPUT": str(output),
                        "DYN4K_PULLEY_JDI_V1_NONCE": nonce})
    with (output / "compile.stdout").open("xb") as stdout, \
            (output / "compile.stderr").open("xb") as stderr:
        subprocess.run([str(JDK / "bin/javac"),
                        "-J-Djava.io.tmpdir=" + str(output / "tmp"),
                        "--add-modules", "jdk.jdi",
                        "-d", str(classes), str(CONTROLLER)],
                       env=environment, stdout=stdout, stderr=stderr, check=True)
    with (output / "controller.stdout").open("xb") as stdout, \
            (output / "controller.stderr").open("xb") as stderr:
        controller = subprocess.Popen(
            [str(JDK / "bin/java"), "-Djava.io.tmpdir=" + str(output / "tmp"),
             "--add-modules", "jdk.jdi", "-cp", str(classes),
             "PulleyJdiControllerV2", profile, str(output / "classpath.txt"), str(output)],
            env=environment, stdout=stdout, stderr=stderr)
        try:
            controller_exit = controller.wait(timeout=60)
        except subprocess.TimeoutExpired:
            controller.kill()
            controller.wait()
            raise
        _require(controller_exit == 0, "JDI controller failed; raw output is retained")
    process = dict(line.split("=", 1) for line in
                   (output / "process.properties").read_text().splitlines())
    worker = json.loads((output / "worker.json").read_bytes())
    _require(process["controller_pid"] == str(controller.pid) and
             process["parent_pid"] == str(controller.pid) and
             process["worker_pid"] == str(worker["pid"]) and
             process["nonce"] == worker["nonce"] == nonce,
             "worker and controller process differ")
    _json_new(output / "live.json", {
        "schema": "pulley-jdi-live/2", "runner_pid": os.getpid(),
        "controller_pid": controller.pid, "worker_pid": worker["pid"],
        "controller_exit": controller_exit, "nonce": nonce,
    })
    _json_new(output / "jdi.json", {
        "schema": "pulley-jdi/1", "profile": profile, "pid": worker["pid"],
        "nonce": nonce, "artifact_sha256": artifact_sha,
        "case_sha256": _digest(output / "case.jsonl"),
        "worker_receipt_sha256": _digest(output / "worker.json"),
        "events_sha256": _digest(output / "events.jsonl"),
        "class_source_name": process["class_source_name"],
        "class_source_uri": (output / "artifact.jar").resolve().as_uri(),
        "debuggee_exit": int(process["exit_code"]),
    })
    _json_new(output / "capture-v2.json", {
        "schema": "pulley-jdi-capture/2", "profile": profile,
        "source_revision": revision, "source_sha256": source_sha,
        "artifact_sha256": artifact_sha, "controller_sha256": _digest(CONTROLLER),
        "controller_class_sha256": _digest(classes / "PulleyJdiControllerV2.class"),
        "classpath_sha256": _digest(output / "classpath.txt"),
        "worker_sha256": _digest(output / "worker.json"),
        "case_sha256": _digest(output / "case.jsonl"),
        "events_sha256": _digest(output / "events.jsonl"),
        "process_sha256": _digest(output / "process.properties"),
        "loaded_pool_sha256": _digest(output / "constant-pool.bin"),
        "loaded_methods_sha256": _digest(output / "methods.tsv"),
        "java_sha256": _digest(JDK / "bin/java"),
        "live_sha256": _digest(output / "live.json"),
    })
    result = inspect_capture(output)
    return {**result, "status": "PROVED_LIVE_ONECASE_OPERATION"}


def replay_capture(original, replay_output):
    original = Path(original)
    prior = inspect_capture(original)
    manifest = json.loads((original / "capture-v2.json").read_bytes())
    replay = capture(manifest["profile"], original / "artifact.jar",
                     original / "classpath.txt", replay_output,
                     manifest["artifact_sha256"])
    _require((original / "case.jsonl").read_bytes() ==
             (Path(replay_output) / "case.jsonl").read_bytes(),
             "replayed one-case worker bytes differ")
    left = json.loads((original / "events.jsonl").read_bytes())
    right = json.loads((Path(replay_output) / "events.jsonl").read_bytes())
    _require({key: value for key, value in left.items() if key != "pid"} ==
             {key: value for key, value in right.items() if key != "pid"},
             "replayed Pulley live operands differ")
    _require(prior["artifact_sha256"] == replay["artifact_sha256"],
             "replayed provider artifact differs")
    return {"status": "PROVED_REPLAYED_ONECASE_OPERATION",
            "case_sha256": prior["case_sha256"],
            "artifact_sha256": prior["artifact_sha256"],
            "replay_output": str(replay_output),
            "frozen_policy_status": "UNPASSED_NOT_EVALUATED"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("baseline", "candidate"))
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--classpath-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-artifact-sha256")
    parser.add_argument("--replay-existing", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.replay_existing:
            result = replay_capture(arguments.replay_existing, arguments.output)
        else:
            if not (arguments.profile and arguments.artifact and arguments.classpath_file and
                    arguments.expected_artifact_sha256):
                parser.error("capture requires profile, artifact, classpath file and artifact hash")
            result = capture(arguments.profile, arguments.artifact,
                             arguments.classpath_file, arguments.output,
                             arguments.expected_artifact_sha256)
    except Exception as error:
        reason = str(error) if isinstance(error, Rejected) else type(error).__name__
        print(json.dumps({"status": "UNPASSED_CAPTURE", "reason": reason}, sort_keys=True))
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
