package performance.portable

import kotlin.native.runtime.GC
import kotlin.native.runtime.NativeRuntimeApi

@OptIn(NativeRuntimeApi::class, ExperimentalStdlibApi::class)
fun main(args: Array<String>) = startPortable(args, memoryProbe = {
    GC.collect()
    val info = requireNotNull(GC.lastGCInfo) { "Native collection information unavailable" }
    val heap = requireNotNull(info.memoryUsageAfter["heap"]) { "Native heap information unavailable" }
    Pair(heap.totalObjectsSizeBytes, info.epoch)
})
