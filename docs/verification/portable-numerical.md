# Portable numerical consumer

The standalone consumer in `tools/numerical/portable` runs common Kotlin engine calls through staged `dyn4k-core` Maven publications. Its Gradle build does not include project source modules or the Java recorder. Run it from a clean commit. The runner freshly builds and hashes the metadata, JVM, Android, Linux x64, JS, Wasm JS, and Wasm WASI publications before any host task executes.

```sh
ANDROID_HOME="$HOME/Android/Sdk" python3 tools/numerical/portable/run.py \
  --output /var/tmp/dyn4k-portable-numerical-evidence
```

The runner executes JVM on Java 21 and Java 8, Android host, Linux x64, Node JS, Node Wasm JS, and Node Wasm WASI test tasks. The Java 8 lane selects the Gradle test launcher from `/tmp/dyn4k-tools/jdk8`; its receipt hashes the process Gradle actually launched. Android host execution uses a JVM. It does not qualify an Android device. The publication log and manifest bind the staged artifacts to the clean source revision. Each completed lane retains its Gradle log, raw XML, whole JSONL trace, per-case JSONL traces, SHA-256 receipt, and result. Every lane without execution gets a `NOT_RUN` or `UNAVAILABLE` receipt with zero executed cases and an unpassed qualification status.

## Recorded contract

The declaration in `cases.py` is the expected case set. The suite records every inner step, ordered step, contact, and time-of-impact callbacks, before-step actions, and configured outer endpoint copies. Endpoint copies do not advance the step or event history. Each state records body transforms, prior transforms, velocity, force, torque, rest state, energy, momentum, joint reactions, and fixed-origin position. Geometry cases also record direct SAT and GJK observations. Nonfinite values appear as tagged raw values; receipt inspection rejects them. Floating-point comparison uses binary64 bits, including the sign of zero, before any tolerance decision.

The six families are geometry/collision boundaries across scales and offsets; free motion, forces, damping, and restitution; default and separately configured contact, friction, sleep, and wake; all ten joint types with initial and active modes; circle and pentagon CCD at 30, 60, and 120 Hz; and a 600-second free-motion invariant scene. A separate 600-step Angle ratio `-1` case retains the reproduced baseline nonfinite failure while allowing other test methods to run. Default sleep/wake uses its own 30/60/120 Hz step. Configured sleep/wake uses 120 Hz inner steps and separate 4/2/1 outer endpoint groups. Its six cases include both repetitions at each outer rate.

The receipt validator rejects missing or duplicate cases, missing steps, lost callbacks, altered action steps, reordered events, changed input, changed signed zero, missing endpoints, nonfinite values, stale artifacts, and an empty suite. The receipt binds the exact Git archive hash, commit, staged metadata and target artifact hashes, runtime identity, trace hash, and expected and executed counts.

`reference_diagnostic.py` compares overlapping body channels with a frozen Java trace. It checks the frozen gzip and input hashes first, then records exact-value and signed-zero differences. It applies the approved comparator to matching channels and reports every failed budget. The result remains unpassed while the input headers, event schemas, or other required channels differ.

The physical diagnostic reuses the approved represented-geometry depth and phase schedule for default and configured sleep/wake cases. It reports all nine case counts and failed steps separately; default failures remain failures. The 36,000-step free-motion invariant is checked against its analytic limits. These diagnostics do not replace input, event, or complete-channel parity.

The runner invokes that diagnostic for every frozen reference found in `--reference-dir`, using `/tmp/dyn4k-configured-control/baseline-trace` by default. Each host gets `frozen-comparison.json` with explicit unavailable references. A missing reference, nonmatching schema, or failed approved channel never becomes a parity pass.

## Acceptance boundary

The pinned baseline is dyn4j 6.0.0 at source revision `058bf6d982a0fb89b54050f929f6ea9dae53b714` and binary SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The approved 14 reference traces use a richer Java schema and exact frozen input headers. This portable trace has its own explicit schema and declared diagnostic cases. A successful portable receipt proves that its declared cases ran and were bound to staged artifacts. It does not make the portable trace an accepted parity comparison against those frozen Java records. Preserve the exact frozen input and event checks, then apply only approved numerical limits to a matching trace. Any unmatched input, channel, case, or runtime remains unpassed.

The configured control in `/tmp/dyn4k-configured-control/result.md` is a mixed diagnostic. Its 1,025,970 matching runtime records do not qualify one coherent candidate artifact. The previous `pow` versus pinned `cbrt` default TOI input difference must be checked on the final merged source. The Angle ratio `-1` case produced `-Infinity` at step 171 with the pinned baseline alone, as recorded in `/tmp/dyn4k-angle-baseline-probe/result.json`. It remains a failed physical case and is ineligible as a finite numerical reference. Neither observation permits a trace rewrite or a wider acceptance limit.
