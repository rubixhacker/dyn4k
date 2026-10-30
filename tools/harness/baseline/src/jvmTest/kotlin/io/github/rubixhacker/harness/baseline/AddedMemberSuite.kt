package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

private fun risks(report: JsonObject): List<MemberRisk> =
    report.array("added_member_risks").map { memberRiskOf(it.jsonObject) }

private fun fixtureResults(report: JsonObject): List<JsonObject> =
    report.array("fixture_results").map { it.jsonObject }

private fun risks(report: CompareReport): List<MemberRisk> = report.addedMemberRisks

/** `bytes.replace(old, new)` over the raw class file, the way the hyphenated-method case patches it. */
private fun replaceBytes(bytes: ByteArray, old: ByteArray, new: ByteArray): ByteArray {
    val out = java.io.ByteArrayOutputStream()
    var index = 0
    while (index < bytes.size) {
        val matches = index + old.size <= bytes.size &&
            (old.indices).all { bytes[index + it] == old[it] }
        if (matches) {
            out.write(new)
            index += old.size
        } else {
            out.write(bytes[index].toInt())
            index++
        }
    }
    return out.toByteArray()
}

/**
 * `AddedMemberTests` of `tools/baseline/test_added_members.py`: every member a candidate adds —
 * declared or inherited — that a Java 8 source unit compiled against the baseline could newly name,
 * shadow, override or find ambiguous.
 *
 * Each case compiles a baseline archive and a candidate archive, proves the Java 8 consequence with
 * `javac` where the Python suite does, and compares the report the port produces.
 */
