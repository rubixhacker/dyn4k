package io.github.rubixhacker.dyn4k.full

import io.github.rubixhacker.dyn4k.Vector2
import org.dyn4j.Reference

object FullKotlinJourney {
    @JvmStatic fun run() {
        val point = Vector2(3.0, 4.0)
        val core: org.dyn4j.geometry.Vector2 = point
        check(Reference(core).value === point)
        check(point.getMagnitude() == 5.0)
        core.x = 6.0
        check(point.x == 6.0)
    }
}
