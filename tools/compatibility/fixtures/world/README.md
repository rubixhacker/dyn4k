# Frozen World Java fixtures

`world_ci.py` runs the 12 unchanged Java sources that were present at
`806db0b6ce40c6345054fc05a9ddb32da14cf153`. Their pinned SHA-256 values
are in the runner. The sources remain in `dyn4k-core/src/jvmConsumer/java/`;
the runner copies their verified bytes into each raw evidence directory.

The frozen source set has 23 execution modes. The runner compiles it with Java
8 against the pinned baseline and both staged host archives, then runs every
mode on Java 8 and 21. Each candidate's output must match the baseline on the
same Java runtime: 138 passing process executions in total.

`bad-body-view-bc71.jar` is the retained candidate archive from
`bc71eeb1b5de81f1c61c2fa63481dda163d03f4a`. Its SHA-256 is
`b53ae4c5e85bc5f37866e9ead1d0558e0128c8dde9542789f51f62b9d5a6e57b`.
It includes its original `META-INF/LICENSE.md`. A separate Java 8 compilation
and Java 8/21 execution of `WorldSerializableViewsConsumer` must expose its
known body-view serialization failure. The bad archive is an adverse control;
it is never a staged publication candidate.

The fixture runs Android `classes.jar` on a host JVM. It does not qualify an
Android device or any other native target.
