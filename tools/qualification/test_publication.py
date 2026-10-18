import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import qualify
import stage
import publication


class PublicationAuditTests(unittest.TestCase):
    REPOSITORY = Path(__file__).resolve().parents[2]

    def stage(self, root, targets=("jvm", "js")):
        license_bytes = b"Fixture license\n"
        (root / "LICENSE.md").write_bytes(license_bytes)
        staging = root / "build/staging-repository"
        names = [module for module in qualify.MODULES]
        names += [qualify.target_publication_name(module, target)
                  for module in qualify.MODULES for target in targets]
        for name in names:
            base = staging / qualify.GROUP.replace(".", "/") / name / qualify.VERSION
            base.mkdir(parents=True)
            module = "dyn4k-core" if name.startswith("dyn4k-core") else "dyn4k"
            target = None if name == module else next(
                target for target in targets if qualify.target_publication_name(module, target) == name)
            dependencies_xml = []
            if module == "dyn4k":
                dependencies_xml.append((qualify.GROUP, name.replace("dyn4k", "dyn4k-core", 1), qualify.VERSION))
            if target == "js":
                dependencies_xml.append(("org.jetbrains.kotlin", "kotlin-dom-api-compat", "2.4.20"))
            stdlib = ("kotlin-stdlib-js" if target == "js" else
                      "kotlin-stdlib-wasm-js" if target == "wasmJs" else
                      "kotlin-stdlib-wasm-wasi" if target == "wasmWasi" else "kotlin-stdlib")
            dependencies_xml.append(("org.jetbrains.kotlin", stdlib, "2.4.20"))
            dependency = "<dependencies>" + "".join(
                f"<dependency><groupId>{group}</groupId><artifactId>{artifact}</artifactId>"
                f"<version>{version}</version><scope>{'runtime' if target is None else 'compile'}</scope></dependency>"
                for group, artifact, version in dependencies_xml) + "</dependencies>"
            packaging = ("" if target in (None, "jvm") else
                         f"<packaging>{'aar' if target == 'android' else 'klib'}</packaging>")
            title = "dyn4k core" if module == "dyn4k-core" else "dyn4k"
            description = ("Kotlin Multiplatform dyn4j 6.0.0 compatible foundation"
                           if module == "dyn4k-core" else "Kotlin conveniences for the dyn4k core")
            pom = (f'<project xmlns="http://maven.apache.org/POM/4.0.0">'
                   '<modelVersion>4.0.0</modelVersion>'
                   f'<groupId>{qualify.GROUP}</groupId><artifactId>{name}</artifactId>'
                   f'<version>{qualify.VERSION}</version>' + packaging + f'<name>{title}</name>'
                   f'<description>{description}</description>'
                   '<url>https://github.com/rubixhacker/dyn4k</url>'
                   '<licenses><license><name>BSD 3-Clause License</name>'
                   '<url>https://opensource.org/licenses/BSD-3-Clause</url></license></licenses>'
                   '<developers><developer><id>rubixhacker</id>'
                   '<name>Stewart Boling</name></developer></developers>'
                   '<scm><url>https://github.com/rubixhacker/dyn4k</url></scm>'
                   + dependency + '</project>')
            self.write(base / f"{name}-{qualify.VERSION}.pom", pom.encode())
            binary = qualify.publication_binary_path(module, None if name == module else
                                                     next(target for target in targets if
                                                          qualify.target_publication_name(module, target) == name))
            with tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / "archive.jar"
                with zipfile.ZipFile(archive, "w") as jar:
                    if target in qualify.APPLE_TARGETS:
                        jar.writestr("default/manifest", b"unique_name=fixture\n")
                        jar.writestr("default/linkdata/module", b"module")
                        jar.writestr("default/linkdata/package_api/0_api.knm", b"metadata")
                        jar.writestr("default/ir/bodies.knb", b"ir")
                    else:
                        jar.writestr("META-INF/LICENSE.md", license_bytes)
                        jar.writestr("api/Type.class", b"class")
                self.write(staging / binary, archive.read_bytes())
                with zipfile.ZipFile(archive, "w") as jar:
                    jar.writestr("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\r\n\r\n")
                    jar.writestr("commonMain/api/Type.kt", "// Fixture notice\npackage api\nclass Type\n")
                self.write(base / f"{name}-{qualify.VERSION}-sources.jar", archive.read_bytes())
                with zipfile.ZipFile(archive, "w") as jar:
                    jar.writestr("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\r\n\r\n")
                    jar.writestr("META-INF/LICENSE.md", license_bytes)
                    jar.writestr("index.html", "<html><body>Type API</body></html>")
                    jar.writestr("api/Type/index.html", "<html><body>Type members</body></html>")
                self.write(base / f"{name}-{qualify.VERSION}-javadoc.jar", archive.read_bytes())
            source_tree = root / module / "src/commonMain/kotlin/api/Type.kt"
            source_tree.parent.mkdir(parents=True, exist_ok=True)
            source_tree.write_text("// Fixture notice\npackage api\nclass Type\n")
            docs_tree = root / module / "build/dokka/html"
            (docs_tree / "api/Type").mkdir(parents=True, exist_ok=True)
            (docs_tree / "index.html").write_text("<html><body>Type API</body></html>")
            (docs_tree / "api/Type/index.html").write_text("<html><body>Type members</body></html>")
            self.write(base / f"{name}-{qualify.VERSION}-license.md", license_bytes)
            if target in qualify.APPLE_TARGETS:
                with tempfile.TemporaryDirectory() as temporary:
                    archive = Path(temporary) / "metadata.jar"
                    with zipfile.ZipFile(archive, "w") as jar:
                        jar.writestr("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\r\n\r\n")
                    self.write(base / f"{name}-{qualify.VERSION}-metadata.jar", archive.read_bytes())
            prefix = "metadata" if target is None else target
            variant_name = lambda kind: f"{prefix}{kind}Elements" + ("-published" if target else "")
            def referenced(path):
                return {"name": path.name, "url": path.name, "size": path.stat().st_size,
                        **{algorithm: hashlib.new(algorithm, path.read_bytes()).hexdigest()
                           for algorithm in ("sha512", "sha256", "sha1", "md5")}}
            dependencies = [{"group": "org.jetbrains.kotlin", "module": "kotlin-stdlib",
                             "version": {"requires": "2.4.20"}}]
            if target == "js":
                dependencies.append({"group": "org.jetbrains.kotlin", "module": "kotlin-dom-api-compat",
                                     "version": {"requires": "2.4.20"}})
            if module == "dyn4k":
                dependencies.append({"group": qualify.GROUP, "module": "dyn4k-core",
                                     "version": {"requires": qualify.VERSION}})
            suffix = f"{name}-{qualify.VERSION}"
            extension = ".jar" if target in (None, "jvm") else ".aar" if target == "android" else ".klib"
            binary_reference = referenced(base / (suffix + extension))
            source_reference = referenced(base / (suffix + "-sources.jar"))
            if target is None:
                binary_reference["name"] = f"{module}-metadata-{qualify.VERSION}.jar"
                source_reference["name"] = f"{module}-kotlin-{qualify.VERSION}-sources.jar"
            elif target == "android":
                binary_reference["name"] = f"{module}.aar"
            elif target not in ("jvm", "js", "wasmJs", "wasmWasi"):
                binary_reference["name"] = f"{module}-{target}Main-{qualify.VERSION}.klib"
            variants = [{"name": variant_name("Api"), "attributes": qualify.variant_attributes(target, "Api"),
                         "dependencies": dependencies,
                         "files": [binary_reference]},
                        {"name": variant_name("Sources"),
                         "attributes": qualify.variant_attributes(target, "Sources"),
                         "files": [source_reference]}]
            if target in ("jvm", "android", "js", "wasmJs", "wasmWasi"):
                variants.insert(1, {"name": variant_name("Runtime"),
                                    "attributes": qualify.variant_attributes(target, "Runtime"),
                                    "dependencies": dependencies,
                                    "files": [binary_reference]})
            if target in qualify.APPLE_TARGETS:
                variants.append({"name": variant_name("Metadata"),
                                 "attributes": qualify.variant_attributes(target, "Metadata"),
                                 "dependencies": dependencies,
                                 "files": [referenced(base / (suffix + "-metadata.jar"))]})
            if target is None:
                for mapped in sorted(qualify.matrix_targets()):
                    mapped_name = qualify.target_publication_name(module, mapped)
                    available = {"group": qualify.GROUP, "module": mapped_name,
                                 "version": qualify.VERSION,
                                 "url": f"../../{mapped_name}/{qualify.VERSION}/{mapped_name}-{qualify.VERSION}.module"}
                    kinds = ["Api", "Sources"]
                    if mapped in ("jvm", "android", "js", "wasmJs", "wasmWasi"):
                        kinds.append("Runtime")
                    if mapped in qualify.APPLE_TARGETS:
                        kinds.append("Metadata")
                    variants.extend({"name": f"{mapped}{kind}Elements-published",
                                     "attributes": qualify.variant_attributes(mapped, kind),
                                     "available-at": available}
                                    for kind in kinds)
            component = {"group": qualify.GROUP, "module": module,
                         "version": qualify.VERSION}
            if target is not None:
                component["url"] = f"../../{module}/{qualify.VERSION}/{module}-{qualify.VERSION}.module"
            self.write(base / f"{name}-{qualify.VERSION}.module", json.dumps({
                "formatVersion": "1.1", "component": component, "variants": variants}).encode())
        return staging

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.with_name(path.name + ".sha256").write_text(hashlib.sha256(content).hexdigest() + "\n")

    def publication_command(self, tasks):
        wrapper = "gradlew.bat" if os.name == "nt" else "gradlew"
        return [str(self.REPOSITORY / wrapper),
                "--no-daemon", "--console=plain", *tasks]

    def test_selected_target_audit_accepts_exact_published_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = self.stage(root)
            audit = qualify.audit_staging(staging, "a" * 40, targets=("jvm", "js"), license_file=root / "LICENSE.md")
            self.assertEqual("PASSED", audit["status"], audit["errors"])

    def test_jvm_module_descriptor_matches_only_committed_core_jvm_source(self):
        descriptor = b"module org.dyn4j { exports org.dyn4j; }\n"
        source = b"package api\nclass Type\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for module in qualify.MODULES:
                path = root / module / "src/commonMain/kotlin/api/Type.kt"
                path.parent.mkdir(parents=True)
                path.write_bytes(source)
            descriptor_path = root / "dyn4k-core/src/jvmModule/java/module-info.java"
            descriptor_path.parent.mkdir(parents=True)
            descriptor_path.write_bytes(descriptor)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "dyn4k-core", "dyn4k"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "-qm", "candidate"],
                           check=True)
            candidate = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                                text=True).strip()
            contract = qualify.candidate_source_contract(root, candidate)
            expected = qualify.expected_source_entries(contract, "dyn4k-core", "jvm")
            self.assertEqual(hashlib.sha256(descriptor).hexdigest(),
                             expected["jvmModule/module-info.java"])
            self.assertNotIn("jvmModule/module-info.java",
                             qualify.expected_source_entries(contract, "dyn4k-core", "js"))
            self.assertNotIn("jvmModule/module-info.java",
                             qualify.expected_source_entries(contract, "dyn4k", "jvm"))

            archive = root / "sources.jar"
            manifest = b"Manifest-Version: 1.0\r\n\r\n"
            common = "commonMain/api/Type.kt"
            descriptor_name = "jvmModule/module-info.java"
            def write_archive(entries):
                with zipfile.ZipFile(archive, "w") as jar:
                    jar.writestr("META-INF/MANIFEST.MF", manifest)
                    for name, contents in entries.items():
                        jar.writestr(name, contents)

            write_archive({common: source, descriptor_name: descriptor})
            qualify.validate_source_archive(archive, expected)
            for entries in ({common: source},
                            {common: source, descriptor_name: descriptor + b"changed"},
                            {common: source, descriptor_name: descriptor,
                             "jvmModule/extra.java": b"class Extra {}\n"},
                            {common: source + b"changed", descriptor_name: descriptor}):
                write_archive(entries)
                with self.assertRaisesRegex(ValueError, "exact candidate source tree"):
                    qualify.validate_source_archive(archive, expected)
            write_archive({common: source, descriptor_name: descriptor})
            for module, target in (("dyn4k-core", "js"), ("dyn4k", "jvm")):
                with self.subTest(module=module, target=target):
                    with self.assertRaisesRegex(ValueError, "exact candidate source tree"):
                        qualify.validate_source_archive(
                            archive, qualify.expected_source_entries(contract, module, target))

    def test_pom_dependency_attributes_reject_coherent_scope_and_transitivity_changes(self):
        for mutation in ("test_scope", "runtime_scope", "optional", "type", "classifier",
                         "exclusion", "unknown_attribute"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                staging = self.stage(root)
                base = staging / "io/github/rubixhacker/dyn4k-jvm" / qualify.VERSION
                pom = base / f"dyn4k-jvm-{qualify.VERSION}.pom"
                contents = pom.read_text()
                core = f"<artifactId>dyn4k-core-jvm</artifactId><version>{qualify.VERSION}</version>"
                extras = {
                    "test_scope": "<scope>test</scope>",
                    "runtime_scope": "<scope>runtime</scope>",
                    "optional": "<scope>compile</scope><optional>true</optional>",
                    "type": "<scope>compile</scope><type>pom</type>",
                    "classifier": "<scope>compile</scope><classifier>tests</classifier>",
                    "exclusion": ("<scope>compile</scope><exclusions><exclusion>"
                                  "<groupId>org.jetbrains.kotlin</groupId><artifactId>kotlin-stdlib</artifactId>"
                                  "</exclusion></exclusions>"),
                    "unknown_attribute": "<scope>compile</scope><systemPath>/tmp/core.jar</systemPath>",
                }
                self.write(pom, contents.replace(core + "<scope>compile</scope>", core + extras[mutation]).encode())
                audit = qualify.audit_staging(staging, "a" * 40, ("jvm", "js"), root / "LICENSE.md")
                self.assertEqual("FAILED", audit["status"], (mutation, audit["errors"]))

    def test_pom_effective_dependency_overrides_are_rejected(self):
        core = (f"<dependency><groupId>{qualify.GROUP}</groupId>"
                f"<artifactId>dyn4k-core-jvm</artifactId><version>{qualify.VERSION}</version>"
                "<scope>test</scope></dependency>")
        overrides = {
            "active_profile_test_scope": (
                "<profiles><profile><id>override-core</id><activation>"
                "<activeByDefault>true</activeByDefault></activation>"
                f"<dependencies>{core}</dependencies></profile></profiles>"),
            "dependency_management": f"<dependencyManagement><dependencies>{core}</dependencies></dependencyManagement>",
            "parent": ("<parent><groupId>org.example</groupId><artifactId>parent</artifactId>"
                       "<version>1</version></parent>"),
            "properties": "<properties><core.scope>test</core.scope></properties>",
            "duplicate_dependencies_block": f"<dependencies>{core}</dependencies>",
        }
        for mutation, override in overrides.items():
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                staging = self.stage(root)
                base = staging / "io/github/rubixhacker/dyn4k-jvm" / qualify.VERSION
                pom = base / f"dyn4k-jvm-{qualify.VERSION}.pom"
                self.write(pom, pom.read_text().replace("</project>", override + "</project>").encode())
                audit = qualify.audit_staging(staging, "a" * 40, ("jvm", "js"), root / "LICENSE.md")
                self.assertEqual("FAILED", audit["status"], (mutation, audit["errors"]))

    def pom_metadata_changes(self):
        title = "<name>dyn4k</name>"
        description = "<description>Kotlin conveniences for the dyn4k core</description>"
        project_url = "<url>https://github.com/rubixhacker/dyn4k</url>"
        license_section = ("<licenses><license><name>BSD 3-Clause License</name>"
                           "<url>https://opensource.org/licenses/BSD-3-Clause</url></license></licenses>")
        developer_section = ("<developers><developer><id>rubixhacker</id>"
                             "<name>Stewart Boling</name></developer></developers>")
        scm_section = "<scm><url>https://github.com/rubixhacker/dyn4k</url></scm>"
        return {
            "empty_license": (license_section, "<licenses/>"),
            "wrong_license_name": (license_section, license_section.replace("BSD 3-Clause License", "Wrong License")),
            "wrong_license_url": (license_section, license_section.replace("opensource.org", "example.invalid")),
            "missing_license_url": (license_section, license_section.replace(
                "<url>https://opensource.org/licenses/BSD-3-Clause</url>", "")),
            "duplicate_license": (license_section, license_section.replace("</licenses>",
                "<license><name>Other</name><url>https://example.invalid</url></license></licenses>")),
            "unsupported_license_distribution": (license_section, license_section.replace(
                "</license>", "<distribution>repo</distribution></license>")),
            "empty_name": (title, "<name/>"),
            "wrong_name": (title, "<name>Other library</name>"),
            "wrong_description": (description, "<description>Other library</description>"),
            "wrong_project_url": (project_url, "<url>https://example.invalid</url>"),
            "empty_developers": (developer_section, "<developers/>"),
            "wrong_developer_id": (developer_section, developer_section.replace("rubixhacker", "other")),
            "wrong_developer_name": (developer_section, developer_section.replace("Stewart Boling", "Other")),
            "duplicate_developer": (developer_section, developer_section.replace(
                "</developers>", "<developer><id>other</id><name>Other</name></developer></developers>")),
            "unsupported_developer_field": (developer_section, developer_section.replace(
                "</developer>", "<organization>Other</organization></developer>")),
            "empty_scm": (scm_section, "<scm/>"),
            "wrong_scm_url": (scm_section, "<scm><url>https://example.invalid</url></scm>"),
            "unsupported_scm_connection": (scm_section, scm_section.replace(
                "</scm>", "<connection>scm:git:other</connection></scm>")),
        }

    def test_pom_metadata_requires_approved_values_and_complete_sections(self):
        for label, (before, after) in self.pom_metadata_changes().items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                staging = self.stage(root)
                pom = (staging / qualify.GROUP.replace(".", "/") / "dyn4k-jvm" / qualify.VERSION /
                       f"dyn4k-jvm-{qualify.VERSION}.pom")
                content = pom.read_text()
                self.assertIn(before, content)
                self.write(pom, content.replace(before, after, 1).encode())
                audit = qualify.audit_staging(staging, "a" * 40, ("jvm", "js"), root / "LICENSE.md")
                self.assertEqual("FAILED", audit["status"], (label, audit["errors"]))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = self.stage(root)
            pom = (staging / qualify.GROUP.replace(".", "/") / "dyn4k-jvm" / qualify.VERSION /
                   f"dyn4k-jvm-{qualify.VERSION}.pom")
            self.write(pom, pom.read_text().replace("</project>",
                "<!-- harmless POM comment -->\n</project>").encode())
            audit = qualify.audit_staging(staging, "a" * 40, ("jvm", "js"), root / "LICENSE.md")
            self.assertEqual("PASSED", audit["status"], audit["errors"])

    def test_all_published_jvm_binary_jars_require_exact_embedded_license(self):
        for module in qualify.MODULES:
            for target in (None, "jvm"):
                with self.subTest(module=module, target=target), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    staging = self.stage(root)
                    name = module if target is None else qualify.target_publication_name(module, target)
                    base = staging / qualify.GROUP.replace(".", "/") / name / qualify.VERSION
                    binary = staging / qualify.publication_binary_path(module, target)
                    output = io.BytesIO()
                    with zipfile.ZipFile(binary) as original, zipfile.ZipFile(output, "w") as changed:
                        for member in original.infolist():
                            contents = (b"Wrong legal notice\n" if member.filename == "META-INF/LICENSE.md"
                                        else original.read(member.filename))
                            changed.writestr(member, contents)
                    self.write(binary, output.getvalue())
                    metadata = base / f"{name}-{qualify.VERSION}.module"
                    content = json.loads(metadata.read_text())
                    for variant in content["variants"]:
                        for file in variant.get("files", []):
                            if file["url"] == binary.name:
                                file.update(size=binary.stat().st_size,
                                    **{algorithm: hashlib.new(algorithm, binary.read_bytes()).hexdigest()
                                       for algorithm in ("sha512", "sha256", "sha1", "md5")})
                    self.write(metadata, json.dumps(content).encode())
                    audit = qualify.audit_staging(staging, "a" * 40, ("jvm", "js"), root / "LICENSE.md")
                    self.assertEqual("FAILED", audit["status"], (name, audit["errors"]))

    def test_gradle_format_and_all_advertised_hashes_reject_coherent_changes(self):
        for mutation in ("missing_format", "wrong_format", "missing_sha512", "wrong_sha512",
                         "missing_sha256", "wrong_sha256", "missing_sha1", "wrong_sha1",
                         "missing_md5", "wrong_md5"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                staging = self.stage(root)
                base = staging / "io/github/rubixhacker/dyn4k-core-jvm" / qualify.VERSION
                metadata = base / f"dyn4k-core-jvm-{qualify.VERSION}.module"
                content = json.loads(metadata.read_text())
                if mutation == "missing_format":
                    del content["formatVersion"]
                elif mutation == "wrong_format":
                    content["formatVersion"] = "9.9"
                else:
                    kind, algorithm = mutation.split("_", 1)
                    file = content["variants"][0]["files"][0]
                    if kind == "missing":
                        del file[algorithm]
                    else:
                        file[algorithm] = "0" * len(file[algorithm])
                self.write(metadata, json.dumps(content).encode())
                audit = qualify.audit_staging(staging, "a" * 40, ("jvm", "js"), root / "LICENSE.md")
                self.assertEqual("FAILED", audit["status"], (mutation, audit["errors"]))

    def test_apple_metadata_reference_checks_every_advertised_hash(self):
        for algorithm in ("sha512", "sha256", "sha1", "md5"):
            with self.subTest(algorithm=algorithm), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                staging = self.stage(root, ("iosArm64",))
                base = staging / "io/github/rubixhacker/dyn4k-core-iosarm64" / qualify.VERSION
                metadata = base / f"dyn4k-core-iosarm64-{qualify.VERSION}.module"
                content = json.loads(metadata.read_text())
                variant = next(v for v in content["variants"] if
                               v["name"] == "iosArm64MetadataElements-published")
                variant["files"][0][algorithm] = "0" * len(variant["files"][0][algorithm])
                self.write(metadata, json.dumps(content).encode())
                audit = qualify.audit_staging(staging, "a" * 40, ("iosArm64",), root / "LICENSE.md")
                self.assertEqual("FAILED", audit["status"], audit["errors"])

    def test_source_docs_and_apple_metadata_reject_coherent_content_changes(self):
        for mutation in ("fake_source", "missing_source", "fake_docs", "changed_docs_page",
                         "literal_apple_jar",
                         "missing_klib_metadata"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                targets = ("jvm", "iosArm64")
                staging = self.stage(root, targets)
                name = "dyn4k-core-iosarm64" if "apple" in mutation or "klib" in mutation else "dyn4k-core-jvm"
                base = staging / "io/github/rubixhacker" / name / qualify.VERSION
                prefix = f"{name}-{qualify.VERSION}"
                if mutation in ("fake_source", "missing_source"):
                    source = base / (prefix + "-sources.jar")
                    with zipfile.ZipFile(source, "w") as jar:
                        if mutation == "fake_source":
                            jar.writestr("commonMain/api/Type.kt", "package wrong\nclass Fake\n")
                        else:
                            jar.writestr("commonMain/api/Other.kt", "package api\nclass Other\n")
                    self.write(source, source.read_bytes())
                    metadata = base / (prefix + ".module")
                    content = json.loads(metadata.read_text())
                    selected = next(v for v in content["variants"] if v["name"] == "jvmSourcesElements-published")
                    selected["files"][0].update(size=source.stat().st_size,
                        **{algorithm: hashlib.new(algorithm, source.read_bytes()).hexdigest()
                           for algorithm in ("sha512", "sha256", "sha1", "md5")})
                    self.write(metadata, json.dumps(content).encode())
                elif mutation in ("fake_docs", "changed_docs_page"):
                    docs = base / (prefix + "-javadoc.jar")
                    with zipfile.ZipFile(docs, "w") as jar:
                        if mutation == "changed_docs_page":
                            jar.writestr("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\r\n\r\n")
                            jar.writestr("META-INF/LICENSE.md", b"Fixture license\n")
                            jar.writestr("index.html", "<html><body>Type API</body></html>")
                            jar.writestr("api/Type/index.html", "<html>wrong member</html>")
                        else:
                            jar.writestr("index.html", "<html>wrong API</html>")
                            jar.writestr("api/Wrong.html", "<html>wrong API</html>")
                    self.write(docs, docs.read_bytes())
                elif mutation == "literal_apple_jar":
                    apple = base / (prefix + "-metadata.jar")
                    self.write(apple, b"not a jar")
                    metadata = base / (prefix + ".module")
                    content = json.loads(metadata.read_text())
                    selected = next(v for v in content["variants"] if v["name"] == "iosArm64MetadataElements-published")
                    selected["files"][0].update(size=apple.stat().st_size,
                        **{algorithm: hashlib.new(algorithm, apple.read_bytes()).hexdigest()
                           for algorithm in ("sha512", "sha256", "sha1", "md5")})
                    self.write(metadata, json.dumps(content).encode())
                else:
                    binary = base / (prefix + ".klib")
                    with zipfile.ZipFile(binary, "w") as jar:
                        jar.writestr("default/manifest", b"unique_name=fixture\n")
                    self.write(binary, binary.read_bytes())
                    metadata = base / (prefix + ".module")
                    content = json.loads(metadata.read_text())
                    selected = next(v for v in content["variants"] if v["name"] == "iosArm64ApiElements-published")
                    selected["files"][0].update(size=binary.stat().st_size,
                        **{algorithm: hashlib.new(algorithm, binary.read_bytes()).hexdigest()
                           for algorithm in ("sha512", "sha256", "sha1", "md5")})
                    self.write(metadata, json.dumps(content).encode())
                audit = qualify.audit_staging(staging, "a" * 40, targets, root / "LICENSE.md")
                self.assertEqual("FAILED", audit["status"], (mutation, audit["errors"]))

    def test_selected_variant_reference_and_graph_reject_coherent_metadata_changes(self):
        for mutation in ("missing_url", "wrong_extension", "missing_file", "wrong_size", "wrong_hash",
                         "missing_variant", "wrong_target", "wrong_mapping", "wrong_dependency",
                         "wrong_pom_dependency", "wrong_selection"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                staging = self.stage(root)
                base = staging / "io/github/rubixhacker/dyn4k-core-jvm" / qualify.VERSION
                metadata = base / f"dyn4k-core-jvm-{qualify.VERSION}.module"
                content = json.loads(metadata.read_text())
                variant = content["variants"][0]
                if mutation == "missing_url":
                    variant["files"][0]["url"] = "missing-core-jvm.jar"
                elif mutation == "wrong_extension":
                    variant["files"][0]["url"] = f"dyn4k-core-jvm-{qualify.VERSION}.klib"
                elif mutation == "missing_file":
                    (base / variant["files"][0]["url"]).unlink()
                elif mutation == "wrong_size":
                    variant["files"][0]["size"] += 1
                elif mutation == "wrong_hash":
                    variant["files"][0]["sha256"] = "0" * 64
                elif mutation == "wrong_target":
                    content["component"]["module"] = "dyn4k-core-js"
                elif mutation == "missing_variant":
                    content["variants"].pop(0)
                elif mutation == "wrong_selection":
                    variant["attributes"]["org.jetbrains.kotlin.platform.type"] = "js"
                elif mutation == "wrong_mapping":
                    metadata = staging / "io/github/rubixhacker/dyn4k-core" / qualify.VERSION / (
                        f"dyn4k-core-{qualify.VERSION}.module")
                    content = json.loads(metadata.read_text())
                    next(item for item in content["variants"] if item["name"] == "jvmApiElements-published")[
                        "available-at"]["module"] = "dyn4k-core-js"
                elif mutation == "wrong_pom_dependency":
                    pom = staging / "io/github/rubixhacker/dyn4k-jvm" / qualify.VERSION / (
                        f"dyn4k-jvm-{qualify.VERSION}.pom")
                    inserted = ("<dependency><groupId>org.example</groupId>"
                                "<artifactId>unapproved</artifactId><version>1</version></dependency>")
                    self.write(pom, pom.read_text().replace("</dependencies>", inserted + "</dependencies>").encode())
                else:
                    variant["dependencies"][0]["module"] = "kotlin-test"
                self.write(metadata, json.dumps(content).encode())
                audit = qualify.audit_staging(staging, "a" * 40, ("jvm", "js"), root / "LICENSE.md")
                self.assertEqual("FAILED", audit["status"], mutation)

    def test_selected_target_audit_rejects_renamed_docs_and_wrong_extension(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = self.stage(root)
            base = staging / "io/github/rubixhacker/dyn4k-js" / qualify.VERSION
            docs = base / f"dyn4k-js-{qualify.VERSION}-javadoc.jar"
            docs.rename(base / f"dyn4k-js-{qualify.VERSION}-dokka-other.jar")
            wrong = staging / qualify.publication_binary_path("dyn4k", "js")
            wrong.rename(wrong.with_suffix(".jar"))
            audit = qualify.audit_staging(staging, "a" * 40, targets=("jvm", "js"), license_file=root / "LICENSE.md")
            self.assertEqual("FAILED", audit["status"])
            self.assertTrue(any("API documentation" in error for error in audit["errors"]))
            self.assertTrue(any("binary" in error for error in audit["errors"]))

    def test_selected_target_audit_rejects_mismatched_license_and_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = self.stage(root)
            base = staging / "io/github/rubixhacker/dyn4k-jvm" / qualify.VERSION
            license_path = base / f"dyn4k-jvm-{qualify.VERSION}-license.md"
            self.write(license_path, b"Different license\n")
            source = base / f"dyn4k-jvm-{qualify.VERSION}-sources.jar"
            source.write_bytes(source.read_bytes() + b"changed")
            audit = qualify.audit_staging(staging, "a" * 40, targets=("jvm", "js"), license_file=root / "LICENSE.md")
            self.assertEqual("FAILED", audit["status"])
            self.assertTrue(any("license differs" in error for error in audit["errors"]))
            self.assertTrue(any("SHA-256" in error for error in audit["errors"]))

    def test_selected_target_audit_rejects_empty_api_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = self.stage(root)
            docs = staging / "io/github/rubixhacker/dyn4k-jvm" / qualify.VERSION / (
                f"dyn4k-jvm-{qualify.VERSION}-javadoc.jar")
            with zipfile.ZipFile(docs, "w") as jar:
                jar.writestr("index.html", "<html></html>")
            self.write(docs, docs.read_bytes())
            audit = qualify.audit_staging(staging, "a" * 40, targets=("jvm", "js"),
                                          license_file=root / "LICENSE.md")
            self.assertEqual("FAILED", audit["status"])
            self.assertTrue(any("API documentation pages" in error for error in audit["errors"]))

    def test_stage_receipt_binds_candidate_task_outcomes_and_console_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            console = root / "stage.log"
            tasks = stage.publication_tasks(("jvm", "js"))
            console.write_text("".join(f"> Task {task}\n" for task in tasks) + "BUILD SUCCESSFUL\n")
            command = self.publication_command(tasks)
            receipt = {"candidate_sha": "a" * 40, "repository": str(self.REPOSITORY),
                       "targets": ["jvm", "js"],
                       "tasks": tasks, "command": command, "status": "PASSED", "exit_code": 0,
                       "console_sha256": hashlib.sha256(console.read_bytes()).hexdigest()}
            stage.verify_receipt(receipt, console, "a" * 40, ("jvm", "js"))
            windows_repository = "C:\\agent\\dyn4k"
            windows_command = [windows_repository + "\\gradlew.bat",
                               "--no-daemon", "--console=plain", *tasks]
            stage.verify_receipt({**receipt, "repository": windows_repository,
                                  "command": windows_command},
                                 console, "a" * 40, ("jvm", "js"), windows_repository)
            unc_repository = r"\\server\share\repo"
            stage.verify_receipt({**receipt, "repository": unc_repository,
                                  "command": [unc_repository + r"\gradlew.bat", *command[1:]]},
                                 console, "a" * 40, ("jvm", "js"))
            changed_command = (
                {key: value for key, value in receipt.items() if key != "command"},
                {key: value for key, value in receipt.items() if key != "repository"},
                {**receipt, "repository": "/tmp"},
                {**receipt, "repository": "/tmp/repo/../unrelated",
                 "command": ["/tmp/repo/../unrelated/gradlew", *command[1:]]},
                {**receipt, "repository": "/tmp/repo/./unrelated",
                 "command": ["/tmp/repo/./unrelated/gradlew", *command[1:]]},
                {**receipt, "repository": "//tmp/repo",
                 "command": ["//tmp/repo/gradlew", *command[1:]]},
                {**receipt, "repository": "C:\\agent\\dyn4k\\..\\unrelated",
                 "command": ["C:\\agent\\dyn4k\\..\\unrelated\\gradlew.bat", *command[1:]]},
                {**receipt, "repository": "C:\\agent\\dyn4k\\.\\unrelated",
                 "command": ["C:\\agent\\dyn4k\\.\\unrelated\\gradlew.bat", *command[1:]]},
                {**receipt, "repository": "C:\\agent\\dyn4k.\\unrelated",
                 "command": ["C:\\agent\\dyn4k.\\unrelated\\gradlew.bat", *command[1:]]},
                {**receipt, "repository": "C:\\agent\\dyn4k \\unrelated",
                 "command": ["C:\\agent\\dyn4k \\unrelated\\gradlew.bat", *command[1:]]},
                {**receipt, "repository": r"\\server\share.\repo",
                 "command": [r"\\server\share.\repo\gradlew.bat", *command[1:]]},
                {**receipt, "repository": r"\\server\share \repo",
                 "command": [r"\\server\share \repo\gradlew.bat", *command[1:]]},
                {**receipt, "command": ["false"]},
                {**receipt, "command": ["/tmp/gradlew", *command[1:]]},
                {**receipt, "command": [command[0], *command[2:]]},
                {**receipt, "command": [command[0], "--daemon", *command[2:]]},
                {**receipt, "command": [command[0], command[1], "--console=rich", *command[3:]]},
                {**receipt, "command": [*command[:3], command[4], command[3], *command[5:]]},
                {**receipt, "command": [*command[:4],
                                         ":dyn4k-core:publishAndroidPublicationToStagingRepository",
                                         *command[5:]]},
            )
            for changed in changed_command:
                with self.subTest(command=changed.get("command")):
                    with self.assertRaises(ValueError):
                        stage.verify_receipt(changed, console, "a" * 40, ("jvm", "js"))
            for changed in ({**receipt, "candidate_sha": "b" * 40},
                            {**receipt, "targets": ["jvm"]},
                            {**receipt, "tasks": tasks[:-1]},
                            {**receipt, "status": "FAILED"},
                            {**receipt, "exit_code": 1},
                            {**receipt, "console_sha256": "0" * 64}):
                with self.assertRaises(ValueError):
                    stage.verify_receipt(changed, console, "a" * 40, ("jvm", "js"))
            console.write_text(console.read_text().replace("> Task " + tasks[0],
                                                        "> Task " + tasks[0] + " SKIPPED"))
            receipt["console_sha256"] = hashlib.sha256(console.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                stage.verify_receipt(receipt, console, "a" * 40, ("jvm", "js"))

    def test_staging_audit_binds_receipt_to_actual_checkout_after_hash_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            targets = ("js", "jvm")
            staging = self.stage(root, targets)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "LICENSE.md",
                            "dyn4k-core/src", "dyn4k/src"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "-qm", "candidate"],
                           check=True)
            candidate = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                                text=True).strip()
            tasks = stage.publication_tasks(targets)
            stage_dir = staging / ".qualification/local"
            stage_dir.mkdir(parents=True)
            console = stage_dir / "stage.log"
            console.write_text("".join(f"> Task {task}\n" for task in tasks) + "BUILD SUCCESSFUL\n")
            wrapper = "gradlew.bat" if os.name == "nt" else "gradlew"
            receipt = {"candidate_sha": candidate, "repository": str(root),
                       "targets": list(targets), "tasks": tasks,
                       "command": [str(root / wrapper), "--no-daemon", "--console=plain", *tasks],
                       "status": "PASSED", "exit_code": 0,
                       "console_sha256": hashlib.sha256(console.read_bytes()).hexdigest()}
            receipt_path = stage_dir / "receipt.json"
            receipt_path.write_text(json.dumps(receipt))
            stage.verify_receipt(receipt, console, candidate, targets)
            audit = qualify.audit_staging(staging, candidate, targets, root / "LICENSE.md",
                                          receipt_path, console)
            self.assertEqual("PASSED", audit["status"], audit["errors"])

            false_repository = str(root.parent / "false-checkout")
            receipt["repository"] = false_repository
            receipt["command"][0] = str(Path(false_repository) / wrapper)
            receipt_path.write_text(json.dumps(receipt))
            next(item for item in audit["artifacts"]
                 if item["path"] == ".qualification/local/receipt.json")["sha256"] = (
                     hashlib.sha256(receipt_path.read_bytes()).hexdigest())
            with self.assertRaisesRegex(ValueError, "staging receipt repository differs"):
                stage.verify_receipt(receipt, console, candidate, targets)
            failed = qualify.audit_staging(staging, candidate, targets, root / "LICENSE.md",
                                           receipt_path, console)
            self.assertEqual("FAILED", failed["status"])
            self.assertTrue(any("staging receipt repository differs" in error
                                for error in failed["errors"]), failed["errors"])
            with self.assertRaisesRegex(ValueError, "staged audit differs"):
                qualify.verify_audit_against_staging(audit, root, allow_pinned_content_contract=True)

            downloaded_console = root / "downloaded/stage.log"
            downloaded_console.parent.mkdir()
            shutil.copy2(console, downloaded_console)
            stage.verify_receipt(receipt, downloaded_console, candidate, targets)
            with self.assertRaisesRegex(ValueError, "staging receipt repository differs"):
                stage.verify_receipt(receipt, downloaded_console, candidate, targets, root)

    def test_downloaded_bundle_rejects_unc_share_aliases_with_refreshed_pin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = self.stage(root)
            targets = ("js", "jvm")
            tasks = stage.publication_tasks(targets)
            stage_dir = staging / ".qualification/test"
            stage_dir.mkdir(parents=True)
            console = stage_dir / "stage.log"
            console.write_text("".join(f"> Task {task}\n" for task in tasks) + "BUILD SUCCESSFUL\n")
            receipt_path = stage_dir / "receipt.json"
            receipt_path.write_text(json.dumps({
                "candidate_sha": "a" * 40, "repository": str(self.REPOSITORY),
                "targets": list(targets), "tasks": tasks, "command": self.publication_command(tasks),
                "status": "PASSED", "exit_code": 0,
                "console_sha256": hashlib.sha256(console.read_bytes()).hexdigest()}))
            audit = qualify.audit_staging(staging, "a" * 40, targets, root / "LICENSE.md",
                                          receipt_path, console)
            self.assertEqual("PASSED", audit["status"], audit["errors"])
            audit_path = root / "artifact-audit.json"
            audit_path.write_text(json.dumps(audit))
            bundle = root / "bundle"
            publication.package(root, audit_path, bundle)
            original_pin = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
            publication.verify(bundle, "a" * 40, original_pin)

            for index, share in enumerate(("share.", "share ")):
                with self.subTest(share=share):
                    changed = root / f"changed-{index}"
                    shutil.copytree(bundle, changed)
                    changed_receipt = changed / "build/staging-repository/.qualification/test/receipt.json"
                    receipt = json.loads(changed_receipt.read_text())
                    receipt["repository"] = f"\\\\server\\{share}\\repo"
                    receipt["command"][0] = receipt["repository"] + r"\gradlew.bat"
                    changed_receipt.write_text(json.dumps(receipt))
                    changed_audit = changed / "artifact-audit.json"
                    audit_data = json.loads(changed_audit.read_text())
                    next(item for item in audit_data["artifacts"]
                         if item["path"] == ".qualification/test/receipt.json")["sha256"] = (
                             hashlib.sha256(changed_receipt.read_bytes()).hexdigest())
                    changed_audit.write_text(json.dumps(audit_data))
                    changed_manifest = changed / "manifest.json"
                    manifest = json.loads(changed_manifest.read_text())
                    for path in (changed_receipt, changed_audit):
                        manifest["files"][path.relative_to(changed).as_posix()] = (
                            hashlib.sha256(path.read_bytes()).hexdigest())
                    changed_manifest.write_text(json.dumps(manifest))
                    refreshed_pin = hashlib.sha256(changed_manifest.read_bytes()).hexdigest()
                    with self.assertRaisesRegex(ValueError, "trusted manifest SHA-256 differs"):
                        publication.verify(changed, "a" * 40, original_pin)
                    with self.assertRaisesRegex(ValueError, "staged audit differs"):
                        publication.verify(changed, "a" * 40, refreshed_pin)

    def test_downloaded_publication_bundle_rejects_partial_or_changed_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = self.stage(root)
            stage_dir = staging / ".qualification/test"
            stage_dir.mkdir(parents=True)
            targets = ("js", "jvm")
            tasks = stage.publication_tasks(targets)
            console = stage_dir / "stage.log"
            console.write_text("".join(f"> Task {task}\n" for task in tasks) + "BUILD SUCCESSFUL\n")
            receipt = stage_dir / "receipt.json"
            receipt.write_text(json.dumps({"candidate_sha": "a" * 40,
                                           "repository": str(self.REPOSITORY), "targets": list(targets),
                                           "tasks": tasks, "command": self.publication_command(tasks),
                                           "status": "PASSED", "exit_code": 0,
                                           "console_sha256": hashlib.sha256(console.read_bytes()).hexdigest()}))
            audit = qualify.audit_staging(staging, "a" * 40, targets, root / "LICENSE.md",
                                          receipt, console)
            self.assertEqual("PASSED", audit["status"], audit["errors"])
            audit_file = root / "artifact-audit.json"
            audit_file.write_text(json.dumps(audit))
            stale = staging / ".qualification/old/receipt.json"
            stale.parent.mkdir(parents=True)
            stale.write_text('{"candidate_sha":"old"}')
            bundle = root / "bundle"
            publication.package(root, audit_file, bundle)
            manifest_sha256 = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
            publication.verify(bundle, "a" * 40, manifest_sha256)
            self.assertFalse((bundle / "build/staging-repository/.qualification/old").exists())
            changed = root / "coherent-bundle"
            shutil.copytree(bundle, changed)
            binary = changed / "build/staging-repository/io/github/rubixhacker/dyn4k-core-jvm" / (
                f"{qualify.VERSION}/dyn4k-core-jvm-{qualify.VERSION}.jar")
            with zipfile.ZipFile(binary, "a") as jar:
                jar.comment = b"changed after staging"
            binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
            binary.with_name(binary.name + ".sha256").write_text(binary_hash + "\n")
            metadata = binary.with_suffix(".module")
            content = json.loads(metadata.read_text())
            for variant in content["variants"]:
                if variant["name"] in ("jvmApiElements-published", "jvmRuntimeElements-published"):
                    variant["files"][0]["size"] = binary.stat().st_size
                    variant["files"][0]["sha256"] = binary_hash
            metadata.write_text(json.dumps(content))
            metadata_hash = hashlib.sha256(metadata.read_bytes()).hexdigest()
            metadata.with_name(metadata.name + ".sha256").write_text(metadata_hash + "\n")
            changed_audit = changed / "artifact-audit.json"
            audit_data = json.loads(changed_audit.read_text())
            for item in audit_data["artifacts"]:
                if item["path"] == binary.relative_to(changed / "build/staging-repository").as_posix():
                    item["sha256"] = binary_hash
                if item["path"] == metadata.relative_to(changed / "build/staging-repository").as_posix():
                    item["sha256"] = metadata_hash
            changed_audit.write_text(json.dumps(audit_data))
            changed_manifest = changed / "manifest.json"
            manifest_data = json.loads(changed_manifest.read_text())
            for path in (binary, binary.with_name(binary.name + ".sha256"), metadata,
                         metadata.with_name(metadata.name + ".sha256"), changed_audit):
                manifest_data["files"][path.relative_to(changed).as_posix()] = (
                    hashlib.sha256(path.read_bytes()).hexdigest())
            changed_manifest.write_text(json.dumps(manifest_data))
            with self.assertRaisesRegex(ValueError, "trusted manifest SHA-256 differs"):
                publication.verify(changed, "a" * 40, manifest_sha256)
            docs = next(bundle.rglob("dyn4k-js-*-javadoc.jar"))
            docs.unlink()
            with self.assertRaises(ValueError):
                publication.verify(bundle, "a" * 40, manifest_sha256)

    def test_downloaded_bundle_rejects_coherently_refreshed_metadata_and_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = self.stage(root)
            stage_dir = staging / ".qualification/test"
            stage_dir.mkdir(parents=True)
            tasks = stage.publication_tasks(("js", "jvm"))
            console = stage_dir / "stage.log"
            console.write_text("".join(f"> Task {task}\n" for task in tasks) + "BUILD SUCCESSFUL\n")
            receipt = stage_dir / "receipt.json"
            receipt.write_text(json.dumps({"candidate_sha": "a" * 40,
                                           "repository": str(self.REPOSITORY), "targets": ["js", "jvm"],
                                           "tasks": tasks, "command": self.publication_command(tasks),
                                           "status": "PASSED", "exit_code": 0,
                                           "console_sha256": hashlib.sha256(console.read_bytes()).hexdigest()}))
            audit_file = root / "artifact-audit.json"
            audit_file.write_text(json.dumps(qualify.audit_staging(
                staging, "a" * 40, ("js", "jvm"), root / "LICENSE.md", receipt, console)))
            bundle = root / "bundle"
            publication.package(root, audit_file, bundle)
            manifest_sha256 = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
            relative = Path("build/staging-repository/io/github/rubixhacker/dyn4k-core-jvm") / (
                f"{qualify.VERSION}/dyn4k-core-jvm-{qualify.VERSION}.module")
            metadata = bundle / relative
            content = json.loads(metadata.read_text())
            for variant in content["variants"]:
                if variant["name"] in ("jvmApiElements-published", "jvmRuntimeElements-published"):
                    variant["files"][0]["url"] = "missing-core-jvm.jar"
            metadata.write_text(json.dumps(content))
            checksum = metadata.with_name(metadata.name + ".sha256")
            checksum.write_text(hashlib.sha256(metadata.read_bytes()).hexdigest() + "\n")
            audit_path = bundle / "artifact-audit.json"
            audit = json.loads(audit_path.read_text())
            next(item for item in audit["artifacts"] if item["path"] ==
                 relative.relative_to("build/staging-repository").as_posix())["sha256"] = (
                     hashlib.sha256(metadata.read_bytes()).hexdigest())
            audit_path.write_text(json.dumps(audit))
            manifest_path = bundle / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            for path in (metadata, checksum, audit_path):
                manifest["files"][path.relative_to(bundle).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                publication.verify(bundle, "a" * 40, manifest_sha256)

    def test_downloaded_bundle_rejects_coherent_pom_source_docs_and_apple_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            targets = ("jvm", "iosArm64")
            staging = self.stage(root, targets)
            stage_dir = staging / ".qualification/test"
            stage_dir.mkdir(parents=True)
            tasks = stage.publication_tasks(tuple(sorted(targets)))
            console = stage_dir / "stage.log"
            console.write_text("".join(f"> Task {task}\n" for task in tasks) + "BUILD SUCCESSFUL\n")
            receipt = stage_dir / "receipt.json"
            receipt.write_text(json.dumps({"candidate_sha": "a" * 40,
                                           "repository": str(self.REPOSITORY), "targets": sorted(targets),
                                           "tasks": tasks, "command": self.publication_command(tasks),
                                           "status": "PASSED", "exit_code": 0,
                                           "console_sha256": hashlib.sha256(console.read_bytes()).hexdigest()}))
            audit_file = root / "artifact-audit.json"
            audit = qualify.audit_staging(staging, "a" * 40, targets, root / "LICENSE.md",
                                          receipt, console)
            self.assertEqual("PASSED", audit["status"], audit["errors"])
            audit_file.write_text(json.dumps(audit))
            original = root / "bundle"
            publication.package(root, audit_file, original)
            external_digest = hashlib.sha256((original / "manifest.json").read_bytes()).hexdigest()
            for mutation in ("pom_scope", "source_bytes", "fake_docs", "apple_literal"):
                with self.subTest(mutation=mutation):
                    bundle = root / ("changed-" + mutation)
                    shutil.copytree(original, bundle)
                    stage_root = bundle / "build/staging-repository"
                    name = "dyn4k-core-iosarm64" if mutation == "apple_literal" else (
                        "dyn4k-jvm" if mutation == "pom_scope" else "dyn4k-core-jvm")
                    base = stage_root / "io/github/rubixhacker" / name / qualify.VERSION
                    prefix = f"{name}-{qualify.VERSION}"
                    extension = {"pom_scope": ".pom", "source_bytes": "-sources.jar",
                                 "fake_docs": "-javadoc.jar", "apple_literal": "-metadata.jar"}[mutation]
                    changed = base / (prefix + extension)
                    if mutation == "pom_scope":
                        changed.write_text(changed.read_text().replace("<scope>compile</scope>",
                                                                     "<scope>test</scope>", 1))
                    elif mutation == "source_bytes":
                        with zipfile.ZipFile(changed, "w") as jar:
                            jar.writestr("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\r\n\r\n")
                            jar.writestr("commonMain/api/Type.kt", b"package wrong\nclass Fake\n")
                    elif mutation == "fake_docs":
                        with zipfile.ZipFile(changed, "w") as jar:
                            jar.writestr("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\r\n\r\n")
                            jar.writestr("META-INF/LICENSE.md", b"Fixture license\n")
                            jar.writestr("index.html", "<html>wrong API</html>")
                            jar.writestr("api/Wrong.html", "<html>wrong API</html>")
                    else:
                        changed.write_bytes(b"not a jar")
                    touched = [changed]
                    checksum = changed.with_name(changed.name + ".sha256")
                    checksum.write_text(hashlib.sha256(changed.read_bytes()).hexdigest() + "\n")
                    touched.append(checksum)
                    if mutation in ("source_bytes", "apple_literal"):
                        metadata = base / (prefix + ".module")
                        content = json.loads(metadata.read_text())
                        kind = "Sources" if mutation == "source_bytes" else "Metadata"
                        variant = next(v for v in content["variants"] if v["name"] ==
                                       ("jvm" if kind == "Sources" else "iosArm64") + kind + "Elements-published")
                        variant["files"][0].update(size=changed.stat().st_size,
                            **{algorithm: hashlib.new(algorithm, changed.read_bytes()).hexdigest()
                               for algorithm in ("sha512", "sha256", "sha1", "md5")})
                        metadata.write_text(json.dumps(content))
                        touched.append(metadata)
                        metadata_sidecar = metadata.with_name(metadata.name + ".sha256")
                        metadata_sidecar.write_text(hashlib.sha256(metadata.read_bytes()).hexdigest() + "\n")
                        touched.append(metadata_sidecar)
                    bundled_audit = bundle / "artifact-audit.json"
                    audit_data = json.loads(bundled_audit.read_text())
                    for path in touched:
                        if path.suffix == ".sha256":
                            continue
                        relative = path.relative_to(stage_root).as_posix()
                        next(item for item in audit_data["artifacts"] if item["path"] == relative)["sha256"] = (
                            hashlib.sha256(path.read_bytes()).hexdigest())
                    bundled_audit.write_text(json.dumps(audit_data))
                    touched.append(bundled_audit)
                    manifest_path = bundle / "manifest.json"
                    manifest = json.loads(manifest_path.read_text())
                    for path in touched:
                        manifest["files"][path.relative_to(bundle).as_posix()] = (
                            hashlib.sha256(path.read_bytes()).hexdigest())
                    manifest_path.write_text(json.dumps(manifest))
                    with self.assertRaisesRegex(ValueError, "trusted manifest SHA-256 differs"):
                        publication.verify(bundle, "a" * 40, external_digest)
                    with self.assertRaises(ValueError):
                        publication.verify(bundle, "a" * 40,
                                           hashlib.sha256(manifest_path.read_bytes()).hexdigest())

    def test_downloaded_bundle_rejects_coherent_profile_and_embedded_notice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            targets = ("jvm",)
            staging = self.stage(root, targets)
            stage_dir = staging / ".qualification/test"
            stage_dir.mkdir(parents=True)
            tasks = stage.publication_tasks(targets)
            console = stage_dir / "stage.log"
            console.write_text("".join(f"> Task {task}\n" for task in tasks) + "BUILD SUCCESSFUL\n")
            receipt = stage_dir / "receipt.json"
            receipt.write_text(json.dumps({"candidate_sha": "a" * 40,
                                           "repository": str(self.REPOSITORY), "targets": list(targets),
                                           "tasks": tasks, "command": self.publication_command(tasks),
                                           "status": "PASSED", "exit_code": 0,
                                           "console_sha256": hashlib.sha256(console.read_bytes()).hexdigest()}))
            audit = qualify.audit_staging(staging, "a" * 40, targets, root / "LICENSE.md",
                                          receipt, console)
            self.assertEqual("PASSED", audit["status"], audit["errors"])
            audit_file = root / "artifact-audit.json"
            audit_file.write_text(json.dumps(audit))
            original = root / "bundle"
            publication.package(root, audit_file, original)
            external_digest = hashlib.sha256((original / "manifest.json").read_bytes()).hexdigest()
            publication.verify(original, "a" * 40, external_digest)
            for mutation in ("active_profile_test_scope", "wrong_embedded_notice"):
                with self.subTest(mutation=mutation):
                    bundle = root / mutation
                    shutil.copytree(original, bundle)
                    stage_root = bundle / "build/staging-repository"
                    name = "dyn4k-jvm" if mutation == "active_profile_test_scope" else "dyn4k-core-jvm"
                    base = stage_root / qualify.GROUP.replace(".", "/") / name / qualify.VERSION
                    prefix = f"{name}-{qualify.VERSION}"
                    touched = []
                    if mutation == "active_profile_test_scope":
                        pom = base / (prefix + ".pom")
                        profile = ("<profiles><profile><id>override-core</id><activation>"
                                   "<activeByDefault>true</activeByDefault></activation><dependencies>"
                                   f"<dependency><groupId>{qualify.GROUP}</groupId>"
                                   f"<artifactId>dyn4k-core-jvm</artifactId><version>{qualify.VERSION}</version>"
                                   "<scope>test</scope></dependency></dependencies></profile></profiles>")
                        pom.write_text(pom.read_text().replace("</project>", profile + "</project>"))
                        touched.append(pom)
                    else:
                        binary = base / (prefix + ".jar")
                        output = io.BytesIO()
                        with zipfile.ZipFile(binary) as source, zipfile.ZipFile(output, "w") as changed:
                            for member in source.infolist():
                                contents = (b"Wrong legal notice\n" if member.filename == "META-INF/LICENSE.md"
                                            else source.read(member.filename))
                                changed.writestr(member, contents)
                        binary.write_bytes(output.getvalue())
                        touched.append(binary)
                        metadata = base / (prefix + ".module")
                        content = json.loads(metadata.read_text())
                        for variant in content["variants"]:
                            for file in variant.get("files", []):
                                if file["url"] == binary.name:
                                    file.update(size=binary.stat().st_size,
                                        **{algorithm: hashlib.new(algorithm, binary.read_bytes()).hexdigest()
                                           for algorithm in ("sha512", "sha256", "sha1", "md5")})
                        metadata.write_text(json.dumps(content))
                        touched.append(metadata)
                    for path in touched:
                        sidecar = path.with_name(path.name + ".sha256")
                        sidecar.write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
                    bundled_audit = bundle / "artifact-audit.json"
                    audit_data = json.loads(bundled_audit.read_text())
                    for path in touched:
                        relative = path.relative_to(stage_root).as_posix()
                        next(item for item in audit_data["artifacts"] if item["path"] == relative)["sha256"] = (
                            hashlib.sha256(path.read_bytes()).hexdigest())
                    bundled_audit.write_text(json.dumps(audit_data))
                    manifest_path = bundle / "manifest.json"
                    manifest = json.loads(manifest_path.read_text())
                    for path in (*touched, *(path.with_name(path.name + ".sha256") for path in touched),
                                 bundled_audit):
                        manifest["files"][path.relative_to(bundle).as_posix()] = (
                            hashlib.sha256(path.read_bytes()).hexdigest())
                    manifest_path.write_text(json.dumps(manifest))
                    with self.assertRaisesRegex(ValueError, "trusted manifest SHA-256 differs"):
                        publication.verify(bundle, "a" * 40, external_digest)
                    with self.assertRaises(ValueError):
                        publication.verify(bundle, "a" * 40,
                                           hashlib.sha256(manifest_path.read_bytes()).hexdigest())

    def test_downloaded_bundle_rejects_coherently_refreshed_pom_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            targets = ("jvm",)
            staging = self.stage(root, targets)
            stage_dir = staging / ".qualification/test"
            stage_dir.mkdir(parents=True)
            tasks = stage.publication_tasks(targets)
            console = stage_dir / "stage.log"
            console.write_text("".join(f"> Task {task}\n" for task in tasks) + "BUILD SUCCESSFUL\n")
            receipt = stage_dir / "receipt.json"
            receipt.write_text(json.dumps({"candidate_sha": "a" * 40,
                                           "repository": str(self.REPOSITORY), "targets": list(targets),
                                           "tasks": tasks, "command": self.publication_command(tasks),
                                           "status": "PASSED", "exit_code": 0,
                                           "console_sha256": hashlib.sha256(console.read_bytes()).hexdigest()}))
            audit = qualify.audit_staging(staging, "a" * 40, targets, root / "LICENSE.md",
                                          receipt, console)
            self.assertEqual("PASSED", audit["status"], audit["errors"])
            audit_file = root / "artifact-audit.json"
            audit_file.write_text(json.dumps(audit))
            original = root / "bundle"
            publication.package(root, audit_file, original)
            external_digest = hashlib.sha256((original / "manifest.json").read_bytes()).hexdigest()
            publication.verify(original, "a" * 40, external_digest)

            for label, (before, after) in self.pom_metadata_changes().items():
                with self.subTest(label=label):
                    bundle = root / label
                    shutil.copytree(original, bundle)
                    stage_root = bundle / "build/staging-repository"
                    pom = (stage_root / qualify.GROUP.replace(".", "/") / "dyn4k-jvm" / qualify.VERSION /
                           f"dyn4k-jvm-{qualify.VERSION}.pom")
                    content = pom.read_text()
                    self.assertIn(before, content)
                    pom.write_text(content.replace(before, after, 1))
                    sidecar = pom.with_name(pom.name + ".sha256")
                    sidecar.write_text(hashlib.sha256(pom.read_bytes()).hexdigest() + "\n")

                    bundled_audit = bundle / "artifact-audit.json"
                    audit_data = json.loads(bundled_audit.read_text())
                    relative = pom.relative_to(stage_root).as_posix()
                    next(item for item in audit_data["artifacts"] if item["path"] == relative)["sha256"] = (
                        hashlib.sha256(pom.read_bytes()).hexdigest())
                    bundled_audit.write_text(json.dumps(audit_data))
                    manifest_path = bundle / "manifest.json"
                    manifest = json.loads(manifest_path.read_text())
                    for path in (pom, sidecar, bundled_audit):
                        manifest["files"][path.relative_to(bundle).as_posix()] = (
                            hashlib.sha256(path.read_bytes()).hexdigest())
                    manifest_path.write_text(json.dumps(manifest))

                    with self.assertRaisesRegex(ValueError, "trusted manifest SHA-256 differs"):
                        publication.verify(bundle, "a" * 40, external_digest)
                    with self.assertRaisesRegex(ValueError, "staged audit differs"):
                        publication.verify(bundle, "a" * 40,
                                           hashlib.sha256(manifest_path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
