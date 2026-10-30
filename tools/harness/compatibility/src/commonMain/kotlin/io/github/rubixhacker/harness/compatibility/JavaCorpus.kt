package io.github.rubixhacker.harness.compatibility

/**
 * The pinned Java corpus case identities of `tools/compatibility/java_corpus.py`.
 *
 * Ported: [PARAMETER_CLASSES], [PARAMETER_PATTERN], and [normalizedCases].
 *
 * Not ported: `read_xml`, `tool`, `checked_inputs`, `java_temp_directory`, `runtime_command`,
 * `replay_temp_directory`, `capture`, `validate_report`, and `main`. Those need an XML parser, a
 * JDK, git, and the JUnit runner. `read_xml` is the only gap in [normalizedCases]'s input path: the
 * port takes the identities a caller has already read.
 */
object JavaCorpus {
    /** Parameterised owners and the multiplicity each case identity must appear with. */
    val PARAMETER_CLASSES: Map<String, Int> = linkedMapOf(
        "org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest" to 25,
        "org.dyn4j.collision.broadphase.CollisionItemBroadphaseTest" to 29,
    )

    val PARAMETER_PATTERN = Regex("""([^\[]+)\[([^@\]]+)@([0-9a-fA-F]+)\]""")

    /**
     * Collapses repeated parameterised runs onto one case identity per parameter, numbering the
     * parameters in the order the corpus first ran them.
     */
    fun normalizedCases(identities: List<Pair<String, String>>): Map<Pair<String, String>, Int> {
        val groups = linkedMapOf<String, Map<Pair<String, String>, Int>>()
        for ((owner, count) in PARAMETER_CLASSES) {
            val rows = identities.filter { it.first == owner }.map { it.second }
            val seen = linkedMapOf<Pair<String, String>, MutableSet<String>>()
            for (name in rows) {
                val match = PARAMETER_PATTERN.matchEntire(name)
                    ?: throw IllegalArgumentException(
                        "parameterized case identity is malformed: $owner",
                    )
                val method = match.groupValues[1]
                val parameterType = match.groupValues[2]
                val address = match.groupValues[3]
                seen.getOrPut(parameterType to address) { linkedSetOf() }.add(method)
            }
            if (seen.size != 5 || rows.size != count * 5 || seen.values.any { it.size != count }) {
                throw IllegalArgumentException("parameterized case inventory differs: $owner")
            }
            groups[owner] = seen.keys.withIndex().associate { it.value to it.index }
        }
        val result = linkedMapOf<Pair<String, String>, Int>()
        for (identity in identities) {
            val owner = identity.first
            var name = identity.second
            val group = groups[owner]
            if (group != null) {
                val match = PARAMETER_PATTERN.matchEntire(name)
                    ?: throw IllegalArgumentException(
                        "parameterized case identity is malformed: $owner",
                    )
                val method = match.groupValues[1]
                val parameterType = match.groupValues[2]
                val address = match.groupValues[3]
                val index = group.getValue(parameterType to address)
                name = "$method[$parameterType#$index]"
            }
            val key = owner to name
            result[key] = (result[key] ?: 0) + 1
        }
        return result
    }
}
