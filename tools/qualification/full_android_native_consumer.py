#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import independent_gates


PROJECT = "consumers/qualification/portable/full-android-native"
MODULES = ("dyn4k-core", "dyn4k")
VERSION = "0.1.0-alpha.1"
GROUP = "io.github.rubixhacker"
ROUTES = {
    "androidNativeArm32": ("Android Native armeabi-v7a", "armeabi-v7a", "armeabi-v7a", 40, 1),
    "androidNativeArm64": ("Android Native arm64-v8a", "arm64-v8a", "arm64-v8a", 183, 2),
    "androidNativeX86": ("Android Native x86", "x86", "x86", 3, 1),
    "androidNativeX64": ("Android Native x86_64", "x86_64", "x86_64", 62, 2),
}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
RUN = re.compile(r"^\[ RUN      \] ([A-Za-z_][\w.]*)$", re.M)
OK = re.compile(r"^\[       OK \] ([A-Za-z_][\w.]*) \((\d+) ms\)$", re.M)
TOTAL = re.compile(r"^\[==========\] (\d+) tests from \d+ test cases ran\. \(\d+ ms total\)$", re.M)
PASSED = re.compile(r"^\[  PASSED  \] (\d+) tests\.$", re.M)
GUEST_PROPERTIES = {
    "ro.build.version.sdk": "api",
    "ro.product.cpu.abi": "primary_abi",
    "ro.product.cpu.abilist": "abi_list",
    "sys.boot_completed": "boot_completed",
    "ro.build.fingerprint": "fingerprint",
    "ro.boot.qemu.avd_name": "avd_name",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(path):
    return sha(Path(path).read_bytes())


def encoded(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def git(repository, *args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(repository),
                                    *args], stderr=subprocess.PIPE)


def approved_manifest(repository):
    return independent_gates.load_approved_manifest(repository)


def lanes(manifest):
    result = sorted(lane for lane, data in manifest["lanes"].items()
                    if data["target"] in ROUTES)
    if len(result) != 16 or any(route(lane)["target"] != manifest["lanes"][lane]["target"]
                                for lane in result):
        raise ValueError("approved Android Native lane matrix differs")
    return result


def route(lane):
    parts = lane.split(":")
    if len(parts) != 4 or parts[0] not in ROUTES:
        raise ValueError("Android Native lane is absent")
    target, runtime, version, configuration = parts
    approved_runtime, abi, _, machine, elf_class = ROUTES[target]
    if (runtime != approved_runtime or version not in ("minimum", "current")
            or configuration not in ("debug-g", "optimized-opt")):
        raise ValueError("Android Native lane is absent")
    api = 21 if version == "minimum" else 37
    return {"target": target, "runtime": runtime, "version": version,
            "configuration": configuration, "api": api, "abi": abi,
            "machine": machine, "elf_class": elf_class,
            "link": "Debug" if configuration == "debug-g" else "Release"}


def selected_cases(repository, lane):
    manifest = approved_manifest(repository)
    if lane not in lanes(manifest):
        raise ValueError("Android Native lane is absent from approved manifest")
    contract = independent_gates.consumer_contract(manifest, lane)
    cases = contract["cases"]
    if (len(cases) != 2523 or len({case["id"] for case in cases}) != 2523
            or sum(case["module"] == "dyn4k-core" for case in cases) != 2465
            or sum(case["module"] == "dyn4k" for case in cases) != 58
            or any(case["scope"] != "portable" for case in cases)):
        raise ValueError("approved portable method contract differs")
    return manifest, contract


def original_sources(repository, candidate, cases):
    roots = ("dyn4k-core/src/commonTest/kotlin", "dyn4k/src/commonTest/kotlin",
             "dyn4k-core/src/nativeTest/kotlin")
    tracked = sorted(path for path in git(repository, "ls-tree", "-r", "--name-only",
                                          candidate, "--", *roots).decode().splitlines()
                     if path.endswith(".kt"))
    live = sorted(path.relative_to(repository).as_posix() for root in roots
                  for path in (repository / root).rglob("*.kt") if path.is_file())
    if tracked != live or len(tracked) != len(set(tracked)):
        raise ValueError("original common and native test inventory differs")
    hashes = {}
    for name in tracked:
        raw = git(repository, "show", f"{candidate}:{name}")
        if (repository / name).read_bytes() != raw:
            raise ValueError(f"original test source differs: {name}")
        hashes[name] = sha(raw)
    if any(hashes.get(case["source"]["path"]) != case["source"]["sha256"]
           for case in cases):
        raise ValueError("approved original method source differs")
    return hashes


def staged_binary(staging, module, target):
    variant = target.lower()
    name = f"{module}-{variant}-{VERSION}.klib"
    return Path(staging) / GROUP.replace(".", "/") / f"{module}-{variant}" / VERSION / name


def check_executable(path, selected):
    data = Path(path).read_bytes()[:20]
    if (len(data) < 20 or data[:4] != b"\x7fELF" or data[4] != selected["elf_class"]
            or data[5] != 1 or int.from_bytes(data[18:20], "little") != selected["machine"]):
        raise ValueError("linked executable ELF ABI differs from selected lane")
    return digest(path)


def check_guest(selected, guest, expected_serial=None):
    if expected_serial is None and selected["target"] == "androidNativeX64":
        expected_serial = "emulator-5560" if selected["api"] == 21 else "emulator-5558"
    if (guest.get("api") != str(selected["api"])
            or guest.get("primary_abi") != selected["abi"]
            or selected["abi"] not in guest.get("abi_list", "").split(",")
            or guest.get("boot_completed") != "1"
            or not guest.get("serial")
            or expected_serial is not None and guest.get("serial") != expected_serial
            or not str(guest.get("fingerprint", ""))
            or not str(guest.get("pid", ""))):
        raise ValueError("guest ABI, API, serial, boot, or process identity differs")
    return guest


def case_map(cases, module):
    return {case["id"]: (case["classname"], case["method"])
            for case in cases if case["module"] == module}


def parse_guest(raw, expected):
    normalized = raw.replace(b"\r\n", b"\n")
    if b"\r" in normalized:
        raise ValueError("guest event line endings differ")
    text = normalized.decode("utf-8")
    runs = RUN.findall(text)
    oks = OK.findall(text)
    totals, passed = TOTAL.findall(text), PASSED.findall(text)
    if (not runs or runs != [name for name, _ in oks] or len(totals) != 1
            or len(passed) != 1 or int(totals[0]) != len(runs)
            or int(passed[0]) != len(runs)
            or re.search(r"(?m)^\[\s*(?:FAILED|SKIPPED|DISABLED)\s*\]", text)):
        raise ValueError("guest method event rows or totals differ")
    reverse = {f"{name}.{method}": identity for identity, (name, method) in expected.items()}
    if len(reverse) != len(expected):
        raise ValueError("approved method identities collide")
    ids = [reverse.get(name) for name in runs]
    if (None in ids or len(ids) != len(expected) or len(set(ids)) != len(ids)
            or set(ids) != set(expected)):
        raise ValueError("guest method results are missing, duplicate, or foreign")
    suite = ET.Element("testsuite", tests=str(len(ids)), failures="0", errors="0",
                       skipped="0", time=str(sum(int(ms) for _, ms in oks) / 1000))
    for identity, (_, ms) in zip(ids, oks):
        classname, method = expected[identity]
        ET.SubElement(suite, "testcase", id=identity, classname=classname,
                      name=method, time=str(int(ms) / 1000))
    return ids, ET.tostring(suite, encoding="utf-8", xml_declaration=True)


def checked(command, *, cwd=None, env=None):
    start = time.time_ns()
    proc = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=False)
    end = time.time_ns()
    return {"command": [str(item) for item in command], "exit_code": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr, "started_ns": start,
            "finished_ns": end}


