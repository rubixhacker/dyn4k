# Boolean rotation JDI probe

This directory holds a separate diagnostic for `joint-Revolute-LimitsEnabled-false`.
The probe records entry and exit observations for `Transform.rotatePivotObserved`.
It does not change the 332-case catalog or the accepted numerical rule.

`RotationJdiProbe.java` can launch a small Java main class or attach to a JVM
with JDWP socket transport. It writes a constant pool, every method's bytecode,
the class loader ID, and ordered entry/exit records. Each record contains raw
bits for the `c` and `s` arguments, rotation fields before and after the method,
the boxed angle, receiver and thread IDs, and the source caller's method and
bytecode location. The probe requires a VM death event and an exact event count
before it writes `complete.txt`. A disconnect without VM death fails the capture.
One reusable reader waits for JDI events. The controller applies the observation
deadline while it waits for that reader. This avoids a new JDK timer thread for
each event set. `JdiWaitControl.java` and `test_jdi_wait.py` are synthetic public
CLI controls for thread use, the deadline, VM disconnect, and normal completion.
They do not qualify a numerical or runtime lane.

`loaded_code.py` compares the observed constant pool and method inventory and
bytes with a source-pinned JAR class. A match covers only the code that JDI
exposes. It does not establish the complete loaded class file, classpath, JAR
origin, JVM loader decision, or source provenance by itself.

`source_guard.py` pins the six source files that define this one-case fixture
and call schedule. `witness.py` checks 1,800 ordered calls against 600 marker
steps and the source schedule: body `b1` integration, then `b0` and `b1`
Revolute point corrections. All three calls enter `rotatePivotObserved`.
The latter two caller branches remain null. The checker compares raw bits,
including signed zero. A consistent synthetic stream still returns
`UNPASSED_WORKER_BINDING`; a changed stream returns a typed failure.
The three caller bytecode locations must come from an independent source and
compiled-code review. Without them, the checker returns
`UNPASSED_SOURCE_CALL_SITE`.

`capture_actual.py` now starts JDWP for the selected Boolean `jvmTest` worker.
It checks the worker's live loopback socket before it attaches the helper.
The producer seals the helper classes, JDI output, process traces, worker XML,
and operation markers. `actual_arithmetic.py` checks these inputs in a
versioned `/5` receipt. It derives caller bytecode locations from the staged
artifact and checks 1,800 JDI calls against 600 worker marker steps. A
candidate marker or audit cannot supply its own expected call sequence.

A `/5` worker witness requires an actual selected Gradle worker capture and
independent replay of its retained evidence. Source-only and toy controls do
not satisfy that requirement. Historical `/4` Boolean and `/3` Wheel receipts
remain separate, unqualified evidence.

Response-file READ bytes, worker write FD destination, actual JVM loader
bytes, and global order across threads remain separate premises. The helper
class ZIP is source-bound, but its JVM class loading is not independently
proved. A JDI observation is a JVM report and does not prove those kernel
facts. The fixed 32-ULP failure at step 231 and the conditional arithmetic
premise remain open.
