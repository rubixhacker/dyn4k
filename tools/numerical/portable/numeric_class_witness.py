import hashlib
import io
from pathlib import Path
import re
import subprocess
import zipfile

from receipt import Rejected


SCHEMA = "class-witness/2"
AGENT_CLASS = "dyn4k.witness.NumericClassWitness"
MANIFEST = b"Manifest-Version: 1.0\r\nPremain-Class: " + AGENT_CLASS.encode() + b"\r\n\r\n"
SOURCE_NAME = "NumericClassWitness.java"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build_agent(source: bytes, jdk: Path, output: Path, scratch: Path) -> bytes:
    jdk, output, scratch = Path(jdk), Path(output), Path(scratch)
    if scratch.exists() or not source or not (jdk / "bin/javac").is_file():
        raise Rejected("class witness compiler input differs")
    scratch.mkdir(parents=True)
    source_path = scratch / SOURCE_NAME
    source_path.write_bytes(source)
    classes = scratch / "classes"
    classes.mkdir()
    process = subprocess.run([str(jdk / "bin/javac"), "--release", "8", "-encoding", "UTF-8",
                              "-d", str(classes), str(source_path)], capture_output=True,
                             timeout=60, check=False)
    if process.returncode:
        raise Rejected("class witness source did not compile")
    class_files = sorted(classes.rglob("*.class"))
    if not class_files or any(not path.relative_to(classes).as_posix().startswith("dyn4k/witness/")
                              for path in class_files):
        raise Rejected("class witness class inventory differs")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as jar:
        for name, data in [("META-INF/MANIFEST.MF", MANIFEST)] + [
                (path.relative_to(classes).as_posix(), path.read_bytes()) for path in class_files]:
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_STORED
            entry.external_attr = 0o644 << 16
            jar.writestr(entry, data)
    data = buffer.getvalue()
    with output.open("xb") as stream:
        stream.write(data)
    return data


def read_witness(raw: bytes, expected_classes: dict[str, bytes],
                 expected_origins: dict[str, str] | None = None) -> dict:
    if len(raw) > 32 * 1024 * 1024 or not raw.endswith(b"\n"):
        raise Rejected("class witness is incomplete or oversized")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError as error:
        raise Rejected("class witness is not ASCII") from error
    if len(lines) < 3 or lines[0] != "BEGIN\t" + SCHEMA:
        raise Rejected("class witness start differs")
    end = re.fullmatch(r"END\t(OK|FAIL)\t([0-9]+)\t([0-9]{20})", lines[-1])
    if end is None or end[1] != "OK" or int(end[3]) != len(raw):
        raise Rejected("class witness terminal record differs")
    definitions = []
    seen = set()
    try:
        seal_index = next(index for index, line in enumerate(lines) if line.startswith("SEALED\t"))
    except StopIteration as error:
        raise Rejected("class witness seal is absent") from error
    if lines[seal_index] != "SEALED\t" + str(seal_index - 1):
        raise Rejected("class witness seal count differs")
    for ordinal, line in enumerate(lines[1:seal_index], 1):
        fields = line.split("\t")
        if len(fields) != 7 or fields[0] != "CLASS" or fields[1] != str(ordinal):
            raise Rejected("class witness sequence differs")
        _, _, name, digest, loader, origin, thread = fields
        if (name not in expected_classes or name in seen or
                not re.fullmatch(r"[0-9a-f]{64}", digest) or
                digest != _sha(expected_classes[name]) or
                not re.fullmatch(r"(?:bootstrap|system|L[1-9][0-9]*)", loader) or
                not origin.startswith("file:/") or
                not re.fullmatch(r"java:[1-9][0-9]*", thread)):
            raise Rejected("class witness definition differs")
        if expected_origins is not None and origin != expected_origins[name]:
            raise Rejected("class witness origin differs")
        seen.add(name)
        definitions.append({"name": name, "sha256": digest, "loader": loader,
                            "origin": origin, "thread": thread, "sequence": ordinal})
    if len(definitions) != int(end[2]):
        raise Rejected("class witness count differs")
    loaded = []
    for ordinal, line in enumerate(lines[seal_index + 1:-1], 1):
        fields = line.split("\t")
        if len(fields) != 5 or fields[:2] != ["LOADED", str(ordinal)]:
            raise Rejected("class witness successful-load sequence differs")
        _, _, name, loader, origin = fields
        if not re.fullmatch(r"(?:bootstrap|system|L[1-9][0-9]*)", loader):
            raise Rejected("class witness successful loader differs")
        loaded.append({"name": name, "loader": loader, "origin": origin})
    by_name = {row["name"]: row for row in definitions}
    if (len(loaded) != len(definitions) or len({row["name"] for row in loaded}) != len(loaded) or
            {row["name"] for row in loaded} != seen or
            any((row["loader"], row["origin"]) !=
                (by_name[row["name"]]["loader"], by_name[row["name"]]["origin"])
                for row in loaded)):
        raise Rejected("class witness successful loads differ from callbacks")
    return {"schema": SCHEMA, "definitions": definitions, "loaded": loaded,
            "sha256": _sha(raw)}
