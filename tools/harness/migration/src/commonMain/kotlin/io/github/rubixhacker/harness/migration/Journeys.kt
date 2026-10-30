package io.github.rubixhacker.harness.migration

import io.github.rubixhacker.harness.contract.Sha256

/**
 * The constants and evidence rules of `tools/migration/journeys.py`.
 *
 * The pinned values identify the frozen sample sources, the published baseline artifacts, and the
 * candidate publication. Changing one invalidates retained migration evidence.
 */
object Journeys {
    const val SAMPLE_REVISION = "2c6b318e929baab77e9753ae78a4965eee74a30a"
    const val SOURCE_MANIFEST_SHA256 = "15ce636ac8eec34b24e73bc96270b49a44c94318850050b1e9bc0d930a9c8d58"
    val SCENES = listOf("Tracking", "Pyramid", "Crank", "Billiards", "Truck")
    val PROVIDERS = listOf("baseline", "candidate")

    val PINNED_JARS = linkedMapOf(
        "dyn4j-6.0.0.jar" to "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e",
        "jogl-all-2.3.2.jar" to "e74603dc77b4183f108480279dbbf7fed3ac206069478636406c1fb45e83b31a",
        "gluegen-rt-2.3.2.jar" to "084844543b18f7ff71b4c0437852bd22f0cb68d7e44c2c611c1bbea76f8c6fdf",
    )

    const val CANDIDATE_JAR = "dyn4k-core-jvm-0.1.0-alpha.1.jar"
    const val JAVASSIST_SHA256 = "eba37290994b5e4868f3af98ff113f6244a6b099385d9ad46881307d3cb01aaf"
    const val DEFAULT_HEADFUL_IMAGE = "localhost/dyn4k-migration:journeys"
    const val JAVASSIST_JAR = "javassist-3.30.2-GA.jar"
}

/**
 * The pinned identities a journey run checks.
 *
 * `DEFAULT` is the Python module's constants verbatim. A test supplies its own policy to exercise
 * the same code against a generated fixture whose bytes it can control; the production command
 * line always uses `DEFAULT`.
 */
data class JourneyPolicy(
    val sampleRevision: String = Journeys.SAMPLE_REVISION,
    val sourceManifestSha256: String = Journeys.SOURCE_MANIFEST_SHA256,
    val pinnedJars: Map<String, String> = Journeys.PINNED_JARS,
    val candidateJar: String = Journeys.CANDIDATE_JAR,
    val javassistSha256: String = Journeys.JAVASSIST_SHA256,
) {
    companion object {
        val DEFAULT = JourneyPolicy()
    }
}

/** One file of a raw-evidence tree, as the manifest records it. */
data class EvidenceFile(
    val relative: String,
    val digest: String,
    val symlink: Boolean = false,
)

/** The evidence-manifest rules of `journeys.py`. */
object JourneyEvidence {
    /** `journeys.raw_evidence_manifest` over already-read entries. */
    fun rawEvidenceManifest(entries: List<EvidenceFile>): String {
        val out = StringBuilder()
        for (entry in entries.sortedWith { left, right ->
            io.github.rubixhacker.harness.contract.CanonicalJson.compareCodePoints(left.relative, right.relative)
        }) {
            if (entry.relative == "summary.json" || entry.relative == "evidence.sha256") continue
            if (entry.symlink || "\n" in entry.relative) {
                throw MigrationFailure("unsafe raw evidence path: ${entry.relative}")
            }
            out.append(entry.digest).append("  ").append(entry.relative).append('\n')
        }
        return out.toString()
    }

    /** `journeys.record_unavailable`'s report, before the manifest fields are bound. */
    fun unavailableReport(reason: String): PyValue {
        val cases = mutableListOf<PyValue>()
        for (provider in Journeys.PROVIDERS) {
            for (scene in Journeys.SCENES) {
                cases.add(
                    pyMap(
                        "provider" to pyText(provider),
                        "scene" to pyText(scene),
                        "status" to pyText("UNAVAILABLE"),
                        "reason" to pyText(reason),
                    ),
                )
            }
        }
        return pyMap(
            "cases" to pyList(cases),
            "expected_cases" to pyInt(10),
            "passed_cases" to pyInt(0),
            "unavailable_cases" to pyInt(10),
            "failed_cases" to pyInt(0),
        )
    }

    /** `journeys.verify_evidence`'s binding check; returns the summary when it holds. */
    fun verifyEvidence(summary: PyValue, manifest: ByteArray, expectedManifest: ByteArray): PyValue {
        val digest = Sha256.of(manifest)
        val count = manifestLineCount(manifest)
        if (!manifest.contentEquals(expectedManifest) ||
            !pyEquals(summary.getOrNull("evidence_manifest_sha256") ?: PyValue.Null, pyText(digest)) ||
            !pyEquals(summary.getOrNull("evidence_file_count") ?: PyValue.Null, pyInt(count))
        ) {
            throw MigrationFailure("raw evidence changed or summary manifest binding differs")
        }
        return summary
    }

    /** Python's `len(manifest.splitlines())` over bytes. */
    fun manifestLineCount(manifest: ByteArray): Int {
        if (manifest.isEmpty()) return 0
        var lines = 0
        var index = 0
        while (index < manifest.size) {
            lines += 1
            while (index < manifest.size && manifest[index] != '\n'.code.toByte()) index += 1
            index += 1
        }
        return lines
    }
}
