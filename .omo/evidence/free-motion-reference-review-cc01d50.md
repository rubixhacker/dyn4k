# Exact free-motion review evidence receipt

Worktree: /tmp/dyn4k-free-motion-reference-review-20261014

Executed full discovery: `python3 docs/research/free-motion-reference-review-fetch.py .omo/evidence/free-motion` (exit 0). It validated 408 tar headers and downloaded 4,154,226 bytes in 409 bounded HTTP 206 requests. Target raw hash matched.
Executed streaming audit: `python3 docs/research/free-motion-reference-review-audit.py .omo/evidence/free-motion .` (exit 0).
Executed direct shortcut and repeated audit: `python3 docs/research/free-motion-reference-review-fetch.py .omo/evidence/free-motion-fast 19804447744` followed by the same auditor against that directory (both exit 0). Two requests transferred 3,945,842 bytes. Full-walk and shortcut audit outputs match apart from retrieval counts.

Artifacts: `.omo/evidence/free-motion/` and `.omo/evidence/free-motion-fast/` in that worktree retain retrieved bytes, assets.json, ranges.json, visited-headers.json, retrieval.json and manifest.json. All report/helper/manifest files committed; evidence directories remain untracked.

Final commands: git rev-parse HEAD; git ls-remote origin refs/heads/research/free-motion-reference-review; sha256sum raw member + committed manifest/helpers; Python reads and asserts full audit result; git diff --check. Actual output (exit 0):

```text
cc01d509b5de6f10ebb410b58a37f8722a43d5c7
cc01d509b5de6f10ebb410b58a37f8722a43d5c7	refs/heads/research/free-motion-reference-review
4981795bffcd2a0262040acb53c60b20607fea14a2a0c7d79e858ba68e7f2743  .omo/evidence/free-motion/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz
090e8865325707c4a40b1b71c3a652d3a22fab4b6a21e19c23e55cd126f5f117  docs/research/free-motion-reference-review-manifest.json
d4344761e4233d5d65b67e8de71af81fdd724d2e1ff97d2d72c7479607655d88  docs/research/free-motion-reference-review-fetch.py
d3a392805d686e0918419c83d944b997b363dd917289154405d0e72aec81978f  docs/research/free-motion-reference-review-audit.py
{
  "record_counts": {
    "inputs": 1,
    "event": 108001,
    "state": 36000
  },
  "state_event_audit": "PASS",
  "analytical_position": {
    "formula": "initial_position[axis] + initial_velocity[axis] * (step * fixed_dt)",
    "units": "metres",
    "samples_per_axis": 36000,
    "absolute_limit_per_axis": 1e-10,
    "relative_limit": 0,
    "maximum_absolute_errors_xy": [
      5.425704330264125e-11,
      2.7128521651320625e-11
    ],
    "maximum_error_steps_xy": [
      35997,
      35997
    ],
    "first_violating_steps_xy": [
      null,
      null
    ],
    "result": "PASS"
  },
  "approval": "PENDING_HUMAN_APPROVAL"
}
```

Outcome: exact reference candidate prepared and published; raw verification and approved per-step analytical check pass. Reference selection remains a live human decision. No engine execution, new tolerance, complete-part/archive verification or cross-target claim is made.
