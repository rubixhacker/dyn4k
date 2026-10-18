import hashlib
import itertools
import json
import os
import re
import stat
import subprocess
from contextlib import contextmanager
from pathlib import Path


SOURCE = Path("tools/qualification/safari-karma-reporter.js")
STAGED_NAME = "qualification-safari-reporter.js"
PROJECTS = (Path("dyn4k-core"), Path("dyn4k"),
            Path("consumers/qualification/portable"))
MAX_FRAGMENT_BYTES = 256 * 1024
PACKAGES = {Path("dyn4k-core"): "dyn4k-dyn4k-core-test",
            Path("dyn4k"): "dyn4k-dyn4k-test",
            Path("consumers/qualification/portable"): "dyn4k-staged-portable-consumer-test"}


class ConfigBindingError(ValueError):
    pass


def config_relative(project):
    base = project if project == Path("consumers/qualification/portable") else Path()
    return base / "build/js/packages" / PACKAGES[project] / "karma.conf.js"


def validate_config(data, fragment, repository, project, configuration=None):
    project = Path(project)
    if project not in PACKAGES:
        raise ConfigBindingError("karma_config_module_mismatch")
    try:
        source = data.decode("utf-8")
        expected = fragment.decode("utf-8")
    except UnicodeError as error:
        raise ConfigBindingError("karma_config_invalid_encoding") from error
    if source.count(expected) != 1:
        raise ConfigBindingError("reporter_fragment_missing")
    position = source.index(expected)
    line_start = source.rfind("\n", 0, position) + 1
    if (source[:position].rfind("/*") > source[:position].rfind("*/")
            or source[line_start:position].strip()
            or not re.fullmatch(r"\s*}\s*", source[position + len(expected):])):
        raise ConfigBindingError("reporter_fragment_in_comment")
    provider = "config.plugins.push(require('kotlin-web-helpers/dist/karma-kotlin-reporter'));"
    if source.count(provider) != 1 or source.index(provider) > position:
        raise ConfigBindingError("reporter_provider_missing")
    match = re.match(r"\s*module\.exports\s*=\s*function\s*\(config\)\s*\{\s*config\.set\(",
                     source)
    if match is None:
        raise ConfigBindingError("karma_config_shape_mismatch")
    try:
        settings, end = json.JSONDecoder().raw_decode(source, match.end())
    except (ValueError, TypeError) as error:
        raise ConfigBindingError("karma_config_shape_mismatch") from error
    if not isinstance(settings, dict) or not source[end:].startswith(");"):
        raise ConfigBindingError("karma_config_shape_mismatch")
    extra_sets = re.findall(r"config\.set\s*\([^;]*;", source[end + 2:])
    if extra_sets not in ([], ["config.set({webpack: createWebpackConfig()});"]):
        raise ConfigBindingError("karma_config_shape_mismatch")
    if extra_sets and source.index(extra_sets[0]) > position:
        raise ConfigBindingError("karma_config_shape_mismatch")
    root = repository / project
    package = PACKAGES[project]
    package_build_root = root if project == Path("consumers/qualification/portable") \
        else repository
    package_root = package_build_root / "build/js/packages" / package
    if settings.get("basePath") != str(package_root):
        raise ConfigBindingError("karma_config_module_mismatch")
    runner = str(package_build_root / "build/js/node_modules/kotlin-web-helpers/dist"
                 / "kotlin-test-karma-runner.js")
    inputs = {
        "development": str(package_root / "kotlin" / f"{package}.js"),
        "production": str(root / "build/compileSync/js/test/testProductionExecutable"
                          / "kotlin" / f"{package}.js"),
    }
    files = settings.get("files")
    observed = next((mode for mode, path in inputs.items()
                     if files == [runner, path]), None)
    if observed is None or (configuration is not None and configuration != observed):
        raise ConfigBindingError("karma_config_source_mismatch")
    if (settings.get("browsers") != ["Safari"]
            or settings.get("reporters") != ["karma-kotlin-reporter"]
            or settings.get("customLaunchers", {}) != {}
            or settings.get("exclude", []) != []
            or settings.get("preprocessors") != {
                runner: ["webpack", "sourcemap"], files[1]: ["webpack", "sourcemap"]}):
        raise ConfigBindingError("karma_config_source_mismatch")
    return observed


