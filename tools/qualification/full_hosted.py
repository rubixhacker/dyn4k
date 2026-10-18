#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath

import artifact
import hosted
import qualify


TARGETS = hosted.TARGETS
NATIVE = set(hosted.NATIVE_TARGETS)
CONFIGS = {target: ("debug-g", "optimized-opt") for target in NATIVE}
CONFIGS["jsSafari"] = ("development", "production")
MANIFEST = "tools/qualification/full-common-corpus.json"
MAPPING = "tools/qualification/full-common-original-map.tsv"
PAIRS = "tools/qualification/full-common-reviewed-pairs.tsv"
INPUTS = (MANIFEST, MAPPING, PAIRS, "tools/qualification/foundation-probes.json",
          "tools/qualification/full_corpus.py", "tools/qualification/full_hosted.py",
          "tools/qualification/hosted.py", "tools/qualification/qualify.py",
          "tools/qualification/artifact.py", "build.gradle.kts",
          "consumers/qualification/portable/build.gradle.kts")
SOURCE_TASK = {target: f"{target}Test" for target in NATIVE}
SOURCE_TASK["jsSafari"] = "jsBrowserTest"
REVIEWED_COMMON_COUNTS = {"dyn4k-core": 2465, "dyn4k": 58}
PINNED_GRADLE = "9.5.0"
PINNED_KGP = "2.4.20"
PINNED_AGP = "9.3.1"


def require_pinned_toolchain(runtime):
    if (not isinstance(runtime, dict)
            or not re.fullmatch(r"21(?:\.\d+)+(?:\+\d+)?", str(runtime.get("java_version", "")))
            or runtime.get("gradle_version") != PINNED_GRADLE
            or runtime.get("kgp_declared_version") != PINNED_KGP
            or runtime.get("agp_declared_version") != PINNED_AGP):
        raise ValueError("hosted toolchain differs from pinned Java, Gradle, KGP, or AGP")


def declared_plugin_version(build, pattern):
    found = re.search(pattern, build)
    return found.group(1) if found else ""


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("unsafe archive path")
    path = Path(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")) \
            or ":" in path.parts[0]:
        raise ValueError("unsafe archive path")
    return path


def original_path(target, value):
    kind = PureWindowsPath if target == "mingwX64" else PurePosixPath
    path = kind(str(value))
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("original path is not absolute or safe")
    return path


def archived_file(output, name):
    path = output / relative_path(name)
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(output.resolve()):
        raise ValueError(f"missing or unsafe archive file: {name}")
    return path


def archive_copy(source, output, name):
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"missing source for archive: {source}")
    dest = output / relative_path(name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return {"path": name, "sha256": sha256(dest), "size": dest.stat().st_size,
            "modified_ns": dest.stat().st_mtime_ns}


def archive_inventory(output):
    files = []
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise ValueError("symbolic archive member")
        if path.is_file() and path.relative_to(output).as_posix() != "receipt.json":
            name = path.relative_to(output).as_posix()
            files.append({"path": name, "sha256": sha256(path),
                          "size": path.stat().st_size,
                          "modified_ns": path.stat().st_mtime_ns})
    return files


def verify_inventory(output, files):
    if not isinstance(files, list):
        raise ValueError("archive inventory is missing")
    names = [item["path"] for item in files]
    if len(names) != len(set(names)):
        raise ValueError("duplicate archive path")
    for item in files:
        path = archived_file(output, item["path"])
        if (sha256(path) != item.get("sha256") or path.stat().st_size != item.get("size")
                or path.stat().st_mtime_ns != item.get("modified_ns")):
            raise ValueError(f"archive member differs: {item['path']}")
    actual = {item["path"] for item in archive_inventory(output)}
    if actual != set(names):
        raise ValueError("unlisted or missing archive member")


def package_archive(output, archive):
    if not (output / "receipt.json").is_file() or archive.resolve().is_relative_to(output.resolve()):
        raise ValueError("full receipt or external archive destination is absent")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as packed:
        for path in sorted(output.rglob("*")):
            if path.is_symlink():
                raise ValueError("symbolic archive member")
            if not path.is_file():
                continue
            name = path.relative_to(output).as_posix()
            relative_path(name)
            info = packed.gettarinfo(str(path), arcname=name)
            info.pax_headers["dyn4k.mtime_ns"] = str(path.stat().st_mtime_ns)
            with path.open("rb") as stream:
                packed.addfile(info, stream)


def verify_transport_archive(archive, candidate_sha, target=None, candidate_repository=None):
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary)
        names = set()
        with tarfile.open(archive, "r") as packed:
            for member in packed:
                name = member.name
                relative_path(name)
                if name in names:
                    raise ValueError("duplicate transport archive path")
                names.add(name)
                if not member.isfile():
                    raise ValueError("non-file transport archive member")
                value = member.pax_headers.get("dyn4k.mtime_ns", "")
                if not re.fullmatch(r"[0-9]+", value):
                    raise ValueError("transport archive file timestamp is absent")
                if not math.isfinite(member.mtime) or int(member.mtime) != int(value) // 1_000_000_000:
                    raise ValueError("transport archive PAX timestamp differs")
                source = packed.extractfile(member)
                if source is None:
                    raise ValueError("transport archive file bytes are absent")
                destination = output / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("wb") as stream:
                    shutil.copyfileobj(source, stream)
                if destination.stat().st_size != member.size:
                    raise ValueError("transport archive file size differs")
                os.utime(destination, ns=(int(value), int(value)))
        if "receipt.json" not in names:
            raise ValueError("transport archive receipt is absent")
        receipt = qualify.load_json_strict(output / "receipt.json")
        if not isinstance(receipt, dict):
            raise ValueError("full hosted receipt must be an object")
        if receipt.get("candidate_sha") != candidate_sha or (
                target is not None and receipt.get("target") != target):
            raise ValueError("transport archive candidate or target differs")
        verify_raw_files(output, receipt, candidate_repository=candidate_repository)
        return receipt


def sha256(path):
    return qualify.digest(path)


def canonical_hash(value):
    return qualify.manifest_digest(value)


def candidate_checkout():
    return Path(__file__).resolve().parents[2]


def committed_input(repository, candidate_sha, relative):
    path = repository / relative
    raw = subprocess.check_output(["git", "-C", str(repository), "show",
                                   f"{candidate_sha}:{relative}"])
    if path.read_bytes() != raw:
        raise ValueError(f"candidate source differs: {relative}")
    return raw


def load_corpus(repository, candidate_sha):
    import full_corpus

    qualify.require_clean_checkout(repository, candidate_sha)
    manifest = json.loads(committed_input(repository, candidate_sha, MANIFEST))
    mapping = list(csv.DictReader(committed_input(repository, candidate_sha, MAPPING)
                                  .decode().splitlines(), delimiter="\t"))
    committed_input(repository, candidate_sha, PAIRS)
    problems = full_corpus.candidate_input_problems(
        repository, candidate_sha, manifest, mapping,
        repository / MANIFEST, repository / MAPPING, check_checkout=False)
    if problems:
        raise ValueError("reviewed corpus input differs: " + "; ".join(problems))
    if full_corpus.make_manifest(full_corpus.scan_sources(repository), mapping,
                                 production=True, repository=repository) != manifest:
        raise ValueError("source-derived corpus differs from candidate")
    if manifest.get("unresolved") or manifest.get("counts", {}).get("unresolved_mappings"):
        raise ValueError("reviewed corpus has unresolved mappings")
    return manifest


