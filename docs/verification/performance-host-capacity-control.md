# Terminal capacity host diagnostic

The [performance fixture and reference-environment task](https://github.com/rubixhacker/dyn4k/issues/17) still has no validated reference row. This short diagnostic checks whether the existing macOS and Windows terminal memory helpers work on actual hosted children. It does not select a stress ceiling, validate a reference row, or qualify sustained performance.

## Hosted capture

The `performance-host-capacity-control.yml` workflow has one `macos-26` job and one `windows-2025` job. Each checks out the dispatched candidate SHA, selects Python 3.12, and starts one Python child. The child touches a 16 MiB test buffer, writes a ready PID, prints one raw ready record, and waits. The producer observes the live executable through the production OS image helper. It archives those executable bytes while the child is live, samples memory through the production external monitor, and requests a stop.

On macOS, the producer sends SIGTERM to the exact child and reads its terminal `wait4` status and `ru_maxrss` through `wait4_peak_rss`. It compares the terminal value with the live `/bin/ps` RSS sample in bytes. A smaller terminal value is inconclusive for the proposed byte interpretation. On Windows, it calls the production `windows_dispatch_stop` helper on the original child handle. It waits for exit code 1, then calls `windows_terminal_peak` on the retained exact-PID handle. A failed native dispatch or unavailable post-stop counter is inconclusive. The Windows metric is peak working set bytes; the macOS metric is peak RSS bytes.

The five-minute workflow timeout bounds the job. The child normally sleeps for 30 seconds. The producer waits up to five seconds for the complete PID and flushed stdout marker. It stops the child after the ready and memory samples. Both upload steps run after a capture failure. Once archive creation begins, the producer retains available raw files. It writes a signed failure receipt when cleanup returns.

The receipt identifies the candidate source, executed tool bytes, host, PID, observed executable, and sample. It records the stop request, native result, terminal status, and peak bytes. It hashes stdout, stderr, the child source, ready marker, archived executable, and executed producer script. A generated test-only HMAC key stays outside the raw archive. The workflow uploads that key as a separate artifact. This key aids replay integrity. It is not an approved production signing authority or numeric policy.

The [GitHub `workflow_dispatch` rule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch) requires this workflow file on the repository's default `main` branch before manual dispatch works. Publishing only a branch or tag does not enable dispatch. After independent review and publication on `main`, dispatch the exact candidate branch or tag:

```sh
gh workflow run performance-host-capacity-control.yml --ref PUBLISHED_BRANCH_OR_TAG
gh run view RUN_ID --json headSha --jq .headSha
```

Compare the run's `headSha` with the intended candidate SHA before using its evidence. Both artifact names include the executed SHA, runner OS, GitHub run ID, and attempt. Download the raw artifact and its matching key artifact for each OS. Replay from a checkout containing the exact executed commit:

```sh
python3 tools/performance/host_capacity_control.py verify --archive DOWNLOADED_RAW --trusted-key DOWNLOADED_KEY/operator.key --expected-source-commit EXACT_CANDIDATE_SHA
```

The public verifier requires the independently supplied candidate SHA and its Git source bytes. It checks the archived executed script bytes against that source. Only exact Git bytes or an exact LF-to-CRLF checkout conversion are accepted. It also checks the test-only signature, raw hashes, child PID marker, executable bytes, clock order, method, terminal exit, and counter relationship. It does not need the source host's executable path after download. A successful replay returns `diagnostic: verified` and `qualification: unpassed`. A failure returns a nonzero exit and `qualification: unpassed`. The exact run URL, artifact digests, and public replay results must be retained before claiming either hosted helper was observed.

This diagnostic cannot establish a row-specific stress policy. The [delegated decision](https://github.com/rubixhacker/dyn4k/issues/17#issuecomment-6246347463) requires independent reference overhead, monitor validation, units, and host capacity before a numeric ceiling is frozen. All 28 reference rows remain unvalidated. No 600-second run is part of this workflow.
