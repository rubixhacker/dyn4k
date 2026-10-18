package io.github.rubixhacker.dyn4k.runtime

import io.github.rubixhacker.dyn4k.Vector2
import org.dyn4j.Reference
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

class StagedKotlinConsumerTest {
    @Test fun sharedMutableIdentity() {
        val point = Vector2(3.0, 4.0)
        val core: org.dyn4j.geometry.Vector2 = point
        val reference = Reference(core)
        assertSame(point, core)
        assertSame(point, reference.value)
        assertEquals(5.0, point.getMagnitude(), 0.0)
        core.x = 6.0
        assertEquals(6.0, point.x, 0.0)
    }
}
