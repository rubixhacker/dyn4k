import argparse
import copy
import json
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import full


def replace_raw(record, raw, directory, name):
    path = directory / name
    path.write_bytes(raw)
    record["path"] = str(path)
    record["sha256"] = full.digest_bytes(raw)


def test_adverse(root, receipt_path):
    original = json.loads(receipt_path.read_text())
    if full.validate_result(original, root)["status"] != "CONSISTENCY_ONLY":
        raise ValueError("passing full receipt is required")
    rejected = []
    with tempfile.TemporaryDirectory(prefix="dyn4k-native-adverse-") as temporary:
        directory = Path(temporary)

        def expect_rejected(name, mutate, patches=()):
            item = copy.deepcopy(original)
            mutate(item)
            contexts = [patch(*entry) for entry in patches]
            try:
                for context in contexts:
                    context.__enter__()
                try:
                    full.validate_result(item, root)
                except (ValueError, OSError, KeyError, IndexError, UnicodeError):
                    rejected.append(name)
                    return
                raise AssertionError(f"adverse control was accepted: {name}")
            finally:
                for context in reversed(contexts):
                    context.__exit__(None, None, None)

        key = "core-debug"
        process = original["lanes"][key]["process"]["stdout"]
        stdout = full.read_record(process)
        first = full.parse_test_run(stdout)[0].encode()

        def missing_case(item):
            raw = stdout.replace(b"[ RUN      ] " + first + b"\n", b"", 1)
            raw = re.sub(rb"\[       OK \] " + re.escape(first) + rb" \(\d+ ms\)\n", b"", raw, count=1)
            raw = raw.replace(b"[==========] 2465 tests from", b"[==========] 2464 tests from")
            raw = raw.replace(b"[  PASSED  ] 2465 tests.", b"[  PASSED  ] 2464 tests.")
            replace_raw(item["lanes"][key]["process"]["stdout"], raw, directory, "missing.stdout")
            item["lanes"][key]["case_count"] = 2464
            item["total_common_cases"] -= 1

        def duplicate_case(item):
            run_line = b"[ RUN      ] " + first + b"\n"
            match = re.search(rb"\[       OK \] " + re.escape(first) + rb" \(\d+ ms\)\n", stdout)
            pair = run_line + match.group()
            raw = stdout.replace(pair, pair + pair, 1)
            raw = raw.replace(b"[==========] 2465 tests from", b"[==========] 2466 tests from")
            raw = raw.replace(b"[  PASSED  ] 2465 tests.", b"[  PASSED  ] 2466 tests.")
            replace_raw(item["lanes"][key]["process"]["stdout"], raw, directory, "duplicate.stdout")
            item["lanes"][key]["case_count"] = 2466
            item["total_common_cases"] += 1

        expect_rejected("missing case", missing_case)
        expect_rejected("duplicate case", duplicate_case)
        expect_rejected("forged PASS line", lambda item: replace_raw(
            item["lanes"][key]["process"]["stdout"], stdout + b"[  PASSED  ] 2465 tests.\n", directory, "forged.stdout"))
        expect_rejected("nonzero process", lambda item: item["lanes"][key]["process"].update(exit_code=1))
        expect_rejected("lost stdout", lambda item: item["lanes"][key]["process"]["stdout"].update(path=str(directory / "missing")))
        expect_rejected("lost stderr", lambda item: item["lanes"][key]["process"]["stderr"].update(path=str(directory / "missing")))
        expect_rejected("debug optimized swap", lambda item: item["lanes"].update(
            {"core-debug": item["lanes"]["core-optimized"], "core-optimized": item["lanes"]["core-debug"]}))
        expect_rejected("wrong source tree", lambda item: item.update(source_tree="0" * 40))
        expect_rejected("changed committed pin", lambda item: item.update(pin_sha256="0" * 64))
        expect_rejected("wrong guest fingerprint", lambda item: item["guest"]["values"].update(fingerprint="other/image"))
        expect_rejected("wrong guest ABI", lambda item: item["guest"]["values"].update(primary_abi="arm64-v8a"))
        core_graph = full.read_record(original["graphs"]["core"]["stdout"])
        expect_rejected("changed dependency graph", lambda item: replace_raw(
            item["graphs"]["core"]["stdout"], core_graph.replace(
                b"org.jetbrains.kotlin:kotlin-stdlib:2.4.20", b"org.jetbrains.kotlin:kotlin-stdlib:2.4.21", 1),
            directory, "changed-graph.stdout"))

        graph = full.read_record(original["graphs"]["consumer"]["stdout"])
        header = b"androidNativeX64CompileKlibraries -"
        start = graph.index(header)
        end = graph.index(b"\n\n", start)
        forged_graph = graph[:end] + b"\n+--- example:unapproved:1.0" + graph[end:]
        expect_rejected("unapproved provider", lambda item: replace_raw(
            item["graphs"]["consumer"]["stdout"], forged_graph, directory, "unapproved-graph.stdout"))

        wrong_elf = directory / "wrong.kexe"
        wrong_elf.write_bytes(b"wrong ELF")
        real_executable_path = full.executable_path
        expect_rejected("wrong executable", lambda item: None,
                        (("full.executable_path", lambda repo, module, variant:
                          wrong_elf if (module, variant) == ("core", "debug")
                          else real_executable_path(repo, module, variant)),))
        wrong_klib = directory / "wrong.klib"
        wrong_klib.write_bytes(b"wrong KLIB")
        real_klib_paths = full.klib_paths
        expect_rejected("wrong KLIB", lambda item: None,
                        (("full.klib_paths", lambda repo: {**real_klib_paths(repo), "dyn4k-core": wrong_klib}),))
        wrong_image = directory / "wrong-image.properties"
        wrong_image.write_bytes(b"stale Android image")
        real_tool_paths = full.tool_paths
        expect_rejected("stale Android image", lambda item: None,
                        (("full.tool_paths", lambda repo: {**real_tool_paths(repo), "image": wrong_image}),))

        drift = root / ".dyn4k-native-source-drift-probe"
        if drift.exists():
            raise ValueError("source drift probe path already exists")
        try:
            drift.write_text("adverse source drift\n")
            expect_rejected("source checkout drift", lambda item: None)
        finally:
            drift.unlink(missing_ok=True)

    return rejected


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    rejected = test_adverse(args.source_root.resolve(), args.receipt.resolve())
    print(json.dumps({"status": "PASS", "rejected": rejected, "count": len(rejected)}, indent=2))
