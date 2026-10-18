# Mobile Native performance producer

The consumer links the common five-family fixture for each selected mobile
Native target. `portableMobileBuildInventory` records the committed source,
resolved staged `dyn4k-core` and `dyn4k` target KLIBs, compiler mode, linked
executable, and package bytes. Apple targets produce a `.app` with a native
executable and `Info.plist`. Simulator packages receive an ad hoc signature.
Android Native targets produce a device executable. The Java baseline stays
on JVM.

Run from the repository root with JDK 21, Gradle 9.5.0, KGP 2.4.20, a
home-backed `TMPDIR`, and the matching platform toolchain. Stage both target
publications and both Kotlin Multiplatform publications from the same commit.
For `androidNativeArm64`, use:

```sh
export JAVA_HOME=/path/to/cached/jdk21
export TMPDIR=/home/runner/tmp
export JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=$TMPDIR"
GRADLE=/path/to/cached/gradle-9.5.0/bin/gradle
"$GRADLE" --offline \
  :dyn4k-core:publishAndroidNativeArm64PublicationToStagingRepository \
  :dyn4k:publishAndroidNativeArm64PublicationToStagingRepository \
  :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository \
  :dyn4k:publishKotlinMultiplatformPublicationToStagingRepository
STAGED_REPO_URI="file://$PWD/build/staging-repository"
"$GRADLE" -p consumers/performance/portable --offline --rerun-tasks \
  -PperformanceRepository="$STAGED_REPO_URI" \
  -PportableMobileTarget=androidNativeArm64 -PportableMobileBuild=development \
  portableMobileBuildInventory
```

Repeat with `androidNativeArm32`, `androidNativeX86`, or `androidNativeX64`.
Select `optimized` for the release link. The inventory task fails if the
selected link skips or its executable is absent. Commit the producer before
writing an inventory. The staged artifacts need their own publication receipt
to prove their source provenance.

Use a task-owned ADB server port of at least 5040 and a task-owned device
serial. The capture rejects port 5038 and `emulator-5558`, which are leased
to the ART producer. Select a guest whose primary ABI matches the target.

```sh
python3 -B tools/performance/sustained_portable/mobile_capture.py \
  --inventory "$PWD/consumers/performance/portable/build/portable-inventory/androidNativeArm64-development.json" \
  --target androidNativeArm64 --build development \
  --scenario separated.default.small.30hz.direct_kotlin \
  --adb /absolute/path/to/cached/adb --adb-port 5049 --serial emulator-5570 \
  --archive /absolute/new/archive/android-native-direct --steps 30 --warmup 3
```

Repeat with the compatibility scenario and a new archive. The launcher checks
ELF class and machine, guest ABI and API, installed bytes, `/proc/<pid>/exe`,
PID, host monotonic interval, linked identity, clocks, activity, reset, and
completion. It retains raw files and an `unpassed` result on failure.

On macOS, select one of `iosSimulatorArm64`, `iosX64`,
`tvosSimulatorArm64`, or `watchosSimulatorArm64`. Stage the corresponding
target publications with the same task names. Build the package with the
same consumer command, replacing the target. Choose a booted simulator UDID
from `xcrun simctl list -j devices available`. Use an ARM64 Mac for the
ARM64 simulators and an x86_64 Mac for `iosX64`.

```sh
python3 -B tools/performance/sustained_portable/mobile_capture.py \
  --inventory "$PWD/consumers/performance/portable/build/portable-inventory/iosSimulatorArm64-development.json" \
  --target iosSimulatorArm64 --build development \
  --scenario separated.default.small.30hz.direct_kotlin \
  --udid SELECTED_BOOTED_SIMULATOR_UDID \
  --archive /absolute/new/archive/ios-native-direct --steps 30 --warmup 3
```

The launcher checks Xcode 26.4.1, host architecture, simulator family, app
installation, installed image bytes, observed `proc_pidpath`, PID, monotonic
interval, and the fixture protocol. A missing process observation fails the
capture. Physical `iosArm64`, `tvosArm64`, `watchosArm64`, and
`watchosDeviceArm64` app builds preserve source scope. Device deployment
requires a selected physical device and signing identity. Their runtime
qualification remains unpassed until a matching signed launch is observed.

A valid short capture still has `qualification: unpassed`. It does not prove
the 600-second sustained run, reference memory, allocation, plateau, noise,
stress, optimized build, or performance budgets.
