#!/usr/bin/env python3

import argparse
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import threading
import time
from urllib.parse import unquote, urlsplit

import capture


class Handler(SimpleHTTPRequestHandler):
    page = b""
    directory_path = Path(".")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.directory_path), **kwargs)

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(self.page)))
            self.end_headers()
            self.wfile.write(self.page)
        else:
            name = unquote(urlsplit(self.path).path).lstrip("/")
            selected = (self.directory_path / name).resolve()
            if selected.is_file() and selected.is_relative_to(self.directory_path.resolve()):
                self.server.served[name] = capture.digest(selected)
            super().do_GET()

    def do_POST(self):
        if self.path not in ("/complete", "/error"):
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        if size < 1 or size > 4_000_000:
            self.send_error(413)
            return
        payload = self.rfile.read(size)
        if not self.server.completed.is_set():
            self.server.received = {"kind": self.path[1:], "payload": payload}
            self.server.completed.set()
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def browser_page(target, args):
    arguments = json.dumps(args).replace("</", "<\\/")
    setup = (
        "<script>globalThis.DYN4K_ARGS=" + arguments + ";"
        "const records=[];const nativeLog=console.log.bind(console);"
        "console.log=(...parts)=>{const value=parts.join(' ');"
        "if(value.startsWith('DYN4K\\t')){records.push(value);"
        "if(value.startsWith('DYN4K\\tCOMPLETE\\t'))"
        "fetch('/complete',{method:'POST',body:records.join('\\n')+'\\n'});}"
        "nativeLog(...parts)};"
        "window.addEventListener('error',e=>{"
        "fetch('/error',{method:'POST',body:e.message||'browser error'})});"
        "window.addEventListener('unhandledrejection',e=>{"
        "fetch('/error',{method:'POST',body:String(e.reason)})});"
        "</script>"
    )
    if target == "js":
        scripts = "".join(
            f'<script src="/{name}"></script>'
            for name in ("kotlin-kotlin-stdlib.js",
                         "kotlin_org_jetbrains_kotlin_kotlin_dom_api_compat.js",
                         "dyn4k-dyn4k-core.js", "dyn4k-dyn4k.js",
                         "dyn4k-performance-portable.js")
        )
    else:
        scripts = '<script type="module" src="/dyn4k-performance-portable.mjs"></script>'
    return ("<!doctype html><html><body>" + setup + scripts + "</body></html>").encode()


