import hashlib
import json
import platform
import re
import subprocess
from contextvars import ContextVar
from pathlib import Path

import independent_gates


SHA = re.compile(r"[0-9a-f]{64}\Z")
MODULES = frozenset(("dyn4k-core", "dyn4k"))
COUNTS = {"jvm": 4, "android-jvm": 4, "klib": 8, "browser": 24,
          "wasm-node": 12, "native-host": 28, "android-native": 16,
          "apple-device": 16}
PUBLIC_REPLAY_ACTIVE = ContextVar("dyn4k_public_replay_active", default=False)


def route_table(repository, manifest=None):
    import full_android_adapter
    import full_android_native_consumer
    import full_apple_device_consumer
    import full_browser_consumer
    import full_jvm_consumer
    import full_klib_consumer
    import full_native_host_consumer
    import full_wasm_node_consumer

    manifest = manifest if manifest is not None else independent_gates.load_approved_manifest(repository)
    lanes = manifest["lanes"]
    families = {
        "jvm": set(full_jvm_consumer.LANES),
        "android-jvm": set(full_android_adapter.ROUTES),
        "klib": set(full_klib_consumer.LOCAL_LANES),
        "browser": set(full_browser_consumer.LANES),
        "wasm-node": set(full_wasm_node_consumer.LANES),
        "native-host": {lane for lane in lanes if lane.split(":", 1)[0]
                        in full_native_host_consumer.TARGETS},
        "android-native": {lane for lane in lanes if lane.split(":", 1)[0]
                           in full_android_native_consumer.ROUTES},
        "apple-device": {lane for lane in lanes if lane.split(":", 1)[0]
                         in full_apple_device_consumer.TARGETS},
    }
    if {name: len(ids) for name, ids in families.items()} != COUNTS:
        raise ValueError("dedicated route family counts differ from approved matrix")
    table = {}
    for family, ids in families.items():
        for lane in ids:
            if lane in table:
                raise ValueError(f"duplicate dedicated staged consumer route: {lane}")
            table[lane] = family
    if set(table) != set(lanes) or len(table) != 112:
        raise ValueError("dedicated staged consumer routes do not cover 112 approved lanes")
    return table


def _sha(value, label):
    if type(value) is not str or SHA.fullmatch(value) is None:
        raise ValueError(f"signed {label} SHA-256 is missing")
    return value


def _file(path, expected, label):
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError(f"signed {label} executable is absent or symbolic")
    if hashlib.sha256(path.read_bytes()).hexdigest() != _sha(expected, label):
        raise ValueError(f"signed {label} executable bytes differ")
    return path


def _source(repository, candidate, name):
    paths = (f"tools/qualification/full_{name}_consumer.py",
             "tools/qualification/full_signed_routes.py",
             "tools/qualification/independent_gates.py",
             "tools/qualification/independent_adapter.py")
    for path in paths:
        try:
            committed = subprocess.check_output(
                ["git", "--no-replace-objects", "-C", str(repository), "show",
                 f"{candidate}:{path}"], stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            raise ValueError(f"public producer or central verifier absent from candidate: {path}") from None
        if (Path(repository) / path).read_bytes() != committed:
            raise ValueError(f"public producer or central verifier differs from candidate: {path}")


def _browser_observer_source(repository, candidate):
    path = "tools/qualification/independent_browser_observer.js"
    try:
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "show",
             f"{candidate}:{path}"], stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        raise ValueError("independent browser observer is absent from candidate") from None
    if (Path(repository) / path).read_bytes() != committed:
        raise ValueError("independent browser observer differs from candidate")
def _observer_source(repository, candidate, module):
    path = "tools/qualification/independent_linux_observer.py"
    selected = (Path(repository) / path).resolve(strict=True)
    loaded = Path(module.__file__).resolve(strict=True)
    origin = Path(module.__spec__.origin).resolve(strict=True)
    verifier = Path(module.verify.__code__.co_filename).resolve(strict=True)
    committed = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show", f"{candidate}:{path}"],
        stderr=subprocess.PIPE)
    if (loaded != selected or origin != selected or verifier != selected
            or selected.read_bytes() != committed):
        raise ValueError("independent Linux observer source differs from candidate")


