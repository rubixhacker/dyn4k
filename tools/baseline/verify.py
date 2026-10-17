from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

COMMIT = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
BINARY_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
SOURCES_SHA256 = "83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223"
BASE = "https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/6.0.0"
JUNIT = "https://repo.maven.apache.org/maven2/junit/junit/4.13.1/junit-4.13.1.jar"
HAMCREST = "https://repo.maven.apache.org/maven2/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar"
EXPECTED_CASES = 2385
REQUIRED_FIXTURE_SHA256 = {
    "six extension helpers": "b668a59b6b50e6d5be1ca4828d2eaa179c6f9b3623a839be3e8c2c063d9ce6a4",
    "eight extension helpers": "bb3f75b5f938b5e6da6e2444f5626606daa2223d29ba5c9ba2405660e50097ed",
    "CopyException null call": "b37d307b808a55961bad6d6cfd5606ec7d27b2ba33567e8d44621d0942530ff0",
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path, expected: str | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        temp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, temp)
        temp.replace(dest)
    if expected and digest(dest) != expected:
        dest.unlink(missing_ok=True)
        raise SystemExit(f"checksum mismatch for {dest.name}")
    if not dest.is_file() or not dest.stat().st_size:
        raise SystemExit(f"missing or empty artifact: {dest}")


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    kwargs.setdefault("text", True)
    return subprocess.run(command, check=True, **kwargs)


GIT_NETWORK_AUTH_ENV = {"GIT_ASKPASS", "GIT_SSH", "GIT_SSH_COMMAND",
                        "GIT_SSH_VARIANT", "GIT_TERMINAL_PROMPT"}


def git_environment(network_auth: bool = False) -> dict[str, str]:
    return {key: value for key, value in os.environ.items()
            if not key.startswith("GIT_") or (network_auth and key in GIT_NETWORK_AUTH_ENV)}


