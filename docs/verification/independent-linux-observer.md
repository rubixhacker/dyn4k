# Independent Linux process observer

The Linux collector launches the selected command under `ptrace` and writes an unsigned process witness. It stops the initial child before `exec` and follows fork, vfork, clone, exec, and exit events. It opens `/proc/<pid>/exe` while each image is stopped and hashes that open handle. It also records the boot ID, PID, start ticks, parent PID, executable path and file identity, argv, monotonic event times, and exit status.

The collector writes `events.jsonl` and `witness.json` into a new private directory. Each event has a sequence number, the previous event hash, and its own SHA-256. The public `verify` command checks exact event bytes and the full chain. It reconstructs the witness from the events and rejects missing images, exits, reaps, ancestry, selected executables, or archive sealing. It rejects a lost-event count, observation error, changed event byte, symlink, hardlink, and path traversal in the observer bundle. An incomplete trace keeps its error log and creates no verified witness. Preflight failure creates no output directory.

## Local use

Run the collector as a separate process. Give it the command argv after `--`. `--expect` names the child executables to select from the traced descendant tree. For the central `core` and `facade` fields, use those exact names. The root executable is the build image by default. Use `--build-executable PATH` when the selected command launches a separate build process. The named child processes must descend from that observed build process. Expected paths and staged artifact paths are comparison inputs; they are not process observations.

```sh
TMPDIR="$HOME" python3 tools/qualification/independent_linux_observer.py capture \
  --output "$HOME/dyn4k-linux-observer-example" \
  --candidate-sha 7458ae264a79ce3e6e36fd625afda0fd246be843 \
  --lane local:observer:example --runtime-identity linux-x86_64-local \
  --mode debug --archive README.md \
  --expect core=/usr/bin/true --expect facade=/usr/bin/echo -- \
  /usr/bin/python3 -c 'import subprocess; subprocess.run(["/usr/bin/true"], check=True); subprocess.run(["/usr/bin/echo", "observed"], check=True)'

python3 tools/qualification/independent_linux_observer.py verify \
  "$HOME/dyn4k-linux-observer-example"
```

The example uses `README.md` as a regular-file digest fixture. For a qualification producer, pass its archive directory. The collector seals that directory after all traced processes exit. Its directory digest uses sorted relative paths, file SHA-256 values, and nanosecond mtimes, matching the current central archive digest algorithm. The directory must contain `receipt.json`. Supply each staged publication as `--artifact core=PATH` and `--artifact facade=PATH` when applicable.

The witness has the central `independent-execution-witness/1` fields: candidate SHA, lane, runtime identity, mode, archive digest, staged artifact hashes, named executable hashes, auditor, build process, and named child processes. Each process has the central PID, image hash, interval, and exit code fields. Additional fields retain the observed boot ID, PID start ticks, image path and file identity, argv, and coverage. Every successful result says `OBSERVED_UNSIGNED` and `unqualified`.

## Limits and remaining integration

The default timeout is 20 seconds. The caller can set `--timeout` up to 3,600 seconds. One wall clock timer covers preflight hashing, process tracing, archive sealing, and witness verification. The timer interrupts Python work and interruptible system calls. Uninterruptible kernel I/O can delay its handling. The defaults are 256 observed processes, 4,096 events, and an 8 MiB event log. Event and log limits below those defaults fail before launch. The hard ceilings are 1,024 processes, 8,192 events, and 16 MiB. Normal events reserve two terminal slots and 4,096 bytes for a failed trace. Other bounds are a 4,096-file archive and 2 GiB per archive, preflight input, or live image. The archive byte limit applies to both a regular file and a directory. The collector fails closed if the kernel denies tracing or an image cannot be opened. A real Gradle producer needs a reviewed timeout and sufficient event limits. Linux ptrace observation has been exercised here with two short lived children, a nested fork/exec tree, and a separate observed build child. A child-local seccomp control produced a real `EPERM` denial, an error event, and no witness in the focused test. The first Linux x64 KLIB consumer attempt reached the core and facade tests, then failed the current-source pin and produced no witness.

The hash chain detects changes against the retained witness. It does not authenticate an attacker who can replace both files and recompute the chain. Qualification requires a detached signed audit and independent key custody. The selected audit process must bind verified observer evidence, the final archive, and the candidate. A separate signer service or hardware key is an implementation choice, not a requirement of this collector. The Native cross signed route checks the observer chain and signed byte hashes. Other routes still rely on the independent auditor's signed process observations.

For a Gradle script, pass `--launcher-script PATH` and select the live Java image with `--build-executable PATH`. The observer measures the script before launch and after all traced processes exit. It records script bytes and path separately from the stopped process image. `--build-only` permits an x64 build capture without claiming ARM64 child execution. The Native cross route checks the script argv, archived Gradle PID, observed shell image, Java image and ancestry, and build archive digest. It compares observer wall-clock events with the producer wall-clock interval. Witness monotonic times stay in the observer clock domain. The signed runtime witness remains a separate requirement for actual ARM64 processes. Raw test output interval binding and staged publication identity remain integration work.
The run event retains the requested build executable path and the resolved image path separately. For a Native cross replay, the requested path must be the selected signed JDK `bin/java`; the resolved path must match the independently observed Java executable. The central route compares the observer source file with the exact candidate, then compiles those candidate bytes in a fresh namespace and calls its `verify` function. A cached `.pyc` or replaced imported function cannot supply this replay verifier. This permits copied archives and honest JDK symlinks without consulting a replay host's JDK.

Android guest execution still needs evidence from the selected device and installed executable. Browser routes still need independently bound browser execution and response bytes. Windows and macOS routes need observed execution on their selected hosts and runtimes. A Windows debugger with a Job Object or an entitled macOS Endpoint Security collector are possible designs, not approved prerequisites. The supplied local Mac does not require a privileged observer service by this specification. No 112-lane qualification follows from this local observation.
