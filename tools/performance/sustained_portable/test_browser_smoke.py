import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

import browser_smoke


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


if __name__ == "__main__":
    unittest.main()
