import java.lang.reflect.InvocationTargetException;
import java.util.function.Consumer;
import java.util.function.IntConsumer;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.joint.*;
import org.dyn4j.geometry.*;
import org.dyn4j.world.World;

/** P matrix: exact initial U states, isolated fields, no invented activation stimulus. */
public final class JointCases {
    private record Seed(World<Body> world, Joint<Body> joint) {}
    private static final String[] TYPES = {"Angle", "Distance", "Friction", "Motor", "Pin", "Prismatic", "Pulley", "Revolute", "Weld", "Wheel"};
    private static int attempted, completed, rejected;

    public static void runAll() {
        for (String type : TYPES) {
            row(type, "initial", s -> {}, null);
            for (String field : new String[]{"LimitsEnabled", "LowerLimitEnabled", "UpperLimitEnabled", "MotorEnabled", "MaximumMotorForceEnabled", "MaximumMotorTorqueEnabled", "SpringEnabled", "SpringDamperEnabled", "MaximumSpringForceEnabled", "MaximumSpringTorqueEnabled", "SlackEnabled"}) {
                if (!has(type, "set" + field, boolean.class)) continue;
                for (boolean value : new boolean[]{false,true}) row(type, field + "-" + value, s -> set(s.joint, field, value), null);
                row(type, field + "-toggle", s -> set(s.joint, field, false), s -> step -> {
                    if (step == 201 || step == 401) {
                        boolean value = step == 201;
                        set(s.joint, field, value);
                        Capture.action("set" + field + "(" + value + ") before step " + step);
                    }
                });
            }
            grid(type, "Ratio", type.equals("Angle") ? new double[]{0.5,1,2,-1} : new double[]{0.5,1,2});
            grid(type, "SpringDampingRatio", new double[]{0,0.2,1});
            grid(type, "SpringFrequency", new double[]{2,8});
            grid(type, "CorrectionFactor", new double[]{0,0.3,1});
            for (String f : new String[]{"MaximumForce","MaximumSpringForce","MaximumMotorForce","MaximumCorrectionForce"}) grid(type,f,new double[]{0,10,1000});
            for (String f : new String[]{"MaximumTorque","MaximumSpringTorque","MaximumMotorTorque"}) grid(type,f,new double[]{0,0.25,10});
            grid(type,"MotorSpeed",type.equals("Prismatic") ? new double[]{-1,0,1} : new double[]{-Math.PI/2,0,Math.PI/2});
            if (has(type,"setLimits",double.class,double.class)) {
                double limit = type.equals("Angle") || type.equals("Revolute") || type.equals("Weld") ? Math.PI/6 : 1;
                row(type,"limits-range",s -> limits(s.joint,-limit,limit),null);
                row(type,"limits-equal",s -> limits(s.joint,0,0),null);
            }
            if (has(type,"setSpringStiffness",double.class)) {
                for (double frequency : new double[]{2,8}) {
                    Seed probe = compatibleSeed(type,"SpringFrequency");
                    set(probe.joint,"SpringEnabled",true);
                    set(probe.joint,"SpringFrequency",frequency);
                    // Compute via baseline initialization in a throwaway world, never advance captured initial states.
                    probe.world.step(1,1.0/60);
                    double stiffness = number(probe.joint,"getSpringStiffness");
                    if (!(stiffness > 0) || !Double.isFinite(stiffness)) throw new IllegalStateException("invalid effective stiffness " + type + ": " + stiffness);
                    row(type,"stiffness-from-"+frequency+"Hz-"+Double.toHexString(stiffness),s -> set(s.joint,"SpringStiffness",stiffness),null);
                }
            }
            if (type.equals("Angle")) for (double ratio : new double[]{0.5,1,2,-1}) row(type,"ratio-limits-off-"+ratio,s -> {set(s.joint,"LimitsEnabled",false);set(s.joint,"Ratio",ratio);},null);
            if (type.equals("Motor") || type.equals("Pin")) {
                row(type,"moving-linear-target",s -> {},s -> step -> {
                    if (step == 201) {
                        if (s.joint instanceof MotorJoint<?> j) j.setLinearTarget(j.getLinearTarget().sum(new Vector2(0.5,0.5)));
                        if (s.joint instanceof PinJoint<?> j) j.setTarget(j.getTarget().sum(new Vector2(0.5,0.5)));
                        Capture.action("target += (0.5,0.5) before step 201");
                    }
                });
                if (type.equals("Motor")) row(type,"moving-angular-target",s -> {},s -> step -> {
                    if (step == 201) { MotorJoint<?> j=(MotorJoint<?>)s.joint; j.setAngularTarget(j.getAngularTarget()+Math.PI/6); Capture.action("angular target += pi/6 before step 201"); }
                });
            }
            if (type.equals("Prismatic") || type.equals("Wheel") || type.equals("Distance") || type.equals("Weld") || type.equals("Revolute")) {
                row(type,"interaction",s -> {
                    if (has(type,"setSpringEnabled",boolean.class)) set(s.joint,"SpringEnabled",true);
                    if (has(type,"setMotorEnabled",boolean.class)) set(s.joint,"MotorEnabled",true);
                    set(s.joint,"LimitsEnabled",true);
                },null);
            }
        }
        System.err.println("JointCases attempted="+attempted+" completed="+completed+" rejected="+rejected);
    }
    private interface Schedule { IntConsumer bind(Seed s); }
    private static void row(String type,String name,Consumer<Seed> configure,Schedule schedule) {
        attempted++;
        Seed s=compatibleSeed(type,name);
        String id="P-J-"+type+"-"+name;
        try { configure.accept(s); }
        catch (IllegalArgumentException e) { rejected++; Capture.rejected(id,e.toString()); return; }
        Capture.run(id,s.world,600,1.0/60,1,0,0,schedule == null ? step -> {} : schedule.bind(s));
        completed++;
    }
    private static void grid(String type,String field,double[] values) {
        if (!has(type,"set"+field,double.class)) return;
        for (double value: values) row(type,field+"-"+value,s -> set(s.joint,field,value),null);
    }
    private static boolean has(String type,String method,Class<?>... args) {
        try { Class.forName("org.dyn4j.dynamics.joint."+type+"Joint").getMethod(method,args); return true; }
        catch (ClassNotFoundException | NoSuchMethodException e) { return false; }
    }
    private static void set(Object j,String field,Object value) { invoke(j,"set"+field,new Class<?>[]{value instanceof Boolean ? boolean.class : double.class},value); }
    private static void limits(Object j,double lo,double hi) { invoke(j,"setLimits",new Class<?>[]{double.class,double.class},lo,hi); }
    private static Object invoke(Object j,String method,Class<?>[] types,Object... values) {
        try { return j.getClass().getMethod(method,types).invoke(j,values); }
        catch (InvocationTargetException e) { if (e.getCause() instanceof IllegalArgumentException a) throw a; throw new IllegalStateException(e.getCause()); }
        catch (ReflectiveOperationException e) { throw new IllegalStateException(e); }
    }
    private static double number(Object j,String method) { return ((Number)invoke(j,method,new Class<?>[0])).doubleValue(); }
    private static Body body(World<Body> w,Convex shape,MassType mass,double x,double y) {
        Body b=new Body(); b.addFixture(shape).setFriction(0); b.setMass(mass); b.setLinearDamping(0); b.setAngularDamping(0); b.translate(x,y); w.addBody(b); return b;
    }
    private static Seed pinNoSpring() {
        World<Body> w=new World<>(); Body b=new Body(); b.addFixture(Geometry.createCircle(1)); b.setMass(MassType.NORMAL); w.addBody(b);
        PinJoint<Body> p=new PinJoint<>(b,new Vector2(0,0)); p.setSpringEnabled(false); p.setSpringDamperEnabled(false); p.setMaximumSpringForceEnabled(false); p.setTarget(new Vector2(0.7,0.5)); w.addJoint(p); return new Seed(w,p);
    }
    private static Seed compatibleSeed(String type,String name) {
        if (type.equals("Pin") && (name.startsWith("CorrectionFactor") || name.startsWith("MaximumCorrectionForce"))) return pinNoSpring();
        Seed s=seed(type);
        boolean spring=name.contains("Spring") || name.startsWith("stiffness-");
        boolean motor=name.contains("Motor");
        if (spring) {
            switch(type) {
                case "Distance":
                    DistanceJoint<?> d=(DistanceJoint<?>)s.joint; d.setLimitsEnabled(1,5); d.setSpringEnabled(true); d.setSpringFrequency(8); d.setSpringDamperEnabled(true); d.setSpringDampingRatio(0.2); break;
                case "Prismatic":
                    s.world.setGravity(World.ZERO_GRAVITY);
                    PrismaticJoint<?> p=(PrismaticJoint<?>)s.joint; p.setSpringEnabled(true); p.setSpringFrequency(8); p.setSpringDamperEnabled(true); p.setSpringDampingRatio(0.2); p.setMaximumSpringForceEnabled(true); p.setMaximumSpringForce(1000); p.setSpringRestOffset(2); break;
                case "Weld":
                    s.world.removeJoint(s.joint);
                    WeldJoint<Body> w=new WeldJoint<>(s.world.getBody(0),s.world.getBody(1),s.world.getBody(1).getWorldCenter().sum(-0.5,0));
                    w.setSpringEnabled(true); w.setSpringDamperEnabled(true); w.setSpringDampingRatio(0.3); w.setSpringFrequency(8); s.world.addJoint(w); s=new Seed(s.world,w); break;
                case "Wheel":
                    s.world.removeJoint(s.joint);
                    WheelJoint<Body> wh=new WheelJoint<>(s.world.getBody(0),s.world.getBody(1),s.world.getBody(1).getWorldCenter(),new Vector2(0,1));
                    wh.setLimitsEnabled(-1,5); s.world.addJoint(wh); s=new Seed(s.world,wh); break;
                default: break;
            }
        } else if (motor) {
            switch(type) {
                case "Prismatic":
                    s.world.setGravity(World.ZERO_GRAVITY);
                    PrismaticJoint<?> p=(PrismaticJoint<?>)s.joint; p.setMaximumMotorForce(1000); p.setMotorSpeed(10); p.setMotorEnabled(true); p.setMaximumMotorForceEnabled(true); break;
                case "Revolute":
                    s.world.setGravity(World.ZERO_GRAVITY); s.world.getSettings().setAngularTolerance(0);
                    RevoluteJoint<?> r=(RevoluteJoint<?>)s.joint; r.setMaximumMotorTorque(1000); r.setMaximumMotorTorqueEnabled(true); r.setMotorSpeed(Math.toRadians(20)); r.setMotorEnabled(true); break;
                case "Wheel":
                    s.world.setGravity(World.ZERO_GRAVITY); s.world.removeJoint(s.joint);
                    WheelJoint<Body> wh=new WheelJoint<>(s.world.getBody(0),s.world.getBody(1),s.world.getBody(1).getWorldCenter(),new Vector2(-1,0));
                    wh.setMaximumMotorTorqueEnabled(true); wh.setMaximumMotorTorque(10000); wh.setMotorSpeed(Math.toRadians(90)); wh.setMotorEnabled(true); s.world.addJoint(wh); s=new Seed(s.world,wh); break;
                default: break;
            }
        }
        return s;
    }
    private static Seed seed(String type) {
        World<Body> w=new World<>(); Joint<Body> j;
        if (type.equals("Pin")) {
            Body b=new Body(); b.addFixture(Geometry.createCircle(1)); b.setMass(MassType.FIXED_LINEAR_VELOCITY); w.addBody(b);
            PinJoint<Body> p=new PinJoint<>(b,new Vector2(0.5,0)); p.setTarget(new Vector2(0.7,0.5)); j=p;
        } else if (type.equals("Pulley")) {
            Body a=body(w,Geometry.createCircle(0.5),MassType.NORMAL,-1,0), b=body(w,Geometry.createCircle(0.5),MassType.NORMAL,1,0);
            j=new PulleyJoint<>(a,b,new Vector2(-1,1),new Vector2(1,1),new Vector2(-1,0),new Vector2(1,0));
        } else {
            if (type.equals("Angle") || type.equals("Distance") || type.equals("Friction") || type.equals("Motor")) w.setGravity(World.ZERO_GRAVITY);
            Body a=body(w,type.equals("Angle") || type.equals("Motor") ? Geometry.createCircle(0.5) : Geometry.createRectangle(10,0.5),type.equals("Angle") ? MassType.NORMAL : MassType.INFINITE,0,0);
            Body b=body(w,type.equals("Weld") ? Geometry.createRectangle(1,0.5) : Geometry.createCircle(0.5),MassType.NORMAL,0,2);
            switch(type) {
                case "Angle": b.setAngularVelocity(-Math.toRadians(30)); j=new AngleJoint<>(a,b); break;
                case "Distance": DistanceJoint<Body> d=new DistanceJoint<>(a,b,a.getWorldCenter(),b.getWorldCenter()); d.setRestDistance(10); w.getSettings().setMaximumLinearCorrection(0.2); w.getSettings().setPositionConstraintSolverIterations(10); j=d; break;
                case "Friction": b.setLinearVelocity(4,3); b.setAngularVelocity(Math.toRadians(30)); FrictionJoint<Body> f=new FrictionJoint<>(a,b,b.getWorldCenter()); f.setMaximumForce(1000); f.setMaximumTorque(1000); j=f; break;
                case "Motor": MotorJoint<Body> m=new MotorJoint<>(a,b);m.setLinearTarget(new Vector2(0,3));m.setAngularTarget(Math.toRadians(30));m.setMaximumForce(0);m.setMaximumTorque(0);j=m;break;
                case "Prismatic": j=new PrismaticJoint<>(a,b,b.getWorldCenter(),new Vector2(1,0));break;
                case "Revolute": j=new RevoluteJoint<>(a,b,b.getWorldCenter());break;
                case "Weld": j=new WeldJoint<>(a,b,b.getWorldCenter());break;
                case "Wheel": j=new WheelJoint<>(a,b,b.getWorldCenter(),new Vector2(1,0));break;
                default: throw new IllegalArgumentException(type);
            }
        }
        w.addJoint(j); return new Seed(w,j);
    }
}
