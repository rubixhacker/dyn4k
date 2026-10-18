# Browser and Wasmtime qualification

This runner checks the staged `dyn4k-core` and `dyn4k` publications on the assigned web runtimes. Each applicable lane must execute all 2,465 core and 58 facade cases from the committed `full-common-corpus.json`. It checks the manifest against the committed original map, reviewed pair file, and current test source tree. Candidate preflight also compares production and consumer source bytes with their committed Git blobs. A separate consumer resolves both staged modules and steps a world. Its test checks shared body identity, collision detection, and contact callbacks.

Run against a clean candidate commit with JDK 21. First check its committed corpus, test sources, reviewed map, and consumer pins:

```sh
python3 tools/qualification/browser_wasi/runner.py candidate \
  --root "$PWD" --candidate-sha "$SHA"
```

This preflight does not execute a runtime lane. A clean production-source successor can retain the same manifest when its test inventory and reviewed map are unchanged. Changed test sources require a regenerated and reviewed manifest. Changed mappings also require reviewed map and pair pins. A changed generator or consumer contract requires verifier review and updated code-owned digests. Every new candidate needs fresh staged artifacts and runtime evidence bound to its exact SHA. Stage the three target publications and root metadata:

The standalone browser/WASI consumer has its own ignored `kotlin-js-store/yarn.lock`. A clean checkout has no generated consumer lock. The runner verifies the committed `fixtures/consumer-yarn.lock` against both the candidate Git tree and the reviewed SHA-256, then copies those bytes to the consumer store before staging or running a lane. An existing generated lock must match exactly; wrong bytes, symlinks, and extra untracked inputs fail candidate preflight. Stage and lane Gradle commands set `YARN_OFFLINE=true`, so `kotlinUpgradeYarnLock` and `kotlinWasmUpgradeYarnLock` use the reviewed lock and cached packages. A checkout without the committed fixture cannot qualify as a new candidate. This fixture pins the consumer's dependency graph separately from the root `kotlin-js-store/yarn.lock`.

```sh
python3 tools/qualification/browser_wasi/runner.py stage \
  --root "$PWD" --candidate-sha "$SHA" --output /tmp/dyn4k-browser-stage
```

Run one selected lane with its exact binary. For example:

```sh
python3 tools/qualification/browser_wasi/runner.py run \
  --root "$PWD" --candidate-sha "$SHA" \
  --receipt /tmp/dyn4k-browser-stage/stage.json \
  --target wasmJs --runtime firefox --version-role minimum \
  --configuration production --expected-version 120.0.1 \
  --binary /path/to/firefox --output /tmp/dyn4k-browser-wasm-firefox-min-production
```

Run `js` and `wasmJs` on Chromium and Firefox at minimum and current versions. Run `wasmWasi` on Wasmtime at minimum and current versions. Each version needs development and production execution: 20 lanes. The runner writes `lane.json`, a result JSON for each module, separate stdout and stderr, Gradle consoles, browser XML, and Wasmtime consoles. A passing lane requires all committed source case identities, zero failed or skipped tests, the staged consumer physics test, the selected runtime, and the selected linked output. It checks the runtime binary hash again after each module.

Karma launches browsers through `browser_launcher.py`. The runner gives each browser module an isolated local Karma port and retains its generated configuration. This prevents browsers left by another task on Karma's default port from adding cases to a lane. The launcher records the live process image and its hash. The runner checks that image against the selected browser installation and exact version. XML must name the selected browser family and exact major number. XML can omit patch detail, so the process image supplies the exact-version check.

The staged world consumer source has a reviewed SHA-256 contract. An empty test or removal of its identity, step, collision, or contact assertions fails before a lane can pass. If the consumer source must change, review its behavior and update the pinned digest with the mutation controls.

Each lane keeps a private copy of the linked test executable. Wasmtime executes that copy. Gradle, Wasmtime, and browser launch consoles and reports have SHA-256 digests in module and lane receipts. The lane binds the candidate SHA, source tree, corpus manifest, original map, reviewed pairs, staged artifacts, and runtime binary. The runner refuses an output directory that already contains evidence. Audit retained bytes with:

```sh
python3 tools/qualification/browser_wasi/runner.py audit --receipt /path/to/lane.json
```

The audit replays raw case checks and rejects PASS fields that differ from XML or Wasmtime events. Each browser module must have the exact Gradle command, linked source, and configuration marker in raw stdout. Development stdout must have no production marker. The retained executable and configuration-specific source must match the recorded source digest. A passing browser audit requires the retained Karma config, its SHA-256, and a valid port.

The audit compares the complete generated JSON settings with the expected settings for the target and module. These bind the browser, both file inputs, both preprocessors, package path, launchers, and other generated options. Wasm JS helper paths must point to an installed Kotlin tooling cache with the expected layout. The runner and Wasm context files must match reviewed byte digests. An added exclusion, launcher override, `set` value, or other setting fails. The audit also compares the remaining executable config with reviewed JS or Wasm JS scaffolds after normalizing only the isolated port. This rejects code that skips the port setter or overrides the browser or input later. A changed Kotlin Gradle scaffold or helper needs verifier review and an updated code-owned digest. Resealing a receipt cannot change that rule.

The process image and XML bind the exact browser version. An older 932/46 receipt cannot pass the full corpus audit. Preserve older failed receipts as failed evidence.

The runner invokes Wasmtime with `-W gc=y -W exceptions=y -W function-references=y` and the test binary's `startUnitTests` export. Production WASI and Wasm JS tests consume Binaryen's `optimized` output. JavaScript production tests consume the production linked output. Browser tests use Karma and the selected `CHROME_BIN` or `FIREFOX_BIN`; the XML records the actual browser family and major version.

## Runtime selection

The minimum and current versions below were selected from official release feeds on 2026-10-17. Recheck current releases for a later candidate.

| Runtime | Minimum selection | Current selection | Source |
| --- | --- | --- | --- |
| Chromium | Chrome for Testing 119.0.6045.105 | 155.0.8059.84 | [Chrome for Testing versions](https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json), [current stable feed](https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json) |
| Firefox | 120.0.1 | 158.0 | [Mozilla release archive](https://ftp.mozilla.org/pub/firefox/releases/) |
| Wasmtime | 37.0.3 | 49.0.3 | [Wasmtime releases](https://github.com/bytecodealliance/wasmtime/releases) |

Chrome published a later 119.0.6045.199 Linux stable patch, but the official Chrome for Testing archive lists 119.0.6045.105 as its last retrievable 119 Linux build. The [Chrome release record](https://chromereleases.googleblog.com/2023/11/stable-channel-update-for-desktop_28.html) establishes the later patch. Record this gap with the minimum lane; execution of 119.0.6045.105 does not demonstrate 119.0.6045.199.

Firefox can update an extracted old archive when it launches. Put `{"policies":{"DisableAppUpdate":true}}` in its `firefox/distribution/policies.json` before testing. Verify the binary version and SHA-256 before and after every lane. The runner rejects a changed binary.

This is an assigned subset of the 21-target, 28-runtime support contract. A passing subset does not qualify Safari, Apple devices, Android, native targets, or the 112-lane release matrix. Baseline physical and numerical acceptance results remain separate.
