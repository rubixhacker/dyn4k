# Full Android staged consumer

This consumer compiles the approved portable assertion sources from an exact dyn4k checkout. It uses the staged Android core and facade AAR class bytes as its only dyn4k compile inputs. The core test module receives friend access to the staged core classes. The facade test module receives friend access to both staged modules. The Android app resolves both AARs through the staged Maven repository and packages the external test modules.

Run each command with JDK 21 at `/tmp/dyn4k-tools/jdk21`, Gradle 9.5.0 at `/tmp/dyn4k-tools/gradle-9.5.0`, and Android SDK at `/var/home/stewart/Android/Sdk`. Set `JAVA_HOME`, `ANDROID_HOME`, and a home backed `TMPDIR` explicitly. Keep each output and archive directory under the session evidence directory.

The producer places Gradle project caches under the selected output directory. This keeps the exact-source checkout clean for staging and public replay.

```sh
python3 tools/qualification/full_android_consumer.py compile --staging build/staging-repository --output "$OUTPUT"
python3 -m unittest tools.qualification.test_full_android_consumer -v
python3 tools/qualification/full_android_consumer.py build --staging build/staging-repository --output "$OUTPUT"
python3 tools/qualification/full_android_consumer.py run --staging build/staging-repository --output "$OUTPUT" --archive "$DEBUG_ARCHIVE" --variant debug --expected-api 37
python3 tools/qualification/full_android_consumer.py run --staging build/staging-repository --output "$OUTPUT" --archive "$RELEASE_ARCHIVE" --variant release --expected-api 37
```

The installed run uses ADB server port 5038 and emulator 5558. Check active guest and host processes before each run. It records the installed app and test APK bytes, API, fingerprint, ABI, selected process, original method rows, provider graph, toolchain hashes, and DEX evidence. Failed attempts remain in their archive directories. A passing debug run does not stand in for R8 or API 21.

Verify each sealed archive from a clean checkout at its exact candidate commit. Supply the archive digest and both AAR hashes independently of the archive. Supply the independently selected runtime identity as well.

```sh
python3 tools/qualification/full_android_consumer.py verify --checkout "$CLEAN_CHECKOUT" --archive "$DEBUG_ARCHIVE" --expected-archive-digest "$ARCHIVE_SHA256" --expected-core-aar-sha256 "$CORE_AAR_SHA256" --expected-facade-aar-sha256 "$FACADE_AAR_SHA256" --expected-runtime-identity "$RUNTIME_SHA256"
```

The verifier checks source and toolchain bytes, the compiled class inventory, raw installed method rows, XML normalization, installed APK hashes, process identity, DEX transformation, and the `independent_gates.py` full staged consumer contract. This result is one gate for one approved lane. Other lane and global gates remain separate.
