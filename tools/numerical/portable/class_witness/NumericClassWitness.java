package dyn4k.witness;

import java.io.IOException;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.net.URISyntaxException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.security.CodeSource;
import java.security.MessageDigest;
import java.security.ProtectionDomain;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Locale;
import java.util.Set;

public final class NumericClassWitness {
    private static final String[] CRITICAL = {
        "portable/NumericProbeMatrixTest", "portable/PortableMatrixTest",
        "portable/NumericalRecorder"
    };
    private static final char[] HEX = "0123456789abcdef".toCharArray();
    private static FileChannel output;
    private static final Set<String> seen = new HashSet<String>();
    private static final IdentityHashMap<ClassLoader, String> loaders =
        new IdentityHashMap<ClassLoader, String>();
    private static int count;
    private static boolean failed;

    private NumericClassWitness() {}

    private static boolean relevant(String name) {
        return name != null && (name.startsWith("portable/") || name.startsWith("org/dyn4j/"));
    }

    private static void provider(Class<?> type, Path jar) throws Exception {
        CodeSource source = type.getProtectionDomain().getCodeSource();
        if (type.getClassLoader() != ClassLoader.getSystemClassLoader() || source == null ||
            !Paths.get(source.getLocation().toURI()).toRealPath().equals(jar)) {
            throw new IllegalStateException("class witness helper provider differs");
        }
    }

    private static void write(String line) throws IOException {
        ByteBuffer bytes = ByteBuffer.wrap(line.getBytes(StandardCharsets.US_ASCII));
        while (bytes.hasRemaining()) {
            output.write(bytes);
        }
    }

    private static String hash(byte[] bytes) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
        char[] text = new char[digest.length * 2];
        for (int index = 0; index < digest.length; index++) {
            text[index * 2] = HEX[(digest[index] & 255) >>> 4];
            text[index * 2 + 1] = HEX[digest[index] & 15];
        }
        return new String(text);
    }

    private static synchronized void record(ClassLoader loader, String name,
                                             Class<?> redefining, ProtectionDomain domain,
                                             byte[] bytes) {
        try {
            if (redefining != null || bytes == null || !seen.add(name) || domain == null ||
                domain.getCodeSource() == null) {
                throw new IllegalStateException("class witness definition is ambiguous");
            }
            String id;
            if (loader == null) {
                id = "bootstrap";
            } else if (loader == ClassLoader.getSystemClassLoader()) {
                id = "system";
            } else {
                id = loaders.get(loader);
                if (id == null) {
                    id = "L" + (loaders.size() + 1);
                    loaders.put(loader, id);
                }
            }
            String origin = domain.getCodeSource().getLocation().toURI().toASCIIString();
            if (origin.indexOf('\t') >= 0 || origin.indexOf('\n') >= 0 ||
                name.indexOf('\t') >= 0 || name.indexOf('\n') >= 0) {
                throw new IllegalStateException("class witness record is malformed");
            }
            count++;
            write("CLASS\t" + count + "\t" + name + "\t" + hash(bytes) + "\t" + id +
                  "\t" + origin + "\tjava:" + Thread.currentThread().getId() + "\n");
        } catch (Throwable error) {
            failed = true;
        }
    }

    private static final class Observer implements ClassFileTransformer {
        @Override
        public byte[] transform(ClassLoader loader, String name, Class<?> redefining,
                                ProtectionDomain domain, byte[] bytes) {
            if (relevant(name)) {
                record(loader, name, redefining, domain, bytes);
            }
            return null;
        }
    }

    private static synchronized void finish() {
        try {
            for (String name : CRITICAL) {
                if (!seen.contains(name)) {
                    failed = true;
                }
            }
            String status = failed ? "FAIL" : "OK";
            String start = "END\t" + status + "\t" + count + "\t";
            long finalSize = output.size() + start.length() + 21;
            write(start + String.format(Locale.ROOT, "%020d", finalSize) + "\n");
            output.force(true);
            if (output.size() != finalSize) {
                failed = true;
            }
            output.close();
        } catch (Throwable error) {
            failed = true;
        }
        if (failed) {
            Runtime.getRuntime().halt(86);
        }
    }

    public static void premain(String destination, Instrumentation instrumentation) throws Exception {
        Path jar = Paths.get(NumericClassWitness.class.getProtectionDomain()
            .getCodeSource().getLocation().toURI()).toRealPath();
        provider(NumericClassWitness.class, jar);
        provider(Observer.class, jar);
        if (instrumentation.isRetransformClassesSupported() ||
            instrumentation.isRedefineClassesSupported()) {
            throw new IllegalStateException("class witness capability differs");
        }
        for (Class<?> loaded : instrumentation.getAllLoadedClasses()) {
            if (relevant(loaded.getName().replace('.', '/'))) {
                throw new IllegalStateException("relevant class was loaded before witness registration");
            }
        }
        MessageDigest.getInstance("SHA-256");
        ByteBuffer.allocate(1);
        Path path = Paths.get(destination);
        output = FileChannel.open(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        write("BEGIN\tclass-witness/1\n");
        Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
            @Override public void run() { finish(); }
        }, "numeric-class-witness-finish"));
        instrumentation.addTransformer(new Observer(), false);
    }
}