def pinned_git(source: Path, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    source = source.absolute()
    metadata = source / ".git"
    if (source.is_symlink() or not source.is_dir() or metadata.is_symlink()
            or not metadata.exists()):
        raise ValueError(f"source path is not a Git checkout: {source}")
    kwargs["env"] = git_environment(network_auth=bool(command and command[0] == "fetch"))
    return run(["git", "--no-replace-objects", "-C", str(source),
                "--work-tree", str(source), *command], **kwargs)


def jar_types(binary: Path, only: set[str] | None = None,
              visibility: str = "-protected", verbose: bool = False) -> tuple[list[str], dict[str, str]]:
    names = run(["jar", "tf", str(binary)], capture_output=True).stdout.splitlines()
    classes = sorted(n[:-6].replace("/", ".") for n in names
                     if n.endswith(".class") and not n.endswith("module-info.class"))
    signatures = {name: run(["javap", "-classpath", str(binary), visibility, "-s",
                             *(["-v"] if verbose else []), name],
                            capture_output=True).stdout for name in classes
                  if only is None or name in only}
    return classes, signatures


def type_header(signature: str) -> str | None:
    return next((line.strip() for line in signature.splitlines() if re.match(
        r"^(?:(?:public|protected|private|abstract|final|sealed|strictfp) )*"
        r"(?:class|interface|enum|@interface) ", line.strip())), None)


def surface(signature: str, include_package: bool = False) -> tuple[str, dict[tuple[str, str], list[str]]] | None:
    raw_lines = signature.splitlines()
    lines = [line.strip() for line in raw_lines]
    header = type_header(signature)
    if (header is None or header.startswith("private ")
            or (not include_package and not header.startswith(("public ", "protected ")))):
        return None
    header = re.sub(r"\s+", " ", header)
    members = {}
    for index, line in enumerate(lines):
        if not re.match(r"^  \S", raw_lines[index]):
            continue
        if not line.endswith(";") or (not include_package and
                                       not line.startswith(("public ", "protected "))):
            continue
        if include_package and line.startswith(("private ", "#")):
            continue
        if index + 1 >= len(lines) or not lines[index + 1].startswith("descriptor: "):
            raise ValueError(f"missing descriptor for {line}")
        if index + 2 >= len(lines) or not lines[index + 2].startswith("flags: "):
            raise ValueError(f"missing flags for {line}")
        flags = lines[index + 2]
        if "ACC_BRIDGE" in flags or "ACC_SYNTHETIC" in flags:
            continue
        descriptor = lines[index + 1].removeprefix("descriptor: ")
        name = line.split("(", 1)[0].split()[-1] if "(" in line else line[:-1].split()[-1]
        parameter_types = descriptor.split(")", 1)[0] + ")" if "(" in descriptor else ""
        key = (name, parameter_types)
        declaration = re.sub(r"\s+", " ", line) + " descriptor: " + descriptor
        members.setdefault(key, []).append(declaration)
    return header, members


def split_top_level(value: str, separator: str) -> list[str]:
    parts = []
    depth = 0
    start = 0
    index = 0
    while index < len(value):
        if value[index] == "<":
            depth += 1
        elif value[index] == ">":
            depth -= 1
        elif depth == 0 and value.startswith(separator, index):
            parts.append(value[start:index].strip())
            index += len(separator)
            start = index
            continue
        index += 1
    parts.append(value[start:].strip())
    return parts


def type_contract(header: str) -> tuple[str, str | None, set[str]]:
    declaration = header.removesuffix(" {")
    implemented = split_top_level(declaration, " implements ")
    base = implemented[0]
    interfaces = set(split_top_level(implemented[1], ",")) if len(implemented) > 1 else set()
    extended = split_top_level(base, " extends ")
    if len(extended) > 1:
        if " interface " in f" {extended[0]} ":
            interfaces.update(split_top_level(extended[1], ","))
            superclass = None
        else:
            superclass = extended[1]
    else:
        superclass = None
    return extended[0], superclass, interfaces


def source_compatible_declaration(expected: str, actual: str,
                                  allow_final_removal: bool = True,
                                  allow_final_addition: bool = False) -> bool:
    if expected == actual:
        return True
    widened = expected
    if expected.startswith("protected ") and actual.startswith("public "):
        widened = "public " + expected.removeprefix("protected ")
    elif not expected.startswith(("public ", "protected ")) and actual.startswith(
            ("public ", "protected ")):
        widened = actual.split(" ", 1)[0] + " " + expected
    if (allow_final_removal and " final " in f" {widened} "
            and " final " not in f" {actual} "):
        widened = re.sub(r"\bfinal ", "", widened, count=1)
    if (allow_final_addition and " final " not in f" {widened} "
            and " final " in f" {actual} "):
        if " static " in f" {widened} ":
            widened = re.sub(r"\bstatic ", "static final ", widened, count=1)
        elif widened.startswith(("public ", "protected ")):
            widened = re.sub(r"^(public|protected) ", r"\1 final ", widened, count=1)
        else:
            widened = "final " + widened
    return widened == actual


def constructor_list_widening(expected: str, actual: str,
                              type_parameters: set[str]) -> bool:
    found = set(re.findall(r"java\.util\.List<([A-Za-z_$][\w$]*)>", expected))
    if not found or not found.issubset(type_parameters):
        return False
    widened = re.sub(r"java\.util\.List<([A-Za-z_$][\w$]*)>",
                     r"java.util.List<? extends \1>", expected)
    return source_compatible_declaration(widened, actual)


def member_inventory(signature: str) -> tuple[str, list[dict[str, object]]]:
    header = type_header(signature)
    if header is None:
        raise ValueError("class-file type header is missing")
    declared_name = re.search(r"(?:^|\s)(?:class|interface|enum|@interface) ([^< ]+)", header)
    if declared_name is None:
        raise ValueError("class-file type name is missing")
    raw_lines = signature.splitlines()
    records = []
    in_body = False
    opened = False
    closed = False
    for index, raw in enumerate(raw_lines):
        if raw == "{":
            in_body = True
            opened = True
            continue
        if raw == "}":
            in_body = False
            closed = True
        if not in_body:
            continue
        if not re.match(r"^  \S", raw):
            continue
        declaration = raw.strip()
        if not declaration.endswith(";") or declaration.endswith("{};"):
            continue
        if index + 2 >= len(raw_lines):
            raise ValueError(f"incomplete class-file member: {declaration}")
        descriptor_line = raw_lines[index + 1].strip()
        flags_line = raw_lines[index + 2].strip()
        if not descriptor_line.startswith("descriptor: ") or not flags_line.startswith("flags: "):
            raise ValueError(f"class-file descriptor or flags missing: {declaration}")
        descriptor = descriptor_line.removeprefix("descriptor: ")
        flags = re.findall(r"ACC_[A-Z_]+", flags_line)
        if not descriptor:
            raise ValueError(f"empty class-file descriptor: {declaration}")
        method = "(" in descriptor
        name = (declaration.split("(", 1)[0].split()[-1] if method
                else declaration[:-1].split()[-1])
        constructor = method and name == declared_name.group(1)
        parameters = descriptor.split(")", 1)[0] + ")" if method else ""
        source_parameters = (declaration.split("(", 1)[1].rsplit(")", 1)[0]
                             if method else "")
        return_type = (declaration.split("(", 1)[0].rsplit(name, 1)[0].split()[-1]
                       if method and not constructor else "")
        records.append({"name": name, "descriptor": descriptor, "flags": flags,
                        "declaration": declaration, "parameters": parameters,
                        "source_parameters": source_parameters.replace("...", "[]"),
                        "return_type": return_type,
                        "kind": "constructor" if constructor else
                                "method" if method else "field"})
    if not opened or not closed:
        raise ValueError("class-file member inventory is incomplete")
    return header, records


def source_visible(record: dict[str, object]) -> bool:
    flags = record["flags"]
    if any(flag in flags for flag in ("ACC_PRIVATE", "ACC_BRIDGE", "ACC_SYNTHETIC")):
        return False
    return not (record["kind"] == "method" and "-" in str(record["name"]))


def private_nested_type(signature: str, name: str) -> bool:
    section = signature.partition("\nInnerClasses:\n")[2]
    if not section:
        return False
    internal_name = name.replace(".", "/")
    for line in section.splitlines():
        if not line.startswith("  "):
            break
        if re.search(r"=class " + re.escape(internal_name) + r"(?:\s|$)", line):
            return "private" in line.split("#", 1)[0].split()
    return False


def added_member_gate(baseline: Path, candidate: Path, selected: set[str],
                      baseline_signatures: dict[str, str],
                      candidate_signatures: dict[str, str],
                      candidate_classpath: str) -> tuple[list[dict[str, object]], list[str]]:
    caches = (dict(baseline_signatures), dict(candidate_signatures))
    classpaths = (str(baseline), candidate_classpath)
    artifact_hash = digest(candidate)
    risks = []
    errors = []

    def arity(record: dict[str, object]) -> int:
        parameters = str(record["source_parameters"])
        return len(split_top_level(parameters, ",")) if parameters else 0

    def signature(provider: int, name: str) -> str:
        cache = caches[provider]
        if name not in cache:
            cache[name] = run(["javap", "-classpath", classpaths[provider], "-p", "-s",
                               "-v", name], capture_output=True).stdout
        if not cache[name].strip():
            raise ValueError(f"empty class-file inventory: {name}")
        return cache[name]

    def walk(provider: int, name: str) -> list[tuple[str, dict[str, object]]]:
        result = []
        seen = set()

        def visit(type_name: str) -> None:
            if type_name in seen:
                return
            seen.add(type_name)
            raw = type_name.split("<", 1)[0]
            header, records = member_inventory(signature(provider, raw))
            declaration, superclass, interfaces = type_contract(header)
            generic = re.search(r"\b(?:class|interface|enum) [^< ]+<(.+)>$", declaration)
            parameters = split_top_level(generic.group(1), ",") if generic else []
            arguments = (split_top_level(type_name[len(raw) + 1:-1], ",")
                         if type_name.startswith(raw + "<") else [])
            mapping = {parameter.split()[0]: value
                       for parameter, value in zip(parameters, arguments)}

            def substitute(value: str, protected: set[str] | None = None) -> str:
                protected = protected or set()
                return re.sub(r"(?<!\.)\b[A-Za-z_$][\w$]*\b",
                              lambda match: (match.group(0) if match.group(0) in protected
                                             else mapping.get(match.group(0), match.group(0))), value)

            for record in records:
                if not source_visible(record):
                    continue
                if raw != name and record["kind"] == "constructor":
                    continue
                flags = record["flags"]
                if ("ACC_PUBLIC" not in flags and "ACC_PROTECTED" not in flags
                        and raw.rpartition(".")[0] != name.rpartition(".")[0]):
                    continue
                resolved = dict(record)
                method_generics = re.match(
                    r"^(?:(?:public|protected|private|static|final|abstract|synchronized|native|strictfp) )*<",
                    str(record["declaration"]))
                method_parameters: set[str] = set()
                if method_generics is not None:
                    generic_start = method_generics.end()
                    generic_tail = str(record["declaration"])[generic_start:]
                    depth = 1
                    generic_end = 0
                    for index, character in enumerate(generic_tail):
                        if character == "<":
                            depth += 1
                        elif character == ">":
                            depth -= 1
                            if depth == 0:
                                generic_end = index
                                break
                    if depth != 0:
                        raise ValueError(f"incomplete method type parameters: {record['declaration']}")
                    method_parameters = {part.split()[0] for part in
                                         split_top_level(generic_tail[:generic_end], ",")}
                resolved["source_parameters"] = substitute(
                    str(record["source_parameters"]), method_parameters)
                resolved["return_type"] = substitute(
                    str(record["return_type"]), method_parameters)
                result.append((raw, resolved))
            if superclass:
                visit(substitute(superclass))
            elif " interface " not in f" {declaration} " and raw != "java.lang.Object":
                visit("java.lang.Object")
            for interface in interfaces:
                visit(substitute(interface))

        visit(name)
        return result

    for name in sorted(selected):
        if name not in baseline_signatures:
            continue
        if (name.endswith(".package-info") or
                re.search(r"^EnclosingMethod:", baseline_signatures[name], re.MULTILINE)):
            continue
        if name not in candidate_signatures:
            header = type_header(baseline_signatures[name])
            if (header is not None and not private_nested_type(baseline_signatures[name], name)
                    and not header.startswith(("public ", "protected ", "private "))
                    and not re.search(r"\bfinal class\b|\benum\b|@interface", header)):
                errors.append(f"{name}: missing same-package subclassable baseline type")
            continue
        try:
            expected_header, _ = member_inventory(signature(0, name))
            if expected_header.startswith("private ") or private_nested_type(signature(0, name), name):
                continue
            if re.search(r"\benum\b|@interface", expected_header):
                continue
            baseline_final = bool(re.search(r"\bfinal class\b", expected_header))
            baseline_members = walk(0, name)
            candidate_members = walk(1, name)
        except (ValueError, subprocess.CalledProcessError) as error:
            errors.append(f"{name}: {error}")
            continue
        for owner, record in candidate_members:
            key = (record["kind"], record["name"])
            prior = [(prior_owner, item) for prior_owner, item in baseline_members
                     if (item["kind"], item["name"]) == key]
            if record["kind"] == "field":
                matched = any(item["descriptor"] == record["descriptor"] for _, item in prior)
            elif record["kind"] == "constructor":
                matched = any(item["parameters"] == record["parameters"]
                              for _, item in prior)
            else:
                matched = any(item["source_parameters"] == record["source_parameters"]
                              and item["return_type"] == record["return_type"]
                              for _, item in prior)
            if matched:
                newly_declared = owner == name and not any(
                    prior_owner == name and item["source_parameters"] == record["source_parameters"]
                    and item["return_type"] == record["return_type"]
                    for prior_owner, item in prior)
                if not newly_declared:
                    continue
                changed_inherited = any(
                    prior_owner != name and item["source_parameters"] == record["source_parameters"]
                    and item["return_type"] == record["return_type"]
                    and (("ACC_FINAL" in record["flags"]) != ("ACC_FINAL" in item["flags"])
                         or ("ACC_STATIC" in record["flags"]) != ("ACC_STATIC" in item["flags"]))
                    for prior_owner, item in prior)
                if not changed_inherited or (baseline_final and record["kind"] == "method"):
                    continue
            if (baseline_final and record["kind"] != "field"
                    and "ACC_STATIC" not in record["flags"]):
                if not any(
                    ("ACC_VARARGS" in item["flags"] or "ACC_VARARGS" in record["flags"]
                     or arity(item) == arity(record))
                    for _, item in prior):
                    continue
            risks.append({"candidate_type": name, "declaring_type": owner,
                          "descriptor": record["descriptor"], "flags": record["flags"],
                          "origin": "declared" if name == owner else "inherited",
                          "kind": record["kind"], "declaration": record["declaration"],
                          "artifact_sha256": artifact_hash})
    return risks, errors


def fixture_audit(baseline: Path, fixtures: list[Path],
                  require_fixture: bool, candidate_classpath: str
                  ) -> tuple[list[dict[str, object]], list[str], list[str]]:
    results = []
    failures = []
    errors = []
    if require_fixture and not fixtures:
        errors.append("required Java 8 fixture was skipped")
    for source in fixtures:
        try:
            if not source.is_file():
                raise ValueError("fixture is missing or empty")
            with tempfile.TemporaryDirectory() as directory:
                snapshot = Path(directory) / source.name
                shutil.copyfile(source, snapshot)
                if not snapshot.stat().st_size:
                    raise ValueError("fixture is missing or empty")
                source_hash = digest(snapshot)
                outputs = []
                for label, artifact in (("baseline", str(baseline)),
                                        ("candidate", candidate_classpath)):
                    output = Path(directory) / label
                    output.mkdir()
                    compiled = subprocess.run(["javac", "--release", "8", "-Xlint:-options",
                                               "-cp", str(artifact), "-d", str(output),
                                               str(snapshot)], capture_output=True, text=True)
                    outputs.append((compiled, any(output.rglob("*.class"))))
                if digest(snapshot) != source_hash:
                    raise ValueError("fixture snapshot SHA-256 changed during compilation")
            baseline_compile, baseline_classes = outputs[0]
            candidate_compile, candidate_classes = outputs[1]
            if baseline_compile.returncode or not baseline_classes:
                raise ValueError(f"baseline fixture did not compile into classes: "
                                 f"{baseline_compile.stderr.strip()}")
            item = {"source": str(source), "source_sha256": source_hash,
                    "baseline_exit_code": baseline_compile.returncode,
                    "candidate_exit_code": candidate_compile.returncode,
                    "candidate_stderr": candidate_compile.stderr.strip()}
            results.append(item)
            if candidate_compile.returncode or not candidate_classes:
                failures.append(str(source))
        except (OSError, ValueError) as error:
            errors.append(f"{source}: {error}")
    if require_fixture:
        present = {item["source_sha256"] for item in results}
        for label, expected_hash in REQUIRED_FIXTURE_SHA256.items():
            if expected_hash not in present:
                errors.append(f"required Java 8 fixture missing or changed: {label} ({expected_hash})")
    return results, failures, errors


def compare_jars(baseline: Path, candidate: Path, only: set[str] | None = None,
                 visibility: str = "-protected", fixtures: list[Path] | None = None,
                 require_fixture: bool = False,
                 dependencies: list[Path] | None = None) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="dyn4k-candidate-") as directory:
        baseline_snapshot = Path(directory) / "baseline.jar"
        shutil.copyfile(baseline, baseline_snapshot)
        baseline_hash = digest(baseline_snapshot)
        if baseline_hash != BINARY_SHA256:
            raise ValueError(f"baseline SHA-256 mismatch: expected {BINARY_SHA256}, "
                             f"got {baseline_hash}")
        snapshot = Path(directory) / "candidate.jar"
        shutil.copyfile(candidate, snapshot)
        dependency_snapshots = []
        dependency_hashes = {}
        dependency_errors = []
        for index, path in enumerate(dependencies or []):
            if str(path) in dependency_hashes:
                dependency_errors.append(f"duplicate dependency JAR: {path}")
                continue
            try:
                if not path.is_file():
                    raise ValueError("missing or empty dependency JAR")
                dependency_snapshot = Path(directory) / f"dependency-{index}.jar"
                shutil.copyfile(path, dependency_snapshot)
                if not dependency_snapshot.stat().st_size:
                    raise ValueError("missing or empty dependency JAR")
                dependency_hash = digest(dependency_snapshot)
                dependency_snapshots.append((path, dependency_snapshot, dependency_hash))
                dependency_hashes[str(path)] = dependency_hash
            except (OSError, ValueError):
                dependency_errors.append(f"missing or empty dependency JAR: {path}")
        return _compare_jars_snapshot(baseline_snapshot, baseline_hash, snapshot, only,
                                      visibility, fixtures, require_fixture, dependency_snapshots,
                                      dependency_hashes, dependency_errors)


