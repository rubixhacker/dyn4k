#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
sys.dont_write_bytecode = True
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "consumers/qualification/portable/full-android"
VERSION = "0.1.0-alpha.1"
MODULES = ("dyn4k-core", "dyn4k")
SOURCE_ROOTS = ("dyn4k-core/src/commonTest/kotlin", "dyn4k/src/commonTest/kotlin",
                "dyn4k-core/src/androidHostTest/kotlin")
sys.path.insert(0, str(ROOT / "tools/qualification"))
import independent_gates
sys.path.insert(0, str(ROOT / "tools/android-runtime"))
from evidence import parse_instrumentation, validate_lane
from full_evidence import validate_full_process_log
from run_full import API21_FINGERPRINTS, validate_api21_process_log, api21_process_pid
from run_optimized import dex_evidence


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def approved_cases(checkout):
    manifest = independent_gates.load_approved_manifest(checkout)
    from full_suite_manifest import validate_manifest
    validate_manifest(manifest, checkout)
    cases = [case for case in manifest["cases"] if case["scope"] == "portable"]
    if len(cases) != 2523 or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("approved portable case set differs")
    return manifest, cases


def staged_aar(staging, module):
    artifact = module + "-android"
    return (staging / "io/github/rubixhacker" / artifact / VERSION /
            f"{artifact}-{VERSION}.aar")


def original_source_hashes(checkout):
    sources = {}
    for root in SOURCE_ROOTS:
        directory = checkout / root
        if not directory.is_dir():
            raise ValueError(f"original source root is absent: {root}")
        for path in sorted(directory.rglob("*.kt")):
            if not path.is_file() or not path.resolve().is_relative_to(checkout.resolve()):
                raise ValueError(f"original source escapes checkout: {path}")
            sources[path.relative_to(checkout).as_posix()] = sha256(path)
    return sources


def verified_original_sources(checkout, archived):
    if not isinstance(archived, dict):
        raise ValueError("archived original source map is malformed")
    for key in archived:
        if (not isinstance(key, str) or "\\" in key or
                any(part in ("", ".", "..") for part in key.split("/")) or
                not any(key.startswith(root + "/") for root in SOURCE_ROOTS) or
                not key.endswith(".kt")):
            raise ValueError(f"archived original source path is foreign or unsafe: {key}")
    rebuilt = original_source_hashes(checkout)
    if archived != rebuilt:
        raise ValueError("archived original source file set or hashes differ")
    return rebuilt


def prepare(checkout, staging, output):
    manifest, cases = approved_cases(checkout)
    output.mkdir(parents=True, exist_ok=True)
    source_hashes = original_source_hashes(checkout)
    for case in cases:
        if source_hashes[case["source"]["path"]] != case["source"]["sha256"]:
            raise ValueError(f"approved source changed: {case['id']}")
    providers = {}
    for module in MODULES:
        source = staged_aar(staging, module)
        if not source.is_file():
            raise ValueError(f"staged Android AAR missing: {source}")
        target = output / f"{module}-android.aar"
        shutil.copyfile(source, target)
        with zipfile.ZipFile(target) as archive:
            classes = archive.read("classes.jar")
        jar = output / f"{module}-classes.jar"
        write(jar, classes)
        providers[module] = {"coordinate": f"io.github.rubixhacker:{module}-android:{VERSION}",
                             "staged_path": str(source), "aar_sha256": sha256(target),
                             "classes_sha256": sha256(jar)}
    asset = "\n".join("\t".join((case["id"], case["classname"], case["method"]))
                      for case in cases) + "\n"
    write(output / "assets/cases.tsv", asset)
    rules = [
        "-keepattributes RuntimeVisibleAnnotations,AnnotationDefault,InnerClasses,EnclosingMethod,Signature",
        "-keep class io.github.rubixhacker.dyn4k.qualification.fullandroid.FullCorpusExecutor { public static java.util.List runAll(android.content.Context); }",
        "-keep class io.github.rubixhacker.dyn4k.qualification.fullandroid.FullActivity { public <init>(); public void onCreate(android.os.Bundle); }",
    ]
    rules.extend(f"-keep,allowoptimization class {name} {{ *; }}" for name in
                 sorted({case["classname"] for case in cases}))
    rules.extend(f"-keep,allowobfuscation class {name}" for name in (
        "org.dyn4j.collision.CollisionModelTest$RootFilter",
        "org.dyn4j.collision.CollisionModelTest$ChildFilter",
        "org.dyn4j.collision.CollisionModelTest$OtherFilter",
        "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Parent",
        "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Child",
        "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Sibling",
        "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Unrelated",
    ))
    rules.append("-keepclassmembers class org.dyn4j.geometry.Matrix22 { public double normMax(); }")
    write(output / "full-keep.pro", "\n".join(rules) + "\n")
    return {"manifest_sha256": independent_gates.digest(manifest),
            "source_hashes": source_hashes, "providers": providers,
            "case_count": len(cases), "asset_sha256": sha256(output / "assets/cases.tsv"),
            "keep_sha256": sha256(output / "full-keep.pro")}


