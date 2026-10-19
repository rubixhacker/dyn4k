package performance.portable

import kotlinx.cinterop.ByteVar
import kotlinx.cinterop.ExperimentalForeignApi
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
import kotlin.time.TimeSource
import platform.posix.close
import platform.posix.fstat
import platform.posix.link
import platform.posix.open
import platform.posix.read
import platform.posix.stat
import platform.posix.unlink
import platform.posix.usleep
import platform.posix.write

private const val DARWIN_O_NOFOLLOW = 0x00000100
private const val DARWIN_O_NONBLOCK = 0x00000004
private const val DARWIN_O_CREAT = 0x00000200
private const val DARWIN_O_EXCL = 0x00000800
private const val LINUX_O_NOFOLLOW = 0x00020000
private const val LINUX_O_NONBLOCK = 0x00000800
private const val LINUX_O_CREAT = 0x00000040
private const val LINUX_O_EXCL = 0x00000080
private const val O_WRONLY = 0x00000001

private fun releaseDigest(label: String, source: String, nonce: String, token: String): String =
    sha256Hex("dyn4k-performance-$label-v1|$source|$nonce|$token")

@OptIn(ExperimentalForeignApi::class, ExperimentalNativeApi::class)
private fun publishSimulatorMarker(path: String, bytes: String) {
    val flags = when (Platform.osFamily) {
        OsFamily.IOS, OsFamily.TVOS, OsFamily.WATCHOS, OsFamily.MACOSX ->
            O_WRONLY or DARWIN_O_CREAT or DARWIN_O_EXCL or DARWIN_O_NOFOLLOW
        OsFamily.LINUX, OsFamily.ANDROID ->
            O_WRONLY or LINUX_O_CREAT or LINUX_O_EXCL or LINUX_O_NOFOLLOW
        else -> error("simulator attestation requires a POSIX no-follow open")
    }
    val pending = "$path.tmp"
    val descriptor = open(pending, flags, 0x180)
    require(descriptor >= 0) { "simulator attestation marker cannot open" }
    try {
        memScoped {
            val data = bytes.cstr
            require(write(descriptor, data.ptr, bytes.length.convert()).toLong() == bytes.length.toLong()) {
                "simulator attestation marker cannot write"
            }
        }
    } finally {
        require(close(descriptor) == 0) { "simulator attestation marker cannot close" }
    }
    require(link(pending, path) == 0) { "simulator attestation marker already exists" }
    require(unlink(pending) == 0) { "simulator attestation marker cannot finalize" }
}

@OptIn(ExperimentalForeignApi::class, ExperimentalNativeApi::class)
private fun validSimulatorRelease(release: String, source: String, nonce: String,
                                  commitment: String): String? {
    val flags = when (Platform.osFamily) {
        OsFamily.IOS, OsFamily.TVOS, OsFamily.WATCHOS, OsFamily.MACOSX ->
            DARWIN_O_NOFOLLOW or DARWIN_O_NONBLOCK
        OsFamily.LINUX, OsFamily.ANDROID -> LINUX_O_NOFOLLOW or LINUX_O_NONBLOCK
        else -> error("simulator attestation requires a POSIX no-follow open")
    }
    val descriptor = open(release, flags)
    if (descriptor < 0) return null
    try {
        return memScoped {
            val details = alloc<stat>()
            if (fstat(descriptor, details.ptr) != 0 ||
                (details.st_mode.toInt() and 0xF000) != 0x8000 ||
                details.st_size != 64L
            ) return@memScoped null
            val bytes = allocArray<ByteVar>(65)
            val count = read(descriptor, bytes, 64.convert())
            bytes[64] = 0.toByte()
            val token = bytes.toKString()
            if (count.toLong() == 64L && token.matches(Regex("[0-9a-f]{64}")) &&
                releaseDigest("release", source, nonce, token) == commitment) token else null
        }
    } finally {
        close(descriptor)
    }
}

@OptIn(ExperimentalForeignApi::class)
internal actual fun awaitSimulatorAttestation(source: String, nonce: String, dataContainer: String,
                                      commitment: String) {
    require(nonce.matches(Regex("[0-9a-f]{32}"))) { "simulator attestation nonce is invalid" }
    require(source == BuildIdentity.sourceSha) { "simulator attestation source differs from linked producer" }
    require(commitment.matches(Regex("[0-9a-f]{64}"))) { "simulator release commitment is invalid" }
    require(dataContainer.startsWith("/") && ".." !in dataContainer.split('/')) {
        "simulator data container path is invalid"
    }
    val prefix = "$dataContainer/dyn4k-performance-$nonce"
    val ready = "$prefix.ready"
    val release = "$prefix.release"
    publishSimulatorMarker(ready, nonce)
    val started = TimeSource.Monotonic.markNow()
    var token: String? = null
    while (token == null) {
        token = validSimulatorRelease(release, source, nonce, commitment)
        require(started.elapsedNow().inWholeSeconds < 60) { "simulator attestation timed out" }
        if (token == null) usleep(5_000u)
    }
    publishSimulatorMarker("$prefix.ack", releaseDigest("ack", source, nonce, token))
}
