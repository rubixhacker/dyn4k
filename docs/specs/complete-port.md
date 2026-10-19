# Complete the dyn4j 6.0.0 Kotlin port

## Problem Statement

Developers need the complete dyn4j physics library in Kotlin Multiplatform. Existing Java applications must be able to replace dyn4j without changing their source. New Kotlin applications need a clear API that uses the same objects and physics implementation.

The repository currently contains planning evidence. The shared-model prototype proves a small part of the API boundary. It does not provide a production engine.

## Solution

Port the complete fixed dyn4j 6.0.0 baseline to common Kotlin. Provide the original `org.dyn4j` declarations in `dyn4k-core`. Provide Kotlin names and conveniences in `dyn4k`. Both modules share the same mutable objects. Publish them with one version.

Complete implementation and release qualification are separate claims. A missing runtime, failed physical check, or unavailable memory probe remains an open requirement. A successful build cannot replace execution.

## User Stories

1. As a Kotlin developer, I want vectors, rotations, matrices, and transforms, so that I can describe a two-dimensional scene.
2. As a Kotlin developer, I want all baseline shapes, so that I can model the same bodies as dyn4j.
3. As a geometry user, I want robust predicates, hulls, decomposition, and simplification, so that I can prepare usable shapes.
4. As a collision user, I want every baseline broad-phase and narrow-phase algorithm, so that I can retain existing behavior.
5. As a collision user, I want manifolds, distance queries, ray casts, and continuous detection, so that I can inspect contact and motion.
6. As a simulation developer, I want bodies, fixtures, materials, mass, and forces, so that I can create a physical world.
7. As a simulation developer, I want the baseline contact solver and world stepping, so that bodies interact correctly.
8. As a simulation developer, I want every baseline joint and its supported modes, so that I can build constrained mechanisms.
9. As a simulation developer, I want natural sleep, wake, and body removal, so that world state stays consistent.
10. As a simulation developer, I want the baseline event order and callback data, so that my application responds at the correct stage.
11. As an extension author, I want subclass overrides and custom detectors and solvers to run, so that my extensions retain their effect.
12. As a Java developer, I want unchanged `org.dyn4j` imports and source signatures, so that migration needs only a dependency change.
13. As a Java developer, I want mutable public fields, protected state, and live views, so that existing code observes the same objects.
14. As a Kotlin developer, I want properties, operators, builders, and callback helpers, so that I can use Kotlin conventions.
15. As a mixed-language developer, I want both APIs to share identity and state, so that I need no conversion or synchronization.
16. As a library consumer, I want all approved Kotlin targets, so that my platform does not lose functionality.
17. As a library consumer, I want documented runtime minima, so that I can choose a supported environment.
18. As a migration user, I want the pinned sample applications to compile and run unchanged, so that I can inspect a real migration.
19. As a maintainer, I want a complete declaration and test inventory, so that missing coverage stays visible.
20. As a maintainer, I want numerical comparisons with fixed inputs and explicit units, so that failures can be reproduced.
21. As a maintainer, I want separate physical and parity checks, so that a baseline defect cannot count as physical correctness.
22. As a maintainer, I want timing, allocation, and memory measurements, so that I can enforce the agreed resource budgets.
23. As a consumer, I want staged artifacts with correct metadata, sources, documentation, and licenses, so that I can resolve and inspect the library.
24. As a Java consumer, I want a clear duplicate-provider error, so that dyn4j and dyn4k classes cannot silently conflict.
25. As a release owner, I want evidence tied to one commit and its artifact checksums, so that a release claim is auditable.
26. As a reader, I want clear documentation and code comments, so that I can understand the limits and use the library correctly.

## Implementation Decisions