def gradle_command(checkout, staging, output, *tasks, build_type=None):
    command = ["/tmp/dyn4k-tools/gradle-9.5.0/bin/gradle", "--no-daemon", "--console=plain",
               f"--project-cache-dir={output / 'project-cache'}",
               "-p", str(PROJECT), f"-PqualificationRepository={staging}",
               f"-PqualificationOutput={output}", f"-PsourceCheckout={checkout}",
               f"-PcoreClasses={output / 'dyn4k-core-classes.jar'}",
               f"-PfacadeClasses={output / 'dyn4k-classes.jar'}"]
    if build_type:
        command.append(f"-PruntimeTestBuildType={build_type}")
    return command + list(tasks)


def run_command(command, path, *, env=None, check=True):
    started = time.time_ns()
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env, check=False)
    write(path, result.stdout)
    if check and result.returncode:
        raise RuntimeError(f"command exited {result.returncode}; raw output: {path}")
    return {"command": command, "exit_code": result.returncode,
            "started_ns": started, "finished_ns": time.time_ns(),
            "stdout": str(path), "stdout_sha256": sha256(path)}


def bounded_compile(checkout, staging, output):
    prepared = prepare(checkout, staging, output)
    env = os.environ.copy()
    env.update(JAVA_HOME="/tmp/dyn4k-tools/jdk21",
               ANDROID_HOME="/var/home/stewart/Android/Sdk",
               ANDROID_SDK_ROOT="/var/home/stewart/Android/Sdk",
               TMPDIR=str(output / "tmp"))
    (output / "tmp").mkdir(exist_ok=True)
    command = gradle_command(checkout, staging, output,
                             ":core-tests:jar", ":facade-tests:jar", ":app:providerArtifacts")
    result = run_command(command, output / "compile.log", env=env, check=False)
    prepared["compile"] = result
    write(output / "compile-result.json", json.dumps(prepared, indent=2, sort_keys=True) + "\n")
    if result["exit_code"]:
        raise RuntimeError(f"bounded external compile failed; raw output: {output / 'compile.log'}")
    return prepared


PACKAGE = "io.github.rubixhacker.dyn4k.qualification.fullandroid"
UMBRELLA = PACKAGE + ".FullJourneyTest#allInstalledCases"
SDK = Path("/var/home/stewart/Android/Sdk")


def adb_for_serial(serial):
    if not re.fullmatch(r"emulator-[0-9]{4}", serial) or int(serial[-4:]) % 2:
        raise ValueError(f"Android task serial is invalid: {serial}")
    return [str(SDK / "platform-tools/adb"), "-P", "5038", "-s", serial]


ADB = adb_for_serial(os.environ.get("DYN4K_ANDROID_SERIAL", "emulator-5558"))


def api21_pid_from_ps(raw, required=True):
    return api21_process_pid(raw, PACKAGE, required=required)


def capture_api21_pid(archive, phase, required=True):
    path = archive / f"ps-{phase}.txt"
    adb_capture(["shell", "ps"], path)
    pid = api21_pid_from_ps(path.read_text(), required=required)
    write(archive / f"pid-{phase}.txt", (pid or "") + "\n")
    return pid


def validate_original_rows(raw, cases, exit_code):
    observed = parse_instrumentation(raw)
    expected = {case["id"] for case in cases}
    validate_lane(observed, expected, {UMBRELLA}, exit_code)
    if observed["portable"]["passed"] != len(cases):
        raise ValueError("installed assertion count differs from approved methods")
    return observed


def xml_from_original_rows(raw, cases, exit_code):
    observations = validate_original_rows(raw, cases, exit_code)
    suite = ET.Element("testsuite", tests=str(len(cases)), failures="0", errors="0",
                       skipped="0", time="0")
    for case in cases:
        ET.SubElement(suite, "testcase", id=case["id"], classname=case["classname"],
                      name=case["method"], time="0")
    return ET.tostring(suite, encoding="utf-8", xml_declaration=True), observations


def observed_method_rows(raw):
    rows = []
    current = None
    for line in raw.splitlines():
        if line.startswith("INSTRUMENTATION_STATUS: dyn4k_case="):
            if current is not None:
                rows.append(current)
            current = {"id": line.partition("=")[2]}
        elif current is not None and line.startswith("INSTRUMENTATION_STATUS: dyn4k_status="):
            current["status"] = line.partition("=")[2]
        elif current is not None and line.startswith("INSTRUMENTATION_STATUS: dyn4k_stack="):
            current["stack"] = line.partition("=")[2]
        elif current is not None and line.startswith("INSTRUMENTATION_STATUS_CODE: "):
            current["status_code"] = line.partition(": ")[2]
    if current is not None:
        rows.append(current)
    return rows


