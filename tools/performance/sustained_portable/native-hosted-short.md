# Hosted Native host short captures

Dispatch `Native host short performance producer` manually for one target and
one build mode. Select `macosArm64` for `macos-26` or `mingwX64` for
`windows-2025`. Select `development` or `optimized`. Each dispatch stages the
selected target and root publications from `GITHUB_SHA`, then builds a consumer
inventory from that staged repository. The job runs the direct Kotlin and
compatibility scenarios with 3 warm-up steps and 30 measured steps each.
The workflow invokes the tracked `native_hosted_short_runner.py` from its
checked-out workspace. The runner checks the checkout SHA, its own path, and
worktree status before staging. Its command and failure receipts stay in the
uploaded artifact. The short workflow keeps its run expression below the
hosted parser limit.

Download the `performance-native-host-short-*` artifact even when the job
fails. `route-result.json` names every command and scenario result. The
`setup/`, `stage/`, and `build/` directories retain complete command output,
exit status, host toolchains, staged publication receipt, and selected
executable and artifact identities. `captures/` retains each API's raw process
archive, stdout, stderr, exit status, and capture receipt. The staged
repository is uploaded with the route evidence.

The workflow also runs `native_host_capture.py --mode memory` as a separate
bounded process for each API. Memory archives live at
`captures/memory/direct_kotlin/` and `captures/memory/compatibility/`.
Their `execution.json` and `capture.json` retain the selected PID, mapped
executable observation, exit, raw stream hashes, and input identities.
`stdout.raw` and `stderr.raw` retain producer bytes. `rss.json` and `rss.csv`
retain live resident-byte samples or probe errors. `heap.csv` retains the
three validated post-collection managed heap checkpoints. The route result
reports each memory status as `observed_diagnostic`,
`unavailable_or_partial`, or `failed`. It reads JSON and CSV snapshots within
an 8 MiB bound and checks retained hashes before reporting a positive diagnostic.
A probe failure or incomplete sidecar gets an unpassed failure receipt, and
the other API still runs.
Timing results remain in `scenarios`; memory results are in
`memory_scenarios`. If staging fails, neither capture starts.

Each command writes stdout and stderr directly to files. On a POSIX deadline,
the runner stops the wrapper group, finds descendants across sessions, kills
them, and checks the observed PIDs. Windows uses bounded `taskkill /T /F`.
This includes Gradle started by the staging helper. The Native helper writes
child raw streams from launch and bounds process-image observation. A failed
capture also gets an unpassed workflow receipt. The hash reads at most the
initial file size plus one byte, capped at 64 MiB plus one byte. A changing,
oversized, or unreadable raw file has no trusted hash and remains on disk.
Treat `deadline_tree_unverified` or `raw_collection: incomplete` as missing
proof.

The capture adapter gets its source SHA, executable runtime and harness, and
both artifact identities from the exact consumer inventory. It does not use a
Java baseline on these Native hosts. A missing executable or publication fails
before capture. A failed direct capture does not suppress the compatibility
attempt.

The observer can report `mapped_executable_vnode` on macOS and
`mapped_executable_code` on Windows. Capture validation accepts these identity
kinds when they match the selected executable. A `reported_path_only` value
records a path; capture validation rejects it as process-image proof. These
observation routes do not establish a sustained performance pass. The policy
still has 0 of 28 validated sustained reference environments. Short memory
captures do not establish allocation attribution, a post-cycle plateau,
sustained duration, or a reference performance pass. Timing-only archives
carry no memory result. Release qualification remains open.
