import org.dyn4j.dynamics.*;
import org.dyn4j.geometry.*;
import org.dyn4j.world.World;

/** Recorder-free reproduction of the approved small-scale pentagon CCD scene. */
public final class CcdPassageProbe {
    public static void main(String[] args) {
        if(args.length==1&&args[0].equals("--help")){System.out.println("Usage: CcdPassageProbe\nRuns unchanged P pentagon inputs at scale .01/origin zero, ALL/NONE at 60/120Hz; reports first two steps.");return;}
        if(args.length!=0)throw new IllegalArgumentException("Use --help");
        for(int hz:new int[]{60,120})for(ContinuousDetectionMode mode:new ContinuousDetectionMode[]{ContinuousDetectionMode.ALL,ContinuousDetectionMode.NONE}){
            World<Body>w=new World<>();SceneCases.scaleWorld(w,0.01);w.setGravity(0,0);w.getSettings().setContinuousDetectionMode(mode);
            Body ground=new Body();BodyFixture gf=ground.addFixture(Geometry.createRectangle(0.2,0.0005));gf.setDensity(1);gf.setFriction(0);gf.setRestitution(0);gf.setRestitutionVelocity(0.01);ground.setMass(MassType.INFINITE);ground.setLinearDamping(0);ground.setAngularDamping(0);w.addBody(ground);
            Body b=new Body();Polygon shape=Geometry.createUnitCirclePolygon(5,0.001);BodyFixture f=b.addFixture(shape);f.setDensity(1);f.setFriction(0);f.setRestitution(0);f.setRestitutionVelocity(0.01);b.setMass(MassType.NORMAL);b.setLinearDamping(0);b.setAngularDamping(0);b.translate(0,0.01);b.setLinearVelocity(0,-1.2);b.setAngularVelocity(20);b.setBullet(true);w.addBody(b);
            for(int step=1;step<=2;step++){
                w.step(1,1.0/hz);double maxY=Double.NEGATIVE_INFINITY,minY=Double.POSITIVE_INFINITY;for(Vector2 vertex:shape.getVertices()){double y=b.getTransform().getTransformed(vertex).y;maxY=Math.max(maxY,y);minY=Math.min(minY,y);}
                System.out.println("hz="+hz+" mode="+mode+" step="+step+" centre="+b.getWorldCenter()+" velocity="+b.getLinearVelocity()+" omega="+b.getAngularVelocity()+" polygonMinY="+minY+" polygonMaxY="+maxY+" entirelyBelowGround="+(maxY < -0.00025));
            }
        }
    }
}
