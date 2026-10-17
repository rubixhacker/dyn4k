import hashlib
import tempfile
import unittest
from pathlib import Path

from candidate_runner import check_route, verify_hashes


class CandidateRouteTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.core = self.root / "io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar"
        self.api = self.root / "io/github/rubixhacker/dyn4k-jvm/0.1.0-alpha.1/dyn4k-jvm-0.1.0-alpha.1.jar"
        for path in (self.core, self.api):
            path.parent.mkdir(parents=True)
            path.write_bytes(path.name.encode())

    def test_missing_and_crossed_staged_routes_fail(self):
        check_route("direct_kotlin", [self.api, self.core], self.root)
        check_route("compatibility", [self.core], self.root)
        with self.assertRaises(ValueError):
            check_route("direct_kotlin", [self.core], self.root)
        with self.assertRaises(ValueError):
            check_route("compatibility", [self.api, self.core], self.root)

    def test_upstream_provider_and_stale_binary_fail(self):
        upstream = self.root / "dyn4j-6.0.0.jar"
        upstream.write_bytes(b"upstream")
        with self.assertRaises(ValueError):
            check_route("compatibility", [self.core, upstream], self.root)
        expected = {str(self.core): hashlib.sha256(self.core.read_bytes()).hexdigest()}
        verify_hashes(expected)
        self.core.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            verify_hashes(expected)


if __name__ == "__main__":
    unittest.main()
