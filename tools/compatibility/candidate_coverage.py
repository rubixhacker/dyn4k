from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import struct
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path


SOURCE_ROOTS = ("dyn4k-core/src/commonMain/kotlin", "dyn4k-core/src/jvmMain/kotlin")
MODULE_SOURCE = "dyn4k-core/src/jvmModule/java/module-info.java"
ANONYMOUS_BEHAVIORS = {
    "org.dyn4j.collision.Filter$1": ("dyn4k-core/src/commonMain/kotlin/org/dyn4j/collision/FiltersAndFixture.kt", "DEFAULT_FILTER"),
    "org.dyn4j.collision.manifold.ManifoldPointId$1": ("dyn4k-core/src/commonMain/kotlin/org/dyn4j/collision/manifold/ManifoldModels.kt", "DISTANCE"),
    "org.dyn4j.world.ValueMixer$1": ("dyn4k-core/src/commonMain/kotlin/org/dyn4j/world/ValueMixer.kt", "DEFAULT_MIXER"),
    "org.dyn4j.collision.broadphase.DynamicAABBTree$1": ("dyn4k-core/src/commonMain/kotlin/org/dyn4j/collision/broadphase/DynamicAABBTree.kt", "sorted.sortWith"),
}
COMMON_EXPECT_SOURCES = {
    "org.dyn4j.exception.CopyException":
        ("dyn4k-core/src/commonMain/kotlin/org/dyn4j/exception/CollisionExceptions.kt",
         "expect open class CopyException"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def committed_sha(root: Path, revision: str, path: str) -> str:
    content = subprocess.run(["git", "-C", str(root), "show", f"{revision}:{path}"],
                             check=True, capture_output=True).stdout
    return hashlib.sha256(content).hexdigest()


def safe_source(path: str) -> bool:
    value = Path(path)
    return bool(path) and not value.is_absolute() and ".." not in value.parts and (
        path.startswith(SOURCE_ROOTS) or path == MODULE_SOURCE)


def source_record(root: Path, revision: str, path: str) -> dict:
    if not safe_source(path):
        raise ValueError(f"unsafe candidate source path: {path}")
    observed = digest(root / path)
    if committed_sha(root, revision, path) != observed:
        raise ValueError(f"candidate source differs from revision: {path}")
    return {"path": path, "sha256": observed}


def check_source_candidate(candidate: dict, root: Path) -> str | None:
    revision = candidate.get("commit")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        return "candidate source revision is invalid"
    try:
        if git(root, "rev-parse", f"{revision}^{{commit}}") != revision:
            return "candidate source revision is invalid"
        if subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor",
                           revision, "HEAD"], check=False).returncode != 0:
            return "candidate source revision is not an ancestor"
        if candidate.get("source_tree") != git(root, "rev-parse", f"{revision}^{{tree}}"):
            return "candidate source revision tree differs"
        sources = candidate.get("sources")
        if not isinstance(sources, list) or not sources:
            return "candidate source paths are missing"
        paths = [item.get("path") for item in sources if isinstance(item, dict)]
        if len(paths) != len(sources) or len(paths) != len(set(paths)) or paths != sorted(paths):
            return "candidate source paths are duplicate or unordered"
        for item in sources:
            path = item["path"]
            if not isinstance(path, str) or not safe_source(path):
                return "candidate source path is unsafe"
            current = root / path
            if (not current.is_file() or not isinstance(item.get("sha256"), str)
                    or digest(current) != item["sha256"]
                    or committed_sha(root, revision, path) != item["sha256"]):
                return f"candidate source hash differs: {path}"
    except (OSError, subprocess.CalledProcessError, ValueError):
        return "candidate source revision or file is unavailable"
    return None


def source_index(root: Path, revision: str) -> dict[tuple[str, str], list[str]]:
    result = defaultdict(list)
    for source_root in SOURCE_ROOTS:
        for path in sorted((root / source_root).rglob("*.kt")):
            relative = path.relative_to(root).as_posix()
            text = path.read_text()
            package = re.search(r"(?m)^package\s+([\w.]+)\s*$", text)
            if package is None:
                continue
            source_record(root, revision, relative)
            result[(package.group(1), path.name)].append(relative)
    return result


