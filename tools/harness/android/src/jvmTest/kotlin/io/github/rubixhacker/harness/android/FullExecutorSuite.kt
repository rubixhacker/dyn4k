package io.github.rubixhacker.harness.android

import de.infix.testBalloon.framework.core.testSuite
import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * `tools/android-runtime/test_full_executor.py`.
 *
 * The installed full app runs frozen JUnit cases through `FullCorpusExecutor`, so a JUnit assumption
 * failure must be reported as a FAILED case rather than escaping or being counted as a skip. The case is
 * exercised by compiling the executor with a real `javac` and running it; the pinned JDK 21 is only one
 * possible compiler.
 */
val FullExecutorContract by testSuite {
    test("assumption failure is a failed installed case") {
        val junit = gradleJar("junit/junit/4.13.2", "junit-4.13.2.jar")
        val hamcrest = gradleJar("org.hamcrest/hamcrest-core/1.3", "hamcrest-core-1.3.jar")
        assertEquals(1, junit.size, "pinned junit JAR in the Gradle cache")
        assertEquals(1, hamcrest.size, "pinned hamcrest JAR in the Gradle cache")
        val javac = javac()
        val repository = repositoryRoot()
        val executor = repository.resolve(
            "consumers/android-runtime/full/src/main/java/io/github/rubixhacker/dyn4k/full/" +
                "FullCorpusExecutor.java",
        )
        assertTrue(Files.isRegularFile(executor), "the full corpus executor source is present")

        withTempDirectory { directory ->
            val sources = linkedMapOf(
                "android/content/Context.java" to
                    "package android.content; public class Context { " +
                    "public android.content.res.AssetManager getAssets() " +
                    "{ return new android.content.res.AssetManager(); } " +
                    "public ClassLoader getClassLoader() { return getClass().getClassLoader(); } }",
                "android/content/res/AssetManager.java" to
                    "package android.content.res; public class AssetManager { " +
                    "public java.io.InputStream open(String name) throws Exception " +
                    "{ return new java.io.FileInputStream(name); } }",
                "SkippedCase.java" to
                    "public class SkippedCase { @org.junit.Test public void skips() { " +
                    "org.junit.Assume.assumeTrue(false); } }",
                "Harness.java" to
                    "public class Harness { public static void main(String[] args) throws Exception { " +
                    "for (String[] row : io.github.rubixhacker.dyn4k.full.FullCorpusExecutor.runAll(" +
                    "new android.content.Context())) " +
                    "System.out.println(row[0] + \" \" + row[1]); } }",
            )
            for ((name, body) in sources) writeFile(directory, name, body)
            writeFile(directory, "cases.tsv", "dyn4k-core:SkippedCase#skips\tSkippedCase\tskips\n")
            val classpath = listOf(junit[0], hamcrest[0], directory)
                .joinToString(File.pathSeparator)
            val javaSources = Files.walk(directory).use { stream ->
                stream.filter {
                    Files.isRegularFile(it) && it.fileName.toString().endsWith(".java")
                }.sorted().toList()
            }
            val compile = ProcessBuilder(
                listOf(
                    javac.toString(), "-cp", classpath, "-d", directory.toString(),
                ) + javaSources.map { it.toString() } + executor.toString(),
            ).redirectErrorStream(true).start()
            val compileOutput = compile.inputStream.bufferedReader().use { it.readText() }
            assertEquals(0, compile.waitFor(), "javac: $compileOutput")

            val harness = ProcessBuilder(
                listOf(javaBinary().toString(), "-cp", classpath, "Harness"),
            ).directory(directory.toFile()).redirectErrorStream(true).start()
            val output = harness.inputStream.bufferedReader().use { it.readText() }
            assertEquals(0, harness.waitFor(), "harness: $output")
            assertEquals("dyn4k-core:SkippedCase#skips FAILED", output.trim())
        }
    }
}

/** The one JAR matching [name] under the Gradle module cache for [coordinate]. */
private fun gradleJar(coordinate: String, name: String): List<Path> {
    val root = File(System.getProperty("user.home"))
        .resolve(".gradle/caches/modules-2/files-2.1/$coordinate")
    if (!root.isDirectory) return emptyList()
    return root.walkTopDown().filter { it.isFile && it.name == name }.map { it.toPath() }.toList()
}

/** `javac` from JAVA_HOME when set, otherwise the executable on the PATH. */
private fun javac(): Path = jdkTool("javac")

private fun javaBinary(): Path = jdkTool("java")

private fun jdkTool(name: String): Path {
    val home = System.getenv("JAVA_HOME")
    if (home != null) {
        val candidate = Path.of(home, "bin", name)
        if (Files.isRegularFile(candidate)) return candidate
    }
    val path = System.getenv("PATH").orEmpty().split(File.pathSeparator)
        .map { Path.of(it, name) }
        .firstOrNull { Files.isRegularFile(it) }
    check(path != null) {
        "no $name on the PATH and no JAVA_HOME; the full executor case needs a JDK to compile with"
    }
    return path
}

/** The repository root, three levels above the harness build directory. */
private fun repositoryRoot(): Path {
    val working = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize()
    var candidate: Path? = working
    while (candidate != null) {
        if (Files.isDirectory(candidate.resolve("tools/harness/android"))) return candidate
        candidate = candidate.parent
    }
    error("repository root not found above $working")
}
