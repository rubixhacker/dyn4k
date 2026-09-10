# Establish the complete Kotlin target and verification matrix

Id: 02
Parent: ../map.md
Label: wayfinder:research
Type: research
Status: resolved
Assignee: Codex research-02-targets
Blocked by: none

## Question

Which Kotlin toolchain should be considered for this port, and which non-deprecated JVM, Android, JavaScript, Wasm and Native targets does it expose, including experimental targets? Enumerate exact target identifiers, support status and source citations, build-host restrictions, test execution environments and publication constraints. Recommend a dated candidate matrix without treating unavailable runtime evidence as completed support or silently omitting targets.

## Comments

Created during initial map charting. Research may resolve factual questions; recommendations remain inputs to human decisions.


Research context: branch `research/targets`; working tree `/var/home/stewart/Workspace/dyn4k-research/targets`; report `docs/research/targets.md`. Research is in progress; no result is accepted yet.

## Answer

Resolved as a factual inventory, not a toolchain or release-policy selection. Kotlin 2.4.20 is a candidate with 21 documented non-deprecated targets (16 Native and five other target configurations). A disputed 22nd candidate, watchosArm32, remains explicit because current documentation and pinned source disagree on deprecation. The report records host restrictions, runtime harness gaps, consumer/publication constraints, and separate declared/built/executed/consumable evidence states. No compiler, test or publication execution is claimed.

[Target research report](../../../docs/research/targets.md). Research branch: `research/targets`; report commit: `e0ab42c7a41d2fe7ffe311d426edb478384c22c9`. The exact manifest, including the watchOS discrepancy and any required pinned-toolchain probe, remains with [Define support and verification for every target](05-support-contract.md).
