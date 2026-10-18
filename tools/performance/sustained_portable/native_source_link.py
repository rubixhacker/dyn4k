#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

import capture


ROOT = capture.ROOT
SOURCE_SETS = ("commonMain", "nativeMain", "linuxMain", "linuxX64Main")
LABELS = ("dyn4k-core", "dyn4k")
BUILDS = ("development", "optimized")


def source_files(root=ROOT):
    files = {}
    for label in LABELS:
        for source_set in SOURCE_SETS:
            for path in sorted((root / label / "src" / source_set).rglob("*.kt")):
                files[str(path.resolve())] = capture.digest(path)
    if not files:
        raise ValueError("Linux x64 source set is empty")
    return files


def consumer_source_files(root=ROOT):
    source_root = root / "consumers/performance/portable/src"
    files = {}
    for source_set in SOURCE_SETS:
        for path in sorted((source_root / source_set).rglob("*.kt")):
            files[str(path.resolve())] = capture.digest(path)
    if not files:
        raise ValueError("Linux x64 producer source set is empty")
    return files


def identity_source(root=ROOT):
    return root / "consumers/performance/portable/build/generated/portableIdentity/commonMain/kotlin/performance/portable/BuildIdentity.kt"


def native_compiler_jar():
    path = Path.home() / ".konan/kotlin-native-prebuilt-linux-x86_64-2.4.20/konan/lib/kotlin-native-compiler-embeddable.jar"
    return capture.required_file(str(path), "pinned Kotlin Native compiler")


def git_value(*arguments):
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments], text=True).strip()


def trace_events(path, watched):
    watched = set(watched)
    observed = {name: set() for name in ("read", "write", "exec")}
    with path.open(errors="replace") as stream:
        for line in stream:
            paths = watched.intersection(re.findall(r"<([^<>]+)>", line))
            if not paths:
                continue
            if ("read(" in line or "pread64(" in line or "mmap(" in line) and \
                    re.search(r"= (?:[1-9][0-9]*|0x[0-9a-f]+)(?:\s|$)", line):
                observed["read"].update(paths)
            if "write(" in line and re.search(r"= [1-9][0-9]*(?:\s|$)", line):
                observed["write"].update(paths)
    return {key: sorted(value) for key, value in observed.items()}


def executable_install(path, executable):
    predecessor = None
    rename_pattern = re.compile(r'rename\("([^"\\]+)", "' +
                                re.escape(executable) + r'"\) = 0(?:\s|$)')
    with path.open(errors="replace") as stream:
        for line in stream:
            match = rename_pattern.search(line)
            if match:
                predecessor = match.group(1)
                break
    if predecessor is None or not predecessor.startswith(executable + ".tmp"):
        raise ValueError("linked executable lacks traced temporary-file install")
    created = False
    mapped_write = False
    with path.open(errors="replace") as stream:
        for line in stream:
            if predecessor not in line:
                continue
            if "openat(" in line and f'"{predecessor}"' in line and "O_CREAT" in line and \
                    f"<{predecessor}>" in line:
                created = True
            if "mmap(" in line and f"<{predecessor}>" in line and \
                    "PROT_WRITE" in line and "MAP_SHARED" in line and \
                    re.search(r"= 0x[0-9a-f]+(?:\s|$)", line):
                mapped_write = True
    if not created or not mapped_write:
        raise ValueError("linked executable lacks traced writable output mapping")
    return {"temporary": predecessor, "created": True,
            "shared_writable_mapping": True, "renamed_to_executable": True}


