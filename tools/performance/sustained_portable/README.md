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

The launcher accepts JS, Wasm JS, and Wasm WASI through Node, plus a Linux
x64 ELF process. It hashes all files adjacent to the harness entry, including
Wasm binaries, before launch. On Linux it reads `/proc/<pid>/exe` and
compares that image with the selected runtime. The archive contains the
raw streams, exit code, PID, monotonic host times, input hashes, linked identity,
positive clock calibration, fixture reset, and activity. Invalid or incomplete output
leaves the raw archive and exits nonzero.

`browser_smoke.py` accepts JS or Wasm JS with an installed Flatpak Chrome.
The local server waits under real wall time for the page to post its final
`COMPLETE` record, then archives the posted raw stream, exact files served,
wrapper output, page, inventory, staged hashes, and Flatpak binary identity.
The controller terminates the wrapper after receipt, so its recorded exit is
a controlled stop. The Flatpak wrapper does not expose a trusted browser
process-image receipt. Incomplete or rejected browser runs retain their raw
archives. Earlier virtual-clock failures are preserved.

Wasm WASI receives the fixed launch fields on one tab-delimited stdin line.
The archive retains that line. The other targets receive the fields as
command arguments. No Java baseline is launched for these targets.

Run the focused adverse controls with:

```sh
python3 -m unittest discover -s tools/performance/sustained_portable -p 'test_*.py' -v
```

The capture result is always `qualification: unpassed`. This module only
accepts timing mode. A short run checks
the producer protocol and host process only. Memory attribution, allocation
stream, plateau, approved noise and stress ceilings, reference environment,
optimized build, and sustained durations remain separate open requirements.
