package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * The `ComparatorTests` cases of `tools/baseline/test_verify.py`: the Java 8 source contract the
 * comparison enforces, the two snapshot-identity proofs, and the archive digests that identify the
 * bytes each report describes.
 *
 * Two Python cases of that class are not here. `test_geometry_cli_*` runs
 * `scripts/verify-geometry-jvm-api.py`, and `FoundationComparatorTests` runs
 * `scripts/verify-foundation-jvm-api.py`; both are separate tools outside this module, so neither
 * says anything about the port of `verify.py`.
 */
val ComparatorCases by testSuite {
    test("a baseline hash identifies the bytes it inventoried during a temporary replacement") {
        withCase { root ->
            val baseline = jarOf(root.resolve("baseline"), mapOf("Api.java" to "public class Api {}"))
            val originalCopy = root.resolve("baseline-original.jar")
            copyFile(baseline, originalCopy)
            val candidate = jarOf(root.resolve("candidate"), mapOf("Api.java" to "public class Api {}"))
            val changed = jarOf(
                root.resolve("changed"),
                mapOf("Api.java" to "public class Api { public final String helper() { return \"new\"; } }"),
            )
            val originalHash = digest(baseline)
            var calls = 0
            val replacing = object : TestSeams() {
                override fun jarInventory(
                    binary: Path,
                    only: Set<String>?,
                    visibility: String,
                    verbose: Boolean,
                ): JarInventory {
                    calls++
                    if (calls == 1) copyFile(changed, baseline)
                    val inventory = super.jarInventory(binary, only, visibility, verbose)
                    if (calls == 1) copyFile(originalCopy, baseline)
                    return inventory
                }
            }
            val report = compareJars(
                baseline,
                candidate,
                policy = BaselinePolicy(binarySha256 = originalHash),
                seams = replacing,
            )
            assertEquals(originalHash, digest(baseline))
            assertEquals(originalHash, report.baselineSha256)
            assertEquals(emptyList(), report.signatureMismatches)
        }
    }

    test("a candidate hash identifies the bytes it inventoried during a path replacement") {
        withCase { root ->
            val baseline = jarOf(root.resolve("baseline"), mapOf("Api.java" to "public class Api {}"))
            val candidate = root.resolve("candidate.jar")
            copyFile(baseline, candidate)
            val changed = jarOf(
                root.resolve("changed"),
                mapOf("Api.java" to "public class Api { public final String helper() { return \"new\"; } }"),
            )
            val initialHash = digest(candidate)
            val changedHash = digest(changed)
            var calls = 0
            val replacing = object : TestSeams() {
                override fun jarInventory(
                    binary: Path,
                    only: Set<String>?,
                    visibility: String,
                    verbose: Boolean,
                ): JarInventory {
                    calls++
                    val inventory = super.jarInventory(binary, only, visibility, verbose)
                    if (calls == 2) copyFile(changed, candidate)
                    return inventory
                }
            }
            val raced = compareJars(
                baseline,
                candidate,
                policy = BaselinePolicy(binarySha256 = digest(baseline)),
                seams = replacing,
            )
            val direct = compareJars(
                baseline,
                candidate,
                policy = BaselinePolicy(binarySha256 = digest(baseline)),
            )
            assertEquals(2, calls)
            assertNotEquals(initialHash, changedHash)
            assertEquals(changedHash, digest(candidate))
            assertEquals(initialHash, raced.candidateSha256)
            assertEquals(emptyList(), raced.addedMemberRisks)
            assertEquals(1, direct.addedMemberRisks.size)
            assertEquals(changedHash, direct.addedMemberRisks[0].artifactSha256)
        }
    }

    test("kotlin style additions and declaration order are accepted") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf(
                    "Api.java" to "public final class Api<T extends Number> { public T value; " +
                        "public void move(int n) {} public static int size() { return 1; } }",
                    "Helper.java" to "class Helper { public void internal() {} }",
                ),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf(
                    "Api.java" to "public final class Api<T extends Number> implements java.io.Serializable " +
                        "{ public static int size() { return 1; } public void move(int n) {} " +
                        "public T value; public int added() { return 0; } }",
                    "Helper.java" to "class Helper { public void internal() {} }",
                ),
            )
            val (result, report) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stderr + result.stdout)
            assertEquals(emptyList(), report.strings("missing_types"))
        }
    }

    test("the java 8 extension contract rejects incompatible modifiers and generics") {
        val cases = linkedMapOf(
            Triple(
                "subclass_override",
                "public class Api { public Number value() { return 1; } }",
                "public class Api { public final Number value() { return 1; } }",
            ) to "public class Consumer extends Api { @Override public Number value() { return 2; } }",
            Triple(
                "static_hiding",
                "public class Api { public static int count() { return 1; } }",
                "public class Api { public static final int count() { return 1; } }",
            ) to "public class Consumer extends Api { public static int count() { return 2; } }",
            Triple(
                "generic_list_override",
                "public class Api { public java.util.List<? extends Vector2> points() { return null; } }",
                "public class Api { public java.util.List<Vector2> points() { return null; } }",
            ) to "public class Consumer extends Api { @Override public java.util.List<? extends Vector2> points() { return null; } }",
            Triple(
                "final_type",
                "public class Api {}",
                "public final class Api {}",
            ) to "public class Consumer extends Api {}",
            Triple(
                "constant_field",
                "public class Api { public static final int KEY = 1; }",
                "public class Api { public static int KEY = 1; }",
            ) to "public class Consumer { int run(int value) { switch (value) { case Api.KEY: return 1; default: return 0; } } }",
        )
        val expectedText = linkedMapOf(
            "subclass_override" to "public final java.lang.Number value()",
            "static_hiding" to "public static final int count()",
            "generic_list_override" to "java.util.List<Vector2>",
            "final_type" to "public final class Api",
            "constant_field" to "public static int KEY",
        )
        withCase { root ->
            for ((triple, consumerSource) in cases) {
                val (label, before, after) = triple
                val case = root.resolve(label)
                val extra = if (label == "generic_list_override") {
                    mapOf("Vector2.java" to "public class Vector2 {}")
                } else {
                    emptyMap()
                }
                val baseline = jarOf(case.resolve("baseline"), mapOf("Api.java" to before) + extra)
                val candidate = jarOf(case.resolve("candidate"), mapOf("Api.java" to after) + extra)
                assertJava8Consumer(case, baseline, candidate, consumerSource)
                val (result, report) = compare(baseline, candidate)
                assertEquals(1, result.code, result.stdout + result.stderr)
                assertTrue(report.strings("signature_mismatches").isNotEmpty())
                assertTrue(result.stdout.contains(expectedText.getValue(label)), label)
            }
        }
    }

    test("a covariant bridge does not replace the source method") {
        withCase { root ->
            val shared = mapOf("Parent.java" to "public class Parent<T> { public T value() { return null; } }")
            val baseline = jarOf(
                root.resolve("baseline"),
                shared + ("Api.java" to "public class Api extends Parent<String> { @Override public String value() { return \"ok\"; } }"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                shared + ("Api.java" to "public class Api extends Parent<String> {}"),
            )
            val details = javapOutput(baseline, "Api", "-protected", "-s")
            assertTrue(details.contains("descriptor: ()Ljava/lang/String;"))
            assertTrue(details.contains("descriptor: ()Ljava/lang/Object;"))
            val (result, _) = compare(baseline, candidate, "--only", "Api")
            assertEquals(1, result.code, result.stdout + result.stderr)
            assertTrue(result.stdout.contains("java.lang.String value()"))
            assertFalse(result.stdout.contains("missing public java.lang.Object value()"))
        }
    }

    test("a java 8 consumer accepts wider access and a removed final") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf(
                    "Api.java" to "public class Api { protected static final int count() { return 1; } " +
                        "protected final void move() {} }",
                ),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf(
                    "Api.java" to "public class Api { public static int count() { return 1; } " +
                        "public void move() {} }",
                ),
            )
            val source = "public class Consumer { int run(Api api) { api.move(); return Api.count(); } }"
            for (archive in listOf(baseline, candidate)) {
                val output = root.resolve(if (archive == baseline) "baseline-classes" else "candidate-classes")
                val compiled = compileSource(root, archive, source, output.fileName.toString())
                assertEquals(0, compiled.exitCode, compiled.stderrText())
            }
            val (result, _) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stdout + result.stderr)
        }
    }

    test("a transitive interface is source equivalent") {
        withCase { root ->
            val shared = mapOf(
                "Parent.java" to "public interface Parent { void move(); }",
                "Child.java" to "public interface Child extends Parent {}",
            )
            val baseline = jarOf(
                root.resolve("baseline"),
                shared + ("Api.java" to "public class Api implements Child, Parent { public void move() {} }"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                shared + ("Api.java" to "public class Api implements Child { public void move() {} }"),
            )
            val source = "public class Consumer { Parent run() { return new Api(); } }"
            for (archive in listOf(baseline, candidate)) {
                val label = if (archive == baseline) "b" else "c"
                val compiled = compileSource(root, archive, source, label)
                assertEquals(0, compiled.exitCode, compiled.stderrText())
            }
            val (result, _) = compare(baseline, candidate, "--only", "Api")
            assertEquals(0, result.code, result.stdout + result.stderr)
        }
    }

    test("final methods in a final type preserve the source contract") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf(
                    "Api.java" to "public final class Api { public int value() { return 1; } " +
                        "public static int count() { return 1; } public static final int KEY = 1; }",
                ),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf(
                    "Api.java" to "public final class Api { public final int value() { return 1; } " +
                        "public static final int count() { return 1; } public static final int KEY = 1; }",
                ),
            )
            val source = "public class Consumer { int run(Api api) { switch (api.value()) " +
                "{ case Api.KEY: return Api.count(); default: return 0; } } }"
            assertJava8ConsumerResult(root, baseline, candidate, source, candidatePasses = true)
            val (result, report) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stdout + result.stderr)
            assertEquals(2, report.strings("compatible_differences").size)
        }
    }

    test("a final type does not relax the field constant contract") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf("Api.java" to "public final class Api { public static final int KEY = 1; }"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf("Api.java" to "public final class Api { public static int KEY = 1; }"),
            )
            val source = "public class Consumer { int run(int value) { switch (value) " +
                "{ case Api.KEY: return 1; default: return 0; } } }"
            assertJava8ConsumerResult(root, baseline, candidate, source, candidatePasses = false)
            val (result, _) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            assertTrue(result.stdout.contains("public static int KEY"))
        }
    }

    test("a transitive generic interface requires substitution") {
        withCase { root ->
            val shared = mapOf(
                "Parent.java" to "public interface Parent<T> {}",
                "Child.java" to "public interface Child<U> extends Parent<U> {}",
            )
            val baseline = jarOf(
                root.resolve("baseline"),
                shared + ("Api.java" to "public class Api implements Child<String>, Parent<String> {}"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                shared + ("Api.java" to "public class Api implements Child<String> {}"),
            )
            val wrong = jarOf(
                root.resolve("wrong"),
                shared + ("Api.java" to "public class Api implements Child<Integer> {}"),
            )
            val source = "public class Consumer { Parent<String> run(Api value) { return value; } }"
            assertJava8ConsumerResult(root, baseline, candidate, source, candidatePasses = true)
            assertJava8ConsumerResult(root, baseline, wrong, source, candidatePasses = false)
            val (good, _) = compare(baseline, candidate, "--only", "Api")
            val (bad, _) = compare(baseline, wrong, "--only", "Api")
            assertEquals(0, good.code, good.stdout + good.stderr)
            assertEquals(1, bad.code, bad.stdout + bad.stderr)
        }
    }

    test("a constructor list extends widens without relaxing methods") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf(
                    "Api.java" to "public abstract class Api<T> { public Api(java.util.List<T> values) {} " +
                        "protected Api(Api<T> other, java.util.List<T> values) {} " +
                        "public void move(java.util.List<T> values) {} }",
                ),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf(
                    "Api.java" to "public abstract class Api<T> { public Api(java.util.List<? extends T> values) {} " +
                        "protected Api(Api<T> other, java.util.List<? extends T> values) {} " +
                        "public void move(java.util.List<T> values) {} }",
                ),
            )
            val wrong = jarOf(
                root.resolve("wrong"),
                mapOf(
                    "Api.java" to "public abstract class Api<T> { public Api(java.util.List<? extends T> values) {} " +
                        "protected Api(Api<T> other, java.util.List<? extends T> values) {} " +
                        "public void move(java.util.List<? extends T> values) {} }",
                ),
            )
            val source = "import java.util.List; public class Consumer<T> extends Api<T> { " +
                "Consumer(List<T> values) { super(values); } " +
                "Consumer(Api<T> other, List<T> values) { super(other, values); } " +
                "@Override public void move(List<T> values) {} }"
            assertJava8ConsumerResult(root, baseline, candidate, source, candidatePasses = true)
            assertJava8ConsumerResult(root, baseline, wrong, source, candidatePasses = false)
            val (good, _) = compare(baseline, candidate, "--only", "Api")
            val (bad, _) = compare(baseline, wrong, "--only", "Api")
            assertEquals(0, good.code, good.stdout + good.stderr)
            assertEquals(1, bad.code, bad.stdout + bad.stderr)
        }
    }

    test("an implicit object header preserves java 8 source") {
        withCase { root ->
            val baseline = jarOf(root.resolve("baseline"), mapOf("Api.java" to "public class Api {}"))
            val candidate = jarOf(root.resolve("candidate"), mapOf("Api.java" to "public class Api {}"))
            assertJava8ConsumerResult(
                root,
                baseline,
                candidate,
                "public class Consumer extends Api {}",
                candidatePasses = true,
            )
            var calls = 0
            val rewriting = object : TestSeams() {
                override fun jarInventory(
                    binary: Path,
                    only: Set<String>?,
                    visibility: String,
                    verbose: Boolean,
                ): JarInventory {
                    calls++
                    val inventory = super.jarInventory(binary, only, visibility, verbose)
                    if (calls != 1) return inventory
                    val signatures = inventory.signatures.toMutableMap()
                    signatures["Api"] = signatures.getValue("Api").replaceFirst(
                        "public class Api\n",
                        "public class Api extends java.lang.Object\n",
                    )
                    return JarInventory(inventory.classes, signatures)
                }
            }
            val report = compareJars(
                baseline,
                candidate,
                policy = BaselinePolicy(binarySha256 = digest(baseline)),
                seams = rewriting,
            )
            assertEquals(emptyList(), report.signatureMismatches)
            assertEquals(1, report.compatibleDifferences.size)
        }
    }

    test("public contract mutations are rejected") {
        withCase { root ->
            val baselineSource = "public class Api<T extends Number> extends Parent { public T value; " +
                "public static int size() { return 1; } public void move(int n) {} " +
                "public java.util.List<String> items() { return null; } }"
            val parent = mapOf("Parent.java" to "public class Parent {}")
            val baseline = jarOf(root.resolve("baseline"), mapOf("Api.java" to baselineSource) + parent)
            val mutations = linkedMapOf(
                "missing_method" to baselineSource.replace("public void move(int n) {}", ""),
                "access" to baselineSource.replace("public void move", "protected void move"),
                "static" to baselineSource.replace("public static int size", "public int size"),
                "final" to baselineSource.replace("public void move", "public final void move"),
                "abstract_type" to baselineSource.replace("public class Api", "public abstract class Api"),
                "final_type" to baselineSource.replace("public class Api", "public final class Api"),
                "generic_bound" to baselineSource.replace("T extends Number", "T extends Object"),
                "superclass" to baselineSource.replace(" extends Parent", ""),
                "field_type" to baselineSource.replace("public T value", "public Number value"),
                "generic_return" to baselineSource.replace("List<String>", "List<Integer>"),
            )
            for ((label, source) in mutations) {
                val candidate = jarOf(root.resolve(label), mapOf("Api.java" to source) + parent)
                val (result, report) = compare(baseline, candidate)
                assertEquals(1, result.code, "$label: ${result.stderr}${result.stdout}")
                assertTrue(report.strings("signature_mismatches").isNotEmpty(), label)
            }
        }
    }
}