def write(root, relative, raw):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw if isinstance(raw, bytes) else raw.encode())
    return relative


def save_process(root, name, result):
    stdout = write(root, f"process/{name}.stdout", result["stdout"])
    stderr = write(root, f"process/{name}.stderr", result["stderr"])
    return ({key: result[key] for key in
             ("command", "exit_code", "started_ns", "finished_ns")}
            | {"stdout": stdout, "stderr": stderr,
               "stdout_sha256": sha(result["stdout"]),
               "stderr_sha256": sha(result["stderr"])})


def adb_command(adb, serial, *arguments):
    return [str(adb), "-P", "5038", "-s", serial, *arguments]


def guest_query(adb, serial, root):
    devices = checked([str(adb), "-P", "5038", "devices", "-l"])
    save_process(root, "devices", devices)
    lines = devices["stdout"].decode().splitlines()
    if (devices["exit_code"] or not any(line.split()[:2] == [serial, "device"]
                                         for line in lines)):
        raise ValueError("leased guest is unavailable on ADB port 5038")
    guest = {"serial": serial}
    for prop, key in GUEST_PROPERTIES.items():
        result = checked(adb_command(adb, serial, "shell", "getprop", prop))
        save_process(root, "guest-" + key, result)
        if result["exit_code"]:
            raise ValueError(f"guest property query failed: {prop}")
        guest[key] = result["stdout"].decode().strip()
    pid = checked(adb_command(adb, serial, "shell", "cat", "/proc/self/stat"))
    save_process(root, "guest-pid", pid)
    if pid["exit_code"]:
        raise ValueError("guest process identity query failed")
    guest["pid"] = pid["stdout"].decode().split()[0]
    return guest


def source_hashes(repository, candidate):
    paths = [f"{PROJECT}/{name}" for name in ("settings.gradle.kts", "build.gradle.kts",
              "core/build.gradle.kts", "facade/build.gradle.kts")]
    paths.append("tools/qualification/full_android_native_consumer.py")
    return {path: sha(git(repository, "show", f"{candidate}:{path}")) for path in paths}


def input_content(sources, cases):
    result = {"source-inventory.tsv": "".join(f"{name}\t{value}\n"
              for name, value in sorted(sources.items())).encode()}
    for module, short in (("dyn4k-core", "core"), ("dyn4k", "facade")):
        result[f"{short}-cases.tsv"] = "".join(
            f"{identity}\t{classname}\t{method}\n"
            for identity, (classname, method) in sorted(case_map(cases, module).items())).encode()
    return result


