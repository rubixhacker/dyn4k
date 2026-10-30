#!/usr/bin/env python3
"""Regenerate `HostedSafariVectors.kt` for the hosted and Safari-reporter ports.

Provenance
----------
Every input and every expected value written here is produced by the Python reference,
`tools/qualification/hosted.py` and `tools/qualification/safari_reporter.py`, at the git revision
recorded in the emitted file (see `REVISION`). Nothing was computed by the Kotlin port and copied
back.

The stage and `committed_bytes` vectors are produced against throw-away Git repositories created
below with fixed content, so the outcomes (statuses, project verdicts, forensic paths and retained
bytes) are the reference's own. Commit identifiers are deliberately not recorded: the Kotlin
suite builds an identical fixture and asserts the same outcome shape.

Output
------
`src/jvmTest/kotlin/io/github/rubixhacker/harness/qualification/HostedSafariVectors.kt` in the
`tools/harness/qualification` module. Run from anywhere:

    python3 tools/harness/qualification/parity/generate_hosted_safari_vectors.py
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools" / "qualification"))

import hosted  # noqa: E402
import qualify  # noqa: E402
import safari_reporter  # noqa: E402

TARGET = (
    ROOT / "tools" / "harness" / "qualification" / "src" / "jvmTest" / "kotlin" / "io" / "github"
    / "rubixhacker" / "harness" / "qualification" / "HostedSafariVectors.kt"
)


def revision():
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()


def kotlin(text):
    """A Kotlin string literal holding exactly `text`."""
    encoded = json.dumps(text, ensure_ascii=True)
    return '"' + encoded[1:-1].replace("\\/", "/").replace("$", "\\$").replace("\\'", "'") + '"'


def kotlin_list(items):
    if not items:
        return "emptyList()"
    return "listOf(" + ", ".join(items) + ")"


def kompact(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=False)


# --------------------------------------------------------------------------------------
# hosted.runtime_status
# --------------------------------------------------------------------------------------

DARWIN = {
    "system": "Darwin", "machine": "arm64", "os_version": "26.6.2",
    "xcode_version": "26.5", "xcode_build": "Build version 17F42",
    "simulators": {"iOS": [{"name": "iPhone 17"}]},
}

RUNTIME_OBSERVATIONS = [
    ("macos ready", "macosArm64", DARWIN),
    ("macos without simulators", "macosArm64", {**DARWIN, "simulators": {}}),
    ("macos 25 runner", "macosArm64", {**DARWIN, "os_version": "25.1"}),
    ("macos numeric os version", "macosArm64", {**DARWIN, "os_version": 26.5}),
    ("macos integer os version", "macosArm64", {**DARWIN, "os_version": 26}),
    ("macos xcode 26.4.1", "macosArm64", {**DARWIN, "xcode_version": "26.4.1"}),
    ("macos xcode 26.6", "macosArm64", {**DARWIN, "xcode_version": "26.6"}),
    ("macos x86 machine", "macosArm64", {**DARWIN, "machine": "x86_64"}),
    ("macos upper machine", "macosArm64", {**DARWIN, "machine": "ARM64"}),
    ("macos linux system", "macosArm64", {**DARWIN, "system": "Linux"}),
    ("macos build absent", "macosArm64",
     {key: value for key, value in DARWIN.items() if key != "xcode_build"}),
    ("macos build empty", "macosArm64", {**DARWIN, "xcode_build": ""}),
    ("macos build blank", "macosArm64", {**DARWIN, "xcode_build": "Build version "}),
    ("macos build padded", "macosArm64", {**DARWIN, "xcode_build": "Build version    "}),
    ("macos build split", "macosArm64", {**DARWIN, "xcode_build": "Build version 17 F42"}),
    ("macos build suffixed", "macosArm64", {**DARWIN, "xcode_build": "Build version 17F42!"}),
    ("macos build only id", "macosArm64", {**DARWIN, "xcode_build": "17F42"}),
    ("macos build numeric", "macosArm64", {**DARWIN, "xcode_build": 17}),
    ("ios simulator ready", "iosSimulatorArm64", DARWIN),
    ("ios simulator second build", "iosSimulatorArm64",
     {**DARWIN, "xcode_build": "Build version 18A1"}),
    ("ios simulator absent", "iosSimulatorArm64", {**DARWIN, "simulators": {}}),
    ("ios simulator empty family", "iosSimulatorArm64", {**DARWIN, "simulators": {"iOS": []}}),
    ("tvos simulator absent", "tvosSimulatorArm64", {**DARWIN, "simulators": {"iOS": [{}]}}),
    ("watchos simulator ready", "watchosSimulatorArm64",
     {**DARWIN, "simulators": {"watchOS": [{"name": "Watch"}]}}),
    ("ios x64 machine mismatch", "iosX64", DARWIN),
    ("ios x64 ready", "iosX64", {**DARWIN, "machine": "x86_64"}),
    ("mingw old build", "mingwX64",
     {"system": "Windows", "machine": "AMD64", "os_version": "10.0.19045"}),
    ("mingw server 2025", "mingwX64",
     {"system": "Windows", "machine": "AMD64", "os_version": "10.0.26100.1742"}),
    ("mingw lower machine", "mingwX64",
     {"system": "Windows", "machine": "amd64", "os_version": "10.0.26100"}),
    ("safari ready", "jsSafari",
     {**DARWIN, "simulators": {}, "safari_version": "26.6.2",
      "safaridriver_version": "SafariDriver 26.6.2 (WebKit)"}),
    ("safari driver differs", "jsSafari",
     {**DARWIN, "simulators": {}, "safari_version": "26.6.2",
      "safaridriver_version": "SafariDriver 26.6.1"}),
    ("safari absent", "jsSafari", {**DARWIN, "simulators": {}}),
    ("safari empty driver", "jsSafari",
     {**DARWIN, "simulators": {}, "safari_version": "26.6.2", "safaridriver_version": ""}),
    ("unknown target", "jvm", DARWIN),
    ("observed string", "macosArm64", "Darwin"),
    ("observed list", "macosArm64", []),
]


def runtime_vectors():
    cases = []
    for label, target, observed in RUNTIME_OBSERVATIONS:
        status, reason = hosted.runtime_status(target, observed)
        cases.append(
            "RuntimeCase(%s, %s, %s, %s)" % (
                kotlin(label), kotlin(target), kotlin(kompact(observed)),
                kotlin(status) + ", " + kotlin(reason)))
    return cases


# --------------------------------------------------------------------------------------
# hosted.hosted_status
# --------------------------------------------------------------------------------------

def hosted_vectors():
    manifest = qualify.load_json_strict(ROOT / "tools" / "qualification" / "foundation-probes.json")
    groups = {group["id"]: group for group in manifest["groups"]}
    sha = "a" * 40
    source_ids = ("core-macosArm64", "macosArm64")
    source_groups = []
    for group_id in source_ids:
        count = len(qualify.expected_probe_cases(manifest, groups[group_id]))
        source_groups.append({"id": group_id, "expected": count, "executed": count,
                              "reported": count, "failures": 0, "errors": 0, "skipped": 0})
    consumer_count = len(qualify.expected_probe_cases(manifest, groups["consumer-macosArm64"]))
    source_total = sum(item["expected"] for item in source_groups)
    good = {"candidate_sha": sha, "status": "PROBE_PASSED", "expected": source_total,
            "executed": source_total, "reported": source_total, "failures": 0, "errors": 0,
            "skipped": 0, "exit_code": 0, "groups": source_groups}
    consumer = {**good, "expected": consumer_count, "executed": consumer_count,
                "reported": consumer_count,
                "groups": [{"id": "consumer-macosArm64", "expected": consumer_count,
                            "executed": consumer_count, "reported": consumer_count,
                            "failures": 0, "errors": 0, "skipped": 0}]}
    hashes = {"dyn4k-core": "b" * 64, "dyn4k": "c" * 64}
    safari_consumer_count = len(qualify.expected_probe_cases(
        manifest, groups["consumer-jsSafari"]))
    safari_consumer = {**consumer, "expected": safari_consumer_count,
                       "executed": safari_consumer_count,
                       "reported": safari_consumer_count,
                       "groups": [{"id": "consumer-jsSafari", "expected": safari_consumer_count,
                                   "executed": safari_consumer_count,
                                   "reported": safari_consumer_count,
                                   "failures": 0, "errors": 0, "skipped": 0}]}
    cases = [
        ("ready", "macosArm64", good, consumer, hashes, DARWIN),
        ("stale source", "macosArm64", {**good, "candidate_sha": "d" * 40}, consumer, hashes,
         DARWIN),
        ("missing source", "macosArm64", None, consumer, hashes, DARWIN),
        ("partial source", "macosArm64", {**good, "executed": source_total - 1}, consumer, hashes,
         DARWIN),
        ("failed consumer", "macosArm64", good, {**consumer, "status": "PROBE_FAILED"}, hashes,
         DARWIN),
        ("missing consumer", "macosArm64", good, None, hashes, DARWIN),
        ("absent hashes", "macosArm64", good, consumer, None, DARWIN),
        ("one hash", "macosArm64", good, consumer, {"dyn4k-core": "b" * 64}, DARWIN),
        ("short hash", "macosArm64", good, consumer,
         {"dyn4k-core": "b" * 63, "dyn4k": "c" * 64}, DARWIN),
        ("safari ready", "jsSafari", None, safari_consumer, hashes,
         {**DARWIN, "simulators": {}, "safari_version": "26.6.2",
          "safaridriver_version": "SafariDriver 26.6.2"}),
        ("runtime failed", "macosArm64", good, consumer, hashes,
         {**DARWIN, "xcode_version": "26.4.1"}),
        ("reported float", "macosArm64", good,
         {**consumer, "reported": float(consumer_count)}, hashes, DARWIN),
        ("reported missing", "macosArm64", good,
         {key: value for key, value in consumer.items() if key != "reported"}, hashes, DARWIN),
        ("failure counted", "macosArm64", good, {**consumer, "failures": 1}, hashes, DARWIN),
        ("exit not zero", "macosArm64", good, {**consumer, "exit_code": 1}, hashes, DARWIN),
        ("accounting differs", "macosArm64", good,
         {**consumer, "groups": [{"id": "consumer-macosArm64", "expected": consumer_count,
                                  "executed": consumer_count, "reported": consumer_count,
                                  "failures": 0, "errors": 0, "skipped": 0},
                                 {"id": "macosArm64", "expected": 45, "executed": 45,
                                  "reported": 45, "failures": 0, "errors": 0, "skipped": 0}]},
         hashes, DARWIN),
    ]
    rendered = []
    for label, target, source, staged, artifact_hashes, runtime in cases:
        status, reason = hosted.hosted_status(target, sha, runtime, source, staged,
                                              artifact_hashes, manifest)
        rendered.append(
            "HostedCase(%s, %s, %s, %s, %s, %s, %s, %s)" % (
                kotlin(label), kotlin(target),
                "null" if source is None else kotlin(kompact(source)),
                "null" if staged is None else kotlin(kompact(staged)),
                "null" if artifact_hashes is None else kotlin(kompact(artifact_hashes)),
                kotlin(kompact(runtime)), kotlin(status), kotlin(reason)))
    return rendered


def group_vectors():
    manifest = qualify.load_json_strict(ROOT / "tools" / "qualification" / "foundation-probes.json")
    rendered = []
    for label, ids in (
        ("native source groups", ("core-macosArm64", "macosArm64")),
        ("native consumer group", ("consumer-macosArm64",)),
        ("safari consumer group", ("consumer-jsSafari",)),
    ):
        selected, patterns = hosted.selected_groups(manifest, ids)
        rendered.append(
            "GroupCase(%s, %s, %s, %s, %s, %s)" % (
                kotlin(label), kotlin_list([kotlin(item) for item in ids]),
                kotlin(kompact(list(selected.keys()))),
                kotlin(kompact(selected["groups"])),
                kotlin_list([kotlin(pattern) for pattern in patterns]),
                kotlin("")))
    for label, ids in (
        ("missing group", ("consumer-doesNotExist",)),
        ("one missing group", ("macosArm64", "consumer-doesNotExist")),
    ):
        try:
            hosted.selected_groups(manifest, ids)
            message = ""
        except ValueError as error:
            message = str(error)
        rendered.append(
            "GroupCase(%s, %s, %s, %s, %s, %s)" % (
                kotlin(label), kotlin_list([kotlin(item) for item in ids]),
                kotlin("[]"), kotlin("[]"), kotlin_list([]), kotlin(message)))
    return rendered


def wrapper_vectors():
    cases = [
        ("posix", "/work/dyn4k", False),
        ("posix trailing", "/work/dyn4k/", False),
        ("posix root", "/", False),
        ("nt", "C:\\work\\dyn4k", True),
        ("nt trailing", "C:\\work\\dyn4k\\", True),
        ("empty", "", False),
    ]
    return [
        "WrapperCase(%s, %s, %s, %s)" % (
            kotlin(label), kotlin(path), "true" if windows else "false",
            kotlin(_wrapper(path, windows)))
        for label, path, windows in cases
    ]


def _wrapper(path, windows):
    """`hosted.gradle_wrapper`: `str(repository / name)` for the target path flavour."""
    if windows:
        import ntpath
        return ntpath.normpath(ntpath.join(path, "gradlew.bat")) if path else "gradlew.bat"
    import posixpath
    return posixpath.normpath(posixpath.join(path, "gradlew")) if path else "gradlew"


# --------------------------------------------------------------------------------------
# safari_reporter.validate_config
# --------------------------------------------------------------------------------------

def generated_config(fragment, repository, project, mode, settings=None):
    package = safari_reporter.PACKAGES[project]
    build_root = (repository / project if project == Path("consumers/qualification/portable")
                  else repository)
    package_root = build_root / "build/js/packages" / package
    runner = str(build_root / "build/js/node_modules/kotlin-web-helpers/dist"
                 / "kotlin-test-karma-runner.js")
    selected = str((package_root / "kotlin" / f"{package}.js") if mode == "development"
                   else (repository / project / "build/compileSync/js/test"
                         / "testProductionExecutable/kotlin" / f"{package}.js"))
    if settings is None:
        settings = {
            "singleRun": True, "autoWatch": False,
            "basePath": str(package_root), "files": [runner, selected],
            "frameworks": ["webpack-output", "mocha", "webpack"],
            "client": {"args": []}, "browsers": ["Safari"],
            "customLaunchers": {}, "failOnFailingTestSuite": False,
            "failOnEmptyTestSuite": False,
            "reporters": ["karma-kotlin-reporter"],
            "preprocessors": {runner: ["webpack", "sourcemap"],
                              selected: ["webpack", "sourcemap"]},
            "proxies": {}, "webpackCopy": [],
        }
    return ("\nmodule.exports = function(config) {\n\nconfig.set("
            + json.dumps(settings) + ");"
            + safari_reporter.APPROVED_GENERATOR_TAIL
            + fragment.decode() + "\n}\n").encode()


def config_vectors():
    fragment = (ROOT / safari_reporter.SOURCE).read_bytes()
    repository = Path("/fixtures/repository")
    rendered = []
    accepted = {}
    for project, mode in (("dyn4k-core", "development"), ("dyn4k", "production"),
                          ("consumers/qualification/portable", "development"),
                          ("consumers/qualification/portable", "production")):
        data = generated_config(fragment, repository, Path(project), mode)
        observed = safari_reporter.validate_config(data, fragment, repository, Path(project), mode)
        accepted[(project, mode)] = data
        rendered.append(
            "ConfigCase(%s, %s, %s, %s, %s, %s, %s)" % (
                kotlin(f"{project} {mode}"), kotlin(project), kotlin(mode),
                kotlin(str(repository)), kotlin(base64.b64encode(data).decode()),
                kotlin(observed), kotlin("")))
    development = accepted[("dyn4k-core", "development")]
    production = accepted[("consumers/qualification/portable", "production")]
    mutations = [
        ("development mode on production file", "dyn4k-core", "development", development),
        ("production file as development", "consumers/qualification/portable", "development",
         production),
        ("wrong project", "dyn4k", None, development),
        ("modified tail comment", "dyn4k-core", None,
         development.replace(b"// qualification-safari-reporter.js\n",
                             b"// other-reporter.js\n")),
        ("replaced tail comment", "dyn4k-core", None,
         development.replace(b"// qualification-safari-reporter.js\n", b"config.plugins = [];\n")),
        ("missing fragment", "dyn4k-core", None,
         development.replace(fragment, b"")),
        ("duplicate fragment", "dyn4k-core", None,
         development.replace(fragment + b"\n}\n", fragment + fragment + b"\n}\n")),
        ("duplicate setting", "dyn4k-core", None,
         development.replace(b'{"singleRun": true', b'{"singleRun": true, "singleRun": false')),
        ("missing prefix", "dyn4k-core", None, development[1:]),
        ("leading space in settings", "dyn4k-core", None,
         development.replace(b"config.set({", b"config.set( {")),
        ("trailing junk", "dyn4k-core", None,
         development.replace(b"\n}\n", b"\n}\n\n")),
        ("unterminated settings", "dyn4k-core", None,
         development.replace(b");", b"", 1)),
        ("changed base path", "dyn4k-core", None,
         development.replace(b'"basePath":', b'"basePath": "x", "ignored":')),
        ("changed browser", "dyn4k-core", None,
         development.replace(b'["Safari"]', b'["Chrome"]')),
        ("invalid utf-8", "dyn4k-core", None, development.replace(b"//default layout",
                                                                 b"//default \xff layout")),
    ]
    for label, project, configuration, data in mutations:
        try:
            observed = safari_reporter.validate_config(
                data, fragment, repository, Path(project), configuration)
            result = ("observed", observed)
        except safari_reporter.ConfigBindingError as error:
            result = ("error", str(error))
        rendered.append(
            "ConfigCase(%s, %s, %s, %s, %s, %s, %s)" % (
                kotlin(label), kotlin(project),
                "null" if configuration is None else kotlin(configuration),
                kotlin(str(repository)), kotlin(base64.b64encode(data).decode()),
                "null" if result[0] == "error" else kotlin(result[1]),
                kotlin("" if result[0] == "observed" else result[1])))
    return rendered, base64.b64encode(fragment).decode()


# --------------------------------------------------------------------------------------
# committed_bytes / committed_fragment / stage
# --------------------------------------------------------------------------------------

def git(repository, *arguments, check=True):
    return subprocess.run(["git", "-C", str(repository)] + list(arguments),
                          check=check, capture_output=True, text=True)


def make_repository(root, fragment, autocrlf="false"):
    repository = root / "repository"
    repository.mkdir(parents=True)
    git(repository, "init", "-q")
    git(repository, "config", "core.autocrlf", autocrlf)
    source = repository / safari_reporter.SOURCE
    source.parent.mkdir(parents=True)
    source.write_bytes(fragment)
    for project in safari_reporter.PROJECTS:
        (repository / project).mkdir(parents=True, exist_ok=True)
    git(repository, "add", ".")
    git(repository, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "candidate")
    return repository, git(repository, "rev-parse", "HEAD").stdout.strip()


def committed_vectors(root, fragment):
    repository, candidate = make_repository(root, fragment)
    source = repository / safari_reporter.SOURCE
    rendered = []
    committed = safari_reporter.committed_bytes(
        repository, candidate, Path(safari_reporter.SOURCE))
    rendered.append("CommittedCase(%s, %s, %s, %s, %s)" % (
        kotlin("committed source"), kotlin(safari_reporter.SOURCE.as_posix()), kotlin(candidate),
        kotlin(base64.b64encode(committed).decode()), kotlin("")))

    windows = fragment.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    source.write_bytes(windows)
    git(repository, "add", safari_reporter.SOURCE)
    git(repository, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "crlf")
    crlf_candidate = git(repository, "rev-parse", "HEAD").stdout.strip()
    crlf_committed = safari_reporter.committed_bytes(
        repository, crlf_candidate, Path(safari_reporter.SOURCE))
    rendered.append("CommittedCase(%s, %s, %s, %s, %s)" % (
        kotlin("crlf source"), kotlin(safari_reporter.SOURCE.as_posix()), kotlin(crlf_candidate),
        kotlin(base64.b64encode(crlf_committed).decode()), kotlin("")))

    for label, relative, use_candidate in (
        ("absolute path", "/etc/passwd", candidate),
        ("parent traversal", "dyn4k-core/../dyn4k", candidate),
        ("single dot", "./x", candidate),
        ("short commit", safari_reporter.SOURCE.as_posix(), "abc"),
        ("missing path", "dyn4k-core/absent.txt", candidate),
        ("directory path", "dyn4k-core", candidate),
        ("missing commit", safari_reporter.SOURCE.as_posix(), "0" * 40),
    ):
        try:
            value = safari_reporter.committed_bytes(repository, use_candidate, Path(relative))
            rendered.append("CommittedCase(%s, %s, %s, %s, %s)" % (
                kotlin(label), kotlin(relative), kotlin(use_candidate),
                kotlin(base64.b64encode(value).decode()), kotlin("")))
        except ValueError as error:
            rendered.append("CommittedCase(%s, %s, %s, %s, %s)" % (
                kotlin(label), kotlin(relative), kotlin(use_candidate), "null",
                kotlin(str(error))))

    shred = root / "sha256"
    shred.mkdir()
    git(shred, "init", "-q", "--object-format=sha256")
    (shred / safari_reporter.SOURCE).parent.mkdir(parents=True)
    (shred / safari_reporter.SOURCE).write_bytes(fragment)
    git(shred, "add", ".")
    git(shred, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "sha256")
    sha256_candidate = git(shred, "rev-parse", "HEAD").stdout.strip()
    try:
        safari_reporter.committed_bytes(shred, sha256_candidate, Path(safari_reporter.SOURCE))
        message = ""
    except ValueError as error:
        message = str(error)
    rendered.append("CommittedCase(%s, %s, %s, %s, %s)" % (
        kotlin("sha256 object format"), kotlin(safari_reporter.SOURCE.as_posix()),
        kotlin(sha256_candidate), "null", kotlin(message)))

    source.write_bytes(fragment)
    git(repository, "checkout", "--", safari_reporter.SOURCE)
    try:
        fragment_value = safari_reporter.committed_fragment(repository, candidate)
        fragment_error = ""
    except ValueError as error:
        fragment_value = b""
        fragment_error = str(error)
    rendered.append("CommittedCase(%s, %s, %s, %s, %s)" % (
        kotlin("working tree fragment"), kotlin(safari_reporter.SOURCE.as_posix()), kotlin(candidate),
        ("null" if fragment_error else kotlin(base64.b64encode(fragment_value).decode())),
        kotlin(fragment_error)))

    source.write_bytes(fragment.replace(b"// ", b"// changed ", 1))
    try:
        safari_reporter.committed_fragment(repository, candidate)
        modified_error = ""
    except ValueError as error:
        modified_error = str(error)
    rendered.append("CommittedCase(%s, %s, %s, %s, %s)" % (
        kotlin("modified working tree"), kotlin(safari_reporter.SOURCE.as_posix()), kotlin(candidate),
        "null", kotlin(modified_error)))
    git(repository, "checkout", "--", safari_reporter.SOURCE)

    link = root / "linked-repository"
    shutil.copytree(repository, link, symlinks=True)
    (link / safari_reporter.SOURCE).unlink()
    outside = root / "outside-fragment.js"
    outside.write_bytes(fragment)
    (link / safari_reporter.SOURCE).symlink_to(outside)
    try:
        safari_reporter.committed_fragment(link, candidate)
        symlink_error = ""
    except ValueError as error:
        symlink_error = str(error)
    rendered.append("CommittedCase(%s, %s, %s, %s, %s)" % (
        kotlin("symlinked working tree"), kotlin(safari_reporter.SOURCE.as_posix()), kotlin(candidate),
        "null", kotlin(symlink_error)))
    return rendered, candidate


def stage_vectors(root, fragment):
    repository, candidate = make_repository(root / "stage-source", fragment)
    output = root / "stage-output"
    output.mkdir(parents=True)
    rendered = []

    def run(label, body, output_directory=output):
        for project in ("dyn4k-core", "dyn4k"):
            for name in ("karma.config.d", "karma.config.d.moved"):
                shutil.rmtree(repository / project / name, ignore_errors=True)
        try:
            with safari_reporter.stage(repository, candidate,
                                       [Path("dyn4k-core"), Path("dyn4k")],
                                       output_directory) as staged:
                body(staged, repository)
            result = staged
            error = ""
        except ValueError as failure:
            result = {"status": "REJECTED", "projects": {}, "forensic": []}
            error = str(failure)
        forensic_paths = [item["path"] for item in result["forensic"]]
        forensic_errors = [("error" in item) for item in result["forensic"]]
        forensic_hashes = [item.get("sha256", "") for item in result["forensic"]]
        leftovers = result.get("leftovers")
        rendered.append("StageCase(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" % (
            kotlin(label),
            kotlin(kompact(result.get("projects", {}))),
            kotlin(result.get("status", "")),
            kotlin_list([kotlin(path) for path in forensic_paths]),
            kotlin_list(["true" if value else "false" for value in forensic_errors]),
            kotlin_list([kotlin(value or "") for value in forensic_hashes]),
            "null" if leftovers is None else kotlin(kompact(leftovers)),
            "true" if result.get("leftovers_truncated") else "false",
            kotlin(result.get("source_sha256", "")),
            kotlin(error)))
        staged_snapshot = result.get("projects", {}).get("dyn4k-core")
        return staged_snapshot

    def clean(staged, repo):
        assert staged["projects"]["dyn4k-core"] == "STAGED"

    run("clean", clean)

    def changed(staged, repo):
        (repo / "dyn4k-core/karma.config.d" / safari_reporter.STAGED_NAME).write_bytes(
            b"config.plugins = [];\n")

    run("changed", changed)

    def leftover(staged, repo):
        (repo / "dyn4k-core/karma.config.d/extra.js").write_bytes(b"extra")

    run("leftover", leftover)

    def many_leftovers(staged, repo):
        folder = repo / "dyn4k-core/karma.config.d"
        for index in range(17):
            (folder / f"{chr(ord('a') + index)}.js").write_bytes(b"x")

    run("seventeen leftovers", many_leftovers)

    def swapped(staged, repo):
        folder = repo / "dyn4k-core/karma.config.d"
        folder.rename(folder.with_name("karma.config.d.moved"))
        folder.mkdir()

    run("directory swapped", swapped)

    def dangling(staged, repo):
        (repo / "dyn4k-core/karma.config.d/dangling.js").symlink_to(repo / "absent.js")

    run("dangling leftover", dangling)

    try:
        with safari_reporter.stage(repository, candidate, [Path("dyn4k-core")],
                                   repository / "build/output"):
            pass
        inside_error = ""
    except ValueError as error:
        inside_error = str(error)
    rendered.append("StageCase(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" % (
        kotlin("output inside repository"), kotlin("{}"), kotlin("REJECTED"),
        kotlin_list([]), kotlin_list([]), kotlin_list([]), "null", "false", kotlin(""),
        kotlin(inside_error)))

    for label, projects in (("unknown project", [Path("other")]),
                            ("duplicate project", [Path("dyn4k-core"), Path("dyn4k-core")]),
                            ("empty projects", [])):
        try:
            with safari_reporter.stage(repository, candidate, projects, output):
                pass
            message = ""
        except ValueError as error:
            message = str(error)
        rendered.append("StageCase(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" % (
            kotlin(label), kotlin("{}"), kotlin("REJECTED"), kotlin_list([]), kotlin_list([]),
            kotlin_list([]), "null", "false", kotlin(""), kotlin(message)))
    return rendered


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        fragment = (ROOT / safari_reporter.SOURCE).read_bytes()
        runtime = runtime_vectors()
        hosted_cases = hosted_vectors()
        groups = group_vectors()
        wrappers = wrapper_vectors()
        configs, fragment_base64 = config_vectors()
        committed, candidate = committed_vectors(root / "committed", fragment)
        stages = stage_vectors(root / "stage", fragment)

    sha = revision()
    lines = [
        "package io.github.rubixhacker.harness.qualification",
        "",
        "/**",
        " * Recorded reference vectors for the `hosted.py` and `safari_reporter.py` ports.",
        " *",
        " * Generated by `tools/harness/qualification/parity/generate_hosted_safari_vectors.py`",
        " * from the Python implementations at git revision",
        " * [`REVISION`]. Every input and expectation below was produced by Python; the Kotlin",
        " * suites replay them. Do not edit by hand.",
        " */",
        "internal object HostedSafariVectors {",
        "    const val REVISION = %s" % kotlin(sha),
        "    const val GENERATOR = %s" % kotlin(
            "tools/harness/qualification/parity/generate_hosted_safari_vectors.py"),
        "",
        "    class RuntimeCase(",
        "        val label: String,",
        "        val target: String,",
        "        val observed: String,",
        "        val status: String,",
        "        val reason: String,",
        "    )",
        "",
        "    val RUNTIME: List<RuntimeCase> = listOf(",
    ]
    lines += ["        " + case + "," for case in runtime]
    lines += [
        "    )",
        "",
        "    class HostedCase(",
        "        val label: String,",
        "        val target: String,",
        "        val source: String?,",
        "        val consumer: String?,",
        "        val hashes: String?,",
        "        val runtime: String,",
        "        val status: String,",
        "        val reason: String,",
        "    )",
        "",
        "    val HOSTED: List<HostedCase> = listOf(",
    ]
    lines += ["        " + case + "," for case in hosted_cases]
    lines += [
        "    )",
        "",
        "    class GroupCase(",
        "        val label: String,",
        "        val ids: List<String>,",
        "        val keys: String,",
        "        val groups: String,",
        "        val patterns: List<String>,",
        "        val error: String,",
        "    )",
        "",
        "    val GROUPS: List<GroupCase> = listOf(",
    ]
    lines += ["        " + case + "," for case in groups]
    lines += [
        "    )",
        "",
        "    class WrapperCase(val label: String, val repository: String, val windows: Boolean, val path: String)",
        "",
        "    val WRAPPERS: List<WrapperCase> = listOf(",
    ]
    lines += ["        " + case + "," for case in wrappers]
    lines += [
        "    )",
        "",
        "    const val APPROVED_GENERATOR_TAIL_SHA256 = %s" % kotlin(
            __import__("hashlib").sha256(
                safari_reporter.APPROVED_GENERATOR_TAIL.encode()).hexdigest()),
        "    const val APPROVED_GENERATOR_TAIL_LENGTH = %d" % len(
            safari_reporter.APPROVED_GENERATOR_TAIL.encode()),
        "    const val SOURCE = %s" % kotlin(safari_reporter.SOURCE.as_posix()),
        "    const val STAGED_NAME = %s" % kotlin(safari_reporter.STAGED_NAME),
        "    const val MAX_FRAGMENT_BYTES = %d" % safari_reporter.MAX_FRAGMENT_BYTES,
        "    const val MAX_COMMITTED_OBJECT_BYTES = %d" % safari_reporter.MAX_COMMITTED_OBJECT_BYTES,
        "    const val CONSUMER = %s" % kotlin("consumers/qualification/portable"),
        "",
        "    val PROJECTS: List<String> = " + kotlin_list(
            [kotlin(project.as_posix()) for project in safari_reporter.PROJECTS]),
        "",
        "    val PACKAGES: List<Pair<String, String>> = listOf(",
    ]
    lines += ["        " + kotlin(project.as_posix()) + " to " + kotlin(package) + ","
              for project, package in safari_reporter.PACKAGES.items()]
    lines += [
        "    )",
        "",
        "    val CONFIG_PATHS: List<Pair<String, String>> = listOf(",
    ]
    lines += ["        " + kotlin(project.as_posix()) + " to "
              + kotlin(safari_reporter.config_relative(project).as_posix()) + ","
              for project in safari_reporter.PROJECTS]
    lines += [
        "    )",
        "",
        "    /** The committed reporter fragment, base64 encoded. */",
        "    const val FRAGMENT_BASE64 = %s" % kotlin(fragment_base64),
        "",
        "    class ConfigCase(",
        "        val label: String,",
        "        val project: String,",
        "        val configuration: String?,",
        "        val repository: String,",
        "        val data: String,",
        "        val observed: String?,",
        "        val error: String,",
        "    )",
        "",
        "    val CONFIGS: List<ConfigCase> = listOf(",
    ]
    lines += ["        " + case + "," for case in configs]
    lines += [
        "    )",
        "",
        "    class CommittedCase(",
        "        val label: String,",
        "        val relative: String,",
        "        val candidate: String,",
        "        val bytes: String?,",
        "        val error: String,",
        "    )",
        "",
        "    val COMMITTED: List<CommittedCase> = listOf(",
    ]
    lines += ["        " + case + "," for case in committed]
    lines += [
        "    )",
        "",
        "    class StageCase(",
        "        val label: String,",
        "        val projects: String,",
        "        val status: String,",
        "        val forensicPaths: List<String>,",
        "        val forensicErrors: List<Boolean>,",
        "        val forensicSha256: List<String>,",
        "        val leftovers: String?,",
        "        val leftoversTruncated: Boolean,",
        "        val sourceSha256: String,",
        "        val error: String,",
        "    )",
        "",
        "    val STAGES: List<StageCase> = listOf(",
    ]
    lines += ["        " + case + "," for case in stages]
    lines += [
        "    )",
        "}",
        "",
    ]
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text("\n".join(lines))
    print("wrote", TARGET, "at revision", sha)


if __name__ == "__main__":
    main()
