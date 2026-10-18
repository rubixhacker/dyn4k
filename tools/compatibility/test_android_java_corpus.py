from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import android_java_corpus


ROOT = Path(__file__).resolve().parents[2]
ORIGIN = ROOT
UPSTREAM = Path("/tmp/dyn4k-baseline-cache/dyn4j-source")
REPORT = ROOT / "tools/compatibility/receipts/android-java-corpus-0681a8cd/report.json"
ANDROID_JAR = ROOT / "dyn4k-core/build/intermediates/aar_main_jar/androidMain/syncAndroidMainLibJars/classes.jar"


@unittest.skipUnless(REPORT.is_file() and ANDROID_JAR.is_file() and UPSTREAM.is_dir(),
                     "pinned Android Java corpus inputs unavailable")
class AndroidJavaCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads((ROOT / "tools/compatibility/declaration-ledger.json").read_text())
        cls.report = json.loads(REPORT.read_text())
        cls.build = json.loads((ROOT / "tools/compatibility/receipts/"
                                "candidate-android-build-0681a8cd.json").read_text())
        cls.jvm = json.loads((ROOT / "tools/compatibility/receipts/"
                              "java-corpus-0681a8cd/report.json").read_text())

    def checked(self, report=None, ledger=None, build=None):
        return android_java_corpus.check(report or self.report, ledger or self.ledger,
                                         ROOT, UPSTREAM, ORIGIN, build or self.build, self.jvm)

    def test_all_eight_android_host_lanes_replay_all_pinned_cases(self):
        self.assertIsNone(self.checked())

    def test_changed_commit_artifact_or_source_fails(self):
        for kind in ("commit", "artifact", "source"):
            report = copy.deepcopy(self.report)
            ledger = copy.deepcopy(self.ledger)
            if kind == "commit":
                report["candidate_commit"] = "0" * 40
            elif kind == "artifact":
                report["artifact_sha256"] = "0" * 64
            else:
                ledger["tests"][0]["sha256"] = "0" * 64
            self.assertIsNotNone(self.checked(report, ledger), kind)

    def test_missing_or_changed_host_case_or_build_receipt_fails(self):
        for kind in ("host", "case", "receipt"):
            report = copy.deepcopy(self.report)
            if kind == "host":
                del report["lanes"]["candidate-javac21-java21"]
            elif kind == "case":
                report["lanes"]["candidate-javac21-java21"]["xml_sha256"] = "0" * 64
            else:
                report["build_receipt_sha256"] = "0" * 64
            self.assertIsNotNone(self.checked(report), kind)


if __name__ == "__main__":
    unittest.main()
