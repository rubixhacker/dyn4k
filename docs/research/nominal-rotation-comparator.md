# Verified nominal rotation comparator and frozen baseline

Result for [Verify the nominal rotation comparator and frozen baseline](https://github.com/rubixhacker/dyn4k/issues/23): **all 144,000 current-metric checks and all 36,000 full previous-transform inheritance checks pass**, with zero failures and zero inconclusive results. This directly establishes the frozen baseline outputs' compliance with the [approved nominal rotational caps/model](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6162049136). It does not qualify historical hidden primitive calls, any dyn4k runtime, or a real baseline-to-port pair.

| Current metric | Checks / pass | Fail / inconclusive | Largest certified upper bound, rounded upward for display | Step | Approved absolute cap |
|---|---:|---:|---:|---:|---:|
| Cosine component | 36,000 / 36,000 | 0 / 0 | `1.811470424e-12` | 35814 | `7e-11` |
| Sine component | 36,000 / 36,000 | 0 / 0 | `1.820148268e-12` | 36000 | `7e-11` |
| Wrapped public angle, rad | 36,000 / 36,000 | 0 / 0 | `1.391202109e-9` | 35814 | `5e-8` |
| Unwrapped recorder sum, rad | 36,000 / 36,000 | 0 / 0 | `1.425853092e-9` | 35814 | `6e-8` |

The [compact evidence manifest](nominal-rotation-comparator-manifest.json) retains exact rational upper bounds, first-unpassed fields, runtime/tool identities and output hashes. No cap was derived from these measurements. Relative allowance remains zero. The complete preceding transform, including its rotation, matrix, translation and metadata fields, equals the initial/prior current transform in all 36,000 states under approved numerical equality; signed zeros compare equal. Previous-transform rotational acceptance therefore inherits the corresponding current checks at `n-1`, with the initial identity checked exactly.

## Exact data and bounded scope

The unchanged member is `L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz`, compressed SHA-256 `4981795bffcd2a0262040acb53c60b20607fea14a2a0c7d79e858ba68e7f2743`. Header SHA-256 excluding newline is `91f914d3c9993ac238c66e88015861ece560e20333f9e831f3ff4758980b3dd9`; decompressed stream SHA-256 including newlines is `4a2919c350f61974b8046dd5fe11e0710db37abde26b5db0af909ab4b8d83f78`. The comparator requires all three, exactly one input, contiguous states `1..36000`, one body/no joints, the selected input identity/dt and 108,001 event records. It never generates reference bytes or runs physics.

The source remains dyn4j `058bf6d982a0fb89b54050f929f6ea9dae53b714` and recorder/fixture `0995a6bac84de882b0d04b6c3ea18162ca3b4a7c`. See the [pinned model report](https://github.com/rubixhacker/dyn4k/blob/9994a0e16470e51df8a1ddfa21227620e9951239/docs/research/nominal-rotation-error-model.md). That revision's certificate is reused without modification and required to hash to `710b70f0bcc780dd81883ef1d9971b7b6c6b47e78c86a3a5dd07f3d1edb2b97b`.

## Decoder and enclosure argument

[The numeric helper](nominal-rotation-comparator-numbers.py) converts each decimal floating token to an exact rational, identifies its binary binade by integer bit lengths plus an exact comparison, and divides by the binade's binary64 quantum `2^(e-52)`. Integer quotient/remainder select the nearest significand; at an exact halfway tie the even significand wins. A carry advances the exponent. The output is an exact rational and a separately retained 64-bit encoding. Thus `0.1` means the represented binary64 rational, not the mathematical fraction `1/10`.

Zero's sign is retained in decoding tests; numerical checks intentionally identify positive and negative zero. Structural JSON integer tokens remain integers only if their magnitude is at most `2^53`, so they also denote exact binary64 values when used in selected numeric fields. Larger integer tokens are rejected. Nonfinite values, nonzero values in the subnormal input binade, rounding overflow, overly long tokens and excessive decimal exponents are explicitly unsupported/rejected. This limited decoder is sufficient for every frozen numeric token and does not claim a general subnormal parser. JSON's grammar handles lexical validity; malformed syntax, duplicate keys and non-object top-level values are rejected.

[The comparator](nominal-rotation-comparator.py) reuses the prior exact-integer outward oracle: a `10^-70` lattice, rational Machin pi enclosure, degree119/118 Taylor polynomials with bounded remainders, and interval-certified principal-phase reduction. It evaluates exact `theta_n=n*(4803839602528529/576460752303423488)` from encoded dt and omega, independently of any simulated or recorded angle sum. Sine/cosine and principal phase are enclosed; accumulated theta is an exact rational. Differences and absolute-value intervals use rational arithmetic, with no host libm or target-library comparator.

For wrapped distance, both angle operands must be in `[-4,4]`. Their difference is in `[-8,8]`. Since `pi>3`, every omitted integer branch `|k|>=3` has `|a-b-2k*pi|>10`, whereas `k=0` gives a distance at most eight. Therefore enumerating `k=-2..2` is complete. Each branch gives an outward absolute-distance interval. The minimum of all lower endpoints and minimum of all upper endpoints enclose the true minimum, even though the branches share the same pi and operand uncertainties. Tests cover point values and narrow intervals on opposite sides of the `+/-pi` cut. Unsupported operand domains are not silently reduced with an unqualified function.

For nonnegative error interval `[L,U]` and real cap `C`, **PASS iff `U<=C`; FAIL iff `L>C`; otherwise INCONCLUSIVE**. Inconclusive never counts as a pass, and the full run exits nonzero if any metric or inheritance check is unpassed. Output goes to a new directory to prevent stale manifests. Checker/helper source hashes are checked for changes during execution; the oracle source identity is enforced before calculation. A rejected/truncated/mismatched input cannot publish a success manifest.

The helper also implements the approved differential caps (`1.4e-10`, `1.4e-10`, `1e-7 rad`, `1.2e-7 rad`) on exact decoded metric tuples. This logic is verified with synthetic known values; it is not a claim that a real port trajectory has been compared. Future port file ingestion/runtime qualification remains separate.

## Executed verification and qualification boundary

[The verification script](nominal-rotation-comparator-verify.py) passed the following independent cases:

- Six exact halfway rounding cases exercise even-lower/even-upper selection, binade carry and both signs; known `0.1` and signed-zero bit patterns; 90 independently constructed normal binary64 bit patterns spanning exponents from -1000 to 1000; normal-range endpoints and eight invalid/nonfinite/unsupported/overflow cases.
- Inclusive cap equality, an upper endpoint exactly at the cap, strict failure above it, and two intervals straddling the cap (including a lower endpoint exactly at the cap).
- Opposite sides of the angle cut, narrow pi intervals and half-turn rejection; 16 synthetic differential outcomes covering identical values, inclusive caps, above-cap failures and the wrap cut.
- Full nested transform equality with equivalent signed zeros, and detection of a changed value one ulp away; eight malformed/nonfinite/truncated/duplicate/unsafe-integer/schema JSON inputs; three full-entry empty/truncated/mismatched gzip cases, each rejected without a success manifest.
- Every one of **251,640 distinct archived floating-point lexemes** was independently decoded by CPython's float parser and compared bit-for-bit with the exact integer/rational decoder. No disagreement occurred. The actual comparator does not depend on the float parser for its metrics; this is a cross-check using a different conversion implementation.

The mathematical interval/metric/decoding arguments and these executed boundary checks qualify the comparator for this bounded frozen input and operation set. They are not a formal machine proof of Python, a whole-domain proof of its JSON parser, or a future target/runtime qualification. The prior model's pi/Taylor derivation is reused and hash-bound, not replaced by agreement with measured residuals. Python3.14.7 on the recorded Linux x86_64 environment executed this run; complete runtime strings are in the manifest. Language-server tools were unavailable, so no static type-check success is claimed.

Direct analytic enclosure checks establish the baseline side of the approved parity comparison independently of historical hidden primitive behavior. The archived wrapper's unobserved calls remain unqualified. Every future port/runtime still needs the approved exact-candidate hypothesis qualification and trajectory checks, and no actual baseline-to-port run has occurred. Broader numerical/migration acceptance remains open.

## Reproduction and evidence

From the published branch checkout, with the exact selected gzip already retrieved, run into new directories:

```sh
python3 docs/research/nominal-rotation-comparator-verify.py \
  /path/to/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz \
  .omo/evidence/nominal-rotation-comparator/verification
python3 docs/research/nominal-rotation-comparator.py \
  /path/to/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz \
  .omo/evidence/nominal-rotation-comparator/baseline-final
```

The final run's `comparisons.jsonl` contains 144,000 exact interval/cap/verdict rows; `inheritance.jsonl` contains 36,000 full-transform relationship results. Their SHA-256 values are respectively `733dc97d76d7ec3a55f71354fbc435df3ce4b00f3d0d914dab3569b4203b8436` and `1e7d05a14cd1c8bf27ff4d847c374e97cc4f65008f27739fe848284a8333e031`. The generated baseline manifest and verification result are embedded in the compact publication manifest. Runtime strings can differ on another host; metric row hashes are deterministic for these exact scripts and inputs.
