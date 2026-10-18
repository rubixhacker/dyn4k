import hashlib
import tempfile
import unittest
from pathlib import Path

import prepare


class GeneratedConsumerProvenanceTest(unittest.TestCase):
    def test_rejects_changed_generated_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            originals = {}
            generated = {}
            for name in prepare.CONSUMERS:
                relative_source = Path("dyn4k-core/src/jvmConsumer/java") / (name + ".java")
                relative_copy = Path("consumers/android-runtime/app/build/generated/consumer-java") / (name + ".java")
                source = root / relative_source
                copy = root / relative_copy
                source.parent.mkdir(parents=True, exist_ok=True)
                copy.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("class " + Path(name).name + " {}\n")
                copy.write_bytes(source.read_bytes())
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                originals[str(relative_source)] = digest
                generated[str(relative_copy)] = {"source": str(relative_source), "sha256": digest}
            manifest = {"consumer_sources": originals, "generated_consumer_sources": generated}
            self.assertEqual(prepare.verify_consumer_sources(root, manifest), generated)
            changed = root / next(iter(generated))
            changed.write_bytes(changed.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "generated consumer source changed"):
                prepare.verify_consumer_sources(root, manifest)

    def test_rejects_unlisted_generated_java_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated = root / "consumers/android-runtime/app/build/generated/consumer-java"
            generated.mkdir(parents=True)
            (generated / "Extra.java").write_text("class Extra {}\n")
            with self.assertRaisesRegex(ValueError, "generated consumer source set"):
                prepare.verify_consumer_sources(root, {"consumer_sources": {}, "generated_consumer_sources": {}})

    def test_rejects_generated_copy_mapped_to_another_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            originals = {}
            generated = {}
            digest = hashlib.sha256(b"same bytes\n").hexdigest()
            for name in prepare.CONSUMERS:
                source = Path("dyn4k-core/src/jvmConsumer/java") / (name + ".java")
                copy = Path("consumers/android-runtime/app/build/generated/consumer-java") / (name + ".java")
                for path in (source, copy):
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"same bytes\n")
                originals[str(source)] = digest
                generated[str(copy)] = {"source": str(source), "sha256": digest}
            first, second = list(generated)[:2]
            generated[first]["source"] = generated[second]["source"]
            with self.assertRaisesRegex(ValueError, "mapping"):
                prepare.verify_consumer_sources(root, {"consumer_sources": originals,
                                                      "generated_consumer_sources": generated})
