package performance.portable

import kotlinx.cinterop.ExperimentalForeignApi
import kotlinx.cinterop.ByteVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.convert
import kotlinx.cinterop.cstr
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.toKString
import kotlin.experimental.ExperimentalNativeApi
import kotlin.native.OsFamily
import kotlin.native.Platform
import kotlin.native.runtime.GC
import kotlin.native.runtime.NativeRuntimeApi
import kotlin.time.TimeSource
import platform.posix.close
import platform.posix.fclose
import platform.posix.fopen
import platform.posix.fstat
import platform.posix.fputs
import platform.posix.open
import platform.posix.read
import platform.posix.rename
import platform.posix.stat
import platform.posix.usleep

private const val DARWIN_O_NOFOLLOW = 0x00000100
private const val DARWIN_O_NONBLOCK = 0x00000004
private const val LINUX_O_NOFOLLOW = 0x00020000
private const val LINUX_O_NONBLOCK = 0x00000800

@OptIn(ExperimentalForeignApi::class, ExperimentalNativeApi::class)
private fun validSimulatorRelease(release: String, nonce: String): Boolean {
    val flags = when (Platform.osFamily) {
        OsFamily.IOS, OsFamily.TVOS, OsFamily.WATCHOS, OsFamily.MACOSX ->
            DARWIN_O_NOFOLLOW or DARWIN_O_NONBLOCK
        OsFamily.LINUX, OsFamily.ANDROID -> LINUX_O_NOFOLLOW or LINUX_O_NONBLOCK
        else -> error("simulator attestation requires a POSIX no-follow open")
    }
    val descriptor = open(release, flags)
    if (descriptor < 0) return false
    try {
        return memScoped {
            val details = alloc<stat>()
            if (fstat(descriptor, details.ptr) != 0 ||
                (details.st_mode.toInt() and 0xF000) != 0x8000 ||
                details.st_size != nonce.length.toLong()
            ) return@memScoped false
            val bytes = allocArray<ByteVar>(nonce.length + 1)
            val count = read(descriptor, bytes, nonce.length.convert())
            bytes[nonce.length] = 0.toByte()
            count == nonce.length.toLong() && bytes.toKString() == nonce
        }
    } finally {
        close(descriptor)
    }
}

@OptIn(ExperimentalForeignApi::class)
private fun awaitSimulatorAttestation(nonce: String, dataContainer: String) {
    require(nonce.matches(Regex("[0-9a-f]{32}"))) { "simulator attestation nonce is invalid" }
    require(dataContainer.startsWith("/") && ".." !in dataContainer.split('/')) {
        "simulator data container path is invalid"
    }
    val prefix = "$dataContainer/dyn4k-performance-$nonce"
    val pending = "$prefix.ready.tmp"
    val ready = "$prefix.ready"
    val release = "$prefix.release"
    memScoped {
        val file = fopen(pending, "w") ?: error("simulator attestation ready file cannot open")
        val written = fputs(nonce.cstr.ptr, file)
        val closed = fclose(file)
        require(written >= 0 && closed == 0) { "simulator attestation ready file cannot write" }
    }
    require(rename(pending, ready) == 0) { "simulator attestation ready file cannot publish" }
    val started = TimeSource.Monotonic.markNow()
    while (!validSimulatorRelease(release, nonce)) {
        require(started.elapsedNow().inWholeSeconds < 60) { "simulator attestation timed out" }
        usleep(5_000u)
    }
}

@OptIn(NativeRuntimeApi::class, ExperimentalStdlibApi::class)
fun main(args: Array<String>) {
    if (args.size == 2 && args[0] == "--image-control-hold") {
        require(args[1] == BuildIdentity.sourceSha) { "image control source differs from linked producer" }
        println("DYN4K_IMAGE_CONTROL_READY\t${BuildIdentity.sourceSha}")
        readln()
        return
    }
    val portableArgs = if (args.size == 16 && args[14] == "--simulator-attestation-barrier") {
        awaitSimulatorAttestation(args[13], args[15])
        args.copyOfRange(0, 14)
    } else args
    startPortable(portableArgs, memoryProbe = {
        GC.collect()
        val info = requireNotNull(GC.lastGCInfo) { "Native collection information unavailable" }
        val heap = requireNotNull(info.memoryUsageAfter["heap"]) { "Native heap information unavailable" }
        Pair(heap.totalObjectsSizeBytes, info.epoch)
    })
}