def expected_cases(manifest, module):
    if module not in REVIEWED_COMMON_COUNTS:
        raise ValueError(f"unknown common corpus module: {module}")
    cases = [(item["classname"], item["method"]) for item in manifest["cases"]
             if item["module"] == module and item["source_set"] == "commonTest"]
    if not cases or len(cases) != len(set(cases)):
        raise ValueError(f"empty or duplicate common cases: {module}")
    if len(cases) != REVIEWED_COMMON_COUNTS[module]:
        raise ValueError(f"reviewed common corpus count differs: {module}")
    return set(cases)


def read_reports(paths, expected, target, started_ns, finished_ns, safari_version=None):
    if not paths:
        raise ValueError("required XML reports are missing")
    seen = Counter()
    reports = []
    for path in paths:
        stat = path.stat()
        if not started_ns <= stat.st_mtime_ns <= finished_ns:
            raise ValueError(f"stale or post-invocation XML: {path}")
        raw = path.read_bytes()
        suite = ET.fromstring(raw)
        if suite.tag != "testsuite":
            raise ValueError(f"invalid XML suite: {path}")
        if not math.isfinite(float(suite.get("time", "nan"))):
            raise ValueError(f"invalid XML suite duration: {path}")
        cases = list(suite.iter("testcase"))
        actual = {"tests": len(cases),
                  "failures": sum(case.find("failure") is not None for case in cases),
                  "errors": sum(case.find("error") is not None for case in cases),
                  "skipped": sum(case.find("skipped") is not None for case in cases)}
        for key, count in actual.items():
            if suite.get(key) is None or int(suite.get(key)) != count:
                raise ValueError(f"XML {key} count differs: {path}")
        if any(actual[key] for key in ("failures", "errors", "skipped")):
            raise ValueError(f"failed, errored, or skipped XML case: {path}")
        for case in cases:
            classname, name = case.get("classname"), case.get("name")
            if not classname or not name:
                raise ValueError(f"case identity is absent: {path}")
            if (not math.isfinite(float(case.get("time", "nan")))
                    or case.find("ignored") is not None):
                raise ValueError(f"ignored or invalid case duration: {path}")
            if target == "jsSafari":
                if not classname.startswith("jsBrowserTest."):
                    raise ValueError("wrong Safari test target")
                match = re.fullmatch(r"(.+)\[js, browser, Safari[^]]+\]", name)
                if not match:
                    raise ValueError("Safari browser identity is absent")
                if safari_version and f"Safari{safari_version}," not in name:
                    raise ValueError("Safari browser version differs from runtime")
                identity = (classname.removeprefix("jsBrowserTest."), match.group(1))
            else:
                prefix, suffix = f"{target}Test.", f"[{target}]"
                if not classname.startswith(prefix) or not name.endswith(suffix):
                    raise ValueError("wrong native test target")
                identity = (classname.removeprefix(prefix), name.removesuffix(suffix))
            seen[identity] += 1
        reports.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                        "modified_ns": stat.st_mtime_ns, "cases": len(cases)})
    if set(seen) != expected or any(count != 1 for count in seen.values()):
        missing = sorted(expected - set(seen))[:3]
        extra = sorted(set(seen) - expected)[:3]
        raise ValueError(f"missing, extra, or duplicate cases: missing={missing}; extra={extra}")
    return {"expected": len(expected), "executed": sum(seen.values()),
            "case_ids": [f"{name}#{method}" for name, method in sorted(seen)],
            "reports": reports}


def run_command(command, cwd, destination, invocation_id=None):
    started = time.time_ns()
    environment = os.environ.copy()
    if invocation_id:
        environment["DYN4K_QUALIFICATION_INVOCATION"] = invocation_id
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=environment)
    stdout, stderr = process.communicate()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "stdout.txt").write_bytes(stdout)
    (destination / "stderr.txt").write_bytes(stderr)
    finished = time.time_ns()
    return {"command": command, "pid": process.pid, "exit_code": process.returncode,
            "invocation_id": invocation_id,
            "started_ns": started, "finished_ns": finished,
            "stdout_sha256": sha256(destination / "stdout.txt"),
            "stderr_sha256": sha256(destination / "stderr.txt")}


def require_test_tasks(process, folder, target, configuration, modules):
    output = (folder / "stdout.txt").read_text(errors="replace")
    if process["exit_code"] or "BUILD SUCCESSFUL" not in output:
        raise ValueError("Gradle test invocation did not succeed")
    for module in modules:
        task = f":{module}:{SOURCE_TASK[target]}" if module else f":{SOURCE_TASK[target]}"
        if not re.search(rf"^> Task {re.escape(task)}$", output, re.MULTILINE):
            raise ValueError(f"Gradle did not execute {task}")
        if target in NATIVE:
            mode = "Release" if configuration == "optimized-opt" else "Debug"
            link = f"link{mode}Test{target[0].upper()}{target[1:]}"
            link_task = f":{module}:{link}" if module else f":{link}"
            if not re.search(rf"^> Task {re.escape(link_task)}$", output, re.MULTILINE):
                raise ValueError(f"Gradle did not link the {mode} test binary")
        elif configuration == "production":
            if "jsTestTestProductionExecutableCompileSync" not in output:
                raise ValueError("production Safari test executable was not built")


def test_products(project, target, configuration, process):
    if target in NATIVE:
        binary_mode = "releaseTest" if configuration == "optimized-opt" else "debugTest"
        root = project / "build/bin" / target / binary_mode
        products = [path for path in root.glob("*") if path.is_file()
                    and path.suffix in (".kexe", ".exe")]
    else:
        binary_mode = "Production" if configuration == "production" else "Development"
        root = project / "build/compileSync/js/test" / f"test{binary_mode}Executable/kotlin"
        products = list(root.glob("*-test.js"))
    if len(products) != 1:
        raise ValueError(f"exactly one {configuration} test executable is required: {root}")
    product = products[0]
    stat = product.stat()
    if not process["started_ns"] <= stat.st_mtime_ns <= process["finished_ns"]:
        raise ValueError("test executable predates invocation")
    return {"path": str(product), "sha256": sha256(product),
            "size": stat.st_size, "modified_ns": stat.st_mtime_ns}


def product_inventory(project, target):
    root = project / "build/bin"
    result = {"root": str(root), "requested_target": str(root / target),
              "present": root.is_dir() and not root.is_symlink(),
              "entries": [], "truncated": False}
    if not result["present"]:
        return result
    hash_budget = 256 * 1024 * 1024
    def scan(directory):
        nonlocal hash_budget
        children = sorted(directory.iterdir(),
                          key=lambda path: (path.name != target, path.name)
                          if directory == root else (False, path.name))
        for path in children:
            if len(result["entries"]) == 128:
                result["truncated"] = True
                return
            metadata = path.lstat()
            kind = ("file" if stat.S_ISREG(metadata.st_mode) else
                    "directory" if stat.S_ISDIR(metadata.st_mode) else
                    "symlink" if stat.S_ISLNK(metadata.st_mode) else "other")
            entry = {"path": path.relative_to(project).as_posix(), "kind": kind,
                     "size": metadata.st_size, "mode": stat.S_IMODE(metadata.st_mode),
                     "modified_ns": metadata.st_mtime_ns}
            if kind == "file" and metadata.st_size <= hash_budget:
                entry["sha256"] = sha256(path)
                hash_budget -= metadata.st_size
            result["entries"].append(entry)
            if kind == "directory":
                scan(path)
                if result["truncated"]:
                    return
    scan(root)
    return result


