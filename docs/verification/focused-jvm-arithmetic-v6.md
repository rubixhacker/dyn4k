# Focused JVM arithmetic receipt

## What the command checks

The version 6 receipt covers one Boolean method and one case: captureRevoluteLimitsFalse and joint-Revolute-LimitsEnabled-false. It keeps the approved 600 steps, 1,800 observed pivot calls, 1,200 body-step receipts, three caller locations, and fixed input and reference bytes.

The capture retains raw timestamped worker and helper traces. The verifier checks protected operations before it projects syntax for the older process readers. It keeps the original bytes and hashes. The selected worker must read the response and rebuilt agent inputs, write the direct mirror, and produce the class-load, argument, and class witness files at their recorded destinations.

The class witness records each relevant definition, successful load, provider, and loader label. At the unique Transform class-prepare event, JDI reads the agent's retained loader object, label, and definition ordinal. The verifier compares JVM object IDs with JVM object IDs. It joins the local label and ordinal to the terminal witness record. It also compares the loaded Transform and agent helper code with their source-derived bytes.

The direct mirror must equal the complete XML output in order, including its final newline. The existing caller, receiver, thread, order, bit, signed-zero, and arithmetic-oracle checks still apply. A passing focused receipt is method evidence with outer qualification UNPASSED. It does not change the fixed 32-ulp result or activate the conditional budget.

## Capture and replay

Capture requires a clean committed source tree, the pinned JDK 21, the existing staged build tools, and a private home-backed TMPDIR whose path is at most 40 bytes. The output directory must be new and outside the source tree. The indexed reference case must have the pinned bytes.

Run the capture with:

~~~text
python -B tools/numerical/portable/capture_actual.py --method captureRevoluteLimitsFalse --output ABSOLUTE_NEW_ARCHIVE --reference-case ABSOLUTE_INDEXED_REFERENCE
~~~

Replay with an independently sealed JVM lane, its baseline archive, and its external baseline attestation:

~~~text
python -B tools/numerical/portable/capture_actual.py --verify-existing ABSOLUTE_ARCHIVE --lane ABSOLUTE_SEALED_JVM_LANE --baseline ABSOLUTE_BASELINE --attestation ABSOLUTE_ATTESTATION
~~~

Replay first runs the existing whole-lane comparison with no arithmetic-capture override. It then recomputes the version 6 receipt from raw files and compares the focused case bytes with the validated lane case. A Boolean-only archive root remains insufficient for the 15-method arithmetic verifier.

## Current evidence boundary

The source phase has a bounded JDK 21 toy loader and transport pilot. It has no version 6 capture of the 600-step case and no whole-lane replay. The parent and runtime child tickets remain open. Source review, exact-main CI, full capture, independent runtime audit, and retrospective are separate checks.
