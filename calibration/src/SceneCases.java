import java.util.function.IntConsumer;
import org.dyn4j.collision.CollisionItem;
import org.dyn4j.collision.broadphase.*;
import org.dyn4j.collision.continuous.ConservativeAdvancement;
import org.dyn4j.collision.narrowphase.*;
import org.dyn4j.dynamics.*;
import org.dyn4j.dynamics.joint.DistanceJoint;
import org.dyn4j.geometry.*;
import org.dyn4j.world.World;
import org.dyn4j.world.PhysicsBodySweptAABBProducer;

/** Added scenes from the approved calibration recipe; each run constructs a fresh world. */
public final class SceneCases {
    private static final double[][] OFFSETS = {{0,0},{1000,1000},{-1000,1000},{1000000,-1000000},{-1000000,1000000}};
    public static void runAll() {
        for (double s : new double[]{0.01,1,100}) for (double[] o : OFFSETS) {
            for (double damping : new double[]{0,0.1}) integrator(s,o,damping);
            slide(s,o);
            for (int hz : new int[]{30,60,120}) {
                for (double e : new double[]{0,0.5,1}) bounce(s,o,hz,e);
                stack(s,o,hz);
                for (boolean polygon : new boolean[]{false,true}) for (ContinuousDetectionMode mode : new ContinuousDetectionMode[]{ContinuousDetectionMode.ALL,ContinuousDetectionMode.NONE}) ccd(s,o,hz,polygon,mode);
                for (boolean damper : new boolean[]{false,true}) spring(s,o,hz,damper);
            }
        }
        World<Body> w = world(1,true);
        Body b = body(w,Geometry.createCircle(0.5),0,0,false,0.2,0);
        b.setLinearVelocity(0.25,-0.125); b.setAngularVelocity(0.5);
        w.getSettings().setAtRestDetectionEnabled(false);
        run("L-free",w,600,60,1,new double[]{0,0},i -> {});
    }
    public static void scaleWorld(World<Body> w,double s) {
        Settings q=w.getSettings();
        q.setMaximumTranslation(q.getMaximumTranslation()*s);
        q.setMaximumAtRestLinearVelocity(q.getMaximumAtRestLinearVelocity()*s);
        q.setMaximumWarmStartDistance(q.getMaximumWarmStartDistance()*s);
        q.setLinearTolerance(q.getLinearTolerance()*s);
        q.setMaximumLinearCorrection(q.getMaximumLinearCorrection()*s);
        w.setBroadphaseDetector(new CollisionItemBroadphaseDetectorAdapter<Body,BodyFixture>(
            new DynamicAABBTree<CollisionItem<Body,BodyFixture>>(new CollisionItemBroadphaseFilter<Body,BodyFixture>(),new CollisionItemAABBProducer<Body,BodyFixture>(),new StaticValueAABBExpansionMethod<CollisionItem<Body,BodyFixture>>(0.2*s))));
        w.setContinuousCollisionDetectionBroadphaseDetector(new DynamicAABBTree<Body>(new CollisionBodyBroadphaseFilter<Body>(),new PhysicsBodySweptAABBProducer<Body>(),new StaticValueAABBExpansionMethod<Body>(0.2*s)));
        scaleGjk((Gjk)w.getNarrowphaseDetector(),s);
        scaleGjk((Gjk)w.getRaycastDetector(),s);
        ConservativeAdvancement ca=(ConservativeAdvancement)w.getTimeOfImpactDetector();
        ca.setDistanceEpsilon(ca.getDistanceEpsilon()*s);
        scaleGjk((Gjk)ca.getDistanceDetector(),s);
    }
    private static void scaleGjk(Gjk g,double s) {
        g.setDistanceEpsilon(g.getDistanceEpsilon()*s*s);
        g.setRaycastEpsilon(g.getRaycastEpsilon()*s*s);
        Epa e=(Epa)g.getMinkowskiPenetrationSolver(); e.setDistanceEpsilon(e.getDistanceEpsilon()*s);
    }
    private static World<Body> world(double s,boolean zeroGravity) {
        World<Body> w=new World<>(); scaleWorld(w,s); w.setGravity(0,zeroGravity?0:-9.8*s); return w;
    }
    private static Body body(World<Body> w,Convex shape,double x,double y,boolean fixed,double friction,double restitution) {
        Body b=new Body(); BodyFixture f=b.addFixture(shape); f.setDensity(1); f.setFriction(friction); f.setRestitution(restitution);
        b.setMass(fixed?MassType.INFINITE:MassType.NORMAL); b.setLinearDamping(0); b.setAngularDamping(0); b.translate(x,y); w.addBody(b); return b;
    }
    private static Body ground(World<Body> w,double s,double[] o,double friction,double restitution) {
        return body(w,Geometry.createRectangle(20*s,0.5*s),o[0],o[1]-0.25*s,true,friction,restitution);
    }
    private static void run(String id,World<Body> w,int seconds,int hz,double s,double[] o,IntConsumer action) {
        for (Body b : w.getBodies()) for (BodyFixture f : b.getFixtures()) f.setRestitutionVelocity(f.getRestitutionVelocity()*s);
        Capture.run(id+"-s"+s+"-o"+o[0]+","+o[1]+"-hz"+hz,w,seconds*hz,1.0/hz,s,o[0],o[1],action);
    }
    private static void integrator(double s,double[] o,double damping) {
        World<Body> w=world(s,true); Body b=body(w,Geometry.createCircle(0.5*s),o[0],o[1],false,0.2,0);
        b.setLinearDamping(damping); b.setAngularDamping(damping);
        run("F-integrator-damping"+damping,w,10,60,s,o,i->{if(i<=60){Capture.action("apply force=("+(s*s*s)+",0), torque="+(0.25*s*s*s*s));b.applyForce(new Vector2(s*s*s,0));b.applyTorque(0.25*s*s*s*s);}});
    }
    private static void bounce(double s,double[] o,int hz,double e) {
        World<Body> w=world(s,false); Body g=ground(w,s,o,0,e); Body b=body(w,Geometry.createCircle(0.5*s),o[0],o[1]+2*s,false,0,e);
        g.getFixture(0).setRestitutionVelocity(0); b.getFixture(0).setRestitutionVelocity(0);
        run("C-bounce-e"+e,w,10,hz,s,o,i->{});
    }
    private static void stack(double s,double[] o,int hz) {
        World<Body> w=world(s,false); ground(w,s,o,0.5,0); Body top=null;
        for(int i=0;i<10;i++) top=body(w,Geometry.createSquare(s),o[0],o[1]+s*(0.51+1.01*i),false,0.5,0);
        Body target=top;
        run("C-stack",w,600,hz,s,o,i->{if(i==300*hz+1){Capture.action("wake impulse at top centre; sleepingBefore="+target.isAtRest()+"; impulse="+(s*s*s)+",0");target.applyImpulse(new Vector2(s*s*s,0),target.getWorldCenter());}});
    }
    private static void slide(double s,double[] o) {
        World<Body> w=world(s,false); ground(w,s,o,0.5,0); Body b=body(w,Geometry.createSquare(s),o[0],o[1]+0.5*s,false,0.5,0); b.setLinearVelocity(5*s,0);
        run("C-slide",w,10,60,s,o,i->{});
    }
    private static void ccd(double s,double[] o,int hz,boolean polygon,ContinuousDetectionMode mode) {
        World<Body> w=world(s,true); w.getSettings().setContinuousDetectionMode(mode);
        body(w,Geometry.createRectangle(20*s,0.05*s),o[0],o[1],true,0,0);
        Body b=body(w,polygon?Geometry.createUnitCirclePolygon(5,0.1*s):Geometry.createCircle(0.1*s),o[0],o[1]+s,false,0,0);
        b.setLinearVelocity(0,-120*s); b.setBullet(true); if(polygon)b.setAngularVelocity(20);
        run("CCD-world-"+(polygon?"pentagon":"circle")+"-"+mode,w,1,hz,s,o,i->{if(i==1)Capture.action("initial requested translation="+(120*s/hz)+"; maximum="+w.getSettings().getMaximumTranslation()+"; clampExpected="+(120*s/hz>w.getSettings().getMaximumTranslation()));});
    }
    private static void spring(double s,double[] o,int hz,boolean damper) {
        World<Body> w=world(s,true);
        // U fixture restitution defaults are retained, unlike P defaults elsewhere.
        Body g=new Body();g.addFixture(Geometry.createRectangle(10*s,0.5*s)).setFriction(0);g.setMass(MassType.INFINITE);g.setLinearDamping(0);g.setAngularDamping(0);g.translate(o[0],o[1]);w.addBody(g);
        Body b=new Body();b.addFixture(Geometry.createCircle(0.5*s)).setFriction(0);b.setMass(MassType.NORMAL);b.translate(o[0],o[1]+2*s);b.setLinearDamping(0);b.setAngularDamping(0);w.addBody(b);
        DistanceJoint<Body> joint=new DistanceJoint<>(g,b,g.getWorldCenter(),b.getWorldCenter());joint.setRestDistance(3*s);joint.setSpringEnabled(true);joint.setSpringFrequency(8);joint.setSpringDamperEnabled(damper);joint.setSpringDampingRatio(0.2);w.addJoint(joint);
        run("L-spring-damper"+damper,w,600,hz,s,o,i->{});
    }
}
