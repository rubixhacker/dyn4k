# Agreed charter

These requirements were agreed directly with the user during initial Wayfinder charting.

- Name: dyn4k.
- Destination: an implementation-ready specification for the complete port; this map produces decisions, not a production implementation.
- Idiomatic Kotlin library with a thin compatibility shim; no second physics engine in the shim.
- Baseline: latest stable dyn4j at selection time, verified as 6.0.0 through [Maven Central metadata](https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/maven-metadata.xml). Research must pin the matching immutable source revision and artifact checksums.
- Independent fork from that baseline. The shim targets only dyn4j 6.0.0, with no promise to track future upstream APIs.
- Full 6.0.0 library coverage, including geometry, collision detection, dynamics, joints, utilities, and public extension points. Implementation may be staged internally.
- Compatibility API available on every supported target; existing Java source must compile unchanged on JVM, including org.dyn4j imports. Binary compatibility with already compiled consumers is outside the initial contract.
- Every non-deprecated target available in the chosen Kotlin version is in scope, including experimental targets. Exact target list, chosen toolchain, and runtime-verification coverage remain to be decided.
- Preserve baseline algorithms and double precision. Numerical parity is verified with explicit tolerances; bit-for-bit cross-platform determinism is outside the initial contract.
- Workspace: /var/home/stewart/Workspace/dyn4k. Use the local Markdown tracker initially.

## Open boundaries

The Kotlin API shape, meaning and evidence of target support, numerical acceptance thresholds, performance budgets, artifact packaging, and distribution requirements remain decisions on the map. Research findings are evidence, not user approval of a design.

