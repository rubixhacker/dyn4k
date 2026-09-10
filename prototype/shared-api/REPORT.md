# Prototype findings for human review

Status: **initial feasibility demonstrated for the sampled boundary; decision pending**. No decision has been resolved and no charter requirement has been narrowed.

## Results observed on 2026-09-10 UTC

| Journey | Evidence | Observed result |
|---|---|---|
| Same unchanged Java source against both implementations | [baseline](evidence/baseline.txt), [candidate](evidence/candidate.txt), [diff](evidence/java-comparison.diff), [source hashes](evidence/fixture-checksums.txt) | Both compile and run; complete stdout byte-identical, empty diff. |
| Public field and protected-state aliases | Java fixture and [JVM declarations](evidence/jvm-declarations.txt) | Retained velocity is the protected field and getter result; protected transform is the public getter result; setter preserves vector identity. |
| World/body virtual dispatch through real integration | Java event trace | Public `step(1, .25)` reaches protected Java world override, Java body velocity/position overrides, and registered user solver/listener implementations. |
| Nested simulation re-entry | Java event trace | Begin listener invokes another real step. Nested step advances x to 1.0; outer step advances x to 2.5; final live velocity is 6.0. All world/body/velocity/solver identity checks pass. |
| Custom solver effect | Java fixture | Solver initialization increments the retained velocity before integration. Initialization and position methods each run twice across the two steps. Velocity-constraint method is deliberately skipped because there are no contacts/joints, matching baseline. Solver uses the captured canonical body; contact-body identity has not been tested. |
| DSL-created object delivered to unchanged Java | [mixed](evidence/mixed.txt) | Java writes velocity.x=4, calls Kotlin synchronously, Kotlin observes 4 and writes 6, Java observes 6 through its retained vector. Subsequent integration yields x=1.5. |
| Kotlin JVM runtime | [JVM](evidence/kotlin-jvm.txt) | DSL, explicit construction, context attach/explicit attach, shared aliases, nested callback and live immutable membership surface pass. x=2, velocity=4, snapshot=2, two callbacks. |
| Same common Kotlin journey on non-JVM runtime | [Node JS](evidence/kotlin-js.txt) | Same numeric states/identities and assertions pass on Node; JVM decimal formatting differs. Actual generated JS executed. |
| Membership view and owner iterator | Java outputs | Stable retained view reflects add/remove, preserves body identities, and snapshot remains independent. View add/set/iterator.remove throw UnsupportedOperationException. Owner iterator permits removal, sees later additions, rejects remove-before-next/double-remove with IllegalStateException, and exhausted next throws IndexOutOfBoundsException. |
| Kotlin mutation escape | JVM and JS journey | Attempted MutableList cast/add is rejected; membership remains unchanged. JVM unmodifiable wrapper rejects mutation; JS read-only collection rejects the cast. |
| Interactive terminal | [capture](evidence/play.ansi) | Driven through Kotlin +1, compatibility +1, callback toggle, step, remove, step while empty, reattach, unknown command, quit. At the first step: x=1.25, live velocity=5, snapshot=2. Removed body does not move. Invalid command leaves state intact. |

The harness also checks help and rejects an unknown mode with exit 2. All physics state/assertion output is produced by executable fixtures, not manually transcribed expectations.

## Reproduction and versions

Run `./prototype/shared-api/run verify` at the repo root. The script runs separate `compileBaseline` and `compileCandidate` JavaCompile tasks, JVM/JS/mixed execution, validates the baseline JAR hash, compares Java output, and captures [build output](evidence/build.log) and [versions](evidence/versions.txt). Run `./prototype/shared-api/run play` for the interactive surface.

Observed compiler/plugin: **Kotlin 2.4.10**. Context parameters compile as part of language 2.4 without the redundant experimental flag. This uses a **named context parameter**, not the superseded context-receiver syntax; the ordinary helper supplies the explicit equivalent. The [official context-parameter documentation](https://kotlinlang.org/docs/context-parameters.html) was consulted; successful compilation/execution is the evidence for this compiler.

Gradle wrapper: **9.7.1**. Build and Java fixture runtime: **JetBrains OpenJDK 25.0.3**; Java/Kotlin bytecode target **17**. Gradle's displayed embedded Kotlin **2.4.0** is its script runtime, not the project's compiler. Non-JVM runtime: managed **Node v24.10.0** on Linux x86_64.

Baseline: `org.dyn4j:dyn4j:6.0.0`, JAR SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`, [checksum output](evidence/baseline-checksum.txt). Upstream source checkout verified at `058bf6d982a0fb89b54050f929f6ea9dae53b714`.

## Source basis

The restricted translation retains the upstream BSD notice in [UPSTREAM-LICENSE.md](UPSTREAM-LICENSE.md). Consult these immutable baseline sources for what the sampled behavior represents:

- [Body integration](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/AbstractPhysicsBody.java): public/protected velocity storage, infinite mass behavior, translation and clamping.
- [World step](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractPhysicsWorld.java): overridable protected step and listener ordering.
- [Island.solve](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/Island.java): actual empty-contact solver dispatch and integration order.
- [Body collections and owner iterator](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractCollisionWorld.java): backed unmodifiable view and specialized removal/exhaustion semantics.

## What this supports, and what it does not

**Inference from the observations:** using compatibility-shaped common objects as the canonical model avoids the immediate field-write/identity/override problems of separate wrappers for this slice. Kotlin convenience code can remain small and share the exact objects. This supports continuing with the selected candidate, subject to human acceptance.

The cost is real: Java public/protected fields and virtual extension methods constrain the common model's storage and inheritance. This experiment does not justify promising arbitrary internal representation freedom or measuring the shim as negligible in size/cost. A future rename into different consumer artifacts cannot be inferred from this one-module prototype.

Remaining compatibility inventory includes the complete public/protected hierarchy, generic interfaces and constructors, fixture/joint/contact identity, nonempty solver callbacks and numerical outcomes, geometry arrays and transforms, user-data/null/exception behavior, callback structural mutation, static methods/overloads, owner bookkeeping, fail-fast iterators, serialization/copying/type checks, and performance. The prototype has deliberate omissions; it is not a drop-in replacement JAR.

Target evidence is **JVM + JS/Node only**. Native, Wasm, mobile/device runtimes, and the complete chosen compiler's non-deprecated target matrix remain unverified. This selects an experiment compiler, not the separate all-target toolchain/support decision. Numerical observations use exact values in the Kotlin journey and absolute tolerance 1e-12 in the Java fixture; this does not ratify a library-wide numerical tolerance.

## Review decision

Recommendation: accept this as **initial feasibility evidence for a compatibility-shaped authoritative common model**, retaining the full compatibility/target obligations. Before finalizing the boundary, the human may instead request a stronger probe of nonempty contact solving or another problematic extension surface. Neither response is assumed here. The canonical decision ticket stays open until that review.