def collect_test_products(projects, target, configuration, process, diagnostic, archive_root):
    products = {}
    errors = []
    for name, project in projects.items():
        try:
            products[name] = test_products(project, target, configuration, process)
        except ValueError as error:
            errors.append(f"{name}: {error}")
    if errors:
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        record = {"schema": 1, "target": target, "configuration": configuration,
                  "invocation_id": process["invocation_id"],
                  "started_ns": process["started_ns"],
                  "finished_ns": process["finished_ns"],
                  "exit_code": process["exit_code"],
                  "projects": {name: product_inventory(project, target)
                               for name, project in projects.items()}}
        diagnostic.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        relative = diagnostic.relative_to(archive_root).as_posix()
        raise ValueError("; ".join(errors) +
                         f"; product inventory {relative} SHA-256 {sha256(diagnostic)}")
    return products


def init_script(target, configuration, simulator_udid=None):
    if target == "jsSafari":
        production = configuration == "production"
        source = "\n".join((
            "gradle.beforeProject { project ->",
            "  project.plugins.withId('org.jetbrains.kotlin.multiplatform') {",
            "    project.afterEvaluate {",
            "      project.tasks.named('jsBrowserTest').configure { task ->",
            "        task.useKarma { useSafari() }",
            "        if (PRODUCTION) {",
            "          task.dependsOn('jsTestTestProductionExecutableCompileSync')",
            "          task.inputFileProperty.set(project.layout.buildDirectory.file(",
            "            'compileSync/js/test/testProductionExecutable/kotlin/' +",
            "            project.rootProject.name + '-' + project.name + '-test.js'))",
            "        }",
            "      }",
            "    }",
            "  }",
            "}", ""))
        return source.replace("PRODUCTION", "true" if production else "false")
    lines = [
        "gradle.beforeProject { project ->",
        "  project.plugins.withId('org.jetbrains.kotlin.multiplatform') {",
        "    project.afterEvaluate {",
    ]
    if configuration == "optimized-opt":
        lines += [
            "    def nativeTarget = project.kotlin.targets.findByName('TARGET')",
            "    if (nativeTarget != null) {",
            "      def kind = nativeTarget.binaries.getTest('DEBUG').buildType",
            "      nativeTarget.binaries.test([kind.class.valueOf('RELEASE')])",
            "      def release = nativeTarget.binaries.getTest('RELEASE')",
            "      project.tasks.matching { it.name == 'TARGETTest' }.configureEach { task ->",
            "        task.dependsOn('linkReleaseTest' + 'TARGET'.capitalize())",
            "        task.executable(release.outputFile)",
            "      }",
            "    }",
        ]
    if simulator_udid:
        if not re.fullmatch(r"[0-9A-Fa-f-]{36}", simulator_udid):
            raise ValueError("simulator UDID is invalid")
        lines += [
            "    project.tasks.matching { it.name == 'TARGETTest' }.configureEach { task ->",
            f"      task.device.set('{simulator_udid}')",
            "    }",
        ]
    lines += ["    }", "  }", "}", ""]
    return "\n".join(lines).replace("TARGET", target)


def graph_script(target):
    configuration = "jsCompileClasspath" if target == "jsSafari" else f"{target}CompileKlibraries"
    return "\n".join((
        "import groovy.json.JsonOutput",
        "import java.security.MessageDigest",
        "gradle.beforeProject { project ->",
        "  project.tasks.register('qualificationResolvedGraph') { task ->",
        "    task.doLast {",
        f"      def conf = project.configurations.getByName('{configuration}')",
        "      def components = conf.incoming.resolutionResult.allComponents.collect { it.id.displayName }.sort()",
        "      def artifacts = conf.resolvedConfiguration.resolvedArtifacts.collect { artifact ->",
        "        def bytes = artifact.file.bytes",
        "        [component: artifact.moduleVersion.id.toString(), file: artifact.file.absolutePath,",
        "         name: artifact.file.name, size: bytes.length,",
        "         sha256: MessageDigest.getInstance('SHA-256').digest(bytes).encodeHex().toString()]",
        "      }.sort { a, b -> a.component <=> b.component ?: a.name <=> b.name }",
        f"      println('DYN4K_RESOLVED_GRAPH=' + JsonOutput.toJson([configuration: '{configuration}',",
        "        components: components, artifacts: artifacts]))",
        "    }",
        "  }",
        "}", ""))


def parse_graph(folder, process, target, hashes, staging):
    if process["exit_code"]:
        raise ValueError("external consumer graph resolution failed")
    lines = [line.removeprefix("DYN4K_RESOLVED_GRAPH=")
             for line in (folder / "stdout.txt").read_text().splitlines()
             if line.startswith("DYN4K_RESOLVED_GRAPH=")]
    if len(lines) != 1:
        raise ValueError("external consumer graph observation is absent or duplicate")
    graph = json.loads(lines[0])
    expected_config = "jsCompileClasspath" if target == "jsSafari" else f"{target}CompileKlibraries"
    if graph.get("configuration") != expected_config:
        raise ValueError("external consumer graph configuration differs")
    artifact_target = "js" if target == "jsSafari" else target
    required = {f"{qualify.GROUP}:{qualify.target_publication_name(module, artifact_target)}:{qualify.VERSION}"
                for module in qualify.MODULES}
    artifacts = graph.get("artifacts")
    if not isinstance(artifacts, list) or not all(isinstance(item, dict) for item in artifacts):
        raise ValueError("external consumer graph artifacts are invalid")
    components = graph.get("components")
    if not isinstance(components, list) or not all(isinstance(item, str) for item in components) \
            or len(components) != len(set(components)):
        raise ValueError("external consumer dependency graph is invalid")
    for item in artifacts:
        path = original_path(target, item.get("file", ""))
        if (path.name != item.get("name") or not isinstance(item.get("size"), int)
                or isinstance(item["size"], bool) or item["size"] <= 0
                or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))):
            raise ValueError("external consumer graph artifact identity is invalid")
    staged_prefix = f"{qualify.GROUP}:"
    if not required.issubset({item.get("component") for item in artifacts}):
        raise ValueError("external consumer graph lacks staged target components")
    if Counter(item["component"] for item in artifacts
               if str(item.get("component", "")).startswith(staged_prefix)) != Counter(required):
        raise ValueError("external consumer graph has extra or duplicate staged target artifacts")
    root_components = {f"{qualify.GROUP}:{module}:{qualify.VERSION}"
                       for module in qualify.MODULES}
    if ({item for item in components if item.startswith(staged_prefix)}
            != required | root_components):
        raise ValueError("external consumer dependency graph lacks or adds staged targets")
    for module in qualify.MODULES:
        name = qualify.target_publication_name(module, artifact_target)
        matches = [item for item in artifacts if item.get("component") ==
                   f"{qualify.GROUP}:{name}:{qualify.VERSION}"]
        expected_file = original_path(target, staging) / qualify.target_binary_path(
            module, artifact_target)
        resolved_file = original_path(target, matches[0]["file"])
        cache_parts = resolved_file.parts
        cached = (len(cache_parts) >= 8 and cache_parts[-8:-2] ==
                  ("caches", "modules-2", "files-2.1", qualify.GROUP, name, qualify.VERSION)
                  and re.fullmatch(r"[0-9a-f]{40}", cache_parts[-2]))
        if (len(matches) != 1 or matches[0].get("sha256") != hashes[module]
                or (resolved_file != expected_file and not cached)):
            raise ValueError("external consumer resolved artifact differs from staging")
    return graph


