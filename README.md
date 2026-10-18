# dyn4k

An independently evolving Kotlin Multiplatform fork of dyn4j 6.0.0, with an idiomatic Kotlin API and a thin, fixed-version compatibility shim.

At integration revision `23aa6bc4f086b929610d4260fd480cf77e8fafce`, the source inventory contains 2,515 test methods. It includes 2,454 core common, 58 facade common, and three facade JVM-only methods. The tracked suite manifest configures 21 targets, 28 target/runtime families, and 112 lanes. These counts describe scope, not qualification.

At that revision, the qualification recorder reports all 112 lanes as `NOT_RUN`. Earlier host and Android Native runs bind to earlier source revisions. No full exact-head runtime qualification exists for this revision. See the [complete corpus inventory](docs/verification/complete-common-corpus.md), [suite manifest](docs/verification/full-suite-manifest.md), and [qualification harness](docs/verification/qualification-harness.md).

Public repository: [rubixhacker/dyn4k](https://github.com/rubixhacker/dyn4k).

- [Complete-port specification](https://github.com/rubixhacker/dyn4k/issues/32)
- [Implementation work and evidence](docs/planning/implementation-ledger.md)

- [Decision map](https://github.com/rubixhacker/dyn4k/issues/1)
- [Agreed charter](docs/planning/charter.md)
- [Domain language](CONTEXT.md)
- [GitHub issue tracker](docs/agents/issue-tracker.md)
- [Foundation build and verification](docs/implementation/foundation.md)
- [Complete suite manifest](docs/verification/full-suite-manifest.md)
- [Runtime qualification harness](docs/verification/qualification-harness.md)
- [Consumer migration and usage guide](docs/guide/migration.md)