def execution_witness(expected, candidate, lane, digest, runtime, mode,
                      executables, artifacts, build_executable, archive=None,
                      launcher=None):
    binding = expected.get("expected_execution_witness")
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("independently signed process witness is missing")
    path = Path(binding["path"])
    if (not path.is_absolute() or not path.is_file() or path.is_symlink()
            or archive is not None and path.is_relative_to(Path(archive))):
        raise ValueError("independent process witness file is absent or symbolic")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _sha(binding["sha256"], "process witness"):
        raise ValueError("independent process witness bytes differ from signed digest")
    witness = json.loads(raw, object_pairs_hook=independent_gates._strict_object,
                         parse_constant=lambda value: (_ for _ in ()).throw(
                             ValueError(f"non-finite witness value: {value}")))
    if (not isinstance(witness, dict)
            or witness.get("schema") != "independent-execution-witness/1"
            or witness.get("candidate_sha") != candidate
            or witness.get("lane") != lane
            or witness.get("archive_sha256") != digest
            or witness.get("runtime_identity") != runtime
            or witness.get("mode") != mode
            or witness.get("executables") != executables
            or witness.get("staged_artifacts") != artifacts
            or not isinstance(witness.get("auditor"), str)
            or not witness["auditor"].strip()
            or not isinstance(witness.get("processes"), dict)
            or set(witness["processes"]) != set(executables)):
        raise ValueError("independent process witness differs from signed route")
    build = witness.get("build")
    if (not isinstance(build, dict)
            or build.get("executable_sha256") != _sha(build_executable, "build executable")
            or type(build.get("pid")) is not int or build["pid"] <= 0
            or build.get("exit_code") != 0
            or type(build.get("started_ns")) is not int
            or type(build.get("finished_ns")) is not int
            or build["started_ns"] <= 0 or build["finished_ns"] < build["started_ns"]):
        raise ValueError("independent build process witness is incomplete")
    if launcher is not None:
        observed = witness.get("launcher")
        image = expected.get("expected_build_launcher_image")
        if (not isinstance(image, dict) or set(image) != {"path", "sha256"}
                or type(image["path"]) is not str
                or not Path(image["path"]).is_absolute()
                or SHA.fullmatch(str(image["sha256"])) is None):
            raise ValueError("signed launcher process image is missing")
        if (not isinstance(observed, dict)
                or observed.get("script_path") != launcher["path"]
                or observed.get("script_sha256") != _sha(launcher["sha256"], "launcher")
                or observed.get("command") != launcher["command"]
                or type(observed.get("pid")) is not int or observed["pid"] <= 0
                or type(observed.get("parent_pid")) is not int or observed["parent_pid"] <= 0
                or type(observed.get("started_ns")) is not int
                or type(observed.get("finished_ns")) is not int
                or observed["started_ns"] <= 0
                or observed["finished_ns"] < observed["started_ns"]
                or observed.get("executable_path") != image["path"]
                or observed.get("executable_sha256") != image["sha256"]):
            raise ValueError("independent launcher process witness is incomplete")
        if ("expected_native_build_observer" not in expected
                and observed["pid"] != build["pid"]
                and build.get("parent_pid") != observed["pid"]
                and not _witness_ancestry(witness.get("build_ancestry"),
                                          build, observed)):
            raise ValueError("independent build image ancestry differs from launcher")
        if not (observed["started_ns"] <= build["started_ns"]
                <= build["finished_ns"] <= observed["finished_ns"]):
            raise ValueError("independent build image interval differs from launcher")
    for name, process in witness["processes"].items():
        if (not isinstance(process, dict) or process.get("executable_sha256") != executables[name]
                or type(process.get("pid")) is not int or process["pid"] <= 0
                or process.get("exit_code") != 0
                or type(process.get("started_ns")) is not int
                or type(process.get("finished_ns")) is not int
                or process["started_ns"] <= 0
                or process["finished_ns"] < process["started_ns"]):
            raise ValueError("independent process witness lacks observed execution")
    return witness


def browser_execution_witness(expected, candidate, lane, digest, runtime, hashes,
                              toolchain, archive):
    binding = expected.get("expected_execution_witness")
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("independently signed browser execution witness is missing")
    path = Path(binding["path"])
    if (not path.is_absolute() or not path.is_file() or path.is_symlink()
            or path.resolve().is_relative_to(Path(archive).resolve())):
        raise ValueError("independent browser execution witness file is absent or symbolic")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _sha(binding["sha256"], "browser witness"):
        raise ValueError("independent browser execution witness bytes differ")
    witness = json.loads(raw, object_pairs_hook=independent_gates._strict_object,
                         parse_constant=lambda value: (_ for _ in ()).throw(
                             ValueError(f"non-finite browser witness value: {value}")))
    observer = Path(__file__).with_name("independent_browser_observer.js")
    source_sha = hashlib.sha256(observer.read_bytes()).hexdigest()
    if (not isinstance(witness, dict)
            or set(witness) != {"schema", "candidate_sha", "lane", "archive_sha256",
                                "runtime_identity", "mode", "staged_artifacts",
                                "browser_sha256", "observer_source_sha256", "auditor",
                                "responses", "browser_consumption"}
            or witness["schema"] != "independent-browser-execution-witness/1"
            or witness["candidate_sha"] != candidate or witness["lane"] != lane
            or witness["archive_sha256"] != digest
            or witness["runtime_identity"] != runtime
            or witness["mode"] != lane.rsplit(":", 1)[1]
            or witness["staged_artifacts"] != hashes
            or witness["browser_sha256"] != toolchain["browser_sha256"]
            or witness["observer_source_sha256"] != source_sha
            or witness["responses"] != expected.get("expected_browser_responses")
            or not isinstance(witness["auditor"], str)
            or not witness["auditor"].strip()):
        raise ValueError("independent browser execution witness differs from signed lane")
    return witness
def _witness_ancestry(rows, build, launcher):
    if not isinstance(rows, list) or not rows:
        return False
    pid = build["pid"]
    seen = set()
    for index, row in enumerate(rows):
        if (not isinstance(row, dict) or set(row) != {"pid", "parent_pid"}
                or type(row["pid"]) is not int or row["pid"] != pid
                or type(row["parent_pid"]) is not int or row["parent_pid"] <= 0
                or pid in seen):
            return False
        seen.add(pid)
        pid = row["parent_pid"]
        if pid == launcher["pid"]:
            return index == len(rows) - 1 and rows[0]["parent_pid"] == build.get("parent_pid")
    return False


def _launcher(path, sha, command):
    if (type(path) is not str or not Path(path).is_absolute()
            or type(command) is not list or not command or command[0] != path
            or any(type(arg) is not str for arg in command)):
        raise ValueError("archived Gradle launcher command differs")
    return {"path": path, "sha256": _sha(sha, "Gradle launcher"),
            "command": command}


def _cross_java_path(run, observed, image, java):
    if (run.get("build", {}).get("requested_path") != java
            or run["build"].get("path") != image.get("executable_path")
            or observed.get("build", {}).get("executable_path") != image.get("executable_path")
            or image.get("argv", [None])[0] != java):
        raise ValueError("Native cross pinned Java process image differs")


