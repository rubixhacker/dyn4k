# Hosted Native host short captures

Dispatch `Native host short performance producer` manually for one target and
one build mode. Select `macosArm64` for `macos-26` or `mingwX64` for
`windows-2025`. Select `development` or `optimized`. Each dispatch stages the
selected target and root publications from `GITHUB_SHA`, then builds a consumer
inventory from that staged repository. The job runs the direct Kotlin and
compatibility scenarios with 3 warm-up steps and 30 measured steps each.

Download the `performance-native-host-short-*` artifact even when the job
fails. `route-result.json` names every command and scenario result. The
`setup/`, `stage/`, and `build/` directories retain complete command output,
exit status, host toolchains, staged publication receipt, and selected
executable and artifact identities. `captures/` retains each API's raw process
archive, stdout, stderr, exit status, and capture receipt. The staged
repository is uploaded with the route evidence.

Each command writes stdout and stderr directly to files. On a deadline, the
runner terminates its POSIX process group or uses Windows `taskkill /T /F` for
the command tree. This includes Gradle started by the staging helper. The
command receipt records the deadline and termination result. Treat
`deadline_tree_unverified` as a failed cleanup observation.

The capture adapter gets its source SHA, executable runtime and harness, and
both artifact identities from the exact consumer inventory. It does not use a
Java baseline on these Native hosts. A missing executable or publication fails
before capture. A failed direct capture does not suppress the compatibility
attempt.

Read a macOS or Windows `observed_image.identity_kind` value of
`reported_path_only` as a path observation. It is not mapped executable byte
proof. Until the Native adapter can verify the running image on the real host,
the capture must exit unpassed. A valid short protocol also leaves sustained
performance, memory, allocation, reference, and release qualification open.
