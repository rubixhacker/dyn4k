# Remaining free-motion metric research receipt

Worktree: /tmp/dyn4k-free-motion-remaining-20261014
Branch: research/free-motion-remaining-metrics
Published commit: d59094416267583d9344d154b8b9a85d855882af

Scenario: exact approved nominal gzip, 36000 completed states, all remaining dynamic numerical channels and duplicate/derived relationships.
Invocation (worktree above):
`python3 docs/research/free-motion-remaining-metrics-audit.py /tmp/dyn4k-free-motion-reference-review-20261014/.omo/evidence/free-motion/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz . .omo/evidence/free-motion-remaining/measured > .omo/evidence/free-motion-remaining/audit.log`

Binary observable: audit exited0, mandatory gzip/header/stream hashes and state/event schema/order passed, no metric with an explicit comparison limit failed. All rotational limits remain unapproved; their diagnostics are not acceptance passes.

Captured artifacts:
- /tmp/dyn4k-free-motion-remaining-20261014/.omo/evidence/free-motion-remaining/audit.log
- /tmp/dyn4k-free-motion-remaining-20261014/.omo/evidence/free-motion-remaining/measured/manifest.json
- /tmp/dyn4k-free-motion-remaining-20261014/.omo/evidence/free-motion-remaining/measured/samples.jsonl
- /tmp/dyn4k-free-motion-remaining-20261014/.omo/evidence/free-motion-remaining/precision-check.txt

Additional scenario: copied auditor using precision100 / Taylor termination1e-85 instead of75 /1e-65; output at sibling higher-precision/. All metric summaries matched. Initial strict whole-file equality expectation failed: two unit-circle defects differed by one final binary64 ulp. Revised inspection verified exact scope and recorded these differences, rather than asserting identical sample files. No numerical acceptance limit was widened.

Publication invocation: git rev-parse HEAD; git ls-remote origin refs/heads/research/free-motion-remaining-metrics. Final verification parsed both manifests, verified equality of committed/fresh manifests, auditor and per-step hashes,36000 samples for each metric and absence of explicit-limit failures, then git diff --check and git status --short.

Actual final command output (exit 0):
```text
d59094416267583d9344d154b8b9a85d855882af
d59094416267583d9344d154b8b9a85d855882af	refs/heads/research/free-motion-remaining-metrics
PASS: all35 metrics have36000 samples; no supplied comparison failure; committed manifest, auditor and sample hashes match fresh run.
Counts: {'inputs': 1, 'event': 108001, 'state': 36000}
current_getCost {'samples': 36000, 'maximum_absolute_residual': 1.811470423674861e-12, 'maximum_step': 35814, 'limit': None, 'first_violation': None, 'role': 'diagnostic_limit_missing', 'status': 'DIAGNOSTIC_NO_APPROVED_LIMIT'}
current_getSint {'samples': 36000, 'maximum_absolute_residual': 1.820148267512173e-12, 'maximum_step': 36000, 'limit': None, 'first_violation': None, 'role': 'diagnostic_limit_missing', 'status': 'DIAGNOSTIC_NO_APPROVED_LIMIT'}
current_orientation_rad {'samples': 36000, 'maximum_absolute_residual': 1.3912021084299924e-09, 'maximum_step': 35814, 'limit': None, 'first_violation': None, 'role': 'diagnostic_limit_missing', 'status': 'DIAGNOSTIC_NO_APPROVED_LIMIT'}
unwrapped_rotation_rad {'samples': 36000, 'maximum_absolute_residual': 1.4258530918465073e-09, 'maximum_step': 35814, 'limit': None, 'first_violation': None, 'role': 'diagnostic_limit_missing', 'status': 'DIAGNOSTIC_NO_APPROVED_LIMIT'}
force_zero {'samples': 36000, 'maximum_absolute_residual': 0.0, 'maximum_step': 1, 'limit': 0, 'first_violation': None, 'role': 'proposed_fixture_specific_check', 'status': 'PASS'}
previous_equals_prior_current {'samples': 36000, 'maximum_absolute_residual': 0.0, 'maximum_step': 1, 'limit': 0, 'first_violation': None, 'role': 'proposed_fixture_specific_check', 'status': 'PASS'}
Per-step sample SHA256: ae0930ea9d209e68deb91304aadba40bccb82c717c512487832b5c50cea6e25d
Auditor SHA256: e7bbd4273505a6491b63ac6fd02a6de3eaa5bd10300f0f901889cbed81dfd4c6
PASS: all35 metric summaries identical for precision75/termination1e-65 vs precision100/termination1e-85. The only two per-step differences are one binary64 ulp in unit-circle-defect conversion; no claimed cross-libm proof.
[
  [
    260,
    "current_unit_circle_defect",
    2.6409149280091637e-14,
    2.6409149280091634e-14
  ],
  [
    261,
    "previous_unit_circle_defect",
    2.6409149280091637e-14,
    2.6409149280091634e-14
  ]
]

?? .omo/
```

Judgment: bounded research published and remote verified. Proposed source-grounded exact checks remain pending human approval. Rotational budgets, baseline-versus-port comparison rules and all-target execution remain explicit blockers; no physics regenerated and no engine changes. Only untracked local .omo evidence remains.

