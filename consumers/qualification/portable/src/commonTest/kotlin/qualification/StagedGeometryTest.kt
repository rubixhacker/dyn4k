package qualification

import io.github.rubixhacker.dyn4k.Transform
import io.github.rubixhacker.dyn4k.Vector2
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame
import org.dyn4j.Reference

class StagedGeometryTest {
    @Test
    fun namedConstructorsResolveFromPublishedCommonAndPlatformVariants() {
        val direct = org.dyn4j.geometry.Vector2(x = 1.0, y = 2.0)
        val alias = Vector2(x = 3.0, y = 4.0)
        val same: org.dyn4j.geometry.Vector2 = alias
        val reference = Reference(value = direct)
        direct.add(x = 1.0, y = 2.0)

        assertEquals(2.0, reference.value?.x)
        assertEquals(4.0, reference.value?.y)
        assertSame(alias, same)
        assertEquals(3.0, same.x)
        assertEquals(4.0, same.y)
    }

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