def verify_graph(graph, target, hashes):
    variant = target.lower()
    if set(graph) != {"compile"}:
        raise ValueError("provider phases differ")
    rows = graph["compile"]
    if len(rows) != 2 or {row["project"] for row in rows} != {"core", "facade"}:
        raise ValueError("provider graph modules differ")
    for row in rows:
        if row["configuration"] != f"{target}TestCompileKlibraries":
            raise ValueError("provider configuration differs")
        roots = {f"{GROUP}:{module}:{VERSION}" for module in MODULES}
        providers = {f"{GROUP}:{module}-{variant}:{VERSION}" for module in MODULES}
        components = {item for item in row["components"] if item.startswith(GROUP + ":")}
        if components != roots | providers or any("org.dyn4j:dyn4j" in item
                                                  for item in row["components"]):
            raise ValueError("provider graph has missing or foreign component")
        artifacts = [item for item in row["artifacts"]
                     if item["component"].startswith(GROUP + ":")]
        if len(artifacts) != 2 or {item["component"] for item in artifacts} != providers:
            raise ValueError("provider graph has missing or duplicate binary")
        for module in MODULES:
            item = next(item for item in artifacts
                        if item["component"] == f"{GROUP}:{module}-{variant}:{VERSION}")
            if item["sha256"] != hashes[module] or item["size"] <= 0:
                raise ValueError("provider artifact hash differs from independent input")
    return True


def inventory(root):
    return [{"path": path.relative_to(root).as_posix(), "sha256": digest(path),
             "mtime_ns": path.stat().st_mtime_ns}
            for path in sorted(root.rglob("*")) if path.is_file()]


def guest_command(adb, serial, remote, lane):
    script = f"echo QUALIFICATION_LANE=$0; echo QUALIFICATION_GUEST_PID=$$; exec {remote} --ktest_logger=GTEST"
    return adb_command(adb, serial, "shell", "sh", "-c", "'" + script + "'",
                       "'" + lane + "'", lane)


def run_guest(adb, serial, remote, binary, lane, root, name):
    push = checked(adb_command(adb, serial, "push", str(binary), remote))
    operations = {"push": save_process(root, name + "-push", push)}
    chmod = checked(adb_command(adb, serial, "shell", "chmod", "700", remote))
    operations["chmod"] = save_process(root, name + "-chmod", chmod)
    expected_hash = digest(binary)
    if push["exit_code"] or chmod["exit_code"]:
        raise ValueError("pushed guest executable differs from linked binary")
    installed_path = None
    if route(lane)["api"] == 21:
        installed_path = f"installed/{name}.kexe"
        destination = root / installed_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        pull = checked(adb_command(adb, serial, "pull", remote, str(destination)))
        operations["pull"] = save_process(root, name + "-pull", pull)
        if pull["exit_code"] or digest(destination) != expected_hash:
            raise ValueError("pulled guest executable differs from linked binary")
    else:
        remote_hash = checked(adb_command(adb, serial, "shell", "sha256sum", remote))
        operations["remote_hash"] = save_process(root, name + "-remote-hash", remote_hash)
        if (remote_hash["exit_code"] or not remote_hash["stdout"].split()
                or remote_hash["stdout"].decode().split()[0] != expected_hash):
            raise ValueError("guest executable hash differs from linked binary")
    result = checked(guest_command(adb, serial, remote, lane))
    record = save_process(root, name + "-guest", result)
    if result["exit_code"]:
        raise ValueError(f"{name} guest test process exited {result['exit_code']}")
    guest_pids = re.findall(rb"(?m)^QUALIFICATION_GUEST_PID=(\d+)\r?$", result["stdout"])
    if len(guest_pids) != 1 or int(guest_pids[0]) <= 0:
        raise ValueError("guest test process identity is absent")
    record["guest_pid"] = int(guest_pids[0])
    record["remote"] = remote
    record["binary_sha256"] = expected_hash
    record["installed_path"] = installed_path
    record["operations"] = operations
    return record


def toolchain(gradle, adb):
    java_home = Path(os.environ["JAVA_HOME"]).resolve()
    java = java_home / "bin/java"
    version = subprocess.check_output([str(java), "-version"],
                                      stderr=subprocess.STDOUT, text=True)
    gradle_version = subprocess.check_output([str(gradle), "--version"], text=True)
    if 'version "21' not in version or "Gradle 9.5.0" not in gradle_version:
        raise ValueError("JDK 21 and Gradle 9.5.0 are required")
    return {"java_sha256": digest(java), "java_version": next(
                line for line in version.splitlines() if 'version "21' in line),
            "gradle_sha256": digest(gradle), "gradle_version": "Gradle 9.5.0",
            "adb_sha256": digest(adb), "kgp_version": "2.4.20",
            "agp_version": "9.3.1"}


def build_command(repository, staging, output, work, gradle, selected, hashes):
    target, link = selected["target"], selected["link"]
    task_target = target[0].upper() + target[1:]
    return [str(gradle), "-p", str(repository / PROJECT), "--offline", "--no-daemon",
            "--max-workers=2", "--console=plain", "--rerun-tasks",
            "--project-cache-dir", str(work / "project-cache"),
            f"-PqualificationCheckout={repository}",
            f"-PqualificationRepository={staging}",
            f"-PqualificationArchiveRoot={output}",
            f"-PqualificationWorkRoot={work}",
            f"-PqualificationTarget={target}",
            f"-PqualificationCoreSha256={hashes['dyn4k-core']}",
            f"-PqualificationFacadeSha256={hashes['dyn4k']}",
            "qualificationGraph", f":core:link{link}Test{task_target}",
            f":facade:link{link}Test{task_target}"]


def build_program(work, module, selected):
    mode = "debugTest" if selected["link"] == "Debug" else "releaseTest"
    return work / module / "bin" / selected["target"] / mode / "test.kexe"


