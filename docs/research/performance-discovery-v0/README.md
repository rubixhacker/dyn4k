# Superseded fixture exploration

These raw JVM CSV files came from early bounded runs before the version 1 fixture was frozen. The separated-motion fixture used opposing velocities and produced collisions. The mixed joint fixture allowed bodies to sleep. Later runs also changed lifecycle joint cleanup, material settings, pacing, and diagnostic channels.

The files are retained so invalid observations are not silently discarded. They have no reliable single harness-source identity and must not be compared with the version 1 pilot or used for a gate. The version 1 pilot archive has its own SHA-256 bound evidence index.

An interrupted first calibration process left `calibration-interrupted-r1.csv` empty. It was stopped before measurement because the Angle joint fixture needed periodic angular excitation. The empty file is retained as a termination record, not a sample series.

The [pre-angular pilot](pre-angular/README.md) and [interrupted broad-phase pilot](pre-full-broadphase/README.md) retain later superseded raw runs with their own limitations.
