# Define support and verification for every target

Id: 05
Parent: ../map.md
Label: wayfinder:grilling
Type: grilling
Status: open
Assignee: none
Blocked by: 02

## Question

Which candidate Kotlin version is the initial toolchain, and what exact compilation, test, runtime and consumer evidence is required for each in-scope target before release? Define how experimental targets and gaps in runtime infrastructure are disclosed and gated without reducing the agreed target scope.

## Comments

Created during initial map charting. Requires live user discussion before resolution.


Research input: [Target matrix](../../../docs/research/targets.md). Explicitly reconcile watchosArm32 documentation versus tagged-source deprecation before freezing the manifest; decide whether a pinned-plugin diagnostic probe is needed. Candidate Kotlin/Gradle/AGP versions are research recommendations, not approved choices. Include consumer platform floors and custom harness requirements in this decision.
