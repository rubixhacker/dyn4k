# Nominal comparator root verification

Task: https://github.com/rubixhacker/dyn4k/issues/23

Reviewed exact-rational ties-to-even decoding, bounded normal/zero scope and integer exact-range guard, interval absolute/minimum operations, complete wrapped-angle branch enumeration, phase reduction, inclusive-cap classification, and full previous-transform inheritance. Reviewed independent halfway, binade, signed-zero, endpoint, wrap-cut, mutation and rejection cases. This is manual mathematical review and executed bounded checking, not formal machine verification.

Independent full replay command (exit 0):

```sh
python3 docs/research/nominal-rotation-comparator.py /tmp/dyn4k-free-motion-reference-review-20261014/.omo/evidence/free-motion/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz /tmp/dyn4k-comparator-root-verification-20261014
```

Working tree: /tmp/dyn4k-nominal-rotation-comparator.

Result: PASS; 36,000 states, 108,001 events; all 144,000 current rotational comparisons and all 36,000 full previous-transform inheritance comparisons pass; no FAIL/INCONCLUSIVE.

- Checker SHA-256: 181440967b44e3e52427dd905ca9854acb9114c5305719a8fe3a0749f98b29ba
- Numeric helper SHA-256: c7955aeb9a6a0a97decaf015f1382b4ac0be0a187f849fc0ad5fdea15fa96c09
- Oracle SHA-256: 710b70f0bcc780dd81883ef1d9971b7b6c6b47e78c86a3a5dd07f3d1edb2b97b
- Comparison rows SHA-256: 733dc97d76d7ec3a55f71354fbc435df3ce4b00f3d0d914dab3569b4203b8436
- Inheritance rows SHA-256: 1e7d05a14cd1c8bf27ff4d847c374e97cc4f65008f27739fe848284a8333e031

Raw, input-header and full stream hashes match frozen identities. Historical hidden primitive calls remain unqualified; actual baseline-to-port comparison has not run because no port trajectory exists; all port runtime qualifications remain unpassed.

Independent boundary/decoder verification (exit 0):

```sh
python3 docs/research/nominal-rotation-comparator-verify.py /tmp/dyn4k-free-motion-reference-review-20261014/.omo/evidence/free-motion/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz /tmp/dyn4k-comparator-root-boundaries-20261014
```

All halfway, binade, endpoint, wrap-cut, synthetic differential, inheritance mutation and rejection cases passed. Every one of 251,640 distinct archived floating tokens agrees with the independent CPython float parser. Verification script SHA-256: e26e550d2a382e4b3ea54776d3eb9a42fc92f8bb4918edbcf4f6ca7b3f8210c0.

Confirmed final tested checker includes begin/end comparator/helper source hash checks (lines 121-122 and 198-200); oracle source identity is enforced before calculation. Report/source bindings are consistent.
