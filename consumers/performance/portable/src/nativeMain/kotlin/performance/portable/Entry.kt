package performance.portable

import kotlinx.cinterop.ExperimentalForeignApi
import kotlinx.cinterop.cstr
import kotlinx.cinterop.memScoped
import kotlin.native.runtime.GC
import kotlin.native.runtime.NativeRuntimeApi
import kotlin.time.TimeSource
import platform.posix.F_OK
import platform.posix.access
import platform.posix.fclose
import platform.posix.fopen
import platform.posix.fputs
import platform.posix.rename
import platform.posix.usleep

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
    while (access(release, F_OK) != 0) {
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
