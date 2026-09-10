# Chart the dyn4k multiplatform fork

Label: wayfinder:map
Status: open

## Destination

An implementation-ready specification for an idiomatic Kotlin Multiplatform fork of the complete dyn4j 6.0.0 library, with a thin fixed-version compatibility shim and explicit verification requirements for every in-scope target.

## Notes

- [Agreed charter](../../docs/planning/charter.md) is the ratified input to this map.
- Consult Wayfinder, grilling, domain-modeling, and research; use [the local tracker](../../docs/agents/issue-tracker.md).
- Charting is planning only. Resolve research autonomously; resolve at most one human decision ticket per later session through live discussion.
- Child tickets live in issues/. Query metadata for the frontier rather than keeping an open-ticket list here.
- Research reports live in docs/research/ with source citations and branch context pointers.

## Decisions so far

- [Establish the immutable dyn4j 6.0.0 baseline](issues/01-baseline.md) — Source and published artifacts pinned; functionality, tests and portability surfaces inventoried.

- [Establish the complete Kotlin target and verification matrix](issues/02-targets.md) — Candidate targets and evidence gaps enumerated; disputed watchOS deprecation remains an explicit input to the support decision.

- [Assess thin-shim compatibility feasibility](issues/03-shim.md) — Mutable state, identity and subclass dispatch constrain the core; candidate boundaries need a selected prototype before feasibility can be claimed.

## Not yet specified

- How to stage migration and implementation once the API and compatibility boundary are understood.
- Which concrete examples will best expose awkward API choices and establish a migration guide.
- Long-term evolution and versioning of the idiomatic API after the initial port, within the fixed shim contract.

## Out of scope

- Production implementation and release execution during this planning map.
- Tracking future dyn4j releases or supporting multiple upstream baselines.
- Binary compatibility with already compiled JVM consumers.
- Bit-for-bit cross-platform simulation determinism.
- Deprecated Kotlin targets in the selected toolchain.

