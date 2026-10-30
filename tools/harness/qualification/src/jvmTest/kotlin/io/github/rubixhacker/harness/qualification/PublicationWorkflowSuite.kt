package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import kotlin.test.assertTrue

/**
 * `test_publication.test_workflow_harness_requests_full_history_without_bytecode`.
 *
 * Both publication jobs must check out full history (the staging audit reads committed bytes) and
 * the hosted job must not write bytecode into the tree it packages.
 */
val PublicationWorkflow by testSuite {
    test("the workflow harness requests full history without bytecode") {
        val workflow = Files.readString(
            repositoryRoot().resolve(".github/workflows/qualification.yml"),
        )
        val ubuntu = workflow.split("  staged-jvm-and-linux:\n", limit = 2)[1]
            .split("  hosted-publications:\n", limit = 2)[0]
        val hosted = workflow.split("  hosted-publications:\n", limit = 2)[1]
            .split("  hosted-native:\n", limit = 2)[0]
        for ((name, job) in listOf("ubuntu" to ubuntu, "hosted-publications" to hosted)) {
            val checkout = job.split("      - uses: actions/checkout@v4\n", limit = 2)[1]
                .split("      - uses:", limit = 2)[0]
            assertTrue(
                "        with:\n          fetch-depth: 0\n" in checkout,
                "$name: checkout does not request full history",
            )
            assertTrue(
                "unittest discover -s tools/qualification" in job,
                "$name: qualification unittest discovery is missing",
            )
        }
        assertTrue(
            "    env:\n      PYTHONDONTWRITEBYTECODE: '1'\n" in hosted,
            "hosted job does not suppress bytecode",
        )
    }
}
