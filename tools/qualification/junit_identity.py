"""Approved (JUnit) result identities for Gradle and device test reports.

TestBalloon writes `classname="suite_<package>.<SuiteProperty>"` and `name="<test>[<target>]"`,
while the approved corpus records the JUnit shape `classname="<package>.<Class>"` and
`name="<test>"`. Kotlin suite properties keep the original class names, so stripping the `suite_`
prefix and the trailing `[...]` recovers the approved identity exactly.

Reports written before the conversion keep working: they already carry the approved shape, and
normalisation leaves them unchanged. Every consumer normalises at the read boundary so that the
same set of cases is required and the same foreign identities are rejected.
"""

SUITE_PREFIX = "suite_"


def normalized_identity(node):
    """Map a TestBalloon result identity to the JUnit-style approved identity."""
    return normalized(str(node.get("classname") or ""), str(node.get("name") or ""))


def normalized(classname, name):
    """Normalise one `(classname, name)` pair; both shapes are accepted."""
    if classname.startswith(SUITE_PREFIX):
        classname = classname[len(SUITE_PREFIX):]
    if name.endswith("]") and name.rfind("[") > 0:
        name = name[:name.rfind("[")]
    return classname, name


def normalized_class(classname):
    """Normalise a class name alone, for the report shapes that carry no method suffix."""
    if classname.startswith(SUITE_PREFIX):
        return classname[len(SUITE_PREFIX):]
    return classname