def copy_reports(repository, target, destination, process, expected, safari_version=None):
    reports = []
    for module in qualify.MODULES:
        paths = sorted((repository / module / "build/test-results" /
                        SOURCE_TASK[target]).glob("TEST-*.xml"))
        checked = read_reports(paths, expected_cases(expected, module), target,
                               process["started_ns"], process["finished_ns"], safari_version)
        for item, path in zip(checked["reports"], paths):
            relative = Path("xml") / module / path.name
            to = destination / relative
            to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, to)
            item["path"] = relative.as_posix()
        reports.append({"module": module, **checked})
    return reports


def capture_consumer(repository, target, destination, process):
    manifest = qualify.load_json_strict(repository / "tools/qualification/foundation-probes.json")
    group = next(group for group in manifest["groups"]
                 if group["id"] == f"consumer-{target}")
    paths = sorted(repository.glob(group["report_pattern"]))
    expected = set(qualify.expected_probe_cases(manifest, group))
    if not paths:
        raise ValueError("staged consumer XML is missing")
    checked = read_consumer_reports(paths, expected, process)
    for item, path in zip(checked["reports"], paths):
        relative = Path("xml/consumer") / path.name
        to = destination / relative
        to.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, to)
        item["path"] = relative.as_posix()
    return checked


def read_consumer_reports(paths, expected, process):
    if not paths:
        raise ValueError("staged consumer XML is missing")
    seen = Counter()
    result = []
    for path in paths:
        if not process["started_ns"] <= path.stat().st_mtime_ns <= process["finished_ns"]:
            raise ValueError("staged consumer XML is stale")
        suite = ET.fromstring(path.read_bytes())
        if suite.tag != "testsuite" or not math.isfinite(float(suite.get("time", "nan"))):
            raise ValueError("staged consumer XML suite is invalid")
        cases = list(suite.iter("testcase"))
        for key, actual in (("tests", len(cases)),
                            ("failures", sum(c.find("failure") is not None for c in cases)),
                            ("errors", sum(c.find("error") is not None for c in cases)),
                            ("skipped", sum(c.find("skipped") is not None for c in cases))):
            if suite.get(key) is None or int(suite.get(key)) != actual or (key != "tests" and actual):
                raise ValueError("staged consumer XML is partial or failed")
        for case in cases:
            if (not case.get("classname") or not case.get("name")
                    or not math.isfinite(float(case.get("time", "nan")))
                    or case.find("ignored") is not None):
                raise ValueError("staged consumer case is invalid or ignored")
            seen[case.get("classname"), case.get("name")] += 1
        result.append({"path": str(path), "sha256": sha256(path),
                       "modified_ns": path.stat().st_mtime_ns})
    if seen != Counter(expected):
        raise ValueError("staged consumer cases are missing, extra, or duplicate")
    return {"expected": len(expected), "executed": sum(seen.values()),
            "case_ids": [f"{name}#{method}" for name, method in sorted(seen)],
            "reports": result}


def verify_staging(output, receipt):
    target = receipt["target"]
    artifact_target = "js" if target == "jsSafari" else target
    expected_names = {module for module in qualify.MODULES}
    expected_names.update(qualify.target_publication_name(module, artifact_target)
                          for module in qualify.MODULES)
    if set(receipt.get("staged_gav", [])) != {
            f"{qualify.GROUP}:{name}:{qualify.VERSION}" for name in expected_names}:
        raise ValueError("staged GAV inventory differs")
    expected_paths = set()
    ns = "{http://maven.apache.org/POM/4.0.0}"
    for name in expected_names:
        base = Path("staged") / qualify.GROUP.replace(".", "/") / name / qualify.VERSION
        suffixes = (".pom", ".module", "-sources.jar", "-javadoc.jar", "-license.md")
        if name in qualify.MODULES:
            suffixes += (".jar",)
        if artifact_target in qualify.APPLE_TARGETS and name not in qualify.MODULES:
            suffixes += ("-metadata.jar",)
        for suffix in suffixes:
            relative = base / f"{name}-{qualify.VERSION}{suffix}"
            expected_paths.update((relative.as_posix(), relative.as_posix() + ".sha256"))
        for suffix in (".pom", ".module"):
            relative = base / f"{name}-{qualify.VERSION}{suffix}"
            path = archived_file(output, relative.as_posix())
            if suffix == ".pom":
                root = ET.parse(path).getroot()
                for key, value in (("groupId", qualify.GROUP), ("artifactId", name),
                                   ("version", qualify.VERSION)):
                    if root.findtext(ns + key) != value:
                        raise ValueError("staged POM identity differs")
                dependencies = {(node.findtext(ns + "groupId"), node.findtext(ns + "artifactId"),
                                 node.findtext(ns + "version"))
                                for node in root.findall(ns + "dependencies/" + ns + "dependency")}
                if name.startswith("dyn4k-") and not name.startswith("dyn4k-core"):
                    core = name.replace("dyn4k", "dyn4k-core", 1)
                    if (qualify.GROUP, core, qualify.VERSION) not in dependencies:
                        raise ValueError("staged target POM lacks core dependency")
                if name == "dyn4k" and (qualify.GROUP, "dyn4k-core", qualify.VERSION) not in dependencies:
                    raise ValueError("staged root POM lacks core dependency")
            else:
                metadata = json.loads(path.read_text())
                component = metadata.get("component", {})
                root_name = name if name in qualify.MODULES else (
                    "dyn4k-core" if name.startswith("dyn4k-core-") else "dyn4k")
                if any(component.get(key) != value for key, value in
                       (("group", qualify.GROUP), ("module", root_name), ("version", qualify.VERSION))):
                    raise ValueError("staged Gradle metadata identity differs")
                if name not in qualify.MODULES and component.get("url") != (
                        f"../../{root_name}/{qualify.VERSION}/{root_name}-{qualify.VERSION}.module"):
                    raise ValueError("staged target metadata root link differs")
                if name in qualify.MODULES:
                    target_name = qualify.target_publication_name(name, artifact_target)
                    matches = [item.get("available-at", {}) for item in metadata.get("variants", [])
                               if item.get("available-at", {}).get("module") == target_name]
                    expected_link = {"group": qualify.GROUP, "module": target_name,
                                     "version": qualify.VERSION,
                                     "url": f"../../{target_name}/{qualify.VERSION}/{target_name}-{qualify.VERSION}.module"}
                    if not matches or any(link != expected_link for link in matches):
                        raise ValueError("staged root metadata lacks target mapping")
    hashes = receipt.get("artifact_hashes", {})
    if set(hashes) != set(qualify.MODULES):
        raise ValueError("staged artifact hash inventory differs")
    for module in qualify.MODULES:
        relative = Path("staged") / qualify.target_binary_path(module, artifact_target)
        binary = archived_file(output, relative.as_posix())
        sidecar = archived_file(output, relative.as_posix() + ".sha256")
        expected_paths.update((relative.as_posix(), relative.as_posix() + ".sha256"))
        if sha256(binary) != hashes[module] or sidecar.read_text().strip().lower() != hashes[module]:
            raise ValueError("archived staged artifact differs from receipt")
    staged = {item["path"] for item in receipt["files"] if item["path"].startswith("staged/")}
    if staged != expected_paths:
        raise ValueError("staged artifact archive inventory differs")


