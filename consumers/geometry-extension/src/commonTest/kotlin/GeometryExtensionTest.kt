import io.github.rubixhacker.dyn4k.AABB
import io.github.rubixhacker.dyn4k.Ellipse
import io.github.rubixhacker.dyn4k.Interval
import io.github.rubixhacker.dyn4k.Ray
import io.github.rubixhacker.dyn4k.Vector2
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

private class CustomEllipse : Ellipse(2.0, 1.0) {
    override fun getWidth(): Double = 9.0
    override fun getHeight(): Double = 8.0
    fun storedHalfWidth(): Double = halfWidth
}

private class CustomBounds : AABB(0.0, 0.0, 1.0, 1.0) {
    override fun getWidth(): Double = 7.0
    override fun getMinX(): Double = -1.0
}

private class CustomInterval : Interval(1.0, 2.0) {
    override fun getLength(): Double = 10.0
}

private class CustomRay : Ray(Vector2(1.0, 0.0)) {
    override fun getStart(): Vector2 = Vector2(3.0, 4.0)
}

class GeometryExtensionTest {
    @Test
    fun publicGeometryOverridesDispatchThroughBaseTypes() {
        val ellipseExtension = CustomEllipse()
        val ellipse: Ellipse = ellipseExtension
        val bounds: AABB = CustomBounds()
        val interval: Interval = CustomInterval()
        val ray: Ray = CustomRay()
        assertEquals(9.0, ellipse.getWidth())
        assertEquals(8.0, ellipse.getHeight())
        assertEquals(1.0, ellipseExtension.storedHalfWidth())
        assertTrue(ellipse.toString().contains("Width=9") && ellipse.toString().contains("Height=8"))
        assertEquals(7.0, bounds.getWidth())
        assertEquals(-1.0, bounds.getMinX())
        assertEquals(10.0, interval.getLength())
        assertEquals(3.0, ray.getStart().x)
    }
}