def _cross_build_observer(repository, expected, archive, candidate, lane, build_digest,
                          hashes, toolchain, process, signed_witness):
    import independent_linux_observer

    _observer_source(repository, candidate, independent_linux_observer)

    binding = expected.get("expected_native_build_observer")
    if (not isinstance(binding, dict)
            or set(binding) != {"path", "events_sha256", "witness_sha256"}
            or type(binding["path"]) is not str):
        raise ValueError("signed Native cross build observer is missing")
    root = Path(binding["path"])
    if (not root.is_absolute() or root.is_symlink() or not root.is_dir()
            or root.is_relative_to(archive)):
        raise ValueError("signed Native cross build observer path differs")
    for name, key in (("events.jsonl", "events_sha256"),
                      ("witness.json", "witness_sha256")):
        _file(root / name, binding[key], "Native cross observer " + name)
    observed, rows = independent_linux_observer.verify(root, include_events=True)
    run = rows[0]
    launcher = _launcher(toolchain["gradle_executable"],
                         toolchain["gradle_sha256"], process.get("command"))
    if (observed.get("candidate_sha") != candidate or observed.get("lane") != lane
            or observed.get("archive_sha256") != build_digest
            or observed.get("mode") != lane.rsplit(":", 1)[1]
            or observed.get("staged_artifacts") != hashes
            or observed.get("build") != signed_witness["build"]
            or run.get("build_only") is not True
            or run.get("launcher_seal_required") is not True
            or run.get("expected_processes") != {}
            or run.get("launcher") != {"path": launcher["path"],
                                       "sha256": launcher["sha256"]}
            or observed["build"].get("executable_sha256") != toolchain["java_sha256"]):
        raise ValueError("Native cross build observer differs from signed build")
    shell = [row for row in rows if row["kind"] == "image"
             and row.get("origin") == "exec" and row.get("pid") == process.get("pid")
             and row.get("argv", [None])[1:] == launcher["command"]]
    if len(shell) != 1:
        raise ValueError("Native cross Gradle script argv or PID was not observed")
    shell = shell[0]
    recorded_launcher = signed_witness.get("launcher")
    spawns = [row for row in rows if row["kind"] == "spawn"
              and row.get("pid") == shell["pid"]]
    exits = [row for row in rows if row["kind"] == "exit"
             and row.get("pid") == shell["pid"]]
    if (len(spawns) != 1 or spawns[0].get("parent_pid") != process.get("parent_pid")
            or len(exits) != 1 or not isinstance(recorded_launcher, dict)
            or recorded_launcher.get("pid") != shell["pid"]
            or recorded_launcher.get("parent_pid") != process.get("parent_pid")
            or recorded_launcher.get("script_path") != launcher["path"]
            or recorded_launcher.get("script_sha256") != launcher["sha256"]
            or recorded_launcher.get("command") != launcher["command"]
            or recorded_launcher.get("executable_path") != shell["executable_path"]
            or recorded_launcher.get("executable_sha256") != shell["executable_sha256"]
            or recorded_launcher.get("started_ns") != shell["observed_at_ns"]
            or recorded_launcher.get("finished_ns") != exits[0]["observed_at_ns"]):
        raise ValueError("Native cross launcher differs from observed interpreter")
    image = [row for row in rows if row["kind"] == "image"
             and row.get("origin") == "exec"
             and row.get("pid") == observed["build"]["pid"]
             and row.get("executable_sha256") == toolchain["java_sha256"]
             and row.get("observed_at_ns") == observed["build"]["started_ns"]]
    java = str(Path(toolchain["java_home"]) / "bin/java")
    if (len(image) != 1 or image[0]["argv"][-len(launcher["command"][1:]):]
            != launcher["command"][1:]):
        raise ValueError("Native cross pinned Java process image differs")
    _cross_java_path(run, observed, image[0], java)
    parents = {row["pid"]: row["parent_pid"] for row in rows
               if row["kind"] == "spawn"}
    pid = observed["build"]["pid"]
    while pid != shell["pid"] and pid in parents:
        pid = parents[pid]
    if pid != shell["pid"] or image[0]["seq"] <= shell["seq"]:
        raise ValueError("Native cross Java image does not descend from Gradle launcher")
    java_exits = [row for row in rows if row["kind"] == "exit"
                  and row.get("pid") == observed["build"]["pid"]]
    if (type(process.get("started_ns")) is not int
            or type(process.get("finished_ns")) is not int
            or len(java_exits) != 1
            or not process["started_ns"] <= shell["observed_wall_ns"]
            <= image[0]["observed_wall_ns"] <= java_exits[0]["observed_wall_ns"]
            <= process["finished_ns"]
            or exits[0]["observed_wall_ns"] > process["finished_ns"]):
        raise ValueError("Native cross build observer is outside archived interval")
    return observed


def _signed(expected, hashes, runtime, digest, receipt):
    if (not isinstance(expected, dict) or expected.get("expected_artifact_hashes") != hashes
            or expected.get("expected_runtime_identity") != runtime
            or expected.get("expected_archive_digests", {}).get("staged-consumer") != digest
            or type(runtime) is not str or not runtime
            or not isinstance(hashes, dict) or set(hashes) != MODULES
            or any(type(value) is not str or SHA.fullmatch(value) is None
                   for value in hashes.values())):
        raise ValueError("signed staged consumer identity is incomplete")
    _sha(digest, "archive")
    if (receipt.get("status") != "PASSED" or receipt.get("artifact_hashes",
            receipt.get("staged_hashes")) != hashes):
        raise ValueError("producer did not report passing audited artifacts")


def _selected(repository, lane, expected_count=2523):
    manifest = independent_gates.load_approved_manifest(repository)
    cases = independent_gates.consumer_contract(manifest, lane)["cases"]
    if (len(cases) != expected_count or len({row["id"] for row in cases}) != expected_count
            or (expected_count == 2523 and
                (sum(row["module"] == "dyn4k-core" for row in cases) != 2465
                 or sum(row["module"] == "dyn4k" for row in cases) != 58))):
        raise ValueError("selected original method contract differs")
    return cases


