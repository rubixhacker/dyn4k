from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

from candidate_coverage import digest, git


COMMAND = ["./gradlew", "--offline", "--no-daemon", "--console=plain", ":dyn4k-core:jvmJar"]
ARTIFACT = "dyn4k-core/build/libs/dyn4k-core-jvm-0.1.0-alpha.1.jar"
ANDROID_COMMAND = ["./gradlew", "--offline", "--no-daemon", "--console=plain",
                   ":dyn4k-core:syncAndroidMainLibJars"]
ANDROID_ARTIFACT = ("dyn4k-core/build/intermediates/aar_main_jar/androidMain/"
                    "syncAndroidMainLibJars/classes.jar")


def java_home() -> Path:
    selected = os.environ.get("DYN4K_LEDGER_JAVA_HOME") or "/tmp/dyn4k-tools/jdk21"
    return Path(selected).resolve()


def jdk21_version(java: Path, rejection: str) -> str:
    lines = subprocess.run([str(java), "-version"], capture_output=True,
                           text=True, check=True).stderr.splitlines()
    if (len(lines) < 3 or not lines[-3].startswith('openjdk version "21.')
            or not lines[-2].startswith("OpenJDK Runtime Environment ")
            or not lines[-1].startswith("OpenJDK 64-Bit Server VM ")):
        raise ValueError(rejection)
    return lines[-3]


def identity(root: Path, revision: str, artifact: Path) -> dict:
    root = root.resolve()
    artifact = artifact.resolve()
    if artifact != root / ARTIFACT:
        raise ValueError("candidate artifact path differs from the allowlisted JVM build output")
    if git(root, "--no-replace-objects", "rev-parse", f"{revision}^{{commit}}") != revision:
        raise ValueError("candidate source revision is invalid")
    java = java_home() / "bin/java"
    if not java.is_file():
        raise ValueError("pinned JDK 21 executable is unavailable")
    version = jdk21_version(java, "source rebuild requires JDK 21")
    return {"schema_version": 1, "revision": revision,
            "source_tree": git(root, "--no-replace-objects", "rev-parse", f"{revision}^{{tree}}"),
            "artifact": ARTIFACT, "artifact_sha256": digest(artifact),
            "gradle_wrapper_sha256": digest(root / "gradlew"),
            "java": str(java), "java_sha256": digest(java),
            "java_version": version, "command": COMMAND}


def check_identity(receipt: dict, root: Path, artifact: Path) -> str | None:
    try:
        expected = identity(root, receipt.get("revision"), artifact)
    except (OSError, TypeError, ValueError, subprocess.CalledProcessError):
        return "candidate source revision, artifact, or build tool is unavailable"
    for key, value in expected.items():
        if receipt.get(key) != value:
            return f"candidate build provenance {key} differs"
    return None


def probe(root: Path, revision: str, artifact: Path) -> dict:
    record = identity(root, revision, artifact)
    return _probe(root, revision, artifact, record, COMMAND, ARTIFACT)


def _probe(root: Path, revision: str, artifact: Path, record: dict,
           command: list[str], artifact_name: str) -> dict:
    before = record["artifact_sha256"]
    archive = subprocess.run(["git", "--no-replace-objects", "-C", str(root),
                              "-c", "core.autocrlf=false", "archive", "--format=tar", revision],
                             check=True, capture_output=True).stdout
    with tempfile.TemporaryDirectory(prefix="dyn4k-ledger-build-") as directory:
        checkout = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            tar.extractall(checkout, filter="data")
        environment = os.environ.copy()
        environment["JAVA_HOME"] = str(java_home())
        environment.setdefault("ANDROID_HOME", "/var/home/stewart/Android/Sdk")
        run = subprocess.run(command, cwd=checkout, env=environment,
                             capture_output=True, text=True, check=False, timeout=600)
        rebuilt = checkout / artifact_name
        rebuilt_sha = digest(rebuilt) if rebuilt.is_file() else None
        record.update({"process_exit_code": run.returncode, "rebuilt_sha256": rebuilt_sha,
                       "build_stdout": run.stdout, "build_stderr": run.stderr,
                       "build_stdout_sha256": hashlib.sha256(run.stdout.encode()).hexdigest(),
                       "build_stderr_sha256": hashlib.sha256(run.stderr.encode()).hexdigest(),
                       "passed": run.returncode == 0 and rebuilt_sha == before,
                       "reason": (None if run.returncode == 0 and rebuilt_sha == before else
                                  "isolated source rebuild failed or produced different JAR bytes")})
    if digest(artifact) != before:
        record["passed"] = False
        record["reason"] = "candidate JAR changed during source rebuild"
    return record


