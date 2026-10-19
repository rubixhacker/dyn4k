import hashlib
import http.server
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path


OBSERVER = Path(__file__).with_name("independent_browser_observer.js")
CHROME = Path("/tmp/dyn4k-browser-wasi-tools/chrome-155/chrome-linux64/chrome")
BODY = {"runtime.js": b"globalThis.dyn4kRuntime = 1;",
        "commons.js": b"globalThis.dyn4kCommons = 2;"}


def free_port():
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


class ObserverTests(unittest.TestCase):
    def test_non_browser_pid_cannot_create_observation(self):
        if not CHROME.is_file() or not shutil.which("node"):
            self.skipTest("retained local Chromium or Node is absent")
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output = base / "observation.json"
            result = subprocess.run([
                "node", str(OBSERVER), "--browser", str(CHROME),
                "--cdp-port", "12345", "--karma-port", "23456", "--module", "core",
                "--output", str(output), "--pid", str(os.getpid()),
                "--ready-file", str(base / "ready"), "--stop-file", str(base / "stop"),
                "--target", "js", "--timeout-ms", "1000"],
                capture_output=True, text=True, timeout=10)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("live browser executable differs", result.stderr)
            self.assertFalse(output.exists())

    def test_live_chromium_process_and_body_capture(self):
        if not CHROME.is_file() or not shutil.which("node"):
            self.skipTest("retained local Chromium or Node is absent")
        received = {name: threading.Event() for name in BODY}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                name = self.path.rsplit("/", 1)[-1]
                if name in BODY:
                    data = BODY[name]
                    kind = "application/javascript"
                    received[name].set()
                else:
                    data = (b'<script src="/absolute/_karma_webpack_/runtime.js"></script>'
                            b'<script src="/absolute/_karma_webpack_/commons.js"></script>')
                    kind = "text/html"
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args):
                pass

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cdp_port = free_port()
            browser = subprocess.Popen([
                str(CHROME), "--headless=new", "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage", f"--remote-debugging-port={cdp_port}",
                f"--user-data-dir={base / 'profile'}", "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            observer = None
            try:
                for _ in range(200):
                    try:
                        urllib.request.urlopen(
                            f"http://127.0.0.1:{cdp_port}/json/version", timeout=0.3).close()
                        break
                    except OSError:
                        time.sleep(0.05)
                else:
                    self.fail("local Chromium CDP did not start")
                ready, stop, output = (base / name for name in
                                       ("ready.json", "stop", "observation.json"))
                observer = subprocess.Popen([
                    "node", str(OBSERVER), "--browser", str(CHROME),
                    "--cdp-port", str(cdp_port), "--karma-port", str(server.server_port),
                    "--module", "core", "--output", str(output), "--pid", str(browser.pid),
                    "--ready-file", str(ready), "--stop-file", str(stop),
                    "--target", "js", "--timeout-ms", "15000"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for _ in range(200):
                    if ready.is_file() or observer.poll() is not None:
                        break
                    time.sleep(0.05)
                if not ready.is_file():
                    self.fail(f"observer did not attach: {observer.communicate()[1]}")
                url = f"http://127.0.0.1:{server.server_port}/"
                navigate = (
                    "(async()=>{const p=process.argv[1],u=process.argv[2];"
                    "const t=await(await fetch('http://127.0.0.1:'+p+'/json/list')).json();"
                    "const x=t.find(v=>v.type==='page'&&v.url==='about:blank');"
                    "const w=new WebSocket(x.webSocketDebuggerUrl);"
                    "await new Promise(r=>w.onopen=r);"
                    "w.send(JSON.stringify({id:1,method:'Page.navigate',params:{url:u}}));"
                    "await new Promise(r=>setTimeout(r,300));w.close()})()")
                subprocess.run(["node", "-e", navigate, str(cdp_port), url],
                               check=True, timeout=10)
                for event in received.values():
                    self.assertTrue(event.wait(10), "test browser did not load JS body")
                time.sleep(0.4)
                stop.touch()
                _, error = observer.communicate(timeout=15)
                self.assertEqual(0, observer.returncode, error)
                observed = json.loads(output.read_text())
                self.assertEqual(browser.pid, observed["browser_pid"])
                self.assertEqual(hashlib.sha256(CHROME.read_bytes()).hexdigest(),
                                 observed["browser_sha256"])
                self.assertEqual("unix-epoch-ns", observed["clock"])
                self.assertEqual(2, len(observed["responses"]))
                for row in observed["responses"]:
                    name = row["url"].rsplit("/", 1)[-1]
                    self.assertEqual(hashlib.sha256(BODY[name]).hexdigest(),
                                     row["body_sha256"])
                    self.assertEqual(len(BODY[name]), row["size"])
                    self.assertLessEqual(observed["started_ns"], row["request_ns"])
                    self.assertLessEqual(row["request_ns"], row["response_ns"])
                    self.assertLessEqual(row["response_ns"], row["finished_ns"])
                    self.assertLessEqual(row["finished_ns"], observed["finished_ns"])
            finally:
                if observer is not None and observer.poll() is None:
                    observer.kill()
                    observer.wait()
                browser.terminate()
                try:
                    browser.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    browser.kill()
                    browser.wait()
                server.shutdown()
                server.server_close()
