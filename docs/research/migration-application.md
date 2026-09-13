# Existing Java migration application

Research for [Select an unchanged Java migration application](https://github.com/rubixhacker/dyn4k/issues/13), 2026-09-13. Recommendation, not human approval or migration acceptance.

## Candidate and immutable inputs

Recommend the first-party **dyn4j-samples** application collection at source revision **2c6b318e929baab77e9753ae78a4965eee74a30a**. Its [original POM](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/pom.xml) already depends on `org.dyn4j:dyn4j:6.0.0`, plus JOGL and GlueGen 2.3.2; no dependency substitution was needed for the baseline probe. Its [license](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/LICENSE.md) is BSD 3-Clause. It is an existing runnable consumer, not a newly constructed compatibility fixture, but human selection must explicitly accept a sample application collection as the required real application.

Downloaded Maven Central JARs and observed SHA-256:

| Artifact | SHA-256 |
| --- | --- |
| [dyn4j 6.0.0](https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/6.0.0/dyn4j-6.0.0.jar) | `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e` |
| [jogl-all 2.3.2](https://repo.maven.apache.org/maven2/org/jogamp/jogl/jogl-all/2.3.2/jogl-all-2.3.2.jar) | `e74603dc77b4183f108480279dbbf7fed3ac206069478636406c1fb45e83b31a` |
| [gluegen-rt 2.3.2](https://repo.maven.apache.org/maven2/org/jogamp/gluegen/gluegen-rt/2.3.2/gluegen-rt-2.3.2.jar) | `084844543b18f7ff71b4c0437852bd22f0cb68d7e44c2c611c1bbea76f8c6fdf` |

All 42 tracked Java source files remained unchanged. The SHA-256 of the sorted relative-path/source-hash manifest was `15ce636ac8eec34b24e73bc96270b49a44c94318850050b1e9bc0d930a9c8d58` (command below). Candidate `git status --short` was empty after probes.

## Observed compile and runtime evidence

On this Bazzite host, OpenJDK `25.0.3` compiled **all 42 Java sources**, exit 0, using the three JARs above and `--release 8`. Only three obsolete source/target option warnings were emitted. This is a direct javac build probe, not a successful Maven package. Maven and Xvfb were absent from PATH. The original POM specifies compiler release 6, so reproducing the Maven build on this modern JDK needs a build-only release-level override and verification. No application Java files were changed.

An actual launch of `org.dyn4j.samples.Tracking` exited **1**, with `java.awt.HeadlessException: No X11 DISPLAY variable was set`. The stack stopped in `JFrame` construction through `SimulationFrame:133`, `Tracking:114`, `Tracking.main:223`, before world initialization. **No physics scenario ran and no GUI was observed.** This is an environment blocker, not evidence that the application or baseline physics is broken. No system service or display server was installed.

The source explains the requirement: [SimulationFrame](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/src/main/java/org/dyn4j/samples/framework/SimulationFrame.java#L76) extends JFrame; its [start path](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/src/main/java/org/dyn4j/samples/framework/SimulationFrame.java#L292) initializes the world and requires a visible canvas for its buffer strategy. A headful Java desktop/display runner is required. Restrict initial runtime journeys to Java2D scenes; the JOGL scene additionally needs native graphics dependencies and is not covered by the JAR-only compile probe.

## Proposed representative journeys

These are candidate acceptance journeys inferred from source, **not executed checks**:

| Scene | Proposed journey and evidence purpose |
| --- | --- |
| [Tracking](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/src/main/java/org/dyn4j/samples/Tracking.java) | Run contacts through begin/persist/end, observe console events and absence of its `Shouldn't happen` diagnostics; exercises custom listener overrides and contact data. |
| [Pyramid](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/src/main/java/org/dyn4j/samples/Pyramid.java) | Run the initialized stack, manipulate bodies and reset; contact stacking and interactive world lifecycle. |
| [Crank](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/src/main/java/org/dyn4j/samples/Crank.java) | Observe driven mechanism motion; revolute/prismatic joints. |
| [Billiards](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/src/main/java/org/dyn4j/samples/Billiards.java#L177) | Shoot the cue ball and observe ball collisions/settling; bullet flags explicitly set on balls, making it a candidate CCD journey. Pin an input script and verify actual CCD exercise before counting CCD coverage. |
| [Truck](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/src/main/java/org/dyn4j/samples/Truck.java) | Drive, brake and manipulate suspension/cargo; wheel joints and compound fixtures. Its initialization explicitly disables CCD, so it cannot supply CCD evidence. |

The shared [SimulationBody](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/src/main/java/org/dyn4j/samples/framework/SimulationBody.java#L42) subclasses dyn4j Body, adding a concrete inheritance consumer to these journeys.

## Limits and decision still required

Select this pinned sample collection only with human approval. Then obtain a successful baseline run on a headful runner, with named journeys, scripted inputs, observations, logs and source manifests. Repeat against the eventual shim with identical Java sources and only dependency/build changes. No shim exists in this planning checkout, so neither migration execution nor parity is established.

This candidate cannot replace exhaustive declaration/test inventories, mixed Kotlin/shim identity checks, all-target coverage, or calibrated numerical fixtures. Its [game loop](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/src/main/java/org/dyn4j/samples/framework/SimulationFrame.java#L345) uses wall-clock elapsed time; screenshots alone cannot prove numerical parity. Some scenes also randomize physical inputs (for example [Platformer](https://github.com/dyn4j/dyn4j-samples/blob/2c6b318e929baab77e9753ae78a4965eee74a30a/src/main/java/org/dyn4j/samples/Platformer.java#L121)). Deterministic fixtures remain separate. Do not edit these application Java sources to make a migration check easier. No broader third-party candidate search was needed after finding an existing first-party 6.0.0 consumer; this is not a claim that it is uniquely suitable or exhaustive.

## Reproduction and retained local probe paths

Candidate checkout: `/tmp/dyn4j-migration-candidate`; probe directory: `/tmp/dyn4j-migration-probe`. These are disposable local artifacts, not durable public evidence. The observations and commands in this report are retained on the research branch.

After cloning the pinned source into the candidate directory and downloading the linked JARs into the probe `lib` directory:

```bash
git checkout --detach 2c6b318e929baab77e9753ae78a4965eee74a30a
mkdir -p /tmp/dyn4j-migration-probe/classes
rg --files src/main/java -g '*.java' > /tmp/dyn4j-migration-probe/sources.txt
javac --release 8 -cp '/tmp/dyn4j-migration-probe/lib/*' -d /tmp/dyn4j-migration-probe/classes @/tmp/dyn4j-migration-probe/sources.txt
java -cp '/tmp/dyn4j-migration-probe/classes:/tmp/dyn4j-migration-probe/lib/*:src/main/java' org.dyn4j.samples.Tracking
git ls-files '*.java' | LC_ALL=C sort | xargs sha256sum > /tmp/dyn4j-migration-probe/java-sources.sha256
sha256sum /tmp/dyn4j-migration-probe/java-sources.sha256
git status --short
```

Other Java2D scenes use the same command with the corresponding class name. The source directory on the runtime classpath preserves access to the existing image resources. A successful launch, GUI interaction, and physics observation still need to be recorded on a suitable runner.