def parsed_provider_graph(raw, prepared):
    graph = {}
    for variant in ("debug", "release"):
        start = f"DYN4K_GRAPH_BEGIN {variant}"
        end = f"DYN4K_GRAPH_END {variant}"
        if raw.count(start) != 1 or raw.count(end) != 1:
            raise ValueError(f"{variant} Maven provider graph missing or duplicate")
        artifacts = re.findall(rf"(?m)^DYN4K_GRAPH_ARTIFACT {variant} (\S+) (\S+)$", raw)
        if len(artifacts) != len(set(artifacts)):
            raise ValueError(f"{variant} Maven provider artifact duplicated")
        found = {}
        for coordinate, file_name in artifacts:
            for module in MODULES:
                if coordinate == prepared["providers"][module]["coordinate"]:
                    if module in found or sha256(file_name) != prepared["providers"][module]["aar_sha256"]:
                        raise ValueError(f"{variant} resolved {module} AAR differs")
                    found[module] = file_name
            if coordinate.startswith("org.dyn4j:dyn4j:"):
                raise ValueError("upstream dyn4j provider in external graph")
        if set(found) != set(MODULES):
            raise ValueError(f"{variant} Maven provider graph omits an AAR")
        graph[variant] = found
    return graph


def single_apk(directory):
    found = list(directory.glob("*.apk"))
    if len(found) != 1:
        raise ValueError(f"APK missing or ambiguous: {directory}")
    return found[0]


def copy_into(source, destination):
    shutil.copyfile(source, destination)
    if sha256(source) != sha256(destination):
        raise ValueError(f"artifact changed during copy: {source}")
    return sha256(destination)


def adb_capture(arguments, destination, *, check=True):
    return run_command(ADB + arguments, destination, check=check)


def installed_apk(package, archive, prefix):
    path_log = archive / f"{prefix}-package-path.txt"
    adb_capture(["shell", "pm", "path", package], path_log)
    paths = path_log.read_text().splitlines()
    if len(paths) != 1 or not re.fullmatch(r"package:/data/app/[^\n]+/base\.apk", paths[0]):
        raise ValueError(f"installed package path differs: {package}")
    target = archive / f"{prefix}-installed.apk"
    adb_capture(["pull", paths[0].removeprefix("package:"), str(target)],
                archive / f"{prefix}-pull.txt")
    return {"package_path": paths[0], "sha256": sha256(target)}


def runtime_identity(archive, expected_api):
    keys = ("ro.build.version.sdk", "ro.build.fingerprint", "ro.product.cpu.abi",
            "ro.product.cpu.abilist", "ro.product.model", "sys.boot_completed")
    props = {}
    for key in keys:
        path = archive / (key.replace(".", "-") + ".txt")
        adb_capture(["shell", "getprop", key], path)
        props[key] = path.read_text().strip()
    if props["ro.build.version.sdk"] != str(expected_api) or props["sys.boot_completed"] != "1":
        raise ValueError("installed API or boot status differs")
    if props["ro.product.cpu.abi"] != "x86_64":
        raise ValueError("installed ABI differs from approved guest")
    return props


def transformation_from_descriptors(debug, release, mapping, usage):
    mapping_text = mapping.read_text()
    usage_text = usage.read_text()
    changed = {}
    for original, target in re.findall(r"(?m)^(org\.dyn4j\.[\w.$]+) -> ([^:\s]+):$", mapping_text):
        if (target != original and not target.startswith("R8$$REMOVED$$CLASS$$")
                and "L" + original.replace(".", "/") + ";" in debug
                and "L" + target.replace(".", "/") + ";" in release):
            changed[original] = target
    removed = re.findall(r"(?m)^org\.dyn4j\.[\w.$]+(?::)?$", usage_text)
    if len(changed) < 10 or not removed or len(release) >= len(debug):
        raise ValueError("release DEX lacks genuine R8 class transformation")
    return {"debug_classes": len(debug), "release_classes": len(release),
            "transformed_classes": changed, "removed_classes": len(removed)}


def dex_transformation(debug_apk, release_apk, mapping, usage, archive):
    debug_dir, release_dir = archive / "debug-dex", archive / "release-dex"
    debug_dir.mkdir()
    release_dir.mkdir()
    debug, _ = dex_evidence(debug_apk, debug_dir, SDK)
    release, _ = dex_evidence(release_apk, release_dir, SDK)
    return transformation_from_descriptors(debug, release, mapping, usage)


