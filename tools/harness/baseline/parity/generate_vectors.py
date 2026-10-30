#!/usr/bin/env python3
"""Regenerate the Kotlin parity vectors for the baseline-verifier port.

Provenance
----------
Every value written here was printed by the Python implementation in `tools/baseline/verify.py`
at the git revision reported as `revision` in the payload (see [revision]); nothing was computed
by the Kotlin port and copied back. The `javap` text the readers are replayed against is the
output of the `javac`/`javap` on the host that generated the file, reported as `javac`.

Output
------
`stdout` is JSON. `--kotlin PATH` writes the fixture the Kotlin suites use:
`src/commonTest/.../BaselineVectors.kt`, holding the same payload base64 encoded in chunks so no
literal exceeds the JVM class-file constant-pool limit.

Usage
-----
    python3 tools/harness/baseline/parity/generate_vectors.py \
        --kotlin tools/harness/baseline/src/commonTest/kotlin/io/github/rubixhacker/harness/baseline/BaselineVectors.kt

Re-running this script reproduces every recorded value except the absolute scratch paths, which
are normalised to `<root>` before they are written, and the digests, which are normalised to
`<sha256>`.
"""

from __future__ import annotations

import argparse
import base64
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from tools.baseline import verify  # noqa: E402

TEMP = Path(tempfile.mkdtemp(prefix="dyn4k-baseline-vectors-"))

SHA256 = re.compile(r"\b[0-9a-f]{64}\b")


def normalise(value):
    """Replace the scratch root and every SHA-256 digest with a stable placeholder."""
    if isinstance(value, str):
        text = value.replace(str(TEMP), "<root>")
        return SHA256.sub("<sha256>", text)
    if isinstance(value, list):
        return [normalise(item) for item in value]
    if isinstance(value, dict):
        return {normalise(key): normalise(item) for key, item in value.items()}
    return value


def digest(path):
    return verify.digest(Path(path))


def revision():
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def javac_version():
    return subprocess.run(
        ["javac", "-version"], check=True, capture_output=True, text=True
    ).stdout.strip()


def build_jar(root: Path, sources: dict[str, str], synthetic_method=None) -> Path:
    root.mkdir(parents=True)
    paths = []
    for name, source in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        paths.append(str(path))
    classes = root / "classes"
    classes.mkdir()
    subprocess.run(
        ["javac", "--release", "8", "-Xlint:-options", "-d", str(classes), *paths],
        check=True,
        capture_output=True,
    )
    if synthetic_method is not None:
        class_name, method_name = synthetic_method
        target = classes / (class_name + ".class")
        target.write_bytes(mark_synthetic(target.read_bytes(), method_name))
    archive = root / "library.jar"
    subprocess.run(
        ["jar", "cf", str(archive), "-C", str(classes), "."], check=True, capture_output=True
    )
    return archive


def mark_synthetic(binary: bytes, target: str) -> bytes:
    """Set ACC_SYNTHETIC on one method, the way `test_added_members.py` does."""
    import struct

    data = bytearray(binary)
    offset = 8
    count = struct.unpack_from(">H", data, offset)[0]
    offset += 2
    names = {}
    index = 1
    while index < count:
        tag = data[offset]
        offset += 1
        if tag == 1:
            size = struct.unpack_from(">H", data, offset)[0]
            offset += 2
            names[index] = data[offset : offset + size].decode()
            offset += size
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            offset += 4
        elif tag in (5, 6):
            offset += 8
            index += 1
        elif tag in (7, 8, 16, 19, 20):
            offset += 2
        elif tag == 15:
            offset += 3
        else:
            raise ValueError(f"unknown constant pool tag {tag}")
        index += 1
    offset += 6
    interfaces = struct.unpack_from(">H", data, offset)[0]
    offset += 2 + 2 * interfaces

    def skip_members(position):
        number = struct.unpack_from(">H", data, position)[0]
        position += 2
        for _ in range(number):
            position += 6
            attributes = struct.unpack_from(">H", data, position)[0]
            position += 2
            for _ in range(attributes):
                size = struct.unpack_from(">I", data, position + 2)[0]
                position += 6 + size
        return position

    offset = skip_members(offset)
    number = struct.unpack_from(">H", data, offset)[0]
    offset += 2
    found = False
    for _ in range(number):
        name = names[struct.unpack_from(">H", data, offset + 2)[0]]
        if name == target:
            flags = struct.unpack_from(">H", data, offset)[0]
            struct.pack_into(">H", data, offset, flags | 0x1000)
            found = True
        offset += 6
        attributes = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        for _ in range(attributes):
            size = struct.unpack_from(">I", data, offset + 2)[0]
            offset += 6 + size
    if not found:
        raise ValueError(f"method {target} not found")
    return bytes(data)


