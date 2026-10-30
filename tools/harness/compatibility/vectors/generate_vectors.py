"""Record golden vectors for the Kotlin port of tools/compatibility.

Run `python3 tools/harness/compatibility/vectors/generate_vectors.py` from anywhere, then
`emit_kotlin_vectors.py`. The script imports the Python reference implementation and drives the
pure validators and the process probes with real inputs at the recorded revision.
"""
import copy
import hashlib
import subprocess
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "tools/baseline"))
sys.path.insert(0, str(ROOT / "tools/compatibility"))
sys.path.insert(0, str(ROOT / "tools/qualification"))

import verify as oracle
import world_ci
import governing_seams
import candidate_coverage
import method_coverage
import java_corpus
import execution_probe
import governing_disposition
import full_ci
import module_probe
import ledger
import exception_ci
import struct
import zipfile


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def attempt(fn):
    try:
        return {"ok": fn()}
    except Exception as error:  # noqa: BLE001 - vector records the message
        return {"error": str(error), "type": type(error).__name__}


vectors = {}

# ---------------------------------------------------------------- world_ci
modes = [[main, mode] for main, mode in world_ci.expected_modes()]
runlog = [
    {"provider": provider, "runtime": runtime, "index": index,
     "name": world_ci.runlog_name(provider, runtime, index)}
    for provider in world_ci.PROVIDERS for runtime in world_ci.RUNTIMES
    for index in range(len(modes))
]

with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    (base / "WorldListSemanticsConsumer.java").write_text("class WorldListSemanticsConsumer {}")
    source_ok = [{"path": "WorldListSemanticsConsumer.java", "text": "class WorldListSemanticsConsumer {}"}]
    source_expected = {"WorldListSemanticsConsumer.java":
                       digest(b"class WorldListSemanticsConsumer {}")}
    validate_sources_cases = [
        {"name": "matching", "expected": source_expected,
         "result": attempt(lambda: world_ci.validate_sources(base, source_expected))},
        {"name": "changed", "expected": {"WorldListSemanticsConsumer.java": "0" * 64},
         "result": attempt(lambda: world_ci.validate_sources(
             base, {"WorldListSemanticsConsumer.java": "0" * 64}))},
        {"name": "missing", "expected": {"Absent.java": "0" * 64},
         "result": attempt(lambda: world_ci.validate_sources(base, {"Absent.java": "0" * 64}))},
        {"name": "empty", "expected": {},
         "result": attempt(lambda: world_ci.validate_sources(base, {}))},
    ]
    validate_sources_files = source_ok
    (base / "WorldListSemanticsConsumer.java").unlink()

# The matrix fixture the Python unittest builds.
def build_world_workspace(output: Path):
    (output / "runs").mkdir(parents=True, exist_ok=True)
    rows = []
    files = {}
    for provider in world_ci.PROVIDERS:
        for runtime in world_ci.RUNTIMES:
            for index, (main, mode) in enumerate(world_ci.expected_modes()):
                name = world_ci.runlog_name(provider, runtime, index)
                content = {"exit": 0, "stdout": f"{runtime}:{main}:{mode}\n",
                           "stderr": "", "command": ["/jdk/bin/java", "-cp",
                                                     "classpath", main] +
                           ([mode] if mode is not None else [])}
                text = json.dumps(content) + "\n"
                (output / name).write_text(text)
                files[name] = text
                rows.append({"provider": provider, "runtime": runtime,
                             "main": main, "mode": mode, "exit": 0,
                             "log": name, "log_sha256": digest(text.encode())})
    return rows, files


