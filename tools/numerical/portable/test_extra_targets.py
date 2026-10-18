import base64
import json
import hashlib
import gzip
import os
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import extra_targets
from extra_targets import (ROUTES, Rejected, bounded_gradle_filter, browser_lock_task,
                           browser_methods, collect_trace, isolated_karma_port, native_methods,
                           observed_counts, verify_inputs, verify_methods, verify_process,
                           wasmtime_methods)


ARCHIVED_KARMA_TAILS = {
    "js": (
        "eNq1Vd2P0zgQf89fYUVUbaRNI5B4IBU6rWCRjjsE0i7ioRud3GSamnVsnz92KUv/d8axk6Z7q4MHyEMbj+fzN7+Z1FJsWbtU3LVMGPKS1KeCb9/Iulolp9Klcma30PCvYxoW8xtpORP5HWzyHXAF2hQNM7a4obqjebzVoKS2oOdZtkoGf1y2Lapj2HVC8Lnvf/1j9wpK8sMQts7RR06VAtF452ejh6JoYEsdt4TTvXR2vAjHktzHIHNFLSYm5mckvqFstp4196/Pry6u/nx3cShniqxndVWSWTXr5uTQOzsk1QNgfgd+KFa0vskxZ+VsgK8oSBTHeMnWidoyKUitgVr4FG5f9ZeLDIHlYKMuJulx7mTji2/gFrhUHQg79+BpMJLf4k3oBWo5DqaMDSIkFWj3TxSnvbDC34O3jeWhcnWWDLaDJx39jNrJIVRipNM1kI4qM+AULJe9SQBrwgww2Lzietn98dk8KY4NdwZjrdPgLkd3SA2KpEirow6IrcTbkqRKQ5ocsrE1iIOVkiM4W8oNjHLWCqnhE9WCifbI1OINZRwaYiWSRhuYVBFTKs7rGoxBK8I6z33MGCwlDfa8tnxPmCFOGKf6uWjI9UIKlCotkQF2T2hvTqQmDVasXW2d7p0ZMhpdZ0VSrRBK8uBBWKWyrGNfqWfFf+5jcVOdI3dPpEhgj31qFGf21c6JG5OWASPfQAwkJPZcQaDf28uPQoDPnOr9JXSslhzjrxYDQRchSBZZgSdjia0vtJb6Q88fTORn5x681TAhc2zmpLaTWRNwdxpkkWVTZWOpnUxvOPrSw6S/33zG+pYU29kOFQSlM3J6OvL0LlImgjXhoM9iEIdFkiETB2BG5sEXrJf5wTRxZJH8Uv3tB/b8jjKcAqQFOj70UxQaUJKLL1ZT7AMm1gDZatmRv3oUT3YCeke1t2ZiisPR/KJ+Dstp0slJk5LI0J21ypRF0TK7c5tlLbsiao3/zBgHpnj67MXzpxP/H6itd5f9xL2jKrz8DG2GXfo8b2Dj2h8x5rEwA3H+1zDGWY62r+H2CrdL5N6RJGHRvcFVImgHV9Apjtsb19OabnAPOwu5X8j9RsOP065KI2FOGePXK+B+EDGjFXJioJEBu7iPCZWPfx78GkyS73Wmpbo="
    ),
    "wasmJs": (
        "eNq1Vm1v2zYQ/q5fQQgzJAO2hQ4o0MkYhqBOh6RpXSwe+sERAlo620wkkiOppJ7r/76jRNlyYjtdsOlDYh3v9eHdc0oFn7PFQOblgnFNfiXpvuD7dzJNht6+dCBLvQwV/FUyBWFwL0zOeP8RZv0l5BKUjjKmTXRPVUH77lSBFMqACrrdodf4y8VigeoYduoRfNbVX/uYlYSYvBjCpH300adSAs+s897WQxRlMKdlbkhOV6I024P6NSZrFySQ1GBiPOgR9wtlnWknW4/OJueTi0/nm7gjybSTJjHpJJ0iIJvK2cZLngDzf+CHYknT+z7mLEtTwxdFxIldPG9e8tQwwUmqgBr4Wp++rw7DbgvY9pODcfaY+GEVQgqRWZAyeIBcyAK4CXpHVBVokT+g9jFflbcyBx27Cz/8+Bxj3jpV/6hicuRkcyw/Bz8GT3reqfxOVaBc/v86ukPnSlDs1DrCDo2gXbLtRCVS0HoA/GEafBxPri4+307GY/z3++3o4o8gSbzNwTib4UGxbRktSpUCKajUTUPWAQdVTXVXtkYQNE5JdDMofrvTP0W7skqNAE392l0f3eEM2pr8FqrA5wJPY+JLBb636W5nABvJCJFjx81prmErZwsuFHylijO+2FFC9IGyHDJiBE6n0tCqwqUUnaUWKrQirLAkgxmDoSTD4UpNviJMk5LrUlYElJGbUHCUIsI4amZFaGVOhCIZVqzK1JSqcqbJ1uimG3nJEGF8iivCKqRhBfub2vF7du6Ka+vsSGJPikxhsfe1zJl5vyz5vfbjGiMPLxUDcYHNK6Ge88vrPzkHmzlVq2soWCpyjD8MGyYI6yDN7OObNsSk50oJ9aUaBEzkRwkWrFVDRUF36LVq2yM1Do/7QcJut62sDTUtmqxfbel1N49nd1jfgOJ1LpoKaqUe2X/b9emjaxkHVqsHbRaNuGbsLnZiA8zwJbAait3B5DuR3x2SluII5ozDFlSnNGiLTyPW1gzXJ5gR+8MuLTFvCAJb5PJ6/BlRsT3L5qswKHETWndZexs+NR8BF6+1zd691pLxC8Ffa3yn07G0l/VC0e6m96+6YRn4hr3N7BbT251nhLyy2+3skTJkPKQAbKJNxZj1sMXk/JtRFIPiDWZA5koU5GM1MXuLFr2j2qVumSIRZv/R7D5vx6A1kJ5jo6UxUsdRtGBmWc4GqSgip7X9z7QuQUdvfv7l7ZuW/y/UpMvril0/UVn/+BGKaD5Q3vYzmJWLl9jhUJiGJE4aNmO1tR3BwwQ3ybOxqZfaB1wbnBYwgULm+EmEq2hKZ7iCSwN9u4ur7YVffMvEP9gy1crGXcBdRkPsiaaNNJhw7RKKD39z2ZXnef8Afzx1EA=="
    ),
}


