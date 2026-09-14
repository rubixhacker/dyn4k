import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.zip.GZIPInputStream;

/** Streaming diagnostics only: no numerical acceptance threshold is assigned here. */
public final class Analyze {
    private record Case(Path file, Map<String,Object> input, Map<String,Object> summary) {
        String id(){return string(input.get("id"));}
        double scale(){return number(input.get("scale"));}
        int hz(){return (int)Math.round(1/number(input.get("dt")));}
        boolean grid(){return id().startsWith("U-scale-") || (id().contains("-s")&&id().contains("-hz"));}
        String family(){if(id().startsWith("U-scale-")){String filename=file.getFileName().toString();return id().split("-")[2]+"/segment"+filename.substring(filename.lastIndexOf("-")+1,filename.indexOf(".jsonl.gz"));}int i=id().lastIndexOf("-s");return i<0?id():id().substring(0,i);}
        List<Object> origin(){return list(input.get("origin"));}
        String key(){return family()+"|"+scale()+"|"+origin()+"|"+hz();}
    }
    public static void main(String[] args) throws Exception {
        if(args.length==1 && args[0].equals("--help")){System.out.println("Usage: java Analyze CAPTURE_DIRECTORY OUTPUT_PREFIX [INDEX COUNT]\nOptional zero-based INDEX selects summary rows modulo positive COUNT; all references remain available.\nStreams retained traces; writes diagnostic JSON and Markdown. No tolerances or pass verdicts.");return;}
        if(args.length!=2&&args.length!=4)throw new IllegalArgumentException("Expected CAPTURE_DIRECTORY OUTPUT_PREFIX [INDEX COUNT]; use --help");
        int partitionIndex=args.length==4?Integer.parseInt(args[2]):0;
        int partitionCount=args.length==4?Integer.parseInt(args[3]):1;
        if(partitionCount<=0||partitionIndex<0||partitionIndex>=partitionCount)throw new IllegalArgumentException("Require COUNT > 0 and 0 <= INDEX < COUNT");
        Path dir=Path.of(args[0]),prefix=Path.of(args[1]);
        List<Case> cases=new ArrayList<>();Map<String,Case> keyed=new HashMap<>();
        try(BufferedReader r=Files.newBufferedReader(dir.resolve("summary.jsonl"))){String line;while((line=r.readLine())!=null){Map<String,Object> s=object(parse(line));Path file=dir.resolve(string(s.get("file")));try(Trace t=new Trace(file)){Case c=new Case(file,t.input,s);cases.add(c);if(c.grid())keyed.put(c.key(),c);}}}
        List<Object> coverage=new ArrayList<>(),energy=new ArrayList<>(),comparisons=new ArrayList<>(),missing=new ArrayList<>();
        for(int caseIndex=0;caseIndex<cases.size();caseIndex++){
            if(caseIndex%partitionCount!=partitionIndex)continue;
            Case c=cases.get(caseIndex);
            Map<String,Object> row=new LinkedHashMap<>();row.put("id",c.id());row.put("summary",c.summary);
            List<String> gaps=new ArrayList<>();boolean contact=c.id().startsWith("C-")||c.id().startsWith("CCD-world");
            if(contact&&number(c.summary.get("solvedContactCallbacks"))==0)gaps.add("no solved contact callbacks");
            if(c.id().startsWith("CCD-world")&&c.id().contains("-ALL")&&number(c.summary.get("toiPayloadCallbacks"))==0)gaps.add("ALL mode has no TOI payload callbacks");
            if(c.id().startsWith("C-stack")&&number(c.summary.get("stepsWithSleepingDynamicBody"))==0)gaps.add("no sleeping dynamic body observed");
            if(c.id().startsWith("C-stack")||c.id().startsWith("CCD-world")){
                List<Object> actions=new ArrayList<>();boolean sleepTrigger=false;double lowest=Double.POSITIVE_INFINITY;
                try(Trace t=new Trace(c.file)){Map<String,Object> event;while((event=t.nextRelevant(true))!=null){
                    if("action".equals(event.get("kind"))){actions.add(event);if(string(event.get("description")).contains("sleepingBefore=true"))sleepTrigger=true;}
                    else if(c.id().startsWith("CCD-world")){List<Object>b=list(object(event.get("state")).get("bodies"));lowest=Math.min(lowest,number(list(object(b.get(1)).get("fixedOriginPosition")).get(1))/c.scale());}
                }}
                row.put("actions",actions);
                if(c.id().startsWith("C-stack")&&!sleepTrigger)gaps.add("wake action did not reach a sleeping top body");
                if(c.id().startsWith("CCD-world")){row.put("minimumNormalizedProjectileCenterY",lowest);row.put("projectileCentreCrossedBelowGroundBottom",lowest < -0.025);row.put("fullyBelowGroundBoundingRadius",lowest < -0.125);}
            }
            row.put("coverageGaps",gaps);coverage.add(row);
            if(c.id().startsWith("L-spring"))energy.add(springEnergy(c));
            if(c.grid()){
                Case nominal=keyed.get(c.family()+"|1.0|[0.0, 0.0]|"+c.hz());
                if(nominal==null)missing.add(Map.of("id",c.id(),"comparison","scale/origin","reason","nominal same-Hz trace absent"));
                else if(nominal!=c)comparisons.add(compare(nominal,c,"scale/origin"));
                if(c.hz()!=60){Case base=keyed.get(c.family()+"|"+c.scale()+"|"+c.origin()+"|60");if(base==null)missing.add(Map.of("id",c.id(),"comparison","timestep","reason","same scale/origin 60Hz trace absent"));else comparisons.add(compare(base,c,"timestep"));}
            }
            System.out.println("ANALYZED "+c.id());
        }
        Map<String,Object> report=new LinkedHashMap<>();report.put("status","exploratory diagnostics; no approved numerical bounds");report.put("caseCount",coverage.size());report.put("referenceCatalogCount",cases.size());report.put("partitionIndex",partitionIndex);report.put("partitionCount",partitionCount);report.put("coverage",coverage);report.put("springEnergy",energy);report.put("comparisons",comparisons);report.put("missingReferences",missing);
        report.put("comparisonScope","Every matched physical-time body position, velocity, angle, unwrapped rotation, force/torque and joint reactions/anchors/current distance. Contacts/events are coverage counts, not cross-run matched impulses. Normalization removes fixed origin and dimensional scale. No per-run recentering. First difference means exact unequal doubles, not an acceptance failure.");
        Path json=Path.of(prefix+".json"),md=Path.of(prefix+".md");if(json.toAbsolutePath().getParent()!=null)Files.createDirectories(json.toAbsolutePath().getParent());
        Files.writeString(json,encode(report)+"\n",StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
        StringBuilder text=new StringBuilder("# Baseline diagnostic measurements\n\nNo numerical limits or invariant acceptance are established by this report.\n\n");
        text.append("Cases: ").append(coverage.size()).append(". Reference catalog: ").append(cases.size()).append(". Partition: ").append(partitionIndex).append("/").append(partitionCount).append(" (zero-based). Matched trajectory comparisons: ").append(comparisons.size()).append(". Missing references: ").append(missing.size()).append(".\n\n");
        text.append("## Coverage gaps\n\n");int count=0;for(Object v:coverage){Map<String,Object>r=object(v);List<Object>g=list(r.get("coverageGaps"));if(!g.isEmpty()){text.append("- ").append(r.get("id")).append(": ").append(g).append('\n');count++;}}if(count==0)text.append("No contact/CCD/stack-sleep gaps detected by these checks. Other mode coverage requires its own audit.\n");
        text.append("\n## Largest normalized trajectory differences\n\nDifferences are componentwise maxima at common physical times, not acceptance failures. Values are normalized to nominal length/mass units. See JSON for every component maximum and the first differing sample.\n\n| Case | Comparison | Largest difference | Quantity | Time (s) |\n| --- | --- | ---: | --- | ---: |\n");
        for(Object v:comparisons){Map<String,Object>r=object(v);Map<String,Object>m=object(r.get("maxima"));String key="none";Map<String,Object>best=Map.of("absoluteDifference",0,"time",0);for(var e:m.entrySet()){Map<String,Object>x=object(e.getValue());if(number(x.get("absoluteDifference"))>number(best.get("absoluteDifference"))){best=x;key=e.getKey();}}text.append("| ").append(r.get("actual")).append(" | ").append(r.get("comparison")).append(" | ").append(best.get("absoluteDifference")).append(" | ").append(key).append(" | ").append(best.get("time")).append(" |\n");}
        text.append("\n## Spring mechanical-energy diagnostics\n\nE = Σ(½mv² + ½Iω² − m g·(x−O)) + ½k(d−rest)². Source: pinned DistanceJoint.updateSpringCoefficients uses reduced mass and k=mReduced(2πf)². Initial stiffness is calculated from initial masses/frequency because upstream computes the effective getter at first initialization. Captured stiffness is checked against that value. Energy drift is a baseline diagnostic, including undamped numerical dissipation; damped cases intentionally dissipate energy. No conservation bound is approved.\n\n");
        for(Object v:energy){Map<String,Object>r=object(v);text.append("- ").append(r.get("id")).append(": initial energy ").append(r.get("initialEnergy")).append("; max absolute drift ").append(r.get("maxAbsoluteEnergyDrift")).append("; max stiffness discrepancy ").append(r.get("maxEffectiveStiffnessDifference")).append(".\n");}
        text.append("\nComparisons cover bodies and selected joint fields, not contact identity alignment or every joint mode/cap. CCD centre crossing is geometric observation, not by itself a solver verdict. See JSON for exact actions, source summaries, missing references and first differences.\n");
        Files.writeString(md,text.toString(),StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
    }
    private static Map<String,Object> springEnergy(Case c)throws IOException{
        Map<String,Object> initialState=object(c.input.get("state"));List<Object>initialBodies=list(initialState.get("bodies"));List<Object>joints=list(initialState.get("joints"));Map<String,Object>j=object(joints.get(0));
        double m0=mass(object(initialBodies.get(0)),"getMass"),m1=mass(object(initialBodies.get(1)),"getMass");double reduced=m0>0&&m1>0?m0*m1/(m0+m1):Math.max(m0,m1);
        double frequency=number(j.get("getSpringFrequency")),expected=reduced*Math.pow(2*Math.PI*frequency,2);
        double initialEnergy=mechanical(initialState,initialBodies,c.input,expected);double max=0,kdiff=0,last=initialEnergy;int first=-1;Map<String,Object>firstSample=Map.of();int count=0;
        try(Trace t=new Trace(c.file)){Map<String,Object>line;while((line=t.nextRelevant(false))!=null){Map<String,Object>s=object(line.get("state"));Map<String,Object>joint=object(list(s.get("joints")).get(0));double k=number(joint.get("getSpringStiffness"));kdiff=Math.max(kdiff,Math.abs(k-expected));last=mechanical(s,initialBodies,c.input,k);double drift=Math.abs(last-initialEnergy);max=Math.max(max,drift);count++;if(first<0&&drift!=0){first=(int)number(line.get("step"));firstSample=Map.of("step",first,"reference",initialEnergy,"actual",last,"absoluteDifference",drift);}}}
        Map<String,Object>r=new LinkedHashMap<>();r.put("id",c.id());r.put("modelStiffness",expected);r.put("initialEnergy",initialEnergy);r.put("finalEnergy",last);r.put("maxAbsoluteEnergyDrift",max);r.put("maxEffectiveStiffnessDifference",kdiff);r.put("firstExactEnergyDifference",firstSample);r.put("states",count);return r;
    }
    private static double mass(Map<String,Object>b,String property){return number(object(object(b.get("properties")).get("getMass")).get(property));}
    private static double mechanical(Map<String,Object>state,List<Object>initialBodies,Map<String,Object>input,double k){
        double e=0;List<Object>gravity=list(object(input.get("world")).get("gravity")),bodies=list(state.get("bodies"));
        for(int i=0;i<bodies.size();i++){Map<String,Object>b=object(bodies.get(i));double m=mass(object(initialBodies.get(i)),"getMass"),inertia=mass(object(initialBodies.get(i)),"getInertia"),omega=number(b.get("angularVelocity"));List<Object>v=list(b.get("velocity")),p=list(b.get("fixedOriginPosition"));e+=0.5*m*(square(number(v.get(0)))+square(number(v.get(1))))+0.5*inertia*omega*omega-m*(number(gravity.get(0))*number(p.get(0))+number(gravity.get(1))*number(p.get(1)));}
        Map<String,Object>j=object(list(state.get("joints")).get(0));return e+0.5*k*square(number(j.get("getCurrentDistance"))-number(j.get("getRestDistance")));
    }
    private static double square(double x){return x*x;}
    private static Map<String,Object> compare(Case reference,Case actual,String mode)throws IOException{
        Map<String,Object> maxima=new TreeMap<>();Map<String,Object>first=new LinkedHashMap<>();long matched=0,restDifferences=0;
        try(Trace a=new Trace(reference.file);Trace b=new Trace(actual.file)){
            Map<String,Object>x=a.nextRelevant(false),y=b.nextRelevant(false);
            while(x!=null&&y!=null){long i=(long)number(x.get("step")),j=(long)number(y.get("step"));long left=i*actual.hz(),right=j*reference.hz();if(left<right){x=a.nextRelevant(false);continue;}if(right<left){y=b.nextRelevant(false);continue;}
                double time=(double)i/reference.hz();Map<String,Double>v=quantities(object(x.get("state")),reference),w=quantities(object(y.get("state")),actual);
                if(!v.keySet().equals(w.keySet()))throw new IllegalStateException("Mismatched observable keys: "+actual.id());
                for(String key:v.keySet()){double ref=v.get(key),act=w.get(key),delta=act-ref;if(key.endsWith(".orientation"))delta=Math.atan2(Math.sin(delta),Math.cos(delta));double error=Math.abs(delta);Map<String,Object>entry=Map.of("reference",ref,"actual",act,"absoluteDifference",error,"time",time,"referenceStep",i,"actualStep",j);
                    if(!maxima.containsKey(key)||number(object(maxima.get(key)).get("absoluteDifference"))<error)maxima.put(key,entry);
                    if(error>0&&first.isEmpty()){first.put("quantity",key);first.putAll(entry);}
                }
                List<Object>ab=list(object(x.get("state")).get("bodies")),bb=list(object(y.get("state")).get("bodies"));for(int body=0;body<ab.size();body++)if(!Objects.equals(object(ab.get(body)).get("atRest"),object(bb.get(body)).get("atRest")))restDifferences++;
                matched++;x=a.nextRelevant(false);y=b.nextRelevant(false);
            }
        }
        return Map.of("reference",reference.id(),"actual",actual.id(),"comparison",mode,"matchedPhysicalTimes",matched,"maxima",maxima,"firstExactDifference",first,"differentRestFlagBodySamples",restDifferences);
    }
    private static Map<String,Double> quantities(Map<String,Object>state,Case c){
        Map<String,Double>r=new TreeMap<>();double s=c.scale();
        for(Object o:list(state.get("bodies"))){Map<String,Object>b=object(o);String id=string(b.get("id"));vector(r,id+".position",b.get("fixedOriginPosition"),s);vector(r,id+".velocity",b.get("velocity"),s);vector(r,id+".force",b.get("force"),s*s*s);vector(r,id+".accumulatedForce",b.get("accumulatedForce"),s*s*s);r.put(id+".orientation",number(object(b.get("transform")).get("getRotationAngle")));r.put(id+".rotationIncrementSum",number(b.get("rotationIncrementSum")));r.put(id+".angularVelocity",number(b.get("angularVelocity")));r.put(id+".torque",number(b.get("torque"))/Math.pow(s,4));r.put(id+".accumulatedTorque",number(b.get("accumulatedTorque"))/Math.pow(s,4));}
        for(Object o:list(state.get("joints"))){Map<String,Object>j=object(o);String id=string(j.get("id"));vector(r,id+".reactionForce",j.get("reactionForce"),Math.pow(s,3));r.put(id+".reactionTorque",number(j.get("reactionTorque"))/Math.pow(s,4));if(j.containsKey("getCurrentDistance"))r.put(id+".currentDistance",number(j.get("getCurrentDistance"))/s);for(String name:List.of("getAnchor1","getAnchor2"))if(j.containsKey(name)){List<Object>v=list(j.get(name));r.put(id+"."+name+".x",(number(v.get(0))-number(c.origin().get(0)))/s);r.put(id+"."+name+".y",(number(v.get(1))-number(c.origin().get(1)))/s);}}
        return r;
    }
    private static void vector(Map<String,Double>m,String key,Object value,double divisor){List<Object>v=list(value);m.put(key+".x",number(v.get(0))/divisor);m.put(key+".y",number(v.get(1))/divisor);}
    private static final class Trace implements AutoCloseable {
        final BufferedReader reader;final Map<String,Object>input;
        Trace(Path p)throws IOException{reader=new BufferedReader(new InputStreamReader(new GZIPInputStream(Files.newInputStream(p),65536),StandardCharsets.UTF_8),65536);String first=reader.readLine();if(first==null)throw new EOFException(p.toString());input=object(parse(first));if(!"inputs".equals(input.get("kind")))throw new IOException("Missing inputs: "+p);}
        Map<String,Object> nextRelevant(boolean actions)throws IOException{String line;while((line=reader.readLine())!=null){if(line.contains("\"kind\":\"state\"")||(actions&&line.contains("\"kind\":\"action\"")))return object(parse(line));}return null;}
        public void close()throws IOException{reader.close();}
    }
    private static String string(Object x){if(x instanceof String s)return s;throw new IllegalArgumentException("Expected string: "+x);}
    private static double number(Object x){if(x instanceof Number n)return n.doubleValue();throw new IllegalArgumentException("Expected number: "+x);}
    private static Map<String,Object> object(Object x){if(!(x instanceof Map<?,?>m))throw new IllegalArgumentException("Expected object");Map<String,Object>r=new LinkedHashMap<>();for(var e:m.entrySet())r.put(string(e.getKey()),e.getValue());return r;}
    private static List<Object> list(Object x){if(!(x instanceof List<?>l))throw new IllegalArgumentException("Expected array");return new ArrayList<>(l);}
    private static Object parse(String s){Parser p=new Parser(s);Object v=p.value();p.space();if(p.i!=s.length())throw new IllegalArgumentException("Trailing JSON");return v;}
    private static String encode(Object v){if(v==null)return "null";if(v instanceof String s)return "\""+s.replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n").replace("\r","\\r").replace("\t","\\t")+"\"";if(v instanceof Number||v instanceof Boolean)return v.toString();if(v instanceof Map<?,?>m){List<String>parts=new ArrayList<>();for(var e:m.entrySet())parts.add(encode(e.getKey())+":"+encode(e.getValue()));return "{"+String.join(",",parts)+"}";}if(v instanceof Iterable<?>l){List<String>parts=new ArrayList<>();for(Object x:l)parts.add(encode(x));return "["+String.join(",",parts)+"]";}throw new IllegalArgumentException("Cannot encode "+v);}
    private static final class Parser {
        final String s;int i;Parser(String s){this.s=s;}void space(){while(i<s.length()&&Character.isWhitespace(s.charAt(i)))i++;}
        Object value(){space();if(i>=s.length())throw new IllegalArgumentException("Truncated JSON");char c=s.charAt(i);if(c=='"')return text();if(c=='{'){i++;Map<String,Object>m=new LinkedHashMap<>();space();if(take('}'))return m;do{space();String k=text();space();expect(':');m.put(k,value());space();}while(take(','));expect('}');return m;}if(c=='['){i++;List<Object>l=new ArrayList<>();space();if(take(']'))return l;do{l.add(value());space();}while(take(','));expect(']');return l;}for(String token:List.of("true","false","null")){if(s.startsWith(token,i)){i+=token.length();return token.equals("null")?null:Boolean.valueOf(token);}}int start=i;while(i<s.length()&&"-+0123456789.eE".indexOf(s.charAt(i))>=0)i++;if(start==i)throw new IllegalArgumentException("Invalid JSON at "+i);return Double.valueOf(s.substring(start,i));}
        boolean take(char c){if(i<s.length()&&s.charAt(i)==c){i++;return true;}return false;}void expect(char c){if(!take(c))throw new IllegalArgumentException("Expected "+c+" at "+i);}
        String text(){expect('"');StringBuilder b=new StringBuilder();while(i<s.length()){char c=s.charAt(i++);if(c=='"')return b.toString();if(c!='\\'){b.append(c);continue;}char e=s.charAt(i++);switch(e){case '"','\\','/'->b.append(e);case 'b'->b.append('\b');case 'f'->b.append('\f');case 'n'->b.append('\n');case 'r'->b.append('\r');case 't'->b.append('\t');case 'u'->{b.append((char)Integer.parseInt(s.substring(i,i+4),16));i+=4;}default->throw new IllegalArgumentException("Invalid escape");}}throw new IllegalArgumentException("Unterminated string");}
    }
}
