# Qualification harness

This harness records what ran against one staged candidate. It does not turn a build, a host probe, or an empty suite into runtime qualification. [Qualify staged artifacts on every required runtime](https://github.com/rubixhacker/dyn4k/issues/43) remains open until every required case and the independent performance and compatibility gates pass.

## What the harness checks

`tools/qualification/qualify.py matrix` emits the complete approved support matrix: 21 targets, 28 target/runtime families, and 112 cases after minimum/current and two build configurations. The configuration names correspond to the [approved support contract](https://github.com/rubixhacker/dyn4k/issues/6#issuecomment-5651793360): JVM no-optimize/default; Android debug/R8; web development/production; Native debug `-g`/optimized `-opt`. A matrix row is a requirement, not a result.

`audit-staging` checks both module roots and all target publications referenced by their Gradle metadata. It checks POM identity and descriptive metadata, target mapping, sources, API documentation and license artifacts, an embedded JAR license, and SHA-256 sidecars. It writes every observed POM, module metadata file and distributable artifact with its computed SHA-256. Any missing publication fails the audit. The current build publishes some staged artifacts but does not attach API documentation artifacts; that remains a real failure.

The external JVM consumer in `consumers/qualification/` resolves `io.github.rubixhacker:dyn4k:0.1.0-alpha.1` from the staged repository. It executes Kotlin and Java public geometry calls. Its `verifySingleProvider` task rejects a graph containing both `dyn4k-core` and upstream `org.dyn4j:dyn4j`. The portable KMP consumer in `consumers/qualification/portable/` declares every approved target and runs a common public geometry test wherever an actual staged target artifact and runtime are available. These are foundation probes. They do not claim the full geometry, collision, dynamics, joint or compatibility suite.

`probe` captures an actual Gradle command, XML test counts and exit status. A zero case count, skipped case, failure or command failure makes the probe fail. Probe output says `foundation probe only`. `execute` accepts an explicit JSON plan keyed by matrix case ID. Each plan entry supplies either `unavailable_reason`, or a command array and `result_file` for a runtime harness that writes observed evidence. Missing plans remain `NOT_RUN`. `record` evaluates all 112 cases and exits nonzero until each case passes. A lane needs a full candidate SHA, artifact SHA-256, runtime identity, positive expected count, matching executed count, zero failures and skips, a staged consumer pass, and `suite: complete`. A runtime result may include target, runtime, version and configuration; those values must match its case. An external harness must establish the minimum/current runtime pin and actual build configuration before supplying a passing record.

Statuses have distinct meanings: `PASSED` has complete evidence; `FAILED` has attempted but invalid or failing evidence; `UNAVAILABLE` names an absent runner or probe; `NOT_RUN` has no attempt. A missing device or suite never becomes a pass or a zero measurement.

## Local commands

Set JDK 21 and the Android SDK paths for this pinned build. Stage the two module roots and the target publications you can build with Gradle. Then run:

```sh
python3 -m unittest discover -s tools/qualification -p 'test_*.py' -v
./gradlew -p consumers/qualification --no-daemon run -PqualificationRepository="$PWD/build/staging-repository"
./gradlew -p consumers/qualification/portable --no-daemon jvmTest linuxX64Test -PqualificationRepository="$PWD/build/staging-repository"
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

The runtime runner must write its actual suite and consumer observations. The harness rejects missing output. The plan alone never passes a lane.

## Open qualification requirements

The current engine has a foundation suite only. Full portable correctness, exact runtime pins, both executed build configurations, physical Apple devices, Android ABI execution, browser/Safari, old Linux kernels, and Windows remain unpassed until their own observations exist. [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42) and [Freeze and validate the performance fixture and reference-environment manifest](https://github.com/rubixhacker/dyn4k/issues/17) remain independent final blockers. A host JVM or Linux run cannot establish Apple, device, or release qualification.
