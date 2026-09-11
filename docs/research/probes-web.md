# JS and Wasm consumer probes

Observed 2026-09-10, Bazzite Linux x86_64. This answers part of [Probe the selected toolchain and unresolved consumer floors](https://github.com/rubixhacker/dyn4k/issues/11). These are compiler/runtime smoke probes, not dyn4k physics-suite coverage or ratified support guarantees.

## Exact artifact configuration and observed results

Retained source: [`probes/toolchain/web`](../../probes/toolchain/web). Kotlin/KGP 2.4.20, Gradle 9.5.0, Temurin build JDK 21.0.12.1+1; Binaryen actually reports `wasm-opt version 130 (version_130)`. Build succeeds for development and production. The test creates a mutable object, throws/catches a Kotlin exception, checks 42, and prints `WEB_FLOOR_OK 42`.

| Lane | Explicit output settings | Candidate minimum | Current frozen candidate | Observed execution, development AND production |
| --- | --- | --- | --- | --- |
| Plain JS / Node | `target=es5`, `moduleKind=UMD`, executable | Absolute minimum unresolved; 22.0.0 is a tested upper bound, **not** a floor | 26.8.2 | Both pass; exploratory 0.10.48 and 0.12.18 reject development JS syntax |
| wasmJs / Node | legacy EH explicitly `-Xwasm-use-new-exception-proposal=false`; generated `.mjs` loader | 22.0.0 candidate without experimental Wasm flags | 26.8.2 | Both pass |
| wasmWasi / Node | new EH explicitly `-Xwasm-use-new-exception-proposal`; generated WASI Preview 1 `.mjs` loader | 24.15.0 candidate without experimental Wasm flags | 26.8.2 | Both pass; 22.0.0 and 24.14.1 fail new-EH validation |
| wasmWasi / Wasmtime | same new-EH `.wasm`; Preview 1 | 37.0.0 **with** `-W gc=y -W exceptions=y -W function-references=y`; 47.0.0 default-enabled candidate, not executed | 48.0.2 | 37.0.0 explicit flags and 48.0.2 defaults pass |
| Plain JS / Chrome, Firefox, Safari | ES5 / UMD compiler output, no extra transpilation/polyfills | Numbered browser minimum unresolved | Chrome 153.0.8010.36; Firefox 155.0.1 publication-date caveat; Safari 26.6 | Browsers not executed |
| wasmJs / Chrome | explicit legacy EH | 119 (Kotlin documented) | 153.0.8010.36 | Browser not executed |
| wasmJs / Firefox | explicit legacy EH | 120 (Kotlin documented) | 155.0.1 publication-date caveat | Browser not executed |
| wasmJs / Safari | explicit legacy EH | Safari 18.2 (Kotlin documented) | Safari 26.6 | Safari not executed; arbitrary Playwright WebKit cannot certify Safari |

Node's [22 release announcement](https://nodejs.org/en/blog/announcements/v22-release-announce) identifies WasmGC support. The actual tagged V8 sources show new EH (`exnref`) disabled in [24.14.1](https://github.com/nodejs/node/blob/v24.14.1/deps/v8/src/wasm/wasm-feature-flags.h) and enabled in [24.15.0](https://github.com/nodejs/node/blob/v24.15.0/deps/v8/src/wasm/wasm-feature-flags.h). The matching runtime probe establishes this boundary on these artifacts. A V8 version-number lookup alone misses this backport. No exhaustive search of older Node 22 patches, experimental-flag combinations, or other releases was performed; therefore 24.15.0 remains a candidate floor, not a proof no older patched branch works. Node prints its own experimental WASI warning even where no experimental Wasm command flags are supplied.

Wasmtime [37.0.0 release notes](https://github.com/bytecodealliance/wasmtime/blob/v37.0.0/RELEASES.md) announce completed, disabled-by-default exception handling. Its actual CLI rejects this module by default (GC types), then with GC and exceptions alone (function references), and passes with all three flags. The [Bytecode Alliance announcement](https://bytecodealliance.org/articles/) identifies 47 as enabling GC and exceptions by default. This bounded probe did not execute 47 or pre-37 versions.

Kotlin's [Wasm configuration](https://kotlinlang.org/docs/wasm-configuration.html) documents the three browser minima and the target-specific EH defaults. The [WASI guide](https://kotlinlang.org/docs/wasm-wasi.html) specifies Preview 1 and the Node/Wasmtime task families. The generated loader, not a handwritten substitute, was run in Node; Wasmtime directly consumed the matching `.wasm`.

## Plain JS is still a real factual gap

The chosen `es5` setting does **not** justify claiming all ES5 browsers. The generated development stdlib contains the parse-time syntax `var newCtor = class extends ctor {}` in `createExternalThis`, plus references to `Reflect.construct` and `Object.assign`. The optional BigInt helpers must also be assessed for reachability. This explains the observed old-Node parse failures; a dead helper still must parse. Optimized output can remove helpers, so testing only production is insufficient.

This is direct artifact evidence, not a claim that every stdlib operation requires every referenced API. To freeze an exact old browser floor, audit the complete dependency graph and test the chosen browser binaries with the generated development artifact and production artifact, or explicitly add and verify a transpilation/polyfill policy. Kotlin's [project setup](https://kotlinlang.org/docs/js-project-setup.html) describes output and environments but supplies no numbered plain-JS browser support guarantee. No defensible exact plain-JS minimum was established here.

## Current versions and artifact existence

- [Node distribution index](https://nodejs.org/dist/index.json) identifies v26.8.2, dated 2026-09-09. Downloaded and executed its Linux x64 archive; hash matches its official [checksum manifest](https://nodejs.org/dist/v26.8.2/SHASUMS256.txt).
- [Wasmtime latest release API](https://api.github.com/repos/bytecodealliance/wasmtime/releases/latest) identified v48.0.2, published 2026-09-10T19:20:08Z. Downloaded and executed Linux x86_64 archive; hash matches release asset digest.
- [Chrome for Testing stable channel metadata](https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions.json), timestamp 2026-09-10T16:20:11.129Z: 153.0.8010.36, revision 1681091. Stable candidate, not executed or downloaded here.
- [Mozilla product metadata](https://product-details.mozilla.org/1.0/firefox_versions.json) reports latest 155.0.1, and the official [155.0.1 checksum manifest](https://archive.mozilla.org/pub/firefox/releases/155.0.1/SHA256SUMS) exists. Metadata also says `LAST_RELEASE_DATE=2026-09-11`, later than this local research date. Retain that discrepancy; do not silently assert released-before-cutoff status. Browser not downloaded/executed.
- [Apple Safari 26.6 release notes](https://developer.apple.com/documentation/safari-release-notes/safari-26_6-release-notes) and [security release](https://support.apple.com/en-us/128073) substantiate Safari 26.6 as released. Safari 27 beta is excluded. No Apple runtime was available in this local probe.

## Development and optimized-release equivalents

These targets use Kotlin binary modes **DEVELOPMENT / PRODUCTION**, not Native debug/release switches. Both modes are actual compiled executables here. Wasm production consumption uses the `optimized` directory produced by Binaryen, not the pre-optimization sibling. The pinned [KGP binary implementation](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/libraries/tools/kotlin-gradle-plugin/src/common/kotlin/org/jetbrains/kotlin/gradle/targets/js/ir/JsBinaries.kt) routes production Wasm through its optimize task; the [link implementation](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/libraries/tools/kotlin-gradle-plugin/src/common/kotlin/org/jetbrains/kotlin/gradle/targets/js/ir/KotlinJsIrLink.kt) enables development debugger formatting and compilation caching. Compiler flag names are in [CompilerFlags.kt](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/libraries/tools/kotlin-gradle-plugin/src/common/kotlin/org/jetbrains/kotlin/gradle/targets/js/ir/CompilerFlags.kt).

A future full test harness must drive the same assertions through both resulting executables and check reported assertions, not merely task success. A `NodeTest` or browser task alone does not prove it ran production-linked code. Browser automation should load UMD dependencies in order (or a verified webpack bundle), await completion, and expose failures to the process. Server-side Linux x86_64 smoke runs do not cover ARM64 consumers. Build/link host can be any selected supported JDK21/Gradle9.5.0 host; browser OS and Safari host constraints are independent. Actual local evidence here is only Linux x86_64.

## Reproduction and retained evidence

Run from repository root, after the sibling JVM probe tool bootstrap has supplied the specified Gradle/JDK:

```bash
bash probes/toolchain/web/bootstrap-runtimes.sh
JAVA_HOME=/tmp/dyn4k-probe-tools/jdk-21.0.12.1+1 \
 /tmp/dyn4k-probe-tools/gradle-9.5.0/bin/gradle -p probes/toolchain/web \
 compileDevelopmentExecutableKotlinJs compileDevelopmentExecutableKotlinWasmJs \
 compileDevelopmentExecutableKotlinWasmWasi compileProductionExecutableKotlinJs \
 compileProductionExecutableKotlinWasmJsOptimize compileProductionExecutableKotlinWasmWasiOptimize --console=plain
bash probes/toolchain/web/run-consumers.sh
```

The runtime bootstrap records exact download URLs and verifies pinned SHA-256 hashes. Node hashes were compared with the respective upstream `SHASUMS256.txt`; Wasmtime48 matches GitHub's asset digest. Wasmtime37 hash is an observed archive hash, not a separately verified signature. The scripts require Linux x86_64 and network access; build downloads remain normal Gradle dependencies.

`build-probe.log`, `production-build.log`, and `consumer-results.log` preserve actual results. The latter completes with `Unexpected exit results: 0`, including deliberate negative compatibility cases. `initial-dsl-failure.log` retains the corrected initial DSL error: wasmWasi options must configure its compilation tasks in this selected API rather than invoke an unavailable target-level receiver. `old-node.log` is exploratory partial evidence, not part of the reproducible selected-runtime pass matrix.

Remaining decision blockers: exact plain-JS browser and Node minima, exhaustive oldest compatible Node patched-branch boundary, actual browser minimum/current execution, Firefox cutoff reconciliation, architecture-specific consumers, and full physics-suite harnesses. None is converted into a passed lane or a narrower support contract.

The exploratory Node 4.0.0 download stalled and was stopped; extraction encountered an incomplete archive and the resulting incomplete binary failed. That attempt has **no compatibility meaning**, is excluded from all candidate-floor conclusions, and is preserved only in `old-node.log`. No successfully verified Node 4 artifact was executed.