def archived_karma_config(loaded, port, console, method, target="js"):
    runner = loaded.parent.parent / "node_modules/kotlin-web-helpers/dist/kotlin-test-karma-runner.js"
    settings = {"singleRun": True, "autoWatch": False, "basePath": str(loaded.parent.parent),
                "files": [str(runner), str(loaded)],
                "frameworks": ["webpack-output", "mocha", "webpack"],
                "client": {"args": ["--include", f"portable.{extra_targets.expected_class(method)}.{method}"]},
                "browsers": ["ChromeHeadless"], "customLaunchers": {},
                "failOnFailingTestSuite": False, "failOnEmptyTestSuite": False,
                "reporters": ["karma-kotlin-reporter"],
                "preprocessors": {str(runner): ["webpack", "sourcemap"],
                                  str(loaded): ["webpack", "sourcemap"]},
                "proxies": {}, "webpackCopy": []}
    if target == "wasmJs":
        settings.update(customContextFile=str(runner.parent / "static/context.html"),
                        customDebugFile=str(runner.parent / "static/debug.html"))
    generated = zlib.decompress(base64.b64decode(ARCHIVED_KARMA_TAILS[target])).decode()
    patch = extra_targets.KARMA_REPORTER_PATCH.replace(
        "__NUMERICAL_CAPTURE__", json.dumps(str(console)))
    return ("\nmodule.exports = function(config) {\n\nconfig.set("
            + json.dumps(settings, indent=2) + ");\n" + generated
            + "// portable-port.js\n" + f"config.set({{port: {port}}});\n"
            + "config.set({pingTimeout: 28800000, browserNoActivityTimeout: 28800000, "
            "browserDisconnectTimeout: 28800000, browserSocketTimeout: 28800000});\n"
            + patch + "\n\n\n\n}\n")


