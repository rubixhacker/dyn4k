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
MAX_COMMITTED_OBJECT_BYTES = 16 * 1024 * 1024
PACKAGES = {Path("dyn4k-core"): "dyn4k-dyn4k-core-test",
            Path("dyn4k"): "dyn4k-dyn4k-test",
            Path("consumers/qualification/portable"): "dyn4k-staged-portable-consumer-test"}

APPROVED_GENERATOR_TAIL = (
    '\n'
    'config.plugins = config.plugins || [];\n'
    "config.plugins.push(require('kotlin-web-helpers/dist/karma-kotlin-reporter'));\n"
    '\n'
    'config.loggers = [\n'
    '    {\n'
    "        type: require('kotlin-web-helpers/dist/tc-log-appender'),\n"
    '        //default layout\n'
    "        layout: { type: 'pattern', pattern: '%[%d{DATETIME}:%p [%c]: %]%m' }\n"
    '    }\n'
    ']\n'
    'config.plugins = config.plugins || [];\n'
    "config.plugins.push(require('kotlin-web-helpers/dist/karma-webpack-output'));\n"
    '\n'
    '// webpack config\n'
    'function createWebpackConfig() {\n'
    'let config = {\n'
    "  mode: 'development',\n"
    '  resolve: {\n'
    '    modules: [\n'
    '      "node_modules"\n'
    '    ]\n'
    '  },\n'
    '  plugins: [],\n'
    '  module: {\n'
    '    rules: []\n'
    '  },\n'
    '  \n'
    '};\n'
    '\n'
    '// source maps\n'
    'config.module.rules.push({\n'
    '        test: /\\.m?js$/,\n'
    '        use: ["source-map-loader"],\n'
    '        enforce: "pre"\n'
    '});\n'
    'config.devtool = false;\n'
    'config.ignoreWarnings = [\n'
    '    /Failed to parse source map/,\n'
    '    /Accessing import\\.meta directly is unsupported \\(only property access or destructuring is supported\\)/\n'
    '];  \n'
    '                // optimization\n'
    '                config.optimization = config.optimization || {\n'
    '  "splitChunks": false\n'
    '};\n'
    '// noinspection JSUnnecessarySemicolon\n'
    ';(function(config) {\n'
    "    const tcErrorPlugin = require('kotlin-web-helpers/dist/tc-log-error-webpack');\n"
    '    config.plugins.push(new tcErrorPlugin())\n'
    '    config.stats = config.stats || {}\n'
    '    Object.assign(config.stats, config.stats, {\n'
    '        warnings: false,\n'
    '        errors: false\n'
    '    })\n'
    '})(config);\n'
    'config.experiments = {\n'
    '    topLevelAwait: true,\n'
    '}\n'
    '// section: Extra JS code from KotlinWebpackConfig.extraJs\n'
    '// section end\n'
    '// noinspection JSUnnecessarySemicolon\n'
    ';(function(config) {\n'
    "    const webpack = require('webpack');\n"
    '\n'
    '    // https://github.com/webpack/webpack/issues/12951\n'
    "    const PatchSourceMapSource = require('kotlin-web-helpers/dist/webpack-5-debug');\n"
    '    config.plugins.push(new PatchSourceMapSource())\n'
    '    \n'
    '    config.plugins.push(new webpack.SourceMapDevToolPlugin({\n'
    '        moduleFilenameTemplate: "[absolute-resource-path]"\n'
    '    }))\n'
    '})(config);\n'
    '   return config;\n'
    '}\n'
    '\n'
    'config.set({webpack: createWebpackConfig()});\n'
    '\n'
    '\n'
    f'// {STAGED_NAME}\n'
)


class ConfigBindingError(ValueError):
    pass


