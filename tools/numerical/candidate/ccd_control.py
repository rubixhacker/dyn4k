import argparse
import json
import subprocess
import sys
from pathlib import Path

import matrix
import receipt


SOURCE_SHA256 = "ca36a7d9d55c3e21e0f313656d28c317aa763f3f54ed7d9b36e5b3d5eed31689"


def run(args, output):
    with output.open("xb") as stream:
        process = subprocess.run(args, stdout=stream, stderr=subprocess.PIPE,
                                 cwd=matrix.ROOT, check=False)
    return process.returncode, process.stderr


def main():
    parser = argparse.ArgumentParser(description="Run the frozen prospective CCD body-hash control")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--baseline-jar", required=True, type=Path)
    parser.add_argument("--java21", required=True, type=Path)
    parser.add_argument("--kotlin-stdlib", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    commit = receipt.clean_commit()
    if matrix.digest(args.source) != SOURCE_SHA256:
        raise ValueError("root CCD control source hash differs")
    if matrix.digest(args.baseline_jar) != matrix.BASELINE_SHA256:
        raise ValueError("pinned baseline JAR hash differs")
    args.output.mkdir(parents=True)
    result = {"source_sha256": SOURCE_SHA256, "candidate_commit": commit,
              "candidate_source_sha256": receipt.source_hash(),
              "java_executable_sha256": matrix.digest(args.java21 / "bin" / "java"),
              "providers": {}}
    for provider, jar in (("baseline", args.baseline_jar), ("candidate", receipt.ARTIFACT)):
        directory = args.output / provider
        directory.mkdir()
        classes = directory / "classes"
        classes.mkdir()
        classpath = [jar] + ([args.kotlin_stdlib] if provider == "candidate" else [])
        compile_args = [str(args.java21 / "bin" / "javac"), "--release", "8", "-cp",
                        ":".join(map(str, classpath)), "-d", str(classes), str(args.source)]
        compile_exit, compile_stderr = run(compile_args, directory / "compile.log")
        if compile_exit:
            raise ValueError(provider + " CCD compile failed: " + compile_stderr.decode(errors="replace"))
        rows = {}
        for offset in (0, 1, 11, 31):
            command = [str(args.java21 / "bin" / "java"), "-XshowSettings:properties", "-cp",
                       ":".join(map(str, [classes] + classpath)), "CcdOrderProbe", str(offset)]
            trace = directory / f"offset-{offset}.tsv"
            exit_code, stderr = run(command, trace)
            (directory / f"offset-{offset}.stderr").write_bytes(stderr)
            if exit_code:
                raise ValueError(f"{provider} offset {offset}: recorder exited {exit_code}")
            data = trace.read_bytes()
            count = len(data.splitlines())
            if count != 121:
                raise ValueError(f"{provider} offset {offset}: {count} / 121 rows")
            rows[offset] = {"command": command, "trace_sha256": matrix.digest(trace),
                            "stderr_sha256": matrix.digest(directory / f"offset-{offset}.stderr"),
                            "rows": count, "final_hits": int(data.splitlines()[-1].split(b"\t")[1])}
        result["providers"][provider] = {"jar_sha256": matrix.digest(jar), "offsets": rows}
    result["matching_offsets"] = {
        str(offset): result["providers"]["baseline"]["offsets"][offset]["trace_sha256"] ==
        result["providers"]["candidate"]["offsets"][offset]["trace_sha256"]
        for offset in (0, 1, 11, 31)
    }
    result["status"] = "DIAGNOSTIC_MATCH" if all(result["matching_offsets"].values()) else "DIAGNOSTIC_DIFFERENCE"
    (args.output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "matching_offsets": result["matching_offsets"]}))
    return 0 if all(result["matching_offsets"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
