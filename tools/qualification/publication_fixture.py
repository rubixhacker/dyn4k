"""The staged publication tree builder `test_publication.py` used to own.

`test_artifact.py` and `test_full_hosted.py` build their fixtures with `stage(root, targets)` for
target tuples no recorded archive carries, so the builder outlives the suite it was written for. It
is the reference's own builder, moved here unchanged; `:qualification` owns the Kotlin port of every
case that used to test it.
"""
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

import qualify


class PublicationFixture:
    REPOSITORY = Path(__file__).resolve().parents[2]

    def stage(self, root, targets=("jvm", "js")):
        license_bytes = b"Fixture license\n"
        (root / "LICENSE.md").write_bytes(license_bytes)
        (root / ".gitattributes").write_bytes(b"*.kt -text\n*.java -text\n")
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
                    for member, contents in (
                            ("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\r\n\r\n"),
                            ("META-INF/LICENSE.md", license_bytes),
                            ("index.html", "<html><body>Type API</body></html>"),
                            ("api/Type/index.html", "<html><body>Type members</body></html>")):
                        jar.writestr(zipfile.ZipInfo(member, (1980, 1, 1, 0, 0, 0)), contents)
                self.write(base / f"{name}-{qualify.VERSION}-javadoc.jar", archive.read_bytes())
            source_tree = root / module / "src/commonMain/kotlin/api/Type.kt"
            source_tree.parent.mkdir(parents=True, exist_ok=True)
            source_tree.write_bytes(b"// Fixture notice\npackage api\nclass Type\n")
            docs_tree = root / module / "build/dokka/html"
            (docs_tree / "api/Type").mkdir(parents=True, exist_ok=True)
            (docs_tree / "index.html").write_bytes(b"<html><body>Type API</body></html>")
            (docs_tree / "api/Type/index.html").write_bytes(b"<html><body>Type members</body></html>")
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
                         "version": qualify.VERSION,
                         "attributes": {"org.gradle.status": "release"}}
            if target is not None:
                component["url"] = f"../../{module}/{qualify.VERSION}/{module}-{qualify.VERSION}.module"
            self.write(base / f"{name}-{qualify.VERSION}.module", json.dumps({
                "formatVersion": "1.1", "createdBy": {"gradle": {"version": "9.5.0"}},
                "component": component, "variants": variants}).encode())
        return staging

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.with_name(path.name + ".sha256").write_text(hashlib.sha256(content).hexdigest() + "\n")

    def publication_command(self, tasks):
        wrapper = "gradlew.bat" if os.name == "nt" else "gradlew"
        return [str(self.REPOSITORY / wrapper),
                "--no-daemon", "--console=plain", *tasks]

