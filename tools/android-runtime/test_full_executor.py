import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
JDK = Path("/tmp/dyn4k-tools/jdk21")


class FullExecutorTest(unittest.TestCase):
    def test_assumption_failure_is_a_failed_installed_case(self):
        cache = Path.home() / ".gradle/caches/modules-2/files-2.1"
        junit = list((cache / "junit/junit/4.13.2").rglob("junit-4.13.2.jar"))
        hamcrest = list((cache / "org.hamcrest/hamcrest-core/1.3").rglob("hamcrest-core-1.3.jar"))
        self.assertEqual((len(junit), len(hamcrest)), (1, 1))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            sources = {
                "android/content/Context.java": (
                    "package android.content; public class Context { "
                    "public android.content.res.AssetManager getAssets() { return new android.content.res.AssetManager(); } "
                    "public ClassLoader getClassLoader() { return getClass().getClassLoader(); } }"),
                "android/content/res/AssetManager.java": (
                    "package android.content.res; public class AssetManager { "
                    "public java.io.InputStream open(String name) throws Exception { "
                    "return new java.io.FileInputStream(name); } }"),
                "SkippedCase.java": (
                    "public class SkippedCase { @org.junit.Test public void skips() { "
                    "org.junit.Assume.assumeTrue(false); } }"),
                "Harness.java": (
                    "public class Harness { public static void main(String[] args) throws Exception { "
                    "for (String[] row : io.github.rubixhacker.dyn4k.full.FullCorpusExecutor.runAll("
                    "new android.content.Context())) System.out.println(row[0] + \" \" + row[1]); } }"),
            }
            for name, body in sources.items():
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body)
            (directory / "cases.tsv").write_text("dyn4k-core:SkippedCase#skips\tSkippedCase\tskips\n")
            classpath = os.pathsep.join((str(junit[0]), str(hamcrest[0]), str(directory)))
            executor = ROOT / "consumers/android-runtime/full/src/main/java/io/github/rubixhacker/dyn4k/full/FullCorpusExecutor.java"
            subprocess.run([str(JDK / "bin/javac"), "-cp", classpath, "-d", str(directory),
                            *map(str, directory.rglob("*.java")), str(executor)], check=True)
            result = subprocess.run([str(JDK / "bin/java"), "-cp", classpath, "Harness"],
                                    cwd=directory, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), "dyn4k-core:SkippedCase#skips FAILED")


if __name__ == "__main__":
    unittest.main()