class StageFailure(OSError):
    def __init__(self, result):
        self.result = result
        failed = next((item.get("path", "") for item in result["forensic"]
                       if item.get("error")), "karma.config.d")
        super().__init__(f"Safari reporter staging residue: {str(failed)[:256]}")


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
    prefix = "\nmodule.exports = function(config) {\n\nconfig.set("
    if not source.startswith(prefix):
        raise ConfigBindingError("karma_config_shape_mismatch")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ConfigBindingError("karma_config_duplicate_setting")
            result[key] = value
        return result
    try:
        settings, end = json.JSONDecoder(object_pairs_hook=unique_pairs).raw_decode(
            source, len(prefix))
    except (ValueError, TypeError) as error:
        raise ConfigBindingError("karma_config_shape_mismatch") from error
    if not isinstance(settings, dict) or not source[end:].startswith(");"):
        raise ConfigBindingError("karma_config_shape_mismatch")
    position = source.index(expected)
    if (source[end + 2:position] != APPROVED_GENERATOR_TAIL
            or not re.fullmatch(r"\s*}\s*", source[position + len(expected):])):
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
    approved = {
        "singleRun": True, "autoWatch": False, "basePath": str(package_root),
        "files": [runner, files[1]],
        "frameworks": ["webpack-output", "mocha", "webpack"],
        "client": {"args": []}, "browsers": ["Safari"], "customLaunchers": {},
        "failOnFailingTestSuite": False, "failOnEmptyTestSuite": False,
        "reporters": ["karma-kotlin-reporter"],
        "preprocessors": {runner: ["webpack", "sourcemap"],
                          files[1]: ["webpack", "sourcemap"]},
        "proxies": {}, "webpackCopy": [],
    }
    if settings != approved:
        raise ConfigBindingError("karma_config_source_mismatch")
    return observed


def committed_bytes(repository, candidate_sha, relative):
    relative = Path(relative)
    if (relative.is_absolute() or not relative.parts
            or any(part in ("", ".", "..") for part in relative.parts)
            or re.fullmatch(r"[0-9a-f]{40}", candidate_sha) is None):
        raise ValueError("invalid Safari candidate source path or commit")
    command = ["git", "--no-replace-objects", "-C", str(repository)]
    try:
        if subprocess.check_output(command + ["rev-parse", "--show-object-format"],
                                   stderr=subprocess.PIPE).strip() != b"sha1":
            raise ValueError("Safari candidate requires SHA-1 Git objects")
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Safari candidate object format is unavailable") from error

    objects = {}

    def read_object(oid, expected_kind):
        if oid in objects:
            kind, raw = objects[oid]
            if kind != expected_kind:
                raise ValueError(f"Safari candidate object type differs: {oid}")
            return raw
        try:
            size_raw = subprocess.check_output(command + ["cat-file", "-s", oid],
                                               stderr=subprocess.PIPE, timeout=15).strip()
            if re.fullmatch(rb"0|[1-9][0-9]*", size_raw) is None:
                raise ValueError(f"Safari candidate object size is invalid: {oid}")
            size = int(size_raw)
            if size > MAX_COMMITTED_OBJECT_BYTES:
                raise ValueError(f"Safari candidate object is oversized: {oid}")
            response = subprocess.check_output(command + ["cat-file", "--batch"],
                                               input=(oid + "\n").encode(),
                                               stderr=subprocess.PIPE, timeout=15)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ValueError(f"Safari candidate object is unavailable: {oid}") from error
        header = f"{oid} {expected_kind} {size}\n".encode()
        if not response.startswith(header) or len(response) != len(header) + size + 1 \
                or response[-1:] != b"\n":
            raise ValueError(f"Safari candidate object type or size differs: {oid}")
        raw = response[len(header):-1]
        identity = hashlib.sha1(expected_kind.encode() + b" " + str(size).encode()
                                + b"\0" + raw).hexdigest()
        if identity != oid:
            raise ValueError(f"Safari candidate object identity differs: {oid}")
        objects[oid] = (expected_kind, raw)
        return raw

    def tree_entries(oid):
        raw = read_object(oid, "tree")
        entries = {}
        position = 0
        while position < len(raw):
            separator = raw.find(b" ", position)
            end = raw.find(b"\0", separator + 1)
            if separator < position or end < 0 or end + 21 > len(raw):
                raise ValueError(f"Safari candidate tree entry is malformed: {oid}")
            mode = raw[position:separator]
            name = raw[separator + 1:end]
            child = raw[end + 1:end + 21].hex()
            if (not name or name in (b".", b"..") or b"/" in name
                    or name in entries):
                raise ValueError(f"Safari candidate tree has duplicate or invalid name: {oid}")
            entries[name] = (mode, child)
            position = end + 21
        return entries

    commit = read_object(candidate_sha, "commit")
    first_line = commit.split(b"\n", 1)[0]
    if re.fullmatch(rb"tree [0-9a-f]{40}", first_line) is None:
        raise ValueError("Safari candidate commit tree is invalid")
    tree = first_line[5:].decode()
    for part in relative.parts[:-1]:
        entry = tree_entries(tree).get(os.fsencode(part))
        if entry is None or entry[0] != b"40000":
            raise ValueError(f"Safari candidate source tree path differs: {relative}")
        tree = entry[1]
    entry = tree_entries(tree).get(os.fsencode(relative.parts[-1]))
    if entry is None or entry[0] not in (b"100644", b"100755"):
        raise ValueError(f"Safari candidate source is not a regular file: {relative}")
    return read_object(entry[1], "blob")


