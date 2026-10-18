# Native host performance producer

Linux x64, Linux ARM64, Windows x64, and macOS ARM64 have Native executables.
Each process runs the common direct or compatibility fixture. The Java
comparator remains JVM-only. Short captures stay `qualification: unpassed`
even when their protocol and process checks pass.

Use a clean checkout at the selected commit. `STAGED_REPO_URI` must point to
the exact staged repository for that commit, with both `dyn4k-core` and `dyn4k`
target publications. Use JDK 21, Gradle 9.5.0, Kotlin Gradle plugin 2.4.20,
and the selected platform's Native toolchain. The selected target must link.
Missing resolved artifacts or executables fail the inventory task. Run each
command from the repository root.

If the staged repository lacks the target publications, stage them from the
same checkout before the consumer build. For `linuxArm64`, for example, run
these root tasks with the pinned Gradle command and `--offline`:

```sh
/path/to/gradle-9.5.0/bin/gradle --offline \
  :dyn4k-core:publishLinuxArm64PublicationToStagingRepository \
  :dyn4k:publishLinuxArm64PublicationToStagingRepository \
  :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository \
  :dyn4k:publishKotlinMultiplatformPublicationToStagingRepository
```

Use `MingwX64` on Windows and `MacosArm64` on macOS in the two target
publication task names. The root publication tasks write
`build/staging-repository`; pass its absolute file URI to the consumer.

## Linux x64 and Linux ARM64

Select `linuxX64` on x64 Linux or `linuxArm64` on ARM64 Linux. Kotlin Native
does not list ARM64 Linux as a supported compiler host in this project's
target research. The ARM64 KLIB and executable cross-build on x64 Linux;
the coordinator must establish a matching-host staging and receipt route
before an ARM64 runtime capture can pass this launcher's exact-path checks.

```sh
export JAVA_HOME=/path/to/jdk21
export STAGED_REPO_URI=file:///absolute/path/to/staging-repository
export STAGED_REPO_ROOT=/absolute/path/to/staging-repository
export NATIVE_TARGET=linuxArm64
export NATIVE_BUILD=development
/path/to/gradle-9.5.0/bin/gradle -p consumers/performance/portable --offline \
  -PperformanceRepository="$STAGED_REPO_URI" \
  -PportableNativeHostTarget="$NATIVE_TARGET" -PportableNativeHostBuild="$NATIVE_BUILD" \
  portableNativeHostBuildInventory
python3 -B tools/performance/sustained_portable/native_host_capture.py \
  --inventory "$PWD/consumers/performance/portable/build/portable-inventory/$NATIVE_TARGET-$NATIVE_BUILD.json" \
  --publication-root "$STAGED_REPO_ROOT" \
  --target "$NATIVE_TARGET" --build "$NATIVE_BUILD" \
  --scenario separated.default.small.30hz.direct_kotlin \
  --archive /absolute/new/archive/native-direct --steps 30 --warmup 3
```

Repeat with `separated.default.small.30hz.compatibility` and a new archive.
Use `NATIVE_BUILD=optimized` for the release executable and its inventory.
The launcher rejects a target on the wrong host architecture.

### Traced Linux x64 source and link inputs

For a Linux x64 provenance receipt, create a clean detached checkout at the
selected commit under home storage. Its four build output directories must
not exist. Run the traced builder from that checkout with the pinned offline
toolchain. Keep the trace archive and checkout together. The builder records
each exact Gradle command, JDK and tracer hash, raw syscall trace, Gradle log,
Kotlin source digests, freshly built and staged KLIB hashes, resolved link
inputs, and both executable hashes.

```sh
git worktree add --detach /home/stewart/native-source-link-checkout COMMIT
cd /home/stewart/native-source-link-checkout
export TMPDIR=/home/stewart/native-source-link-tmp
export JAVA_TOOL_OPTIONS=-Djava.io.tmpdir=/home/stewart/native-source-link-tmp
python3 -B tools/performance/sustained_portable/native_source_link.py \
  --archive /home/stewart/native-source-link-evidence \
  --gradle /tmp/dyn4k-tools/gradle-9.5.0/bin/gradle \
  --jdk /tmp/dyn4k-tools/jdk21 \
  --older-core-klib /absolute/path/to/older-valid-linux-x64-core.klib
```

The older KLIB option is an adverse control. It reseals an isolated staged
copy while leaving the current source archive intact. Pairwise publication
validation must accept the old KLIB as a selected input, and the traced
selection check must reject its provenance. The adverse copy and JSON result
remain in the evidence archive. The builder does not edit the selected staged
repository.

