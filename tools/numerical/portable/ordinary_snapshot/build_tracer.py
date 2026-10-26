import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time


ARCHIVE_SHA256 = "4bde6246926890dcee824f6e6ac42a06752f47d77e5097d86e3c0d6d4b709fe5"
SOURCE_SHA256 = "06525ee83048d477139312ad96e750585354e5f9f56663bdde0f959dce5b16dc"
HERE = Path(__file__).resolve().parent
PATCH = HERE / "strace-7.2.patch"
INCLUDE = HERE / "owned_snapshot.inc"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(argv, cwd, environment, timeout):
    started = time.time_ns()
    result = subprocess.run(argv, cwd=cwd, env=environment, timeout=timeout,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {"argv": argv, "cwd": str(cwd), "utc_start_ns": started,
            "utc_end_ns": time.time_ns(), "exit_code": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


def build(archive, output, *, timeout=600):
    archive = Path(archive).resolve()
    output = Path(output).resolve()
    if digest(archive) != ARCHIVE_SHA256:
        raise ValueError("pinned strace source archive differs")
    if output.exists():
        raise ValueError("private build output already exists")
    output.mkdir(mode=0o700, parents=True)
    commands = []
    with tarfile.open(archive, "r:xz") as source:
        names = source.getnames()
        if not names or any(name != "strace-7.2" and
                            not name.startswith("strace-7.2/") or
                            ".." in Path(name).parts for name in names):
            raise ValueError("strace source archive layout differs")
        source.extractall(output, filter="data")
    tree = output / "strace-7.2"
    source_file = tree / "src/strace.c"
    if digest(source_file) != SOURCE_SHA256:
        raise ValueError("pinned strace source file differs")
    shutil.copyfile(INCLUDE, tree / "src/owned_snapshot.inc")
    env = dict(os.environ)
    env.update({"LC_ALL": "C", "TZ": "UTC", "SOURCE_DATE_EPOCH": "1770000000",
                "CFLAGS": "-O2 -g0 -ffile-prefix-map=" + str(tree) + "=/strace-7.2",
                "MAKEFLAGS": "-j2"})
    for index, (argv, cwd) in enumerate(((["git", "apply", str(PATCH)], tree),
                      ([str(tree / "configure"), "--disable-mpers",
                        "--disable-stacktrace"], output),
                      (["make", "-j2"], output))):
        command = run(argv, cwd, env, timeout)
        for name in ("stdout", "stderr"):
            path = output / f"build-{index}-{name}.raw"
            with path.open("xb") as stream:
                stream.write(command[name])
            command[name + "_path"] = str(path)
        commands.append(command)
        if command["exit_code"]:
            raise RuntimeError(f"private strace build failed: {argv[0]}: " +
                               command["stderr"].decode("utf-8", "replace")[-2000:])
    binary = output / "src/strace"
    record = {"schema": "ordinary-snapshot-build/1",
              "archive_sha256": ARCHIVE_SHA256,
              "upstream_source_sha256": SOURCE_SHA256,
              "patch_sha256": digest(PATCH), "include_sha256": digest(INCLUDE),
              "compiler_path": shutil.which("gcc"),
              "compiler_sha256": digest(shutil.which("gcc")),
              "binary_sha256": digest(binary),
              "commands": [{key: value for key, value in item.items()
                            if key not in {"stdout", "stderr"}} |
                           {"stdout_sha256": hashlib.sha256(item["stdout"]).hexdigest(),
                            "stderr_sha256": hashlib.sha256(item["stderr"]).hexdigest()}
                           for item in commands]}
    (output / "build-record.json").write_text(json.dumps(record, sort_keys=True) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    parser.add_argument("output")
    parser.add_argument("--compare-binary")
    args = parser.parse_args()
    result = build(args.archive, args.output)
    if args.compare_binary and digest(args.compare_binary) != result["binary_sha256"]:
        raise ValueError("private strace binary differs from exact rebuild")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