# --------------------------------------------------------------------------------------------
# The compiled fixture every `javap` reader vector is taken from.
# --------------------------------------------------------------------------------------------

FIXTURE_SOURCES = {
    "p/Base.java": """package p;
public abstract class Base implements java.io.Serializable {
  protected Base() {}
  public abstract void run();
  protected java.util.List<String> names() { return null; }
}
""",
    "p/Api.java": """package p;
public class Api<T extends Number> extends Base implements Comparable<Api<T>> {
  public T value;
  protected java.util.List<T> items;
  private int hidden;
  public static final int KEY = 1;
  static { System.setProperty("dyn4k.fixture", "1"); }
  public Api() {}
  protected Api(T value, java.util.List<T> items) { this.value = value; this.items = items; }
  public void run() {}
  public void move(int n) {}
  public java.util.List<? extends T> points() { return null; }
  public void varargs(String... names) {}
  public int compareTo(Api<T> other) { return 0; }
  int packageLevel() { return 0; }
  protected final T both(Number n, String... extra) { return null; }
}
""",
    "p/Mode.java": """package p;
public enum Mode {
  ONE, TWO;
  private int weight;
  public static Object getEntries() { return null; }
}
""",
    "p/Marker.java": """package p;
public @interface Marker {
  String value() default "";
}
""",
    "p/Outer.java": """package p;
public class Outer {
  private static class Warm { public final String helper() { return null; } }
  class Inner { int x; }
  static class Nested { protected long y; }
  public Runnable task = new Runnable() { public void run() {} };
  public Class<?> warm() { return Warm.class; }
}
""",
    "p/Generic.java": """package p;
public class Generic<T> { public T value() { return null; } }
""",
    "p/Child.java": """package p;
public class Child extends Generic<String> {
  @Override public String value() { return "x"; }
}
""",
    "p/PackagePrivate.java": """package p;
class PackagePrivate {
  int value;
  void move() {}
  public void visible() {}
}
""",
    "p/package-info.java": """@Deprecated
package p;
""",
}

TYPE_NAMES = [
    "p.Api",
    "p.Base",
    "p.Child",
    "p.Generic",
    "p.Marker",
    "p.Mode",
    "p.Outer",
    "p.Outer$1",
    "p.Outer$Inner",
    "p.Outer$Nested",
    "p.Outer$Warm",
    "p.PackagePrivate",
    "p.package-info",
]


