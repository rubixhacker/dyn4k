package portable

import de.infix.testBalloon.framework.core.TestConfig
import de.infix.testBalloon.framework.core.testScope
import de.infix.testBalloon.framework.core.testSuite
import kotlin.time.Duration.Companion.minutes
import java.io.OutputStream
import java.io.PrintStream
import java.nio.channels.Channels
import java.nio.channels.FileChannel
import java.nio.file.Path
import java.nio.file.StandardOpenOption

val FocusedBooleanArithmeticSourceTestSuite by testSuite(
    testConfig = TestConfig.testScope(isEnabled = true, timeout = 60.minutes),
) {
    test("captureRevoluteLimitsFalse") { FocusedBooleanArithmeticSourceTest().run { captureRevoluteLimitsFalse() } }
}

class FocusedBooleanArithmeticSourceTest {
fun captureRevoluteLimitsFalse() {
        val mirror = Path.of(requireNotNull(System.getProperty("portable.booleanMirror")))
        val original = System.out
        FileChannel.open(mirror, StandardOpenOption.CREATE_NEW,
                         StandardOpenOption.WRITE).use { channel ->
            channel.size()
            val file = Channels.newOutputStream(channel)
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
            var failure: Throwable? = null
            try {
                RevoluteLimitsFalseCaptureTest().captureRevoluteLimitsFalse()
                stream.flush()
                channel.size()
            } catch (cause: Throwable) {
                failure = cause
                throw cause
            } finally {
                try {
                    stream.flush()
                } catch (cleanup: Throwable) {
                    failure?.addSuppressed(cleanup) ?: run { failure = cleanup }
                }
                try {
                    System.setOut(original)
                } catch (cleanup: Throwable) {
                    failure?.addSuppressed(cleanup) ?: run { failure = cleanup }
                }
                try {
                    stream.close()
                } catch (cleanup: Throwable) {
                    failure?.addSuppressed(cleanup) ?: run { failure = cleanup }
                }
                failure?.let { throw it }
            }
        }
    }
}
