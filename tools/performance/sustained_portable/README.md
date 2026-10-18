# Portable process capture

Run `capture.py` with a manifest scenario whose API is `direct_kotlin` or
`compatibility`. Supply the absolute runtime, executable harness entry,
staged `dyn4k-core` and `dyn4k` target artifacts, current source SHA,
build configuration, warm-up steps, and measured steps. Use a new absolute
archive directory. The command's `--help` lists every argument.

After a clean producer commit, run the consumer's `portableBuildInventory`
Gradle task with the pinned offline toolchain and staged repository. Pass its
`build/portable-inventory/<target>-development.json` as `--inventory` to each
launcher. Gradle records the committed producer tree and source file hashes,
resolved compilation artifacts, compiler configuration, and completed bundle
hashes. The launcher recomputes them before launch and stores the receipt
bytes. The executable's `LINK` record contains source/tree identity generated
at compilation rather than supplied by the launcher. `PROVIDER` remains a
launch challenge response, not proof of loaded code. The staged engine
artifacts' own source-build provenance needs an upstream publication receipt.

The launcher accepts JS, Wasm JS, and Wasm WASI through Node, plus Linux x64,
Linux ARM64, Windows x64, and macOS ARM64 Native processes. See the
[Native host commands](native-hosts.md). It hashes all files adjacent to the
harness entry, including Wasm binaries, before launch. On Linux it reads
`/proc/<pid>/exe`; on Windows it compares mapped PE headers and code through
`ReadProcessMemory`; on macOS it compares the mapped executable vnode with a
selected file handle through `proc_pidinfo` or a bounded `lsof` text mapping
probe. Path APIs provide diagnostics;
a failed lookup records `path: null` and `path_error` without replacing the
mapped identity check.
Each OS probe fails closed when its identity check is unavailable. The archive contains the
raw streams, exit code, PID, monotonic host times, input hashes, linked identity,
positive clock calibration, fixture reset, and activity. Invalid or incomplete output
leaves the raw archive and exits nonzero.

`browser_smoke.py` accepts JS or Wasm JS with an installed Flatpak Chrome.
The local server waits under real wall time for the page to post its final
`COMPLETE` record, then archives the posted raw stream, exact files served,
wrapper output, page, inventory, staged hashes, and Flatpak binary identity.
For each fetched bundle resource the server reads one byte snapshot, checks it
against the frozen target inventory, and sends that same snapshot. Its receipt
records every successful response and every rejection. The browser route
requires all five JS scripts, including DOM compatibility, or the Wasm entry,
binary, custom formatters, import-object, and builtins modules. An unknown
resource request or a missing required dependency rejects the capture.
The controller terminates the wrapper after receipt, so its recorded exit is
a controlled stop. On this Linux host the launcher separately observes the
live Chrome PID through its unique profile and page arguments, wrapper
ancestry, start time, and mapped `/proc/<pid>/exe` digest. For every accepted
page, bundle, and completion request, the server resolves the client TCP
socket inode to its owning process fd and records that process's ancestry to
the selected Chrome PID. It retains a pidfd for the initially observed owner
through the request and checks socket ownership, ancestry, and liveness again
while handling the request. A completion body is checked both before and after
it is read. Missing, foreign, changed, or ambiguous owners reject the request.
After server shutdown, the launcher compares the final response, origin, and
completion records with the snapshot checked at completion. Late records reject
the capture. The archive retains rejected completion bodies and errors.

These Linux `/proc` observations establish socket owner consistency at the
sample points. The receipt records this as
`http_origin_observation_scope: socket_owner_consistency_at_sampled_points`.
A shared TCP socket can leave the sender of individual bytes ambiguous. The
wrapper PID is not described as the browser image. This observation requires an
accessible Linux `/proc` TCP and fd view and does not establish browser process
identity on other hosts. Incomplete or rejected browser runs retain their raw
archives. Earlier virtual-clock failures are preserved.

Wasm WASI receives the fixed launch fields on one tab-delimited stdin line.
The archive retains that line. The other targets receive the fields as
command arguments. No Java baseline is launched for these targets.

Run the focused adverse controls with:

```sh
python3 -m unittest discover -s tools/performance/sustained_portable -p 'test_*.py' -v
```

Set `DYN4K_BROWSER_CONTROL_ARCHIVE` to a new absolute home directory when
running those tests to retain the rejected HTTP response bytes, changed
resource bytes, frozen inventory hashes, and rejection records for the
omitted-import, lookup-to-read swap, and unknown-executable controls.

The capture result is always `qualification: unpassed`. Native hosts also
accept a separate `--mode memory` process. It retains live resident-byte
samples from the selected PID and post-collection Native heap checkpoints.
A short run checks the producer
protocol and host process. Memory attribution, allocation stream, plateau,
approved noise and stress ceilings, reference environment, optimized build,
and sustained durations remain separate open requirements.
