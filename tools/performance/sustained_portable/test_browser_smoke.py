import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import urlopen

import browser_smoke
import browser_process


WASM_FILES = (
    "custom-formatters.js",
    "dyn4k-performance-portable.import-object.mjs",
    "dyn4k-performance-portable.js-builtins.mjs",
    "dyn4k-performance-portable.mjs",
    "dyn4k-performance-portable.wasm",
)
JS_FILES = (
    "kotlin-kotlin-stdlib.js",
    "kotlin_org_jetbrains_kotlin_kotlin_dom_api_compat.js",
    "dyn4k-dyn4k-core.js",
    "dyn4k-dyn4k.js",
    "dyn4k-performance-portable.js",
)


class BrowserResourceBindingTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name in WASM_FILES:
            (self.root / name).write_bytes(("original:" + name).encode())
        self.bundle = {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                       for name in WASM_FILES}

    def serve(self, handler=browser_smoke.Handler, target="wasmJs"):
        server = browser_smoke.browser_server(self.root, b"<html></html>", self.bundle,
                                              target, handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def get(self, server, name):
        with urlopen(f"http://127.0.0.1:{server.server_port}/{name}", timeout=2) as response:
            return response.read()

    def archive_control(self, name, server, requested, status, response):
        destination = os.environ.get("DYN4K_BROWSER_CONTROL_ARCHIVE")
        if not destination:
            return
        root = Path(destination)
        if not root.is_absolute():
            raise ValueError("control archive must be absolute")
        archive = root / name
        archive.mkdir(parents=True, exist_ok=False)
        (archive / "response.raw").write_bytes(response)
        selected = self.root / requested
        resource = selected.read_bytes() if selected.is_file() else b""
        (archive / "resource.raw").write_bytes(resource)
        with server.resource_lock:
            responses = list(server.resource_responses)
            errors = list(server.resource_errors)
        source = subprocess.check_output(
            ["git", "-C", str(browser_smoke.capture.ROOT), "rev-parse", "HEAD"],
            text=True).strip()
        record = {
            "source_sha": source, "case": name, "requested": requested,
            "http_status": status, "frozen_bundle_sha256": self.bundle,
            "resource_responses": responses, "resource_errors": errors,
            "response_sha256": hashlib.sha256(response).hexdigest(),
            "response_bytes": len(response),
            "resource_sha256": hashlib.sha256(resource).hexdigest(),
            "resource_bytes": len(resource), "qualification": "rejected_control",
        }
        (archive / "control.json").write_text(json.dumps(record, indent=2) + "\n")

    def test_omitted_wasm_dependency_changed_after_inventory_is_rejected(self):
        server = self.serve()
        name = "dyn4k-performance-portable.import-object.mjs"
        (self.root / name).write_bytes(b"substituted import")
        with self.assertRaises(HTTPError) as error:
            self.get(server, name)
        self.assertEqual(error.exception.code, 409)
        self.archive_control("omitted-wasm-import-changed", server, name, 409,
                             error.exception.read())
        error.exception.close()
        with self.assertRaisesRegex(ValueError, "resource"):
            browser_smoke.validate_loaded_resources(server)

    def test_change_between_lookup_and_read_is_rejected(self):
        class SwapBeforeRead(browser_smoke.Handler):
            def read_resource(self, selected):
                selected.write_bytes(b"changed after lookup")
                return super().read_resource(selected)

        server = self.serve(SwapBeforeRead)
        with self.assertRaises(HTTPError) as error:
            self.get(server, "dyn4k-performance-portable.import-object.mjs")
        self.assertEqual(error.exception.code, 409)
        self.archive_control("lookup-to-read-swap", server,
                             "dyn4k-performance-portable.import-object.mjs", 409,
                             error.exception.read())
        error.exception.close()
        with self.assertRaisesRegex(ValueError, "resource"):
            browser_smoke.validate_loaded_resources(server)

    def test_change_after_read_cannot_change_response_or_receipt(self):
        class SwapAfterRead(browser_smoke.Handler):
            def read_resource(self, selected):
                payload = super().read_resource(selected)
                selected.write_bytes(b"changed after read")
                return payload

        server = self.serve(SwapAfterRead)
        name = "dyn4k-performance-portable.import-object.mjs"
        response = self.get(server, name)
        self.assertEqual(hashlib.sha256(response).hexdigest(), self.bundle[name])
        self.assertNotEqual(hashlib.sha256((self.root / name).read_bytes()).hexdigest(),
                            self.bundle[name])
        self.assertEqual(server.served[name], self.bundle[name])

    def test_unknown_executable_and_missing_required_dependency_are_rejected(self):
        server = self.serve()
        (self.root / "injected.mjs").write_bytes(b"unexpected")
        with self.assertRaises(HTTPError) as error:
            self.get(server, "injected.mjs")
        self.assertEqual(error.exception.code, 404)
        self.archive_control("unknown-executable", server, "injected.mjs", 404,
                             error.exception.read())
        error.exception.close()
        with self.assertRaisesRegex(ValueError, "unknown resource"):
            browser_smoke.validate_loaded_resources(server)

        other = self.serve()
        for name in WASM_FILES[:-1]:
            self.get(other, name)
        with self.assertRaisesRegex(ValueError, "missing required"):
            browser_smoke.validate_loaded_resources(other)

    def test_dom_compatibility_script_is_required(self):
        for name in JS_FILES:
            (self.root / name).write_bytes(("original:" + name).encode())
        self.bundle = {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                       for name in JS_FILES}
        server = self.serve(target="js")
        for name in JS_FILES:
            if name != "kotlin_org_jetbrains_kotlin_kotlin_dom_api_compat.js":
                self.get(server, name)
        with self.assertRaisesRegex(ValueError, "kotlin_org_jetbrains_kotlin_kotlin_dom_api_compat.js"):
            browser_smoke.validate_loaded_resources(server)

    def test_wasm_custom_formatters_and_builtins_are_required(self):
        for omitted in ("custom-formatters.js", "dyn4k-performance-portable.js-builtins.mjs"):
            with self.subTest(omitted=omitted):
                server = self.serve()
                for name in WASM_FILES:
                    if name != omitted:
                        self.get(server, name)
                with self.assertRaisesRegex(ValueError, omitted.replace(".", "\\.")):
                    browser_smoke.validate_loaded_resources(server)

    def test_complete_http_fetch_records_the_sent_lengths(self):
        server = self.serve()
        for name in WASM_FILES:
            self.assertEqual(self.get(server, name), ("original:" + name).encode())
        browser_smoke.validate_loaded_resources(server)
        self.assertEqual(server.served_bytes,
                         {name: len(("original:" + name).encode()) for name in WASM_FILES})


class BrowserResourceRecordTest(unittest.TestCase):
    def server(self):
        bundle = {name: hashlib.sha256(name.encode()).hexdigest() for name in WASM_FILES}
        responses = [{"name": name, "sha256": digest, "bytes": len(name)}
                     for name, digest in bundle.items()]
        return SimpleNamespace(
            resource_lock=threading.Lock(), resource_errors=[],
            resource_responses=responses, served=dict(bundle),
            served_bytes={item["name"]: item["bytes"] for item in responses},
            expected_bundle=bundle, required_resources=frozenset(WASM_FILES),
        )

    def test_zero_bytes_are_rejected(self):
        server = self.server()
        for response in server.resource_responses:
            response["bytes"] = 0
        with self.assertRaisesRegex(ValueError, "bytes"):
            browser_smoke.validate_loaded_resources(server)

    def test_empty_served_map_is_rejected(self):
        server = self.server()
        server.served = {}
        with self.assertRaisesRegex(ValueError, "served"):
            browser_smoke.validate_loaded_resources(server)

    def test_missing_fields_raise_value_error(self):
        for field in ("bytes", "sha256", "name"):
            with self.subTest(field=field):
                server = self.server()
                del server.resource_responses[0][field]
                with self.assertRaisesRegex(ValueError, "record"):
                    browser_smoke.validate_loaded_resources(server)

    def test_record_schema_types_and_digest_shape_are_strict(self):
        invalid = (
            ("extra", "unexpected", "record"),
            ("bytes", True, "bytes"),
            ("bytes", -1, "bytes"),
            ("bytes", 1.5, "bytes"),
            ("name", 42, "name"),
            ("sha256", "not-a-digest", "sha256"),
            ("sha256", "A" * 64, "sha256"),
        )
        for field, value, message in invalid:
            with self.subTest(field=field, value=value):
                server = self.server()
                server.resource_responses[0][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    browser_smoke.validate_loaded_resources(server)
        server = self.server()
        server.resource_responses[0] = None
        with self.assertRaisesRegex(ValueError, "record"):
            browser_smoke.validate_loaded_resources(server)

    def test_duplicate_fetch_must_keep_digest_and_length(self):
        server = self.server()
        first = server.resource_responses[0]
        server.resource_responses.append(dict(first))
        browser_smoke.validate_loaded_resources(server)
        for field, value in (("sha256", "0" * 64), ("bytes", first["bytes"] + 1)):
            with self.subTest(field=field):
                server.resource_responses[-1][field] = value
                with self.assertRaises(ValueError):
                    browser_smoke.validate_loaded_resources(server)
                server.resource_responses[-1][field] = first[field]

    def test_served_map_must_match_all_response_records(self):
        server = self.server()
        server.served[next(iter(server.served))] = "0" * 64
        with self.assertRaisesRegex(ValueError, "served"):
            browser_smoke.validate_loaded_resources(server)
        server = self.server()
        server.served["unknown.mjs"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "served"):
            browser_smoke.validate_loaded_resources(server)

    def test_positive_byte_claim_must_match_sent_length_map(self):
        server = self.server()
        server.resource_responses[0]["bytes"] -= 1
        with self.assertRaisesRegex(ValueError, "served bytes"):
            browser_smoke.validate_loaded_resources(server)
        server = self.server()
        server.served_bytes = {}
        with self.assertRaisesRegex(ValueError, "served bytes"):
            browser_smoke.validate_loaded_resources(server)

    def test_served_byte_map_rejects_equal_noninteger_values_and_nonplain_keys(self):
        class StringName(str):
            pass

        for change in ("float", "bool", "zero", "negative", "string_subclass",
                       "dict_subclass", "extra_key"):
            with self.subTest(change=change):
                server = self.server()
                name = next(iter(server.served_bytes))
                if change == "float":
                    server.served_bytes[name] = float(server.served_bytes[name])
                elif change == "bool":
                    server.resource_responses[0]["bytes"] = 1
                    server.served_bytes[name] = True
                elif change == "zero":
                    server.served_bytes[name] = 0
                elif change == "negative":
                    server.served_bytes[name] = -1
                elif change == "string_subclass":
                    server.served_bytes[StringName(name)] = server.served_bytes.pop(name)
                elif change == "dict_subclass":
                    server.served_bytes = type("ForgedMap", (dict,), {})(server.served_bytes)
                else:
                    server.served_bytes["unknown.mjs"] = 1
                with self.assertRaisesRegex(ValueError, "served bytes"):
                    browser_smoke.validate_loaded_resources(server)


class BrowserRunFailureReceiptTest(unittest.TestCase):
    def test_missing_internal_map_retains_raw_and_structured_receipt(self):
        class FinishedProcess:
            pid = 1
            returncode = 0

            def poll(self):
                return 0

            def communicate(self, timeout):
                return b"", b""

        for missing in ("served_bytes", "served", "process"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                bundle_dir = root / "bundle"
                bundle_dir.mkdir()
                for name in JS_FILES:
                    (bundle_dir / name).write_bytes(name.encode())
                core = root / "core.bin"
                kotlin = root / "kotlin.bin"
                inventory = root / "inventory.json"
                browser = root / "files/extra/chrome"
                browser.parent.mkdir(parents=True)
                for path in (core, kotlin, browser):
                    path.write_bytes(b"fixture")
                inventory.write_text("{}")
                source = "a" * 40
                raw = b"DYN4K\tCOMPLETE\tretained raw\n"
                archive = root / "capture"
                args = SimpleNamespace(
                    archive=archive, target="js",
                    scenario="pile.default.small.30hz.direct_kotlin",
                    source_sha=source, steps=1, warmup=0,
                    harness=str(bundle_dir / "dyn4k-performance-portable.js"),
                    core=str(core), kotlin=str(kotlin), inventory=str(inventory),
                )

                def check_output(command, text):
                    if command[0] == "git" and "rev-parse" in command:
                        return source + "\n"
                    if command[0] == "git" and "status" in command:
                        return ""
                    if command[:3] == ["flatpak", "info", "--show-commit"]:
                        return "fixture-commit"
                    if command[:3] == ["flatpak", "info", "--show-location"]:
                        return str(root)
                    raise AssertionError(command)

                original_factory = browser_smoke.browser_server

                def faulty_server(*factory_args):
                    server = original_factory(*factory_args)
                    server.received = {"kind": "complete", "payload": raw}
                    server.completed.set()
                    if missing == "process":
                        for name, digest in server.expected_bundle.items():
                            size = (bundle_dir / name).stat().st_size
                            server.served[name] = digest
                            server.served_bytes[name] = size
                            server.resource_responses.append(
                                {"name": name, "sha256": digest, "bytes": size})
                    else:
                        delattr(server, missing)
                    return server

                class Observer:
                    def __init__(self, *args):
                        pass

                    def sample(self):
                        pass

                    def finish(self, *args):
                        if missing == "process":
                            raise ValueError("browser process image was not uniquely observed")
                        return {"pid": 1}

                with mock.patch.object(browser_smoke.subprocess, "check_output",
                                       side_effect=check_output), \
                     mock.patch.object(browser_smoke.subprocess, "Popen",
                                       return_value=FinishedProcess()), \
                     mock.patch.object(browser_smoke.capture, "source_tree",
                                       return_value="fixture-tree"), \
                     mock.patch.object(browser_smoke.capture, "validate_inventory",
                                       return_value={"gradle": "9.5.0", "kgp": "2.4.20",
                                                     "compile_configuration": "development"}), \
                     mock.patch.object(browser_smoke, "browser_server",
                                       side_effect=faulty_server), \
                     mock.patch.object(browser_smoke, "ChromeObserver", Observer):
                    expected = ("not uniquely observed" if missing == "process"
                                else "resource state is incomplete")
                    with self.assertRaisesRegex(ValueError, expected):
                        browser_smoke.run(args)

                self.assertEqual((archive / "producer.raw").read_bytes(), raw)
                self.assertEqual((archive / "completion.raw").read_bytes(), raw)
                receipt = json.loads((archive / "capture.json").read_text())
                self.assertEqual(receipt["qualification"], "unpassed")
                self.assertEqual(receipt["source_sha"], source)
                self.assertEqual(receipt["producer_sha256"], hashlib.sha256(raw).hexdigest())
                if missing == "process":
                    self.assertIn("not uniquely observed", receipt["process_validation_error"])
                    self.assertIsNone(receipt["browser_process_image"])
                else:
                    self.assertIn("resource state is incomplete",
                                  receipt["resource_validation_error"])
                    self.assertNotIn("loaded_resource_bytes", receipt)


class BrowserProcessObservationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.proc = self.root / "proc"
        self.proc.mkdir()
        self.selected = self.root / "selected/chrome"
        self.selected.parent.mkdir()
        self.selected.write_bytes(b"selected image")
        self.profile = self.root / "profile"
        self.page_url = "http://127.0.0.1:12345/"
        self.write_process(100, 1, 10000)
        self.write_process(101, 100, 10001)
        self.write_process(102, 101, 10002, chrome=True)

    def write_process(self, pid, ppid, start_ticks, chrome=False, url=None):
        directory = self.proc / str(pid)
        directory.mkdir(exist_ok=True)
        fields = ["S", str(ppid), str(pid), "100"] + ["0"] * 15 + [str(start_ticks)]
        (directory / "stat").write_text(f"{pid} (chrome) " + " ".join(fields) + "\n")
        if chrome:
            arguments = [str(self.selected), "--headless",
                         f"--user-data-dir={self.profile}", url or self.page_url]
            (directory / "cmdline").write_bytes(
                b"\0".join(os.fsencode(arg) for arg in arguments) + b"\0")
            if not (directory / "exe").exists():
                (directory / "exe").symlink_to(self.selected)
        else:
            (directory / "cmdline").unlink(missing_ok=True)
            (directory / "exe").unlink(missing_ok=True)

    def observer(self):
        digest = hashlib.sha256(self.selected.read_bytes()).hexdigest()
        return browser_process.ChromeObserver(
            100, self.profile, self.page_url, self.selected, digest,
            10001 * browser_process.TICK_NS, proc_root=self.proc)

    def test_profile_tree_mapped_image_and_exchange_are_bound(self):
        observer = self.observer()
        observer.sample()
        page = 10003 * browser_process.TICK_NS
        record = observer.finish(page, page + 1, page + 2, page + 3,
                                 "nonce")
        self.assertEqual(record["pid"], 102)
        self.assertEqual([item["pid"] for item in record["ancestry"]], [101, 100])
        self.assertEqual(record["mapped_image"]["sha256"], observer.selected_sha256)
        self.assertIn(f"--user-data-dir={self.profile}", record["argv"])
        self.assertEqual(record["page_url"], self.page_url)

    def test_live_running_to_sleeping_transition_keeps_process_identity(self):
        original = browser_process.process_stat
        reads = 0

        def changing_state(root, pid):
            nonlocal reads
            result = original(root, pid)
            if pid == 102:
                reads += 1
                result["state"] = "R" if reads == 1 else "S"
            return result

        observer = self.observer()
        with mock.patch.object(browser_process, "process_stat", side_effect=changing_state):
            observer.sample()
        self.assertEqual(next(iter(observer.observed.values()))["pid"], 102)

    def test_missing_ambiguous_mismatched_and_raced_processes_reject(self):
        self.write_process(102, 101, 10002)
        observer = self.observer()
        with self.assertRaisesRegex(ValueError, "not uniquely observed"):
            observer.finish(1, 2, 3, 4, "nonce")

        self.write_process(102, 101, 10002, chrome=True)
        self.write_process(103, 101, 10003, chrome=True)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.observer().sample()
        for path in (self.proc / "103").iterdir():
            path.unlink()
        (self.proc / "103").rmdir()

        self.write_process(102, 101, 10002, chrome=True,
                           url="http://127.0.0.1:99999/")
        with self.assertRaisesRegex(ValueError, "profile or page"):
            self.observer().sample()

        self.write_process(102, 101, 10002, chrome=True)
        observer = self.observer()
        observer.sample()
        self.write_process(102, 101, 10004, chrome=True)
        with self.assertRaises(ValueError):
            observer.finish(1, 2, 3, 4, "nonce")

    def test_live_selected_path_swap_rejects_mapped_image(self):
        selected = self.root / "live/chrome"
        selected.parent.mkdir()
        shutil.copy2("/usr/bin/sleep", selected)
        expected = hashlib.sha256(selected.read_bytes()).hexdigest()
        process = subprocess.Popen([str(selected), "5"], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        try:
            observed = browser_process.verify_mapped_image(
                Path("/proc"), process.pid, selected, expected)
            self.assertEqual(observed["sha256"], expected)
            replacement = self.root / "replacement"
            replacement.write_bytes(b"replaced selected pathname")
            replacement.replace(selected)
            with self.assertRaisesRegex(ValueError, "differs from selected"):
                browser_process.verify_mapped_image(Path("/proc"), process.pid,
                                                    selected, expected)
        finally:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
