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
before it writes `complete.txt`. Its current completion rule fits the tiny toy.
A Gradle worker capture needs a separate reviewed endpoint and process witness.

`loaded_code.py` compares the observed constant pool and method inventory and
bytes with a source-pinned JAR class. A match covers only the code that JDI
exposes. It does not establish the complete loaded class file, classpath, JAR
origin, JVM loader decision, or source provenance by itself.

`source_guard.py` pins the five source files that define this one-case fixture
and call schedule. `witness.py` checks 1,800 ordered calls against 600 marker
steps and the source schedule: body `b1` integration, then `b0` and `b1`
Revolute point corrections. All three calls enter `rotatePivotObserved`.
The latter two caller branches remain null. The checker compares raw bits,
including signed zero. A consistent synthetic stream still returns
`UNPASSED_WORKER_BINDING`; a changed stream returns a typed failure.
The three caller bytecode locations must come from an independent source and
compiled-code review. Without them, the checker returns
`UNPASSED_SOURCE_CALL_SITE`.

The coordinator must connect a future exact-source worker capture to this
probe through a reviewed producer change. That change must arrange JDWP before
the selected worker executes, prove the attached PID and process descendants,
seal the JDI output with the worker XML and operation markers, and compare the
JDI receiver IDs to independently witnessed body identities. It must define
the worker endpoint so missing or later operations reject. It must also bind
the helper binary and its own execution to the receipt. The current
`capture_actual.py` does not provide those hooks. A candidate marker or audit
cannot supply its own independent expected call sequence.

Response-file READ bytes, write FD destination, actual JVM loader bytes, and
global order across threads remain separate premises. A JDI observation is a
JVM report and does not prove those kernel facts. The fixed 32-ULP failure at
step 231 and the conditional arithmetic premise remain open.
