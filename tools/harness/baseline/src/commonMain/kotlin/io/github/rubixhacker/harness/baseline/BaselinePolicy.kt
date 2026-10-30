package io.github.rubixhacker.harness.baseline

/**
 * The pinned baseline corpus `tools/baseline/verify.py` verifies.
 *
 * The values are the ones the Python module declares. The Python unittest suites replace them on
 * the module (`patch.object(verify, "COMMIT", ...)`); the Kotlin port threads the same values
 * through [BaselinePolicy] instead, so a test changes them for one call.
 */
object Baseline {
    const val COMMIT: String = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
    const val BINARY_SHA256: String = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
    const val SOURCES_SHA256: String = "83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223"
    const val BASE: String = "https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/6.0.0"
    const val JUNIT: String = "https://repo.maven.apache.org/maven2/junit/junit/4.13.1/junit-4.13.1.jar"
    const val HAMCREST: String = "https://repo.maven.apache.org/maven2/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar"
    const val EXPECTED_CASES: Int = 2385
    const val COORDINATE: String = "org.dyn4j:dyn4j:6.0.0"

    /** Java 8 source fixtures whose compiled identity the gate records, in declaration order. */
    val REQUIRED_FIXTURE_SHA256: Map<String, String> = linkedMapOf(
        "six extension helpers" to "b668a59b6b50e6d5be1ca4828d2eaa179c6f9b3623a839be3e8c2c063d9ce6a4",
        "eight extension helpers" to "bb3f75b5f938b5e6da6e2444f5626606daa2223d29ba5c9ba2405660e50097ed",
        "CopyException null call" to "b37d307b808a55961bad6d6cfd5606ec7d27b2ba33567e8d44621d0942530ff0",
    )

    /** Paths `execute` fetches into the cache. */
    const val JUNIT_FILE: String = "junit-4.13.1.jar"
    const val HAMCREST_FILE: String = "hamcrest-core-1.3.jar"
}

/** The mutable globals the Python module exposes to its tests, as one immutable record. */
data class BaselinePolicy(
    val commit: String = Baseline.COMMIT,
    val binarySha256: String = Baseline.BINARY_SHA256,
    val sourcesSha256: String = Baseline.SOURCES_SHA256,
    val expectedCases: Int = Baseline.EXPECTED_CASES,
    val requiredFixtureSha256: Map<String, String> = Baseline.REQUIRED_FIXTURE_SHA256,
    val coordinate: String = Baseline.COORDINATE,
)