with tempfile.TemporaryDirectory() as directory:
    output = Path(directory)
    rows, files = build_world_workspace(output)
    ok = attempt(lambda: {
        f"{runtime}|{main}|{'' if mode is None else mode}": stdout
        for (runtime, main, mode), stdout in world_ci.validate_runs(rows, output).items()})
    baseline_observed = dict(world_ci.validate_runs(rows, output))

    def mutated(mutation):
        changed = copy.deepcopy(rows)
        mutation(changed)
        return changed

    missing_last = attempt(lambda: world_ci.validate_runs(rows[:-1], output))
    duplicate_key = attempt(lambda: world_ci.validate_runs([*rows[:-1], rows[0]], output))

    # changed stdout inside one raw log, with the recorded hash refreshed
    def rewrite_stdout(path_name, stdout):
        path = output / path_name
        content = json.loads(path.read_text())
        content["stdout"] = stdout
        text = json.dumps(content) + "\n"
        path.write_text(text)
        for row in rows:
            if row["log"] == path_name:
                row["log_sha256"] = digest(text.encode())

    candidate = next(row for row in rows if row["provider"] == "jvm" and row["runtime"] == "jdk8")
    rewrite_stdout(candidate["log"], "wrong World list result\n")
    changed_stdout = attempt(lambda: world_ci.validate_runs(rows, output))
    changed_stdout_text = (output / candidate["log"]).read_text()

    # restore, then break the raw log hash
    rewrite_stdout(candidate["log"], f"jdk8:{candidate['main']}:{candidate['mode']}\n")
    changed_hash_rows = copy.deepcopy(rows)
    next(row for row in changed_hash_rows if row["log"] == candidate["log"])["log_sha256"] = "0" * 64
    changed_hash = attempt(lambda: world_ci.validate_runs(changed_hash_rows, output))
    files[candidate["log"]] = (output / candidate["log"]).read_text()

    # command identity differs
    original_command = json.loads((output / candidate["log"]).read_text())["command"]
    content = json.loads((output / candidate["log"]).read_text())
    content["command"] = ["/jdk/bin/java", "-cp", "classpath"]
    text = json.dumps(content) + "\n"
    (output / candidate["log"]).write_text(text)
    bad_command_rows = copy.deepcopy(rows)
    next(row for row in bad_command_rows if row["log"] == candidate["log"])["log_sha256"] = \
        digest(text.encode())
    bad_command = attempt(lambda: world_ci.validate_runs(bad_command_rows, output))
    bad_command_text = text
    content["command"] = original_command
    text = json.dumps(content) + "\n"
    (output / candidate["log"]).write_text(text)
    files[candidate["log"]] = text

# seal_files runs on its own directory so the world run logs do not interfere.
with tempfile.TemporaryDirectory() as directory:
    output = Path(directory)
    (output / "sources").mkdir(exist_ok=True)
    (output / "sources" / "WorldListSemanticsConsumer.java").write_text("source")
    (output / "run.json").write_text("log")
    recorded = {"sources/WorldListSemanticsConsumer.java": digest(b"source"),
                "run.json": digest(b"log")}
    seal_ok = attempt(lambda: dict(world_ci.seal_files(output, recorded)))
    (output / "sources" / "WorldListSemanticsConsumer.java").unlink()
    seal_missing = attempt(lambda: world_ci.seal_files(output, recorded))
    (output / "sources" / "WorldListSemanticsConsumer.java").write_text("changed")
    seal_changed = attempt(lambda: world_ci.seal_files(output, recorded))
    (output / "sources" / "WorldListSemanticsConsumer.java").write_text("source")
    (output / "extra.txt").write_text("extra")
    seal_extra = attempt(lambda: world_ci.seal_files(output, recorded))
    (output / "extra.txt").unlink()
    (output / "result.json").write_text("report")
    seal_result_excluded = attempt(lambda: dict(world_ci.seal_files(output, recorded)))
    (output / "result.json").unlink()
    seal_empty_recorded = attempt(lambda: world_ci.seal_files(output, {}))

    vectors["world_ci"] = {
        "modes": modes,
        "runlog": runlog,
        "validate_runs": {
            "files": {name: text for name, text in files.items() if name.startswith("runs/")},
            "rows": rows,
            "ok": ok,
            "missing_row": missing_last,
            "duplicate_key": duplicate_key,
            "changed_stdout": changed_stdout,
            "changed_hash": changed_hash,
            "bad_command": bad_command,
            "changed_log": candidate["log"],
            "changed_stdout_text": changed_stdout_text,
            "bad_command_text": bad_command_text,
            "baseline_stdout": {
                f"{runtime}|{main}|{'' if mode is None else mode}": stdout
                for (runtime, main, mode), stdout in baseline_observed.items()},
        },
        "validate_sources_files": validate_sources_files,
        "seal_files": {
            "files": {"sources/WorldListSemanticsConsumer.java": "source", "run.json": "log"},
            "recorded": recorded,
            "ok": seal_ok,
            "missing": seal_missing,
            "changed": seal_changed,
            "extra": seal_extra,
            "result_excluded": seal_result_excluded,
            "empty_recorded": seal_empty_recorded,
        },
        "validate_sources": validate_sources_cases,
        "adverse": [
            {"baseline": "bodies,empty=VALUE:232:abc\n",
             "mutant": "bodies,empty=NotSerializableException:"
                       "org.dyn4j.world.AbstractCollisionWorldKt$worldReadOnlyView$1\n",
             "result": attempt(lambda: world_ci.validate_adverse_output(
                 "bodies,empty=VALUE:232:abc\n",
                 "bodies,empty=NotSerializableException:"
                 "org.dyn4j.world.AbstractCollisionWorldKt$worldReadOnlyView$1\n"))},
            {"baseline": "bodies,empty=VALUE:232:abc\n",
             "mutant": "bodies,empty=VALUE:232:abc\n",
             "result": attempt(lambda: world_ci.validate_adverse_output(
                 "bodies,empty=VALUE:232:abc\n", "bodies,empty=VALUE:232:abc\n"))},
            {"baseline": "bodies,empty=VALUE:232:abc\n",
             "mutant": "other mismatch\n",
             "result": attempt(lambda: world_ci.validate_adverse_output(
                 "bodies,empty=VALUE:232:abc\n", "other mismatch\n"))},
        ],
    }

