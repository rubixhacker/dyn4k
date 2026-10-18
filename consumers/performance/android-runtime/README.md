# Installed Android JVM short process producer

The debug and R8-optimized app and instrumentation pairs exercise the frozen small and medium
scenarios on Android API 21 or API 37. It uses the same fixture source as the
[portable producer](../portable/README.md). The build command checks that the
Android copy and portable source have identical SHA-256 digests. The direct
route calls the Kotlin convenience API; the compatibility route calls the
`org.dyn4j` API on the same staged engine. The baseline Java route stays on JVM.

Use the [host command](../../../tools/performance/sustained_android/README.md)
to build and capture. It requires a committed, clean source tree and a staged
repository with both Android AARs. The command accepts one exact manifest
scenario. It installs both APKs on a task-owned emulator and retains one raw
archive per run. An existing archive is never overwritten.

Each process writes its provider, package, guest identity, PID, construction,
warm-up clocks, fixture reset, measured clocks, and every step observation to
JSONL in the app's private files. The host reads the nonce-named stream through
the app's read-only evidence provider and
checks case order, counts, clocks, and identity. It also hashes the built and
installed APK bytes independently. The build receipt records both resolved
runtime dependency graphs with artifact versions, paths, and hashes. For the
release pair it binds the R8 mapping and mapped `World` class in both APKs.
The instrumentation checks that the actual provider class is loaded from the
target app and can construct a `World` before it starts the fixture.

The R8 build uses a debug signing key for local installation. Its APK is not
a release-signing or production-installability result.

This bounded process is a producer check. Its result remains `unpassed` for
performance qualification. It does not establish sustained timing, reference
noise, allocation, attributable memory, plateau, or stress acceptance.
