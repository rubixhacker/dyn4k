#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import check_links


ROOT = Path(__file__).resolve().parents[2]
GUIDE = Path(__file__).with_name("migration.md")
VERSION = "0.1.0-alpha.1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("staged_repository", type=Path)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()

    staged_repository = args.staged_repository.resolve()
    if not staged_repository.is_dir():
        parser.error(f"staged repository does not exist: {staged_repository}")
    version_path = Path("io/github/rubixhacker")
    version = Path(VERSION)
    required_artifacts = (
        version_path / "dyn4k" / version / f"dyn4k-{VERSION}.module",
        version_path / "dyn4k-jvm" / version / f"dyn4k-jvm-{VERSION}.module",
        version_path / "dyn4k-jvm" / version / f"dyn4k-jvm-{VERSION}.jar",
        version_path / "dyn4k-core-jvm" / version / f"dyn4k-core-jvm-{VERSION}.jar",
    )
    missing_artifacts = [
        str(artifact) for artifact in required_artifacts if not (staged_repository / artifact).is_file()
    ]
    if missing_artifacts:
        parser.error("staged JVM artifacts are missing: " + ", ".join(missing_artifacts))
    guide = GUIDE.read_text(encoding="utf-8")
    errors = check_links.check_assignment_example(guide)
    if errors:
        parser.error("; ".join(errors))
    source = check_links.assignment_example_code(guide)
    if source is None:
        parser.error("Kotlin assignment example is missing")

    settings = "\n".join((
        "pluginManagement {",
        "    repositories {",
        "        mavenCentral()",
        "        gradlePluginPortal()",
        "    }",
        "}",
        "",
        'rootProject.name = "dyn4k-guide-example"',
        "",
    ))
    build = "\n".join((
        "plugins {",
        '    kotlin("jvm") version "2.4.20"',
        "    application",
        "}",
        "",
        "repositories {",
        '    maven { url = uri(providers.gradleProperty("stagedRepository").get()) }',
        "    mavenCentral()",
        "}",
        "",
        "dependencies {",
        f'    implementation("io.github.rubixhacker:dyn4k:{VERSION}")',
        "}",
        "",
        'application { mainClass = "guide.example.VectorAssignmentKt" }',
        "",
    ))

    with tempfile.TemporaryDirectory(prefix="dyn4k-guide-example-") as temporary:
        project = Path(temporary)
        source_path = project / "src/main/kotlin/guide/example/VectorAssignment.kt"
        source_path.parent.mkdir(parents=True)
        source_path.write_text(source + "\n", encoding="utf-8")
        (project / "settings.gradle.kts").write_text(settings, encoding="utf-8")
        (project / "build.gradle.kts").write_text(build, encoding="utf-8")
        task = "run" if args.run else "compileKotlin"
        command = [
            str(ROOT / "gradlew"),
            "-p",
            str(project),
            task,
            f"-PstagedRepository={staged_repository}",
            "--offline",
            "--rerun-tasks",
            "--console=plain",
        ]
        result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode == 0:
        mode = "ran" if args.run else "compiled"
        print(f"GUIDE_EXAMPLE_{mode.upper()} gav=io.github.rubixhacker:dyn4k:{VERSION}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
