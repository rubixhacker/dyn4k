#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import full_corpus
import qualify


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / full_corpus.MANIFEST_PATH
VERSION = "0.1.0-alpha.1"
MODULES = ("dyn4k-core", "dyn4k")
JDK = {"java8": Path("/tmp/dyn4k-tools/jdk8"),
       "current": Path("/tmp/dyn4k-tools/jdk21")}
BUILD_JDK = JDK["current"]
GRADLE = Path("/tmp/dyn4k-tools/gradle-9.5.0")
SOURCE = Path("/tmp/dyn4k-upstream-6.0.0")
NATIVE_MODES = {"debug": "Debug", "optimized": "Release"}
JUNIT_HELPER = r'''import java.io.FileOutputStream;
import java.util.ArrayList;
import java.util.List;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamWriter;
import org.junit.runner.Description;
import org.junit.runner.JUnitCore;
import org.junit.runner.Result;
import org.junit.runner.notification.Failure;
import org.junit.runner.notification.RunListener;

public final class PinnedCorpusReport {
    private static final class Case {
        final String className;
        final String name;
        String status = "passed";
        String detail = "";
        Case(Description description) {
            className = description.getClassName() == null ? "unknown" : description.getClassName();
            name = description.getMethodName() == null ? description.getDisplayName() : description.getMethodName();
        }
    }
    public static void main(String[] args) throws Exception {
        if (args.length < 2) throw new IllegalArgumentException("XML path and test classes required");
        List<Case> cases = new ArrayList<Case>();
        JUnitCore core = new JUnitCore();
        core.addListener(new RunListener() {
            private Case active;
            @Override public void testStarted(Description description) {
                active = new Case(description);
                cases.add(active);
            }
            @Override public void testFailure(Failure failure) {
                if (active != null) { active.status = "failure"; active.detail = failure.getTrace(); }
            }
            @Override public void testAssumptionFailure(Failure failure) {
                if (active != null) { active.status = "skipped"; active.detail = failure.getTrace(); }
            }
            @Override public void testIgnored(Description description) {
                Case ignored = new Case(description);
                ignored.status = "skipped";
                cases.add(ignored);
            }
            @Override public void testFinished(Description description) { active = null; }
        });
        Class<?>[] classes = new Class<?>[args.length - 1];
        for (int index = 1; index < args.length; index++) classes[index - 1] = Class.forName(args[index]);
        Result result = core.run(classes);
        XMLStreamWriter xml = XMLOutputFactory.newFactory().createXMLStreamWriter(new FileOutputStream(args[0]), "UTF-8");
        xml.writeStartDocument("UTF-8", "1.0");
        xml.writeStartElement("testsuite");
        xml.writeAttribute("tests", Integer.toString(cases.size()));
        xml.writeAttribute("failures", Integer.toString(result.getFailureCount()));
        xml.writeAttribute("errors", "0");
        xml.writeAttribute("skipped", Integer.toString(result.getIgnoreCount()));
        for (Case entry : cases) {
            xml.writeStartElement("testcase");
            xml.writeAttribute("classname", entry.className);
            xml.writeAttribute("name", entry.name);
            xml.writeAttribute("time", "0");
            if (!entry.status.equals("passed")) {
                xml.writeStartElement(entry.status);
                xml.writeCharacters(entry.detail);
                xml.writeEndElement();
            }
            xml.writeEndElement();
        }
        xml.writeEndElement();
        xml.writeEndDocument();
        xml.close();
        System.out.println("ACTUAL_TESTS=" + cases.size());
        System.out.println("FAILURES=" + result.getFailureCount());
        System.out.println("IGNORED=" + result.getIgnoreCount());
        if (!result.wasSuccessful() || result.getIgnoreCount() != 0) System.exit(1);
    }
}
'''


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def jvm_flags(mode):
    if mode == "default":
        return []
    if mode == "no-optimize":
        return ["-Xno-optimize"]
    raise ValueError(f"unknown JVM compiler mode: {mode}")


def gradle_flag_line(module, flags):
    return f"JVM compiler flags :{module}: [{', '.join(flags)}]"


def jvm_build_tasks():
    return (
        ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
        ":dyn4k:publishKotlinMultiplatformPublicationToStagingRepository",
        ":dyn4k-core:publishJvmPublicationToStagingRepository",
        ":dyn4k:publishJvmPublicationToStagingRepository",
        ":dyn4k-core:jvmTest", ":dyn4k:jvmTest",
    )


def native_build_tasks(mode):
    build = NATIVE_MODES[mode]
    return (
        ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
        ":dyn4k:publishKotlinMultiplatformPublicationToStagingRepository",
        ":dyn4k-core:publishLinuxX64PublicationToStagingRepository",
        ":dyn4k:publishLinuxX64PublicationToStagingRepository",
        f":dyn4k-core:link{build}TestLinuxX64",
        f":dyn4k:link{build}TestLinuxX64",
    )


def native_consumer_command_problems(output, consumer, artifact, mode):
    project = output / "external-native-consumer"
    task = f"link{NATIVE_MODES[mode]}TestLinuxX64"
    compile_command = [str(ROOT / "gradlew"), "-p", str(project), "--offline",
                       "--no-daemon", "--max-workers=1", "--rerun-tasks",
                       "--console=plain", task]
    compile_log = output / "logs/consumer-compile.log"
    executable = output / artifact["path"]
    problems = []
    if consumer["compile"].get("command") != compile_command:
        problems.append("Native staged consumer link command differs")
    compiled = consumer["compile"]
    raw = compile_log.read_text(errors="replace")
    if (compiled.get("log") != str(compile_log)
            or compiled.get("log_sha256") != digest(compile_log)
            or compiled.get("exit_code") != 0
            or not re.search(r"^> Task :" + re.escape(task) + r"\s*$", raw, re.M)
            or not re.search(r"^BUILD SUCCESSFUL\b", raw, re.M)):
        problems.append("Native staged consumer link log differs")
    if (consumer["elf"] != artifact or consumer["process"].get("command") != [str(executable)]
            or digest(executable) != artifact["sha256"]):
        problems.append("Native staged consumer executable differs")
    return problems


