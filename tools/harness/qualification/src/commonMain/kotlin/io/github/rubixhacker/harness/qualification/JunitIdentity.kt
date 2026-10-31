package io.github.rubixhacker.harness.qualification

/**
 * `tools/qualification/junit_identity.py`: the approved (JUnit) result identities.
 *
 * TestBalloon writes `classname="suite_<package>.<SuiteProperty>"` and `name="<test>[<target>]"`,
 * while the approved corpus records `classname="<package>.<Class>"` and `name="<test>"`. Stripping
 * the `suite_` prefix and the trailing `[...]` recovers the approved identity exactly; reports that
 * already carry the approved shape are unchanged.
 */
object JunitIdentity {
    const val SUITE_PREFIX = "suite_"

    /** `normalized(classname, name)`: both shapes are accepted. */
    fun normalized(classname: String, name: String): Pair<String, String> {
        val normalizedClass = if (classname.startsWith(SUITE_PREFIX)) {
            classname.removePrefix(SUITE_PREFIX)
        } else {
            classname
        }
        val normalizedName = if (name.endsWith("]") && name.lastIndexOf('[') > 0) {
            name.substring(0, name.lastIndexOf('['))
        } else {
            name
        }
        return normalizedClass to normalizedName
    }

    /** `normalized_class(classname)`: for report shapes that carry no method suffix. */
    fun normalizedClass(classname: String): String =
        if (classname.startsWith(SUITE_PREFIX)) classname.removePrefix(SUITE_PREFIX) else classname
}
