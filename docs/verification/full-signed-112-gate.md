# Signed staged consumer routes for all 112 lanes

The approved manifest defines 112 lane IDs. The signed adapter checks that every
ID has one dedicated source route: four JVM, four Android JVM, eight KLIB,
24 browser, 12 nonbrowser Wasm, 28 Native host or simulator, 16 Android Native,
and 16 physical Apple routes. This registry describes supported verification
code. It does not report that any lane ran.

The independent audit is a detached Ed25519 signature over the exact audit
bytes. The caller pins the DER public key SHA-256 outside the producer archive.
The audit binds the candidate SHA, approved suite digest, candidate manifest,
staged publication audit, both target KLIB hashes, lane runtime identity, and
each supplied archive digest. A passing candidate also needs every other
required gate. Missing archives remain `NOT_RUN`. A failed or malformed
attempt is `FAILED`. An `UNAVAILABLE` receipt is accepted only when its entire
content and archive digest are independently signed as an unavailable
observation. A producer's own reason is insufficient.
An explicit `NOT_RUN` producer receipt likewise needs an exact signed
`expected_not_run` object. An absent archive remains `NOT_RUN` without a
producer claim.

## Signed fields for the added routes

All fields below belong to the signed lane object. They supplement
`expected_artifact_hashes`, `expected_runtime_identity`, and
`expected_archive_digests.staged-consumer`. The signed runtime string must
also equal the candidate manifest's lane runtime string.

| Route | Additional signed fields |
| --- | --- |
| Browser beyond the original four Chromium routes | `expected_browser_toolchain`, `expected_browser_bundles`; Wasm browser also needs `expected_browser_responses` and `expected_execution_witness` |
| Nonbrowser Wasm | `expected_wasm_runtime`, `expected_wasm_runtime_binary` |
| Native host and simulator | `expected_native_selection`, `expected_native_host`, `expected_native_toolchain`, `expected_native_host_executables`, `expected_execution_witness` |
| Linux ARM64 Native cross runtime, schema 3 | `expected_native_selection`, `expected_native_host`, `expected_native_toolchain`, `expected_native_build_archive_sha256`, `expected_native_build_host`, `expected_native_build_executables`, `expected_execution_witness` |
| Android Native | `expected_android_native_guest`, `expected_android_native_toolchain`, `expected_android_native_executables`, `expected_android_native_adb`, `expected_android_native_serial`, `expected_android_native_replay_output`, `expected_android_native_executable_paths`, `expected_execution_witness` |
| Physical Apple | `expected_apple_device`, `expected_apple_device_toolchain`, `expected_apple_device_executable_paths`, `expected_apple_device_executable_hashes`, `expected_apple_os_roles` (signed path and digest of an external OS role selection) |
| Native KLIB | `expected_klib_native_executables`, `expected_execution_witness` |

For nonbrowser Wasm, the signed string has the exact form
`wasm-node-v1:<SHA-256>`. The digest is computed with the central canonical
JSON function over `expected_wasm_runtime`, an independently selected object
with `family`, `role`, `version`, `sha256`, `path`, and `host`. The gate compares
the native receipt object to that signed object, checks the selected runtime
executable bytes and version, checks the current host, and replays both
transported test bundles with `replay=True`. Stringifying receipt JSON does
not satisfy this mapping. A signer must measure the object independently.

`expected_execution_witness` has `path` and `sha256` fields. The path points
to a separate regular JSON file whose bytes match that signed digest. Its
schema is `independent-execution-witness/1`. It records the exact candidate,
lane, staged archive digest, runtime string, mode, both staged artifact hashes,
executable hashes, an independent auditor name, a build process observation,
and `core` and `facade` runtime process observations. Each
process records its executable hash, positive PID, zero exit code, and a valid
start and finish time. The auditor must obtain these observations independently
from actual runtime execution. A signed declaration copied from the producer
is not an independent process observation. Native host and KLIB Native routes
need this witness because their current receipts do not bind the retained
executable to an observed child process. Android Native needs it for the
original guest process and build provenance.

For a Linux ARM64 Native cross run, the signed witness binds the x64 build
process and both ARM64 runtime processes. The verifier checks each process PID
and observation interval against its archived record. It checks the signed
Gradle and executable hashes. Build and runtime clocks are checked separately.
The schema-3 public result must report audited artifact hashes and a complete
selected suite. A compile-only build does not prove runtime execution.

`expected_browser_bundles` maps `core` and `facade` to separate
`karma_selected_js` and `linked_executable_js` SHA-256 values. For Wasm JS,
each module also has `linked_executable_wasm` and an `assets` map from every
served asset name to its SHA-256. The gate checks each actual archive file.
The selected Karma JS and linked executable JS can have different bytes.

For Wasm browser, the independent auditor must capture every delivered HTTP
response body during the observed browser process. Each
`expected_browser_responses` module entry is a list with `name`, `url`,
`status`, `sha256`, `body_path`, `observed_at_ns`, and `browser_id`. The
`body_path` is an absolute path to an independently captured regular file
outside the producer archive. Its bytes must equal the signed response hash
and the archived served asset. The status must be HTTP 200, the URL must use
HTTP or HTTPS, the browser ID must match the selected bundle observation, and
the response time must fall within the independently witnessed browser
process. The signed execution witness repeats the complete response records.
The auditor must record the actual HTTP exchange and body at the network
boundary. Copying producer asset declarations or files into these fields does
not establish a delivered response. The gate rejects a missing body or
mismatched witness instead of treating that source gap as `UNAVAILABLE`.

The Android Native public verifier performs live ADB replay in the separately
selected output directory. The Apple verifier checks physical device install,
launch, image readback, and all original methods. Browser verification checks
the selected browser executable and both staged bundles. The older JVM and
Android JVM routes retain their established public verifier contracts. The
KLIB JS adapter supplies the selected Node executable so its public verifier
replays the transported program. The KLIB schema 2 raw gate accepts Gradle
debug prefixes around task and file markers. It requires an observed lane
marker, even when the command includes the lane. Exact task, file, and 2,523
method checks remain required. The public KLIB verifier accepts the captured
schema 2 `--debug`, `--max-workers=1`, and `--no-parallel` command and its
timestamped Gradle channels. It requires Node replay for JS and checks the
native executable bytes. The retained archives belong to historical source
commits; an exact assembled candidate still needs its own captures and signed
audit.

The earlier producer reviews recorded source gaps before the current imports.
The Android Native API 21 installed-byte check, KLIB schema 2 replay, and
browser Wasm reporter have reviewed source repairs. The Native host Windows
archive path is under separate repair. Browser Wasm still lacks an
independently observed HTTP response body and process witness. Native and
Android Native routes still need independently observed build and runtime
processes tied to a detached signed audit. Physical Apple routes need actual
device execution and an external OS role selection. These requirements remain
open at this assembled source; a route registry does not pass a lane.