def run(args):
    if args.archive.exists() or not args.archive.is_absolute():
        raise ValueError("archive must be a new absolute path")
    if args.target not in ("js", "wasmJs"):
        raise ValueError("browser target must be js or wasmJs")
    if args.steps < 1 or args.warmup < 0:
        raise ValueError("invalid step count")
    manifest = json.loads(capture.MANIFEST.read_text())
    scenario = capture.scenario_from_manifest(manifest, args.scenario)
    source = subprocess.check_output(
        ["git", "-C", str(capture.ROOT), "rev-parse", "HEAD"], text=True).strip()
    if args.source_sha != source:
        raise ValueError("source SHA does not match checkout")
    dirty = subprocess.check_output(
        ["git", "-C", str(capture.ROOT), "status", "--porcelain", "--untracked-files=all"],
        text=True)
    if dirty.strip():
        raise ValueError("source checkout is dirty; commit the producer before capture")
    harness = capture.required_file(args.harness, "harness")
    core = capture.required_file(args.core, "core")
    kotlin = capture.required_file(args.kotlin, "kotlin")
    if args.target == "js" and harness.suffix != ".js":
        raise ValueError("JS browser needs a JavaScript entry")
    if args.target == "wasmJs" and harness.suffix != ".mjs":
        raise ValueError("Wasm browser needs a module entry")
    bundle = capture.bundle_hashes(harness)
    if args.target == "wasmJs" and not any(name.endswith(".wasm") for name in bundle):
        raise ValueError("Wasm browser bundle has no Wasm binary")
    hashes = {"core": capture.digest(core), "kotlin": capture.digest(kotlin)}
    producer_tree = capture.source_tree()
    inventory_path = capture.required_file(args.inventory, "build inventory")
    inventory = capture.validate_inventory(inventory_path, args.target, "development", source,
                                           producer_tree, capture.MANIFEST, harness, core, kotlin,
                                           bundle)
    flatpak_commit = subprocess.check_output(
        ["flatpak", "info", "--show-commit", "com.google.Chrome"], text=True).strip()
    flatpak_location = Path(subprocess.check_output(
        ["flatpak", "info", "--show-location", "com.google.Chrome"], text=True).strip())
    browser_binary = capture.required_file(
        str(flatpak_location / "files/extra/chrome"), "browser binary")
    browser_sha = capture.digest(browser_binary)
    nonce = secrets.token_hex(16)
    producer_args = [
        scenario["id"], scenario["family"], scenario["variant"], scenario["size"],
        str(scenario["rate_hz"]), str(args.steps), str(args.warmup), "timing",
        scenario["api"], source, hashes["core"], hashes["kotlin"],
        "development", nonce,
    ]
    page = browser_page(args.target, producer_args)
    Handler.page = page
    Handler.directory_path = harness.parent
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.completed = threading.Event()
    server.received = None
    server.served = {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    args.archive.mkdir(parents=True)
    (args.archive / "page.html").write_bytes(page)
    (args.archive / "build-inventory.json").write_bytes(inventory_path.read_bytes())
    profile = args.archive / "chrome-profile"
    command = [
        "dbus-run-session", "--", "flatpak", "run", "com.google.Chrome",
        "--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
        "--no-first-run", "--disable-background-timer-throttling",
        f"--user-data-dir={profile}",
    ]
    command.append(f"http://127.0.0.1:{server.server_port}/")
    started = time.monotonic_ns()
    process = None
    completed = False
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        deadline = time.monotonic() + 45
        while not server.completed.wait(timeout=0.1):
            if process.poll() is not None or time.monotonic() >= deadline:
                break
        completed = server.completed.is_set()
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        if process is not None:
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate(timeout=5)
        else:
            stdout, stderr = b"", b""
        server.shutdown()
        server.server_close()
    ended = time.monotonic_ns()
    (args.archive / "stdout.raw").write_bytes(stdout)
    (args.archive / "stderr.raw").write_bytes(stderr)
    received = server.received
    raw = received["payload"] if received and received["kind"] == "complete" else b""
    (args.archive / "producer.raw").write_bytes(raw)
    (args.archive / "completion.raw").write_bytes(received["payload"] if received else b"")
    receipt = {
        "qualification": "unpassed", "target": args.target + "Browser",
        "scenario": scenario, "source_sha": source, "command": command,
        "producer_tree": producer_tree,
        "build_inventory_sha256": capture.digest(args.archive / "build-inventory.json"),
        "build_inventory": {"gradle": inventory["gradle"], "kgp": inventory["kgp"],
                            "compile_configuration": inventory["compile_configuration"]},
        "wrapper_exit_code": process.returncode if process is not None else None,
        "controller_terminated_after_receipt": bool(completed),
        "completion_kind": received["kind"] if received else "timeout",
        "started_monotonic_ns": started, "ended_monotonic_ns": ended,
        "page_sha256": hashlib.sha256(page).hexdigest(),
        "bundle_sha256": bundle, "core_sha256": hashes["core"],
        "kotlin_sha256": hashes["kotlin"],
        "flatpak_commit": flatpak_commit,
        "browser_binary_path": str(browser_binary),
        "browser_binary_sha256": browser_sha,
        "stdout_sha256": capture.digest(args.archive / "stdout.raw"),
        "stdout_bytes": len(stdout),
        "producer_sha256": capture.digest(args.archive / "producer.raw"),
        "producer_bytes": len(raw),
        "completion_sha256": capture.digest(args.archive / "completion.raw"),
        "loaded_resources_sha256": server.served,
        "stderr_sha256": capture.digest(args.archive / "stderr.raw"),
        "stderr_bytes": len(stderr),
        "browser_process_image": "unobserved_through_flatpak_wrapper",
        "memory_attribution": "missing", "allocation": "missing", "plateau": "missing",
        "required_non_jvm_gates": {
            "absolute_p99_seconds": manifest["budgets"]["absolute_p99_seconds"][str(scenario["rate_hz"])],
            "shim_vs_direct": manifest["budgets"]["shim_vs_direct"],
            "java_baseline": "jvm_only",
        },
    }
    (args.archive / "capture.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if not completed:
        raise ValueError("browser completion timed out; raw archive retained")
    if received["kind"] == "error":
        raise ValueError(f"browser script error: {received['payload'][:200]!r}")
    needed = (["kotlin-kotlin-stdlib.js", "dyn4k-dyn4k-core.js",
               "dyn4k-dyn4k.js", "dyn4k-performance-portable.js"]
              if args.target == "js" else
              ["dyn4k-performance-portable.mjs", "dyn4k-performance-portable.wasm"])
    if any(server.served.get(name) != bundle.get(name) for name in needed):
        raise ValueError("browser did not load the selected provider bundle")
    try:
        capture.validate_protocol(
            raw, scenario, source, producer_tree, hashes, "development", nonce,
            args.steps, args.warmup, "timing")
    except ValueError as error:
        receipt["protocol_error"] = str(error)
        (args.archive / "capture.json").write_text(json.dumps(receipt, indent=2) + "\n")
        raise
    return receipt


def main():
    parser = argparse.ArgumentParser(description="Capture a short headless browser candidate process")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--target", choices=("js", "wasmJs"), required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--harness", required=True)
    parser.add_argument("--core", required=True)
    parser.add_argument("--kotlin", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--warmup", type=int, required=True)
    args = parser.parse_args()
    try:
        receipt = run(args)
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"qualification: unpassed; {error}\n")
    print(json.dumps({"qualification": "unpassed", "archive": str(args.archive),
                      "producer_bytes": receipt["producer_bytes"]}))


if __name__ == "__main__":
    main()
