# Full staged physical Apple device consumer

This route covers the 16 approved physical Apple lanes. It selects one exact
`iosArm64`, `tvosArm64`, `watchosArm64`, or `watchosDeviceArm64` lane. Each target
has minimum and current OS roles with `debug-g` and `optimized-opt` builds.
`matrix` prints the exact lane IDs from the approved complete suite manifest.

The external Gradle project resolves both staged target KLIBs by their Maven
coordinates. It checks their bytes against independently supplied SHA-256
values. It compiles the original portable test sources from the exact candidate
as friends of the resolved KLIBs. Gradle links a native test executable for
each module in the selected debug or release mode. The producer packages the
executables into signed test apps, installs them on the selected physical
device, and launches the Kotlin/Native test runner with CoreDevice console
capture. This signed native app is the test host; its original method events
come from the device process. A link result or simulator run is not a physical
qualification result.

The external project also compiles one image proof test per host. That test
copies its running executable into its app data container. The producer reads
the copy back with `devicectl` and compares its SHA-256 to the signed host
binary. The raw GTest stream must contain this extra passing proof method and
all 2,523 selected methods. The normalized XML contains exactly the 2,523
selected IDs: 2,465 core and 58 facade. Failure, skip, duplicate, missing, or
foreign original methods reject replay.

## Run on a matching Mac and device

Use a clean checkout at the candidate commit. Keep `TMPDIR` and the output
outside the checkout and staging repository. Supply a provisioning profile
that admits the selected device and a real development signing identity.
The `--expected-os` value is the actual OS version reported by CoreDevice. A
minimum lane requires the approved major version: iOS 15, tvOS 15, watchOS 8
for ILP32, or watchOS 26 for LP64. A current lane requires an observed version
at or above that floor.

```sh
python3 tools/qualification/full_apple_device_consumer.py matrix --repository "$PWD"
python3 tools/qualification/full_apple_device_consumer.py run \
  --repository "$PWD" --candidate "$CANDIDATE_SHA" \
  --lane 'iosArm64:iOS physical ARM64:minimum:debug-g' \
  --staging "$STAGED_REPOSITORY" --output "$TMPDIR/dyn4k-apple-ios-min-debug" \
  --gradle "$GRADLE_9_5_0" --java-home "$JDK_21" \
  --gradle-home "$GRADLE_USER_HOME" \
  --udid "$PHYSICAL_DEVICE_UDID" --model "$DEVICE_PRODUCT_TYPE" \
  --expected-os "$DEVICE_OS_VERSION" \
  --signing-identity "$APPLE_DEVELOPMENT_IDENTITY" \
  --provisioning-profile "$DEVICE_PROVISIONING_PROFILE" \
  --core-sha256 "$AUDITED_TARGET_CORE_KLIB_SHA256" \
  --facade-sha256 "$AUDITED_TARGET_FACADE_KLIB_SHA256"
```

The pinned toolchain is JDK 21, Gradle 9.5.0, Kotlin plugin 2.4.20, and Xcode
26.4.1. If no physical device UDID/model, matching ARM64 Mac, Xcode, or signing
inputs are available, `run` writes an `UNAVAILABLE` receipt with
`execution: NOT_RUN`. It does not write a passing lane. Keep a failed attempt
archive for diagnosis; do not change its receipt into a pass.

## Public replay

The producer prints the archive digest. A separate auditor supplies that
digest, exact candidate, both staged target KLIB hashes, observed runtime
identity, and toolchain JSON. The runtime identity format is
`<product type> | <OS> <version> | <UDID>`.

```sh
python3 tools/qualification/full_apple_device_consumer.py verify \
  --repository "$PWD" --candidate "$CANDIDATE_SHA" \
  --lane 'iosArm64:iOS physical ARM64:minimum:debug-g' \
  --archive "$TMPDIR/dyn4k-apple-ios-min-debug" \
  --archive-sha256 "$INDEPENDENT_ARCHIVE_SHA256" \
  --core-sha256 "$AUDITED_TARGET_CORE_KLIB_SHA256" \
  --facade-sha256 "$AUDITED_TARGET_FACADE_KLIB_SHA256" \
  --runtime-identity "$AUDITED_DEVICE_RUNTIME_IDENTITY" \
  --toolchain-json "$AUDITED_TOOLCHAIN_JSON"
```

Replay checks the original CoreDevice device listing, model, UDID, OS,
physical reality, CPU ABI, installation URL, launched process image and PID,
signed bundle bytes, device readback hash, source tree, external project,
provider graph, resolved staged KLIBs, original GTest events, XML, and file
inventory. A changed archive digest rejects replay before parsing its receipt.
The public verifier is separate from the integration owner's generic gate and
signed adapter wiring. A public replay result alone does not pass the full
release candidate.

This Linux worktree cannot execute or validate Xcode packaging, provisioning,
watchOS installation, or physical test runtime. Those checks remain
`UNAVAILABLE` and `NOT_RUN` until run on matching devices. A hosted simulator
may rehearse the adapter mechanics but cannot qualify a physical lane.

Apple documents [device deployment](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices)
and [CoreDevice console launch](https://developer.apple.com/documentation/xcode-release-notes/xcode-16-release-notes).
The [Kotlin target guide](https://kotlinlang.org/docs/native-target-support.html)
describes the Apple target architecture and host requirements.
