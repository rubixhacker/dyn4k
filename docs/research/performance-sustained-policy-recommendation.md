# Proposed sustained calibration limits

**Decision needed:** The coordinator should record a numeric noise rule and stress safety ceilings on the [approved performance policy ticket](https://github.com/rubixhacker/dyn4k/issues/8). An independent Sol review should approve them before the `sustained_gate` section is frozen or production candidate evaluation starts. The values below are a recommendation, not an approved budget or an observed result.

## Recommended choice

| Policy field | Proposed value | Meaning |
| --- | ---: | --- |
| `noise_upper_ratio_max` | `1.025` | Each unchanged-baseline 95% ratio interval, including the final-minute interval, must fit from `1/1.025` through `1.025`. |
| `stress_wall_ns_max` | `720000000000` | Stop a stress process after 720 seconds of elapsed wall time. |
| `stress_rss_bytes_max` | `3221225472` | Stop a stress process above 3 GiB peak resident memory. |

The approved shim median and total-time allowance is 5%. A 2.5% unchanged-baseline ceiling reserves half of that allowance for a detectable candidate effect. This is an engineering allocation of the approved margin, not a threshold supplied by NIST. The existing manifest already requires three balanced unchanged-baseline pairs, one-second blocks, 2,000 seeded bootstrap draws, and separate full-run and final-minute checks. [NIST's measurement guidance](https://www.itl.nist.gov/div898/handbook/mpc/section2/mpc21.htm) supports checking stable reference measurements before interpreting a changed candidate. Its [bootstrap guidance](https://itl.nist.gov/div898/handbook/eda/section3/eda334.htm) describes interval estimation, but does not choose this numeric bound.

The 720-second stop covers the approved maximum 600-second warm-up and the 60-second stress report. It leaves 60 seconds for launch, collection, and teardown. This is a safety ceiling, not an extra stress latency pass gate. The 3 GiB proposal uses the current JVM adapter's `-Xmx2g` heap setting plus 1 GiB for native runtime overhead. [Oracle documents `-Xmx` as a heap limit](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html); it is not a process-memory cap. [Linux documents `VmHWM` as peak RSS and warns that it can be inaccurate](https://www.man7.org/linux/man-pages/man5/proc_pid_status.5.html). A validated monitor and per-row device feasibility check remain prerequisites. The 1 GiB allowance is a proposed operational margin, not a measured overhead claim.

If a reference device cannot enforce these ceilings or cannot attribute memory, its row remains unvalidated. The coordinator should record any different per-runtime ceiling as a new reviewed decision before capture. The checked-in manifest contains no `sustained_gate` values, and this report does not add them. The historical pilot failures, 0 of 28 validated rows, and empirical qualification remain unpassed.
