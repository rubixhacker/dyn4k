# Root verification record

Revision: cd610b696f1f7be2f3c1590840139a7cc596b04c
Branch: task/sleep-wake-exact-checks
Worktree: /tmp/dyn4k-sleep-wake-exact-checks (locked for review)

manualQa: PASS for this exact revision's code/test/artifact bytes.
selfReview: PASS for this exact revision; no independent certification claimed.

Authority: /tmp/dyn4k-wayfinder-next-handoff-20261014.md and live acceptance checkpoint https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6167266418. Bounded exact checks only; no engine, new budgets or physics experiment.

Artifacts and observed commands:
- `node --check docs/research/sleep-wake-exact-checks.mjs` and test file: exit 0.
- `SLEEP_EVIDENCE=/tmp/dyn4k-sleep-wake-numerical-budgets/.omo/evidence/sleep-wake-budget-review/dyn4k-sleep-evidence node --test --test-reporter=tap docs/research/sleep-wake-exact-checks.test.mjs`: exit 0; 649 passed, 0 failed/skipped/cancelled. Transcript: /tmp/dyn4k-sleep-exact-final-tests.tap.
- CLI over the same extracted evidence: exit 0; published observations are docs/research/sleep-wake-exact-observations.json, hash 072ee5e01a336732555442da8087562b9ccab98992a03d422c6826239e9b894f.
- Archive sha256sum: 89d88301ad5ea14a621d8a6e86bfc3dfc90f84a0d7e8abda65f2f526de1b5bee.
- Staged diff inspection and `git diff --cached --check`: exit 0, only four in-scope new files.
- Historical auditor and reference/budget manifests: no diff from parent 884ff5a6c2c1fe81384b9522511d5d7ef0d42e89.

Six approved groups traced against immutable detailed report; initial previous copies, pre/post impulse copy phases, within-run sleep freezes, property aliases and timestep initialization checked. Main session ran actual public functions and CLI. Tests separate semantic rejection from hash-guard rejection, and cover permitted boundaries. No blocker found in bounded scope.

Limits: no port, runtime, numerical callback comparator or full acceptance qualification. Existing all-target commitments and unresolved dynamic/physical budgets retained. Acceptance decision remains open.