def compile_process_problems(process, expected_command, expected_log, *, split_streams=False):
    problems = []
    if process.get("command") != expected_command or process.get("exit_code") != 0:
        problems.append("compile command or result differs")
    if (process.get("log") != str(expected_log)
            or process.get("log_sha256") != digest(expected_log)):
        problems.append("compile log differs")
    if split_streams:
        stdout = expected_log.with_suffix(".stdout")
        stderr = expected_log.with_suffix(".stderr")
        if (process.get("stdout") != str(stdout)
                or process.get("stdout_sha256") != digest(stdout)
                or process.get("stderr") != str(stderr)
                or process.get("stderr_sha256") != digest(stderr)
                or expected_log.read_bytes() != stdout.read_bytes() + stderr.read_bytes()):
            problems.append("compile stdout, stderr, or combined log differs")
    return problems


def jvm_consumer_evidence_problems(output, consumer, artifacts, dependencies):
    runtime = consumer["runtime"]
    if runtime not in JDK:
        return ["staged Java/Kotlin consumer runtime differs"]
    project = output / "external-jvm-consumer"
    compile_command = [str(ROOT / "gradlew"), "-p", str(project), "--offline",
                       "--no-daemon", "--max-workers=1", "--rerun-tasks",
                       "--console=plain", "classes"]
    compile_log = output / "logs" / f"consumer-compile-{runtime}.log"
    problems = compile_process_problems(consumer["compile"], compile_command, compile_log)
    raw_compile = compile_log.read_text(errors="replace")
    if ("BUILD SUCCESSFUL" not in raw_compile
            or any(not re.search(r"^> Task :" + task + r"\s*$", raw_compile, re.M)
                   for task in ("compileKotlin", "compileJava", "classes"))):
        problems.append("staged Java/Kotlin compile task evidence differs")
    classpath = [project / "build/classes/kotlin/main", project / "build/classes/java/main",
                 output / artifacts["dyn4k-core"]["path"],
                 output / artifacts["dyn4k"]["path"], *dependencies]
    execution_command = [str(JDK[runtime] / "bin/java"), "-cp",
                         os.pathsep.join(map(str, classpath)), "qualification.ConsumerKt"]
    execution_log = output / "logs" / f"consumer-{runtime}.log"
    process = consumer["process"]
    if (process.get("command") != execution_command or process.get("exit_code") != 0
            or process.get("log") != str(execution_log)
            or process.get("log_sha256") != digest(execution_log)
            or "STAGED_CONSUMER_PASSED kotlin=2 java=1" not in execution_log.read_text()):
        problems.append("staged Java/Kotlin consumer execution differs")
    return problems


def jvm_report_command_problems(output, report, manifest, artifacts, dependencies,
                                compiled_tests):
    runtime = report["runtime"]
    if runtime not in JDK:
        return ["JVM report runtime differs"]
    if report["kind"] == "full-common":
        module = report["module"]
        if module not in MODULES:
            return ["JVM report module differs"]
        classes = sorted({name for name, _ in expected_cases(manifest, module, "jvm")})
        classpath = [*retained_test_classpath(output, compiled_tests, module),
                     *retained_test_classpath(output, compiled_tests, "dyn4k-core"),
                     output / artifacts["dyn4k-core"]["path"],
                     output / artifacts["dyn4k"]["path"], *dependencies]
    elif report["kind"] == "unchanged-java":
        _, classes = original_classes()
        classpath = [output / "original-classes",
                     output / artifacts["dyn4k-core"]["path"], *dependencies]
    else:
        return ["JVM report kind differs"]
    command = [str(JDK[runtime] / "bin/java"), "-cp",
               os.pathsep.join(str(path) for path in [*classpath, output / "helper-classes"]),
               "PinnedCorpusReport", str(output / report["file"]["path"]), *classes]
    return [] if report["process"].get("command") == command else ["JVM report command differs"]


def build_evidence_problems(process, raw, target, mode):
    tasks = jvm_build_tasks() if target == "jvm" else native_build_tasks(mode)
    command = process.get("command", [])
    problems = []
    if (process.get("exit_code") != 0 or command[-len(tasks):] != list(tasks)
            or any(option not in command for option in
                   ("--offline", "--no-daemon", "--max-workers=1", "--rerun-tasks",
                    "--console=plain")) or "BUILD SUCCESSFUL" not in raw):
        problems.append("full configuration build command or result differs")
    for task in tasks:
        if not re.search(r"^> Task " + re.escape(task) + r"\s*$", raw, re.M):
            problems.append(f"executed Gradle task missing: {task}")
    selected = [item for item in command if item.startswith("-PjvmCompilerMode=")]
    if target == "jvm":
        if selected != [f"-PjvmCompilerMode={mode}"]:
            problems.append("JVM compiler mode property differs")
        for module in MODULES:
            if (gradle_flag_line(module, jvm_flags(mode)) not in raw
                    or not re.search(r"^> Task :" + re.escape(module) +
                                     r":compileKotlinJvm\s*$", raw, re.M)):
                problems.append(f"compiler task flags missing: {module}")
    elif selected:
        problems.append("Native build contains JVM mode property")
    return problems