def _compare_jars_snapshot(baseline: Path, baseline_hash: str, candidate: Path,
                           only: set[str] | None,
                           visibility: str, fixtures: list[Path] | None,
                           require_fixture: bool,
                           dependency_snapshots: list[tuple[Path, Path, str]],
                           dependency_hashes: dict[str, str],
                           dependency_errors: list[str]) -> dict[str, object]:
    candidate_hash = digest(candidate)
    candidate_classpath = os.pathsep.join(
        [str(candidate), *(str(snapshot) for _, snapshot, _ in dependency_snapshots)])
    baseline_types, baseline_signatures = jar_types(baseline, only, "-p", verbose=True)
    candidate_types, candidate_signatures = jar_types(
        candidate, set(baseline_types) if only is None else only, "-p", verbose=True)
    if not baseline_types or not candidate_types:
        raise ValueError("empty baseline or candidate class-file inventory")
    selected = set(baseline_types) if only is None else only
    unknown = sorted(selected - set(baseline_types))
    if unknown:
        raise ValueError(f"types absent from baseline: {', '.join(unknown)}")
    missing = []
    mismatches = []
    compatible = []
    compared = []
    declarations = 0
    type_cache = {}

    def candidate_interfaces(type_name: str, seen: set[str]) -> set[str]:
        raw = type_name.split("<", 1)[0]
        if type_name in seen:
            return set()
        seen.add(type_name)
        signature = candidate_signatures.get(raw)
        if signature is None:
            try:
                signature = run(["javap", "-classpath", candidate_classpath, visibility,
                                 "-s", "-v", raw], capture_output=True).stdout
            except subprocess.CalledProcessError:
                return set()
        if raw not in type_cache:
            parsed = surface(signature, visibility == "-package")
            type_cache[raw] = type_contract(parsed[0]) if parsed else None
        contract = type_cache[raw]
        if contract is None:
            return set()
        generic = re.search(r"\b(?:class|interface|enum) [^< ]+<(.+)>$", contract[0])
        arguments = type_name[len(raw) + 1:-1] if type_name.startswith(raw + "<") else ""
        parameters = split_top_level(generic.group(1), ",") if generic else []
        values = split_top_level(arguments, ",") if arguments else []
        mapping = {parameter.split()[0]: value for parameter, value in zip(parameters, values)}

        def substitute(value: str) -> str:
            return re.sub(r"\b[A-Za-z_$][\w$]*\b",
                          lambda match: mapping.get(match.group(0), match.group(0)), value)

        parents = {substitute(item) for item in contract[2]}
        interfaces = set(parents)
        for item in parents:
            interfaces.update(candidate_interfaces(item, seen))
        if contract[1]:
            interfaces.update(candidate_interfaces(substitute(contract[1]), seen))
        return interfaces

    for name in sorted(selected):
        expected = surface(baseline_signatures[name], visibility == "-package")
        if expected is None:
            continue
        compared.append(name)
        declarations += sum(len(members) for members in expected[1].values())
        if name not in candidate_signatures:
            missing.append(name)
            continue
        actual = surface(candidate_signatures[name], visibility == "-package")
        if actual is None:
            mismatches.append(f"{name}: type access lost: {expected[0]} -> "
                              f"{type_header(candidate_signatures[name]) or '<no type declaration>'}")
            continue
        expected_type = type_contract(expected[0])
        actual_type = type_contract(actual[0])
        generic = re.search(r"\b(?:class|interface|enum) [^< ]+<(.+)>$", expected_type[0])
        type_parameters = ({part.split()[0] for part in split_top_level(generic.group(1), ",")}
                           if generic else set())
        interfaces = set(actual_type[2])
        if not expected_type[2].issubset(interfaces):
            interfaces.update(candidate_interfaces(name, set()))
        expected_superclass = expected_type[1] or ("java.lang.Object" if " class " in f" {expected_type[0]} " else None)
        actual_superclass = actual_type[1] or ("java.lang.Object" if " class " in f" {actual_type[0]} " else None)
        if (not source_compatible_declaration(expected_type[0], actual_type[0])
                or expected_superclass != actual_superclass
                or not expected_type[2].issubset(interfaces)):
            mismatches.append(f"{name}: type contract changed: {expected[0]} -> {actual[0]}")
        elif expected[0] != actual[0]:
            compatible.append(f"{name}: compatible type difference: {expected[0]} -> {actual[0]}")
        for key, members in expected[1].items():
            for member in members:
                if key not in actual[1]:
                    mismatches.append(f"{name}: missing {member}")
                elif member not in actual[1][key]:
                    equivalent = next((item for item in actual[1][key]
                                       if source_compatible_declaration(
                                           member, item, "descriptor: (" in member,
                                           " final class " in f" {expected_type[0]} "
                                           and "descriptor: (" in member)
                                       or (key[0] == name and constructor_list_widening(
                                           member, item, type_parameters))), None)
                    if equivalent is None:
                        mismatches.append(f"{name}: changed {member} -> {actual[1][key]}")
                    else:
                        compatible.append(f"{name}: compatible member difference: {member} -> {equivalent}")
    added_risks, inventory_errors = added_member_gate(
        baseline, candidate, selected, baseline_signatures, candidate_signatures,
        candidate_classpath)
    inventory_errors.extend(dependency_errors)
    fixture_results, fixture_failures, fixture_errors = fixture_audit(
        baseline, fixtures or [], require_fixture, candidate_classpath)
    if digest(baseline) != baseline_hash:
        raise ValueError("baseline SHA-256 changed during comparison")
    if digest(candidate) != candidate_hash:
        raise ValueError("candidate snapshot SHA-256 changed during comparison")
    for path, snapshot, expected_hash in dependency_snapshots:
        if digest(snapshot) != expected_hash:
            raise ValueError(f"dependency snapshot SHA-256 changed during comparison: {path}")
    return {"baseline_types": len(baseline_types), "candidate_types": len(candidate_types),
            "compared_baseline_declarations": declarations,
            "compared_api_types": compared, "missing_types": missing,
            "signature_mismatches": mismatches, "compatible_differences": compatible,
            "baseline_sha256": baseline_hash, "candidate_sha256": candidate_hash,
            "dependency_sha256": dependency_hashes,
            "added_member_risks": added_risks,
            "inventory_errors": inventory_errors, "fixture_results": fixture_results,
            "fixture_failures": fixture_failures, "fixture_errors": fixture_errors}


