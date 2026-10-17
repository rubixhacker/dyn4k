# World port inventory and evidence

## Pinned inventory

The source is dyn4j 6.0.0 revision `058bf6d982a0fb89b54050f929f6ea9dae53b714` at `/tmp/dyn4k-upstream-6.0.0`. The owned surface contains 39 production Java files, 9,184 source lines, 52 compiled types including 13 nested classes, and 14 unchanged upstream test files with 189 textual `@Test` annotations. Textual annotations are not executed-case counts. The pinned binary is `/tmp/dyn4k-baseline-cache/dyn4j-6.0.0.jar` (SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`).

| Package | Pinned production files | Pinned tests |
| --- | --- | --- |
| `org.dyn4j.world` | `AbstractCollisionWorld`, `AbstractPhysicsWorld`, `BroadphaseCollisionData`, `BroadphaseCollisionDataFilter`, `BroadphaseCollisionDataFilterAdapter`, `CollisionBodyBroadphaseCollisionDataFilter`, `CollisionData`, `CollisionItemAdapter`, `CollisionWorld`, `ConstraintGraph`, `ConstraintGraphNode`, `ContactCollisionData`, `DetectFilter`, `Island`, `ManifoldCollisionData`, `NarrowphaseCollisionData`, `PhysicsBodyBroadphaseCollisionDataFilter`, `PhysicsBodySweptAABBProducer`, `PhysicsWorld`, `ValueMixer`, `World`, `WorldCollisionData` | `AbstractCollisionWorldTest` (65), `AbstractPhysicsWorldTest` (61), `BroadphaseFilterAdapterTest` (1), `CollisionBodyBroadphaseFilterTest` (2), `CollisionItemAdapterTest` (5), `ConstraintGraphTest` (25), `DetectFilterTest` (4), `IslandTest` (4), `PhysicsBodyBroadphaseFilterTest` (4), `PhysicsBodySweptAABBProducerTest` (4), `ValueMixerTest` (3), `WorldTest` (1) |
| `org.dyn4j.world.listener` | `BoundsListener`, `BoundsListenerAdapter`, `CollisionListener`, `CollisionListenerAdapter`, `ContactListener`, `ContactListenerAdapter`, `DestructionListener`, `DestructionListenerAdapter`, `StepListener`, `StepListenerAdapter`, `TimeOfImpactListener`, `TimeOfImpactListenerAdapter`, `WorldEventListener` | `ListenerAdaptersTest` (6) |
| `org.dyn4j.world.result` | `ConvexCastResult`, `ConvexDetectResult`, `DetectResult`, `RaycastResult` | `DetectResultTest` (4) |

`package-info.java` is excluded. The 13 nested binary types are the 11 iterator/handler classes in `AbstractCollisionWorld` and the two iterator/handler classes in `AbstractPhysicsWorld`. The pinned JVM declaration inventory is `/tmp/dyn4k-issue39-world-pinned-declarations.txt` (SHA-256 `4c13c9ccabbbf7ed2c2f30b846be283e0ecd1c235048cecb15fa1bc53df38483`). It records `javap -protected` output for each of the 52 compiled types and 594 member lines, including constructors. Private and package members require a separate compatibility audit. Declaration parity must be checked on JVM and both Android archives after implementation. The unchanged upstream suite and staged consumers must execute before this slice can pass.

## Current gate state

Implementation and verification are in progress. The default sleep/wake physical penetration result remains a separate known baseline failure: 125,847 of 126,000 end states exceeded the approved ceiling. The `nsoft1.dat` area-quality failure is separate baseline evidence. No candidate world physical, numerical, runtime, or migration gate is marked passed by this inventory.