def committed_fragment(repository, candidate_sha):
    path = repository / SOURCE
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FRAGMENT_BYTES:
        raise ValueError("committed Safari reporter source is unsafe or oversized")
    current = path.read_bytes()
    committed = committed_bytes(repository, candidate_sha, SOURCE)
    if current != committed:
        raise ValueError("Safari reporter source differs from candidate")
    return committed


def open_directory_no_follow(repository, relative):
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        raise ValueError(f"unsafe Safari path: {relative}")
    directory = os.open(repository, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        return directory
    except BaseException:
        os.close(directory)
        raise


def same_directory(repository, relative, descriptor):
    try:
        current = open_directory_no_follow(repository, relative)
    except OSError:
        return False
    try:
        before, after = os.fstat(descriptor), os.fstat(current)
        return (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
    finally:
        os.close(current)


def read_generated_config(repository, relative):
    if os.name == "nt":
        from safari_windows_file import LockedDirectory
        with LockedDirectory(repository, relative.parent) as directory:
            descriptor = directory.open_file(relative.name)
            try:
                before = os.fstat(descriptor)
                if before.st_size > MAX_FRAGMENT_BYTES:
                    raise ValueError(f"unsafe or oversized Safari generated config: {relative}")
                data = os.read(descriptor, MAX_FRAGMENT_BYTES + 1)
                after = os.fstat(descriptor)
                identity = lambda item: (item.st_dev, item.st_ino, item.st_size,
                                         item.st_mtime_ns, item.st_ctime_ns)
                if len(data) != before.st_size or identity(before) != identity(after):
                    raise ValueError(f"Safari generated config changed while reading: {relative}")
                return data, before
            finally:
                os.close(descriptor)
    directory = open_directory_no_follow(repository, relative.parent)
    try:
        descriptor = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FRAGMENT_BYTES:
                raise ValueError(f"unsafe or oversized Safari generated config: {relative}")
            data = os.read(descriptor, MAX_FRAGMENT_BYTES + 1)
            after = os.fstat(descriptor)
            identity = lambda item: (item.st_dev, item.st_ino, item.st_size,
                                     item.st_mtime_ns, item.st_ctime_ns)
            if len(data) != before.st_size or identity(before) != identity(after):
                raise ValueError(f"Safari generated config changed while reading: {relative}")
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)
    current_dir = open_directory_no_follow(repository, relative.parent)
    try:
        current = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                          dir_fd=current_dir)
        try:
            if identity(before) != identity(os.fstat(current)):
                raise ValueError(f"Safari generated config path identity changed: {relative}")
        finally:
            os.close(current)
    finally:
        os.close(current_dir)
    return data, before


def _forensic(directory, name, output, relative):
    record = {"path": str(relative), "original_size": None, "retained_size": 0}
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
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


