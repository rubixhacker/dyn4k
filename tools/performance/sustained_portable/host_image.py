import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import struct
import subprocess


def file_sha256(stream):
    stream.seek(0)
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(65536), b""):
        value.update(block)
    stream.seek(0)
    return value.hexdigest()


class _RegionInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in
                ("protection", "max_protection", "inheritance", "flags")]
    _fields_ += [("offset", ctypes.c_uint64)]
    _fields_ += [(name, ctypes.c_uint32) for name in
                 ("behavior", "user_wired_count", "user_tag", "pages_resident",
                  "pages_shared_now_private", "pages_swapped_out", "pages_dirtied",
                  "ref_count", "shadow_depth", "share_mode", "private_pages_resident",
                  "shared_pages_resident", "obj_id", "depth")]
    _fields_ += [("address", ctypes.c_uint64), ("size", ctypes.c_uint64)]


class _VInfoStat(ctypes.Structure):
    _fields_ = [("dev", ctypes.c_uint32), ("mode", ctypes.c_uint16),
                ("nlink", ctypes.c_uint16), ("ino", ctypes.c_uint64),
                ("uid", ctypes.c_uint32), ("gid", ctypes.c_uint32),
                ("atime", ctypes.c_int64), ("atimensec", ctypes.c_int64),
                ("mtime", ctypes.c_int64), ("mtimensec", ctypes.c_int64),
                ("ctime", ctypes.c_int64), ("ctimensec", ctypes.c_int64),
                ("birthtime", ctypes.c_int64), ("birthtimensec", ctypes.c_int64),
                ("size", ctypes.c_int64), ("blocks", ctypes.c_int64),
                ("blksize", ctypes.c_int32), ("flags", ctypes.c_uint32),
                ("gen", ctypes.c_uint32), ("rdev", ctypes.c_uint32),
                ("qspare", ctypes.c_int64 * 2)]


class _VnodeInfo(ctypes.Structure):
    _fields_ = [("stat", _VInfoStat), ("type", ctypes.c_int32),
                ("pad", ctypes.c_int32), ("fsid", ctypes.c_int32 * 2)]


class _RegionWithPath(ctypes.Structure):
    _fields_ = [("region", _RegionInfo), ("vnode", _VnodeInfo),
                ("path", ctypes.c_char * 1024)]


def select_macos_region(regions, selected_stat):
    matches = [region for region in regions
               if region["protection"] & 4 and
               region["dev"] == (selected_stat.st_dev & 0xffffffff) and
               region["ino"] == selected_stat.st_ino and region["size"] > 0]
    if len(matches) != 1:
        raise ValueError("one executable main-image vnode mapping was not observed")
    return matches[0]


def select_macos_text_vnode(raw, pid, selected_stat):
    records = []
    current = None
    observed_pid = None
    for field in (part.lstrip(b"\n") for part in raw.split(b"\0") if part.strip(b"\n")):
        key, value = field[:1], field[1:]
        if key == b"p":
            if observed_pid is not None or value != str(pid).encode():
                raise ValueError("macOS text mapping PID differs from selected child")
            observed_pid = pid
        elif key == b"f":
            if current is not None:
                records.append(current)
            current = {b"f": value}
        elif current is None or key in current:
            raise ValueError("macOS text mapping record is malformed")
        else:
            current[key] = value
    if current is not None:
        records.append(current)
    if observed_pid != pid:
        raise ValueError("macOS text mapping PID was not observed")
    matches = []
    for record in records:
        if record.get(b"f") != b"txt":
            continue
        try:
            device = int(record[b"D"], 0)
            inode = int(record[b"i"])
            size = int(record[b"s"])
        except (KeyError, ValueError):
            continue
        if (device, inode, size) == (selected_stat.st_dev, selected_stat.st_ino,
                                      selected_stat.st_size):
            matches.append({"dev": device, "ino": inode, "size": size,
                            "path": os.fsdecode(record.get(b"n", b""))})
    if len(matches) != 1:
        raise ValueError("one selected executable text vnode was not observed")
    return matches[0]


