# Full staged Wasm consumers on Node.js and Wasmtime

The full staged Wasm consumer checks the original 2,523 portable methods through
an external Gradle project. It resolves both `dyn4k-core` and `dyn4k` from a
separate Maven stage. It compiles the original common test sources against those
publications. The test compilation uses the staged KLIB as a friend so existing
internal tests retain their intended access.

The route covers 12 approved lanes: Wasm JS on Node.js, and Wasm WASI on Node.js
or Wasmtime. Each runtime has minimum and current roles. Each role has
development and production configurations. The producer uses the linked test
module for the selected configuration and executes it under the selected runtime.
The Wasmtime command enables GC, exceptions, and function references.

## Capture a lane

Stage both target publications and their Kotlin Multiplatform metadata from the
exact candidate. Keep the stage, archive, build directory, and `TMPDIR` on home
storage. Set `JAVA_HOME` to JDK 21 and use Gradle 9.5.0 with KGP 2.4.20. Supply
independently audited SHA-256 values for the two target KLIBs.

```sh
export JAVA_HOME=/path/to/jdk21
export GRADLE_USER_HOME=/path/to/home/gradle-cache
export TMPDIR=/path/to/home/wasm-consumer-temp
python3 tools/qualification/full_wasm_node_consumer.py run \
  --repository /path/to/exact/checkout \
  --candidate-sha "$CANDIDATE_SHA" \
  --lane 'wasmJs:Node.js:current:development' \
  --staging /path/to/independent/maven-stage \
  --output /path/to/home/empty/raw-archive \
  --gradle /path/to/gradle-9.5.0/bin/gradle \
  --runtime /path/to/selected/node \
  --expected-core-sha256 "$CORE_WASM_JS_KLIB_SHA256" \
  --expected-facade-sha256 "$FACADE_WASM_JS_KLIB_SHA256"
```

Change the lane, runtime executable, and target hashes for each route. The
candidate runtime pins selected on 2026-10-18 are Node.js 22.23.3 for minimum
Wasm JS, Node.js 24.22.0 for minimum Wasm WASI, and Node.js 26.12.0 for both
current Node routes. Wasmtime uses 37.0.3 for minimum and 49.0.3 for current.
These follow the approved latest maintenance patch and newest stable policy.
Recheck them for a later candidate. The [Node.js 22.23.3](https://nodejs.org/en/blog/release/v22.23.3),
[24.22.0](https://nodejs.org/en/blog/release/v24.22.0), and
[26.12.0](https://nodejs.org/en/blog/release/v26.12.0) release records and the
[Wasmtime 37.0.3](https://github.com/bytecodealliance/wasmtime/releases/tag/v37.0.3)
and [49.0.3](https://github.com/bytecodealliance/wasmtime/releases/tag/v49.0.3)
releases identify the selected versions.

An absent selected executable returns `NOT_RUN`. A wrong version or an attempted
build or test failure returns `FAILED`. The producer leaves each failed attempt
in its output directory. An older binary that executes every method is useful
diagnostic evidence. It does not pass the approved minimum or current role.

The archive contains the original source inventory and approved method order,
both target KLIBs, the compile and runtime provider graphs, raw Gradle output,
the complete linked module bundles, each selected executable's process record,
raw TeamCity test events, and XML derived from those events. The receipt records
the candidate commit, Git tree, original source hashes, artifact hashes, exact
route, runtime version and executable hash, process windows, and every archive
file hash. The core has 2,465 selected methods. The facade has 58.

## Replay a captured lane

An independent auditor computes the archive digest from its transported bytes.
The digest is a SHA-256 of canonical JSON mapping each relative file path to its
size and SHA-256. `archive_digest()` in the public verifier computes this value.
Pass that independently recorded value, the same two audited target hashes, and
an independently selected runtime executable to the verifier.

```sh
python3 tools/qualification/full_wasm_node_consumer.py verify \
  --repository /path/to/exact/checkout \
  --candidate-sha "$CANDIDATE_SHA" \
  --lane 'wasmJs:Node.js:current:development' \
  --archive /path/to/transported/raw-archive \
  --expected-archive-digest "$AUDITED_ARCHIVE_DIGEST" \
  --runtime /path/to/selected/node \
  --expected-core-sha256 "$CORE_WASM_JS_KLIB_SHA256" \
  --expected-facade-sha256 "$FACADE_WASM_JS_KLIB_SHA256" \
  --replay
```

`--replay` executes both retained bundles again from the transported archive.
Omitting it returns `NOT_RUN`; a static archive inspection cannot pass this
route. The selected runtime must pass the exact version and byte identity check
before execution. Archive inventory rejects symbolic paths, external hardlinks,
and nonregular files before reading their bytes.
The verifier checks the raw event order and outcomes against every selected
method, checks the normalized XML against those same raw events, and compares
the replay order. It rejects changed source, provider, binary, process, event,
or bundle bytes. Absolute paths in the original process record remain evidence
of the capture location; the archive itself can move to another directory.

This route qualifies only the staged consumer gate. Numerical, physical,
publication, duplicate-provider, and independent review gates retain their own
evidence requirements. The generic signed gate will be wired by its integration
owner after review of this producer and public verifier.
