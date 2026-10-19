import hashlib
import os
import re
import subprocess
from pathlib import Path

import full_klib_consumer
import independent_gates


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
TOOLCHAIN_KEYS = frozenset((
    "java_home", "java_version", "java_sha256", "gradle_version",
    "gradle_sha256", "node_version", "node_sha256", "gradle_user_home",
    "kgp_version", "kotlin_native"))
NATIVE_KEYS = frozenset(("home", "version", "executable_sha256", "compiler_sha256"))


def _hash_file(path, expected, label):
    if type(expected) is not str or not SHA256.fullmatch(expected):
        raise ValueError(f"signed {label} SHA-256 is missing or invalid")
    if not path.is_file():
        raise ValueError(f"signed {label} executable is missing")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"signed {label} executable SHA-256 differs")


def _absolute_path(value, label):
    if type(value) is not str or not value or not Path(value).is_absolute():
        raise ValueError(f"signed {label} path is missing or relative")
    return Path(value)


def _output(command, environment):
    result = subprocess.run(command, env=environment, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, check=False)
    if result.returncode:
        raise ValueError(f"auditor tool execution failed: {command[0]}")
    return result.stdout


def _trusted_toolchain(expected, lane_id):
    trusted = expected.get("expected_klib_toolchain")
    binaries = expected.get("expected_klib_executables")
    if (not isinstance(trusted, dict) or set(trusted) != TOOLCHAIN_KEYS
            or not isinstance(binaries, dict) or set(binaries) != {"gradle", "node"}):
        raise ValueError("signed KLIB toolchain identity is incomplete")
    for key in ("java_sha256", "gradle_sha256", "node_sha256"):
        if type(trusted[key]) is not str or not SHA256.fullmatch(trusted[key]):
            raise ValueError(f"signed KLIB {key} is missing or invalid")
    for key in ("java_version", "gradle_version", "node_version", "kgp_version"):
        if type(trusted[key]) is not str or not trusted[key]:
            raise ValueError(f"signed KLIB {key} is missing")
    java_home = _absolute_path(trusted["java_home"], "JDK 21 home")
    _absolute_path(trusted["gradle_user_home"], "Gradle user home")
    gradle = _absolute_path(binaries["gradle"], "Gradle executable")
    node = _absolute_path(binaries["node"], "Node executable")
    native = trusted["kotlin_native"]
    if lane_id.startswith("linuxX64:"):
        if not isinstance(native, dict) or set(native) != NATIVE_KEYS:
            raise ValueError("signed Kotlin/Native compiler identity is incomplete")
        native_home = _absolute_path(native["home"], "Kotlin/Native home")
        for key in ("executable_sha256", "compiler_sha256"):
            if type(native[key]) is not str or not SHA256.fullmatch(native[key]):
                raise ValueError(f"signed Kotlin/Native {key} is missing or invalid")
        if type(native["version"]) is not str or not native["version"]:
            raise ValueError("signed Kotlin/Native version is missing")
    elif native is not None:
        raise ValueError("signed Node lane has a foreign Native compiler identity")
    if (not trusted["java_version"].startswith('openjdk version "21.')
            or trusted["gradle_version"] != "Gradle 9.5.0"
            or trusted["kgp_version"] != "2.4.20"):
        raise ValueError("signed KLIB toolchain differs from approved pins")

    java = java_home / "bin/java"
    _hash_file(java, trusted["java_sha256"], "JDK 21")
    _hash_file(gradle, trusted["gradle_sha256"], "Gradle")
    _hash_file(node, trusted["node_sha256"], "Node")
    environment = os.environ.copy()
    environment["JAVA_HOME"] = str(java_home)
    environment["GRADLE_USER_HOME"] = trusted["gradle_user_home"]
    java_version = next((line for line in _output([str(java), "-version"], environment)
                         .splitlines() if line.startswith("openjdk version ")), None)
    if java_version != trusted["java_version"]:
        raise ValueError("signed JDK 21 version differs from auditor tool")
    if trusted["gradle_version"] not in _output([str(gradle), "--version"], environment):
        raise ValueError("signed Gradle version differs from auditor tool")
    if _output([str(node), "--version"], environment).strip() != trusted["node_version"]:
        raise ValueError("signed Node version differs from auditor tool")
    if native is not None:
        compiler = native_home / "bin/kotlinc-native"
        _hash_file(compiler, native["executable_sha256"], "Kotlin/Native")
        _hash_file(native_home / "konan/lib/kotlin-native-compiler-embeddable.jar",
                   native["compiler_sha256"], "Kotlin/Native compiler JAR")
        lines = _output([str(compiler), "-version"], environment).splitlines()
        version = "\n".join(line for line in lines if line.startswith((
            "info: kotlinc-native", "Kotlin/Native:")))
        if version != native["version"] or "Kotlin/Native: 2.4.20" not in version:
            raise ValueError("signed Kotlin/Native version differs from auditor tool")
    return trusted, node


def verify_staged_consumer(repository, candidate_sha, lane_id, selected_case_ids,
                           archive, gate_result, expected, audited_target_hashes):
    if lane_id not in full_klib_consumer.LOCAL_LANES:
        raise ValueError(f"public full KLIB verifier does not cover lane: {lane_id}")
    if not isinstance(expected, dict):
        raise ValueError("signed KLIB lane audit is missing")
    if not isinstance(gate_result, dict) or gate_result.get("status") != "PASSED":
        raise ValueError("independent staged-consumer gate has not passed")
    repository = Path(repository)
    selected = full_klib_consumer.contract(repository, lane_id)[1]
    approved_ids = [case["id"] for case in selected["cases"]]
    if selected_case_ids != approved_ids:
        raise ValueError("signed KLIB lane selects a different approved case suite")
    hashes = expected.get("expected_artifact_hashes")
    if (not isinstance(hashes, dict) or set(hashes) != set(full_klib_consumer.MODULES)
            or any(type(value) is not str or not SHA256.fullmatch(value)
                   for value in hashes.values())
            or hashes != audited_target_hashes):
        raise ValueError("signed KLIB artifacts differ from independently audited target")
    runtime = expected.get("expected_runtime_identity")
    digests = expected.get("expected_archive_digests")
    digest = digests.get("staged-consumer") if isinstance(digests, dict) else None
    if (type(runtime) is not str or not runtime
            or type(digest) is not str or not SHA256.fullmatch(digest)):
        raise ValueError("signed KLIB runtime or archive digest is incomplete")
    root = Path(archive)
    if independent_gates.archive_digest(root) != digest:
        raise ValueError("signed KLIB archive digest differs from transported archive")
    trusted, node = _trusted_toolchain(expected, lane_id)
    public = full_klib_consumer.verify(
        root, repository, candidate_sha, lane_id, hashes, runtime, digest, trusted,
        str(node) if lane_id.startswith("js:") else None)
    if public != gate_result:
        raise ValueError(f"public KLIB verifier differs from independent gate: {lane_id}")
    return public
