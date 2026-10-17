# Port implementation ledger

Spec: [Complete the dyn4j 6.0.0 Kotlin Multiplatform port](https://github.com/rubixhacker/dyn4k/issues/32).

Integration branch: `codex/dyn4k-port`. Starting main revision: `2925a86d2b9bcdbc512f71b476ec00f02509e8b0`.

The user authorized implementation, recommended remaining choices, and GitHub publication on 2026-10-17. Use ISO 24495-1 and ISO 24495-3 for human-readable text and ASD-STE100 for new code comments.

## Work graph

- [Run the fixed baseline corpus and inventory its compatibility surface](https://github.com/rubixhacker/dyn4k/issues/45): Luna baseline and Sol verifier repair merged; acceptance verified and ticket closed.
- [Resolve staged vector and transform consumers on the pinned toolchain](https://github.com/rubixhacker/dyn4k/issues/33): Sol foundation merged; independent review and staged consumers passed; ticket closed.
- [Create and query every baseline shape through both APIs](https://github.com/rubixhacker/dyn4k/issues/34): Sol; active on `codex/port-geometry`.
- [Traverse and mutate baseline tree data structures](https://github.com/rubixhacker/dyn4k/issues/46): Sol; active on `codex/port-trees`.
- [Use baseline filters, bounds, and collision objects from consumers](https://github.com/rubixhacker/dyn4k/issues/35): Sol; not started.
- [Turn input polygons into usable convex shapes](https://github.com/rubixhacker/dyn4k/issues/36): Sol; not started.
- [Run collision, distance, ray, and time-of-impact queries](https://github.com/rubixhacker/dyn4k/issues/37): Sol; not started.
- [Apply forces and inspect body state through both APIs](https://github.com/rubixhacker/dyn4k/issues/38): Sol; not started.
- [Step interacting bodies with callbacks and continuous collision](https://github.com/rubixhacker/dyn4k/issues/39): Sol; not started.
- [Simulate every baseline joint and supported joint mode](https://github.com/rubixhacker/dyn4k/issues/40): Sol; not started.
- [Build and extend a simulation with the idiomatic Kotlin API](https://github.com/rubixhacker/dyn4k/issues/41): Sol; not started.
- [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42): Sol; not started.
- [Qualify staged artifacts on every required runtime](https://github.com/rubixhacker/dyn4k/issues/43): Sol; independent harness active on `codex/port-qualification-harness`; full acceptance remains blocked by compatibility and performance evidence.
- [Guide consumers through migration and explain qualification results](https://github.com/rubixhacker/dyn4k/issues/44): Luna; not started.

## Evidence rules

- Record the actual model from session `turn_context`. The role launcher forced Astra despite model overrides. Explicit `codex exec -m gpt-6-sol` and `-m gpt-6-luna` recorded the requested models.
- Use separate ticket branches and worktrees based on the integration branch. Merge the latest integration branch into each ticket branch before handoff.
- Close a ticket only when all acceptance criteria have evidence. Keep failed and unavailable qualification separate.
- Review the integrated diff with independent standards and spec reviewers. Run the retrospective after review.

## Integrated evidence

- Baseline verifier repair: `53aa120a3e0111823c36bb8e20ecdf0d56caf7b1` merges `5f0601100ebb19e965e51dea15995570763b5d04`. The merged verifier ran 2,385 unchanged baseline cases with zero failures or ignored cases, and its four regression tests passed. It inventories 268 production source files, 199 test files, 2,171 test annotations, and 297 baseline binary types. See `/tmp/dyn4k-baseline-fix-result.md` and `/tmp/dyn4k-merge-baseline-fix-result.md`. This evidence does not qualify the incomplete candidate.
- The pinned upstream geometry algorithm packages import geometry and root tree/reference APIs, but no collision model APIs. [Turn input polygons into usable convex shapes](https://github.com/rubixhacker/dyn4k/issues/36) now depends on the geometry and tree tickets. Its acceptance criteria are unchanged.
- Foundation: `550d662e5a54c368ebbba97454fa7ce27cb80ea8` merges the complete Sol foundation branch. A separate Sol review found a common `Copyable` generic-bound defect, then verified its repair against the staged Kotlin and Java consumers. The merged head passed 133 unchanged upstream foundation tests, 7 common tests each on JVM/Linux x64/Android host, 12 Java consumer checks on each tested archive, and selective baseline signature checks on seven types. Staged external Kotlin resolution passed. See `/tmp/dyn4k-foundation-result.md`, `/tmp/dyn4k-foundation-rereview-result.md`, and `/tmp/dyn4k-merge-foundation-result.md`. All-target runtime and complete-library qualification remain open.

## Open qualification limits

The default sleep/wake physical check has a retained baseline failure. The configured-profile evidence does not replace it. Required Apple devices, other unavailable runtimes, performance probes, and remaining numerical comparator qualification are open obligations. See [acceptance decisions and evidence](acceptance-implementation.md).
