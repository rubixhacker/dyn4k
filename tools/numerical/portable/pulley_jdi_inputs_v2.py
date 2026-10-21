import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path

import run as portable_runner
from pulley_jdi_v1 import Rejected, _digest, _require


MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_ENTRY_BYTES = 32 * 1024 * 1024
MAX_CLASSPATH_BYTES = 256 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_CLASS_FILES = 10000
MAX_LOG_BYTES = 2 * 1024 * 1024
REQUIRED_PROVIDER = {
    "org/dyn4j/dynamics/joint/PulleyJoint.class",
    "org/dyn4j/dynamics/Body.class",
    "org/dyn4j/world/World.class",
    "org/dyn4j/geometry/Geometry.class",
}
REQUIRED_FIXTURE = {
    "portable/PulleyPreparationJdiV1Test.class",
    "portable/NumericalRecorder.class",
}
REQUIRED_DEPENDENCIES = {
    "org/junit/runner/JUnitCore.class",
    "kotlin/jvm/internal/Intrinsics.class",
}


def bounded_file(path, maximum=MAX_ENTRY_BYTES):
    path = Path(path)
    _require(path.is_file() and not path.is_symlink() and
             path.stat().st_nlink == 1 and path.stat().st_size <= maximum,
             "classpath or artifact file exceeds bound or is linked")
    return path


def _jar_classes(path):
    classes = set()
    uncompressed = 0
    try:
        with zipfile.ZipFile(path) as archive:
            _require(len(archive.infolist()) <= MAX_CLASS_FILES,
                     "classpath ZIP entry count exceeds bound")
            names = set()
            for item in archive.infolist():
                name = item.filename
                _require(name not in names and not name.startswith("/") and
                         ".." not in Path(name).parts and
                         stat.S_IFMT(item.external_attr >> 16) != stat.S_IFLNK,
                         "classpath ZIP entry is duplicate, linked or unsafe")
                names.add(name)
                uncompressed += item.file_size
                _require(uncompressed <= MAX_UNCOMPRESSED_BYTES and
                         item.file_size <= MAX_ENTRY_BYTES and
                         item.file_size <= max(1024, item.compress_size * 100),
                         "classpath ZIP expansion exceeds bound")
                if name.endswith(".class") and not name.startswith("META-INF/"):
                    classes.add(name)
            if "META-INF/MANIFEST.MF" in names:
                raw = archive.read("META-INF/MANIFEST.MF")
                _require(len(raw) <= 64 * 1024, "classpath manifest exceeds bound")
                lines = raw.decode("utf-8", "replace").splitlines()
                _require(not any(line.lower().startswith(("class-path:", "multi-release: true"))
                                 for line in lines), "classpath manifest adds hidden providers")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise Rejected("classpath JAR is malformed") from error
    return classes


def inspect_classpath(classpath_file, provider, fixture, dependency_root):
    classpath_file = bounded_file(classpath_file, 64 * 1024)
    provider = bounded_file(provider, MAX_ARTIFACT_BYTES).resolve()
    fixture = Path(fixture).resolve()
    dependency_root = Path(dependency_root).resolve()
    raw = classpath_file.read_text(encoding="utf-8")
    _require(raw.endswith("\n") and raw.count("\n") == 1 and
             not any(character.isspace() for character in raw.strip()),
             "focused classpath text differs")
    paths = [Path(part) for part in raw.strip().split(os.pathsep)]
    _require(len(paths) >= 3 and len(paths) <= 32 and
             all(path.is_absolute() for path in paths) and
             len(set(paths)) == len(paths), "focused classpath entry count or path differs")
    _require(paths[0] == fixture and paths[1] == provider,
             "fixture or selected provider classpath order differs")
    _require(all(path == path.resolve() for path in paths),
             "classpath contains a linked or noncanonical path")
    entries = []
    owners = {}
    total = 0
    for index, path in enumerate(paths):
        bounded_file(path, MAX_ARTIFACT_BYTES if index == 1 else MAX_ENTRY_BYTES)
        if index == 0:
            role = "fixture"
        elif index == 1:
            role = "provider"
        else:
            _require(path.is_relative_to(dependency_root),
                     "classpath dependency is outside approved cache")
            role = "dependency"
        total += path.stat().st_size
        _require(total <= MAX_CLASSPATH_BYTES, "classpath bytes exceed bound")
        classes = _jar_classes(path)
        for name in classes:
            _require(name not in owners, "duplicate classpath class: " + name)
            owners[name] = role
        entries.append({"role": role, "index": index, "sha256": _digest(path),
                        "size": path.stat().st_size, "path": str(path)})
    _require(all(owners.get(name) == "provider" for name in REQUIRED_PROVIDER),
             "engine provider class origin differs")
    _require(all(owners.get(name) == "fixture" for name in REQUIRED_FIXTURE),
             "one-case fixture or recorder origin differs")
    _require(all(owners.get(name) == "dependency" for name in REQUIRED_DEPENDENCIES),
             "worker runtime dependency origin differs")
    _require(not any(name.startswith(("org/dyn4j/", "portable/")) and role == "dependency"
                     for name, role in owners.items()),
             "classpath dependency shadows engine or fixture")
    return entries


def receipt_bytes(entries):
    return (json.dumps({"schema": "pulley-jdi-classpath/2", "entries": entries},
                       sort_keys=True, separators=(",", ":")) + "\n").encode()


def verify_candidate_publication(artifact, record):
    os.environ.pop("OLLAMA_API_KEY", None)
    _require(record is not None, "exact-current publication record is absent")
    record = bounded_file(record, 64 * 1024)
    log = bounded_file(record.with_name("publication.log"), 64 * 1024 * 1024)
    _require(record.name == "publication.json" and
             record.parent.resolve().is_relative_to(Path.home().resolve()),
             "publication record is outside task home")
    try:
        manifest = json.loads(record.read_bytes())
    except (ValueError, UnicodeError) as error:
        raise Rejected("publication record is malformed") from error
    _require(set(manifest) == {"candidate_commit", "source_sha256", "artifact_sha256",
                               "publication_log_sha256"},
             "publication record fields differ")
    commit, source_archive = portable_runner.clean_identity()
    _require(manifest["candidate_commit"] == commit and
             manifest["source_sha256"] == source_archive and
             manifest["publication_log_sha256"] == _digest(log),
             "publication source or build log differs")
    names = portable_runner._publication_names()
    _require(set(manifest["artifact_sha256"]) == names,
             "publication artifact inventory differs")
    for name in names:
        staged = bounded_file(portable_runner.STAGED / name, MAX_ARTIFACT_BYTES)
        _require(_digest(staged) == manifest["artifact_sha256"][name],
                 "staged publication artifact differs")
    selected = portable_runner.artifact_relative_paths("jvm")["target"]
    _require(_digest(bounded_file(artifact, MAX_ARTIFACT_BYTES)) ==
             manifest["artifact_sha256"][selected],
             "selected candidate JAR differs from current publication")
    return {"record": record, "log": log, "commit": commit,
            "source_archive_sha256": source_archive,
            "record_sha256": _digest(record), "log_sha256": _digest(log)}
