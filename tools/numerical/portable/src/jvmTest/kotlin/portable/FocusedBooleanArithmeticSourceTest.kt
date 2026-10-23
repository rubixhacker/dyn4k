package portable

import java.io.OutputStream
import java.io.PrintStream
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import kotlin.test.Test

class FocusedBooleanArithmeticSourceTest {
    @Test
    fun captureRevoluteLimitsFalse() {
        val mirror = Path.of(requireNotNull(System.getProperty("portable.booleanMirror")))
        val original = System.out
        Files.newOutputStream(mirror, StandardOpenOption.CREATE_NEW,
                              StandardOpenOption.WRITE).use { file ->
            val paired = object : OutputStream() {
                override fun write(value: Int) {
                    original.write(value)
                    file.write(value)
                }

                override fun write(value: ByteArray, offset: Int, length: Int) {
                    original.write(value, offset, length)
                    file.write(value, offset, length)
                }

                override fun flush() {
                    original.flush()
                    file.flush()
                }
            }
            val stream = PrintStream(paired, true, Charsets.UTF_8)
            System.setOut(stream)
            try {
                RevoluteLimitsFalseCaptureTest().captureRevoluteLimitsFalse()
            } finally {
                stream.flush()
                System.setOut(original)
                stream.close()
            }
        }
    }
}