def verify_xml(paths, expected):
    seen = Counter()
    for path in paths:
        suite = ET.parse(path).getroot()
        if suite.tag != "testsuite":
            raise ValueError(f"invalid test suite: {path}")
        cases = list(suite.iter("testcase"))
        counts = {"tests": len(cases),
                  "failures": sum(item.find("failure") is not None for item in cases),
                  "errors": sum(item.find("error") is not None for item in cases),
                  "skipped": sum(item.find("skipped") is not None for item in cases)}
        if any(int(suite.get(key, "-1")) != count for key, count in counts.items()):
            raise ValueError(f"suite count differs: {path}")
        if any(counts[key] for key in ("failures", "errors", "skipped")):
            raise ValueError(f"failed or skipped cases: {path}")
        for item in cases:
            identity = (item.get("classname"), item.get("name"))
            if not all(identity) or list(item):
                raise ValueError(f"invalid case: {path}")
            seen[identity] += 1
    if seen != Counter(expected):
        raise ValueError(f"missing, extra, or duplicate cases: expected {len(expected)}, observed {sum(seen.values())}")
    return sum(seen.values())


def verify_original_xml(path, mappings):
    suite = ET.parse(path).getroot()
    cases = list(suite.iter("testcase"))
    if suite.tag != "testsuite" or len(cases) != len(mappings):
        raise ValueError("unchanged Java case count differs")
    for key, value in (("tests", len(cases)), ("failures", 0), ("errors", 0), ("skipped", 0)):
        if suite.get(key) != str(value):
            raise ValueError("unchanged Java suite failed or skipped")
    expected = Counter()
    for row in mappings:
        owner, method = row["original"].split("#", 1)
        expected[owner, method.split("[", 1)[0]] += 1
    actual = Counter()
    identities = set()
    for case in cases:
        owner, method = case.get("classname"), case.get("name")
        if not owner or not method or (owner, method) in identities or list(case):
            raise ValueError("unchanged Java case is missing, duplicate, or failed")
        identities.add((owner, method))
        actual[owner, method.split("[", 1)[0]] += 1
    if actual != expected:
        raise ValueError("unchanged Java identities differ from pinned source map")
    return len(cases)