def observe_macos(pid, selected):
    if ctypes.sizeof(_RegionWithPath) != 1272:
        raise ValueError("macOS region ABI size differs from selected XNU layout")
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    library.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    library.proc_pidpath.restype = ctypes.c_int
    library.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                     ctypes.c_void_p, ctypes.c_int]
    library.proc_pidinfo.restype = ctypes.c_int
    path_buffer = ctypes.create_string_buffer(4096)
    reported_path = None
    path_error = None
    try:
        if library.proc_pidpath(pid, path_buffer, len(path_buffer)) > 0 and path_buffer.value:
            reported_path = os.fsdecode(path_buffer.value)
        else:
            path_error = f"proc_pidpath returned no path (errno={ctypes.get_errno()})"
    except OSError as error:
        path_error = f"proc_pidpath failed: {error}"
    with Path(selected).open("rb") as stream:
        selected_stat = os.fstat(stream.fileno())
        selected_sha = file_sha256(stream)
        regions = []
        address = 0
        for _ in range(512):
            record = _RegionWithPath()
            count = library.proc_pidinfo(pid, 8, address, ctypes.byref(record), ctypes.sizeof(record))
            if count != ctypes.sizeof(record):
                break
            info = record.region
            following = info.address + info.size
            if info.size == 0 or following <= address:
                raise ValueError("invalid macOS process region sequence")
            region = {"address": info.address, "size": info.size,
                            "protection": info.protection, "offset": info.offset,
                            "dev": record.vnode.stat.dev, "ino": record.vnode.stat.ino,
                            "path": os.fsdecode(record.path).rstrip("\x00")}
            regions.append(region)
            if region["protection"] & 4 and \
                    region["dev"] == (selected_stat.st_dev & 0xffffffff) and \
                    region["ino"] == selected_stat.st_ino:
                break
            address = following
        else:
            raise ValueError("macOS process region scan exceeded bound")
        try:
            match = select_macos_region(regions, selected_stat)
            method = "proc_pidinfo_region_vnode"
            mapped_size = match["size"]
            raw_text = None
        except ValueError as region_error:
            try:
                result = subprocess.run(
                    ["/usr/sbin/lsof", "-a", "-p", str(pid), "-d", "txt", "-F0pfiDns"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3, check=True)
                if len(result.stdout) > 1024 * 1024:
                    raise ValueError("macOS text mapping output exceeded bound")
                match = select_macos_text_vnode(result.stdout, pid, selected_stat)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                raise ValueError(f"macOS selected vnode mapping unavailable: "
                                 f"region={region_error}; text={error}") from error
            method = "lsof_txt_vnode"
            mapped_size = match["size"]
            raw_text = result.stdout.hex()
        if os.fstat(stream.fileno()).st_size != selected_stat.st_size or \
                file_sha256(stream) != selected_sha:
            raise ValueError("selected executable changed during image observation")
    return {"method": method, "identity_kind": "mapped_executable_vnode",
            "path": reported_path, "path_error": path_error, "mapped_path": match["path"],
            "mapped_address": match.get("address"), "mapped_size": mapped_size,
            "mapped_dev": match["dev"], "mapped_ino": match["ino"],
            "selected_dev": selected_stat.st_dev & 0xffffffff,
            "selected_ino": selected_stat.st_ino, "selected_size": selected_stat.st_size,
            "lsof_stdout_hex": raw_text,
            "sha256": selected_sha, "hash_scope": "selected_file_on_matching_mapped_vnode"}


def pe_executable_sections(image):
    if len(image) < 0x100 or image[:2] != b"MZ":
        raise ValueError("selected Windows executable lacks PE header")
    pe = struct.unpack_from("<I", image, 0x3c)[0]
    if pe + 24 > len(image) or image[pe:pe + 4] != b"PE\0\0":
        raise ValueError("selected Windows executable has invalid PE signature")
    machine, count = struct.unpack_from("<HH", image, pe + 4)
    optional_size = struct.unpack_from("<H", image, pe + 20)[0]
    optional = pe + 24
    if machine != 0x8664 or count < 1 or count > 96 or optional + optional_size > len(image) or \
            optional_size < 160 or struct.unpack_from("<H", image, optional)[0] != 0x20b:
        raise ValueError("selected Windows executable is not valid PE32+ x64")
    if struct.unpack_from("<I", image, optional + 108)[0] < 6:
        raise ValueError("selected Windows executable lacks relocation directory")
    image_size = struct.unpack_from("<I", image, optional + 56)[0]
    header_size = struct.unpack_from("<I", image, optional + 60)[0]
    preferred_base = struct.unpack_from("<Q", image, optional + 24)[0]
    table = optional + optional_size
    if table + count * 40 > len(image) or header_size > len(image) or header_size < table + count * 40:
        raise ValueError("selected Windows executable has invalid section table")
    sections = []
    for index in range(count):
        entry = table + index * 40
        name = image[entry:entry + 8].split(b"\0", 1)[0].decode("ascii", "replace")
        virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", image, entry + 8)
        flags = struct.unpack_from("<I", image, entry + 36)[0]
        if raw_offset + raw_size > len(image) or rva + virtual_size > image_size:
            raise ValueError("selected Windows executable section exceeds image")
        sections.append({"name": name, "rva": rva, "raw_offset": raw_offset,
                         "size": min(virtual_size, raw_size), "flags": flags})
    executable = [item for item in sections if item["flags"] & 0x20000000 and
                  item["flags"] & 0x40000000 and not item["flags"] & 0x80000000 and
                  item["size"] > 0]
    if not executable:
        raise ValueError("selected Windows executable has no immutable code section")
    reloc_rva, reloc_size = struct.unpack_from("<II", image, optional + 112 + 5 * 8)
    relocations = set()
    if reloc_size:
        section = next((item for item in sections if item["rva"] <= reloc_rva and
                        reloc_rva + reloc_size <= item["rva"] + item["size"]), None)
        if section is None:
            raise ValueError("selected Windows executable relocation table is invalid")
        offset = section["raw_offset"] + reloc_rva - section["rva"]
        end = offset + reloc_size
        while offset < end:
            if offset + 8 > end:
                raise ValueError("truncated PE relocation block")
            page, block_size = struct.unpack_from("<II", image, offset)
            if block_size < 8 or block_size % 2 or offset + block_size > end:
                raise ValueError("invalid PE relocation block")
            for entry in range(offset + 8, offset + block_size, 2):
                value = struct.unpack_from("<H", image, entry)[0]
                kind = value >> 12
                if kind == 0:
                    continue
                width = {3: 4, 10: 8}.get(kind)
                if width is None:
                    raise ValueError("unsupported PE32+ relocation type")
                relocations.update(range(page + (value & 0xfff),
                                         page + (value & 0xfff) + width))
            offset += block_size
    return {"image_size": image_size, "header_size": header_size,
            "preferred_base": preferred_base, "image_base_offset": optional + 24,
            "sections": executable,
            "relocations": relocations}


class PECodeMismatch(ValueError):
    def __init__(self, detail):
        self.detail = detail
        super().__init__("live mapped PE code differs from selected executable "
                         f"in {detail['section']} at RVA 0x{detail['rva']:x}: "
                         f"selected=0x{detail['selected_byte']:02x}, "
                         f"mapped=0x{detail['mapped_byte']:02x}")


def compare_pe_code(image, layout, read_memory, base):
    mapped_header = read_memory(base, layout["header_size"])
    selected_header = bytearray(image[:layout["header_size"]])
    struct.pack_into("<Q", selected_header, layout["image_base_offset"], base)
    if len(mapped_header) != len(selected_header):
        raise ValueError("live mapped PE header differs from selected executable in length")
    if mapped_header != selected_header:
        offset = next(index for index, pair in enumerate(zip(selected_header, mapped_header))
                      if pair[0] != pair[1])
        raise ValueError("live mapped PE header differs from selected executable "
                         f"at offset 0x{offset:x}: selected=0x{selected_header[offset]:02x}, "
                         f"mapped=0x{mapped_header[offset]:02x}")
    matched = 0
    digest = hashlib.sha256()
    for section in layout["sections"]:
        selected_code = image[section["raw_offset"]:section["raw_offset"] + section["size"]]
        mapped_code = read_memory(base + section["rva"], section["size"])
        expected = bytearray(selected_code)
        observed = bytearray(mapped_code)
        if len(observed) != len(expected):
            raise ValueError("live mapped PE code read was incomplete")
        for rva in layout["relocations"]:
            index = rva - section["rva"]
            if 0 <= index < len(expected):
                expected[index] = observed[index] = 0
        if observed != expected:
            index = next(index for index, pair in enumerate(zip(expected, observed))
                         if pair[0] != pair[1])
            window = slice(max(0, index - 8), min(len(expected), index + 9))
            raise PECodeMismatch({
                "section": section["name"], "section_rva": section["rva"],
                "section_size": len(expected), "mapped_base": base,
                "preferred_base": layout["preferred_base"],
                "selected_image_sha256": hashlib.sha256(image).hexdigest(),
                "parsed_relocation_byte_count": len(layout["relocations"]),
                "rva": section["rva"] + index,
                "file_offset": section["raw_offset"] + index,
                "selected_byte": expected[index], "mapped_byte": observed[index],
                "selected_window_hex": selected_code[window].hex(),
                "mapped_window_hex": mapped_code[window].hex(),
                "window_relocation_rvas": [section["rva"] + position
                                           for position in range(window.start, window.stop)
                                           if section["rva"] + position in layout["relocations"]],
                "selected_section_sha256": hashlib.sha256(expected).hexdigest(),
                "mapped_section_sha256": hashlib.sha256(observed).hexdigest()})
        matched += len(expected) - sum(section["rva"] <= rva < section["rva"] + len(expected)
                                       for rva in layout["relocations"])
        digest.update(expected)
    if matched < 4096:
        raise ValueError("live mapped PE code coverage is too small")
    return {"mapped_code_sha256": digest.hexdigest(), "matched_code_bytes": matched,
            "sections": [item["name"] for item in layout["sections"]]}


class _ModuleInfo(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("size", wintypes.DWORD),
                ("entry", ctypes.c_void_p)]


def observe_windows(pid, selected):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    kernel.ReadProcessMemory.restype = wintypes.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                  wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p),
                                           wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    psapi.EnumProcessModulesEx.restype = wintypes.BOOL
    psapi.GetModuleInformation.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                           ctypes.POINTER(_ModuleInfo), wintypes.DWORD]
    psapi.GetModuleInformation.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        with Path(selected).open("rb") as stream:
            image = stream.read()
            selected_sha = hashlib.sha256(image).hexdigest()
            layout = pe_executable_sections(image)
        modules = (ctypes.c_void_p * 1024)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcessModulesEx(handle, modules, ctypes.sizeof(modules),
                                          ctypes.byref(needed), 0x02) or needed.value < ctypes.sizeof(ctypes.c_void_p) or \
                needed.value > ctypes.sizeof(modules):
            raise OSError(ctypes.get_last_error(), "main process module unavailable")
        info = _ModuleInfo()
        if not psapi.GetModuleInformation(handle, modules[0], ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.size != layout["image_size"] or not info.base:
            raise ValueError("live mapped PE image size differs from selected executable")
        def read_memory(address, size):
            buffer = ctypes.create_string_buffer(size)
            count = ctypes.c_size_t()
            if not kernel.ReadProcessMemory(handle, ctypes.c_void_p(address), buffer, size,
                                            ctypes.byref(count)) or count.value != size:
                raise OSError(ctypes.get_last_error(), "live PE image read failed")
            return buffer.raw
        comparison = compare_pe_code(image, layout, read_memory, info.base)
        path_buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path_buffer))
        reported_path = None
        path_error = None
        try:
            if kernel.QueryFullProcessImageNameW(handle, 0, path_buffer, ctypes.byref(length)) and \
                    length.value and path_buffer.value:
                reported_path = path_buffer.value
            else:
                path_error = f"QueryFullProcessImageNameW returned no path (winerror={ctypes.get_last_error()})"
        except OSError as error:
            path_error = f"QueryFullProcessImageNameW failed: {error}"
        return {"method": "ReadProcessMemory_main_PE_code", "identity_kind": "mapped_executable_code",
                "path": reported_path, "path_error": path_error,
                "mapped_base": info.base, "mapped_size": info.size,
                "sha256": selected_sha, "hash_scope": "selected_file_with_matching_live_PE_header_and_code",
                **comparison}
    finally:
        kernel.CloseHandle(handle)