def class_source_file(data: bytes) -> str | None:
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        raise ValueError("candidate classfile header is invalid")
    cursor = 8

    def take(size: int) -> bytes:
        nonlocal cursor
        value = data[cursor:cursor + size]
        if len(value) != size:
            raise ValueError("candidate classfile is truncated")
        cursor += size
        return value

    def u2() -> int:
        return struct.unpack(">H", take(2))[0]

    def u4() -> int:
        return struct.unpack(">I", take(4))[0]

    pool = [None] * u2()
    index = 1
    while index < len(pool):
        tag = take(1)[0]
        if tag == 1:
            pool[index] = take(u2()).decode("utf-8", errors="replace")
        elif tag in {3, 4, 9, 10, 11, 12, 17, 18}:
            take(4)
        elif tag in {5, 6}:
            take(8)
            index += 1
        elif tag in {7, 8, 16, 19, 20}:
            take(2)
        elif tag == 15:
            take(3)
        else:
            raise ValueError(f"unsupported candidate classfile constant tag: {tag}")
        index += 1

    def attributes() -> list[tuple[str | None, bytes]]:
        return [(pool[u2()], take(u4())) for _ in range(u2())]

    take(6)
    take(2 * u2())
    for _ in range(u2()):
        take(6)
        attributes()
    for _ in range(u2()):
        take(6)
        attributes()
    for name, value in attributes():
        if name == "SourceFile":
            if len(value) != 2:
                raise ValueError("candidate SourceFile attribute is invalid")
            return pool[struct.unpack(">H", value)[0]]
    return None


def class_sources(root: Path, revision: str, jar: Path, class_name: str,
                  archive: zipfile.ZipFile, sources: dict[tuple[str, str], list[str]]) -> tuple[list[dict], str | None]:
    classfile = class_name.replace(".", "/") + ".class"
    try:
        class_bytes = archive.read(classfile)
    except KeyError:
        return [], "candidate JVM class is absent"
    compiled = class_source_file(class_bytes)
    if not isinstance(compiled, str) or not re.fullmatch(r"[^/]+\.kt", compiled):
        return [], "candidate JVM class has no Kotlin SourceFile"
    package = class_name.rpartition(".")[0]
    paths = sources.get((package, compiled), [])
    if not paths:
        return [], "candidate Kotlin SourceFile is absent"
    if len(paths) > 2 or (len(paths) == 2 and
                          not any("/commonMain/" in path for path in paths)):
        return [], "candidate Kotlin SourceFile is ambiguous"
    if class_name in COMMON_EXPECT_SOURCES:
        common_path, marker = COMMON_EXPECT_SOURCES[class_name]
        if marker not in (root / common_path).read_text():
            return [], "candidate common expect declaration is absent"
        paths = [*paths, common_path]
    return [source_record(root, revision, path) for path in sorted(paths)], None


