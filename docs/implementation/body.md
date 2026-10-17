# Root dynamics body port

The fixed baseline is dyn4j 6.0.0 at upstream revision
`058bf6d982a0fb89b54050f929f6ea9dae53b714`. The root
`org.dyn4j.dynamics` package contains nine public types:
`AbstractPhysicsBody`, `Body`, `BodyFixture`, `ContinuousDetectionMode`,
`Force`, `PhysicsBody`, `Settings`, `TimeStep`, and `Torque`. Its tenth Java
source is `package-info.java`. The pinned release has no standalone `Capacity`
type; body constructors accept fixture capacity.

The common Kotlin implementation keeps live fixture collections, protected
fields, mutable force identity, and the baseline's virtual method dispatch.
The Java source surface is checked against 289 public and protected baseline
declarations across the nine types. Unchanged upstream Java body tests and
staged Java and Kotlin consumers check behavior through their respective APIs.

Four internal field readers on subclassable types require special care:
`BodyFixture.rawDensity`, `Force.rawForce`, `TimeStep.rawDeltaTime`, and
`Torque.rawTorque`. Kotlin emits internal member functions as public JVM
methods with module-mangled names. Those names are legal Java identifiers.
Unchanged Java 8 subclasses can define the same names against dyn4j 6.0.0,
but the added final methods prevented those subclasses from compiling.
`@JvmSynthetic` hides the field readers from Java source. The helpers also
use JVM names containing a hyphen, which Java source cannot declare. Both
measures are needed: a synthetic final method with the same JVM descriptor
still causes `IncompatibleClassChangeError` when a Java subclass loads.
Common Kotlin calls and Kotlin metadata retain the helpers. The protected
fields remain available to Java subclasses. The Java extension consumer
checks all four names with matching and different return types against the
baseline and candidate.

The six-host common test also exercises Kotlin subclasses that override the
public getters. It checks that body integration reads stored fields, calls
the force completion callback with the actual step time, and retains mass and
torque behavior. Host results cover JVM, Linux x64, JS Node, Wasm JS Node,
Wasm WASI Node, and Android host. Android host execution is not device
execution. The full 2,385-case Java corpus, native and device runtimes, and
physical acceptance gates require separate evidence.