def run(repository, candidate, lane, staging, output, work, gradle, adb, serial, hashes):
    repository, staging, output, work, gradle, adb = (Path(path).resolve() for path in
        (repository, staging, output, work, gradle, adb))
    selected = route(lane)
    _, contract = selected_cases(repository, lane)
    if (git(repository, "rev-parse", "HEAD").decode().strip() != candidate
            or git(repository, "status", "--porcelain", "--untracked-files=all").strip()):
        raise ValueError("producer requires a clean exact candidate checkout")
    if (output.is_relative_to(repository) or work.is_relative_to(repository)
            or output == work or staging.is_relative_to(repository)
            or output.exists() and any(output.iterdir())):
        raise ValueError("producer paths must be distinct home paths and output empty")
    if set(hashes) != set(MODULES) or any(not SHA256.fullmatch(value) for value in hashes.values()):
        raise ValueError("independent staged KLIB hashes are incomplete")
    for module in MODULES:
        if digest(staged_binary(staging, module, selected["target"])) != hashes[module]:
            raise ValueError("independently supplied staged KLIB hash differs")
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    started = time.time_ns()
    try:
        source_inventory = original_sources(repository, candidate, contract["cases"])
        inputs = input_content(source_inventory, contract["cases"])
        for name, raw in inputs.items():
            write(output, "inputs/" + name, raw)
        tools = toolchain(gradle, adb)
        command = build_command(repository, staging, output, work, gradle, selected, hashes)
        build = checked(command, cwd=repository)
        build_process = save_process(output, "gradle", build)
        if build["exit_code"]:
            raise ValueError(f"external Gradle link failed: {build['exit_code']}")
        if (git(repository, "rev-parse", "HEAD").decode().strip() != candidate
                or git(repository, "status", "--porcelain", "--untracked-files=all").strip()
                or original_sources(repository, candidate, contract["cases"]) != source_inventory
                or any(digest(repository / path) != value
                       for path, value in source_hashes(repository, candidate).items())):
            raise ValueError("candidate or original test sources changed during link")
        build_output = build["stdout"].decode(errors="replace")
        for module in ("core", "facade"):
            task = f"> Task :{module}:link{selected['link']}Test{selected['target'][0].upper() + selected['target'][1:]}"
            if task not in build_output:
                raise ValueError(f"selected compiler/link task is absent: {task}")
        graph = json.loads((output / "provider-graph.json").read_bytes())
        verify_graph(graph, selected["target"], hashes)
        executables = {}
        for module in ("core", "facade"):
            source = build_program(work, module, selected)
            check_executable(source, selected)
            destination = output / f"runtime/{module}.kexe"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            executables[module] = digest(destination)
        build_evidence = {"process": build_process, "repository": str(repository),
                          "staging": str(staging), "output": str(output),
                          "work": str(work), "gradle": str(gradle),
                          "gradle_sha256": tools["gradle_sha256"],
                          "staged_inputs": {module: {"path": str(staged_binary(
                              staging, module, selected["target"])), "sha256": hashes[module]}
                              for module in MODULES},
                          "provider_graph_sha256": digest(output / "provider-graph.json"),
                          "linked_outputs": {module: {
                              "path": str(build_program(work, module, selected)),
                              "sha256": executables[module],
                              "archived_path": f"runtime/{module}.kexe"}
                              for module in ("core", "facade")}}
        write(output, "build.json", encoded(build_evidence) + b"\n")
        guest = guest_query(adb, serial, output)
        check_guest(selected, guest, serial)
        write(output, "guest.json", encoded(guest) + b"\n")
        runtime = {}
        raw_reports = []
        xml_reports = []
        for module, source_module in (("core", "dyn4k-core"), ("facade", "dyn4k")):
            remote = f"/data/local/tmp/dyn4k-full-{candidate[:12]}-{selected['target'].lower()}-{selected['link'].lower()}-{module}"
            record = run_guest(adb, serial, remote, output / f"runtime/{module}.kexe",
                               lane, output, module)
            runtime[module] = record
            raw = (output / record["stdout"]).read_bytes()
            ids, xml = parse_guest(raw, case_map(contract["cases"], source_module))
            if len(ids) != (2465 if module == "core" else 58):
                raise ValueError("guest selected original method count differs")
            raw_reports.append(record["stdout"])
            xml_reports.append(write(output, f"reports/{module}.xml", xml))
        write(output, "runtime.json", encoded(runtime) + b"\n")
        lines = [build_output, f"QUALIFICATION_LANE={lane}",
                 "QUALIFICATION_PROCESS_EXIT=0",
                 f"QUALIFICATION_PROVIDER_GRAPH_SHA256={digest(output / 'provider-graph.json')}"]
        for module in MODULES:
            name = staged_binary(staging, module, selected["target"]).name
            lines.append(f"QUALIFICATION_RESOLVED_{module.upper().replace('-', '_')}_SHA256={digest(output / 'resolved' / name)}")
        for path in xml_reports:
            lines.append(f"QUALIFICATION_CONSUMER_XML_SHA256={digest(output / path)}")
        for module, path in zip(("core", "facade"), raw_reports):
            lines.append(f"QUALIFICATION_RAW_GUEST_{module.upper()}_SHA256={digest(output / path)}")
            lines.append(f"QUALIFICATION_GUEST_{module.upper()}_PID={runtime[module]['guest_pid']}")
        write(output, "process.txt", "\n".join(lines) + "\n")
        write(output, "process-stderr.txt", b"")
        finished = time.time_ns()
        receipt = {"schema": 1, "status": "PASSED", "candidate_sha": candidate,
                   "source_tree": git(repository, "rev-parse", f"{candidate}^{{tree}}").decode().strip(),
                   "lane": lane, **{key: selected[key] for key in
                                   ("target", "runtime", "version", "configuration")},
                   "abi": selected["abi"], "api": selected["api"],
                   "link_mode": selected["link"],
                   "runtime_identity": independent_gates.digest(guest),
                   "consumer_group": "full-suite",
                   "consumer_contract_sha256": independent_gates.digest(contract),
                   "artifact_hashes": hashes, "toolchain": tools,
                   "source_hashes": source_hashes(repository, candidate),
                   "source_inventory_sha256": sha(inputs["source-inventory.tsv"]),
                   "executable_hashes": executables,
                   "provider_graph": "provider-graph.json",
                   "resolved_artifacts": {module: "resolved/" + staged_binary(
                       staging, module, selected["target"]).name for module in MODULES},
                   "raw_consumer_events": raw_reports,
                   "consumer_xml": xml_reports,
                   "runtime_record": "runtime.json", "guest_record": "guest.json",
                   "build_record": "build.json",
                   "process": {"command": runtime["core"]["command"],
                               "exit_code": 0, "stdout": "process.txt",
                               "stderr": "process-stderr.txt",
                               "started_ns": started, "finished_ns": finished,
                               "pid": os.getpid(),
                               "guest_pid": runtime["core"]["guest_pid"]},
                   "files": inventory(output)}
        write(output, "receipt.json", encoded(receipt) + b"\n")
        return receipt
    except Exception as error:
        write(output, "failure.json", encoded({"lane": lane, "candidate_sha": candidate,
              "error": str(error), "status": "FAILED", "ended_ns": time.time_ns()}) + b"\n")
        raise


