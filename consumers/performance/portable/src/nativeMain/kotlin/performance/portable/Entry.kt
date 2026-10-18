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
private val HEX = "0123456789abcdef"
private val SHA256_ROUNDS = intArrayOf(
    0x428a2f98, 0x71374491, 0xb5c0fbcf.toInt(), 0xe9b5dba5.toInt(),
    0x3956c25b, 0x59f111f1, 0x923f82a4.toInt(), 0xab1c5ed5.toInt(),
    0xd807aa98.toInt(), 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe.toInt(), 0x9bdc06a7.toInt(), 0xc19bf174.toInt(),
    0xe49b69c1.toInt(), 0xefbe4786.toInt(), 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152.toInt(), 0xa831c66d.toInt(), 0xb00327c8.toInt(), 0xbf597fc7.toInt(),
    0xc6e00bf3.toInt(), 0xd5a79147.toInt(), 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e.toInt(), 0x92722c85.toInt(),
    0xa2bfe8a1.toInt(), 0xa81a664b.toInt(), 0xc24b8b70.toInt(), 0xc76c51a3.toInt(),
    0xd192e819.toInt(), 0xd6990624.toInt(), 0xf40e3585.toInt(), 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814.toInt(), 0x8cc70208.toInt(),
    0x90befffa.toInt(), 0xa4506ceb.toInt(), 0xbef9a3f7.toInt(), 0xc67178f2.toInt(),
)

private fun rotateRight(value: Int, amount: Int): Int =
    (value ushr amount) or (value shl (32 - amount))

private fun sha256Hex(input: String): String {
    val source = input.encodeToByteArray()
    val bytes = ByteArray(((source.size + 72) / 64) * 64)
    source.copyInto(bytes)
    bytes[source.size] = 0x80.toByte()
    val length = source.size.toLong() * 8
    for (index in 0..7) bytes[bytes.lastIndex - index] = (length ushr (index * 8)).toByte()
    val state = intArrayOf(0x6a09e667, 0xbb67ae85.toInt(), 0x3c6ef372, 0xa54ff53a.toInt(),
        0x510e527f, 0x9b05688c.toInt(), 0x1f83d9ab, 0x5be0cd19)
    val words = IntArray(64)
    for (offset in bytes.indices step 64) {
        for (index in 0..15) {
            val start = offset + index * 4
            words[index] = ((bytes[start].toInt() and 255) shl 24) or
                ((bytes[start + 1].toInt() and 255) shl 16) or
                ((bytes[start + 2].toInt() and 255) shl 8) or
                (bytes[start + 3].toInt() and 255)
        }
        for (index in 16..63) {
            val a = words[index - 15]
            val b = words[index - 2]
            words[index] = words[index - 16] +
                (rotateRight(a, 7) xor rotateRight(a, 18) xor (a ushr 3)) +
                words[index - 7] +
                (rotateRight(b, 17) xor rotateRight(b, 19) xor (b ushr 10))
        }
        var a = state[0]
        var b = state[1]
        var c = state[2]
        var d = state[3]
        var e = state[4]
        var f = state[5]
        var g = state[6]
        var h = state[7]
        for (index in 0..63) {
            val first = h + (rotateRight(e, 6) xor rotateRight(e, 11) xor rotateRight(e, 25)) +
                ((e and f) xor (e.inv() and g)) + SHA256_ROUNDS[index] + words[index]
            val second = (rotateRight(a, 2) xor rotateRight(a, 13) xor rotateRight(a, 22)) +
                ((a and b) xor (a and c) xor (b and c))
            h = g
            g = f
            f = e
            e = d + first
            d = c
            c = b
            b = a
            a = first + second
        }
        state[0] += a
        state[1] += b
        state[2] += c
        state[3] += d
        state[4] += e
        state[5] += f
        state[6] += g
        state[7] += h
    }
    return buildString(64) {
        for (word in state) for (shift in 28 downTo 0 step 4) append(HEX[(word ushr shift) and 15])
    }
}

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
            require(write(descriptor, data.ptr, bytes.length.convert()) == bytes.length.toLong()) {
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
            if (count == 64L && token.matches(Regex("[0-9a-f]{64}")) &&
                releaseDigest("release", source, nonce, token) == commitment) token else null
        }
    } finally {
        close(descriptor)
    }
}

@OptIn(ExperimentalForeignApi::class)
private fun awaitSimulatorAttestation(source: String, nonce: String, dataContainer: String,
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

@OptIn(NativeRuntimeApi::class, ExperimentalStdlibApi::class)
fun main(args: Array<String>) {
    if (args.size == 2 && args[0] == "--sha256-control") {
        println(sha256Hex(args[1]))
        return
    }
    if (args.size == 2 && args[0] == "--image-control-hold") {
        require(args[1] == BuildIdentity.sourceSha) { "image control source differs from linked producer" }
        println("DYN4K_IMAGE_CONTROL_READY\t${BuildIdentity.sourceSha}")
        readln()
        return
    }
    val portableArgs = if (args.size == 17 && args[14] == "--simulator-attestation-barrier") {
        awaitSimulatorAttestation(args[9], args[13], args[15], args[16])
        args.copyOfRange(0, 14)
    } else args
    startPortable(portableArgs, memoryProbe = {
        GC.collect()
        val info = requireNotNull(GC.lastGCInfo) { "Native collection information unavailable" }
        val heap = requireNotNull(info.memoryUsageAfter["heap"]) { "Native heap information unavailable" }
        Pair(heap.totalObjectsSizeBytes, info.epoch)
    })
}
