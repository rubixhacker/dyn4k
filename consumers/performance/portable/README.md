# Portable sustained candidate producer

This staged consumer resolves the published `dyn4k` and `dyn4k-core` artifacts.
Its common fixture covers each family, size, rate, variant, and direct or
compatibility API in the [frozen performance manifest](../../../docs/research/performance-manifest-v1.json).
The compatibility route uses the `org.dyn4j` API on the same engine. The
direct route uses Kotlin conveniences. The Java baseline is a JVM-only process.

The executable emits same-process provider, construction, warm-up clock,
fixture reset, measured clock, activity, and run records. The public
[`capture.py`](../../../tools/performance/sustained_portable/capture.py) launcher
selects a manifest scenario and records the exact staged inputs, observed
process image, PID, command, runtime bundle hashes, raw exit, raw bytes, and parsed streams.
It retains raw output if the producer fails. Use one new absolute archive
directory for each process.

`generatePortableIdentity` compiles the committed source SHA and producer Git
tree into the executable. After a clean commit, `portableBuildInventory`
records source file hashes, Gradle-resolved compile artifacts, and bundle
hashes for the four available host executables. Launchers require that receipt
and compare it with current files. The runtime `LINK` marker is checked against
the inventory independently of the command-line provider challenge. Browser
captures also record the exact provider bundle files served to Chrome. The
staged engine artifacts still need their own source-to-publication receipt;
the current inventory verifies the bytes selected for this consumer build.

JS takes selected arguments from Node. Wasm JS reads them from Node or
`globalThis.DYN4K_ARGS` in a browser harness. Wasm WASI reads one framed
stdin line because KGP 2.4.20 passed an empty array to its `main(args)`
on this host. The launcher records the exact stdin bytes and hash.
The provider echoes the launcher's staged hashes; that record alone cannot
establish loaded origin. The build inventory, embedded source/tree marker,
selected bundle hashes, and available host image/resource observations are
separate evidence. Browser process identity remains unobserved through Flatpak.

The portable pacing loop uses the common monotonic clock. JS and Wasm JS use
real timers to yield between steps; native and WASI wait locally. Every run
records a positive 64-sample monotonic resolution probe before construction.
The browser controller waits for an explicit final marker without virtual time.
This short route proves producer protocol and runtime execution.
It does not validate reference load, timer overhead, admissible noise,
long-run convergence, or an optimized production build. Allocation and
retained-memory attribution, collection data, and plateau streams have no
portable producer yet. The archive labels each of those requirements missing.
No capture from this module is a performance pass.

The project declares the common producer for JVM, Android JVM, JS, Wasm JS, Wasm
WASI, Linux, Windows, Apple, and Android Native Kotlin targets. This does not claim
execution on unavailable targets or provide an Android JVM application shell.
Each target still needs its staged artifacts, runtime host, and full
qualification evidence.
