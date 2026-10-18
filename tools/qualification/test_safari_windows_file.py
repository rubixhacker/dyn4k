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

import safari_reporter
import safari_yarn_lock


class Function:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


class SafariWindowsFileTests(unittest.TestCase):
    def test_source_bytes_accepts_root_alias_and_rejects_aliased_child_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "source"
            source = repository / "build/js/yarn.lock"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"approved\n")
            alias = root / "var-style-alias"
            alias.symlink_to(repository, target_is_directory=True)
            relative = Path("build/js/yarn.lock")
            self.assertEqual(b"approved\n", safari_yarn_lock.source_bytes(alias, relative))
            archived = safari_yarn_lock.copy_file(alias, relative, root / "capture", "generated")
            self.assertEqual(b"approved\n", (root / "capture" / archived["path"]).read_bytes())

            outside = root / "outside"
            outside.mkdir()
            (outside / "yarn.lock").write_bytes(b"hidden provider\n")
            (repository / "build/js").rename(repository / "build/js.saved")
            (repository / "build/js").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink source path or ancestor"):
                safari_yarn_lock.source_bytes(alias, relative)
            self.assertEqual(b"hidden provider\n", (outside / "yarn.lock").read_bytes())

    def test_source_bytes_rejects_root_alias_swap_before_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "source"
            repository.mkdir()
            (repository / "lock").write_bytes(b"approved\n")
            outside = root / "outside"
            outside.mkdir()
            (outside / "lock").write_bytes(b"hidden provider\n")
            alias = root / "var-style-alias"
            alias.symlink_to(repository, target_is_directory=True)
            real_source_path = safari_yarn_lock.source_path

            def swap_after_validation(source_root, relative):
                path = real_source_path(source_root, relative)
                alias.unlink()
                alias.symlink_to(outside, target_is_directory=True)
                return path

            with mock.patch.object(safari_yarn_lock, "source_path",
                                   side_effect=swap_after_validation):
                with self.assertRaisesRegex(ValueError, "source path identity changed"):
                    safari_yarn_lock.source_bytes(alias, Path("lock"))

    def test_generated_input_rejects_stable_short_read_and_accepts_repeated_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "source"
            path = repository / "build/js/yarn.lock"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"abcdef")

            class Directory:
                def __init__(self, root, relative):
                    self.path = root / relative

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    pass

                def open_file(self, name):
                    return os.open(self.path / name, os.O_RDONLY)

            proxy = mock.Mock(wraps=os)
            proxy.name = "nt"
            fake_module = types.SimpleNamespace(LockedDirectory=Directory)
            output = Path(temporary) / "capture"
            with mock.patch.dict(sys.modules, {"safari_windows_file": fake_module}), \
                    mock.patch.object(safari_yarn_lock, "os", proxy):
                with mock.patch.object(proxy, "read", side_effect=[b"abc", b"", b"abc", b"def", b""]):
                    with self.assertRaisesRegex(ValueError, "incomplete diagnostic source"):
                        safari_yarn_lock.copy_file(repository, Path("build/js/yarn.lock"),
                                                   output, "generated")
                    self.assertFalse((output / "generated/build/js/yarn.lock").exists())
                    archived = safari_yarn_lock.copy_file(
                        repository, Path("build/js/yarn.lock"), output, "generated")
                    self.assertEqual(b"abcdef", (output / archived["path"]).read_bytes())

    def test_staging_handle_failure_records_leftover_instead_of_clean(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "source"
            (repository / "dyn4k-core").mkdir(parents=True)
            result = {"status": "CLEAN", "projects": {}, "forensic": []}

            class Directory:
                def __init__(self, source, relative):
                    self.path = source / relative

                def child(self, name, removable=False):
                    raise OSError("simulated handle-open failure after mkdir")

                def close(self):
                    pass

            fake_module = types.SimpleNamespace(LockedDirectory=Directory)
            with mock.patch.dict(sys.modules, {"safari_windows_file": fake_module}):
                with self.assertRaisesRegex(OSError, "handle-open failure"):
                    with safari_reporter._stage_windows(
                            repository, (Path("dyn4k-core"),), b"fragment", root, result):
                        pass
            self.assertEqual("CHANGED", result["status"])
            self.assertEqual("LEFTOVER", result["projects"]["dyn4k-core"])
            self.assertTrue((repository / "dyn4k-core/karma.config.d").is_dir())

    def test_windows_stage_normal_cleanup_removes_owned_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "source"
            (repository / "dyn4k-core").mkdir(parents=True)
            result = {"status": "CLEAN", "projects": {}, "forensic": []}

            class Directory:
                def __init__(self, source, relative):
                    self.path = source / relative

                def child(self, name, removable=False):
                    return Directory(self.path, Path(name))

                def open_file(self, name):
                    return os.open(self.path / name, os.O_RDONLY)

                def remove_empty(self):
                    self.path.rmdir()

                def close(self):
                    pass

            fake_module = types.SimpleNamespace(LockedDirectory=Directory)
            with mock.patch.dict(sys.modules, {"safari_windows_file": fake_module}):
                with safari_reporter._stage_windows(
                        repository, (Path("dyn4k-core"),), b"fragment", root, result):
                    staged = repository / "dyn4k-core/karma.config.d" \
                        / safari_reporter.STAGED_NAME
                    self.assertEqual(b"fragment", staged.read_bytes())
            self.assertEqual("CLEAN", result["status"])
            self.assertEqual("CLEAN", result["projects"]["dyn4k-core"])
            self.assertFalse((repository / "dyn4k-core/karma.config.d").exists())

    def test_stage_close_swap_rejects_replacement_and_preserves_outside(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "source"
            (repository / "dyn4k-core").mkdir(parents=True)
            outside = root / "outside.txt"
            outside.write_bytes(b"outside sentinel")
            result = {"status": "CLEAN", "projects": {}, "forensic": []}

            class Directory:
                def __init__(self, source, relative, child=False):
                    self.path = source / relative
                    self.is_child = child

                def child(self, name, removable=False):
                    return Directory(self.path, Path(name), True)

                def open_file(self, name):
                    return os.open(self.path / name, os.O_RDONLY)

                def remove_empty(self):
                    self.path.rmdir()

                def close(self):
                    if self.is_child:
                        if self.path.exists():
                            self.path.rename(self.path.with_name("karma.config.d.moved"))
                        self.path.mkdir()

            fake_module = types.SimpleNamespace(LockedDirectory=Directory)
            with mock.patch.dict(sys.modules, {"safari_windows_file": fake_module}):
                with safari_reporter._stage_windows(
                        repository, (Path("dyn4k-core"),), b"fragment", root, result):
                    pass
            self.assertEqual("CHANGED", result["status"])
            self.assertEqual("LEFTOVER", result["projects"]["dyn4k-core"])
            self.assertEqual(b"outside sentinel", outside.read_bytes())
            self.assertTrue((repository / "dyn4k-core/karma.config.d").is_dir())

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
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW |
                                     (os.O_DIRECTORY if directory else 0))
                loaded.setdefault("paths", {})[descriptor] = path
                return descriptor

            def information(handle, pointer):
                observed = os.fstat(handle)
                item = ctypes.cast(pointer,
                                   ctypes.POINTER(loaded["module"].FileInformation)).contents
                item.attributes = ((0x10 if stat.S_ISDIR(observed.st_mode) else 0) |
                                   (0x400 if stat.S_ISLNK(observed.st_mode) else 0))
                return 1

            functions = types.SimpleNamespace(CreateFileW=Function(create),
                                              GetFileInformationByHandle=Function(information),
                                              SetFileInformationByHandle=Function(
                                                  lambda handle, kind, pointer, size:
                                                  os.rmdir(loaded["paths"][handle]) or 1),
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
            empty = repository / "package/empty"
            empty.mkdir()
            with directory.child("empty", removable=True) as held:
                held.remove_empty()
            self.assertFalse(empty.exists())
        with self.assertRaises((OSError, ValueError)):
            module.LockedDirectory(repository, Path("linked"))
        self.assertEqual(b"outside\n", sentinel.read_bytes())


if __name__ == "__main__":
    unittest.main()
