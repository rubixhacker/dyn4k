# dyn4k

An independently evolving Kotlin Multiplatform fork of dyn4j 6.0.0, with an idiomatic Kotlin API and a thin, fixed-version compatibility shim.

The assembled implementation includes the dyn4k engine, Kotlin facade, and baseline compatibility shim across the agreed 21 targets, 28 target/runtime families, and 112 qualification lanes. See the [source inventory](docs/verification/complete-common-corpus.md) and [open qualification status](docs/verification/qualification-harness.md) for current evidence and remaining gates.

Qualification remains open. The inventory and configured lane count describe scope; they do not establish a passing exact-source release candidate or completed runtime qualification.

## Try it

A falling box in the idiomatic API (needs the staged `dyn4k-jvm` and
`dyn4k-core-jvm` jars from `build/staging-repository` on the classpath):

```kotlin
import io.github.rubixhacker.dyn4k.body
import io.github.rubixhacker.dyn4k.fixture
import io.github.rubixhacker.dyn4k.gravity
import io.github.rubixhacker.dyn4k.massType
import io.github.rubixhacker.dyn4k.rectangle
import io.github.rubixhacker.dyn4k.world
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

fun main() {
    val scene = world {
        gravity = Vector2(0.0, -9.81)
        body { // ground slab, top surface at y = 0
            fixture(rectangle(20.0, 1.0))
            massType = MassType.INFINITE
            translate(0.0, -0.5)
        }
    }
    val box = scene.body {
        fixture(rectangle(1.0, 1.0))
        massType = MassType.NORMAL
        translate(0.0, 3.0)
    }
    repeat(120) { step ->
        scene.step(1)
        println("$step,${box.getTransform().getTranslationY()}")
    }
}
```

Captured against `0.1.0-alpha.1` on JVM (120 steps, 60 Hz):

- The box falls monotonically from 3.0, touches 0.5 at step 42, dips on first
  impact, and rests at `y = 0.4949` from step 74 on — a 1x1 box on a surface
  at 0, as expected.
- With gravity off and velocity set to (4, 3), all 61 sampled positions land
  exactly on the analytic track `x = 4t, y = 3t`.
- A ball with restitution 0.8 dropped from 3.0 reports decaying apexes
  (2.24, 1.72, 1.34, …), one per bounce.

Public repository: [rubixhacker/dyn4k](https://github.com/rubixhacker/dyn4k).

- [Complete-port specification](https://github.com/rubixhacker/dyn4k/issues/32)
- [Implementation work and evidence](docs/planning/implementation-ledger.md)

- [Decision map](https://github.com/rubixhacker/dyn4k/issues/1)
- [Agreed charter](docs/planning/charter.md)
- [Domain language](CONTEXT.md)
- [GitHub issue tracker](docs/agents/issue-tracker.md)
- [Complete source inventory](docs/verification/complete-common-corpus.md)
- [Complete suite manifest](docs/verification/full-suite-manifest.md)
- [Runtime qualification harness](docs/verification/qualification-harness.md)
- [Consumer migration and usage guide](docs/guide/migration.md)

