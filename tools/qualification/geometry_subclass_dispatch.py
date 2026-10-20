#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import subclass_provider


BASELINE_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
CASES = (
    "transform_x", "transform_y", "transform", "inverse_transform", "transform_r",
    "inverse_transform_r", "get_transformed", "get_inverse_transformed",
    "get_transformed_r", "get_inverse_transformed_r",
    "destination_transformed_control", "destination_inverse_control",
    "destination_rotation_control", "destination_inverse_rotation_control",
    "transform_lerp", "lerped_end", "lerped_delta", "set_translation_vector_control",
    "lerp_delta_translate_control", "ellipse_mass", "half_ellipse_mass",
    "half_ellipse_height_string", "interval_expanded", "interval_shrink",
    "matrix_transpose", "matrix_invert", "matrix_multiply", "matrix_self_multiply_control",
    "matrix_copy_sum_control", "matrix_copy_inverse_control", "matrix22_copy_control",
)
PROVIDERS = ("Transform", "Ellipse", "HalfEllipse", "Interval", "Matrix33", "Matrix22")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, output, env):
    result = subprocess.run(command, capture_output=True, check=False, env=env)
    output.with_suffix(".stdout").write_bytes(result.stdout)
    output.with_suffix(".stderr").write_bytes(result.stderr)
    if result.returncode:
        raise ValueError(f"{output.name} failed with exit code {result.returncode}")
    return result.stdout.decode("utf-8")


def parse(text, jar):
    values = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key in values:
            raise ValueError("fixture output has a malformed or duplicate key")
        values[key] = value
    expected = set(CASES) | {"provider." + name for name in PROVIDERS}
    if set(values) != expected:
        raise ValueError(f"fixture key mismatch: missing={sorted(expected - set(values))}, extra={sorted(set(values) - expected)}")
    for name in PROVIDERS:
        if not subclass_provider.matches_provider(values.pop("provider." + name), jar):
            raise ValueError(f"{name} class provider is not {jar}")
    return values


def main():
    parser = argparse.ArgumentParser(description="Compare Java geometry subclass behavior")
    parser.add_argument("--baseline-jar", required=True, type=Path)
    parser.add_argument("--candidate-jar", required=True, type=Path)
    parser.add_argument("--kotlin-stdlib", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--java-home", type=Path, default=Path("/tmp/dyn4k-tools/jdk21"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixture = Path(__file__).with_name("fixtures") / "GeometrySubclassDispatch.java"
    java_home = args.java_home
    env = os.environ.copy()
    env.pop("OLLAMA_API_KEY", None)
    baseline_hash = sha256(args.baseline_jar)
    candidate_hash = sha256(args.candidate_jar)
    receipt = {"fixture_sha256": sha256(fixture), "baseline_sha256": baseline_hash,
               "candidate_sha256": candidate_hash, "stdlib_sha256": sha256(args.kotlin_stdlib),
               "case_count": len(CASES), "status": "FAILED"}
    try:
        if baseline_hash != BASELINE_SHA256:
            raise ValueError("baseline JAR hash differs from pinned dyn4j 6.0.0")
        if candidate_hash == BASELINE_SHA256:
            raise ValueError("candidate JAR is the pinned baseline JAR")
        classes = output / "classes"
        classes.mkdir(exist_ok=True)
        run([str(java_home / "bin/javac"), "-cp", str(args.baseline_jar.resolve()),
             "-d", str(classes), str(fixture)], output / "compile", env)
        receipt["class_sha256"] = sha256(classes / "GeometrySubclassDispatch.class")
        observations = {}
        for name, jar in (("baseline", args.baseline_jar), ("candidate", args.candidate_jar)):
            raw = run([str(java_home / "bin/java"), "-cp", os.pathsep.join((str(jar.resolve()),
                       str(classes), str(args.kotlin_stdlib.resolve()))),
                       "GeometrySubclassDispatch"], output / name, env)
            observations[name] = parse(raw, jar)
        differences = {key: {name: observations[name][key] for name in observations}
                       for key in CASES if observations["baseline"][key] != observations["candidate"][key]}
        receipt["differences"] = differences
        receipt["status"] = "PASSED" if not differences else "FAILED"
    except (OSError, UnicodeError, ValueError) as error:
        receipt["error"] = str(error)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": receipt["status"], "case_count": len(CASES),
                      "difference_count": len(receipt.get("differences", {})),
                      "error": receipt.get("error")}, sort_keys=True))
    return 0 if receipt["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
