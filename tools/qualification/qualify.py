#!/usr/bin/env python3
import argparse
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tarfile
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
import tarfile
from pathlib import Path


SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
VERSION = "0.1.0-alpha.1"
GROUP = "io.github.rubixhacker"
MODULES = ("dyn4k-core", "dyn4k")
KOTLIN_VERSION = "2.4.20"
POM_PROJECT_URL = "https://github.com/rubixhacker/dyn4k"
POM_LICENSE_NAME = "BSD 3-Clause License"
POM_LICENSE_URL = "https://opensource.org/licenses/BSD-3-Clause"
POM_DEVELOPER_ID = "rubixhacker"
POM_DEVELOPER_NAME = "Stewart Boling"
POM_MODULE_DESCRIPTIONS = {
    "dyn4k-core": ("dyn4k core", "Kotlin Multiplatform dyn4j 6.0.0 compatible foundation"),
    "dyn4k": ("dyn4k", "Kotlin conveniences for the dyn4k core"),
}
APPLE_TARGETS = {"iosArm64", "iosSimulatorArm64", "iosX64", "macosArm64",
                 "tvosArm64", "tvosSimulatorArm64", "watchosArm64",
                 "watchosDeviceArm64", "watchosSimulatorArm64"}
APPROVED_COMPLETE_SUITE_SHA256 = "9aa2f50dd3c38129a70f4ed042f2b7ae5a90d4234def40d70520aad13f36b3fc"


def matrix():
    groups = [
        ("jvm", ["Java"], "8", "jvm"),
        ("android", ["Android JVM"], "API 21", "android"),
        ("js", ["Chromium", "Firefox", "Safari", "Node.js"], "119/120/18.2/22.0.0", "web"),
        ("wasmJs", ["Chromium", "Firefox", "Safari", "Node.js"], "119/120/18.2/22.0.0", "web"),
        ("wasmWasi", ["Node.js", "Wasmtime"], "24.15.0/37.0.0", "web"),
        ("linuxX64", ["Linux x64"], "kernel 4.9.156 glibc 2.19", "native"),
        ("linuxArm64", ["Linux ARM64"], "kernel 4.9.156 glibc 2.25", "native"),
        ("mingwX64", ["Windows x64"], "Windows 10 1507 build 10240", "native"),
        ("macosArm64", ["macOS ARM64"], "macOS 11", "native"),
        ("iosArm64", ["iOS physical ARM64"], "iOS 15", "native"),
        ("iosSimulatorArm64", ["iOS simulator ARM64"], "iOS 15", "native"),
        ("iosX64", ["iOS simulator x64"], "iOS 15", "native"),
        ("tvosArm64", ["tvOS physical ARM64"], "tvOS 15", "native"),
        ("tvosSimulatorArm64", ["tvOS simulator ARM64"], "tvOS 15", "native"),
        ("watchosArm64", ["watchOS physical ILP32"], "watchOS 8", "native"),
        ("watchosDeviceArm64", ["watchOS physical LP64"], "watchOS 26", "native"),
        ("watchosSimulatorArm64", ["watchOS simulator ARM64"], "watchOS 8", "native"),
        ("androidNativeArm32", ["Android Native armeabi-v7a"], "API 21", "native"),
        ("androidNativeArm64", ["Android Native arm64-v8a"], "API 21", "native"),
        ("androidNativeX86", ["Android Native x86"], "API 21", "native"),
        ("androidNativeX64", ["Android Native x86_64"], "API 21", "native"),
    ]
    rows = []
    web_floors = {"Chromium": "119", "Firefox": "120", "Safari": "18.2", "Node.js": "22.0.0"}
    for target, runtimes, floor, kind in groups:
        for runtime in runtimes:
            minimum = floor
            if target in ("js", "wasmJs"):
                minimum = web_floors[runtime]
            elif target == "wasmWasi":
                minimum = "24.15.0 without experimental Wasm flags" if runtime == "Node.js" else "37.0.0 with -W gc=y -W exceptions=y -W function-references=y"
            rows.append({"target": target, "runtime": runtime, "minimum": minimum, "kind": kind})
    assert len(rows) == 28 and len({row["target"] for row in rows}) == 21
    return rows


def expand(rows):
    configs = {"jvm": ("no-optimize", "default"),
               "android": ("debug", "r8-optimized"),
               "web": ("development", "production"),
               "native": ("debug-g", "optimized-opt")}
    return [{**row, "version": version, "configuration": config,
             "id": f'{row["target"]}:{row["runtime"]}:{version}:{config}'}
            for row in rows for version in ("minimum", "current")
            for config in configs[row["kind"]]]


def target_publication_name(module, target):
    suffix = target.lower().replace("wasmjs", "wasm-js").replace("wasmwasi", "wasm-wasi")
    return f"{module}-{suffix}"


def matrix_targets():
    return {row["target"] for row in matrix()}


def check_providers(graph):
    if re.search(r"(?:^|\W)org\.dyn4j:dyn4j(?::|\W)", graph) and re.search(
        r"(?:^|\W)io\.github\.rubixhacker:dyn4k-core(?:-jvm)?(?::|\W)", graph
    ):
        raise ValueError("duplicate org.dyn4j provider: exclude org.dyn4j:dyn4j from the consumer dependency graph")


def target_binary_path(module, target):
    publication = target_publication_name(module, target)
    extension = ".aar" if target == "android" else ".jar" if target == "jvm" else ".klib"
    return f'{GROUP.replace(".", "/")}/{publication}/{VERSION}/{publication}-{VERSION}{extension}'


def publication_binary_path(module, target):
    if target is not None:
        return target_binary_path(module, target)
    return f'{GROUP.replace(".", "/")}/{module}/{VERSION}/{module}-{VERSION}.jar'


def publication_variant_contract(module, target):
    name = module if target is None else target_publication_name(module, target)
    base = f"{name}-{VERSION}"
    prefix = "metadata" if target is None else target
    published = "" if target is None else "-published"
    def variant(kind, url=None, file_name=None, library=False):
        entry = {"name": f"{prefix}{kind}Elements{published}", "kind": kind, "target": target}
        if url is not None:
            entry["url"] = url
            entry["file_name"] = file_name or url
        if library:
            dependencies = {("org.jetbrains.kotlin", "kotlin-stdlib", KOTLIN_VERSION)}
            if target == "js":
                dependencies.add(("org.jetbrains.kotlin", "kotlin-dom-api-compat", KOTLIN_VERSION))
            if module == "dyn4k":
                dependencies.add((GROUP, "dyn4k-core", VERSION))
            entry["dependencies"] = dependencies
        else:
            entry["dependencies"] = set()
        return entry
    binary = Path(publication_binary_path(module, target)).name
    binary_name = binary
    if target is None:
        binary_name = f"{module}-metadata-{VERSION}.jar"
    elif target == "android":
        binary_name = f"{module}.aar"
    elif target not in ("jvm", "js", "wasmJs", "wasmWasi"):
        binary_name = f"{module}-{target}Main-{VERSION}.klib"
    sources = f"{base}-sources.jar"
    source_name = f"{module}-kotlin-{VERSION}-sources.jar" if target is None else sources
    variants = [variant("Api", binary, binary_name, library=True),
                variant("Sources", sources, source_name)]
    if target in ("jvm", "android", "js", "wasmJs", "wasmWasi"):
        variants.insert(1, variant("Runtime", binary, binary_name, library=True))
    if target in APPLE_TARGETS:
        metadata = f"{base}-metadata.jar"
        variants.append(variant("Metadata", metadata, metadata, library=True))
    if target is None:
        for mapped in matrix_targets():
            mapped_name = target_publication_name(module, mapped)
            available = {"group": GROUP, "module": mapped_name, "version": VERSION,
                         "url": f"../../{mapped_name}/{VERSION}/{mapped_name}-{VERSION}.module"}
            kinds = ["Api", "Sources"]
            if mapped in ("jvm", "android", "js", "wasmJs", "wasmWasi"):
                kinds.append("Runtime")
            if mapped in APPLE_TARGETS:
                kinds.append("Metadata")
            for kind in kinds:
                variants.append({"name": f"{mapped}{kind}Elements-published",
                                 "kind": kind, "target": mapped,
                                 "available-at": available})
    return {entry["name"]: entry for entry in variants}


def pom_dependency_contract(module, target):
    stdlib = ("kotlin-stdlib-js" if target == "js" else
              "kotlin-stdlib-wasm-js" if target == "wasmJs" else
              "kotlin-stdlib-wasm-wasi" if target == "wasmWasi" else "kotlin-stdlib")
    scope = "runtime" if target is None else "compile"
    dependencies = {("org.jetbrains.kotlin", stdlib, KOTLIN_VERSION, scope)}
    if target == "js":
        dependencies.add(("org.jetbrains.kotlin", "kotlin-dom-api-compat", KOTLIN_VERSION, scope))
    if module == "dyn4k":
        core = "dyn4k-core" if target is None else target_publication_name("dyn4k-core", target)
        dependencies.add((GROUP, core, VERSION, scope))
    return dependencies


def pom_metadata_contract(module):
    title, description = POM_MODULE_DESCRIPTIONS[module]
    return {
        "name": title,
        "description": description,
        "url": POM_PROJECT_URL,
        "licenses": {"license": {"name": POM_LICENSE_NAME, "url": POM_LICENSE_URL}},
        "developers": {"developer": {"id": POM_DEVELOPER_ID, "name": POM_DEVELOPER_NAME}},
        "scm": {"url": POM_PROJECT_URL},
    }


def pom_element_matches(element, name, expected):
    namespace = "{http://maven.apache.org/POM/4.0.0}"
    if element is None or element.tag != namespace + name or element.attrib:
        return False
    if isinstance(expected, str):
        return not len(element) and element.text == expected
    return (not (element.text or "").strip() and len(element) == len(expected)
            and all(pom_element_matches(child, key, value) and not (child.tail or "").strip()
                    for child, (key, value) in zip(element, expected.items())))


