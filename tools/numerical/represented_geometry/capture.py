import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).with_name("RepresentedGeometryProbe.java")
BASELINE = Path("/var/home/stewart/dyn4k-evidence/session-control/baseline-current-4d-home-full")
CANDIDATE = Path("/var/home/stewart/dyn4k-evidence/session-control/numerical-followup-7d/wheel/capture-7d")
JDK = Path("/tmp/dyn4k-tools/jdk21")
KOTLIN_STDLIB = Path("/var/home/stewart/.gradle/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib/2.4.20/94c1451890d164aed65d43b3db0b7ecef7c183e7/kotlin-stdlib-2.4.20.jar")
FIXTURE_SHA = "dd104a7e018b9d0bd77c9af14e929699d68f29fa4ac8179a5bd7d98bdc87d9ce"
BASELINE_JAR_SHA = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
CANDIDATE_JAR_SHA = "07d7a18f418a9f222e8dce1c2f1005865cb25052eab088854a968c3c8b8b3d13"
CANDIDATE_COMMIT = "7d319d5027f2b10c11eae7f4574e6edf407449c0"
KOTLIN_STDLIB_SHA = "2226de463d309d4a5500a481320b3dea515a6981dcae1def531fbc158884e25f"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return sha(path.read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(("git", *args), cwd=ROOT)


def committed_source():
    revision = git("rev-parse", "HEAD").decode().strip()
    paths = (SOURCE, Path(__file__))
    hashes = {}
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        require(git("show", f"HEAD:{relative}") == data,
                f"local diagnostic source differs from commit: {relative}")
        hashes[relative] = sha(data)
    return revision, hashes


def run(label, command, environment, output):
    process = subprocess.Popen(command, cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    stdout_path = output / f"{label}.stdout"
    stderr_path = output / f"{label}.stderr"
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    receipt = {"pid": process.pid, "exit_code": process.returncode,
               "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr),
               "stdout_file": stdout_path.name, "stderr_file": stderr_path.name}
    require(process.returncode == 0, f"{label} exited {process.returncode}")
    return stdout, receipt


def encode_rows(rows):
    return b"".join((json.dumps(row, sort_keys=True, separators=(",", ":"),
                                 allow_nan=False) + "\n").encode() for row in rows)


def raw_bits(value):
    return format(struct.unpack(">Q", struct.pack(">d", value))[0], "x")


def parse_rows(data):
    rows = [json.loads(line) for line in data.splitlines()]
    require(len(rows) == 8, "probe did not produce eight rows")
    require(all(set(row) == {"id", "input", "result"} for row in rows),
            "probe row shape differs")
    origins = ((1000.0, 1000.0), (-1000.0, 1000.0),
               (1000000.0, -1000000.0), (-1000000.0, 1000000.0))
    for index, row in enumerate(rows):
        origin_index, sign_index = divmod(index, 2)
        direction = "negative" if sign_index == 0 else "positive"
        sign = -1 if sign_index == 0 else 1
        expected_id = f"geometry-represented-v1-s0-o{origin_index + 1}-{direction}"
        values = row["input"]
        ox, oy = origins[origin_index]
        neutral = ox + 0.01 * 1.5
        center = math.nextafter(neutral, math.copysign(math.inf, sign))
        gap = (center - ox) - 0.01 * 1.5
        require(row["id"] == expected_id, "probe ID differs")
        require(values == {"originX": ox, "originY": oy, "scale": 0.01,
                           "direction": direction, "neutral": neutral, "center": center,
                           "gap": gap, "neutralBits": raw_bits(neutral),
                           "centerBits": raw_bits(center)},
                f"probe input differs: {expected_id}")
        require(center != neutral and sign * gap > 0.0,
                f"represented premise differs: {expected_id}")
        result = row["result"]
        require(set(result) == {"sat", "satDepth", "gjk", "gjkDepth",
                                "separated", "distance"}, "probe result shape differs")
        require(all(type(result[name]) is bool for name in ("sat", "gjk", "separated")),
                "probe boolean result differs")
        require(all(math.isfinite(result[name]) for name in
                    ("satDepth", "gjkDepth", "distance")), "probe result is nonfinite")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(Path.home().resolve()), "output must be under home")
    require(not output.exists(), "output already exists")
    output.mkdir(parents=True)
    (output / "tmp").mkdir()
    environment = os.environ.copy()
    environment.pop("OLLAMA_API_KEY", None)
    environment["TMPDIR"] = str(output / "tmp")
    environment["JAVA_TOOL_OPTIONS"] = f"-Djava.io.tmpdir={output / 'tmp'}"
    environment["JAVA_HOME"] = str(JDK)
    environment["PATH"] = str(JDK / "bin") + os.pathsep + environment.get("PATH", "")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    sys.path.insert(0, str(ROOT / "tools/numerical/portable"))
    from baseline_capture import fixture_source_sha256
    fixture_hash = fixture_source_sha256()
    require(fixture_hash == FIXTURE_SHA, "frozen baseline fixture source differs")
    revision, source_hashes = committed_source()
    verified = json.loads((BASELINE / "verified.json").read_text())
    baseline_jar = BASELINE / "dyn4j-6.0.0.jar"
    candidate_jar = CANDIDATE / "artifact.jar"
    candidate_receipt_path = CANDIDATE / "receipt.json"
    candidate_receipt = json.loads(candidate_receipt_path.read_text())
    require(verified["fixture_source_sha256"] == FIXTURE_SHA and
            verified["baseline_jar_sha256"] == BASELINE_JAR_SHA and
            file_sha(baseline_jar) == BASELINE_JAR_SHA,
            "baseline artifact identity differs")
    require(candidate_receipt["candidate_commit"] == CANDIDATE_COMMIT and
            candidate_receipt["artifact_sha256"] == CANDIDATE_JAR_SHA and
            file_sha(candidate_jar) == CANDIDATE_JAR_SHA,
            "candidate artifact identity differs")
    require(any(entry["path"] == str(KOTLIN_STDLIB) and
                entry["sha256"] == KOTLIN_STDLIB_SHA
                for entry in candidate_receipt["worker_classpath_entries"]) and
            file_sha(KOTLIN_STDLIB) == KOTLIN_STDLIB_SHA,
            "candidate Kotlin runtime identity differs")

    java = JDK / "bin/java"
    javac = JDK / "bin/javac"
    _, java_version_receipt = run("java-version", (java, "-version"),
                                  environment, output)
    _, javac_version_receipt = run("javac-version", (javac, "-version"),
                                    environment, output)
    classes = output / "classes"
    classes.mkdir()
    _, compile_receipt = run("compile", (javac, "-cp", baseline_jar,
                                         "-d", classes, SOURCE), environment, output)
    class_sha = file_sha(classes / "RepresentedGeometryProbe.class")
    captures = {}
    for label, jar in (("baseline", baseline_jar), ("candidate", candidate_jar)):
        classpath = f"{classes}{os.pathsep}{jar}"
        if label == "candidate":
            classpath += f"{os.pathsep}{KOTLIN_STDLIB}"
        data, process_receipt = run(label, (java, "-cp", classpath,
                                           "RepresentedGeometryProbe"), environment, output)
        rows = parse_rows(data)
        inputs = encode_rows([{"id": row["id"], **row["input"]} for row in rows])
        results = encode_rows([{"id": row["id"], **row["result"]} for row in rows])
        (output / f"{label}-inputs.jsonl").write_bytes(inputs)
        (output / f"{label}-results.jsonl").write_bytes(results)
        captures[label] = {"process": process_receipt, "input_sha256": sha(inputs),
                           "result_sha256": sha(results), "row_count": len(rows)}
    require(captures["baseline"]["input_sha256"] ==
            captures["candidate"]["input_sha256"], "baseline and candidate inputs differ")

    manifest = {
        "status": "COMPLETED_BOUNDED_DIAGNOSTIC",
        "source_commit": revision,
        "source_sha256": source_hashes,
        "fixture_source_sha256": fixture_hash,
        "candidate_origin_commit": CANDIDATE_COMMIT,
        "candidate_origin_receipt_sha256": file_sha(candidate_receipt_path),
        "candidate_origin_source_archive_sha256": candidate_receipt["source_archive_sha256"],
        "artifacts": {"baseline": {"path": str(baseline_jar), "sha256": BASELINE_JAR_SHA},
                      "candidate": {"path": str(candidate_jar), "sha256": CANDIDATE_JAR_SHA},
                      "candidate_kotlin_stdlib": {"path": str(KOTLIN_STDLIB),
                                                   "sha256": KOTLIN_STDLIB_SHA}},
        "jdk": {"java_sha256": file_sha(java), "javac_sha256": file_sha(javac),
                "release_sha256": file_sha(JDK / "release"),
                "java_version": java_version_receipt,
                "javac_version": javac_version_receipt},
        "compiled_class_sha256": class_sha,
        "compile": compile_receipt,
        "captures": captures,
        "results_byte_identical": captures["baseline"]["result_sha256"] ==
                                  captures["candidate"]["result_sha256"],
        "limit": "Eight public API observations; no portable numerical lane is qualified."
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"], "rows_per_artifact": 8,
                      "results_byte_identical": manifest["results_byte_identical"]}))


if __name__ == "__main__":
    main()