class ExtraTargetSeamTest(unittest.TestCase):
    def test_browser_console_teamcity_row_decodes_source_fields(self):
        line = ("##teamcity[testStdOut out='|[log|] NUMERICAL_JSON "
                "{\"id\":\"one\",\"kind\":\"inputs\",\"values\":|[1,2|]}|n' "
                "name='geometryCollisionBoundaryAndScale' flowId='one']\n")
        self.assertEqual(list(extra_targets.output_rows(line)),
                         [{"id": "one", "kind": "inputs", "values": [1, 2]}])

    def test_public_browser_archive_binds_all_17_methods_and_332_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / "chrome"
            gradlew = root / "gradlew"
            artifact = root / "core.klib"
            runner.write_bytes(b"chrome-image")
            gradlew.write_bytes(b"gradle-wrapper")
            artifact.write_bytes(b"staged-core")
            source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=extra_targets.ROOT).decode().strip()
            archive = hashlib.sha256(subprocess.check_output(
                ["git", "-c", "core.autocrlf=false", "archive", "--format=tar", "HEAD"],
                cwd=extra_targets.ROOT)).hexdigest()
            cases = extra_targets.declared_cases()
            groups = []
            for case in cases:
                method = extra_targets.method_for_case(case)
                if not groups or groups[-1][0] != method:
                    groups.append((method, []))
                groups[-1][1].append(case)
            groups.extend((method, []) for method in sorted(extra_targets.RECORDER_METHODS))
            self.assertEqual(len(set(method for method, _ in groups)), 17)
            segments = []
            invocations = []
            xml_streams = {}
            combined = bytearray()
            for index, (method, method_cases) in enumerate(groups):
                slot = root / f"method-{index:02}"
                slot.mkdir()
                raw_rows = bytearray()
                for case in method_cases:
                    plain = b"".join((json.dumps({"kind": kind, "id": case["id"]},
                                                  separators=(",", ":")).encode() + b"\n")
                                     for kind in ("inputs", "case-end"))
                    raw_rows.extend(b"".join(b"NUMERICAL_JSON " + line + b"\n"
                                             for line in plain.splitlines()))
                    segment = root / f"case-{len(segments):03}.jsonl.gz"
                    with gzip.open(segment, "wb") as stream:
                        stream.write(plain)
                    segments.append({"case_id": case["id"], "method": method,
                                     "path": str(segment), "gzip_sha256": extra_targets.digest(segment),
                                     "plain_sha256": hashlib.sha256(plain).hexdigest(),
                                     "plain_bytes": len(plain), "rows": 2,
                                     "observed_index": len(segments)})
                combined.extend(raw_rows)
                raw = slot / "runtime-stdout.gz"
                with gzip.open(raw, "wb") as stream:
                    stream.write(raw_rows)
                console = slot / "browser-console.jsonl"
                console.write_bytes(raw_rows)
                raw_info = {"path": str(raw), "gzip_sha256": extra_targets.digest(raw),
                            "plain_sha256": hashlib.sha256(raw_rows).hexdigest(),
                            "plain_bytes": len(raw_rows)}
                classname = extra_targets.expected_class(method)
                xml_plain = (f'<testsuite tests="1" failures="0" errors="0" skipped="0">\n'
                             f'<testcase classname="jsBrowserTest.portable.{classname}" '
                             f'name="{method}[js, browser, ChromeHeadless155]"/>\n'
                             f'<system-out><![CDATA[\n').encode() + b']]></system-out>\n</testsuite>\n'
                xml = slot / "TEST-portable.xml.gz"
                with gzip.open(xml, "wb") as stream:
                    stream.write(xml_plain)
                xml_key = f"TEST-{index:02}-{method}.xml"
                xml_streams[xml_key] = {"path": str(xml), "gzip_sha256": extra_targets.digest(xml),
                                        "plain_sha256": hashlib.sha256(xml_plain).hexdigest(),
                                        "plain_bytes": len(xml_plain),
                                        "source_name": f"TEST-jsBrowserTest.portable.{classname}.xml"}
                binary = slot / "linked.js"
                loaded = slot / "kotlin/dyn4k-portable-numerical-consumer-test.js"
                loaded.parent.mkdir()
                binary.write_bytes(b"linked-browser-test")
                loaded.write_bytes(binary.read_bytes())
                port = 43000 + index
                config = slot / "karma.conf.js"
                config.write_text(archived_karma_config(loaded, port, console, method))
                profile = f"/tmp/karma-synthetic-{index:02}"
                launch = {"command": [str(runner), f"--user-data-dir={profile}"],
                          "runner_sha256": extra_targets.digest(runner), "pid": index + 1,
                          "process_executable": str(runner),
                          "process_sha256": extra_targets.digest(runner)}
                attestation = slot / "browser-processes.jsonl"
                launches = [launch]
                if index == 0:
                    launches.append({**launch, "pid": 1000 + index})
                attestation.write_text("".join(json.dumps(item) + "\n" for item in launches))
                build_log = slot / "build.log"
                build_log.write_text("BUILD SUCCESSFUL\n")
                invocation = {"index": index, "method": method, "candidate_commit": source,
                              "artifact_sha256": extra_targets.digest(artifact),
                              "build_runner_sha256": extra_targets.digest(gradlew),
                              "build": {"command": [str(gradlew), "-p", str(extra_targets.PORTABLE),
                                                    extra_targets.browser_lock_task("js"), "jsBrowserTest",
                                                    f"-PportableRepository={root / 'staging'}",
                                                    "--rerun-tasks", "--no-daemon", "--console=plain", "--info",
                                                    "--tests", f"portable.{classname}.{method}"],
                                        "exit_code": 0, "timed_out": False, "log": str(build_log),
                                        "log_sha256": extra_targets.digest(build_log)},
                              "browser_attestation": str(attestation),
                              "browser_attestation_sha256": extra_targets.digest(attestation),
                              "browser_processes": launches, "profile": profile,
                              "karma_port": port, "karma_config": str(config),
                              "karma_config_sha256": extra_targets.digest(config),
                              "linked_executable": {"path": str(binary), "sha256": extra_targets.digest(binary)},
                              "loaded_input": {"path": str(loaded), "sha256": extra_targets.digest(loaded),
                                               "source_path": str(loaded)},
                              "console_source": {"path": str(console),
                                                 "sha256": extra_targets.digest(console),
                                                 "plain_bytes": len(raw_rows)},
                              "xml_keys": [xml_key], "raw_stream": raw_info}
                invocations.append(invocation)
            combined_raw = root / "runtime-stdout.gz"
            with gzip.open(combined_raw, "wb") as stream:
                stream.write(combined)
            manifest = {"schema": "portable-numerical-segments/3", "candidate_commit": source,
                        "source_sha256": archive, "route": "js-chromium", "target": "js",
                        "runner": str(runner), "runner_sha256": extra_targets.digest(runner),
                        "artifact": {"path": str(artifact), "sha256": extra_targets.digest(artifact)},
                        "linked_executable": invocations[-1]["linked_executable"],
                        "process": {"command": invocations[0]["browser_processes"][0]["command"],
                                    "exit_code": 0, "timed_out": False},
                        "raw_stream": {"path": str(combined_raw), "gzip_sha256": extra_targets.digest(combined_raw),
                                       "plain_sha256": hashlib.sha256(combined).hexdigest(),
                                       "plain_bytes": len(combined)},
                        "xml_streams": xml_streams, "browser_invocations": invocations,
                        "segments": segments}
            manifest_path = root / "segments.json"
            assembled = root / "assembled.jsonl"

            def check(value):
                manifest_path.write_text(json.dumps(value))
                assembled.unlink(missing_ok=True)
                return subprocess.run([sys.executable, str(Path(extra_targets.__file__).resolve()),
                                       "--verify-segments", str(manifest_path), "--output", str(assembled)],
                                      capture_output=True, text=True)

            good = check(manifest)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(json.loads(good.stdout)["cases"], 332)
            first_config = Path(invocations[0]["karma_config"])
            original_config = first_config.read_text()
            for override in (
                'config.set({files: []});\n',
                'config.set({customLaunchers: {ChromeHeadless: {base: "Firefox"}}});\n',
                'config.set = function() {}; config.set({browsers: []});\n',
            ):
                first_config.write_text(original_config + override)
                altered = json.loads(json.dumps(manifest))
                altered["browser_invocations"][0]["karma_config_sha256"] = extra_targets.digest(first_config)
                self.assertNotEqual(check(altered).returncode, 0, override)
            first_config.write_text(original_config.replace(
                f'"{invocations[0]["loaded_input"]["source_path"]}"', '"/dev/null"', 1))
            altered = json.loads(json.dumps(manifest))
            altered["browser_invocations"][0]["karma_config_sha256"] = extra_targets.digest(first_config)
            self.assertNotEqual(check(altered).returncode, 0, "initial file set changed")
            first_config.write_text(original_config)
            for change in (
                lambda value: value["browser_invocations"].pop(),
                lambda value: value["browser_invocations"].__setitem__(0, value["browser_invocations"][1]),
                lambda value: value["browser_invocations"][0]["build"]["command"].__setitem__(-1, "wrongMethod"),
                lambda value: value["browser_invocations"][0]["build"].__setitem__("exit_code", 1),
                lambda value: value["browser_invocations"][0].__setitem__("karma_port", 1),
                lambda value: value["browser_invocations"][1].__setitem__(
                    "profile", value["browser_invocations"][0]["profile"]),
                lambda value: value["browser_invocations"][0]["loaded_input"].__setitem__("sha256", "0" * 64),
                lambda value: value["browser_invocations"][0]["console_source"].__setitem__("sha256", "0" * 64),
                lambda value: value["browser_invocations"][0]["xml_keys"].clear(),
                lambda value: value["browser_invocations"][0]["raw_stream"].__setitem__("plain_sha256", "0" * 64),
            ):
                bad = json.loads(json.dumps(manifest))
                change(bad)
                self.assertNotEqual(check(bad).returncode, 0)
            pair = ("geometryCollisionBoundaryAndScale", "continuousCollisionCasesAtFrozenRates")
            bounded = json.loads(json.dumps(manifest))
            bounded["bounded_methods"] = list(pair)
            selected = [item for item in bounded["browser_invocations"] if item["method"] in pair]
            for index, item in enumerate(selected):
                item["index"] = index
            bounded["browser_invocations"] = selected
            bounded["linked_executable"] = selected[-1]["linked_executable"]
            bounded["xml_streams"] = {key: bounded["xml_streams"][key]
                                      for item in selected for key in item["xml_keys"]}
            bounded["segments"] = [entry for entry in bounded["segments"] if entry["method"] in pair]
            for index, entry in enumerate(bounded["segments"]):
                entry["observed_index"] = index
            pair_plain = b"".join(gzip.decompress(Path(item["raw_stream"]["path"]).read_bytes())
                                  for item in selected)
            with gzip.open(combined_raw, "wb") as stream:
                stream.write(pair_plain)
            bounded["raw_stream"].update(gzip_sha256=extra_targets.digest(combined_raw),
                                         plain_sha256=hashlib.sha256(pair_plain).hexdigest(),
                                         plain_bytes=len(pair_plain))
            self.assertEqual(json.loads(check(bounded).stdout)["cases"], 87)
            reversed_pair = json.loads(json.dumps(bounded))
            reversed_pair["bounded_methods"].reverse()
            self.assertNotEqual(check(reversed_pair).returncode, 0)
            wasm_pair = json.loads(json.dumps(bounded))
            wasm_pair["route"] = "wasm-js-chromium"
            wasm_pair["target"] = "wasmJs"
            for item in wasm_pair["browser_invocations"]:
                item["build"]["command"][3:5] = ["kotlinWasmUpgradeYarnLock", "wasmJsBrowserTest"]
                slot = Path(item["loaded_input"]["path"]).parent.parent
                loader = slot / "static/load.mjs"
                loader.parent.mkdir()
                loader.write_text('import "../kotlin/dyn4k-portable-numerical-consumer-test.mjs"\n')
                module = slot / "kotlin/dyn4k-portable-numerical-consumer-test.mjs"
                module.write_text('const input = "dyn4k-portable-numerical-consumer-test.wasm"\n')
                linked = slot / "linked.mjs"
                linked.write_bytes(module.read_bytes())
                packaged_wasm = module.with_suffix(".wasm")
                packaged_wasm.write_bytes(b"linked-wasm-binary")
                linked_wasm = linked.with_suffix(".wasm")
                linked_wasm.write_bytes(packaged_wasm.read_bytes())
                config = Path(item["karma_config"])
                config.write_text(archived_karma_config(
                    loader, item["karma_port"], Path(item["console_source"]["path"]),
                    item["method"], "wasmJs"))
                item["karma_config_sha256"] = extra_targets.digest(config)
                item["loaded_input"] = {"path": str(loader), "sha256": extra_targets.digest(loader),
                                        "source_path": str(loader)}
                item["linked_executable"] = {"path": str(linked),
                                             "sha256": extra_targets.digest(linked),
                                             "source_path": str(linked)}
                for key, path in (("package", module), ("linked_wasm", linked_wasm),
                                  ("packaged_wasm", packaged_wasm)):
                    item[key] = {"path": str(path), "sha256": extra_targets.digest(path),
                                 "source_path": str(path)}
                item["support_inputs"] = {}
                for name in extra_targets.WASM_HELPERS:
                    original = slot / name
                    packaged = module.parent / name
                    original.write_text(name + "\n")
                    packaged.write_bytes(original.read_bytes())
                    item["support_inputs"][name] = {
                        "linked": {"path": str(original), "sha256": extra_targets.digest(original),
                                   "source_path": str(original)},
                        "package": {"path": str(packaged), "sha256": extra_targets.digest(packaged),
                                    "source_path": str(packaged)}}
                for key in item["xml_keys"]:
                    xml_item = wasm_pair["xml_streams"][key]
                    xml_path = Path(xml_item["path"])
                    xml_plain = gzip.decompress(xml_path.read_bytes()).replace(
                        b"jsBrowserTest", b"wasmJsBrowserTest")
                    with gzip.open(xml_path, "wb") as stream:
                        stream.write(xml_plain)
                    xml_item.update(gzip_sha256=extra_targets.digest(xml_path),
                                    plain_sha256=hashlib.sha256(xml_plain).hexdigest(),
                                    plain_bytes=len(xml_plain),
                                    source_name=xml_item["source_name"].replace(
                                        "jsBrowserTest", "wasmJsBrowserTest"))
            wasm_pair["linked_executable"] = wasm_pair["browser_invocations"][-1]["linked_executable"]
            self.assertEqual(json.loads(check(wasm_pair).stdout)["cases"], 87)
            for key in ("package", "linked_wasm", "packaged_wasm"):
                altered = json.loads(json.dumps(wasm_pair))
                altered["browser_invocations"][0][key]["sha256"] = "0" * 64
                self.assertNotEqual(check(altered).returncode, 0)
            altered = json.loads(json.dumps(wasm_pair))
            altered["browser_invocations"][0]["support_inputs"][extra_targets.WASM_HELPERS[0]][
                "linked"]["sha256"] = "0" * 64
            self.assertNotEqual(check(altered).returncode, 0)

    def test_public_segment_cli_requires_exact_332_case_inventory_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / "runner"
            binary = root / "test.wasm"
            artifact = root / "core.klib"
            for path in (runner, binary, artifact):
                path.write_bytes(path.name.encode())
            source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=extra_targets.ROOT).decode().strip()
            archive = hashlib.sha256(subprocess.check_output(
                ["git", "-c", "core.autocrlf=false", "archive", "--format=tar", "HEAD"],
                cwd=extra_targets.ROOT)).hexdigest()
            segments = []
            raw_rows = []
            active_method = None
            for index, case in enumerate(extra_targets.declared_cases()):
                method = extra_targets.method_for_case(case)
                if method != active_method:
                    if active_method is not None:
                        raw_rows.append(f"##teamcity[testFinished name='{active_method}' flowId='one']\n".encode())
                    raw_rows.append(f"##teamcity[testStarted name='{method}' flowId='one']\n".encode())
                    active_method = method
                plain = (json.dumps({"kind": "inputs", "id": case["id"]}, separators=(",", ":")) + "\n" +
                         json.dumps({"kind": "case-end", "id": case["id"]},
                                    separators=(",", ":")) + "\n").encode()
                raw_rows.extend(b"NUMERICAL_JSON " + line + b"\n" for line in plain.splitlines())
                path = root / f"case-{index:03}.jsonl.gz"
                with gzip.open(path, "wb") as stream:
                    stream.write(plain)
                segments.append({"case_id": case["id"], "method": extra_targets.method_for_case(case),
                                 "path": str(path), "gzip_sha256": extra_targets.digest(path),
                                 "plain_sha256": hashlib.sha256(plain).hexdigest(),
                                 "plain_bytes": len(plain), "rows": 2,
                                 "observed_index": index})
            raw_rows.append(f"##teamcity[testFinished name='{active_method}' flowId='one']\n".encode())
            raw = root / "runtime-stdout.gz"
            raw_plain = b"".join(raw_rows)
            with gzip.open(raw, "wb") as stream:
                stream.write(raw_plain)
            manifest = {"schema": "portable-numerical-segments/1", "candidate_commit": source,
                        "source_sha256": archive, "route": "wasm-wasi-wasmtime", "target": "wasmWasi",
                        "runner": str(runner), "runner_sha256": extra_targets.digest(runner),
                        "linked_executable": {"path": str(binary), "sha256": extra_targets.digest(binary)},
                        "artifact": {"path": str(artifact), "sha256": extra_targets.digest(artifact)},
                        "process": {"command": [str(runner), str(binary)], "exit_code": 0,
                                    "timed_out": False},
                        "raw_stream": {"path": str(raw), "gzip_sha256": extra_targets.digest(raw),
                                       "plain_sha256": hashlib.sha256(raw_plain).hexdigest(),
                                       "plain_bytes": len(raw_plain)},
                        "segments": segments}
            manifest_path = root / "manifest.json"
            assembled = root / "assembled.jsonl"

            def check(value, env=None):
                manifest_path.write_text(json.dumps(value))
                assembled.unlink(missing_ok=True)
                return subprocess.run([sys.executable, str(Path(extra_targets.__file__).resolve()),
                                       "--verify-segments", str(manifest_path), "--output", str(assembled)],
                                      capture_output=True, text=True, env=env)

            good = check(manifest)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(len(assembled.read_text().splitlines()), 664)
            self.assertEqual(len(segments), 332)
            autocrlf_env = dict(os.environ, GIT_CONFIG_COUNT="1",
                                GIT_CONFIG_KEY_0="core.autocrlf", GIT_CONFIG_VALUE_0="true")
            with_autocrlf = check(manifest, autocrlf_env)
            self.assertEqual(with_autocrlf.returncode, 0, with_autocrlf.stderr)
            self.assertEqual(json.loads(with_autocrlf.stdout)["cases"], 332)
            wrong_source = json.loads(json.dumps(manifest))
            wrong_source["source_sha256"] = "0" * 64
            self.assertNotEqual(check(wrong_source, autocrlf_env).returncode, 0)
            wrong_segment = json.loads(json.dumps(manifest))
            wrong_segment["segments"][0]["plain_sha256"] = "0" * 64
            self.assertNotEqual(check(wrong_segment, autocrlf_env).returncode, 0)
            manifest_path.write_text(json.dumps(manifest))
            assembled.unlink(missing_ok=True)
            archival = subprocess.run([sys.executable, str(Path(extra_targets.__file__).resolve()),
                                       "--verify-segments", str(manifest_path), "--output", str(assembled),
                                       "--replay-source", source], capture_output=True, text=True)
            self.assertEqual(archival.returncode, 0, archival.stderr)
            native_manifest = json.loads(json.dumps(manifest))
            native_manifest["route"] = "linux-arm64"
            native_manifest["target"] = "linuxArm64"
            native_lines = []
            for line in raw_rows:
                if line.startswith(b"##teamcity[testStarted "):
                    method = line.decode().split("'")[1]
                    native_lines.append(f"[ RUN      ] portable.{extra_targets.expected_class(method)}.{method}\n".encode())
                elif line.startswith(b"##teamcity[testFinished "):
                    method = line.decode().split("'")[1]
                    native_lines.append(f"[       OK ] portable.{extra_targets.expected_class(method)}.{method}\n".encode())
                else:
                    native_lines.append(line)
            native_plain = b"".join(native_lines)
            with gzip.open(raw, "wb") as stream:
                stream.write(native_plain)
            native_manifest["raw_stream"].update(gzip_sha256=extra_targets.digest(raw),
                                                 plain_sha256=hashlib.sha256(native_plain).hexdigest(),
                                                 plain_bytes=len(native_plain))
            self.assertEqual(check(native_manifest).returncode, 0)
            wrong_native = json.loads(json.dumps(native_manifest))
            wrong_native_plain = (b"[ RUN      ] portable.PortableMatrixTest.longRunningFreeMotionInvariantScene\n" +
                                  b"".join(line for line in native_lines if line.startswith(b"NUMERICAL_JSON ")) +
                                  b"[       OK ] portable.PortableMatrixTest.longRunningFreeMotionInvariantScene\n")
            with gzip.open(raw, "wb") as stream:
                stream.write(wrong_native_plain)
            wrong_native["raw_stream"].update(gzip_sha256=extra_targets.digest(raw),
                                               plain_sha256=hashlib.sha256(wrong_native_plain).hexdigest(),
                                               plain_bytes=len(wrong_native_plain))
            self.assertNotEqual(check(wrong_native).returncode, 0)
            with gzip.open(raw, "wb") as stream:
                stream.write(raw_plain)
            swapped = json.loads(json.dumps(manifest))
            swapped_rows = list(raw_rows)
            swapped_rows[1:5] = swapped_rows[3:5] + swapped_rows[1:3]
            swapped_plain = b"".join(swapped_rows)
            with gzip.open(raw, "wb") as stream:
                stream.write(swapped_plain)
            swapped["raw_stream"].update(gzip_sha256=extra_targets.digest(raw),
                                         plain_sha256=hashlib.sha256(swapped_plain).hexdigest(),
                                         plain_bytes=len(swapped_plain))
            swapped["segments"][0]["observed_index"] = 1
            swapped["segments"][1]["observed_index"] = 0
            self.assertNotEqual(check(swapped).returncode, 0)
            with gzip.open(raw, "wb") as stream:
                stream.write(raw_plain)
            wrong_method = json.loads(json.dumps(manifest))
            wrong_lines = [b"##teamcity[testStarted name='longRunningFreeMotionInvariantScene' flowId='one']\n",
                           *(line for line in raw_rows if line.startswith(b"NUMERICAL_JSON ")),
                           b"##teamcity[testFinished name='longRunningFreeMotionInvariantScene' flowId='one']\n"]
            wrong_plain = b"".join(wrong_lines)
            with gzip.open(raw, "wb") as stream:
                stream.write(wrong_plain)
            wrong_method["raw_stream"].update(gzip_sha256=extra_targets.digest(raw),
                                               plain_sha256=hashlib.sha256(wrong_plain).hexdigest(),
                                               plain_bytes=len(wrong_plain))
            self.assertNotEqual(check(wrong_method).returncode, 0)
            with gzip.open(raw, "wb") as stream:
                stream.write(raw_plain)
            wrong_teamcity = json.loads(json.dumps(manifest))
            named_lines = list(raw_rows)
            payload = named_lines[1].decode().strip()
            named_lines[1] = ("##teamcity[testStdOut name='longRunningFreeMotionInvariantScene' "
                              f"out='{payload}|n' flowId='one']\n").encode()
            named_plain = b"".join(named_lines)
            with gzip.open(raw, "wb") as stream:
                stream.write(named_plain)
            wrong_teamcity["raw_stream"].update(gzip_sha256=extra_targets.digest(raw),
                                                plain_sha256=hashlib.sha256(named_plain).hexdigest(),
                                                plain_bytes=len(named_plain))
            self.assertNotEqual(check(wrong_teamcity).returncode, 0)
            with gzip.open(raw, "wb") as stream:
                stream.write(raw_plain)
            for change in (
                lambda value: value["segments"].pop(),
                lambda value: value["segments"].append(dict(value["segments"][-1])),
                lambda value: value["segments"].__setitem__(0, value["segments"][1]),
                lambda value: value["segments"][0].__setitem__("method", "wrongMethod"),
                lambda value: value["segments"][0].__setitem__("observed_index", 99),
                lambda value: value["segments"][0].__setitem__("plain_sha256", "0" * 64),
                lambda value: value["segments"][0].__setitem__("gzip_sha256", "0" * 64),
                lambda value: value["process"].__setitem__("timed_out", True),
                lambda value: value["process"].__setitem__("exit_code", -9),
                lambda value: value["process"].__setitem__("command", ["/wrong/runner"]),
                lambda value: value["process"].__setitem__("command", [str(runner), "/stale/test.wasm"]),
                lambda value: value["linked_executable"].__setitem__("sha256", "0" * 64),
                lambda value: value["artifact"].__setitem__("sha256", "0" * 64),
                lambda value: value.__setitem__("candidate_commit", "0" * 40),
                lambda value: value.__setitem__("target", "js"),
            ):
                bad = json.loads(json.dumps(manifest))
                change(bad)
                self.assertNotEqual(check(bad).returncode, 0)
            segments[0]["path"] = str(root / "missing.gz")
            self.assertNotEqual(check(manifest).returncode, 0)
            segments[0]["path"] = str(root / "case-000.jsonl.gz")
            original = Path(segments[0]["path"]).read_bytes()
            Path(segments[0]["path"]).write_bytes(original[:-8])
            self.assertNotEqual(check(manifest).returncode, 0)
            Path(segments[0]["path"]).write_bytes(original)
            altered = (json.dumps({"kind": "inputs", "id": segments[0]["case_id"],
                                   "altered": True}, separators=(",", ":")) + "\n" +
                       json.dumps({"kind": "case-end", "id": segments[0]["case_id"]},
                                  separators=(",", ":")) + "\n").encode()
            with gzip.open(segments[0]["path"], "wb") as stream:
                stream.write(altered)
            altered_manifest = json.loads(json.dumps(manifest))
            altered_manifest["segments"][0].update(
                gzip_sha256=extra_targets.digest(Path(segments[0]["path"])),
                plain_sha256=hashlib.sha256(altered).hexdigest(), plain_bytes=len(altered))
            self.assertNotEqual(check(altered_manifest).returncode, 0)
            Path(segments[0]["path"]).write_bytes(original)
            with gzip.open(raw, "wb") as stream:
                stream.write(b"changed raw producer output\n")
            manifest["raw_stream"]["gzip_sha256"] = extra_targets.digest(raw)
            self.assertNotEqual(check(manifest).returncode, 0)
            with gzip.open(raw, "wb") as stream:
                stream.write(raw_plain)
            browser_manifest = json.loads(json.dumps(manifest))
            browser_manifest["raw_stream"]["gzip_sha256"] = extra_targets.digest(raw)
            browser_manifest["route"] = "js-chromium"
            browser_manifest["target"] = "js"
            browser_plain = b"".join(line for line in raw_rows if line.startswith(b"NUMERICAL_JSON "))
            with gzip.open(raw, "wb") as stream:
                stream.write(browser_plain)
            browser_manifest["raw_stream"].update(gzip_sha256=extra_targets.digest(raw),
                                                  plain_sha256=hashlib.sha256(browser_plain).hexdigest(),
                                                  plain_bytes=len(browser_plain))
            xml_parts = [b'<testsuite tests="17" failures="0" errors="0" skipped="0">\n']
            for method in sorted(extra_targets.ALL_METHODS):
                classname = f"jsBrowserTest.portable.{extra_targets.expected_class(method)}"
                xml_parts.append(f'<testcase classname="{classname}" name="{method}[js, browser, ChromeHeadless155]">\n'.encode())
                if method == "longRunningFreeMotionInvariantScene":
                    xml_parts.extend((b"<system-out><![CDATA[\n", browser_plain,
                                      b"]]></system-out>\n"))
                xml_parts.append(b"</testcase>\n")
            xml_parts.append(b"</testsuite>\n")
            xml_plain = b"".join(xml_parts)
            xml_path = root / "TEST-portable.xml.gz"
            with gzip.open(xml_path, "wb") as stream:
                stream.write(xml_plain)
            browser_manifest["xml_streams"] = {"TEST-portable.xml": {
                "path": str(xml_path), "gzip_sha256": extra_targets.digest(xml_path),
                "plain_sha256": hashlib.sha256(xml_plain).hexdigest(),
                "plain_bytes": len(xml_plain)}}
            self.assertNotEqual(check(browser_manifest).returncode, 0)
            bounded_browser = json.loads(json.dumps(browser_manifest))
            bounded_browser["bounded_geometry"] = True
            bounded_browser["segments"] = bounded_browser["segments"][:75]
            bounded_plain = b"".join(line for line in browser_plain.splitlines(keepends=True)[:150])
            with gzip.open(raw, "wb") as stream:
                stream.write(bounded_plain)
            bounded_browser["raw_stream"].update(gzip_sha256=extra_targets.digest(raw),
                                                 plain_sha256=hashlib.sha256(bounded_plain).hexdigest(),
                                                 plain_bytes=len(bounded_plain))
            bounded_xml = (b'<testsuite tests="1" failures="0" errors="0" skipped="0">\n'
                           b'<testcase classname="jsBrowserTest.portable.PortableMatrixTest" '
                           b'name="geometryCollisionBoundaryAndScale[js, browser, ChromeHeadless155]">\n'
                           b'<system-out><![CDATA[\n' + bounded_plain +
                           b']]></system-out>\n</testcase>\n</testsuite>\n')
            with gzip.open(xml_path, "wb") as stream:
                stream.write(bounded_xml)
            bounded_browser["xml_streams"]["TEST-portable.xml"].update(
                gzip_sha256=extra_targets.digest(xml_path),
                plain_sha256=hashlib.sha256(bounded_xml).hexdigest(), plain_bytes=len(bounded_xml))
            self.assertEqual(check(bounded_browser).returncode, 0)
            with gzip.open(raw, "wb") as stream:
                stream.write(browser_plain)
            with gzip.open(xml_path, "wb") as stream:
                stream.write(xml_plain)
            xml_plain = xml_plain.replace(b"NUMERICAL_JSON", b"CHANGED_JSON", 1)
            with gzip.open(xml_path, "wb") as stream:
                stream.write(xml_plain)
            browser_manifest["xml_streams"]["TEST-portable.xml"].update(
                gzip_sha256=extra_targets.digest(xml_path),
                plain_sha256=hashlib.sha256(xml_plain).hexdigest(), plain_bytes=len(xml_plain))
            self.assertNotEqual(check(browser_manifest).returncode, 0)

    def test_process_capture_compresses_exact_stdout_and_times_out(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "stdout.gz"
            process = extra_targets.run_command([sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'a' * 1500000)"],
                                                root, log, timeout_seconds=10)
            self.assertEqual(process["exit_code"], 0)
            self.assertFalse(process["timed_out"])
            self.assertEqual(process["plain_bytes"], 1500000)
            self.assertEqual(process["plain_sha256"], hashlib.sha256(b"a" * 1500000).hexdigest())
            self.assertEqual(gzip.decompress(log.read_bytes()), b"a" * 1500000)
            timeout = extra_targets.run_command([sys.executable, "-c", "import time;time.sleep(5)"],
                                                root, root / "timeout.gz", timeout_seconds=0.1)
            self.assertTrue(timeout["timed_out"])
            self.assertNotEqual(timeout["exit_code"], 0)

    def test_segment_extraction_rejects_lost_case_end_and_retains_large_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = extra_targets.declared_cases()[:2]
            raw = root / "raw.gz"
            rows = []
            for case in cases:
                rows.extend(({"kind": "inputs", "id": case["id"], "data": "x" * 1100000},
                             {"kind": "case-end", "id": case["id"]}))
            with gzip.open(raw, "wt") as stream:
                for row in rows:
                    stream.write("NUMERICAL_JSON " + json.dumps(row) + "\n")
            entries = extra_targets.segment_trace(raw, root / "cases", cases, 0)
            self.assertEqual([entry["case_id"] for entry in entries], [case["id"] for case in cases])
            self.assertEqual(sum(entry["plain_bytes"] for entry in entries) > 2200000, True)
            with gzip.open(raw, "wt") as stream:
                for row in rows[:-1]:
                    stream.write("NUMERICAL_JSON " + json.dumps(row) + "\n")
            with self.assertRaisesRegex(Rejected, "incomplete"):
                extra_targets.segment_trace(raw, root / "truncated", cases, 0)

    def test_all_approved_targets_have_a_task_and_runtime(self):
        self.assertEqual(len({route.target for route in ROUTES.values()}), 21)
        self.assertEqual(ROUTES["android-native-x64"].task, "linkDebugTestAndroidNativeX64")
        self.assertEqual(ROUTES["js-chromium"].task, "jsBrowserTest")
        self.assertEqual(ROUTES["wasm-wasi-wasmtime"].task,
                         "compileTestDevelopmentExecutableKotlinWasmWasi")
        self.assertEqual(browser_lock_task("js"), "kotlinUpgradeYarnLock")
        self.assertEqual(browser_lock_task("wasmJs"), "kotlinWasmUpgradeYarnLock")
        self.assertEqual(bounded_gradle_filter(ROUTES["android-native-x64"], True), [])
        self.assertEqual(bounded_gradle_filter(ROUTES["js-chromium"], True),
                         ["--tests", "portable.PortableMatrixTest.geometryCollisionBoundaryAndScale"])
        filtered = extra_targets.wasmtime_invocation(Path("/runner"), Path("/test.wasm"), True)
        self.assertEqual(filtered[-3:], ["portable-numerical", "--include",
                                         "portable.PortableMatrixTest.geometryCollisionBoundaryAndScale"])
        self.assertEqual(extra_targets.wasmtime_invocation(Path("/runner"), Path("/test.wasm"), False)[-1],
                         "/test.wasm")

    def test_browser_full_plan_rejects_a_method_revisited_after_other_cases(self):
        cases = extra_targets.declared_cases()
        geometry = next(case for case in cases if case["family"] == "geometry-collision")
        ccd = next(case for case in cases if case["family"] == "ccd")
        with self.assertRaisesRegex(Rejected, "revisits"):
            extra_targets.browser_capture_plan([geometry, ccd, geometry], True)

    def test_input_identity_rejects_wrong_source_artifact_and_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "candidate.klib"
            artifact.write_bytes(b"published")
            expected_digest = hashlib.sha256(b"published").hexdigest()
            verify_inputs("a" * 40, "a" * 40, "android-native-x64",
                          "android-native-x64", artifact, expected_digest)
            for source, target, digest in (("b" * 40, "android-native-x64", expected_digest),
                                           ("a" * 40, "linux-x64", expected_digest),
                                           ("a" * 40, "android-native-x64", "0" * 64)):
                with self.assertRaises(Rejected):
                    verify_inputs("a" * 40, source, "android-native-x64", target, artifact, digest)

    def test_process_requires_selected_runner_and_successful_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / "runner"
            runner.write_bytes(b"runner")
            digest = hashlib.sha256(b"runner").hexdigest()
            verify_process(runner, digest, 0, [str(runner), "test"])
            for path, expected, code, command in ((runner, "0" * 64, 0, [str(runner)]),
                                                  (runner, digest, 1, [str(runner)]),
                                                  (runner, digest, 0, ["/other/runner"]),
                                                  (root / "missing", digest, 0, [str(runner)])):
                with self.assertRaises(Rejected):
                    verify_process(path, expected, code, command)

    def test_full_method_set_rejects_missing_extra_failed_and_ignored(self):
        expected = {"one", "two"}
        verify_methods({"one": "passed", "two": "passed"}, expected)
        for observed in ({"one": "passed"}, {"one": "passed", "two": "passed", "three": "passed"},
                         {"one": "passed", "two": "failed"}, {"one": "passed", "two": "ignored"}):
            with self.assertRaises(Rejected):
                verify_methods(observed, expected)

    def test_trace_is_streamed_and_requires_fresh_case_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.txt"
            trace = root / "trace.jsonl"
            row = {"kind": "inputs", "id": "one"}
            raw.write_text("NUMERICAL_JSON " + json.dumps(row) + "\n")
            self.assertEqual(collect_trace(raw, trace, raw.stat().st_mtime_ns - 1), 1)
            self.assertEqual(json.loads(trace.read_text()), row)
            self.assertEqual(observed_counts(trace)["inputs"], 1)
            with self.assertRaises(Rejected):
                collect_trace(raw, root / "stale.jsonl", raw.stat().st_mtime_ns + 1)
            raw.write_text("ordinary test output\n")
            with self.assertRaises(Rejected):
                collect_trace(raw, root / "empty.jsonl", 0)

    def test_native_summary_rejects_false_pass_and_ignored_case(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "native.txt"
            raw.write_text("[ RUN      ] portable.PortableMatrixTest.geometryCollisionBoundaryAndScale\n"
                           "[       OK ] portable.PortableMatrixTest.geometryCollisionBoundaryAndScale (1 ms)\n"
                           "[  PASSED  ] 1 tests.\n")
            self.assertEqual(native_methods(raw), {"geometryCollisionBoundaryAndScale": "passed"})
            raw.write_text(raw.read_text() + "[ DISABLED ] other\n")
            with self.assertRaises(Rejected):
                native_methods(raw)
            raw.write_text("[ RUN      ] portable.PortableMatrixTest.geometryCollisionBoundaryAndScale\n"
                           "[  PASSED  ] 1 tests.\n")
            with self.assertRaises(Rejected):
                native_methods(raw)

    def test_browser_xml_rejects_wrong_target_and_skips(self):
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / "TEST-matrix.xml"
            def write(classname, body=""):
                xml.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0">'
                               f'<testcase classname="{classname}" name="geometryCollisionBoundaryAndScale[js, browser, ChromeHeadless155.0, Linux]">'
                               f'{body}</testcase></testsuite>')
            write("jsBrowserTest.portable.PortableMatrixTest")
            self.assertEqual(browser_methods(xml.parent, 0, "jsBrowserTest", "ChromeHeadless"),
                             {"geometryCollisionBoundaryAndScale": "passed"})
            write("jsNodeTest.portable.PortableMatrixTest")
            with self.assertRaises(Rejected):
                browser_methods(xml.parent, 0, "jsBrowserTest", "ChromeHeadless")
            write("jsBrowserTest.portable.PortableMatrixTest", "<skipped/>")
            with self.assertRaises(Rejected):
                browser_methods(xml.parent, 0, "jsBrowserTest", "ChromeHeadless")
            with self.assertRaises(Rejected):
                browser_methods(xml.parent, xml.stat().st_mtime_ns + 1)

    def test_browser_karma_uses_a_unique_temporary_port(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with isolated_karma_port(root) as first:
                config = root / "karma.config.d/portable-port.js"
                self.assertIn(f"config.set({{port: {first}}});", config.read_text())
                self.assertIn("pingTimeout: 28800000", config.read_text())
                self.assertIn("browserNoActivityTimeout: 28800000", config.read_text())
                self.assertIn("browserDisconnectTimeout: 28800000", config.read_text())
                self.assertIn("LineSeparatedReporter", config.read_text())
                with self.assertRaisesRegex(Rejected, "already present"):
                    with isolated_karma_port(root):
                        pass
            self.assertFalse(config.exists())
            self.assertFalse(config.parent.exists())

    def test_browser_karma_config_must_load_selected_port(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "karma.conf.js"
            method = "geometryCollisionBoundaryAndScale"
            console = root / "numerical.jsonl"
            loaded = root / "kotlin/dyn4k-portable-numerical-consumer-test.js"
            valid = archived_karma_config(loaded, 43210, console, method)
            checks = {"target": "js", "method": method, "browser": "ChromeHeadless",
                      "loaded_input": str(loaded)}
            generated.write_text(valid.replace("port: 43210", "port: 9876"))
            with self.assertRaises(Rejected):
                extra_targets.verify_karma_port(generated, 43210, console, **checks)
            generated.write_text(valid.replace("pingTimeout: 28800000", "pingTimeout: 100"))
            with self.assertRaises(Rejected):
                extra_targets.verify_karma_port(generated, 43210, console, **checks)
            generated.write_text(valid.replace("LineSeparatedReporter", "DisabledReporter"))
            with self.assertRaises(Rejected):
                extra_targets.verify_karma_port(generated, 43210, console, **checks)
            generated.write_text(valid)
            extra_targets.verify_karma_port(generated, 43210, console, **checks)

    def test_wasmtime_case_and_trace_require_finished_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "wasmtime.txt"
            trace = root / "trace.jsonl"
            lines = ["##teamcity[testSuiteStarted name='portable' flowId='one']",
                     "##teamcity[testSuiteStarted name='PortableMatrixTest' flowId='one']",
                     "##teamcity[testStarted name='geometryCollisionBoundaryAndScale' flowId='one']",
                     "##teamcity[testStdOut name='geometryCollisionBoundaryAndScale' out='NUMERICAL_JSON {\"kind\":\"inputs\",\"id\":\"one\"}|n' flowId='one']",
                     "##teamcity[testFinished name='geometryCollisionBoundaryAndScale' flowId='one']",
                     "##teamcity[testSuiteFinished name='PortableMatrixTest' flowId='one']",
                     "##teamcity[testSuiteFinished name='portable' flowId='one']"]
            raw.write_text("\n".join(lines) + "\n")
            self.assertEqual(wasmtime_methods(raw), {"geometryCollisionBoundaryAndScale": "passed"})
            self.assertEqual(collect_trace(raw, trace, 0), 1)
            self.assertEqual(json.loads(trace.read_text())["id"], "one")
            raw.write_text("\n".join(lines[:4] + ["##teamcity[testFailed name='geometryCollisionBoundaryAndScale' flowId='one']"] + lines[4:]) + "\n")
            with self.assertRaises(Rejected):
                verify_methods(wasmtime_methods(raw), {"geometryCollisionBoundaryAndScale"})
            raw.write_text("\n".join(lines[:-1]) + "\n")
            with self.assertRaises(Rejected):
                wasmtime_methods(raw)

    def test_concatenated_teamcity_stdout_retains_every_numerical_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "teamcity.gz"
            content = ("##teamcity[testStdOut name='method' out='"
                       "NUMERICAL_JSON {\"kind\":\"inputs\",\"id\":\"one\"}|n"
                       "NUMERICAL_JSON {\"kind\":\"case-end\",\"id\":\"one\"}|n"
                       "' flowId='one']\n")
            with gzip.open(raw, "wt") as stream:
                stream.write(content)
            self.assertEqual([row["kind"] for row in extra_targets.trace_rows(raw)],
                             ["inputs", "case-end"])

    def test_missing_native_and_hosted_runner_fails_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            for key in ("android-native-arm64", "macos-arm64", "wasm-wasi-wasmtime"):
                output = Path(directory) / key
                args = SimpleNamespace(route=key, output=output, configuration="debug",
                                       runner=None, runner_arg=[], expected_version=None)
                self.assertEqual(extra_targets.run(args), 1)
                self.assertIn("runner is absent", json.loads((output / "receipt.json").read_text())["reason"])

    def test_guest_command_binds_api_abi_fingerprint_and_bounded_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adb = root / "adb"
            binary = root / "test.kexe"
            adb.write_bytes(b"adb")
            binary.write_bytes(b"native-binary")
            properties = {"ro.build.version.sdk": "37", "ro.product.cpu.abi": "x86_64",
                          "ro.boot.qemu.avd_name": "dyn4k_api37_play_x64",
                          "ro.build.fingerprint": extra_targets.ANDROID_GUEST_FINGERPRINT}
            def command(argv, **_):
                if "devices" in argv:
                    value = "List of devices attached\nemulator-5558 device product:sdk\n"
                elif "getprop" in argv:
                    value = properties[argv[-1]] + "\n"
                elif "sha256sum" in argv:
                    value = hashlib.sha256(b"native-binary").hexdigest() + "  test.kexe\n"
                else:
                    value = ""
                return SimpleNamespace(returncode=0, stdout=value, stderr="")
            with patch.object(extra_targets.subprocess, "run", side_effect=command):
                invocation, guest = extra_targets.guest_command(adb, binary, root, True)
                self.assertIn("--ktest_filter=portable.PortableMatrixTest.geometryCollisionBoundaryAndScale",
                              invocation)
                self.assertEqual(guest["remote_sha256"], hashlib.sha256(b"native-binary").hexdigest())
                properties["ro.build.fingerprint"] = "different-build"
                with self.assertRaisesRegex(Rejected, "wrong Android Native guest"):
                    extra_targets.guest_command(adb, binary, root, True)

    def test_browser_launcher_attests_execed_process_image(self):
        with tempfile.TemporaryDirectory() as directory:
            attestation = Path(directory) / "browser.jsonl"
            runner = Path("/bin/sleep").resolve()
            environment = dict(os.environ, DYN4K_NUMERICAL_BROWSER=str(runner),
                               DYN4K_NUMERICAL_ATTESTATION=str(attestation), DYN4K_BROWSER="chromium")
            done = subprocess.run([sys.executable, str(Path(extra_targets.__file__).resolve()), "0.5"],
                                  env=environment, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            launched = [json.loads(line) for line in attestation.read_text().splitlines()]
            self.assertEqual(len(launched), 1)
            self.assertEqual(launched[0]["process_executable"], str(runner))
            self.assertEqual(launched[0]["process_sha256"], extra_targets.digest(runner))

    def test_source_guard_rejects_ignored_production_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("tools/numerical/portable/src/build/\n")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c",
                            "user.email=test@example.com", "commit", "-qm", "seed"], check=True)
            ignored = root / "tools/numerical/portable/src/build/Hidden.kt"
            ignored.parent.mkdir(parents=True)
            ignored.write_text("class Hidden\n")
            with patch.object(extra_targets, "ROOT", root):
                with self.assertRaisesRegex(Rejected, "ignored portable source"):
                    extra_targets.source_identity()

    def test_source_identity_uses_canonical_archive_with_autocrlf_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "source.txt").write_text("first\nsecond\n")
            subprocess.run(["git", "-C", str(root), "add", "source.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c",
                            "user.email=test@example.com", "commit", "-qm", "seed"], check=True)
            commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
            canonical = hashlib.sha256(subprocess.check_output(
                ["git", "-C", str(root), "-c", "core.autocrlf=false", "archive", "--format=tar",
                 "HEAD"])).hexdigest()
            converted = hashlib.sha256(subprocess.check_output(
                ["git", "-C", str(root), "-c", "core.autocrlf=true", "archive", "--format=tar",
                 "HEAD"])).hexdigest()
            self.assertNotEqual(canonical, converted)
            with patch.object(extra_targets, "ROOT", root), patch.dict(
                    os.environ, {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.autocrlf",
                                 "GIT_CONFIG_VALUE_0": "true"}):
                self.assertEqual(extra_targets.source_identity(), (commit, canonical))


if __name__ == "__main__":
    unittest.main()
