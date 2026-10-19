import os
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import full_android_adapter as subject
import full_android_consumer
import independent_gates


EVIDENCE = os.environ.get("DYN4K_RETAINED_ANDROID_EVIDENCE")
CORE = "9eaf8113aa62365b2ca0a4a9e5fe13615271ad2e22f3a8c414633ffcde824a53"
FACADE = "352e3433ba8af93ad7ace849b0baa4abd35cf5262c8aead9109e9c140c8547ed"
ROUTES = (
    ("android:Android JVM:minimum:debug", "full-android-api21-bb2-sol-run/replay-checkout",
     "full-android-api21-bb2-sol-run/archives/api21-x64-debug-1",
     "09ef68ead49c0be97ebc0422b918845978a7421e",
     "9126d7c4da87f5df9978cf8647a73d22cd3470df1d7d9b0329b3f4ddf303436e",
     "7bfd8373dbd54adbd89494ceb745d15a1bba09fb987b380a1745f3a22695c072",
     "8bb8af96a50dbf6182b21540c2075300879bb032b74a9f709f6778160e08dc5a"),
    ("android:Android JVM:minimum:r8-optimized", "full-android-api21-bb2-sol-run/replay-checkout",
     "full-android-api21-bb2-sol-run/archives/api21-x64-r8-1",
     "09ef68ead49c0be97ebc0422b918845978a7421e",
     "89cbaee3d01167f044b4195dd37848648dd5a0df52e15a4081213641a5636f55",
     "1bff0cc2ce2a323ae5d30143d4fc95e45f9bdaab9b66e3e5af1b40ca5a6b10a1",
     "8bb8af96a50dbf6182b21540c2075300879bb032b74a9f709f6778160e08dc5a"),
    ("android:Android JVM:current:debug", "full-staged-android-112-sol-final/replay-checkout",
     "full-staged-android-112-sol-final/api37-debug",
     "415acaacc4415ca1b2d2fa4abda0b6c6c78f9d4a",
     "5e38aa2ddc28934672c887111cb1a39947aa29f98f3543d6754a687e7a776f3e",
     "824f227a12e410ffb5bd07ff5bde9dc9e207d649b3570c24eaf4f06b9b1ee296",
     "89c057851c524665a4f7024f3b461b5e2bd10b4924c7aeb3a61c1445abc3f036"),
    ("android:Android JVM:current:r8-optimized", "full-staged-android-112-sol-final/replay-checkout",
     "full-staged-android-112-sol-final/api37-release",
     "415acaacc4415ca1b2d2fa4abda0b6c6c78f9d4a",
     "7f6d38a88e61137a6bd17a770c80d2c15e1b77c2c086e4b4df8ae3dacb43cd50",
     "a2e7c7fc58f02b25e6464036ec7a22c775efadfce95b99007fd9c41684ea6657",
     "89c057851c524665a4f7024f3b461b5e2bd10b4924c7aeb3a61c1445abc3f036"),
)


class ContractTests(unittest.TestCase):
    def test_unsupported_lane_fails_without_archive_access(self):
        with self.assertRaisesRegex(ValueError, "does not cover lane"):
            subject.verify_full_android_staged_consumer(
                Path("/missing"), "a" * 40, "android:Android JVM:minimum:other",
                {}, Path("/missing"), {}, {})

    def test_missing_signed_source_digest_fails_without_archive_access(self):
        expected = {"expected_artifact_hashes": {"dyn4k-core": CORE, "dyn4k": FACADE},
                    "expected_runtime_identity": "a" * 64,
                    "expected_archive_digests": {"staged-consumer": "b" * 64}}
        with self.assertRaisesRegex(ValueError, "source/toolchain identity is incomplete"):
            subject.verify_full_android_staged_consumer(
                Path("/missing"), "a" * 40, ROUTES[0][0], {}, Path("/missing"),
                expected, {"gate": "staged-consumer", "status": "PASSED",
                           "complete_selected_suite": True})


