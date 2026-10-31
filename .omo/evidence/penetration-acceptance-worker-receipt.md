# Execution evidence: physical FAIL, research audit complete

Worktree: /tmp/dyn4k-sleep-wake-penetration-acceptance
Frozen root: /tmp/dyn4k-sleep-wake-numerical-budgets/.omo/evidence/sleep-wake-budget-review/dyn4k-sleep-evidence
No active attempt directory: `omo-agent-toolkit ulw-loop status --json` reported ULW_LOOP_PLAN_MISSING.

Commands, binary observables, captured artifacts:

1. `sha256sum /tmp/dyn4k-sleep-wake-numerical-budgets/.omo/evidence/sleep-wake-budget-review/dyn4j-sleep-wake-20260914.tar.gz`: published hash match in archive.log (also Node version).
2. `node docs/research/sleep-wake-penetration-acceptance.test.mjs /tmp/dyn4k-sleep-wake-numerical-budgets/.omo/evidence/sleep-wake-budget-review/dyn4k-sleep-evidence`: exit0, 295 semantic assertions, source/gzip mutations each reject exit1, tests.log.
3. `node docs/research/sleep-wake-penetration-acceptance.mjs /tmp/dyn4k-sleep-wake-numerical-budgets/.omo/evidence/sleep-wake-budget-review/dyn4k-sleep-evidence .omo/evidence/penetration-acceptance/audit`: exit2 (physical FAIL), audit.log, audit/observations.json, audit/failures.jsonl.gz. 126000 states, 125847 failures, 153 passes. No engine run.
4. `python3 .omo/evidence/penetration-acceptance/validate.py`: exit0, validation.log; byte-identical published observations, hash matches full details, every failed row exact rational depth/excess and unique membership in full failure ranges verified.

Pinned Transform.java, Rectangle.java and SequentialImpulses.java downloaded from dyn4j revision058bf6d982a0fb89b54050f929f6ea9dae53b714 for source inspection are captured alongside.
Parent independently checked every state using Fraction.from_float and explicit four vertices; parent owns oracle evidence. No claim of port/runtime qualification.

Remote verified revision: b7af287c3581f402053511d9556d65e610d71a5e
Canonical local ledger: /tmp/dyn4k-sleep-wake-penetration-acceptance/.omo/evidence/penetration-acceptance/README.md
