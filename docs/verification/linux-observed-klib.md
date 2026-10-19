# Linux x64 KLIB process observation

`linux_observed_klib.py` runs the reviewed full staged KLIB consumer under the independent Linux ptrace collector. It supports the current Linux x64 `debug-g` and `optimized-opt` routes. The selected checkout must be clean at the exact candidate SHA. Core and facade KLIBs must be separately published from that candidate and copied to an external staging repository. The collector starts before the producer and follows its Gradle and test descendants.

## Capture

Use the pinned JDK 21, Gradle 9.5.0, Kotlin/Native 2.4.20, and an existing Gradle cache. Use a new output directory. The following values are examples; select and hash the staged files independently.

```sh
TMPDIR="$HOME/dyn4k-klib-observer-tmp" python3 tools/qualification/linux_observed_klib.py capture \
  --repository "$PWD" --candidate-sha "$(git rev-parse HEAD)" \
  --lane 'linuxX64:Linux x64:current:debug-g' \
  --staging "$HOME/dyn4k-klib-stage" --output "$HOME/dyn4k-klib-observed-debug" \
  --gradle /tmp/dyn4k-tools/gradle-9.5.0/bin/gradle --node /usr/local/bin/node \
  --java-home /tmp/dyn4k-tools/jdk21 --gradle-user-home "$HOME/.gradle" \
  --konan-data-dir "$HOME/.konan" --android-home "$HOME/Android/Sdk" \
  --tmpdir "$HOME/dyn4k-klib-observer-tmp" --timeout 1200
```

The runner measures the selected stage KLIBs, source inventory, manifest contract, tool binaries, and Gradle script before capture. The observer starts the real `full_klib_consumer.py run` command. The producer then launches pinned Gradle 9.5.0 with its existing exact-source and clean-checkout guards. The observer selects the Gradle Java image by its `qualificationEvidence` and lane arguments. It also requires a prior shell image with the Gradle script path in the **same PID and start identity**. The script hash, shell image, observed Java image, and argv are retained together. The script file is not represented as a `/proc/<pid>/exe` image.

The runner sets `JAVA_TOOL_OPTIONS=-XX:ActiveProcessorCount=2` for the traced process tree. This bounds JVM thread churn during observation. The selected value is recorded in the route record.

The route requests at most 1,024 traced identities, 8,192 events, and a 16 MiB event log. Those are hard ceilings checked by capture and public replay. The general collector still defaults to 256 identities, 4,096 events, and 8 MiB. The first exact-source attempt reached that default identity cap during the producer's Git source inventory and retained a failed event log.

The Native test executables are generated during the Gradle run. `--expect-generated` selects each child by its canonical path only after a stopped `exec`. The selected SHA-256 comes from the live open `/proc/<pid>/exe` handle. Capture fails if the child never executes, the path is wrong, the image cannot be read, process coverage is lost, or an observed process exits unsuccessfully. The runner compares those live image hashes with the archived program bytes and runtime records. It checks that the producer's Gradle PID is the observed build PID and that both child intervals lie inside the build interval.

The output contains the original producer archive, observer `events.jsonl` and `witness.json`, an independently selected `selection.json`, and a derived `record.json`. The record binds 2,465 core and 58 facade original XML identities, raw XML hashes and write times inside the observed Gradle interval, staged KLIB hashes, exact source tree, source inventory, toolchain, launcher binding, process images, and the public staged-consumer gate result. It is `OBSERVED_UNSIGNED` and `unqualified`.

## Transport and public replay

Copy the complete output directory while preserving file mtimes. Verify the relocated copy with the public route command:

```sh
TMPDIR="$HOME/dyn4k-klib-observer-tmp" python3 tools/qualification/linux_observed_klib.py verify \
  --root "$HOME/dyn4k-klib-observed-debug-transported" --repository "$PWD"
```

Replay first reselects the exact clean source checkout, staged bytes, and pinned local tools. It then recomputes the observer chain and sealed archive digest, checks the launcher and child image binding, validates original XML identities, and invokes `full_klib_consumer.py verify` on the relocated archive. The verifier rejects changed record bytes, link aliases, changed process identities, unmatched image bytes, wrong task argv, missing raw outputs, and raw XML outside the build interval. The Native public producer verifier checks retained executable bytes and original XML. It does not re-execute the archived ELF, so the original observed execution remains the process evidence.

The bundle is unsigned. An actor able to replace the whole bundle can recompute its chain and record. A separate auditor must bind the final observer record and archive to a detached signed audit under independent key custody. The central signed gate must verify that binding. This local route does not qualify a lane or the 112-lane matrix. The Linux minimum runtime and every other target remain separate requirements.

## Retained attempts

At source candidate `a36c08c8a0f05e17177545746bcbb611b2c0d378`, the full `debug-g` Gradle run completed 2,465 core and 58 facade original methods. The collector observed both generated test images and their zero exits. The producer then failed while hashing its schema-2 consumer build inventory because that candidate lacked `linuxX64/Linux x64/minimum/build.gradle.kts`. It wrote no `receipt.json` or observer witness. Relocated public replay rejects that retained incomplete archive.

At clean source `f498c237c331905176509f349fd8a945edd03d1e`, the restored consumer inventory allowed full current `debug-g` and `optimized-opt` runs. Each executed all 2,523 selected original methods under ptrace. The original and transported archives passed the public observer and route verifiers. The route driver came from the separately reviewed `8aaaa1ff7fd8837a106fca217901017a70fe6f43` source tree because it was absent from the `f498c237` candidate. Both records remain `OBSERVED_UNSIGNED` and `unqualified`. Importing the driver into a later candidate does not change those archived source identities or create a signed lane pass.
