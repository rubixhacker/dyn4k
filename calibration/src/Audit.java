import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.zip.*;

/** Independent structural audit and lossless line-selection derivative of closed captures. */
public final class Audit {
    static long files, planned, states, rejected, events, records, derivativeRecords;
    public static void main(String[] args) throws Exception {
        if(args.length==1 && args[0].equals("--help")) {
            System.out.println("Usage: java Audit --complete RAW_DIRECTORY NEW_DERIVATIVE_DIRECTORY [EXPECTED_PLANNED_STEPS]\nRun only after capture processes exit. Reads summary.jsonl and each raw gzip once; retains inputs/state/action lines. Structural integrity is distinct from completed physics or numerical acceptance."); return;
        }
        if(args.length<3||args.length>4||!args[0].equals("--complete"))throw new IllegalArgumentException("Use --help; explicit --complete required");
        Path source=Path.of(args[1]),out=Path.of(args[2]);
        Files.createDirectory(out);
        Path summary=source.resolve("summary.jsonl");
        byte[] summaryBytes=Files.readAllBytes(summary);
        Set<String> names=new HashSet<>();
        try(BufferedWriter manifest=Files.newBufferedWriter(out.resolve("audit-manifest.jsonl"),StandardOpenOption.CREATE_NEW)) {
            for(String line:new String(summaryBytes,StandardCharsets.UTF_8).split("\\R")) {
                if(line.isBlank())continue;
                Map<String,String> row=top(line);
                String name=text(row,"file");
                if(!names.add(name))throw new IllegalStateException("Duplicate summary file: "+name);
                if(!Path.of(name).getFileName().toString().equals(name))throw new IllegalStateException("Non-flat trace filename");
                audit(source.resolve(name),out.resolve(name),row,manifest);
            }
            if(!Arrays.equals(summaryBytes,Files.readAllBytes(summary)))throw new IllegalStateException("Summary changed during audit");
            long actualFiles;try(var paths=Files.list(source)){actualFiles=paths.filter(p->p.toString().endsWith(".jsonl.gz")).count();}
            if(actualFiles!=files)throw new IllegalStateException("Unindexed gzip files: indexed="+files+" found="+actualFiles);
            if(args.length==4&&planned!=Long.parseLong(args[3]))throw new IllegalStateException("Planned count mismatch: "+planned);
            Files.write(out.resolve("summary.jsonl"),summaryBytes,StandardOpenOption.CREATE_NEW);
            String totals="{\"kind\":\"audit-totals\",\"structuralIntegrity\":\"PASS\",\"physicsCompletion\":"+quote(rejected==0?"all indexed steps captured":"INCOMPLETE: rejected cases retained")+",\"files\":"+files+",\"plannedSteps\":"+planned+",\"capturedStates\":"+states+",\"uncapturedPlannedSteps\":"+(planned-states)+",\"rejectedCases\":"+rejected+",\"rawRecords\":"+records+",\"listenerEvents\":"+events+",\"derivativeRecords\":"+derivativeRecords+",\"summarySha256\":"+quote(hex(MessageDigest.getInstance("SHA-256").digest(summaryBytes)))+"}";
            manifest.write(totals);manifest.newLine();System.out.println(totals);
        }
    }
    static void audit(Path raw,Path derivative,Map<String,String> summary,BufferedWriter manifest)throws Exception {
        long size=Files.size(raw),modified=Files.getLastModifiedTime(raw).toMillis();
        String filename=raw.getFileName().toString(),id=text(summary,"id");
        int end=filename.length()-".jsonl.gz".length();
        long start=Long.parseLong(filename.substring(filename.lastIndexOf('-',end)+1,end));
        boolean reject="REJECTED_NONFINITE".equals(optionalText(summary,"status"));
        long expected=num(summary,reject?"expectedSteps":"steps"),failure=reject?num(summary,"firstFailureStep"):-1;
        long count=0,ev=0,total=0,kept=0,lastState=start,currentStep=start,lastOrder=-1;
        MessageDigest inHash=MessageDigest.getInstance("SHA-256"),outHash=MessageDigest.getInstance("SHA-256");
        try(BufferedReader reader=new BufferedReader(new InputStreamReader(new GZIPInputStream(new DigestInputStream(Files.newInputStream(raw),inHash),65536),StandardCharsets.UTF_8),65536);
            BufferedWriter writer=new BufferedWriter(new OutputStreamWriter(new GZIPOutputStream(new DigestOutputStream(Files.newOutputStream(derivative,StandardOpenOption.CREATE_NEW),outHash),65536),StandardCharsets.UTF_8),65536)) {
            String line;while((line=reader.readLine())!=null) {
                total++;Map<String,String> fields=top(line);String kind=text(fields,"kind");
                if(total==1) {
                    require(kind.equals("inputs"),raw,"missing initial input header");
                    require(text(fields,"id").equals(id),raw,"input id mismatch");
                    require(num(fields,"steps")==expected,raw,"input expected count mismatch");
                    require(fields.containsKey("state")&&fields.containsKey("settings")&&fields.containsKey("world"),raw,"incomplete input sections");
                } else {
                    require(!kind.equals("inputs"),raw,"duplicate input header");
                    long step=num(fields,"step");
                    require(step>=currentStep&&step<=lastState+1,raw,"noncontiguous or reversed step");
                    if(step!=currentStep){currentStep=step;lastOrder=-1;}
                    if(reject)require(step<=failure,raw,"record after rejection step");
                    if(kind.equals("state")) {
                        require(step==lastState+1,raw,"duplicate or missing state");
                        if(reject)require(step<failure,raw,"state at/after nonfinite failure");
                        lastState=step;count++;
                    } else {
                        require(Set.of("event","action","instrumented-callback").contains(kind),raw,"unknown record kind "+kind);
                        long order=num(fields,"order");
                        require(order==lastOrder+1,raw,"noncontiguous within-step event order");lastOrder=order;
                        if(kind.equals("event"))ev++;
                    }
                }
                if(kind.equals("inputs")||kind.equals("state")||kind.equals("action")){writer.write(line);writer.newLine();kept++;}
            }
        }
        require(total>0,raw,"empty gzip");
        require(Files.size(raw)==size&&Files.getLastModifiedTime(raw).toMillis()==modified,raw,"file changed during read");
        require(count==(reject?failure-start-1:expected),raw,"state count mismatch: "+count);
        if(!reject)require(ev==num(summary,"events"),raw,"listener event count mismatch");
        if(reject)require(failure>=start+1&&failure<=start+expected,raw,"rejection outside planned segment");
        String row="{\"file\":"+quote(filename)+",\"id\":"+quote(id)+",\"rawSha256\":"+quote(hex(inHash.digest()))+",\"derivativeSha256\":"+quote(hex(outHash.digest()))+",\"rawBytes\":"+size+",\"derivativeBytes\":"+Files.size(derivative)+",\"rawRecords\":"+total+",\"derivativeRecords\":"+kept+",\"states\":"+count+",\"listenerEvents\":"+ev+",\"plannedSteps\":"+expected+",\"startStep\":"+start+",\"rejected\":"+reject+",\"firstFailureStep\":"+failure+"}";
        manifest.write(row);manifest.newLine();manifest.flush();
        files++;planned+=expected;states+=count;records+=total;derivativeRecords+=kept;events+=ev;if(reject)rejected++;
        System.out.println("AUDITED "+filename+" states="+count+" planned="+expected+" rejected="+reject);
    }
    static void require(boolean condition,Path path,String message){if(!condition)throw new IllegalStateException(path+": "+message);}
    static long num(Map<String,String> m,String key){String v=m.get(key);if(v==null)throw new IllegalArgumentException("Missing "+key);return Long.parseLong(v);}
    static String optionalText(Map<String,String>m,String key){return m.containsKey(key)?text(m,key):"";}
    static String text(Map<String,String> m,String key){String s=m.get(key);if(s==null||s.length()<2||s.charAt(0)!='"'||s.charAt(s.length()-1)!='"')throw new IllegalArgumentException("Expected text "+key);return s.substring(1,s.length()-1);}
    static String quote(String s){return "\""+s.replace("\\","\\\\").replace("\"","\\\"")+"\"";}
    static String hex(byte[] bytes){return HexFormat.of().formatHex(bytes);}
    /** Select top-level raw values without allocating or confusing nested payload members. */
    static Map<String,String> top(String s) {
        Map<String,String> result=new HashMap<>();int i=space(s,0);if(i>=s.length()||s.charAt(i++)!='{')throw new IllegalArgumentException("Expected object");
        while(true){i=space(s,i);if(i>=s.length())throw new IllegalArgumentException("Unclosed object");if(s.charAt(i)=='}'){i++;break;}
            int keyStart=i;i=stringEnd(s,i);String key=s.substring(keyStart+1,i-1);i=space(s,i);if(s.charAt(i++)!=':')throw new IllegalArgumentException("Expected colon");i=space(s,i);int begin=i;
            char c=s.charAt(i);if(c=='"')i=stringEnd(s,i);else if(c=='{'||c=='['){int depth=0;do{char v=s.charAt(i);if(v=='"'){i=stringEnd(s,i);continue;}if(v=='{'||v=='[')depth++;if(v=='}'||v==']')depth--;i++;}while(depth>0&&i<s.length());if(depth!=0)throw new IllegalArgumentException("Unclosed nested value");}else{while(i<s.length()&&s.charAt(i)!=','&&s.charAt(i)!='}')i++;}
            if(result.put(key,(key.equals("state")||key.equals("settings")||key.equals("world")||key.equals("payload")||key.equals("values"))?"present":s.substring(begin,i).trim())!=null)throw new IllegalArgumentException("Duplicate top-level key");
            i=space(s,i);if(i<s.length()&&s.charAt(i)==','){i++;continue;}if(i<s.length()&&s.charAt(i)=='}'){i++;break;}throw new IllegalArgumentException("Expected separator");
        }
        if(space(s,i)!=s.length())throw new IllegalArgumentException("Trailing JSON");return result;
    }
    static int space(String s,int i){while(i<s.length()&&Character.isWhitespace(s.charAt(i)))i++;return i;}
    static int stringEnd(String s,int i){if(s.charAt(i++)!='"')throw new IllegalArgumentException("Expected string");while(i<s.length()){char c=s.charAt(i++);if(c=='"')return i;if(c=='\\')i++;}throw new IllegalArgumentException("Unclosed string");}
}