def capture_dokka_output(repository, output, receipt):
    modules = {}
    for module in qualify.MODULES:
        generated = repository / module / "build/dokka/html"
        if not generated.is_dir() or generated.is_symlink():
            raise ValueError(f"{module}: generated Dokka output is missing or unsafe")
        entries = {}
        for source in sorted(generated.rglob("*")):
            if source.is_symlink():
                raise ValueError(f"{module}: generated Dokka output has a symbolic link")
            if source.is_file():
                relative = source.relative_to(generated).as_posix()
                relative_path(relative)
                copied = archive_copy(source, output, f"dokka/{module}/{relative}")
                entries[relative] = copied["sha256"]
        if not entries:
            raise ValueError(f"{module}: generated Dokka output is empty")
        jar = archived_file(output, (Path("staged") / qualify.GROUP.replace(".", "/") /
                                     module / qualify.VERSION /
                                     f"{module}-{qualify.VERSION}-javadoc.jar").as_posix())
        qualify.validate_generated_docs(jar, output / "dokka" / module,
                                        committed_input(repository, receipt["candidate_sha"], "LICENSE.md"))
        modules[module] = entries
    receipt["dokka_provenance"] = {
        "schema": 1, "candidate_sha": receipt["candidate_sha"],
        "source_tree_sha256": receipt["source_tree_sha256"],
        "stage_stdout_sha256": receipt["stage"]["stdout_sha256"],
        "modules": modules,
    }


def verify_staged_content(output, receipt, repository):
    contract = receipt.get("staged_content_contract")
    if not isinstance(contract, dict):
        raise ValueError("staged publication content contract is absent")
    if not (repository / ".git").exists():
        raise ValueError("staged publication candidate Git checkout is absent")
    candidate_sha = receipt["candidate_sha"]
    try:
        candidate_sources = qualify.candidate_source_contract(repository, candidate_sha)
        license_bytes = committed_input(repository, candidate_sha, "LICENSE.md")
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("staged publication candidate source is unavailable") from error
    if contract.get("sources") != candidate_sources:
        raise ValueError("staged sources differ from exact candidate")
    license_path = archived_file(output, "LICENSE.md")
    if license_path.read_bytes() != license_bytes:
        raise ValueError("staged license differs from exact candidate")
    docs = contract.get("api_docs_sha256")
    if not isinstance(docs, dict) or set(docs) != set(qualify.MODULES):
        raise ValueError("staged API documentation contract is invalid")
    provenance = receipt.get("dokka_provenance")
    stage = receipt.get("stage")
    if (not isinstance(provenance, dict)
            or set(provenance) != {"schema", "candidate_sha", "source_tree_sha256",
                                   "stage_stdout_sha256", "modules"}
            or provenance["schema"] != 1 or provenance["candidate_sha"] != candidate_sha
            or provenance["source_tree_sha256"] != receipt.get("source_tree_sha256")
            or not isinstance(stage, dict)
            or provenance["stage_stdout_sha256"] != stage.get("stdout_sha256")
            or not isinstance(provenance["modules"], dict)
            or set(provenance["modules"]) != set(qualify.MODULES)):
        raise ValueError("archived Dokka provenance differs from candidate or staging process")
    expected_dokka = set()
    for module in qualify.MODULES:
        name = f"{module}-{qualify.VERSION}-javadoc.jar"
        relative = Path("staged") / qualify.GROUP.replace(".", "/") / module / qualify.VERSION / name
        jar = archived_file(output, relative.as_posix())
        entries = provenance["modules"][module]
        if not isinstance(entries, dict) or not entries:
            raise ValueError("archived Dokka file inventory is absent")
        for name, digest in entries.items():
            path = relative_path(name)
            if (path.as_posix() != name or not qualify.SHA64.fullmatch(str(digest))):
                raise ValueError("archived Dokka file identity is invalid")
            archive_name = f"dokka/{module}/{name}"
            expected_dokka.add(archive_name)
            archived = archived_file(output, archive_name)
            if sha256(archived) != digest:
                raise ValueError("archived Dokka file differs from provenance")
            modified = archived.stat().st_mtime_ns
            if not stage["started_ns"] <= modified <= stage["finished_ns"]:
                raise ValueError("archived Dokka file predates staging invocation")
        qualify.validate_generated_docs(jar, output / "dokka" / module, license_bytes)
        if sha256(jar) != docs[module]:
            raise ValueError("staged API documentation differs from audited checkout")
    actual_dokka = {item["path"] for item in receipt["files"]
                    if item["path"].startswith("dokka/")}
    if actual_dokka != expected_dokka:
        raise ValueError("archived Dokka file inventory differs")
    target = "js" if receipt["target"] == "jsSafari" else receipt["target"]
    audit = qualify.audit_staging(output / "staged", candidate_sha, [target], license_path,
                                  content_contract=contract)
    if audit["status"] != "PASSED" or audit["content_contract"] != contract:
        raise ValueError("archived staged publication differs from content audit: "
                         + "; ".join(audit["errors"]))


def verify_process(output, folder, process, invocation, required_task=None):
    if (process.get("invocation_id") != invocation or process.get("exit_code") != 0
            or type(process.get("pid")) is not int or process["pid"] <= 0
            or type(process.get("started_ns")) is not int
            or type(process.get("finished_ns")) is not int
            or process["started_ns"] <= 0 or process["finished_ns"] < process["started_ns"]):
        raise ValueError("archived process exit, identity, or timestamps differ")
    command = process.get("command")
    if not isinstance(command, list) or required_task not in command:
        raise ValueError("archived process command lacks required task")
    for stream in ("stdout", "stderr"):
        name = (folder / f"{stream}.txt").relative_to(output).as_posix()
        log = archived_file(output, name)
        if sha256(log) != process.get(f"{stream}_sha256"):
            raise ValueError("archived process log differs from receipt")
        if not process["started_ns"] <= log.stat().st_mtime_ns <= process["finished_ns"]:
            raise ValueError("archived process log timestamp differs from invocation")
    if "BUILD SUCCESSFUL" not in (folder / "stdout.txt").read_text(errors="replace"):
        raise ValueError("archived process did not complete successfully")


def verify_report_group(output, folder, group, checked, prefix):
    if (group.get("expected") != checked["expected"]
            or group.get("executed") != checked["executed"]
            or group.get("case_ids") != checked["case_ids"]):
        raise ValueError("archived case identities differ from source inventory")
    reports = group.get("reports")
    if not isinstance(reports, list) or len(reports) != len(checked["reports"]):
        raise ValueError("archived XML report inventory differs")
    actual = {item["path"]: item for item in checked["reports"]}
    if len(actual) != len(reports):
        raise ValueError("duplicate archived XML report")
    for item in reports:
        path = relative_path(item["path"])
        if path.parts[:len(prefix)] != prefix or path.as_posix() not in actual:
            raise ValueError("archived XML path or report identity differs")
        found = actual[path.as_posix()]
        if item["sha256"] != found["sha256"] or item["modified_ns"] != found["modified_ns"]:
            raise ValueError("archived XML differs from receipt")