def check_raw_archive(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("archive root is a symlink or absent")
    for directory, names, files in os.walk(root, followlinks=False):
        for name in names + files:
            path = Path(directory) / name
            if path.is_symlink() or path.is_file() and path.stat(follow_symlinks=False).st_nlink != 1:
                raise ValueError("archive contains a symlink or hardlinked raw file")


def verify_process(root, record, name, command, earliest, latest):
    if (record.get("command") != command or record.get("exit_code") != 0
            or record.get("stdout") != f"process/{name}.stdout"
            or record.get("stderr") != f"process/{name}.stderr"
            or not isinstance(record.get("started_ns"), int)
            or not isinstance(record.get("finished_ns"), int)
            or not earliest <= record["started_ns"] <= record["finished_ns"] <= latest):
        raise ValueError(f"{name} command, exit, path, or window differs")
    stdout = (root / record["stdout"]).read_bytes()
    stderr = (root / record["stderr"]).read_bytes()
    if (sha(stdout) != record.get("stdout_sha256")
            or sha(stderr) != record.get("stderr_sha256")):
        raise ValueError(f"{name} process output digest differs")
    return stdout, stderr


def authenticate(root, expected_digest):
    root = Path(root)
    check_raw_archive(root)
    if not SHA256.fullmatch(expected_digest):
        raise ValueError("independent archive provenance is missing")
    if independent_gates.archive_digest(root) != expected_digest:
        raise ValueError("independent archive provenance digest differs")
    receipt = json.loads((root / "receipt.json").read_bytes())
    independent_gates._inventory(root, receipt)
    return receipt


def pack(archive, expected_digest, package):
    archive, package = Path(archive), Path(package)
    authenticate(archive, expected_digest)
    if package.exists() or package.is_relative_to(archive):
        raise ValueError("transport package path is occupied or inside archive")
    files = inventory(archive)
    package.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package, "x", compression=zipfile.ZIP_STORED) as bundle:
        bundle.writestr("__dyn4k_transport_manifest.json", encoded({
            "archive_sha256": expected_digest, "files": files}) + b"\n")
        for item in files:
            bundle.write(archive / item["path"], item["path"])
    return digest(package)


def unpack(package, target, expected_digest):
    package, target = Path(package), Path(target)
    if target.exists():
        raise ValueError("transport destination already exists")
    with zipfile.ZipFile(package) as bundle:
        names = bundle.namelist()
        if names.count("__dyn4k_transport_manifest.json") != 1 or len(names) != len(set(names)):
            raise ValueError("transport members are missing or duplicated")
        metadata = json.loads(bundle.read("__dyn4k_transport_manifest.json"))
        files = metadata.get("files")
        if (metadata.get("archive_sha256") != expected_digest or not isinstance(files, list)
                or set(names) != {"__dyn4k_transport_manifest.json"} |
                   {item["path"] for item in files}):
            raise ValueError("transport inventory differs")
        target.mkdir(parents=True)
        for item in files:
            relative = item["path"]
            independent_gates._file_path_name(relative)
            if relative == "__dyn4k_transport_manifest.json":
                raise ValueError("transport member name is reserved")
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = bundle.read(relative)
            if sha(raw) != item["sha256"]:
                raise ValueError("transport member hash differs")
            path.write_bytes(raw)
            os.utime(path, ns=(item["mtime_ns"], item["mtime_ns"]))
    authenticate(target, expected_digest)
    return target


