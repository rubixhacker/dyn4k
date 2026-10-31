# Reference packet publication verification

Worktree: /tmp/dyn4k-initial-reference-review-20261014

Invocations: git rev-parse HEAD; git ls-remote origin refs/heads/research/initial-reference-review; sha256sum docs/research/initial-reference-review-manifest.json docs/research/initial-reference-review-audit.py; Python JSON assertions against the fresh full selection manifest; git diff --check.

Actual command output (exit code 0):

```text
4674e089d6f968bf752741f2be85cf2048962552
4674e089d6f968bf752741f2be85cf2048962552	refs/heads/research/initial-reference-review
b42174c7523bea9687e4ab015a215b4e652c2446df73d2f41e836e8a165c1208  docs/research/initial-reference-review-manifest.json
6fd5a7da3f39bc27fc374119808c3a5ed331b955dfe5c7a72d1f81ff57690f46  docs/research/initial-reference-review-audit.py
Internal checksum entries verified: 31
Unique states: 126000
Ordered listener events: 1637943
Fresh stream audits: ['PASS', 'PASS', 'PASS']
Free motion: RAW_TRACE_NOT_RECHECKED_NOT_READY_TO_FREEZE
```

The final full auditor was executed with `python3 docs/research/initial-reference-review-audit.py .omo/evidence/reference-review .` and exited 0. Its full result is /tmp/dyn4k-initial-reference-review-20261014/.omo/evidence/reference-review/selection-manifest.json; the actual 31 checksum outputs are in internal-checksums.log alongside it. Counts above are freshly read and asserted from that artifact. Remote revision and committed manifest/auditor hashes match the published packet. Free-motion raw verification remains unresolved; human reference selection and numerical tolerance approvals remain pending.
