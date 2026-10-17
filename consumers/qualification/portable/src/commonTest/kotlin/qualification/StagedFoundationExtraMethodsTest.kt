package qualification

import io.github.rubixhacker.dyn4k.Rotation
import io.github.rubixhacker.dyn4k.Transform
import kotlin.test.Test
import kotlin.test.assertEquals

class StagedFoundationExtraMethodsTest {
    private class RotationExtension : Rotation() {
        init { cost = 0.0; sint = 1.0 }

        override fun getCost() = 17.0
        override fun getSint() = 19.0
    }

    private class TransformExtension : Transform() {
        init { cost = 0.0; sint = 1.0 }

        override fun getCost() = 23.0
        override fun getSint() = 29.0
    }

    @Test
    fun publishedAliasesRetainKotlinHelpersAndGetterOverrides() {
        val rotation: Rotation = RotationExtension()
        val transform: Transform = TransformExtension()

        assertEquals(0.0, rotation.costValue())
        assertEquals(1.0, rotation.sintValue())
        assertEquals(17.0, rotation.getCost())
        assertEquals(19.0, rotation.getSint())
        assertEquals(0.0, transform.costValue())
        assertEquals(1.0, transform.sintValue())
        assertEquals(23.0, transform.getCost())
        assertEquals(29.0, transform.getSint())

        val fromFields = Rotation.of(transform)
        assertEquals(0.0, fromFields.getCost())
        assertEquals(1.0, fromFields.getSint())
    }
}
