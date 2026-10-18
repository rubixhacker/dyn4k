# JVM worker class-load evidence

`capture_actual.py` enables JDK21 `class+load` logging for its `jvmTest` worker.
The staging build does not receive the logging option. The option names a
home-backed file with `%p`, so the JVM writes its process ID into the filename
and every log line. The capture retains that raw file, the `execve` trace,
Gradle log, worker classpath, test XML, staged JAR, runtime, and source archive.
The trace records process arguments, not environment values.

The public receipt checker selects the one successful Gradle test worker
`execve`. It requires the captured method and log pattern in the Gradle
invocation, the same logging option in the worker launch, and the worker PID
on every class-load record. It requires `Transform`, `RotationOperationTap`,
`AbstractPhysicsWorld`, and `ToiAcceptedResetTap` to load exactly once from
the staged JAR. A separate scan rejects other engine class providers on the
complete worker classpath. The receipt hashes the raw log and capture XML.

This is executed JVM worker evidence for the audited class sources. It does
not qualify numerical parity, other target runtimes, or the 318 prospective
cases. The fixed 32-ulp rule and conditional `U(N)` status stay separate.
