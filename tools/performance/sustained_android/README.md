# Capture an installed Android JVM short process

Build a committed source revision with local staged Android artifacts. The
build command uses JDK 21 and Gradle 9.5.0 from `/tmp/dyn4k-tools`, AGP 9.3.1,
KGP 2.4.20, and the installed Android SDK. It runs offline and checks the
resolved AAR bytes against the staged AAR bytes.

```bash
python3 tools/performance/sustained_android/capture.py build \
  --source-commit "$(git rev-parse HEAD)" \
  --staging-repository "$PWD/build/staging-repository" \
  --build-type debug \
  --receipt /tmp/dyn4k-performance-android-build.json
```

Run `build` again with `--build-type release` and a separate receipt for the
R8-optimized APK pair. Each capture uses the build type in its receipt.

After the ART full-corpus owner releases its ADB lease, create and start an AVD
whose name begins `dyn4k-performance-`. Use a separate ADB server port. The
capture command rejects the shared `emulator-5558` serial and port 5038.
Choose an API 21 or API 37 guest, then capture one frozen scenario:

```bash
python3 tools/performance/sustained_android/capture.py capture \
  --receipt /tmp/dyn4k-performance-android-build.json \
  --archive /tmp/dyn4k-performance-android-run-001 \
  --scenario separated.default.small.60hz.direct_kotlin \
  --api 21 --serial emulator-5560 \
  --avd-name dyn4k-performance-api21 \
  --adb-port 5039 --steps 120 --warmup-steps 60
```

The archive stores raw ADB output, installed APK bytes, the instrumentation
JSONL, and a receipt. It keeps failure output if a guest, install, process, or
record check fails. A captured short process still has qualification
`unpassed`. The receipt carries the Android absolute and direct/shim budgets as
metadata. The Java baseline comparison is JVM-only. No 600-second, memory,
plateau, noise, stress, or reference result is inferred from this command.
