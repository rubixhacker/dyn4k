# Assess thin-shim compatibility feasibility

Id: 03
Parent: ../map.md
Label: wayfinder:research
Type: research
Status: resolved
Assignee: Codex research-03-shim
Blocked by: none

## Question

Can a thin multiplatform shim preserve the complete dyn4j 6.0.0 API while delegating to an idiomatic Kotlin engine? Investigate public/protected inheritance, generic signatures, static methods/fields, overloads, exceptions, mutable aliases, object identity, collections, callbacks and custom engine extensions. Address unchanged Java source on JVM separately from Kotlin access on other targets. Cite concrete baseline examples and official Kotlin interop contracts. Identify design constraints, cost risks and experiments needed; do not select the user's API design.

## Comments

Created during initial map charting. Research may resolve factual questions; recommendations remain inputs to human decisions.


Research context: branch `research/shim`; working tree `/var/home/stewart/Workspace/dyn4k-research/shim`; report `docs/research/shim.md`. Research is in progress; no result is accepted yet.

## Answer

Resolved as a source/documentation investigation. A complete thin shim is not yet proven feasible. Public mutable fields, live aliases, protected state and internal virtual dispatch constrain the engine's authoritative model. JVM declarations need explicit field/static/overload/generic shaping; user callbacks and solvers need identity-preserving bidirectional behavior. The report identifies candidate boundaries and concrete feasibility experiments, without selecting a Kotlin API or claiming a compiled prototype.

[Shim feasibility report](../../../docs/research/shim.md). Research branch: `research/shim`; report commit: `5617a64211ad6077702179bfe88ef70231f9bdf8`. [Choose the idiomatic Kotlin API and shim boundary](04-kotlin-api.md) owns design selection and the decision to prototype the boundary.