def result_field(output: str, label: str) -> int | None:
    values = [line.split("=", 1)[1] for line in output.splitlines()
              if line.startswith(label + "=")]
    if len(values) != 1 or not values[0].isdigit():
        return None
    return int(values[0])


def validate_run_report(report: dict[str, object]) -> None:
    output = report.get("output")
    stderr = report.get("stderr")
    if not isinstance(output, str) or not isinstance(stderr, str):
        raise ValueError("run output fields are missing or invalid")
    expected = {"actual_executed_cases": ("ACTUAL_TESTS", EXPECTED_CASES),
                "failures": ("FAILURES", 0), "ignored": ("IGNORED", 0)}
    for field, (marker, value) in expected.items():
        observed = report.get(field)
        if type(observed) is not int or observed != value or result_field(output, marker) != observed:
            raise ValueError(f"invalid {field}: expected {value} and matching {marker} marker")
    if type(report.get("process_exit_code")) is not int or report["process_exit_code"] != 0:
        raise ValueError("baseline test process did not exit successfully")
    if report.get("compile_release") != 8 or report.get("harness_class_major") != 52:
        raise ValueError("harness must use Java 8 APIs and bytecode")
    if not isinstance(report.get("javac_version"), str) or not report["javac_version"]:
        raise ValueError("missing compiler version")
    if not isinstance(report.get("java_version"), str) or not report["java_version"]:
        raise ValueError("missing runtime version")
    if not isinstance(report.get("test_input_sha256"), dict) or not report["test_input_sha256"]:
        raise ValueError("missing test input hashes")


