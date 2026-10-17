# Polygon algorithms and Java extension surface

The fixed baseline is dyn4j 6.0.0 at source revision
`058bf6d982a0fb89b54050f929f6ea9dae53b714`. The polygon slice owns
`org.dyn4j.geometry.hull`, `org.dyn4j.geometry.decompose`, and
`org.dyn4j.geometry.simplify`. Its algorithms and support types live in common
Kotlin. The JVM artifact retains the baseline package and subclass contracts.

The 170-entry extra-method inventory in
`/tmp/dyn4k-full-java-probe/extra-methods.json` names 39 subclassable baseline
types. Exactly one entry belongs to these three packages:
`VertexClusterReduction.getClusterTolerance(): double`. Baseline
`VertexClusterReduction` stores the tolerance in a private field and has no
getter. A Java subclass can therefore declare its own
`String getClusterTolerance()` method.

The common Kotlin class keeps `clusterTolerance` as a readable property for
Kotlin consumers. Its JVM getter is marked synthetic, so Java source does not
inherit that helper name. The getter and Kotlin metadata remain in the JVM
artifact. `PolygonExtraMethodsProbe.java` compiles unchanged with Java 8
against the baseline, staged JVM, and Android host class archives. It runs
the subclass helper and inherited simplification algorithm. A common Kotlin
subclass test reads the property, declares its own helper, and executes the
algorithm on each available host.

The unchanged upstream Java polygon suites contain 290 cases. The portable
polygon corpus contains 284 cases per available host. The separate
`nsoft1.dat` area-quality limit is shared by baseline and candidate: its
Bayazit pieces total `18.60476525953471` square units versus input shoelace
area `18.08387899963746` square units, with a zero-area piece. That quality
case remains failed physical evidence. Six host runs do not qualify every
declared target or an Android device.
