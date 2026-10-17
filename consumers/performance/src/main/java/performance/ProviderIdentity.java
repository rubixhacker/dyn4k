package performance;

import java.net.URL;

public final class ProviderIdentity {
    private static String origin(String name) throws Exception {
        Class<?> type = Class.forName(name);
        URL source = type.getProtectionDomain().getCodeSource().getLocation();
        return source.toURI().getPath();
    }

    public static void main(String[] args) throws Exception {
        String core = origin("org.dyn4j.world.World");
        String api;
        try {
            api = origin("io.github.rubixhacker.dyn4k.WorldConveniencesKt");
        } catch (ClassNotFoundException missing) {
            api = "unavailable";
        }
        System.out.println("core=" + core);
        System.out.println("api=" + api);
        System.out.println("java_version=" + System.getProperty("java.version"));
        System.out.println("pid=" + ProcessHandle.current().pid());
    }
}