def source_file_bytes(source: Path, name: str) -> bytes:
    parts = name.split("/")
    if (len(parts) < 4 or parts[:3] not in (["src", "main", "java"],
                                           ["src", "test", "java"])
            or any(part in ("", ".", "..") for part in parts)):
        raise ValueError(f"invalid pinned source path: {name}")
    opened = []
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC

    def identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
        return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)

    try:
        opened.append(os.open(source, flags | os.O_DIRECTORY))
        for part in parts[:-1]:
            opened.append(os.open(part, flags | os.O_DIRECTORY, dir_fd=opened[-1]))
        file_fd = os.open(parts[-1], flags, dir_fd=opened[-1])
        opened.append(file_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"pinned source path is not a regular file: {name}")
        chunks = []
        while chunk := os.read(file_fd, 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(file_fd)
        path_stat = os.stat(parts[-1], dir_fd=opened[-2], follow_symlinks=False)
        if identity(before) != identity(after) or identity(after) != identity(path_stat):
            raise ValueError(f"pinned source bytes changed during read: {name}")
        for parent, part, child in zip(opened[:-2], parts[:-1], opened[1:-1]):
            if identity(os.stat(part, dir_fd=parent, follow_symlinks=False)) != identity(os.fstat(child)):
                raise ValueError(f"pinned source path changed during read: {name}")
        if identity(source.lstat()) != identity(os.fstat(opened[0])):
            raise ValueError(f"pinned source root changed during read: {name}")
        return b"".join(chunks)
    except OSError as error:
        raise ValueError(f"pinned source path is missing or not a regular file: {name}") from error
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)


