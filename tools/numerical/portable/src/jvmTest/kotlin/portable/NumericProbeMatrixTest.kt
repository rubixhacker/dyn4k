package portable

import java.io.OutputStream
import java.io.PrintStream
import java.net.URLClassLoader
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Paths
import java.nio.file.StandardOpenOption
import org.dyn4j.dynamics.Body
import org.dyn4j.geometry.Geometry
import kotlin.test.Test

class NumericProbeMatrixTest {
    @Test
    fun geometryCollisionBoundaryAndScale() {
        val path = Paths.get(requireNotNull(System.getProperty("portable.numericProbeMirror")))
        require(path.isAbsolute)
        val original = System.out
        val file = Files.newOutputStream(path, StandardOpenOption.CREATE_NEW,
            StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)
        val tee = PrintStream(object : OutputStream() {
            override fun write(value: Int) {
                original.write(value)
                file.write(value)
            }
            override fun write(bytes: ByteArray, offset: Int, length: Int) {
                original.write(bytes, offset, length)
                file.write(bytes, offset, length)
            }
            override fun flush() {
                original.flush()
                file.flush()
            }
        }, true, "UTF-8")
        try {
            System.setOut(tee)
            PortableMatrixTest().geometryCollisionBoundaryAndScale()
            emitProbe()
            emitProviders()
            tee.flush()
            check(!tee.checkError()) { "Numeric probe output failed" }
        } finally {
            System.setOut(original)
            try {
                tee.flush()
                check(!tee.checkError()) { "Numeric probe output failed" }
            } finally {
                file.close()
            }
        }
    }

    private fun operand(value: String): Double = java.lang.Double.parseDouble(value)

    private fun bits(value: Double): String =
        java.lang.Long.toHexString(java.lang.Double.doubleToRawLongBits(value)).padStart(16, '0')

    private fun gap(origin: Double, scale: Double, delta: Double): Double {
        val first = Body()
        first.addFixture(Geometry.createCircle(scale))
        first.translate(origin, -origin)
        val second = Body()
        second.addFixture(Geometry.createCircle(operand("0.5") * scale))
        second.translate(origin + scale * (operand("1.5") + delta), -origin)
        return (second.getTransform().getTranslationX() - first.getTransform().getTranslationX()) -
            operand("1.5") * scale
    }

    private fun emitProbe() {
        val one = operand("1.0")
        val zero = operand("0.0")
        val negativeZero = -zero
        val million = operand("1000000.0")
        val delta = operand("1e-12")
        val values = linkedMapOf(
            "ulpOneBits" to bits(Math.ulp(one)),
            "nextUpOneBits" to bits(Math.nextUp(one)),
            "nextDownOneBits" to bits(Math.nextDown(one)),
            "negativeZeroBits" to bits(negativeZero),
            "positiveZeroBits" to bits(zero),
            "negativeZeroReciprocalBits" to bits(one / negativeZero),
            "ulpMillionBits" to bits(Math.ulp(million)),
            "boundaryOriginZeroGapBits" to bits(gap(zero, one, delta)),
            "boundaryPositiveMillionGapBits" to bits(gap(million, one, delta)),
            "boundaryNegativeMillionGapBits" to bits(gap(-million, one, delta)),
        )
        val fields = values.entries.joinToString(",") { (key, value) -> "\"$key\":\"$value\"" }
        println("NUMERICAL_PROBE_JSON {\"schema\":\"portable-binary64-probe/1\",$fields," +
            "\"maximumFinite\":${operand("1.7976931348623157e308").isFinite()}," +
            "\"positiveInfinityFinite\":${(one / zero).isFinite()}," +
            "\"nanFinite\":${(zero / zero).isFinite()}}")
    }

    private fun quote(value: String): String = "\"" + value.flatMap { character ->
        when (character) {
            '\\' -> "\\\\".toList()
            '\"' -> "\\\"".toList()
            else -> if (character.code < 32) {
                "\\u".plus(character.code.toString(16).padStart(4, '0')).toList()
            } else listOf(character)
        }
    }.joinToString("") + "\""

    private fun emitProviders() {
        val classes = listOf(NumericProbeMatrixTest::class.java, PortableMatrixTest::class.java,
            NumericalRecorder::class.java, Body::class.java, Geometry::class.java)
        val providers = classes.joinToString(",") { type ->
            quote(type.name) + ":" + quote(type.protectionDomain.codeSource.location.toExternalForm())
        }
        val paths = linkedSetOf<String>()
        paths.addAll(System.getProperty("java.class.path").split(java.io.File.pathSeparator))
        var loader: ClassLoader? = NumericProbeMatrixTest::class.java.classLoader
        while (loader != null) {
            if (loader is URLClassLoader) {
                loader.getURLs().forEach { url ->
                    require(url.protocol == "file")
                    paths.add(java.io.File(url.toURI()).canonicalPath)
                }
            }
            loader = loader.parent
        }
        val effective = paths.joinToString(java.io.File.pathSeparator)
        println("NUMERICAL_PROVIDER_JSON {\"classpath\":" +
            quote(System.getProperty("java.class.path")) + ",\"effective_classpath\":" +
            quote(effective) + ",\"providers\":{$providers}}")
    }
}
