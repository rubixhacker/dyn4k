# Focused JVM arithmetic receipt

## What the command checks

The version 6 receipt covers one Boolean method and one case: captureRevoluteLimitsFalse and joint-Revolute-LimitsEnabled-false. It keeps the approved 600 steps, 1,800 observed pivot calls, 1,200 body-step receipts, three caller locations, and fixed input and reference bytes.

The capture retains raw timestamped worker and helper traces. The verifier checks protected operations before it projects syntax for the older process readers. It keeps the original bytes and hashes. The selected worker must read the response and rebuilt agent inputs, write the direct mirror, and produce the class-load, argument, and class witness files at their recorded destinations.

Version 6 checks each protected descriptor use across threads, copies, reassignment, and closure. For helper outputs, it permits sequential writes, close, fstat, and an initial zero-length ftruncate before any write. It rejects operations that can change the file offset or bytes outside the byte reader's model. Its helper output scope includes every archived JDI file. The byte check reads the projected trace only after the raw destination check succeeds. The verifier checks the raw accept, the live worker listener, the helper peer, and both sides of the JDWP handshake. It uses each handshake thread's file order to establish that end's handshake. Later packets may run on other proved threads of the selected process and shared descriptor table. For those packets, the next syscall entry on the handshake thread proves that its handshake syscall returned. A packet on another thread must enter strictly after that entry. Packets on the handshake thread use its file order. If the trace has no such completion witness, it cannot credit a packet from another thread. A strace line timestamp records syscall entry, so the verifier does not treat timestamps from different processes as completion order. The successful socket calls, exact peer tokens and handshake bytes, and live descriptor scope establish the selected exchange. It checks the selected socket lifetime through every credited exchange event. The raw lifetime check recognizes decorated and undecorated first descriptor operands. It treats descriptor 5 and descriptor 50 as different values. While a selected socket is live, version 6 rejects copied descriptor tables, socket descriptor aliases, and unsupported table changes. This narrow scope also rejects a copied child that only closes its own socket descriptor. The older socket and file status values remain unpassed records; they do not establish this version 6 transport proof.

The bounded JDI pilot writes the worker and helper raw trace archives and a diagnostic marked `UNVERIFIED` before proof checks. A failed pilot retains those bytes for diagnosis. A separate passing pilot summary records the completed checks; the raw diagnostic alone is not proof.

The capture records each rebuilt helper class file's identity before and after execution. Replay checks the selected helper process's complete reads of every class file it accessed. The main helper class must be read. The helper's effective startup log and the worker's effective startup log must contain only their permitted agent options. Both logs are tied to the selected process and their raw file writes.

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

The source phase requires a bounded JDK 21 toy loader and transport pilot at the clean source commit. A toy run cannot establish the 600-step method result. There is no version 6 capture of that case or whole-lane replay yet. The parent and runtime child tickets remain open. Source review, exact-main CI, full capture, independent runtime audit, and retrospective are separate checks.
