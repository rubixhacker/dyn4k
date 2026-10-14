# Approved separate-quality penetration audit

**PASS for the represented-geometry penetration gate of these six frozen configured captures:** all **432,000 internal states** pass their approved ceilings; all **252,000 outer-endpoint mappings** are valid and inherit passing results. There are **zero state failures and zero endpoint failures**. Endpoints duplicate internal observations and are not counted as additional physics steps.

This is not overall physics acceptance, a port/runtime qualification, or a default-settings quality pass. The [original default-settings audit](sleep-wake-penetration-acceptance.md) remains **failed: 125,847 of 126,000 states**. No physics was run, no ceiling widened, and no reference, algorithm or default changed here.

Supports [Evaluate approved separate-quality penetration acceptance](https://github.com/rubixhacker/dyn4k/issues/30). The [live approval](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6174366120) selects repetition 1 at each outer cadence as the reference, retains repetition 2 as corroboration, and freezes the inclusive internal-step schedule below. Historical pending labels in the immutable [candidate manifest](sleep-wake-quality-candidate-manifest.json) precede this approval.

## Binding identities and exact measurement

Manifest revision: `a7718eb6380b8fc51179a953dff4f3f33949c801`; SHA-256 `7efd60aa76cab10fdc27eb8e968a2868e854433cc4556e10257dbd290a63e554`. [Lossless archive](https://github.com/rubixhacker/dyn4k/releases/download/sleep-wake-quality-candidate-20261014/dyn4j-sleep-wake-quality-20261014.tar.gz) SHA-256: `057d96767dcf4ef863afb61417f8ef9cc6b7fc1442e0e39df55bbe006cb1212c`. A fresh remote download matched the local archive byte-for-byte. The new [bounded evaluator](sleep-wake-quality-acceptance.mjs) checks that archive hash, the frozen manifest hash, every manifest-listed source/class/JAR/runtime-metadata hash, all six gzip hashes, each input hash and each full decompressed-stream hash. These guards establish artifact identity, not runtime qualification. The [observations](sleep-wake-quality-acceptance-observations.json) retain the identities alongside each separate result.

The evaluator imports only `depth`, `accepts`, `SCALE` and `checkGeometry` from the unchanged [prior exact-math module](sleep-wake-penetration-acceptance.mjs), SHA-256 `6b5e633814b7fd11404f53362a500e45371dc3210e295f5ea59fb0401d11e52f`. It does **not** import or modify that module's original phase schedule. The new schedule uses internal indices, independent of outer cadence and observed sleep flags.

The checked observable is mathematical geometry represented by the stored binary64 affine coefficients: the deepest of the square's four transformed vertices below floor top zero, `max(0,(abs(s)+abs(c))/2−ty)`. The pinned [Rectangle constructor](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Rectangle.java#L80-L84) and [Transform mapping](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Transform.java#L246-L257) establish these coordinates. The input guards verify square vertices `(±1/2,±1/2)` and floor vertices `(±10,±1/4)`; the [frozen driver](https://github.com/rubixhacker/dyn4k/blob/82395ce9c39f7a0973f71ecb025275d8a496683e/docs/research/sleep-wake-quality-capture/SleepWakeQuality.java) creates that unchanged geometry. Each state verifies finite coefficients, body identities, the floor's identity rotation/translation `(0,−1/4)`, and exact horizontal square extent within the finite floor span `[-10,10]`. Source and stream identities bind fixture immutability; per-step records themselves do not reserialize fixture vertices.

The reused decoder represents each finite binary64 exactly as a BigInt multiple of `2^-1075`; halving the coefficient sum remains exact even for subnormals. Comparisons use exact rational ceilings `0`, `1/100`, `1/200`, `1/1000` through integer arithmetic, with equality permitted and no numerical allowance. No normalized rotation, center-height approximation, callback depth or floating-point ceiling literal substitutes for the geometric test. Approximate decimals below are presentation only; exact reduced minima, maxima and signed headroom fractions are in observations.

## Complete results

Each stream was read and checked directly, including corroborating repetitions; equality of earlier traces was not used to skip a capture.

| Outer cadence | Repetition | Role | Internal states passed | Outer endpoints verified/passing | Failures |
|---|---:|---|---:|---:|---:|
| 30 Hz | 1 | Approved reference | 72,000 | 18,000 | 0 |
| 30 Hz | 2 | Corroboration | 72,000 | 18,000 | 0 |
| 60 Hz | 1 | Approved reference | 72,000 | 36,000 | 0 |
| 60 Hz | 2 | Corroboration | 72,000 | 36,000 | 0 |
| 120 Hz | 1 | Approved reference | 72,000 | 72,000 | 0 |
| 120 Hz | 2 | Corroboration | 72,000 | 72,000 | 0 |

Every capture has the following per-phase counts and maxima. These maxima and their locations are observations, not new limits. Exact maxima and nearest-to-ceiling headrooms agree with the independent oracle in all **36 case/phase combinations**.

| Phase | Inclusive internal indices | States per capture | Ceiling, m | Maximum penetration, approximate m | First maximizing step |
|---|---|---:|---:|---:|---:|
| initial-approach | 1–4 | 4 | 0/1 | 0 | 1 |
| impact | 5–7 | 3 | 1/100 | 0.004083333333333328 | 6 |
| initial-settling | 8–65 | 58 | 1/200 | 0.0006395658955666427 | 8 |
| rest-before | 66–36000 | 35,935 | 1/1000 | 0.0002441535540929695 | 66 |
| wake-settling | 36001–36083 | 83 | 1/200 | 0.0002441514414041744 | 36001 |
| rest-after | 36084–72000 | 35,917 | 1/1000 | 0.0002441406250039669 | 36084 |

All 36 internal failure-range lists and all 36 outer-frame failure-range lists are empty. The closest approach samples have zero depth and zero headroom, which passes the inclusive zero ceiling. Every positive-ceiling phase retains strictly positive exact headroom. The companion observations include each minimum, maximum, first extremal step, closest-boundary step and signed rational margin; no uncertain comparison is counted as passing.

Each outer endpoint is required immediately after its corresponding internal state; index, outer frame and full state equality are checked before inheriting the exact measurement and phase. Frame `j` maps to internal index `j*(120/outerHz)`. Missing, extra, mismatched or non-endpoint rows cannot silently add, drop or relabel a sample. Endpoint counts per phase are as follows, for **each repetition**:

| Phase | Outer 30 Hz | Outer 60 Hz | Outer 120 Hz |
|---|---:|---:|---:|
| Initial approach | 1 | 2 | 4 |
| Impact | 0 | 1 | 3 |
| Initial settling | 15 | 29 | 58 |
| Rest before action | 8,984 | 17,968 | 35,935 |
| Wake settling | 20 | 41 | 83 |
| Rest after wake | 8,980 | 17,959 | 35,917 |

The 30 Hz grouping has no outer endpoint during the impact interval, but all three internal impact states were checked. Checking outer endpoints alone would miss this interval.

## Independent checks and reproduction

The [adaptation tests](sleep-wake-quality-acceptance.test.mjs) pass **65 semantic assertions**, covering every new phase edge and immediate neighbour, complete internal/endpoint phase counts, wake indexing at every outer cadence, state grouping, full endpoint mismatch rejection, wrong body identity and nonfinite coefficients. Three separate identity mutations—archive bytes, runtime metadata and one gzip—are rejected by the corresponding hash guards. The unchanged prior suite passes **295 semantic/arithmetic assertions** plus its two source/gzip mutation checks, including exact zero, representable equality, decimal-ceiling adjacent binary64 values, independent four-vertex sign/extreme cases and fixture/span guards. Hash rejection is not presented as semantic comparison coverage.

The main session separately audited all six frozen streams with Python `Fraction.from_float` and explicit four-vertex enumeration, including finite floor geometry/span and outer endpoint equality. Comparison with that independent result matches all 432,000 state results, all 252,000 endpoint counts/results, and all 36 phase counts, failure ranges, exact rational maxima/maximizing indices and exact nearest headrooms/indices. This independently checks both the reused arithmetic and the new binding/schedule adaptation.

From this branch, using Node.js (captured version in evidence) and the extracted approved package:

```sh
node docs/research/sleep-wake-quality-acceptance.test.mjs EXTRACTED_PACKAGE ARCHIVE
node docs/research/sleep-wake-penetration-acceptance.test.mjs ORIGINAL_EXTRACTED_SLEEP_EVIDENCE
node docs/research/sleep-wake-quality-acceptance.mjs EXTRACTED_PACKAGE ARCHIVE observations.json
cmp observations.json docs/research/sleep-wake-quality-acceptance-observations.json
```

Expected evaluator exit: **0** with `REPRESENTED_BASELINE_GEOMETRY_PASS`. Exit 2 would retain physical failures; exit 1 means invalid/incomplete evidence and cannot establish a pass. Complete failed internal/outer ranges would be emitted if any existed. Every failed internal sample is reproducible from its frozen stream and range; here every range is empty.

| Scenario | Invocation / binary observable | Captured artifact relative to this worktree |
|---|---|---|
| Remote archive identity | fresh `curl -fL` of archive above, `sha256sum`, `cmp` with local archive; matching hash and exit 0 | `.omo/evidence/quality-acceptance/remote-identity.log`, `download.log`, fresh `remote/` archive |
| New phase/endpoint semantics and hash rejection | first test command above; exit 0, 65 assertions and three hash rejections | `.omo/evidence/quality-acceptance/tests.log` |
| Reused exact arithmetic and geometry | second test command above; exit 0, 295 assertions and two hash rejections | `.omo/evidence/quality-acceptance/exact-math-tests.log` |
| All six exact physical audits | evaluator command above; exit 0, 432,000 passing states and 252,000 verified endpoints | `.omo/evidence/quality-acceptance/audit.log`, `observations.json` |
| Independent oracle and published output | `node .omo/evidence/quality-acceptance/compare-oracle.mjs`; exit 0, exact 36-phase agreement and published/captured byte equality | `.omo/evidence/quality-acceptance/oracle-comparison.log` |

The local ledger is `.omo/evidence/quality-acceptance/README.md`; the parent owns its separately captured oracle implementation/output. This work changes only this new bounded wrapper, tests, observations and report; the default-settings evaluator and its recorded failures remain intact.

## Qualification boundary

This result establishes the approved penetration requirement for **stored-coefficient geometry of this configured baseline profile**: tolerance `1/4096 m`, maximum eight position iterations, fixed internal `1/120 s`, grouped 4/2/1 for the outer cadences. It establishes neither native 30/60 Hz single-step quality nor any default-settings improvement. It does not establish platform getter rounding equivalence, hidden intermediate simulation accuracy, other physical requirements, callback/contact/TOI numerical budgets, actual baseline-to-port parity, all-target execution, performance or release support. Those remain separate unresolved or unpassed gates. Every in-scope target remains required, and [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7) remains open.
