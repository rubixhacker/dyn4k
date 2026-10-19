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

The hash chain detects changes against the retained witness. It does not authenticate an attacker who can replace both files and recompute the chain. Qualification requires a detached signed audit and independent key custody. The selected audit process must bind verified observer evidence, the final archive, and the candidate. A separate signer service or hardware key is an implementation choice, not a requirement of this collector. The central signed gate must then check the observer chain and audit binding; its current witness field checks alone do not prove independent observation. The present central `build.executable_sha256` expects Gradle launcher bytes. A script launcher is not the live `/proc/<pid>/exe` image, so that case needs a separately reviewed launcher-to-interpreter binding. Raw test output interval binding, archive freezing, staged publication identity, and relocated replay also remain integration work.

Android guest execution still needs evidence from the selected device and installed executable. Browser routes still need independently bound browser execution and response bytes. Windows and macOS routes need observed execution on their selected hosts and runtimes. A Windows debugger with a Job Object or an entitled macOS Endpoint Security collector are possible designs, not approved prerequisites. The supplied local Mac does not require a privileged observer service by this specification. No 112-lane qualification follows from this local observation.
