#!/usr/bin/env python3
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from manifest import manifest


ROOT = Path(__file__).resolve().parents[2]
CONSUMER = ROOT / "consumers" / "performance"
STAGING = ROOT / "build" / "staging-repository"
PATHS = CONSUMER / "build" / "candidate-paths.tsv"
IDENTITY = CONSUMER / "build" / "candidate-identity.json"
VERSION = "0.1.0-alpha.1"
CORE = Path(f"io/github/rubixhacker/dyn4k-core-jvm/{VERSION}/dyn4k-core-jvm-{VERSION}.jar")
API = Path(f"io/github/rubixhacker/dyn4k-jvm/{VERSION}/dyn4k-jvm-{VERSION}.jar")
FLAGS = ["-Xms256m", "-Xmx2g", "-XX:+UseG1GC"]


def hash_path(path):
    path = Path(path)
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    elif path.is_dir():
        for item in sorted(child for child in path.rglob("*") if child.is_file()):
            digest.update(str(item.relative_to(path)).encode())
            digest.update(bytes.fromhex(hash_path(item)))
    else:
        raise ValueError(f"missing candidate path: {path}")
    return digest.hexdigest()


def verify_hashes(expected):
    for name, digest in expected.items():
        if hash_path(name) != digest:
            raise ValueError(f"stale candidate path: {name}")


def read_paths(path=PATHS):
    rows = [line.split("\t", 1) for line in Path(path).read_text().splitlines()]
    if len(rows) != 2 or {row[0] for row in rows} != {"direct_kotlin", "compatibility"}:
        raise ValueError("missing candidate route")
    return {route: [Path(item) for item in value.split(os.pathsep)] for route, value in rows}


def check_route(route, paths, staging_root=STAGING):
    paths = [Path(item).resolve() for item in paths]
    root = Path(staging_root).resolve()
    core = (root / CORE).resolve()
    api = (root / API).resolve()
    if route == "direct_kotlin":
        if paths.count(core) != 1 or paths.count(api) != 1:
            raise ValueError("direct Kotlin route lacks its staged API and core artifacts")
    elif route == "compatibility":
        if paths.count(core) != 1 or api in paths:
            raise ValueError("Java compatibility route has a missing or crossed provider")
    else:
        raise ValueError(f"unknown candidate route: {route}")
    if any(path.name.startswith("dyn4j-") and path.suffix == ".jar" for path in paths):
        raise ValueError("upstream dyn4j artifact is on a candidate route")
    if any(path.suffix == ".jar" and "rubixhacker" in path.parts and not path.is_relative_to(root)
           for path in paths):
        raise ValueError("candidate artifact came from outside the staging repository")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def source_trees(commit):
    return {name: git("rev-parse", f"{commit}:{name}") for name in ("dyn4k-core", "dyn4k")}


def prepare(java, source_commit):
    paths = read_paths()
    for route, values in paths.items():
        check_route(route, values)
    if git("status", "--porcelain", "--", "dyn4k", "dyn4k-core"):
        raise ValueError("engine sources have uncommitted changes")
    trees = source_trees(source_commit)
    if trees != source_trees("HEAD"):
        raise ValueError("staged engine source revision differs from current tree")
    version = subprocess.run([java, "-version"], capture_output=True, text=True, check=True).stderr.strip()
    all_paths = {path for values in paths.values() for path in values}
    missing = sorted(str(path) for path in all_paths if not path.exists())
    if any(Path(path).suffix == ".jar" for path in missing):
        raise ValueError("candidate classpath has a missing artifact")
    observed = {str(path): hash_path(path) for path in all_paths if path.exists()}
    if not (CONSUMER / "build/classes/kotlin/main/performance/DirectPilotKt.class").is_file():
        raise ValueError("direct Kotlin entry point is missing")
    if not (CONSUMER / "build/classes/java/compatibility/BaselinePilot.class").is_file():
        raise ValueError("Java compatibility entry point is missing")
    core = STAGING / CORE
    api = STAGING / API
    if observed[str(core)] == manifest()["baseline_jar_sha256"]:
        raise ValueError("core artifact matches the upstream binary")
    for file in (ROOT / "tools/performance/BaselinePilot.java",
                 ROOT / "tools/performance/candidate_runner.py",
                 CONSUMER / "src/main/kotlin/performance/DirectFixture.kt",
                 CONSUMER / "src/main/kotlin/performance/DirectPilot.kt",
                 CONSUMER / "src/main/java/performance/ProviderIdentity.java",
                 CONSUMER / "build.gradle.kts",
                 ROOT / "docs/research/performance-manifest-v1.json"):
        observed[str(file)] = hash_path(file)
    identity = {
        "schema": 1,
        "source_commit": git("rev-parse", source_commit),
        "source_trees": trees,
        "staging_repository": str(STAGING),
        "java": str(Path(java).resolve()),
        "java_version": version,
        "java_flags": FLAGS,
        "paths": {route: [str(path) for path in values] for route, values in paths.items()},
        "absent_classpath_paths": missing,
        "sha256": observed,
        "entrypoints": {"direct_kotlin": "performance.DirectPilotKt", "compatibility": "BaselinePilot"},
        "qualification": "unpassed",
    }
    IDENTITY.write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"identity": str(IDENTITY), "source_commit": identity["source_commit"],
                      "core_sha256": observed[str(core)], "api_sha256": observed[str(api)]}))


def run(args):
    if len(args) != 8:
        raise ValueError("runner needs family variant size hz steps mode warmup_steps api")
    family, variant, size, hz, steps, mode, warmup, route = args
    allowed = {item["id"] for item in manifest()["scenarios"]}
    if f"{family}.{variant}.{size}.{hz}hz.{route}" not in allowed:
        raise ValueError("workload is absent from the frozen manifest")
    if mode not in ("timing", "allocation", "memory", "plateau") or int(steps) <= 0 or int(warmup) < 0:
        raise ValueError("invalid measurement mode or step count")
    identity = json.loads(IDENTITY.read_text())
    paths = read_paths()
    if identity["source_trees"] != source_trees("HEAD"):
        raise ValueError("engine source tree changed after staging")
    if identity["paths"] != {key: [str(path) for path in values] for key, values in paths.items()}:
        raise ValueError("candidate route classpath changed after staging")
    if any(Path(path).exists() for path in identity["absent_classpath_paths"]):
        raise ValueError("candidate classpath gained an unverified path")
    check_route(route, paths[route])
    verify_hashes(identity["sha256"])
    java = identity["java"]
    if not Path(java).is_file():
        raise ValueError("recorded Java runtime is missing")
    marker = {"direct_kotlin": 1, "compatibility": 2}[route]
    print(f"#process_pid={os.getpid()}", file=sys.stderr)
    print(f"#route_marker={marker}", file=sys.stderr, flush=True)
    os.execv(java, [java, *FLAGS, "-cp", os.pathsep.join(map(str, paths[route])),
                    identity["entrypoints"][route], *args[:7]])


if __name__ == "__main__":
    try:
        if len(sys.argv) == 4 and sys.argv[1] == "prepare":
            prepare(sys.argv[2], sys.argv[3])
        else:
            run(sys.argv[1:])
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc
