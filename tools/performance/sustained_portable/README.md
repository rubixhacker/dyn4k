# Portable process capture

Run `capture.py` with a manifest scenario whose API is `direct_kotlin` or
`compatibility`. Supply the absolute runtime, executable harness entry,
staged `dyn4k-core` and `dyn4k` target artifacts, current source SHA,
build configuration, warm-up steps, and measured steps. Use a new absolute
archive directory. The command's `--help` lists every argument.

The launcher accepts JS, Wasm JS, and Wasm WASI through Node, plus a Linux
x64 ELF process. It hashes all files adjacent to the harness entry, including
Wasm binaries, before launch. On Linux it reads `/proc/<pid>/exe` and
compares that image with the selected runtime. The archive contains the
raw streams, exit code, PID, monotonic host times, input hashes, provider
response, clocks, fixture reset, and activity. Invalid or incomplete output
leaves the raw archive and exits nonzero.

`browser_smoke.py` accepts JS or Wasm JS with an installed Flatpak Chrome.
It serves the built bundle from a local HTTP server and keeps the returned
DOM, browser stderr, page, staged hashes, and Flatpak binary identity. The
Flatpak wrapper does not expose a trusted browser process-image receipt.
An incomplete browser module run is unpassed and retains its raw output.
For Wasm JS, a one-step zero-warm-up protocol check uses Chrome virtual
time. Longer browser pacing remains unverified on this host.

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