def _browser_bundle_bytes(root, bundles, wasm):
    if not isinstance(bundles, dict) or set(bundles) != {"core", "facade"}:
        raise ValueError("signed browser bundle inventory is missing")
    executables = {}
    for short in ("core", "facade"):
        record = bundles[short]
        keys = {"karma_selected_js", "linked_executable_js"}
        if wasm:
            keys |= {"linked_executable_wasm", "assets"}
        if not isinstance(record, dict) or set(record) != keys:
            raise ValueError("signed browser bundle file inventory differs")
        for key, name in (("karma_selected_js", "karma-selected.js"),
                          ("linked_executable_js", "linked-executable.js"),
                          ("linked_executable_wasm", "linked-executable.wasm")):
            if key not in record:
                continue
            if hashlib.sha256((root / short / name).read_bytes()).hexdigest() != _sha(
                    record[key], f"browser {short} {name}"):
                raise ValueError("browser selected or linked executable bytes differ")
        executables[short] = record["linked_executable_js"]
        if wasm:
            assets = record["assets"]
            selected = independent_gates._json(root / short / "selected-bundle.json")
            declared = selected.get("assets") if isinstance(selected, dict) else None
            if (not isinstance(assets, dict) or not assets
                    or not isinstance(declared, list)
                    or any(not isinstance(item, dict) or set(item) != {"name", "sha256"}
                           for item in declared)
                    or len(declared) != len(assets)
                    or {item["name"]: item["sha256"] for item in declared} != assets):
                raise ValueError("browser linked asset inventory differs from signed bytes")
            for name, value in assets.items():
                if (type(name) is not str or Path(name).name != name or "\\" in name
                        or not name or hashlib.sha256(
                            (root / short / "assets" / name).read_bytes()).hexdigest()
                        != _sha(value, f"browser {short} asset")):
                    raise ValueError("browser linked asset bytes differ")
    return executables


def _browser_response_proof(root, responses, witness, receipt, wasm):
    if (not isinstance(responses, dict) or set(responses) != {"core", "facade"}
            or witness.get("responses") != responses
            or receipt.get("schema") not in (3, 4)
            or not isinstance(receipt.get("modules"), dict)):
        raise ValueError("browser HTTP responses differ from signed witness or producer")
    for short in ("core", "facade"):
        folder = root / short
        selected = independent_gates._json(folder / "selected-bundle.json")
        captured = independent_gates._json(folder / "http-responses.json")
        signed = responses[short]
        process = receipt["modules"].get(short)
        package = f"dyn4k-full-staged-browser-consumer-{short}-test"
        if (not isinstance(selected, dict) or not isinstance(captured, dict)
                or not isinstance(signed, dict) or captured != signed
                or not isinstance(process, dict)
                or type(process.get("started_ns")) is not int
                or type(process.get("finished_ns")) is not int
                or process["started_ns"] <= 0
                or process["finished_ns"] < process["started_ns"]
                or any(captured.get(key) != selected.get(key) for key in
                       ("browser_id", "browser_name", "node_pid", "captured_ns",
                        "complete_ns"))
                or set(captured) != {"browser_id", "browser_name", "node_pid",
                                     "captured_ns", "complete_ns", "generated", "responses"}
                or type(captured["node_pid"]) is not int or captured["node_pid"] <= 0
                or type(captured["captured_ns"]) is not int
                or type(captured["complete_ns"]) is not int
                or not process["started_ns"] <= captured["captured_ns"]
                    <= captured["complete_ns"] <= process["finished_ns"]):
            raise ValueError("browser HTTP response archive or Gradle interval differs")
        generated = captured["generated"]
        effective = selected.get("effective_files")
        if (not isinstance(generated, list) or generated != selected.get("generated")
                or len(generated) != (5 if wasm else 4)
                or not isinstance(effective, list) or not effective
                or not isinstance(effective[0], dict)
                or type(effective[0].get("pattern")) is not str):
            raise ValueError("browser generated source inventory differs")
        webpack = Path(effective[0]["pattern"]).parent
        generated_names = [item.get("name") for item in generated
                           if isinstance(item, dict)]
        if (len(generated_names) != len(generated)
                or any(type(name) is not str for name in generated_names)
                or len(set(generated_names)) != len(generated)
                or "runtime.js" not in generated_names
                or "commons.js" not in generated_names
                or not any(re.fullmatch(r"kotlin-test-karma-runner\.[0-9]+\.js", name)
                           for name in generated_names)
                or not any(re.fullmatch(
                    rf"{re.escape('load' if wasm else package)}\.[0-9]+\.js", name)
                    for name in generated_names)):
            raise ValueError("browser generated executable names differ")
        emitted_wasm = next((name for name in generated_names if name.endswith(".wasm")),
                            None)
        if wasm and (emitted_wasm is None
                     or re.fullmatch(r"[0-9a-f]{20}\.wasm", emitted_wasm) is None):
            raise ValueError("browser generated Wasm name differs")
        generated_hashes = {}
        for item in generated:
            name = item["name"]
            source = folder / "http-sources" / name
            if (set(item) != {"name", "source_path", "size", "sha256"}
                    or type(name) is not str or Path(name).name != name
                    or "\\" in name
                    or item["source_path"] != str(webpack / name)
                    or type(item["size"]) is not int or item["size"] <= 0
                    or _file(source, item["sha256"], "browser generated source").stat().st_size
                    != item["size"]):
                raise ValueError("browser generated source bytes or mapping differ")
            generated_hashes[name] = item["sha256"]
        assets = selected.get("assets")
        asset_hashes = {}
        if wasm:
            if (not isinstance(assets, list) or any(not isinstance(item, dict)
                    or set(item) != {"name", "sha256"}
                    or type(item["name"]) is not str
                    or Path(item["name"]).name != item["name"]
                    or type(item["sha256"]) is not str
                    or SHA.fullmatch(item["sha256"]) is None for item in assets)):
                raise ValueError("browser selected package assets differ")
            asset_hashes = {item["name"]: item["sha256"] for item in assets}
            selected_wasm = folder / "assets" / f"{package}.wasm"
            if (len(asset_hashes) != len(assets)
                    or asset_hashes.get(f"{package}.wasm") != generated_hashes[emitted_wasm]
                    or _file(selected_wasm, generated_hashes[emitted_wasm],
                             "browser selected Wasm").read_bytes() !=
                    _file(folder / "linked-executable.wasm", generated_hashes[emitted_wasm],
                          "browser linked Wasm").read_bytes()):
                raise ValueError("browser emitted Wasm differs from selected package")
        allowed_assets = ({f"{package}.mjs", f"{package}.wasm",
                           f"{package}.import-object.mjs", f"{package}.js-builtins.mjs",
                           "custom-formatters.js"} if wasm else set())
        allowed = set(generated_names) | (allowed_assets & set(asset_hashes))
        required = {"runtime.js", "commons.js"}
        if wasm:
            required.add(emitted_wasm)
        items = captured["responses"]
        if (not isinstance(items, list) or not required <=
                {item.get("name") for item in items if isinstance(item, dict)} <= allowed
                or len(items) > len(allowed)
                or len({item.get("name") for item in items if isinstance(item, dict)})
                != len(items)):
            raise ValueError("browser HTTP response inventory differs")
        previous = process["started_ns"]
        for index, item in enumerate(items):
            if (not isinstance(item, dict)
                    or set(item) != {"ordinal", "name", "url", "method", "started_ns",
                                     "finished_ns", "status", "content_encoding", "range",
                                     "size", "sha256", "body_path"}
                    or type(item["ordinal"]) is not int or item["ordinal"] != index
                    or type(item["started_ns"]) is not int
                    or type(item["finished_ns"]) is not int
                    or not previous <= item["started_ns"] <= item["finished_ns"]
                        <= captured["complete_ns"]
                    or item["method"] != "GET" or item["status"] != 200
                    or item["content_encoding"] is not None or item["range"] is not None
                    or item["body_path"] != f"http-responses/{index:04d}.body"
                    or type(item["url"]) is not str
                    or re.fullmatch(r"/(?:absolute|base)/[^?#]+(?:\?[^#]*)?",
                                    item["url"]) is None
                    or Path(item["url"].split("?", 1)[0]).name != item["name"]
                    or type(item["size"]) is not int
                    or not 0 < item["size"] <= 64 * 1024 * 1024
                    or type(item["sha256"]) is not str
                    or SHA.fullmatch(item["sha256"]) is None
                    or item["sha256"] != generated_hashes.get(
                        item["name"], asset_hashes.get(item["name"]))):
                raise ValueError("browser HTTP response order or interval differs")
            source = (folder / "http-sources" / item["name"]
                      if item["name"] in generated_hashes
                      else folder / "assets" / item["name"])
            body = _file(folder / item["body_path"], item["sha256"],
                         "browser HTTP response body")
            if (body.stat().st_size != item["size"]
                    or body.read_bytes() != _file(source, item["sha256"],
                                                  "browser served source").read_bytes()):
                raise ValueError("browser HTTP response bytes differ from selected source")
            previous = item["started_ns"]


