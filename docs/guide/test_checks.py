from __future__ import annotations

import unittest

import check_links


class GuideAdverseControlsTest(unittest.TestCase):
    def test_assignment_example_accepts_a_declared_body(self) -> None:
        guide = (
            "### Vector assignment and shared mutation\n\n"
            "```kotlin\n"
            "val body = Body()\n"
            "val sharedVelocity = body.linearVelocity\n"
            "var localVelocity = sharedVelocity\n"
            "localVelocity += Vector2(1.0, 0.0)\n"
            "check(localVelocity !== sharedVelocity)\n"
            "sharedVelocity.add(Vector2(0.0, 1.0))\n"
            "check(body.linearVelocity === sharedVelocity)\n"
            "```\n"
        )
        self.assertEqual([], check_links.check_assignment_example(guide))

    def test_assignment_example_rejects_an_undeclared_body(self) -> None:
        guide = (
            "### Vector assignment and shared mutation\n\n"
            "```kotlin\n"
            "val sharedVelocity = body.linearVelocity\n"
            "var localVelocity = sharedVelocity\n"
            "localVelocity += Vector2(1.0, 0.0)\n"
            "check(localVelocity !== sharedVelocity)\n"
            "```\n"
        )
        errors = check_links.check_assignment_example(guide)
        self.assertTrue(any("body" in error and "declared" in error for error in errors))

    def test_candidate_mapping_claim_is_rejected_without_mapping_evidence(self) -> None:
        claim = "The independently recorded candidate mapping supplies `--expected-provider-sha256 <value>`."
        errors = check_links.check_candidate_mapping_claim(claim)
        self.assertTrue(any("candidate mapping claim" in error for error in errors))

    def test_default_penetration_failure_cannot_be_reported_as_passed(self) -> None:
        claim = "The default profile penetration passed at 125,847 of 126,000 samples."
        errors = check_links.check_guide_claims(claim)
        self.assertTrue(any("penetration passed at 125,847" in error for error in errors))

    def test_combined_named_module_result_requires_revision_and_provider_hash(self) -> None:
        guide = "A bounded named-module result was recorded."
        errors = check_links.check_guide_claims(guide)
        self.assertTrue(any("combined-head source revision" in error for error in errors))
        self.assertTrue(any("combined-head provider SHA" in error for error in errors))
        self.assertTrue(any("combined-head qualification boundary" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
