from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


MODULE_NAME = "org.dyn4j"
EXPORTS = frozenset({
    "org.dyn4j", "org.dyn4j.collision", "org.dyn4j.collision.broadphase",
    "org.dyn4j.collision.continuous", "org.dyn4j.collision.manifold",
    "org.dyn4j.collision.narrowphase", "org.dyn4j.dynamics",
    "org.dyn4j.dynamics.contact", "org.dyn4j.dynamics.joint",
    "org.dyn4j.exception", "org.dyn4j.geometry", "org.dyn4j.geometry.decompose",
    "org.dyn4j.geometry.hull", "org.dyn4j.geometry.simplify",
    "org.dyn4j.world", "org.dyn4j.world.listener", "org.dyn4j.world.result",
})
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "named_module"


def command(parts: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(parts, capture_output=True, text=True, check=False)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def descriptor(jar: Path) -> dict:
    result = command(["jar", "--describe-module", "--file", str(jar)])
    if result.returncode:
        raise ValueError(f"module descriptor cannot be read: {result.stderr.strip()}")
    lines = result.stdout.splitlines()
    explicit = not any("No module descriptor found" in line for line in lines)
    header = next((line for line in lines if re.match(r"^[A-Za-z][A-Za-z0-9_.]*(?:@[^ ]+)?\s", line)), "")
    name = header.split("@", 1)[0].split(" ", 1)[0] if header else ""
    exports = sorted(line.removeprefix("exports ") for line in lines if line.startswith("exports "))
    return {"passed": explicit and name == MODULE_NAME and set(exports) == EXPORTS
            and len(exports) == len(EXPORTS), "explicit": explicit, "name": name,
            "exports": exports, "descriptor_lines": lines[1:]}


def provider_check(jar: Path, dependencies: list[Path], expected_sha256: str | None) -> dict:
    providers = []
    expected_path = str(jar.resolve())
    for path in [jar, *dependencies]:
        resolved = path.resolve()
        if not resolved.is_file():
            return {"passed": False, "reason": "unreadable module-path entry",
                    "expected_path": expected_path, "expected_sha256": expected_sha256,
                    "entry": str(resolved), "providers": providers}
        result = command(["jar", "--describe-module", "--file", str(resolved), "--release", "21"])
        if result.returncode:
            return {"passed": False, "reason": "unreadable module-path entry",
                    "expected_path": expected_path, "expected_sha256": expected_sha256,
                    "entry": str(resolved), "error": result.stderr.strip(), "providers": providers}
        header = next((line for line in result.stdout.splitlines()
                       if re.match(r"^[A-Za-z][A-Za-z0-9_.]*(?:@[^ ]+)?\s", line)), "")
        name = header.split("@", 1)[0].split(" ", 1)[0] if header else ""
        if name == MODULE_NAME:
            providers.append({"path": str(resolved), "sha256": digest(resolved)})
    reason = ("duplicate org.dyn4j providers" if len(providers) > 1 else
              "expected org.dyn4j provider missing" if len(providers) == 0 else
              "wrong org.dyn4j provider path" if providers[0]["path"] != expected_path else
              "expected provider SHA-256 required" if expected_sha256 is None else
              "expected provider SHA-256 mismatch" if providers[0]["sha256"] != expected_sha256 else
              "single org.dyn4j provider")
    return {"passed": reason == "single org.dyn4j provider", "reason": reason,
            "expected_path": expected_path, "expected_sha256": expected_sha256,
            "providers": providers}


def probe(jar: Path, mode: str, dependencies: list[Path] | None = None,
          java8_java: Path | None = None, expected_provider_sha256: str | None = None) -> dict:
    dependencies = dependencies or []
    if mode == "module-descriptor":
        return descriptor(jar)
    if mode not in {"named-module-consumer", "java8-classpath"}:
        raise ValueError(f"unknown module probe: {mode}")
    check = provider_check(jar, dependencies, expected_provider_sha256) if mode == "named-module-consumer" else None
    if check is not None and not check["passed"]:
        return {"passed": False, "compile_release": 9, "compile_exit_code": None,
                "run_exit_code": None, "output": "", "java_version": "", "provider_check": check}
    with tempfile.TemporaryDirectory(prefix="dyn4k-module-probe-") as directory:
        classes = Path(directory) / "classes"
        classes.mkdir()
        main = FIXTURE / "example" / "Main.java"
        if mode == "named-module-consumer":
            path = os.pathsep.join(str(part) for part in [jar, *dependencies])
            compile_result = command(["javac", "--release", "9", "--module-path", path,
                                      "-d", str(classes), str(FIXTURE / "module-info.java"), str(main)])
            run_result = (command(["java", "--module-path", os.pathsep.join([path, str(classes)]),
                                   "-m", "dyn4k.migration.probe/example.Main"])
                          if compile_result.returncode == 0 else None)
            version = command(["java", "-version"])
        else:
            if java8_java is None:
                raise ValueError("Java 8 runtime path is required")
            version = command([str(java8_java), "-version"])
            if not re.search(r'\bversion "(?:1\.8\.|8(?:\.|"))', version.stderr + version.stdout):
                raise ValueError("classpath runtime is not Java 8")
            path = os.pathsep.join(str(part) for part in [jar, *dependencies])
            compile_result = command(["javac", "--release", "8", "-cp", path,
                                      "-d", str(classes), str(main)])
            run_result = (command([str(java8_java), "-cp", os.pathsep.join([path, str(classes)]),
                                   "example.Main"])
                          if compile_result.returncode == 0 else None)
        observed = {"passed": compile_result.returncode == 0 and run_result is not None
                and run_result.returncode == 0 and run_result.stdout.strip() == "Named module consumer passed",
                "compile_release": 9 if mode == "named-module-consumer" else 8,
                "compile_exit_code": compile_result.returncode,
                "run_exit_code": run_result.returncode if run_result else None,
                "output": run_result.stdout if run_result else "",
                "java_version": (version.stderr + version.stdout).splitlines()[0] if version.stderr or version.stdout else ""}
        if check is not None:
            observed["provider_check"] = check
        return observed


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe a staged JVM module with unchanged Java consumers.")
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--mode", choices=("module-descriptor", "named-module-consumer", "java8-classpath"),
                        required=True)
    parser.add_argument("--dependency", type=Path, action="append", default=[])
    parser.add_argument("--java8-java", type=Path)
    parser.add_argument("--expected-provider-sha256", help="required independent SHA-256 for a named-module consumer pass")
    parser.add_argument("--ledger", type=Path, default=Path("tools/compatibility/declaration-ledger.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = probe(args.jar, args.mode, args.dependency, args.java8_java,
                   args.expected_provider_sha256)
    if args.output:
        if args.output.exists():
            parser.error("evidence report exists; refusing to overwrite it")
        if not result["passed"]:
            parser.error("probe failed; refusing to record passed evidence")
        root = Path.cwd().resolve()
        ledger = json.loads(args.ledger.read_text())
        module = ledger["module"]
        candidate = module.get("candidate")
        revision = command(["git", "rev-parse", "HEAD"]).stdout.strip()
        if (not isinstance(candidate, dict) or candidate.get("identity") != MODULE_NAME
                or candidate.get("commit") != revision or candidate.get("artifact_sha256") != digest(args.jar)
                or not isinstance(candidate.get("artifact"), str)
                or (root / candidate["artifact"]).resolve() != args.jar.resolve()
                or digest(args.jar) == ledger["baseline"]["binary_sha256"]):
            parser.error("staged JAR does not match the current module ledger mapping")
        if any(digest(path) == ledger["baseline"]["binary_sha256"] for path in args.dependency):
            parser.error("baseline JAR cannot appear in candidate dependencies")
        report = {"schema_version": 1, "kind": args.mode, "baseline": ledger["baseline"],
                  "candidate_identity": MODULE_NAME,
                  "candidate_commit": revision,
                  "artifact_sha256": digest(args.jar), "source_sha256": module["sha256"],
                  "fixture_sha256": module["fixture_sha256"],
                  "dependencies": [{"path": str(path.resolve().relative_to(root)), "sha256": digest(path)}
                                   for path in args.dependency], "observed": result}
        if args.mode == "java8-classpath":
            report["java8_java"] = str(args.java8_java.resolve())
            report["java8_java_sha256"] = digest(args.java8_java)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(f"report SHA-256: {digest(args.output)}")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