def check_artifacts(root, receipt, mode):
    problems = []
    if receipt.get("mode") != mode:
        problems.append("compiler mode differs")
    for name, item in receipt.get("artifacts", {}).items():
        try:
            relative = Path(item["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("unsafe path")
            if digest(Path(root) / relative) != item["sha256"]:
                raise ValueError("SHA-256 differs")
        except (OSError, KeyError, TypeError, ValueError) as error:
            problems.append(f"{name}: {error}")
    if not receipt.get("artifacts"):
        problems.append("artifacts missing")
    return problems


def environment():
    result = dict(os.environ)
    result["JAVA_HOME"] = str(BUILD_JDK)
    result["PATH"] = f"{BUILD_JDK}/bin:{GRADLE}/bin:" + result.get("PATH", "")
    result["ANDROID_HOME"] = "/var/home/stewart/Android/Sdk"
    result["ANDROID_SDK_ROOT"] = result["ANDROID_HOME"]
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    return result


def execute(command, log, *, cwd=ROOT, env=None, timeout=7200, split_streams=False):
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.time_ns()
    if split_streams:
        result = subprocess.run(command, cwd=cwd, env=env or environment(), capture_output=True,
                                check=False, timeout=timeout)
        stdout = log.with_suffix(".stdout")
        stderr = log.with_suffix(".stderr")
        stdout.write_bytes(result.stdout)
        stderr.write_bytes(result.stderr)
        log.write_bytes(result.stdout + result.stderr)
    else:
        with log.open("wb") as stream:
            result = subprocess.run(command, cwd=cwd, env=env or environment(), stdout=stream,
                                    stderr=subprocess.STDOUT, check=False, timeout=timeout)
    record = {"command": [str(part) for part in command], "exit_code": result.returncode,
              "started_ns": started, "finished_ns": time.time_ns(),
              "log": str(log), "log_sha256": digest(log)}
    if split_streams:
        record.update({"stdout": str(stdout), "stdout_sha256": digest(stdout),
                       "stderr": str(stderr), "stderr_sha256": digest(stderr)})
    return record


def require_success(result):
    if result["exit_code"]:
        raise ValueError(f"command exited {result['exit_code']}: {result['log']}")


def gradle(output, name, *tasks, property_args=()):
    command = [str(ROOT / "gradlew"), "--offline", "--no-daemon", "--max-workers=1",
               "--rerun-tasks", "--console=plain", "--info", *property_args, *tasks]
    result = execute(command, output / "logs" / f"{name}.log")
    require_success(result)
    return result


def dependency(name, version):
    matches = sorted(Path.home().joinpath(".gradle/caches/modules-2/files-2.1").glob(
        f"**/{name}/{version}/*/{name}-{version}.jar"))
    if len(matches) != 1:
        raise ValueError(f"pinned dependency unavailable or ambiguous: {name} {version}")
    return matches[0]


def staged_binary(staging, module, target):
    name = qualify.target_publication_name(module, target)
    suffix = "jar" if target == "jvm" else "klib"
    return staging / "io/github/rubixhacker" / name / VERSION / f"{name}-{VERSION}.{suffix}"


def snapshot_staging(output, target):
    source = ROOT / "build/staging-repository"
    destination = output / "staged"
    if destination.exists():
        raise ValueError("mode stage already exists")
    shutil.copytree(source, destination)
    artifacts = {}
    for module in MODULES:
        binary = staged_binary(destination, module, target)
        if not binary.is_file():
            raise ValueError(f"staged {module} {target} binary missing")
        base = binary.parent
        for suffix in (".pom", ".module"):
            descriptor = base / (binary.stem + suffix)
            if not descriptor.is_file():
                raise ValueError(f"staged metadata missing: {descriptor}")
        sidecar = binary.with_name(binary.name + ".sha256")
        if not sidecar.is_file() or sidecar.read_text().strip().lower() != digest(binary):
            raise ValueError(f"staged checksum differs: {binary}")
        artifacts[module] = {"path": binary.relative_to(output).as_posix(),
                             "sha256": digest(binary)}
    return artifacts


def expected_cases(manifest, module, host):
    return {(case["classname"], case["method"]) for case in manifest["cases"]
            if case["module"] == module and host in case["hosts"]}


def checked_source(candidate):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if candidate != head:
        raise ValueError("candidate SHA differs from checkout")
    problems = full_corpus.candidate_checkout_problems(ROOT, candidate)
    if problems:
        raise ValueError("; ".join(problems))
    committed = full_corpus.committed_bytes(ROOT, candidate, full_corpus.MANIFEST_PATH)
    if MANIFEST.read_bytes() != committed:
        raise ValueError("source manifest differs from candidate commit")
    manifest = json.loads(committed)
    if full_corpus.make_manifest(full_corpus.scan_sources(ROOT), manifest["original_mappings"],
                                 production=True, repository=ROOT) != manifest:
        raise ValueError("source-derived corpus differs from committed manifest")
    source_head = subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"],
                                          text=True).strip()
    if source_head != full_corpus.ORIGINAL_REVISION:
        raise ValueError("pinned original Java source revision differs")
    return manifest


def staged_file_hashes(output):
    stage = output / "staged"
    return {path.relative_to(output).as_posix(): digest(path)
            for path in sorted(stage.rglob("*")) if path.is_file()}


def record_file(output, path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"evidence file missing: {path}")
    return {"path": path.relative_to(output).as_posix(), "sha256": digest(path)}


def preserve_file(output, source, name):
    target = output / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return record_file(output, target)


def runtime_identity(jdk):
    java = jdk / "bin/java"
    result = subprocess.run([str(java), "-version"], capture_output=True, text=True,
                            check=False)
    if result.returncode:
        raise ValueError(f"runtime unavailable: {java}")
    return {"path": str(java.resolve()), "sha256": digest(java),
            "version": (result.stdout + result.stderr).strip()}


def jvm_dependencies():
    return [dependency("kotlin-stdlib", "2.4.20"),
            dependency("kotlin-test", "2.4.20"),
            dependency("kotlin-test-junit", "2.4.20"),
            dependency("junit", "4.13.1"),
            dependency("hamcrest-core", "1.3"),
            dependency("annotations", "26.0.2-1")]


def test_class_locations(module):
    return ((f"{module}/build/classes/kotlin/jvm/test", f"test-classes/{module}/kotlin"),
            (f"{module}/build/classes/java/jvmTest", f"test-classes/{module}/java"),
            (f"{module}/build/processedResources/jvm/test", f"test-classes/{module}/resources"))


def snapshot_jvm_test_classes(output):
    snapshots = {}
    for module in MODULES:
        snapshots[module] = []
        for source_name, retained_name in test_class_locations(module):
            source = ROOT / source_name
            if not source.is_dir():
                continue
            retained = output / retained_name
            shutil.copytree(source, retained)
            files = {path.relative_to(retained).as_posix(): digest(path)
                     for path in sorted(retained.rglob("*")) if path.is_file()}
            snapshots[module].append({"source": source_name, "path": retained_name,
                                      "files": files})
        if (not snapshots[module]
                or not any(name.endswith(".class") for item in snapshots[module]
                           for name in item["files"])):
            raise ValueError(f"compiled JVM tests missing: {module}")
    return snapshots


def retained_test_classpath(output, compiled_tests, module):
    return [output / item["path"] for item in compiled_tests[module]]


def compiled_test_evidence_problems(output, compiled_tests):
    if not isinstance(compiled_tests, dict) or set(compiled_tests) != set(MODULES):
        return ["compiled JVM test classpath missing"]
    problems = []
    for module in MODULES:
        records = compiled_tests[module]
        known = test_class_locations(module)
        declared = [(item["source"], item["path"]) for item in records]
        if (not records or not any(name.endswith(".class") for item in records
                                   for name in item["files"])
                or declared != [pair for pair in known if pair in declared]):
            problems.append(f"compiled JVM test classpath differs: {module}")
        for item in records:
            if (item["source"], item["path"]) not in known:
                continue
            retained = output / item["path"]
            if (not retained.is_dir()
                    or {path.relative_to(retained).as_posix(): digest(path)
                        for path in sorted(retained.rglob("*")) if path.is_file()}
                    != item["files"]):
                problems.append(f"compiled JVM test bytes differ: {module}")
    return problems


def compile_helper(output, dependencies):
    source = output / "PinnedCorpusReport.java"
    source.write_text(JUNIT_HELPER)
    classes = output / "helper-classes"
    classes.mkdir()
    command = [str(JDK["java8"] / "bin/javac"), "-source", "8", "-target", "8",
               "-cp", os.pathsep.join(str(path) for path in dependencies),
               "-d", str(classes), str(source)]
    result = execute(command, output / "logs/compile-helper.log")
    require_success(result)
    return classes, result


def junit_run(output, name, runtime, classes, classpath, helper):
    xml = output / "xml" / f"{name}.xml"
    xml.parent.mkdir(parents=True, exist_ok=True)
    command = [str(JDK[runtime] / "bin/java"), "-cp",
               os.pathsep.join(str(path) for path in [*classpath, helper]),
               "PinnedCorpusReport", str(xml), *classes]
    result = execute(command, output / "logs" / f"{name}.log", timeout=3600)
    return xml, result


def original_classes():
    source = SOURCE / "src/test/java"
    files = sorted(source.rglob("*.java"))
    classes = sorted(".".join(path.relative_to(source).with_suffix("").parts)
                     for path in files if "@Test" in path.read_text(errors="replace")
                     or "@RunWith" in path.read_text(errors="replace"))
    if len(files) != 199 or len(classes) != 190:
        raise ValueError(f"pinned original inventory differs: {len(files)} files, {len(classes)} classes")
    return files, classes


def original_source_args(source_files):
    return "\n".join('"' + str(path) + '"' for path in source_files)


def original_compile_command(output, archive, dependencies):
    classpath = os.pathsep.join(str(path) for path in [archive, *dependencies])
    return [str(JDK["java8"] / "bin/javac"), "-source", "8", "-target", "8",
            "-encoding", "UTF-8", "-cp", classpath, "-d",
            str(output / "original-classes"), "@" + str(output / "original-sources.args")]


def original_compile_evidence_problems(output, record, archive, dependencies):
    source_files, _ = original_classes()
    argfile = output / "original-sources.args"
    problems = []
    if (record.get("source_count") != 199
            or record.get("argfile") != record_file(output, argfile)
            or argfile.read_text() != original_source_args(source_files)):
        problems.append("unchanged Java source list differs")
    problems.extend(compile_process_problems(
        record["process"], original_compile_command(output, archive, dependencies),
        output / "logs/compile-originals.log", split_streams=True))
    return problems


def run_originals(output, archive, runtime, dependencies, helper, mappings, receipt):
    source_files, classes = original_classes()
    compiled = output / "original-classes"
    if not compiled.is_dir():
        compiled.mkdir()
        argfile = output / "original-sources.args"
        argfile.write_text(original_source_args(source_files))
        command = original_compile_command(output, archive, dependencies)
        process = execute(command, output / "logs/compile-originals.log", timeout=3600,
                          split_streams=True)
        receipt["original_compile"] = {"process": process, "argfile": record_file(output, argfile),
                                       "source_count": len(source_files)}
        require_success(process)
        resources = SOURCE / "src/test/resources"
        if resources.is_dir():
            shutil.copytree(resources, compiled, dirs_exist_ok=True)
    elif "original_compile" not in receipt:
        raise ValueError("unchanged Java compile record missing")
    xml, process = junit_run(output, f"original-{runtime}", runtime, classes,
                             [compiled, archive, *dependencies], helper)
    require_success(process)
    verify_original_xml(xml, mappings)
    return xml, process


def jvm_test_run(output, manifest, artifacts, compiled_tests, runtime, dependencies, helper):
    reports = []
    for module in MODULES:
        expected = expected_cases(manifest, module, "jvm")
        classes = sorted({name for name, _ in expected})
        classpath = [*retained_test_classpath(output, compiled_tests, module),
                     *retained_test_classpath(output, compiled_tests, "dyn4k-core"),
                     output / artifacts["dyn4k-core"]["path"],
                     output / artifacts["dyn4k"]["path"], *dependencies]
        xml, process = junit_run(output, f"{module}-{runtime}", runtime, classes,
                                 classpath, helper)
        error = None
        try:
            if process["exit_code"]:
                raise ValueError(f"JUnit process exited {process['exit_code']}")
            count = verify_xml([xml], expected)
        except (OSError, ValueError, ET.ParseError) as failure:
            error = str(failure)
            count = len(ET.parse(xml).getroot().findall("testcase")) if xml.is_file() else 0
        reports.append({"module": module, "runtime": runtime, "kind": "full-common",
                        "count": count, "file": record_file(output, xml), "process": process,
                        "status": "UNPASSED" if error else "PASSED", "error": error})
    return reports


def run_consumer_jvm(output, runtime, artifacts, dependencies):
    stage = output / "staged"
    project = output / "external-jvm-consumer"
    if not project.exists():
        project.mkdir()
        (project / "settings.gradle.kts").write_text('rootProject.name = "compiler-mode-consumer"\n')
        (project / "build.gradle.kts").write_text(
            'import org.jetbrains.kotlin.gradle.dsl.JvmTarget\n'
            'plugins { kotlin("jvm") version "2.4.20"; application }\n'
            f'repositories {{ maven {{ url = uri("{stage}") }}; mavenCentral() }}\n'
            f'dependencies {{ implementation("io.github.rubixhacker:dyn4k:{VERSION}") }}\n'
            'kotlin { jvmToolchain(21); compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) } }\n'
            'tasks.withType<JavaCompile>().configureEach { options.release.set(8) }\n'
            'application { mainClass = "qualification.ConsumerKt" }\n')
        for language, name in (("kotlin", "Consumer.kt"), ("java", "JavaMigration.java")):
            source = ROOT / "consumers/qualification/src/main" / language / "qualification" / name
            target = project / "src/main" / language / "qualification" / name
            target.parent.mkdir(parents=True)
            target.write_bytes(source.read_bytes())
    command = [str(ROOT / "gradlew"), "-p", str(project),
               "--offline", "--no-daemon", "--max-workers=1", "--rerun-tasks",
               "--console=plain", "classes"]
    compile_result = execute(command, output / "logs" / f"consumer-compile-{runtime}.log")
    require_success(compile_result)
    classes = project / "build/classes/kotlin/main"
    java_classes = project / "build/classes/java/main"
    classpath = [classes, java_classes, output / artifacts["dyn4k-core"]["path"],
                 output / artifacts["dyn4k"]["path"], *dependencies]
    command = [str(JDK[runtime] / "bin/java"), "-cp", os.pathsep.join(map(str, classpath)),
               "qualification.ConsumerKt"]
    process = execute(command, output / "logs" / f"consumer-{runtime}.log")
    require_success(process)
    if "STAGED_CONSUMER_PASSED kotlin=2 java=1" not in Path(process["log"]).read_text():
        raise ValueError("staged Java and Kotlin consumer did not execute")
    return {"runtime": runtime, "compile": compile_result, "process": process,
            "source": {path.relative_to(output).as_posix(): digest(path)
                       for path in project.rglob("*") if path.is_file()
                       and "build" not in path.relative_to(project).parts
                       and ".gradle" not in path.relative_to(project).parts},
            "classes": [preserve_file(output, path,
                         f"consumer-classes/{runtime}/{path.name}")
                        for path in (classes / "qualification/ConsumerKt.class",
                                     java_classes / "qualification/JavaMigration.class")]}


def run_jvm(output, manifest, mode, receipt):
    flags = jvm_flags(mode)
    properties = (f"-PjvmCompilerMode={mode}",)
    receipt["flags"] = flags
    receipt["processes"].append(gradle(output, "jvm-build", *jvm_build_tasks(),
                                        property_args=properties))
    log = Path(receipt["processes"][-1]["log"]).read_text(errors="replace")
    problems = build_evidence_problems(receipt["processes"][-1], log, "jvm", mode)
    if problems:
        raise ValueError("; ".join(problems))
    receipt["artifacts"] = snapshot_staging(output, "jvm")
    receipt["staged_files"] = staged_file_hashes(output)
    receipt["compiled_tests"] = snapshot_jvm_test_classes(output)
    dependencies = jvm_dependencies()
    receipt["dependencies"] = {path.name: digest(path) for path in dependencies}
    helper, process = compile_helper(output, dependencies)
    receipt["processes"].append(process)
    receipt["runtimes"] = {name: runtime_identity(jdk) for name, jdk in JDK.items()}
    for runtime in JDK:
        receipt["reports"].extend(jvm_test_run(output, manifest, receipt["artifacts"],
                                               receipt["compiled_tests"], runtime,
                                               dependencies, helper))
        for report in receipt["reports"][-2:]:
            if report["status"] != "PASSED":
                receipt["errors"].append(f"{report['module']} {runtime}: {report['error']}")
        try:
            xml, process = run_originals(output,
                output / receipt["artifacts"]["dyn4k-core"]["path"],
                runtime, dependencies, helper, manifest["original_mappings"], receipt)
            receipt["reports"].append({"kind": "unchanged-java", "runtime": runtime,
                                       "count": 2385, "file": record_file(output, xml),
                                       "process": process})
        except (OSError, ValueError, ET.ParseError) as error:
            receipt["errors"].append(f"unchanged Java {runtime}: {error}")
        try:
            receipt["consumers"].append(run_consumer_jvm(output, runtime,
                                                         receipt["artifacts"], dependencies))
        except (OSError, ValueError) as error:
            receipt["errors"].append(f"staged consumer {runtime}: {error}")


def native_cases(log, expected):
    raw = Path(log).read_text(errors="replace")
    started = re.findall(r"^\[ RUN      \] (\S+)\s*$", raw, re.M)
    passed = re.findall(r"^\[       OK \] (\S+) \(\d+ ms\)\s*$", raw, re.M)
    totals = re.findall(r"^\[  PASSED  \] (\d+) tests?\.\s*$", raw, re.M)
    if (Counter(started) != Counter(expected) or Counter(passed) != Counter(expected)
            or totals != [str(len(expected))]
            or "[  FAILED  ]" in raw or "[  SKIPPED ]" in raw):
        raise ValueError(f"Native cases missing, extra, failed, or skipped: {log}")
    return len(passed)


def native_environment():
    libc = platform.libc_ver()
    if platform.system() != "Linux" or platform.machine() != "x86_64" or libc[0] != "glibc":
        raise ValueError("Linux x64 glibc host is required")
    return {"system": platform.system(), "machine": platform.machine(),
            "kernel": platform.release(), "glibc": libc[1],
            "distribution": platform.platform()}


def native_consumer_project(output):
    project = output / "external-native-consumer"
    project.mkdir()
    (project / "settings.gradle.kts").write_text('rootProject.name = "compiler-mode-native-consumer"\n')
    (project / "build.gradle.kts").write_text(
        'import org.jetbrains.kotlin.gradle.plugin.mpp.NativeBuildType\n'
        'plugins { kotlin("multiplatform") version "2.4.20" }\n'
        f'repositories {{ maven {{ url = uri("{output / "staged"}") }}; mavenCentral() }}\n'
        'kotlin {\n'
        '  linuxX64 { binaries { test(setOf(NativeBuildType.RELEASE)) } }\n'
        f'  sourceSets {{ commonMain.dependencies {{ api("io.github.rubixhacker:dyn4k:{VERSION}") }}\n'
        '               commonTest.dependencies { implementation(kotlin("test")) } }\n'
        '}\n')
    source = ROOT / "consumers/qualification/portable/src/commonTest/kotlin/qualification"
    for item in sorted(source.glob("*.kt")):
        target = project / "src/commonTest/kotlin/qualification" / item.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.read_bytes())
    (project / "src/commonTest/kotlin/qualification/StagedPhysicsTest.kt").write_text(
        'package qualification\n'
        'import kotlin.test.Test\n'
        'import kotlin.test.assertTrue\n'
        'import org.dyn4j.dynamics.Body\n'
        'import org.dyn4j.geometry.Circle\n'
        'import org.dyn4j.geometry.MassType\n'
        'import org.dyn4j.world.World\n'
        'class StagedPhysicsTest {\n'
        '  @Test fun stagedWorldStepsDynamicBody() {\n'
        '    val body = Body()\n'
        '    body.addFixture(Circle(1.0))\n'
        '    body.setMass(MassType.NORMAL)\n'
        '    val world = World<Body>()\n'
        '    world.addBody(body)\n'
        '    world.step(1)\n'
        '    assertTrue(body.getTransform().getTranslationY() < 0.0)\n'
        '  }\n'
        '}\n')
    return project