def run_traced(command, archive, name, environment):
    trace = archive / f"{name}.strace"
    output = archive / f"{name}.gradle.log"
    tracer = shutil.which("strace")
    if tracer is None:
        raise ValueError("strace is required for Linux x64 provenance")
    traced = [tracer, "-f", "-ttt", "-yy", "-s", "65535",
              "-e", "trace=execve,openat,openat2,read,pread64,mmap,write,rename,renameat,renameat2",
              "-o", str(trace), *command]
    with output.open("wb") as stream:
        process = subprocess.Popen(traced, stdout=stream, stderr=subprocess.STDOUT,
                                   env=environment, start_new_session=True)
        try:
            code = process.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            code = -1
    record = {"command": command, "traced_command": traced,
              "gradle_sha256": capture.digest(Path(command[0])),
              "java_sha256": capture.digest(Path(environment["JAVA_HOME"]) / "bin/java"),
              "tracer_sha256": capture.digest(Path(tracer)),
              "environment": {key: environment[key] for key in
                              ("JAVA_HOME", "TMPDIR", "JAVA_TOOL_OPTIONS", "GRADLE_OPTS")},
              "trace": str(trace), "trace_sha256": capture.digest(trace),
              "gradle_log": str(output), "gradle_log_sha256": capture.digest(output),
              "exit_code": code}
    (archive / f"{name}.action.json").write_text(json.dumps(record, indent=2) + "\n")
    if code != 0:
        raise ValueError(f"{name} failed ({code}); raw trace and Gradle log retained")
    return record


def artifact_paths(root, label):
    module = f"{label}-linuxx64"
    stem = f"{module}-{capture.ARTIFACT_VERSION}"
    directory = root / "build/staging-repository/io/github/rubixhacker" / module / capture.ARTIFACT_VERSION
    return root / label / "build/libs" / f"{label}-linuxX64Main-{capture.ARTIFACT_VERSION}.klib", \
        directory / f"{stem}.klib"


def build(args):
    if sys.platform != "linux" or os.uname().machine not in ("x86_64", "amd64"):
        raise ValueError("this trace route requires Linux x64")
    if args.archive.exists() or not args.archive.is_absolute():
        raise ValueError("evidence archive must be a new absolute path")
    if git_value("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("build checkout must be clean")
    for relative in ("build", "dyn4k-core/build", "dyn4k/build",
                     "consumers/performance/portable/build"):
        if (ROOT / relative).exists():
            raise ValueError(f"fresh checkout already has build outputs: {relative}")
    gradle = capture.required_file(str(args.gradle), "pinned Gradle")
    java = capture.required_file(str(args.jdk / "bin/java"), "pinned JDK 21")
    if "gradle-9.5.0" not in str(gradle) or "jdk21" not in str(java):
        raise ValueError("select pinned Gradle 9.5.0 and JDK 21")
    sources = source_files()
    producer_sources = consumer_source_files()
    compiler_jar = native_compiler_jar()
    args.archive.mkdir(parents=True)
    temporary = args.archive / "tmp"
    temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"JAVA_HOME": str(args.jdk.resolve()), "TMPDIR": str(temporary),
                        "JAVA_TOOL_OPTIONS": f"-Djava.io.tmpdir={temporary}",
                        "GRADLE_OPTS": "-Dorg.gradle.caching=false"})
    common = [str(gradle), "--offline", "--no-daemon", "--no-build-cache",
              "--rerun-tasks", "--info"]
    source_command = common + ["-p", str(ROOT),
        ":dyn4k-core:publishLinuxX64PublicationToStagingRepository",
        ":dyn4k:publishLinuxX64PublicationToStagingRepository",
        ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
        ":dyn4k:publishKotlinMultiplatformPublicationToStagingRepository"]
    actions = {"publication": run_traced(source_command, args.archive, "publication", environment)}
    if source_files() != sources:
        raise ValueError("source files changed during publication")
    publication = {}
    for label in LABELS:
        output, staged = artifact_paths(ROOT, label)
        output = capture.required_file(str(output), "fresh compiler KLIB")
        staged = capture.required_file(str(staged), "fresh staged KLIB")
        if capture.digest(output) != capture.digest(staged):
            raise ValueError("fresh compiler KLIB differs from staged KLIB")
        publication[label] = {"compiler_klib": str(output), "staged_klib": str(staged),
                              "sha256": capture.digest(output)}
    publication_watched = list(sources) + [str(compiler_jar)]
    for item in publication.values():
        publication_watched.extend((item["compiler_klib"], item["staged_klib"]))
    publication_events = trace_events(Path(actions["publication"]["trace"]), publication_watched)
    uri = (ROOT / "build/staging-repository").resolve().as_uri()
    inventories = {}
    link_events = {}
    for build_name in BUILDS:
        command = common + ["-p", str(ROOT / "consumers/performance/portable"),
            f"-PperformanceRepository={uri}", "-PportableNativeHostTarget=linuxX64",
            f"-PportableNativeHostBuild={build_name}", "portableNativeHostBuildInventory"]
        actions[build_name] = run_traced(command, args.archive, build_name, environment)
        inventory_path = ROOT / "consumers/performance/portable/build/portable-inventory" / \
            f"linuxX64-{build_name}.json"
        inventory = json.loads(inventory_path.read_text())
        selected = capture.native_artifacts(inventory, "linuxX64")
        for label in LABELS:
            if selected[label]["sha256"] != publication[label]["sha256"]:
                raise ValueError("consumer resolved KLIB differs from fresh compiler output")
        executable = capture.required_file(inventory["harness"], "fresh linked executable")
        identity = capture.required_file(str(identity_source()), "generated producer identity")
        inventories[build_name] = {"path": str(inventory_path), "sha256": capture.digest(inventory_path),
                                   "executable": str(executable), "executable_sha256": capture.digest(executable),
                                   "generated_identity": str(identity),
                                   "generated_identity_sha256": capture.digest(identity),
                                   "resolved_klibs": {label: selected[label] for label in LABELS}}
        link_events[build_name] = trace_events(Path(actions[build_name]["trace"]),
            [selected[label]["path"] for label in LABELS] + [str(executable), str(identity)] +
            list(producer_sources) + [str(compiler_jar)])
        link_events[build_name]["executable_install"] = executable_install(
            Path(actions[build_name]["trace"]), str(executable))
    if (source_files() != sources or consumer_source_files() != producer_sources or
            git_value("status", "--porcelain", "--untracked-files=all")):
        raise ValueError("source checkout changed during traced build")
    receipt = {"format": "linux-x64-native-source-link-v1", "qualification": "unpassed",
               "source_to_link": "unpassed", "source_sha": git_value("rev-parse", "HEAD"),
               "checkout": str(ROOT), "source_files": sources, "actions": actions,
               "producer_source_files": producer_sources,
               "compiler_jar": str(compiler_jar),
               "compiler_jar_sha256": capture.digest(compiler_jar),
               "publication": publication, "inventories": inventories,
               "observed_syscalls": {"publication": publication_events,
                                     "development": link_events["development"],
                                     "optimized": link_events["optimized"]}}
    path = args.archive / "source-link.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    verify_receipt(path)
    return path


