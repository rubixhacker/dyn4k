# dyn4k

Language for the multiplatform physics library and its migration contract.

## Language

**dyn4k**: The independently evolving Kotlin Multiplatform fork of dyn4j.

**Baseline**: The fixed dyn4j 6.0.0 release whose library functionality and compatibility surface define the initial port.

**Kotlin API**: The idiomatic interface through which new Kotlin consumers use dyn4k.

**Compatibility shim**: The thin interface that exposes the baseline's API while using dyn4k's engine, so existing consumers can migrate.

**Source compatibility**: Existing baseline Java source compiles unchanged against the shim on JVM, including its original package imports.

**Numerical parity**: Corresponding simulation results agree within explicitly chosen tolerances, without requiring identical floating-point bit patterns across platforms.

