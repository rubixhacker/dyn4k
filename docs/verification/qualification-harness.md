# Qualification harness

This harness records what ran against one staged candidate. It does not turn a build, a host probe, or an empty suite into runtime qualification. [Qualify staged artifacts on every required runtime](https://github.com/rubixhacker/dyn4k/issues/43) remains open until every required case and the independent performance and compatibility gates pass.

## What the harness checks

`tools/qualification/qualify.py matrix` emits the complete approved support matrix: 21 targets, 28 target/runtime families, and 112 cases after minimum/current and two build configurations. The configuration names correspond to the [approved support contract](https://github.com/rubixhacker/dyn4k/issues/6#issuecomment-5651793360): JVM no-optimize/default; Android debug/R8; web development/production; Native debug `-g`/optimized `-opt`. A matrix row is a requirement, not a result.

`audit-staging` checks both module roots and all target publications referenced by their Gradle metadata. It checks POM identity and descriptive metadata, target mapping, sources, API documentation and license artifacts, an embedded JAR license, and SHA-256 sidecars. It writes every observed POM, module metadata file and distributable artifact with its computed SHA-256. Any missing publication fails the audit. The current build publishes some staged artifacts but does not attach API documentation artifacts; that remains a real failure.

The external JVM consumer in `consumers/qualification/` resolves `io.github.rubixhacker:dyn4k:0.1.0-alpha.1` from the staged repository. It executes Kotlin and Java public geometry calls. Its `verifySingleProvider` task rejects a graph containing both `dyn4k-core` and upstream `org.dyn4j:dyn4j`. The portable KMP consumer in `consumers/qualification/portable/` declares every approved target and runs a common public geometry test wherever an actual staged target artifact and runtime are available. These are foundation probes. They do not claim the full geometry, collision, dynamics, joint or compatibility suite.

`probe` uses the tracked `tools/qualification/foundation-probes.json` manifest. Each of the six available `dyn4k` host groups pins 30 cases: seven foundation, four tree, and 19 integrated geometry cases. The six core groups declare zero cases. The JVM/Linux command therefore expects 60 cases, the JS/Wasm command expects 90, and the Android host command expects 30. Each selected report group and case identity must match the frozen manifest. Missing, renamed, duplicate, extra, skipped, failed, or non-finite cases fail. Probe results use `PROBE_PASSED` or `PROBE_FAILED` and state `foundation probe only`; they cannot become full-lane results.

`hosted.py run` adds bounded probes for macOS ARM64, iOS/tvOS/watchOS ARM64 simulators, iOS x64 simulator, Windows x64, and Safari JS. Each native route stages both module roots and its target publications, checks both staged binary checksums, runs 30 frozen library cases, then resolves the staged artifacts in an external consumer and runs its one frozen case. The Safari route enables WebDriver and uses the external JS browser test with the Karma Safari launcher through Launch Services; it requires installed Safari and SafariDriver. The hosted runner records its actual OS, architecture, runner image, Java, Gradle, declared Kotlin plugin, pinned Xcode version, and available simulator or Safari identity. A missing simulator or browser is `UNAVAILABLE`; wrong runner or toolchain identity and missing, partial, or failed reports are `PROBE_FAILED`. Hosted JSON is tied to the workflow commit. These are bounded development probes, not the complete suite or minimum-OS evidence.

The Safari manifest pins the exact case name emitted by Safari 26.6.2. Its `MacOS10.15.7` suffix comes from Safari's user agent and is not the host OS version. The host version comes from `sw_vers` in the runtime record. A future Safari reporter identity change fails until the manifest is reviewed.

`execute` accepts a JSON plan keyed by matrix case ID. Each entry supplies a command and result path, or an exact unavailability reason. Before a command, it moves any old result to a distinct `.previous-<id>` file. It gives the command `DYN4K_QUALIFICATION_INVOCATION`. The runner must write that value as `invocation_id` in a new JSON result. A no-op, failed command, stale file, wrong invocation, or invalid JSON fails execution. Missing plans remain `NOT_RUN`.

`record` evaluates all 112 cases. It requires a clean checkout at the candidate SHA, including untracked files hidden by ignore rules. The input check excludes generated `build/`, `.gradle/`, and `.kotlin/` files only under the repository root and the four Gradle project roots. It also excludes `tools/qualification/__pycache__/` and the generated `kotlin-js-store/yarn.lock` files at the repository root and in `consumers/qualification/portable/`. An untracked source, build script, or ignored `local.properties` invalidates the candidate, even if a source path contains a directory named `build`. A full pass also requires a tracked `tools/qualification/full-suite-manifest.json` with every approved case and area. That file does not exist until [the complete compatibility corpus](https://github.com/rubixhacker/dyn4k/issues/42) can freeze it. A candidate manifest must select the exact runtime identity, version, configuration, suite ID, and both target binary hashes for each lane. The result must match those selections, include every distinct frozen case, and bind the suite, candidate, and staged audit digests. The audit is recomputed against staged files before it is accepted. There is no full-lane pass while the complete suite manifest is absent.

`record --hosted-probe <json>` checks the bounded result's candidate SHA, selected runtime identity, frozen source and consumer manifest digests, exact counts, and staged target hashes. It stores the result under `bounded_hosted_probes`. It does not promote a bounded probe to a `PASSED` full lane. The macOS 26 and Windows Server 2025 jobs do not establish the approved minimum OS versions. Windows Server 2025 is not a Windows 10 client runtime. Simulator tests do not establish physical Apple device support.

Statuses have distinct meanings: `PASSED` has complete evidence; `FAILED` has attempted but invalid or failing evidence; `UNAVAILABLE` names an absent runner or probe; `NOT_RUN` has no attempt. `record --availability <json>` accepts target, `target:runtime`, `target:runtime:version`, or exact case IDs with concrete reasons. More specific selectors take priority. A missing device or suite never becomes a pass or a zero measurement.

## Local commands

Set JDK 21 and the Android SDK paths for this pinned build. Stage the two module roots and the target publications you can build with Gradle. Then run:

```sh
python3 -m unittest discover -s tools/qualification -p 'test_*.py' -v
./gradlew -p consumers/qualification --no-daemon run -PqualificationRepository="$PWD/build/staging-repository"
./gradlew -p consumers/qualification/portable --no-daemon jvmTest linuxX64Test -PqualificationRepository="$PWD/build/staging-repository"
python3 tools/qualification/qualify.py probe --candidate-sha "$(git rev-parse HEAD)" --manifest tools/qualification/foundation-probes.json --group core-jvm --group jvm --report 'dyn4k-core/build/test-results/jvmTest/TEST-*.xml' --report 'dyn4k/build/test-results/jvmTest/TEST-*.xml' --output /tmp/foundation-probe.json -- ./gradlew --no-daemon :dyn4k-core:jvmTest :dyn4k:jvmTest
python3 tools/qualification/qualify.py audit-staging --candidate-sha "$(git rev-parse HEAD)" --repository build/staging-repository --output /tmp/artifact-audit.json
python3 tools/qualification/qualify.py record --candidate-sha "$(git rev-parse HEAD)" --output /tmp/runtime-matrix.json
```

`audit-staging` and `record` are expected to exit nonzero while contract gaps remain. The dedicated CI workflow runs host foundation probes, staged consumers, the duplicate-provider diagnosis, artifact audit, and full matrix recording. It uploads JSON evidence keyed to the workflow commit. Runtime owners can use `execute` with a plan such as:

```json
{
  "jvm:Java:minimum:default": {
    "command": ["/path/to/jdk8/bin/java", "-jar", "/path/to/complete-suite-runner.jar"],
    "result_file": "/path/to/observed-result.json"
  }
}
```

The runtime runner must write `invocation_id` from its environment, actual case and consumer observations, and the selected manifest and artifact digests. The plan alone never passes a lane. The exact full-lane JSON schema is exercised in `tools/qualification/test_qualify.py`; the production gate will not accept a synthetic suite file outside the tracked candidate.

## Open qualification requirements

The current engine has a foundation suite only. Full portable correctness, exact runtime pins, both executed build configurations, physical Apple devices, Android ABI execution, browser/Safari, old Linux kernels, and Windows remain unpassed until their own observations exist. The new hosted jobs must be evaluated through their actual run logs and artifacts; runner image documentation alone is discovery. [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42) and [Freeze and validate the performance fixture and reference-environment manifest](https://github.com/rubixhacker/dyn4k/issues/17) remain independent final blockers. A host JVM or Linux run cannot establish Apple, device, or release qualification.
