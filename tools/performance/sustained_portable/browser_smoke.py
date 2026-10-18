#!/usr/bin/env python3

import argparse
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import threading
import time
from urllib.parse import unquote, urlsplit

from browser_process import ChromeObserver, ClientOriginGuard, boottime_ns
import capture

JS_SCRIPTS = (
    "kotlin-kotlin-stdlib.js",
    "kotlin_org_jetbrains_kotlin_kotlin_dom_api_compat.js",
    "dyn4k-dyn4k-core.js", "dyn4k-dyn4k.js",
    "dyn4k-performance-portable.js",
)
WASM_EXECUTABLES = (
    "custom-formatters.js",
    "dyn4k-performance-portable.import-object.mjs",
    "dyn4k-performance-portable.js-builtins.mjs",
    "dyn4k-performance-portable.mjs",
    "dyn4k-performance-portable.wasm",
)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server, directory=str(server.directory_path))

    def setup(self):
        super().setup()
        self.connection.settimeout(5)
        self.connection_lease = None
        self.connection_origin_error = None
        self.origin_error_reported = False
        if not self.server.origin_required:
            return
        if not self.server.origin_ready.wait(timeout=2):
            self.connection_origin_error = "browser request origin guard was not ready"
            return
        try:
            if self.server.origin_guard is None:
                raise ValueError("browser request origin guard is missing")
            self.connection_lease = self.server.origin_guard.hold_socket(self.connection)
            self.connection_lease.verify()
        except (OSError, ValueError) as error:
            self.connection_origin_error = str(error)
            if self.connection_lease is not None:
                self.connection_lease.close()
                self.connection_lease = None

    def finish(self):
        try:
            super().finish()
        finally:
            if self.connection_lease is not None:
                self.connection_lease.close()

    def read_resource(self, selected):
        with selected.open("rb") as stream:
            return stream.read()

    def resource_error(self, message):
        with self.server.resource_lock:
            self.server.resource_errors.append(message)

    def prove_origin(self, send_error=True):
        if self.connection_origin_error is None:
            if not self.server.origin_required:
                return {}
            try:
                return self.connection_lease.verify()
            except (OSError, ValueError) as error:
                self.connection_origin_error = str(error)
        if not self.origin_error_reported:
            with self.server.resource_lock:
                self.server.origin_errors.append(self.connection_origin_error)
            self.origin_error_reported = True
        if send_error:
            self.send_error(403)
        return None

    def do_GET(self):
        if self.path == "/":
            origin = self.prove_origin()
            if origin is None:
                return
            page = self.server.page
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            with self.server.resource_lock:
                observed_ns = boottime_ns()
                if self.server.page_served_boottime_ns is None:
                    self.server.page_served_boottime_ns = observed_ns
                if self.server.origin_required:
                    self.server.request_origins.append({
                        "kind": "page", "name": "/", "sha256": hashlib.sha256(page).hexdigest(),
                        "bytes": len(page), "time_ns": observed_ns, "origin": origin})
        else:
            name = unquote(urlsplit(self.path).path).lstrip("/")
            if name not in self.server.expected_bundle:
                if name != "favicon.ico":
                    self.resource_error(f"unknown resource: {name}")
                self.send_error(404)
                return
            origin = self.prove_origin()
            if origin is None:
                return
            selected = (self.server.directory_path / name).resolve()
            if not selected.is_relative_to(self.server.directory_path.resolve()) or not selected.is_file():
                self.resource_error(f"missing resource: {name}")
                self.send_error(404)
                return
            try:
                payload = self.read_resource(selected)
            except OSError:
                self.resource_error(f"resource read failed: {name}")
                self.send_error(500)
                return
            actual = hashlib.sha256(payload).hexdigest()
            if actual != self.server.expected_bundle[name]:
                self.resource_error(f"resource digest mismatch: {name}")
                self.send_error(409)
                return
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(name))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except OSError:
                self.resource_error(f"resource response incomplete: {name}")
                return
            with self.server.resource_lock:
                observed_ns = boottime_ns()
                self.server.served[name] = actual
                self.server.served_bytes[name] = len(payload)
                self.server.resource_responses.append(
                    {"name": name, "sha256": actual, "bytes": len(payload)})
                if self.server.origin_required:
                    self.server.request_origins.append({
                        "kind": "resource", "name": name, "sha256": actual,
                        "bytes": len(payload), "time_ns": observed_ns, "origin": origin})
                if self.server.first_resource_boottime_ns is None:
                    self.server.first_resource_boottime_ns = observed_ns
                self.server.last_resource_boottime_ns = observed_ns

    def do_POST(self):
        if self.path not in ("/complete", "/error"):
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if size < 1 or size > 4_000_000:
            self.send_error(413)
            return
        request_origin = self.prove_origin(send_error=False)
        payload = self.rfile.read(size)
        origin = self.prove_origin(send_error=False)
        if len(payload) != size or request_origin is None or origin is None:
            with self.server.resource_lock:
                self.server.rejected_completion_payloads.append(payload)
                if len(payload) != size:
                    self.server.origin_errors.append("browser completion body was truncated")
            self.send_error(403 if len(payload) == size else 400)
            return
        with self.server.completion_lock:
            if not self.server.completed.is_set():
                self.server.received = {"kind": self.path[1:], "payload": payload}
                self.server.completion_boottime_ns = boottime_ns()
                if self.server.origin_required:
                    with self.server.resource_lock:
                        self.server.request_origins.append({
                            "kind": self.path[1:], "name": self.path,
                            "sha256": hashlib.sha256(payload).hexdigest(),
                            "bytes": len(payload),
                            "time_ns": self.server.completion_boottime_ns,
                            "origin": origin})
                self.server.completed.set()
            else:
                with self.server.resource_lock:
                    self.server.origin_errors.append("browser completion was repeated")
                self.send_error(409)
                return
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def required_resources(target):
    if target == "js":
        return frozenset(JS_SCRIPTS)
    if target == "wasmJs":
        return frozenset(WASM_EXECUTABLES)
    raise ValueError(f"unsupported browser target: {target}")


