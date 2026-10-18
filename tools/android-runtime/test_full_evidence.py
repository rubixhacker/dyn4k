import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

import full_evidence
import run_full
from android_corpus import FINGERPRINTS


CASE = "dyn4k-core:org.dyn4j.CoreTest#works"
CONSUMER = "external-kotlin:io.github.rubixhacker.dyn4k.full.FullKotlinJourney#run"
RAW = "\n".join((
    "INSTRUMENTATION_STATUS: class=io.github.rubixhacker.dyn4k.full.FullJourneyTest",
    "INSTRUMENTATION_STATUS: test=allInstalledCases",
    "INSTRUMENTATION_STATUS: numtests=1",
    "INSTRUMENTATION_STATUS_CODE: 1",
    f"INSTRUMENTATION_STATUS: dyn4k_case={CASE}",
    "INSTRUMENTATION_STATUS: dyn4k_status=PASSED",
    "INSTRUMENTATION_STATUS_CODE: 0",
    f"INSTRUMENTATION_STATUS: dyn4k_case={CONSUMER}",
    "INSTRUMENTATION_STATUS: dyn4k_status=PASSED",
    "INSTRUMENTATION_STATUS_CODE: 0",
    "INSTRUMENTATION_STATUS: class=io.github.rubixhacker.dyn4k.full.FullJourneyTest",
    "INSTRUMENTATION_STATUS: test=allInstalledCases",
    "INSTRUMENTATION_STATUS: numtests=1",
    "INSTRUMENTATION_STATUS_CODE: 0",
    "INSTRUMENTATION_RESULT: stream=",
    "OK (1 test)",
    "INSTRUMENTATION_CODE: -1",
    "",
))


def complete_graph(providers):
    rows = ["DYN4K_BUILD_JDK javaHome=/tmp/dyn4k-tools/jdk21 javaVersion=21 gradleVersion=9.5.0"]
    for variant in ("debug", "release"):
        rows.append(f"DYN4K_GRAPH_BEGIN {variant}")
        rows.extend(f"DYN4K_GRAPH_COMPONENT {variant} {name}"
                    for name in sorted(run_full.GRAPH_COMPONENTS))
        rows.extend(f"DYN4K_GRAPH_EDGE {variant} {edge}"
                    for edge in sorted(run_full.GRAPH_EDGES))
        rows.extend(f"DYN4K_GRAPH_ARTIFACT {variant} {coordinate} {providers.get(coordinate, '/unused.jar')}"
                    for coordinate in sorted(run_full.GRAPH_ARTIFACTS))
        rows.append(f"DYN4K_GRAPH_END {variant} 11 15 9")
    return "\n".join(rows) + "\n"


