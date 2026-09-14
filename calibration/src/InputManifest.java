import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.zip.GZIPInputStream;

/** Extracts immutable input headers from a previously audited trace directory. */
public final class InputManifest {
    public static void main(String[] args) throws Exception {
        if(args.length!=2)throw new IllegalArgumentException("Usage: InputManifest AUDITED_TRACE_DIRECTORY NEW_JSONL");
        try(var files=Files.list(Path.of(args[0]));BufferedWriter out=Files.newBufferedWriter(Path.of(args[1]),StandardOpenOption.CREATE_NEW)) {
            for(Path file:files.filter(p->p.toString().endsWith(".jsonl.gz")).sorted().toList()) {
                try(BufferedReader in=new BufferedReader(new InputStreamReader(new GZIPInputStream(Files.newInputStream(file)),StandardCharsets.UTF_8))) {
                    String header=in.readLine();
                    if(header==null||!header.contains("\"kind\":\"inputs\""))throw new IOException("Missing header "+file);
                    String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(header.getBytes(StandardCharsets.UTF_8)));
                    out.write("{\"traceFile\":\""+file.getFileName()+"\",\"inputSha256\":\""+hash+"\",\"input\":"+header+"}");out.newLine();
                }
            }
        }
    }
}