def browser_server(directory, page, bundle, target, handler=Handler,
                   origin_required=True):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = False
    server.directory_path = Path(directory)
    server.page = page
    server.expected_bundle = dict(bundle)
    server.required_resources = required_resources(target)
    server.resource_lock = threading.Lock()
    server.served = {}
    server.served_bytes = {}
    server.resource_responses = []
    server.resource_errors = []
    server.page_served_boottime_ns = None
    server.first_resource_boottime_ns = None
    server.last_resource_boottime_ns = None
    server.completion_boottime_ns = None
    server.completion_lock = threading.Lock()
    server.completed = threading.Event()
    server.received = None
    server.origin_required = origin_required
    server.origin_ready = threading.Event()
    server.origin_guard = None
    server.origin_errors = []
    server.request_origins = []
    server.rejected_completion_payloads = []
    return server


def validate_loaded_resources(server):
    try:
        with server.resource_lock:
            errors = server.resource_errors
            responses = server.resource_responses
            served = server.served
            served_bytes = server.served_bytes
            if type(errors) is not list or not all(type(error) is str for error in errors):
                raise ValueError("browser resource errors must be a list of strings")
            if type(responses) is not list:
                raise ValueError("browser resource responses must be a list")
            if type(served) is not dict:
                raise ValueError("browser served map must be an object")
            if type(served_bytes) is not dict:
                raise ValueError("browser served bytes map must be an object")
            errors = list(errors)
            responses = [dict(item) if type(item) is dict else item for item in responses]
            served = dict(served)
            served_bytes = dict(served_bytes)
        bundle = server.expected_bundle
        required = server.required_resources
    except AttributeError as error:
        raise ValueError("browser resource state is incomplete") from error
    if type(bundle) is not dict or not all(
        type(name) is str and name and type(digest) is str and
        re.fullmatch(r"[0-9a-f]{64}", digest)
        for name, digest in bundle.items()
    ):
        raise ValueError("browser frozen build inventory is malformed")
    if type(required) not in (set, frozenset) or not all(
        type(name) is str and name in bundle for name in required
    ):
        raise ValueError("browser required resource set is malformed")
    if not all(type(name) is str and name and type(size) is int and size > 0
               for name, size in served_bytes.items()):
        raise ValueError("browser served bytes map has invalid keys or values")
    if errors:
        raise ValueError("browser resource rejection: " + "; ".join(errors))
    loaded = {}
    for index, item in enumerate(responses):
        if type(item) is not dict or item.keys() != {"name", "sha256", "bytes"}:
            raise ValueError(f"browser response record {index} has invalid keys or type")
        name, digest, size = item["name"], item["sha256"], item["bytes"]
        if type(name) is not str or not name:
            raise ValueError(f"browser response record {index} has invalid name")
        if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"browser response record {index} has invalid sha256")
        if type(size) is not int or size <= 0:
            raise ValueError(f"browser response record {index} has invalid bytes")
        if name not in bundle or digest != bundle[name]:
            raise ValueError("browser resource differs from frozen build inventory")
        if name in loaded and loaded[name] != (digest, size):
            raise ValueError(f"browser repeated resource response differs: {name}")
        loaded[name] = (digest, size)
    if served != {name: digest for name, (digest, _) in loaded.items()}:
        raise ValueError("browser served map differs from resource responses")
    if served_bytes != {name: size for name, (_, size) in loaded.items()}:
        raise ValueError("browser served bytes differ from resource responses")
    missing = required - loaded.keys()
    if missing:
        raise ValueError("browser missing required dependencies: " + ", ".join(sorted(missing)))
    return {
        "loaded_resources_sha256": served,
        "loaded_resource_bytes": served_bytes,
        "resource_responses": responses,
        "resource_errors": errors,
    }