class FullInstalledEvidenceTest(unittest.TestCase):
    def test_provider_graph_rejects_wrong_coordinates_second_provider_and_missing_graph(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            providers = {}
            staged = {}
            for name in ("dyn4k-core-android", "dyn4k-android"):
                aar = root / f"{name}.aar"
                aar.write_bytes(name.encode())
                staged[name] = {"sha256": run_full.sha256(aar)}
                providers[f"io.github.rubixhacker:{name}:0.1.0-alpha.1"] = str(aar)
            prepared = {"staged": staged}
            graph = complete_graph(providers)
            self.assertEqual(set(run_full.validate_provider_artifacts(graph, prepared)),
                             {"debug", "release"})
            for bad in (graph.replace("io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1",
                                      "example.invalid:dyn4k-android:9.9.9"),
                        graph.replace("DYN4K_GRAPH_COMPONENT debug project:full\n", ""),
                        graph.replace("DYN4K_GRAPH_EDGE release project:full junit:junit:4.13.2\n", ""),
                        graph.replace("DYN4K_GRAPH_BEGIN release\n", ""),
                        graph + "DYN4K_GRAPH_ARTIFACT debug org.dyn4j:dyn4j:6.0.0 /unused.jar\n"):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    run_full.validate_provider_artifacts(bad, prepared)

    def test_build_jdk_rejects_wrong_home_version_and_missing_daemon_identity(self):
        good = ("Starting process 'Gradle build daemon'. Working directory: "
                "/tmp/gradle/daemon/9.5.0 Command: /tmp/dyn4k-tools/jdk21/bin/java "
                "org.gradle.launcher.daemon.bootstrap.GradleDaemon 9.5.0\n"
                "DYN4K_BUILD_JDK javaHome=/tmp/dyn4k-tools/jdk21 javaVersion=21 "
                "gradleVersion=9.5.0\nBUILD SUCCESSFUL\n")
        run_full.validate_build_jdk(good)
        for bad in (good.replace("/tmp/dyn4k-tools/jdk21", "/tmp/jdk25"),
                    good.replace("javaVersion=21", "javaVersion=25"),
                    good.replace("gradleVersion=9.5.0", "gradleVersion=9.4"),
                    good.replace("DYN4K_BUILD_JDK", "MISSING_BUILD_JDK")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                run_full.validate_build_jdk(bad)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            daemon = root / "daemon-123.out.log"
            build = root / "build.log"
            build.write_text(good + f"The daemon log file: {daemon}\n")
            daemon.write_text("DefaultDaemonContext[javaHome=/tmp/jdk25,javaVersion=25]\n")
            with self.assertRaisesRegex(ValueError, "raw Gradle daemon"):
                run_full.build_log_identity(build, require_marker=True)
            daemon.write_text("DefaultDaemonContext[javaHome=/tmp/dyn4k-tools/jdk21,"
                              "javaVersion=21,daemonRegistryDir=/tmp]\n")
            run_full.build_log_identity(build, require_marker=True)

    def test_installed_process_log_requires_matching_instrumentation_pid(self):
        package = "io.github.rubixhacker.dyn4k.full"
        log = (f"I ActivityManager: Start proc 4804:{package}/u0a241 for added application {package}\n"
               f"I ActivityManager: Killing 4804:{package}/u0a241 (adj 0): stop {package} "
               "due to finished inst\n")
        self.assertEqual(full_evidence.validate_full_process_log(log, package), "4804")
        for bad in (log.replace("4804:", "4805:", 1),
                    log.replace("finished inst", "crash"),
                    log.replace("Start proc", "Started proc"),
                    log + log):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "instrumentation process"):
                full_evidence.validate_full_process_log(bad, package)

    def test_api21_process_log_requires_matching_started_and_finished_pid(self):
        package = "io.github.rubixhacker.dyn4k.full"
        log = (f"I/ActivityManager( 1485): Start proc {package} for activity "
               f"{package}/.FullActivity: pid=3334 uid=10058 gids={{50058}} abi=x86\n"
               f"I/ActivityManager( 1485): Killing 3334:{package}/u0a58 (adj 0): stop {package}\n"
               f"I/ActivityManager( 1485): Start proc {package} for added application "
               f"{package}: pid=3378 uid=10058 gids={{50058, 9997}} abi=x86\n"
               f"I/ActivityManager( 1485): Force stopping {package} appid=10058 user=0: "
               "finished inst\n"
               f"I/ActivityManager( 1485): Killing 3378:{package}/u0a58 (adj 0): stop {package}\n")
        added = (f"I/ActivityManager( 1485): Start proc {package} for added application "
                 f"{package}: pid=3378 uid=10058 gids={{50058, 9997}} abi=x86\n")
        service = (f"I/ActivityManager( 1485): Start proc {package} for service "
                   f"{package}/.SyncService: pid=3379 uid=10058 gids={{50058}} "
                   "abi=arm64-v8a\n")
        other_activity = (f"I/ActivityManager( 1485): Start proc {package} for activity "
                          f"{package}/.OtherActivity: pid=3379 uid=10058 gids={{50058}} "
                          "abi=arm64-v8a\n")
        external = (f"I/ActivityManager( 1485): Start proc {package}.other for service "
                    f"{package}.other/.SyncService: pid=3379 uid=10059 gids={{50059}} "
                    "abi=arm64-v8a\n")
        self.assertEqual(run_full.validate_api21_process_log(log, package, "x86", "3334"), "3378")
        self.assertEqual(run_full.validate_api21_process_log(
            log.replace(added, added + external), package, "x86", "3334"), "3378")
        with self.assertRaisesRegex(ValueError, "instrumentation process"):
            run_full.validate_api21_process_log(log, package, "x86", "not-a-pid")
        for bad in (log.replace("pid=3378", "pid=3379"),
                    log.replace("finished inst", "crash"),
                    log.replace("appid=10058 user=0: finished inst",
                                "appid=10059 user=0: finished inst"),
                    log.replace("abi=x86\n", "abi=arm64-v8a\n"),
                    log.replace("pid=3334", "pid=3335"),
                    log.replace(f"Killing 3334:{package}", f"Killing 3335:{package}"),
                    log.replace(added, ""),
                    log.replace(added, added + added),
                    log.replace(added, added.replace("abi=x86", "abi=arm64-v8a") + added),
                    log.replace(added, added.replace("pid=3378", "pid=3379") + added),
                    log + f"I/ActivityManager( 1485): Killing 9999:{package}/u0a58 "
                          f"(adj 0): crash {package}\n",
                    log + log):
            with self.subTest(bad=bad[-100:]), self.assertRaisesRegex(ValueError, "instrumentation process"):
                run_full.validate_api21_process_log(bad, package, "x86", "3334")
        for reason, extra in (("service", service),
                              ("service with matching identity", service.replace(
                                  "pid=3379", "pid=3378").replace("abi=arm64-v8a", "abi=x86")),
                              ("other activity", other_activity)):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, "instrumentation process"):
                run_full.validate_api21_process_log(
                    log.replace(added, added + extra), package, "x86", "3334")

    def test_api21_process_list_requires_one_exact_application_pid(self):
        package = "io.github.rubixhacker.dyn4k.full"
        header = "USER PID PPID VSIZE RSS WCHAN PC NAME\n"
        row = f"u0_a58 3334 123 540000 32000 ffffffff 00000000 {package}\n"
        unrelated = "u0_a59 1111 123 540000 32000 ffffffff 00000000 other.app\n"
        self.assertEqual(run_full.api21_process_pid(header + unrelated + row, package), "3334")
        self.assertIsNone(run_full.api21_process_pid(header + unrelated, package, required=False))
        for bad in ("/system/bin/sh: pidof: not found\n", header + unrelated,
                    header + row + row,
                    header + row.replace("3334", "not-a-pid")):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "API 21 app process"):
                run_full.api21_process_pid(bad, package)

    def test_accepts_exact_case_id_set(self):
        result = full_evidence.validate_full_installed(RAW, {CASE, CONSUMER}, 0)
        self.assertEqual(result["portable"]["passed"], 2)

    def test_rejects_missing_extra_duplicate_skip_failure_and_raw_tampering(self):
        variants = (
            RAW.replace(f"INSTRUMENTATION_STATUS: dyn4k_case={CASE}\nINSTRUMENTATION_STATUS: dyn4k_status=PASSED\nINSTRUMENTATION_STATUS_CODE: 0\n", ""),
            RAW.replace(f"dyn4k_case={CASE}", "dyn4k_case=forged:Case#works"),
            RAW.replace("dyn4k_status=PASSED", "dyn4k_status=SKIPPED", 1),
            RAW.replace("dyn4k_status=PASSED", "dyn4k_status=FAILED", 1),
            RAW.replace("OK (1 test)", "OK (2 tests)"),
            RAW.replace("INSTRUMENTATION_CODE: -1", "INSTRUMENTATION_CODE: 0"),
        )
        for raw in variants:
            with self.subTest(raw=raw[-80:]), self.assertRaises(ValueError):
                full_evidence.validate_full_installed(raw, {CASE, CONSUMER}, 0)
        duplicate = RAW.replace(f"INSTRUMENTATION_STATUS: dyn4k_case={CONSUMER}",
                                f"INSTRUMENTATION_STATUS: dyn4k_case={CASE}")
        with self.assertRaises(ValueError):
            full_evidence.validate_full_installed(duplicate, {CASE, CONSUMER}, 0)

    def test_rejects_broad_keep_or_unchanged_engine_dex(self):
        rules = "-keep class io.github.rubixhacker.dyn4k.full.FullActivity { *; }\n"
        mapping = "org.dyn4j.geometry.Vector2 -> a:\norg.dyn4j.dynamics.Body -> b:\n"
        usage = "org.dyn4j.geometry.Unused\n"
        debug = {"Lorg/dyn4j/geometry/Vector2;", "Lorg/dyn4j/dynamics/Body;", "Lc;"}
        release = {"La;", "Lb;"}
        full_evidence.validate_full_r8(rules, mapping, usage, debug, release, minimum_transformed=2)
        with self.assertRaisesRegex(ValueError, "broad keep"):
            full_evidence.validate_full_r8(rules + "-keep class org.dyn4j.** { *; }\n",
                                               mapping, usage, debug, release, minimum_transformed=2)
        with self.assertRaises(ValueError):
            full_evidence.validate_full_r8(rules, mapping, usage, debug, debug, minimum_transformed=2)
        for bad_rules, bad_mapping, bad_usage, bad_dex in (
                (rules + "-keep class org.dyn4j.geometry.Vector2 { *; }\n", mapping, usage, release),
                (rules, mapping.replace("org.dyn4j.dynamics.Body -> b:\n", ""), usage, release),
                (rules, mapping, "", release),
                (rules, mapping, usage, {"La;"})):
            with self.subTest(bad_rules=bad_rules[-80:]), self.assertRaises(ValueError):
                full_evidence.validate_full_r8(bad_rules, bad_mapping, bad_usage, debug,
                                               bad_dex, minimum_transformed=2)

    def test_targeted_x86_member_keep_still_requires_engine_transformation(self):
        matrix = "org.dyn4j.coverage.UpstreamMatrix22CoverageTest"
        rules = (f"-keep,allowoptimization class {matrix} {{ *; }}\n"
                 "-keepclassmembers class org.dyn4j.geometry.Matrix22 "
                 "{ public double normMax(); }\n")
        mapping = "org.dyn4j.geometry.Vector2 -> a:\norg.dyn4j.dynamics.Body -> b:\n"
        usage = "org.dyn4j.geometry.Unused\n"
        debug = {"Lorg/dyn4j/geometry/Vector2;", "Lorg/dyn4j/dynamics/Body;", "Lc;"}
        release = {"La;", "Lb;"}
        self.assertEqual(len(full_evidence.validate_full_r8(
            rules, mapping, usage, debug, release, {matrix}, minimum_transformed=2
        )["transformed_engine_classes"]), 2)
        for bad_rules, bad_release in ((rules + "-keep class org.dyn4j.** { *; }\n", release),
                                       (rules.replace("normMax", "norm*"), release),
                                       (rules + "-keepclassmembers class org.dyn4j.geometry.Matrix22 "
                                        "{ public double normMax(); }\n", release),
                                       (rules + "-keepclassmembers class org.dyn4j.geometry.Matrix22 "
                                        "{ public double normInfinity(); }\n", release),
                                       (rules, debug)):
            with self.subTest(bad_rules=bad_rules, bad_release=bad_release), \
                    self.assertRaises(ValueError):
                full_evidence.validate_full_r8(
                    bad_rules, mapping, usage, debug, bad_release, {matrix},
                    minimum_transformed=2)

    def test_rejects_wrong_resolved_aar_apk_and_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            aar = root / "dyn4k-core-android.aar"
            facade = root / "dyn4k-android.aar"
            aar.write_bytes(b"staged")
            facade.write_bytes(b"facade")
            prepared = {"staged": {"dyn4k-core-android": {"sha256": run_full.sha256(aar)},
                                    "dyn4k-android": {"sha256": run_full.sha256(facade)}}}
            graph = complete_graph({"io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1": str(aar),
                                    "io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1": str(facade)})
            run_full.validate_provider_artifacts(graph, prepared)
            aar.write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "wrong resolved staged AAR"):
                run_full.validate_provider_artifacts(graph, prepared)

            apk = root / "app.apk"
            apk.write_bytes(b"exact")
            manifest = root / "prepared.json"
            jdk = {"java_home": "/tmp/dyn4k-tools/jdk21", "java_version": "21.0.12.1",
                   "gradle_version": "9.5.0"}
            manifest.write_text(json.dumps({"build_jdk": jdk}))
            build_log = ("Starting process 'Gradle build daemon'. Working directory: "
                         "/tmp/gradle/daemon/9.5.0 Command: /tmp/dyn4k-tools/jdk21/bin/java "
                         "org.gradle.launcher.daemon.bootstrap.GradleDaemon 9.5.0\nBUILD SUCCESSFUL\n")
            logs = {}
            for name in ("debug", "release", "provider"):
                path = root / f"{name}.log"
                daemon = root / f"daemon-{len(logs) + 100}.out.log"
                daemon.write_text("DefaultDaemonContext[javaHome=/tmp/dyn4k-tools/jdk21,"
                                  "javaVersion=21,daemonRegistryDir=/tmp]\n")
                path.write_text(build_log + f"The daemon log file: {daemon}\n" +
                                ("DYN4K_BUILD_JDK javaHome=/tmp/dyn4k-tools/jdk21 "
                                             "javaVersion=21 gradleVersion=9.5.0\n" if name == "provider" else ""))
                logs[name] = run_full.build_log_identity(path, require_marker=name == "provider")
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({"candidate_commit": "candidate",
                                           "prepared_sha256": run_full.sha256(manifest),
                                           "build_jdk": jdk, "build_logs": logs,
                                           "artifacts": {"app-debug-apk": {"path": str(apk),
                                                                            "sha256": run_full.sha256(apk)}}}))
            with patch.object(run_full, "build_artifacts", return_value={"app-debug-apk": apk}), \
                    patch.object(run_full, "command", return_value="candidate"), \
                    patch.object(run_full, "current_java", return_value=jdk):
                run_full.verify_build_receipt(root, manifest, root / "provider.log", receipt)
                apk.write_bytes(b"forged")
                with self.assertRaisesRegex(ValueError, "wrong APK"):
                    run_full.verify_build_receipt(root, manifest, root / "provider.log", receipt)
            identity = {"ro.build.fingerprint": FINGERPRINTS["37"], "ro.build.version.sdk": "37",
                        "ro.product.cpu.abi": "x86_64"}
            run_full.validate_runtime(identity, "37", "x86_64", "1")
            with self.assertRaisesRegex(ValueError, "wrong installed runtime"):
                run_full.validate_runtime({**identity, "ro.build.fingerprint": "forged"},
                                          "37", "x86_64", "1")
            for api, abi, boot in (("36", "x86_64", "1"), ("37", "arm64-v8a", "1"),
                                   ("37", "x86_64", "0")):
                with self.assertRaisesRegex(ValueError, "wrong installed runtime"):
                    run_full.validate_runtime(identity, api, abi, boot)

    def test_api21_runtime_requires_exact_google_image_and_primary_abi(self):
        expected = {
            "x86_64": "generic_x86_64/sdk_google_phone_x86_64/generic_x86_64:5.0.2/LSY66K/6695550:eng/test-keys",
            "x86": "generic_x86/sdk_google_phone_x86/generic_x86:5.0.2/LSY66K/6695550:eng/test-keys",
        }
        for abi, fingerprint in expected.items():
            identity = {"ro.build.fingerprint": fingerprint, "ro.build.version.sdk": "21",
                        "ro.product.cpu.abi": abi}
            with self.subTest(abi=abi):
                run_full.validate_runtime(identity, "21", abi, "1")
                for wrong, wrong_abi, boot in (({**identity, "ro.build.fingerprint": "forged"}, abi, "1"),
                                               (identity, "arm64-v8a", "1"),
                                               (identity, abi, "0")):
                    with self.assertRaisesRegex(ValueError, "wrong installed runtime"):
                        run_full.validate_runtime(wrong, "21", wrong_abi, boot)

    def test_cli_accepts_api21_for_full_installed_route(self):
        with patch("sys.argv", ["run_full.py", "--prepared", "prepared.json",
                                "--provider-artifacts", "providers.txt",
                                "--build-receipt", "receipt.json", "--build-type", "debug",
                                "--expected-api", "21", "--expected-abi", "x86",
                                "--output", "out"]), \
                patch.object(run_full, "run", return_value={"status": "PASSED", "cases": {}}) as execute:
            run_full.main()
            self.assertEqual(execute.call_args.args[0].expected_api, "21")


if __name__ == "__main__":
    unittest.main()
