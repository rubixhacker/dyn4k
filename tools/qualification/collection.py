#!/usr/bin/env python3
import argparse
import contextlib
import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import independent_gates
import qualify


SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
REQUIRED = ("full-ci", "full-common", "publication-ubuntu", "duplicate-provider")
SOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
MAX_SOURCE_BYTES = 10 * 1024**3
MAX_EXPANDED_BYTES = 20 * 1024**3
MAX_MEMBERS = 200_000
WINDOWS_REPARSE_ATTRIBUTE = 0x400
WINDOWS_DIRECTORY_ATTRIBUTE = 0x10
WINDOWS_OPEN_REPARSE_POINT = 0x00200000
WINDOWS_OBJ_DONT_REPARSE = 0x1000


def digest(path, limit=None, expected=None):
    hashed = hashlib.sha256()
    total = 0
    with _anchored_open(path, expected=expected) as source:
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            if limit is not None and total > limit:
                raise ValueError("source file exceeds byte bound")
            hashed.update(chunk)
    return hashed.hexdigest()


def source_tree(repository, candidate_sha):
    if not SHA40.fullmatch(candidate_sha):
        raise ValueError("candidate SHA must be a full Git commit")
    head, tree = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "rev-parse",
         "HEAD", f"{candidate_sha}^{{tree}}"], text=True).splitlines()
    if head != candidate_sha or not SHA40.fullmatch(tree):
        raise ValueError("collector checkout differs from exact candidate")
    return tree


def artifact_route(name, candidate_sha):
    routes = {
        f"full-ci-{candidate_sha}": "full-ci",
        f"full-common-{candidate_sha}": "full-common",
        f"publication-{candidate_sha}-ubuntu": "publication-ubuntu",
        f"publication-{candidate_sha}-macos": "publication-macos",
        f"publication-{candidate_sha}-windows": "publication-windows",
        f"duplicate-provider-{candidate_sha}": "duplicate-provider",
        f"qualification-{candidate_sha}": "qualification-ubuntu",
    }
    if name in routes:
        return routes[name]
    for prefix, route in (("qualification-full-", "full-hosted-"),
                          ("qualification-", "qualification-"),
                          ("windows-failure-raw-", "windows-failure-raw-")):
        match = re.fullmatch(re.escape(prefix) + r"([0-9a-f]{40})-(.+)", name)
        if match:
            if match.group(1) != candidate_sha:
                raise ValueError(f"artifact belongs to another candidate: {name}")
            return route + match.group(2)
    if re.search(r"[0-9a-f]{40}", name):
        raise ValueError(f"unrecognized candidate artifact: {name}")
    raise ValueError(f"artifact has no exact candidate SHA: {name}")


def files_in(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("artifact root is missing or symbolic")
    files = {}
    for base, directories, filenames in os.walk(root, followlinks=False):
        for name in directories + filenames:
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            independent_gates._file_path_name(relative)
            if path.is_symlink():
                raise ValueError(f"symbolic artifact path: {relative}")
            if path.is_file():
                files[relative] = digest(path)
            elif not path.is_dir():
                raise ValueError(f"nonregular artifact path: {relative}")
    return dict(sorted(files.items()))


def checked_tar(path, destination):
    destination.mkdir(parents=True, exist_ok=False)
    seen = set()
    with tarfile.open(path, "r:*") as archive:
        for item in archive:
            name = item.name.removeprefix("./")
            if name in ("", "."):
                continue
            independent_gates._file_path_name(name)
            if name in seen or not (item.isfile() or item.isdir()):
                raise ValueError("archive has duplicate or nonregular members")
            seen.add(name)
            target = destination.joinpath(*name.split("/"))
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(item) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
            stamp = item.pax_headers.get("dyn4k.mtime_ns")
            if stamp is not None:
                if not stamp.isdecimal():
                    raise ValueError("archive timestamp is invalid")
                os.utime(target, ns=(int(stamp), int(stamp)))
    return destination


def _keys(value, required, optional=()):
    if (not isinstance(value, dict) or not set(required) <= set(value)
            or set(value) - set(required) - set(optional)):
        raise ValueError("source index object keys are invalid")


def _strict_json_bytes(data):
    return json.loads(data,
                      object_pairs_hook=independent_gates._strict_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError(f"non-finite JSON value: {value}")))


def _strict_json(path):
    return _strict_json_bytes(_read_anchored(path))


def _read_anchored(path):
    with _anchored_open(path) as source:
        data = source.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            raise ValueError("source file exceeds byte bound")
        source.seek(0)
        if source.read(MAX_SOURCE_BYTES + 1) != data:
            raise ValueError("source file changed while read")
    return data


def _positive(value):
    return type(value) is int and value > 0


