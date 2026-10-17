import com.sun.management.ThreadMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class ProbeValidation {
    private static long rssBytes() {
        try {
            for (String line : Files.readAllLines(Path.of("/proc/self/status"))) {
                if (line.startsWith("VmRSS:")) return Long.parseLong(line.trim().split("\\s+")[1]) * 1024L;
            }
        } catch (Exception ignored) {
        }
        return -1L;
    }

    private static long collections() {
        long count = 0L;
        for (GarbageCollectorMXBean bean : ManagementFactory.getGarbageCollectorMXBeans()) {
            if (bean.getCollectionCount() >= 0) count += bean.getCollectionCount();
        }
        return count;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 0) throw new IllegalArgumentException("no arguments expected");
        long[] ticks = new long[10000];
        for (int i = 0; i < ticks.length; i++) {
            long first = System.nanoTime();
            ticks[i] = System.nanoTime() - first;
        }
        Arrays.sort(ticks);
        long positive = -1;
        for (long tick : ticks) if (tick > 0) { positive = tick; break; }
        ThreadMXBean bean = (ThreadMXBean) ManagementFactory.getThreadMXBean();
        boolean supported = bean.isThreadAllocatedMemorySupported();
        if (supported) bean.setThreadAllocatedMemoryEnabled(true);
        long thread = Thread.currentThread().getId();
        long allocBefore = supported ? bean.getThreadAllocatedBytes(thread) : -1;
        List<byte[]> live = new ArrayList<>();
        for (int i = 0; i < 4096; i++) live.add(new byte[256]);
        long allocAfter = supported ? bean.getThreadAllocatedBytes(thread) : -1;
        long liveChecksum = live.stream().mapToLong(a -> a.length).sum();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        long heapLive = memory.getHeapMemoryUsage().getUsed();
        long rssLive = rssBytes();
        long gcBefore = collections();
        live.clear();
        System.gc();
        Thread.sleep(100);
        long gcAfter = collections();
        long heapReleased = memory.getHeapMemoryUsage().getUsed();
        long rssReleased = rssBytes();
        System.out.println("{\"timer_min_positive_ns\":" + positive
            + ",\"timer_median_pair_ns\":" + ticks[ticks.length / 2]
            + ",\"timer_p99_pair_ns\":" + ticks[ticks.length * 99 / 100]
            + ",\"allocation_supported\":" + supported
            + ",\"controlled_payload_bytes\":" + liveChecksum
            + ",\"controlled_allocated_bytes\":" + (supported ? allocAfter - allocBefore : -1)
            + ",\"heap_live_bytes\":" + heapLive
            + ",\"heap_after_collection_bytes\":" + heapReleased
            + ",\"rss_live_bytes\":" + rssLive
            + ",\"rss_after_collection_bytes\":" + rssReleased
            + ",\"collection_count_delta\":" + (gcAfter - gcBefore) + "}");
    }
}
