import copy
import ctypes
import errno
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import warnings
import zipfile

import capture
import native_host_capture
import native_memory
import native_source_link
import host_image_adverse
import host_image


class PortableCaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(capture.MANIFEST.read_text())
        cls.scenario = capture.scenario_from_manifest(
            cls.manifest, "separated.default.small.30hz.direct_kotlin")
        cls.hashes = {"core": "a" * 64, "kotlin": "b" * 64}
        cls.source = "c" * 40
        cls.producer_tree = "e" * 40
        cls.nonce = "d" * 32

    def protocol(self):
        scenario = self.scenario
        lines = [
            ["PROVIDER", scenario["api"], self.source, self.hashes["core"],
             self.hashes["kotlin"], scenario["id"], "development", self.nonce],
            ["RESOLUTION", "1", "64"],
            ["LINK", self.source, self.producer_tree],
            ["CONSTRUCTION", "100", "0"],
            ["CLOCK", "warmup", "0", "1", "3"],
            ["RESET", "after_warmup", "1"],
            ["CLOCK", "measure", "0", "4", "10"],
            ["STEP", "0", "6", "2", "0", "100", "0", "100",
             "75.0", "0.0", "0", "0", "0", "0", "0", "0"],
            ["RUN", scenario["api"], "timing", "1", "1", "10", "1",
             "memory_attribution_missing", "plateau_missing", "unpassed"],
            ["COMPLETE", self.nonce],
        ]
        return ("\n".join("DYN4K\t" + "\t".join(row) for row in lines) + "\n").encode()

    def validate(self, payload):
        return capture.validate_protocol(
            payload, self.scenario, self.source, self.producer_tree, self.hashes,
            "development", self.nonce, 1, 1, "timing")

    def test_manifest_rejects_baseline_and_unknown_scenario(self):
        with self.assertRaisesRegex(ValueError, "requires direct_kotlin or compatibility"):
            capture.scenario_from_manifest(
                self.manifest, "separated.default.small.30hz.baseline")
        with self.assertRaisesRegex(ValueError, "no unique scenario"):
            capture.scenario_from_manifest(self.manifest, "missing")

    def test_complete_protocol_preserves_raw_clock_and_activity(self):
        clocks, steps, provider, run = self.validate(self.protocol())
        self.assertEqual(clocks["measure"], [(0, 4, 10)])
        self.assertEqual(int(steps[0][7]), 100)
        self.assertEqual(provider[1], "direct_kotlin")
        self.assertEqual(run[-1], "unpassed")

    def test_memory_mode_requires_its_own_producer_process_marker(self):
        payload = self.protocol().replace(b"RUN\tdirect_kotlin\ttiming",
                                          b"RUN\tdirect_kotlin\tmemory")
        with self.assertRaisesRegex(ValueError, "HEAP"):
            capture.validate_protocol(payload, self.scenario, self.source,
                                      self.producer_tree, self.hashes,
                                      "development", self.nonce, 1, 1, "memory")
        payload = payload.replace(b"DYN4K\tCLOCK\twarmup", b"DYN4K\tHEAP\tconstructed\t100\t1\nDYN4K\tCLOCK\twarmup")
        payload = payload.replace(b"DYN4K\tCLOCK\tmeasure", b"DYN4K\tHEAP\tafter_reset\t90\t2\nDYN4K\tCLOCK\tmeasure")
        payload = payload.replace(b"DYN4K\tRUN", b"DYN4K\tHEAP\tmeasured\t120\t3\nDYN4K\tRUN")
        result = capture.validate_protocol(payload, self.scenario, self.source,
                                           self.producer_tree, self.hashes,
                                           "development", self.nonce, 1, 1, "memory")
        self.assertEqual(result[3][2], "memory")
        self.assertEqual(result[0]["heap"], [("constructed", 100, 1),
                                             ("after_reset", 90, 2),
                                             ("measured", 120, 3)])
        with self.assertRaisesRegex(ValueError, "HEAP"):
            capture.validate_protocol(payload.replace(b"\t120\t3", b"\t120\t1"),
                                      self.scenario, self.source, self.producer_tree,
                                      self.hashes, "development", self.nonce, 1, 1, "memory")
        with self.assertRaisesRegex(ValueError, "HEAP"):
            capture.validate_protocol(self.protocol(), self.scenario, self.source,
                                      self.producer_tree, self.hashes,
                                      "development", self.nonce, 1, 1, "memory")

    def test_rejects_substituted_provider(self):
        payload = self.protocol().replace(b"\taaaaaaaaaa", b"\teeeeeeeeee")
        with self.assertRaisesRegex(ValueError, "provider"):
            self.validate(payload)

    def test_rejects_missing_reset_and_truncated_clock(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "RESET"):
            self.validate(payload.replace(b"DYN4K\tRESET\tafter_warmup\t1\n", b""))
        with self.assertRaisesRegex(ValueError, "CLOCK"):
            self.validate(payload.replace(b"DYN4K\tCLOCK\tmeasure\t0\t4\t10\n", b""))

    def test_rejects_fake_activity_or_performance_pass(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "fixture activity"):
            self.validate(payload.replace(b"\t100\t0\t100\t75.0", b"\t1\t0\t100\t75.0"))
        with self.assertRaisesRegex(ValueError, "unfinished evidence"):
            self.validate(payload.replace(b"\tplateau_missing\tunpassed", b"\tplateau_missing\tpassed"))

    def test_rejects_phase_swap_and_run_activity_mismatch(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "warmup clock"):
            self.validate(payload.replace(b"CLOCK\twarmup", b"CLOCK\tother")
                          .replace(b"CLOCK\tmeasure", b"CLOCK\twarmup")
                          .replace(b"CLOCK\tother", b"CLOCK\tmeasure"))
        with self.assertRaisesRegex(ValueError, "activity count"):
            self.validate(payload.replace(b"\t10\t1\tmemory_attribution",
                                          b"\t10\t0\tmemory_attribution"))

    def test_rejects_wrong_source_before_process_launch(self):
        request = SimpleNamespace(target="linuxX64", mode="timing",
                                  steps=1, warmup=0, build="development",
                                  scenario=self.scenario["id"], source_sha=self.source)
        with self.assertRaisesRegex(ValueError, "source SHA"):
            capture.capture(request)
        with self.assertRaisesRegex(ValueError, "absolute regular file"):
            capture.required_file("relative.klib", "core")

    def test_native_host_and_process_image_fail_closed(self):
        wrong_host = "linuxArm64" if capture.sys.platform == "win32" else "mingwX64"
        with self.assertRaisesRegex(ValueError, "matching Native host"):
            capture.require_native_host(wrong_host)
        with self.assertRaisesRegex(ValueError, "unobserved"):
            capture.require_process_image(None, "a" * 64)
        with self.assertRaisesRegex(ValueError, "unobserved"):
            capture.require_process_image({"identity_kind": "reported_path_only", "sha256": "a" * 64},
                                          "a" * 64)
        with self.assertRaisesRegex(ValueError, "observed process image"):
            capture.require_process_image({"identity_kind": "mapped_executable", "sha256": "b" * 64},
                                          "a" * 64)
        capture.require_process_image({"identity_kind": "mapped_executable", "sha256": "a" * 64},
                                      "a" * 64)
        vnode = {"method": "proc_pidinfo_region_vnode", "identity_kind": "mapped_executable_vnode",
                 "sha256": "a" * 64, "mapped_dev": 1, "selected_dev": 1,
                 "mapped_ino": 2, "selected_ino": 2, "mapped_size": 4096}
        capture.require_process_image(vnode, "a" * 64)
        with self.assertRaisesRegex(ValueError, "mapped vnode differs"):
            capture.require_process_image({**vnode, "mapped_ino": 3}, "a" * 64)
        code = {"method": "ReadProcessMemory_main_PE_code",
                "identity_kind": "mapped_executable_code", "sha256": "a" * 64,
                "mapped_code_sha256": "b" * 64, "matched_code_bytes": 8192}
        capture.require_process_image(code, "a" * 64)
        with self.assertRaisesRegex(ValueError, "lacks selected executable binding"):
            capture.require_process_image({**code, "matched_code_bytes": 10}, "a" * 64)

    def test_macos_region_requires_selected_executable_vnode(self):
        selected = SimpleNamespace(st_dev=7, st_ino=11)
        region = {"protection": 5, "offset": 4096, "dev": 7, "ino": 11, "size": 4096}
        self.assertEqual(host_image.select_macos_region([region], selected), region)
        for changed in ({**region, "ino": 12}, {**region, "protection": 1},
                        {**region, "size": 0}):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "vnode mapping"):
                host_image.select_macos_region([changed], selected)

    def test_macos_diagnostic_path_failure_preserves_vnode_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            selected = Path(temporary) / "selected"
            selected.write_bytes(b"selected executable")
            stat = selected.stat()

            def observe_region(ino, path_lookup=None):
                def pidinfo(pid, flavor, address, pointer, size):
                    if address:
                        return 0
                    record = ctypes.cast(pointer, ctypes.POINTER(host_image._RegionWithPath)).contents
                    record.region.address = 0x1000
                    record.region.size = 4096
                    record.region.protection = 5
                    record.vnode.stat.dev = stat.st_dev & 0xffffffff
                    record.vnode.stat.ino = ino
                    return size
                library = SimpleNamespace(proc_pidpath=path_lookup or mock.Mock(return_value=0),
                                          proc_pidinfo=mock.Mock(side_effect=pidinfo))
                with mock.patch.object(host_image.ctypes, "CDLL", return_value=library):
                    return host_image.observe_macos(17, selected)

            for path_lookup, error in ((mock.Mock(return_value=0), "returned no path"),
                                       (mock.Mock(side_effect=OSError(3, "denied")), "denied")):
                with self.subTest(error=error):
                    receipt = observe_region(stat.st_ino, path_lookup)
                    self.assertIsNone(receipt["path"])
                    self.assertIn(error, receipt["path_error"])
                    capture.require_process_image(
                        receipt, hashlib.sha256(selected.read_bytes()).hexdigest())
            with self.assertRaisesRegex(ValueError, "vnode mapping"):
                observe_region(stat.st_ino + 1)

    def test_macos_text_vnode_fallback_survives_path_swap(self):
        with tempfile.TemporaryDirectory() as temporary:
            selected = Path(temporary) / "moved-sleep"
            selected.write_bytes(b"actual child image")
            stat = selected.stat()
            raw = (f"p17\0ftxt\0n/unrelated/cache\0ftxt\0D{stat.st_dev:#x}\0i{stat.st_ino}\0s{stat.st_size}"
                   "\0n/old/path/sleep\0").encode()
            match = host_image.select_macos_text_vnode(raw, 17, stat)
            self.assertEqual((match["dev"], match["ino"], match["size"]),
                             (stat.st_dev, stat.st_ino, stat.st_size))
            self.assertEqual(match["path"], "/old/path/sleep")
            for adverse in (raw.replace(b"p17", b"p18"),
                            raw.replace(f"i{stat.st_ino}".encode(), b"i1"),
                            raw.replace(f"s{stat.st_size}".encode(), b"s1"), raw + raw[4:]):
                with self.subTest(adverse=adverse), self.assertRaises(ValueError):
                    host_image.select_macos_text_vnode(adverse, 17, stat)

            library = SimpleNamespace(proc_pidpath=mock.Mock(return_value=0),
                                      proc_pidinfo=mock.Mock(return_value=0))
            completed = SimpleNamespace(stdout=raw, stderr=b"", returncode=0)
            with mock.patch.object(host_image.ctypes, "CDLL", return_value=library), \
                    mock.patch.object(host_image.subprocess, "run", return_value=completed) as probe:
                receipt = host_image.observe_macos(17, selected)
            probe.assert_called_once()
            self.assertEqual(receipt["method"], "lsof_txt_vnode")
            self.assertEqual(bytes.fromhex(receipt["lsof_stdout_hex"]), raw)
            self.assertIsNone(receipt["path"])
            capture.require_process_image(receipt, hashlib.sha256(selected.read_bytes()).hexdigest())
            with self.assertRaisesRegex(ValueError, "observed mapped vnode"):
                capture.require_process_image({**receipt, "mapped_ino": stat.st_ino + 1},
                                              receipt["sha256"])

    @staticmethod
    def windows_pe_fixture():
        image = bytearray(0x2200)
        image[:2] = b"MZ"
        struct.pack_into("<I", image, 0x3c, 0x80)
        image[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<HH", image, 0x84, 0x8664, 1)
        struct.pack_into("<H", image, 0x94, 0xf0)
        struct.pack_into("<H", image, 0x98, 0x20b)
        struct.pack_into("<Q", image, 0x98 + 24, 0x140000000)
        struct.pack_into("<I", image, 0x98 + 56, 0x3000)
        struct.pack_into("<I", image, 0x98 + 60, 0x200)
        struct.pack_into("<I", image, 0x98 + 108, 16)
        image[0x188:0x18d] = b".text"
        struct.pack_into("<IIII", image, 0x190, 8192, 0x1000, 8192, 0x200)
        struct.pack_into("<I", image, 0x188 + 36, 0x60000020)
        image[0x200:] = bytes(range(256)) * 32
        return image

    def test_windows_live_pe_code_comparison_rejects_substitution(self):
        image = self.windows_pe_fixture()
        layout = host_image.pe_executable_sections(image)
        base = 0x140000000
        def read(address, size):
            return bytes(image[:size] if address == base else image[0x200:0x200 + size])
        self.assertEqual(host_image.compare_pe_code(image, layout, read, base)
                         ["matched_code_bytes"], 8192)
        relocated_base = base + 0x6c0000
        def rebased_read(address, size):
            if address == relocated_base:
                header = bytearray(image[:size])
                struct.pack_into("<Q", header, 0x98 + 24, relocated_base)
                return bytes(header)
            return bytes(image[0x200:0x200 + size])
        self.assertEqual(host_image.compare_pe_code(image, layout, rebased_read,
                                                    relocated_base)["matched_code_bytes"], 8192)
        with self.assertRaisesRegex(ValueError, "mapped PE header differs"):
            host_image.compare_pe_code(image, layout,
                lambda address, size: (bytes(image[:size]) if address == relocated_base
                                       else rebased_read(address, size)), relocated_base)
        relocated_layout = {**layout, "relocations": set(range(0x1010, 0x1018))}
        def relocated_read(address, size):
            if address == base:
                return read(address, size)
            code = bytearray(read(address, size))
            code[0x10:0x18] = b"relocate"
            return bytes(code)
        self.assertEqual(host_image.compare_pe_code(image, relocated_layout, relocated_read, base)
                         ["matched_code_bytes"], 8184)
        with self.assertRaisesRegex(ValueError, "mapped PE code differs"):
            host_image.compare_pe_code(image, layout,
                lambda address, size: (b"z" * size if address != base else read(address, size)), base)
        with self.assertRaisesRegex(ValueError, "mapped PE header differs.*offset 0x0"):
            host_image.compare_pe_code(image, layout,
                lambda address, size: (b"z" * size if address == base else read(address, size)), base)

    def test_windows_live_pe_code_mismatch_identifies_exact_bytes(self):
        image = self.windows_pe_fixture()
        layout = host_image.pe_executable_sections(image)
        base = 0x140000000

        def read(address, size):
            if address == base:
                return bytes(image[:size])
            mapped = bytearray(image[0x200:0x200 + size])
            mapped[37] ^= 1
            return bytes(mapped)

        with self.assertRaises(host_image.PECodeMismatch) as mismatch:
            host_image.compare_pe_code(image, layout, read, base)
        detail = mismatch.exception.detail
        self.assertEqual((detail["section"], detail["rva"], detail["file_offset"]),
                         (".text", 0x1025, 0x225))
        self.assertEqual((detail["selected_byte"], detail["mapped_byte"]), (37, 36))
        self.assertLessEqual(len(bytes.fromhex(detail["selected_window_hex"])), 17)
        self.assertEqual((detail["selected_file_size"], detail["pe_image_size"],
                          detail["pe_header_size"]), (len(image), 0x3000, 0x200))
        self.assertEqual((detail["section_raw_offset"], detail["section_flags"]),
                         (0x200, 0x60000020))
        self.assertEqual((detail["relocation_directory_rva"],
                          detail["relocation_directory_size"]), (0, 0))
        self.assertEqual(detail["selected_image_sha256"], hashlib.sha256(image).hexdigest())
        self.assertEqual(detail["parsed_relocation_byte_count"], 0)
        self.assertEqual(detail["window_relocation_rvas"], [])

    def test_f666_fothk_jump_mismatch_is_not_accepted_as_base_relocation(self):
        image = self.windows_pe_fixture()
        image.extend(b"\x00" * (0x5000 - len(image)))
        struct.pack_into("<H", image, 0x86, 2)
        struct.pack_into("<I", image, 0x98 + 56, 0x6000)
        image[0x1b0:0x1b5] = b"fothk"
        struct.pack_into("<IIII", image, 0x1b8, 4096, 0x4000, 4096, 0x4000)
        struct.pack_into("<I", image, 0x1b0 + 36, 0x60000020)
        image[0x4000:0x5000] = b"\xcc" * 4096
        image[0x4010:0x4015] = bytes.fromhex("e99bfbffff")
        mapped_fothk = bytearray(image[0x4000:0x5000])
        mapped_fothk[0x10:0x15] = bytes.fromhex("e9ab800000")
        layout = host_image.pe_executable_sections(image)
        base = 0x140000000
        def read(address, size):
            if address == base:
                return bytes(image[:size])
            if address == base + 0x4000:
                return bytes(mapped_fothk[:size])
            return bytes(image[0x200:0x200 + size])
        with self.assertRaises(host_image.PECodeMismatch) as mismatch:
            host_image.compare_pe_code(image, layout, read, base)
        detail = mismatch.exception.detail
        self.assertEqual((detail["section"], detail["rva"], detail["file_offset"]),
                         ("fothk", 0x4011, 0x4011))
        self.assertEqual((detail["selected_byte"], detail["mapped_byte"]), (0x9b, 0xab))
        self.assertEqual(detail["selected_window_hex"],
                         "cccccccccccccce99bfbffffcccccccccc")
        self.assertEqual(detail["mapped_window_hex"],
                         "cccccccccccccce9ab800000cccccccccc")
        self.assertEqual(detail["window_relocation_rvas"], [])
        self.assertNotEqual(detail["selected_section_sha256"],
                            detail["mapped_section_sha256"])

    def test_windows_source_archive_entry_uses_jar_separators(self):
        relative = PureWindowsPath("commonMain", "kotlin", "org", "dyn4j", "Vector2.kt")
        self.assertEqual(capture.source_archive_name(relative),
                         "commonMain/org/dyn4j/Vector2.kt")

    def test_native_memory_observer_retains_live_resident_series(self):
        if sys.platform != "linux":
            self.skipTest("local live resident-byte control requires Linux")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = root / "inventory.json"
            inventory.write_text("{}\n")
            archive = root / "archive"
            archive.mkdir()
            receipt, _, _ = capture.run_process(
                [sys.executable, "-c", "import time; time.sleep(0.18)"],
                archive, inventory, b"", 2, observe_memory=True)
            series = json.loads((archive / "rss.json").read_text())
            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(series["status"], "observed_diagnostic")
            self.assertGreaterEqual(len(series["samples"]), 2)
            self.assertTrue(all(value > 0 for _, value in series["samples"]))
            self.assertEqual(receipt["rss_observation"]["rss_json_sha256"],
                             capture.digest(archive / "rss.json"))

    def test_native_host_terminal_esrch_retains_raw_probe_and_live_samples(self):
        if sys.platform != "linux":
            self.skipTest("local live child control requires Linux")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = root / "inventory.json"
            inventory.write_text("{}\n")
            archive = root / "archive"
            archive.mkdir()
            read_resident = native_memory.read_rss_bytes
            calls = 0

            def probe(pid):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return read_resident(pid)
                time.sleep(0.16)
                raise OSError(errno.ESRCH, "macOS process resident bytes unavailable")

            observer = lambda process, stop: native_host_capture.sample_native_resident(
                process, stop, platform_name="darwin")
            with mock.patch.object(native_memory, "sample_while_alive", side_effect=observer), \
                    mock.patch.object(native_memory, "read_rss_bytes", side_effect=probe):
                receipt, stdout, _ = capture.run_process(
                    [sys.executable, "-c", "import time; print('started', flush=True); "
                     "time.sleep(0.09); print('finished', flush=True)"],
                    archive, inventory, b"", 2, observe_memory=True)
            series = json.loads((archive / "rss.json").read_text())
            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(receipt["termination"], "natural")
            self.assertEqual(stdout, b"started\nfinished\n")
            self.assertEqual((archive / "stdout.raw").read_bytes(), stdout)
            self.assertEqual(series["status"], "observed_diagnostic")
            self.assertGreaterEqual(len(series["samples"]), 1)
            self.assertEqual(len(series["errors"]), 1)
            terminal = series["errors"][0]
            self.assertEqual(terminal["errno"], errno.ESRCH)
            self.assertEqual(terminal["classification"], "terminal_esrch_exit_confirmed")
            self.assertEqual(terminal["exit_code"], 0)
            self.assertLessEqual(terminal["error_observed_monotonic_ns"],
                                 terminal["exit_observed_monotonic_ns"])
            self.assertLessEqual(terminal["exit_observed_monotonic_ns"],
                                 receipt["ended_monotonic_ns"])
            self.assertEqual(receipt["rss_observation"]["errors"], 1)
            self.assertEqual(receipt["rss_observation"]["rss_json_sha256"],
                             capture.digest(archive / "rss.json"))

    def test_native_host_midrun_probe_error_stays_partial(self):
        if sys.platform != "linux":
            self.skipTest("local live child control requires Linux")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = root / "inventory.json"
            inventory.write_text("{}\n")
            archive = root / "archive"
            archive.mkdir()
            read_resident = native_memory.read_rss_bytes
            calls = 0

            def probe(pid):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError(errno.ESRCH, "macOS process resident bytes unavailable")
                return read_resident(pid)

            observer = lambda process, stop: native_host_capture.sample_native_resident(
                process, stop, platform_name="darwin")
            with mock.patch.object(native_memory, "sample_while_alive", side_effect=observer), \
                    mock.patch.object(native_memory, "read_rss_bytes", side_effect=probe):
                receipt, stdout, _ = capture.run_process(
                    [sys.executable, "-c", "import time; print('started', flush=True); "
                     "time.sleep(0.18); print('finished', flush=True)"],
                    archive, inventory, b"", 2, observe_memory=True)
            series = json.loads((archive / "rss.json").read_text())
            self.assertEqual((receipt["exit_code"], receipt["termination"]), (0, "natural"))
            self.assertEqual(stdout, b"started\nfinished\n")
            self.assertEqual(series["status"], "unavailable_or_partial")
            self.assertEqual(len(series["errors"]), 1)
            self.assertEqual(series["errors"][0]["errno"], errno.ESRCH)
            self.assertNotIn("classification", series["errors"][0])
            self.assertGreater(series["samples"][-1][0],
                               series["errors"][0]["monotonic_ns"])
            self.assertEqual(receipt["rss_observation"]["rss_json_sha256"],
                             capture.digest(archive / "rss.json"))

    def test_native_memory_unavailable_is_explicit(self):
        class FakeProcess:
            pid = 17
            calls = 0
            def poll(self):
                self.calls += 1
                return None if self.calls < 3 else 1
        with mock.patch.object(native_memory, "read_rss_bytes", side_effect=OSError(5, "denied")):
            result = native_memory.sample_while_alive(FakeProcess(), mock.Mock(is_set=lambda: False))
        self.assertEqual(result["status"], "unavailable_or_partial")
        self.assertEqual(result["samples"], [])
        self.assertGreaterEqual(len(result["errors"]), 1)
        self.assertIn("denied", result["errors"][0]["error"])

    def test_macos_resident_probe_uses_task_info_bytes(self):
        requested_sizes = []

        def pidinfo(pid, flavor, argument, pointer, size):
            self.assertEqual((pid, flavor, argument), (17, 4, 0))
            requested_sizes.append(size)
            if size != 96:
                return 0
            info = ctypes.cast(pointer, ctypes.POINTER(native_memory._MacTaskInfo)).contents
            info.resident_size = 123456
            return 96
        library = SimpleNamespace(proc_pidinfo=mock.Mock(side_effect=pidinfo))
        with mock.patch.object(native_memory.sys, "platform", "darwin"), \
                mock.patch.object(native_memory.ctypes, "CDLL", return_value=library):
            self.assertEqual(native_memory.read_rss_bytes(17), 123456)
            self.assertEqual(requested_sizes, [96])
            self.assertEqual(ctypes.sizeof(native_memory._MacTaskInfo), 96)
            library.proc_pidinfo.return_value = 0
            library.proc_pidinfo.side_effect = None
            with self.assertRaisesRegex(OSError, "resident bytes unavailable"):
                native_memory.read_rss_bytes(17)

    def test_macos_resident_probe_rejects_wrong_abi_size(self):
        class ShortTaskInfo(ctypes.Structure):
            _fields_ = [("values", ctypes.c_uint64 * 6),
                        ("counts", ctypes.c_int32 * 10)]

        with mock.patch.object(native_memory.sys, "platform", "darwin"), \
                mock.patch.object(native_memory, "_MacTaskInfo", ShortTaskInfo), \
                mock.patch.object(native_memory.ctypes, "CDLL") as load_library:
            with self.assertRaisesRegex(ValueError, "ABI size is 88, expected 96"):
                native_memory.read_rss_bytes(17)
            load_library.assert_not_called()

    def test_windows_resident_probe_uses_working_set_bytes(self):
        def memory_info(handle, pointer, size):
            self.assertEqual((handle, size), (123, ctypes.sizeof(native_memory._WindowsMemoryCounters)))
            counters = ctypes.cast(pointer, ctypes.POINTER(
                native_memory._WindowsMemoryCounters)).contents
            counters.working_set = 654321
            return 1
        kernel = SimpleNamespace(OpenProcess=mock.Mock(return_value=123),
                                 CloseHandle=mock.Mock())
        psapi = SimpleNamespace(GetProcessMemoryInfo=mock.Mock(side_effect=memory_info))
        with mock.patch.object(native_memory.sys, "platform", "win32"), \
                mock.patch.object(native_memory.ctypes, "WinDLL", create=True,
                                  side_effect=lambda name, **kwargs:
                                  kernel if name == "kernel32" else psapi), \
                mock.patch.object(native_memory.ctypes, "WinError", create=True,
                                  side_effect=lambda code: OSError(code, "denied")), \
                mock.patch.object(native_memory.ctypes, "get_last_error", create=True,
                                  return_value=5):
            self.assertEqual(native_memory.read_rss_bytes(17), 654321)
            kernel.CloseHandle.assert_called_once_with(123)
            psapi.GetProcessMemoryInfo.side_effect = None
            psapi.GetProcessMemoryInfo.return_value = 0
            with self.assertRaises(OSError):
                native_memory.read_rss_bytes(17)

    def test_windows_diagnostic_path_failure_preserves_live_code_gate(self):
        image = self.windows_pe_fixture()
        base = 0x140000000
        with tempfile.TemporaryDirectory() as temporary:
            selected = Path(temporary) / "selected.exe"
            selected.write_bytes(image)

            def observe(mutated, path_lookup=None):
                def enum_modules(handle, modules, length, needed, flags):
                    modules[0] = base
                    ctypes.cast(needed, ctypes.POINTER(host_image.wintypes.DWORD))[0] = \
                        ctypes.sizeof(ctypes.c_void_p)
                    return 1
                def module_info(handle, module, pointer, length):
                    info = ctypes.cast(pointer, ctypes.POINTER(host_image._ModuleInfo)).contents
                    info.base = base
                    info.size = 0x3000
                    return 1
                def read_memory(handle, address, buffer, size, count):
                    data = bytearray(image[:size] if address.value == base else image[0x200:0x200 + size])
                    if mutated == "header" and address.value == base:
                        data[0] ^= 1
                    if mutated == "code" and address.value != base:
                        data[0] ^= 1
                    ctypes.memmove(buffer, bytes(data), size)
                    ctypes.cast(count, ctypes.POINTER(ctypes.c_size_t))[0] = size
                    return 1
                kernel = SimpleNamespace(OpenProcess=mock.Mock(return_value=123),
                                         CloseHandle=mock.Mock(),
                                         ReadProcessMemory=mock.Mock(side_effect=read_memory),
                                         QueryFullProcessImageNameW=path_lookup or mock.Mock(return_value=0))
                psapi = SimpleNamespace(EnumProcessModulesEx=mock.Mock(side_effect=enum_modules),
                                        GetModuleInformation=mock.Mock(side_effect=module_info))
                with mock.patch.object(host_image.ctypes, "get_last_error", return_value=5,
                                       create=True), mock.patch.object(
                                           host_image.ctypes, "WinDLL", create=True,
                                           side_effect=lambda name, **kwargs:
                                               kernel if name == "kernel32" else psapi):
                    try:
                        return host_image.observe_windows(17, selected)
                    finally:
                        kernel.CloseHandle.assert_called_once_with(123)

            for path_lookup, error in ((mock.Mock(return_value=0), "returned no path"),
                                       (mock.Mock(side_effect=OSError(5, "denied")), "denied")):
                with self.subTest(error=error):
                    receipt = observe(None, path_lookup)
                    self.assertIsNone(receipt["path"])
                    self.assertIn(error, receipt["path_error"])
                    capture.require_process_image(receipt, hashlib.sha256(image).hexdigest())
            for mutated in ("header", "code"):
                with self.subTest(mutated=mutated), self.assertRaisesRegex(
                        ValueError, f"mapped PE {mutated} differs"):
                    observe(mutated)

    def test_native_host_selects_only_resolved_target_artifacts(self):
        inventory = {"resolved_artifacts": [
            {"module": capture.native_module("dyn4k-core", "linuxArm64"), "path": "/core.klib"},
            {"module": capture.native_module("dyn4k", "linuxArm64"), "path": "/kotlin.klib"},
        ]}
        self.assertEqual(native_host_capture.selected_artifact(inventory, "dyn4k-core", "linuxArm64"),
                         "/core.klib")
        self.assertEqual(native_host_capture.selected_artifact(inventory, "dyn4k", "linuxArm64"),
                         "/kotlin.klib")
        inventory["resolved_artifacts"].append(inventory["resolved_artifacts"][0])
        with self.assertRaisesRegex(ValueError, "exactly two"):
            native_host_capture.selected_artifact(inventory, "dyn4k-core", "linuxArm64")

    def test_native_host_cli_uses_terminal_observer_only_for_macos_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            inventory = Path(temporary) / "inventory.json"
            inventory.write_text(json.dumps({
                "target": "macosArm64", "build": "development",
                "harness": "/selected/producer.kexe", "source_sha": "a" * 40}))
            original_sampler = native_memory.sample_while_alive
            for mode in ("timing", "memory"):
                observed = {}

                def dispatched():
                    observed["argv"] = list(sys.argv)
                    observed["sampler"] = native_memory.sample_while_alive

                argv = [str(Path(native_host_capture.__file__)),
                        "--archive", str(Path(temporary) / mode),
                        "--inventory", str(inventory),
                        "--publication-root", temporary,
                        "--scenario", "separated.default.small.30hz.direct_kotlin",
                        "--target", "macosArm64", "--build", "development",
                        "--mode", mode, "--steps", "30", "--warmup", "3"]
                with mock.patch.object(sys, "argv", argv), \
                        mock.patch.object(native_host_capture.sys, "platform", "darwin"), \
                        mock.patch.object(native_host_capture, "selected_artifact",
                                          return_value="/selected/artifact.klib"), \
                        mock.patch.object(capture, "main", side_effect=dispatched), \
                        mock.patch.object(native_host_capture.subprocess, "call",
                                          return_value=0) as subprocess_call:
                    if mode == "memory":
                        native_host_capture.main()
                        self.assertEqual(observed["argv"][0],
                                         str(Path(capture.__file__).resolve()))
                        self.assertEqual(observed["argv"][observed["argv"].index("--runtime") + 1],
                                         "/selected/producer.kexe")
                        self.assertIs(observed["sampler"],
                                      native_host_capture.sample_native_resident)
                        subprocess_call.assert_not_called()
                    else:
                        with self.assertRaises(SystemExit) as exit_status:
                            native_host_capture.main()
                        self.assertEqual(exit_status.exception.code, 0)
                        self.assertEqual(subprocess_call.call_args.args[0][0], sys.executable)
                        self.assertEqual(subprocess_call.call_args.args[0][1],
                                         str(Path(capture.__file__).resolve()))
                self.assertIs(native_memory.sample_while_alive, original_sampler)

    def test_publication_receipt_rejects_resealed_source_archive(self):
        label, target = "dyn4k-core", "linuxX64"
        module = "dyn4k-core-linuxx64"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "io/github/rubixhacker" / module / capture.ARTIFACT_VERSION
            directory.mkdir(parents=True)
            stem = f"{module}-{capture.ARTIFACT_VERSION}"
            klib = directory / f"{stem}.klib"
            klib.write_bytes(b"staged bytes")
            metadata = directory / f"{stem}.module"
            sources = directory / f"{stem}-sources.jar"
            source_root = capture.ROOT / label / "src"
            entries = {capture.source_archive_name(path.relative_to(source_root)): path
                       for path in source_root.rglob("*.kt")
                       if path.relative_to(source_root).parts[0] in ("commonMain", "nativeMain",
                                                                    "linuxMain", "linuxX64Main")}
            with zipfile.ZipFile(sources, "w") as archive:
                for name, path in entries.items():
                    archive.write(path, name)
            document = {
                "component": {"url": f"../../{label}/{capture.ARTIFACT_VERSION}/"
                              f"{label}-{capture.ARTIFACT_VERSION}.module",
                              "group": capture.ARTIFACT_GROUP, "module": label,
                              "version": capture.ARTIFACT_VERSION,
                              "attributes": {"org.gradle.status": "release"}},
                "variants": [{"name": "linuxX64ApiElements-published",
                              "files": [{"url": klib.name, "sha256": capture.digest(klib)}]},
                             {"name": "linuxX64SourcesElements-published",
                              "files": [{"url": sources.name,
                                         "sha256": capture.digest(sources)}]}],
            }
            metadata.write_text(json.dumps(document))
            for path in (klib, metadata, sources):
                path.with_name(path.name + ".sha256").write_text(capture.digest(path))
            self.assertTrue(capture.validate_publication(root, label, target,
                                                         capture.digest(klib))["source_archive_matches_checkout"])
            name = next(iter(entries))
            original = [(entry, path.read_bytes()) for entry, path in entries.items()]
            mutations = (
                ("changed", [(entry, b"substituted" if entry == name else data)
                             for entry, data in original], "source bytes"),
                ("missing", [(entry, data) for entry, data in original if entry != name],
                 "source inventory"),
                ("duplicate", [(name, b"SUBSTITUTED_FIRST"), *original],
                 "duplicate Kotlin"),
            )
            for mutation, members, error in mutations:
                with self.subTest(mutation=mutation), warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(sources, "w") as archive:
                        for entry, data in members:
                            archive.writestr(entry, data)
                    sources.with_name(sources.name + ".sha256").write_text(capture.digest(sources))
                    document["variants"][1]["files"][0]["sha256"] = capture.digest(sources)
                    metadata.write_text(json.dumps(document))
                    metadata.with_name(metadata.name + ".sha256").write_text(capture.digest(metadata))
                    with self.assertRaisesRegex(ValueError, error):
                        capture.validate_publication(root, label, target, capture.digest(klib))

    def test_source_link_trace_requires_real_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = str(Path(temporary) / "source.kt")
            output = str(Path(temporary) / "output.klib")
            trace = Path(temporary) / "build.strace"
            trace.write_text(
                f'1 read(3<{source}>, "abc", 3) = 3\n'
                f'1 write(4<{output}>, "abc", 3) = 3\n')
            events = native_source_link.trace_events(trace, (source, output))
            self.assertEqual(events["read"], [source])
            self.assertEqual(events["write"], [output])
            trace.write_text(f'1 openat(AT_FDCWD, "{source}", O_RDONLY) = 3<{source}>\n')
            self.assertEqual(native_source_link.trace_events(trace, (source,))["read"], [])

    def test_resealed_older_klib_cannot_claim_traced_selection(self):
        receipt = {"publication": {"dyn4k-core": {"sha256": "a" * 64},
                                   "dyn4k": {"sha256": "b" * 64}},
                   "inventories": {"development": {"path": "/fresh/inventory.json",
                                                   "executable_sha256": "c" * 64}}}
        native_source_link.require_selected_inputs(
            receipt, "development", "/fresh/inventory.json", "c" * 64,
            {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64})
        with self.assertRaisesRegex(ValueError, "lacks traced source-to-link provenance"):
            native_source_link.require_selected_inputs(
                receipt, "development", "/fresh/inventory.json", "c" * 64,
                {"dyn4k-core": "d" * 64, "dyn4k": "b" * 64})

    def test_link_output_requires_writable_mapping_and_rename(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = str(Path(temporary) / "program.kexe")
            staged = executable + ".tmp123"
            trace = Path(temporary) / "link.strace"
            created = f'1 1.0 openat(AT_FDCWD, "{staged}", O_RDWR|O_CREAT) = 3<{staged}>\n'
            mapped = f'1 2.0 mmap(NULL, 100, PROT_READ|PROT_WRITE, MAP_SHARED, 3<{staged}>, 0) = 0x1234\n'
            renamed = f'1 3.0 rename("{staged}", "{executable}") = 0\n'
            trace.write_text(created + mapped + renamed)
            self.assertTrue(native_source_link.executable_install(trace, executable)
                            ["renamed_to_executable"])
            for mutation in (created + mapped.replace("MAP_SHARED", "MAP_PRIVATE") + renamed,
                             renamed + created + mapped,
                             created + mapped.replace("1 2.0", "2 2.0") + renamed,
                             created + mapped.replace("3<", "4<") + renamed,
                             created + mapped + renamed.replace("1 3.0", "2 3.0")):
                with self.subTest(mutation=mutation):
                    trace.write_text(mutation)
                    with self.assertRaisesRegex(ValueError, "ordered same-process"):
                        native_source_link.executable_install(trace, executable)

    def test_traced_command_requires_selected_gradle_and_java_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            trace = Path(temporary) / "action.strace"
            command = ["/pinned/gradle", "--offline", "task"]
            gradle = f'1 1.0 execve("/pinned/gradle", {json.dumps(command)}, 0x1) = 0\n'
            java = '1 2.0 execve("/pinned/jdk/bin/java", ' + \
                json.dumps(["/pinned/jdk/bin/java", *command[1:]]) + ', 0x1) = 0\n'
            trace.write_text(gradle + java)
            native_source_link.require_traced_execve(trace, command, "/pinned/jdk/bin/java")
            for mutation in (java, gradle, gradle + java.replace("1 2.0", "2 2.0"),
                             java + gradle, gradle.replace("task", "other") + java):
                with self.subTest(mutation=mutation):
                    trace.write_text(mutation)
                    with self.assertRaisesRegex(ValueError, "execve unobserved"):
                        native_source_link.require_traced_execve(
                            trace, command, "/pinned/jdk/bin/java")

    @unittest.skipUnless(os.environ.get("DYN4K_NATIVE_RETAINED_RECEIPT"),
                         "set DYN4K_NATIVE_RETAINED_RECEIPT for raw trace replay")
    def test_public_receipt_replay_rejects_resealed_trace_mutants(self):
        selected = Path(os.environ["DYN4K_NATIVE_RETAINED_RECEIPT"])
        original = json.loads(selected.read_text())
        root = Path(original["checkout"])
        source_files = native_source_link.source_files
        producer_files = native_source_link.consumer_source_files
        identity_source = native_source_link.identity_source
        with ExitStack() as patches:
            patches.enter_context(mock.patch.object(native_source_link, "ROOT", root))
            patches.enter_context(mock.patch.object(capture, "ROOT", root))
            patches.enter_context(mock.patch.object(native_source_link, "source_files",
                                              side_effect=lambda: source_files(root)))
            patches.enter_context(mock.patch.object(native_source_link, "consumer_source_files",
                                              side_effect=lambda: producer_files(root)))
            patches.enter_context(mock.patch.object(native_source_link, "identity_source",
                                              side_effect=lambda: identity_source(root)))
            self.assertEqual(native_source_link.verify_receipt(selected)["source_sha"],
                             original["source_sha"])
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                action = original["actions"]["publication"]
                gradle = f'1 1.0 execve({json.dumps(action["command"][0])}, ' + \
                    f'{json.dumps(action["command"])}, 0x1) = 0\n'
                java_path = action["environment"]["JAVA_HOME"] + "/bin/java"
                java = f'1 2.0 execve({json.dumps(java_path)}, ' + \
                    f'{json.dumps([java_path, *action["command"][1:]])}, 0x1) = 0\n'
                reads = "".join(f'1 3.0 read(3<{path}>, "x", 1) = 1\n'
                                for path in (*original["source_files"], original["compiler_jar"]))
                output_paths = [item[field] for item in original["publication"].values()
                                for field in ("compiler_klib", "staged_klib")]
                for name, trace_text, expected in (
                    ("no-writes", gradle + java + reads, "KLIB writes unobserved"),
                    ("no-staged-writes", gradle + java + reads +
                     "".join(f'1 4.0 write(4<{path}>, "x", 1) = 1\n'
                             for path in output_paths[::2]), "KLIB writes unobserved"),
                    ("no-java", gradle + reads, "Gradle/JDK execve unobserved")):
                    with self.subTest(name=name):
                        trace = directory / f"{name}.strace"
                        trace.write_text(trace_text)
                        candidate = copy.deepcopy(original)
                        candidate["actions"]["publication"]["trace"] = str(trace)
                        candidate["actions"]["publication"]["trace_sha256"] = capture.digest(trace)
                        candidate["actions"]["publication"]["traced_command"][9] = str(trace)
                        candidate["observed_syscalls"]["publication"] = \
                            native_source_link.trace_events(trace,
                                [*original["source_files"], original["compiler_jar"],
                                 *output_paths])
                        candidate_path = directory / f"{name}.json"
                        candidate_path.write_text(json.dumps(candidate))
                        with self.assertRaisesRegex(ValueError, expected):
                            native_source_link.verify_receipt(candidate_path)
                candidate = copy.deepcopy(original)
                candidate["actions"]["publication"]["traced_command"][9] = \
                    str(directory / "unrelated.strace")
                candidate_path = directory / "wrong-output-argument.json"
                candidate_path.write_text(json.dumps(candidate))
                with self.assertRaisesRegex(ValueError, "traced toolchain differs"):
                    native_source_link.verify_receipt(candidate_path)

                link_action = original["actions"]["development"]
                executable = original["inventories"]["development"]["executable"]
                temporary_output = executable + ".tmp-replay"
                link_gradle = f'1 1.0 execve({json.dumps(link_action["command"][0])}, ' + \
                    f'{json.dumps(link_action["command"])}, 0x1) = 0\n'
                link_java_path = link_action["environment"]["JAVA_HOME"] + "/bin/java"
                link_java = f'1 2.0 execve({json.dumps(link_java_path)}, ' + \
                    f'{json.dumps([link_java_path, *link_action["command"][1:]])}, 0x1) = 0\n'
                link_reads = "".join(f'1 3.0 read(3<{path}>, "x", 1) = 1\n'
                                     for path in original["observed_syscalls"]["development"]["read"])
                link_writes = "".join(f'1 4.0 write(4<{path}>, "x", 1) = 1\n'
                                      for path in original["observed_syscalls"]["development"]["write"])
                created = f'1 5.0 openat(AT_FDCWD, "{temporary_output}", O_RDWR|O_CREAT) = 5<{temporary_output}>\n'
                mapped = f'1 6.0 mmap(NULL, 100, PROT_READ|PROT_WRITE, MAP_SHARED, 5<{temporary_output}>, 0) = 0x1234\n'
                renamed = f'1 7.0 rename("{temporary_output}", "{executable}") = 0\n'
                for name, install, accepted in (
                    ("ordered-install", created + mapped + renamed, True),
                    ("reversed-install", renamed + created + mapped, False),
                    ("cross-pid-install", created + mapped.replace("1 6.0", "2 6.0") + renamed, False),
                    ("wrong-fd-install", created + mapped.replace("5<", "6<") + renamed, False)):
                    with self.subTest(name=name):
                        trace = directory / f"{name}.strace"
                        trace.write_text(link_gradle + link_java + link_reads + link_writes + install)
                        candidate = copy.deepcopy(original)
                        candidate["actions"]["development"]["trace"] = str(trace)
                        candidate["actions"]["development"]["trace_sha256"] = capture.digest(trace)
                        candidate["actions"]["development"]["traced_command"][9] = str(trace)
                        if accepted:
                            candidate["observed_syscalls"]["development"] = \
                                native_source_link.trace_events(trace,
                                    [*original["observed_syscalls"]["development"]["read"],
                                     *original["observed_syscalls"]["development"]["write"]])
                            candidate["observed_syscalls"]["development"]["executable_install"] = \
                                native_source_link.executable_install(trace, executable)
                        candidate_path = directory / f"{name}.json"
                        candidate_path.write_text(json.dumps(candidate))
                        if accepted:
                            native_source_link.verify_receipt(candidate_path)
                        else:
                            with self.assertRaisesRegex(ValueError, "ordered same-process"):
                                native_source_link.verify_receipt(candidate_path)

    def test_host_deadline_retains_raw_and_process_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            archive.mkdir()
            inventory = root / "inventory.json"
            inventory.write_text("{}\n")
            command = [sys.executable, "-u", "-c",
                       "import sys,time; print('raw',flush=True); "
                       "print('error',file=sys.stderr,flush=True); time.sleep(30)"]
            execution, stdout, stderr = capture.run_process(command, archive, inventory, b"", 0.2)
            self.assertEqual(execution["termination"], "host_deadline")
            self.assertNotEqual(execution["exit_code"], 0)
            self.assertEqual(stdout, (archive / "stdout.raw").read_bytes())
            self.assertEqual(stderr, (archive / "stderr.raw").read_bytes())
            self.assertIn(b"raw", stdout)
            self.assertIn(b"error", stderr)
            self.assertEqual((archive / "build-inventory.json").read_bytes(), inventory.read_bytes())
            self.assertEqual(json.loads((archive / "execution.json").read_text())["pid"],
                             execution["pid"])

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux capture timeout control")
    def test_capture_timeout_writes_unpassed_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "debugExecutable" / "probe.kexe"
            executable.parent.mkdir()
            shutil.copy2(sys.executable, executable)
            core, kotlin, inventory = (root / name for name in ("core.klib", "kotlin.klib",
                                                                 "inventory.json"))
            core.write_bytes(b"core")
            kotlin.write_bytes(b"kotlin")
            inventory.write_text("{}\n")
            source = subprocess.check_output(["git", "-C", str(capture.ROOT), "rev-parse", "HEAD"],
                                             text=True).strip()
            request = SimpleNamespace(target="linuxX64", mode="timing", steps=1, warmup=0,
                                      build="development", scenario=self.scenario["id"],
                                      source_sha=source, runtime=str(executable),
                                      harness=str(executable), core=str(core), kotlin=str(kotlin),
                                      inventory=str(inventory), archive=root / "archive",
                                      host_timeout_seconds=0.2, publication_root=root)
            actual_check = capture.subprocess.check_output
            actual_run = capture.run_process
            def check(command, **kwargs):
                return "" if "status" in command else actual_check(command, **kwargs)
            def hang(command, archive, receipt, stdin, deadline):
                script = "import sys,time; print('raw',flush=True); " \
                         "print('error',file=sys.stderr,flush=True); time.sleep(30)"
                return actual_run([sys.executable, "-u", "-c", script], archive, receipt,
                                  stdin, deadline)
            with mock.patch.object(capture.subprocess, "check_output", side_effect=check), \
                 mock.patch.object(capture, "validate_inventory", return_value={
                     "gradle": "9.5.0", "kgp": "2.4.20",
                     "compile_configuration": "linuxX64CompileKlibraries"}), \
                 mock.patch.object(capture, "run_process", side_effect=hang):
                with self.assertRaisesRegex(ValueError, "host deadline"):
                    capture.capture(request)
            record = json.loads((request.archive / "capture.json").read_text())
            self.assertEqual(record["termination"], "host_deadline")
            self.assertEqual(record["qualification"], "unpassed")
            self.assertIn(b"raw", (request.archive / "stdout.raw").read_bytes())
            self.assertIn(b"error", (request.archive / "stderr.raw").read_bytes())
            self.assertEqual((request.archive / "build-inventory.json").read_bytes(), b"{}\n")

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux receipt archive control")
    def test_capture_verifies_archived_receipt_and_rejects_postcheck_swap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "debugExecutable" / "probe.kexe"
            executable.parent.mkdir()
            shutil.copy2(sys.executable, executable)
            core, kotlin, inventory = (root / name for name in ("core.klib", "kotlin.klib",
                                                                 "inventory.json"))
            core.write_bytes(b"core")
            kotlin.write_bytes(b"kotlin")
            inventory.write_text("{}\n")
            external = root / "candidate.json"
            original = b'{"selected":true}\n'
            source = subprocess.check_output(["git", "-C", str(capture.ROOT), "rev-parse", "HEAD"],
                                             text=True).strip()
            actual_check = capture.subprocess.check_output
            actual_run = capture.run_process
            def check(command, **kwargs):
                return "" if "status" in command else actual_check(command, **kwargs)
            def hang(command, archive, receipt, stdin, deadline):
                return actual_run([sys.executable, "-c", "import time;time.sleep(30)"],
                                  archive, receipt, stdin, deadline)
            evidence = {"source_files": {"engine": "hash"},
                        "producer_source_files": {"producer": "hash"},
                        "compiler_jar_sha256": "a" * 64,
                        "observed_syscalls": {
                            "publication": {"write": ["core", "kotlin"]},
                            "development": {"write": [], "executable_install": {}}}}
            for swap in ("external", "archived", "during-capture"):
                with self.subTest(swap=swap):
                    external.write_bytes(original)
                    archive = root / (swap + "-swap")
                    request = SimpleNamespace(target="linuxX64", mode="timing", steps=1, warmup=0,
                        build="development", scenario=self.scenario["id"], source_sha=source,
                        runtime=str(executable), harness=str(executable), core=str(core),
                        kotlin=str(kotlin), inventory=str(inventory), archive=archive,
                        host_timeout_seconds=0.2, publication_root=root,
                        source_link_receipt=external)
                    def verify(path, *_):
                        self.assertEqual(Path(path).read_bytes(), original)
                        self.assertEqual(Path(path), archive / "source-link.json")
                        if swap != "during-capture":
                            (Path(path) if swap == "archived" else external).write_bytes(
                                b'{"tampered":true}\n')
                        return evidence
                    def run_with_swap(command, archive, receipt, stdin, deadline):
                        result = hang(command, archive, receipt, stdin, deadline)
                        if swap == "during-capture":
                            (archive / "source-link.json").write_bytes(b'{"tampered":true}\n')
                        return result
                    with mock.patch.object(capture.subprocess, "check_output", side_effect=check), \
                         mock.patch.object(capture, "validate_inventory", return_value={
                             "gradle": "9.5.0", "kgp": "2.4.20",
                             "compile_configuration": "linuxX64CompileKlibraries"}), \
                         mock.patch.object(native_source_link, "verify_receipt", side_effect=verify), \
                         mock.patch.object(native_source_link, "require_selected_inputs"), \
                         mock.patch.object(capture, "run_process", side_effect=run_with_swap) as launched:
                        if swap == "archived":
                            with self.assertRaisesRegex(ValueError, "archived source-link receipt changed"):
                                capture.capture(request)
                            launched.assert_not_called()
                        elif swap == "during-capture":
                            with self.assertRaisesRegex(ValueError, "changed during process capture"):
                                capture.capture(request)
                        else:
                            with self.assertRaisesRegex(ValueError, "host deadline"):
                                capture.capture(request)
                            self.assertEqual((archive / "source-link.json").read_bytes(), original)
                            record = json.loads((archive / "capture.json").read_text())
                            self.assertEqual(record["source_link_trace"]["receipt_sha256"],
                                             capture.digest(archive / "source-link.json"))
                            self.assertEqual(record["source_to_link"], "observed_build_provenance")

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux mapped executable control")
    def test_path_swap_keeps_linux_proc_image_bytes(self):
        result = host_image_adverse.path_swap_control()
        self.assertEqual(result["swap"], "applied")
        self.assertEqual(result["mapped_image_identity"], "matched_original")
        self.assertEqual(result["stale_pid"], "rejected")

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux mapped executable control")
    def test_path_swap_does_not_copy_system_file_metadata(self):
        with mock.patch.object(host_image_adverse.shutil, "copy2",
                               side_effect=PermissionError(1, "copy metadata denied")):
            result = host_image_adverse.path_swap_control()
        self.assertEqual(result["swap"], "applied")
        self.assertEqual(result["mapped_image_identity"], "matched_original")
        self.assertEqual(result["stale_pid"], "rejected")

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux mapped executable control")
    def test_path_swap_retains_failing_step(self):
        failures = ((host_image_adverse.shutil, "copyfile", "copy_image", "copy denied"),
                    (host_image_adverse.subprocess, "Popen", "launch_image", "launch denied"),
                    (capture, "observed_process_image", "observe_before",
                     "live mapped PE header differs at offset 0x10"))
        for module, function, stage, message in failures:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "path-swap.json"
                error = ValueError(message) if stage == "observe_before" else PermissionError(1, message)
                with mock.patch.object(module, function, side_effect=error), \
                        mock.patch.object(sys, "argv", ["host_image_adverse.py", "--output", str(output)]), \
                        redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        host_image_adverse.main()
                receipt = json.loads(output.read_text())
                self.assertEqual(receipt["mapped_image_identity"], "unobserved")
                self.assertEqual(receipt["error_stage"], stage)
                self.assertIn(message, receipt["error"])

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux mapped executable control")
    def test_path_swap_retains_pe_mismatch_and_cleans_child(self):
        detail = {"section": ".text", "rva": 0x1042,
                  "selected_byte": 1, "mapped_byte": 2}
        launched = []
        original_popen = host_image_adverse.subprocess.Popen

        def launch(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            launched.append(process)
            return process

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "path-swap.json"
            with mock.patch.object(capture, "observed_process_image",
                                   side_effect=host_image.PECodeMismatch(detail)), \
                    mock.patch.object(host_image_adverse.subprocess, "Popen", side_effect=launch), \
                    mock.patch.object(sys, "argv", ["host_image_adverse.py", "--output", str(output)]), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    host_image_adverse.main()
            receipt = json.loads(output.read_text())
        self.assertEqual(receipt["error_stage"], "observe_before")
        self.assertEqual(receipt["original_sha256"], capture.digest(Path("/bin/sleep")))
        self.assertEqual(receipt["control_image_source"], "/bin/sleep")
        self.assertEqual(receipt["pe_mismatch"], detail)
        self.assertEqual(receipt["stale_pid"], "rejected")
        self.assertEqual(len(launched), 1)
        self.assertIsNotNone(launched[0].poll())
        self.assertFalse(Path(launched[0].args[0]).exists())

    def test_windows_path_swap_main_uploads_only_bounded_diagnostics(self):
        image = self.windows_pe_fixture()
        layout = host_image.pe_executable_sections(image)
        base = 0x140000000

        def read(address, size):
            if address == base:
                return bytes(image[:size])
            mapped = bytearray(image[0x200:0x200 + size])
            mapped[37] ^= 1
            return bytes(mapped)

        with self.assertRaises(host_image.PECodeMismatch) as mismatch:
            host_image.compare_pe_code(image, layout, read, base)
        source_sha = "a" * 40
        process = SimpleNamespace(pid=17, poll=mock.Mock(return_value=None),
                                  stdout=io.BytesIO(b"DYN4K_IMAGE_CONTROL_READY\t" +
                                                    source_sha.encode() + b"\n"),
                                  terminate=mock.Mock(), communicate=mock.Mock(return_value=(b"", b"")),
                                  returncode=1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "build" / "dyn4k-performance-portable.exe"
            source.parent.mkdir(parents=True)
            source.write_bytes(image)
            image_sha = hashlib.sha256(image).hexdigest()
            artifact = root / "runner" / "performance-native-host-short"
            output = artifact / "setup" / "path-swap.json"
            private_home = root / "private-home"
            private_home.mkdir()
            launched = []

            def launch(command, **kwargs):
                selected = Path(command[0])
                self.assertEqual(command[1:], ["--image-control-hold", source_sha])
                self.assertFalse(selected.is_relative_to(artifact))
                self.assertEqual(selected.read_bytes(), image)
                launched.append(selected)
                return process

            with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(root / "runner"),
                                              "GITHUB_WORKSPACE": str(root / "workspace")}), \
                    mock.patch.object(Path, "home", return_value=private_home), \
                    mock.patch.object(host_image_adverse.sys, "platform", "win32"), \
                    mock.patch.object(host_image_adverse.subprocess, "Popen", side_effect=launch), \
                    mock.patch.object(host_image_adverse.time, "sleep"), \
                    mock.patch.object(capture, "observed_process_image",
                                      side_effect=mismatch.exception), \
                    mock.patch.object(sys, "argv", ["host_image_adverse.py", "--output", str(output),
                                                    "--control-image", str(source),
                                                    "--control-sha256", image_sha,
                                                    "--control-source-sha", source_sha]), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    host_image_adverse.main()
            receipt = json.loads(output.read_text())
            self.assertEqual([p.relative_to(artifact).as_posix() for p in artifact.rglob("*")
                              if p.is_file()], ["setup/path-swap.json"])
            self.assertLess(output.stat().st_size, 4096)
            self.assertNotIn("selected_image_archive", receipt)
            self.assertEqual(receipt["original_sha256"], hashlib.sha256(image).hexdigest())
            self.assertEqual(receipt["control_image_size"], len(image))
            self.assertEqual(receipt["control_image_source"], str(source))
            self.assertEqual(receipt["pe_mismatch"], mismatch.exception.detail)
            self.assertEqual(receipt["error_stage"], "observe_before")
            self.assertEqual(receipt["mapped_image_identity"], "unobserved")
            self.assertEqual(receipt["stale_pid"], "rejected")
            self.assertEqual(receipt["public_upload_root_relation"],
                             {"native_host_evidence": "disjoint",
                              "staging_repository": "disjoint"})
            self.assertEqual(receipt["public_upload_roots"],
                             {"native_host_evidence": str(artifact.resolve()),
                              "staging_repository": str((root / "workspace" / "build" /
                                                         "staging-repository").resolve())})
            self.assertEqual(len(launched), 1)
            self.assertFalse(launched[0].exists())
            process.terminate.assert_called_once()
            process.communicate.assert_called_once_with(timeout=3)

    def test_task_owned_image_control_applies_swap_and_rejects_stale_pid(self):
        source_sha = "a" * 40
        image = self.windows_pe_fixture()
        image_sha = hashlib.sha256(image).hexdigest()
        ready_line = b"DYN4K_IMAGE_CONTROL_READY\t" + source_sha.encode() + b"\r\n"
        process = SimpleNamespace(pid=17, poll=mock.Mock(return_value=None),
                                  stdout=io.BytesIO(ready_line),
                                  terminate=mock.Mock(),
                                  communicate=mock.Mock(return_value=(b"", b"")), returncode=1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "build" / "dyn4k-performance-portable.exe"
            source.parent.mkdir()
            source.write_bytes(image)
            artifact = root / "runner" / "performance-native-host-short"
            output = artifact / "setup" / "path-swap.json"
            private_home = root / "private-home"
            private_home.mkdir()
            observed = []
            def observe(pid, selected):
                observed.append((pid, selected))
                if len(observed) == 3:
                    raise OSError("stale PID")
                return {"identity_kind": "mapped_executable_code",
                        "method": "ReadProcessMemory_main_PE_code", "sha256": image_sha,
                        "mapped_code_sha256": "b" * 64, "matched_code_bytes": 8192,
                        "path": str(private_home / "diagnostic"), "path_error": None}
            def launch(command, **kwargs):
                self.assertEqual(command[1:], ["--image-control-hold", source_sha])
                self.assertEqual(kwargs["stdin"], subprocess.PIPE)
                self.assertEqual(Path(command[0]).read_bytes(), image)
                self.assertFalse(Path(command[0]).is_relative_to(artifact))
                return process
            with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(root / "runner"),
                                              "GITHUB_WORKSPACE": str(root / "workspace")}), \
                    mock.patch.object(Path, "home", return_value=private_home), \
                    mock.patch.object(host_image_adverse.sys, "platform", "win32"), \
                    mock.patch.object(host_image_adverse.subprocess, "Popen", side_effect=launch), \
                    mock.patch.object(capture, "observed_process_image", side_effect=observe), \
                    mock.patch.object(sys, "argv", ["host_image_adverse.py", "--output", str(output),
                                                    "--control-image", str(source),
                                                    "--control-sha256", image_sha,
                                                    "--control-source-sha", source_sha]), \
                    redirect_stdout(io.StringIO()):
                host_image_adverse.main()
            receipt = json.loads(output.read_text())
            self.assertEqual(receipt["swap"], "applied")
            self.assertEqual(receipt["mapped_image_identity"], "matched_original")
            self.assertEqual(receipt["stale_pid"], "rejected")
            self.assertEqual(receipt["control_image_source"], str(source))
            self.assertEqual(receipt["original_sha256"], image_sha)
            self.assertEqual(receipt["control_ready"], "source_matched")
            self.assertEqual(receipt["control_ready_record"], {
                "bytes": len(ready_line), "sha256": hashlib.sha256(ready_line).hexdigest(),
                "hex": ready_line.hex(), "truncated": False})
            self.assertEqual(len(observed), 3)
            self.assertFalse(any(p.read_bytes() == image for p in artifact.rglob("*") if p.is_file()))
            process.terminate.assert_called_once()

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                         "real Linux ELF control needs cc")
    def test_task_owned_image_control_rejects_extra_stdout_from_real_child(self):
        source_sha = "a" * 40
        program = "\n".join((
            "#include <string.h>",
            "#include <unistd.h>",
            "int main(int argc, char **argv) {",
            '    if (argc != 3 || strcmp(argv[1], "--image-control-hold") ||',
            f'        strcmp(argv[2], "{source_sha}")) return 2;',
            f'    static const char output[] = "DYN4K_IMAGE_CONTROL_READY\\t{source_sha}\\nEXTRA\\n";',
            "    if (write(1, output, sizeof(output) - 1) != sizeof(output) - 1) return 3;",
            "    char input;",
            "    while (read(0, &input, 1) > 0) {}",
            "    return 0;",
            "}",
        ))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "dyn4k-performance-portable.kexe"
            subprocess.run(["cc", "-x", "c", "-", "-o", str(image)], input=program,
                           text=True, capture_output=True, check=True)
            output = root / "runner" / "performance-native-host-short" / "path-swap.json"
            environment = {**os.environ, "RUNNER_TEMP": str(root / "runner"),
                           "GITHUB_WORKSPACE": str(root / "workspace"),
                           "PYTHONDONTWRITEBYTECODE": "1"}
            completed = subprocess.run([
                sys.executable, "-B", str(Path(host_image_adverse.__file__).resolve()),
                "--output", str(output), "--control-image", str(image),
                "--control-sha256", hashlib.sha256(image.read_bytes()).hexdigest(),
                "--control-source-sha", source_sha,
            ], env=environment, capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            receipt = json.loads(output.read_text())
            self.assertEqual(receipt["control_ready"], "unexpected_output")
            self.assertEqual(receipt["control_stdout_tail"]["hex"], b"EXTRA\n".hex())
            self.assertEqual(receipt["mapped_image_identity"], "matched_original")
            self.assertEqual(receipt["swap"], "applied")
            self.assertEqual(receipt["stale_pid"], "rejected")

    def test_task_owned_image_control_rejects_wrong_inventory_hash_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "build" / "dyn4k-performance-portable.exe"
            source.parent.mkdir()
            source.write_bytes(self.windows_pe_fixture())
            output = root / "runner" / "performance-native-host-short" / "setup" / "path-swap.json"
            with mock.patch.object(host_image_adverse.sys, "platform", "win32"), \
                    mock.patch.object(host_image_adverse.subprocess, "Popen",
                                      side_effect=AssertionError("must not launch")), \
                    mock.patch.object(sys, "argv", ["host_image_adverse.py", "--output", str(output),
                                                    "--control-image", str(source),
                                                    "--control-sha256", "0" * 64,
                                                    "--control-source-sha", "a" * 40]), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as failure:
                    host_image_adverse.main()
            self.assertEqual(failure.exception.code, 1)
            receipt = json.loads(output.read_text())
            self.assertEqual(receipt["error_stage"], "validate_image_hash")
            self.assertEqual(receipt["mapped_image_identity"], "unobserved")
            self.assertFalse(any(p.read_bytes() == source.read_bytes()
                                 for p in output.parents[1].rglob("*") if p.is_file()))

    def test_task_owned_image_control_rejects_wrong_live_image_and_stale_pid(self):
        image = self.windows_pe_fixture()
        image_sha = hashlib.sha256(image).hexdigest()
        source_sha = "a" * 40
        for failure_kind in ("wrong_live_image", "stale_pid", "blocked_swap",
                             "wrong_ready_source", "malformed_ready", "overlong_ready",
                             "extra_ready_bytes", "extra_ready_output", "startup_error"):
            with self.subTest(failure_kind=failure_kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "build" / "dyn4k-performance-portable.exe"
                source.parent.mkdir()
                source.write_bytes(image)
                output = root / "runner" / "performance-native-host-short" / "setup" / "path-swap.json"
                home = root / "private-home"
                home.mkdir()
                ready_source = "0" * 40 if failure_kind == "wrong_ready_source" else source_sha
                ready_line = b"DYN4K_IMAGE_CONTROL_READY\t" + ready_source.encode() + b"\n"
                if failure_kind == "wrong_ready_source":
                    ready_line = ready_line[:-1] + b"\r\n"
                elif failure_kind == "malformed_ready":
                    ready_line = ready_line[:-1] + b"\r\r\n"
                elif failure_kind == "overlong_ready":
                    ready_line = b"DYN4K_IMAGE_CONTROL_READY\t" + b"x" * 200 + b"\n"
                elif failure_kind == "extra_ready_bytes":
                    ready_line = ready_line[:-1] + b" extra\n"
                elif failure_kind == "startup_error":
                    ready_line = b""
                process = SimpleNamespace(pid=17, poll=mock.Mock(return_value=(
                                              1 if failure_kind == "startup_error" else None)),
                                          stdout=io.BytesIO(ready_line),
                                          terminate=mock.Mock(),
                                          communicate=mock.Mock(return_value=(
                                              b"EXTRA\n" if failure_kind == "extra_ready_output" else b"",
                                              b"Native startup failed\n" if failure_kind ==
                                              "startup_error" else b"")),
                                          returncode=1)
                observations = 0
                def observe(pid, selected):
                    nonlocal observations
                    observations += 1
                    if observations == 3 and failure_kind != "stale_pid":
                        raise OSError("stale PID")
                    return {"identity_kind": "mapped_executable_code",
                            "method": "ReadProcessMemory_main_PE_code",
                            "sha256": ("0" * 64 if observations == 2 and
                                       failure_kind == "wrong_live_image" else image_sha),
                            "mapped_code_sha256": "b" * 64,
                            "matched_code_bytes": 8192, "path": None,
                            "path_error": "diagnostic path denied"}
                replace = (mock.patch.object(host_image_adverse.os, "replace",
                                             side_effect=PermissionError("sharing denied"))
                           if failure_kind == "blocked_swap" else mock.patch.object(
                               host_image_adverse.os, "replace", wraps=os.replace))
                with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(root / "runner"),
                                                  "GITHUB_WORKSPACE": str(root / "workspace")}), \
                        mock.patch.object(Path, "home", return_value=home), \
                        mock.patch.object(host_image_adverse.sys, "platform", "win32"), \
                        mock.patch.object(host_image_adverse.subprocess, "Popen", return_value=process), \
                        mock.patch.object(capture, "observed_process_image", side_effect=observe), \
                        replace, \
                        mock.patch.object(sys, "argv", ["host_image_adverse.py", "--output", str(output),
                                                        "--control-image", str(source),
                                                        "--control-sha256", image_sha,
                                                        "--control-source-sha", source_sha]), \
                        redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as failure:
                        host_image_adverse.main()
                self.assertEqual(failure.exception.code, 1)
                receipt = json.loads(output.read_text())
                if failure_kind == "wrong_live_image":
                    self.assertEqual(receipt["mapped_image_identity"], "mismatched")
                elif failure_kind == "stale_pid":
                    self.assertEqual(receipt["stale_pid"], "incorrectly_observed")
                elif failure_kind == "blocked_swap":
                    self.assertEqual(receipt["swap"], "blocked_by_os")
                elif failure_kind == "extra_ready_output":
                    self.assertEqual(receipt["control_ready"], "unexpected_output")
                    self.assertEqual(receipt["control_stdout_tail"]["hex"], b"EXTRA\n".hex())
                elif failure_kind == "startup_error":
                    self.assertEqual(receipt["error_stage"], "wait_control_ready")
                    self.assertEqual(receipt["control_ready_error"], "empty readiness")
                    self.assertEqual(receipt["pre_cleanup_exit_code"], 1)
                    self.assertEqual(receipt["control_stderr"]["hex"],
                                     b"Native startup failed\n".hex())
                else:
                    self.assertEqual(receipt["error_stage"], "wait_control_ready")
                    self.assertIn("control_ready_record", receipt)
                    self.assertIn("readiness", receipt["control_ready_error"])
                    self.assertEqual(receipt["control_ready_record"]["sha256"],
                                     hashlib.sha256(ready_line[:129]).hexdigest())
                    self.assertLessEqual(receipt["control_ready_record"]["bytes"], 129)
                if failure_kind != "startup_error":
                    self.assertIsNone(receipt["pre_cleanup_exit_code"])
                process.terminate.assert_called_once()

    @unittest.skipUnless(sys.platform.startswith("linux"), "bounded real child cleanup")
    def test_task_owned_image_control_times_out_without_ready_child(self):
        image = self.windows_pe_fixture()
        source_sha = "a" * 40
        launched = []
        original_popen = host_image_adverse.subprocess.Popen
        def launch(*_args, **_kwargs):
            child = original_popen(["/bin/sleep", "10"], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            launched.append(child)
            return child
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "build" / "dyn4k-performance-portable.exe"
            source.parent.mkdir()
            source.write_bytes(image)
            output = root / "runner" / "performance-native-host-short" / "setup" / "path-swap.json"
            home = root / "private-home"
            home.mkdir()
            started = time.monotonic()
            with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(root / "runner"),
                                              "GITHUB_WORKSPACE": str(root / "workspace")}), \
                    mock.patch.object(Path, "home", return_value=home), \
                    mock.patch.object(host_image_adverse.sys, "platform", "win32"), \
                    mock.patch.object(host_image_adverse.subprocess, "Popen", side_effect=launch), \
                    mock.patch.object(capture, "observed_process_image",
                                      side_effect=OSError("stale PID")), \
                    mock.patch.object(sys, "argv", ["host_image_adverse.py", "--output", str(output),
                                                    "--control-image", str(source),
                                                    "--control-sha256", hashlib.sha256(image).hexdigest(),
                                                    "--control-source-sha", source_sha]), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as failure:
                    host_image_adverse.main()
            self.assertEqual(failure.exception.code, 1)
            self.assertLess(time.monotonic() - started, 5)
            receipt = json.loads(output.read_text())
            self.assertEqual(receipt["error_stage"], "wait_control_ready")
            self.assertEqual(receipt["stale_pid"], "rejected")
            self.assertEqual(len(launched), 1)
            self.assertIsNotNone(launched[0].poll())

    def test_windows_path_swap_rejects_both_upload_roots_before_interrupted_copy(self):
        code = "\n".join((
            "import os, sys",
            "sys.path.insert(0, sys.argv[1])",
            "import host_image_adverse",
            "from pathlib import Path",
            "from unittest import mock",
            "host_image_adverse.sys.platform = 'win32'",
            "host_image_adverse.subprocess.Popen = lambda *a, **k: os._exit(77)",
            "with mock.patch.object(Path, 'home', return_value=Path(sys.argv[3])):",
            "    sys.argv = ['host_image_adverse.py', '--output', sys.argv[2],",
            "                '--control-image', sys.argv[4], '--control-sha256', sys.argv[5],",
            "                '--control-source-sha', 'a' * 40]",
            "    host_image_adverse.main()",
        ))
        cases = [("native_host_evidence", False), ("staging_repository", False)]
        if os.name == "posix":
            cases.append(("native_host_evidence", True))
        for selected_root, via_symlink in cases:
            with self.subTest(selected_root=selected_root, via_symlink=via_symlink), \
                    tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "build" / "dyn4k-performance-portable.exe"
                source.parent.mkdir(parents=True)
                image = b"MZ" + b"synthetic-control" * 200
                source.write_bytes(image)
                image_sha = hashlib.sha256(image).hexdigest()
                evidence = root / "runner" / "performance-native-host-short"
                staging = root / "workspace" / "build" / "staging-repository"
                evidence.mkdir(parents=True)
                staging.mkdir(parents=True)
                output = evidence / "setup" / "path-swap.json"
                roots = {"native_host_evidence": evidence, "staging_repository": staging}
                home = roots[selected_root]
                if via_symlink:
                    home = root / "home-link"
                    home.symlink_to(roots[selected_root], target_is_directory=True)
                environment = {**os.environ, "HOME": str(home),
                               "RUNNER_TEMP": str(root / "runner"),
                               "GITHUB_WORKSPACE": str(root / "workspace"),
                               "GITHUB_ACTIONS": "true"}
                run = subprocess.run([sys.executable, "-B", "-c", code,
                                      str(Path(__file__).parent), str(output), str(home),
                                      str(source), image_sha],
                                     env=environment, capture_output=True, timeout=10)
                self.assertEqual(run.returncode, 1, run.stderr.decode(errors="replace"))
                self.assertTrue(output.exists(), run.stderr.decode(errors="replace"))
                receipt = json.loads(output.read_text())
                self.assertEqual(receipt["error_stage"], "validate_private_directory")
                self.assertEqual(receipt["public_upload_root_relation"][selected_root], "overlap")
                self.assertEqual(receipt["mapped_image_identity"], "unobserved")
                self.assertEqual(receipt["swap"], "unavailable")
                self.assertFalse(any(p.read_bytes() == image for public in roots.values()
                                     for p in public.rglob("*") if p.is_file()))
                self.assertEqual(source.read_bytes(), image)

    def test_path_swap_home_failure_retains_structured_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "runner" / "performance-native-host-short" / "setup" / "path-swap.json"
            with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(root / "runner"),
                                              "GITHUB_WORKSPACE": str(root / "workspace")}), \
                    mock.patch.object(Path, "home", side_effect=RuntimeError("home unavailable")), \
                    mock.patch.object(sys, "argv", ["host_image_adverse.py", "--output", str(output)]), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as failure:
                    host_image_adverse.main()
            self.assertEqual(failure.exception.code, 1)
            receipt = json.loads(output.read_text())
            self.assertEqual(receipt["error_stage"], "select_private_directory")
            self.assertIn("home unavailable", receipt["error"])
            self.assertEqual(receipt["mapped_image_identity"], "unobserved")
            self.assertEqual(receipt["swap"], "unavailable")

    def test_path_swap_missing_hosted_upload_root_retains_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "runner" / "performance-native-host-short" / "setup" / "path-swap.json"
            with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(root / "runner"),
                                              "GITHUB_WORKSPACE": "", "GITHUB_ACTIONS": "true"}), \
                    mock.patch.object(sys, "argv", ["host_image_adverse.py", "--output", str(output)]), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as failure:
                    host_image_adverse.main()
            self.assertEqual(failure.exception.code, 1)
            receipt = json.loads(output.read_text())
            self.assertEqual(receipt["error_stage"], "resolve_public_upload_roots")
            self.assertEqual(receipt["mapped_image_identity"], "unobserved")
            self.assertEqual(receipt["swap"], "unavailable")
            self.assertFalse(any(p.suffix.lower() == ".exe" for p in root.rglob("*")))

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux mapped executable control")
    def test_path_swap_writes_receipt_when_diagnostic_path_is_absent(self):
        observer = capture.observed_process_image
        def without_path(pid, selected):
            image = observer(pid, selected)
            image["path"] = None
            image["path_error"] = "diagnostic path denied"
            return image
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "path-swap.json"
            with mock.patch.object(capture, "observed_process_image", side_effect=without_path), \
                    mock.patch.object(sys, "argv", ["host_image_adverse.py", "--output", str(output)]), \
                    redirect_stdout(io.StringIO()):
                host_image_adverse.main()
            result = json.loads(output.read_text())
        self.assertEqual(result["swap"], "applied")
        self.assertEqual(result["mapped_image_identity"], "matched_original")
        self.assertEqual(result["stale_pid"], "rejected")
        self.assertIsNone(result["reported_path_sha256_after"])
        self.assertEqual(result["path_error"], "diagnostic path denied")
        self.assertIsNone(result["after"]["path"])

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux mapped executable control")
    def test_path_swap_without_path_rejects_wrong_mapped_identity(self):
        observer = capture.observed_process_image
        def run_with_mutation(mutation):
            observed = 0
            def mutate_after(pid, selected):
                nonlocal observed
                image = observer(pid, selected)
                observed += 1
                image["path"] = None
                image["path_error"] = "diagnostic path denied"
                if observed == 2:
                    image.update(mutation)
                return image
            with mock.patch.object(capture, "observed_process_image", side_effect=mutate_after):
                return host_image_adverse.path_swap_control()
        cases = (
            {"sha256": "0" * 64},
            {"identity_kind": "mapped_executable_vnode", "method": "proc_pidinfo_region_vnode",
             "mapped_dev": 2, "selected_dev": 1, "mapped_ino": 3, "selected_ino": 3,
             "mapped_size": 4096},
            {"identity_kind": "mapped_executable_code", "method": "ReadProcessMemory_main_PE_code",
             "mapped_code_sha256": "0" * 64, "matched_code_bytes": 10},
        )
        for mutation in cases:
            with self.subTest(mutation=mutation):
                result = run_with_mutation(mutation)
                self.assertEqual(result["swap"], "applied")
                self.assertEqual(result["mapped_image_identity"], "mismatched")
                self.assertEqual(result["stale_pid"], "rejected")

    def test_rejects_nonfinite_and_negative_physical_diagnostics(self):
        payload = self.protocol()
        for replacement in (b"NaN", b"Infinity", b"-1.0"):
            with self.subTest(replacement=replacement), self.assertRaisesRegex(ValueError, "physical activity"):
                self.validate(payload.replace(b"75.0", replacement))

    def test_rejects_negative_or_unsampled_pair_counts(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "sampled pair"):
            self.validate(payload.replace(b"\t0\t0\t0\nDYN4K\tRUN",
                                          b"\t-99\t0\t0\nDYN4K\tRUN"))
        additional = payload.replace(
            b"DYN4K\tRUN", b"DYN4K\tCLOCK\tmeasure\t1\t11\t13\n"
            b"DYN4K\tSTEP\t1\t2\t1\t0\t100\t0\t100\t75.0\t0.0\t0\t0\t0\t0\t0\t0\n"
            b"DYN4K\tCLOCK\tmeasure\t2\t14\t16\n"
            b"DYN4K\tSTEP\t2\t2\t1\t0\t100\t0\t100\t75.0\t0.0\t0\t0\t0\t0\t0\t0\nDYN4K\tRUN")
        additional = additional.replace(b"\ttiming\t1\t1\t10\t1", b"\ttiming\t3\t1\t18\t3")
        with self.assertRaisesRegex(ValueError, "unsampled pair"):
            capture.validate_protocol(additional, self.scenario, self.source, self.producer_tree, self.hashes,
                                      "development", self.nonce, 3, 1, "timing")

    def test_rejects_cross_phase_clock_reversal_and_clock_after_step(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "measure clock"):
            self.validate(payload.replace(b"\tmeasure\t0\t4\t10", b"\tmeasure\t0\t1\t7")
                          .replace(b"STEP\t0\t6", b"STEP\t0\t6"))
        clock = b"DYN4K\tCLOCK\tmeasure\t0\t4\t10\n"
        activity = b"DYN4K\tSTEP\t0\t6\t2\t0\t100\t0\t100\t75.0\t0.0\t0\t0\t0\t0\t0\t0\n"
        with self.assertRaisesRegex(ValueError, "expected CLOCK"):
            self.validate(payload.replace(clock + activity, activity + clock))

    def test_rejects_missing_family_joints_and_extra_bodies(self):
        joint = dict(self.scenario, id="joint.angle_free.small.30hz.direct_kotlin",
                     family="joint", variant="angle_free", dynamic_bodies=50)
        payload = self.protocol().replace(self.scenario["id"].encode(), joint["id"].encode())
        payload = payload.replace(b"CONSTRUCTION\t100\t0", b"CONSTRUCTION\t100\t0")
        with self.assertRaisesRegex(ValueError, "construction"):
            capture.validate_protocol(payload, joint, self.source, self.producer_tree, self.hashes,
                                      "development", self.nonce, 1, 1, "timing")
        payload = payload.replace(b"CONSTRUCTION\t100\t0", b"CONSTRUCTION\t100\t50")
        payload = payload.replace(b"STEP\t0\t6\t2\t0\t100\t0\t100",
                                  b"STEP\t0\t6\t2\t0\t100\t0\t50")
        with self.assertRaisesRegex(ValueError, "fixture activity"):
            capture.validate_protocol(payload, joint, self.source, self.producer_tree, self.hashes,
                                      "development", self.nonce, 1, 1, "timing")
        with self.assertRaisesRegex(ValueError, "fixture activity"):
            self.validate(self.protocol().replace(b"\t100\t0\t100\t75.0",
                                                 b"\t101\t0\t100\t75.0"))

    def test_rejects_missing_calibration_link_and_completion(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "resolution calibration"):
            self.validate(payload.replace(b"RESOLUTION\t1\t64", b"RESOLUTION\t0\t64"))
        with self.assertRaisesRegex(ValueError, "linked producer identity"):
            self.validate(payload.replace(b"LINK\t" + self.source.encode(),
                                          b"LINK\t" + b"f" * 40))
        with self.assertRaisesRegex(ValueError, "COMPLETE"):
            self.validate(payload.replace(b"DYN4K\tCOMPLETE\t" + self.nonce.encode() + b"\n", b""))

    def test_build_inventory_binds_resolved_and_staged_bytes(self):
        source = subprocess.check_output(["git", "-C", str(capture.ROOT), "rev-parse", "HEAD"],
                                         text=True).strip()
        tracked = subprocess.check_output(
            ["git", "-C", str(capture.ROOT), "ls-tree", "-r", "--name-only", "HEAD",
             "consumers/performance/portable", "tools/performance/sustained_portable"],
            text=True).splitlines()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / name for name in ("entry.js", "core.klib", "kotlin.klib",
                                               "resolved-core.klib", "resolved-kotlin.klib")]
            for path, value in zip(paths, (b"entry", b"core", b"kotlin", b"core", b"kotlin")):
                path.write_bytes(value)
            harness, core, kotlin, resolved_core, resolved_kotlin = paths
            bundle = {harness.name: capture.digest(harness)}
            inventory = {
                "format": "portable-build-inventory-v1", "target": "js",
                "build": "development", "source_sha": source,
                "producer_tree": capture.source_tree(), "gradle": "9.5.0", "kgp": "2.4.20",
                "manifest_sha256": capture.digest(capture.MANIFEST),
                "harness": str(harness), "bundle_sha256": bundle,
                "source_files": {name: capture.digest(capture.ROOT / name) for name in tracked},
                "resolved_artifacts": [
                    {"module": "example:dyn4k-core-js:1", "path": str(resolved_core),
                     "sha256": capture.digest(resolved_core)},
                    {"module": "example:dyn4k-js:1", "path": str(resolved_kotlin),
                     "sha256": capture.digest(resolved_kotlin)},
                ],
            }
            receipt = root / "inventory.json"
            receipt.write_text(json.dumps(inventory))
            capture.validate_inventory(receipt, "js", "development", source,
                                       capture.source_tree(), capture.MANIFEST, harness,
                                       core, kotlin, bundle)
            bad_bundle = {harness.name: "0" * 64}
            with self.assertRaisesRegex(ValueError, "source, build, or bundle"):
                capture.validate_inventory(receipt, "js", "development", source,
                                           capture.source_tree(), capture.MANIFEST, harness,
                                           core, kotlin, bad_bundle)
            inventory.update(target="linuxX64", compile_configuration="linuxX64CompileKlibraries",
                             compiler_mode="debug", link_task="linkDebugExecutableLinuxX64")
            inventory["resolved_artifacts"][1]["module"] = capture.native_module("dyn4k", "linuxX64")
            for module in ("example:dyn4k-core-linuxx64:1",
                           capture.native_module("dyn4k-core", "linuxArm64"),
                           "io.github.rubixhacker:dyn4k-core-linuxx64:wrong"):
                inventory["resolved_artifacts"][0]["module"] = module
                receipt.write_text(json.dumps(inventory))
                with self.subTest(module=module), self.assertRaisesRegex(ValueError, "coordinates"):
                    capture.validate_inventory(receipt, "linuxX64", "development", source,
                                               capture.source_tree(), capture.MANIFEST, harness,
                                               core, kotlin, bundle, root)
            inventory["resolved_artifacts"][0]["module"] = capture.native_module("dyn4k-core", "linuxArm64")
            inventory["resolved_artifacts"][1]["module"] = capture.native_module("dyn4k", "linuxArm64")
            receipt.write_text(json.dumps(inventory))
            with self.assertRaisesRegex(ValueError, "coordinates"):
                capture.validate_inventory(receipt, "linuxX64", "development", source,
                                           capture.source_tree(), capture.MANIFEST, harness,
                                           core, kotlin, bundle, root)
            inventory["resolved_artifacts"][0]["module"] = capture.native_module("dyn4k-core", "linuxX64")
            inventory["resolved_artifacts"][1]["module"] = capture.native_module("dyn4k", "linuxX64")
            receipt.write_text(json.dumps(inventory))
            with self.assertRaisesRegex(ValueError, "not a KLIB"):
                capture.validate_inventory(receipt, "linuxX64", "development", source,
                                           capture.source_tree(), capture.MANIFEST, harness,
                                           core, kotlin, bundle, root)
            inventory.update(target="js", compiler_mode="debug")
            inventory["resolved_artifacts"][0]["module"] = "example:dyn4k-core-js:1"
            inventory["resolved_artifacts"][1]["module"] = "example:dyn4k-js:1"
            receipt.write_text(json.dumps(inventory))
            core.write_bytes(b"substituted")
            with self.assertRaisesRegex(ValueError, "Gradle-resolved build input"):
                capture.validate_inventory(receipt, "js", "development", source,
                                           capture.source_tree(), capture.MANIFEST, harness,
                                           core, kotlin, bundle)
            with self.assertRaisesRegex(ValueError, "source, build, or bundle"):
                capture.validate_inventory(receipt, "js", "development", "f" * 40,
                                           capture.source_tree(), capture.MANIFEST, harness,
                                           core, kotlin, bundle)


if __name__ == "__main__":
    unittest.main()
