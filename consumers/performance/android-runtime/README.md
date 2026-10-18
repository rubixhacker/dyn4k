# Installed Android JVM short process producer

This app and instrumentation pair exercises the frozen small and medium
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
JSONL in the app's private files. The host reads that stream with `run-as` and
checks case order, counts, clocks, and identity. It also hashes the built and
installed APK bytes independently.

This bounded process is a producer check. Its result remains `unpassed` for
performance qualification. It does not establish sustained timing, reference
noise, allocation, attributable memory, plateau, or stress acceptance.