def javap(archive: Path, name: str, visibility: str = "-p", verbose: bool = True) -> str:
    command = ["javap", "-classpath", str(archive), visibility, "-s"]
    if verbose:
        command.append("-v")
    command.append(name)
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def read_signatures(archive: Path):
    """`javap -p -s -v` for every class in the archive, keyed by binary name."""
    names = subprocess.run(
        ["jar", "tf", str(archive)], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    classes = sorted(n[:-6].replace("/", ".") for n in names
                     if n.endswith(".class") and not n.endswith("module-info.class"))
    signatures = {}
    for name in classes:
        signatures[name] = javap(archive, name)
    return classes, signatures


def surface_case(signature: str, include_package: bool) -> dict:
    try:
        result = verify.surface(signature, include_package)
    except ValueError as error:
        return {"include_package": include_package, "error": str(error)}
    if result is None:
        return {"include_package": include_package, "surface": None}
    header, members = result
    return {
        "include_package": include_package,
        "surface": {
            "header": header,
            "members": [
                [key[0], key[1], list(declarations)] for key, declarations in members.items()
            ],
        },
    }


def inventory_case(signature: str) -> dict:
    try:
        header, records = verify.member_inventory(signature)
    except ValueError as error:
        return {"error": str(error)}
    return {"header": header, "records": records, "json": json.dumps(records)}


def member(declaration: str, descriptor=None, flags=None) -> str:
    """One `javap` member block, laid out the way `javap -v` lays it out."""
    lines = [f"  {declaration};"]
    if descriptor is not None:
        lines.append(f"    descriptor: {descriptor}")
    if flags is not None:
        lines.append(f"    flags: {flags}")
    return "\n".join(lines) + "\n"


def type_body(header: str, *members: str) -> str:
    """A `javap -v` class body: header lines, the opening `{`, members, the closing `}`."""
    return f"{header}\n  minor version: 0\n  major version: 52\n{{\n" + "".join(members) + "}\n"


SYNTHETIC_SIGNATURES = {
    "missing-descriptor": type_body(
        "public class X extends java.lang.Object",
        member("public void move()"),
        member("public void after()", "()V", "(0x0001) ACC_PUBLIC"),
    ),
    "missing-flags": type_body(
        "public class X extends java.lang.Object",
        member("public void move()", "()V"),
        member("public void after()", "()V", "(0x0001) ACC_PUBLIC"),
    ),
    "empty-descriptor": type_body(
        "public class X extends java.lang.Object",
        member("public void move()", "", "(0x0001) ACC_PUBLIC"),
        member("public void after()", "()V", "(0x0001) ACC_PUBLIC"),
    ),
    "incomplete-member": type_body(
        "public class X extends java.lang.Object",
        member("public void move()"),
    ).removesuffix("}\n"),
    "unclosed-body": type_body(
        "public class X extends java.lang.Object",
        member("public void move()", "()V", "(0x0001) ACC_PUBLIC"),
    ).removesuffix("}\n"),
    "static-initializer": type_body(
        "public class X extends java.lang.Object",
        member("static {}", "()V", "(0x0008) ACC_STATIC"),
        member("public void move()", "()V", "(0x0001) ACC_PUBLIC"),
    ),
    "no-header": type_body(
        "X extends java.lang.Object",
        member("public void move()", "()V", "(0x0001) ACC_PUBLIC"),
    ),
    "generic-method": type_body(
        "public class X<T extends java.lang.Object> extends java.lang.Object",
        member("public int value", "I", "(0x0001) ACC_PUBLIC"),
        member("public X()", "()V", "(0x0001) ACC_PUBLIC"),
        member("public <U extends java.lang.CharSequence> U convert(U)",
               "(Ljava/lang/CharSequence;)Ljava/lang/CharSequence;", "(0x0001) ACC_PUBLIC"),
        member("public java.lang.String name()", "()Ljava/lang/String;",
               "(0x0011) ACC_PUBLIC, ACC_FINAL"),
        member("public int[] array()", "()[I", "(0x0001) ACC_PUBLIC"),
        member("protected java.lang.String[] names(java.lang.String...)",
               "([Ljava/lang/String;)[Ljava/lang/String;",
               "(0x0084) ACC_PROTECTED, ACC_VARARGS"),
        member("private void hidden()", "()V", "(0x0002) ACC_PRIVATE"),
        member("void bridge(void)", "()V", "(0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC"),
        member("public void foo-bar()", "()V", "(0x0001) ACC_PUBLIC"),
        member("public java.lang.String nested(p.X$Inner<T>)",
               "(Lp/X$Inner;)Ljava/lang/String;", "(0x0001) ACC_PUBLIC"),
        member("int packageLevel()", "()I", "(0x0000)"),
        member("public void many(java.util.List<java.util.Map<K, V>> values)",
               "(Ljava/util/List;)V", "(0x0001) ACC_PUBLIC"),
    ),
    "package-header": type_body(
        "class X extends java.lang.Object",
        member("int value", "I", "(0x0000)"),
        member("void move()", "()V", "(0x0000)"),
    ),
    "final-header": type_body(
        "public final class X extends java.lang.Object implements java.util.Map$Entry",
    ),
}

DECLARATIONS = [
    "public void move(int n)",
    "protected void move(int n)",
    "void move(int n)",
    "public final void move(int n)",
    "public static int count()",
    "public static final int count()",
    "public int count()",
    "static final int KEY",
    "public static int KEY",
    "public static final int KEY",
    "public java.util.List<? extends Vector2> points()",
    "public java.util.List<android.graphics.Vector2> points()",
    "public final class Api",
    "public class Api",
    "public abstract class Api",
    "java.lang.String value()",
    "java.lang.Object value()",
    "public java.lang.String value(java.lang.String[] names)",
    "public java.lang.String value(java.lang.String... names)",
    "protected Api(Api<T> other, java.util.List<T> values)",
    "public Api(java.util.List<? extends T> values)",
    "public Api(java.util.List<T> values)",
    "public void move(java.util.List<T> values)",
    "public void move(java.util.List<? extends T> values)",
]

WIDENING_CASES = [
    ("public Api(java.util.List<T> values)", "public Api(java.util.List<? extends T> values)",
     ["T"]),
    ("public Api(java.util.List<T> values)", "public Api(java.util.List<? extends T> values)",
     []),
    ("public void move(java.util.List<T> values)",
     "public void move(java.util.List<? extends T> values)", ["T"]),
    ("protected Api(Api<T> other, java.util.List<T> values)",
     "protected Api(Api<T> other, java.util.List<? extends T> values)", ["T"]),
    ("public Api(java.util.List<java.lang.String> values)",
     "public Api(java.util.List<? extends java.lang.String> values)", ["T"]),
]


def text_vectors() -> dict:
    cases = [
        "",
        "a",
        "a\n",
        "a\n\n",
        "a\r\nb",
        "a\rb",
        "a\x0bb",
        "a\x0cb",
        "a\x1cb",
        "a\x1db",
        "a\x1eb",
        "a\x85b",
        "a\u2028b",
        "a\u2029b",
        "  padded  ",
        "\t x \t",
        "a\u00a0b",
        "a  b\tc\nd",
        "x=1\nx=2\n",
    ]
    return {
        "splitlines": [
            {"input": text, "lines": text.splitlines()} for text in cases
        ],
        "strip": [{"input": text, "stripped": text.strip()} for text in cases],
        "split_whitespace": [
            {"input": text, "parts": text.split()} for text in cases
        ],
        "sorted": [
            {
                "input": values,
                "sorted": sorted(values),
            }
            for values in (
                ["b", "a", "Z", "A", "a b"],
                ["\u00e9", "e", "E"],
                ["z", "\u00e9", "\u007f"],
                ["org.dyn4j.Api", "org.dyn4j.api", "org.dyn4j.Api$1", "org.dyn4j.Api0"],
            )
        ],
        "repr": [
            {"value": value, "repr": repr(value)}
            for value in ("", "plain", "it's", 'say "hi"', "back\\slash", "line\nbreak",
                          "tab\tstop", "\u00e9", "\u2603")
        ],
        "list_repr": [
            {
                "values": values,
                "repr": repr(values),
            }
            for values in ([], ["one"], ["public void a()", "public void b()"],
                           ["public void a() descriptor: ()V"])
        ],
    }


def declaration_vectors() -> dict:
    headers = [
        "public class Api<T extends Number> extends Base implements java.io.Serializable",
        "public class Api implements Child, Parent",
        "public interface Child extends Parent",
        "public final class Api extends java.lang.Object",
        "public abstract class Api<T> extends java.util.AbstractList<T> implements "
        "java.util.RandomAccess",
        "public class Api {",
        "public interface Api<T> extends Parent<T>, java.io.Serializable",
    ]
    flags = [[True, False], [False, False], [True, True]]
    compatible = [
        [
            expected_index,
            actual_index,
            flags_index,
            verify.source_compatible_declaration(expected, actual, *flags[flags_index]),
        ]
        for expected_index, expected in enumerate(DECLARATIONS)
        for actual_index, actual in enumerate(DECLARATIONS)
        for flags_index in range(len(flags))
    ]
    return {
        "split_top_level": [
            {"value": value, "separator": separator, "parts": verify.split_top_level(value, separator)}
            for value, separator in (
                ("Child, Parent", ","),
                ("base", " implements "),
                ("Api<T extends Number> extends Base", " extends "),
                ("java.util.Map<K, V> implements java.io.Serializable, java.lang.Cloneable",
                 " implements "),
                ("Api<java.util.Map<String, Integer>> extends Base", " extends "),
                ("<T extends java.lang.Number & java.lang.Comparable<T>>", ","),
                ("", ","),
            )
        ],
        "contracts": [
            {
                "header": header,
                "declaration": contract[0],
                "superclass": contract[1],
                "interfaces": sorted(contract[2]),
            }
            for header in headers
            for contract in [verify.type_contract(header)]
        ],
        "declarations": DECLARATIONS,
        "final_flags": flags,
        "compatible": compatible,
        "widening": [
            {
                "expected": expected,
                "actual": actual,
                "type_parameters": parameters,
                "result": verify.constructor_list_widening(expected, actual, set(parameters)),
            }
            for expected, actual, parameters in WIDENING_CASES
        ],
    }


def report_vectors() -> dict:
    good = {
        "actual_executed_cases": 2385,
        "failures": 0,
        "ignored": 0,
        "process_exit_code": 0,
        "output": "ACTUAL_TESTS=2385\nFAILURES=0\nIGNORED=0\n",
        "stderr": "",
        "compile_release": 8,
        "harness_class_major": 52,
        "javac_version": "javac 25.0.3",
        "java_version": "openjdk 25.0.3",
        "test_input_sha256": {"src/test/java/Example.java": "example"},
    }
    invalid = {
        "incomplete": {
            "actual_executed_cases": 2384,
            "output": "ACTUAL_TESTS=2384\nFAILURES=0\nIGNORED=0\n",
        },
        "ignored": {"ignored": 1, "output": "ACTUAL_TESTS=2385\nFAILURES=0\nIGNORED=1\n"},
        "failed": {"failures": 1, "output": "ACTUAL_TESTS=2385\nFAILURES=1\nIGNORED=0\n"},
        "exit": {"process_exit_code": 1},
        "missing_output": {"output": ""},
        "nonnumeric": {"actual_executed_cases": "2385"},
        "wrong_bytecode": {"harness_class_major": 65},
    }
    validations = []
    for label, changes in (("good", {}), *invalid.items()):
        report = dict(good)
        report.update(changes)
        try:
            verify.validate_run_report(report)
            validations.append({"label": label, "report": report, "error": None})
        except ValueError as error:
            validations.append({"label": label, "report": report, "error": str(error)})
    outputs = [
        "ACTUAL_TESTS=2385\nFAILURES=0\nIGNORED=0\n",
        "ACTUAL_TESTS=2385\n",
        "ACTUAL_TESTS=2385\nACTUAL_TESTS=2385\n",
        "ACTUAL_TESTS=\n",
        "ACTUAL_TESTS=23x\n",
        "ACTUAL_TESTS =2385\n",
        "ACTUAL_TESTS=2385\r\nIGNORED=0\r\n",
        "",
    ]
    return {
        "result_field": [
            {"output": output, "label": label, "result": verify.result_field(output, label)}
            for output in outputs
            for label in ("ACTUAL_TESTS", "FAILURES", "IGNORED")
        ],
        "validate": validations,
    }


def json_vectors() -> dict:
    values = [
        {},
        [],
        {"b": 1, "a": [1, 2], "c": {"d": None, "e": True, "f": False}},
        {"text": "quote \" backslash \\ newline \n tab \t caf\u00e9 \u2603"},
        {"empty": "", "zero": 0, "list": ["a", ["b"]]},
        [{"name": "Api", "flags": ["ACC_PUBLIC", "ACC_FINAL"]}],
        {"unicode": "\u0000\u001f\u007f\u0080"},
        {"long": "x" * 40},
    ]
    return {
        "dumps": [
            {
                "value": value,
                "sort_keys": sorted_keys,
                "compact": json.dumps(value, sort_keys=sorted_keys),
                "indented": json.dumps(value, indent=2, sort_keys=sorted_keys),
            }
            for value in values
            for sorted_keys in (False, True)
        ]
    }


def type_vectors(fixture: Path) -> dict:
    classes, signatures = read_signatures(fixture)
    names = list(classes)
    for label, signature in SYNTHETIC_SIGNATURES.items():
        names.append(label)
        signatures[label] = signature
    surfaces = []
    inventories = []
    private_nested = []
    for name in names:
        signature = signatures[name]
        for include_package in (False, True):
            case = {"name": name}
            case.update(surface_case(signature, include_package))
            surfaces.append(case)
        inventory = {"name": name}
        inventory.update(inventory_case(signature))
        inventories.append(inventory)
        if name in classes:
            private_nested.append(
                {"name": name, "result": verify.private_nested_type(signature, name)}
            )
    records = []
    for inventory in inventories:
        for record in inventory.get("records", []):
            records.append({"record": record, "visible": verify.source_visible(record)})
    return {
        "types": classes,
        "synthetic": list(SYNTHETIC_SIGNATURES),
        "signatures": signatures,
        "surfaces": surfaces,
        "inventories": inventories,
        "visibility": records,
        "private_nested": private_nested,
    }


GATE_CASES = {
    "declared-and-inherited": (
        {
            "Epa.java": "public class Epa {}",
            "BaseWorld.java": "public class BaseWorld<T> {}",
            "World.java": "public class World<T> extends BaseWorld<T> {}",
            "Rotation.java": "public class Rotation { protected double cost; }",
            "Force.java": "public class Force {}",
            "DetectResult.java": "public class DetectResult<T> {}",
        },
        {
            "Epa.java": "public class Epa { protected final int maxIterationsField() { return 1; } }",
            "BaseWorld.java": "public class BaseWorld<T> { protected final T settingsField() { return null; } }",
            "World.java": "public class World<T> extends BaseWorld<T> {}",
            "Rotation.java": "public class Rotation { protected double cost; public double costValue() { return cost; } }",
            "Force.java": "public class Force { public final Object rawForce$io_github_rubixhacker_dyn4k_core() { return null; } }",
            "DetectResult.java": "public class DetectResult<T> { protected final T bodyField() { return null; } }",
        },
        None,
    ),
    "generated-identifiers": (
        {
            "Api.java": "package p; public class Api {}",
            "Mode.java": "package p; public enum Mode { ONE; }",
            "Other.java": "package q; public class Other { public static Object Companion = new Object(); "
                          "public static Object getEntries() { return null; } }",
        },
        {
            "Api.java": "package p; public class Api { public static Object Companion = new Object(); }",
            "Mode.java": "package p; public enum Mode { ONE; public static Object getEntries() { return null; } }",
            "Other.java": "package q; public class Other { public static Object Companion = new Object(); "
                          "public static Object getEntries() { return null; } }",
        },
        None,
    ),
    "final-type-overload": (
        {"Api.java": "public final class Api { public String value(String input) { return input; } }"},
        {
            "Api.java": "public final class Api { public String value(String input) { return input; } "
                        "public String value(Integer input) { return null; } }"
        },
        None,
    ),
    "field-hiding-constant": (
        {
            "Parent.java": "public class Parent { public static final int KEY = 1; }",
            "Api.java": "public class Api extends Parent {}",
        },
        {
            "Parent.java": "public class Parent { public static final int KEY = 1; }",
            "Api.java": "public class Api extends Parent { public static int KEY = 2; }",
        },
        None,
    ),
    "package-private": (
        {"Api.java": "package p; class Api {}"},
        {"Api.java": "package p; class Api { public final String helper() { return \"api\"; } }"},
        None,
    ),
    "missing-package-private": (
        {"Api.java": "package p; class Api {}"},
        {"Other.java": "package p; public class Other {}"},
        None,
    ),
    "method-type-parameter": (
        {
            "Parent.java": "public class Parent<T> { public <T> T convert(T value) { return value; } }",
            "Api.java": "public class Api extends Parent<String> {}",
        },
        {
            "Parent.java": "public class Parent<T> { public <T> T convert(T value) { return value; } }",
            "Api.java": "public class Api extends Parent<String> { public final String convert(String value) { return value; } }",
        },
        None,
    ),
    "private-nested": (
        {"World.java": "package p; public class World { private static class WarmStartHandler {} }"},
        {"World.java": "package p; public class World { private static class WarmStartHandler "
                       "{ public final String helper() { return null; } } }"},
        None,
    ),
}


def gate_vectors() -> list[dict]:
    cases = []
    for label, (before, after, only) in GATE_CASES.items():
        baseline = build_jar(TEMP / ("gate-" + label + "-baseline"), before)
        candidate = build_jar(TEMP / ("gate-" + label + "-candidate"), after)
        baseline_types, baseline_signatures = verify.jar_types(baseline, None, "-p", True)
        selected = set(baseline_types) if only is None else only
        candidate_types, candidate_signatures = verify.jar_types(
            candidate, set(baseline_types) if only is None else only, "-p", True
        )
        lookups = {"baseline": {}, "candidate": {}}
        real_run = subprocess.run

        def recording(command, *args, _real=real_run, **kwargs):
            result = _real(command, *args, **kwargs)
            if command and command[0] == "javap" and "-classpath" in command:
                classpath = command[command.index("-classpath") + 1]
                key = "baseline" if Path(classpath) == baseline else "candidate"
                lookups[key][command[-1]] = result.stdout
            return result

        with patch.object(verify.subprocess, "run", side_effect=recording):
            risks, errors = verify.added_member_gate(
                baseline,
                candidate,
                selected,
                baseline_signatures,
                candidate_signatures,
                str(candidate),
            )
        for risk in risks:
            risk["artifact_sha256"] = "<sha256>"
        cases.append(
            {
                "label": label,
                "selected": sorted(selected),
                "baseline_signatures": baseline_signatures,
                "candidate_signatures": candidate_signatures,
                "extra_baseline": lookups["baseline"],
                "extra_candidate": lookups["candidate"],
                "risks": risks,
                "errors": errors,
            }
        )
    return cases


COMPARE_CASES = {
    "kotlin-style-additions": (
        {
            "Api.java": "public final class Api<T extends Number> { public T value; "
                        "public void move(int n) {} public static int size() { return 1; } }",
            "Helper.java": "class Helper { public void internal() {} }",
        },
        {
            "Api.java": "public final class Api<T extends Number> implements java.io.Serializable "
                        "{ public static int size() { return 1; } public void move(int n) {} "
                        "public T value; public int added() { return 0; } }",
            "Helper.java": "class Helper { public void internal() {} }",
        },
        None,
    ),
    "final-method-override": (
        {"Api.java": "public class Api { public Number value() { return 1; } }"},
        {"Api.java": "public class Api { public final Number value() { return 1; } }"},
        None,
    ),
    "final-type": (
        {"Api.java": "public class Api {}"},
        {"Api.java": "public final class Api {}"},
        None,
    ),
    "transitive-interface": (
        {
            "Parent.java": "public interface Parent { void move(); }",
            "Child.java": "public interface Child extends Parent {}",
            "Api.java": "public class Api implements Child, Parent { public void move() {} }",
        },
        {
            "Parent.java": "public interface Parent { void move(); }",
            "Child.java": "public interface Child extends Parent {}",
            "Api.java": "public class Api implements Child { public void move() {} }",
        },
        ["Api"],
    ),
    "constructor-widening": (
        {
            "Api.java": "public abstract class Api<T> { public Api(java.util.List<T> values) {} "
                        "protected Api(Api<T> other, java.util.List<T> values) {} "
                        "public void move(java.util.List<T> values) {} }",
        },
        {
            "Api.java": "public abstract class Api<T> { public Api(java.util.List<? extends T> values) {} "
                        "protected Api(Api<T> other, java.util.List<? extends T> values) {} "
                        "public void move(java.util.List<T> values) {} }",
        },
        ["Api"],
    ),
    "missing-method": (
        {
            "Api.java": "public class Api<T extends Number> extends Parent { public T value; "
                        "public static int size() { return 1; } public void move(int n) {} "
                        "public java.util.List<String> items() { return null; } }",
            "Parent.java": "public class Parent {}",
        },
        {
            "Api.java": "public class Api<T extends Number> extends Parent { public T value; "
                        "public static int size() { return 1; } "
                        "public java.util.List<String> items() { return null; } }",
            "Parent.java": "public class Parent {}",
        },
        None,
    ),
}


REPORT_FIELDS = (
    "compared_api_types",
    "missing_types",
    "signature_mismatches",
    "compatible_differences",
    "inventory_errors",
    "fixture_failures",
    "fixture_errors",
)


def compare_vectors() -> list[dict]:
    cases = []
    for label, (before, after, only) in COMPARE_CASES.items():
        baseline = build_jar(TEMP / ("compare-" + label + "-baseline"), before)
        candidate = build_jar(TEMP / ("compare-" + label + "-candidate"), after)
        with patch.object(verify, "BINARY_SHA256", verify.digest(baseline)):
            report = verify.compare_jars(
                baseline, candidate, set(only) if only else None
            )
        risks = [
            {key: value for key, value in risk.items() if key != "artifact_sha256"}
            for risk in report["added_member_risks"]
        ]
        cases.append(
            {
                "label": label,
                "baseline_sources": before,
                "candidate_sources": after,
                "only": only,
                "baseline_types": report["baseline_types"],
                "candidate_types": report["candidate_types"],
                "compared_baseline_declarations": report["compared_baseline_declarations"],
                "risk_declarations": risks,
                **{field: report[field] for field in REPORT_FIELDS},
            }
        )
    return cases


def check_source_vectors() -> list[dict]:
    """The `check-source` command over one clean, then three broken, checkouts."""
    root = TEMP / "check-source"
    checkout = root / "checkout"
    source = checkout / "src/main/java/example/Api.java"
    test = checkout / "src/test/java/example/ApiTest.java"
    source.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    source.write_text("package example; public class Api {}\n")
    test.write_text("package example; public class ApiTest {}\n")
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    subprocess.run(["git", "-C", str(checkout), "add", "src"], check=True)
    subprocess.run(
        ["git", "-C", str(checkout), "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "commit", "-qm", "fixture"],
        check=True,
    )
    revision = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    archive = root / "sources.jar"
    with zipfile.ZipFile(archive, "w") as jar:
        jar.writestr("example/Api.java", source.read_bytes())
    cases = []

    def record(label):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/baseline/verify.py"), "check-source",
             "--checkout", str(checkout), "--sources-jar", str(archive), "--commit", revision],
            capture_output=True, text=True,
        )
        cases.append(
            {
                "label": label,
                "exit_code": result.returncode,
                "stdout": normalise(result.stdout),
                "stderr": normalise(result.stderr),
            }
        )

    record("clean")
    original = "package example; public class Api {}\n"
    source.write_text("package example; public class Api { int changed; }\n")
    record("dirty")
    source.write_text(original)
    untracked = checkout / "src/test/java/example/Extra.java"
    untracked.write_text("class Extra {}\n")
    record("untracked")
    untracked.unlink()
    with zipfile.ZipFile(archive, "w") as jar:
        jar.writestr("example/Api.java", b"package example; public class Api { int changed; }\n")
    record("archive-bytes")
    return cases