def _safe_source_path(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("local source path must be absolute")
    for part in (path, *path.parents):
        try:
            mode = os.lstat(part)
        except FileNotFoundError:
            continue
        if _is_reparse(mode):
            raise ValueError("symbolic source path is forbidden")
    return path


def _is_reparse(info):
    return (stat.S_ISLNK(info.st_mode)
            or bool(getattr(info, "st_file_attributes", 0)
                    & WINDOWS_REPARSE_ATTRIBUTE))


def _path_identity(path):
    _safe_source_path(Path(path).absolute())
    info = os.lstat(path)
    if _is_reparse(info):
        raise ValueError("symbolic source path is forbidden")
    if os.name == "nt" and not info.st_ino:
        raise ValueError("source file identity is unavailable")
    return info.st_dev, info.st_ino


def _windows_open(path, directory=False):
    class AttributeTag(ctypes.Structure):
        _fields_ = [("attributes", ctypes.c_ulong), ("tag", ctypes.c_ulong)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = (ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                                   ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                                   ctypes.c_void_p)
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.GetFileInformationByHandleEx.argtypes = (
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong)
    kernel.GetFileInformationByHandleEx.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.CloseHandle.restype = ctypes.c_int
    flags = WINDOWS_OPEN_REPARSE_POINT | (0x02000000 if directory else 0)
    access = 0x1000a1 if directory else 0x80000000
    share = 3 if directory else 1
    handle = kernel.CreateFileW(str(path), access, share, None, 3, flags, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        info = AttributeTag()
        if not kernel.GetFileInformationByHandleEx(handle, 9, ctypes.byref(info),
                                                   ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes & WINDOWS_REPARSE_ATTRIBUTE:
            raise ValueError("symbolic source path is forbidden")
        if bool(info.attributes & WINDOWS_DIRECTORY_ATTRIBUTE) != directory:
            raise ValueError("source path has wrong file type")
        return handle
    except BaseException:
        kernel.CloseHandle(handle)
        raise


def _windows_close(handle):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.CloseHandle.restype = ctypes.c_int
    kernel.CloseHandle(handle)


def _windows_handle_identity(handle):
    class FileIdInfo(ctypes.Structure):
        _fields_ = [("volume", ctypes.c_ulonglong),
                    ("identifier", ctypes.c_ubyte * 16)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetFileInformationByHandleEx.argtypes = (
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong)
    kernel.GetFileInformationByHandleEx.restype = ctypes.c_int
    info = FileIdInfo()
    if not kernel.GetFileInformationByHandleEx(handle, 18, ctypes.byref(info),
                                               ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    identity = int.from_bytes(bytes(info.identifier), "little")
    if not identity:
        raise ValueError("source directory identity is unavailable")
    return identity


def _windows_relative_open(parent, name, directory):
    # Resolve one child against its open parent handle.
    if name in ("", ".", "..") or any(character in name for character in "\\/\x00:"):
        raise ValueError("unsafe source path component")

    class UnicodeString(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("maximum", ctypes.c_ushort),
                    ("buffer", ctypes.c_void_p)]

    class ObjectAttributes(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("root", ctypes.c_void_p),
                    ("name", ctypes.POINTER(UnicodeString)),
                    ("attributes", ctypes.c_ulong), ("security", ctypes.c_void_p),
                    ("quality", ctypes.c_void_p)]

    class IoStatus(ctypes.Structure):
        _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]

    encoded = name.encode("utf-16-le")
    if len(encoded) > 65532:
        raise ValueError("source path component is too long")
    buffer = ctypes.create_unicode_buffer(name)
    unicode_name = UnicodeString(len(encoded), len(encoded) + 2,
                                 ctypes.cast(buffer, ctypes.c_void_p))
    attributes = ObjectAttributes(ctypes.sizeof(ObjectAttributes), parent,
                                  ctypes.pointer(unicode_name),
                                  WINDOWS_OBJ_DONT_REPARSE | 0x40, None, None)
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtCreateFile.argtypes = (
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_ulong,
        ctypes.POINTER(ObjectAttributes), ctypes.POINTER(IoStatus), ctypes.c_void_p,
        ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.c_void_p, ctypes.c_ulong)
    ntdll.NtCreateFile.restype = ctypes.c_long
    handle = ctypes.c_void_p()
    result = IoStatus()
    access = (0x1000a1 if directory else 0x80100080)
    status = ntdll.NtCreateFile(ctypes.byref(handle), access,
                                ctypes.byref(attributes), ctypes.byref(result),
                                None, 0, 3 if directory else 1, 1,
                                WINDOWS_OPEN_REPARSE_POINT | 0x20, None, 0)
    if status != 0:
        raise OSError(f"anchored source open failed: NTSTATUS 0x{status & 0xffffffff:08x}")
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        class AttributeTag(ctypes.Structure):
            _fields_ = [("attributes", ctypes.c_ulong), ("tag", ctypes.c_ulong)]
        kernel.GetFileInformationByHandleEx.argtypes = (
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong)
        kernel.GetFileInformationByHandleEx.restype = ctypes.c_int
        info = AttributeTag()
        if not kernel.GetFileInformationByHandleEx(handle, 9, ctypes.byref(info),
                                                   ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes & WINDOWS_REPARSE_ATTRIBUTE:
            raise ValueError("symbolic source path is forbidden")
        if bool(info.attributes & WINDOWS_DIRECTORY_ATTRIBUTE) != directory:
            raise ValueError("source path has wrong file type")
        return handle.value
    except BaseException:
        _windows_close(handle.value)
        raise


def _windows_names(handle):
    class IoStatus(ctypes.Structure):
        _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]

    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtQueryDirectoryFile.argtypes = (
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(IoStatus), ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
        ctypes.c_ubyte, ctypes.c_void_p, ctypes.c_ubyte)
    ntdll.NtQueryDirectoryFile.restype = ctypes.c_long
    names = []
    seen = set()
    buffer = ctypes.create_string_buffer(65536)
    first = True
    while True:
        result = IoStatus()
        status = ntdll.NtQueryDirectoryFile(
            handle, None, None, None, ctypes.byref(result), buffer,
            len(buffer), 12, 0, None, int(first))
        if (status & 0xffffffff) == 0x80000006:
            break
        if (status & 0xffffffff) == 0xc000000f and first:
            break
        if status != 0 or not 12 <= result.information <= len(buffer):
            raise OSError(f"anchored directory query failed: NTSTATUS 0x{status & 0xffffffff:08x}")
        first = False
        offset = 0
        while True:
            if offset + 12 > result.information:
                raise ValueError("anchored directory entry is truncated")
            next_offset = int.from_bytes(buffer.raw[offset:offset + 4], "little")
            name_size = int.from_bytes(buffer.raw[offset + 8:offset + 12], "little")
            if (not name_size or name_size % 2 or
                    offset + 12 + name_size > result.information):
                raise ValueError("anchored directory name is invalid")
            name = buffer.raw[offset + 12:offset + 12 + name_size].decode("utf-16-le")
            if name not in (".", ".."):
                if name in seen:
                    raise ValueError("duplicate source directory member")
                if len(names) >= MAX_MEMBERS:
                    raise ValueError("source directory exceeds transport bounds")
                seen.add(name)
                names.append(name)
            if next_offset == 0:
                break
            if next_offset < 12 + name_size or offset + next_offset >= result.information:
                raise ValueError("anchored directory entry offset is invalid")
            offset += next_offset
    return names


def _open_windows_no_reparse(path, parent):
    import msvcrt

    handle = _windows_relative_open(parent, Path(path).name, directory=False)
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        handle = None
        return descriptor
    finally:
        if handle is not None:
            _windows_close(handle)


@contextlib.contextmanager
def _anchored_open(path, directory=False, expected=None):
    path = _safe_source_path(Path(path).absolute())
    before = os.lstat(path)
    if (_is_reparse(before) or
            not (stat.S_ISDIR(before.st_mode) if directory else
                 stat.S_ISREG(before.st_mode))):
        raise ValueError("source path is symbolic or has wrong file type")
    if expected is not None and (before.st_dev, before.st_ino) != expected:
        raise ValueError("source path changed before it was opened")
    parts = path.parts
    with contextlib.ExitStack() as stack:
        if os.name == "nt":
            prefix = Path(parts[0])
            parents = parts[1:] if directory else parts[1:-1]
            handle = _windows_open(prefix, directory=True)
            stack.callback(_windows_close, handle)
            for part in parents:
                prefix = prefix / part
                handle = _windows_relative_open(handle, part, directory=True)
                stack.callback(_windows_close, handle)
            if directory:
                opened = handle
            else:
                descriptor = _open_windows_no_reparse(path, handle)
                opened = stack.enter_context(os.fdopen(descriptor, "rb"))
        else:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            descriptor = os.open(parts[0], flags)
            stack.callback(os.close, descriptor)
            for position, part in enumerate(parts[1:], 1):
                final = position == len(parts) - 1
                selected = (os.O_RDONLY | os.O_NOFOLLOW |
                            (os.O_DIRECTORY if not final or directory else 0))
                descriptor = os.open(part, selected, dir_fd=descriptor)
                stack.callback(os.close, descriptor)
            opened = descriptor if directory else os.fdopen(os.dup(descriptor), "rb")
            if not directory:
                stack.enter_context(opened)
        _safe_source_path(path)
        after = os.lstat(path)
        if (_is_reparse(after) or
                (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)):
            raise ValueError("source path changed or became symbolic while opened")
        if not directory:
            info = os.fstat(opened.fileno())
            if (not stat.S_ISREG(info.st_mode)
                    or (os.name == "nt" and not info.st_ino)
                    or (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino)):
                raise ValueError("source file changed or became symbolic while opened")
        elif os.name == "nt":
            if before.st_ino != _windows_handle_identity(opened):
                raise ValueError("source directory changed while opened")
        elif os.name != "nt":
            info = os.fstat(opened)
            if (not stat.S_ISDIR(info.st_mode)
                    or (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino)):
                raise ValueError("source directory changed while opened")
        yield opened
        _safe_source_path(path)
        finished = os.lstat(path)
        if (_is_reparse(finished) or
                (before.st_dev, before.st_ino) != (finished.st_dev, finished.st_ino)):
            raise ValueError("source path changed while read")


@contextlib.contextmanager
def _directory_names(anchor):
    if os.name == "nt":
        yield _windows_names(anchor)
    else:
        with os.scandir(anchor) as members:
            yield (member.name for member in members)


def _file_inventory(root):
    root = Path(root)
    root_info = os.lstat(root)
    if _is_reparse(root_info) or not stat.S_ISDIR(root_info.st_mode):
        raise ValueError("source directory is missing or symbolic")
    files = {}
    count = 0
    total = 0

    def visit(current, expected):
        nonlocal count, total
        with _anchored_open(current, directory=True, expected=expected) as anchor:
            with _directory_names(anchor) as names:
                for name in names:
                    path = current / name
                    relative = path.relative_to(root).as_posix()
                    independent_gates._file_path_name(relative)
                    info = os.lstat(path)
                    if _is_reparse(info):
                        raise ValueError(f"symbolic source member: {relative}")
                    identity = info.st_dev, info.st_ino
                    count += 1
                    if count > MAX_MEMBERS:
                        raise ValueError("source directory exceeds transport bounds")
                    if stat.S_ISDIR(info.st_mode):
                        visit(path, identity)
                    elif stat.S_ISREG(info.st_mode):
                        total += info.st_size
                        if total > MAX_EXPANDED_BYTES:
                            raise ValueError("source directory exceeds transport bounds")
                        hashed = digest(path, expected=identity)
                        if (_path_identity(path) != identity
                                or os.lstat(path).st_size != info.st_size):
                            raise ValueError("source directory changed while inventoried")
                        files[relative] = {"size": info.st_size, "sha256": hashed}
                    else:
                        raise ValueError(f"nonregular source member: {relative}")

    visit(root, (root_info.st_dev, root_info.st_ino))
    return dict(sorted(files.items()))


def _inventory_digest(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _validate_index(index, candidate_sha, tree, manifest, repository_name,
                    run_id, run_attempt, allow_local=True):
    _keys(index, ("schema", "candidate_sha", "source_tree", "sources", "bindings"))
    if (type(index["schema"]) is not int or index["schema"] != 1
            or index["candidate_sha"] != candidate_sha
            or index["source_tree"] != tree):
        raise ValueError("source index candidate or tree differs")
    if not isinstance(index["sources"], list) or not isinstance(index["bindings"], list):
        raise ValueError("source index lists are invalid")
    ids, artifacts, bindings = set(), set(), set()
    for source in index["sources"]:
        _keys(source, ("id", "origin", "transport"))
        source_id = source["id"]
        if (not isinstance(source_id, str) or not SOURCE_ID.fullmatch(source_id)
                or source_id in ids):
            raise ValueError("source index has duplicate or unsafe source ID")
        ids.add(source_id)
        origin, transport = source["origin"], source["transport"]
        if not isinstance(origin, dict):
            raise ValueError("source origin is invalid")
        kind = origin["kind"]
        if kind == "local":
            if not allow_local:
                raise ValueError("workflow token cannot read arbitrary local source paths")
            _keys(origin, ("kind", "path"))
            _safe_source_path(origin["path"])
        elif kind in ("same_run", "github_actions"):
            common = ("kind", "repository", "workflow", "run_id", "run_attempt",
                      "name", "head_sha")
            _keys(origin, common + (("artifact_id", "api_size_in_bytes")
                                    if kind == "github_actions" else ()))
            if (origin["repository"] != repository_name
                    or origin["workflow"] != ".github/workflows/qualification.yml"
                    or origin["head_sha"] != candidate_sha
                    or not _positive(origin["run_id"])
                    or not _positive(origin["run_attempt"])
                    or not isinstance(origin["name"], str) or not origin["name"]):
                raise ValueError("source run, workflow, head, or artifact name differs")
            if kind == "same_run":
                if origin["run_id"] != run_id or origin["run_attempt"] != run_attempt:
                    raise ValueError("same-run source identity differs")
                if origin["run_attempt"] != 1:
                    raise ValueError("same-run artifact lacks rerun attempt ownership proof")
                artifact_route(origin["name"], candidate_sha)
            else:
                artifact_id = origin.get("artifact_id")
                if (not _positive(artifact_id) or artifact_id in artifacts
                        or not _positive(origin["api_size_in_bytes"])):
                    raise ValueError("duplicate or invalid GitHub artifact ID")
                artifacts.add(artifact_id)
        else:
            raise ValueError("source origin kind is invalid")
        _keys(transport, ("format",), ("size", "sha256", "files", "inventory_sha256"))
        fmt = transport["format"]
        if fmt == "directory":
            _keys(transport, ("format", "files", "inventory_sha256"))
            files = transport["files"]
            if (not isinstance(files, dict) or not files
                    or len(files) > MAX_MEMBERS):
                raise ValueError("source directory inventory is invalid")
            total = 0
            for path, record in files.items():
                independent_gates._file_path_name(path)
                _keys(record, ("size", "sha256"))
                if (type(record["size"]) is not int or record["size"] < 0
                        or not SHA64.fullmatch(str(record["sha256"]))):
                    raise ValueError("source directory file pin is invalid")
                total += record["size"]
            if (total > MAX_EXPANDED_BYTES
                    or transport["inventory_sha256"] != _inventory_digest(files)):
                raise ValueError("source directory inventory digest differs")
        elif fmt in ("zip", "tar", "tar.gz"):
            _keys(transport, ("format", "size", "sha256"))
            if (not _positive(transport["size"])
                    or transport["size"] > MAX_SOURCE_BYTES
                    or not SHA64.fullmatch(str(transport["sha256"]))):
                raise ValueError("source archive byte pin is invalid")
        else:
            raise ValueError("source transport format is invalid")
        if kind == "github_actions" and fmt != "zip":
            raise ValueError("GitHub Actions artifact transport must be ZIP")
    for binding in index["bindings"]:
        _keys(binding, ("source_id", "gate", "lane"), ("member_root", "target"))
        source_id, gate, lane = binding["source_id"], binding["gate"], binding["lane"]
        if source_id not in ids:
            raise ValueError("binding names an absent source")
        if lane is None:
            if gate not in independent_gates.GLOBAL_GATES:
                raise ValueError("global binding gate is not approved")
            target = binding.get("target")
            if target is not None and target not in {row["target"]
                                                      for row in manifest["lanes"].values()}:
                raise ValueError("global binding target is not approved")
        elif (lane not in manifest["lanes"] or gate not in
              manifest["lanes"][lane]["required_gates"]):
            raise ValueError("lane or gate binding is not approved")
        elif ("target" in binding and binding["target"] !=
              manifest["lanes"][lane]["target"]):
            raise ValueError("lane binding target differs from approved target")
        key = (lane, gate)
        if key in bindings:
            raise ValueError("duplicate lane or global gate binding")
        bindings.add(key)
        if "member_root" in binding:
            independent_gates._file_path_name(binding["member_root"])
    if ids != {binding["source_id"] for binding in index["bindings"]}:
        raise ValueError("source index has unbound source")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


def _github_request(url, token, destination=None, limit=None):
    headers = {"Accept": "application/vnd.github+json",
               "Authorization": f"Bearer {token}",
               "X-GitHub-Api-Version": "2022-11-28"}
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        response = opener.open(request, timeout=60)
    except urllib.error.HTTPError as error:
        if destination is None or error.code not in (301, 302, 303, 307, 308):
            raise ValueError(f"GitHub artifact API returned HTTP {error.code}") from error
        location = error.headers.get("Location", "")
        parsed = urllib.parse.urlparse(location)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("GitHub artifact redirect is not HTTPS") from error
        response = urllib.request.urlopen(urllib.request.Request(location), timeout=60)
    with response:
        if destination is None:
            return json.load(response)
        size = 0
        with Path(destination).open("wb") as output:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise ValueError("GitHub artifact download exceeds pinned byte limit")
                output.write(chunk)
    return size


def _github_artifact(origin, candidate_sha, token, destination, expected_size):
    if not token:
        raise ValueError("GitHub Actions token is unavailable")
    repository = origin["repository"]
    base = f"https://api.github.com/repos/{repository}/actions"
    run = _github_request(f"{base}/runs/{origin['run_id']}", token)
    artifact = _github_request(f"{base}/artifacts/{origin['artifact_id']}", token)
    workflow_run = artifact.get("workflow_run") or {}
    if (run.get("id") != origin["run_id"]
            or run.get("head_sha") != candidate_sha
            or run.get("run_attempt") != origin["run_attempt"]
            or run.get("path", "").split("@", 1)[0] != origin["workflow"]
            or (run.get("repository") or {}).get("full_name") != repository
            or artifact.get("id") != origin["artifact_id"]
            or artifact.get("name") != origin["name"]
            or artifact.get("expired") is not False
            or workflow_run.get("id") != origin["run_id"]
            or workflow_run.get("head_sha") != candidate_sha
            or workflow_run.get("repository_id") != (run.get("repository") or {}).get("id")):
        raise ValueError("GitHub run or artifact source identity differs")
    if origin["run_attempt"] != 1:
        raise ValueError("artifact API does not prove rerun attempt ownership")
    if (artifact.get("size_in_bytes") != origin["api_size_in_bytes"]
            or artifact["size_in_bytes"] > MAX_SOURCE_BYTES):
        raise ValueError("GitHub artifact API byte size differs")
    _github_request(f"{base}/artifacts/{origin['artifact_id']}/zip", token,
                    destination, expected_size)
    return {"run_id": run["id"], "run_attempt": run["run_attempt"],
            "artifact_id": artifact["id"], "name": artifact["name"],
            "head_sha": run["head_sha"], "workflow": origin["workflow"],
            "api_size_in_bytes": artifact["size_in_bytes"]}


def _copy_regular(source, destination, limit=None, preflight=True, expected=None):
    if limit is None:
        limit = MAX_SOURCE_BYTES
    with _anchored_open(source, expected=expected) as original:
        source_stat = os.fstat(original.fileno())
        if not stat.S_ISREG(source_stat.st_mode):
            raise ValueError("source file is not regular")
        if preflight and source_stat.st_size > limit:
            raise ValueError("source file exceeds byte bound")
        total = 0
        with Path(destination).open("wb") as frozen:
            while chunk := original.read(min(1024 * 1024, limit - total + 1)):
                remaining = limit - total
                if len(chunk) > remaining:
                    frozen.write(chunk[:remaining])
                    raise ValueError("source file exceeds byte bound while copied")
                frozen.write(chunk)
                total += len(chunk)
        if total != source_stat.st_size:
            raise ValueError("source file changed size while copied")
        _safe_source_path(Path(source).absolute())
        after = os.lstat(source)
        if (_is_reparse(after) or (after.st_dev, after.st_ino) !=
                (source_stat.st_dev, source_stat.st_ino)):
            raise ValueError("source file changed or became symbolic while copied")
    return total


def _copy_directory(source, destination):
    source, destination = Path(source), Path(destination)
    root_info = os.lstat(source)
    if _is_reparse(root_info) or not stat.S_ISDIR(root_info.st_mode):
        raise ValueError("source directory is missing or symbolic")
    destination.mkdir(parents=True, exist_ok=False)
    count = 0
    total = 0

    def visit(current, frozen, expected):
        nonlocal count, total
        with _anchored_open(current, directory=True, expected=expected) as anchor:
            with _directory_names(anchor) as names:
                for name in names:
                    path = current / name
                    relative = path.relative_to(source).as_posix()
                    independent_gates._file_path_name(relative)
                    count += 1
                    if count > MAX_MEMBERS:
                        raise ValueError("source directory exceeds transport bounds")
                    target = frozen / name
                    info = os.lstat(path)
                    if _is_reparse(info):
                        raise ValueError(f"symbolic source member: {relative}")
                    identity = info.st_dev, info.st_ino
                    if stat.S_ISDIR(info.st_mode):
                        target.mkdir()
                        visit(path, target, identity)
                    elif stat.S_ISREG(info.st_mode):
                        try:
                            total += _copy_regular(path, target,
                                                   limit=MAX_EXPANDED_BYTES - total,
                                                   preflight=False, expected=identity)
                        except ValueError as error:
                            if "exceeds byte bound" in str(error):
                                raise ValueError(
                                    "source directory exceeds transport bounds while copied"
                                ) from error
                            raise
                    else:
                        raise ValueError(f"nonregular source member: {relative}")

    visit(source, destination, (root_info.st_dev, root_info.st_ino))


def _extract_transport(packed, fmt, destination):
    destination.mkdir(parents=True, exist_ok=False)
    seen = set()
    total = 0
    if fmt == "zip":
        with zipfile.ZipFile(packed) as archive:
            members = archive.infolist()
            if len(members) > MAX_MEMBERS:
                raise ValueError("ZIP member count exceeds bound")
            for member in members:
                name = member.filename.rstrip("/")
                independent_gates._file_path_name(name)
                if name in seen:
                    raise ValueError("duplicate archive member")
                seen.add(name)
                mode = stat.S_IFMT(member.external_attr >> 16)
                directory = member.is_dir()
                if mode not in (0, stat.S_IFDIR if directory else stat.S_IFREG):
                    raise ValueError("nonregular ZIP member")
                total += member.file_size
                if total > MAX_EXPANDED_BYTES:
                    raise ValueError("ZIP expanded bytes exceed bound")
                target = destination.joinpath(*name.split("/"))
                if directory:
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as original, target.open("wb") as frozen:
                        shutil.copyfileobj(original, frozen, 1024 * 1024)
                    if target.stat().st_size != member.file_size:
                        raise ValueError("ZIP member byte count differs")
    else:
        with tarfile.open(packed, "r:*") as archive:
            for member in archive:
                name = member.name.rstrip("/")
                independent_gates._file_path_name(name)
                if name in seen:
                    raise ValueError("duplicate archive member")
                seen.add(name)
                if len(seen) > MAX_MEMBERS or not (member.isfile() or member.isdir()):
                    raise ValueError("nonregular or excessive TAR member")
                total += member.size
                if total > MAX_EXPANDED_BYTES:
                    raise ValueError("TAR expanded bytes exceed bound")
                target = destination.joinpath(*name.split("/"))
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as original, target.open("wb") as frozen:
                        shutil.copyfileobj(original, frozen, 1024 * 1024)
                    if target.stat().st_size != member.size:
                        raise ValueError("TAR member byte count differs")
    return _file_inventory(destination)


def _transport_format(normalized, bindings, candidate_sha, manifest):
    stage = normalized / "build/stage-receipt.json"
    capture = normalized / "captures/compatibility/result.json"
    if not (stage.is_file() and capture.is_file()):
        return "unsupported producer format; raw bytes retained without a gate adapter"
    stage_receipt = _strict_json(stage)
    result = _strict_json(capture)
    if (stage_receipt.get("candidate_sha") != candidate_sha
            or result.get("source_sha") != candidate_sha
            or result.get("format") != "portable-mobile-capture-v1"):
        raise ValueError("mobile capture source identity differs")
    target = result.get("target")
    if (target not in stage_receipt.get("targets", [])
            or target not in {lane["target"] for lane in manifest["lanes"].values()}):
        raise ValueError("mobile capture target identity differs")
    for binding in bindings:
        expected = (binding.get("target") if binding["lane"] is None else
                    manifest["lanes"][binding["lane"]]["target"])
        if expected is not None and expected != target:
            raise ValueError("bound lane or target differs from mobile capture")
    return ("portable-mobile-capture-v1 source and target bound; "
            "no complete independent gate adapter or signed audit")


def snapshot_source_index(index_path, candidate_sha, tree, manifest, artifacts_dir,
                          output, repository_name="rubixhacker/dyn4k", run_id=None,
                          run_attempt=None, github_token=None):
    output, artifacts_dir = Path(output), Path(artifacts_dir)
    original_index = _read_anchored(index_path)
    index = _strict_json_bytes(original_index)
    _validate_index(index, candidate_sha, tree, manifest, repository_name,
                    run_id, run_attempt, allow_local=github_token is None)
    (output / "source-index.json").write_bytes(original_index)
    (output / "raw/sources").mkdir(parents=True)
    (output / "normalized").mkdir()
    rows = []
    for source in index["sources"]:
        source_id = source["id"]
        origin, pin = source["origin"], source["transport"]
        folder = output / "raw/sources" / source_id
        folder.mkdir()
        row = {"id": source_id, "origin": origin, "transport": pin,
               "status": "FAILED"}
        try:
            if origin["kind"] == "local":
                source_path = _safe_source_path(origin["path"])
            elif origin["kind"] == "same_run":
                source_path = _safe_source_path(artifacts_dir.resolve() / origin["name"])
            else:
                source_path = None
            if source_path is not None and (
                    source_path.resolve().is_relative_to(output.resolve())
                    or output.resolve().is_relative_to(source_path.resolve())):
                raise ValueError("source and collection output cannot contain each other")
            if pin["format"] == "directory":
                if source_path is None:
                    raise ValueError("GitHub Actions source must be a ZIP")
                identity = _path_identity(source_path)
                before = _file_inventory(source_path)
                frozen = folder / "original-directory"
                _copy_directory(source_path, frozen)
                after = _file_inventory(source_path)
                copied = _file_inventory(frozen)
                row["raw_inventory"] = copied
                if (identity != _path_identity(source_path)
                        or before != after or before != copied):
                    raise ValueError("source directory changed while copied")
                if copied != pin["files"] or _inventory_digest(copied) != pin["inventory_sha256"]:
                    raise ValueError("source directory byte inventory differs")
                normalized = frozen
            else:
                frozen = folder / "original"
                if source_path is None:
                    row["api"] = _github_artifact(origin, candidate_sha, github_token,
                                                   frozen, pin["size"])
                else:
                    if not source_path.is_file():
                        raise ValueError("source archive is missing")
                    if source_path.stat().st_size > MAX_SOURCE_BYTES:
                        raise ValueError("source archive exceeds byte bound")
                    before = (_path_identity(source_path), source_path.stat().st_size,
                              digest(source_path, MAX_SOURCE_BYTES))
                    _copy_regular(source_path, frozen)
                    after = (_path_identity(source_path), source_path.stat().st_size,
                             digest(source_path, MAX_SOURCE_BYTES))
                    if before != after:
                        raise ValueError("source archive changed while copied")
                row["raw_size"] = frozen.stat().st_size
                row["raw_sha256"] = digest(frozen, MAX_SOURCE_BYTES)
                if (row["raw_size"] != pin["size"]
                        or row["raw_sha256"] != pin["sha256"]):
                    raise ValueError("source archive bytes differ from exact pin")
                normalized = output / "normalized" / source_id
                row["normalized_inventory"] = _extract_transport(
                    frozen, pin["format"], normalized)
            bindings = [binding for binding in index["bindings"]
                        if binding["source_id"] == source_id]
            reasons = []
            for binding in bindings:
                root = normalized
                if binding.get("member_root"):
                    root = normalized.joinpath(*binding["member_root"].split("/"))
                if not root.is_dir():
                    raise ValueError("bound member root is missing")
                reasons.append(_transport_format(root, [binding], candidate_sha,
                                                 manifest))
            row["reason"] = "; ".join(sorted(set(reasons)))
            row["status"] = "NOT_RUN"
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, tarfile.TarError,
                zipfile.BadZipFile, urllib.error.URLError) as error:
            row["reason"] = str(error)
            incomplete = output / "normalized" / source_id
            if incomplete.is_dir() and "normalized_inventory" not in row:
                shutil.rmtree(incomplete)
            partial = folder / "original"
            if partial.is_file():
                row["raw_size"] = partial.stat().st_size
                row["raw_sha256"] = digest(partial, MAX_SOURCE_BYTES)
            partial_dir = folder / "original-directory"
            if partial_dir.is_dir():
                try:
                    row["raw_inventory"] = _file_inventory(partial_dir)
                except ValueError:
                    shutil.rmtree(partial_dir)
                    row["raw_inventory"] = None
        rows.append(row)
    ledger = {"schema": 1, "candidate_sha": candidate_sha, "source_tree": tree,
              "index_sha256": hashlib.sha256(original_index).hexdigest(),
              "sources": rows,
              "status": "FAILED" if any(row["status"] == "FAILED" for row in rows)
              else "NOT_RUN"}
    (output / "cross-run-ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")
    return ledger


def verify_source_snapshot(output, candidate_sha, tree):
    output = Path(output)
    if ((output / "source-index.json").is_symlink()
            or (output / "cross-run-ledger.json").is_symlink()):
        raise ValueError("frozen source index or ledger is symbolic")
    ledger = _strict_json(output / "cross-run-ledger.json")
    index_bytes = _read_anchored(output / "source-index.json")
    index = _strict_json_bytes(index_bytes)
    if (ledger.get("candidate_sha") != candidate_sha or ledger.get("source_tree") != tree
            or hashlib.sha256(index_bytes).hexdigest() != ledger.get("index_sha256")
            or [source["id"] for source in index["sources"]]
            != [row["id"] for row in ledger["sources"]]):
        raise ValueError("frozen cross-run source index or ledger differs")
    if (output / "raw/sources").is_symlink():
        raise ValueError("frozen source set is symbolic")
    if ({path.name for path in (output / "raw/sources").iterdir()}
            != {source["id"] for source in index["sources"]}):
        raise ValueError("frozen source set differs")
    for source, row in zip(index["sources"], ledger["sources"]):
        folder = output / "raw/sources" / source["id"]
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("frozen source folder is missing or symbolic")
        pin = source["transport"]
        if pin["format"] == "directory":
            path = folder / "original-directory"
            recorded = row.get("raw_inventory")
            expected = {"original-directory"} if isinstance(recorded, dict) else set()
            if {child.name for child in folder.iterdir()} != expected:
                raise ValueError("frozen source has missing or unrecorded files")
            if expected and _file_inventory(path) != recorded:
                raise ValueError("frozen source directory bytes differ")
            if row["status"] == "NOT_RUN" and (not expected or recorded != pin["files"]):
                raise ValueError("frozen source directory differs from pin")
        else:
            path = folder / "original"
            recorded = "raw_size" in row and "raw_sha256" in row
            if ("raw_size" in row) != ("raw_sha256" in row):
                raise ValueError("frozen source archive ledger is incomplete")
            expected = {"original"} if recorded else set()
            if {child.name for child in folder.iterdir()} != expected:
                raise ValueError("frozen source has missing or unrecorded files")
            if recorded and (path.is_symlink() or not path.is_file()
                             or path.stat().st_size != row["raw_size"]
                             or digest(path, MAX_SOURCE_BYTES) != row["raw_sha256"]):
                raise ValueError("frozen source archive bytes differ")
            if row["status"] == "NOT_RUN" and (not recorded
                    or row["raw_size"] != pin["size"] or row["raw_sha256"] != pin["sha256"]):
                raise ValueError("frozen source archive differs from pin")
            normalized = output / "normalized" / source["id"]
            if "normalized_inventory" in row and _file_inventory(normalized) != row[
                    "normalized_inventory"]:
                raise ValueError("normalized source archive bytes differ")
    return True


def checked_sidecar(root, stem):
    archive = root / stem
    sidecar = root / f"{stem.removesuffix('.tar.gz')}.sha256"
    if not archive.is_file() or not sidecar.is_file():
        raise ValueError("archive or SHA-256 sidecar is missing")
    recorded = sidecar.read_text().strip().split()
    if len(recorded) != 2 or not SHA64.fullmatch(recorded[0]) or Path(recorded[1]).name != stem:
        raise ValueError("archive SHA-256 sidecar is malformed")
    if digest(archive) != recorded[0]:
        raise ValueError("archive bytes differ from SHA-256 sidecar")
    return archive


def inspect_artifact(route, root, candidate_sha, tree, extracted, repository, upstream):
    if route in ("full-ci", "full-common"):
        stem = f"{route}-{candidate_sha}.tar.gz"
        archive = checked_sidecar(root, stem)
        members = root / f"{route}-{candidate_sha}.members"
        if not members.is_file():
            raise ValueError(f"{route} archive member list is missing")
        with tarfile.open(archive, "r:*") as packed:
            if ([name.rstrip("/") for name in members.read_text().splitlines()]
                    != [name.rstrip("/") for name in packed.getnames()]):
                raise ValueError(f"{route} archive member list differs")
        unpacked = checked_tar(archive, extracted / route)
        manifest = (unpacked / "full-ci/lane-manifest.json" if route == "full-ci"
                    else unpacked / "archive-index.json")
        declared = qualify.load_json_strict(manifest)
        if declared.get("candidate_sha") != candidate_sha:
            raise ValueError(f"{route} source candidate differs")
        if route == "full-ci":
            from sys import path as python_path
            python_path.insert(0, str(Path(__file__).resolve().parents[1] / "compatibility"))
            import full_ci
            full_ci.verify_archive(unpacked / "full-ci", candidate_sha)
        else:
            import full_corpus
            result = full_corpus.verify_archive(unpacked, repository, candidate_sha,
                                                upstream=upstream, require_checkout=True)
            if result["status"] != "PASSED":
                raise ValueError("full common raw archive does not verify")
        return "PRODUCER_VERIFIED"
    if route.startswith("full-hosted-"):
        from full_hosted import verify_transport_archive
        target = route.removeprefix("full-hosted-")
        archives = list(root.glob("*.tar"))
        if len(archives) != 1:
            raise ValueError("full hosted transport archive is missing or duplicated")
        receipt = verify_transport_archive(archives[0], candidate_sha, target,
                                           repository)
        if receipt.get("candidate_sha") != candidate_sha:
            raise ValueError("full hosted source candidate differs")
        return "PRODUCER_VERIFIED"
    if route == "duplicate-provider":
        receipt = qualify.load_json_strict(root / "receipt.json")
        if (receipt.get("candidate_sha") != candidate_sha
                or receipt.get("source_tree") != tree):
            raise ValueError("duplicate provider source identity differs")
        independent_gates._inventory(root, receipt)
        if receipt.get("status") == "PASSED":
            if receipt.get("process", {}).get("exit_code") == 0:
                raise ValueError("forged provider success lacks failing exit")
            return "PRODUCER_VERIFIED"
        return "FAILED"
    if route.startswith("publication-"):
        from publication import verify
        bundles = list(root.glob("*-publication"))
        if len(bundles) != 1:
            raise ValueError("publication bundle is missing or duplicated")
        verify(bundles[0], candidate_sha, digest(bundles[0] / "manifest.json"))
        return "PRODUCER_VERIFIED"
    if route.startswith("qualification-"):
        from artifact import verify_bundle
        manifest = qualify.load_json_strict(repository /
                                            "tools/qualification/foundation-probes.json")
        verify_bundle(root, manifest, candidate_sha)
        return "PRODUCER_VERIFIED"
    identity = root / "identity.txt"
    if identity.is_file() and f"sha={candidate_sha}" not in identity.read_text().splitlines():
        raise ValueError("failed-route diagnostic source SHA differs")
    return "RETAINED_UNVERIFIED"


def unsigned_inputs(manifest, artifacts, rows):
    inputs = {lane: {"archives": {}} for lane in manifest["lanes"]}
    for (_, root), row in zip(artifacts, rows):
        if row.get("route") == "duplicate-provider" and Path(root).is_dir():
            inputs["jvm:Java:current:default"]["archives"]["duplicate-provider"] = str(
                Path(root).resolve())
    return inputs


def collect(repository, candidate_sha, artifacts, output, upstream=None, source_index=None,
            repository_name="rubixhacker/dyn4k", run_id=None, run_attempt=None,
            github_token=None, artifacts_dir=None):
    repository, output = Path(repository), Path(output)
    tree = source_tree(repository, candidate_sha)
    manifest = independent_gates.load_approved_manifest(repository)
    if len(manifest["lanes"]) != 112:
        raise ValueError("approved lane inventory is incomplete")
    output.mkdir(parents=True, exist_ok=False)
    extracted = output / "extracted"
    extracted.mkdir()
    artifacts = list(artifacts)
    rows, seen = [], set()
    staged_audit = None
    for name, root in artifacts:
        root = Path(root)
        row = {"name": name, "route": None, "status": "FAILED"}
        try:
            row["files"] = files_in(root)
            route = artifact_route(name, candidate_sha)
            row["route"] = route
            if route in seen:
                raise ValueError(f"duplicate producer artifact route: {route}")
            seen.add(route)
            row["status"] = inspect_artifact(route, root, candidate_sha, tree, extracted,
                                             repository, upstream)
            if route == "publication-ubuntu" and row["status"] == "PRODUCER_VERIFIED":
                staged_audit = qualify.load_json_strict(next(root.glob("*-publication")) /
                                                       "artifact-audit.json")
        except (OSError, ValueError, TypeError, KeyError, tarfile.TarError,
                zipfile.BadZipFile, ET.ParseError, subprocess.SubprocessError) as error:
            row["reason"] = str(error)
        rows.append(row)
    missing = sorted(set(REQUIRED) - seen)
    cross_run = None
    if source_index is not None:
        try:
            cross_run = snapshot_source_index(source_index, candidate_sha, tree, manifest,
                                              artifacts_dir if artifacts_dir is not None else
                                              (Path(artifacts[0][1]).parent if artifacts else
                                               output.parent / "absent-artifacts"),
                                              output, repository_name, run_id,
                                              run_attempt, github_token)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            cross_run = {"schema": 1, "candidate_sha": candidate_sha,
                         "status": "FAILED", "reason": str(error)}
            try:
                rejected = _safe_source_path(source_index)
                if rejected.is_file():
                    (output / "source-index.rejected").write_bytes(
                        _read_anchored(rejected))
                    cross_run["rejected_index_sha256"] = digest(output /
                                                                "source-index.rejected")
            except (OSError, ValueError, TypeError):
                pass
    inputs = unsigned_inputs(manifest, artifacts, rows)
    (output / "assembly-inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    if staged_audit is not None:
        (output / "staged-audit.json").write_text(json.dumps(staged_audit, indent=2) + "\n")
        target_hashes = qualify.target_binary_hashes(staged_audit["artifacts"])
    else:
        target_hashes = {}
    def candidate_lane_input(lane_id, lane):
        selected = {"target": lane["target"],
                    "artifact_hashes": target_hashes.get(lane["target"]),
                    "runtime_identity": None}
        if lane["target"] == "jvm":
            selected["artifact_hashes"] = None
            selected["jvm_mode_publication"] = {
                "candidate_sha": candidate_sha, "lane": lane_id,
                "mode": lane["configuration"], "source": "compiler_modes.replay",
                "source_checkout": None, "publication_archive": None,
                "archive_digest": None, "artifact_hashes": None}
        return selected

    candidate_inputs = {"schema": 1, "candidate_sha": candidate_sha,
                        "suite_manifest_sha256": independent_gates.digest(manifest),
                        "audit_manifest_sha256": (qualify.manifest_digest(staged_audit)
                                                  if staged_audit is not None else None),
                        "status": "INCOMPLETE",
                        "lanes": {lane_id: candidate_lane_input(lane_id, lane)
                                  for lane_id, lane in manifest["lanes"].items()}}
    (output / "candidate-manifest-inputs.json").write_text(
        json.dumps(candidate_inputs, indent=2) + "\n")
    report = {"schema": 1, "candidate_sha": candidate_sha, "source_tree": tree,
              "required_lanes": 112, "artifacts": rows, "missing_artifacts": missing,
              "independent_signature": "MISSING",
              "status": "FAILED" if (any(row["status"] == "FAILED" for row in rows)
                                     or cross_run is not None and cross_run["status"] == "FAILED")
              else "NOT_RUN", "reason": "signed external audit and complete gate routes are absent"}
    if cross_run is not None:
        report["cross_run"] = cross_run
    report["external_inputs_required"] = [
        "all 112 exact-source common gate archives and runtime identities",
        "independently audited archive digests and 21-target artifact hashes",
        "complete candidate manifest bound to a verified staged audit",
        "exact staged repository bytes available to the public qualifier",
        "detached Ed25519 audit signature and pinned trusted public-key fingerprint"]
    (output / "collection.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def verify_collection(repository, candidate_sha, artifacts, output):
    report = qualify.load_json_strict(Path(output) / "collection.json")
    if (report.get("candidate_sha") != candidate_sha
            or report.get("source_tree") != source_tree(Path(repository), candidate_sha)
            or report.get("required_lanes") != 112):
        raise ValueError("collected source identity differs")
    supplied = list(artifacts)
    rows = report.get("artifacts")
    if (not isinstance(rows, list) or len(rows) != len(supplied)
            or [row.get("name") for row in rows] != [name for name, _ in supplied]):
        raise ValueError("collected producer artifact set differs")
    for row, (_, root) in zip(rows, supplied):
        if row.get("files") is not None and files_in(Path(root)) != row["files"]:
            raise ValueError(f"collected raw artifact bytes differ: {row['name']}")
    inputs = qualify.load_json_strict(Path(output) / "assembly-inputs.json")
    approved = independent_gates.load_approved_manifest(Path(repository))
    if inputs != unsigned_inputs(approved, supplied, rows):
        raise ValueError("unsigned 112-lane input map differs")
    cross_run = report.get("cross_run")
    if cross_run is not None:
        if "sources" in cross_run:
            verify_source_snapshot(output, candidate_sha, report["source_tree"])
            if _strict_json(Path(output) / "cross-run-ledger.json") != cross_run:
                raise ValueError("cross-run source ledger differs from collection")
        elif "rejected_index_sha256" in cross_run:
            if digest(Path(output) / "source-index.rejected") != cross_run[
                    "rejected_index_sha256"]:
                raise ValueError("rejected source index bytes differ")
    return True


def _snapshot_external_references(archive_map, approved, stable):
    if (not isinstance(archive_map, dict) or set(archive_map) !=
            {"schema", "candidate_sha", "lanes"}
            or type(archive_map["schema"]) is not int or archive_map["schema"] != 1
            or not isinstance(archive_map["lanes"], dict)
            or set(archive_map["lanes"]) != set(approved["lanes"])):
        raise ValueError("external signed archive map lacks exact 112-lane source binding")
    references = stable / "references"
    references.mkdir()
    rewritten = {"schema": 1, "candidate_sha": archive_map["candidate_sha"],
                 "lanes": {}}
    snapshots = {}
    for lane_id, archives in archive_map["lanes"].items():
        if not isinstance(archives, dict):
            raise ValueError("external lane archive map is invalid")
        allowed = set(approved["lanes"][lane_id]["required_gates"])
        allowed.update(approved["global_gates"])
        if set(archives) - allowed:
            raise ValueError("external archive map names an unapproved gate")
        rewritten["lanes"][lane_id] = {}
        for gate, selected in archives.items():
            source = _safe_source_path(selected)
            if not source.exists():
                raise ValueError("external referenced archive is missing")
            if (source.resolve().is_relative_to(stable.resolve())
                    or stable.resolve().is_relative_to(source.resolve())):
                raise ValueError("external archive and snapshot cannot contain each other")
            resolved = str(source.resolve())
            if resolved not in snapshots:
                frozen = references / str(len(snapshots))
                if source.is_dir():
                    identity_before = _path_identity(source)
                    before = _file_inventory(source)
                    _copy_directory(source, frozen)
                    after = _file_inventory(source)
                    copied = _file_inventory(frozen)
                    if (identity_before != _path_identity(source)
                            or before != after or before != copied):
                        raise ValueError("external archive directory changed while copied")
                    identity = {"kind": "directory", "files": copied,
                                "inventory_sha256": _inventory_digest(copied)}
                elif source.is_file():
                    if source.stat().st_size > MAX_SOURCE_BYTES:
                        raise ValueError("external archive exceeds byte bound")
                    before = (_path_identity(source), source.stat().st_size,
                              digest(source, MAX_SOURCE_BYTES))
                    _copy_regular(source, frozen)
                    after = (_path_identity(source), source.stat().st_size,
                             digest(source, MAX_SOURCE_BYTES))
                    if before != after or before[1:] != (frozen.stat().st_size,
                                                         digest(frozen, MAX_SOURCE_BYTES)):
                        raise ValueError("external archive changed while copied")
                    identity = {"kind": "file", "size": before[1],
                                "sha256": before[2]}
                else:
                    raise ValueError("external archive is nonregular")
                snapshots[resolved] = {"frozen": str(frozen), "identity": identity}
            rewritten["lanes"][lane_id][gate] = snapshots[resolved]["frozen"]
    snapshot_map = stable / "archive-map.snapshot.json"
    snapshot_map.write_text(json.dumps(rewritten, indent=2) + "\n")
    return snapshot_map, snapshots


def _verify_external_references(snapshots):
    for item in snapshots.values():
        path, identity = Path(item["frozen"]), item["identity"]
        if identity["kind"] == "file":
            if (not path.is_file() or path.is_symlink()
                    or path.stat().st_size != identity["size"]
                    or digest(path) != identity["sha256"]):
                raise ValueError("frozen external archive file bytes differ")
        elif (_file_inventory(path) != identity["files"]
              or _inventory_digest(identity["files"]) != identity["inventory_sha256"]):
            raise ValueError("frozen external archive directory bytes differ")


def ingest_external(repository, candidate_sha, artifacts, output, audit_inputs,
                    trusted_key_sha256=None, independent_performance_key=None,
                    performance_key_sha256=None):
    verify_collection(repository, candidate_sha, artifacts, output)
    audit_inputs, output = Path(audit_inputs), Path(output)
    names = ("archive-map.json", "audit.json", "audit.sig", "public.pem",
             "candidate-manifest.json", "staged-audit.json", "evidence.json")
    missing = [name for name in names if not (audit_inputs / name).is_file()]
    if not SHA64.fullmatch(str(trusted_key_sha256 or "")):
        missing.append("externally pinned trusted Ed25519 key SHA-256")
    if not (Path(repository) / "build/staging-repository").is_dir():
        missing.append("verified staged repository bytes at build/staging-repository")
    if independent_performance_key is not None:
        if not SHA64.fullmatch(str(performance_key_sha256 or "")):
            missing.append("externally pinned performance key SHA-256")
        elif not _safe_source_path(independent_performance_key).is_file():
            missing.append("independently supplied performance key")
    result = {"candidate_sha": candidate_sha, "status": "NOT_RUN",
              "missing_external_inputs": missing}
    if missing:
        (output / "audit-ingestion.json").write_text(json.dumps(result, indent=2) + "\n")
        return result
    stable = output / "external-inputs"
    stable.mkdir(exist_ok=False)
    original_hashes = {name: digest(audit_inputs / name) for name in names}
    for name in names:
        shutil.copyfile(audit_inputs / name, stable / name)
        if digest(stable / name) != original_hashes[name]:
            raise ValueError(f"external audit input changed while copied: {name}")
    supplied = _strict_json(stable / "archive-map.json")
    approved = independent_gates.load_approved_manifest(Path(repository))
    if (supplied.get("schema") != 1 or supplied.get("candidate_sha") != candidate_sha):
        raise ValueError("external signed archive map lacks exact 112-lane source binding")
    snapshot_map, snapshots = _snapshot_external_references(supplied, approved, stable)
    snapshot_map_sha256 = digest(snapshot_map)
    performance_copy = None
    if independent_performance_key is not None:
        key = _safe_source_path(independent_performance_key)
        if (key.resolve().is_relative_to(audit_inputs.resolve())
                or key.resolve().is_relative_to(output.resolve())
                or any(key.resolve().is_relative_to(Path(root).resolve())
                       for _, root in artifacts)):
            raise ValueError("performance key must come from outside producer inputs")
        performance_copy = stable / "independent-performance-key.pem"
        _copy_regular(key, performance_copy)
        if (digest(key) != performance_key_sha256
                or digest(performance_copy) != performance_key_sha256):
            raise ValueError("independent performance key bytes differ from external pin")
    for name in ("candidate-manifest.json", "staged-audit.json"):
        if qualify.load_json_strict(stable / name).get("candidate_sha") != candidate_sha:
            raise ValueError(f"external {name} belongs to another candidate")
    if (output / "signed-runtime-matrix.json").exists():
        raise ValueError("signed adapter result already exists")
    command = [sys.executable, str(Path(__file__).with_name("qualify.py")), "record",
               "--candidate-sha", candidate_sha,
               "--evidence", str(stable / "evidence.json"),
               "--audit", str(stable / "staged-audit.json"),
               "--candidate-manifest", str(stable / "candidate-manifest.json"),
               "--independent-archives", str(snapshot_map),
               "--independent-audit", str(stable / "audit.json"),
               "--independent-audit-signature", str(stable / "audit.sig"),
               "--trusted-audit-public-key", str(stable / "public.pem"),
               "--trusted-audit-key-sha256", trusted_key_sha256,
               "--output", str(output / "signed-runtime-matrix.json")]
    if performance_copy is not None:
        command.extend(("--independent-performance-key", str(performance_copy)))
    process = subprocess.run(command, cwd=repository, capture_output=True, check=False)
    if any(digest(audit_inputs / name) != original_hashes[name]
           or digest(stable / name) != original_hashes[name] for name in names):
        raise ValueError("external audit input changed during verification")
    if digest(snapshot_map) != snapshot_map_sha256:
        raise ValueError("frozen external archive map changed during verification")
    verify_collection(repository, candidate_sha, artifacts, output)
    _verify_external_references(snapshots)
    if performance_copy is not None and digest(performance_copy) != performance_key_sha256:
        raise ValueError("frozen independent performance key bytes differ")
    (output / "signed-adapter.stdout").write_bytes(process.stdout)
    (output / "signed-adapter.stderr").write_bytes(process.stderr)
    result.update(status="FAILED" if process.returncode and not
                  (output / "signed-runtime-matrix.json").is_file() else "NOT_RUN",
                  adapter_exit=process.returncode, missing_external_inputs=[],
                  trusted_key_sha256=trusted_key_sha256,
                  input_sha256=original_hashes,
                  referenced_snapshots=snapshots,
                  performance_key_sha256=performance_key_sha256)
    if (output / "signed-runtime-matrix.json").is_file():
        matrix = qualify.load_json_strict(output / "signed-runtime-matrix.json")
        if matrix.get("candidate_sha") != candidate_sha or matrix.get("total") != 112:
            raise ValueError("signed adapter returned an incomplete candidate matrix")
        result["counts"] = matrix["counts"]
        if process.returncode == 0 and matrix["counts"].get("PASSED") == 112:
            result["status"] = "PASSED"
        elif matrix["counts"].get("FAILED", 0):
            result["status"] = "FAILED"
    (output / "audit-ingestion.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--source-index", type=Path)
    parser.add_argument("--repository-name", default="rubixhacker/dyn4k")
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--run-attempt", type=int)
    parser.add_argument("--audit-input-dir", type=Path)
    parser.add_argument("--trusted-key-sha256")
    parser.add_argument("--independent-performance-key", type=Path)
    parser.add_argument("--performance-key-sha256")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    artifacts = sorted((path.name, path) for path in args.artifacts_dir.iterdir())
    if args.verify:
        verify_collection(args.repository, args.candidate_sha, artifacts, args.output)
        print(json.dumps({"candidate_sha": args.candidate_sha, "transport": "VERIFIED"}))
        return 0
    if args.audit_input_dir is not None:
        try:
            result = ingest_external(args.repository, args.candidate_sha, artifacts,
                                     args.output, args.audit_input_dir, args.trusted_key_sha256,
                                     args.independent_performance_key,
                                     args.performance_key_sha256)
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
            result = {"candidate_sha": args.candidate_sha, "status": "FAILED",
                      "reason": str(error)}
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "audit-ingestion.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0 if result["status"] == "PASSED" else 1
    report = collect(args.repository, args.candidate_sha, artifacts, args.output,
                     args.upstream, args.source_index, args.repository_name,
                     args.run_id, args.run_attempt,
                     os.environ.get("DYN4K_GITHUB_TOKEN"), args.artifacts_dir)
    print(json.dumps({key: report[key] for key in ("candidate_sha", "status", "missing_artifacts")}))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