def verify_receipt(path, inventory=None, build_name=None):
    path = capture.required_file(str(path), "source-link receipt")
    receipt = json.loads(path.read_text())
    if (receipt.get("format") != "linux-x64-native-source-link-v1" or
            receipt.get("qualification") != "unpassed" or
            receipt.get("source_to_link") != "unpassed" or
            receipt.get("checkout") != str(ROOT) or
            receipt.get("source_sha") != git_value("rev-parse", "HEAD") or
            receipt.get("source_files") != source_files() or
            receipt.get("producer_source_files") != consumer_source_files() or
            receipt.get("compiler_jar") != str(native_compiler_jar()) or
            receipt.get("compiler_jar_sha256") != capture.digest(native_compiler_jar())):
        raise ValueError("source-link receipt differs from selected checkout source")
    if set(receipt.get("actions", {})) != {"publication", *BUILDS}:
        raise ValueError("source-link receipt lacks exact traced build actions")
    for name, action in receipt["actions"].items():
        for field, sha in (("trace", "trace_sha256"), ("gradle_log", "gradle_log_sha256")):
            value = capture.required_file(action[field], f"{name} raw {field}")
            if capture.digest(value) != action[sha]:
                raise ValueError(f"{name} raw {field} changed")
        if action["exit_code"] != 0 or "--offline" not in action["command"] or \
                "--no-build-cache" not in action["command"] or "--rerun-tasks" not in action["command"]:
            raise ValueError(f"{name} was not a successful fresh offline action")
        if (action["traced_command"][-len(action["command"]):] != action["command"] or
                action["traced_command"][0] != shutil.which("strace") or
                capture.digest(Path(action["traced_command"][0])) != action["tracer_sha256"] or
                capture.digest(Path(action["command"][0])) != action["gradle_sha256"] or
                capture.digest(Path(action["environment"]["JAVA_HOME"]) / "bin/java") !=
                action["java_sha256"]):
            raise ValueError(f"{name} traced toolchain differs")
        expected_tasks = ({"publication": (
            ":dyn4k-core:publishLinuxX64PublicationToStagingRepository",
            ":dyn4k:publishLinuxX64PublicationToStagingRepository",
            ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
            ":dyn4k:publishKotlinMultiplatformPublicationToStagingRepository")}.get(name))
        if name == "publication":
            if tuple(action["command"][-4:]) != expected_tasks or \
                    action["command"][action["command"].index("-p") + 1] != str(ROOT):
                raise ValueError("publication command differs from exact source build")
        elif (action["command"][-1] != "portableNativeHostBuildInventory" or
              f"-PportableNativeHostBuild={name}" not in action["command"] or
              "-PportableNativeHostTarget=linuxX64" not in action["command"] or
              f"-PperformanceRepository={(ROOT / 'build/staging-repository').resolve().as_uri()}"
              not in action["command"] or
              action["command"][action["command"].index("-p") + 1] !=
              str(ROOT / "consumers/performance/portable")):
            raise ValueError(f"{name} command differs from exact consumer link")
    publication_trace = Path(receipt["actions"]["publication"]["trace"])
    publication_watched = list(receipt["source_files"]) + [receipt["compiler_jar"]]
    for item in receipt["publication"].values():
        publication_watched.extend((item["compiler_klib"], item["staged_klib"]))
    publication_events = trace_events(publication_trace, publication_watched)
    if publication_events != receipt["observed_syscalls"]["publication"]:
        raise ValueError("publication syscall observations differ from raw trace")
    source_reads = set(publication_events["read"]).intersection(receipt["source_files"])
    if set(source_reads) != set(receipt["source_files"]):
        raise ValueError(f"compiler source reads unobserved: {len(receipt['source_files']) - len(source_reads)}")
    if receipt["compiler_jar"] not in publication_events["read"]:
        raise ValueError("pinned compiler JAR read unobserved during publication")
    for label in LABELS:
        item = receipt["publication"][label]
        expected_output, expected_stage = artifact_paths(ROOT, label)
        if (item["compiler_klib"] != str(expected_output) or
                item["staged_klib"] != str(expected_stage)):
            raise ValueError("compiler and staged KLIB paths differ from fresh checkout")
        if any(capture.digest(capture.required_file(item[field], field)) != item["sha256"]
               for field in ("compiler_klib", "staged_klib")):
            raise ValueError("fresh KLIB output or staged bytes changed")
    for mode in BUILDS:
        item = receipt["inventories"][mode]
        selected_inventory = json.loads(Path(item["path"]).read_text())
        if (capture.digest(Path(item["path"])) != item["sha256"] or
                selected_inventory.get("source_sha") != receipt["source_sha"] or
                selected_inventory.get("target") != "linuxX64" or
                selected_inventory.get("build") != mode or
                selected_inventory.get("harness") != item["executable"] or
                item["generated_identity"] != str(identity_source()) or
                capture.digest(identity_source()) != item["generated_identity_sha256"] or
                capture.digest(Path(item["executable"])) != item["executable_sha256"]):
            raise ValueError("fresh executable or inventory differs from traced build")
        identity_text = identity_source().read_text()
        if (receipt["source_sha"] not in identity_text or
                selected_inventory["producer_tree"] not in identity_text):
            raise ValueError("generated identity differs from selected source")
        selected = capture.native_artifacts(selected_inventory, "linuxX64")
        trace = Path(receipt["actions"][mode]["trace"])
        paths = [selected[label]["path"] for label in LABELS]
        expected_sources = set(receipt["producer_source_files"]) | {item["generated_identity"]}
        events = trace_events(trace, paths + [item["executable"], receipt["compiler_jar"]] +
                              list(expected_sources))
        events["executable_install"] = executable_install(trace, item["executable"])
        if events != receipt["observed_syscalls"][mode]:
            raise ValueError(f"{mode} syscall observations differ from raw trace")
        reads = events["read"]
        if not expected_sources <= set(reads):
            raise ValueError(f"{mode} producer compiler source reads unobserved")
        if receipt["compiler_jar"] not in reads:
            raise ValueError(f"{mode} pinned compiler JAR read unobserved")
        for label in LABELS:
            if (selected[label] != item["resolved_klibs"][label] or
                    selected[label]["sha256"] != receipt["publication"][label]["sha256"] or
                    capture.digest(Path(selected[label]["path"])) != selected[label]["sha256"] or
                    selected[label]["path"] not in reads):
                raise ValueError(f"{mode} linked KLIB input lacks fresh byte/read evidence")
    if inventory is not None:
        if build_name not in BUILDS or inventory != receipt["inventories"][build_name]["path"]:
            raise ValueError("capture inventory differs from source-link receipt")
    return receipt