def verify_browser(repository, candidate, lane, root, expected, hashes, runtime, digest):
    import full_browser_consumer

    if route_table(repository)[lane] != "browser":
        raise ValueError("signed browser route differs from selected lane")
    toolchain = expected.get("expected_browser_toolchain")
    bundles = expected.get("expected_browser_bundles")
    if not isinstance(toolchain, dict) or not isinstance(bundles, dict):
        raise ValueError("signed browser toolchain or bundles are missing")
    root = Path(root)
    if root.is_symlink() or independent_gates.archive_digest(root) != digest:
        raise ValueError("signed browser archive digest differs")
    receipt = independent_gates._json(root / "receipt.json")
    _signed(expected, hashes, runtime, digest, receipt)
    _source(repository, candidate, "browser")
    if receipt.get("schema") == 4:
        _browser_observer_source(repository, candidate)
    selected_lane = independent_gates.load_approved_manifest(repository)["lanes"][lane]
    if (receipt.get("candidate_sha") != candidate or receipt.get("lane") != lane
            or receipt.get("consumer_contract_sha256") != independent_gates.digest(
                independent_gates.consumer_contract(
                    independent_gates.load_approved_manifest(repository), lane))
            or tuple(lane.split(":")) != tuple(selected_lane[key] for key in
                   ("target", "runtime", "version", "configuration"))):
        raise ValueError("browser candidate, route, or approved methods differ")
    if (receipt.get("runtime_identity") != runtime or receipt.get("toolchain") != toolchain
            or type(runtime) is not str
            or re.fullmatch(r"(Linux|Darwin) [^ ]+ [^ ]+", runtime) is None):
        raise ValueError("browser runtime or toolchain differs from signed lane")
    if toolchain.get("kgp_version") != "2.4.20" or toolchain.get("gradle_version") != "9.5.0":
        raise ValueError("browser toolchain differs from approved versions")
    family = selected_lane["runtime"]
    if (toolchain.get("java_sha256") != full_browser_consumer.expected_java_sha256(
            runtime.split(" ", 1)[0], family)
            or toolchain.get("gradle_sha256") != full_browser_consumer.GRADLE_SHA256):
        raise ValueError("browser JDK or Gradle differs from approved executable")
    browser = _file(toolchain.get("browser"), toolchain.get("browser_sha256"), "browser")
    _file(Path(toolchain.get("java_home", "")) / "bin/java",
          toolchain.get("java_sha256"), "JDK 21")
    _file(toolchain.get("gradle"), toolchain.get("gradle_sha256"), "Gradle")
    role = selected_lane["version"]
    full_browser_consumer.runtime_pin(family, role, browser,
                                      toolchain.get("browser_sha256"))
    executables = _browser_bundle_bytes(root, bundles, lane.startswith("wasmJs:"))
    public = full_browser_consumer.verify(repository, candidate, lane, root, digest,
                                          browser, hashes, toolchain["browser_sha256"])
    if public != {"status": "PASSED", "lane": lane, "selected_cases": len(_selected(repository, lane)),
                  "archive_sha256": digest, "candidate_sha": candidate}:
        raise ValueError("browser public verifier differs from signed lane")
    if receipt.get("schema") in (3, 4) or lane.startswith("wasmJs:"):
        responses = expected.get("expected_browser_responses")
        witness = (browser_execution_witness(expected, candidate, lane, digest, runtime,
                                             hashes, toolchain, root)
                   if receipt.get("schema") == 4 else
                   execution_witness(expected, candidate, lane, digest, runtime,
                                     lane.rsplit(":", 1)[1], executables, hashes,
                                     toolchain["java_sha256"], root,
                                     _launcher(toolchain["gradle"],
                                               toolchain["gradle_sha256"],
                                               receipt["process"]["graph"]["command"])))
        _browser_response_proof(root, responses, witness, receipt,
                                lane.startswith("wasmJs:"))
        if receipt.get("schema") == 4:
            independent_gates._browser_consumption_witness(root, receipt, expected)
    return public