def canonical_dexdump(output, relative, current_path=None):
    first, separator, remaining = output.partition(b"\n")
    second, next_separator, body = remaining.partition(b"\n")
    processing = re.fullmatch(rb"Processing '([^'\r\n]+)'\.\.\.", first)
    opened = re.fullmatch(rb"Opened '([^'\r\n]+)', DEX version '[0-9]{3}'", second)
    if not separator or not next_separator or not processing or not opened:
        raise ValueError(f"dexdump path headers are malformed: {relative}")
    path = processing.group(1)
    if path != opened.group(1):
        raise ValueError(f"dexdump path headers differ: {relative}")
    if current_path is None:
        parts = path[1:].split(b"/")
        if (not path.startswith(b"/") or b"\x00" in path or
                any(part in (b"", b".", b"..") for part in parts) or
                not path.endswith(b"/" + os.fsencode(relative))):
            raise ValueError(f"archived dexdump path headers differ from original input: {relative}")
    elif path != os.fsencode(current_path):
        raise ValueError(f"regenerated dexdump path headers differ from current input: {relative}")
    marker = b"<DEX_INPUT_PATH>"
    return (first[:processing.start(1)] + marker + first[processing.end(1):] + b"\n" +
            second[:opened.start(1)] + marker + second[opened.end(1):] + b"\n" + body)


def archived_dex_descriptors(archive, prefix, apk_name):
    directory = archive / prefix
    names = sorted(path.name for path in directory.glob("classes*.dex"))
    descriptors = set()
    with zipfile.ZipFile(archive / apk_name) as apk:
        apk_names = sorted(name for name in apk.namelist()
                           if re.fullmatch(r"classes\d*\.dex", name))
        if not names or names != apk_names:
            raise ValueError("archived DEX file set differs from APK")
        for name in names:
            if apk.read(name) != (directory / name).read_bytes():
                raise ValueError(f"archived {name} differs from installed APK build")
            command = [str(SDK / "build-tools/36.0.0/dexdump"), "-f",
                       str(directory / name)]
            run = subprocess.run(command, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, check=False)
            if run.returncode:
                raise ValueError(f"pinned dexdump failed for {prefix}/{name}: {run.returncode}")
            relative = f"{prefix}/{name}"
            archived_dump = (directory / (name + ".dexdump.txt")).read_bytes()
            archived = canonical_dexdump(archived_dump, relative)
            regenerated = canonical_dexdump(run.stdout, relative, directory / name)
            if archived != regenerated:
                raise ValueError(f"archived dexdump output differs from DEX: {prefix}/{name}")
            descriptors.update(re.findall(r"Class descriptor\s+: '([^']+)'",
                                          run.stdout.decode()))
    if not descriptors:
        raise ValueError("archived DEX class inventory is empty")
    return descriptors


def build_apks(checkout, staging, output):
    prepared = json.loads((output / "compile-result.json").read_text())
    if prepared["compile"]["exit_code"] != 0:
        raise ValueError("bounded external compile did not pass")
    env = os.environ.copy()
    env.update(JAVA_HOME="/tmp/dyn4k-tools/jdk21", ANDROID_HOME=str(SDK),
               ANDROID_SDK_ROOT=str(SDK), TMPDIR=str(output / "tmp"))
    results = {}
    for variant in ("debug", "release"):
        title = variant[0].upper() + variant[1:]
        command = gradle_command(checkout, staging, output,
                                 f":app:assemble{title}", f":app:assemble{title}AndroidTest",
                                 build_type=variant)
        results[variant] = run_command(command, output / f"build-{variant}.log",
                                       env=env, check=False)
        if results[variant]["exit_code"]:
            write(output / "build-result.json", json.dumps(results, indent=2, sort_keys=True) + "\n")
            raise RuntimeError(f"{variant} APK build failed: {output / f'build-{variant}.log'}")
    graph_raw = (output / "compile.log").read_text()
    parsed_provider_graph(graph_raw, prepared)
    write(output / "build-result.json", json.dumps(results, indent=2, sort_keys=True) + "\n")
    return prepared, results


def source_and_toolchain(checkout, prepared):
    project = checkout / PROJECT.relative_to(ROOT)
    project_files = sorted(path for path in project.rglob("*") if path.is_file()
                           and "build" not in path.parts and ".gradle" not in path.parts)
    tools = {"java": Path("/tmp/dyn4k-tools/jdk21/bin/java"),
             "javac": Path("/tmp/dyn4k-tools/jdk21/bin/javac"),
             "gradle": Path("/tmp/dyn4k-tools/gradle-9.5.0/bin/gradle"),
             "gradle_launcher": Path("/tmp/dyn4k-tools/gradle-9.5.0/lib/gradle-launcher-9.5.0.jar"),
             "adb": SDK / "platform-tools/adb",
             "dexdump": SDK / "build-tools/36.0.0/dexdump",
             "android_api36": SDK / "platforms/android-36/android.jar",
             "android_d8": SDK / "build-tools/36.0.0/lib/d8.jar",
             "python": Path(sys.executable)}
    cache = Path.home() / ".gradle/caches/modules-2/files-2.1"
    for name, pattern in (
        ("kotlin_compiler", "org.jetbrains.kotlin/kotlin-compiler-embeddable/2.4.20/*/kotlin-compiler-embeddable-2.4.20.jar"),
        ("kotlin_gradle813", "org.jetbrains.kotlin/kotlin-gradle-plugin/2.4.20/*/kotlin-gradle-plugin-2.4.20-gradle813.jar"),
        ("kotlin_gradle96", "org.jetbrains.kotlin/kotlin-gradle-plugin/2.4.20/*/kotlin-gradle-plugin-2.4.20-gradle96.jar"),
        ("android_gradle_plugin", "com.android.tools.build/gradle/9.3.1/*/gradle-9.3.1.jar"),
    ):
        found = list(cache.glob(pattern))
        if len(found) != 1:
            raise ValueError(f"pinned {name} binary is missing or ambiguous")
        tools[name] = found[0]
    return {"source_hashes": prepared["source_hashes"],
            "consumer_source_hashes": {str(path.relative_to(checkout)): sha256(path)
                                       for path in project_files},
            "producer_sha256": sha256(checkout / "tools/qualification/full_android_consumer.py"),
            "toolchain_sha256": {name: sha256(path) for name, path in tools.items()}}


