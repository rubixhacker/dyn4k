import subprocess
import tempfile
import unittest
from pathlib import Path

from full import (build_task_marker, check_cases, graph_section, parse_list,
                  parse_test_run, source_identity, validate_deployment_output)


class FullCorpusTests(unittest.TestCase):
    def test_root_and_external_task_markers_match_gradle_output(self):
        self.assertEqual(build_task_marker(":dyn4k-core:linkDebugTestAndroidNativeX64"),
                         "> Task :dyn4k-core:linkDebugTestAndroidNativeX64")
        self.assertEqual(build_task_marker("linkReleaseExecutableAndroidNativeX64"),
                         "> Task :linkReleaseExecutableAndroidNativeX64")

    def test_adb_push_transfer_report_may_be_on_stderr(self):
        validate_deployment_output(b"", b"1 file pushed\n", b"", b"abc  /data/local/tmp/test\n", b"", "abc")
        with self.assertRaises(ValueError):
            validate_deployment_output(b"", b"1 file pushed\n", b"", b"def  /data/local/tmp/test\n", b"", "abc")

    def test_native_listing_and_process_require_exact_cases(self):
        listing = b"p.AlphaTest.\n  first\n  second\np.BetaTest.\n  third\n"
        names = parse_list(listing)
        self.assertEqual(names, ["p.AlphaTest.first", "p.AlphaTest.second", "p.BetaTest.third"])
        self.assertEqual(check_cases(names, set(names)), 3)
        with self.assertRaises(ValueError):
            check_cases(names[:-1], set(names))
        with self.assertRaises(ValueError):
            check_cases(names + names[:1], set(names))
        with self.assertRaises(ValueError):
            parse_list(listing + b"FORGED PASS\n")

        transcript = ("[==========] Running 3 tests from 2 test cases.\n"
                      "[ RUN      ] p.AlphaTest.first\n"
                      "[       OK ] p.AlphaTest.first (0 ms)\n"
                      "[ RUN      ] p.AlphaTest.second\n"
                      "[       OK ] p.AlphaTest.second (1 ms)\n"
                      "[ RUN      ] p.BetaTest.third\n"
                      "[       OK ] p.BetaTest.third (0 ms)\n"
                      "[==========] 3 tests from 2 test cases ran. (1 ms total)\n"
                      "[  PASSED  ] 3 tests.\n").encode()
        self.assertEqual(parse_test_run(transcript), names)
        mutants = (
            transcript.replace(b"[ RUN      ] p.BetaTest.third\n[       OK ] p.BetaTest.third (0 ms)\n", b""),
            transcript.replace(b"[ RUN      ] p.BetaTest.third", b"[ RUN      ] p.AlphaTest.first"),
            transcript + b"[  PASSED  ] 3 tests.\n",
            transcript.replace(b"[       OK ] p.BetaTest.third", b"[  FAILED  ] p.BetaTest.third"),
            transcript.replace(b"[       OK ] p.BetaTest.third", b"[  SKIPPED ] p.BetaTest.third"),
            transcript.replace(b"[  PASSED  ] 3 tests.", b"[  PASSED  ] 2 tests."),
        )
        for mutant in mutants:
            with self.subTest(mutant=mutant[-80:]), self.assertRaises(ValueError):
                parse_test_run(mutant)

    def test_dependency_provider_and_graph_changes_fail(self):
        external = (b"androidNativeX64CompileKlibraries - Compile classpath.\n"
                    b"+--- org.jetbrains.kotlin:kotlin-stdlib:2.4.20\n"
                    b"+--- io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1\n"
                    b"|    \\--- io.github.rubixhacker:dyn4k-core-androidnativex64:0.1.0-alpha.1\n"
                    b"\\--- io.github.rubixhacker:dyn4k:0.1.0-alpha.1\n"
                    b"     \\--- io.github.rubixhacker:dyn4k-androidnativex64:0.1.0-alpha.1\n\n")
        self.assertIn("dyn4k-core", graph_section(external, "consumer"))
        for provider in (b"org.dyn4j:dyn4j:6.0.0", b"project :unapproved", b"example:other:1.0"):
            with self.subTest(provider=provider), self.assertRaises(ValueError):
                graph_section(external.replace(b"\n\n", b"\n+--- " + provider + b"\n\n"), "consumer")

    def test_source_checkout_drift_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            source = root / "source.kt"
            source.write_text("one\n")
            subprocess.run(["git", "-C", str(root), "add", "source.kt"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c",
                            "user.email=test@example.invalid", "commit", "-q", "-m", "fixture"], check=True)
            identity = source_identity(root)
            self.assertEqual(len(identity[0]), 40)
            source.write_text("two\n")
            with self.assertRaisesRegex(ValueError, "not clean"):
                source_identity(root)
            source.write_text("one\n")
            (root / "extra.kt").write_text("extra\n")
            with self.assertRaisesRegex(ValueError, "not clean"):
                source_identity(root)


if __name__ == "__main__":
    unittest.main()