def _verify_native_cross(repository, candidate, lane, root, receipt, expected,
                         hashes, runtime, digest):
    import full_native_host_consumer

    manifest = independent_gates.load_approved_manifest(repository)
    selected_lane = manifest["lanes"][lane]
    selected = _selected(repository, lane)
    contract_sha = independent_gates.digest(
        independent_gates.consumer_contract(manifest, lane))
    if (selected_lane["target"] != "linuxArm64"
            or tuple(lane.split(":")) != tuple(selected_lane[key] for key in
                ("target", "runtime", "version", "configuration"))
            or receipt.get("candidate_sha") != candidate or receipt.get("lane") != lane
            or receipt.get("artifact_hash_provenance") != "audited"
            or independent_gates.archive_digest(root) != digest):
        raise ValueError("signed Native cross runtime archive or lane differs")
    build_digest = _sha(expected.get("expected_native_build_archive_sha256"),
                        "cross build archive")
    build_root = root / "build"
    if (build_root.is_symlink() or not build_root.is_dir()
            or receipt.get("build_archive_sha256") != build_digest
            or independent_gates.archive_digest(build_root) != build_digest):
        raise ValueError("signed Native cross build archive differs")
    build = independent_gates._json(build_root / "receipt.json")
    selection = expected.get("expected_native_selection")
    host = expected.get("expected_native_host")
    build_host = expected.get("expected_native_build_host")
    toolchain = expected.get("expected_native_toolchain")
    executables = expected.get("expected_native_build_executables")
    if (not isinstance(selection, dict) or not isinstance(host, dict)
            or not isinstance(build_host, dict) or not isinstance(toolchain, dict)
            or not isinstance(executables, dict) or set(executables) != {"core", "facade"}
            or any(type(value) is not str or SHA.fullmatch(value) is None
                   for value in executables.values())
            or receipt.get("selection") != selection
            or receipt.get("runtime_host") != host
            or receipt.get("runtime_host_after") != host
            or receipt.get("build_host") != build_host
            or runtime != full_native_host_consumer.digest(
                full_native_host_consumer.encoded(host))):
        raise ValueError("signed Native cross runtime host or selection differs")
    full_native_host_consumer.validate_cross_build_host(build_host)
    full_native_host_consumer.validate_host(lane, selection, host)
    if (not isinstance(build, dict) or build.get("schema") != 2
            or build.get("status") != "COMPILED_ONLY"
            or build.get("phase") != "linux-x64-cross-build"
            or build.get("candidate_sha") != candidate or build.get("lane") != lane
            or build.get("source_tree") != receipt.get("source_tree")
            or build.get("consumer_contract_sha256") != contract_sha
            or build.get("artifact_hashes") != hashes
            or build.get("artifact_hash_provenance") != "audited"
            or build.get("build_host") != build_host
            or build.get("toolchain") != toolchain
            or build.get("selected_cases") != len(selected)):
        raise ValueError("signed Native cross build toolchain or contract differs")
    if (not isinstance(toolchain.get("java_version"), str)
            or re.search(r'version "21(?:\.|\")', toolchain["java_version"]) is None
            or toolchain.get("gradle_version") != "Gradle 9.5.0"
            or toolchain.get("kgp_version") != "2.4.20"
            or not isinstance(toolchain.get("native_version"), str)
            or "Kotlin/Native: 2.4.20" not in toolchain.get("native_version", "")
            or any(type(toolchain.get(key)) is not str
                   or not Path(toolchain[key]).is_absolute() for key in
                   ("gradle_executable", "python_executable", "java_home", "native_home"))
            or any(type(toolchain.get(key)) is not str
                   or SHA.fullmatch(toolchain[key]) is None for key in
                   ("gradle_sha256", "python_sha256", "java_sha256",
                    "native_sha256", "native_compiler_sha256"))):
        raise ValueError("signed Native cross build toolchain version differs")
    products = build.get("products")
    if (not isinstance(products, dict) or set(products) != {"core", "facade"}
            or any(not isinstance(products[name], dict)
                   or products[name].get("sha256") != executables[name]
                   or products[name].get("archive") != f"runtime/{name}.program"
                   for name in executables)):
        raise ValueError("signed Native cross build executable identity differs")
    for name, sha in executables.items():
        _file(build_root / "runtime" / f"{name}.program", sha,
              f"cross build {name}")
    order = receipt.get("method_order")
    processes = receipt.get("processes")
    if (receipt.get("selected_cases") != len(selected)
            or not isinstance(order, list) or len(order) != len(selected)
            or any(type(item) is not str for item in order)
            or set(order) != {item["id"] for item in selected}
            or not isinstance(processes, dict) or set(processes) != {"core", "facade"}
            or any(not isinstance(processes[name], dict)
                   or processes[name].get("exit_code") != 0
                   or not isinstance(processes[name].get("observed_process"), dict)
                   or type(processes[name]["observed_process"].get("pid")) is not int
                   or processes[name]["observed_process"]["pid"] <= 0
                   for name in ("core", "facade"))):
        raise ValueError("signed Native cross runtime execution is incomplete")
    witness = execution_witness(expected, candidate, lane, digest, runtime,
                                selected_lane["configuration"], executables, hashes,
                                toolchain["java_sha256"], root,
                                _launcher(toolchain["gradle_executable"],
                                          toolchain["gradle_sha256"],
                                          build.get("process", {}).get("command")))
    _cross_build_observer(repository, expected, root, candidate, lane,
                          build_digest, hashes, toolchain,
                          build.get("process", {}), witness)
    for name in ("core", "facade"):
        recorded = processes[name]
        observed = witness["processes"][name]
        if (not isinstance(recorded, dict)
                or type(recorded.get("pid")) is not int
                or observed["pid"] != recorded["pid"]
                or type(recorded.get("started_ns")) is not int
                or type(recorded.get("finished_ns")) is not int
                or type(observed.get("started_wall_ns")) is not int
                or type(observed.get("finished_wall_ns")) is not int
                or not recorded["started_ns"] <= observed["started_wall_ns"]
                    <= observed["finished_wall_ns"] <= recorded["finished_ns"]):
            raise ValueError("signed Native cross process witness differs from producer")
    if any(witness["processes"][name]["pid"] !=
           processes[name]["observed_process"]["pid"]
           for name in ("core", "facade")):
        raise ValueError("signed Native cross observed process witness differs")
    public = full_native_host_consumer.verify_cross_run(
        root, repository, candidate, lane, hashes, selection, digest, build_digest, toolchain)
    if public != {"status": "PASSED", "lane": lane, "candidate_sha": candidate,
                  "archive_sha256": digest, "selected_cases": len(selected),
                  "artifact_hash_provenance": "audited", "complete_selected_suite": True}:
        raise ValueError("Native cross runtime public replay differs")
    return public