def verify(repository, candidate, lane, archive, archive_digest, hashes,
           expected_runtime_identity, expected_executables, trusted_toolchain,
           adb, serial, replay_output):
    if Path(archive).is_symlink():
        raise ValueError("archive root is a symlink")
    repository, archive, adb, replay_output = (Path(path).resolve() for path in
                                              (repository, archive, adb, replay_output))
    selected = route(lane)
    manifest, contract = selected_cases(repository, lane)
    if (set(hashes) != set(MODULES) or set(expected_executables) != {"core", "facade"}
            or any(not SHA256.fullmatch(str(value)) for value in
                   list(hashes.values()) + list(expected_executables.values()))):
        raise ValueError("independent staged or executable hashes are incomplete")
    receipt = authenticate(archive, archive_digest)
    if (receipt.get("candidate_sha") != candidate or receipt.get("lane") != lane
            or receipt.get("status") != "PASSED"
            or receipt.get("source_tree") != git(repository, "rev-parse", f"{candidate}^{{tree}}").decode().strip()
            or receipt.get("consumer_group") != "full-suite"
            or receipt.get("consumer_contract_sha256") != independent_gates.digest(contract)
            or receipt.get("artifact_hashes") != hashes
            or receipt.get("executable_hashes") != expected_executables
            or receipt.get("runtime_identity") != expected_runtime_identity
            or receipt.get("toolchain") != trusted_toolchain
            or receipt.get("source_hashes") != source_hashes(repository, candidate)
            or receipt.get("abi") != selected["abi"] or receipt.get("api") != selected["api"]
            or receipt.get("link_mode") != selected["link"]
            or any(receipt.get(key) != selected[key] for key in
                   ("target", "runtime", "version", "configuration"))):
        raise ValueError("archive differs from exact candidate, lane, or independent inputs")
    if any(digest(repository / path) != value
           for path, value in receipt["source_hashes"].items()):
        raise ValueError("local public verifier or consumer source differs from candidate")
    if (trusted_toolchain.get("java_version", "").find('version "21') == -1
            or trusted_toolchain.get("gradle_version") != "Gradle 9.5.0"
            or trusted_toolchain.get("kgp_version") != "2.4.20"
            or trusted_toolchain.get("agp_version") != "9.3.1"
            or trusted_toolchain.get("adb_sha256") != digest(adb)):
        raise ValueError("pinned or independently selected toolchain differs")
    sources = original_sources(repository, candidate, contract["cases"])
    inputs = input_content(sources, contract["cases"])
    for name, raw in inputs.items():
        if (archive / "inputs" / name).read_bytes() != raw:
            raise ValueError("archived original source or method input differs")
    if receipt.get("source_inventory_sha256") != sha(inputs["source-inventory.tsv"]):
        raise ValueError("archived source inventory digest differs")
    graph = json.loads((archive / receipt["provider_graph"]).read_bytes())
    verify_graph(graph, selected["target"], hashes)
    if set(receipt["resolved_artifacts"]) != set(MODULES):
        raise ValueError("both staged target artifacts are required")
    for module in MODULES:
        relative = receipt["resolved_artifacts"][module]
        independent_gates._file_path_name(relative)
        if (relative != "resolved/" + staged_binary(Path("/"), module,
                                                     selected["target"]).name
                or digest(archive / relative) != hashes[module]):
            raise ValueError("archived resolved target KLIB differs")
    if receipt.get("build_record") != "build.json":
        raise ValueError("original link evidence is absent")
    build_evidence = json.loads((archive / "build.json").read_bytes())
    original = {key: build_evidence.get(key) for key in
                ("repository", "staging", "output", "work", "gradle")}
    if (any(not isinstance(value, str) or not Path(value).is_absolute()
            for value in original.values())
            or build_evidence.get("gradle_sha256") != trusted_toolchain["gradle_sha256"]
            or build_evidence.get("provider_graph_sha256") != digest(archive / receipt["provider_graph"])
            or build_evidence.get("staged_inputs") != {
                module: {"path": str(staged_binary(Path(original["staging"]), module,
                                                    selected["target"])), "sha256": hashes[module]}
                for module in MODULES}
            or build_evidence.get("linked_outputs") != {
                module: {"path": str(build_program(Path(original["work"]), module, selected)),
                         "sha256": expected_executables[module],
                         "archived_path": f"runtime/{module}.kexe"}
                for module in ("core", "facade")}):
        raise ValueError("original link inputs, outputs, or tool differ")
    build_command_line = build_command(Path(original["repository"]),
        Path(original["staging"]), Path(original["output"]), Path(original["work"]),
        Path(original["gradle"]), selected, hashes)
    build_stdout, _ = verify_process(archive, build_evidence["process"], "gradle",
        build_command_line, receipt["process"]["started_ns"], receipt["process"]["finished_ns"])
    build_log = build_stdout.decode(errors="replace")
    if "BUILD SUCCESSFUL" not in build_log:
        raise ValueError("external build did not complete")
    for module in ("core", "facade"):
        task = f"> Task :{module}:link{selected['link']}Test{selected['target'][0].upper() + selected['target'][1:]}"
        if task not in build_log:
            raise ValueError("selected native linker mode was not run")
    guest = json.loads((archive / receipt["guest_record"]).read_bytes())
    check_guest(selected, guest, serial)
    if independent_gates.digest(guest) != expected_runtime_identity:
        raise ValueError("independent guest identity differs")
    runtime = json.loads((archive / receipt["runtime_record"]).read_bytes())
    if (set(runtime) != {"core", "facade"}
            or len(receipt.get("raw_consumer_events", [])) != 2
            or len(receipt.get("consumer_xml", [])) != 2):
        raise ValueError("both native guest method streams are required")
    observed = []
    previous_finish = build_evidence["process"]["finished_ns"]
    for module, source_module in (("core", "dyn4k-core"), ("facade", "dyn4k")):
        binary = archive / f"runtime/{module}.kexe"
        if check_executable(binary, selected) != expected_executables[module]:
            raise ValueError("archived mode executable differs from independent hash")
        record = runtime[module]
        remote = (f"/data/local/tmp/dyn4k-full-{candidate[:12]}-"
                  f"{selected['target'].lower()}-{selected['link'].lower()}-{module}")
        operations = record.get("operations", {})
        proof = "pull" if selected["api"] == 21 else "remote_hash"
        if record.get("remote") != remote or set(operations) != {"push", "chmod", proof}:
            raise ValueError("guest installation operations or path differ")
        original_binary = str(Path(original["output"]) / f"runtime/{module}.kexe")
        push_stdout, push_stderr = verify_process(archive, operations["push"],
            module + "-push", adb_command(adb, serial, "push", original_binary, remote),
            previous_finish, receipt["process"]["finished_ns"])
        if (push_stdout or not re.search(rb"(?m)^" + re.escape(original_binary.encode()) +
                rb": 1 file pushed, 0 skipped\. .*\(" + str(binary.stat().st_size).encode() +
                rb" bytes in ", push_stderr)):
            raise ValueError("guest push output does not identify linked ELF bytes")
        chmod_stdout, chmod_stderr = verify_process(archive, operations["chmod"],
            module + "-chmod", adb_command(adb, serial, "shell", "chmod", "700", remote),
            operations["push"]["finished_ns"], receipt["process"]["finished_ns"])
        if chmod_stdout or chmod_stderr:
            raise ValueError("guest chmod output differs")
        if selected["api"] == 21:
            installed = str(Path(original["output"]) / f"installed/{module}.kexe")
            proof_command = adb_command(adb, serial, "pull", remote, installed)
        else:
            proof_command = adb_command(adb, serial, "shell", "sha256sum", remote)
        proof_stdout, proof_stderr = verify_process(archive, operations[proof],
            module + "-" + ("pull" if selected["api"] == 21 else "remote-hash"),
            proof_command, operations["chmod"]["finished_ns"],
            receipt["process"]["finished_ns"])
        if selected["api"] == 21:
            if (proof_stdout or not re.search(rb"(?m)^" + re.escape(remote.encode()) +
                    rb": 1 file pulled, 0 skipped\. .*\(" + str(binary.stat().st_size).encode() +
                    rb" bytes in ", proof_stderr)):
                raise ValueError("guest pull output does not identify installed ELF bytes")
        elif proof_stderr or proof_stdout.strip().decode() != f"{expected_executables[module]}  {remote}":
            raise ValueError("guest installed ELF hash output differs")
        raw, guest_stderr = verify_process(archive, record, module + "-guest",
            guest_command(adb, serial, remote, lane), operations[proof]["finished_ns"],
            receipt["process"]["finished_ns"])
        if (guest_stderr or raw.count(f"QUALIFICATION_LANE={lane}".encode()) != 1
                or raw.count(f"QUALIFICATION_GUEST_PID={record['guest_pid']}".encode()) != 1):
            raise ValueError("guest process identity or stderr differs")
        previous_finish = record["finished_ns"]
        if (record["exit_code"] != 0 or record["binary_sha256"] != expected_executables[module]
                or record["command"] != guest_command(
                    record["command"][0], serial, record["remote"], lane)
                or record["guest_pid"] <= 0
                or record["stdout"] != f"process/{module}-guest.stdout"):
            raise ValueError("recorded guest process or selected binary differs")
        if f"QUALIFICATION_GUEST_PID={record['guest_pid']}".encode() not in raw:
            raise ValueError("guest process identity is not present in original events")
        ids, xml = parse_guest(raw, case_map(contract["cases"], source_module))
        if (receipt["raw_consumer_events"].count(record["stdout"]) != 1
                or receipt["consumer_xml"].count(f"reports/{module}.xml") != 1
                or (archive / f"reports/{module}.xml").read_bytes() != xml):
            raise ValueError("normalized XML differs from original guest event stream")
        if selected["api"] == 21:
            if (record.get("installed_path") != f"installed/{module}.kexe"
                    or digest(archive / record["installed_path"]) != expected_executables[module]
                    or not (archive / f"process/{module}-pull.stderr").is_file()):
                raise ValueError("pulled API 21 guest executable hash differs")
        observed.extend(ids)
    expected = {case["id"] for case in contract["cases"]}
    if len(observed) != 2523 or len(set(observed)) != 2523 or set(observed) != expected:
        raise ValueError("original selected methods are missing or duplicated")
    process = receipt["process"]
    if (process["command"] != runtime["core"]["command"]
            or process["guest_pid"] != runtime["core"]["guest_pid"]
            or process["exit_code"] != 0 or lane not in process["command"]):
        raise ValueError("public process record differs from native guest execution")
    output_lines = (archive / process["stdout"]).read_text().splitlines()
    for relative, label in [(receipt["provider_graph"], "PROVIDER_GRAPH"),
                             *[(path, "CONSUMER_XML") for path in receipt["consumer_xml"]],
                             *[(path, "RESOLVED_" + module.upper().replace("-", "_"))
                               for module, path in receipt["resolved_artifacts"].items()]]:
        if f"QUALIFICATION_{label}_SHA256={digest(archive / relative)}" not in output_lines:
            raise ValueError("public process output does not bind staged bytes or method XML")
    if f"QUALIFICATION_LANE={lane}" not in output_lines or "QUALIFICATION_PROCESS_EXIT=0" not in output_lines:
        raise ValueError("public process output lacks lane or guest exit marker")
    for module in ("core", "facade"):
        if (f"QUALIFICATION_RAW_GUEST_{module.upper()}_SHA256={digest(archive / runtime[module]['stdout'])}"
                not in output_lines
                or f"QUALIFICATION_GUEST_{module.upper()}_PID={runtime[module]['guest_pid']}"
                not in output_lines):
            raise ValueError("public output does not bind original guest events or process")
    if replay_output.exists() and any(replay_output.iterdir()):
        raise ValueError("live replay output must be empty")
    replay_output.mkdir(parents=True, exist_ok=True)
    current_guest = guest_query(adb, serial, replay_output)
    check_guest(selected, current_guest, serial)
    for key in ("fingerprint", "avd_name", "api", "primary_abi", "abi_list"):
        if current_guest[key] != guest[key]:
            raise ValueError("live replay guest differs from archived runtime identity")
    for module, source_module in (("core", "dyn4k-core"), ("facade", "dyn4k")):
        remote = f"/data/local/tmp/dyn4k-replay-{candidate[:12]}-{selected['target'].lower()}-{selected['link'].lower()}-{module}"
        record = run_guest(adb, serial, remote, archive / f"runtime/{module}.kexe",
                           lane, replay_output, module)
        ids, _ = parse_guest((replay_output / record["stdout"]).read_bytes(),
                             case_map(contract["cases"], source_module))
        if len(ids) != (2465 if module == "core" else 58):
            raise ValueError("live replay did not execute every selected method")
    check_raw_archive(archive)
    if independent_gates.archive_digest(archive) != archive_digest:
        raise ValueError("archive changed during public replay")
    gate = independent_gates.evaluate_gate(
        "staged-consumer", archive, candidate, lane, manifest["lanes"][lane],
        repository, hashes, expected_runtime_identity,
        expected_archive_digest=archive_digest, manifest=manifest)
    if gate["status"] != "PASSED" or gate.get("complete_selected_suite") is not True:
        raise ValueError(f"generic staged consumer gate failed: {gate['reason']}")
    return {"status": "PASSED", "lane": lane, "selected_cases": 2523,
            "archive_sha256": archive_digest, "candidate_sha": candidate,
            "gate": gate}


