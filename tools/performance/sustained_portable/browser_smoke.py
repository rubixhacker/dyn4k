#!/usr/bin/env python3

import argparse
import hashlib
import html
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time

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
            super().do_GET()

    def log_message(self, format, *args):
        pass


def browser_page(target, args):
    arguments = json.dumps(args).replace("</", "<\\/")
    setup = (
        "<script>globalThis.DYN4K_ARGS=" + arguments + ";"
        "const nativeLog=console.log.bind(console);"
        "console.log=(...parts)=>{const value=parts.join(' ');"
        "if(value.startsWith('DYN4K\\t'))"
        "document.getElementById('records').textContent+=value+'\\n';"
        "nativeLog(...parts)};"
        "window.addEventListener('error',e=>{"
        "document.getElementById('errors').textContent+=e.message+'\\n'});"
        "window.addEventListener('unhandledrejection',e=>{"
        "document.getElementById('errors').textContent+=String(e.reason)+'\\n'});"
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
    return ("<!doctype html><html><body><pre id=\"records\"></pre>"
            "<pre id=\"errors\"></pre>" + setup + scripts + "</body></html>").encode()


def pre_text(dom, identifier):
    match = re.search(r'<pre id="' + identifier + r'">([\s\S]*?)</pre>', dom)
    if match is None:
        raise ValueError(f"browser omitted {identifier} output")
    return html.unescape(match.group(1))


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
    bundle = {path.name: capture.digest(path)
              for path in harness.parent.iterdir() if path.is_file()}
    if args.target == "wasmJs" and not any(name.endswith(".wasm") for name in bundle):
        raise ValueError("Wasm browser bundle has no Wasm binary")
    hashes = {"core": capture.digest(core), "kotlin": capture.digest(kotlin)}
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
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    args.archive.mkdir(parents=True)
    (args.archive / "page.html").write_bytes(page)
    profile = args.archive / "chrome-profile"
    command = [
        "dbus-run-session", "--", "flatpak", "run", "com.google.Chrome",
        "--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
        "--no-first-run", "--dump-dom", f"--user-data-dir={profile}",
    ]
    if args.target == "js" or (args.target == "wasmJs" and args.steps == 1 and args.warmup == 0):
        command.append("--virtual-time-budget=5000")
    command.append(f"http://127.0.0.1:{server.server_port}/")
    started = time.monotonic_ns()
    try:
        try:
            process = subprocess.run(command, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired as error:
            (args.archive / "dom.raw").write_bytes(error.stdout or b"")
            (args.archive / "stderr.raw").write_bytes(error.stderr or b"")
            (args.archive / "capture.json").write_text(json.dumps({
                "qualification": "unpassed", "error": "browser_timeout",
                "command": command, "source_sha": source,
                "scenario": scenario, "bundle_sha256": bundle,
                "core_sha256": hashes["core"], "kotlin_sha256": hashes["kotlin"],
                "dom_bytes": len(error.stdout or b""),
                "stderr_bytes": len(error.stderr or b""),
                "flatpak_commit": flatpak_commit,
                "browser_binary_sha256": browser_sha,
            }, indent=2) + "\n")
            raise
    finally:
        server.shutdown()
        server.server_close()
    ended = time.monotonic_ns()
    (args.archive / "dom.raw").write_bytes(process.stdout)
    (args.archive / "stderr.raw").write_bytes(process.stderr)
    receipt = {
        "qualification": "unpassed", "target": args.target + "Browser",
        "scenario": scenario, "source_sha": source, "command": command,
        "wrapper_exit_code": process.returncode,
        "started_monotonic_ns": started, "ended_monotonic_ns": ended,
        "page_sha256": hashlib.sha256(page).hexdigest(),
        "bundle_sha256": bundle, "core_sha256": hashes["core"],
        "kotlin_sha256": hashes["kotlin"],
        "flatpak_commit": flatpak_commit,
        "browser_binary_path": str(browser_binary),
        "browser_binary_sha256": browser_sha,
        "dom_sha256": capture.digest(args.archive / "dom.raw"),
        "dom_bytes": len(process.stdout),
        "stderr_sha256": capture.digest(args.archive / "stderr.raw"),
        "stderr_bytes": len(process.stderr),
        "browser_process_image": "unavailable_through_flatpak_wrapper",
        "memory_attribution": "missing", "allocation": "missing", "plateau": "missing",
        "required_non_jvm_gates": {
            "absolute_p99_seconds": manifest["budgets"]["absolute_p99_seconds"][str(scenario["rate_hz"])],
            "shim_vs_direct": manifest["budgets"]["shim_vs_direct"],
            "java_baseline": "jvm_only",
        },
    }
    (args.archive / "capture.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if process.returncode != 0:
        raise ValueError(f"browser wrapper exited {process.returncode}; raw archive retained")
    dom = process.stdout.decode("utf-8")
    error_text = pre_text(dom, "errors")
    if error_text:
        raise ValueError(f"browser script error: {error_text[:200]}")
    raw = pre_text(dom, "records").encode()
    (args.archive / "producer.raw").write_bytes(raw)
    try:
        capture.validate_protocol(
            raw, scenario, source, hashes, "development", nonce,
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
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--warmup", type=int, required=True)
    args = parser.parse_args()
    try:
        receipt = run(args)
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"qualification: unpassed; {error}\n")
    print(json.dumps({"qualification": "unpassed", "archive": str(args.archive),
                      "dom_bytes": receipt["dom_bytes"]}))


if __name__ == "__main__":
    main()