def _forensic_windows(directory, name, output, relative):
    record = {"path": str(relative), "original_size": None, "retained_size": 0}
    try:
        descriptor = directory.open_file(name)
        try:
            before = os.fstat(descriptor)
            record["original_size"] = before.st_size
            data = os.read(descriptor, min(before.st_size, MAX_FRAGMENT_BYTES))
            after = os.fstat(descriptor)
            if (len(data) != min(before.st_size, MAX_FRAGMENT_BYTES) or
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise ValueError("staged reporter changed during forensic capture")
        finally:
            os.close(descriptor)
        destination = output / "forensic/safari-reporter" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)
        record.update(archive_path=destination.relative_to(output).as_posix(),
                      retained_size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                      truncated=before.st_size > MAX_FRAGMENT_BYTES)
    except (OSError, ValueError) as error:
        record["error"] = str(error)
    return record


@contextmanager
def _stage_windows(repository, projects, content, output, result):
    from safari_windows_file import LockedDirectory
    created = []
    try:
        for project in projects:
            relative = Path(project)
            root = LockedDirectory(repository, relative)
            try:
                stage_path = root.path / "karma.config.d"
                stage_path.mkdir()
            except BaseException:
                root.close()
                raise
            created.append((relative, root, None))
            directory = root.child("karma.config.d", removable=True)
            created[-1] = (relative, root, directory)
            with (stage_path / STAGED_NAME).open("xb") as staged:
                staged.write(content)
            result["projects"][relative.as_posix()] = "STAGED"
        yield result
    finally:
        for relative, root, directory in reversed(created):
            key = relative.as_posix()
            if directory is None:
                result["status"] = "CHANGED"
                result["projects"][key] = "LEFTOVER"
                result["forensic"].append({"path": str(relative / "karma.config.d"),
                                           "error": "staging directory handle unavailable"})
                root.close()
                continue
            try:
                try:
                    descriptor = directory.open_file(STAGED_NAME)
                    try:
                        observed = os.fstat(descriptor)
                        unchanged = (observed.st_size == len(content) and
                                     os.read(descriptor, len(content) + 1) == content)
                    finally:
                        os.close(descriptor)
                except (OSError, ValueError):
                    unchanged = False
                if not unchanged:
                    result["status"] = "CHANGED"
                    result["projects"][key] = "CHANGED"
                    result["forensic"].append(_forensic_windows(
                        directory, STAGED_NAME, output, relative / STAGED_NAME))
                else:
                    result["projects"][key] = "CLEAN"
                try:
                    (directory.path / STAGED_NAME).unlink(missing_ok=True)
                except OSError as error:
                    result["status"] = "CHANGED"
                    result["projects"][key] = "LEFTOVER"
                    result["forensic"].append({"path": str(relative / STAGED_NAME),
                                               "error": str(error)})
                try:
                    with os.scandir(directory.path) as entries:
                        leftovers = sorted(item.name for item in itertools.islice(entries, 17))
                except OSError as error:
                    leftovers = []
                    result["status"] = "CHANGED"
                    result["projects"][key] = "LEFTOVER"
                    result["forensic"].append({"path": str(relative / "karma.config.d"),
                                               "error": str(error)})
                if leftovers:
                    result["status"] = "CHANGED"
                    result["projects"][key] = "LEFTOVER"
                    result.setdefault("leftovers", {})[key] = leftovers[:16]
                    if len(leftovers) > 16:
                        result.setdefault("leftovers_truncated", []).append(key)
                    for name in leftovers[:16]:
                        result["forensic"].append(_forensic_windows(
                            directory, name, output, relative / name))
            finally:
                if not result.get("leftovers", {}).get(key):
                    try:
                        directory.remove_empty()
                    except (OSError, ValueError) as error:
                        result["status"] = "CHANGED"
                        result["projects"][key] = "LEFTOVER"
                        result["forensic"].append({"path": str(relative / "karma.config.d"),
                                                   "error": str(error)[:512]})
                directory.close()
                try:
                    (root.path / "karma.config.d").lstat()
                    residue = True
                except FileNotFoundError:
                    residue = False
                except OSError:
                    residue = True
                if residue:
                    result["status"] = "CHANGED"
                    result["projects"][key] = "LEFTOVER"
                    result["forensic"].append({"path": str(relative / "karma.config.d"),
                                               "error": "staging directory remains after cleanup"})
                root.close()


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
    if os.name == "nt":
        try:
            with _stage_windows(repository, projects, content, output, result) as staged:
                yield staged
        except (OSError, ValueError) as error:
            if result["status"] != "CLEAN":
                raise StageFailure(result) from error
            raise
        return
    created = []
    try:
        for project in projects:
            relative = Path(project)
            root = open_directory_no_follow(repository, relative)
            try:
                os.mkdir("karma.config.d", dir_fd=root)
                directory = os.open("karma.config.d", os.O_RDONLY | os.O_DIRECTORY |
                                    os.O_NOFOLLOW, dir_fd=root)
            except BaseException:
                os.close(root)
                raise
            created.append((relative, root, directory))
            descriptor = os.open(STAGED_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(descriptor, "wb") as staged:
                staged.write(content)
            result["projects"][relative.as_posix()] = "STAGED"
        yield result
    finally:
        for relative, root, directory in reversed(created):
            key = relative.as_posix()
            try:
                root_same = same_directory(repository, relative, root)
                try:
                    linked = os.stat("karma.config.d", dir_fd=root, follow_symlinks=False)
                    held = os.fstat(directory)
                    directory_same = (linked.st_dev, linked.st_ino) == (held.st_dev, held.st_ino)
                except OSError:
                    directory_same = False
                if not root_same or not directory_same:
                    result["status"] = "CHANGED"
                    result["projects"][key] = "DIRECTORY_CHANGED"
                    result["forensic"].append({"path": str(relative / "karma.config.d"),
                                               "error": "staging ancestor identity changed"})
                try:
                    staged = os.open(STAGED_NAME, os.O_RDONLY | os.O_NOFOLLOW |
                                     os.O_NONBLOCK, dir_fd=directory)
                    try:
                        observed = os.fstat(staged)
                        unchanged = (stat.S_ISREG(observed.st_mode)
                                     and observed.st_size == len(content)
                                     and os.read(staged, len(content) + 1) == content)
                    finally:
                        os.close(staged)
                except OSError:
                    unchanged = False
                if not unchanged:
                    result["status"] = "CHANGED"
                    if root_same and directory_same:
                        result["projects"][key] = "CHANGED"
                    result["forensic"].append(_forensic(
                        directory, STAGED_NAME, output, relative / STAGED_NAME))
                elif root_same and directory_same:
                    result["projects"][key] = "CLEAN"
                try:
                    os.unlink(STAGED_NAME, dir_fd=directory)
                except FileNotFoundError:
                    pass
                except OSError as error:
                    result["status"] = "CHANGED"
                    result["projects"][key] = "LEFTOVER"
                    result["forensic"].append({"path": str(relative / STAGED_NAME),
                                               "error": str(error)})
                try:
                    scan = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                   dir_fd=directory)
                    try:
                        with os.scandir(scan) as entries:
                            leftovers = sorted(item.name for item in itertools.islice(entries, 17))
                    finally:
                        os.close(scan)
                except OSError as error:
                    result["status"] = "CHANGED"
                    result["projects"][key] = "LEFTOVER"
                    result["forensic"].append({"path": str(relative / "karma.config.d"),
                                               "error": str(error)})
                    continue
                if leftovers:
                    result["status"] = "CHANGED"
                    if root_same and directory_same:
                        result["projects"][key] = "LEFTOVER"
                    result.setdefault("leftovers", {})[key] = leftovers[:16]
                    if len(leftovers) > 16:
                        result.setdefault("leftovers_truncated", []).append(key)
                    for name in leftovers[:16]:
                        result["forensic"].append(_forensic(
                            directory, name, output, relative / name))
                elif directory_same:
                    try:
                        os.rmdir("karma.config.d", dir_fd=root)
                    except OSError as error:
                        result["status"] = "CHANGED"
                        result["projects"][key] = "LEFTOVER"
                        result["forensic"].append({"path": str(relative / "karma.config.d"),
                                                   "error": str(error)})
            finally:
                os.close(directory)
                os.close(root)