def verify_raw_files(output, receipt, manifest=None, consumer_manifest=None,
                     candidate_repository=None):
    repository = candidate_repository or Path(__file__).resolve().parents[2]
    target = receipt.get("target")
    if (target not in TARGETS or receipt.get("status") != "FULL_COMMON_PASSED"
            or receipt.get("schema") != 2 or receipt.get("kind") != "hosted-full-common-corpus"
            or not qualify.SHA40.fullmatch(str(receipt.get("candidate_sha", "")))):
        raise ValueError("full hosted receipt is not a completed target")
    lanes = receipt.get("configurations")
    if not isinstance(lanes, list) or [lane.get("configuration") for lane in lanes] != list(CONFIGS[target]):
        raise ValueError("both required configurations are absent, duplicated, or unordered")
    if manifest is None:
        manifest = load_corpus(repository, receipt["candidate_sha"])
    if consumer_manifest is None:
        consumer_manifest = qualify.load_json_strict(
            repository / "tools/qualification/foundation-probes.json")
    if (receipt.get("manifest_sha256") != canonical_hash(manifest)
            or receipt.get("source_tree_sha256") != manifest["source_tree_sha256"]
            or receipt.get("map_sha256") != sha256(repository / MAPPING)
            or receipt.get("reviewed_pairs_sha256") != sha256(repository / PAIRS)):
        raise ValueError("source or manifest hash differs")
    for module in qualify.MODULES:
        expected_cases(manifest, module)
    if hosted.runtime_status(target, receipt.get("runtime"))[0] != "READY":
        raise ValueError("runner or runtime identity differs")
    require_pinned_toolchain(receipt["runtime"])
    simulator_family = hosted.NATIVE_TARGETS.get(target, (None, None, None))[2]
    if simulator_family:
        selected = receipt.get("selected_simulator")
        if (not isinstance(selected, dict)
                or selected not in receipt["runtime"].get("simulators", {}).get(simulator_family, [])
                or not re.fullmatch(r"[0-9A-Fa-f-]{36}", str(selected.get("udid", "")))):
            raise ValueError("selected simulator is not bound to runtime observation")
    if not all(receipt.get(key) for key in ("github_run_id", "github_job", "runner_name",
                                             "runner_os", "runner_arch", "archive_root")):
        raise ValueError("GitHub runner identity is absent")
    original_root = original_path(target, receipt["archive_root"])
    staging_root = original_path(target, receipt["staging_repository"])
    repository_root = original_path(target, receipt["repository_root"])
    wrapper = repository_root / ("gradlew.bat" if target == "mingwX64" else "gradlew")
    consumer_root = repository_root / "consumers/qualification/portable"
    if staging_root != repository_root / "build/staging-repository":
        raise ValueError("staging repository path differs from checkout")
    system = receipt["runtime"]["system"]
    expected_os = "Windows" if system == "Windows" else "macOS"
    expected_arch = "ARM64" if receipt["runtime"]["machine"].lower() == "arm64" else "X64"
    if receipt["runner_os"] != expected_os or receipt["runner_arch"] != expected_arch:
        raise ValueError("GitHub runner OS or architecture differs")
    verify_inventory(output, receipt.get("files"))
    verify_staging(output, receipt)
    verify_staged_content(output, receipt, candidate_repository or candidate_checkout())
    stage = receipt.get("stage")
    if not isinstance(stage, dict):
        raise ValueError("staging process is absent")
    verify_process(output, output / "stage", stage, None,
                   ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository")
    if (not stage["command"] or original_path(target, stage["command"][0]) != wrapper
            or "--rerun-tasks" not in stage["command"]):
        raise ValueError("staging wrapper differs from checkout")
    for item in receipt["files"]:
        if item["path"].startswith("staged/") and not (
                stage["started_ns"] <= item["modified_ns"] <= stage["finished_ns"]):
            raise ValueError("staged publication predates staging invocation")
    artifact_target = "js" if target == "jsSafari" else target
    for module in qualify.MODULES:
        for task in (f":{module}:publishKotlinMultiplatformPublicationToStagingRepository",
                     f":{module}:publish{artifact_target[0].upper()}{artifact_target[1:]}PublicationToStagingRepository"):
            if task not in stage["command"]:
                raise ValueError("staging command lacks root or target publication")
    for path in INPUTS:
        archived = archived_file(output, f"inputs/{path}")
        if sha256(archived) != sha256(repository / path):
            raise ValueError("archived source input differs")
    expected_inputs = {f"inputs/{path}" for path in INPUTS}
    if {item["path"] for item in receipt["files"] if item["path"].startswith("inputs/")} != expected_inputs:
        raise ValueError("archived source input inventory differs")
    for source in manifest["source_files"]:
        name = source["path"]
        path = archived_file(output, f"sources/{name}")
        if sha256(path) != source["sha256"]:
            raise ValueError("archived source file differs from reviewed corpus")
    expected_source_paths = {f"sources/{item['path']}" for item in manifest["source_files"]}
    if {item["path"] for item in receipt["files"] if item["path"].startswith("sources/")} != expected_source_paths:
        raise ValueError("archived source inventory differs")
    group = next(item for item in consumer_manifest["groups"] if item["id"] == f"consumer-{target}")
    expected_consumer = set(qualify.expected_probe_cases(consumer_manifest, group))
    seen_invocations = set()
    expected_xml = set()
    expected_executables = set()
    expected_resolved = set()
    for lane in lanes:
        if lane.get("status") != "FULL_COMMON_PASSED":
            raise ValueError("configuration is incomplete")
        config = lane["configuration"]
        invocation = lane.get("invocation_id")
        if not isinstance(invocation, str) or not re.fullmatch(r"[0-9a-f]{32}", invocation) \
                or invocation in seen_invocations:
            raise ValueError("configuration invocation is absent or duplicate")
        seen_invocations.add(invocation)
        if simulator_family and lane.get("simulator_udid") != receipt["selected_simulator"]["udid"]:
            raise ValueError("configuration simulator differs from runtime observation")
        folder = output / config
        graph_script_path = archived_file(output, f"{config}/qualification-graph.init.gradle")
        if graph_script_path.read_text() != graph_script(target):
            raise ValueError("consumer graph task script differs")
        source_script_path = archived_file(output, f"{config}/qualification.init.gradle")
        simulator = receipt.get("selected_simulator", {}).get("udid")
        if source_script_path.read_text() != init_script(target, config, simulator):
            raise ValueError("source test task script differs")
        for process_name, task in (("source", f":dyn4k-core:{SOURCE_TASK[target]}"),
                                   ("consumer", SOURCE_TASK[target]),
                                   ("graph", "qualificationResolvedGraph")):
            process = lane[f"{process_name}_process"]
            verify_process(output, folder / process_name, process, invocation, task)
            command = process["command"]
            if not command or original_path(target, command[0]) != wrapper:
                raise ValueError("process wrapper differs from checkout")
            if f"-PqualificationInvocationId={invocation}" not in command:
                raise ValueError("process command lacks bound invocation")
            if process_name in ("consumer", "graph") and (
                    f"-PqualificationRepository={receipt['staging_repository']}" not in command):
                raise ValueError("external consumer repository provenance is absent")
            if process_name in ("consumer", "graph") and (
                    "-p" not in command or str(consumer_root) not in command):
                raise ValueError("external consumer project invocation is absent")
            if process_name in ("source", "consumer") and "--rerun-tasks" not in command:
                raise ValueError("test process did not force execution")
            if process_name in ("source", "graph"):
                script = source_script_path if process_name == "source" else graph_script_path
                original = original_root / script.relative_to(output).as_posix()
                if "--init-script" not in command or str(original) not in command:
                    raise ValueError("test or graph init script is unbound")
            if process_name == "source" and f":dyn4k:{SOURCE_TASK[target]}" not in command:
                raise ValueError("facade source test task is absent")
            if target == "jsSafari" and process_name == "source" and config == "production" \
                    and "-PqualificationProduction=true" not in command:
                raise ValueError("Safari production source mode is absent")
            if target == "jsSafari" and process_name == "consumer" \
                    and "-PqualificationSafari=true" not in command:
                raise ValueError("Safari consumer browser mode is absent")
        source_process = lane["source_process"]
        consumer_process = lane["consumer_process"]
        graph_process = lane["graph_process"]
        if not (stage["finished_ns"] <= source_process["started_ns"]
                <= source_process["finished_ns"] <= consumer_process["started_ns"]
                <= consumer_process["finished_ns"] <= graph_process["started_ns"]):
            raise ValueError("archived process order differs from staged test invocation")
        require_test_tasks(lane["source_process"], folder / "source", target, config, qualify.MODULES)
        require_test_tasks(lane["consumer_process"], folder / "consumer", target, config, ("",))
        source = lane.get("source")
        if not isinstance(source, list) or [item.get("module") for item in source] != list(qualify.MODULES):
            raise ValueError("both core and facade source groups are required")
        for item in source:
            module = item["module"]
            paths = [archived_file(output, f"{config}/{record['path']}")
                     for record in item["reports"]]
            checked = read_reports(paths, expected_cases(manifest, module), target,
                                   lane["source_process"]["started_ns"],
                                   lane["source_process"]["finished_ns"],
                                   receipt["runtime"].get("safari_version"))
            for report in checked["reports"]:
                report["path"] = Path(report["path"]).relative_to(folder).as_posix()
                expected_xml.add(f"{config}/{report['path']}")
            verify_report_group(output, folder, item, checked, ("xml", module))
        consumer = lane.get("consumer")
        paths = [archived_file(output, f"{config}/{record['path']}")
                 for record in consumer["reports"]]
        checked = read_consumer_reports(paths, expected_consumer, lane["consumer_process"])
        for report in checked["reports"]:
            report["path"] = Path(report["path"]).relative_to(folder).as_posix()
            expected_xml.add(f"{config}/{report['path']}")
        verify_report_group(output, folder, consumer, checked, ("xml", "consumer"))
        if set(lane.get("source_executables", {})) != set(qualify.MODULES):
            raise ValueError("source test executable inventory differs")
        for name, product in [*lane["source_executables"].items(), ("consumer", lane["consumer_executable"])]:
            path = archived_file(output, product["archive_path"])
            expected_executables.add(product["archive_path"])
            if path.parent.relative_to(output).as_posix() != f"{config}/executables/{name}":
                raise ValueError("test executable archive path differs")
            project = consumer_root if name == "consumer" else repository_root / name
            if target in NATIVE:
                mode = "releaseTest" if config == "optimized-opt" else "debugTest"
                expected_parent = project / "build/bin" / target / mode
            else:
                mode = "Production" if config == "production" else "Development"
                expected_parent = project / "build/compileSync/js/test" / f"test{mode}Executable/kotlin"
            executable = original_path(target, product.get("path", ""))
            if executable.parent != expected_parent or executable.name != path.name:
                raise ValueError("test executable target or configuration path differs")
            if (sha256(path) != product["sha256"] or path.stat().st_size != product["size"]
                    or path.stat().st_mtime_ns != product["modified_ns"]
                    or product["size"] <= 0):
                raise ValueError("archived test executable differs")
            process = lane["consumer_process"] if name == "consumer" else lane["source_process"]
            if not process["started_ns"] <= product["modified_ns"] <= process["finished_ns"]:
                raise ValueError("test executable predates invocation")
        graph = parse_graph(folder / "graph", lane["graph_process"], target,
                            receipt["artifact_hashes"], receipt["staging_repository"])
        if graph != lane.get("consumer_graph"):
            raise ValueError("external consumer graph differs from archived observation")
        archived_graph = lane.get("resolved_artifacts")
        if not isinstance(archived_graph, list) or len(archived_graph) != len(graph["artifacts"]):
            raise ValueError("resolved dependency artifact archive is incomplete")
        for index, (item, archived) in enumerate(zip(graph["artifacts"], archived_graph)):
            expected_name = f"{config}/resolved-artifacts/{index:03d}-{item['name']}"
            if (archived.get("archive_path") != expected_name
                    or any(archived.get(key) != item.get(key) for key in
                           ("component", "file", "name", "size", "sha256"))):
                raise ValueError("resolved dependency artifact provenance differs")
            resolved = archived_file(output, expected_name)
            if sha256(resolved) != item["sha256"] or resolved.stat().st_size != item["size"]:
                raise ValueError("resolved dependency artifact bytes differ")
            expected_resolved.add(expected_name)
    archived_xml = {item["path"] for item in receipt["files"] if "/xml/" in item["path"]}
    archived_executables = {item["path"] for item in receipt["files"]
                            if "/executables/" in item["path"]}
    archived_resolved = {item["path"] for item in receipt["files"]
                         if "/resolved-artifacts/" in item["path"]}
    if (archived_xml != expected_xml or archived_executables != expected_executables
            or archived_resolved != expected_resolved):
        raise ValueError("extra or missing XML, executable, or resolved artifact archive member")


def run(target, candidate_sha, output):
    repository = Path(__file__).resolve().parents[2]
    output.mkdir(parents=True, exist_ok=True)
    output = output.resolve()
    receipt = {"schema": 2, "kind": "hosted-full-common-corpus", "candidate_sha": candidate_sha,
               "target": target, "status": "NOT_RUN", "configurations": [],
               "archive_root": str(output),
               "repository_root": str(repository),
               "github_run_id": os.environ.get("GITHUB_RUN_ID"),
               "github_job": os.environ.get("GITHUB_JOB"),
               "runner_name": os.environ.get("RUNNER_NAME"),
               "runner_os": os.environ.get("RUNNER_OS"),
               "runner_arch": os.environ.get("RUNNER_ARCH")}
    try:
        if target not in TARGETS or not qualify.SHA40.fullmatch(candidate_sha):
            raise ValueError("target or candidate SHA is invalid")
        manifest = load_corpus(repository, candidate_sha)
        receipt["manifest_sha256"] = canonical_hash(manifest)
        receipt["source_tree_sha256"] = manifest["source_tree_sha256"]
        receipt["map_sha256"] = sha256(repository / MAPPING)
        receipt["reviewed_pairs_sha256"] = sha256(repository / PAIRS)
        for path in INPUTS:
            archive_copy(repository / path, output, f"inputs/{path}")
        for source in manifest["source_files"]:
            archive_copy(repository / source["path"], output, f"sources/{source['path']}")
        runtime = hosted.discover_runtime(target)
        receipt["runtime"] = runtime
        status, reason = hosted.runtime_status(target, runtime)
        if status != "READY":
            receipt.update(status=status, reason=reason)
            return receipt
        wrapper = hosted.gradle_wrapper(repository)
        runtime["gradle_version"] = hosted.tool_version([wrapper, "--version"],
                                                         r"Gradle ([0-9.]+)")
        build = (repository / "build.gradle.kts").read_text()
        runtime["kgp_declared_version"] = declared_plugin_version(
            build, r'kotlin\("multiplatform"\) version "([^"]+)"')
        runtime["agp_declared_version"] = declared_plugin_version(
            build, r'id\("com\.android\.kotlin\.multiplatform\.library"\) version "([^"]+)"')
        require_pinned_toolchain(runtime)
        simulator_udid = None
        simulator_family = hosted.NATIVE_TARGETS.get(target, (None, None, None))[2]
        if simulator_family:
            devices = runtime.get("simulators", {}).get(simulator_family, [])
            if not devices or not isinstance(devices[0], dict):
                raise ValueError("available simulator identity is absent")
            chosen = devices[0]
            simulator_udid = chosen.get("udid")
            receipt["selected_simulator"] = chosen
        artifact_target = "js" if target == "jsSafari" else target
        stage = [wrapper, "--no-daemon", "--console=plain", "--rerun-tasks"]
        for module in qualify.MODULES:
            stage += [f":{module}:publishKotlinMultiplatformPublicationToStagingRepository",
                      f":{module}:publish{artifact_target[0].upper()}{artifact_target[1:]}PublicationToStagingRepository"]
        receipt["stage"] = run_command(stage, repository, output / "stage")
        if receipt["stage"]["exit_code"]:
            raise ValueError("staging command failed")
        staging = repository / "build/staging-repository"
        receipt["staging_repository"] = str(staging)
        receipt["artifact_hashes"] = hosted.target_hashes(staging, artifact_target)
        (receipt["staged_gav"], _, staged_hashes,
         receipt["staged_content_contract"]) = artifact.capture_staging(
             repository, output, [artifact_target], candidate_sha)
        if staged_hashes[artifact_target] != receipt["artifact_hashes"]:
            raise ValueError("staged artifact capture differs from target hashes")
        capture_dokka_output(repository, output, receipt)
        for config in CONFIGS[target]:
            folder = output / config
            folder.mkdir()
            lane = {"configuration": config, "invocation_id": uuid.uuid4().hex,
                    "status": "NOT_RUN"}
            receipt["configurations"].append(lane)
            try:
                script = init_script(target, config, simulator_udid)
                init = folder / "qualification.init.gradle"
                init.write_text(script)
                args = ["--init-script", str(init)] if script else []
                for module in qualify.MODULES:
                    pattern = repository / module / "build/test-results" / SOURCE_TASK[target]
                    for old in pattern.glob("TEST-*.xml"):
                        old.unlink()
                command = [wrapper, "--no-daemon", "--console=plain", "--rerun-tasks", *args,
                           f":dyn4k-core:{SOURCE_TASK[target]}", f":dyn4k:{SOURCE_TASK[target]}",
                           f"-PqualificationInvocationId={lane['invocation_id']}"]
                if target == "jsSafari" and config == "production":
                    command.append("-PqualificationProduction=true")
                lane["source_process"] = run_command(command, repository, folder / "source",
                                                      lane["invocation_id"])
                require_test_tasks(lane["source_process"], folder / "source", target, config,
                                   qualify.MODULES)
                lane["source_executables"] = collect_test_products(
                    {module: repository / module for module in qualify.MODULES},
                    target, config, lane["source_process"],
                    folder / "product-inventory-source.json", output)
                for module, product in lane["source_executables"].items():
                    name = f"{config}/executables/{module}/{Path(product['path']).name}"
                    archive_copy(Path(product["path"]), output, name)
                    product["archive_path"] = name
                lane["source"] = copy_reports(repository, target, folder,
                                               lane["source_process"], manifest,
                                               runtime.get("safari_version"))
                consumer = repository / "consumers/qualification/portable"
                for old in (consumer / "build/test-results" / SOURCE_TASK[target]).glob("TEST-*.xml"):
                    old.unlink()
                consumer_command = [wrapper, "-p", str(consumer), "--no-daemon", "--console=plain",
                                    "--rerun-tasks", *args, SOURCE_TASK[target],
                                    f"-PqualificationRepository={staging}",
                                    f"-PqualificationInvocationId={lane['invocation_id']}"]
                if target == "jsSafari":
                    consumer_command.append("-PqualificationSafari=true")
                lane["consumer_process"] = run_command(consumer_command, repository,
                                                        folder / "consumer", lane["invocation_id"])
                require_test_tasks(lane["consumer_process"], folder / "consumer", target, config,
                                   ("",))
                lane["consumer_executable"] = collect_test_products(
                    {"consumer": consumer}, target, config, lane["consumer_process"],
                    folder / "product-inventory-consumer.json", output)["consumer"]
                product = lane["consumer_executable"]
                name = f"{config}/executables/consumer/{Path(product['path']).name}"
                archive_copy(Path(product["path"]), output, name)
                product["archive_path"] = name
                lane["consumer"] = capture_consumer(repository, target, folder,
                                                     lane["consumer_process"])
                graph_init = folder / "qualification-graph.init.gradle"
                graph_init.write_text(graph_script(target))
                graph_command = [wrapper, "-p", str(consumer), "--no-daemon", "--console=plain",
                                 "--init-script", str(graph_init), "qualificationResolvedGraph",
                                 f"-PqualificationRepository={staging}",
                                 f"-PqualificationInvocationId={lane['invocation_id']}"]
                lane["graph_process"] = run_command(graph_command, repository,
                                                     folder / "graph", lane["invocation_id"])
                lane["consumer_graph"] = parse_graph(folder / "graph", lane["graph_process"],
                                                       target, receipt["artifact_hashes"], staging)
                lane["resolved_artifacts"] = []
                for index, item in enumerate(lane["consumer_graph"]["artifacts"]):
                    name = f"{config}/resolved-artifacts/{index:03d}-{item['name']}"
                    archived = archive_copy(Path(item["file"]), output, name)
                    if archived["sha256"] != item["sha256"] or archived["size"] != item["size"]:
                        raise ValueError("resolved dependency changed after graph observation")
                    lane["resolved_artifacts"].append({**item, "archive_path": name})
                if simulator_udid:
                    lane["simulator_udid"] = simulator_udid
                lane["status"] = "FULL_COMMON_PASSED"
            except (OSError, ValueError, ET.ParseError) as error:
                lane.update(status="FAILED", reason=str(error))
        load_corpus(repository, candidate_sha)
        if all(lane["status"] == "FULL_COMMON_PASSED" for lane in receipt["configurations"]):
            receipt.update(status="FULL_COMMON_PASSED",
                           reason="source-derived common core and facade cases and staged consumers ran")
            receipt["files"] = archive_inventory(output)
            verify_raw_files(output, receipt, manifest)
        else:
            receipt.update(status="FAILED", reason="one or more hosted configurations failed")
    except (ImportError, OSError, ValueError, KeyError, subprocess.CalledProcessError,
            ET.ParseError) as error:
        receipt.update(status="FAILED", reason=str(error))
        if receipt["configurations"]:
            receipt["configurations"][-1]["status"] = "FAILED"
    finally:
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS)
    parser.add_argument("--candidate-sha")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--archive", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--package", action="store_true")
    mode.add_argument("--verify-tar", action="store_true")
    args = parser.parse_args()
    if args.package:
        if not args.output or not args.archive:
            parser.error("--package requires --output and --archive")
        package_archive(args.output, args.archive)
        print(json.dumps({"archive": str(args.archive), "packaged": True}))
        return 0
    if args.verify_tar:
        if not args.archive or not args.target or not args.candidate_sha:
            parser.error("--verify-tar requires --archive, --target, and --candidate-sha")
        receipt = verify_transport_archive(args.archive, args.candidate_sha, args.target)
        print(json.dumps({"status": receipt["status"], "verified": True}))
        return 0
    if args.verify:
        if not args.output:
            parser.error("--verify requires --output")
        receipt = qualify.load_json_strict(args.output / "receipt.json")
        if (args.target and args.target != receipt.get("target")) or (
                args.candidate_sha and args.candidate_sha != receipt.get("candidate_sha")):
            raise ValueError("verify target or candidate SHA differs from receipt")
        verify_raw_files(args.output, receipt)
        print(json.dumps({"status": receipt["status"], "verified": True}))
        return 0
    if not args.target or not args.candidate_sha or not args.output:
        parser.error("--target, --candidate-sha, and --output are required for execution")
    result = run(args.target, args.candidate_sha, args.output)
    print(json.dumps({"status": result["status"], "reason": result.get("reason")}))
    return 0 if result["status"] == "FULL_COMMON_PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