def run_linux(output, manifest, mode, receipt):
    build = NATIVE_MODES[mode]
    receipt["runtime"] = native_environment()
    receipt["flags"] = [f"link{build}TestLinuxX64"]
    receipt["processes"].append(gradle(output, "linux-build", *native_build_tasks(mode)))
    problems = build_evidence_problems(receipt["processes"][-1],
        Path(receipt["processes"][-1]["log"]).read_text(errors="replace"), "linuxX64", mode)
    if problems:
        raise ValueError("; ".join(problems))
    receipt["artifacts"] = snapshot_staging(output, "linuxX64")
    receipt["staged_files"] = staged_file_hashes(output)
    for module in MODULES:
        executable = ROOT / module / "build/bin/linuxX64" / ("debugTest" if mode == "debug" else "releaseTest") / "test.kexe"
        file = preserve_file(output, executable, f"elf/{module}-{mode}.kexe")
        receipt["artifacts"][f"{module}-test-elf"] = file
        process = execute([str(output / file["path"])], output / "logs" / f"{module}-test.log")
        require_success(process)
        expected = {f"{name}.{method}" for name, method in expected_cases(manifest, module, "linuxX64")}
        count = native_cases(process["log"], expected)
        receipt["reports"].append({"module": module, "kind": "full-common-native",
                                   "count": count, "process": process})
    consumer_root = native_consumer_project(output)
    command = [str(ROOT / "gradlew"), "-p", str(consumer_root), "--offline",
               "--no-daemon", "--max-workers=1", "--rerun-tasks", "--console=plain",
               f"link{build}TestLinuxX64"]
    compiled = execute(command, output / "logs/consumer-compile.log", timeout=7200)
    require_success(compiled)
    consumer = consumer_root / "build/bin/linuxX64" / ("debugTest" if mode == "debug" else "releaseTest") / "test.kexe"
    file = preserve_file(output, consumer, f"elf/staged-consumer-{mode}.kexe")
    receipt["artifacts"]["staged-consumer-elf"] = file
    process = execute([str(output / file["path"])], output / "logs/consumer-test.log")
    require_success(process)
    expected = {
        "qualification.StagedGeometryTest.namedConstructorsResolveFromPublishedCommonAndPlatformVariants",
        "qualification.StagedGeometryTest.stagedRootCoordinatesResolveAndTransformSharedObjects",
        "qualification.StagedFoundationExtraMethodsTest.publishedAliasesRetainKotlinHelpersAndGetterOverrides",
        "qualification.StagedPhysicsTest.stagedWorldStepsDynamicBody",
    }
    receipt["consumers"].append({"count": native_cases(process["log"], expected),
                                 "compile": compiled, "process": process, "elf": file,
                                 "source": {path.relative_to(output).as_posix(): digest(path)
                                            for path in consumer_root.rglob("*.kt")}})