def check_run_vectors() -> list[dict]:
    good = {
        "actual_executed_cases": 2385,
        "failures": 0,
        "ignored": 0,
        "process_exit_code": 0,
        "output": "ACTUAL_TESTS=2385\nFAILURES=0\nIGNORED=0\n",
        "stderr": "",
        "compile_release": 8,
        "harness_class_major": 52,
        "javac_version": "javac 25.0.3",
        "java_version": "openjdk 25.0.3",
        "test_input_sha256": {"src/test/java/Example.java": "example"},
    }
    cases = []
    report = TEMP / "run.json"
    for label, changes in (
        ("good", {}),
        ("incomplete", {"actual_executed_cases": 2384}),
        ("missing_output", {"output": ""}),
        ("wrong_bytecode", {"harness_class_major": 65}),
    ):
        value = dict(good)
        value.update(changes)
        report.write_text(json.dumps(value))
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/baseline/verify.py"), "check-run",
             "--report", str(report)],
            capture_output=True, text=True,
        )
        cases.append(
            {
                "label": label,
                "report": value,
                "exit_code": result.returncode,
                "stdout": normalise(result.stdout),
                "stderr": normalise(result.stderr),
            }
        )
    return cases


def harness_vectors() -> dict:
    """The JUnit runner source `_execute_snapshot` writes, read out of the Python source."""
    module = ast.parse((ROOT / "tools/baseline/verify.py").read_text())
    for node in ast.walk(module):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and \
                node.value.startswith("import org.junit.runner.JUnitCore;"):
            return {"report_harness": node.value}
    raise SystemExit("the JUnit runner literal is missing from verify.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate the baseline port's parity vectors.")
    parser.add_argument("--kotlin", type=Path, help="write BaselineVectors.kt to this path")
    parser.add_argument("--json", type=Path, help="also write the raw JSON payload here")
    options = parser.parse_args()

    fixture = build_jar(TEMP / "fixture", FIXTURE_SOURCES)
    payload = {
        "revision": revision(),
        "python_module": "tools/baseline/verify.py",
        "javac": javac_version(),
        "policy": {
            "commit": verify.COMMIT,
            "binary_sha256": verify.BINARY_SHA256,
            "sources_sha256": verify.SOURCES_SHA256,
            "base": verify.BASE,
            "junit": verify.JUNIT,
            "hamcrest": verify.HAMCREST,
            "expected_cases": verify.EXPECTED_CASES,
            "required_fixture_sha256": verify.REQUIRED_FIXTURE_SHA256,
        },
        "text": text_vectors(),
        "declarations": declaration_vectors(),
        "types": type_vectors(fixture),
        "gate": gate_vectors(),
        "reports": report_vectors(),
        "json": json_vectors(),
        "compare": compare_vectors(),
        "check_source": check_source_vectors(),
        "check_run": check_run_vectors(),
        "harness": harness_vectors(),
    }
    text = json.dumps(payload, indent=1, sort_keys=False, ensure_ascii=True)
    if options.json:
        options.json.write_text(text + "\n")
    if options.kotlin:
        chunks = [
            base64.b64encode(text.encode()).decode()[index : index + 60000]
            for index in range(0, len(base64.b64encode(text.encode()).decode()), 60000)
        ]
        body = "\n".join('        "%s",' % chunk for chunk in chunks)
        options.kotlin.write_text(
            f'''package io.github.rubixhacker.harness.baseline

import okio.ByteString.Companion.decodeBase64

/**
 * Recorded outputs of `tools/baseline/verify.py`, generated at git revision
 * {payload["revision"]} by `tools/harness/baseline/parity/generate_vectors.py` with
 * `{payload["javac"]}`.
 *
 * Every value in the payload was printed by the Python implementation; the Kotlin suites replay
 * these vectors and assert the port reproduces them. The payload is base64 so the literals stay
 * inside the class-file constant-pool limit without escaping.
 */
internal object BaselineVectors {{
    const val PYTHON_REVISION: String = "{payload["revision"]}"

    private val chunks: List<String> = listOf(
{body}
    )

    /** The recorded JSON payload. */
    val json: String by lazy {{ chunks.joinToString("").decodeBase64()!!.utf8() }}
}}
'''
        )
    if not options.kotlin and not options.json:
        print(text)
    shutil.rmtree(TEMP, ignore_errors=True)


if __name__ == "__main__":
    main()
