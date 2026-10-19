# Local Apple simulator short capture

Run Apple simulator captures on the installed local Mac over SSH with Xcode
26.5. Do not dispatch the GitHub-hosted macOS workflow. Select a clean source
commit, stage both modules' publications from that commit, and follow the
[mobile Native capture guide](mobile-native.md). Set
`DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` for the task.

Select one target and build mode per capture: `iosSimulatorArm64`,
`tvosSimulatorArm64`, `watchosSimulatorArm64`, or `iosX64`; then `development`
or `optimized`. The local ARM64 Mac cannot establish the `iosX64` runtime.
A missing tvOS simulator or physical device remains unavailable until a
matching runtime is observed. These platform runtime requirements are
separate from the Xcode 26.5 toolchain pin.

Run the direct Kotlin and compatibility scenarios in separate archives. Each
short capture uses 3 warmup and 30 measured steps. Retain raw setup streams,
inventories, capture streams, and failure receipts. A failed route remains
failed. A valid short capture remains `qualification: unpassed`; it does not
establish the 600-second calibration, reference, memory, allocation, stress,
device, or performance-budget gates.