def verify_archive(checkout, archive, expected_digest, expected_core_aar,
                   expected_facade_aar, expected_runtime_identity):
    import qualify
    candidate = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                                        text=True).strip()
    qualify.require_clean_checkout(checkout, candidate)
    manifest, cases = approved_cases(checkout)
    expected = {"dyn4k-core": expected_core_aar, "dyn4k": expected_facade_aar}
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) or len(set(value)) == 1
           for value in (expected_digest, *expected.values())):
        raise ValueError("independent archive digest or AAR hashes are malformed")
    if independent_gates.archive_digest(archive) != expected_digest:
        raise ValueError("independent archive digest differs")
    receipt = json.loads((archive / "receipt.json").read_text())
    if receipt["candidate_sha"] != candidate or receipt["artifact_hashes"] != expected:
        raise ValueError("candidate or independent staged AAR hashes differ")
    source = json.loads((archive / "source-toolchain.json").read_text())
    original_sources = verified_original_sources(checkout, source["source_hashes"])
    rebuilt = source_and_toolchain(checkout, {"source_hashes": original_sources})
    if source != rebuilt:
        raise ValueError("original source, consumer source, producer, or toolchain hash differs")
    asset = (archive / "cases.tsv").read_text().splitlines()
    expected_asset = ["\t".join((case["id"], case["classname"], case["method"]))
                      for case in cases]
    if asset != expected_asset:
        raise ValueError("installed selected method asset differs from approved source")
    for module, jar_name in (("dyn4k-core", "core-tests.jar"), ("dyn4k", "facade-tests.jar")):
        with zipfile.ZipFile(archive / f"{module}-android.aar") as aar:
            if aar.read("classes.jar") != (archive / f"{module}-classes.jar").read_bytes():
                raise ValueError(f"external compiler {module} classes differ from staged AAR")
        with zipfile.ZipFile(archive / jar_name) as compiled:
            names = set(compiled.namelist())
        missing = {case["classname"].replace(".", "/") + ".class" for case in cases
                   if case["module"] == module} - names
        if missing:
            raise ValueError(f"external compiled test classes are missing: {sorted(missing)[:3]}")
    compile_log = (archive / "compile.log").read_text()
    if ("BUILD SUCCESSFUL" not in compile_log
            or not all(f"> Task :{module}:compileKotlin" in compile_log
                       for module in ("core-tests", "facade-tests"))):
        raise ValueError("external assertion source compilation is absent")
    for name in ("build-debug.log", "build-release.log"):
        if "BUILD SUCCESSFUL" not in (archive / name).read_text():
            raise ValueError(f"external Android APK build did not pass: {name}")
    raw = (archive / "instrumentation.txt").read_text()
    if json.loads((archive / "observed-method-rows.json").read_text()) != observed_method_rows(raw):
        raise ValueError("observed original method rows differ from raw instrumentation")
    xml, observations = xml_from_original_rows(raw, cases, receipt["process"]["exit_code"])
    if xml != (archive / "consumer.xml").read_bytes():
        raise ValueError("consumer XML differs from original installed method rows")
    execution = json.loads((archive / "instrument-command.json").read_text())
    if (execution["logical_arguments"] != receipt["process"]["command"]
            or execution["transport_arguments"] != receipt["process"]["transport_command"]
            or receipt["lane"] not in execution["logical_arguments"]
            or shlex.quote(receipt["lane"]) not in " ".join(execution["transport_arguments"])):
        raise ValueError("installed instrumentation command differs from selected lane")
    for name, file_name in (("app", "app.apk"), ("test", "test.apk")):
        if sha256(archive / f"{name}-installed.apk") != sha256(archive / file_name):
            raise ValueError(f"installed {name} APK differs from built APK")
    runtime = json.loads((archive / "runtime.json").read_text())
    props = runtime["properties"]
    for key, value in props.items():
        if (archive / (key.replace(".", "-") + ".txt")).read_text().strip() != value:
            raise ValueError(f"raw runtime property differs: {key}")
    if props["ro.build.version.sdk"] == "21":
        selected_pid = validate_api21_process_log(
            (archive / "logcat.txt").read_text(), PACKAGE, "x86_64", runtime["before_pid"])
        if (api21_pid_from_ps((archive / "ps-before.txt").read_text()) != runtime["before_pid"]
                or api21_pid_from_ps((archive / "ps-after.txt").read_text(),
                                     required=False) is not None
                or (archive / "pid-after.txt").read_text().strip()):
            raise ValueError("API 21 process snapshots differ from selected process")
    else:
        selected_pid = validate_full_process_log((archive / "logcat.txt").read_text(), PACKAGE)
    if (runtime["before_pid"] != (archive / "pid-before.txt").read_text().strip()
            or runtime["instrumentation_pid"] != selected_pid):
        raise ValueError("selected installed process differs from raw guest log")
    debug = archived_dex_descriptors(
        archive, "debug-dex", "debug-app.apk" if receipt["configuration"] == "r8-optimized" else "app.apk")
    transformation = json.loads((archive / "transformation.json").read_text())
    if receipt["configuration"] == "r8-optimized":
        release = archived_dex_descriptors(archive, "release-dex", "app.apk")
        expected_transform = transformation_from_descriptors(
            debug, release, archive / "mapping.txt", archive / "usage.txt")
    else:
        expected_transform = {"debug_classes": len(debug)}
    if transformation != expected_transform:
        raise ValueError("archived DEX transformation differs from raw descriptors")
    if independent_gates.digest(runtime) != expected_runtime_identity:
        raise ValueError("independently selected runtime identity differs")
    lane = receipt["lane"]
    result = independent_gates.evaluate_gate(
        "staged-consumer", archive, candidate, lane, manifest["lanes"][lane], checkout,
        expected, expected_runtime_identity, expected_archive_digest=expected_digest,
        manifest=manifest)
    if result["status"] != "PASSED" or result.get("complete_selected_suite") is not True:
        raise ValueError("independent full staged-consumer gate did not pass: " + result["reason"])
    return {"gate": result, "cases": observations["portable"]["passed"],
            "candidate_sha": candidate, "archive_digest": expected_digest}


