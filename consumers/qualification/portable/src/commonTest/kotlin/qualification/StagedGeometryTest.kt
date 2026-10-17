package qualification

import io.github.rubixhacker.dyn4k.Transform
import io.github.rubixhacker.dyn4k.Vector2
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame

class StagedGeometryTest {
    @Test
    fun stagedRootCoordinatesResolveAndTransformSharedObjects() {
        val point = Vector2(3.0, 4.0)
        val same: org.dyn4j.geometry.Vector2 = point
        assertSame(point, same)
        assertEquals(5.0, point.getMagnitude(), 1e-12)
        val transform = Transform()
        transform.translate(2.0, -1.0)
        val moved = transform.getTransformed(point)
        assertEquals(5.0, moved.x, 1e-12)
        assertEquals(3.0, moved.y, 1e-12)
    }
}