@unittest.skipUnless(EVIDENCE, "set DYN4K_RETAINED_ANDROID_EVIDENCE for retained replay")
class RetainedReplayTests(unittest.TestCase):
    @staticmethod
    def inputs(row):
        lane, checkout, archive, candidate, digest, runtime, source = row
        checkout = Path(EVIDENCE) / checkout
        archive = Path(EVIDENCE) / archive
        manifest, cases = full_android_consumer.approved_cases(checkout)
        selected = {"case_ids": [case["id"] for case in cases]}
        expected = {
            "expected_artifact_hashes": {"dyn4k-core": CORE, "dyn4k": FACADE},
            "expected_runtime_identity": runtime,
            "expected_archive_digests": {"staged-consumer": digest},
            "expected_android_source_toolchain_sha256": source,
        }
        gate = independent_gates.evaluate_gate(
            "staged-consumer", archive, candidate, lane, manifest["lanes"][lane],
            checkout, expected["expected_artifact_hashes"], runtime,
            expected_archive_digest=digest, manifest=manifest)
        return checkout, candidate, lane, selected, archive, expected, gate

    def test_four_retained_complete_android_routes(self):
        for row in ROUTES:
            with self.subTest(lane=row[0]):
                arguments = self.inputs(row)
                self.assertEqual(arguments[-1]["status"], "PASSED")
                public = subject.verify_full_android_staged_consumer(*arguments)
                self.assertEqual(public["cases"], 2523)
                self.assertEqual(public["gate"], arguments[-1])

    def test_missing_and_wrong_signed_expectations_fail(self):
        arguments = list(self.inputs(ROUTES[0]))
        for field in ("expected_android_source_toolchain_sha256",
                      "expected_runtime_identity", "expected_archive_digests"):
            with self.subTest(missing=field):
                changed = arguments[5].copy()
                changed.pop(field)
                with self.assertRaises(ValueError):
                    subject.verify_full_android_staged_consumer(*arguments[:5], changed,
                                                                arguments[6])
        changed = arguments[5].copy()
        changed["expected_android_source_toolchain_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "source/toolchain digest differs"):
            subject.verify_full_android_staged_consumer(*arguments[:5], changed, arguments[6])
        for field in ("expected_runtime_identity", "expected_archive_digests"):
            with self.subTest(wrong=field):
                changed = arguments[5].copy()
                changed[field] = ("a" * 64 if field == "expected_runtime_identity"
                                  else {"staged-consumer": "a" * 64})
                with self.assertRaises(ValueError):
                    subject.verify_full_android_staged_consumer(*arguments[:5], changed,
                                                                arguments[6])
        changed = arguments[5].copy()
        changed["expected_artifact_hashes"] = {"dyn4k-core": "a" * 64, "dyn4k": FACADE}
        with self.assertRaises(ValueError):
            subject.verify_full_android_staged_consumer(*arguments[:5], changed, arguments[6])
        selected = {"case_ids": arguments[3]["case_ids"][:-1]}
        with self.assertRaisesRegex(ValueError, "different approved case suite"):
            subject.verify_full_android_staged_consumer(*arguments[:3], selected,
                                                        *arguments[4:])

    def test_wrong_lane_candidate_and_gate_fail(self):
        arguments = list(self.inputs(ROUTES[0]))
        for index, value in ((1, ROUTES[2][3]), (2, "android:Android JVM:minimum:unsupported")):
            with self.subTest(index=index):
                changed = arguments.copy()
                changed[index] = value
                with self.assertRaises(ValueError):
                    subject.verify_full_android_staged_consumer(*changed)
        changed = arguments.copy()
        changed[-1] = {**arguments[-1], "selected_cases": 1}
        with self.assertRaisesRegex(ValueError, "differs from independent gate"):
            subject.verify_full_android_staged_consumer(*changed)

    def test_resealed_process_tamper_fails_public_replay(self):
        arguments = list(self.inputs(ROUTES[0]))
        arguments[4] = (Path(EVIDENCE) / "full-android-api21-bb2-sol-run/archives/"
                        "api21-x64-debug-ps-tampered")
        arguments[5] = {**arguments[5], "expected_archive_digests": {
            "staged-consumer": "a23139ee41b4260924ed0d3bda36655d8090d23122c287a260586343abcfac1f"}}
        with self.assertRaisesRegex(ValueError, "process snapshots differ"):
            subject.verify_full_android_staged_consumer(*arguments)


if __name__ == "__main__":
    unittest.main()
