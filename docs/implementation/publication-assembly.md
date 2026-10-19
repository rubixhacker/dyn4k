# Staged publication assembly

The staged Maven repository contains both `dyn4k-core` and `dyn4k` at one version.
Each module has a root publication and one publication for each of the 21 targets.
The root Gradle metadata maps every target to its platform publication.

Each publication must contain a POM, Gradle metadata, a binary, sources, API documentation, and the repository license.
Gradle publishes an SHA-256 sidecar for each file.
The documentation jar contains Dokka HTML pages and uses the `javadoc` classifier.
JVM binaries use `.jar`; Android JVM uses `.aar`; JS, Wasm, and Native binaries use `.klib`.
The JS and Wasm publications are Kotlin library artifacts, not Java jars.

`tools/qualification/stage.py` runs explicit publication tasks for one exact candidate commit.
It records the exact Gradle command, console, task list, exit status, and console digest.
`qualify.py audit-staging` checks the receipt and the exact staged file names and bytes.
For local staging, receipt verification binds the recorded repository to the resolved Git checkout.
It rejects traversal, POSIX double slashes, and Windows components with trailing dots or spaces.
`PureWindowsPath` keeps the UNC server and share in its [anchor](https://docs.python.org/3.14/library/pathlib.html#pathlib.PurePath.anchor).
Microsoft defines both as [path components](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-dfsc/149a3039-98ce-491a-9268-2f5ddef08192).
Windows naming guidance advises against [trailing dots or spaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file) in path names.
`publication.py package` retains the staged repository, license, audit, and a complete file digest list.
`publication.py verify` requires a trusted manifest SHA-256 recorded outside the downloaded
bundle. It checks the downloaded bytes and counts against that digest.
The external digest proves bundle bytes, not the producer's repository identity.
Downloaded verification has no independent origin identity by default.
When origin identity is available, pass that trusted checkout path to the receipt validator.
The audit computes the expected Gradle variant set, target coordinates, selection attributes,
file URLs, direct dependency graph, and Kotlin version from the approved publication contract.
It requires Gradle metadata format `1.1` and compares every referenced file's size, SHA-512,
SHA-256, SHA-1, and MD5 with its staged bytes. The POM check compares the complete approved
dependency fields, including scope, and rejects unapproved optionality, type, classifier,
exclusions, and other dependency fields. It also requires the exact published POM root
sections and packaging. Profiles, parents, dependency management, and properties can change
the effective Maven dependency graph. The audit rejects these and other unapproved sections
even when the approved direct dependency remains.
For both modules on every target, the POM pins the generated name, description, project URL,
and BSD 3-Clause license name and URL. It also pins the developer ID and name and the SCM URL.
Each section must have exactly the approved children and values. Empty, duplicate, changed, or unsupported
nested fields fail the audit; the current Gradle output has no license distribution field.
XML comments do not change the POM metadata contract.

The audit reads the exact candidate's tracked source tree and compares every source JAR entry
and source byte, including notices in the source files. It compares the root documentation
JAR's pages with generated Dokka output. It compares its embedded license with the repository
license. Every target documentation JAR must have the same bytes as the root JAR.
For Apple targets, it opens the metadata JAR and checks its manifest.
It then checks the associated KLIB's manifest, linkdata,
and IR metadata structure. The audit records the source and documentation content contract
for downloaded verification. That record is trusted only after the bundle manifest digest
has been pinned outside the bundle.

Every published JVM binary JAR must contain `META-INF/LICENSE.md` with bytes equal to the
repository `LICENSE.md`. The same check runs when a downloaded bundle is verified, including
when its descriptor hashes, sidecars, audit, and manifest have been refreshed together.

Apple target metadata JARs are included in the audit and downloaded bundle because their
Gradle variants reference them. A refreshed sidecar, audit, and bundle manifest cannot make
an invalid variant reference valid under the trusted external digest.
Keep the trusted manifest digest with the exact candidate evidence before transferring a bundle.

The Linux job cross compiles and stages all 21 targets.
The installed local Mac stages nine Apple targets with Xcode 26.5.
The hosted Windows job stages Windows x64.
Each job publishes both modules and the root coordinates for its selected targets.
Their audits apply to the targets selected on that host.
The full 112-lane runtime matrix remains separate from publication staging.

Stage completion proves that the selected host produced and audited artifact bytes.
It does not prove execution on a physical device, minimum runtime, or sustained performance.
Record failed or unavailable local Mac and Windows jobs as failed or not run until their raw bundles pass verification.
The current workflow does not run the complete unchanged Java corpus on Java 8 and 21.
It also lacks strict API, extension, and static-import archive checks for JVM and Android.
Those checks require the separately reviewed strict verifier before they can pass CI.
After integration, add CI steps to compile and execute the unchanged corpus against staged
JVM GAVs under both JDKs. Invoke the strict verifier against staged JVM and Android archives.
Require checks for required and added public/protected API members, plus permanent extension
and static-import probes. Bind each result to the exact candidate SHA.
Fail the job on a missing or skipped control.
