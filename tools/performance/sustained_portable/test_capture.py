import copy
import ctypes
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

import capture
import native_host_capture
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
        region = {"protection": 5, "offset": 0, "dev": 7, "ino": 11, "size": 4096}
        self.assertEqual(host_image.select_macos_region([region], selected), region)
        for changed in ({**region, "ino": 12}, {**region, "protection": 1},
                        {**region, "offset": 4096}):
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
        with self.assertRaisesRegex(ValueError, "mapped PE header differs"):
            host_image.compare_pe_code(image, layout,
                lambda address, size: (b"z" * size if address == base else read(address, size)), base)

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
            entries = {str(path.relative_to(source_root)).replace("/kotlin/", "/"): path
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
            with zipfile.ZipFile(sources, "w") as archive:
                for entry, path in entries.items():
                    archive.writestr(entry, b"substituted" if entry == name else path.read_bytes())
            sources.with_name(sources.name + ".sha256").write_text(capture.digest(sources))
            document["variants"][1]["files"][0]["sha256"] = capture.digest(sources)
            metadata.write_text(json.dumps(document))
            metadata.with_name(metadata.name + ".sha256").write_text(capture.digest(metadata))
            with self.assertRaisesRegex(ValueError, "source bytes"):
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
