# Full staged browser consumer

The external project covers 24 approved browser configurations. Each runs 2,523 original portable Kotlin methods against separately staged core and facade KLIBs.

The routes are `js` and `wasmJs`, each on Chromium, Firefox, or Safari. Each family has minimum and current roles in development and production modes. Four older JS Chromium receipts remain replayable only for their exact historical candidate.

The project has its own Gradle root and two test modules. It reads original core and facade test sources from the exact candidate checkout. The core module includes the selected JS or Wasm JS platform test sources. Both modules resolve target KLIBs through Maven GAVs. Their test compiles and executable links use the resolved friend KLIBs.

`tools/qualification/full_browser_consumer.py run` requires a clean exact checkout, external staging repository, and independently selected hashes for both target KLIBs. Chromium 119 and 155 and Firefox 120 and 158 have pinned executable hashes. Safari requires a matching macOS host, an executable in a Safari app bundle, and `--browser-sha256` selected independently. The minimum Safari role requires version 18.2. The current role requires major version 26 or newer. The Safari launcher requests a fresh instance through LaunchServices and waits for it to exit. It observes the new selected process with macOS `libproc`.

Use JDK 21, Gradle 9.5.0, and KGP 2.4.20 with cached dependencies. On Linux, set `JAVA_HOME=/tmp/dyn4k-tools/jdk21`. On macOS, select the task-owned JDK 21 whose executable matches the pinned Darwin hash. Set `GRADLE_USER_HOME` to the task cache and `TMPDIR` to a short, home backed directory. Put output and staging outside the checkout. Resolve pinned dependencies into that cache before capture when needed. The producer uses Gradle `--offline --rerun-tasks` and writes raw output under the selected home directory.

The project pins separate JS and Wasm Yarn locks from offline resolution. The producer captures live lock bytes after the provider graph and each module task. Each capture records the process, time, file identity, and a raw lock copy. A mismatch rejects the route. Public replay checks all three copies against the committed lock and their source process intervals. Earlier receipts without these captures remain historical.

The source inventory binds every original test file to a Git blob. The method contract binds 2,465 core and 58 facade methods to the immutable manifest. The archive retains both resolved KLIBs, provider graphs, Gradle output, raw Karma messages, XML results, and method order. Any missing, duplicate, foreign, failing, or skipped method rejects the route. A source compile or smaller consumer is `NOT_RUN`.

The archived Karma config selects the exact JS script or Wasm JS loader for the mode. The reporter verifies all seven effective Karma patterns, their served and included flags, preprocessors, and pinned implementation inputs. It checks original `isBinary` values before Karma normalization. It also records the selected source bytes in Node during Karma's browser start callback. The record binds the capture to the source process interval and the observed browser identity.

For Wasm JS, the reporter also captures all six generated Kotlin package assets at browser start. It checks their bytes again at completion. The verifier compares the archived Wasm and module files with the linked products and captured package copies. These checks attest selected source and package bytes. The archive does not contain browser loaded response bodies.

In production mode, the test task copies optimized Wasm products into Karma's package before browser launch. Replay checks those package bytes against the linked optimized Wasm and module files.

`verify` requires the exact candidate, lane, browser executable, both staged KLIB hashes, and an independently calculated archive digest. Safari replay also requires its independently selected executable hash. Replay checks the complete archive inventory before any executable consideration. It verifies source and method hashes, task and mode, raw rows, provider graphs, config bytes, selected assets, and process identity. It rejects a changed digest, symlink, wrong runtime, changed bundle, or execution outside the process interval.

Replay accepts a metadata-preserving copy at a new canonical archive path. The receipt keeps the original capture path for process commands and selected-bundle observations. The verifier reads archived bytes at the supplied path. It rejects symbolic paths, hardlinked files, and aliases to the original directory.

The coordinator supplies reviewed source to the approved local Mac and serializes Safari execution. No Safari runtime result is inferred from Linux or a Gradle dry run.

Run `python3 tools/qualification/full_browser_consumer.py --help` for command arguments. Keep failed attempts in distinct evidence directories. An unavailable Safari host remains `UNAVAILABLE` and its browser method gate remains `NOT_RUN`. A passing consumer receipt does not qualify numerical parity, physical behavior, performance, memory, publication, or the 112 lane release matrix.
