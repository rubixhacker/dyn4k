package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.createDirectories
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

private const val VALID = "name: Windows and Linux\n" +
    "on: workflow_dispatch\n" +
    "jobs:\n" +
    "  linux:\n" +
    "    runs-on: ubuntu-latest\n" +
    "    steps:\n" +
    "      - run: true\n" +
    "  windows:\n" +
    "    runs-on: windows-2025\n" +
    "    steps:\n" +
    "      - run: true\n"

private class WorkflowTree {
    val root: Path = Files.createTempDirectory("guard-hosted-runners")
    private val workflows: Path = root.resolve(".github").resolve("workflows").also { it.createDirectories() }

    fun write(name: String, source: String) {
        workflows.resolve(name).writeText(source)
    }

    fun scan(): Pair<Int, List<String>> = scan(root.toFile())
}

val HostedRunnerGuard by testSuite {
    test("valid Linux and Windows workflow passes") {
        val tree = WorkflowTree()
        tree.write("valid.yml", VALID)
        assertEquals(1 to emptyList(), tree.scan())
    }

    test("documented Ubuntu ARM runner passes") {
        val tree = WorkflowTree()
        tree.write("arm.yml", VALID.replace("ubuntu-latest", "ubuntu-24.04-arm"))
        assertEquals(1 to emptyList(), tree.scan())
    }

    test("self-hosted mac-mini runner passes") {
        val tree = WorkflowTree()
        tree.write("macmini.yml", VALID.replace("windows-2025", "mac-mini"))
        assertEquals(1 to emptyList(), tree.scan())
    }

    test("mac-mini is not reported as a hosted macOS label") {
        val tree = WorkflowTree()
        tree.write("macmini.yml", VALID.replace("windows-2025", "mac-mini"))
        assertFalse(tree.scan().second.any { "macOS hosted label" in it })
    }

    test("unknown Ubuntu ARM runner is rejected") {
        val tree = WorkflowTree()
        tree.write("unknown.yml", VALID.replace("ubuntu-latest", "ubuntu-24.04-arm64"))
        assertTrue(tree.scan().second.any { "explicit Linux/Windows" in it })
    }

    test("a new workflow file is scanned") {
        val tree = WorkflowTree()
        tree.write("valid.yml", VALID)
        tree.write("new.yaml", VALID.replace("windows-2025", "macos-26"))
        val (count, errors) = tree.scan()
        assertEquals(2, count)
        assertTrue(errors.any { "new.yaml" in it && "macOS hosted label" in it })
    }

    test("a direct macOS label is rejected") {
        val tree = WorkflowTree()
        tree.write("direct.yml", VALID.replace("windows-2025", "macos-26"))
        assertTrue(tree.scan().second.isNotEmpty())
    }

    test("a matrix row with a macOS label is rejected") {
        val tree = WorkflowTree()
        val source = VALID.replace(
            "    runs-on: windows-2025",
            "    strategy:\n      matrix:\n        runner: [windows-2025, macos-26]\n    runs-on: \${{ matrix.runner }}",
        )
        tree.write("matrix.yml", source)
        val errors = tree.scan().second
        assertTrue(errors.any { "macOS hosted label" in it })
        assertTrue(errors.any { "runs-on" in it })
    }

    test("a fromJSON branch with a macOS label is rejected") {
        val tree = WorkflowTree()
        val source = VALID.replace(
            "    runs-on: windows-2025",
            "    runs-on: \${{ fromJSON(inputs.branch && '[\"windows-2025\"]' || '[\"macos-26\"]') }}",
        )
        tree.write("branch.yml", source)
        assertTrue(tree.scan().second.any { "macOS hosted label" in it })
    }

    test("a user-controlled runner expression is rejected") {
        val tree = WorkflowTree()
        tree.write("input.yml", VALID.replace("windows-2025", "\${{ inputs.runner }}"))
        assertTrue(tree.scan().second.any { "runs-on" in it })
    }

    test("a duplicate jobs key fails closed") {
        val tree = WorkflowTree()
        tree.write("duplicate.yml", VALID + "jobs : {hidden: {runs-on: \${{ inputs.runner }}}\n")
        assertTrue(tree.scan().second.any { "one block-style jobs section" in it })
    }

    test("a missing runner fails closed") {
        val tree = WorkflowTree()
        tree.write("missing.yml", VALID.replace("    runs-on: windows-2025\n", ""))
        assertTrue(tree.scan().second.any { "exactly one explicit runs-on" in it })
    }
}
