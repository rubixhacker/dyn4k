import ctypes
import msvcrt
import os
import stat
from contextlib import ExitStack
from ctypes import wintypes
from pathlib import Path


FILE_READ_ATTRIBUTES = 0x80
DELETE = 0x00010000
GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 3
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class FileInformation(ctypes.Structure):
    _fields_ = [
        ("attributes", wintypes.DWORD),
        ("creation", wintypes.FILETIME),
        ("access", wintypes.FILETIME),
        ("write", wintypes.FILETIME),
        ("volume", wintypes.DWORD),
        ("size_high", wintypes.DWORD),
        ("size_low", wintypes.DWORD),
        ("links", wintypes.DWORD),
        ("index_high", wintypes.DWORD),
        ("index_low", wintypes.DWORD),
    ]


_kernel = ctypes.WinDLL("kernel32", use_last_error=True)
_create = _kernel.CreateFileW
_create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
_create.restype = wintypes.HANDLE
_information = _kernel.GetFileInformationByHandle
_information.argtypes = (wintypes.HANDLE, ctypes.POINTER(FileInformation))
_information.restype = wintypes.BOOL
_close = _kernel.CloseHandle
_close.argtypes = (wintypes.HANDLE,)
_close.restype = wintypes.BOOL


def _open(path, directory, removable=False):
    flags = FILE_FLAG_OPEN_REPARSE_POINT
    if directory:
        flags |= FILE_FLAG_BACKUP_SEMANTICS
    desired = (FILE_READ_ATTRIBUTES | DELETE if removable else
               FILE_READ_ATTRIBUTES if directory else GENERIC_READ)
    handle = _create(str(path), desired,
                     FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, flags, None)
    if handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    info = FileInformation()
    if not _information(handle, ctypes.byref(info)):
        error = ctypes.WinError(ctypes.get_last_error())
        _close(handle)
        raise error
    if (info.attributes & FILE_ATTRIBUTE_REPARSE_POINT or
            bool(info.attributes & FILE_ATTRIBUTE_DIRECTORY) != directory):
        _close(handle)
        raise ValueError(f"unsafe Safari path or file type: {path}")
    return handle


class LockedDirectory:
    def __init__(self, repository, relative=Path(), resolve_root=True, removable=False):
        repository = Path(repository).resolve() if resolve_root else Path(repository).absolute()
        relative = Path(relative)
        if (not repository.is_absolute() or ".." in repository.parts or
                relative.is_absolute() or
                any(part in ("", ".", "..") for part in relative.parts)):
            raise ValueError(f"unsafe Safari path: {relative}")
        self.path = repository / relative
        self._stack = ExitStack()
        self._removable = removable
        self._leaf_handle = None
        try:
            current = Path(repository.anchor)
            paths = [current]
            for part in (*repository.parts[1:], *relative.parts):
                current = current / part
                paths.append(current)
            for index, path in enumerate(paths):
                handle = _open(path, True, removable and index == len(paths) - 1)
                self._stack.callback(_close, handle)
                self._leaf_handle = handle
        except BaseException:
            self._stack.close()
            raise

    def close(self):
        self._stack.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def child(self, name, removable=False):
        if not name or name in (".", "..") or "\\" in name or "/" in name:
            raise ValueError("unsafe Safari child name")
        return LockedDirectory(self.path, Path(name), removable=removable)

    def remove_empty(self):
        if not self._removable or self._leaf_handle is None:
            raise ValueError("Safari directory handle does not own deletion")
        disposition = ctypes.c_ubyte(1)
        setter = _kernel.SetFileInformationByHandle
        setter.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        setter.restype = wintypes.BOOL
        if not setter(self._leaf_handle, 4, ctypes.byref(disposition),
                      ctypes.sizeof(disposition)):
            raise ctypes.WinError(ctypes.get_last_error())

    def open_file(self, name):
        if not name or name in (".", "..") or "\\" in name or "/" in name:
            raise ValueError("unsafe Safari file name")
        handle = _open(self.path / name, False)
        try:
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        except BaseException:
            _close(handle)
            raise
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ValueError(f"non-regular Safari file: {name}")
        return descriptor