def verify(repository, candidate, lane, root, expected, hashes, runtime, digest):
    import full_android_native_consumer
    import full_apple_device_consumer
    import full_native_host_consumer
    import full_wasm_node_consumer

    repository, root = Path(repository), Path(root)
    family = route_table(repository)[lane]
    if family not in {"wasm-node", "native-host", "android-native", "apple-device"}:
        raise ValueError(f"route belongs to the retained signed adapter: {lane}")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("transported archive root is absent or symbolic")
    receipt = independent_gates._json(root / "receipt.json")
    if not isinstance(receipt, dict):
        raise ValueError("dedicated producer receipt is invalid")
    _signed(expected, hashes, runtime, digest, receipt)
    _source(repository, candidate, {"wasm-node": "wasm_node",
                                    "native-host": "native_host",
                                    "android-native": "android_native",
                                    "apple-device": "apple_device"}[family])
    if family == "native-host" and receipt.get("schema") == 3:
        return _verify_native_cross(repository, candidate, lane, root, receipt,
                                    expected, hashes, runtime, digest)
    if (receipt.get("candidate_sha") != candidate or receipt.get("lane") != lane
            or receipt.get("consumer_group") != "full-suite"):
        raise ValueError("dedicated producer candidate or lane differs")
    selected = _selected(repository, lane)
    if receipt.get("consumer_contract_sha256") != independent_gates.digest(
            independent_gates.consumer_contract(
                independent_gates.load_approved_manifest(repository), lane)):
        raise ValueError("producer selected a different original method contract")
    selected_lane = independent_gates.load_approved_manifest(repository)["lanes"][lane]
    if any(receipt.get(key) != selected_lane[key] for key in
           ("target", "runtime", "version", "configuration")):
        raise ValueError("producer runtime role, ABI, or mode differs")
    if family == "wasm-node":
        signed_identity = expected.get("expected_wasm_runtime")
        binary = expected.get("expected_wasm_runtime_binary")
        if not isinstance(signed_identity, dict) or type(binary) is not str:
            raise ValueError("signed structured Wasm runtime selection is missing")
        mapped = "wasm-node-v1:" + independent_gates.digest(signed_identity)
        if runtime != mapped or receipt.get("runtime_identity") != signed_identity:
            raise ValueError("structured Wasm observation differs from signed string mapping")
        checked = full_wasm_node_consumer.runtime_preflight(lane, binary)
        if (checked.get("status") != "PASSED"
                or any(signed_identity.get(key) != checked.get(key)
                       for key in ("family", "role", "version", "sha256", "path")
                       if key in checked)
                or signed_identity.get("family") != selected_lane["runtime"]
                or signed_identity.get("role") != selected_lane["version"]
                or signed_identity.get("host") !=
                f"{platform.system()} {platform.release()} {platform.machine()}"
                or signed_identity.get("sha256") != hashlib.sha256(
                    _file(binary, signed_identity.get("sha256"), "Wasm runtime").read_bytes()).hexdigest()):
            raise ValueError("signed Wasm executable, version, or role differs")
        public = full_wasm_node_consumer.verify(root, repository, candidate, lane,
                                                hashes, digest, binary, replay=True)
        if (public.get("status") != "PASSED" or public.get("selected_methods") != len(selected)
                or public.get("archive_digest") != digest):
            raise ValueError("Wasm transported bundle replay differs")
    elif family == "native-host":
        selection = expected.get("expected_native_selection")
        toolchain = expected.get("expected_native_toolchain")
        host = expected.get("expected_native_host")
        if (not isinstance(selection, dict) or not isinstance(toolchain, dict)
                or not isinstance(host, dict) or receipt.get("host") != host
                or runtime != full_native_host_consumer.digest(
                    full_native_host_consumer.encoded(host))):
            raise ValueError("signed Native host, simulator, or runtime selection differs")
        full_native_host_consumer.validate_host(lane, selection, host)
        windows = host["system"] == "Windows"
        for key, sha_key in (("gradle_executable", "gradle_sha256"),
                             ("python_executable", "python_sha256")):
            _file(toolchain.get(key), toolchain.get(sha_key), key)
        _file(Path(toolchain.get("java_home", "")) / "bin" /
              ("java.exe" if windows else "java"),
              toolchain.get("java_sha256"), "JDK 21")
        native_home = Path(toolchain.get("native_home", ""))
        _file(native_home / "bin" /
              ("kotlinc-native.bat" if windows else "kotlinc-native"),
              toolchain.get("native_sha256"),
              "Kotlin Native compiler")
        _file(native_home / "konan/lib/kotlin-native-compiler-embeddable.jar",
              toolchain.get("native_compiler_sha256"), "Kotlin Native compiler JAR")
        public = full_native_host_consumer.verify(root, repository, candidate, lane,
                                                  hashes, selection, digest, toolchain)
        if (public.get("status") != "PASSED" or public.get("selected_cases") != len(selected)
                or public.get("archive_sha256") != digest):
            raise ValueError("Native host public replay differs")
        products = independent_gates._json(root / "runtime/products.json")
        executable_hashes = {name: products[name]["sha256"] for name in ("core", "facade")}
        if executable_hashes != expected.get("expected_native_host_executables"):
            raise ValueError("Native host executable bytes differ from signed audit")
        execution_witness(expected, candidate, lane, digest, runtime,
                          selected_lane["configuration"], executable_hashes,
                          hashes, toolchain["java_sha256"], root,
                          _launcher(toolchain["gradle_executable"],
                                    toolchain["gradle_sha256"],
                                    receipt["process"]["command"]))
    elif family == "android-native":
        guest = expected.get("expected_android_native_guest")
        toolchain = expected.get("expected_android_native_toolchain")
        binaries = expected.get("expected_android_native_executables")
        adb = expected.get("expected_android_native_adb")
        serial = expected.get("expected_android_native_serial")
        replay_output = expected.get("expected_android_native_replay_output")
        if (not isinstance(guest, dict) or not isinstance(toolchain, dict)
                or not isinstance(binaries, dict) or set(binaries) != {"core", "facade"}
                or any(SHA.fullmatch(str(value)) is None for value in binaries.values())
                or runtime != independent_gates.digest(guest)
                or independent_gates._json(independent_gates._file_path(
                    root, receipt.get("guest_record"))) != guest
                or type(serial) is not str or not serial
                or type(replay_output) is not str):
            raise ValueError("signed Android Native guest, ABI, or executable identity differs")
        _file(adb, toolchain.get("adb_sha256"), "ADB")
        paths = expected.get("expected_android_native_executable_paths")
        if not isinstance(paths, dict) or set(paths) != {"java", "gradle", "adb"}:
            raise ValueError("signed Android Native build executable paths are missing")
        for name, key in (("java", "java_sha256"), ("gradle", "gradle_sha256"),
                          ("adb", "adb_sha256")):
            _file(paths[name], toolchain.get(key), name)
        if Path(paths["adb"]) != Path(adb):
            raise ValueError("signed Android Native ADB path differs")
        token = PUBLIC_REPLAY_ACTIVE.set(True)
        try:
            public = full_android_native_consumer.verify(
                repository, candidate, lane, root, digest, hashes, runtime, binaries,
                toolchain, adb, serial, replay_output)
        finally:
            PUBLIC_REPLAY_ACTIVE.reset(token)
        if (public.get("status") != "PASSED" or public.get("selected_cases") != len(selected)
                or public.get("archive_sha256") != digest):
            raise ValueError("Android Native device replay differs")
        build_record = independent_gates._json(root / "build.json")
        execution_witness(expected, candidate, lane, digest, runtime,
                          selected_lane["configuration"], binaries, hashes,
                          toolchain["java_sha256"], root,
                          _launcher(paths["gradle"], toolchain["gradle_sha256"],
                                    build_record["process"]["command"]))
    else:
        toolchain = expected.get("expected_apple_device_toolchain")
        device = expected.get("expected_apple_device")
        if (not isinstance(toolchain, dict) or not isinstance(device, dict)
                or receipt.get("device") != device
                or runtime != f"{device.get('model')} | {device.get('os')} {device.get('version')} | {device.get('udid')}"):
            raise ValueError("signed physical Apple device or runtime identity differs")
        os_roles = expected.get("expected_apple_os_roles")
        if (not isinstance(os_roles, dict)
                or set(os_roles) != {"path", "sha256"}):
            raise ValueError("signed physical Apple OS role selection is missing")
        if type(os_roles["path"]) is not str:
            raise ValueError("independent Apple OS role selection path is invalid")
        os_roles_path = Path(os_roles["path"])
        if (not os_roles_path.is_absolute() or not os_roles_path.is_file()
                or any(path.is_symlink() for path in
                       (os_roles_path, *os_roles_path.parents))
                or os_roles_path.resolve().is_relative_to(root.resolve())):
            raise ValueError("independent Apple OS role selection must be outside the producer archive and symbolic paths")
        selection = full_apple_device_consumer.load_os_selection(
            os_roles_path, _sha(os_roles["sha256"], "Apple OS roles"))
        full_apple_device_consumer.expected_os(
            selected_lane, device.get("version"), selection)
        paths = expected.get("expected_apple_device_executable_paths")
        extra_hashes = expected.get("expected_apple_device_executable_hashes")
        if (not isinstance(paths, dict) or set(paths) !=
                {"java", "gradle", "xcrun", "xcodebuild"}
                or not isinstance(extra_hashes, dict)
                or set(extra_hashes) != {"xcrun", "xcodebuild"}):
            raise ValueError("signed physical Apple executable identities are missing")
        for name, value in (("java", toolchain.get("java_sha256")),
                            ("gradle", toolchain.get("gradle_sha256")),
                            ("xcrun", extra_hashes["xcrun"]),
                            ("xcodebuild", extra_hashes["xcodebuild"])):
            _file(paths[name], value, name)
        if (selected_lane["version"] == "current"
                and int(device["version"].split(".")[0]) <=
                full_apple_device_consumer.TARGETS[selected_lane["target"]][2]):
            raise ValueError("current physical Apple runtime repeats minimum OS family")
        public = full_apple_device_consumer.verify(
            repository, candidate, lane, root, digest, hashes, runtime, toolchain,
            str(os_roles_path), os_roles["sha256"])
        if (public.get("status") != "PASSED" or public.get("selected_cases") != len(selected)
                or public.get("archive_sha256") != digest):
            raise ValueError("physical Apple device execution differs")
    return public