def committed_fragment(repository, candidate_sha):
    path = repository / SOURCE
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FRAGMENT_BYTES:
        raise ValueError("committed Safari reporter source is unsafe or oversized")
    current = path.read_bytes()
    committed = subprocess.check_output(
        ["git", "-C", str(repository), "show", f"{candidate_sha}:{SOURCE}"])
    if current != committed:
        raise ValueError("Safari reporter source differs from candidate")
    return committed


def _forensic(path, output, relative):
    record = {"path": str(relative), "original_size": None, "retained_size": 0}
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            observed = os.fstat(descriptor)
            if not stat.S_ISREG(observed.st_mode):
                raise ValueError("nonregular staged reporter")
            record["original_size"] = observed.st_size
            data = os.read(descriptor, min(observed.st_size, MAX_FRAGMENT_BYTES))
            if len(data) != min(observed.st_size, MAX_FRAGMENT_BYTES):
                raise ValueError("staged reporter changed during forensic capture")
            after = os.fstat(descriptor)
            if (observed.st_dev, observed.st_ino, observed.st_size, observed.st_mtime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError("staged reporter changed during forensic capture")
        finally:
            os.close(descriptor)
        destination = output / "forensic/safari-reporter" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)
        record.update(archive_path=destination.relative_to(output).as_posix(),
                      retained_size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                      truncated=observed.st_size > MAX_FRAGMENT_BYTES)
    except (OSError, ValueError) as error:
        record["error"] = str(error)
    return record


@contextmanager
def stage(repository, candidate_sha, projects, output):
    repository = repository.resolve()
    output = output.resolve()
    if output.is_relative_to(repository):
        raise ValueError("Safari reporter forensic output must be external")
    content = committed_fragment(repository, candidate_sha)
    if not projects or any(Path(project) not in PROJECTS for project in projects) \
            or len(set(projects)) != len(projects):
        raise ValueError("invalid Safari reporter projects")
    result = {"status": "CLEAN", "source_sha256": hashlib.sha256(content).hexdigest(),
              "projects": {}, "forensic": []}
    created = []
    try:
        for project in projects:
            relative = Path(project)
            root = repository / relative
            if root.is_symlink() or not root.is_dir() or root.resolve() != root:
                raise ValueError(f"unsafe Safari reporter project: {relative}")
            directory = root / "karma.config.d"
            if directory.exists() or directory.is_symlink():
                raise ValueError(f"preexisting Safari Karma configuration: {directory}")
            directory.mkdir()
            staged = directory / STAGED_NAME
            created.append((relative, directory, staged))
            staged.write_bytes(content)
            result["projects"][relative.as_posix()] = "STAGED"
        yield result
    finally:
        for relative, directory, staged in reversed(created):
            key = relative.as_posix()
            if directory.is_symlink() or not directory.is_dir():
                result["status"] = "CHANGED"
                result["projects"][key] = "DIRECTORY_CHANGED"
                result["forensic"].append({"path": str(relative / "karma.config.d"),
                                           "error": "staging directory changed"})
                continue
            if staged.is_symlink() or not staged.is_file() \
                    or staged.stat().st_size != len(content) \
                    or staged.read_bytes() != content:
                result["status"] = "CHANGED"
                result["projects"][key] = "CHANGED"
                result["forensic"].append(_forensic(staged, output, relative / STAGED_NAME))
            else:
                result["projects"][key] = "CLEAN"
            if staged.is_file() or staged.is_symlink():
                staged.unlink()
            if directory.is_dir() and not directory.is_symlink():
                with os.scandir(directory) as entries:
                    leftovers = sorted(item.name for item in itertools.islice(entries, 17))
                if leftovers:
                    result["status"] = "CHANGED"
                    result["projects"][key] = "LEFTOVER"
                    result.setdefault("leftovers", {})[key] = leftovers[:16]
                    if len(leftovers) > 16:
                        result.setdefault("leftovers_truncated", []).append(key)
                    for name in leftovers[:16]:
                        result["forensic"].append(
                            _forensic(directory / name, output, relative / name))
                else:
                    try:
                        directory.rmdir()
                    except OSError as error:
                        result["status"] = "CHANGED"
                        result["projects"][key] = "LEFTOVER"
                        result["forensic"].append({"path": str(relative / "karma.config.d"),
                                                   "error": str(error)})
