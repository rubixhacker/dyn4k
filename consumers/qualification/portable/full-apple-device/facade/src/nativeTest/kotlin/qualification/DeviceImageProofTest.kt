package qualification

import kotlin.test.Test
import kotlin.test.assertTrue
import platform.Foundation.NSBundle
import platform.Foundation.NSFileManager
import platform.Foundation.NSHomeDirectory

class DeviceImageProofTest {
    @Test
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