# ------------------------------------------------------- governing_seams
env_cases = [
    {"name": "inherited only", "env": {"JAVA_TOOL_OPTIONS": "-Da=b"},
     "inherited": {"JAVA_TOOL_OPTIONS": "-Da=b"}},
    {"name": "no options", "env": {}, "inherited": {}},
    {"name": "empty inherited", "env": {"JAVA_TOOL_OPTIONS": ""}, "inherited": {}},
]
governing = {"env": []}
for case in env_cases:
    import os
    from unittest.mock import patch
    with patch.dict(os.environ, case["env"], clear=True):
        base_env, base_options = governing_seams.lane_environment()
        candidate_env, candidate_options = governing_seams.lane_environment("-Dcoverage.agent=enabled")
    governing["env"].append({"case": case["name"], "env": case["env"],
                             "baseline": [base_env.get("JAVA_TOOL_OPTIONS"), base_options],
                             "candidate": [candidate_env.get("JAVA_TOOL_OPTIONS"),
                                           candidate_options]})

options = "-Duser.home=/owned/tmp -Djava.io.tmpdir=/owned/tmp"
banner = "Picked up JAVA_TOOL_OPTIONS: " + options + "\n"
governing["banner"] = [
    {"stderr": text, "options": opt,
     "result": governing_seams.strip_java_tool_options_banner(text, opt)}
    for text, opt in (
        (banner + "unexpected\n", options),
        (banner + banner, options),
        ("Picked up JAVA_TOOL_OPTIONS: " + options + " extra\n", options),
        ("unexpected\n" + banner, options),
        ("", options),
        (banner, None),
        ("unexpected\n", options),
        (banner, ""),
    )
]
vectors["governing_seams"] = governing

# ------------------------------------------------------ candidate_coverage
safe_paths = [
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/AVLTree.kt",
    "dyn4k-core/src/jvmMain/kotlin/org/dyn4j/AVLTree.kt",
    "dyn4k-core/src/jvmModule/java/module-info.java",
    "dyn4k-core/src/commonMain/kotlin/../secret.kt",
    "/dyn4k-core/src/commonMain/kotlin/org/dyn4j/AVLTree.kt",
    "",
    "dyn4k-core/src/jsMain/kotlin/org/dyn4j/AVLTree.kt",
    "dyn4k-core/src/commonMain/kotlin//double.kt",
    "./dyn4k-core/src/commonMain/kotlin/org/dyn4j/AVLTree.kt",
]
vectors["candidate_coverage"] = {
    "safe_source": [{"path": value, "result": candidate_coverage.safe_source(value)}
                    for value in safe_paths],
    "anonymous_behaviors": candidate_coverage.ANONYMOUS_BEHAVIORS,
    "common_expect_sources": candidate_coverage.COMMON_EXPECT_SOURCES,
    "class_files": [],
}

# Real class files: recorded bytes and the SourceFile the Python parser reports.
class_candidates = [
    ROOT / "dyn4k-core/build/classes/kotlin/jvm/main/org/dyn4j/RuntimeClassNameKt.class",
    ROOT / "dyn4k-core/build/classes/kotlin/jvm/main/org/dyn4j/collision/narrowphase/CircleDetector.class",
    ROOT / "dyn4k-core/build/classes/kotlin/jvm/main/org/dyn4j/collision/narrowphase/CircleDetector$Companion.class",
]
for path in class_candidates:
    if not path.is_file():
        continue
    data = path.read_bytes()
    vectors["candidate_coverage"]["class_files"].append({
        "path": path.relative_to(ROOT).as_posix(),
        "bytes_base64": __import__("base64").b64encode(data).decode(),
        "sha256": digest(data),
        "source_file": attempt(lambda: {"value": candidate_coverage.class_source_file(data)}),
    })

