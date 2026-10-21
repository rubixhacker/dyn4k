import argparse
import json
import os
import resource
import secrets
import signal
import subprocess
import time
from pathlib import Path

import baseline_capture
import run as portable_runner
from pulley_jdi_v1 import BASELINE_JAR_SHA256, Rejected, _digest, _require
from pulley_jdi_v2 import CONTROLLER, inspect_capture
from pulley_jdi_inputs_v2 import (MAX_ARTIFACT_BYTES, MAX_LOG_BYTES, bounded_file,
                                  inspect_classpath, receipt_bytes,
                                  verify_candidate_publication)


JDK = Path("/tmp/dyn4k-tools/jdk21")
BASELINE_SOURCE = Path("/tmp/dyn4k-upstream-6.0.0/src/main/java/org/dyn4j/dynamics/joint/PulleyJoint.java")
CANDIDATE_SOURCE = Path(__file__).resolve().parents[3] / "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/joint/PulleyJoint.kt"
FIXTURE_SHA256 = "dd104a7e018b9d0bd77c9af14e929699d68f29fa4ac8179a5bd7d98bdc87d9ce"
BASELINE_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
SIDECAR = Path(__file__).resolve().parent / "pulley-jdi-sidecar-v2"


def _write_new(path, data):
    with Path(path).open("xb") as output:
        output.write(data)


def _json_new(path, value):
    _write_new(path, (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())


def _copy_bounded(source, target, maximum):
    bounded_file(source, maximum)
    total = 0
    with Path(source).open("rb") as reader, Path(target).open("xb") as writer:
        for block in iter(lambda: reader.read(1024 * 1024), b""):
            total += len(block)
            _require(total <= maximum, "copied evidence exceeds one-case bound")
            writer.write(block)
    _require(total == Path(source).stat().st_size,
             "source changed during bounded copy")


def _file_limit():
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_LOG_BYTES, MAX_LOG_BYTES))


def _run_bounded(command, environment, stdout_path, stderr_path, timeout):
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        child = subprocess.Popen(command, env=environment, stdout=stdout, stderr=stderr,
                                 preexec_fn=_file_limit, start_new_session=True)
        deadline = time.monotonic() + timeout
        while child.poll() is None:
            if (stdout_path.stat().st_size > MAX_LOG_BYTES or
                    stderr_path.stat().st_size > MAX_LOG_BYTES or
                    time.monotonic() > deadline):
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise Rejected("bounded child log or runtime limit exceeded")
            time.sleep(0.02)
        if child.returncode != 0:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        _require(stdout_path.stat().st_size <= MAX_LOG_BYTES and
                 stderr_path.stat().st_size <= MAX_LOG_BYTES,
                 "bounded child log exceeded")
        return child.pid, child.returncode


def _build_sidecar(profile, artifact, output, environment, expected_entries):
    commit, source_archive = portable_runner.clean_identity()
    classpath = output / "sidecar-classpath.txt"
    _, build_exit = _run_bounded(
        [str(Path(__file__).resolve().parents[3] / "gradlew"), "-p", str(SIDECAR),
         "writePulleyClasspath", "--offline", "--rerun-tasks", "--no-daemon",
         "--console=plain", "--project-cache-dir", str(output / "tmp/gradle-cache"),
         "-PpulleyProfile=" + profile,
         "-PproviderJar=" + str(artifact),
         "-PpulleyBuildDirectory=" + str(output / "build"),
         "-PpulleyClasspathFile=" + str(classpath)],
        environment, output / "sidecar-build.stdout", output / "sidecar-build.stderr", 180)
    _require(build_exit == 0, "focused sidecar build failed; bounded logs are retained")
    fixture = output / "build/pulley-jdi/pulley-fixture.jar"
    built = inspect_classpath(classpath, artifact, fixture,
                              Path.home().resolve() / ".gradle/caches")
    _require([{key: entry[key] for key in ("role", "sha256")} for entry in built] ==
             [{key: entry[key] for key in ("role", "sha256")}
              for entry in expected_entries],
             "focused classpath differs from fresh source build")
    _require(portable_runner.clean_identity() == (commit, source_archive),
             "source changed during focused sidecar build")
    return commit, source_archive, built


