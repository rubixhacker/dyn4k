package performance;

import java.io.BufferedWriter;
import java.io.IOException;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import com.sun.management.ThreadMXBean;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class SustainedSidecars {
    private static final String FIXTURE_SHA256 = "30aadbc84934f3a75e2caffecd9705edfe9b12377e574a65f681cda6589e6c25";
    private static BufferedWriter resource;
    private static BufferedWriter memory;
    private static BufferedWriter allocation;
    private static BufferedWriter plateau;
    private static String binding;
    private static long emptyHeap;
    private static long peakHeap;
    private static long peakRss;

    private SustainedSidecars() {
    }

    public static BufferedWriter clock(String variable, String header) throws IOException {
        String name = System.getenv(variable);
        if (name == null) return null;
        BufferedWriter writer = Files.newBufferedWriter(Path.of(name));
        writer.write(header);
        writer.newLine();
        return writer;
    }

    public static void clockRow(BufferedWriter writer, int step, long begin, long end) throws IOException {
        if (writer != null) {
            writer.write(step + "," + begin + "," + end);
            writer.newLine();
        }
    }

    public static void openResource() throws IOException {
        String name = System.getenv("DYN4K_RESOURCE_CSV");
        if (name == null) return;
        resource = Files.newBufferedWriter(Path.of(name));
        resource.write("phase,step,heap_used_bytes,rss_bytes,allocation_bytes");
        resource.newLine();
    }

    public static void resource(String phase, int step, long heap, long rss, long allocation) throws IOException {
        peakHeap = Math.max(peakHeap, heap);
        peakRss = Math.max(peakRss, rss);
        if (resource != null) {
            resource.write(phase + "," + step + "," + heap + "," + rss + "," + allocation);
            resource.newLine();
        }
    }

    public static void closeResource() throws IOException {
        if (resource != null) resource.close();
        resource = null;
        if (memory != null) memory.close();
        if (allocation != null) allocation.close();
        if (plateau != null) plateau.close();
        memory = null;
        allocation = null;
        plateau = null;
    }

    public static final class AllocationProbe {
        private final ThreadMXBean bean;
        private final long threadId;

        private AllocationProbe(ThreadMXBean bean) {
            this.bean = bean;
            this.threadId = Thread.currentThread().threadId();
        }

        public static AllocationProbe require() {
            return require(ManagementFactory.getThreadMXBean());
        }

        static AllocationProbe require(java.lang.management.ThreadMXBean platform) {
            if (!(platform instanceof ThreadMXBean bean) || !bean.isThreadAllocatedMemorySupported())
                throw new IllegalStateException("per-thread allocation probe unsupported");
            if (!bean.isThreadAllocatedMemoryEnabled()) {
                try {
                    bean.setThreadAllocatedMemoryEnabled(true);
                } catch (RuntimeException unavailable) {
                    throw new IllegalStateException("per-thread allocation probe cannot be enabled", unavailable);
                }
            }
            AllocationProbe probe = new AllocationProbe(bean);
            probe.read();
            return probe;
        }

        public long read() {
            long value = bean.getThreadAllocatedBytes(threadId);
            if (value < 0 || Thread.currentThread().threadId() != threadId)
                throw new IllegalStateException("per-thread allocation reading unavailable or wrong thread");
            return value;
        }

        public long threadId() { return threadId; }
    }

    private static BufferedWriter optional(String variable) throws IOException {
        String path = System.getenv(variable);
        return path == null ? null : Files.newBufferedWriter(Path.of(path), StandardCharsets.UTF_8);
    }

    public static void openMemory(String api, String mode, String family, String variant,
                                  String size, int hz, int steps, int warmup) throws IOException {
        memory = optional("DYN4K_MEMORY_V2_JSONL");
        allocation = optional("DYN4K_ALLOCATION_V2_JSONL");
        plateau = optional("DYN4K_PLATEAU_V2_JSONL");
        if (memory == null && allocation == null && plateau == null) return;
        String providerPath = requiredEnvironment("DYN4K_PROVIDER_JSON");
        binding = "\"schema\":2,\"pid\":" + ProcessHandle.current().pid() +
                ",\"nonce\":" + quoted(requiredEnvironment("DYN4K_CLOCK_NONCE")) +
                ",\"source_commit\":" + quoted(requiredEnvironment("DYN4K_SOURCE_COMMIT")) +
                ",\"provider_sha256\":" + quoted(digest(Path.of(providerPath))) +
                ",\"fixture_sha256\":" + quoted(FIXTURE_SHA256) +
                ",\"clock_domain\":\"System.nanoTime\",\"memory_unit\":\"byte\"" +
                ",\"api\":" + quoted(api) + ",\"mode\":" + quoted(mode) +
                ",\"family\":" + quoted(family) + ",\"variant\":" + quoted(variant) +
                ",\"size\":" + quoted(size) + ",\"rate_hz\":" + hz +
                ",\"measured_steps\":" + steps + ",\"warmup_steps\":" + warmup;
    }

    public static void emptyHeap(long value) { emptyHeap = value; }

    public static void allocation(String phase, int step, AllocationProbe probe,
                                  long before, long after) throws IOException {
        if (after < before || before < 0) throw new IllegalStateException("allocation counter regressed");
        if (allocation == null) return;
        allocation.write("{" + binding + ",\"kind\":\"thread_allocation\",\"phase\":" + quoted(phase) +
                ",\"step\":" + step + ",\"clock_ns\":" + System.nanoTime() +
                ",\"thread_id\":" + probe.threadId() +
                ",\"counter_before_bytes\":" + before + ",\"counter_after_bytes\":" + after +
                ",\"allocation_bytes\":" + (after - before) +
                ",\"probe\":\"com.sun.management.ThreadMXBean.getThreadAllocatedBytes\"}");
        allocation.newLine();
    }

    private static Long bufferMemory() {
        long total = 0;
        boolean observed = false;
        for (BufferPoolMXBean pool : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            long used = pool.getMemoryUsed();
            if (used < 0) return null;
            total = Math.addExact(total, used);
            observed = true;
        }
        return observed ? total : null;
    }

    public static void memory(String phase, int step, long heap, long rss, long collectionDelta)
            throws IOException {
        boolean postCollection = collectionDelta > 0;
        if (phase.equals("retained") != postCollection ||
                (!phase.equals("retained") && collectionDelta != -1)) {
            closeResource();
            throw new IllegalStateException("retained post-collection probe unsupported: no collection observed");
        }
        if (memory == null) return;
        long delta = heap - emptyHeap;
        memory.write("{" + binding + ",\"kind\":\"memory_observation\",\"phase\":" + quoted(phase) +
                ",\"step\":" + step + ",\"clock_ns\":" + System.nanoTime() +
                ",\"heap_used_bytes\":" + heap + ",\"empty_heap_bytes\":" + emptyHeap +
                ",\"managed_heap_delta_bytes\":" + delta +
                ",\"managed_post_collection\":" + postCollection +
                ",\"collection_count_delta\":" + (postCollection ? collectionDelta : "null") +
                ",\"buffer_pool_used_bytes\":" + bufferMemory() +
                ",\"rss_bytes\":" + rss +
                ",\"native_workload_bytes\":null,\"attributed_workload_bytes\":null," +
                "\"native_attribution\":\"unsupported\",\"managed_provenance\":\"Runtime.totalMemory minus freeMemory delta from empty same process; includes unrelated heap objects\"," +
                "\"buffer_provenance\":\"BufferPoolMXBean process total; not workload attribution\"," +
                "\"qualification\":\"unpassed\"}");
        memory.newLine();
    }

    public static void requirePlateauCollection(long beforeCollections, long afterCollections)
            throws IOException {
        if (beforeCollections < 0 || afterCollections < 0) {
            closeResource();
            throw new IllegalStateException("post-collection plateau probe unsupported: collection count unknown");
        }
        if (afterCollections <= beforeCollections) {
            closeResource();
            throw new IllegalStateException("post-collection plateau probe unsupported: no collection observed");
        }
    }

    public static void plateau(int cycle, long heap, long rss, long beforeCollections,
                               long afterCollections, long cycleDisposedNs,
                               long beforeSampleNs, long gcRequestedNs, long afterSampleNs,
                               long heapSampleBeginNs, long heapSampleEndNs,
                               long rssSampleBeginNs, long rssSampleEndNs)
            throws IOException {
        requirePlateauCollection(beforeCollections, afterCollections);
        Long bufferPoolBytes = bufferMemory();
        long writtenNs = System.nanoTime();
        if (cycleDisposedNs <= 0 || cycleDisposedNs > beforeSampleNs ||
                beforeSampleNs > gcRequestedNs || gcRequestedNs > afterSampleNs ||
                afterSampleNs > heapSampleBeginNs || heapSampleBeginNs > heapSampleEndNs ||
                heapSampleEndNs > rssSampleBeginNs || rssSampleBeginNs > rssSampleEndNs ||
                rssSampleEndNs > writtenNs) {
            closeResource();
            throw new IllegalStateException("post-collection plateau probe unsupported: observation order invalid");
        }
        if (plateau == null) return;
        plateau.write("{" + binding + ",\"kind\":\"create_use_dispose\",\"cycle\":" + cycle +
                ",\"clock_ns\":" + writtenNs +
                ",\"cycle_disposed_ns\":" + cycleDisposedNs +
                ",\"collection_before_sample_ns\":" + beforeSampleNs +
                ",\"gc_requested_ns\":" + gcRequestedNs +
                ",\"collection_after_sample_ns\":" + afterSampleNs +
                ",\"heap_sample_begin_ns\":" + heapSampleBeginNs +
                ",\"heap_sample_end_ns\":" + heapSampleEndNs +
                ",\"rss_sample_begin_ns\":" + rssSampleBeginNs +
                ",\"rss_sample_end_ns\":" + rssSampleEndNs +
                ",\"heap_after_collection_bytes\":" + heap +
                ",\"rss_after_collection_bytes\":" + rss +
                ",\"collection_count\":" + afterCollections +
                ",\"collection_count_before\":" + beforeCollections +
                ",\"collection_count_after\":" + afterCollections +
                ",\"collection_count_delta\":" + (afterCollections - beforeCollections) +
                ",\"collection_count_unit\":\"collections\"" +
                ",\"collection_probe\":\"sum of GarbageCollectorMXBean.getCollectionCount\"" +
                ",\"collection_count_status\":\"observed\"" +
                ",\"managed_heap_delta_bytes\":" + (heap - emptyHeap) +
                ",\"buffer_pool_used_bytes\":" + bufferPoolBytes +
                ",\"native_workload_bytes\":null,\"attributed_workload_bytes\":null," +
                "\"reserved_runtime_bytes\":null,\"native_attribution\":\"unsupported\"," +
                "\"qualification\":\"unpassed\"}");
        plateau.newLine();
    }

    private static String digest(Path path) throws IOException {
        try {
            MessageDigest hash = MessageDigest.getInstance("SHA-256");
            try (var input = Files.newInputStream(path)) {
                byte[] buffer = new byte[65536];
                int count;
                while ((count = input.read(buffer)) >= 0) hash.update(buffer, 0, count);
            }
            return HexFormat.of().formatHex(hash.digest());
        } catch (NoSuchAlgorithmException missing) {
            throw new IllegalStateException(missing);
        }
    }

    private static String originDigest(Class<?> type) throws IOException {
        try {
            Path path = Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());
            if (!Files.isRegularFile(path)) throw new IOException("loaded class origin is not a binary file: " + path);
            return digest(path);
        } catch (URISyntaxException invalid) {
            throw new IOException("loaded class origin is invalid", invalid);
        }
    }

    private static String quoted(String value) {
        if (value == null) return "null";
        String escaped = value.replace("\\", "\\\\").replace("\"", "\\\"");
        return "\"" + escaped + "\"";
    }

    private static String requiredEnvironment(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) throw new IllegalStateException("missing " + name);
        return value;
    }

    private static String artifactHash(String input, String field) {
        Matcher match = Pattern.compile("\\\"" + field + "\\\"\\s*:\\s*\\\"([0-9a-f]{64})\\\"").matcher(input);
        if (!match.find()) throw new IllegalStateException("missing staged " + field + " hash");
        return match.group(1);
    }

    public static void provider(String api, Class<?> core, Class<?> adapter, Class<?> kotlin) throws IOException {
        String originPath = System.getenv("DYN4K_CLOCK_ORIGIN_JSON");
        if (originPath != null) {
            String nonce = requiredEnvironment("DYN4K_CLOCK_NONCE");
            long runtimeNs = System.nanoTime();
            String origin = "{\"pid\":" + ProcessHandle.current().pid() +
                    ",\"runtime_ns\":" + runtimeNs +
                    ",\"nonce\":" + quoted(nonce) + "}";
            Files.writeString(Path.of(originPath), origin + "\n", StandardCharsets.UTF_8);
        }
        String name = System.getenv("DYN4K_PROVIDER_JSON");
        if (name == null) return;
        String commit = requiredEnvironment("DYN4K_SOURCE_COMMIT");
        String baseline = requiredEnvironment("DYN4K_BASELINE_SHA256");
        String artifacts = requiredEnvironment("DYN4K_ARTIFACT_HASHES_JSON");
        String coreExpected = artifactHash(artifacts, "core");
        String kotlinExpected = artifactHash(artifacts, "kotlin");
        String runtime = digest(Path.of("/proc/self/exe"));
        String loadedCore = originDigest(core);
        String loadedHarness = originDigest(SustainedSidecars.class);
        String loadedAdapter = originDigest(adapter);
        String loadedKotlin = kotlin == null ? null : originDigest(kotlin);
        String json = "{" +
                "\"pid\":" + ProcessHandle.current().pid() + "," +
                "\"runtime_sha256\":" + quoted(runtime) + "," +
                "\"source_commit\":" + quoted(commit) + "," +
                "\"api\":" + quoted(api) + "," +
                "\"artifact_sha256\":{\"core\":" + quoted(coreExpected) +
                ",\"kotlin\":" + quoted(kotlinExpected) + "}," +
                "\"baseline_sha256\":" + quoted(baseline) + "," +
                "\"loaded_core_sha256\":" + quoted(loadedCore) + "," +
                "\"loaded_kotlin_sha256\":" + quoted(loadedKotlin) + "," +
                "\"loaded_harness_sha256\":" + quoted(loadedHarness) + "," +
                "\"loaded_adapter_sha256\":" + quoted(loadedAdapter) + "," +
                "\"loaded_fixture_sha256\":" + quoted(FIXTURE_SHA256) + "}";
        Files.writeString(Path.of(name), json + "\n", StandardCharsets.UTF_8);
    }

    public static void run(String api, String mode, int samples, int warmup,
                           long measuredWallNs, int activeSteps) throws IOException {
        String name = System.getenv("DYN4K_RUN_JSON");
        if (name == null) return;
        String json = "{" +
                "\"api\":" + quoted(api) + "," +
                "\"mode\":" + quoted(mode) + "," +
                "\"sample_count\":" + samples + "," +
                "\"warmup_count\":" + warmup + "," +
                "\"measured_wall_ns\":" + measuredWallNs + "," +
                "\"active_steps\":" + activeSteps + "," +
                "\"peak_heap_used_bytes\":" + peakHeap + "," +
                "\"peak_rss_bytes\":" + peakRss + "," +
                "\"memory_attribution\":\"unvalidated\"," +
                "\"status\":\"complete\"}";
        Files.writeString(Path.of(name), json + "\n", StandardCharsets.UTF_8);
    }
}