# Synthetic class files the parser rejects.
def synthetic_class(entries):
    import struct
    out = bytearray(b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
    out += struct.pack(">H", len(entries))
    for entry in entries:
        out += entry
    return bytes(out)

vectors["candidate_coverage"]["class_errors"] = []
for name, data in (
    ("short", b"\xca\xfe\xba\xbe"),
    ("badmagic", b"\x00\x01\x02\x03" + b"\x00" * 8),
    ("truncated", b"\xca\xfe\xba\xbe\x00\x00\x00\x34\x00\x01"),
    ("bad tag", b"\xca\xfe\xba\xbe\x00\x00\x00\x34\x00\x02\x63"),
):
    vectors["candidate_coverage"]["class_errors"].append({
        "name": name, "bytes_base64": __import__("base64").b64encode(data).decode(),
        "result": attempt(lambda data=data: {"value": candidate_coverage.class_source_file(data)})})

# ---------------------------------------------------------- method_coverage
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    safe_names = ["a/b.json", "", "/a/b.json", "../a.json", "a/../b.json", "a//b.json",
                  "./a/b.json", "a/b/"]
    vectors["method_coverage"] = {
        "safe_path": [{"name": name,
                       "result": attempt(lambda name=name: str(method_coverage.safe_path(root, name).relative_to(root)) if method_coverage.safe_path(root, name) else None)}
                      for name in safe_names],
    }

    # analyze() and dispatch_inventory() parsing, driven through the real functions with the
    # helper compilations stubbed out.
    from unittest.mock import patch

    class Completed:
        def __init__(self, stdout):
            self.stdout = stdout
            self.returncode = 0
            self.stderr = ""

    def run_stub(*args, **kwargs):
        return Completed(run_stub.stdout)

    analyze_text = "\n".join(
        f"o{index % 7}\tm{index}\t()V\t{index % 5}\t5" for index in range(3000)) + "\n"
    with patch.object(method_coverage, "checked_tools", return_value=(b"", [])), \
            patch.object(method_coverage.subprocess, "run", side_effect=run_stub):
        run_stub.stdout = analyze_text
        try:
            rows = method_coverage.analyze(Path("unused"), Path("unused"), {}, Path("unused"))
        except Exception as error:  # noqa: BLE001
            rows = None
            analyze_error = str(error)
        else:
            analyze_error = None
    vectors["method_coverage"]["analyze"] = {
        "generator": {"count": 3000,
                      "template": "o{i % 7}\\tm{i}\\t()V\\t{i % 5}\\t5"},
        "text_sha256": digest(analyze_text.encode()),
        "rows_count": None if rows is None else len(rows),
        "rows_sha256": None if rows is None else digest(json.dumps(
            [[row["owner"], row["name"], row["descriptor"], row["covered_instructions"],
              row["total_instructions"]] for row in rows],
            sort_keys=True, separators=(",", ":")).encode()),
        "error": analyze_error,
    }
    vectors["method_coverage"]["analyze_short"] = {
        "text": "a\tb\tc\t1\t2\n",
        "error": None,
    }
    with patch.object(method_coverage, "checked_tools", return_value=(b"", [])), \
            patch.object(method_coverage.subprocess, "run", side_effect=run_stub):
        run_stub.stdout = "a\tb\tc\t1\t2\n"
        try:
            method_coverage.analyze(Path("unused"), Path("unused"), {}, Path("unused"))
        except Exception as error:  # noqa: BLE001
            vectors["method_coverage"]["analyze_short"]["error"] = str(error)

    dispatch_lines = []
    for index in range(200):
        dispatch_lines.append(
            f"C\torg.dyn4j.C{index}\t{index}\tjava.lang.Object\tjava.io.Serializable")
    for index in range(3000):
        dispatch_lines.append(f"M\torg.dyn4j.C{index % 200}\tm{index}\t()V\t{index % 4}")
    for index in range(3000):
        codes = "" if index % 3 == 0 else "18,21"
        dispatch_lines.append(
            f"O\torg.dyn4j.C{index % 200}\tm{index}\t()V\t{codes}")
    dispatch_text = "\n".join(dispatch_lines) + "\n"
    with patch.object(method_coverage, "checked_tools", return_value=(b"", [])), \
            patch.object(method_coverage.subprocess, "run", side_effect=run_stub):
        run_stub.stdout = dispatch_text
        classes, methods, invokes, opcodes = method_coverage.dispatch_inventory(
            Path("unused"), {}, Path("unused"))
    vectors["method_coverage"]["dispatch_generated"] = {
        "generator": {
            "classes": 200,
            "methods": 3000,
            "class_template": "C\\torg.dyn4j.C{i}\\t{i}\\tjava.lang.Object\\tjava.io.Serializable",
            "method_template": "M\\torg.dyn4j.C{i % 200}\\tm{i}\\t()V\\t{i % 4}",
            "opcode_template": "O\\torg.dyn4j.C{i % 200}\\tm{i}\\t()V\\t{codes}",
            "opcode_codes": "'' when i % 3 == 0 else '18,21'",
        },
        "text_sha256": digest(dispatch_text.encode()),
        "classes_count": len(classes),
        "methods_count": len(methods),
        "opcodes_count": len(opcodes),
        "first_class": [classes["org.dyn4j.C0"]["access"], classes["org.dyn4j.C0"]["parent"],
                        classes["org.dyn4j.C0"]["interfaces"]],
        "last_method": [*next(reversed(methods)), next(reversed(methods.values()))],
        "first_opcodes": next(iter(opcodes.values())),
        "second_opcodes": list(opcodes.values())[1],
        "sha256": digest(json.dumps({
            "classes": [[name, row["access"], row["parent"], row["interfaces"]]
                        for name, row in classes.items()],
            "methods": [[owner, name, descriptor, access]
                        for (owner, name, descriptor), access in methods.items()],
            "opcodes": [[owner, name, descriptor, codes]
                        for (owner, name, descriptor), codes in opcodes.items()],
            "invokes": [[owner, name, descriptor,
                         [list(item) for item in rows]]
                        for (owner, name, descriptor), rows in invokes.items()],
        }, sort_keys=True, separators=(",", ":")).encode()),
    }
    vectors["method_coverage"]["analyze_malformed"] = []
    for text in ("a\tb\tc\tx\t1\n", "a\tb\tc\t1\n", "a\tb\tc\t1\t2\t3\n"):
        try:
            owner, name, descriptor, covered, total = text.splitlines()[0].split("\t")
            outcome = {"error": None}
        except ValueError as error:
            outcome = {"error": str(error)}
        vectors["method_coverage"]["analyze_malformed"].append(
            {"text": text, "result": outcome})

# Dispatch inventory parsing from method_coverage.dispatch_inventory.
dispatch_text = "\n".join([
    "C\torg.dyn4j.A\t1\tjava.lang.Object\tjava.io.Serializable,java.lang.Comparable",
    "C\torg.dyn4j.B\t2\torg.dyn4j.A\t",
    "M\torg.dyn4j.A\tf\t()V\t1",
    "M\torg.dyn4j.A\tg\t(I)Z\t5",
    "I\torg.dyn4j.A\tf\t()V\t183\torg/dyn4j/B\t\t()V",
    "I\torg.dyn4j.A\tg\t(I)Z\t182\torg/dyn4j/B\tf\t()V",
    "O\torg.dyn4j.A\tf\t()V\t18,21",
    "O\torg.dyn4j.A\tg\t(I)Z\t",
]) + "\n"
vectors["method_coverage"]["dispatch"] = {
    "text": dispatch_text,
    "rows": {
        "classes": {"org.dyn4j.A": {"access": 1, "parent": "java.lang.Object",
                                    "interfaces": ["java.io.Serializable",
                                                   "java.lang.Comparable"]},
                    "org.dyn4j.B": {"access": 2, "parent": "org.dyn4j.A", "interfaces": []}},
        "methods": [["org.dyn4j.A", "f", "()V", 1], ["org.dyn4j.A", "g", "(I)Z", 5]],
        "invokes": [["org.dyn4j.A", "f", "()V", 183, "org/dyn4j/B", "", "()V"],
                    ["org.dyn4j.A", "g", "(I)Z", 182, "org/dyn4j/B", "f", "()V"]],
        "opcodes": [["org.dyn4j.A", "f", "()V", [18, 21]],
                    ["org.dyn4j.A", "g", "(I)Z", []]],
    },
}

vectors["method_coverage"]["dispatch_errors"] = []
for text in ("X\ta\n", "O\ta\tb\tc\t\nO\ta\tb\tc\t\n", "M\ta\n"):
    with patch.object(method_coverage, "checked_tools", return_value=(b"", [])), \
            patch.object(method_coverage.subprocess, "run", side_effect=run_stub):
        run_stub.stdout = text
        try:
            method_coverage.dispatch_inventory(Path("unused"), {}, Path("unused"))
        except Exception as error:  # noqa: BLE001
            outcome = {"error": str(error)}
        else:
            outcome = {"error": None}
    vectors["method_coverage"]["dispatch_errors"].append({"text": text, "result": outcome})

# -------------------------------------------------------------- java_corpus
def parameter_identities():
    identities = []
    for owner, count in java_corpus.PARAMETER_CLASSES.items():
        for method in (f"method{index}" for index in range(count)):
            for parameter, address in (("typeA", "0"), ("typeA", "1"), ("typeB", "0"),
                                       ("typeB", "1"), ("typeC", "0")):
                identities.append([owner, f"{method}[{parameter}@{address}]"])
    return identities

identities = parameter_identities()
normalized = java_corpus.normalized_cases([tuple(item) for item in identities])
vectors["java_corpus"] = {
    "parameter_classes": java_corpus.PARAMETER_CLASSES,
    "parameter_pattern": java_corpus.PARAMETER_PATTERN.pattern,
    "identities": identities,
    "normalized": [[owner, name, count] for (owner, name), count in sorted(normalized.items())],
    "normalized_sha256": digest(json.dumps(
        sorted([[owner, name, count] for (owner, name), count in normalized.items()]),
        sort_keys=True, separators=(",", ":")).encode()),
}
malformed = [list(item) for item in identities]
malformed[0] = [malformed[0][0], "method0[typeA]"]
vectors["java_corpus"]["malformed"] = {
    "mutation": {"kind": "replace-first-name", "name": "method0[typeA]"},
    "result": attempt(lambda: dict(java_corpus.normalized_cases(
        [tuple(item) for item in malformed]))),
}
# wrong multiplicity: drop one row of the first owner
short = [list(item) for item in identities[:-1]]
vectors["java_corpus"]["short"] = {
    "mutation": {"kind": "drop-last"},
    "result": attempt(lambda: dict(java_corpus.normalized_cases(
        [tuple(item) for item in short]))),
}
bad_pattern = [list(item) for item in identities]
bad_pattern[0] = [bad_pattern[0][0], "method0[typeA@xyz]"]
vectors["java_corpus"]["bad_pattern"] = {
    "mutation": {"kind": "replace-first-name", "name": "method0[typeA@xyz]"},
    "result": attempt(lambda: dict(java_corpus.normalized_cases(
        [tuple(item) for item in bad_pattern]))),
}

# --------------------------------------------------------- execution_probe
signatures = [
    "org.dyn4j.AVLTree; descriptor: nope",
    "public class X; descriptor: d",
    "public static final class X; descriptor: d",
    "public class X; descriptor: d",
    "public final class X; descriptor: d",
    "protected static final class X; descriptor: d",
    "public static class X; descriptor: d",
    "public class X descriptor: d",
    "  public static final void f(); descriptor: ()V",
    "public static void f(); descriptor: ()V",
    "public static synthetic void f(); descriptor: ()V",
    "",
]
vectors["execution_probe"] = {
    "declaration_flags": list(execution_probe.DECLARATION_FLAGS),
    "ledger_signature": [{"input": value, "result": execution_probe.ledger_signature(value)}
                         for value in signatures],
}

# --------------------------------------------------- governing_disposition
opcode_sets = [[25, 182, 192, 176], [178, 25, 182, 177], [25, 182, 153, 176],
               [25, 182, 182, 176], [21, 21, 25, 182, 176], [25, 185, 182, 176],
               [25], [25, 182], [42, 25, 182, 176]]
flag_values = [0x1041, 0x0009, 0x0001, 0x0005, 0x1001, 0x1040, 0x0008]
baseline_sets = [["ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"],
                 ["ACC_PUBLIC"], ["ACC_PROTECTED", "ACC_BRIDGE"],
                 ["ACC_PUBLIC", "ACC_STATIC"]]
signatures = ["public org.dyn4j.Copyable copy();",
              "public static void run();",
              "protected Copyable copy();"]
dispatch_cases = []
for opcodes in opcode_sets:
    for flags in flag_values:
        for baseline in baseline_sets:
            for signature in signatures:
                for calls in (1, 2):
                    dispatch_cases.append([
                        opcode_sets.index(opcodes), flag_values.index(flags),
                        baseline_sets.index(baseline), signatures.index(signature),
                        calls,
                        governing_disposition.pure_forwarder(
                            opcodes, flags, baseline, signature, calls)])
descriptors = ["(I)V", "()V", "(Ljava/lang/String;)I", "(Lorg/dyn4j/A;J)[I",
               "I)V", "", "()", "(V"]
vectors["governing_disposition"] = {
    "opcode_sets": opcode_sets,
    "flag_values": flag_values,
    "baseline_sets": baseline_sets,
    "signatures": signatures,
    "pure_forwarder": dispatch_cases,
    "parameter_descriptor": [
        {"descriptor": value,
         "result": attempt(lambda value=value:
                           governing_disposition.parameter_descriptor(value))}
        for value in descriptors],
}

# ---------------------------------------------------------------- full_ci
parameter_rows = []
for owner, (count, types) in full_ci.PARAMETER_SUITES.items():
    for index, parameter_type in enumerate(types):
        for method in range(count):
            parameter_rows.append((owner,
                                   f"method{method}[org.dyn4j.collision.broadphase."
                                   f"{parameter_type}@{index + 1:x}]"))
for index in range(2115):
    parameter_rows.append(("Other", f"case{index}"))
normalized_parameter = full_ci.normalized_cases(parameter_rows)
vectors["full_ci"] = {
    "parameter_digest": digest(json.dumps(
        sorted([owner, name, count] for (owner, name), count in normalized_parameter.items()),
        sort_keys=True, separators=(",", ":")).encode()),
    "parameter_count": len(normalized_parameter),
}

# ------------------------------------------------------------ module_probe
# A synthetic modular JAR carrying every export the probe pins. The descriptor output does not
# include the JAR path, so the vector is location independent.
exports = sorted(module_probe.EXPORTS)
module_source = "module org.dyn4j {\n" + "".join(f"    exports {name};\n" for name in exports) + "}\n"
with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    packages = base / "packages"
    for package in exports:
        target = packages / package.replace(".", "/")
        target.mkdir(parents=True, exist_ok=True)
        (target / "Placeholder.java").write_text(
            f"package {package}; public final class Placeholder {{}}\n")
    module = base / "module-info.java"
    module.write_text(module_source)
    classes = base / "classes"
    classes.mkdir()
    sources = [str(path) for path in sorted(packages.rglob("*.java"))]
    subprocess.run(["javac", "--release", "9", "-d", str(classes), str(module), *sources],
                   check=True, capture_output=True)
    jar = base / "dyn4j.jar"
    subprocess.run(["jar", "--create", "--file", str(jar), "-C", str(classes), "."],
                   check=True, capture_output=True)
    vectors["module_probe"] = {
        "module_source": module_source,
        "placeholder_packages": exports,
        "descriptor": module_probe.descriptor(jar),
    }

# ------------------------------------------------- execution_probe.declarations
JAR = ROOT / "dyn4k-core/build/libs/dyn4k-core-jvm-0.1.0-alpha.1.jar"
NAME = "org.dyn4j.RuntimeClassNameKt"
plain = subprocess.run(["javap", "-classpath", str(JAR), "-protected", "-s", NAME],
                       capture_output=True, text=True)
verbose = subprocess.run(["javap", "-classpath", str(JAR), "-protected", "-s", "-v", NAME],
                         capture_output=True, text=True)
if plain.returncode == 0 and verbose.returncode == 0:
    header, members = execution_probe.declarations(plain.stdout, verbose.stdout, oracle)
    vectors["execution_probe"]["declarations"] = {
        "plain": plain.stdout,
        "verbose": verbose.stdout,
        "header": header,
        "members": [[name, descriptor, value[0], value[1]]
                    for (name, descriptor), value in members.items()],
    }

# ---------------------------------------------------------------- ledger
small_expected = {
    "baseline": {"commit": "a" * 40, "binary_sha256": "b" * 64,
                 "sources_sha256": "c" * 64},
    "baseline_test_counts": {"textual_annotations": 2171, "actual_executed_cases": 2385,
                             "ignored": 0},
    "module": {"id": "module-info.java", "source_file": "src/main/java/module-info.java",
               "sha256": "d" * 64, "name": "org.dyn4j",
               "exports": ["org.dyn4j"], "fixture_sha256": {"module-info.java": "e" * 64}},
    "production": {"src/main/java/org/dyn4j/A.java": "f" * 64},
    "tests": {"src/test/java/org/dyn4j/ATest.java": "1" * 64},
    "declarations": {"org.dyn4j.A|type":
                      ["src/main/java/org/dyn4j/A.java", "public class org.dyn4j.A {", None]},
}
vectors["ledger"] = {
    "expected": small_expected,
    "source": {"revision": "1" * 40},
    "generate": ledger.generate(small_expected),
    "unbound": ledger.unbound_candidate_report(
        small_expected, {"revision": "1" * 40}, "2" * 40, "invalid",
        "requested candidate revision is invalid"),
    "baseline_inputs": [],
}
tests_map = {"src/test/java/A.java": "a" * 64}
resources_map = {"src/test/resources/r.txt": "b" * 64}
vectors["ledger"]["baseline_inputs"].append({
    "observed": {**tests_map, **resources_map}, "result": attempt(
        lambda: ledger.require_baseline_test_inputs({**tests_map, **resources_map},
                                                    tests_map, resources_map))})
vectors["ledger"]["baseline_inputs"].append({
    "observed": dict(tests_map), "result": attempt(
        lambda: ledger.require_baseline_test_inputs(dict(tests_map), tests_map, resources_map))})
vectors["ledger"]["baseline_inputs"].append({
    "observed": {**tests_map, **resources_map, "src/test/resources/extra.txt": "c" * 64},
    "result": attempt(lambda: ledger.require_baseline_test_inputs(
        {**tests_map, **resources_map, "src/test/resources/extra.txt": "c" * 64},
        tests_map, resources_map))})
vectors["ledger"]["baseline_inputs"].append({
    "observed": {**tests_map, **resources_map, "src/test/java/A.java": "c" * 64},
    "result": attempt(lambda: ledger.require_baseline_test_inputs(
        {**tests_map, **resources_map, "src/test/java/A.java": "c" * 64},
        tests_map, resources_map))})

# declaration_inventory over the recorded javap texts of one compiled Java class
with tempfile.TemporaryDirectory() as directory:
    source_dir = Path(directory)
    java_file = source_dir / "src/main/java/org/dyn4j/Sample.java"
    java_file.parent.mkdir(parents=True)
    java_file.write_text(
        "package org.dyn4j;\n"
        "public class Sample {\n"
        "    public static final int VALUE = 3;\n"
        "    public static void run() { }\n"
        "    protected String name() { return \"s\"; }\n"
        "}\n")
    classes = source_dir / "classes"
    classes.mkdir()
    subprocess.run(["javac", "--release", "8", "-g", "-d", str(classes), str(java_file)],
                   check=True, capture_output=True)
    plain = subprocess.run(["javap", "-classpath", str(classes), "-protected", "-s",
                            "org.dyn4j.Sample"], capture_output=True, text=True).stdout
    verbose = subprocess.run(["javap", "-classpath", str(classes), "-protected", "-s", "-v",
                              "org.dyn4j.Sample"], capture_output=True, text=True).stdout
production = {"src/main/java/org/dyn4j/Sample.java": "0" * 64}
inventory = ledger.declaration_inventory({"org.dyn4j.Sample": plain},
                                         {"org.dyn4j.Sample": verbose},
                                         production)
vectors["ledger"]["declaration_inventory"] = {
    "plain": plain,
    "verbose": verbose,
    "production": production,
    "inventory": [[key, value[0], value[1], value[2]]
                  for key, value in inventory.items()],
}

# candidate_source_binding against a fixed-date git repository
with tempfile.TemporaryDirectory() as directory:
    repo = Path(directory)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "file.txt").write_text("first\n")
    environment = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                   "GIT_AUTHOR_DATE": "2020-01-01T00:00:00 +0000",
                   "GIT_COMMITTER_DATE": "2020-01-01T00:00:00 +0000"}
    subprocess.run(["git", "-C", str(repo), "add", "file.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "first"], check=True,
                   env={**os.environ, **environment})
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    tree = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], check=True,
                          capture_output=True, text=True).stdout.strip()
    (repo / "file.txt").write_text("second\n")
    subprocess.run(["git", "-C", str(repo), "commit", "-qam", "second"], check=True,
                   env={**os.environ, **environment})
    second = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                            capture_output=True, text=True).stdout.strip()
    import candidate_coverage
    binding = []
    for name, source, requested in (
            ("bound", {"revision": head, "tree": tree}, head),
            ("historical", {"revision": head, "tree": tree}, second),
            ("invalid revision", {"revision": "0" * 40, "tree": tree}, second),
            ("tree differs", {"revision": head, "tree": "0" * 40}, head),
            ("requested invalid", {"revision": head, "tree": tree}, "nope")):
        try:
            status, reason = ledger.candidate_source_binding(source, requested, repo)
        except Exception as error:  # noqa: BLE001
            status, reason = "raised", str(error)
        binding.append({"case": name, "source": source, "requested": requested,
                        "status": status, "reason": reason})
    vectors["ledger"]["binding"] = {"head": head, "tree": tree, "second": second,
                                    "cases": binding}