def capture(profile, artifact, classpath_file, output, expected_artifact_sha256,
            publication_record=None):
    _require(profile in ("baseline", "candidate"), "Pulley profile differs")
    _require(baseline_capture.fixture_source_sha256() == FIXTURE_SHA256,
             "frozen fixture source differs")
    artifact = bounded_file(artifact, MAX_ARTIFACT_BYTES).resolve(strict=True)
    classpath_file = bounded_file(classpath_file, 64 * 1024).resolve(strict=True)
    output = Path(output)
    _require(output.is_absolute() and not output.exists() and
             str(output.resolve()).startswith(str(Path.home().resolve()) + "/"),
             "capture output is not fresh under home")
    artifact_sha = _digest(artifact, MAX_ARTIFACT_BYTES)
    _require(artifact_sha == expected_artifact_sha256,
             "requested provider artifact hash differs")
    if profile == "baseline":
        _require(artifact_sha == BASELINE_JAR_SHA256,
                 "pinned baseline artifact differs")
        revision = BASELINE_REVISION
        source = BASELINE_SOURCE
        publication = None
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
        publication = verify_candidate_publication(artifact, publication_record)
    source_sha = _digest(source)
    fixture = Path(classpath_file.read_text(encoding="utf-8").split(os.pathsep, 1)[0])
    _require(fixture.name == "pulley-fixture.jar" and
             fixture.is_relative_to(Path.home().resolve()),
             "focused fixture is outside task home")
    entries = inspect_classpath(classpath_file, artifact, fixture,
                                Path.home().resolve() / ".gradle/caches")
    output.mkdir(parents=True, exist_ok=False)
    (output / "tmp").mkdir()
    nonce = secrets.token_hex(32)
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("OLLAMA_API_KEY", "JAVA_TOOL_OPTIONS",
                                  "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH")}
    environment.update({"JAVA_HOME": str(JDK), "PATH": str(JDK / "bin") + os.pathsep +
                        environment.get("PATH", ""), "TMPDIR": str(output / "tmp"),
                        "DYN4K_PULLEY_JDI_V1_OUTPUT": str(output),
                        "DYN4K_PULLEY_JDI_V1_NONCE": nonce})
    fixture_commit, fixture_archive, entries = _build_sidecar(
        profile, artifact, output, environment, entries)
    classpath_dir = output / "classpath"
    classpath_dir.mkdir()
    copied = []
    for entry in entries:
        target = (output / "artifact.jar" if entry["index"] == 1 else
                  classpath_dir / f"{entry['index']:03d}.jar")
        _copy_bounded(entry["path"], target, MAX_ARTIFACT_BYTES)
        _require(_digest(target, MAX_ARTIFACT_BYTES) == entry["sha256"],
                 "copied classpath entry differs")
        copied.append(target)
    _write_new(output / "classpath.txt",
               (os.pathsep.join(map(str, copied)) + "\n").encode())
    _write_new(output / "classpath-entries.json", receipt_bytes(entries))
    if publication:
        _copy_bounded(publication["record"], output / "publication.json", 64 * 1024)
        _copy_bounded(publication["log"], output / "publication.log", 64 * 1024 * 1024)
        _require(_digest(output / "publication.json", 64 * 1024) ==
                 publication["record_sha256"] and
                 _digest(output / "publication.log", 64 * 1024 * 1024) ==
                 publication["log_sha256"], "copied publication differs")
    classes = output / "controller-classes"
    classes.mkdir()
    _, compile_exit = _run_bounded(
        [str(JDK / "bin/javac"), "-J-Djava.io.tmpdir=" + str(output / "tmp"),
         "--add-modules", "jdk.jdi", "-d", str(classes), str(CONTROLLER)],
        environment, output / "compile.stdout", output / "compile.stderr", 30)
    _require(compile_exit == 0, "JDI controller compile failed; raw output is retained")
    controller_pid, controller_exit = _run_bounded(
        [str(JDK / "bin/java"), "-Djava.io.tmpdir=" + str(output / "tmp"),
         "--add-modules", "jdk.jdi", "-cp", str(classes),
         "PulleyJdiControllerV2", profile, str(output / "classpath.txt"), str(output)],
        environment, output / "controller.stdout", output / "controller.stderr", 60)
    _require(controller_exit == 0, "JDI controller failed; raw output is retained")
    process = dict(line.split("=", 1) for line in
                   (output / "process.properties").read_text().splitlines())
    worker = json.loads((output / "worker.json").read_bytes())
    _require(process["controller_pid"] == str(controller_pid) and
             process["parent_pid"] == str(controller_pid) and
             process["worker_pid"] == str(worker["pid"]) and
             process["nonce"] == worker["nonce"] == nonce,
             "worker and controller process differ")
    _json_new(output / "live.json", {
        "schema": "pulley-jdi-live/2", "runner_pid": os.getpid(),
        "controller_pid": controller_pid, "worker_pid": worker["pid"],
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
        "classpath_entries_sha256": _digest(output / "classpath-entries.json"),
        "publication_sha256": publication["record_sha256"] if publication else None,
        "publication_log_sha256": publication["log_sha256"] if publication else None,
        "source_archive_sha256": publication["source_archive_sha256"] if publication else None,
        "fixture_commit": fixture_commit,
        "fixture_archive_sha256": fixture_archive,
        "sidecar_build_stdout_sha256": _digest(output / "sidecar-build.stdout", MAX_LOG_BYTES),
        "sidecar_build_stderr_sha256": _digest(output / "sidecar-build.stderr", MAX_LOG_BYTES),
        "sidecar_classpath_sha256": _digest(output / "sidecar-classpath.txt", 64 * 1024),
    })
    result = inspect_capture(output)
    return {**result, "status": "UNPASSED_REPLAY_REQUIRED"}


def replay_capture(original, replay_output):
    original = Path(original)
    replay_output = Path(replay_output)
    prior = inspect_capture(original)
    manifest = json.loads((original / "capture-v2.json").read_bytes())
    retained = json.loads((original / "classpath-entries.json").read_bytes())
    _require(retained["schema"] == "pulley-jdi-classpath/2" and
             len(retained["entries"]) >= 3 and
             retained["entries"][1]["role"] == "provider",
             "replay source classpath receipt differs")
    source_paths = [entry["path"] for entry in retained["entries"]]
    _require(not replay_output.exists() and
             replay_output.is_absolute() and
             str(replay_output.resolve()).startswith(str(Path.home().resolve()) + "/"),
             "replay output is not fresh under home")
    replay_classpath = replay_output.with_name(replay_output.name + "-input-classpath.txt")
    _write_new(replay_classpath, (os.pathsep.join(source_paths) + "\n").encode())
    replay = capture(manifest["profile"], Path(source_paths[1]),
                     replay_classpath, replay_output,
                     manifest["artifact_sha256"],
                     original / "publication.json" if manifest["profile"] == "candidate" else None)
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
    return {"status": "REPLAYED_ONECASE_OPERATION",
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
    parser.add_argument("--publication-record", type=Path)
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
                             arguments.expected_artifact_sha256,
                             arguments.publication_record)
    except Exception as error:
        reason = str(error) if isinstance(error, Rejected) else type(error).__name__
        print(json.dumps({"status": "UNPASSED_CAPTURE", "reason": reason}, sort_keys=True))
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
