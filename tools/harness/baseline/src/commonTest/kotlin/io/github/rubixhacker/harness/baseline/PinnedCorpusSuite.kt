package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.jsonObject
import kotlin.test.assertEquals

/**
 * The pinned corpus constants and the two literals the port must reproduce exactly.
 *
 * The recorded policy is `verify.py`'s own module state at the revision the vectors were taken from,
 * so a silent edit to a pinned digest, URL or count fails here.
 */
val PinnedCorpusCases by testSuite {
    test("the policy constants are the Python module's") {
        val policy = BaselinePolicy()
        assertEquals(Vectors.policy.str("commit"), policy.commit)
        assertEquals(Vectors.policy.str("binary_sha256"), policy.binarySha256)
        assertEquals(Vectors.policy.str("sources_sha256"), policy.sourcesSha256)
        assertEquals(Vectors.policy.int("expected_cases"), policy.expectedCases)
        assertEquals(Vectors.policy.str("base"), Baseline.BASE)
        assertEquals(Vectors.policy.str("junit"), Baseline.JUNIT)
        assertEquals(Vectors.policy.str("hamcrest"), Baseline.HAMCREST)
        assertEquals("org.dyn4j:dyn4j:6.0.0", policy.coordinate)
        assertEquals(
            Vectors.policy.obj("required_fixture_sha256").stringMap().toList(),
            policy.requiredFixtureSha256.toList(),
        )
        assertEquals("junit-4.13.1.jar", Baseline.JUNIT_FILE)
        assertEquals("hamcrest-core-1.3.jar", Baseline.HAMCREST_FILE)
    }

    test("the recorded vectors name the revision they were taken from") {
        assertEquals(BaselineVectors.PYTHON_REVISION, Vectors.revision)
        assertEquals(40, Vectors.revision.length)
        assertEquals("tools/baseline/verify.py", Vectors.root.str("python_module"))
    }

    test("the git environment filter drops every git variable except the network-auth set") {
        val environment = mapOf(
            "PATH" to "/bin",
            "GIT_DIR" to "/redirected",
            "GIT_WORK_TREE" to "/redirected",
            "GIT_ASKPASS" to "askpass",
            "GIT_TERMINAL_PROMPT" to "0",
            "HOME" to "/home",
        )
        assertEquals(
            mapOf("PATH" to "/bin", "HOME" to "/home"),
            gitEnvironment(environment, networkAuth = false),
        )
        assertEquals(
            mapOf(
                "PATH" to "/bin",
                "HOME" to "/home",
                "GIT_ASKPASS" to "askpass",
                "GIT_TERMINAL_PROMPT" to "0",
            ),
            gitEnvironment(environment, networkAuth = true),
        )
    }
}
