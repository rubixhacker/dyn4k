import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare


ROOT = Path(__file__).resolve().parents[3]
CURRENT_SOURCE = object()
STAGED = ROOT / "build/staging-repository/io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1"
ARTIFACT = STAGED / "dyn4k-core-jvm-0.1.0-alpha.1.jar"
RECEIPT_FIELDS = {
    "fixture_key", "source_sha256", "source_hash_method", "artifact_sha256",
    "artifact_path", "candidate_commit", "trace_sha256", "reference_source_revision",
    "reference_artifact_sha256", "reference_trace_sha256", "expected_counts",
    "executed_counts", "skipped", "build_config_sha256", "runtime",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(*args):
    return subprocess.run(args, cwd=ROOT, check=True, capture_output=True).stdout


def validate_source_commit(commit):
    if type(commit) is not str or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise compare.Rejected("source revision")
    try:
        kind = run("git", "--no-replace-objects", "cat-file", "-t", commit).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise compare.Rejected("source revision unavailable") from error
    if kind != b"commit":
        raise compare.Rejected("source revision is not a commit")
    return commit


def source_hash(commit=CURRENT_SOURCE):
    try:
        head = run("git", "--no-replace-objects", "rev-parse", "--verify",
                   "HEAD^{commit}").decode().strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise compare.Rejected("source revision unavailable") from error
    validate_source_commit(head)
    if commit is CURRENT_SOURCE:
        commit = head
    else:
        validate_source_commit(commit)
        if commit != head:
            raise compare.Rejected("source revision is not HEAD")
    try:
        archive = run("git", "--no-replace-objects", "-c", "core.autocrlf=false",
                      "archive", "--format=tar", commit)
    except (OSError, subprocess.CalledProcessError) as error:
        raise compare.Rejected("source archive unavailable") from error
    return sha256(archive)


def build_config_hash():
    digest = hashlib.sha256()
    for name in ("settings.gradle.kts", "build.gradle.kts"):
        path = Path(__file__).with_name(name)
        content = path.read_bytes()
        digest.update(name.encode() + b"\0" + str(len(content)).encode() + b"\0" + content)
    return digest.hexdigest()


def load_fixture(key, catalog_path):
    catalog = compare.parse(Path(catalog_path).read_bytes())
    matches = [item for item in catalog["fixtures"] if item["key"] == key]
    if len(matches) != 1:
        raise compare.Rejected("missing or duplicate fixture key")
    item = matches[0]
    return {**catalog["profiles"][item["profile"]], **item,
            "baseline_source_revision": catalog.get("baseline_source_revision"),
            "baseline_jar_sha256": catalog.get("baseline_jar_sha256")}


def inspect(trace, fixture):
    return compare.check_counts(compare.records(trace), fixture, reference=False)


def clean_commit():
    commit = run("git", "--no-replace-objects", "rev-parse", "HEAD").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise compare.Rejected("candidate commit is not a full Git SHA")
    status = run("git", "--no-replace-objects", "status", "--porcelain",
                 "--untracked-files=all").decode()
    generated = ("/build/", "/.gradle/", "/__pycache__/", "/.kotlin/")
    dirty = [line for line in status.splitlines() if not any(part in line for part in generated)]
    if dirty:
        raise compare.Rejected("candidate source tree is not clean")
    return commit


RUNTIME_FIELDS = {"process_command", "process_id", "process_start", "java_home",
                  "java_version", "java_vm_name", "java_vm_version", "os_name",
                  "os_arch", "engine_location", "recorder_location"}


def runtime_identity(trace):
    stamp = Path(trace).parent / "runtime.json"
    if not stamp.is_file():
        raise compare.Rejected("recorder process runtime stamp is missing")
    runtime = compare.parse(stamp.read_bytes())
    if not isinstance(runtime, dict) or set(runtime) != RUNTIME_FIELDS:
        raise compare.Rejected("recorder process runtime stamp has missing or extra fields")
    if any(not isinstance(value, str) or not value for value in runtime.values()):
        raise compare.Rejected("recorder process runtime stamp has an empty or invalid value")
    location = urlparse(runtime["engine_location"])
    if location.scheme != "file" or location.netloc not in ("", "localhost"):
        raise compare.Rejected("loaded engine has no local code source")
    loaded = Path(unquote(location.path))
    if not loaded.is_file() or sha256(loaded.read_bytes()) != sha256(ARTIFACT.read_bytes()):
        raise compare.Rejected("loaded engine differs from staged candidate artifact")
    command = Path(runtime["process_command"])
    if not command.is_file():
        raise compare.Rejected("recorder process executable is missing")
    runtime["process_command_sha256"] = sha256(command.read_bytes())
    runtime["runtime_stamp_sha256"] = sha256(stamp.read_bytes())
    return runtime


def seal(args, fixture, counts):
    baseline = compare.audit_reference(fixture, args.reference)
    if baseline["status"] != "PASSED":
        raise compare.Rejected("frozen reference audit failed: " + baseline["reason"])
    if args.artifact and Path(args.artifact).resolve() != ARTIFACT.resolve():
        raise compare.Rejected("artifact is not the staged dyn4k-core-jvm JAR")
    if not ARTIFACT.is_file():
        raise compare.Rejected("staged dyn4k-core-jvm JAR is missing")
    commit = clean_commit()
    receipt = {
        "fixture_key": args.fixture,
        "source_sha256": source_hash(commit),
        "source_hash_method": "SHA-256 of git archive --format=tar HEAD",
        "artifact_sha256": sha256(ARTIFACT.read_bytes()),
        "artifact_path": str(ARTIFACT.relative_to(ROOT)),
        "candidate_commit": commit,
        "trace_sha256": sha256(Path(args.trace).read_bytes()),
        "reference_source_revision": fixture["baseline_source_revision"],
        "reference_artifact_sha256": fixture["baseline_jar_sha256"],
        "reference_trace_sha256": fixture["reference"]["gzip_sha256"],
        "expected_counts": fixture["counts"],
        "executed_counts": counts,
        "skipped": 0,
        "build_config_sha256": build_config_hash(),
        "runtime": runtime_identity(args.trace),
    }
    output = Path(args.output)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return receipt


def verify(args, fixture, counts):
    receipt = compare.parse(Path(args.receipt).read_bytes())
    if set(receipt) != RECEIPT_FIELDS:
        raise compare.Rejected("receipt has missing or extra fields")
    if receipt["fixture_key"] != args.fixture:
        raise compare.Rejected("receipt fixture differs")
    if receipt["source_hash_method"] != "SHA-256 of git archive --format=tar HEAD":
        raise compare.Rejected("source hash method differs")
    if receipt["candidate_commit"] != clean_commit():
        raise compare.Rejected("receipt commit is stale")
    if receipt["source_sha256"] != source_hash(receipt["candidate_commit"]):
        raise compare.Rejected("receipt source hash is stale")
    if receipt["artifact_path"] != str(ARTIFACT.relative_to(ROOT)) or not ARTIFACT.is_file():
        raise compare.Rejected("receipt artifact path differs")
    if receipt["artifact_sha256"] != sha256(ARTIFACT.read_bytes()):
        raise compare.Rejected("receipt artifact hash differs")
    if receipt["trace_sha256"] != sha256(Path(args.trace).read_bytes()):
        raise compare.Rejected("receipt trace hash differs")
    if receipt["build_config_sha256"] != build_config_hash():
        raise compare.Rejected("receipt build configuration differs")
    if receipt["runtime"] != runtime_identity(args.trace):
        raise compare.Rejected("receipt runtime differs")
    compare.load_receipt(args.receipt, args.trace, fixture, receipt["source_sha256"],
                         receipt["artifact_sha256"], receipt["candidate_commit"], counts)
    return receipt


def main():
    parser = argparse.ArgumentParser(description="Inspect and bind staged JVM numerical captures")
    parser.add_argument("mode", choices=("inspect", "seal", "verify"))
    parser.add_argument("--catalog", default=str(ROOT / "tools/numerical/fixtures.json"))
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--reference")
    parser.add_argument("--artifact")
    parser.add_argument("--output")
    parser.add_argument("--receipt")
    args = parser.parse_args()
    try:
        fixture = load_fixture(args.fixture, args.catalog)
        counts = inspect(args.trace, fixture)
        result = {"status": "PASSED", "executed_counts": counts}
        if args.mode == "seal":
            if not args.reference or not args.output:
                parser.error("seal needs --reference and --output")
            result["receipt"] = seal(args, fixture, counts)
        if args.mode == "verify":
            if not args.receipt:
                parser.error("verify needs --receipt")
            result["receipt"] = verify(args, fixture, counts)
    except (compare.Rejected, OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        result = {"status": "FAILED", "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PASSED" else 1)


if __name__ == "__main__":
    main()
