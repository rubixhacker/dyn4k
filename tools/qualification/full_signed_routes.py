import hashlib
import json
import platform
import re
import subprocess
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import unquote, urlparse

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
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "show", f"{candidate}:{path}"],
            stderr=subprocess.PIPE)
        if (Path(repository) / path).read_bytes() != committed:
            raise ValueError(f"public producer or central verifier differs from candidate: {path}")


def execution_witness(expected, candidate, lane, digest, runtime, mode,
                      executables, artifacts, build_executable, archive=None):
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


def _browser_response_proof(root, responses, witness):
    if (not isinstance(responses, dict) or set(responses) != {"core", "facade"}
            or witness.get("responses") != responses):
        raise ValueError("browser responses differ from independent witness")
    for short in ("core", "facade"):
        selected = independent_gates._json(root / short / "selected-bundle.json")
        assets = selected.get("assets") if isinstance(selected, dict) else None
        observed = responses[short]
        process = witness["processes"][short]
        if (not isinstance(assets, list) or not isinstance(observed, list)
                or len(observed) != len(assets) or not observed
                or len({item.get("name") for item in observed if isinstance(item, dict)})
                != len(observed)
                or {item.get("name") for item in observed} !=
                {item.get("name") for item in assets}):
            raise ValueError("browser response inventory differs from served assets")
        asset_hashes = {item["name"]: item["sha256"] for item in assets}
        for item in observed:
            if (set(item) != {"name", "sha256", "url", "status", "body_path",
                              "observed_at_ns", "browser_id"}
                    or type(item["status"]) is not int or item["status"] != 200
                    or type(item["url"]) is not str
                    or urlparse(item["url"]).scheme not in ("http", "https")
                    or not urlparse(item["url"]).netloc
                    or Path(unquote(urlparse(item["url"]).path)).name != item["name"]
                    or item["browser_id"] != selected.get("browser_id")
                    or type(item["observed_at_ns"]) is not int
                    or not process["started_ns"] <= item["observed_at_ns"] <=
                    process["finished_ns"]
                    or item["sha256"] != asset_hashes[item["name"]]):
                raise ValueError("browser HTTP response observation differs")
            body = Path(item["body_path"])
            if (not body.is_absolute() or not body.is_file() or body.is_symlink()
                    or body.resolve() != body
                    or body.is_relative_to(root.resolve()) or body.stat().st_nlink != 1
                    or hashlib.sha256(body.read_bytes()).hexdigest() != item["sha256"]
                    or hashlib.sha256((root / short / "assets" / item["name"])
                                      .read_bytes()).hexdigest() != item["sha256"]):
                raise ValueError("browser observed HTTP response body differs from archive")


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
    if lane.startswith("wasmJs:"):
        responses = expected.get("expected_browser_responses")
        witness = execution_witness(expected, candidate, lane, digest, runtime,
                                    lane.rsplit(":", 1)[1], executables, hashes,
                                    toolchain["gradle_sha256"], root)
        _browser_response_proof(root, responses, witness)
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
                          hashes, toolchain["gradle_sha256"], root)
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
        execution_witness(expected, candidate, lane, digest, runtime,
                          selected_lane["configuration"], binaries, hashes,
                          toolchain["gradle_sha256"], root)
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