def source_sets_for_publication(module, target):
    if module == "dyn4k":
        return {"commonMain"}
    platform = ("nativeMain" if target is None or target not in
                {"jvm", "android", "js", "wasmJs", "wasmWasi"} else
                {"jvm": "jvmMain", "android": "androidMain", "js": "jsMain",
                 "wasmJs": "wasmJsMain", "wasmWasi": "wasmWasiMain"}[target])
    return {"commonMain", platform}


def candidate_source_contract(repository, candidate_sha):
    source_files = {}
    if (repository / ".git").exists():
        # Read Git blobs directly; archive substitutions and line endings can change source bytes.
        tree = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "ls-tree", "-r", "-z", "--full-tree",
             candidate_sha, "--", "dyn4k-core/src", "dyn4k/src"], stderr=subprocess.PIPE)
        blobs = []
        for entry in tree.split(b"\0"):
            if not entry:
                continue
            metadata, name = entry.split(b"\t", 1)
            mode, kind, oid = metadata.split()
            path = os.fsdecode(name)
            if path.endswith((".kt", ".java")):
                if mode not in (b"100644", b"100755") or kind != b"blob":
                    raise ValueError(f"candidate source is not a regular file: {path}")
                blobs.append((path, oid))
        contents = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "cat-file", "--batch"],
            input=b"".join(oid + b"\n" for _, oid in blobs), stderr=subprocess.PIPE)
        stream = io.BytesIO(contents)
        for path, oid in blobs:
            header = stream.readline().rstrip(b"\n")
            prefix = oid + b" blob "
            size_field = header[len(prefix):]
            if (not header.startswith(prefix)
                    or re.fullmatch(rb"0|[1-9][0-9]*", size_field) is None):
                raise ValueError(f"candidate source blob is invalid: {path}")
            size = int(size_field)
            source = stream.read(size)
            if len(source) != size or stream.read(1) != b"\n":
                raise ValueError(f"candidate source blob is incomplete: {path}")
            source_files[path] = source
        if stream.read(1):
            raise ValueError("candidate source blob response has unexpected data")
    else:
        for module in MODULES:
            for source in (repository / module / "src").glob("*Main/*/**/*"):
                if source.is_file() and source.suffix in (".kt", ".java"):
                    source_files[source.relative_to(repository).as_posix()] = source.read_bytes()
        descriptor = repository / "dyn4k-core/src/jvmModule/java/module-info.java"
        if descriptor.is_file():
            source_files[descriptor.relative_to(repository).as_posix()] = descriptor.read_bytes()
    result = {module: {} for module in MODULES}
    for path, contents in source_files.items():
        parts = Path(path).parts
        if path == "dyn4k-core/src/jvmModule/java/module-info.java":
            result["dyn4k-core"]["jvmModule/module-info.java"] = hashlib.sha256(contents).hexdigest()
            continue
        if (len(parts) < 6 or parts[0] not in MODULES or parts[1] != "src"
                or not parts[2].endswith("Main") or parts[3] not in ("kotlin", "java")):
            continue
        module, source_set = parts[0], parts[2]
        jar_path = "/".join((source_set, *parts[4:]))
        if jar_path in result[module]:
            raise ValueError(f"duplicate candidate source path: {jar_path}")
        result[module][jar_path] = hashlib.sha256(contents).hexdigest()
    if any(not sources for sources in result.values()):
        raise ValueError("candidate source tree is missing required module sources")
    return result


def expected_source_entries(source_contract, module, target):
    return {path: sha for path, sha in source_contract[module].items()
            if path.split("/", 1)[0] in source_sets_for_publication(module, target)
            or (module == "dyn4k-core" and target == "jvm"
                and path == "jvmModule/module-info.java")}


def archive_file_names(archive):
    names = archive.namelist()
    if len(names) != len(set(names)) or archive.testzip() is not None:
        raise ValueError("archive has duplicate entries or a corrupt member")
    return {name for name in names if not name.endswith("/")}


def validate_source_archive(path, expected):
    with zipfile.ZipFile(path) as archive:
        names = archive_file_names(archive)
        if names != set(expected) | {"META-INF/MANIFEST.MF"}:
            raise ValueError("source entries differ from exact candidate source tree")
        if archive.read("META-INF/MANIFEST.MF") != b"Manifest-Version: 1.0\r\n\r\n":
            raise ValueError("source JAR manifest differs from publication contract")
        if any(hashlib.sha256(archive.read(name)).hexdigest() != sha
               for name, sha in expected.items()):
            raise ValueError("source bytes differ from exact candidate source tree")


def validate_generated_docs(jar_path, generated, license_bytes):
    if not generated.is_dir():
        raise ValueError("generated Dokka output is missing")
    expected = {path.relative_to(generated).as_posix(): path
                for path in generated.rglob("*") if path.is_file()}
    if not expected or "index.html" not in expected:
        raise ValueError("generated Dokka output is incomplete")
    with zipfile.ZipFile(jar_path) as archive:
        names = archive_file_names(archive)
        if names != set(expected) | {"META-INF/MANIFEST.MF", "META-INF/LICENSE.md"}:
            raise ValueError("API documentation entries differ from generated Dokka output")
        if archive.read("META-INF/MANIFEST.MF") != b"Manifest-Version: 1.0\r\n\r\n":
            raise ValueError("API documentation JAR manifest differs from publication contract")
        if archive.read("META-INF/LICENSE.md") != license_bytes:
            raise ValueError("API documentation license notice differs from repository license")
        if any(archive.read(name) != path.read_bytes() for name, path in expected.items()):
            raise ValueError("API documentation bytes differ from generated Dokka output")


def validate_apple_metadata(metadata_jar, klib):
    with zipfile.ZipFile(metadata_jar) as archive:
        if archive_file_names(archive) != {"META-INF/MANIFEST.MF"}:
            raise ValueError("Apple metadata JAR entries differ from publication contract")
        if archive.read("META-INF/MANIFEST.MF") != b"Manifest-Version: 1.0\r\n\r\n":
            raise ValueError("Apple metadata JAR manifest differs from publication contract")
    with zipfile.ZipFile(klib) as archive:
        names = archive_file_names(archive)
        if (not {"default/manifest", "default/linkdata/module", "default/ir/bodies.knb"} <= names
                or not any(name.startswith("default/linkdata/package_") and name.endswith(".knm")
                           for name in names)
                or any(not archive.read(name) for name in
                       ("default/manifest", "default/linkdata/module", "default/ir/bodies.knb"))):
            raise ValueError("Apple KLIB metadata structure is incomplete")


def variant_attributes(target, kind):
    platform = ("common" if target is None else "jvm" if target == "jvm" else
                "androidJvm" if target == "android" else "js" if target == "js" else
                "wasm" if target in ("wasmJs", "wasmWasi") else "native")
    usage = ("kotlin-metadata" if (target is None and kind == "Api") or kind == "Metadata" else
             "java-api" if kind == "Api" and target in ("jvm", "android") else
             "java-runtime" if kind in ("Runtime", "Sources") and target in ("jvm", "android") else
             "kotlin-api" if kind == "Api" else "kotlin-runtime")
    attributes = {"org.gradle.category": "documentation" if kind == "Sources" else "library",
                  "org.gradle.jvm.environment": "standard-jvm" if target == "jvm" else
                  "android" if target == "android" else "non-jvm",
                  "org.gradle.usage": usage,
                  "org.jetbrains.kotlin.platform.type": platform}
    if kind == "Sources":
        attributes.update({"org.gradle.dependency.bundling": "external",
                           "org.gradle.docstype": "sources"})
    if target in ("jvm", "android"):
        attributes["org.gradle.libraryelements"] = "jar" if kind == "Sources" or target == "jvm" else "aar"
    if target == "js":
        attributes["org.jetbrains.kotlin.js.compiler"] = "ir"
    if target in ("wasmJs", "wasmWasi"):
        attributes["org.jetbrains.kotlin.wasm.target"] = "js" if target == "wasmJs" else "wasi"
    if platform == "native":
        native = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", target).lower().replace("android_native_", "android_")
        attributes["org.jetbrains.kotlin.native.target"] = native
    return attributes


