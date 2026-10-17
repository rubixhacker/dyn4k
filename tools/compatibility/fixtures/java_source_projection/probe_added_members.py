import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_for(record: dict, index: int) -> tuple[str, str, str]:
    owner = record["declaring_type"]
    package, _, simple = owner.rpartition(".")
    name = f"ProjectionProbe{index:02d}"
    header = f"package {package};\n\n"
    if record["kind"] == "field" and record["declaration"].endswith(" Companion;"):
        body = (
            f"import static {owner}.*;\nimport static extra.Names.*;\n\n"
            f"public final class {name} {{\n"
            "    public static void main(String[] args) {\n"
            "        if (!\"existing consumer field\".equals(Companion)) throw new AssertionError();\n"
            "    }\n}\n"
        )
        return package, name, header + body
    if " getEntries(" in record["declaration"]:
        body = (
            f"import static {owner}.*;\nimport static extra.Names.*;\n\n"
            f"public final class {name} {{\n"
            "    public static void main(String[] args) {\n"
            "        if (!\"existing consumer method\".equals(getEntries())) throw new AssertionError();\n"
            "    }\n}\n"
        )
        return package, name, header + body
    if simple in {"DynamicAABBTreeNode", "SegmentTreeNode", "SimplePolygonVertex"}:
        match = re.search(r"\b(\w+)\(([^()]*)\)", record["declaration"])
        if match is None:
            raise ValueError(record)
        method, parameter = match.groups()
        declaration = f"{parameter} value" if parameter else ""
        argument = "0" if parameter == "int" else "null"
        call = f"{method}({argument if parameter else ''})"
        constructor = ("super(0, new org.dyn4j.geometry.Vector2());" if
                       simple == "SimplePolygonVertex" else "super();")
        body = (
            f"public final class {name} extends {simple} {{\n"
            f"    public {name}() {{ {constructor} }}\n"
            f"    public String {method}({declaration}) {{ return \"existing consumer method\"; }}\n"
            "    public static void main(String[] args) {\n"
            f"        if (!\"existing consumer method\".equals(new {name}().{call})) throw new AssertionError();\n"
            "    }\n}\n"
        )
        return package, name, header + body
    raise ValueError(f"source-nameable record was not classified: {record}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", action="append", required=True,
                        help="name=archive path")
    parser.add_argument("--stdlib", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--jdk8", type=Path, required=True)
    parser.add_argument("--jdk21", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()

    records = [item for item in json.loads(args.audit.read_text())["added_member_risks"]
               if item["origin"] == "declared"]
    if len(records) != 98:
        raise ValueError(f"expected 98 distinct declarations, found {len(records)}")
    visible = [item for item in records if
               item["declaration"].endswith(" Companion;") or
               " getEntries(" in item["declaration"] or
               item["declaring_type"].rsplit(".", 1)[-1] in
               {"DynamicAABBTreeNode", "SegmentTreeNode", "SimplePolygonVertex"}]
    if len(visible) != 77:
        raise ValueError(f"expected 77 Java-source-nameable declarations, found {len(visible)}")
    source_root = args.work / "sources"
    source_root.mkdir(parents=True, exist_ok=True)
    fixture_root = Path(__file__).parent
    node_dispatch = fixture_root / "org/dyn4j/geometry/simplify/NodeDispatchProbe.java"
    sources = [fixture_root / "extra" / "Names.java", node_dispatch]
    mains = []
    for index, record in enumerate(visible, 1):
        package, name, contents = source_for(record, index)
        source = source_root / package.replace(".", "/") / f"{name}.java"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(contents)
        sources.append(source)
        mains.append(f"{package}.{name}")
    suite = source_root / "projection" / "Suite.java"
    suite.parent.mkdir(parents=True, exist_ok=True)
    suite.write_text("package projection;\npublic final class Suite {\n"
                     "    public static void main(String[] args) {\n" +
                     "".join(f"        {name}.main(args);\n" for name in mains) +
                     "        org.dyn4j.geometry.simplify.NodeDispatchProbe.main(args);\n" +
                     f"        System.out.println(\"ACTUAL_PROBES={len(mains)}\");\n"
                     "    }\n}\n")
    sources.append(suite)

    providers = {"baseline": args.baseline}
    for entry in args.candidate:
        name, sep, path = entry.partition("=")
        if not sep or name in providers:
            raise ValueError(f"invalid provider: {entry}")
        providers[name] = Path(path)
    observations = []
    for provider, jar in providers.items():
        for compiler, jdk in (("jdk8", args.jdk8), ("jdk21", args.jdk21)):
            destination = args.work / f"classes-{provider}-{compiler}"
            destination.mkdir(parents=True, exist_ok=True)
            classpath = ":".join(map(str, (jar, args.stdlib, args.annotations)))
            compile_command = [str(jdk / "bin" / "javac")]
            if compiler == "jdk21":
                compile_command += ["--release", "8"]
            compile_command += ["-cp", classpath, "-d", str(destination)]
            compile_command += [str(source) for source in sources]
            compiled = subprocess.run(compile_command, capture_output=True, text=True,
                                      timeout=120)
            (args.work / f"compile-{provider}-{compiler}.log").write_text(
                compiled.stdout + compiled.stderr)
            if compiled.returncode:
                raise SystemExit(f"{provider} {compiler} compilation failed: {compiled.stderr}")
            for runtime, runtime_jdk in (("jdk8", args.jdk8), ("jdk21", args.jdk21)):
                executed = subprocess.run(
                    [str(runtime_jdk / "bin" / "java"), "-cp",
                     f"{destination}:{classpath}", "projection.Suite"],
                    capture_output=True, text=True, timeout=120)
                (args.work / f"run-{provider}-{compiler}-{runtime}.log").write_text(
                    executed.stdout + executed.stderr)
                if executed.returncode or executed.stdout.strip() != "(1.0, 2.0)\nACTUAL_PROBES=77":
                    raise SystemExit(f"{provider} {compiler} {runtime} failed: "
                                     f"{executed.stdout}{executed.stderr}")
                observations.append({"provider": provider, "compiler": compiler,
                                     "runtime": runtime, "probes": 77,
                                     "run_log_sha256": digest(args.work / f"run-{provider}-{compiler}-{runtime}.log")})
    source_hashes = {"extra/Names.java": digest(sources[0]),
                     str(node_dispatch.relative_to(fixture_root)): digest(node_dispatch)}
    source_hashes.update({str(path.relative_to(source_root)): digest(path)
                          for path in sources[2:]})
    result = {"audit_sha256": digest(args.audit), "source_count": len(sources),
              "source_sha256": source_hashes,
              "providers": {name: digest(path) for name, path in providers.items()},
              "observations": observations}
    (args.work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"{len(visible)} adverse Java-source probes and one node dispatch control "
          f"passed for {len(providers)} providers, 2 compilers, and 2 runtimes")


if __name__ == "__main__":
    main()