def identity_variant(root: Path, revision: str, artifact: Path, variant: str) -> dict:
    if variant == "jvm":
        return identity(root, revision, artifact)
    if variant != "android":
        raise ValueError(f"unknown candidate build variant: {variant}")
    root = root.resolve()
    artifact = artifact.resolve()
    if artifact != root / ANDROID_ARTIFACT:
        raise ValueError("candidate Android artifact path differs from the allowlisted build output")
    if git(root, "--no-replace-objects", "rev-parse", f"{revision}^{{commit}}") != revision:
        raise ValueError("candidate Android source revision is invalid")
    java = java_home() / "bin/java"
    if not java.is_file():
        raise ValueError("pinned JDK 21 executable is unavailable")
    version = jdk21_version(java, "Android source rebuild requires JDK 21")
    return {"schema_version": 1, "variant": "android", "revision": revision,
            "source_tree": git(root, "--no-replace-objects", "rev-parse", f"{revision}^{{tree}}"),
            "artifact": ANDROID_ARTIFACT, "artifact_sha256": digest(artifact),
            "gradle_wrapper_sha256": digest(root / "gradlew"),
            "java": str(java), "java_sha256": digest(java),
            "java_version": version, "command": ANDROID_COMMAND}


def probe_variant(root: Path, revision: str, artifact: Path, variant: str) -> dict:
    if variant == "jvm":
        return probe(root, revision, artifact)
    record = identity_variant(root, revision, artifact, variant)
    return _probe(root, revision, artifact, record, ANDROID_COMMAND, ANDROID_ARTIFACT)


def verify_variant(receipt: dict, root: Path, artifact: Path, source: dict,
                   variant: str) -> str | None:
    if variant == "jvm":
        return verify(receipt, root, artifact, source)
    for receipt_key, source_key in (("revision", "revision"), ("source_tree", "tree"),
                                    ("artifact", "artifact"),
                                    ("artifact_sha256", "artifact_sha256")):
        if receipt.get(receipt_key) != source.get(source_key):
            return f"candidate Android build receipt {receipt_key} differs from source"
    try:
        expected = identity_variant(root, receipt.get("revision"), artifact, variant)
    except (OSError, TypeError, ValueError, subprocess.CalledProcessError):
        return "candidate Android source revision, artifact, or build tool is unavailable"
    for key, value in expected.items():
        if receipt.get(key) != value:
            return f"candidate Android build provenance {key} differs"
    if receipt.get("passed") is not True:
        return "candidate Android source rebuild did not pass"
    observed = probe_variant(root, receipt["revision"], artifact, variant)
    if not observed["passed"] or observed["rebuilt_sha256"] != receipt.get("rebuilt_sha256"):
        return "candidate Android artifact differs from isolated source rebuild"
    return None


def verify(receipt: dict, root: Path, artifact: Path, source: dict) -> str | None:
    for receipt_key, source_key in (("revision", "revision"), ("source_tree", "tree"),
                                    ("artifact", "artifact"), ("artifact_sha256", "artifact_sha256")):
        if receipt.get(receipt_key) != source.get(source_key):
            return f"candidate build receipt {receipt_key} differs from ledger source"
    error = check_identity(receipt, root, artifact)
    if error:
        return error
    if receipt.get("passed") is not True:
        return "candidate source rebuild did not pass"
    observed = probe(root, receipt["revision"], artifact)
    if not observed["passed"] or observed["rebuilt_sha256"] != receipt.get("rebuilt_sha256"):
        return "candidate artifact differs from isolated source rebuild"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild a pinned candidate artifact in an isolated source archive.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--variant", choices=("jvm", "android"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("build receipt output exists")
    report = probe_variant(args.root, args.revision, args.artifact, args.variant)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "artifact_sha256": report["artifact_sha256"],
                      "rebuilt_sha256": report["rebuilt_sha256"], "reason": report["reason"]},
                     sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