/** `assert_java8_consumer`: the baseline compiles the consumer, the candidate must not. */
internal fun assertJava8Consumer(root: Path, baseline: Path, candidate: Path, source: String) {
    val consumer = consumer(root, source)
    for (archive in listOf(baseline, candidate)) {
        val label = if (archive == baseline) "baseline-classes" else "candidate-classes"
        val result = seams.run(
            listOf(
                "javac", "--release", "8", "-Xlint:-options", "-classpath", archive.toString(),
                "-d", root.resolve(label).toString(), consumer.toString(),
            ),
            null,
        )
        if (archive == baseline) {
            assertEquals(0, result.exitCode, result.stderrText())
        } else {
            assertNotEquals(0, result.exitCode, result.stderrText())
        }
    }
}

/** `assert_java8_consumer_result`: the baseline passes; the candidate passes only when asked to. */
internal fun assertJava8ConsumerResult(
    root: Path,
    baseline: Path,
    candidate: Path,
    source: String,
    candidatePasses: Boolean,
) {
    val consumer = consumer(root, source)
    for ((archive, passes) in listOf(baseline to true, candidate to candidatePasses)) {
        val label = if (archive == baseline) "baseline-classes" else "candidate-classes"
        val result = seams.run(
            listOf(
                "javac", "--release", "8", "-Xlint:-options", "-classpath", archive.toString(),
                "-d", root.resolve(label).toString(), consumer.toString(),
            ),
            null,
        )
        if (passes) {
            assertEquals(0, result.exitCode, result.stderrText())
        } else {
            assertNotEquals(0, result.exitCode, result.stderrText())
        }
    }
}