# -------------------------------------------------------- exception_ci.mutate_uid
uid = exception_ci.UIDS["ArgumentNullException"]
source_zip = Path("/tmp/opencode/uid-source.jar")
target_zip = Path("/tmp/opencode/uid-target.jar")
with zipfile.ZipFile(source_zip, "w") as archive:
    info = zipfile.ZipInfo("org/dyn4j/exception/ArgumentNullException.class",
                           date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    archive.writestr(info, b"header" + struct.pack(">q", uid) + b"tail")
    info = zipfile.ZipInfo("other.txt", date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    archive.writestr(info, b"hello")
exception_ci.mutate_uid(source_zip, target_zip)
with zipfile.ZipFile(target_zip) as archive:
    entries = {info.filename: digest(archive.read(info.filename))
               for info in archive.infolist()}
vectors["exception_ci"] = {
    "uid_source_base64": __import__("base64").b64encode(source_zip.read_bytes()).decode(),
    "mutated_entries": entries,
}

OUTPUT = HERE.parents[1] / "build/vectors/compatibility-vectors.json"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(vectors, indent=1, sort_keys=True) + "\n")
print("wrote", OUTPUT, OUTPUT.stat().st_size, "bytes")
print({key: len(json.dumps(value)) for key, value in vectors.items()})