def execute_lane(checkout, staging, output, archive, variant, expected_api):
    manifest, cases = approved_cases(checkout)
    prepared = json.loads((output / "compile-result.json").read_text())
    builds = json.loads((output / "build-result.json").read_text())
    if any(builds[name]["exit_code"] != 0 for name in ("debug", "release")):
        raise ValueError("both external APK variants must build before guest execution")
    parsed_provider_graph((output / "compile.log").read_text(), prepared)
    if archive.exists():
        raise ValueError(f"raw archive already exists: {archive}")
    archive.mkdir(parents=True)
    started_ns = time.time_ns()
    lane = f"android:Android JVM:{'minimum' if expected_api == 21 else 'current'}:{'debug' if variant == 'debug' else 'r8-optimized'}"
    if lane not in manifest["lanes"]:
        raise ValueError("approved Android lane is missing")
    app_output = output / "app/outputs"
    debug_apk = single_apk(app_output / "apk/debug")
    apk = single_apk(app_output / f"apk/{variant}")
    test_apk = single_apk(app_output / f"apk/androidTest/{variant}")
    app_hash = copy_into(apk, archive / "app.apk")
    test_hash = copy_into(test_apk, archive / "test.apk")
    for module in MODULES:
        copy_into(output / f"{module}-android.aar", archive / f"{module}-android.aar")
        copy_into(output / f"{module}-classes.jar", archive / f"{module}-classes.jar")
    copy_into(output / "core-tests/libs/core-tests.jar", archive / "core-tests.jar")
    copy_into(output / "facade-tests/libs/facade-tests.jar", archive / "facade-tests.jar")
    copy_into(output / "assets/cases.tsv", archive / "cases.tsv")
    copy_into(output / "full-keep.pro", archive / "full-keep.pro")
    for name in ("compile.log", "build-debug.log", "build-release.log"):
        copy_into(output / name, archive / name)
    graph_lines = [line for line in (output / "compile.log").read_text().splitlines()
                   if line.startswith("DYN4K_GRAPH_")]
    write(archive / "provider-graph.txt", "\n".join(graph_lines) + "\n")
    if variant == "release":
        mapping_dir = output / "app/outputs/mapping/release"
        for name in ("configuration.txt", "mapping.txt", "usage.txt"):
            copy_into(mapping_dir / name, archive / name)
        debug_copy = archive / "debug-app.apk"
        copy_into(debug_apk, debug_copy)
        transformation = dex_transformation(debug_copy, archive / "app.apk",
                                            archive / "mapping.txt", archive / "usage.txt", archive)
    else:
        dex_dir = archive / "debug-dex"
        dex_dir.mkdir()
        descriptors, _ = dex_evidence(archive / "app.apk", dex_dir, SDK)
        transformation = {"debug_classes": len(descriptors)}
    identity = runtime_identity(archive, expected_api)
    if expected_api == 37 and identity["ro.build.fingerprint"] != (
            "google/sdk_gphone64_x86_64/emu64xa:17/CE2A.260420.019/15611780:user/release-keys"):
        raise ValueError("API 37 fingerprint differs from pinned guest")
    if expected_api == 21 and identity["ro.build.fingerprint"] != API21_FINGERPRINTS["x86_64"]:
        raise ValueError("API 21 fingerprint differs from pinned guest")
    adb_capture(["shell", "ps"] if expected_api == 21 else ["shell", "ps", "-A"],
                archive / "guest-processes-before.txt")
    active = (archive / "guest-processes-before.txt").read_text()
    if any(PACKAGE in row or "io.github.rubixhacker.dyn4k.full" in row
           for row in active.splitlines()):
        raise ValueError(f"another full corpus process is active on {ADB[-1]}")
    adb_capture(["install", "-r", str(archive / "app.apk")], archive / "install-app.txt")
    adb_capture(["install", "-r", str(archive / "test.apk")], archive / "install-test.txt")
    installed_app = installed_apk(PACKAGE, archive, "app")
    installed_test = installed_apk(PACKAGE + ".test", archive, "test")
    if installed_app["sha256"] != app_hash or installed_test["sha256"] != test_hash:
        raise ValueError("installed APK bytes differ from built APK bytes")
    adb_capture(["shell", "dumpsys", "package", PACKAGE], archive / "package.txt")
    adb_capture(["logcat", "-c"], archive / "logcat-clear.txt")
    adb_capture(["shell", "am", "start", "-W", "-n", PACKAGE + "/.FullActivity"],
                archive / "launch.txt")
    if expected_api == 21:
        before_pid = capture_api21_pid(archive, "before")
    else:
        adb_capture(["shell", "pidof", PACKAGE], archive / "pid-before.txt")
        before_pid = (archive / "pid-before.txt").read_text().strip()
    if not before_pid.isdigit():
        raise ValueError("installed app process is absent before instrumentation")
    adb_capture(["shell", "pm", "list", "instrumentation"], archive / "instrumentations.txt")
    runners = re.findall(r"instrumentation:(\S+) \(target=" + re.escape(PACKAGE) + r"\)",
                         (archive / "instrumentations.txt").read_text())
    if len(runners) != 1:
        raise ValueError("installed instrumentation runner differs")
    command = ADB + ["shell", "am", "instrument", "-w", "-r", "-e", "qualificationLane",
                     lane, runners[0]]
    transport = ADB + ["shell", "am instrument -w -r -e qualificationLane "
                       + shlex.quote(lane) + " " + shlex.quote(runners[0])]
    write(archive / "instrument-command.json", json.dumps(
        {"logical_arguments": command, "transport_arguments": transport},
        sort_keys=True, indent=2) + "\n")
    instrument = run_command(transport, archive / "instrumentation.txt", check=False)
    raw = (archive / "instrumentation.txt").read_text()
    write(archive / "observed-method-rows.json", json.dumps(
        observed_method_rows(raw), sort_keys=True, indent=2) + "\n")
    adb_capture(["logcat", "-d"], archive / "logcat.txt")
    logcat = (archive / "logcat.txt").read_text()
    if expected_api == 21:
        selected_pid = validate_api21_process_log(logcat, PACKAGE, "x86_64", before_pid)
    else:
        selected_pid = validate_full_process_log(logcat, PACKAGE)
    if expected_api == 21:
        capture_api21_pid(archive, "after", required=False)
    else:
        adb_capture(["shell", "pidof", PACKAGE], archive / "pid-after.txt", check=False)
    if (archive / "pid-after.txt").read_text().strip():
        raise ValueError("installed corpus process remains after instrumentation")
    runtime = {"properties": identity, "before_pid": before_pid,
               "instrumentation_pid": selected_pid,
               "app_sha256": app_hash, "test_sha256": test_hash,
               "installed_app_sha256": installed_app["sha256"],
               "installed_test_sha256": installed_test["sha256"]}
    runtime_hash = independent_gates.digest(runtime)
    source = source_and_toolchain(checkout, prepared)
    write(archive / "source-toolchain.json", json.dumps(source, sort_keys=True, indent=2) + "\n")
    write(archive / "runtime.json", json.dumps(runtime, sort_keys=True, indent=2) + "\n")
    write(archive / "transformation.json", json.dumps(transformation, sort_keys=True, indent=2) + "\n")
    xml, observations = xml_from_original_rows(raw, cases, instrument["exit_code"])
    write(archive / "consumer.xml", xml)
    raw_graph = archive / "provider-graph.txt"
    stdout = (f"QUALIFICATION_LANE={lane}\n"
              f"QUALIFICATION_PROCESS_EXIT={instrument['exit_code']}\n"
              f"QUALIFICATION_PROVIDER_GRAPH_SHA256={sha256(raw_graph)}\n"
              f"QUALIFICATION_RESOLVED_DYN4K_CORE_SHA256={sha256(archive / 'dyn4k-core-android.aar')}\n"
              f"QUALIFICATION_RESOLVED_DYN4K_SHA256={sha256(archive / 'dyn4k-android.aar')}\n"
              f"QUALIFICATION_CONSUMER_XML_SHA256={sha256(archive / 'consumer.xml')}\n")
    write(archive / "process.txt", stdout)
    write(archive / "process-stderr.txt", "")
    source_sha = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                                         text=True).strip()
    tree_sha = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD^{tree}"],
                                       text=True).strip()
    finished_ns = time.time_ns()
    files = [{"path": path.relative_to(archive).as_posix(), "sha256": sha256(path),
              "mtime_ns": path.stat().st_mtime_ns}
             for path in sorted(archive.rglob("*")) if path.is_file()]
    receipt = {"schema": 1, "status": "PASSED", "candidate_sha": source_sha,
               "source_tree": tree_sha, "lane": lane, **manifest["lanes"][lane],
               "runtime_identity": runtime_hash,
               "artifact_hashes": {module: prepared["providers"][module]["aar_sha256"]
                                   for module in MODULES},
               "consumer_group": "full-suite",
               "consumer_contract_sha256": independent_gates.digest(
                   independent_gates.consumer_contract(manifest, lane)),
               "provider_graph": "provider-graph.txt",
               "resolved_artifacts": {module: f"{module}-android.aar" for module in MODULES},
               "consumer_xml": ["consumer.xml"], "files": files,
               "process": {"command": command, "transport_command": transport,
                           "exit_code": instrument["exit_code"],
                           "instrumentation_started_ns": instrument["started_ns"],
                           "instrumentation_finished_ns": instrument["finished_ns"],
                           "started_ns": started_ns, "finished_ns": finished_ns,
                           "stdout": "process.txt", "stderr": "process-stderr.txt"},
               "original_method_rows": observations["portable"]["passed"],
               "installed": {"app": installed_app, "test": installed_test}}
    write(archive / "receipt.json", json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    return {"lane": lane, "cases": len(cases), "archive_digest": independent_gates.archive_digest(archive),
            "runtime_identity": runtime_hash, "artifact_hashes": receipt["artifact_hashes"]}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("compile", "build", "run", "verify"))
    parser.add_argument("--checkout", type=Path, default=ROOT)
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--variant", choices=("debug", "release"))
    parser.add_argument("--expected-api", type=int, choices=(21, 37))
    parser.add_argument("--expected-archive-digest")
    parser.add_argument("--expected-core-aar-sha256")
    parser.add_argument("--expected-facade-aar-sha256")
    parser.add_argument("--expected-runtime-identity")
    args = parser.parse_args(argv)
    checkout = args.checkout.resolve()
    if args.operation == "verify":
        if not (args.archive and args.expected_archive_digest and args.expected_core_aar_sha256
                and args.expected_facade_aar_sha256 and args.expected_runtime_identity):
            parser.error("verify requires archive digest, both independent AAR hashes, and runtime identity")
        print(json.dumps(verify_archive(checkout, args.archive.resolve(),
                                        args.expected_archive_digest,
                                        args.expected_core_aar_sha256,
                                        args.expected_facade_aar_sha256,
                                        args.expected_runtime_identity), sort_keys=True))
        return
    if not args.staging or not args.output:
        parser.error("compile, build, and run require staging and output")
    staging, output = args.staging.resolve(), args.output.resolve()
    if args.operation == "compile":
        result = bounded_compile(checkout, staging, output)
        print(json.dumps({"status": "PASSED", "cases": result["case_count"],
                          "source_files": len(result["source_hashes"])}))
    elif args.operation == "build":
        prepared, builds = build_apks(checkout, staging, output)
        print(json.dumps({"status": "PASSED", "cases": prepared["case_count"],
                          "builds": {name: item["exit_code"] for name, item in builds.items()}}))
    else:
        if not args.archive or not args.variant or not args.expected_api:
            parser.error("run requires archive, variant, and expected API")
        archive = args.archive.resolve()
        try:
            result = execute_lane(checkout, staging, output, archive, args.variant,
                                  args.expected_api)
        except Exception as error:
            if archive.is_dir():
                write(archive / "attempt-failure.json", json.dumps(
                    {"status": "FAILED", "error": str(error), "recorded_ns": time.time_ns()},
                    sort_keys=True, indent=2) + "\n")
            raise
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
