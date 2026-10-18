package performance.portable

import kotlin.native.runtime.GC
import kotlin.native.runtime.NativeRuntimeApi

@OptIn(NativeRuntimeApi::class, ExperimentalStdlibApi::class)
fun main(args: Array<String>) {
    if (args.size == 2 && args[0] == "--image-control-hold") {
        require(args[1] == BuildIdentity.sourceSha) { "image control source differs from linked producer" }
        println("DYN4K_IMAGE_CONTROL_READY\t${BuildIdentity.sourceSha}")
        readln()
        return
    }
    startPortable(args, memoryProbe = {
        GC.collect()
        val info = requireNotNull(GC.lastGCInfo) { "Native collection information unavailable" }
        val heap = requireNotNull(info.memoryUsageAfter["heap"]) { "Native heap information unavailable" }
        Pair(heap.totalObjectsSizeBytes, info.epoch)
    })
}