def require_selected_inputs(receipt, build_name, inventory_path, executable_sha, selected_hashes):
    item = receipt["inventories"][build_name]
    if item["path"] != str(inventory_path) or item["executable_sha256"] != executable_sha:
        raise ValueError("selected inventory or executable differs from traced link")
    for label in LABELS:
        if selected_hashes[label] != receipt["publication"][label]["sha256"]:
            raise ValueError(f"selected {label} KLIB lacks traced source-to-link provenance")


def older_klib_adverse(receipt_path, older_path, archive):
    receipt = verify_receipt(receipt_path)
    older_path = capture.required_file(str(older_path), "older KLIB")
    capture.validate_klib(older_path, "dyn4k-core", "linuxX64")
    old_sha = capture.digest(older_path)
    if old_sha == receipt["publication"]["dyn4k-core"]["sha256"]:
        raise ValueError("adverse KLIB must differ from fresh compiler output")
    relative = Path("io/github/rubixhacker/dyn4k-core-linuxx64") / capture.ARTIFACT_VERSION
    destination = archive / "adverse-staged" / relative
    source = ROOT / "build/staging-repository" / relative
    shutil.copytree(source, destination)
    stem = f"dyn4k-core-linuxx64-{capture.ARTIFACT_VERSION}"
    klib = destination / f"{stem}.klib"
    klib.write_bytes(older_path.read_bytes())
    klib.with_name(klib.name + ".sha256").write_text(old_sha + "\n")
    metadata = destination / f"{stem}.module"
    document = json.loads(metadata.read_text())
    variants = [item for item in document["variants"]
                if item["name"] == "linuxX64ApiElements-published"]
    if len(variants) != 1 or len(variants[0]["files"]) != 1:
        raise ValueError("adverse staged module lacks exact Linux x64 variant")
    variants[0]["files"][0]["sha256"] = old_sha
    metadata.write_text(json.dumps(document, indent=2) + "\n")
    metadata.with_name(metadata.name + ".sha256").write_text(capture.digest(metadata) + "\n")
    pairwise = capture.validate_publication(archive / "adverse-staged", "dyn4k-core",
                                            "linuxX64", old_sha)
    selected = {label: receipt["publication"][label]["sha256"] for label in LABELS}
    selected["dyn4k-core"] = old_sha
    try:
        require_selected_inputs(receipt, "development",
                                receipt["inventories"]["development"]["path"],
                                receipt["inventories"]["development"]["executable_sha256"],
                                selected)
    except ValueError as error:
        rejected = str(error)
    else:
        raise ValueError("older resealed KLIB incorrectly gained source-to-link provenance")
    result = {"qualification": "unpassed", "older_klib_sha256": old_sha,
              "fresh_core_klib_sha256": receipt["publication"]["dyn4k-core"]["sha256"],
              "pairwise_publication_accepted": pairwise["source_archive_matches_checkout"],
              "source_link_rejected": rejected, "adverse_staged_root": str(archive / "adverse-staged")}
    (archive / "older-klib-adverse.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--gradle", type=Path, required=True)
    parser.add_argument("--jdk", type=Path, required=True)
    parser.add_argument("--older-core-klib", type=Path)
    args = parser.parse_args()
    try:
        path = build(args)
        if args.older_core_klib is not None:
            older_klib_adverse(path, args.older_core_klib, args.archive)
        print(path)
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as error:
        parser.exit(1, f"source-to-link: unpassed; {error}\n")


if __name__ == "__main__":
    main()
