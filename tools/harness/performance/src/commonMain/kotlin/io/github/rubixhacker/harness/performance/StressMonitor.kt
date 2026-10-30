package io.github.rubixhacker.harness.performance

/** `tools/performance/stress_monitor.py`: the external peak-RSS probes and their method names. */
object StressMonitor {
    val methods: Map<String, String> = mapOf(
        "Linux" to "linux_proc_vmhwm_v1",
        "Darwin" to "macos_wait4_maxrss_v1",
        "Windows" to "windows_psapi_peak_working_set_v1",
    )

    const val UNSUPPORTED: String = "unsupported_unknown_external_peak_v1"

    fun method(system: String): String = methods[system] ?: UNSUPPORTED

    /**
     * `stress_monitor.peak_rss_bytes` for the platforms whose sample is a file or a process call
     * the adapter performs. [linuxStatus] reads `/proc/<pid>/status` and is only invoked once the
     * PID and the platform have both been accepted, so an unknown platform never touches procfs.
     */
    fun peakRssBytes(pid: Long, system: String, linuxStatus: () -> String): Long {
        if (pid <= 0) throw IllegalArgumentException("stress monitor PID is invalid")
        if (system != "Linux") {
            throw IllegalArgumentException("external peak RSS monitor is unvalidated for $system")
        }
        val rows = linuxStatus().split("\n")
            .filter { it.startsWith("VmHWM:") }
            .map { line -> line.trim().split(Regex("\\s+")) }
        if (rows.size != 1 || rows[0].size != 3 || rows[0][2] != "kB") {
            throw IllegalArgumentException("Linux VmHWM reading is invalid")
        }
        val value = rows[0][1].toLongOrNull()
            ?: throw IllegalArgumentException("Linux VmHWM reading is invalid")
        if (value <= 0) throw IllegalArgumentException("Linux VmHWM reading is invalid")
        return value * 1024
    }

    /** `stress_monitor.darwin_wait4_peak_rss`'s PID and sample validation. */
    fun darwinTerminalPeak(pid: Long, observedPid: Long, status: Long, peakKib: Long): Pair<Long, Long> {
        if (pid <= 0) throw IllegalArgumentException("macOS terminal usage PID is invalid")
        if (observedPid != pid || status < 0) {
            throw IllegalArgumentException("macOS terminal usage PID or status is invalid")
        }
        if (peakKib <= 0) throw IllegalArgumentException("macOS terminal peak RSS is invalid")
        return status to peakKib * 1024
    }

    /** `stress_monitor.peak_rss_bytes`'s macOS `ps` sample validation: the PID must be the one asked for. */
    fun darwinExternalSample(pid: Long, observedPid: Long, kib: Long): Long {
        if (pid <= 0) throw IllegalArgumentException("stress monitor PID is invalid")
        if (observedPid != pid || kib <= 0) {
            throw IllegalArgumentException("macOS external RSS PID or sample is invalid")
        }
        return kib * 1024
    }
}
