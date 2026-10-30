package qualification

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertTrue
import platform.Foundation.NSBundle
import platform.Foundation.NSFileManager
import platform.Foundation.NSHomeDirectory

val DeviceImageProofTest by testSuite {
    test("copyInstalledImageToDataContainer") { DeviceImageProofTestFixture().run { copyInstalledImageToDataContainer() } }
}

private class DeviceImageProofTestFixture  {
fun copyInstalledImageToDataContainer() {
        val source = requireNotNull(NSBundle.mainBundle.executablePath)
        val destination = "${NSHomeDirectory()}/Documents/dyn4k-qualified-host.bin"
        val files = NSFileManager.defaultManager
        if (files.fileExistsAtPath(destination)) {
            assertTrue(files.removeItemAtPath(destination, null))
        }
        assertTrue(files.copyItemAtPath(source, destination, null))
    }
}
