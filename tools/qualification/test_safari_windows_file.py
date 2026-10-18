import ctypes
import importlib.util
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


class Function:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


class SafariWindowsFileTests(unittest.TestCase):
    def test_locked_chain_and_file_refuse_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = root / "source"
            package = repository / "package"
            package.mkdir(parents=True)
            (package / "config.js").write_bytes(b"approved\n")
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "config.js"
            sentinel.write_bytes(b"outside\n")
            (repository / "linked").symlink_to(outside, target_is_directory=True)
            (package / "linked.js").symlink_to(sentinel)
            if os.name == "nt":
                import safari_windows_file
                self.check_locked_paths(safari_windows_file, repository, sentinel)
                return
            loaded = {}

            def create(path, desired, share, security, disposition, flags, template):
                directory = bool(flags & 0x02000000)
                return os.open(path, (os.O_PATH if directory else os.O_RDONLY) |
                               os.O_NOFOLLOW)

            def information(handle, pointer):
                observed = os.fstat(handle)
                item = ctypes.cast(pointer,
                                   ctypes.POINTER(loaded["module"].FileInformation)).contents
                item.attributes = ((0x10 if stat.S_ISDIR(observed.st_mode) else 0) |
                                   (0x400 if stat.S_ISLNK(observed.st_mode) else 0))
                return 1

            functions = types.SimpleNamespace(CreateFileW=Function(create),
                                              GetFileInformationByHandle=Function(information),
                                              CloseHandle=Function(lambda handle: os.close(handle) or 1))
            module_path = Path(__file__).with_name("safari_windows_file.py")
            spec = importlib.util.spec_from_file_location("safari_windows_file_control",
                                                          module_path)
            module = importlib.util.module_from_spec(spec)
            loaded["module"] = module
            with mock.patch.dict(sys.modules, {"msvcrt": types.SimpleNamespace(
                    open_osfhandle=lambda handle, flags: handle)}), \
                    mock.patch.object(ctypes, "WinDLL", return_value=functions,
                                      create=True):
                spec.loader.exec_module(module)
                self.check_locked_paths(module, repository, sentinel)

    def check_locked_paths(self, module, repository, sentinel):
        with module.LockedDirectory(repository, Path("package")) as directory:
            descriptor = directory.open_file("config.js")
            try:
                self.assertEqual(b"approved\n", os.read(descriptor, 100))
            finally:
                os.close(descriptor)
            with self.assertRaises((OSError, ValueError)):
                directory.open_file("linked.js")
        with self.assertRaises((OSError, ValueError)):
            module.LockedDirectory(repository, Path("linked"))
        self.assertEqual(b"outside\n", sentinel.read_bytes())


if __name__ == "__main__":
    unittest.main()
