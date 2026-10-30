#!/usr/bin/env python3
"""Regenerate `FullHostedVectors.kt` for the hosted full-corpus port.

Provenance
----------
Every input and every expected value here is produced by the Python reference,
`tools/qualification/full_hosted.py`, at the git revision recorded in the emitted file
(`REVISION`). Nothing was computed by the Kotlin port and copied back.

Only the pure functions are recorded: the generated Gradle scripts, the Safari product paths, the
generated-configuration input reader, the Safari mode arguments, and the Safari diagnostic value
grammar. The file-system and process functions are exercised by their own suites against fixtures
built in the test, because their outcomes depend on the host clock and inode identities.

Output
------
`src/jvmTest/kotlin/io/github/rubixhacker/harness/qualification/FullHostedVectors.kt` in the
`tools/harness/qualification` module. Run from the repository root:

    python3 tools/harness/qualification/parity/generate_full_hosted_vectors.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools" / "qualification"))

import full_hosted  # noqa: E402
import qualify  # noqa: E402

TARGET = (
    ROOT / "tools" / "harness" / "qualification" / "src" / "jvmTest" / "kotlin" / "io" / "github"
    / "rubixhacker" / "harness" / "qualification" / "FullHostedVectors.kt"
)


def revision():
    return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()


def kotlin(text):
    """A Kotlin string literal holding exactly `text`."""
    encoded = json.dumps(text, ensure_ascii=True)
    return '"' + encoded[1:-1].replace("\\/", "/").replace("$", "\\$") + '"'


def outcome(call):
    """Run `call`, recording its result or the exact exception message."""
    try:
        return {"ok": True, "value": call()}
    except Exception as error:  # noqa: BLE001 - the message is the recorded evidence
        return {"ok": False, "error": str(error)}


def emit_outcome(value, render):
    if value["ok"]:
        return "VectorValue(" + render(value["value"]) + ")"
    return "VectorError(" + kotlin(value["error"]) + ")"


# ------------------------------------------------------------------------------------------
# init_script and graph_script
# ------------------------------------------------------------------------------------------

INIT_SCRIPTS = [
    ("jsSafari", "development", None),
    ("jsSafari", "production", None),
    ("macosArm64", "debug-g", None),
    ("macosArm64", "optimized-opt", None),
    ("mingwX64", "optimized-opt", None),
    ("iosSimulatorArm64", "debug-g", "1F0E7D2A-8A1B-4C3D-9E4F-56A7B8C9D0E1"),
    ("iosSimulatorArm64", "debug-g", "not-a-udid"),
]

GRAPH_SCRIPTS = ["jsSafari", "macosArm64", "mingwX64", "iosSimulatorArm64"]

# ------------------------------------------------------------------------------------------
# safari_product_paths
# ------------------------------------------------------------------------------------------

PRODUCT_PATHS = [
    ("/work/dyn4k-core", "development", "dyn4k-core"),
    ("/work/dyn4k-core", "production", "dyn4k-core"),
    ("/work/dyn4k", "development", "dyn4k"),
    ("/work/consumers/qualification/portable", "development", "consumer"),
    ("/work/consumers/qualification/portable", "production", "consumer"),
    ("/work/dyn4k-core", "release", "dyn4k-core"),
    ("/work/dyn4k-core", "development", "other"),
]

# ------------------------------------------------------------------------------------------
# safari_config_input
# ------------------------------------------------------------------------------------------

PREFIX = "\nmodule.exports = function(config) {\n\nconfig.set("


def generated_config(files):
    settings = {
        "singleRun": True,
        "autoWatch": False,
        "basePath": "/work/build/js/packages/dyn4k-dyn4k-core-test",
        "files": files,
        "webpack": {"mode": "development"},
    }
    return PREFIX + json.dumps(settings) + ");\nmodule.exports = null;\n"


CONFIG_INPUTS = [
    generated_config(["/runner.js", "/work/kotlin/dyn4k-dyn4k-core-test.js"]),
    generated_config(["runner", "selected.js", "extra"]),
    "not the generated shape",
    PREFIX + '{"files": ["only-one"]});',
    PREFIX + '{"files": "not-a-list"});',
]

# ------------------------------------------------------------------------------------------
# verify_safari_mode_arguments
# ------------------------------------------------------------------------------------------

MODE_ARGUMENTS = [
    (["gradlew", "--rerun-tasks", "jsBrowserTest"], "source", None),
    (["gradlew", "-PqualificationSafari=true"], "consumer", None),
    (["gradlew", "-PqualificationSafari=true", "-PqualificationProduction=true"],
     "consumer", "production"),
    (["gradlew", "-PqualificationSafari=true"], "consumer", "production"),
    (["gradlew", "-PqualificationSafari=false"], "consumer", None),
    (["gradlew", "--project-prop=qualificationSafari=true"], "consumer", None),
    (["gradlew", "-Dorg.gradle.project.qualificationProduction=true"], "source", "production"),
    (["gradlew", "-PqualificationSafari=true", "-PqualificationProduction=true"], "stage", None),
    (["gradlew", "-PqualificationProduction=true"], "stage", "production"),
]

# ------------------------------------------------------------------------------------------
# Safari diagnostic grammar
# ------------------------------------------------------------------------------------------

INF = "Infinity"
NAN = "NaN"


def number_bits(value):
    import struct
    return struct.unpack(">q", struct.pack(">d", value))[0]


NUMBERS = [
    "1.5@" + str(number_bits(1.5)),
    "0@" + str(number_bits(0.0)),
    "0@-9223372036854775808",
    "-0@" + str(number_bits(-0.0)),
    "0@" + str(number_bits(-0.0)),
    "NaN@" + str(-2251799813685248),
    "Infinity@" + str(number_bits(float("inf"))),
    "-Infinity@" + str(number_bits(float("-inf"))),
    "1e3@" + str(number_bits(1000.0)),
    "1.5@" + str(number_bits(1.25)),
    "1.5@1.5",
    "1.5@" + str(1 << 63),
    "01@" + str(number_bits(1.0)),
    "1.5",
    " 1.5@" + str(number_bits(1.5)),
    "1.5@" + str(number_bits(1.5)) + "@0",
]

INTEGERS = [
    ("0", None),
    ("-1", None),
    ("12", 0),
    ("11", 12),
    ("+1", None),
    ("01", None),
    ("1.0", None),
    ("", None),
    ("12345678901234567890", None),
    ("-1234567890123456789", None),
]

VECTORS = [
    "1@" + str(number_bits(1.0)) + ",2@" + str(number_bits(2.0)),
    "1@1,2@2",
    "1@" + str(number_bits(1.0)),
    "1@" + str(number_bits(1.0)) + ",2@" + str(number_bits(2.0)) + ",3@" + str(number_bits(3.0)),
]

NUMBERS_COUNT = [
    ("1@0,2@0", 2),
    ("1@0,2@0", 3),
    ("1@0;2@0", 2),
]

VECTORS_FORMS = [
    ("null", True, True),
    ("", True, True),
    ("null", False, True),
    ("", True, False),
    ("1@0,2@0;3@0,4@0", True, True),
    ("1@0,2@0;", True, True),
]

FEATURES = [
    "point:3:1@0,2@0",
    "point:3",
    "edge:1:2:1@0,2@0:4:3@0,4@0:6:5@0,6@0",
    "edge:1:2:1@0,2@0",
    "unknown:7",
    "unknown",
    "other:1",
]

SHAPES = [
    "kind=Circle|center=1@0,2@0|radius=3@0|circle.radius=3@0",
    "kind=Polygon|center=0@0,0@0|radius=1@0|vertices=0@0,0@0;1@0,0@0;1@0,1@0|normals=0@0,0@0;1@0,0@0;1@0,1@0",
    "kind=Polygon|center=0@0,0@0|radius=1@0|vertices=0@0,0@0|normals=0@0,0@0;1@0,0@0",
    "kind=Segment|center=0@0,0@0|radius=1@0|vertices=0@0,0@0|normals=0@0,0@0|segment.length=1@0",
    "kind=Capsule|center=0@0,0@0|radius=1@0|capsule.length=1@0|capsule.capRadius=1@0|capsule.localFoci=null|capsule.localAxis=1@0,0@0",
    "kind=Circle|radius=3@0|center=1@0,2@0|circle.radius=3@0",
    "kind=Unknown|center=1@0,2@0|radius=3@0",
    "kind=Circle|center=1@0,2@0|radius=3@0",
]

POLYGON_EDGES = [
    ("na", "Circle", None),
    (
        "0:0@0:1@0:2@0:3@0:4@0:5@0:6@0:7@0:8@0:9@0:10@0:11@0",
        "Polygon",
        1,
    ),
    ("0:0@0:1@0", "Polygon", 1),
    ("na", "Polygon", 1),
    ("na", "Segment", 2),
]

SAT_CANDIDATES = [
    "0:0:zero:1@0,2@0",
    "0:0:separated:1@0,2@0:3@0,4@0:5@0,6@0",
    "0:0:zero:1@0,2@0;1:1:separated:1@0,2@0:3@0,4@0:5@0,6@0",
    "0:0:zero:1@0,2@0;1:1:separated:1@0,2@0:3@0,4@0:5@0,6@0;2:2:zero:1@0,2@0",
    "2:0:zero:1@0,2@0",
    "0:0:zero",
    "",
]

EPA_RECORDS = [
    ("", 0),
    (
        "1:0:1@0,2@0:3@0,4@0:5@0,6@0:7@0,8@0:9@0:10@0,11@0:12@0:13@0:continue:1,2:true",
        1,
    ),
    ("1:na:1@0,2@0:3@0,4@0:5@0,6@0:7@0,8@0:9@0:10@0,11@0:12@0:13@0:epsilon::false", 1),
    ("1:0:1@0,2@0", 1),
    ("", 1),
    (
        "2:0:1@0,2@0:3@0,4@0:5@0,6@0:7@0,8@0:9@0:10@0,11@0:12@0:13@0:continue:1:true",
        1,
    ),
]


def render_paths(value):
    expected, karma_input, build_root, karma_package = value
    return "VectorPaths(" + ", ".join(
        kotlin(str(item)) for item in (expected, karma_input, build_root, karma_package)
    ) + ")"


def render_bool(value):
    return "true" if value else "false"


def render_int_or_null(value):
    return "null" if value is None else str(value)


def render_shape(value):
    kind, count = value
    return "VectorShape(" + kotlin(kind) + ", " + render_int_or_null(count) + ")"


def render_success(value):
    return "VectorOk(" + kotlin(value) + ")"


def render_none(value):
    return "VectorOk(null)"


def render_count(value):
    return "VectorCount(" + render_int_or_null(value) + ")"


def main():
    lines = []
    add = lines.append
    add("// Generated by tools/harness/qualification/parity/generate_full_hosted_vectors.py.")
    add("// Source of truth: tools/qualification/full_hosted.py at the revision below.")
    add("package io.github.rubixhacker.harness.qualification")
    add("")
    add("/** One recorded outcome: either the reference's value or its exact exception message. */")
    add("internal sealed class VectorOutcome")
    add("internal class VectorValue(val value: Any?) : VectorOutcome()")
    add("internal class VectorError(val message: String) : VectorOutcome()")
    add("internal class VectorPaths(")
    add("    val expected: String,")
    add("    val karmaInput: String,")
    add("    val buildRoot: String,")
    add("    val karmaPackage: String,")
    add(")")
    add("internal class VectorShape(val kind: String, val count: Int?)")
    add("internal class VectorInt(val literal: String)")
    add("internal class VectorCount(val value: Int?)")
    add("internal class VectorBoolean(val value: Boolean)")
    add("internal class VectorOk(val value: String?)")
    add("")
    add("internal object FullHostedVectors {")
    add("    const val REVISION = " + kotlin(revision()))
    add("")
    add("    class InitScript(")
    add("        val target: String,")
    add("        val configuration: String,")
    add("        val simulatorUdid: String?,")
    add("        val text: VectorOutcome,")
    add("    )")
    add("")
    add("    val INIT_SCRIPTS = listOf(")
    for target, configuration, simulator in INIT_SCRIPTS:
        result = outcome(lambda: full_hosted.init_script(target, configuration, simulator))
        add(
            "        InitScript("
            + kotlin(target) + ", " + kotlin(configuration) + ", "
            + ("null" if simulator is None else kotlin(simulator)) + ", "
            + emit_outcome(result, render_success) + "),"
        )
    add("    )")
    add("")
    add("    class GraphScript(val target: String, val text: String)")
    add("")
    add("    val GRAPH_SCRIPTS = listOf(")
    for target in GRAPH_SCRIPTS:
        add(
            "        GraphScript(" + kotlin(target) + ", "
            + kotlin(full_hosted.graph_script(target)) + "),"
        )
    add("    )")
    add("")
    add("    class ProductSelection(")
    add("        val project: String,")
    add("        val configuration: String,")
    add("        val name: String,")
    add("        val paths: VectorOutcome,")
    add("    )")
    add("")
    add("    val PRODUCT_PATHS = listOf(")
    for project, configuration, name in PRODUCT_PATHS:
        result = outcome(
            lambda: full_hosted.safari_product_paths(Path(project), configuration, name)
        )
        add(
            "        ProductSelection(" + kotlin(project) + ", " + kotlin(configuration) + ", "
            + kotlin(name) + ", " + emit_outcome(result, render_paths) + "),"
        )
    add("    )")
    add("")
    add("    class ConfigInput(val data: String, val input: VectorOutcome)")
    add("")
    add("    val CONFIG_INPUTS = listOf(")
    for data in CONFIG_INPUTS:
        result = outcome(lambda: full_hosted.safari_config_input(data.encode()))
        add("        ConfigInput(" + kotlin(data) + ", " + emit_outcome(result, render_success) + "),")
    add("    )")
    add("")
    add("    class ModeArguments(")
    add("        val command: List<String>,")
    add("        val processName: String,")
    add("        val configuration: String?,")
    add("        val outcome: VectorOutcome,")
    add("    )")
    add("")
    add("    val MODE_ARGUMENTS = listOf(")
    for command, process_name, configuration in MODE_ARGUMENTS:
        result = outcome(lambda: full_hosted.verify_safari_mode_arguments(
            command, process_name, configuration))
        add(
            "        ModeArguments("
            + "listOf(" + ", ".join(kotlin(item) for item in command) + "), "
            + kotlin(process_name) + ", "
            + ("null" if configuration is None else kotlin(configuration)) + ", "
            + emit_outcome(result, render_none) + "),"
        )
    add("    )")
    add("")
    add("    class Number(final val value: String, final val outcome: VectorOutcome)")
    add("")
    add("    val SAFARI_NUMBERS = listOf(")
    for value in NUMBERS:
        result = outcome(lambda: full_hosted.safari_v2_number(value, "field"))
        add("        Number(" + kotlin(value) + ", " + emit_outcome(result, render_none) + "),")
    add("    )")
    add("")
    add("    class Integer(final val value: String, final val minimum: Long?, final val outcome: VectorOutcome)")
    add("")
    add("    val SAFARI_INTEGERS = listOf(")
    for value, minimum in INTEGERS:
        result = outcome(lambda: full_hosted.safari_v2_integer(value, "field", minimum))
        add(
            "        Integer(" + kotlin(value) + ", "
            + ("null" if minimum is None else str(minimum)) + ", "
            + emit_outcome(result, lambda item: "VectorInt(" + kotlin(str(item)) + ")") + "),"
        )
    add("    )")
    add("")
    add("    class VectorTwo(final val value: String, final val outcome: VectorOutcome)")
    add("")
    add("    val SAFARI_VECTORS = listOf(")
    for value in VECTORS:
        result = outcome(lambda: full_hosted.safari_v2_vector(value, "field"))
        add("        VectorTwo(" + kotlin(value) + ", " + emit_outcome(result, render_none) + "),")
    add("    )")
    add("")
    add("    class NumberList(final val value: String, final val count: Int, final val outcome: VectorOutcome)")
    add("")
    add("    val SAFARI_NUMBER_LISTS = listOf(")
    for value, count in NUMBERS_COUNT:
        result = outcome(lambda: full_hosted.safari_v2_numbers(value, "field", count))
        add(
            "        NumberList(" + kotlin(value) + ", " + str(count) + ", "
            + emit_outcome(result, render_none) + "),"
        )
    add("    )")
    add("")
    add("    class VectorList(")
    add("        final val value: String,")
    add("        final val allowNull: Boolean,")
    add("        final val allowEmpty: Boolean,")
    add("        final val outcome: VectorOutcome,")
    add("    )")
    add("")
    add("    val SAFARI_VECTOR_LISTS = listOf(")
    for value, allow_null, allow_empty in VECTORS_FORMS:
        result = outcome(lambda: full_hosted.safari_v2_vectors(
            value, "field", allow_null, allow_empty))
        add(
            "        VectorList(" + kotlin(value) + ", " + render_bool(allow_null) + ", "
            + render_bool(allow_empty) + ", " + emit_outcome(result, render_count) + "),"
        )
    add("    )")
    add("")
    add("    class Feature(final val value: String, final val outcome: VectorOutcome)")
    add("")
    add("    val SAFARI_FEATURES = listOf(")
    for value in FEATURES:
        result = outcome(lambda: full_hosted.safari_v2_feature(value, "field"))
        add("        Feature(" + kotlin(value) + ", " + emit_outcome(result, render_none) + "),")
    add("    )")
    add("")
    add("    class Shape(final val value: String, final val outcome: VectorOutcome)")
    add("")
    add("    val SAFARI_SHAPES = listOf(")
    for value in SHAPES:
        result = outcome(lambda: full_hosted.safari_v2_shape(value, "field"))
        add("        Shape(" + kotlin(value) + ", " + emit_outcome(result, render_shape) + "),")
    add("    )")
    add("")
    add("    class PolygonEdges(")
    add("        final val value: String,")
    add("        final val kind: String,")
    add("        final val vertices: Int?,")
    add("        final val outcome: VectorOutcome,")
    add("    )")
    add("")
    add("    val SAFARI_POLYGON_EDGES = listOf(")
    for value, kind, vertices in POLYGON_EDGES:
        result = outcome(lambda: full_hosted.safari_v2_polygon_edges(
            value, "field", kind, vertices))
        add(
            "        PolygonEdges(" + kotlin(value) + ", " + kotlin(kind) + ", "
            + render_int_or_null(vertices) + ", " + emit_outcome(result, render_none) + "),"
        )
    add("    )")
    add("")
    add("    class SatCandidates(final val value: String, final val outcome: VectorOutcome)")
    add("")
    add("    val SAFARI_SAT_CANDIDATES = listOf(")
    for value in SAT_CANDIDATES:
        result = outcome(lambda: full_hosted.safari_v2_sat_candidates(value, "field"))
        add(
            "        SatCandidates(" + kotlin(value) + ", "
            + emit_outcome(result, lambda item: "VectorBoolean(" + render_bool(item) + ")") + "),"
        )
    add("    )")
    add("")
    add("    class EpaRecords(final val value: String, final val iteration: Long, final val outcome: VectorOutcome)")
    add("")
    add("    val SAFARI_EPA_RECORDS = listOf(")
    for value, iteration in EPA_RECORDS:
        result = outcome(lambda: full_hosted.safari_v2_epa_records(value, "field", iteration))
        add(
            "        EpaRecords(" + kotlin(value) + ", " + str(iteration) + ", "
            + emit_outcome(result, render_none) + "),"
        )
    add("    )")
    add("}")
    TARGET.write_text("\n".join(lines) + "\n")
    print(f"wrote {TARGET} at {revision()}")


if __name__ == "__main__":
    main()