def checked_java_sources(source: Path, commit: str,
                         expected: dict[str, bytes] | None = None
                         ) -> tuple[list[str], list[str], dict[str, bytes]]:
    revision = pinned_git(source, ["rev-parse", "HEAD"], capture_output=True).stdout.strip()
    if revision != commit:
        raise ValueError(f"pinned source revision mismatch: expected {commit}, got {revision}")
    status = pinned_git(source, ["status", "--porcelain=v1", "--untracked-files=all",
                                 "--ignored", "--", "src/main/java", "src/test/java",
                                 "src/test/resources"], capture_output=True).stdout
    if status:
        raise ValueError(f"dirty or untracked source inputs: {status.strip()}")
    tracked = pinned_git(source, ["ls-tree", "-r", "--name-only", commit,
                                  "src/main/java", "src/test/java"],
                         capture_output=True).stdout.splitlines()
    production = [path for path in tracked if path.startswith("src/main/java/")
                  and path.endswith(".java")]
    tests = [path for path in tracked if path.startswith("src/test/java/")
             and path.endswith(".java")]
    paths = [*production, *tests]
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("pinned source Java paths are empty or duplicated")
    if expected is not None and set(paths) != set(expected):
        raise ValueError("pinned source Java paths changed during verification")
    pinned = {}
    for path in paths:
        committed = pinned_git(source, ["show", f"{commit}:{path}"],
                               text=False, capture_output=True).stdout
        if expected is not None and expected[path] != committed:
            raise ValueError(f"pinned source object bytes changed: {path}")
        if source_file_bytes(source, path) != committed:
            raise ValueError(f"pinned source bytes differ: {path}")
        pinned[path] = committed
    return production, tests, pinned


def verify_source_inputs(source: Path, sources_jar: Path, commit: str) -> dict[str, object]:
    prod, _, pinned = checked_java_sources(source, commit)
    production = {path.removeprefix("src/main/java/"): path for path in prod}
    with tempfile.TemporaryDirectory(prefix="dyn4k-sources-") as directory:
        snapshot = Path(directory) / "sources.jar"
        shutil.copyfile(sources_jar, snapshot)
        archive_hash = digest(snapshot)
        if commit == COMMIT and archive_hash != SOURCES_SHA256:
            raise ValueError(f"source archive SHA-256 mismatch: expected {SOURCES_SHA256}, "
                             f"got {archive_hash}")
        with zipfile.ZipFile(snapshot) as archive:
            archive_names = {name for name in archive.namelist() if name.endswith(".java")}
            if archive_names != set(production):
                raise ValueError(f"source archive entries differ: missing={sorted(set(production) - archive_names)}, "
                                 f"extra={sorted(archive_names - set(production))}")
            for name, path in production.items():
                if archive.read(name) != pinned[path]:
                    raise ValueError(f"source archive bytes differ: {name}")
        if digest(snapshot) != archive_hash:
            raise ValueError("source archive snapshot SHA-256 changed during verification")
    checked_java_sources(source, commit, pinned)
    return {"commit": commit, "tracked_production_java_files": len(production),
            "source_jar_java_files": len(archive_names),
            "source_jar_sha256": archive_hash, "source_inputs_clean": True,
            "source_jar_matches_tracked_bytes": True}


def checked_out_sources(cache: Path) -> Path:
    source = cache / "dyn4j-source"
    if not (source / ".git").exists():
        run(["git", "--no-replace-objects", "clone", "--filter=blob:none",
             "https://github.com/dyn4j/dyn4j.git", str(source)],
            env=git_environment(network_auth=True))
    status = pinned_git(source, ["status", "--porcelain=v1", "--untracked-files=all",
                                 "--ignored", "--", "src/main/java", "src/test/java",
                                 "src/test/resources"], capture_output=True).stdout
    if status:
        raise SystemExit(f"dirty or untracked source inputs: {status.strip()}")
    pinned_git(source, ["fetch", "origin", COMMIT])
    pinned_git(source, ["checkout", "--detach", COMMIT])
    actual = pinned_git(source, ["rev-parse", "HEAD"], capture_output=True).stdout.strip()
    if actual != COMMIT:
        raise SystemExit(f"source revision mismatch: {actual}")
    checked_java_sources(source, COMMIT)
    return source


