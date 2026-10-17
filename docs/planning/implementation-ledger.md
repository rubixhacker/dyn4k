# Port implementation ledger

Spec: [Complete the dyn4j 6.0.0 Kotlin Multiplatform port](https://github.com/rubixhacker/dyn4k/issues/32).

Integration branch: `codex/dyn4k-port`. Starting main revision: `2925a86d2b9bcdbc512f71b476ec00f02509e8b0`.

The user authorized implementation, recommended remaining choices, and GitHub publication on 2026-10-17. Use ISO 24495-1 and ISO 24495-3 for human-readable text and ASD-STE100 for new code comments.

## Work graph

- [Run the fixed baseline corpus and inventory its compatibility surface](https://github.com/rubixhacker/dyn4k/issues/45): Luna; implementation in progress.
- [Resolve staged vector and transform consumers on the pinned toolchain](https://github.com/rubixhacker/dyn4k/issues/33): Sol; implementation in progress.
- [Create and query every baseline shape through both APIs](https://github.com/rubixhacker/dyn4k/issues/34): Sol; not started.
- [Use baseline trees, filters, bounds, and collision objects from consumers](https://github.com/rubixhacker/dyn4k/issues/35): Sol; not started.
- [Turn input polygons into usable convex shapes](https://github.com/rubixhacker/dyn4k/issues/36): Sol; not started.
- [Run collision, distance, ray, and time-of-impact queries](https://github.com/rubixhacker/dyn4k/issues/37): Sol; not started.
- [Apply forces and inspect body state through both APIs](https://github.com/rubixhacker/dyn4k/issues/38): Sol; not started.
- [Step interacting bodies with callbacks and continuous collision](https://github.com/rubixhacker/dyn4k/issues/39): Sol; not started.
- [Simulate every baseline joint and supported joint mode](https://github.com/rubixhacker/dyn4k/issues/40): Sol; not started.
- [Build and extend a simulation with the idiomatic Kotlin API](https://github.com/rubixhacker/dyn4k/issues/41): Sol; not started.
- [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42): Sol; not started.
- [Qualify staged artifacts on every required runtime](https://github.com/rubixhacker/dyn4k/issues/43): Sol; not started.
- [Guide consumers through migration and explain qualification results](https://github.com/rubixhacker/dyn4k/issues/44): Luna; not started.

## Evidence rules

- Record the actual model from session `turn_context`. The role launcher forced Astra despite model overrides. Explicit `codex exec -m gpt-6-sol` and `-m gpt-6-luna` recorded the requested models.
- Use separate ticket branches and worktrees based on the integration branch. Merge the latest integration branch into each ticket branch before handoff.
- Close a ticket only when all acceptance criteria have evidence. Keep failed and unavailable qualification separate.
- Review the integrated diff with independent standards and spec reviewers. Run the retrospective after review.

## Open qualification limits

The default sleep/wake physical check has a retained baseline failure. The configured-profile evidence does not replace it. Required Apple devices, other unavailable runtimes, performance probes, and remaining numerical comparator qualification are open obligations. See [acceptance decisions and evidence](acceptance-implementation.md).
