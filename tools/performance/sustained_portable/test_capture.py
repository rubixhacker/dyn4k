import json
from types import SimpleNamespace
import unittest

import capture


class PortableCaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(capture.MANIFEST.read_text())
        cls.scenario = capture.scenario_from_manifest(
            cls.manifest, "separated.default.small.30hz.direct_kotlin")
        cls.hashes = {"core": "a" * 64, "kotlin": "b" * 64}
        cls.source = "c" * 40
        cls.nonce = "d" * 32

    def protocol(self):
        scenario = self.scenario
        lines = [
            ["PROVIDER", scenario["api"], self.source, self.hashes["core"],
             self.hashes["kotlin"], scenario["id"], "development", self.nonce],
            ["CONSTRUCTION", "100", "0"],
            ["CLOCK", "warmup", "0", "1", "3"],
            ["RESET", "after_warmup", "1"],
            ["CLOCK", "measure", "0", "4", "10"],
            ["STEP", "0", "6", "2", "0", "100", "0", "100",
             "75.0", "0.0", "0", "0", "0", "0", "0", "0"],
            ["RUN", scenario["api"], "timing", "1", "1", "10", "1",
             "memory_attribution_missing", "plateau_missing", "unpassed"],
        ]
        return ("\n".join("DYN4K\t" + "\t".join(row) for row in lines) + "\n").encode()

    def validate(self, payload):
        return capture.validate_protocol(
            payload, self.scenario, self.source, self.hashes,
            "development", self.nonce, 1, 1, "timing")

    def test_manifest_rejects_baseline_and_unknown_scenario(self):
        with self.assertRaisesRegex(ValueError, "requires direct_kotlin or compatibility"):
            capture.scenario_from_manifest(
                self.manifest, "separated.default.small.30hz.baseline")
        with self.assertRaisesRegex(ValueError, "no unique scenario"):
            capture.scenario_from_manifest(self.manifest, "missing")

    def test_complete_protocol_preserves_raw_clock_and_activity(self):
        clocks, steps, provider, run = self.validate(self.protocol())
        self.assertEqual(clocks["measure"], [(0, 4, 10)])
        self.assertEqual(int(steps[0][7]), 100)
        self.assertEqual(provider[1], "direct_kotlin")
        self.assertEqual(run[-1], "unpassed")

    def test_rejects_substituted_provider(self):
        payload = self.protocol().replace(b"\taaaaaaaaaa", b"\teeeeeeeeee")
        with self.assertRaisesRegex(ValueError, "provider"):
            self.validate(payload)

    def test_rejects_missing_reset_and_truncated_clock(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "reset"):
            self.validate(payload.replace(b"DYN4K\tRESET\tafter_warmup\t1\n", b""))
        with self.assertRaisesRegex(ValueError, "clock stream"):
            self.validate(payload.replace(b"DYN4K\tCLOCK\tmeasure\t0\t4\t10\n", b""))

    def test_rejects_fake_activity_or_performance_pass(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "fixture activity"):
            self.validate(payload.replace(b"\t100\t0\t100\t75.0", b"\t1\t0\t100\t75.0"))
        with self.assertRaisesRegex(ValueError, "unfinished evidence"):
            self.validate(payload.replace(b"\tplateau_missing\tunpassed", b"\tplateau_missing\tpassed"))

    def test_rejects_phase_swap_and_run_activity_mismatch(self):
        payload = self.protocol()
        with self.assertRaisesRegex(ValueError, "wrong phase"):
            self.validate(payload.replace(b"CLOCK\twarmup", b"CLOCK\tother")
                          .replace(b"CLOCK\tmeasure", b"CLOCK\twarmup")
                          .replace(b"CLOCK\tother", b"CLOCK\tmeasure"))
        with self.assertRaisesRegex(ValueError, "activity count"):
            self.validate(payload.replace(b"\t10\t1\tmemory_attribution",
                                          b"\t10\t0\tmemory_attribution"))

    def test_rejects_wrong_source_before_process_launch(self):
        request = SimpleNamespace(target="linuxX64", mode="timing",
                                  steps=1, warmup=0, build="development",
                                  scenario=self.scenario["id"], source_sha=self.source)
        with self.assertRaisesRegex(ValueError, "source SHA"):
            capture.capture(request)
        with self.assertRaisesRegex(ValueError, "absolute regular file"):
            capture.required_file("relative.klib", "core")


if __name__ == "__main__":
    unittest.main()