- The immutable source baseline is `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The binary SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The source archive SHA-256 is `83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223`.
- Port all library functionality across the 17 exported packages. Account for every production declaration, including protected and nested extension surfaces. The baseline has 268 Java source files, including package and module descriptors; file count alone is not a coverage measure.
- Use one authoritative mutable common model. Preserve baseline algorithms, double precision, object identity, exception behavior, collection views, callback order, and subclass dispatch. The Kotlin module adds conveniences over these objects.
- Publish `io.github.rubixhacker:dyn4k-core` and `io.github.rubixhacker:dyn4k`. Kotlin convenience packages use `io.github.rubixhacker.dyn4k`. The first preview version is `0.1.0-alpha.1`.
- Retain Kotlin/KGP 2.4.20, Gradle 9.5.0, build JDK 21, AGP 9.3.1, and Xcode 26.5. The [approved Xcode change](https://github.com/rubixhacker/dyn4k/issues/32#issuecomment-6259967473) uses the installed local Mac over SSH. Do not run GitHub-hosted macOS jobs. A toolchain mismatch is a reported blocker, not permission to change the pins silently. Runtime minimum and current versions remain separate from the Xcode build-tool pin.
- Keep all 21 approved targets: JVM, Android JVM, JS, Wasm JS, Wasm WASI, Linux x64/ARM64, Windows x64, macOS ARM64, iOS ARM64/simulator ARM64/x64, tvOS ARM64/simulator ARM64, watchOS ARM64/device ARM64/simulator ARM64, and all four Android Native ABIs.
- Retain the full [support contract](https://github.com/rubixhacker/dyn4k/issues/6#issuecomment-5651793360), including 28 runtime families, minimum/current versions, both build configurations, staged consumers, and physical Apple devices.
- Retain the full [performance policy](https://github.com/rubixhacker/dyn4k/issues/8#issuecomment-5674480273). Freeze fixtures and measurement methods before evaluating the candidate. The [performance manifest task](https://github.com/rubixhacker/dyn4k/issues/17) remains open until its empirical requirements pass.
- Preserve approved numerical decisions on [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7). Additional decisions made under the user's delegated approval must be recorded there. No threshold may be widened to hide a candidate failure.
- Preserve the default-profile penetration failure separately from configured-profile qualification. The configured profile uses an internal step of 1/120 second and outer groups of 4, 2, or 1. Endpoint copies do not advance time or event history.
- Keep baseline compatibility behavior unless a separately documented change is approved. Report known baseline defects and their physical consequences. Never substitute a corrected algorithm silently.
- Select the first-party sample collection at revision `2c6b318e929baab77e9753ae78a4965eee74a30a` as the migration application. Retain its Java sources unchanged. Compile the collection and execute Tracking, Pyramid, Crank, Billiards, and Truck with recorded input and observation. Confirm actual CCD activity before claiming that journey covers CCD.
- Stage delivery in independently verifiable consumer journeys. Implement tickets in separate worktrees and assemble reviewed changes directly on `main` as they are ready. PR47 is merged; no single replacement integration branch or giant replacement PR is planned. Review each assembled change and its combined behavior.
- Use Luna for bounded, routine work and Sol for coupled algorithms, compatibility, and review. Record the actual model. A separate agent reviews the integrated code and spec coverage.
- Use ISO 24495-1:2023 and ISO 24495-3:2026 for human-readable text. Use ASD-STE100 Issue 9 for new code comments. Preserve required upstream legal notices. Review language as well as technical accuracy; do not claim formal certification.

## Testing Decisions

- Test through the public library and consumer boundaries. These are the approved seams under the user's instruction to apply recommended choices. Use additional protected-member probes only where unchanged Java extension behavior is itself part of the contract.
- Use small red-green cycles for each consumer journey. Test expected behavior, not the chosen implementation structure.
- Run the unchanged baseline Java tests on JVM wherever applicable. Inventory all 199 test files and 2,171 test annotations; record actual expanded case counts rather than equating annotations with executions.
- Add common Kotlin behavioral tests for all functional areas. Run the complete portable suite on every required runtime and build configuration. JVM tests alone do not qualify other targets.
- Compare fixed scenarios against the pinned baseline in separate processes. Include geometry, collision, dynamics, every joint type and mode, lifecycle, custom extensions, and error cases.
- Test Java public fields, protected extension state, generic signatures, static members, null behavior, live collection views, iterator mutation, callback re-entry, and mixed Kotlin/Java identity.
- Reject non-finite values, missing channels, skipped cases, empty suites, and mismatched identities. Keep exact structural checks separate from numerical tolerances and physical limits.
- Bind test counts, raw observations, environment identity, and artifact checksums to the candidate commit. A later code or build change invalidates affected evidence.
- Test staged external consumers and dependency conflicts. Keep baseline oracle dependencies out of production artifacts.
- Run the approved sustained performance and memory checks. Unsupported probes and unavailable hardware are incomplete evidence, never zero readings.
- Require independent standards and spec reviews. Resolve their actionable findings before landing the reviewed assembled changes on `main`. Run a retrospective after implementation and review.

## Out of Scope

- Tracking later dyn4j releases or multiple compatibility baselines.
- Binary compatibility with already compiled upstream consumers.
- Bit-for-bit simulation identity across platforms.
- Deprecated Kotlin targets.
- Direct Swift/Objective-C and JavaScript/TypeScript API promises.
- Public release claims before all required gates pass.

## Further Notes

The user authorized the move from planning to implementation on 2026-10-17. The previous planning-only restriction no longer limits this work. The user also authorized publication of this spec and its implementation issues on GitHub, and delegated remaining design choices to the agent's recommendations.

This spec defines the full destination. Unavailable qualification infrastructure does not narrow it. Keep incomplete tickets open and publish the exact remaining work.