def replay(output, candidate, target, mode):
    receipt = json.loads((output / "receipt.json").read_text())
    problems = check_artifacts(output, receipt, mode)
    staged_files = receipt.get("staged_files", {})
    if not staged_files:
        problems.append("staged metadata is absent")
    for relative, expected_hash in staged_files.items():
        try:
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts or path.parts[0] != "staged":
                raise ValueError("unsafe staged path")
            if digest(output / path) != expected_hash:
                raise ValueError("staged byte hash differs")
        except (OSError, ValueError, TypeError) as error:
            problems.append(f"{relative}: {error}")
    if receipt.get("candidate_sha") != candidate or receipt.get("target") != target:
        problems.append("source, target, or mode label differs")
    try:
        manifest = checked_source(candidate)
        if receipt.get("source_tree_sha256") != manifest["source_tree_sha256"]:
            problems.append("source tree differs")
        if receipt.get("manifest_sha256") != full_corpus.canonical_digest(manifest):
            problems.append("source manifest differs")
        if receipt.get("tree_sha") != subprocess.check_output(
                ["git", "rev-parse", f"{candidate}^{{tree}}"], cwd=ROOT,
                text=True).strip():
            problems.append("Git tree differs")
        expected_reports = 6 if target == "jvm" else 2
        if len(receipt.get("reports", [])) != expected_reports:
            problems.append("report groups missing")
        dependencies = jvm_dependencies() if target == "jvm" else []
        if target == "jvm":
            compiled_tests = receipt.get("compiled_tests")
            problems.extend(compiled_test_evidence_problems(output, compiled_tests))
            expected_groups = {(kind, runtime, module) for runtime in JDK
                               for kind, module in (("full-common", "dyn4k-core"),
                                                    ("full-common", "dyn4k"),
                                                    ("unchanged-java", None))}
            actual_groups = {(report.get("kind"), report.get("runtime"), report.get("module"))
                             for report in receipt.get("reports", [])}
            if actual_groups != expected_groups:
                problems.append("JVM report runtime or module groups differ")
        for report in receipt.get("reports", []):
            try:
                if target == "jvm":
                    if compiled_tests is not None:
                        problems.extend(jvm_report_command_problems(
                            output, report, manifest, receipt["artifacts"], dependencies,
                            compiled_tests))
                    file = report["file"]
                    path = output / file["path"]
                    if digest(path) != file["sha256"]:
                        problems.append("XML report SHA-256 differs")
                    elif report["kind"] == "full-common":
                        expected = expected_cases(manifest, report["module"], "jvm")
                        if verify_xml([path], expected) != report["count"]:
                            problems.append("JVM count differs")
                    elif report["kind"] == "unchanged-java":
                        if report["count"] != verify_original_xml(path, manifest["original_mappings"]):
                            problems.append("unchanged Java count differs")
                else:
                    expected = {f"{name}.{method}" for name, method in
                                expected_cases(manifest, report["module"], "linuxX64")}
                    if native_cases(report["process"]["log"], expected) != report["count"]:
                        problems.append("Native count differs")
            except (OSError, KeyError, TypeError, ValueError, ET.ParseError) as error:
                problems.append(f"report replay differs: {error}")
        for process in [*receipt.get("processes", []),
                        *(item["process"] for item in receipt.get("reports", []))]:
            if process["exit_code"] or digest(process["log"]) != process["log_sha256"]:
                problems.append("process result or raw log differs")
        if target == "jvm":
            if receipt.get("flags") != jvm_flags(mode):
                problems.append("compiler flags differ")
            if receipt.get("runtimes") != {name: runtime_identity(jdk) for name, jdk in JDK.items()}:
                problems.append("Java runtime identity differs")
            if receipt.get("dependencies") != {path.name: digest(path) for path in dependencies}:
                problems.append("JVM dependency bytes differ")
            original_compile = receipt.get("original_compile")
            if original_compile is None:
                problems.append("unchanged Java compile process missing")
            else:
                problems.extend(original_compile_evidence_problems(
                    output, original_compile,
                    output / receipt["artifacts"]["dyn4k-core"]["path"], dependencies))
            build_log = Path(receipt["processes"][0]["log"]).read_text(errors="replace")
            problems.extend(build_evidence_problems(receipt["processes"][0],
                                                    build_log, target, mode))
            if len(receipt.get("consumers", [])) != 2:
                problems.append("staged Java/Kotlin consumers missing")
            if {consumer.get("runtime") for consumer in receipt.get("consumers", [])} != set(JDK):
                problems.append("Java 8 or current consumer runtime missing")
            for consumer in receipt.get("consumers", []):
                problems.extend(jvm_consumer_evidence_problems(
                    output, consumer, receipt["artifacts"], dependencies))
                for item in consumer.get("classes", []):
                    if digest(output / item["path"]) != item["sha256"]:
                        problems.append("staged consumer class differs")
                for relative, expected_hash in consumer.get("source", {}).items():
                    if digest(output / relative) != expected_hash:
                        problems.append("staged consumer source differs")
        else:
            if receipt.get("flags") != [f"link{NATIVE_MODES[mode]}TestLinuxX64"]:
                problems.append("Native link configuration differs")
            if receipt.get("runtime") != native_environment():
                problems.append("Linux kernel, glibc, or host identity differs")
            problems.extend(build_evidence_problems(receipt["processes"][0],
                Path(receipt["processes"][0]["log"]).read_text(errors="replace"), target, mode))
            for name in ("dyn4k-core-test-elf", "dyn4k-test-elf", "staged-consumer-elf"):
                if not (output / receipt["artifacts"][name]["path"]).read_bytes().startswith(b"\x7fELF"):
                    problems.append(f"Native executable is not ELF: {name}")
            if len(receipt.get("consumers", [])) != 1:
                problems.append("Native staged consumer missing")
            else:
                consumer = receipt["consumers"][0]
                process = consumer["process"]
                expected = {
                    "qualification.StagedGeometryTest.namedConstructorsResolveFromPublishedCommonAndPlatformVariants",
                    "qualification.StagedGeometryTest.stagedRootCoordinatesResolveAndTransformSharedObjects",
                    "qualification.StagedFoundationExtraMethodsTest.publishedAliasesRetainKotlinHelpersAndGetterOverrides",
                    "qualification.StagedPhysicsTest.stagedWorldStepsDynamicBody",
                }
                compiled = consumer["compile"]
                problems.extend(native_consumer_command_problems(
                    output, consumer, receipt["artifacts"]["staged-consumer-elf"], mode))
                if (consumer["count"] != 4 or process["exit_code"] or compiled["exit_code"]
                        or digest(process["log"]) != process["log_sha256"]
                        or digest(compiled["log"]) != compiled["log_sha256"]
                        or native_cases(process["log"], expected) != 4):
                    problems.append("Native staged consumer failed")
                for relative, expected_hash in consumer.get("source", {}).items():
                    if digest(output / relative) != expected_hash:
                        problems.append("Native staged consumer source differs")
    except (OSError, KeyError, TypeError, ValueError, ET.ParseError) as error:
        problems.append(str(error))
    return {"status": "PASSED" if not problems and receipt.get("status") == "PASSED" else "UNPASSED",
            "problems": problems, "candidate_sha": candidate, "target": target, "mode": mode}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("run", "verify"))
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--target", choices=("jvm", "linuxX64"), required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.target == "jvm":
        jvm_flags(args.mode)
    elif args.mode not in NATIVE_MODES:
        parser.error("unknown Native mode")
    output = args.output.resolve()
    if args.operation == "verify":
        result = replay(output, args.candidate_sha, args.target, args.mode)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PASSED" else 1
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": 1, "candidate_sha": args.candidate_sha,
               "tree_sha": subprocess.check_output(["git", "rev-parse", f"{args.candidate_sha}^{{tree}}"],
                                                   cwd=ROOT, text=True).strip(),
               "target": args.target, "mode": args.mode, "status": "UNPASSED",
               "processes": [], "reports": [], "consumers": [], "artifacts": {}, "errors": []}
    try:
        manifest = checked_source(args.candidate_sha)
        receipt["manifest_sha256"] = full_corpus.canonical_digest(manifest)
        receipt["source_tree_sha256"] = manifest["source_tree_sha256"]
        if args.target == "jvm":
            run_jvm(output, manifest, args.mode, receipt)
        else:
            run_linux(output, manifest, args.mode, receipt)
        receipt["status"] = "PASSED" if not receipt["errors"] else "UNPASSED"
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        receipt["errors"].append(str(error))
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if receipt["status"] == "PASSED":
        result = replay(output, args.candidate_sha, args.target, args.mode)
        if result["status"] != "PASSED":
            receipt["status"] = "UNPASSED"
            receipt["errors"].extend(result["problems"])
            (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "errors": receipt["errors"]}, indent=2))
    return 0 if receipt["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
