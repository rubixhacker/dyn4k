# Shared mutable API and compatibility boundary — throwaway prototype

**Awaiting human review. This is a disposable boundary experiment, not dyn4k's production engine or a finalized API.**

Question: can real compatibility-shaped objects be the authoritative mutable model for both API surfaces, retaining Java fields, protected state, subclass dispatch, live aliases, and Kotlin conveniences without synchronization or a second physics implementation?

Decision ticket: [Prototype the shared mutable API and compatibility boundary](https://github.com/rubixhacker/dyn4k/issues/10). Follows the [agreed API direction](https://github.com/rubixhacker/dyn4k/issues/5#issuecomment-5611715433). The map and charter remain unchanged.

## Run

From the repository root, with Bash, a JDK capable of running Gradle 9.7.1 (verified with JDK 25), `sha256sum`, `diff`, and `rg` available:

```sh
./prototype/shared-api/run verify
./prototype/shared-api/run play
```

The Gradle wrapper downloads its pinned distribution and dependencies on first use; Kotlin's Gradle plugin manages Node. Nothing is installed as a service. The model is in memory. `verify` refreshes the evidence files; it does not write the tracker. `play` prints a small terminal frame after every command. Enter `k`, `j`, `c`, `s`, `r`, `s`, `a`, `bad`, `q` to replay the recorded manual journey. `j` uses the compatibility-shaped field access in Kotlin; the separately compiled Java fixture proves actual Java access.

## Candidate shape

- Common Kotlin owns the real `org.dyn4j` declarations and the one restricted stepping algorithm. On JVM, `@JvmField` emits actual public/protected fields. The Java fixture directly extends those classes.
- `dyn4k` is an idiomatic surface of extensions, a receiver-lambda body builder, a named context parameter, and a listener lambda helper. They return/use those same objects. No facade body/vector, alias cache, caller conversion, reconciliation pass, or second physics engine exists.
- `Body.velocity` returns `getLinearVelocity()` unchanged. Explicit `copy()` makes an independent snapshot.
- `World.members` returns the stored live read-only view. JVM uses `Collections.unmodifiableList`; JS uses a backed `AbstractList`. The owner iterator is separately implemented to match the sampled baseline behavior, including its unusual exhaustion exception.
- `body { velocity.x = 2.0 }` is equivalent to constructing `Body` and calling its setter. `with(world) { body.attach() }` is equivalent to `body.attachTo(world)`, which calls `world.addBody(body)`. `onBegin` registers an ordinary `StepListenerAdapter`.

This places compatibility constraints inside the common model. It does **not** prove that a separately named, freely evolving core hierarchy can be wrapped transparently. Package names, artifact dependencies, class inventory, and signatures remain provisional. In particular, `World<T : Body>` and the reduced hierarchy/interfaces are enough for these fixtures, not the baseline's full generic contract.

## Deliberately restricted physics

Only fixture-free, translational kinematic bodies are modeled: default infinite mass, nonzero linear velocity, no forces, torque, rotation, sleeping, collisions, joints, or CCD. The step computes position from live velocity and elapsed time, including the baseline's maximum-translation clamp. The measured scenarios stay below that clamp.

The ordering is a scoped translation of the pinned baseline's `AbstractPhysicsWorld.step`, `Island.solve`, and `AbstractPhysicsBody.integratePosition`. Each isolated moving body invokes the custom solver with **empty contact lists**. Solver initialization and position callbacks execute; the velocity-constraint callback must not execute for an empty island. The fixture proves this against the baseline. It does not manufacture collision/contact results.

This is enough to probe real integration and dispatch, **not contact-solver feasibility or numerical compatibility across the library**. `ContactConstraint` is only a generic declaration used by the empty-list solver signature. Calls outside the documented subset have no compatibility claim, including collection mutation through protected internals or solver argument lists, ownership across worlds, listener-list mutation during dispatch, nulls, overload inventories, or unequal-dt recursive steps.

## Evidence and interpretation

See [REPORT.md](REPORT.md) for results and [evidence/](evidence/) for raw output. The unchanged [Java consumer](fixtures/Consumer.java) is compiled once against the checksum-pinned dyn4j JAR and separately against the candidate JAR plus Kotlin runtime. The candidate runtime does not include dyn4j's JAR. [Mixed.kt](fixtures/Mixed.kt) calls the same compiled Java consumer from a DSL-created object and re-enters Kotlin.

The probe is retained on `prototype/shared-mutable-api`. The decision ticket's evidence comment supplies the exact published revision; review that immutable revision rather than a moving branch. No prototype code should be merged to main.
