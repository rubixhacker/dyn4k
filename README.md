# dyn4k

An independently evolving Kotlin Multiplatform fork of dyn4j 6.0.0, with an idiomatic Kotlin API and a thin, fixed-version compatibility shim.

The assembled implementation includes the dyn4k engine, Kotlin facade, and baseline compatibility shim across the agreed 21 targets, 28 target/runtime families, and 112 qualification lanes. See the [source inventory](docs/verification/complete-common-corpus.md) and [open qualification status](docs/verification/qualification-harness.md) for current evidence and remaining gates.

Qualification remains open. The inventory and configured lane count describe scope; they do not establish a passing exact-source release candidate or completed runtime qualification.

Public repository: [rubixhacker/dyn4k](https://github.com/rubixhacker/dyn4k).

- [Complete-port specification](https://github.com/rubixhacker/dyn4k/issues/32)
- [Implementation work and evidence](docs/planning/implementation-ledger.md)

- [Decision map](https://github.com/rubixhacker/dyn4k/issues/1)
- [Agreed charter](docs/planning/charter.md)
- [Domain language](CONTEXT.md)
- [GitHub issue tracker](docs/agents/issue-tracker.md)
- [Complete source inventory](docs/verification/complete-common-corpus.md)
- [Complete suite manifest](docs/verification/full-suite-manifest.md)
- [Runtime qualification harness](docs/verification/qualification-harness.md)
- [Consumer migration and usage guide](docs/guide/migration.md)