def materialize(original: dict, root: Path, revision: str, jar: Path) -> dict:
    root = root.resolve()
    jar = jar.resolve()
    if git(root, "rev-parse", f"{revision}^{{commit}}") != revision:
        raise ValueError("candidate source revision is invalid")
    if root not in jar.parents or not jar.is_file():
        raise ValueError("candidate JAR must exist in the worktree")
    result = copy.deepcopy(original)
    result.pop("review_receipts", None)
    tree = git(root, "rev-parse", f"{revision}^{{tree}}")
    artifact = jar.relative_to(root).as_posix()
    artifact_sha = digest(jar)
    if artifact_sha == original["baseline"]["binary_sha256"]:
        raise ValueError("pinned baseline JAR cannot be a candidate artifact")
    shared = {"commit": revision, "source_tree": tree, "artifact": artifact,
              "artifact_sha256": artifact_sha}
    index = source_index(root, revision)
    by_type = {}
    with zipfile.ZipFile(jar) as archive:
        for item in result["declarations"]:
            if not item["id"].endswith("|type"):
                continue
            name = item["id"].split("|")[0]
            if name.endswith(".package-info"):
                package = name.removesuffix(".package-info")
                paths = sorted({path for (owner, _), candidates in index.items()
                                if owner == package for path in candidates
                                if "/commonMain/" in path})
                by_type[name] = ([source_record(root, revision, path) for path in paths],
                                 None if paths else "candidate common Kotlin package is absent")
            elif name in ANONYMOUS_BEHAVIORS:
                path, marker = ANONYMOUS_BEHAVIORS[name]
                if marker not in (root / path).read_text():
                    by_type[name] = ([], "candidate anonymous behavior marker is absent")
                else:
                    by_type[name] = ([source_record(root, revision, path)], None)
            else:
                by_type[name] = class_sources(root, revision, jar, name, archive, index)
    for item in result["declarations"]:
        name = item["id"].split("|")[0]
        paths, reason = by_type[name]
        item["candidate"] = {**shared, "identity": item["id"], "sources": paths} if paths else None
        item["disposition"] = ("package-documentation-only" if paths and name.endswith(".package-info") else
                               "anonymous-behavior-mapped" if paths and name in ANONYMOUS_BEHAVIORS else
                               "source-mapped" if paths else
                               "jvm-only-pending-review" if name.endswith(".package-info") or "$1" in name
                               else "unmapped")
        item["reason"] = (reason or "common portable evidence requires an exact-source host receipt")
        item["evidence"] = []
    owner_types = defaultdict(list)
    for item in result["declarations"]:
        if item["id"].endswith("|type"):
            owner_types[item["source_file"]].append(item)
    for item in result["production"]:
        if item["id"] == "src/main/java/module-info.java":
            paths = [source_record(root, revision, MODULE_SOURCE)]
            reason = None
        else:
            mapped = [row["candidate"] for row in owner_types[item["id"]] if row["candidate"]]
            paths = sorted({entry["path"]: entry for candidate in mapped
                            for entry in candidate["sources"]}.values(), key=lambda entry: entry["path"])
            reason = None if paths else "no candidate Kotlin source backs this original source file"
        identity = "|".join(entry["path"] for entry in paths)
        item["candidate"] = {**shared, "identity": identity, "sources": paths} if paths else None
        item["disposition"] = ("package-documentation-only" if paths and item["id"].endswith("/package-info.java") else
                               "source-mapped" if paths else
                               "jvm-only-pending-review" if item["id"].endswith("/package-info.java")
                               else "unmapped")
        item["reason"] = reason or "implementation evidence requires an exact-source behavior receipt"
        item["evidence"] = []
    groups = defaultdict(list)
    for item in result["production"]:
        if item["candidate"]:
            groups[item["candidate"]["identity"]].append(item["id"])
    for item in result["production"]:
        if item["candidate"]:
            item["candidate"]["mapped_baseline_ids"] = sorted(groups[item["candidate"]["identity"]])
    for item in result["tests"]:
        item["candidate"] = {**shared, "identity": item["id"],
                             "baseline_source_sha256": item["sha256"]}
        item["disposition"] = "unchanged-java-source"
        item["reason"] = "JVM corpus evidence requires unchanged source compilation and execution"
        item["evidence"] = []
    result["module"]["candidate"] = {**shared, "identity": "org.dyn4j",
                                      "sources": [source_record(root, revision, MODULE_SOURCE)]}
    result["module"]["reason"] = "named-module and Java 8 evidence require executable receipts"
    result["module"]["evidence"] = []
    result["candidate_source"] = {"revision": revision, "tree": tree,
                                  "artifact": artifact, "artifact_sha256": artifact_sha}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Map baseline obligations to reviewed candidate source.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--revision", required=True)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists")
    result = materialize(json.loads(args.ledger.read_text()), args.root, args.revision, args.jar)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({section: sum(item["candidate"] is not None for item in result[section])
                      for section in ("production", "tests", "declarations")}, sort_keys=True))


if __name__ == "__main__":
    main()
