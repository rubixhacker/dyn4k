import java.io.IOException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.Map;
import java.util.TreeMap;

public final class RuntimeStamp {
    private RuntimeStamp() {}

    public static void write(Path directory, Class<?> engine, Class<?> recorder) throws IOException {
        ProcessHandle process = ProcessHandle.current();
        String command = process.info().command().orElseThrow(() ->
            new IllegalStateException("recorder process command is unavailable"));
        Instant start = process.info().startInstant().orElseThrow(() ->
            new IllegalStateException("recorder process start is unavailable"));
        Map<String,String> values = new TreeMap<>();
        values.put("process_command", Path.of(command).toRealPath().toString());
        values.put("process_id", Long.toString(process.pid()));
        values.put("process_start", start.toString());
        values.put("java_home", System.getProperty("java.home"));
        values.put("java_version", System.getProperty("java.version"));
        values.put("java_vm_name", System.getProperty("java.vm.name"));
        values.put("java_vm_version", System.getProperty("java.vm.version"));
        values.put("os_name", System.getProperty("os.name"));
        values.put("os_arch", System.getProperty("os.arch"));
        values.put("engine_location", location(engine));
        values.put("recorder_location", location(recorder));
        StringBuilder result = new StringBuilder("{");
        for (Map.Entry<String,String> entry : values.entrySet()) {
            if (result.length() != 1) result.append(',');
            result.append(quote(entry.getKey())).append(':').append(quote(entry.getValue()));
        }
        result.append("}\n");
        Files.writeString(directory.resolve("runtime.json"), result.toString(), StandardCharsets.UTF_8,
            StandardOpenOption.CREATE_NEW);
    }

    private static String location(Class<?> type) {
        URL url = type.getProtectionDomain().getCodeSource().getLocation();
        if (url == null) throw new IllegalStateException("class code source is unavailable: " + type);
        return url.toExternalForm();
    }

    private static String quote(String value) {
        StringBuilder result = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c == '\\' || c == '"') result.append('\\').append(c);
            else if (c < 0x20) result.append(String.format("\\u%04x", (int)c));
            else result.append(c);
        }
        return result.append('"').toString();
    }
}