val AddedMemberCases by testSuite {
    test("private nested members do not create external source paths") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf("World.java" to "package p; public class World { private static class WarmStartHandler {} }"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf(
                    "World.java" to "package p; public class World { private static class WarmStartHandler " +
                        "{ public final String helper() { return null; } } }",
                ),
            )
            val details = javapOutput(baseline, "p.World\$WarmStartHandler", "-p", "-v")
            assertTrue(details.contains("InnerClasses:\n  private"))
            val source = "package p; public class Consumer extends World { public String helper() { return null; } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stdout + result.stderr)
            assertEquals(emptyList<MemberRisk>(), risks(report))
            val omitted = jarOf(root.resolve("omitted"), mapOf("World.java" to "package p; public class World {}"))
            assertEquals(0, compileSource(root, omitted, source, "omitted-classes").exitCode)
            val (omittedResult, omittedReport) = compare(baseline, omitted)
            assertEquals(0, omittedResult.code, omittedResult.stdout + omittedResult.stderr)
            assertEquals(emptyList(), omittedReport.strings("inventory_errors"))
        }
    }

    test("a hyphenated JVM method is not a java source member") {
        withCase { root ->
            val baseline = jarOf(root.resolve("baseline"), mapOf("Api.java" to "public class Api {}"))
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf("Api.java" to "public class Api { public final String fooBarX() { return null; } }"),
            )
            val classes = root.resolve("candidate/classes")
            val api = classes.resolve("Api.class")
            writeBytes(api, replaceBytes(readBytes(api), "fooBarX".encodeToByteArray(), "foo-bar".encodeToByteArray()))
            seams.requireRun(listOf("jar", "cf", candidate.toString(), "-C", classes.toString(), "."))
            val details = javapOutput(candidate, "Api", "-p")
            assertTrue(details.contains("foo-bar()"))
            val source = "public class Consumer extends Api { public String fooBarX() { return null; } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stdout + result.stderr)
            assertEquals(emptyList<MemberRisk>(), risks(report))
        }
    }

    test("generated java identifiers remain source risks") {
        withCase { root ->
            val other = "package q; public class Other { public static Object Companion = new Object(); " +
                "public static Object getEntries() { return null; } }"
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf(
                    "Api.java" to "package p; public class Api {}",
                    "Mode.java" to "package p; public enum Mode { ONE; }",
                    "Other.java" to other,
                ),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf(
                    "Api.java" to "package p; public class Api { public static Object Companion = new Object(); }",
                    "Mode.java" to "package p; public enum Mode { ONE; public static Object getEntries() " +
                        "{ return null; } }",
                    "Other.java" to other,
                ),
            )
            val source = "import static p.Api.*; import static p.Mode.*; import static q.Other.*; " +
                "public class Consumer { Object value = Companion; Object run() { return getEntries(); } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertNotEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            val declarations = risks(report).map { it.declaration }
            assertTrue(declarations.any { "Companion" in it })
            assertTrue(declarations.any { "getEntries()" in it })
        }
    }

    test("a duplicate dependency path cannot hide two snapshots under one hash") {
        withCase { root ->
            val archive = jarOf(root.resolve("library"), mapOf("Api.java" to "public final class Api {}"))
            val dependency = jarOf(root.resolve("dependency"), mapOf("Helper.java" to "public class Helper {}"))
            val report = compareJars(
                archive,
                archive,
                dependencies = listOf(dependency, dependency),
                policy = BaselinePolicy(binarySha256 = digest(archive)),
            )
            assertTrue(
                "duplicate dependency JAR: $dependency" in report.inventoryErrors,
                report.inventoryErrors.joinToString(),
            )
        }
    }

    test("a dependency replacement cannot change the reported member inventory") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf(
                    "Parent.java" to "public class Parent<T> {}",
                    "Api.java" to "public class Api extends Parent<String> {}",
                ),
            )
            val candidate = root.resolve("candidate.jar")
            seams.requireRun(
                listOf(
                    "jar", "cf", candidate.toString(), "-C",
                    root.resolve("baseline/classes").toString(), "Api.class",
                ),
            )
            val dependency = jarOf(
                root.resolve("dependency"),
                mapOf("Parent.java" to "public class Parent<T> { public final String helper() { return \"new\"; } }"),
            )
            val replacement = root.resolve("replacement.jar")
            seams.requireRun(
                listOf(
                    "jar", "cf", replacement.toString(), "-C",
                    root.resolve("baseline/classes").toString(), "Parent.class",
                ),
            )
            val originalHash = digest(dependency)
            val replacementHash = digest(replacement)
            var replaced = false
            val replacing = object : TestSeams() {
                override fun addedMemberGate(
                    selected: Set<String>,
                    baselineSignatures: Map<String, String>,
                    candidateSignatures: Map<String, String>,
                    baselineClasspath: String,
                    candidateClasspath: String,
                    artifactSha256: String,
                ): MemberAdditionResult {
                    if (!replaced) {
                        copyFile(replacement, dependency)
                        replaced = true
                    }
                    return super.addedMemberGate(
                        selected,
                        baselineSignatures,
                        candidateSignatures,
                        baselineClasspath,
                        candidateClasspath,
                        artifactSha256,
                    )
                }
            }
            val report = compareJars(
                baseline,
                candidate,
                only = setOf("Api"),
                dependencies = listOf(dependency),
                policy = BaselinePolicy(binarySha256 = digest(baseline)),
                seams = replacing,
            )
            assertTrue(replaced)
            assertNotEquals(originalHash, replacementHash)
            assertEquals(replacementHash, digest(dependency))
            assertEquals(originalHash, report.dependencySha256[dependency.toString()])
            assertTrue(risks(report).any { "helper()" in it.declaration })
        }
    }

    test("a fixture replacement cannot change the compiled source identity") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf("Api.java" to "public class Api { public String value() { return \"base\"; } }"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf("Api.java" to "public class Api { public final String value() { return \"new\"; } }"),
            )
            val fixture = root.resolve("Child.java")
            writeText(
                fixture,
                "public class Child extends Api { @Override public String value() { return \"child\"; } }\n",
            )
            val approvedHash = digest(fixture)
            var replaced = false
            val replacing = object : TestSeams() {
                override fun run(command: List<String>, environment: Map<String, String>?): ProcessOutput {
                    if (command.first() == "javac" && !replaced) {
                        writeText(fixture, "public class Child {}\n")
                        replaced = true
                    }
                    return super.run(command, environment)
                }
            }
            val report = compareJars(
                baseline,
                candidate,
                fixtures = listOf(fixture),
                requireFixture = true,
                policy = BaselinePolicy(
                    binarySha256 = digest(baseline),
                    requiredFixtureSha256 = mapOf("approved" to approvedHash),
                ),
                seams = replacing,
            )
            assertTrue(replaced)
            assertNotEquals(approvedHash, digest(fixture))
            assertEquals(emptyList(), report.fixtureErrors)
            val result = report.fixtureResults.single()
            assertEquals(approvedHash, result.sourceSha256)
            assertEquals(0, result.baselineExitCode)
            assertNotEquals(0, result.candidateExitCode)
            assertEquals(listOf(fixture.toString()), report.fixtureFailures)
        }
    }

    test("an unrelated required fixture is rejected") {
        withCase { root ->
            val archive = jarOf(root.resolve("library"), mapOf("Api.java" to "public final class Api {}"))
            val fixture = root.resolve("Fixture.java")
            writeText(fixture, "public class Fixture {}")
            val audit = fixtureAudit(seams, archive, listOf(fixture), true, archive.toString())
            assertEquals(1, audit.results.size)
            assertEquals(emptyList(), audit.failures)
            assertTrue(
                audit.errors.any { "required" in it && "fixture" in it },
                audit.errors.joinToString(),
            )
        }
    }

    test("the compare command rejects an unpinned baseline jar") {
        withCase { root ->
            val archive = jarOf(root.resolve("library"), mapOf("Api.java" to "public final class Api {}"))
            val result = cli(
                "compare",
                "--baseline-jar", archive.toString(),
                "--candidate", archive.toString(),
            )
            assertNotEquals(0, result.code)
            assertTrue(result.stderr.contains("baseline SHA-256"), result.stderr)
        }
    }

    test("the comparison function rejects an unpinned baseline jar") {
        withCase { root ->
            val archive = jarOf(root.resolve("library"), mapOf("Api.java" to "public final class Api {}"))
            val error = runCatching { compareJars(archive, archive) }.exceptionOrNull()
            assertTrue(
                error is IllegalArgumentException && "baseline SHA-256" in (error.message ?: ""),
                "unexpected result: $error",
            )
        }
    }

    test("a new final override of an inherited generic method fails") {
        withCase { root ->
            val shared = mapOf("Parent.java" to "public class Parent<T> { public T value() { return null; } }")
            val baseline = jarOf(
                root.resolve("baseline"),
                shared + ("Api.java" to "public class Api extends Parent<String> {}"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                shared + ("Api.java" to "public class Api extends Parent<String> " +
                    "{ @Override public final String value() { return \"x\"; } }"),
            )
            val source = "public class Consumer extends Api { @Override public String value() { return \"child\"; } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertNotEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            assertTrue(
                risks(report).any {
                    it.candidateType == "Api" && "final" in it.declaration && "value()" in it.declaration
                },
            )
        }
    }

    test("a new field hiding an inherited constant fails") {
        withCase { root ->
            val shared = mapOf("Parent.java" to "public class Parent { public static final int KEY = 1; }")
            val baseline = jarOf(
                root.resolve("baseline"),
                shared + ("Api.java" to "public class Api extends Parent {}"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                shared + ("Api.java" to "public class Api extends Parent { public static int KEY = 2; }"),
            )
            val source = "public class Consumer { int run(int x) { switch (x) " +
                "{ case Api.KEY: return 1; default: return 0; } } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertNotEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            assertTrue(
                risks(report).any { it.candidateType == "Api" && it.kind == "field" && "KEY" in it.declaration },
            )
        }
    }

    test("a final type ambiguous added overload fails") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf("Api.java" to "public final class Api { public String value(String input) { return input; } }"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf(
                    "Api.java" to "public final class Api { public String value(String input) { return input; } " +
                        "public String value(Integer input) { return null; } }",
                ),
            )
            val source = "public class Consumer { String run(Api api) { return api.value(null); } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertNotEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            assertTrue(risks(report).any { "value(java.lang.Integer)" in it.declaration })
        }
    }

    test("an added static field can make a wildcard import ambiguous") {
        withCase { root ->
            val shared = mapOf(
                "Other.java" to "package q; public final class Other { public static final int PIN = 1; }",
            )
            val baseline = jarOf(
                root.resolve("baseline"),
                shared + ("Api.java" to "package p; public final class Api {}"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                shared + ("Api.java" to "package p; public final class Api { public static final int PIN = 2; }"),
            )
            val source = "import static p.Api.*; import static q.Other.*; public class Consumer { int value = PIN; }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertNotEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            assertTrue(
                risks(report).any { it.candidateType == "p.Api" && it.kind == "field" && "PIN" in it.declaration },
            )
        }
    }

    test("a package private type cannot gain a member a same package subclass would shadow") {
        withCase { root ->
            val baseline = jarOf(root.resolve("baseline"), mapOf("Api.java" to "package p; class Api {}"))
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf("Api.java" to "package p; class Api { public final String helper() { return \"api\"; } }"),
            )
            val source = "package p; public class Consumer extends Api { public String helper() { return \"child\"; } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertNotEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            assertTrue(risks(report).any { it.candidateType == "p.Api" && "helper()" in it.declaration })
        }
    }

    test("a missing package private type fails a same package extension") {
        withCase { root ->
            val baseline = jarOf(root.resolve("baseline"), mapOf("Api.java" to "package p; class Api {}"))
            val candidate = jarOf(root.resolve("candidate"), mapOf("Other.java" to "package p; public class Other {}"))
            val source = "package p; public class Consumer extends Api {}"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertNotEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            assertTrue(report.strings("inventory_errors").any { "p.Api" in it })
        }
    }

    test("anonymous and package-info classes are not source types") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf(
                    "Api.java" to "package p; public class Api { public Runnable helper = " +
                        "new Runnable() { public void run() {} }; }",
                    "package-info.java" to "@Deprecated package p;",
                ),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf("Api.java" to "package p; public class Api { public Runnable helper = null; }"),
            )
            val source = "package p; public class Consumer { Runnable value = new Api().helper; }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stdout + result.stderr)
            assertEquals(emptyList(), report.strings("inventory_errors"))
        }
    }

    test("six baseline valid helpers expose declared and inherited additions") {
        withCase { root ->
            val before = mapOf(
                "Epa.java" to "public class Epa {}",
                "BaseWorld.java" to "public class BaseWorld<T> {}",
                "World.java" to "public class World<T> extends BaseWorld<T> {}",
                "Rotation.java" to "public class Rotation { protected double cost; }",
                "Force.java" to "public class Force {}",
                "DetectResult.java" to "public class DetectResult<T> {}",
                "VertexClusterReduction.java" to "public class VertexClusterReduction {}",
            )
            val after = before + mapOf(
                "Epa.java" to "public class Epa { protected final int maxIterationsField() { return 1; } }",
                "BaseWorld.java" to "public class BaseWorld<T> { protected final T settingsField() { return null; } }",
                "Rotation.java" to "public class Rotation { protected double cost; " +
                    "public double costValue() { return cost; } }",
                "Force.java" to "public class Force { public final Object " +
                    "rawForce\$io_github_rubixhacker_dyn4k_core() { return null; } }",
                "DetectResult.java" to "public class DetectResult<T> { protected final T bodyField() " +
                    "{ return null; } }",
                "VertexClusterReduction.java" to "public class VertexClusterReduction " +
                    "{ public double getClusterTolerance() { return 0; } }",
            )
            val baseline = jarOf(root.resolve("baseline"), before)
            val candidate = jarOf(root.resolve("candidate"), after)
            val consumer = "public class Consumer { " +
                "static class Detector extends Epa { public String maxIterationsField() { return \"x\"; } } " +
                "static class Simulation extends World<String> { public String settingsField() { return \"x\"; } } " +
                "static class Turn extends Rotation { public String costValue() { return \"x\"; } } " +
                "static class AppliedForce extends Force { public String " +
                "rawForce\$io_github_rubixhacker_dyn4k_core() { return \"x\"; } } " +
                "static class Detection extends DetectResult<String> { public String bodyField() " +
                "{ return \"x\"; } } " +
                "static class Simplifier extends VertexClusterReduction { public String getClusterTolerance() " +
                "{ return \"x\"; } } }"
            assertEquals(0, compileSource(root, baseline, consumer, "baseline-classes").exitCode)
            assertNotEquals(0, compileSource(root, candidate, consumer, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            val observed = risks(report)
            for (name in listOf(
                "maxIterationsField",
                "settingsField",
                "costValue",
                "rawForce\$io_github_rubixhacker_dyn4k_core",
                "bodyField",
                "getClusterTolerance",
            )) {
                assertTrue(observed.any { name in it.declaration }, name)
            }
            val inherited = observed.filter { it.candidateType == "World" && "settingsField" in it.declaration }
            assertEquals(1, inherited.size)
            assertEquals("BaseWorld", inherited[0].declaringType)
        }
    }

    test("an added constructor null ambiguity is rejected") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf(
                    "CopyException.java" to "public class CopyException extends RuntimeException " +
                        "{ public CopyException(Class<?> source, Class<?> copy) {} }",
                ),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf(
                    "CopyException.java" to "public class CopyException extends RuntimeException " +
                        "{ public CopyException(Class<?> source, Class<?> copy) {} " +
                        "public CopyException(String source, String copy) {} }",
                ),
            )
            val source = "public class Consumer { CopyException make() { return new CopyException(null, null); } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertNotEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            assertTrue(
                risks(report).any {
                    "CopyException(java.lang.String, java.lang.String)" in it.declaration
                },
            )
        }
    }

    test("a package method, field name clash and static hiding are rejected") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf("Api.java" to "package p; public class Api { protected int value; }"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf(
                    "Api.java" to "package p; public class Api { protected int value; " +
                        "int value() { return 1; } public static final int count() { return 1; } }",
                ),
            )
            val source = "package p; public class Consumer extends Api { String value() { return \"x\"; } " +
                "public static int count() { return 2; } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertNotEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            val declarations = risks(report).map { it.declaration }
            assertTrue(declarations.any { "value()" in it })
            assertTrue(declarations.any { "count()" in it })
        }
    }

    test("a final type tolerates private and harmless overloads") {
        withCase { root ->
            val baseline = jarOf(
                root.resolve("baseline"),
                mapOf("Api.java" to "public final class Api { public int value() { return 1; } }"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf(
                    "Api.java" to "public final class Api { public int value() { return 1; } " +
                        "public int value(int n) { return n; } private int helper() { return 2; } }",
                ),
            )
            val source = "public class Consumer { int run(Api api) { return api.value(); } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stdout + result.stderr)
            assertEquals(emptyList<MemberRisk>(), risks(report))
        }
    }

    test("a private helper in a subclassable type passes") {
        withCase { root ->
            val baseline = jarOf(root.resolve("baseline"), mapOf("Api.java" to "public class Api {}"))
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf("Api.java" to "public class Api { private int helper() { return 1; } }"),
            )
            val source = "public class Consumer extends Api { public String helper() { return \"ok\"; } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stdout + result.stderr)
            assertEquals(emptyList<MemberRisk>(), risks(report))
        }
    }

    test("a synthetic helper hides the source member but not the runtime override") {
        withCase { root ->
            val baseline = jarOf(root.resolve("baseline"), mapOf("Api.java" to "public class Api {}"))
            val candidate = jarOf(
                root.resolve("candidate"),
                mapOf("Api.java" to "public class Api { public final String helper() { return \"api\"; } }"),
                syntheticMethod = "Api" to "helper",
            )
            val details = javapOutput(candidate, "Api", "-v", "-p")
            assertTrue(details.contains("ACC_PUBLIC, ACC_FINAL, ACC_SYNTHETIC"))
            val source = "public class Consumer extends Api { public String helper() { return \"child\"; } " +
                "public static void main(String[] args) { System.out.println(new Consumer().helper()); } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stdout + result.stderr)
            assertEquals(emptyList<MemberRisk>(), risks(report))
            val runtime = seams.run(
                listOf(
                    "java", "-cp",
                    root.resolve("baseline-classes").toString() + ":" + candidate.toString(),
                    "Consumer",
                ),
                null,
            )
            assertNotEquals(0, runtime.exitCode)
            assertTrue(runtime.stderrText().contains("IncompatibleClassChangeError"), runtime.stderrText())
        }
    }

    test("an inherited generic override is not an added method") {
        withCase { root ->
            val shared = mapOf("Parent.java" to "public class Parent<T> { public T value() { return null; } }")
            val baseline = jarOf(
                root.resolve("baseline"),
                shared + ("Api.java" to "public class Api extends Parent<String> {}"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                shared + ("Api.java" to "public class Api extends Parent<String> " +
                    "{ @Override public String value() { return \"ok\"; } }"),
            )
            val source = "public class Consumer extends Api { @Override public String value() { return \"child\"; } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stdout + result.stderr)
            assertFalse(risks(report).any { "value()" in it.declaration })
        }
    }

    test("a required fixture cannot be skipped or empty") {
        withCase { root ->
            val baseline = jarOf(root.resolve("baseline"), mapOf("Api.java" to "public final class Api {}"))
            val candidate = jarOf(root.resolve("candidate"), mapOf("Api.java" to "public final class Api {}"))
            val skipped = compare(baseline, candidate, "--require-fixture").first
            assertEquals(1, skipped.code)
            assertTrue(skipped.report().strings("fixture_errors")[0].contains("skipped"))
            val missing = compare(
                baseline,
                candidate,
                "--require-fixture",
                "--fixture", root.resolve("missing.java").toString(),
            ).first
            assertEquals(1, missing.code)
            assertTrue(missing.report().strings("fixture_errors")[0].contains("missing"))
            val empty = root.resolve("empty.java")
            writeText(empty, "")
            val noSource = compare(
                baseline,
                candidate,
                "--require-fixture",
                "--fixture", empty.toString(),
            ).first
            assertEquals(1, noSource.code)
            assertTrue(noSource.report().strings("fixture_errors")[0].contains("empty"))
            val fixture = root.resolve("Consumer.java")
            writeText(fixture, "public class Consumer { Api value; }")
            val present = compare(
                baseline,
                candidate,
                "--require-fixture",
                "--fixture", fixture.toString(),
                policy = BaselinePolicy(
                    binarySha256 = digest(baseline),
                    requiredFixtureSha256 = mapOf("test" to digest(fixture)),
                ),
            )
            assertEquals(0, present.first.code, present.first.stdout + present.first.stderr)
            assertEquals(1, fixtureResults(present.second).size)
        }
    }

    test("an empty candidate inventory fails") {
        withCase { root ->
            val baseline = jarOf(root.resolve("baseline"), mapOf("Api.java" to "public class Api {}"))
            val empty = root.resolve("empty")
            makeDirectories(empty)
            val candidate = root.resolve("empty.jar")
            seams.requireRun(listOf("jar", "cf", candidate.toString(), "-C", empty.toString(), "."))
            val result = compare(
                baseline,
                candidate,
                policy = BaselinePolicy(binarySha256 = digest(baseline)),
            ).first
            assertNotEquals(0, result.code)
            assertTrue(
                result.stderr.contains("empty baseline or candidate class-file inventory"),
                result.stderr,
            )
        }
    }

    test("a package constructor inventory is readable") {
        withCase { root ->
            val source = mapOf("Api.java" to "package p; public class Api { Api() {} }")
            val baseline = jarOf(root.resolve("baseline"), source)
            val candidate = jarOf(root.resolve("candidate"), source)
            val (result, report) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stdout + result.stderr)
            assertEquals(emptyList(), report.strings("inventory_errors"))
        }
    }

    test("a method type parameter does not inherit the class substitution") {
        withCase { root ->
            val shared = mapOf(
                "Parent.java" to "public class Parent<T> { public <T> T convert(T value) { return value; } }",
            )
            val baseline = jarOf(
                root.resolve("baseline"),
                shared + ("Api.java" to "public class Api extends Parent<String> {}"),
            )
            val candidate = jarOf(
                root.resolve("candidate"),
                shared + ("Api.java" to "public class Api extends Parent<String> " +
                    "{ public final String convert(String value) { return value; } }"),
            )
            val source = "public class Consumer extends Api { public String convert(String value) { return value; } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertNotEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(1, result.code, result.stdout + result.stderr)
            assertTrue(risks(report).any { "convert(java.lang.String)" in it.declaration })
        }
    }

    test("a method type parameter preserves the unshadowed class substitution") {
        withCase { root ->
            val shared = mapOf(
                "Parent.java" to "public class Parent<T> { public <U> T convert(U value) { return null; } }",
                "Api.java" to "public class Api extends Parent<String> {}",
            )
            val baseline = jarOf(root.resolve("baseline"), shared)
            val candidate = jarOf(
                root.resolve("candidate"),
                shared + ("Api.java" to "public class Api extends Parent<String> " +
                    "{ @Override public <U> String convert(U value) { return \"ok\"; } }"),
            )
            val source = "public class Consumer extends Api { @Override public <U> String convert(U value) " +
                "{ return \"child\"; } }"
            assertEquals(0, compileSource(root, baseline, source, "baseline-classes").exitCode)
            assertEquals(0, compileSource(root, candidate, source, "candidate-classes").exitCode)
            val (result, report) = compare(baseline, candidate)
            assertEquals(0, result.code, result.stdout + result.stderr)
            assertFalse(risks(report).any { "convert(" in it.declaration })
        }
    }
}

