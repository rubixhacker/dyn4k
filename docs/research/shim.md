# Thin-shim compatibility feasibility

Research date: 2026-09-09. Ticket: **Assess thin-shim compatibility feasibility**. Branch: `research/shim`.

## Finding

The complete compatibility promise is materially stronger than a package rename and forwarding facade. Source inspection identifies no general impossibility, but **a thin shim over an independently designed Kotlin object model is not established as feasible**. Mutable public fields, protected state, live aliases, and overridable engine methods constrain the core itself. “Thin” can plausibly mean one physics implementation plus compatibility declarations and adapters; it cannot yet promise negligible adapter complexity or unrestricted core representation choices.

This is source/documentation research, not a compiled or executed compatibility proof. No prototype, engine implementation, exhaustive API extraction, or target build was performed. The API design remains a human decision.

## Baseline and method

`git ls-remote https://github.com/dyn4j/dyn4j.git 'refs/tags/6*'` returned annotated tag `17df5075306d55b6435b866defaa1483a33188fc`, peeled to `058bf6d982a0fb89b54050f929f6ea9dae53b714`. A shallow checkout of tag 6.0.0 was inspected with targeted source searches. All dyn4j links below pin that commit. Baseline artifact verification belongs to the separate baseline research report.

Official Kotlin interop documentation was read live and its corresponding source inspected at [kotlin-web-site revision 456f479aaff89dd6aec6e7886b40d31e693db44a](https://github.com/JetBrains/kotlin-web-site/tree/456f479aaff89dd6aec6e7886b40d31e693db44a). These are documentation facts, not verification against the still-unselected dyn4k compiler.

## Concrete compatibility constraints

### Public fields and live aliases constrain storage

- [Vector2](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Vector2.java#L46-L63) is non-final and exposes `public double x` and `y`. Its [mutating add overloads](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Vector2.java#L452-L467) return the receiver.
- [AbstractPhysicsBody.getLinearVelocity](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/AbstractPhysicsBody.java#L1124-L1126) returns its stored vector. [AbstractCollisionBody.getTransform and setTransform](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision/AbstractCollisionBody.java#L418-L442) expose an existing transform and copy values into it, respectively. [Polygon.getVertices](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Polygon.java#L210-L212) returns the stored array.

**Inference:** existing Java code can retain a velocity reference, assign `velocity.x`, and later expect the body to use that value. A facade containing a copied vector cannot observe a raw field assignment through a setter. Likewise, allocating new wrappers on every getter loses reference identity. Shared authoritative storage, or a demonstrably complete synchronization protocol, is required. The latter becomes especially difficult around callbacks and re-entrant access. This is a stronger issue than merely reproducing method names.

### Inheritance includes data and internal dispatch

[AbstractCollisionBody](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision/AbstractCollisionBody.java#L51-L77) exposes protected transforms, fixture lists, radius, user data, handler, owner, and enabled state. [AbstractPhysicsWorld](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractPhysicsWorld.java#L99-L170) exposes protected settings, gravity, solvers, listeners, joints, and graph state. [World](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/World.java#L47-L71) has generic inheritance, two constructors, and an overridable collision-data factory. [Detection invokes extension hooks](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractCollisionWorld.java#L733-L763) during engine work.

Kotlin's [delegation contract](https://github.com/JetBrains/kotlin-web-site/blob/456f479aaff89dd6aec6e7886b40d31e693db44a/docs/topics/delegation.md) forwards interface members but calls inside the delegate do not dispatch through wrapper overrides. Its [visibility rules](https://kotlinlang.org/docs/visibility-modifiers.html) also differ from Java's package access to protected members.

**Inference:** `by delegate` cannot by itself preserve Java subclasses whose overrides must participate in stepping/detection. Reproducing protected fields while letting a separate delegate maintain different state is similarly insufficient. Compatibility classes must preserve the extension hierarchy and route internal calls through the correct user object. Inventory must include protected constructors, members, and nested types, not just public methods.

### JVM declarations need intentional shaping

The [official interop contract](https://github.com/JetBrains/kotlin-web-site/blob/456f479aaff89dd6aec6e7886b40d31e693db44a/docs/topics/jvm/java-to-kotlin-interop.md) supplies useful mechanisms: properties normally emit accessors; `@JvmField` exposes backed fields but excludes delegated/open properties; `@JvmStatic` emits static methods; default arguments alone do not reproduce Java overloads; wildcard annotations control generic signatures; non-null public parameters add entry checks. These mechanisms require declaration-by-declaration auditing, not an assumption of automatic compatibility.

[Geometry](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Geometry.java#L53-L114) has static constants and both list and vararg overloads. [ContactConstraintSolver](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/contact/ContactConstraintSolver.java#L40-L64) takes nested generic lists and retains the historical names `solveVelocityContraints` and `solvePositionContraints`. The shim must retain these spellings even if the idiomatic API corrects them.

Kotlin [type aliases do not introduce new types](https://github.com/JetBrains/kotlin-web-site/blob/456f479aaff89dd6aec6e7886b40d31e693db44a/docs/topics/type-aliases.md). Therefore aliases alone cannot supply Java-visible `org.dyn4j` classes for unchanged imports. Preserving those real JVM declarations remains necessary even without binary compatibility.

### Collections, nulls, and user objects are observable behavior

[Fixture access](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision/AbstractCollisionBody.java#L277-L287) returns a stored unmodifiable view and separately offers a custom iterator. [World construction](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractCollisionWorld.java#L220-L232) builds unmodifiable views over live lists. [WoundIterator.remove](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/WoundIterator.java#L81-L83) throws. A snapshot or a merely read-only Kotlin type is not evidence of equivalent liveness, mutation rejection, or iterator behavior.

[User data](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision/AbstractCollisionBody.java#L448-L457) stores and returns an arbitrary reference, including null. The shim should not use this slot for its own adapters. The transform setter above deliberately ignores null; replacing it with a non-null Kotlin boundary changes behavior. [ArgumentNullException](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/exception/ArgumentNullException.java#L33-L43) has a specific JVM superclass. Null acceptance and exception hierarchy need explicit coverage.

### Callbacks and custom engines require bidirectional bridges

[ContactListener](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/listener/ContactListener.java#L48-L146) is a multi-method generic interface, not a single function. [Solver replacement](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractPhysicsWorld.java#L862-L918) allows user implementations. [World stepping](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractPhysicsWorld.java#L1225-L1293) calls registered listeners during simulation.

**Inference:** adapting only inputs is insufficient. Callbacks must receive canonical body/fixture/contact identities, preserve generic user subtypes and ordering, and route user solver effects back into authoritative state. Adapter allocation and collection wrapping in these paths are performance risks to measure, not proven failures.

## All-target boundary

The agreed all-target shim means Kotlin-callable dyn4j-shaped declarations on common/Native/JS/Wasm targets; unchanged Java source compilation is an additional JVM obligation. Actual `java.util` classes and JVM field emission are not a portable common API. Candidate common equivalents need deliberate collection, iterator, exception, and identity semantics; JVM shaping may need annotations or platform declarations. Neither a JVM-only adapter nor Java type aliases would meet the charter. This report does not choose the compiler, exact targets, or source-set arrangement.

## Candidate approaches, not decisions

1. **One canonical mutable model with two API surfaces.** Compatibility objects participate directly in authoritative state; idiomatic properties/operators/builders provide the Kotlin surface. Promising for identity and field writes, but preserves compatibility constraints deep in the model and needs package/dependency-cycle design.
2. **Shared engine algorithms behind explicit model contracts.** Compatibility objects supply state and extension hooks through contracts also used by idiomatic objects. Potentially preserves one physics implementation and distinct APIs, at the cost of indirection, generic complexity, and careful override routing.
3. **Separate facade objects with delegates and identity caches.** Plausible for isolated immutable results or utility calls; high risk as the universal strategy because raw mutable fields, protected state, arrays, and internal virtual dispatch remain unsolved by caches alone.

None is ratified. A second physics implementation in the shim would violate the charter.

## Experiments needed after a human design discussion

- Compile the same Java consumer sources against upstream and the candidate shim: field assignments, static imports, overloads/varargs, subclass constructors/protected fields, nested generic solver implementations, and historical method spellings.
- Run a minimal alias journey: retain velocity/transform/vertex references, mutate through old and new APIs, and verify identity plus subsequent engine observation. Include callback re-entry.
- Exercise a custom body/world override and custom solver through an actual step; observe that internal dispatch reaches the user implementation with the original objects.
- Verify live collection views, mutation rejection, iterator behavior, null special cases, and user-data identity on JVM and representative non-JVM runtimes; later extend to the complete agreed matrix.
- Extract the complete public/protected baseline declaration inventory and compare JVM signatures plus source fixtures. Passing a few fixtures would establish feasibility, not complete 1:1 coverage.

The research ticket can close with these factual constraints. API topology, acceptable adapter cost, and the prototype choice remain open human decisions.