def audit_publication_metadata(base, module, target, data):
    name = module if target is None else target_publication_name(module, target)
    errors = []
    if not isinstance(data, dict) or data.get("formatVersion") != "1.1":
        errors.append(f"{name}: Gradle metadata formatVersion differs from publication contract")
    if (not isinstance(data, dict)
            or set(data) != {"formatVersion", "createdBy", "component", "variants"}):
        errors.append(f"{name}: Gradle metadata fields differ from publication contract")
    if isinstance(data, dict) and data.get("createdBy") != {"gradle": {"version": "9.5.0"}}:
        errors.append(f"{name}: Gradle metadata creator differs from publication contract")
    expected_component = {"group": GROUP, "module": module, "version": VERSION}
    if target is not None:
        expected_component["url"] = f"../../{module}/{VERSION}/{module}-{VERSION}.module"
    component = data.get("component") if isinstance(data, dict) else None
    if not isinstance(component, dict) or any(component.get(key) != value for key, value in expected_component.items()):
        errors.append(f"{name}: Gradle component coordinate differs from publication contract")
    if isinstance(component, dict):
        if set(component) != set(expected_component) | {"attributes"}:
            errors.append(f"{name}: Gradle component metadata fields differ from publication contract")
        if component.get("attributes") != {"org.gradle.status": "release"}:
            errors.append(f"{name}: Gradle component status differs from publication contract")
    if target is None and isinstance(component, dict) and "url" in component:
        errors.append(f"{name}: root Gradle component has a parent URL")
    variants = data.get("variants") if isinstance(data, dict) else None
    if not isinstance(variants, list) or any(not isinstance(item, dict) for item in variants):
        return errors + [f"{name}: Gradle variants are invalid"], set()
    actual = {item.get("name"): item for item in variants}
    contract = publication_variant_contract(module, target)
    if len(actual) != len(variants) or set(actual) != set(contract):
        errors.append(f"{name}: Gradle variants differ from publication contract: missing={sorted(set(contract) - set(actual))} extra={sorted(str(item) for item in set(actual) - set(contract))}")
    referenced = set()
    file_hashes = {}
    for variant_name, specification in contract.items():
        item = actual.get(variant_name)
        if not isinstance(item, dict):
            continue
        available = specification.get("available-at")
        expected_fields = ({"name", "attributes", "available-at"} if available is not None else
                           {"name", "attributes", "files"} |
                           ({"dependencies"} if specification["dependencies"] else set()))
        if set(item) != expected_fields:
            errors.append(f"{name}: {variant_name} metadata fields differ from publication contract")
        if item.get("attributes") != variant_attributes(specification["target"], specification["kind"]):
            errors.append(f"{name}: {variant_name} selection attributes differ from publication contract")
        if available is not None:
            if (item.get("available-at") != available or "files" in item
                    or "dependencies" in item):
                errors.append(f"{name}: {variant_name} target mapping differs")
            continue
        if item.get("available-at") is not None:
            errors.append(f"{name}: {variant_name} unexpectedly redirects to another publication")
        dependencies = item.get("dependencies", [])
        if not isinstance(dependencies, list) or any(not isinstance(dep, dict) for dep in dependencies):
            errors.append(f"{name}: {variant_name} dependencies are invalid")
        else:
            observed = {(dep.get("group"), dep.get("module"),
                         dep.get("version", {}).get("requires") if isinstance(dep.get("version"), dict) else None)
                        for dep in dependencies}
            canonical = [{"group": group, "module": dependency_module,
                          "version": {"requires": version}}
                         for group, dependency_module, version in specification["dependencies"]]
            if (len(observed) != len(dependencies) or observed != specification["dependencies"]
                    or any(dep not in canonical for dep in dependencies)):
                errors.append(f"{name}: {variant_name} dependency graph differs from publication contract")
        files = item.get("files")
        if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
            errors.append(f"{name}: {variant_name} must reference one published file")
            continue
        file = files[0]
        url = specification["url"]
        if file.get("url") != url or file.get("name") != specification["file_name"]:
            errors.append(f"{name}: {variant_name} file reference differs from publication contract")
        if set(file) != {"url", "name", "size", "sha512", "sha256", "sha1", "md5"}:
            errors.append(f"{name}: {variant_name} file descriptor fields differ from publication contract")
        path = base / url
        referenced.add(path)
        if not path.is_file():
            errors.append(f"{name}: {variant_name} referenced file missing: {url}")
        else:
            if path not in file_hashes:
                hashes = {algorithm: hashlib.new(algorithm) for algorithm in ("sha512", "sha256", "sha1", "md5")}
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        for value in hashes.values():
                            value.update(block)
                file_hashes[path] = {algorithm: value.hexdigest() for algorithm, value in hashes.items()}
            if file.get("size") != path.stat().st_size or any(
                    file.get(algorithm) != value for algorithm, value in file_hashes[path].items()):
                errors.append(f"{name}: {variant_name} referenced file size or checksum differs from staged bytes")
    return errors, referenced


def full_suite_cases(suite_manifest, lane_id=None):
    if not isinstance(suite_manifest, dict) or suite_manifest.get("kind") != "complete-port":
        raise ValueError("frozen complete suite manifest is unavailable")
    if suite_manifest.get("schema") != 1 or not suite_manifest.get("id"):
        raise ValueError("complete suite manifest identity is invalid")
    cases = suite_manifest.get("cases")
    areas = {"geometry", "collision", "dynamics", "joints", "compatibility"}
    if not isinstance(cases, list) or not cases:
        raise ValueError("complete suite manifest has no cases")
    declared_areas = suite_manifest.get("areas")
    if not isinstance(declared_areas, list) or not all(isinstance(area, str) for area in declared_areas) or set(declared_areas) != areas:
        raise ValueError("complete suite manifest omits a required area")
    identities = []
    covered = set()
    for item in cases:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError("complete suite case identity is invalid")
        if item.get("area") not in areas:
            raise ValueError("complete suite case area is invalid")
        identities.append(item["id"])
        covered.add(item["area"])
    if len(set(identities)) != len(identities) or covered != areas:
        raise ValueError("complete suite cases are duplicate or incomplete")
    lanes = suite_manifest.get("lanes")
    if lane_id is None or lanes is None:
        return identities
    lane = lanes.get(lane_id) if isinstance(lanes, dict) else None
    if not isinstance(lane, dict):
        raise ValueError("complete suite lane is missing")
    scopes = lane.get("case_scopes")
    if (not isinstance(scopes, list) or not scopes
            or len(scopes) != len(set(scopes))
            or not set(scopes) <= {"portable", "jvm-only"}):
        raise ValueError("complete suite lane case scopes are invalid")
    selected = [item["id"] for item in cases if item.get("scope") in scopes]
    if not selected or {item["area"] for item in cases if item.get("scope") in scopes} != areas:
        raise ValueError("complete suite lane cases are incomplete")
    return selected


def validate_complete_suite_bindings(suite_manifest, repository):
    import full_corpus

    if (not isinstance(suite_manifest, dict) or suite_manifest.get("kind") != "complete-port"
            or suite_manifest.get("schema") != 1):
        raise ValueError("complete suite manifest identity is invalid")
    corpus = load_json_strict(repository / full_corpus.MANIFEST_PATH)
    bindings = suite_manifest.get("bindings")
    expected = {
        "corpus_sha256": digest(repository / full_corpus.MANIFEST_PATH),
        "source_tree_sha256": corpus["source_tree_sha256"],
        "original_map_sha256": digest(repository / full_corpus.MAP_PATH),
        "reviewed_pairs_sha256": digest(repository / full_corpus.PAIR_PATH),
        "original_revision": full_corpus.ORIGINAL_REVISION,
    }
    if not isinstance(bindings, dict) or bindings != expected:
        raise ValueError("complete suite reviewed corpus binding differs")
    if corpus.get("policy") != "production" or corpus.get("unresolved"):
        raise ValueError("complete suite reviewed corpus is unresolved")
    cases = suite_manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != len(corpus["cases"]):
        raise ValueError("complete suite case inventory differs from reviewed corpus")
    by_id = {item.get("id"): item for item in cases if isinstance(item, dict)}
    if len(by_id) != len(cases):
        raise ValueError("complete suite has duplicate case identities")
    for source in corpus["cases"]:
        identity = f'{source["module"]}:{source["classname"]}#{source["method"]}'
        item = by_id.get(identity)
        scope = "portable" if source["source_set"] == "commonTest" else "jvm-only"
        if (not isinstance(item, dict) or item.get("scope") != scope
                or item.get("module") != source["module"]
                or item.get("classname") != source["classname"]
                or item.get("method") != source["method"]
                or item.get("kind") != source["kind"]
                or item.get("originals") != source["originals"]
                or item.get("source") != {"path": source["path"],
                                          "sha256": source["sha256"],
                                          "line": source["line"]}):
            raise ValueError(f"complete suite case differs from reviewed corpus: {identity}")
    counts = suite_manifest.get("counts", {})
    if (sum(item.get("scope") == "portable" for item in cases) != 2523
            or sum(item.get("scope") == "jvm-only" for item in cases) != 3
            or counts.get("portable_methods") != 2523
            or counts.get("jvm_only_facade_methods") != 3):
        raise ValueError("complete suite reviewed method counts differ")
    lanes = suite_manifest.get("lanes")
    expected_lanes = {case["id"]: case for case in expand(matrix())}
    if not isinstance(lanes, dict) or set(lanes) != set(expected_lanes):
        raise ValueError("complete suite 112 lane identities differ")
    independent = suite_manifest.get("independent_gates")
    global_gates = suite_manifest.get("global_gates")
    if (not isinstance(independent, dict) or not independent
            or not isinstance(global_gates, list) or not global_gates
            or len(global_gates) != len(set(global_gates))
            or not set(global_gates) <= set(independent)):
        raise ValueError("complete suite independent gate inventory is invalid")
    for lane_id, case in expected_lanes.items():
        lane = lanes[lane_id]
        required_scopes = ["portable", "jvm-only"] if case["target"] == "jvm" else ["portable"]
        if (not isinstance(lane, dict)
                or any(lane.get(key) != case[key] for key in
                       ("target", "runtime", "version", "configuration"))
                or lane.get("case_scopes") != required_scopes
                or not isinstance(lane.get("required_gates"), list)
                or not lane["required_gates"]
                or len(lane["required_gates"]) != len(set(lane["required_gates"]))
                or not set(lane["required_gates"]) <= set(independent)):
            raise ValueError(f"complete suite lane contract differs: {lane_id}")
        full_suite_cases(suite_manifest, lane_id)
    if manifest_digest(suite_manifest) != APPROVED_COMPLETE_SUITE_SHA256:
        raise ValueError("complete suite differs from independently reviewed manifest")


