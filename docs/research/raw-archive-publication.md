# Full original raw archive

Experimental data publication for [Execute the approved baseline calibration experiment](https://github.com/rubixhacker/dyn4k/issues/15). The GitHub asset release is explicitly a prerelease data archive, excluded from Latest; it is not a production dyn4k library release or reference approval.

Archive location: [Experimental baseline calibration raw data](https://github.com/rubixhacker/dyn4k/releases/tag/calibration-raw-20260914).

The archive stores all909 canonical full-precision gzip traces, including ordered within-step events and the rejected nonfinite case boundary. Each original repetition retains5,980,526 complete physics states. Both independently produced trace sets were freshly SHA256-checked against the published audit manifest and against each other before packaging. Separate repetition checksum manifests and metadata are included. No state/event records are dropped to make the archive smaller.

Because both repetitions have identical compressed bytes, canonical trace content is stored once. The14 tar chunks total19,968,512,000 bytes, including original source/class archives and provenance metadata. Each part is at most1.5GB; this satisfies the [GitHub per-asset release limit](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases). Restoration reconstructs both original trace sets from those verified bytes, with each repetition's own query/summary/audit/redundancy metadata. Their logical trace payload remains approximately40GB; shared content is not a lossy summary.

## Download and reconstruct

Download all14 `dyn4j-baseline-raw.tar.part-*` assets, `SHA256SUMS`, and the accompanying upstream license. In a new directory:

```sh
sha256sum -c SHA256SUMS
cat dyn4j-baseline-raw.tar.part-* | tar -xf -
bash package/restore-repeats.sh
```

The restoration script verifies both original manifests against canonical bytes, creates `package/restored-a` and `package/restored-b`, links complete immutable traces, copies separate metadata, and verifies the reconstructed sets. Existing restored directories are refused. If mutable independent working copies are required, copy the files instead of editing the shared hardlinks.

Included material: `canonical/`, `repeat-a/`, `repeat-b/`, original captured source/classes, commands/environment, explicit redundant-invocation accounting, and accumulated-rotation exclusion. The redundant free-motion invocation is byte-identical and retains its accounting record; it is not counted as an additional unique canonical trace. Later corrections, checkpoint probes and interaction probes remain separately identified branch artifacts.

## Publication verification

Server asset digests match every local chunk checksum. Full download, checksum verification and reconstruction evidence is recorded in [the publication evidence directory](calibration-evidence/raw-archive/). The local original directories are retained unchanged; remote publication does not remove local recovery copies.

No baseline exception, finite reference eligibility, numerical bound or all-target parity claim follows from archive integrity. See [the acceptance review packet](calibration-acceptance-review.md).
