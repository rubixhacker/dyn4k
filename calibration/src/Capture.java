import java.io.*;
import java.nio.file.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.function.IntConsumer;
import java.util.zip.GZIPOutputStream;
import org.dyn4j.dynamics.*;
import org.dyn4j.dynamics.joint.Joint;
import org.dyn4j.geometry.*;
import org.dyn4j.world.*;
import org.dyn4j.world.listener.*;

/** Passive baseline recorder. No solver state or callback return decisions are changed. */
public final class Capture {
    static Path directory;
    static BufferedWriter queries, summary;
    static BufferedWriter trace;
    static String current = "outside-run";
    static int step, order;
    static double originX, originY;
    static final Map<String,Integer> counts = new LinkedHashMap<>();
    static final IdentityHashMap<Object,String> ids = new IdentityHashMap<>();
    static final Map<Class<?>,List<Method>> methods = new HashMap<>();
    static long events, solved, toi;
    static double maxReaction, maxTorque;
    static final Map<String,Double> maxima = new TreeMap<>();
    static final IdentityHashMap<Body,double[]> initial = new IdentityHashMap<>();
    static final IdentityHashMap<Body,double[]> rotations = new IdentityHashMap<>();
    static int sleepingSteps;
    static String filter = "";
    static final class NonFinite extends IllegalStateException {
        NonFinite(String message) {super(message);}
    }
    public static void open(Path path, String selected) throws IOException {
        directory=path; filter=selected;
        Files.createDirectories(path);
        queries=Files.newBufferedWriter(path.resolve("queries.jsonl"), StandardOpenOption.CREATE_NEW);
        summary=Files.newBufferedWriter(path.resolve("summary.jsonl"), StandardOpenOption.CREATE_NEW);
    }
    public static void close() throws IOException { queries.close(); summary.close(); }
    public static boolean accepts(String id) {return filter.isEmpty() || id.contains(filter);}
    public static void rejected(String id, String reason) { query(id, Map.of("rejected",reason)); }
    public static void query(String id,Object value) {
        if (!filter.isEmpty() && !id.contains(filter)) return;
        line(queries, Map.of("id",id,"payload",value));
    }
    public static void record(String id,String event,Object... values) {
        if (!accepts(id)) return;
        if(trace!=null) line(trace,Map.of("kind","instrumented-callback","id",id,"event",event,"step",step,"order",order++,"values",Arrays.asList(values)));
        else query(id, Map.of("event",event,"values",Arrays.asList(values)));
    }
    public static void action(String description) {
        line(trace == null ? queries : trace, Map.of("kind","action","id",current,"step",step,"order",order++,"description",description));
    }
    @SuppressWarnings("unchecked")
    public static void run(String id,World<Body> world,int n,double dt,double scale,double ox,double oy,IntConsumer before) {
        if (!filter.isEmpty() && !id.contains(filter)) return;
        current=id; originX=ox;originY=oy; step=counts.getOrDefault(id,0); order=0;
        events=solved=toi=0; maxReaction=maxTorque=0; sleepingSteps=0; maxima.clear(); ids.clear(); initial.clear();rotations.clear();
        for(int i=0;i<world.getBodyCount();i++) {
            Body b=world.getBody(i);ids.put(b,"b"+i);
            for(int f=0;f<b.getFixtureCount();f++) ids.put(b.getFixture(f),"b"+i+"f"+f);
            Vector2 p=b.getWorldCenter(),v=b.getLinearVelocity();
            initial.put(b,new double[]{p.x,p.y,v.x,v.y,b.getAngularVelocity(),energy(b)});
            rotations.put(b,new double[]{b.getTransform().getRotationAngle(),0});
        }
        for(int i=0;i<world.getJointCount();i++)ids.put(world.getJoint(i),"j"+i);
        String file=id.replaceAll("[^A-Za-z0-9._-]","_")+"-"+step+".jsonl.gz";
        try {
            trace=new BufferedWriter(new OutputStreamWriter(new GZIPOutputStream(Files.newOutputStream(directory.resolve(file),StandardOpenOption.CREATE_NEW),65536),java.nio.charset.StandardCharsets.UTF_8),65536);
            line(trace,Map.of("kind","inputs","id",id,"steps",n,"dt",dt,"scale",scale,"origin",List.of(ox,oy),"settings",props(world.getSettings()),"world",worldConfig(world),"state",state(world,dt,false)));
            ContactListener<Body> contacts=listener(ContactListener.class);
            TimeOfImpactListener<Body> impacts=listener(TimeOfImpactListener.class);
            CollisionListener<Body,BodyFixture> collisions=listener(CollisionListener.class);
            StepListener<Body> steps=listener(StepListener.class);
            DestructionListener<Body> destruction=listener(DestructionListener.class);
            BoundsListener<Body,BodyFixture> bounds=listener(BoundsListener.class);
            world.addContactListener(contacts);world.addTimeOfImpactListener(impacts);world.addCollisionListener(collisions);
            world.addStepListener(steps);world.addDestructionListener(destruction);world.addBoundsListener(bounds);
            try {
                for(int i=1;i<=n;i++) {
                    step++; order=0;
                    if(before!=null) before.accept(i);
                    world.step(1,dt);
                    line(trace,Map.of("kind","state","step",step,"state",state(world,dt,true)));
                    residuals(world,i*dt);
                }
            } finally {
                world.removeContactListener(contacts);world.removeTimeOfImpactListener(impacts);world.removeCollisionListener(collisions);
                world.removeStepListener(steps);world.removeDestructionListener(destruction);world.removeBoundsListener(bounds);
            }
            counts.put(id,step);
            Map<String,Object> result=new LinkedHashMap<>();
            result.put("id",id);result.put("file",file);result.put("steps",n);result.put("dt",dt);result.put("seconds",n*dt);
            result.put("events",events);result.put("solvedContactCallbacks",solved);result.put("toiPayloadCallbacks",toi);
            result.put("stepsWithSleepingDynamicBody",sleepingSteps);result.put("maxReactionForce",maxReaction);result.put("maxReactionTorque",maxTorque);
            result.put("diagnosticMaxima",new TreeMap<>(maxima));
            line(summary,result);summary.flush();
            System.out.println("CASE "+id+" steps="+n+" contacts="+solved+" toi="+toi);
        } catch(NonFinite e) {
            line(summary,Map.of("id",id,"file",file,"status","REJECTED_NONFINITE","firstFailureStep",step,"expectedSteps",n,"reason",e.getMessage()));
            try {summary.flush();}catch(IOException io){throw new UncheckedIOException(io);}
            System.out.println("REJECTED "+id+" step="+step+" "+e.getMessage());
        } catch(IOException e) {throw new UncheckedIOException(e);}
        finally {try {if(trace!=null)trace.close();}catch(IOException e){throw new UncheckedIOException(e);}trace=null;}
    }
    @SuppressWarnings("unchecked")
    static <T> T listener(Class<T> type) {
        return (T)Proxy.newProxyInstance(type.getClassLoader(),new Class<?>[]{type},(proxy,m,args)-> {
            if(m.getDeclaringClass()==Object.class) {
                if(m.getName().equals("hashCode")) return System.identityHashCode(proxy);
                if(m.getName().equals("equals")) return proxy==args[0];
                return "PassiveCaptureListener";
            }
            events++;
            if(type==ContactListener.class && m.getName().equals("postSolve")) {
                org.dyn4j.dynamics.contact.SolvedContact c=(org.dyn4j.dynamics.contact.SolvedContact)args[1];
                if(c.isSolved())solved++;
            }
            if(type==TimeOfImpactListener.class && args!=null)for(Object a:args)if(a instanceof org.dyn4j.collision.continuous.TimeOfImpact)toi++;
            List<Object> payload=new ArrayList<>();
            if(args!=null) for(Object a:args) payload.add(a instanceof PhysicsWorld ? Map.of("world",current) : a);
            line(trace,Map.of("kind","event","step",step,"order",order++,"listener",type.getSimpleName(),"method",m.toGenericString(),"payload",payload));
            return m.getReturnType()==boolean.class ? Boolean.TRUE : null;
        });
    }
    static Map<String,Object> worldConfig(World<Body> w) {
        Map<String,Object> m=new TreeMap<>();m.put("gravity",w.getGravity());
        for(Method method: getters(w.getClass())) {
            String name=method.getName();
            if(name.contains("Detector")||name.contains("Solver")||name.contains("Expansion")) {
                try {m.put(name,config(method.invoke(w),0));}catch(ReflectiveOperationException e){throw new IllegalStateException(e);}
            }
        }
        return m;
    }
    static Map<String,Object> config(Object value,int depth) {
        Map<String,Object> m=props(value);
        if(value==null || depth>4)return m;
        for(Method method:getters(value.getClass())) {
            String n=method.getName();
            if(n.contains("Detector")||n.contains("Solver")||n.contains("ExpansionMethod")) {
                try {m.put(n,config(method.invoke(value),depth+1));}catch(ReflectiveOperationException e){throw new IllegalStateException(e);}
            }
        }
        return m;
    }
    static Object state(World<Body> w,double dt,boolean dynamic) {
        List<Object> bodies=new ArrayList<>(),joints=new ArrayList<>();
        boolean asleep=false;
        for(Body b:w.getBodies()) {
            Map<String,Object> m=new LinkedHashMap<>();Vector2 p=b.getWorldCenter();
            m.put("id",ids.get(b)); m.put("transform",b.getTransform());m.put("previousTransform",b.getPreviousTransform());
            m.put("worldCenter",p);m.put("fixedOriginPosition",new Vector2(p.x-originX,p.y-originY));
            m.put("velocity",b.getLinearVelocity());m.put("angularVelocity",b.getAngularVelocity());m.put("atRest",b.isAtRest());
            m.put("force",b.getForce());m.put("torque",b.getTorque());m.put("accumulatedForce",b.getAccumulatedForce());m.put("accumulatedTorque",b.getAccumulatedTorque());
            double[] r=rotations.get(b);double angle=b.getTransform().getRotationAngle();
            if(dynamic) {double delta=Math.atan2(Math.sin(angle-r[0]),Math.cos(angle-r[0]));r[1]+=delta;r[0]=angle;}
            m.put("rotationIncrementSum",r[1]);m.put("rotationTrackingScope","segment-only; unrecorded transform mutations invalidate");
            m.put("rotationStepBoundBelowPi",w.getSettings().getMaximumRotation()<Math.PI);
            if(!dynamic){m.put("properties",props(b));m.put("fixtures",b.getFixtures());}
            bodies.add(m);if(!b.isStatic()&&b.isAtRest())asleep=true;
        }
        if(dynamic&&asleep)sleepingSteps++;
        for(Joint<Body> j:w.getJoints()) {
            Map<String,Object> m=new TreeMap<>(props(j));m.put("id",ids.get(j));m.put("bodies",j.getBodies());
            Vector2 f=j.getReactionForce(1/dt);double torque=j.getReactionTorque(1/dt);
            m.put("reactionForce",f);m.put("reactionTorque",torque);maxReaction=Math.max(maxReaction,f.getMagnitude());maxTorque=Math.max(maxTorque,Math.abs(torque));
            for(Method method:j.getClass().getMethods()) {
                if(method.getName().startsWith("get") && method.getParameterCount()==1 && method.getParameterTypes()[0]==double.class && method.getReturnType()==double.class) {
                    try {m.put(method.getName(),method.invoke(j,1/dt));}catch(ReflectiveOperationException e){throw new IllegalStateException(e);}
                }
            }
            joints.add(m);
        }
        return Map.of("bodies",bodies,"joints",joints);
    }
    static double energy(Body b) {return .5*b.getMass().getMass()*b.getLinearVelocity().getMagnitudeSquared()+.5*b.getMass().getInertia()*b.getAngularVelocity()*b.getAngularVelocity();}
    static void residuals(World<Body> w,double time) {
        if(!current.startsWith("L-free"))return;
        for(Body b:w.getBodies())if(!b.isStatic()) {
            double[] a=initial.get(b);Vector2 p=b.getWorldCenter();
            max("analyticPositionX",Math.abs(p.x-(a[0]+a[2]*time)));max("analyticPositionY",Math.abs(p.y-(a[1]+a[3]*time)));
            max("energyDrift",Math.abs(energy(b)-a[5]));max("linearMomentumXDrift",Math.abs((b.getLinearVelocity().x-a[2])*b.getMass().getMass()));
            max("linearMomentumYDrift",Math.abs((b.getLinearVelocity().y-a[3])*b.getMass().getMass()));
            max("angularMomentumCenterDrift",Math.abs((b.getAngularVelocity()-a[4])*b.getMass().getInertia()));
        }
    }
    static void max(String key,double v){maxima.merge(key,v,Math::max);}
    static List<Method> getters(Class<?> type) {
        return methods.computeIfAbsent(type,t->Arrays.stream(t.getMethods()).filter(m->m.getParameterCount()==0&&!Modifier.isStatic(m.getModifiers())&&(m.getName().startsWith("get")||m.getName().startsWith("is"))).filter(m->!Set.of("getClass","getOwner","getUserData","getIterator","getBodyIterator","getFixtureIterator","getJointIterator").contains(m.getName())).sorted(Comparator.comparing(Method::getName)).toList());
    }
    static Map<String,Object> props(Object value) {
        Map<String,Object> result=new TreeMap<>();if(value==null)return result;
        result.put("type",value.getClass().getName());
        for(Method m:getters(value.getClass())) {
            Class<?> r=m.getReturnType();
            if(r==value.getClass())continue;
            if(r.isPrimitive()||r.isEnum()||r==String.class||r==Vector2.class||r==Transform.class||r==Mass.class||r.isArray()||r==org.dyn4j.geometry.AABB.class) {
                try {if(!m.canAccess(value))m.setAccessible(true);result.put(m.getName(),m.invoke(value));}catch(ReflectiveOperationException e){throw new IllegalStateException("Getter "+m,e);}
            }
        }
        return result;
    }
    static void line(BufferedWriter writer,Object value) {
        try {writer.write(json(value,0,new IdentityHashMap<>()));writer.newLine();}catch(IOException e){throw new UncheckedIOException(e);}
    }
    static String json(Object v,int depth,IdentityHashMap<Object,Boolean> seen) {
        if(v==null)return "null";
        if(v instanceof String||v instanceof Enum<?>)return quote(v.toString());
        if(v instanceof Number n) {if((n instanceof Double||n instanceof Float)&&!Double.isFinite(n.doubleValue()))throw new NonFinite("Non-finite output in "+current+" step "+step+": "+n);return n.toString();}
        if(v instanceof Boolean)return v.toString();
        if((v instanceof Body||v instanceof Joint<?>)&&ids.containsKey(v))return quote(ids.get(v));
        if(depth>12)throw new IllegalStateException("Unbounded payload "+v.getClass());
        if(v instanceof Vector2 p)return "["+json(p.x,depth+1,seen)+","+json(p.y,depth+1,seen)+"]";
        if(v instanceof Map<?,?> map) {List<String> parts=new ArrayList<>();for(var e:map.entrySet().stream().sorted(Comparator.comparing(e->e.getKey().toString())).toList()) {
            try {parts.add(quote(e.getKey().toString())+":"+json(e.getValue(),depth+1,seen));}
            catch(NonFinite failure){throw new NonFinite(e.getKey()+"."+failure.getMessage());}
        }return "{"+String.join(",",parts)+"}";}
        if(v instanceof Iterable<?> list) {List<String> parts=new ArrayList<>();for(Object x:list)parts.add(json(x,depth+1,seen));return "["+String.join(",",parts)+"]";}
        if(v.getClass().isArray()) {List<String> parts=new ArrayList<>();for(int i=0;i<Array.getLength(v);i++)parts.add(json(Array.get(v,i),depth+1,seen));return "["+String.join(",",parts)+"]";}
        Map<String,Object> result=new TreeMap<>(props(v));
        if(v instanceof BodyFixture f){result.put("id",ids.get(f));result.put("shape",props(f.getShape()));result.put("filter",props(f.getFilter()));}
        if(v instanceof ContactCollisionData<?> c) {result.put("body1",c.getBody1());result.put("body2",c.getBody2());result.put("velocity1",c.getBody1().getLinearVelocity());result.put("velocity2",c.getBody2().getLinearVelocity());result.put("angularVelocity1",c.getBody1().getAngularVelocity());result.put("angularVelocity2",c.getBody2().getAngularVelocity());result.put("fixture1",ids.get(c.getFixture1()));result.put("fixture2",ids.get(c.getFixture2()));result.put("constraint",c.getContactConstraint());result.put("manifold",c.getManifold());result.put("penetration",c.getPenetration());}
        if(v instanceof org.dyn4j.dynamics.contact.ContactConstraint<?> c){result.put("contacts",c.getContacts());}
        if(v instanceof org.dyn4j.collision.manifold.Manifold m){result.put("points",m.getPoints());}
        if(v instanceof org.dyn4j.collision.continuous.TimeOfImpact t){result.put("separation",t.getSeparation());}
        if(v instanceof org.dyn4j.dynamics.contact.Contact c){result.put("manifoldId",props(c.getId()));}
        return json(result,depth+1,seen);
    }
    static String quote(String s) {StringBuilder b=new StringBuilder("\"");for(char c:s.toCharArray())switch(c){case '"'->b.append("\\\"");case '\\'->b.append("\\\\");case '\n'->b.append("\\n");case '\r'->b.append("\\r");case '\t'->b.append("\\t");default->{if(c<32)b.append(String.format("\\u%04x",(int)c));else b.append(c);}}return b.append('"').toString();}
}