def evaluate(case, evidence, candidate_sha=None, candidate_manifest=None,
             suite_manifest=None, artifact_audit=None):
    result = {"id": case["id"], "status": "NOT_RUN"}
    if evidence is None:
        result["reason"] = "no evidence supplied"
        return result
    if not isinstance(evidence, dict):
        return {**result, "status": "FAILED", "reason": "evidence must be an object"}
    if evidence.get("unavailable_reason"):
        result.update(status="UNAVAILABLE", reason=evidence["unavailable_reason"])
        return result
    required = ("candidate_sha", "runtime_identity", "runtime_version", "expected",
                "executed", "failures", "skipped", "consumer", "suite_id",
                "target", "runtime", "version", "configuration", "case_results",
                "artifact_hashes", "invocation_id", "exit_code", "command",
                "candidate_manifest_sha256", "suite_manifest_sha256", "audit_manifest_sha256")
    missing = [name for name in required if name not in evidence]
    problems = [f"missing {name}" for name in missing]
    if not finite_json(evidence):
        problems.append("non-finite observation is invalid")
    if not SHA40.fullmatch(str(evidence.get("candidate_sha", ""))):
        problems.append("candidate SHA must be a full commit hash")
    if candidate_sha and evidence.get("candidate_sha") != candidate_sha:
        problems.append("candidate SHA differs from report")
    for key in ("target", "runtime", "version", "configuration"):
        if evidence.get(key) != case[key]:
            problems.append(f"{key} differs from lane")
    if not re.fullmatch(r"[0-9a-f]{32}", str(evidence.get("invocation_id", ""))):
        problems.append("fresh execution invocation ID is missing")
    if evidence.get("exit_code") != 0 or not isinstance(evidence.get("command"), list):
        problems.append("successful executable command is missing")
    try:
        cases = full_suite_cases(suite_manifest, case["id"])
    except ValueError as error:
        problems.append(str(error))
        cases = []
    if not isinstance(candidate_manifest, dict) or not isinstance(artifact_audit, dict):
        problems.append("candidate manifest and staged artifact audit are required")
        lane = None
    else:
        if candidate_manifest.get("schema") != 1:
            problems.append("candidate manifest schema is invalid")
        if candidate_manifest.get("candidate_sha") != candidate_sha:
            problems.append("candidate manifest SHA differs from report")
        if artifact_audit.get("candidate_sha") != candidate_sha or artifact_audit.get("status") != "PASSED":
            problems.append("staged artifact audit did not pass for this candidate")
        if suite_manifest and candidate_manifest.get("suite_manifest_sha256") != manifest_digest(suite_manifest):
            problems.append("candidate manifest does not bind frozen suite")
        if candidate_manifest.get("audit_manifest_sha256") != manifest_digest(artifact_audit):
            problems.append("candidate manifest does not bind staged audit")
        for name, source in (("candidate_manifest_sha256", candidate_manifest),
                             ("audit_manifest_sha256", artifact_audit)):
            if evidence.get(name) != manifest_digest(source):
                problems.append(f"{name} differs from frozen candidate evidence")
        if suite_manifest and evidence.get("suite_manifest_sha256") != manifest_digest(suite_manifest):
            problems.append("suite manifest SHA-256 differs from frozen suite")
        lanes = candidate_manifest.get("lanes")
        lane = lanes.get(case["id"]) if isinstance(lanes, dict) else None
        if not isinstance(lane, dict):
            problems.append("selected runtime lane is absent from candidate manifest")
    if lane:
        for key in ("runtime_identity", "runtime_version", "configuration"):
            if not isinstance(lane.get(key), str) or not lane[key] or evidence.get(key) != lane[key]:
                problems.append(f"{key} differs from selected candidate runtime")
        if suite_manifest and (lane.get("suite_id") != suite_manifest.get("id")
                               or evidence.get("suite_id") != suite_manifest.get("id")):
            problems.append("complete suite identity differs from frozen manifest")
        artifacts = artifact_audit.get("artifacts")
        audited = target_binary_hashes(artifacts).get(case["target"], {}) if isinstance(artifacts, list) else {}
        bound_hashes = lane.get("artifact_hashes")
        if not isinstance(bound_hashes, dict) or set(bound_hashes) != set(MODULES):
            problems.append("both target binary hashes are required")
        else:
            for module in MODULES:
                expected_hash = bound_hashes[module]
                if (not SHA64.fullmatch(str(expected_hash)) or audited.get(module) != expected_hash
                        or not isinstance(evidence.get("artifact_hashes"), dict)
                        or evidence["artifact_hashes"].get(module) != expected_hash):
                    problems.append(f"{module} binary hash differs from target audit")
    observations = evidence.get("case_results")
    if not isinstance(observations, list):
        problems.append("complete case results are missing")
    else:
        identities = [item.get("id") for item in observations if isinstance(item, dict)]
        if (len(identities) != len(observations) or not all(isinstance(identity, str) for identity in identities)
                or len(set(identity for identity in identities if isinstance(identity, str))) != len(identities)
                or set(identity for identity in identities if isinstance(identity, str)) != set(cases)):
            problems.append("complete case identities are missing, duplicate, or unexpected")
        if any(not isinstance(item, dict) or item.get("status") != "PASSED"
               for item in observations):
            problems.append("a complete suite case did not pass")
    for key in ("expected", "executed", "failures", "skipped"):
        if type(evidence.get(key)) is not int or evidence[key] < 0:
            problems.append(f"{key} must be a nonnegative integer")
    if all(type(evidence.get(key)) is int for key in ("expected", "executed", "failures", "skipped")):
        if not cases or evidence["expected"] != len(cases) or evidence["executed"] != len(cases):
            problems.append("suite counts differ from frozen expected cases")
        if evidence["failures"] or evidence["skipped"]:
            problems.append("failed or skipped tests")
    if evidence.get("consumer") != "PASSED":
        problems.append("staged external consumer did not pass")
    if isinstance(suite_manifest, dict) and isinstance(suite_manifest.get("lanes"), dict):
        lane_spec = suite_manifest["lanes"].get(case["id"], {})
        required_gates = set(lane_spec.get("required_gates", [])) | set(
            suite_manifest.get("global_gates", []))
        gate_results = evidence.get("gate_results")
        if (not required_gates or not isinstance(gate_results, dict)
                or set(gate_results) != required_gates):
            problems.append("complete suite independent gate results are missing or unexpected")
        elif any(not isinstance(gate_results[gate], dict)
                 or gate_results[gate].get("status") != "PASSED"
                 or not SHA64.fullmatch(str(gate_results[gate].get("receipt_sha256", "")))
                 for gate in required_gates):
            problems.append("complete suite independent gate did not pass with a bound receipt")
    result.update(status="FAILED" if problems else "PASSED",
                  reason="; ".join(problems) if problems else "all required evidence present")
    return result


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def manifest_digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json_strict(path):
    return json.loads(path.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def finite_json(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite_json(item) for item in value.values())
    if isinstance(value, list):
        return all(finite_json(item) for item in value)
    return True


def require_clean_checkout(repository, candidate_sha):
    head = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    if head != candidate_sha:
        raise ValueError(f"candidate SHA differs from checkout {head}")
    tracked = subprocess.check_output(
        ["git", "-C", str(repository), "status", "--porcelain=v1", "--untracked-files=no"],
        text=True)
    if tracked.strip():
        raise ValueError("dirty tracked checkout invalidates candidate evidence: " + tracked.strip())
    untracked = subprocess.check_output(
        ["git", "-C", str(repository), "ls-files", "--others", "-z"])
    gradle_roots = (b"", b"dyn4k/", b"dyn4k-core/", b"consumers/qualification/",
                    b"consumers/qualification/portable/")
    generated_prefixes = tuple(root + directory + b"/" for root in gradle_roots
                               for directory in (b"build", b".gradle", b".kotlin"))
    generated_prefixes += (b"tools/qualification/__pycache__/",)
    generated_files = {b"kotlin-js-store/yarn.lock",
                       b"consumers/qualification/portable/kotlin-js-store/yarn.lock"}
    relevant = [path for path in untracked.split(b"\0") if path
                and path not in generated_files
                and not path.startswith(generated_prefixes)]
    if relevant:
        names = ", ".join(os.fsdecode(path) for path in relevant[:5])
        raise ValueError(f"untracked checkout inputs invalidate candidate evidence: {names}")


def audit_staging(root, candidate_sha, targets=None, license_file=Path("LICENSE.md"),
                  receipt_path=None, console_path=None, content_contract=None):
    errors, artifacts = [], []
    if not SHA40.fullmatch(candidate_sha):
        raise ValueError("candidate SHA must be a full commit hash")
    selected = matrix_targets() if targets is None else set(targets)
    if not selected or not selected <= matrix_targets():
        raise ValueError("selected publication targets are invalid")
    if not license_file.is_file():
        errors.append("repository license is missing")
        license_bytes = None
    else:
        license_bytes = license_file.read_bytes()
    repository = license_file.parent
    if content_contract is None:
        try:
            sources_contract = candidate_source_contract(repository, candidate_sha)
        except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as error:
            errors.append(f"candidate source tree invalid: {error}")
            sources_contract = {}
        docs_contract = {}
        for module in MODULES:
            root_docs = root / GROUP.replace(".", "/") / module / VERSION / f"{module}-{VERSION}-javadoc.jar"
            if root_docs.is_file():
                try:
                    validate_generated_docs(root_docs, repository / module / "build/dokka/html", license_bytes)
                    docs_contract[module] = digest(root_docs)
                except (OSError, ValueError, zipfile.BadZipFile) as error:
                    errors.append(f"{module}: API documentation differs from Dokka: {error}")
            else:
                errors.append(f"{module}: root API documentation artifact missing")
        content_contract = {"schema": 1, "sources": sources_contract, "api_docs_sha256": docs_contract}
    else:
        sources_contract = content_contract.get("sources") if isinstance(content_contract, dict) else None
        docs_contract = content_contract.get("api_docs_sha256") if isinstance(content_contract, dict) else None
        if (not isinstance(content_contract, dict) or content_contract.get("schema") != 1
                or not isinstance(sources_contract, dict) or set(sources_contract) != set(MODULES)
                or any(not isinstance(value, dict) or not value or
                       any(not isinstance(path, str) or not SHA64.fullmatch(str(sha))
                           for path, sha in value.items())
                       for value in sources_contract.values())
                or not isinstance(docs_contract, dict) or set(docs_contract) != set(MODULES)
                or any(not SHA64.fullmatch(str(value)) for value in docs_contract.values())):
            errors.append("recorded publication content contract is invalid")
            sources_contract, docs_contract = {}, {}
    for module in MODULES:
        root_metadata = root / GROUP.replace(".", "/") / module / VERSION / f"{module}-{VERSION}.module"
        if not root_metadata.is_file():
            errors.append(f"{module}: root Gradle metadata missing")
        for target in [None] + sorted(selected):
            name = module if target is None else target_publication_name(module, target)
            base = root / GROUP.replace(".", "/") / name / VERSION
            pom = base / f"{name}-{VERSION}.pom"
            metadata = base / f"{name}-{VERSION}.module"
            if not pom.is_file() or not metadata.is_file():
                errors.append(f"{name}: staged POM or Gradle metadata missing")
                continue
            try:
                pom_root = ET.parse(pom).getroot()
            except ET.ParseError as error:
                errors.append(f"{name}: POM XML is invalid: {error}")
                continue
            ns = "{http://maven.apache.org/POM/4.0.0}"
            expected_sections = {ns + key for key in
                                 ("modelVersion", "groupId", "artifactId", "version", "name",
                                  "description", "url", "licenses", "developers", "scm", "dependencies")}
            packaging = None if target in (None, "jvm") else "aar" if target == "android" else "klib"
            if packaging is not None:
                expected_sections.add(ns + "packaging")
            observed_sections = [child.tag for child in pom_root]
            if (pom_root.tag != ns + "project" or len(observed_sections) != len(expected_sections)
                    or set(observed_sections) != expected_sections
                    or pom_root.findtext(ns + "modelVersion") != "4.0.0"
                    or pom_root.findtext(ns + "packaging") != packaging):
                errors.append(f"{name}: POM effective model differs from publication contract")
            for key, expected in (("groupId", GROUP), ("artifactId", name), ("version", VERSION)):
                if pom_root.findtext(ns + key) != expected:
                    errors.append(f"{name}: wrong POM {key}")
            for key, expected in pom_metadata_contract(module).items():
                if not pom_element_matches(pom_root.find(ns + key), key, expected):
                    errors.append(f"{name}: POM {key} differs from publication contract")
            pom_entries = pom_root.findall(ns + "dependencies/" + ns + "dependency")
            dependency_container = pom_root.find(ns + "dependencies")
            if (dependency_container is None or dependency_container.attrib
                    or any(child.tag != ns + "dependency" for child in dependency_container)):
                errors.append(f"{name}: POM dependency container differs from publication contract")
            fields = {ns + key for key in ("groupId", "artifactId", "version", "scope")}
            dependencies = {(entry.findtext(ns + "groupId"), entry.findtext(ns + "artifactId"),
                             entry.findtext(ns + "version"), entry.findtext(ns + "scope"))
                            for entry in pom_entries}
            if (len(dependencies) != len(pom_entries) or dependencies != pom_dependency_contract(module, target)
                    or any({child.tag for child in entry} != fields or len(entry) != len(fields)
                           or entry.attrib or any(child.attrib or len(child) for child in entry)
                           for entry in pom_entries)):
                errors.append(f"{name}: POM dependency graph differs from publication contract")
            try:
                module_data = load_json_strict(metadata)
                metadata_errors, referenced = audit_publication_metadata(base, module, target, module_data)
                errors.extend(metadata_errors)
            except (OSError, ValueError, TypeError) as error:
                errors.append(f"{name}: Gradle metadata invalid: {error}")
                referenced = set()
            binary = root / publication_binary_path(module, target)
            source = base / f"{name}-{VERSION}-sources.jar"
            docs = base / f"{name}-{VERSION}-javadoc.jar"
            license_artifact = base / f"{name}-{VERSION}-license.md"
            for path, label in ((binary, "binary"), (source, "sources artifact"),
                                (docs, "API documentation artifact"),
                                (license_artifact, "license artifact")):
                if not path.is_file():
                    errors.append(f"{name}: {label} missing: {path.name}")
            if license_artifact.is_file() and license_bytes is not None and license_artifact.read_bytes() != license_bytes:
                errors.append(f"{name}: license differs from repository license")
            if source.is_file() and module in sources_contract:
                try:
                    expected = expected_source_entries(sources_contract, module, target)
                    if not expected:
                        raise ValueError("candidate source set is empty")
                    validate_source_archive(source, expected)
                except (OSError, ValueError, zipfile.BadZipFile) as error:
                    errors.append(f"{name}: sources archive invalid: {error}")
            if docs.is_file() and module in docs_contract and digest(docs) != docs_contract[module]:
                errors.append(f"{name}: API documentation differs from generated Dokka publication")
            if target in APPLE_TARGETS:
                apple_metadata = base / f"{name}-{VERSION}-metadata.jar"
                if apple_metadata.is_file() and binary.is_file():
                    try:
                        validate_apple_metadata(apple_metadata, binary)
                    except (OSError, ValueError, zipfile.BadZipFile) as error:
                        errors.append(f"{name}: Apple metadata invalid: {error}")
            for path in (binary, source, docs):
                if not path.is_file():
                    continue
                try:
                    with zipfile.ZipFile(path) as archive:
                        entries = archive.namelist()
                        if path == docs and "index.html" not in entries:
                            errors.append(f"{name}: API documentation index missing")
                        if path == docs and not any("/" in item and item.endswith(".html") for item in entries):
                            errors.append(f"{name}: API documentation pages missing")
                        if path == source and not any(item.endswith((".kt", ".java")) for item in entries):
                            errors.append(f"{name}: sources archive has no source files")
                        if path == binary and path.suffix == ".jar":
                            names = archive_file_names(archive)
                            if "META-INF/LICENSE.md" not in names:
                                errors.append(f"{name}: embedded license missing")
                            elif license_bytes is not None and archive.read("META-INF/LICENSE.md") != license_bytes:
                                errors.append(f"{name}: embedded license differs from repository license")
                except (ValueError, zipfile.BadZipFile):
                    errors.append(f"{name}: {path.name} archive is invalid")
            for path in [pom, metadata, binary, source, docs, license_artifact] + sorted(
                    referenced - {binary, source}):
                if not path.is_file():
                    continue
                sha = digest(path)
                artifacts.append({"path": path.relative_to(root).as_posix(), "sha256": sha})
                checksum = path.with_name(path.name + ".sha256")
                if not checksum.is_file() or checksum.read_text().strip().lower() != sha:
                    errors.append(f"{path.name}: SHA-256 sidecar missing or incorrect")
    stage_receipt = None
    stage_console = None
    if receipt_path is not None or console_path is not None:
        try:
            import stage
            if receipt_path is None or console_path is None:
                raise ValueError("staging receipt and console are both required")
            stage_receipt = receipt_path.resolve().relative_to(root.resolve()).as_posix()
            stage_console = console_path.resolve().relative_to(root.resolve()).as_posix()
            receipt = load_json_strict(receipt_path)
            stage.verify_receipt(receipt, console_path, candidate_sha, tuple(sorted(selected)))
            artifacts.append({"path": stage_receipt, "sha256": digest(receipt_path)})
            artifacts.append({"path": stage_console, "sha256": digest(console_path)})
        except (OSError, ValueError) as error:
            errors.append(f"staging task outcome invalid: {error}")
    return {"candidate_sha": candidate_sha, "targets": sorted(selected),
            "stage_receipt": stage_receipt, "stage_console": stage_console,
            "content_contract": content_contract,
            "artifacts": artifacts, "status": "PASSED" if not errors else "FAILED",
            "errors": errors}


def verify_audit_against_staging(audit_data, repository, allow_pinned_content_contract=False):
    if not isinstance(audit_data, dict) or not SHA40.fullmatch(str(audit_data.get("candidate_sha", ""))):
        raise ValueError("staged audit candidate identity is invalid")
    root = repository / "build/staging-repository"
    targets = audit_data.get("targets")
    if not isinstance(targets, list) or not targets or len(set(targets)) != len(targets):
        raise ValueError("staged audit targets are invalid")
    paths = []
    for key in ("stage_receipt", "stage_console"):
        relative = audit_data.get(key)
        if not isinstance(relative, str) or not relative.startswith(".qualification/"):
            raise ValueError("staged audit task outcome path is invalid")
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("staged audit task outcome path escapes repository")
        paths.append(path)
    staged = audit_staging(root, audit_data["candidate_sha"], targets,
                           repository / "LICENSE.md", *paths,
                           content_contract=audit_data.get("content_contract")
                           if allow_pinned_content_contract else None)
    if (audit_data["stage_receipt"] != staged["stage_receipt"]
            or audit_data["stage_console"] != staged["stage_console"]):
        raise ValueError("staged audit task outcome differs from canonical staging path")
    observed_files = {item["path"]: item["sha256"] for item in staged["artifacts"]}
    recorded = audit_data.get("artifacts")
    if not isinstance(recorded, list) or any(not isinstance(item, dict) for item in recorded):
        raise ValueError("staged audit artifact list is invalid")
    recorded_files = {item.get("path"): item.get("sha256") for item in recorded}
    if (len(recorded_files) != len(recorded) or recorded_files != observed_files
            or audit_data.get("content_contract") != staged.get("content_contract")
            or audit_data.get("status") != staged["status"]
            or sorted(audit_data.get("errors", [])) != sorted(staged["errors"])):
        raise ValueError("staged audit differs from current staged files")


def target_binary_hashes(artifacts):
    audited = {item.get("path"): item.get("sha256") for item in artifacts
               if isinstance(item, dict)}
    return {row["target"]: {
        module: audited.get(target_binary_path(module, row["target"])) for module in MODULES}
        for row in matrix()}


def expected_probe_cases(manifest, group):
    if "cases" in group:
        cases = group["cases"]
    else:
        case_sets = manifest.get("case_sets", {})
        if not isinstance(case_sets, dict):
            raise ValueError("probe case sets are invalid")
        names = (case_sets.get(group["case_set"])
                 if "case_set" in group else manifest.get("case_names", []))
        if (not isinstance(names, list) or any(not isinstance(name, str) or not name
                                               for name in names)):
            raise ValueError("probe case names are invalid")
        cases = [{"classname": group.get("classname"),
                  "name": name + group.get("name_suffix", "")} for name in names]
        additional_names = group.get("additional_case_names", [])
        if not isinstance(additional_names, list):
            raise ValueError("additional probe case names must be a list")
        cases.extend({"classname": group.get("additional_classname"),
                      "name": name + group.get("name_suffix", "")}
                     for name in additional_names)
        extra_case_sets = group.get("extra_case_sets", [])
        if not isinstance(extra_case_sets, list):
            raise ValueError("probe case sets are invalid")
        for extra in extra_case_sets:
            if not isinstance(extra, dict) or not isinstance(extra.get("case_set"), str):
                raise ValueError("probe case set reference is invalid")
            extra_names = case_sets.get(extra["case_set"])
            if (not isinstance(extra_names, list) or not extra_names
                    or any(not isinstance(name, str) or not name for name in extra_names)):
                raise ValueError("probe case set is missing or invalid")
            cases.extend({"classname": extra.get("classname"),
                          "name": name + group.get("name_suffix", "")}
                         for name in extra_names)
    if not isinstance(cases, list):
        raise ValueError("probe cases must be a list")
    identities = []
    for case in cases:
        if (not isinstance(case, dict) or not isinstance(case.get("classname"), str)
                or not isinstance(case.get("name"), str) or not case["classname"] or not case["name"]):
            raise ValueError("probe case identity is invalid")
        identities.append((case["classname"], case["name"]))
    if len(set(identities)) != len(identities):
        raise ValueError("probe manifest has duplicate case identities")
    return identities


def validate_probe_accounting(probe, manifest, group_ids):
    groups = {group.get("id"): group for group in manifest.get("groups", [])
              if isinstance(group, dict) and isinstance(group.get("id"), str)}
    summaries = probe.get("groups") if isinstance(probe, dict) else None
    if not isinstance(summaries, list):
        raise ValueError("probe report group counts are missing")
    by_id = {item.get("id"): item for item in summaries
             if isinstance(item, dict) and isinstance(item.get("id"), str)}
    if len(by_id) != len(summaries) or set(by_id) != set(group_ids):
        raise ValueError("probe report group counts differ from selected groups")
    totals = {"expected": 0, "executed": 0, "reported": 0,
              "failures": 0, "errors": 0, "skipped": 0}
    for group_id in group_ids:
        if group_id not in groups:
            raise ValueError(f"probe manifest group is missing: {group_id}")
        summary = by_id[group_id]
        selected = len(expected_probe_cases(manifest, groups[group_id]))
        if (type(summary.get("expected")) is not int or summary["expected"] != selected
                or type(summary.get("executed")) is not int
                or summary["executed"] != selected
                or type(summary.get("reported")) is not int
                or summary["reported"] < selected):
            raise ValueError(f"probe counts differ from selected cases: {group_id}")
        for key in ("failures", "errors", "skipped"):
            if type(summary.get(key)) is not int or summary[key] != 0:
                raise ValueError(f"probe has failed, errored, or skipped cases: {group_id}")
        for key in totals:
            totals[key] += summary[key]
    for key, value in totals.items():
        if type(probe.get(key)) is not int or probe[key] != value:
            raise ValueError(f"probe aggregate {key} differs from report groups")
    return totals


def run_probe(command, report_paths, candidate_sha, output, manifest=None):
    problems = []
    groups = manifest.get("groups") if isinstance(manifest, dict) else None
    if not isinstance(groups, list) or not groups or manifest.get("kind") != "foundation-probe":
        problems.append("frozen foundation probe manifest is required")
        groups = []
    patterns = [group.get("report_pattern") for group in groups if isinstance(group, dict)]
    if len(patterns) != len(groups) or len(set(patterns)) != len(patterns):
        problems.append("probe manifest has duplicate or invalid report groups")
    if sorted(report_paths) != sorted(patterns):
        problems.append("requested report groups differ from frozen manifest")
    expected = executed = reported = failures = errors = skipped = 0
    expected_by_group = {}
    group_reports = []
    for group in groups:
        try:
            identities = expected_probe_cases(manifest, group)
            expected_by_group[group["id"]] = identities
            expected += len(identities)
        except (KeyError, TypeError, ValueError) as error:
            problems.append(str(error))
    if not expected:
        problems.append("probe manifest has no required cases")
    completed = None
    started_at_ns = finished_at_ns = None
    if not problems:
        started_at_ns = time.time_ns()
        for pattern in patterns:
            for path in Path().glob(pattern):
                path.unlink()
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            problems.append(f"probe command exited {completed.returncode}")
        for group in groups:
            expected_cases = expected_by_group[group["id"]]
            paths = list(Path().glob(group["report_pattern"]))
            if expected_cases and not paths:
                problems.append(f'missing report group {group["id"]}')
            if not expected_cases and paths:
                problems.append(f'unexpected report for empty group {group["id"]}')
            observed_cases = []
            skipped_cases = set()
            group_failures = group_errors = group_skipped = 0
            for path in paths:
                try:
                    root = ET.parse(path).getroot()
                    if root.tag != "testsuite":
                        raise ValueError("root element is not testsuite")
                    suite_time = float(root.get("time", "0"))
                    if not math.isfinite(suite_time) or suite_time < 0:
                        raise ValueError("suite time is invalid")
                    testcases = list(root.iter("testcase"))
                    suite_counts = {key: int(root.get(key, "-1")) for key in
                                    ("tests", "failures", "errors", "skipped")}
                    if any(value < 0 for value in suite_counts.values()):
                        raise ValueError("suite counts are missing or negative")
                    actual_failures = sum(bool(testcase.find("failure") is not None) for testcase in testcases)
                    actual_errors = sum(bool(testcase.find("error") is not None) for testcase in testcases)
                    actual_skips = sum(bool(testcase.find("skipped") is not None) for testcase in testcases)
                    if (suite_counts["tests"] != len(testcases)
                            or suite_counts["failures"] != actual_failures
                            or suite_counts["errors"] != actual_errors
                            or suite_counts["skipped"] != actual_skips):
                        raise ValueError("suite counts differ from case elements")
                    for testcase in testcases:
                        duration = float(testcase.get("time", "nan"))
                        if not math.isfinite(duration) or duration < 0:
                            raise ValueError("case time is invalid")
                        identity = (testcase.get("classname"), testcase.get("name"))
                        if not all(identity):
                            raise ValueError("case identity is missing")
                        observed_cases.append(identity)
                        if testcase.find("skipped") is not None:
                            skipped_cases.add(identity)
                    group_failures += actual_failures
                    group_errors += actual_errors
                    group_skipped += actual_skips
                except (ET.ParseError, OSError, TypeError, ValueError) as error:
                    problems.append(f"invalid report {path}: {error}")
            observed_counts = {}
            for identity in observed_cases:
                observed_counts[identity] = observed_counts.get(identity, 0) + 1
            duplicate_cases = [identity for identity, count in observed_counts.items() if count > 1]
            if duplicate_cases:
                problems.append(f'duplicate cases in group {group["id"]}')
            missing_cases = [identity for identity in expected_cases
                             if observed_counts.get(identity, 0) == 0]
            if missing_cases:
                problems.append(f'missing selected cases in group {group["id"]}')
            selected_executed = sum(
                observed_counts.get(identity, 0) == 1 and identity not in skipped_cases
                for identity in expected_cases)
            full_reported = len(observed_cases)
            executed += selected_executed
            reported += full_reported
            failures += group_failures
            errors += group_errors
            skipped += group_skipped
            group_reports.append({"id": group["id"], "expected": len(expected_cases),
                                  "executed": selected_executed, "reported": full_reported,
                                  "failures": group_failures, "errors": group_errors,
                                  "skipped": group_skipped})
        finished_at_ns = time.time_ns()
    if failures or errors or skipped:
        problems.append("probe has failed, errored, or skipped cases")
    if executed != expected:
        problems.append("probe executed count differs from frozen expected count")
    result = {"candidate_sha": candidate_sha, "command": command,
              "exit_code": completed.returncode if completed else None,
              "started_at_ns": started_at_ns, "finished_at_ns": finished_at_ns,
              "expected": expected, "executed": executed, "reported": reported,
              "groups": group_reports, "failures": failures, "errors": errors,
              "skipped": skipped, "manifest_sha256": manifest_digest(manifest) if manifest else None,
              "status": "PROBE_FAILED" if problems else "PROBE_PASSED",
              "reason": "; ".join(problems) if problems else "frozen selected cases verified in full reports",
              "scope": "foundation probe only; not a complete lane"}
    output.write_text(json.dumps(result, indent=2) + "\n")
    if completed:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
    return result


def execute_plan(plan, candidate_sha, output):
    evidence = {}
    for case in expand(matrix()):
        specification = plan.get(case["id"])
        if specification is None:
            continue
        if specification.get("unavailable_reason"):
            evidence[case["id"]] = {"unavailable_reason": specification["unavailable_reason"]}
            continue
        command = specification.get("command")
        if not isinstance(command, list) or not command:
            evidence[case["id"]] = {"error": "no executable command"}
            continue
        result_name = specification.get("result_file")
        if not isinstance(result_name, str) or not result_name:
            evidence[case["id"]] = {"error": "result file path is missing"}
            continue
        result_file = Path(result_name)
        if result_file.is_dir():
            evidence[case["id"]] = {"error": "result file path is a directory"}
            continue
        invocation_id = uuid.uuid4().hex
        previous = None
        if result_file.exists() or result_file.is_symlink():
            previous = result_file.with_name(result_file.name + ".previous-" + invocation_id)
            result_file.rename(previous)
        environment = dict(os.environ, DYN4K_QUALIFICATION_INVOCATION=invocation_id)
        result = subprocess.run(command, text=True, capture_output=True, check=False,
                                env=environment)
        if result.returncode or not result_file.is_file() or result_file.is_symlink():
            evidence[case["id"]] = {"error": "command failed or result file missing",
                                    "exit_code": result.returncode,
                                    "stderr": result.stderr[-4000:],
                                    "previous_result": str(previous) if previous else None}
            continue
        try:
            observed = json.loads(result_file.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (ValueError, OSError) as error:
            evidence[case["id"]] = {"error": f"invalid result JSON: {error}",
                                    "exit_code": result.returncode}
            continue
        if not isinstance(observed, dict) or observed.get("invocation_id") != invocation_id:
            evidence[case["id"]] = {"error": "result invocation ID differs from execution",
                                    "exit_code": result.returncode}
            continue
        observed["command"] = command
        observed["exit_code"] = result.returncode
        evidence[case["id"]] = observed
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def execution_succeeded(evidence):
    return bool(evidence) and all(
        "error" not in result and "unavailable_reason" not in result
        and result.get("exit_code") == 0
        and re.fullmatch(r"[0-9a-f]{32}", str(result.get("invocation_id", ""))) is not None
        for result in evidence.values()
    )


def validate_hosted_probe(probe, candidate_sha, repository=None):
    import hosted

    if not isinstance(probe, dict) or probe.get("candidate_sha") != candidate_sha:
        raise ValueError("hosted probe candidate SHA differs from report")
    target = probe.get("target")
    if target not in hosted.TARGETS:
        raise ValueError("hosted probe target is invalid")
    status = probe.get("status")
    if status not in ("PROBE_PASSED", "PROBE_FAILED", "UNAVAILABLE", "NOT_RUN"):
        raise ValueError("hosted probe status is invalid")
    if status != "PROBE_PASSED":
        if not isinstance(probe.get("reason"), str) or not probe["reason"].strip():
            raise ValueError("hosted probe failure or unavailability needs a reason")
        return probe
    if hosted.runtime_status(target, probe.get("runtime"))[0] != "READY":
        raise ValueError("hosted probe runtime identity is invalid")
    manifest = load_json_strict(Path(__file__).with_name("foundation-probes.json"))
    groups = {group["id"]: group for group in manifest["groups"]}
    selections = {"consumer_probe": (f"consumer-{target}",)}
    if target != "jsSafari":
        selections["source_probe"] = (f"core-{target}", target)
    for key, ids in selections.items():
        if any(group_id not in groups for group_id in ids):
            raise ValueError("hosted probe frozen report group is missing")
        selected = {**manifest, "groups": [group for group in manifest["groups"]
                                             if group["id"] in ids]}
        observed = probe.get(key)
        expected = sum(len(expected_probe_cases(manifest, groups[group_id])) for group_id in ids)
        if (not isinstance(observed, dict) or observed.get("candidate_sha") != candidate_sha
                or observed.get("manifest_sha256") != manifest_digest(selected)
                or observed.get("status") != "PROBE_PASSED"
                or observed.get("expected") != expected or observed.get("executed") != expected
                or observed.get("failures") != 0 or observed.get("errors") != 0
                or observed.get("skipped") != 0
                or type(observed.get("reported")) is not int
                or observed.get("reported") < expected
                or observed.get("exit_code") != 0):
            raise ValueError(f"hosted {key} differs from frozen executed suite")
        validate_probe_accounting(observed, selected, ids)
    hashes = probe.get("artifact_hashes")
    if (not isinstance(hashes, dict) or set(hashes) != set(MODULES)
            or any(not SHA64.fullmatch(str(value)) for value in hashes.values())):
        raise ValueError("hosted target needs both staged binary hashes")
    if repository:
        staging = repository / "build/staging-repository"
        artifact_target = "js" if target == "jsSafari" else target
        if hosted.target_hashes(staging, artifact_target) != hashes:
            raise ValueError("hosted binary hashes differ from staged candidate")
    return probe


def full_hosted_lane(receipt, receipt_sha256, suite_manifest=None):
    target = "js" if receipt["target"] == "jsSafari" else receipt["target"]
    matches = [row for row in matrix() if row["target"] == target
               and (row["runtime"] == "Safari" if target == "js"
                    else True)]
    if len(matches) != 1:
        raise ValueError("full hosted target does not select one runtime family")
    family = matches[0]
    runtime = receipt["runtime"]
    if receipt["target"] == "mingwX64":
        version = str(runtime.get("os_version", ""))
        if not version.startswith("10.0.26100"):
            raise ValueError("full hosted Windows Server runtime differs")
    elif receipt["target"] == "jsSafari":
        version = str(runtime.get("safari_version", ""))
    elif "Simulator" in receipt["target"] or receipt["target"] == "iosX64":
        selected = receipt.get("selected_simulator")
        if not isinstance(selected, dict) or not selected.get("udid"):
            raise ValueError("full hosted simulator observation is missing")
        import hosted
        simulator_family = hosted.NATIVE_TARGETS[receipt["target"]][2]
        if (selected not in runtime.get("simulators", {}).get(simulator_family, [])
                or any(config.get("simulator_udid") != selected["udid"]
                       for config in receipt["configurations"])):
            raise ValueError("full hosted executed simulator differs from selected device")
        version = str(selected.get("runtime", ""))
        if not version:
            raise ValueError("full hosted simulator runtime is missing")
    else:
        version = str(runtime.get("os_version", ""))
    if not version:
        raise ValueError("full hosted runtime version is missing")
    cases = expand([family])
    current = {case["configuration"]: case["id"] for case in cases
               if case["version"] == "current"}
    ids = [current[config["configuration"]] for config in receipt["configurations"]]
    if len(set(ids)) != 2:
        raise ValueError("full hosted configurations do not select distinct lanes")
    observed_cases = []
    for lane_id, config in zip(ids, receipt["configurations"]):
        source = config["source"]
        common = {group["module"]: group["case_ids"] for group in source}
        if (set(common) != set(MODULES) or len(common["dyn4k-core"]) != 2465
                or len(common["dyn4k"]) != 58
                or len(config["consumer"]["case_ids"]) != 3):
            raise ValueError("full hosted reviewed common or consumer case count differs")
        suite_ids = sorted(f"{module}:{case_id}" for module, case_ids in common.items()
                           for case_id in case_ids)
        if suite_manifest is not None and suite_ids != sorted(
                full_suite_cases(suite_manifest, lane_id)):
            raise ValueError("full hosted common cases differ from selected complete suite lane")
        observed_cases.append({"lane_id": lane_id,
                               "configuration": config["configuration"],
                               "common_case_ids": common,
                               "suite_case_ids": suite_ids,
                               "consumer_case_ids": config["consumer"]["case_ids"],
                               "complete_lane_status": "NOT_RUN"})
    return {"target": target, "runtime": family["runtime"],
            "runtime_version": version, "version": "current",
            "runtime_identity": manifest_digest({
                "runtime": runtime, "runner_os": receipt["runner_os"],
                "runner_arch": receipt["runner_arch"],
                "runner_name": receipt["runner_name"],
                "selected_simulator": receipt.get("selected_simulator")}),
            "configuration_lanes": ids,
            "observed_cases": observed_cases,
            "manifest_sha256": receipt["manifest_sha256"],
            "source_tree_sha256": receipt["source_tree_sha256"],
            "map_sha256": receipt["map_sha256"],
            "reviewed_pairs_sha256": receipt["reviewed_pairs_sha256"],
            "artifact_hashes": receipt["artifact_hashes"],
            "receipt_sha256": receipt_sha256,
            "status": "FULL_COMMON_PASSED",
            "reason": "reviewed common corpus and bounded staged consumer only"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("matrix")
    record = sub.add_parser("record")
    record.add_argument("--candidate-sha", required=True)
    record.add_argument("--evidence", type=Path)
    record.add_argument("--audit", type=Path)
    record.add_argument("--candidate-manifest", type=Path)
    record.add_argument("--availability", type=Path)
    record.add_argument("--hosted-probe", action="append", type=Path, default=[])
    record.add_argument("--raw-bundle", action="append", type=Path, default=[])
    record.add_argument("--full-hosted-bundle", action="append", type=Path, default=[])
    record.add_argument("--independent-archives", type=Path)
    record.add_argument("--independent-audit", type=Path)
    record.add_argument("--independent-audit-signature", type=Path)
    record.add_argument("--trusted-audit-public-key", type=Path)
    record.add_argument("--trusted-audit-key-sha256")
    record.add_argument("--independent-performance-key", type=Path)
    record.add_argument("--output", type=Path, required=True)
    execute = sub.add_parser("execute")
    execute.add_argument("--candidate-sha", required=True)
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    audit = sub.add_parser("audit-staging")
    audit.add_argument("--candidate-sha", required=True)
    audit.add_argument("--repository", type=Path, required=True)
    audit.add_argument("--target", action="append", required=True)
    audit.add_argument("--stage-receipt", type=Path, required=True)
    audit.add_argument("--stage-console", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    provider = sub.add_parser("check-providers")
    provider.add_argument("graph", type=Path)
    probe = sub.add_parser("probe")
    probe.add_argument("--candidate-sha", required=True)
    probe.add_argument("--report", action="append", required=True)
    probe.add_argument("--manifest", type=Path, required=True)
    probe.add_argument("--group", action="append", required=True)
    probe.add_argument("--output", type=Path, required=True)
    probe.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "matrix":
        print(json.dumps(expand(matrix()), indent=2))
        return 0
    if args.action == "check-providers":
        try:
            check_providers(args.graph.read_text())
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        print("one org.dyn4j provider")
        return 0
    repository = Path(subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True).strip())
    try:
        require_clean_checkout(repository, args.candidate_sha)
    except (subprocess.CalledProcessError, ValueError) as error:
        parser.error(str(error))
    if args.action == "probe":
        if not SHA40.fullmatch(args.candidate_sha):
            parser.error("candidate SHA must be a full commit hash")
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            parser.error("probe needs a command")
        frozen_path = repository / "tools/qualification/foundation-probes.json"
        if args.manifest.resolve() != frozen_path.resolve():
            parser.error("probe manifest must be the tracked frozen foundation manifest")
        frozen = load_json_strict(frozen_path)
        selected = [group for group in frozen.get("groups", []) if group.get("id") in args.group]
        if len(selected) != len(args.group) or len(set(args.group)) != len(args.group):
            parser.error("unknown or duplicate frozen probe group")
        frozen["groups"] = selected
        result = run_probe(command, args.report, args.candidate_sha, args.output, frozen)
        print(json.dumps(result))
        return 0 if result["status"] == "PROBE_PASSED" else 1
    if args.action == "audit-staging":
        result = audit_staging(args.repository, args.candidate_sha, args.target,
                               repository / "LICENSE.md", args.stage_receipt,
                               args.stage_console)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0 if result["status"] == "PASSED" else 1
    if not SHA40.fullmatch(args.candidate_sha):
        parser.error("candidate SHA must be a full commit hash")
    if args.action == "execute":
        plan = load_json_strict(args.plan)
        valid_ids = {case["id"] for case in expand(matrix())}
        unknown = set(plan) - valid_ids
        if unknown:
            parser.error("unknown lane: " + ", ".join(sorted(unknown)))
        evidence = execute_plan(plan, args.candidate_sha, args.output)
        return 0 if execution_succeeded(evidence) else 1
    evidence = load_json_strict(args.evidence) if args.evidence else {}
    audit_data = load_json_strict(args.audit) if args.audit else None
    if audit_data and audit_data.get("candidate_sha") != args.candidate_sha:
        parser.error("audit candidate SHA differs from report")
    if audit_data:
        try:
            verify_audit_against_staging(audit_data, repository)
        except ValueError as error:
            parser.error(str(error))
    candidate_manifest = load_json_strict(args.candidate_manifest) if args.candidate_manifest else None
    full_manifest_path = repository / "tools/qualification/full-suite-manifest.json"
    tracked_manifest = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "--error-unmatch", "--",
         str(full_manifest_path.relative_to(repository))],
        capture_output=True, check=False).returncode == 0
    suite_manifest = load_json_strict(full_manifest_path) if tracked_manifest and full_manifest_path.is_file() else None
    if suite_manifest is not None:
        try:
            validate_complete_suite_bindings(suite_manifest, repository)
        except (OSError, KeyError, TypeError, ValueError) as error:
            parser.error(str(error))
    cases = expand(matrix())
    availability = load_json_strict(args.availability) if args.availability else {}
    valid_availability = {row["target"] for row in matrix()} | {
        f'{row["target"]}:{row["runtime"]}' for row in matrix()} | {
        f'{case["target"]}:{case["runtime"]}:{case["version"]}' for case in cases} | {
        case["id"] for case in cases}
    unknown = set(availability) - valid_availability
    if unknown:
        parser.error("unknown availability selector: " + ", ".join(sorted(unknown)))
    if any(not isinstance(reason, str) or not reason.strip() for reason in availability.values()):
        parser.error("every unavailable reason must be nonempty text")
    for case in cases:
        if case["id"] not in evidence:
            reason = availability.get(case["id"],
                availability.get(f'{case["target"]}:{case["runtime"]}:{case["version"]}',
                    availability.get(f'{case["target"]}:{case["runtime"]}',
                        availability.get(case["target"]))))
            if reason:
                evidence[case["id"]] = {"unavailable_reason": reason}
    results = [evaluate(case, evidence.get(case["id"]), args.candidate_sha,
                        candidate_manifest, suite_manifest, audit_data)
               for case in cases]
    full_hosted = []
    if args.full_hosted_bundle:
        import artifact
        for bundle in args.full_hosted_bundle:
            try:
                receipt = artifact.verify_full_hosted(bundle, args.candidate_sha, repository)
                receipt_sha256 = receipt.pop("_verified_receipt_sha256")
                transport_sha256 = receipt.pop("_verified_transport_sha256", None)
                scoped = full_hosted_lane(receipt, receipt_sha256, suite_manifest)
                if transport_sha256:
                    scoped["transport_sha256"] = transport_sha256
                if any(set(item["configuration_lanes"]) & set(scoped["configuration_lanes"])
                       for item in full_hosted):
                    raise ValueError("duplicate full hosted lane receipt")
                if audit_data:
                    audited = target_binary_hashes(audit_data.get("artifacts", []))
                    if audited.get(scoped["target"]) != scoped["artifact_hashes"]:
                        raise ValueError("full hosted binaries differ from staged audit")
                    scoped["audit_manifest_sha256"] = manifest_digest(audit_data)
                    scoped["audit_status"] = "PASSED"
                else:
                    scoped["audit_status"] = "NOT_RUN"
                if candidate_manifest:
                    lanes = candidate_manifest.get("lanes")
                    for lane_id in scoped["configuration_lanes"]:
                        selected = lanes.get(lane_id) if isinstance(lanes, dict) else None
                        if (not isinstance(selected, dict)
                                or selected.get("runtime_version") != scoped["runtime_version"]
                                or selected.get("runtime_identity") != scoped["runtime_identity"]
                                or selected.get("artifact_hashes") != scoped["artifact_hashes"]):
                            raise ValueError("full hosted selected candidate lane differs")
                    scoped["candidate_manifest_sha256"] = manifest_digest(candidate_manifest)
                    scoped["candidate_manifest_status"] = "BOUND"
                else:
                    scoped["candidate_manifest_status"] = "NOT_RUN"
                scoped["complete_suite_status"] = "NOT_RUN" if suite_manifest is None else "UNPASSED"
                scoped["release_gate_status"] = "NOT_RUN"
                full_hosted.append(scoped)
            except (OSError, KeyError, TypeError, ValueError, ET.ParseError,
                    tarfile.TarError) as error:
                parser.error(f"full hosted receipt failed: {error}")
    import independent_adapter
    independent_options = (args.independent_archives, args.independent_audit,
                           args.independent_audit_signature,
                           args.trusted_audit_public_key,
                           args.trusted_audit_key_sha256)
    if args.independent_performance_key and not args.independent_archives:
        parser.error("independent performance key requires raw gate archives")
    if any(value is not None for value in independent_options):
        if not all(value is not None for value in independent_options):
            parser.error("independent archives require a signed audit and pinned trusted key")
        if suite_manifest is None:
            parser.error("independent archives require the tracked complete suite")
        try:
            verified_gates = independent_adapter.verify_lanes(
                repository, args.candidate_sha, suite_manifest,
                args.independent_archives, args.independent_audit,
                args.independent_audit_signature, args.trusted_audit_public_key,
                args.trusted_audit_key_sha256, args.independent_performance_key,
                candidate_manifest, audit_data)
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError,
                ImportError) as error:
            parser.error(f"independent gate verification failed: {error}")
    else:
        verified_gates = {}
    by_case_id = {case["id"]: case for case in cases}
    independent_adapter.apply(
        results, evidence, verified_gates,
        lambda lane_id, observed: evaluate(by_case_id[lane_id], observed,
                                           args.candidate_sha, candidate_manifest,
                                           suite_manifest, audit_data))
    by_result_id = {item["id"]: item for item in results}
    for scoped in full_hosted:
        for lane_id in scoped["configuration_lanes"]:
            result = by_result_id[lane_id]
            if result["status"] != "PASSED":
                continue
            lane_evidence = evidence.get(lane_id, {})
            if lane_evidence.get("full_hosted_receipt_sha256") != scoped["receipt_sha256"]:
                result.update(status="FAILED",
                              reason="complete lane evidence does not bind verified full hosted receipt")
    hosted_probes = []
    if len(args.raw_bundle) != len(args.hosted_probe):
        parser.error("each hosted probe needs its matching raw XML bundle")
    for path, bundle in zip(args.hosted_probe, args.raw_bundle):
        try:
            observed = validate_hosted_probe(load_json_strict(path),
                                             args.candidate_sha, repository)
            if observed["status"] == "PROBE_PASSED":
                import artifact
                try:
                    verified = artifact.verify_bundle(
                        bundle, load_json_strict(repository / "tools/qualification/foundation-probes.json"),
                        args.candidate_sha, require_matrix=False)
                    if verified["route"] != observed["target"]:
                        raise ValueError("raw bundle target differs from hosted probe")
                except (OSError, TypeError, ValueError, ET.ParseError) as error:
                    observed = {**observed, "status": "PROBE_FAILED",
                                "reason": f"raw XML bundle failed: {error}"}
            hosted_probes.append(observed)
        except (OSError, ValueError) as error:
            parser.error(str(error))
    report = {"candidate_sha": args.candidate_sha, "total": len(results),
              "counts": {status: sum(item["status"] == status for item in results)
                         for status in ("PASSED", "FAILED", "UNAVAILABLE", "NOT_RUN")},
              "lanes": results, "bounded_hosted_probes": hosted_probes,
              "full_hosted_receipts": full_hosted,
              "independent_gate_results": {lane: item["verification"]
                                           for lane, item in verified_gates.items()}}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["counts"]))
    return 0 if report["counts"]["PASSED"] == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
