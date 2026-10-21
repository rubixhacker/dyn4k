import hashlib
from pathlib import Path
import re
import zipfile


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def class_parts(raw):
    position = 0

    def take(count):
        nonlocal position
        if count < 0 or position + count > len(raw):
            raise ValueError("Truncated class file")
        part = raw[position:position + count]
        position += count
        return part

    def number(count):
        return int.from_bytes(take(count), "big")

    if take(4) != b"\xca\xfe\xba\xbe":
        raise ValueError("Invalid class file")
    take(4)
    count = number(2)
    pool_start = position
    names = {}
    widths = {3: 4, 4: 4, 5: 8, 6: 8, 7: 2, 8: 2, 9: 4, 10: 4,
              11: 4, 12: 4, 15: 3, 16: 2, 17: 4, 18: 4, 19: 2, 20: 2}
    index = 1
    while index < count:
        tag = number(1)
        if tag == 1:
            names[index] = take(number(2))
        elif tag in widths:
            take(widths[tag])
        else:
            raise ValueError("Unknown constant-pool tag")
        index += 2 if tag in (5, 6) else 1
    pool = raw[pool_start:position]
    take(6)
    take(2 * number(2))

    def members():
        found = {}
        for _ in range(number(2)):
            take(2)
            name = names[number(2)].decode("utf-8")
            signature = names[number(2)].decode("utf-8")
            attributes = {}
            for _ in range(number(2)):
                label = names[number(2)]
                if label in attributes:
                    raise ValueError("Duplicate class attribute")
                attributes[label] = take(number(4))
            key = (name, signature)
            if key in found:
                raise ValueError("Duplicate class member")
            found[key] = attributes
        return found

    members()
    methods = {}
    for key, attributes in members().items():
        code = attributes.get(b"Code")
        if code is None:
            methods[key] = b""
        else:
            if len(code) < 8:
                raise ValueError("Malformed method code")
            size = int.from_bytes(code[4:8], "big")
            if len(code) < 8 + size:
                raise ValueError("Truncated method code")
            methods[key] = code[8:8 + size]
    for _ in range(number(2)):
        take(2)
        take(number(4))
    if position != len(raw):
        raise ValueError("Trailing class bytes")
    return count, pool, methods


def verify_probe_code(output, class_bytes, class_name):
    output = Path(output)
    try:
        count, pool, methods = class_parts(class_bytes)
        identity = (output / "class.txt").read_text().splitlines()
        if len(identity) != 3 or identity[0] != class_name or int(identity[1]) != count or int(identity[2]) <= 0:
            return {"status": "FAILED_LOADED_CODE_IDENTITY", "qualification": "UNPASSED"}
        if (output / "constant-pool.bin").read_bytes() != pool:
            return {"status": "FAILED_LOADED_CODE_BYTES", "qualification": "UNPASSED"}
        observed = {}
        filenames = set()
        for line in (output / "methods.tsv").read_text().splitlines():
            parts = line.split("\t")
            if len(parts) != 3 or re.fullmatch(r"method-[0-9]+\.bin", parts[2]) is None:
                return {"status": "FAILED_LOADED_CODE_INVENTORY", "qualification": "UNPASSED"}
            key = (parts[0], parts[1])
            if key in observed or parts[2] in filenames:
                return {"status": "FAILED_LOADED_CODE_INVENTORY", "qualification": "UNPASSED"}
            observed[key] = (output / parts[2]).read_bytes()
            filenames.add(parts[2])
        if observed.keys() != methods.keys():
            return {"status": "FAILED_LOADED_CODE_INVENTORY", "qualification": "UNPASSED"}
        if observed != methods:
            return {"status": "FAILED_LOADED_CODE_BYTES", "qualification": "UNPASSED"}
        if len(list(output.glob("method-*.bin"))) != len(methods):
            return {"status": "FAILED_LOADED_CODE_INVENTORY", "qualification": "UNPASSED"}
        return {"status": "MATCHED_JDI_LOADED_CODE", "qualification": "UNPASSED",
                "class_sha256": _sha(class_bytes), "constant_pool_sha256": _sha(pool),
                "methods": len(methods)}
    except (OSError, UnicodeError, ValueError, KeyError):
        return {"status": "FAILED_LOADED_CODE_INVENTORY", "qualification": "UNPASSED"}


def verify_jar_code(output, jar, expected_jar_sha256, class_name):
    try:
        raw = Path(jar).read_bytes()
        if _sha(raw) != expected_jar_sha256:
            return {"status": "FAILED_JAR_IDENTITY", "qualification": "UNPASSED"}
        with zipfile.ZipFile(jar) as archive:
            path = class_name.replace(".", "/") + ".class"
            if sum(name == path for name in archive.namelist()) != 1:
                return {"status": "FAILED_JAR_INVENTORY", "qualification": "UNPASSED"}
            class_bytes = archive.read(path)
        result = verify_probe_code(output, class_bytes, class_name)
        result["jar_sha256"] = expected_jar_sha256
        return result
    except (OSError, zipfile.BadZipFile, KeyError):
        return {"status": "FAILED_JAR_INVENTORY", "qualification": "UNPASSED"}