def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("run", "verify"):
        action = actions.add_parser(name)
        action.add_argument("--repository", type=Path, required=True)
        action.add_argument("--candidate", required=True)
        action.add_argument("--lane", required=True)
        action.add_argument("--adb", type=Path, required=True)
        action.add_argument("--serial", required=True)
        action.add_argument("--core-sha256", required=True)
        action.add_argument("--facade-sha256", required=True)
        if name == "run":
            action.add_argument("--staging", type=Path, required=True)
            action.add_argument("--output", type=Path, required=True)
            action.add_argument("--work", type=Path, required=True)
            action.add_argument("--gradle", type=Path, required=True)
        else:
            action.add_argument("--archive", type=Path, required=True)
            action.add_argument("--archive-sha256", required=True)
            action.add_argument("--runtime-identity", required=True)
            action.add_argument("--core-executable-sha256", required=True)
            action.add_argument("--facade-executable-sha256", required=True)
            action.add_argument("--trusted-toolchain", type=Path, required=True)
            action.add_argument("--replay-output", type=Path, required=True)
    package = actions.add_parser("pack")
    package.add_argument("--archive", type=Path, required=True)
    package.add_argument("--archive-sha256", required=True)
    package.add_argument("--package", type=Path, required=True)
    extract = actions.add_parser("unpack")
    extract.add_argument("--package", type=Path, required=True)
    extract.add_argument("--archive-sha256", required=True)
    extract.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "pack":
        print(json.dumps({"package_sha256": pack(args.archive, args.archive_sha256,
                                                   args.package)}, sort_keys=True))
        return
    if args.action == "unpack":
        print(json.dumps({"archive": str(unpack(args.package, args.output,
                                                  args.archive_sha256))}, sort_keys=True))
        return
    hashes = {"dyn4k-core": args.core_sha256, "dyn4k": args.facade_sha256}
    if args.action == "run":
        receipt = run(args.repository, args.candidate, args.lane, args.staging,
                      args.output, args.work, args.gradle, args.adb, args.serial, hashes)
        print(json.dumps({"status": receipt["status"], "lane": receipt["lane"],
                          "runtime_identity": receipt["runtime_identity"],
                          "executable_hashes": receipt["executable_hashes"],
                          "archive_sha256": independent_gates.archive_digest(args.output)},
                         sort_keys=True))
    else:
        trusted = json.loads(args.trusted_toolchain.read_bytes())
        result = verify(args.repository, args.candidate, args.lane, args.archive,
                        args.archive_sha256, hashes, args.runtime_identity,
                        {"core": args.core_executable_sha256,
                         "facade": args.facade_executable_sha256}, trusted,
                        args.adb, args.serial, args.replay_output)
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
