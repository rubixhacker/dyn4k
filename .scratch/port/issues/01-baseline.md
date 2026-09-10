# Establish the immutable dyn4j 6.0.0 baseline

Id: 01
Parent: ../map.md
Label: wayfinder:research
Type: research
Status: resolved
Assignee: Codex research-01-baseline
Blocked by: none

## Question

Which exact source revision and published artifacts define dyn4j 6.0.0, and what functionality, tests, JVM-specific dependencies, and license/attribution obligations must the complete port account for? Inventory public packages, extension points, test coverage and portability hotspots. Verify current stable release metadata, pin source and artifact hashes, and distinguish shipped 6.0.0 from master. Do not design the Kotlin API.

## Comments

Created during initial map charting. Research may resolve factual questions; recommendations remain inputs to human decisions.


Research context: branch `research/baseline`; working tree `/var/home/stewart/Workspace/dyn4k-research/baseline`; report `docs/research/baseline.md`. Research is in progress; no result is accepted yet.

## Answer

Resolved by primary-source research. dyn4j 6.0.0 is pinned to source commit `058bf6d982a0fb89b54050f929f6ea9dae53b714`, with binary and sources-JAR SHA-256 pins. All 268 published Java source files match that checkout. The report inventories 17 exported packages, 199 test files, extension points, portability risks, and attribution requirements. Test annotations are not executed-test counts; no complete API manifest or upstream test run is claimed.

[Baseline research report](../../../docs/research/baseline.md). Research branch: `research/baseline`; report commit: `408daa20b35c220853970f9435eef6c10b0e494c`.
