# Hosted Apple simulator short capture

Dispatch `performance-mobile-short.yml` on the selected source commit.
Choose one target and one build mode per run. The four targets are
`iosSimulatorArm64`, `tvosSimulatorArm64`, `watchosSimulatorArm64`, and
`iosX64`. Run both `development` and `optimized` for each available target.
The x64 iOS route uses `macos-26-intel`; the other routes use `macos-26`.

The workflow checks out `GITHUB_SHA` and selects Xcode 26.4.1. It stages
both modules' target and root publications from that checkout. It then builds
the consumer inventory for the selected target and mode. It records the host,
toolchains, simulator runtime, and selected UDID before capture.

Each dispatch runs the direct Kotlin and compatibility scenarios separately.
Each capture uses 3 warmup and 30 measured steps. Download the run's raw
artifact for staging and build logs, setup streams, inventories, capture
streams, and failure receipts. A failed route remains failed; retain its raw
artifact for diagnosis. The launcher keeps source, installed package, and
observed process image checks intact.

The route has no push trigger. The coordinator must integrate the workflow on
`main` and dispatch each selected route before any hosted result exists.
Even a valid short capture remains `qualification: unpassed`. The route does
not run the 600-second sustained calibration or establish a reference,
memory, allocation, stress, device, or performance-budget result. The Java
baseline remains a JVM-only comparison.
