# Browser and Wasmtime qualification

This runner checks the staged `dyn4k-core` and `dyn4k` publications on the assigned web runtimes. It runs every current common test in both modules. A separate consumer resolves both staged modules and steps a world. Its test checks shared body identity, collision detection, and contact callbacks.

Use a clean commit and JDK 21. Stage the three target publications and root metadata:

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

Run `js` and `wasmJs` on Chromium and Firefox at minimum and current versions. Run `wasmWasi` on Wasmtime at minimum and current versions. Each version needs development and production execution. The runner writes `lane.json`, a result JSON for each module, Gradle consoles, browser XML, and Wasmtime consoles. A passing lane requires the source case identities, zero skipped tests, the staged consumer physics test, the selected runtime, and the selected linked output. It checks the runtime binary hash again after each module.

Karma launches browsers through `browser_launcher.py`. The launcher records the live process image and its hash. The runner checks that image against the selected browser installation and exact version. XML must name the selected browser family and exact major number. XML can omit patch detail, so the process image supplies the exact-version check.

The staged world consumer source has a reviewed SHA-256 contract. An empty test or removal of its identity, step, collision, or contact assertions fails before a lane can pass. If the consumer source must change, review its behavior and update the pinned digest with the mutation controls.

Each lane keeps a private copy of the linked test executable. Wasmtime executes that copy. Gradle, Wasmtime, and browser launch consoles and reports have SHA-256 digests in module and lane receipts. The runner refuses an output directory that already contains evidence. Audit retained bytes with:

```sh
python3 tools/qualification/browser_wasi/runner.py audit --receipt /path/to/lane.json
```

An older receipt without these raw-file digests cannot pass this audit. Preserve older failed receipts as failed evidence.

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
