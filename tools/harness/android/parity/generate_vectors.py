#!/usr/bin/env python3
"""Regenerate the Kotlin parity fixtures for the Android harness port.

Provenance
----------
Every value printed here came from the Python implementation in
`tools/android-runtime` and `tools/android-native-runtime` at the git revision
recorded in the output object. Nothing is computed by the Kotlin port and
copied back.

Usage
-----
    python3 tools/harness/android/parity/generate_vectors.py > vectors.json
    python3 tools/harness/android/parity/emit_kotlin_vectors.py < vectors.json

`emit_kotlin_vectors.py` writes
`src/jvmTest/kotlin/io/github/rubixhacker/harness/android/AndroidVectors.kt`.
Re-running both reproduces every recorded value; the only paths that vary
between runs are the `mkdtemp` scratch directories under `/tmp`, which the
generator normalises to `<tmp>`.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/var/home/stewart/Workspace/dyn4k")
RUNTIME = REPO / "tools" / "android-runtime"
NATIVE = REPO / "tools" / "android-native-runtime"
# Both directories contain modules named `run` and `full`, so import the runtime
# modules first and only then put the native directory on the path.
sys.path.insert(0, str(RUNTIME))
import android_corpus  # noqa: E402
import build_identity  # noqa: E402
import evidence  # noqa: E402
import full_evidence  # noqa: E402
import optimized_evidence  # noqa: E402
import prepare  # noqa: E402
import run  # noqa: E402
import run_full  # noqa: E402
import run_optimized  # noqa: E402

sys.path.insert(0, str(NATIVE))
import receipt  # noqa: E402
import full as native_full  # noqa: E402

TEMP = Path(tempfile.mkdtemp(prefix="dyn4k-android-vectors-")).resolve()


def normalise(text):
    return text.replace(str(TEMP), "<tmp>")


def normalise_value(value):
    """Rewrites the scratch directory to ``<tmp>`` in every string of a JSON value."""
    return json.loads(normalise(json.dumps(value)))


def outcome(call):
    try:
        return {"value": call()}
    except Exception as error:  # noqa: BLE001 - the recorded shape is the point
        return {"error": str(error), "type": type(error).__name__}


def revision():
    return subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()


# --------------------------------------------------------------------------- #
# evidence.parse_instrumentation / validate_lane
# --------------------------------------------------------------------------- #

INSTRUMENTATION_RAW = [
    # a plain passing run with one portable case
    "INSTRUMENTATION_STATUS: class=Suite\n"
    "INSTRUMENTATION_STATUS: test=passes\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "INSTRUMENTATION_RESULT: stream=\n"
    "OK (1 test)\n"
    "INSTRUMENTATION_CODE: -1\n",
    # two instrumentation cases, one portable case, a start record, numtests
    "INSTRUMENTATION_STATUS: class=ConsumerJourneyTest\n"
    "INSTRUMENTATION_STATUS: test=worldAndCallbacks\n"
    "INSTRUMENTATION_STATUS_CODE: 1\n"
    "INSTRUMENTATION_STATUS: class=ConsumerJourneyTest\n"
    "INSTRUMENTATION_STATUS: test=worldAndCallbacks\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "INSTRUMENTATION_STATUS: dyn4k_case=org.dyn4j.world.WorldResultTest#resultIsMutable\n"
    "INSTRUMENTATION_STATUS: dyn4k_status=PASSED\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "INSTRUMENTATION_STATUS: class=PortableSuiteTest\n"
    "INSTRUMENTATION_STATUS: test=allPortableCases\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "INSTRUMENTATION_RESULT: stream=\n"
    "OK (2 tests)\n"
    "INSTRUMENTATION_CODE: -1\n",
    # multi-line stack continuation
    "INSTRUMENTATION_STATUS: class=Suite\n"
    "INSTRUMENTATION_STATUS: test=fails\n"
    "INSTRUMENTATION_STATUS: stack=java.lang.AssertionError\n"
    "Caused by: java.lang.LinkageError: method became final\n"
    "INSTRUMENTATION_STATUS_CODE: -2\n"
    "OK (1 test)\n"
    "INSTRUMENTATION_CODE: -1\n",
    # skipped and failed portable cases plus a runner error
    "INSTRUMENTATION_STATUS: dyn4k_case=Suite#skips\n"
    "INSTRUMENTATION_STATUS: dyn4k_status=SKIPPED\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "INSTRUMENTATION_STATUS: dyn4k_case=Suite#breaks\n"
    "INSTRUMENTATION_STATUS: dyn4k_status=FAILED\n"
    "INSTRUMENTATION_STATUS: dyn4k_stack=boom\n"
    "second line\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "INSTRUMENTATION_STATUS: class=Suite\n"
    "INSTRUMENTATION_STATUS: test=skips\n"
    "INSTRUMENTATION_STATUS_CODE: -3\n"
    "INSTRUMENTATION_RESULT: shortMsg=instrumentation crashed\n"
    "OK (1 test)\n"
    "INSTRUMENTATION_CODE: -1\n",
    # duplicate portable case
    "INSTRUMENTATION_STATUS: dyn4k_case=Suite#test\n"
    "INSTRUMENTATION_STATUS: dyn4k_status=PASSED\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "INSTRUMENTATION_STATUS: dyn4k_case=Suite#test\n"
    "INSTRUMENTATION_STATUS: dyn4k_status=PASSED\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "OK (1 test)\n"
    "INSTRUMENTATION_CODE: -1\n",
    # invalid portable status
    "INSTRUMENTATION_STATUS: dyn4k_case=Suite#test\n"
    "INSTRUMENTATION_STATUS: dyn4k_status=WHAT\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "OK (1 test)\n"
    "INSTRUMENTATION_CODE: -1\n",
    # duplicate instrumentation case
    "INSTRUMENTATION_STATUS: class=Suite\n"
    "INSTRUMENTATION_STATUS: test=passes\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "INSTRUMENTATION_STATUS: class=Suite\n"
    "INSTRUMENTATION_STATUS: test=passes\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "OK (1 test)\n"
    "INSTRUMENTATION_CODE: -1\n",
    # missing terminal code
    "INSTRUMENTATION_STATUS: class=Suite\n"
    "INSTRUMENTATION_STATUS: test=passes\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "OK (1 test)\n",
    # unsuccessful terminal code
    "INSTRUMENTATION_STATUS: class=Suite\n"
    "INSTRUMENTATION_STATUS: test=passes\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "OK (1 test)\n"
    "INSTRUMENTATION_CODE: 0\n",
    # terminal code followed by output
    "INSTRUMENTATION_STATUS: class=Suite\n"
    "INSTRUMENTATION_STATUS: test=passes\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "OK (1 test)\n"
    "INSTRUMENTATION_CODE: -1\n"
    "trailing output\n",
    # zero-test summary
    "OK (0 tests)\n"
    "INSTRUMENTATION_CODE: -1\n",
    # duplicated summary
    "INSTRUMENTATION_STATUS: class=Suite\n"
    "INSTRUMENTATION_STATUS: test=passes\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "OK (1 test)\n"
    "OK (1 test)\n"
    "INSTRUMENTATION_CODE: -1\n",
    # failure summary
    "INSTRUMENTATION_STATUS: class=Suite\n"
    "INSTRUMENTATION_STATUS: test=passes\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "FAILURES!!!\n"
    "Tests run: 1,  Failures: 1\n"
    "OK (1 test)\n"
    "INSTRUMENTATION_CODE: -1\n",
    # summary before the case executes
    "OK (1 test)\n"
    "INSTRUMENTATION_STATUS: class=Suite\n"
    "INSTRUMENTATION_STATUS: test=passes\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "INSTRUMENTATION_CODE: -1\n",
    # carriage returns and a final blank line
    "INSTRUMENTATION_STATUS: class=Suite\r\n"
    "INSTRUMENTATION_STATUS: test=passes\r\n"
    "INSTRUMENTATION_STATUS_CODE: 0\r\n"
    "OK (1 test)\r\n"
    "INSTRUMENTATION_CODE: -1\r\n\r\n",
]

LANE_CASES = [
    {
        "raw": INSTRUMENTATION_RAW[0],
        "portable": [],
        "instrumentation": ["Suite#passes"],
        "exit": 0,
    },
    {
        "raw": INSTRUMENTATION_RAW[1],
        "portable": ["org.dyn4j.world.WorldResultTest#resultIsMutable"],
        "instrumentation": ["ConsumerJourneyTest#worldAndCallbacks",
                            "PortableSuiteTest#allPortableCases"],
        "exit": 0,
    },
    {
        "raw": INSTRUMENTATION_RAW[0],
        "portable": ["Missing#test"],
        "instrumentation": ["Suite#passes"],
        "exit": 0,
    },
    {
        "raw": INSTRUMENTATION_RAW[3],
        "portable": ["Suite#skips", "Suite#breaks"],
        "instrumentation": ["Suite#skips"],
        "exit": 0,
    },
    {
        "raw": INSTRUMENTATION_RAW[0],
        "portable": [],
        "instrumentation": ["Suite#passes"],
        "exit": 1,
    },
    {
        "raw": INSTRUMENTATION_RAW[3],
        "portable": [],
        "instrumentation": ["Suite#skips"],
        "exit": 0,
    },
    {
        "raw": INSTRUMENTATION_RAW[0],
        "portable": ["Extra#case"],
        "instrumentation": ["Suite#passes"],
        "exit": 0,
    },
    {
        "raw": INSTRUMENTATION_RAW[0],
        "portable": [],
        "instrumentation": [],
        "exit": 0,
    },
]


def parse_vectors():
    vectors = []
    for raw in INSTRUMENTATION_RAW:
        vectors.append({"raw": raw, "result": outcome(lambda raw=raw: evidence.parse_instrumentation(raw))})
    return vectors


def lane_vectors():
    vectors = []
    for item in LANE_CASES:
        def call(item=item):
            parsed = evidence.parse_instrumentation(item["raw"])
            evidence.validate_lane(parsed, set(item["portable"]),
                                   set(item["instrumentation"]), item["exit"])
            return "ok"
        vectors.append({**item, "result": outcome(call)})
    return vectors


# --------------------------------------------------------------------------- #
# optimized_evidence
# --------------------------------------------------------------------------- #

OPTIMIZED_CASE = "io.github.rubixhacker.dyn4k.optimized.OptimizedJourneyTest#appSideWorldAndSubclassCallbacks"
OPTIMIZED_RAW = "\n".join((
    "INSTRUMENTATION_STATUS: class=io.github.rubixhacker.dyn4k.optimized.OptimizedJourneyTest",
    "INSTRUMENTATION_STATUS: test=appSideWorldAndSubclassCallbacks",
    "INSTRUMENTATION_STATUS_CODE: 1",
    "INSTRUMENTATION_STATUS: class=io.github.rubixhacker.dyn4k.optimized.OptimizedJourneyTest",
    "INSTRUMENTATION_STATUS: test=appSideWorldAndSubclassCallbacks",
    "INSTRUMENTATION_STATUS_CODE: 0",
    "INSTRUMENTATION_RESULT: stream=",
    "OK (1 test)",
    "INSTRUMENTATION_CODE: -1",
    "",
))
PROVIDER = ("io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1\n"
            "io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1\n")
MAPPING = "\n".join((
    "io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer$CountingWorld -> a:",
    "    1:2:java.lang.String io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer.run():42:42 -> x",
    "org.dyn4j.geometry.Vector2 -> b:",
    "org.dyn4j.dynamics.Body -> c:",
    "org.dyn4j.world.World -> R8$$REMOVED$$CLASS$$16:",
))
USAGE = ("org.dyn4j.geometry.CircleDetector\n"
         "io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer\n")
DEX = ["La;", "Lb;", "Lc;"]

ACTIVITY = "io.github.rubixhacker.dyn4k.optimized.OptimizedActivity"
NARROW = f"-keep class {ACTIVITY} {{ public <init>(); public void onCreate(android.os.Bundle); }}\n"

OPTIMIZED_CONFIGURATIONS = [
    # accepted narrow keeps
    NARROW,
    "-keep public interface org.dyn4j.world.PhysicsWorld { *; }\n",
    "-keep enum org.dyn4j.geometry.MassType { *; }\n",
    "-keep @interface org.dyn4j.JvmFieldBridge { *; }\n",
    "-keepclassmembers class org.dyn4j.geometry.Vector2 { *; }\n",
    "-keep @android.support.annotation.Keep class * { *; }\n",
    "-keepclassmembers enum * { public static **[] values(); }\n",
    "-keepclassmembers enum * { public static **[] values(); public static ** valueOf(java.lang.String); }\n",
    "-keepattributes **\n",
    "-keepdirectories **\n",
    "-keeppackagenames org.dyn4j.**\n",
    "-keepparameternames\n",
    "-keep @* class org.dyn4j.geometry.Vector2 { *; }\n",
    f"# -keep class org.dyn4j.** {{ *; }}\n"
    f"-if class {ACTIVITY} -keep class {ACTIVITY} {{ <init>(); }} "
    f"-keepattributes Signature # -keepclassmembers class * {{ *** *; }}\n",
    "-dontwarn org.dyn4j.** # -keepclassmembers class org.dyn4j.** { *; }\n",
    # every broad rule family the Python tests reject
    "-keep class org.dyn4j.** { *; }\n",
    "-keep class org.dyn4j.geometry.** { *; }\n",
    "-keep class org.dyn4j.world.collision.** { *; }\n",
    "-keep class io.github.rubixhacker.dyn4k.geometry.** { *; }\n",
    "-keep public class org.dyn4j.geometry.** { *; }\n",
    "-keep,allowoptimization public final class io.github.rubixhacker.dyn4k.geometry.** { *; }\n",
    "-keep interface org.dyn4j.** { *; }\n",
    "  -keep,allowoptimization\tpublic interface org.dyn4j.world.** { *; }\n",
    "-keep\tpublic\tinterface\tio.github.rubixhacker.dyn4k.geometry.** { *; }\n",
    "-keep enum org.dyn4j.** { *; }\n",
    "-keep @interface org.dyn4j.** { *; }\n",
    "-keepclassmembers class org.dyn4j.** { *; }\n",
    "-keep class * { *; }\n",
    "-keepclassmembers,allowoptimization public @interface kotlin.** { *; }\n",
    "-keepnames class io.github.rubixhacker.dyn4k.optimized.* { *; }\n",
    "-keep! class * { *; }\n",
    "-keep class !android.** { *; }\n",
    "-keep class * extends org.dyn4j.world.World { *; }\n",
    "-keep @org.dyn4j.JvmFieldBridge class * { *; }\n",
    "-keepclassmembers class * { public int exact; *; }\n",
    "-keepclassmembers class * { <methods>; }\n",
    "-keepclassmembers class * { public void *(); }\n",
    "-keepclassmembers class * { *** *; }\n",
    "-keepclassmembers class * { % *; }\n",
    "-keepclassmembers class * { public *** x; }\n",
    "-keepclassmembers class * { *** onCreate(); }\n",
    "-keepclassmembers enum * { public static *** values(...); }\n",
    "-keepclassmembers enum * { public static **[] values(int); }\n",
    "-keepclassmembers enum * { public static int valueOf(int); }\n",
    "-keep class org.** { *; }\n",
    "-keepclassmembers class **.geometry.* { *; }\n",
    "-keep class ** { *; }\n",
    f"-if class {ACTIVITY} -keep class org.dyn4j.** {{ *; }}\n",
    f"-keep class {ACTIVITY} {{ <init>(); }} -keepclassmembers class * {{ *** *; }}\n",
    f"-keep class {ACTIVITY} {{ <init>(); }}-keepclassmembers class * {{ *** *; }}\n",
    # fail-closed unsupported syntax
    "-keepfuture class org.dyn4j.geometry.Vector2 { *; }\n",
    "-keep class { *; }\n",
    "-keep class org.dyn4j.geometry.Vector2 Broken { *; }\n",
    "-keepclassmembers class *\n",
    f"-if class {ACTIVITY}",
    f"-keep class {ACTIVITY} {{ <init>();",
    f"-keep class {ACTIVITY} {{ bogus int field; }}",
    "-keepattributes Signature { -keepclassmembers class * { *** *; } }\n",
    "-keepclassmembers class * { public void exact(); }\n",
    # multi-line forms
    "-keepclassmembers,allowoptimization\n public class\n *\n { *; }\n",
    "-keepclassmembers,allowoptimization\n  public @interface\n  org.dyn4j.** { *; }\n",
    "-keepclasseswithmembers\tclass\n  io.github.rubixhacker.dyn4k.**\n  { *; }\n",
    "-keepclassmembers,allowoptimization\n class *\n {\n   public *** *;\n }\n",
    "-keepclassmembers,allowoptimization\n class *\n {\n   private *** get*(...);\n }\n",
]

OPTIMIZED_MAPPING_MUTANTS = [
    ("mapping", MAPPING.replace("org.dyn4j.world.World -> R8$$REMOVED$$CLASS$$16:", "")),
    ("mapping", MAPPING.replace("OptimizedConsumer.run()", "OptimizedConsumer.missing()")),
    ("usage", ""),
    ("mapping", ""),
]


def optimized_vectors():
    cases = []
    for configuration in OPTIMIZED_CONFIGURATIONS:
        def call(configuration=configuration):
            return optimized_evidence.validate_r8(configuration, MAPPING, USAGE, set(DEX))
        cases.append({"configuration": configuration, "dex": DEX,
                      "mapping": MAPPING, "usage": USAGE, "result": outcome(call)})
    for field, value in OPTIMIZED_MAPPING_MUTANTS:
        arguments = {"mapping": MAPPING, "usage": USAGE}
        arguments[field] = value
        cases.append({
            "configuration": NARROW,
            "dex": DEX,
            "mapping": arguments["mapping"],
            "usage": arguments["usage"],
            "result": outcome(lambda a=arguments: optimized_evidence.validate_r8(
                NARROW, a["mapping"], a["usage"], set(DEX))),
        })
    empty_dex = {"configuration": NARROW, "dex": [], "mapping": MAPPING, "usage": USAGE}
    empty_dex["result"] = outcome(lambda: optimized_evidence.validate_r8(
        NARROW, MAPPING, USAGE, set()))
    cases.append(empty_dex)
    return cases


def optimized_provider_vectors():
    vectors = []
    for graph in (PROVIDER, PROVIDER + "org.dyn4j:dyn4j:6.0.0\n",
                  "io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1\n"):
        vectors.append({"graph": graph,
                        "result": outcome(lambda graph=graph: optimized_evidence.validate_provider(graph))})
    return vectors


def optimized_installed_vectors():
    vectors = []
    for raw, exit_code in ((OPTIMIZED_RAW, 0),
                           ("OK (0 tests)\nINSTRUMENTATION_CODE: -1\n", 0),
                           (OPTIMIZED_RAW, 1)):
        def call(raw=raw, exit_code=exit_code):
            return optimized_evidence.validate_installed_case(raw, exit_code, OPTIMIZED_CASE)
        vectors.append({"raw": raw, "exit": exit_code, "case": OPTIMIZED_CASE,
                        "result": outcome(call)})
    return vectors


# --------------------------------------------------------------------------- #
# full_evidence and run_full
# --------------------------------------------------------------------------- #

FULL_CASE = "dyn4k-core:org.dyn4j.CoreTest#works"
FULL_CONSUMER = "external-kotlin:io.github.rubixhacker.dyn4k.full.FullKotlinJourney#run"
FULL_RAW = "\n".join((
    "INSTRUMENTATION_STATUS: class=io.github.rubixhacker.dyn4k.full.FullJourneyTest",
    "INSTRUMENTATION_STATUS: test=allInstalledCases",
    "INSTRUMENTATION_STATUS: numtests=1",
    "INSTRUMENTATION_STATUS_CODE: 1",
    f"INSTRUMENTATION_STATUS: dyn4k_case={FULL_CASE}",
    "INSTRUMENTATION_STATUS: dyn4k_status=PASSED",
    "INSTRUMENTATION_STATUS_CODE: 0",
    f"INSTRUMENTATION_STATUS: dyn4k_case={FULL_CONSUMER}",
    "INSTRUMENTATION_STATUS: dyn4k_status=PASSED",
    "INSTRUMENTATION_STATUS_CODE: 0",
    "INSTRUMENTATION_STATUS: class=io.github.rubixhacker.dyn4k.full.FullJourneyTest",
    "INSTRUMENTATION_STATUS: test=allInstalledCases",
    "INSTRUMENTATION_STATUS: numtests=1",
    "INSTRUMENTATION_STATUS_CODE: 0",
    "INSTRUMENTATION_RESULT: stream=",
    "OK (1 test)",
    "INSTRUMENTATION_CODE: -1",
    "",
))

FULL_PACKAGE = "io.github.rubixhacker.dyn4k.full"
FULL_PROCESS_LOG = (
    f"I ActivityManager: Start proc 4804:{FULL_PACKAGE}/u0a241 for added application {FULL_PACKAGE}\n"
    f"I ActivityManager: Killing 4804:{FULL_PACKAGE}/u0a241 (adj 0): stop {FULL_PACKAGE} "
    "due to finished inst\n")

API21_LOG = (
    f"I/ActivityManager( 1485): Start proc {FULL_PACKAGE} for activity "
    f"{FULL_PACKAGE}/.FullActivity: pid=3334 uid=10058 gids={{50058}} abi=x86\n"
    f"I/ActivityManager( 1485): Killing 3334:{FULL_PACKAGE}/u0a58 (adj 0): stop {FULL_PACKAGE}\n"
    f"I/ActivityManager( 1485): Start proc {FULL_PACKAGE} for added application "
    f"{FULL_PACKAGE}: pid=3378 uid=10058 gids={{50058, 9997}} abi=x86\n"
    f"I/ActivityManager( 1485): Force stopping {FULL_PACKAGE} appid=10058 user=0: "
    "finished inst\n"
    f"I/ActivityManager( 1485): Killing 3378:{FULL_PACKAGE}/u0a58 (adj 0): stop {FULL_PACKAGE}\n")
API21_ADDED = (f"I/ActivityManager( 1485): Start proc {FULL_PACKAGE} for added application "
               f"{FULL_PACKAGE}: pid=3378 uid=10058 gids={{50058, 9997}} abi=x86\n")

FULL_R8_MAPPING = "org.dyn4j.geometry.Vector2 -> a:\norg.dyn4j.dynamics.Body -> b:\n"
FULL_R8_USAGE = "org.dyn4j.geometry.Unused\n"
FULL_R8_DEBUG = ["Lorg/dyn4j/geometry/Vector2;", "Lorg/dyn4j/dynamics/Body;", "Lc;"]
FULL_R8_RELEASE = ["La;", "Lb;"]
FULL_R8_RULES = ("-keep class io.github.rubixhacker.dyn4k.full.FullActivity { *; }\n"
                 "-keepclassmembers class org.dyn4j.geometry.Matrix22 "
                 "{ public double normMax(); }\n")
MATRIX_COVERAGE = "org.dyn4j.coverage.UpstreamMatrix22CoverageTest"


def full_installed_vectors():
    variants = [FULL_RAW]
    variants.append(FULL_RAW.replace(
        f"INSTRUMENTATION_STATUS: dyn4k_case={FULL_CASE}\n"
        "INSTRUMENTATION_STATUS: dyn4k_status=PASSED\n"
        "INSTRUMENTATION_STATUS_CODE: 0\n", ""))
    variants.append(FULL_RAW.replace(f"dyn4k_case={FULL_CASE}", "dyn4k_case=forged:Case#works"))
    variants.append(FULL_RAW.replace("dyn4k_status=PASSED", "dyn4k_status=SKIPPED", 1))
    variants.append(FULL_RAW.replace("dyn4k_status=PASSED", "dyn4k_status=FAILED", 1))
    variants.append(FULL_RAW.replace("OK (1 test)", "OK (2 tests)"))
    variants.append(FULL_RAW.replace("INSTRUMENTATION_CODE: -1", "INSTRUMENTATION_CODE: 0"))
    variants.append(FULL_RAW.replace(f"INSTRUMENTATION_STATUS: dyn4k_case={FULL_CONSUMER}",
                                     f"INSTRUMENTATION_STATUS: dyn4k_case={FULL_CASE}"))
    vectors = []
    for raw in variants:
        def call(raw=raw):
            return full_evidence.validate_full_installed(raw, {FULL_CASE, FULL_CONSUMER}, 0)
        vectors.append({"raw": raw, "result": outcome(call)})
    return vectors


def full_r8_vectors():
    rules = FULL_R8_RULES
    variants = [
        ("baseline", rules, FULL_R8_MAPPING, FULL_R8_USAGE, FULL_R8_DEBUG, FULL_R8_RELEASE,
         [], 2),
        ("broad keep", rules + "-keep class org.dyn4j.** { *; }\n", FULL_R8_MAPPING,
         FULL_R8_USAGE, FULL_R8_DEBUG, FULL_R8_RELEASE, [], 2),
        ("unchanged dex", rules, FULL_R8_MAPPING, FULL_R8_USAGE, FULL_R8_DEBUG, FULL_R8_DEBUG,
         [], 2),
        ("kept vector2", rules + "-keep class org.dyn4j.geometry.Vector2 { *; }\n",
         FULL_R8_MAPPING, FULL_R8_USAGE, FULL_R8_DEBUG, FULL_R8_RELEASE, [], 2),
        ("missing body mapping", rules,
         FULL_R8_MAPPING.replace("org.dyn4j.dynamics.Body -> b:\n", ""),
         FULL_R8_USAGE, FULL_R8_DEBUG, FULL_R8_RELEASE, [], 2),
        ("empty usage", rules, FULL_R8_MAPPING, "", FULL_R8_DEBUG, FULL_R8_RELEASE, [], 2),
        ("single release class", rules, FULL_R8_MAPPING, FULL_R8_USAGE, FULL_R8_DEBUG,
         ["La;"], [], 2),
        ("targeted matrix keep", rules.replace(
            "-keep class io.github.rubixhacker.dyn4k.full.FullActivity { *; }\n",
            f"-keep,allowoptimization class {MATRIX_COVERAGE} {{ *; }}\n"),
         FULL_R8_MAPPING, FULL_R8_USAGE, FULL_R8_DEBUG, FULL_R8_RELEASE, [MATRIX_COVERAGE], 2),
        ("missing matrix member keep",
         (f"-keep,allowoptimization class {MATRIX_COVERAGE} {{ *; }}\n"),
         FULL_R8_MAPPING, FULL_R8_USAGE, FULL_R8_DEBUG, FULL_R8_RELEASE, [MATRIX_COVERAGE], 2),
        ("wildcard matrix member keep",
         (f"-keep,allowoptimization class {MATRIX_COVERAGE} {{ *; }}\n"
          "-keepclassmembers class org.dyn4j.geometry.Matrix22 { public double norm*(); }\n"),
         FULL_R8_MAPPING, FULL_R8_USAGE, FULL_R8_DEBUG, FULL_R8_RELEASE, [MATRIX_COVERAGE], 2),
        ("duplicate matrix member keep",
         (f"-keep,allowoptimization class {MATRIX_COVERAGE} {{ *; }}\n"
          "-keepclassmembers class org.dyn4j.geometry.Matrix22 { public double normMax(); }\n"
          "-keepclassmembers class org.dyn4j.geometry.Matrix22 { public double normMax(); }\n"),
         FULL_R8_MAPPING, FULL_R8_USAGE, FULL_R8_DEBUG, FULL_R8_RELEASE, [MATRIX_COVERAGE], 2),
        ("wrong matrix member keep",
         (f"-keep,allowoptimization class {MATRIX_COVERAGE} {{ *; }}\n"
          "-keepclassmembers class org.dyn4j.geometry.Matrix22 "
          "{ public double normInfinity(); }\n"),
         FULL_R8_MAPPING, FULL_R8_USAGE, FULL_R8_DEBUG, FULL_R8_RELEASE, [MATRIX_COVERAGE], 2),
        ("too few transformed", rules, FULL_R8_MAPPING, FULL_R8_USAGE, FULL_R8_DEBUG,
         FULL_R8_RELEASE, [], 3),
        ("engine class kept outside entries",
         rules + "-keep class org.dyn4j.geometry.Vector2 { *; }\n", FULL_R8_MAPPING,
         FULL_R8_USAGE, FULL_R8_DEBUG, FULL_R8_RELEASE, [], 2),
    ]
    vectors = []
    for label, configuration, mapping, usage, debug, release, allowed, minimum in variants:
        def call(configuration=configuration, mapping=mapping, usage=usage, debug=debug,
                 release=release, allowed=allowed, minimum=minimum):
            return full_evidence.validate_full_r8(
                configuration, mapping, usage, set(debug), set(release),
                allowed_test_classes=frozenset(allowed), minimum_transformed=minimum)
        vectors.append({
            "label": label,
            "configuration": configuration,
            "mapping": mapping,
            "usage": usage,
            "debug_dex": debug,
            "release_dex": release,
            "allowed": allowed,
            "minimum": minimum,
            "result": outcome(call),
        })
    return vectors


def full_keep_scope_vectors():
    vectors = []
    configurations = [
        FULL_R8_RULES,
        FULL_R8_RULES + "-keep class org.dyn4j.** { *; }\n",
        "-keep class io.github.rubixhacker.dyn4k.full.FullJourneyTest { *; }\n",
        "-keep class io.github.rubixhacker.dyn4k.full.FullActivity { *; }\n",
        "-keep class io.github.rubixhacker.dyn4k.optimized.OptimizedActivity { *; }\n",
        "-keep class org.dyn4j.geometry.Vector2 { *; }\n",
        "-keepclassmembers class org.dyn4j.geometry.Matrix22 { public double normMax(); }\n",
        "-keepclassmembers class org.dyn4j.geometry.Matrix22 { public double normInfinity(); }\n",
        "-keepclassmembers class org.dyn4j.geometry.Matrix22 { *; }\n",
        "",
    ]
    for configuration in configurations:
        def call(configuration=configuration):
            return "ok"
        try:
            full_evidence.validate_full_keep_scope(configuration, frozenset({MATRIX_COVERAGE}))
            result = {"value": "ok"}
        except Exception as error:  # noqa: BLE001
            result = {"error": str(error), "type": type(error).__name__}
        vectors.append({"configuration": configuration, "allowed": [MATRIX_COVERAGE],
                        "result": result})
    return vectors


def process_log_vectors():
    vectors = []
    logs = [FULL_PROCESS_LOG,
            FULL_PROCESS_LOG.replace("4804:", "4805:", 1),
            FULL_PROCESS_LOG.replace("finished inst", "crash"),
            FULL_PROCESS_LOG.replace("Start proc", "Started proc"),
            FULL_PROCESS_LOG + FULL_PROCESS_LOG]
    for log in logs:
        vectors.append({"log": log, "package": FULL_PACKAGE,
                        "result": outcome(lambda log=log: full_evidence.validate_full_process_log(
                            log, FULL_PACKAGE))})
    return vectors


def api21_log_vectors():
    added = API21_ADDED
    service = (f"I/ActivityManager( 1485): Start proc {FULL_PACKAGE} for service "
               f"{FULL_PACKAGE}/.SyncService: pid=3379 uid=10058 gids={{50058}} "
               "abi=arm64-v8a\n")
    other_activity = (f"I/ActivityManager( 1485): Start proc {FULL_PACKAGE} for activity "
                       f"{FULL_PACKAGE}/.OtherActivity: pid=3379 uid=10058 gids={{50058}} "
                       "abi=arm64-v8a\n")
    external = (f"I/ActivityManager( 1485): Start proc {FULL_PACKAGE}.other for service "
                f"{FULL_PACKAGE}.other/.SyncService: pid=3379 uid=10059 gids={{50059}} "
                "abi=arm64-v8a\n")
    variants = {
        "baseline": API21_LOG,
        "external service": API21_LOG.replace(added, added + external),
        "wrong added pid": API21_LOG.replace("pid=3378", "pid=3379"),
        "crash instead of finished": API21_LOG.replace("finished inst", "crash"),
        "wrong finish appid": API21_LOG.replace("appid=10058 user=0: finished inst",
                                                "appid=10059 user=0: finished inst"),
        "wrong activity abi": API21_LOG.replace("abi=x86\n", "abi=arm64-v8a\n"),
        "wrong activity pid": API21_LOG.replace("pid=3334", "pid=3335"),
        "wrong killed pid": API21_LOG.replace(f"Killing 3334:{FULL_PACKAGE}&",
                                              f"Killing 3335:{FULL_PACKAGE}&")
        .replace(f"Killing 3334:{FULL_PACKAGE}/", f"Killing 3335:{FULL_PACKAGE}/"),
        "missing added start": API21_LOG.replace(added, ""),
        "duplicated added start": API21_LOG.replace(added, added + added),
        "wrong added abi": API21_LOG.replace(added, added.replace("abi=x86", "abi=arm64-v8a") + added),
        "wrong added pid plus duplicate": API21_LOG.replace(
            added, added.replace("pid=3378", "pid=3379") + added),
        "extra trailing kill": API21_LOG + (
            f"I/ActivityManager( 1485): Killing 9999:{FULL_PACKAGE}/u0a58 "
            f"(adj 0): crash {FULL_PACKAGE}\n"),
        "doubled log": API21_LOG + API21_LOG,
        "service start": API21_LOG.replace(added, added + service),
        "service start with matching identity": API21_LOG.replace(
            added, added + service.replace("pid=3379", "pid=3378").replace("abi=arm64-v8a", "abi=x86")),
        "other activity start": API21_LOG.replace(added, added + other_activity),
    }
    vectors = []
    for label, log in variants.items():
        vectors.append({"label": label, "log": log, "package": FULL_PACKAGE, "abi": "x86",
                        "before_pid": "3334",
                        "result": outcome(lambda log=log: run_full.validate_api21_process_log(
                            log, FULL_PACKAGE, "x86", "3334"))})
    vectors.append({"label": "non numeric pid", "log": API21_LOG, "package": FULL_PACKAGE,
                    "abi": "x86", "before_pid": "not-a-pid",
                    "result": outcome(lambda: run_full.validate_api21_process_log(
                        API21_LOG, FULL_PACKAGE, "x86", "not-a-pid"))})
    return vectors


def api21_process_vectors():
    package = FULL_PACKAGE
    header = "USER PID PPID VSIZE RSS WCHAN PC NAME\n"
    row = f"u0_a58 3334 123 540000 32000 ffffffff 00000000 {package}\n"
    unrelated = "u0_a59 1111 123 540000 32000 ffffffff 00000000 other.app\n"
    vectors = []
    for label, listing, required in (
            ("unrelated then app", header + unrelated + row, True),
            ("absent optional", header + unrelated, False),
            ("absent required", header + unrelated, True),
            ("duplicate rows", header + row + row, True),
            ("non numeric pid", header + row.replace("3334", "not-a-pid"), True),
            ("shell error", "/system/bin/sh: pidof: not found\n", True),
    ):
        vectors.append({"label": label, "listing": listing, "package": package,
                        "required": required,
                        "result": outcome(lambda listing=listing, required=required:
                                          run_full.api21_process_pid(listing, package, required))})
    return vectors


def runtime_vectors():
    vectors = []
    identities = [
        ({"ro.build.fingerprint": android_corpus.FINGERPRINTS["37"],
          "ro.build.version.sdk": "37", "ro.product.cpu.abi": "x86_64"}, "37", "x86_64", "1"),
        ({"ro.build.fingerprint": "forged", "ro.build.version.sdk": "37",
          "ro.product.cpu.abi": "x86_64"}, "37", "x86_64", "1"),
        ({"ro.build.fingerprint": android_corpus.FINGERPRINTS["37"],
          "ro.build.version.sdk": "37", "ro.product.cpu.abi": "x86_64"}, "36", "x86_64", "1"),
        ({"ro.build.fingerprint": android_corpus.FINGERPRINTS["37"],
          "ro.build.version.sdk": "37", "ro.product.cpu.abi": "x86_64"}, "37", "arm64-v8a", "1"),
        ({"ro.build.fingerprint": android_corpus.FINGERPRINTS["37"],
          "ro.build.version.sdk": "37", "ro.product.cpu.abi": "x86_64"}, "37", "x86_64", "0"),
        ({"ro.build.fingerprint": run_full.API21_FINGERPRINTS["x86_64"],
          "ro.build.version.sdk": "21", "ro.product.cpu.abi": "x86_64"}, "21", "x86_64", "1"),
        ({"ro.build.fingerprint": run_full.API21_FINGERPRINTS["x86"],
          "ro.build.version.sdk": "21", "ro.product.cpu.abi": "x86"}, "21", "x86", "1"),
        ({"ro.build.fingerprint": "forged", "ro.build.version.sdk": "21",
          "ro.product.cpu.abi": "x86_64"}, "21", "x86_64", "1"),
    ]
    for identity, api, abi, boot in identities:
        vectors.append({"identity": identity, "api": api, "abi": abi, "boot": boot,
                        "result": outcome(lambda identity=identity, api=api, abi=abi, boot=boot:
                                          run_full.validate_runtime(identity, api, abi, boot))})
    return vectors


def build_jdk_vectors():
    good = ("Starting process 'Gradle build daemon'. Working directory: "
            "/tmp/gradle/daemon/9.5.0 Command: /tmp/dyn4k-tools/jdk21/bin/java "
            "org.gradle.launcher.daemon.bootstrap.GradleDaemon 9.5.0\n"
            "DYN4K_BUILD_JDK javaHome=/tmp/dyn4k-tools/jdk21 javaVersion=21 "
            "gradleVersion=9.5.0\nBUILD SUCCESSFUL\n")
    variants = {
        "good": good,
        "good without marker": good.replace(
            "DYN4K_BUILD_JDK javaHome=/tmp/dyn4k-tools/jdk21 javaVersion=21 gradleVersion=9.5.0\n", ""),
        "wrong home": good.replace("/tmp/dyn4k-tools/jdk21", "/tmp/jdk25"),
        "wrong version": good.replace("javaVersion=21", "javaVersion=25"),
        "wrong gradle": good.replace("gradleVersion=9.5.0", "gradleVersion=9.4"),
        "missing marker": good.replace("DYN4K_BUILD_JDK", "MISSING_BUILD_JDK"),
        "no success": good.replace("BUILD SUCCESSFUL\n", ""),
        "duplicated marker": good + good.splitlines()[-2] + "\n",
        "wrong daemon class": good.replace("org.gradle.launcher.daemon.bootstrap.GradleDaemon",
                                           "org.example.Other"),
    }
    vectors = []
    for label, raw in variants.items():
        vectors.append({"label": label, "raw": raw, "result": outcome(
            lambda raw=raw: run_full.validate_build_jdk(raw))})
    vectors.append({"label": "marker optional", "raw": variants["good without marker"],
                    "result": outcome(lambda: run_full.validate_build_jdk(
                        variants["good without marker"], require_marker=False))})
    return vectors


def java_version_vectors():
    stderr = ("Picked up JAVA_TOOL_OPTIONS: -Djava.io.tmpdir=/home/task/tmp\n"
              'openjdk version "21.0.12.1" 2025-07-15 LTS\n')
    return [
        {"stderr": stderr, "result": outcome(lambda: build_identity_version(stderr))},
        {"stderr": 'openjdk version "25.0.1" 2026-01-01\n',
         "result": outcome(lambda: build_identity_version('openjdk version "25.0.1" 2026-01-01\n'))},
        {"stderr": "",
         "result": outcome(lambda: build_identity_version(""))},
        {"stderr": 'openjdk version "21.0.1"\nopenjdk version "21.0.2"\n',
         "result": outcome(lambda: build_identity_version(
             'openjdk version "21.0.1"\nopenjdk version "21.0.2"\n'))},
    ]


def build_identity_version(stderr):
    versions = re.findall(r'(?m)^openjdk version "21\.[^\r\n]*', stderr)
    if len(versions) != 1:
        raise ValueError("wrong pinned JDK version")
    return versions[0]


# --------------------------------------------------------------------------- #
# android_corpus
# --------------------------------------------------------------------------- #

CORPUS_MANIFESTS = [
    [
        {"id": "dyn4k-core:org.dyn4j.CoreTest#works", "module": "dyn4k-core",
         "classname": "org.dyn4j.CoreTest", "method": "works", "scope": "portable"},
        {"id": "dyn4k:io.github.FacadeTest#works", "module": "dyn4k",
         "classname": "io.github.FacadeTest", "method": "works", "scope": "portable"},
    ],
    [
        {"id": f"dyn4k-core:{MATRIX_COVERAGE}#norm", "module": "dyn4k-core",
         "classname": MATRIX_COVERAGE, "method": "norm", "scope": "portable"},
        {"id": "dyn4k-core:org.dyn4j.coverage.OtherTest#norm", "module": "dyn4k-core",
         "classname": "org.dyn4j.coverage.OtherTest", "method": "norm", "scope": "portable"},
        {"id": "dyn4k-core:org.dyn4j.CoreTest#jvmOnly", "module": "dyn4k-core",
         "classname": "org.dyn4j.CoreTest", "method": "jvmOnly", "scope": "jvm-only"},
    ],
    [
        {"id": "dyn4k:io.github.FacadeTest#works", "module": "dyn4k",
         "classname": "io.github.FacadeTest", "method": "works", "scope": "portable"},
        {"id": "dyn4k:io.github.FacadeTest#other", "module": "dyn4k",
         "classname": "io.github.FacadeTest", "method": "other", "scope": "portable"},
    ],
]


def corpus_vectors():
    vectors = []
    for cases in CORPUS_MANIFESTS:
        suite = {"cases": cases}
        inputs = android_corpus.full_app_inputs(suite)
        vectors.append({
            "cases": cases,
            "case_ids": [android_corpus.case_id(case) for case in cases],
            "portable": sorted({case["classname"] for case in cases
                                if case["scope"] == "portable"}),
            "case_asset": inputs["case_asset"].decode(),
            "keep_rules": inputs["keep_rules"].decode(),
        })
    return vectors


# --------------------------------------------------------------------------- #
# prepare.android_consumer_source and run.instrumentation_*
# --------------------------------------------------------------------------- #

def prepare_vectors():
    source = b'if ("1.8".equals(version)) return null;\n'
    vectors = [
        {"name": "CollisionModelConsumer", "source": source.decode(),
         "result": outcome(lambda: prepare.android_consumer_source(
             "CollisionModelConsumer", source).decode())},
        {"name": "GeometryConsumer", "source": source.decode(),
         "result": outcome(lambda: prepare.android_consumer_source("GeometryConsumer", source).decode())},
        {"name": "CollisionModelConsumer", "source": "class CollisionModelConsumer {}\n",
         "result": outcome(lambda: prepare.android_consumer_source(
             "CollisionModelConsumer", b"class CollisionModelConsumer {}\n").decode())},
        {"name": "CollisionModelConsumer", "source": (source + source).decode(),
         "result": outcome(lambda: prepare.android_consumer_source(
             "CollisionModelConsumer", source + source).decode())},
    ]
    return vectors


def filter_vectors():
    portable = [f"org.dyn4j.coverage.LongPortableCase{index:03d}Test" for index in range(171)]
    prepared = {"portable_classes": portable}
    vectors = []
    for flavor in ("candidate", "baseline"):
        for api in ("21", "37"):
            def call(flavor=flavor, api=api):
                directory = TEMP / f"filter-{flavor}-{api}"
                directory.mkdir(parents=True, exist_ok=True)
                classes, arguments, selection = run.instrumentation_filter(
                    prepared, flavor, "debug", api, directory)
                return {
                    "classes": list(classes),
                    "arguments": arguments,
                    "selection": None if selection is None else {
                        "path": normalise(str(selection)),
                        "size": selection.stat().st_size,
                        "lines": selection.read_text().splitlines(),
                    },
                }
            vectors.append({"flavor": flavor, "api": api, "prepared": prepared,
                            "result": outcome(call)})
    classes = {"candidate": list(run.instrumentation_classes(prepared, "candidate")),
               "baseline": list(run.instrumentation_classes(prepared, "baseline"))}
    return vectors, classes


def serial_vectors():
    vectors = []
    sdk = "/sdk"
    for serial in ("emulator-5558", "emulator-5562", "emulator-5560", "device-5562",
                   "emulator-5563", "emulator-5562 ", "emulator-5562;id", "",
                   "emulator-65562"):
        vectors.append({"serial": serial,
                        "result": outcome(lambda serial=serial:
                                          run.adb_for_serial(Path(sdk), serial))})
    return vectors


# --------------------------------------------------------------------------- #
# android-native-runtime receipt
# --------------------------------------------------------------------------- #

NATIVE_GRAPH = (
    "androidNativeX64CompileKlibraries - Compile classpath.\n"
    "+--- org.jetbrains.kotlin:kotlin-stdlib:2.4.20\n"
    "+--- io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1\n"
    "|    \\--- io.github.rubixhacker:dyn4k-core-androidnativex64:0.1.0-alpha.1\n"
    "\\--- io.github.rubixhacker:dyn4k:0.1.0-alpha.1\n"
    "     \\--- io.github.rubixhacker:dyn4k-androidnativex64:0.1.0-alpha.1\n\n")


def receipt_vectors():
    graphs = [NATIVE_GRAPH,
              NATIVE_GRAPH.replace("\n\n", "\n+--- org.dyn4j:dyn4j:6.0.0\n\n"),
              NATIVE_GRAPH.replace("\n\n", "\n+--- project :unapproved\n\n"),
              NATIVE_GRAPH.replace("\n\n", "\n+--- example:other:1.0\n\n"),
              NATIVE_GRAPH.replace("\n", "\n", 1).replace(
                  "+--- org.jetbrains.kotlin:kotlin-stdlib:2.4.20\n", ""),
              NATIVE_GRAPH.replace("androidNativeX64CompileKlibraries - Compile classpath.\n", ""),
              "unrecognized line\n"]
    vectors = []
    for graph in graphs:
        vectors.append({"graph": graph, "result": outcome(
            lambda graph=graph: receipt.validate_dependency_graph(graph))})
    return vectors


def elf_vectors():
    good = bytearray(64)
    good[:5] = b"\x7fELF\x02"
    good[5] = 1
    good[18:20] = (62).to_bytes(2, "little")
    truncated = bytes(good)[:19]
    wrong_machine = bytearray(good)
    wrong_machine[18:20] = (183).to_bytes(2, "little")
    not_elf = bytes(b"wrong ELF")
    little_endian_check = bytearray(good)
    little_endian_check[5] = 2
    vectors = []
    for label, raw in (("x86_64", bytes(good)), ("truncated", truncated),
                       ("other machine", bytes(wrong_machine)), ("not elf", not_elf),
                       ("big endian", bytes(little_endian_check))):
        path = TEMP / f"elf-{label.replace(' ', '-')}.kexe"
        path.write_bytes(raw)
        vectors.append({"label": label, "bytes": raw.hex(),
                        "result": outcome(lambda path=path: receipt.elf_abi(path))})
    return vectors


def parse_list_vectors():
    listing = b"p.AlphaTest.\n  first\n  second\np.BetaTest.\n  third\n"
    variants = {
        "baseline": listing,
        "forged tail": listing + b"FORGED PASS\n",
        "empty": b"",
        "indented first": b"  first\n",
        "suite without dot": b"p.AlphaTest\n  first\n",
        "method with dash": b"p.AlphaTest.\n  first-method\n",
        "trailing spaces in suite": b"p.AlphaTest. \n  first\n",
    }
    vectors = []
    for label, raw in variants.items():
        vectors.append({"label": label, "raw": raw.decode(),
                        "result": outcome(lambda raw=raw: native_full.parse_list(raw))})
    transcript = ("[==========] Running 3 tests from 2 test cases.\n"
                  "[ RUN      ] p.AlphaTest.first\n"
                  "[       OK ] p.AlphaTest.first (0 ms)\n"
                  "[ RUN      ] p.AlphaTest.second\n"
                  "[       OK ] p.AlphaTest.second (1 ms)\n"
                  "[ RUN      ] p.BetaTest.third\n"
                  "[       OK ] p.BetaTest.third (0 ms)\n"
                  "[==========] 3 tests from 2 test cases ran. (1 ms total)\n"
                  "[  PASSED  ] 3 tests.\n").encode()
    mutants = {
        "baseline": transcript,
        "missing pair": transcript.replace(
            b"[ RUN      ] p.BetaTest.third\n[       OK ] p.BetaTest.third (0 ms)\n", b""),
        "renamed run": transcript.replace(b"[ RUN      ] p.BetaTest.third",
                                          b"[ RUN      ] p.AlphaTest.first"),
        "duplicate summary": transcript + b"[  PASSED  ] 3 tests.\n",
        "failed line": transcript.replace(b"[       OK ] p.BetaTest.third",
                                          b"[  FAILED  ] p.BetaTest.third"),
        "skipped line": transcript.replace(b"[       OK ] p.BetaTest.third",
                                           b"[  SKIPPED ] p.BetaTest.third"),
        "wrong summary count": transcript.replace(b"[  PASSED  ] 3 tests.",
                                                  b"[  PASSED  ] 2 tests."),
        "empty": b"",
    }
    for label, raw in mutants.items():
        vectors.append({"label": label, "raw": raw.decode(),
                        "result": outcome(lambda raw=raw: native_full.parse_test_run(raw))})
    return vectors


def device_listing_vectors():
    good = (b"List of devices attached\n"
            b"emulator-5558\tdevice product:sdk model:task transport_id:1\n"
            b"emulator-5560\tdevice product:sdk model:other transport_id:2\n"
            b"emulator-5562\toffline\n\n")
    variants = {
        "baseline": good,
        "absent": b"List of devices attached\nemulator-5560\tdevice\n",
        "offline": b"List of devices attached\nemulator-5558\toffline\n",
        "unauthorized": b"List of devices attached\nemulator-5558\tunauthorized\n",
        "duplicate": good + b"emulator-5558\tdevice transport_id:3\n",
        "missing state": b"List of devices attached\nemulator-5558\n",
        "malformed metadata": b"List of devices attached\nemulator-5558\tdevice extra\n",
        "wrong header": b"Devices\nemulator-5558\tdevice\n",
        "empty": b"",
    }
    vectors = []
    for label, raw in variants.items():
        vectors.append({"label": label, "raw": raw.decode(),
                        "result": outcome(lambda raw=raw: native_full.require_task_device(raw))})
    return vectors


def native_result_vectors():
    vectors = []
    expected = {"avd_name": "dyn4k_api37_play_x64", "api": "37",
                "fingerprint": native_full.EXPECTED_FINGERPRINT, "primary_abi": "x86_64",
                "abi_list": "x86_64,armeabi-v7a", "boot_completed": "1"}
    changes = {
        "baseline": {},
        "wrong avd": {"avd_name": "other"},
        "wrong api": {"api": "36"},
        "wrong fingerprint": {"fingerprint": "other/image"},
        "wrong primary abi": {"primary_abi": "arm64-v8a"},
        "abi list without x86_64": {"abi_list": "armeabi-v7a,arm64-v8a"},
        "not booted": {"boot_completed": "0"},
    }
    for label, change in changes.items():
        observed = {**expected, **change}
        observations = {prop: {"stdout": (observed[field] + "\n").encode()}
                        for prop, field in native_full.GUEST_PROPERTIES.items()}
        vectors.append({"label": label, "observations": {
            prop: record["stdout"].decode() for prop, record in observations.items()},
            "result": outcome(lambda observations=observations: native_full.guest_values(
                {"observations": observations}))})
    return vectors


def deployment_vectors():
    vectors = []
    for label, push, push_err, chmod_err, remote_out, remote_err, expected in (
            ("push report on stderr", "", "1 file pushed\n", "", "abc  /data/local/tmp/test\n", "", "abc"),
            ("wrong hash", "", "1 file pushed\n", "", "def  /data/local/tmp/test\n", "", "abc"),
            ("failed push", "", "1 file pushed\nfailed\n", "", "abc  /data/local/tmp/test\n", "", "abc"),
            ("chmod stderr", "", "1 file pushed\n", "denied\n", "abc  x\n", "", "abc"),
            ("remote stderr", "", "1 file pushed\n", "", "abc  x\n", "denied\n", "abc"),
    ):
        vectors.append({"label": label, "push": push, "push_err": push_err,
                        "chmod_err": chmod_err, "remote_out": remote_out,
                        "remote_err": remote_err, "expected": expected,
                        "result": outcome(lambda push=push, push_err=push_err,
                                          chmod_err=chmod_err, remote_out=remote_out,
                                          remote_err=remote_err, expected=expected:
                                          native_full.validate_deployment_output(
                                              push.encode(), push_err.encode(), chmod_err.encode(),
                                              remote_out.encode(), remote_err.encode(), expected))})
    return vectors


def native_graph_section_vectors():
    vectors = []
    root_graph = ("androidNativeX64TestCompileKlibraries - Compile classpath.\n"
                  "+--- org.jetbrains.kotlin:kotlin-stdlib:2.4.20\n"
                  "\\--- junit:junit:4.13.2\n\n")
    for module in ("core", "facade"):
        vectors.append({"module": module, "raw": root_graph,
                        "result": outcome(lambda module=module: native_full.graph_section(
                            root_graph.encode(), module))})
    for module in ("core", "facade", "consumer"):
        vectors.append({"module": module, "raw": NATIVE_GRAPH,
                        "result": outcome(lambda module=module: native_full.graph_section(
                            NATIVE_GRAPH.encode(), module))})
    bad = {
        "unapproved provider": NATIVE_GRAPH.replace("\n\n", "\n+--- org.dyn4j:dyn4j:6.0.0\n\n"),
        "project provider": NATIVE_GRAPH.replace("\n\n", "\n+--- project :unapproved\n\n"),
        "unknown provider": NATIVE_GRAPH.replace("\n\n", "\n+--- example:other:1.0\n\n"),
        "missing header": NATIVE_GRAPH.replace(
            "androidNativeX64CompileKlibraries - Compile classpath.\n", ""),
        "duplicate header": NATIVE_GRAPH + NATIVE_GRAPH,
    }
    for label, raw in bad.items():
        vectors.append({"module": "consumer", "raw": raw, "label": label,
                        "result": outcome(lambda raw=raw: native_full.graph_section(
                            raw.encode(), "consumer"))})
    facade_bad = NATIVE_GRAPH.replace("\n\n", "\n+--- org.dyn4j:dyn4j:6.0.0\n\n")
    vectors.append({"module": "facade", "raw": facade_bad, "label": "facade provider",
                    "result": outcome(lambda: native_full.graph_section(facade_bad.encode(),
                                                                        "facade"))})
    return vectors


def native_full_vectors():
    return {
        "build_task_marker": [
            {"task": ":dyn4k-core:linkDebugTestAndroidNativeX64",
             "value": native_full.build_task_marker(":dyn4k-core:linkDebugTestAndroidNativeX64")},
            {"task": "linkReleaseExecutableAndroidNativeX64",
             "value": native_full.build_task_marker("linkReleaseExecutableAndroidNativeX64")},
        ],
        "commands": {
            "build": {name: list(argv) for name, argv in
                      native_full.build_commands(Path("/repo")).items()},
            "graph": {name: list(argv) for name, argv in
                      native_full.graph_commands(Path("/repo")).items()},
        },
        "executables": {f"{module}-{variant}": normalise(str(native_full.executable_path(
            Path("/repo"), module, variant))) for module, variant in native_full.LANES},
        "klibs": {module: normalise(str(path)) for module, path in
                  native_full.klib_paths(Path("/repo")).items()},
        "guest_remote": {f"{module}-{variant}": native_full.GUEST_REMOTE.format(
            module=module, variant=variant) for module, variant in native_full.LANES},
        "lanes": [list(lane) for lane in native_full.LANES],
        "stage_tasks": list(native_full.STAGE_TASKS),
        "test_tasks": list(native_full.TEST_TASKS),
        "consumer_tasks": list(native_full.CONSUMER_TASKS),
        "root_gradle": list(native_full.ROOT_GRADLE),
        "assertions": list(native_full.ASSERTIONS),
        "guest_properties": dict(native_full.GUEST_PROPERTIES),
        "expected_cases": {
            "core": sorted(native_full.expected_cases(
                {"cases": [
                    {"classname": "org.dyn4j.CoreTest", "method": "works",
                     "module": "dyn4k-core", "source_set": "commonTest"},
                    {"classname": "org.dyn4j.CoreTest", "method": "jvmOnly",
                     "module": "dyn4k-core", "source_set": "jvmTest"},
                ]}, "core")),
            "facade": sorted(native_full.expected_cases(
                {"cases": [
                    {"classname": "io.github.FacadeTest", "method": "works",
                     "module": "dyn4k", "source_set": "commonTest"},
                    {"classname": "io.github.Core", "method": "works",
                     "module": "dyn4k-core", "source_set": "commonTest"},
                ]}, "facade")),
            "consumer-core": sorted(native_full.expected_cases(
                {"cases": [
                    {"classname": "io.github.FacadeTest", "method": "works",
                     "module": "dyn4k", "source_set": "commonTest"},
                ]}, "core")),
        },
        "check_cases": [
            {"observed": ["a", "b"], "expected": ["a", "b"],
             "result": outcome(lambda: native_full.check_cases(["a", "b"], {"a", "b"}))},
            {"observed": ["a"], "expected": ["a", "b"],
             "result": outcome(lambda: native_full.check_cases(["a"], {"a", "b"}))},
            {"observed": ["a", "b", "a"], "expected": ["a", "b"],
             "result": outcome(lambda: native_full.check_cases(["a", "b", "a"], {"a", "b"}))},
            {"observed": [], "expected": ["a"],
             "result": outcome(lambda: native_full.check_cases([], {"a"}))},
        ],
    }


# --------------------------------------------------------------------------- #
# full keep rules and the provider graph
# --------------------------------------------------------------------------- #

def provider_artifacts_vectors():
    root = TEMP / "provider"
    root.mkdir(parents=True, exist_ok=True)
    providers = {}
    staged = {}
    for name in ("dyn4k-core-android", "dyn4k-android"):
        path = root / f"{name}.aar"
        path.write_bytes(name.encode())
        staged[name] = {"sha256": run_full.sha256(path)}
        providers[f"io.github.rubixhacker:{name}:0.1.0-alpha.1"] = str(path)
    rows = ["DYN4K_BUILD_JDK javaHome=/tmp/dyn4k-tools/jdk21 javaVersion=21 gradleVersion=9.5.0"]
    for variant in ("debug", "release"):
        rows.append(f"DYN4K_GRAPH_BEGIN {variant}")
        rows.extend(f"DYN4K_GRAPH_COMPONENT {variant} {name}"
                    for name in sorted(run_full.GRAPH_COMPONENTS))
        rows.extend(f"DYN4K_GRAPH_EDGE {variant} {edge}" for edge in sorted(run_full.GRAPH_EDGES))
        rows.extend(f"DYN4K_GRAPH_ARTIFACT {variant} {coordinate} "
                    f"{providers.get(coordinate, '/unused.jar')}"
                    for coordinate in sorted(run_full.GRAPH_ARTIFACTS))
        rows.append(f"DYN4K_GRAPH_END {variant} 11 15 9")
    graph = "\n".join(rows) + "\n"
    prepared = {"staged": staged}
    variants = {
        "baseline": graph,
        "wrong coordinate": graph.replace(
            "io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1",
            "example.invalid:dyn4k-android:9.9.9"),
        "missing component": graph.replace("DYN4K_GRAPH_COMPONENT debug project:full\n", ""),
        "missing edge": graph.replace(
            "DYN4K_GRAPH_EDGE release project:full junit:junit:4.13.2\n", ""),
        "missing begin": graph.replace("DYN4K_GRAPH_BEGIN release\n", ""),
        "second baseline": graph + "DYN4K_GRAPH_ARTIFACT debug org.dyn4j:dyn4j:6.0.0 /unused.jar\n",
    }
    vectors = []
    for label, raw in variants.items():
        vectors.append({"label": label, "graph": normalise(raw), "staged": staged,
                        "result": normalise_value(outcome(
                            lambda raw=raw: run_full.validate_provider_artifacts(raw, prepared)))})
    aar = root / "dyn4k-core-android.aar"
    aar.write_bytes(b"wrong")
    vectors.append({"label": "changed staged AAR", "graph": normalise(graph), "staged": staged,
                    "overrides": {"dyn4k-core-android": "wrong"},
                    "result": normalise_value(outcome(
                        lambda: run_full.validate_provider_artifacts(graph, prepared)))})
    return {
        "graph": normalise(graph),
        "staged": staged,
        "providers": {coordinate: normalise(path) for coordinate, path in providers.items()},
        "files": {name: name for name in staged},
        "components": sorted(run_full.GRAPH_COMPONENTS),
        "edges": sorted(run_full.GRAPH_EDGES),
        "artifacts": sorted(run_full.GRAPH_ARTIFACTS),
        "vectors": vectors,
    }


def pyjson_vectors():
    values = [
        {"a": 1, "b": [1, 2, 3], "c": {"nested": None, "flag": True}},
        {"paths": {"dyn4k-core": "/tmp/x/a.klib"}, "counts": {"a": 0}},
        {"text": "quote \" and backslash \\ and tab \t and \u00e9 and \u00a7"},
        {"empty_list": [], "empty_object": {}},
        {"unicode": "\u00e9\u4e2d\u6587", "control": "\u0001\u007f"},
    ]
    return [
        {"input": json.dumps(value),
         "pretty": json.dumps(value, indent=2, sort_keys=True) + "\n",
         "compact": json.dumps(value)}
        for value in values
    ]


def main():
    filters, filter_classes = filter_vectors()
    document = {
        "git_revision": revision(),
        "python": sys.version.split()[0],
        "instrumentation": {
            "parse": parse_vectors(),
            "lane": lane_vectors(),
        },
        "optimized": {
            "case": OPTIMIZED_CASE,
            "raw": OPTIMIZED_RAW,
            "mapping": MAPPING,
            "usage": USAGE,
            "provider": provider_vectors_optimized(),
            "r8": optimized_vectors(),
            "installed": optimized_installed_vectors(),
        },
        "full": {
            "case": FULL_CASE,
            "consumer": FULL_CONSUMER,
            "raw": FULL_RAW,
            "installed": full_installed_vectors(),
            "r8": full_r8_vectors(),
            "keep_scope": full_keep_scope_vectors(),
            "process_log": process_log_vectors(),
            "api21_log": api21_log_vectors(),
            "api21_process": api21_process_vectors(),
            "runtime": runtime_vectors(),
            "provider_artifacts": provider_artifacts_vectors(),
        },
        "build_identity": {
            "build_jdk": build_jdk_vectors(),
            "java_version": java_version_vectors(),
        },
        "corpus": {
            "manifests": corpus_vectors(),
            "reflective_filter_types": list(android_corpus.REFLECTIVE_FILTER_TYPES),
            "java_journeys": list(android_corpus.JAVA_JOURNEYS),
            "kotlin_journey": android_corpus.KOTLIN_JOURNEY,
            "x86_dexopt_method": android_corpus.X86_DEXOPT_METHOD,
            "fingerprints": android_corpus.FINGERPRINTS,
            "api21_fingerprints": run_full.API21_FINGERPRINTS,
            "consumer_cases": sorted(run.CONSUMER_CASES),
            "consumers": list(prepare.CONSUMERS),
            "version": prepare.VERSION,
        },
        "pyjson": pyjson_vectors(),
        "prepare": {
            "android_consumer_source": prepare_vectors(),
        },
        "run": {
            "filter": filters,
            "classes": filter_classes,
            "serial": serial_vectors(),
        },
        "native": {
            "receipt": receipt_vectors(),
            "elf": elf_vectors(),
            "list": parse_list_vectors(),
            "device_listing": device_listing_vectors(),
            "guest_values": native_result_vectors(),
            "deployment": deployment_vectors(),
            "graph_section": native_graph_section_vectors(),
            "full": native_full_vectors(),
            "fingerprint": native_full.EXPECTED_FINGERPRINT,
            "trusted_adb": str(receipt.TRUSTED_ADB),
            "trusted_adb_sha256": native_full.TRUSTED_ADB_SHA256,
            "allowed_components": sorted(receipt.ALLOWED_COMPONENTS),
        },
    }
    print(json.dumps(document, indent=1, sort_keys=True))


def provider_vectors_optimized():
    vectors = []
    for graph in (PROVIDER, PROVIDER + "org.dyn4j:dyn4j:6.0.0\n",
                  "io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1\n"):
        vectors.append({"graph": graph,
                        "result": outcome(lambda graph=graph: optimized_evidence.validate_provider(graph))})
    return vectors


if __name__ == "__main__":
    main()
