# Ordinary JVM arithmetic diagnostic

## Purpose

This command measures the first 64 pivot-rotation calls in the original
`captureLongMotion` JVM case. The case retains its 36,000 ordered steps at
60 Hz. The observer detaches after the matched prefix. The worker then
continues without this observer.

The result has schema `ordinary-arithmetic-diagnostic/1`. A positive result
has status `DIAGNOSTIC_ONLY` and qualification `UNPASSED`. It is not an
arithmetic receipt, a completed numerical method, or an admission to the
15-method gate.

## Run and replay

The run requires a separate root resource allocation. Its JSON must use
schema `ordinary-arithmetic-resource-allocation/1`, state
`diagnostic_runtime_allocation: SCHEDULED`, record available memory in KiB,
name a nonempty CPU set, and confirm that other tasks remain allocated.
Without that record, the command creates only `diagnostic.json` with
`NOT_SCHEDULED_RESOURCE` and `NOT_RUN`.

Run the command from a clean, committed source revision. Use a private,
home-backed `TMPDIR` of at most 40 bytes, the pinned JDK 21, and a new private
output directory under the home directory:

```sh
env -u OLLAMA_API_KEY TMPDIR=/path/to/private-scratch python3 -B \
  tools/numerical/portable/ordinary_arithmetic_diagnostic.py \
  --capture --output /path/to/new-private-output \
  --allocation /path/to/scheduled-allocation.json \
  --method captureLongMotion --call-cap 64

env -u OLLAMA_API_KEY TMPDIR=/path/to/private-scratch python3 -B \
  tools/numerical/portable/ordinary_arithmetic_diagnostic.py \
  --verify /path/to/new-private-output
```

The verifier reads the retained raw evidence. It rebuilds the helper from
the committed source and checks the retained source archive, staged artifact,
JDK executable, effective worker classpath and its captured inventory. It
also checks the original case bytes, worker and helper executions, loaded
class bytes and loader object, raw call bits, writers, both selected transport
endpoint closes, worker progress, time limits, and sampled RSS.
Replay also checks the selected worker's Gradle ancestry and compares its
raw trace subset with the full process trace. Each sampled PID records its
parent, process group, session, start tick, command hash, and observed CPU
affinity. Replay checks those records against launch groups, trace members,
the allocated CPU set, and the process phase.
The capture retains each distinct sampled command once. It reads the running
executable from `/proc`. Replay rebuilds the command hash and matches it to a
successful raw exec path and argument list. For the committed `#!/bin/sh`
`gradlew` script, Linux records the script invocation in raw `execve` and
`/bin/sh`, the script path, and the same arguments in `/proc/<pid>/cmdline`.
Replay accepts that one mapping only when the raw script path and arguments
match the selected stage or target launch. The source archive includes the
committed wrapper bytes. Other commands still require an exact raw command
match. The role check uses the proved path, the executable's entry point,
the selected PID, and its process ancestry.
It also checks the sample's wall clock interval against trace timestamps.
A command or executable change without raw exec proof fails replay. A
process-only trace records the staging phase, where the Gradle wrapper can
exec Java.

`tracer` measures the supervisor's traced process roots. `other` measures
owned processes whose executable and entry point do not prove a Gradle,
worker, helper, or observer role. These processes remain in aggregate RSS.
An `other` measurement does not establish a specific process role. Missing
raw exec, identity, or RSS evidence cannot support a positive diagnostic.

It recomputes `diagnostic.json` exactly. A changed report or an extra
`receipt.json` fails archive admission.

The helper uses its own monotonic clock for event durations. The supervisor
uses a separate monotonic clock for process milestones. The report does not
subtract times from those two clocks. The selected worker launch is observed
by the supervisor; that duration is an observation bound, not an exact
launch timestamp.

## Limits and interpretation

The diagnostic retains the 1,200-second total watchdog, 900-second target
deadline, 600-second helper deadline, 10-second detach grace, 1,800 MiB
output budget, 128 MiB observer archive limit, and current bounded raw
readers. It applies a separate 10 GiB ceiling to sampled RSS for its owned
PIDs. Each sample stores its time and PID-to-role membership. The reader
deduplicates a PID before summing RSS. Missing measurements remain
`UNAVAILABLE`. Samples cannot prove that no higher peak occurred between
samples or that physical memory was contained by a hard limit.

If a run stops after a checked call, the incomplete report names
`last-complete-observation.tsv` and its SHA-256. This file holds one raw
observation row. A row that fails the privacy or shape checks is not retained
as proof. A stopped run remains incomplete even when the row is present.

The report lists bytes and observed peak RSS by role. It leaves pair-input,
direct-reset, TOI, subnormal, and zero-product categories `UNEXERCISED`
unless the observed prefix proves them. Equal strict and FMA output bits
remain `AMBIGUOUS`. Later calls remain `UNOBSERVED` by this helper.

A timeout, byte limit, RSS limit, failed detach, or partial original case
returns a typed incomplete diagnostic. Such an outcome can guide a later
mechanism study. It cannot satisfy positive completion. The original
15-method, 332-case destination and independent numerical, physical,
performance, hardware, signer, runtime, and release gates remain open.

This guide follows the repository's ISO 24495-1 and ISO 24495-3 writing
guidance. It makes no certification claim.