def snapshot_exchange(server):
    try:
        with server.resource_lock:
            return {
                "origin": {"request_origins": list(server.request_origins),
                           "origin_errors": list(server.origin_errors)},
                "resources": {
                    "resource_responses": list(server.resource_responses),
                    "served": dict(server.served),
                    "served_bytes": dict(server.served_bytes),
                    "resource_errors": list(server.resource_errors),
                },
                "times": {
                    "page": server.page_served_boottime_ns,
                    "first_resource": server.first_resource_boottime_ns,
                    "last_resource": server.last_resource_boottime_ns,
                    "completion": server.completion_boottime_ns,
                },
                "completion": None if server.received is None else {
                    "kind": server.received["kind"],
                    "sha256": hashlib.sha256(server.received["payload"]).hexdigest(),
                    "bytes": len(server.received["payload"]),
                },
            }
    except (AttributeError, KeyError, TypeError) as error:
        raise ValueError("browser exchange state is incomplete") from error


def validate_origin_stream(server, state):
    records = state["request_origins"]
    errors = state["origin_errors"]
    if not server.origin_required or type(records) is not list or type(errors) is not list:
        raise ValueError("browser request origin state is malformed")
    if not all(type(error) is str for error in errors):
        raise ValueError("browser request origin errors are malformed")
    if errors:
        raise ValueError("browser request origin rejection: " + "; ".join(errors))
    page = []
    resources = []
    completion = []
    for index, record in enumerate(records):
        if type(record) is not dict or record.keys() != {
            "kind", "name", "sha256", "bytes", "time_ns", "origin"
        }:
            raise ValueError(f"browser request origin record {index} is malformed")
        if (type(record["kind"]) is not str or type(record["name"]) is not str or
            type(record["sha256"]) is not str or not re.fullmatch(
                r"[0-9a-f]{64}", record["sha256"]
            ) or type(record["bytes"]) is not int or record["bytes"] <= 0 or
            type(record["time_ns"]) is not int or record["time_ns"] <= 0 or
            type(record["origin"]) is not dict):
            raise ValueError(f"browser request origin record {index} has invalid values")
        origin = record["origin"]
        if (origin.keys() != {
            "client_pid", "client_start_ticks", "client_socket_inode",
            "client_address", "client_port", "server_address", "server_port",
            "client_ancestry", "observed_boottime_ns", "check_times_ns", "method"
        } or any(type(origin[key]) is not int or origin[key] <= 0 for key in (
            "client_pid", "client_start_ticks", "client_socket_inode", "client_port",
            "server_port", "observed_boottime_ns"
        )) or origin["client_address"] != "127.0.0.1" or
            origin["server_address"] != "127.0.0.1" or
            origin["server_port"] != server.server_port or
            origin["method"] != "linux_procfs_tcp_fd" or
            type(origin["client_ancestry"]) is not list or
            not origin["client_ancestry"] or
            not all(type(item) is dict and item.keys() == {"pid", "start_ticks"} and
                    type(item["pid"]) is int and item["pid"] > 0 and
                    type(item["start_ticks"]) is int and item["start_ticks"] > 0
                    for item in origin["client_ancestry"]) or
            origin["client_ancestry"][0] != {
                "pid": origin["client_pid"],
                "start_ticks": origin["client_start_ticks"]
            } or type(origin["check_times_ns"]) is not list or
            len(origin["check_times_ns"]) < (4 if record["kind"] in ("complete", "error") else 3) or
            not all(type(instant) is int and instant > 0
                    for instant in origin["check_times_ns"]) or
            origin["check_times_ns"] != sorted(origin["check_times_ns"]) or
            origin["check_times_ns"][-1] != origin["observed_boottime_ns"] or
            origin["observed_boottime_ns"] > record["time_ns"]):
            raise ValueError(f"browser request origin record {index} has invalid socket proof")
        if record["kind"] == "page":
            page.append(record)
        elif record["kind"] == "resource":
            resources.append(record)
        elif record["kind"] in ("complete", "error"):
            completion.append(record)
        else:
            raise ValueError(f"browser request origin record {index} has invalid kind")
    expected_page_sha = hashlib.sha256(server.page).hexdigest()
    if not page or any(item["name"] != "/" or
                           item["sha256"] != expected_page_sha or
                           item["bytes"] != len(server.page) for item in page):
        raise ValueError("browser page response lacks request origin proof")
    if page[0]["time_ns"] != server.page_served_boottime_ns:
        raise ValueError("browser page origin time differs from served page")
    projected = [{"name": item["name"], "sha256": item["sha256"],
                  "bytes": item["bytes"]} for item in resources]
    if projected != server.resource_responses:
        raise ValueError("browser resource responses lack matching request origins")
    if len(completion) != 1 or server.received is None:
        raise ValueError("browser completion lacks unique request origin proof")
    final = completion[0]
    if (final["kind"] != server.received["kind"] or
        final["name"] != "/" + final["kind"] or
        final["sha256"] != hashlib.sha256(server.received["payload"]).hexdigest() or
        final["bytes"] != len(server.received["payload"]) or
        final["time_ns"] != server.completion_boottime_ns):
        raise ValueError("browser completion differs from request origin record")
    if any(item["time_ns"] > final["time_ns"] for item in page + resources):
        raise ValueError("browser request origins follow completion")
    return state


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
            for name in JS_SCRIPTS
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
    server = browser_server(harness.parent, page, bundle, args.target)
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
    launched_boottime_ns = boottime_ns()
    process = None
    observer = None
    process_image = None
    process_error = None
    origin_error = None
    origin_state = {"request_origins": [], "origin_errors": []}
    early_exchange = None
    completed = False
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        try:
            server.origin_guard = ClientOriginGuard(process.pid)
        except (OSError, ValueError) as error:
            origin_error = str(error)
        server.origin_ready.set()
        try:
            observer = ChromeObserver(process.pid, profile, command[-1], browser_binary,
                                      browser_sha, launched_boottime_ns)
        except (OSError, ValueError) as error:
            process_error = str(error)
        deadline = time.monotonic() + 45
        while True:
            if observer is not None and process_error is None:
                try:
                    observer.sample()
                except (OSError, ValueError) as error:
                    process_error = str(error)
            if server.completed.wait(timeout=0.02):
                break
            if process.poll() is not None or time.monotonic() >= deadline:
                break
        completed = server.completed.is_set()
        try:
            early_exchange = snapshot_exchange(server)
            origin_state = early_exchange["origin"]
            validate_origin_stream(server, origin_state)
        except ValueError as error:
            origin_error = str(error)
        if completed and observer is not None and process_error is None and origin_error is None:
            try:
                process_image = observer.finish(
                    server.page_served_boottime_ns,
                    server.first_resource_boottime_ns,
                    server.last_resource_boottime_ns,
                    server.completion_boottime_ns, nonce,
                    origin_state["request_origins"])
            except (OSError, ValueError) as error:
                process_error = str(error)
    finally:
        server.origin_ready.set()
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
    try:
        final_exchange = snapshot_exchange(server)
        origin_state = final_exchange["origin"]
        if early_exchange is None or final_exchange != early_exchange:
            origin_error = "browser exchange changed after completion"
        try:
            validate_origin_stream(server, origin_state)
        except ValueError as error:
            origin_error = (origin_error + "; " if origin_error else "") + str(error)
    except ValueError as error:
        origin_error = (origin_error + "; " if origin_error else "") + str(error)
    ended = time.monotonic_ns()
    (args.archive / "stdout.raw").write_bytes(stdout)
    (args.archive / "stderr.raw").write_bytes(stderr)
    received = server.received
    raw = received["payload"] if received and received["kind"] == "complete" else b""
    (args.archive / "producer.raw").write_bytes(raw)
    (args.archive / "completion.raw").write_bytes(received["payload"] if received else b"")
    with server.resource_lock:
        rejected_payloads = list(server.rejected_completion_payloads)
    rejected_completions = []
    for index, payload in enumerate(rejected_payloads, 1):
        name = f"rejected-completion-{index:03d}.raw"
        (args.archive / name).write_bytes(payload)
        rejected_completions.append({
            "file": name, "sha256": capture.digest(args.archive / name),
            "bytes": len(payload),
        })
    try:
        resource_state = validate_loaded_resources(server)
    except ValueError as error:
        failure = {
            "qualification": "unpassed", "target": args.target + "Browser",
            "scenario": scenario, "source_sha": source,
            "completion_kind": received["kind"] if received else "timeout",
            "producer_sha256": capture.digest(args.archive / "producer.raw"),
            "producer_bytes": len(raw),
            "completion_sha256": capture.digest(args.archive / "completion.raw"),
            "resource_validation_error": str(error),
            **origin_state,
            "rejected_completions": rejected_completions,
            "http_origin_observation_scope": "socket_owner_consistency_at_sampled_points",
        }
        if process_error is not None:
            failure["process_validation_error"] = process_error
        if origin_error is not None:
            failure["origin_validation_error"] = origin_error
        (args.archive / "capture.json").write_text(json.dumps(failure, indent=2) + "\n")
        raise
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
        "launched_boottime_ns": launched_boottime_ns,
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
        **resource_state,
        "stderr_sha256": capture.digest(args.archive / "stderr.raw"),
        "stderr_bytes": len(stderr),
        "browser_process_image": process_image,
        **origin_state,
        "rejected_completions": rejected_completions,
        "http_origin_observation_scope": "socket_owner_consistency_at_sampled_points",
        **({"origin_validation_error": origin_error} if origin_error is not None else {}),
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
    if origin_error is not None:
        raise ValueError(origin_error)
    if process_error is not None or process_image is None:
        receipt["process_validation_error"] = process_error or "browser process image missing"
        (args.archive / "capture.json").write_text(json.dumps(receipt, indent=2) + "\n")
        raise ValueError(receipt["process_validation_error"])
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