Pass `--source-link-receipt /home/stewart/native-source-link-evidence/source-link.json`
to `native_host_capture.py` for each short Linux x64 direct and compatibility
capture in both builds. A capture verifies the raw trace hashes and exact
selected KLIB and executable bytes before launch. It copies the receipt into
the raw process archive; the large syscall traces remain in their retained
shared archive. `source_to_link` and `qualification` remain `unpassed`:
syscall tracing and fresh output equality show the observed build chain, but
they do not cryptographically attest the compiler's internal byte transform.

## Windows x64 hosted runner

Use a PowerShell session on Windows x64. Set paths to the pinned JDK, Gradle,
checkout, staged repository, and new archive root.

```powershell
$env:JAVA_HOME = 'C:\path\to\jdk21'
$env:STAGED_REPO_URI = 'file:///C:/absolute/path/to/staging-repository'
$publicationRoot = 'C:\absolute\path\to\staging-repository'
$target = 'mingwX64'
$build = 'development'
& 'C:\path\to\gradle-9.5.0\bin\gradle.bat' -p consumers/performance/portable --offline `
  "-PperformanceRepository=$env:STAGED_REPO_URI" `
  "-PportableNativeHostTarget=$target" "-PportableNativeHostBuild=$build" `
  portableNativeHostBuildInventory
$inventory = Join-Path (Get-Location) "consumers/performance/portable/build/portable-inventory/$target-$build.json"
python -B tools/performance/sustained_portable/native_host_capture.py `
  --inventory $inventory --publication-root $publicationRoot --target $target --build $build `
  --scenario separated.default.small.30hz.direct_kotlin `
  --archive 'C:\absolute\new\archive\native-direct' --steps 30 --warmup 3
```

Repeat with the compatibility scenario and another new archive. Select
`optimized` for a release executable. Run the live path-swap control on this
host and retain its JSON receipt:

```powershell
python -B tools/performance/sustained_portable/host_image_adverse.py `
  --output 'C:\absolute\new\archive\windows-path-swap.json'
```

`QueryFullProcessImageNameW` reports the PID's path, not mapped executable
bytes. The capture retains its path and raw protocol but exits unpassed on
process-image identity even if the path-swap control succeeds. A hosted probe
must bind a live PID to an immutable executable mapping or trusted launch
handle and independently compare its bytes with the inventory.

## macOS ARM64 hosted runner

Use an ARM64 macOS runner with the selected Xcode toolchain.

```sh
export JAVA_HOME=/path/to/jdk21
export STAGED_REPO_URI=file:///absolute/path/to/staging-repository
export STAGED_REPO_ROOT=/absolute/path/to/staging-repository
export NATIVE_TARGET=macosArm64
export NATIVE_BUILD=development
/path/to/gradle-9.5.0/bin/gradle -p consumers/performance/portable --offline \
  -PperformanceRepository="$STAGED_REPO_URI" \
  -PportableNativeHostTarget="$NATIVE_TARGET" -PportableNativeHostBuild="$NATIVE_BUILD" \
  portableNativeHostBuildInventory
python3 -B tools/performance/sustained_portable/native_host_capture.py \
  --inventory "$PWD/consumers/performance/portable/build/portable-inventory/$NATIVE_TARGET-$NATIVE_BUILD.json" \
  --publication-root "$STAGED_REPO_ROOT" \
  --target "$NATIVE_TARGET" --build "$NATIVE_BUILD" \
  --scenario separated.default.small.30hz.direct_kotlin \
  --archive /absolute/new/archive/native-direct --steps 30 --warmup 3
```

Repeat for the compatibility scenario and optimized build. Run the live
path-swap control on this host and retain its JSON receipt:

```sh
python3 -B tools/performance/sustained_portable/host_image_adverse.py \
  --output /absolute/new/archive/macos-path-swap.json
```

`proc_pidpath` reports the PID's path, not mapped executable bytes. The
capture retains its path and raw protocol but exits unpassed on process-image
identity. A hosted probe must bind a live PID to an immutable mapped vnode
or equivalent trusted file handle and compare its bytes with the inventory.

## Evidence and remaining paths

`capture.py` checks committed source files, exact Native artifact coordinates,
KLIB manifests, staged publication checksums and module metadata, staged
source archives against checkout bytes, executable bundle, linked producer
identity, PID, monotonic interval, fixture reset, clocks, activity, and
completion marker. Linux reads mapped executable bytes through procfs.
Windows and macOS record only path metadata and fail closed on image identity.
The host controller has a 45-second default deadline with terminate/kill
cleanup; it retains raw stdout, stderr, stdin, inventory, publication inputs,
and process/error receipt on timeout. Linux x64 can retain a traced source
read, fresh KLIB, resolved link read, and executable chain. Its internal
compiler transformation remains unpassed. A valid short capture does not satisfy memory,
allocation, plateau, noise, sustained duration, or performance budgets.

The remaining iOS, tvOS, watchOS, and Android Native device and simulator
routes need application shells, deployment, and device process identity.
Those targets stay declared in the source and full port scope. This host
executable work does not report them as unavailable code.
