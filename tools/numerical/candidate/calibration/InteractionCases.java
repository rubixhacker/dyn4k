import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.joint.DistanceJoint;
import org.dyn4j.dynamics.joint.PrismaticJoint;
import org.dyn4j.dynamics.joint.WheelJoint;
import org.dyn4j.dynamics.joint.WeldJoint;
import org.dyn4j.dynamics.joint.RevoluteJoint;
import org.dyn4j.dynamics.joint.PulleyJoint;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.World;

public final class InteractionCases {
    private static final String SOURCE="058bf6d982a0fb89b54050f929f6ea9dae53b714";
    public static void runAll() {
        for(String control:new String[]{"combined","spring-off","motor-off","limits-off"}) {
            prismatic(control);
            wheel(control);
        }
        distance("combined",false);
        distance("spring-off",false);
        distance("combined",true);
        distance("spring-off",true);
        capTransitions();
        motorCapTransitions();
        prismaticSpringTransition();
        equalLimits();
        weldSpringTransition();
        pulleySlackTransition();
    }
    private static World<Body> bodies(boolean gravity) {
        World<Body>w=new World<>();if(!gravity)w.setGravity(World.ZERO_GRAVITY);
        Body ground=new Body();ground.addFixture(Geometry.createRectangle(10,0.5)).setFriction(0);ground.setMass(MassType.INFINITE);ground.setLinearDamping(0);ground.setAngularDamping(0);w.addBody(ground);
        Body body=new Body();body.addFixture(Geometry.createCircle(0.5)).setFriction(0);body.setMass(MassType.NORMAL);body.translate(0,2);body.setLinearDamping(0);body.setAngularDamping(0);w.addBody(body);
        return w;
    }
    private static void binding(String id,String source,String choices) {
        Capture.record(id,"experimental-input-binding",SOURCE,source,choices,"new experimental input; not U or acceptance approval");
    }
    private static void prismatic(String control) {
        String id="P-JINT-Prismatic-"+control;if(!Capture.accepts(id))return;
        World<Body>w=bodies(false);Body body=w.getBody(1);
        PrismaticJoint<Body>j=new PrismaticJoint<>(w.getBody(0),body,body.getWorldCenter(),new Vector2(1,0));
        j.setSpringEnabled(!control.equals("spring-off"));j.setSpringFrequency(8);j.setSpringDamperEnabled(true);j.setSpringDampingRatio(0.2);j.setSpringRestOffset(2);j.setMaximumSpringForceEnabled(true);j.setMaximumSpringForce(10);
        j.setMotorEnabled(!control.equals("motor-off"));j.setMotorSpeed(1);j.setMaximumMotorForceEnabled(true);j.setMaximumMotorForce(1000);j.setLimits(-1,1);j.setLimitsEnabled(!control.equals("limits-off"));w.addJoint(j);
        String choices="rest2; spring8Hz/damping.2/cap10; motor speed+1/cap1000; limits[-1,1]; motor speed-1 before201,+1 before401; control="+control;
        binding(id,"PrismaticJointSimulationTest.springOnly geometry; declared combined-mode experiment",choices);
        Capture.run(id,w,600,1.0/60,1,0,0,step->{if(step==1)binding(id,"PrismaticJointSimulationTest.springOnly geometry",choices);if(step==201||step==401){j.setMotorSpeed(step==201?-1:1);Capture.action("setMotorSpeed("+(step==201?-1:1)+") before step"+step);}});
    }
    private static void wheel(String control) {
        String id="P-JINT-Wheel-"+control;if(!Capture.accepts(id))return;
        World<Body>w=bodies(true);Body body=w.getBody(1);
        WheelJoint<Body>j=new WheelJoint<>(w.getBody(0),body,body.getWorldCenter(),new Vector2(0,1));
        j.setSpringEnabled(!control.equals("spring-off"));j.setMaximumSpringForceEnabled(true);j.setMaximumSpringForce(10);
        j.setMotorEnabled(!control.equals("motor-off"));j.setMotorSpeed(Math.PI/2);j.setMaximumMotorTorqueEnabled(true);j.setMaximumMotorTorque(0.25);j.setLimits(-1,5);j.setLimitsEnabled(!control.equals("limits-off"));w.addJoint(j);
        String choices="vertical axis; default spring/damper; springcap10; motor speed+pi/2/cap.25; limits[-1,5]; before201 limits[1,5],speed-pi/2; before401 limits[-1,-.5],speed+pi/2; control="+control;
        binding(id,"WheelJointSimulationTest.springDamperWithLimits geometry and limit bands; declared combined-mode experiment",choices);
        Capture.run(id,w,600,1.0/60,1,0,0,step->{if(step==1)binding(id,"WheelJointSimulationTest.springDamperWithLimits geometry and limit bands",choices);if(step==201||step==401){if(step==201)j.setLimits(1,5);else j.setLimits(-1,-0.5);Capture.action("setLimits("+(step==201?"1,5":"-1,-0.5")+") before step"+step);j.setMotorSpeed(step==201?-Math.PI/2:Math.PI/2);Capture.action("setMotorSpeed("+(step==201?-Math.PI/2:Math.PI/2)+") before step"+step);}});
    }
    private static void distance(String control,boolean lower) {
        String id="P-JINT-Distance-valid-1-to-5-"+(lower?"lower-":"")+control;if(!Capture.accepts(id))return;
        World<Body>w=bodies(false);Body ground=w.getBody(0),body=w.getBody(1);
        DistanceJoint<Body>j=new DistanceJoint<>(ground,body,ground.getWorldCenter(),body.getWorldCenter());j.setRestDistance(lower?1:10);j.setLimitsEnabled(1,5);j.setSpringEnabled(!control.equals("spring-off"));j.setSpringFrequency(8);j.setSpringDamperEnabled(true);j.setSpringDampingRatio(0.2);w.addJoint(j);
        String choices="valid nonnegative limits[1,5]; rest"+(lower?1:10)+"; spring8Hz/damping.2; no mutations; control="+control;
        String source=lower?"DistanceJointSimulationTest.lowerLimitWithSpring geometry/rest1; new limit range[1,5]":"DistanceJointSimulationTest.upperLimitWithSpring initial setup";
        binding(id,source,choices);
        Capture.run(id,w,600,1.0/60,1,0,0,step->{if(step==1)binding(id,source,choices);});
    }
    private static void capTransitions() {
        String id="P-JINT-Distance-cap-transition";
        if(Capture.accepts(id)){
            World<Body>w=bodies(false);Body a=w.getBody(0),b=w.getBody(1);DistanceJoint<Body>j=new DistanceJoint<>(a,b,a.getWorldCenter(),b.getWorldCenter());j.setRestDistance(3);j.setSpringEnabled(true);j.setSpringFrequency(8);j.setSpringDamperEnabled(true);j.setSpringDampingRatio(0.2);j.setMaximumSpringForce(200);j.setMaximumSpringForceEnabled(false);w.addJoint(j);
            String choices="springOnly setup; cap200 initially disabled; before201 enable then rest10; before401 disable; no state reset";binding(id,"DistanceJointSimulationTest.springOnly plus declared re-excitation",choices);
            Capture.run(id,w,600,1.0/60,1,0,0,step->{if(step==1)binding("P-JINT-Distance-cap-transition","source-derived cap experiment",choices);if(step==201){j.setMaximumSpringForceEnabled(true);Capture.action("setMaximumSpringForceEnabled(true)");j.setRestDistance(10);Capture.action("setRestDistance(10)");}if(step==401){j.setMaximumSpringForceEnabled(false);Capture.action("setMaximumSpringForceEnabled(false)");}});
        }
        id="P-JINT-Weld-cap-transition";
        if(Capture.accepts(id)){
            World<Body>w=bodies(true);Body a=w.getBody(0),b=w.getBody(1);b.removeAllFixtures();b.addFixture(Geometry.createRectangle(1,0.5)).setFriction(0);b.setMass(MassType.NORMAL);WeldJoint<Body>j=new WeldJoint<>(a,b,b.getWorldCenter().sum(-0.5,0));j.setSpringEnabled(true);j.setSpringDamperEnabled(true);j.setSpringDampingRatio(0.3);j.setSpringFrequency(8);j.setMaximumSpringTorque(5);j.setMaximumSpringTorqueEnabled(false);w.addJoint(j);
            String choices="softConstraint setup; cap5 initially disabled; before201 enable then force(0,-10) at(.5,2); before401 disable; no reset";binding(id,"WeldJointSimulationTest.softConstraint plus declared re-excitation",choices);
            Capture.run(id,w,600,1.0/60,1,0,0,step->{if(step==1)binding("P-JINT-Weld-cap-transition","source-derived cap experiment",choices);if(step==201){j.setMaximumSpringTorqueEnabled(true);Capture.action("setMaximumSpringTorqueEnabled(true)");b.applyForce(new Vector2(0,-10),new Vector2(0.5,2));Capture.action("applyForce((0,-10),world(.5,2))");}if(step==401){j.setMaximumSpringTorqueEnabled(false);Capture.action("setMaximumSpringTorqueEnabled(false)");}});
        }
        id="P-JINT-Wheel-cap-transition";
        if(Capture.accepts(id)){
            World<Body>w=bodies(true);Body a=w.getBody(0),b=w.getBody(1);WheelJoint<Body>j=new WheelJoint<>(a,b,b.getWorldCenter(),new Vector2(0,1));j.setLimitsEnabled(-1,5);j.setMaximumSpringForce(200);j.setMaximumSpringForceEnabled(false);w.addJoint(j);
            String choices="vertical spring setup; cap200 initially disabled; before201 enable then limits[-1,-.5]; before401 disable; no reset";binding(id,"WheelJointSimulationTest.springDamperWithLimits plus declared re-excitation",choices);
            Capture.run(id,w,600,1.0/60,1,0,0,step->{if(step==1)binding("P-JINT-Wheel-cap-transition","source-derived cap experiment",choices);if(step==201){j.setMaximumSpringForceEnabled(true);Capture.action("setMaximumSpringForceEnabled(true)");j.setLimits(-1,-0.5);Capture.action("setLimits(-1,-0.5)");}if(step==401){j.setMaximumSpringForceEnabled(false);Capture.action("setMaximumSpringForceEnabled(false)");}});
        }
    }
    private static void motorCapTransitions() {
        for(String type:new String[]{"Prismatic","Revolute","Wheel"}) {
            String id="P-JINT-"+type+"-motor-cap-transition";if(!Capture.accepts(id))continue;
            World<Body>w=bodies(false);Body a=w.getBody(0),b=w.getBody(1);
            java.util.function.Consumer<Boolean> enable;
            java.util.function.DoubleConsumer speed;
            double magnitude=type.equals("Prismatic")?1:Math.PI/2;
            if(type.equals("Prismatic")){PrismaticJoint<Body>j=new PrismaticJoint<>(a,b,b.getWorldCenter(),new Vector2(1,0));j.setMotorEnabled(true);j.setMaximumMotorForce(10);j.setMaximumMotorForceEnabled(false);j.setMotorSpeed(magnitude);w.addJoint(j);enable=j::setMaximumMotorForceEnabled;speed=j::setMotorSpeed;}
            else if(type.equals("Revolute")){w.getSettings().setAngularTolerance(0);RevoluteJoint<Body>j=new RevoluteJoint<>(a,b,b.getWorldCenter());j.setMotorEnabled(true);j.setMaximumMotorTorque(0.25);j.setMaximumMotorTorqueEnabled(false);j.setMotorSpeed(magnitude);w.addJoint(j);enable=j::setMaximumMotorTorqueEnabled;speed=j::setMotorSpeed;}
            else{WheelJoint<Body>j=new WheelJoint<>(a,b,b.getWorldCenter(),new Vector2(-1,0));j.setMotorEnabled(true);j.setMaximumMotorTorque(0.25);j.setMaximumMotorTorqueEnabled(false);j.setMotorSpeed(magnitude);w.addJoint(j);enable=j::setMaximumMotorTorqueEnabled;speed=j::setMotorSpeed;}
            String choices="source motor geometry; cap"+(type.equals("Prismatic")?"10N":".25Nm")+" initially disabled; speed+"+magnitude+"; before201 enable then reverse; before401 disable then reverse; no reset";
            binding(id,type+" motor source geometry; new cap-transition experiment",choices);
            Capture.run(id,w,600,1.0/60,1,0,0,step->{if(step==1)binding(id,type+" motor-cap experiment",choices);if(step==201||step==401){enable.accept(step==201);Capture.action("motor cap enabled="+(step==201));speed.accept(step==201?-magnitude:magnitude);Capture.action("setMotorSpeed("+(step==201?-magnitude:magnitude)+")");}});
        }
    }
    private static void prismaticSpringTransition() {
        String id="P-JINT-Prismatic-spring-cap-transition";if(!Capture.accepts(id))return;
        World<Body>w=bodies(false);Body a=w.getBody(0),b=w.getBody(1);PrismaticJoint<Body>j=new PrismaticJoint<>(a,b,b.getWorldCenter(),new Vector2(1,0));j.setSpringEnabled(true);j.setSpringFrequency(8);j.setSpringDamperEnabled(true);j.setSpringDampingRatio(0.2);j.setSpringRestOffset(2);j.setMaximumSpringForce(10);j.setMaximumSpringForceEnabled(false);w.addJoint(j);
        String choices="springOnly geometry; spring8Hz/.2/rest+2/cap10 disabled; before201 enable then rest-2; before401 disable; no reset";binding(id,"PrismaticJointSimulationTest.springOnly plus new signed rest stimulus",choices);
        Capture.run(id,w,600,1.0/60,1,0,0,step->{if(step==1)binding(id,"Prismatic spring-cap experiment",choices);if(step==201){j.setMaximumSpringForceEnabled(true);Capture.action("setMaximumSpringForceEnabled(true)");j.setSpringRestOffset(-2);Capture.action("setSpringRestOffset(-2)");}if(step==401){j.setMaximumSpringForceEnabled(false);Capture.action("setMaximumSpringForceEnabled(false)");}});
    }
    private static Body weldBody(World<Body>w){Body b=w.getBody(1);b.removeAllFixtures();b.addFixture(Geometry.createRectangle(1,0.5)).setFriction(0);b.setMass(MassType.NORMAL);return b;}
    private static WeldJoint<Body> weld(World<Body>w,Body b){WeldJoint<Body>j=new WeldJoint<>(w.getBody(0),b,b.getWorldCenter().sum(-0.5,0));j.setSpringEnabled(true);j.setSpringDamperEnabled(true);j.setSpringDampingRatio(0.3);j.setSpringFrequency(8);w.addJoint(j);return j;}
    private static void equalLimits(){
        for(String type:new String[]{"Distance","Prismatic","Revolute","Weld"}){
            String id="P-JINT-"+type+"-enabled-equal";if(!Capture.accepts(id))continue;
            World<Body>w=bodies(type.equals("Weld"));Body a=w.getBody(0),b=w.getBody(1);
            if(type.equals("Distance")){w.getSettings().setMaximumLinearCorrection(0.2);w.getSettings().setPositionConstraintSolverIterations(10);DistanceJoint<Body>j=new DistanceJoint<>(a,b,a.getWorldCenter(),b.getWorldCenter());j.setRestDistance(10);j.setLimitsEnabled(0,0);w.addJoint(j);}
            else if(type.equals("Prismatic")){PrismaticJoint<Body>j=new PrismaticJoint<>(a,b,b.getWorldCenter(),new Vector2(1,0));j.setMotorEnabled(true);j.setMotorSpeed(1);j.setMaximumMotorForceEnabled(true);j.setMaximumMotorForce(10);j.setLimitsEnabled(0,0);w.addJoint(j);}
            else if(type.equals("Revolute")){w.getSettings().setAngularTolerance(0);RevoluteJoint<Body>j=new RevoluteJoint<>(a,b,b.getWorldCenter());j.setMotorEnabled(true);j.setMotorSpeed(Math.PI/2);j.setMaximumMotorTorqueEnabled(true);j.setMaximumMotorTorque(0.25);j.setLimitsEnabled(0,0);w.addJoint(j);}
            else{b=weldBody(w);WeldJoint<Body>j=weld(w,b);j.setLimitsEnabled(0,0);b.applyForce(new Vector2(0,-10),new Vector2(0.5,2));}
            String choices="enabled equal limits[0,0]; source-compatible drive; Distance initialseparation2/rest10, Prism motor1/cap10, Revolute motorpi/2/cap.25, Weld source offcentre force; active type="+type;
            binding(id,type+" source geometry plus declared enabled-equal experiment",choices);
            Capture.run(id,w,600,1.0/60,1,0,0,step->{if(step==1)binding(id,type+" enabled-equal experiment",choices);});
        }
    }
    private static void weldSpringTransition(){
        String id="P-JINT-Weld-spring-enable-transition";if(!Capture.accepts(id))return;
        World<Body>w=bodies(true);Body b=weldBody(w);WeldJoint<Body>j=weld(w,b);j.setSpringEnabled(false);
        String choices="source softConstraint geometry; spring initiallyfalse; before201 springtrue then force(0,-10) at(.5,2); before401 springfalse; no reset";binding(id,"WeldJointSimulationTest.softConstraint plus fresh source force",choices);
        Capture.run(id,w,600,1.0/60,1,0,0,step->{if(step==1)binding(id,"Weld spring-enable experiment",choices);if(step==201){j.setSpringEnabled(true);Capture.action("setSpringEnabled(true)");b.applyForce(new Vector2(0,-10),new Vector2(0.5,2));Capture.action("applyForce((0,-10),world(.5,2))");}if(step==401){j.setSpringEnabled(false);Capture.action("setSpringEnabled(false)");}});
    }
    private static void pulleySlackTransition(){
        String id="P-JINT-Pulley-slack-transition";if(!Capture.accepts(id))return;
        World<Body>w=new World<>();Body g=new Body();g.addFixture(Geometry.createRectangle(10,1)).setFriction(0);g.setMass(MassType.INFINITE);g.setLinearDamping(0);g.setAngularDamping(0);g.translate(0,-1);w.addBody(g);
        Body a=new Body(),b=new Body();for(Body body:new Body[]{a,b}){body.addFixture(Geometry.createCircle(0.5)).setFriction(0);body.setMass(MassType.NORMAL);body.setLinearDamping(0);body.setAngularDamping(0);}a.translate(-1,0);b.translate(1,0.5);w.addBody(a);w.addBody(b);
        PulleyJoint<Body>j=new PulleyJoint<>(a,b,new Vector2(-1,1),new Vector2(1,1),new Vector2(-1,0),new Vector2(1,0.5));w.addJoint(j);
        String choices="withAndWithoutSlack exact3body preparation: step1,velocity(0,10),step2; slackfalse; before201 velocity(0,10),translate(0,.1),slacktrue; before401 slackfalse; same world retained";binding(id,"PulleyJointSimulationTest.withAndWithoutSlack plus delayed fresh source actions",choices);
        Capture.run(id+"-preparation",w,1,1.0/60,1,0,0,step->{});b.setLinearVelocity(0,10);Capture.record(id+"-preparation","source-action","body2.setLinearVelocity(0,10) before source step2");Capture.run(id+"-preparation",w,2,1.0/60,1,0,0,step->{});
        Capture.run(id,w,600,1.0/60,1,0,0,step->{if(step==1)binding(id,"Pulley fresh slack-transition experiment",choices);if(step==201){b.setLinearVelocity(0,10);Capture.action("body2.setLinearVelocity(0,10)");b.translate(0,0.1);Capture.action("body2.translate(0,.1)");j.setSlackEnabled(true);Capture.action("setSlackEnabled(true)");}if(step==401){j.setSlackEnabled(false);Capture.action("setSlackEnabled(false)");}});
    }
}