def inventory(source: Path, binary: Path, output: Path) -> dict[str, object]:
    prod, tests, pinned = checked_java_sources(source, COMMIT)
    if len(prod) != 268 or len(tests) != 199:
        raise SystemExit(f"unaccounted source files: production={len(prod)} tests={len(tests)}")
    source_hashes = {}
    annotation_count = 0
    for path in [*prod, *tests]:
        pinned_bytes = pinned[path]
        source_hashes[path] = hashlib.sha256(pinned_bytes).hexdigest()
        if path in tests:
            annotation_count += pinned_bytes.decode(errors="replace").count("@Test")
    with tempfile.TemporaryDirectory(prefix="dyn4k-inventory-") as directory:
        snapshot = Path(directory) / "baseline.jar"
        shutil.copyfile(binary, snapshot)
        binary_hash = digest(snapshot)
        if binary_hash != BINARY_SHA256:
            raise ValueError(f"baseline SHA-256 mismatch: expected {BINARY_SHA256}, "
                             f"got {binary_hash}")
        classes, signatures = jar_types(snapshot, verbose=True)
        if digest(snapshot) != binary_hash:
            raise ValueError("baseline snapshot SHA-256 changed during inventory")
    checked_java_sources(source, COMMIT, pinned)
    data = {
        "baseline": {"coordinate": "org.dyn4j:dyn4j:6.0.0", "commit": COMMIT,
                     "binary_sha256": binary_hash},
        "production_java_files": prod,
        "test_java_files": tests,
        "source_input_sha256": source_hashes,
        "test_annotations": annotation_count,
        "types": classes,
        "api_types": sorted(name for name, signature in signatures.items() if surface(signature) is not None),
        "public_protected_jvm_signatures": signatures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def execute(source: Path, binary: Path, cache: Path, output: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="dyn4k-run-inputs-") as directory:
        return _execute_snapshot(source, binary, cache, output, Path(directory))


def _execute_snapshot(source: Path, binary: Path, cache: Path, output: Path,
                      private_root: Path) -> dict[str, object]:
    _, _, pinned_sources = checked_java_sources(source, COMMIT)
    deps = cache / "deps"
    junit, hamcrest = deps / "junit-4.13.1.jar", deps / "hamcrest-core-1.3.jar"
    fetch(JUNIT, junit)
    fetch(HAMCREST, hamcrest)
    test_src = sorted((source / "src/test/java").rglob("*.java"))
    resources = source / "src/test/resources"
    test_inputs = [*test_src, *(path for path in sorted(resources.rglob("*")) if path.is_file())]
    work = cache / "run"
    if work.exists():
        shutil.rmtree(work)
    input_root = private_root / "inputs"
    artifacts = private_root / "artifacts"
    artifacts.mkdir(parents=True)
    snapshots = []
    test_hashes = {}
    for path in test_inputs:
        relative = path.relative_to(source)
        snapshot = input_root / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, snapshot)
        source_hash = digest(snapshot)
        snapshots.append((snapshot, source_hash))
        test_hashes[str(relative)] = source_hash
    revision = pinned_git(source, ["rev-parse", "HEAD"], capture_output=True).stdout.strip()
    if revision != COMMIT:
        raise ValueError(f"pinned source revision mismatch: expected {COMMIT}, got {revision}")
    tracked = pinned_git(source, ["ls-tree", "-r", "--name-only", COMMIT,
                                  "src/test/java", "src/test/resources"],
                         capture_output=True).stdout.splitlines()
    expected_inputs = {path for path in tracked if path.endswith(".java") or
                       path.startswith("src/test/resources/")}
    if expected_inputs != set(test_hashes):
        raise ValueError("pinned source test input paths differ")
    for path in expected_inputs:
        committed = pinned_git(source, ["show", f"{COMMIT}:{path}"],
                               text=False, capture_output=True).stdout
        if (input_root / path).read_bytes() != committed:
            raise ValueError(f"pinned source test input bytes differ: {path}")
    test_src = [input_root / path.relative_to(source) for path in test_src]
    test_classes = [p for p in test_src if "@Test" in p.read_text(errors="replace") or "@RunWith" in p.read_text(errors="replace")]
    if not test_classes:
        raise SystemExit("empty test suite")
    binary_snapshot = artifacts / "baseline.jar"
    junit_snapshot = artifacts / "junit.jar"
    hamcrest_snapshot = artifacts / "hamcrest.jar"
    for original, snapshot in ((binary, binary_snapshot), (junit, junit_snapshot),
                               (hamcrest, hamcrest_snapshot)):
        shutil.copyfile(original, snapshot)
        snapshots.append((snapshot, digest(snapshot)))
    binary_hash, junit_hash, hamcrest_hash = (expected for _, expected in snapshots[-3:])
    if binary_hash != BINARY_SHA256:
        raise ValueError(f"baseline SHA-256 mismatch: expected {BINARY_SHA256}, "
                         f"got {binary_hash}")
    classes = work / "classes"
    classes.mkdir(parents=True)
    cp = os.pathsep.join(map(str, [binary_snapshot, junit_snapshot, hamcrest_snapshot]))
    all_test_sources = [str(p) for p in test_src]
    argfile = work / "test-sources.args"
    argfile.write_text("\n".join('"' + p.replace('"', '\\"') + '"' for p in all_test_sources) + "\n")
    run(["javac", "-encoding", "UTF-8", "--release", "8", "-cp", cp,
         "-d", str(classes), "@" + str(argfile)])
    snapshot_resources = input_root / "src/test/resources"
    if snapshot_resources.exists():
        shutil.copytree(snapshot_resources, classes, dirs_exist_ok=True)
    class_names = sorted({
        ".".join(p.relative_to(input_root / "src/test/java").with_suffix("").parts)
        for p in test_classes
    })
    report_class = work / "BaselineJUnitReport.java"
    report_class.write_text('''import org.junit.runner.JUnitCore;\nimport org.junit.runner.Result;\npublic final class BaselineJUnitReport {\n public static void main(String[] args) { Result r = new JUnitCore().run(load(args));\n  System.out.println("ACTUAL_TESTS=" + r.getRunCount()); System.out.println("FAILURES=" + r.getFailureCount());\n  System.out.println("IGNORED=" + r.getIgnoreCount()); if (!r.wasSuccessful()) { r.getFailures().forEach(System.err::println); System.exit(1); } }\n static Class<?>[] load(String[] names) { try { Class<?>[] c = new Class<?>[names.length]; for (int i=0;i<names.length;i++) c[i]=Class.forName(names[i]); return c; } catch(Exception e) { throw new RuntimeException(e); } }\n}\n''')
    run(["javac", "--release", "8", "-cp", os.pathsep.join([cp, str(classes)]),
         "-d", str(classes), str(report_class)])
    harness_bytes = (classes / "BaselineJUnitReport.class").read_bytes()
    harness_major = int.from_bytes(harness_bytes[6:8], "big")
    result = subprocess.run(["java", "-cp", os.pathsep.join([cp, str(classes)]),
                             "BaselineJUnitReport", *class_names], check=False,
                            capture_output=True, text=True)
    for snapshot, expected_hash in snapshots:
        if digest(snapshot) != expected_hash:
            raise ValueError(f"run input snapshot SHA-256 changed during execution: {snapshot}")
    checked_java_sources(source, COMMIT, pinned_sources)
    actual = result_field(result.stdout, "ACTUAL_TESTS")
    failures = result_field(result.stdout, "FAILURES")
    summary = {"commit": COMMIT, "binary_sha256": binary_hash, "test_files": len(test_src),
               "test_classes": len(class_names), "actual_executed_cases": actual, "failures": failures,
               "ignored": result_field(result.stdout, "IGNORED"),
               "process_exit_code": result.returncode, "output": result.stdout, "stderr": result.stderr,
               "javac_version": run(["javac", "-version"], capture_output=True).stdout.strip(),
               "java_version": run(["java", "-version"], capture_output=True).stderr.splitlines()[0],
               "compile_release": 8, "harness_class_major": harness_major,
               "test_input_sha256": test_hashes,
               "junit_sha256": junit_hash, "hamcrest_sha256": hamcrest_hash}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n")
    try:
        validate_run_report(summary)
    except ValueError as error:
        raise SystemExit(f"upstream baseline suite failed: {error}; see the retained run summary") from error
    return summary


