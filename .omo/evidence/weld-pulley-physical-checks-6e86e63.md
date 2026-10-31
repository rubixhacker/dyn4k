# Weld/Pulley physical-check research verification receipt

Working tree: /tmp/dyn4k-weld-pulley-20261014
Published branch: research/weld-pulley-physical-checks
Commit: 6e86e63683b2cbac8bda70da94d69d1266ac2563

## Scenario and invocation
The exact four pinned supplemental trace members were extracted from Git revision 0995a6bac84de882b0d04b6c3ea18162ca3b4a7c and independently audited with:
`python3 docs/research/weld-pulley-physical-checks-audit.py . .omo/evidence/weld-pulley/measured-final`

Binary observable: exit 0, four PASS audits and byte-identical corresponding repeat members. Fresh full measurements are at /tmp/dyn4k-weld-pulley-20261014/.omo/evidence/weld-pulley/measured-final/manifest.json and samples.jsonl.

Publication verification used git rev-parse HEAD and git ls-remote origin refs/heads/research/weld-pulley-physical-checks. Artifact identity used sha256sum on the committed manifest and auditor. Python independently read fresh measurement output and asserted PASS/completeness and counts; git diff --check exited 0.

## Actual captured verification output
```text
6e86e63683b2cbac8bda70da94d69d1266ac2563
6e86e63683b2cbac8bda70da94d69d1266ac2563	refs/heads/research/weld-pulley-physical-checks
2e424064ca14a3d27630f7197d3dfc929afda024d27741cb2427194c49784509  docs/research/weld-pulley-physical-checks-manifest.json
c4510fbeb9b7561d59a1c96cf7a82c07d7b2376537710eba18a24f23059a9adc  docs/research/weld-pulley-physical-checks-audit.py
Approval: PENDING_HUMAN_DECISION
Audits: [('P-JINT-Weld-enabled-equal-0.jsonl.gz', 'PASS', True), ('P-JINT-Pulley-slack-transition-preparation-0.jsonl.gz', 'PASS', True), ('P-JINT-Pulley-slack-transition-preparation-1.jsonl.gz', 'PASS', True), ('P-JINT-Pulley-slack-transition-0.jsonl.gz', 'PASS', True)]
Total states/events: 1203 5561
Weld {'equal_limits_enabled': {'steps': [1, 600], 'samples': 600, 'angle_rad': {'minimum': -0.0014456701862869353, 'minimum_step': 2, 'maximum': 0.0006125732000417096, 'maximum_step': 3}, 'anchor_gap_m': {'minimum': 5.438094419218942e-12, 'minimum_step': 34, 'maximum': 0.0010240181055693979, 'maximum_step': 1}}}
Pulley enabled residual {'minimum': -0.7061984767002047, 'minimum_step': 204, 'maximum': 0.1208278904872957, 'maximum_step': 209}
Pulley positive / above configured tolerance 48 39
```

Command exit code: 0

## Judgment
Research report, compact manifest and durable auditor are published at the verified remote commit. Completeness, finite values, ordering, exact identities, repeat equality and measured diagnostics passed. This establishes data evidence; it does not approve physical budgets or prove ideal angular locking/per-step inextensibility. Pulley has 39 enabled-phase samples above the configured linear tolerance; this is an observed diagnostic, not an adopted limit or a proven upstream bug. All proposed reference decisions remain PENDING_HUMAN_DECISION. No engine changes or new physics experiments were performed.