def main() -> None:
    if len(os.sys.argv) > 1 and os.sys.argv[1] == "check-source":
        source_parser = argparse.ArgumentParser(description="Check pinned source inputs and archive bytes.")
        source_parser.add_argument("--checkout", type=Path, required=True)
        source_parser.add_argument("--sources-jar", type=Path, required=True)
        source_parser.add_argument("--commit", required=True)
        options = source_parser.parse_args(os.sys.argv[2:])
        try:
            print(json.dumps(verify_source_inputs(options.checkout, options.sources_jar,
                                                  options.commit), indent=2))
        except (ValueError, OSError, zipfile.BadZipFile) as error:
            raise SystemExit(str(error)) from error
        return
    if len(os.sys.argv) > 1 and os.sys.argv[1] == "check-run":
        check_parser = argparse.ArgumentParser(description="Check an upstream JUnit run report.")
        check_parser.add_argument("--report", type=Path, required=True)
        options = check_parser.parse_args(os.sys.argv[2:])
        try:
            validate_run_report(json.loads(options.report.read_text()))
        except (ValueError, OSError) as error:
            raise SystemExit(str(error)) from error
        print("baseline run report valid")
        return
    if len(os.sys.argv) > 1 and os.sys.argv[1] == "compare":
        compare_parser = argparse.ArgumentParser(description="Compare JVM source compatibility surfaces.")
        compare_parser.add_argument("--baseline-jar", type=Path, required=True)
        compare_parser.add_argument("--candidate", type=Path, required=True)
        compare_parser.add_argument("--only", action="append", default=[])
        compare_parser.add_argument("--fixture", type=Path, action="append", default=[])
        compare_parser.add_argument("--require-fixture", action="store_true")
        compare_parser.add_argument("--dependency-jar", type=Path, action="append", default=[])
        options = compare_parser.parse_args(os.sys.argv[2:])
        try:
            result = compare_jars(options.baseline_jar, options.candidate,
                                  set(options.only) if options.only else None,
                                  fixtures=options.fixture, require_fixture=options.require_fixture,
                                  dependencies=options.dependency_jar)
        except (OSError, ValueError) as error:
            raise SystemExit(str(error)) from error
        print(json.dumps(result, indent=2))
        if (result["missing_types"] or result["signature_mismatches"]
                or result["added_member_risks"] or result["inventory_errors"]
                or result["fixture_failures"] or result["fixture_errors"]):
            raise SystemExit(1)
        return
    parser = argparse.ArgumentParser(description="Verify the pinned dyn4j baseline corpus.")
    parser.add_argument("--cache", type=Path, default=Path(".cache/baseline"))
    parser.add_argument("--inventory", type=Path, default=Path("docs/verification/baseline-inventory.json"))
    parser.add_argument("--summary", type=Path, default=Path("docs/verification/baseline-run.json"))
    parser.add_argument("--candidate", type=Path, help="compare candidate JAR public/protected signatures")
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    cache = args.cache.resolve()
    binary = cache / "dyn4j-6.0.0.jar"
    sources_jar = cache / "dyn4j-6.0.0-sources.jar"
    fetch(BASE + "/dyn4j-6.0.0.jar", binary, BINARY_SHA256)
    fetch(BASE + "/dyn4j-6.0.0-sources.jar", sources_jar, SOURCES_SHA256)
    source = checked_out_sources(cache)
    source_provenance = verify_source_inputs(source, sources_jar, COMMIT)
    data = inventory(source, binary, args.inventory.resolve())
    data["baseline"]["sources_sha256"] = source_provenance["source_jar_sha256"]
    data["source_provenance"] = source_provenance
    args.inventory.resolve().write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    if args.candidate:
        comparison = compare_jars(binary, args.candidate.resolve())
        print(json.dumps(comparison, indent=2))
        if (comparison["missing_types"] or comparison["signature_mismatches"]
                or comparison["added_member_risks"] or comparison["inventory_errors"]
                or comparison["fixture_failures"] or comparison["fixture_errors"]):
            raise SystemExit(1)
    if not args.inventory_only:
        summary = execute(source, binary, cache, args.summary.resolve())
        print(json.dumps(summary, indent=2))
    print(f"inventory: {args.inventory.resolve()}")


if __name__ == "__main__":
    main()
