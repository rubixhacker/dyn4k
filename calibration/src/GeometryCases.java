import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.dyn4j.collision.narrowphase.*;
import org.dyn4j.geometry.*;

/** Deterministic geometry probes against the pinned, unmodified baseline. */
public final class GeometryCases {
    private GeometryCases() {}
    public static void runAll() {
        double[] scales = {0.01, 1, 100};
        double[][] offsets = {{0,0},{1000,1000},{-1000,1000},{1000000,-1000000},{-1000000,1000000}};
        for (int si=0; si<scales.length; si++) for (int oi=0; oi<offsets.length; oi++) {
            double s=scales[si], ox=offsets[oi][0], oy=offsets[oi][1];
            String suffix="/s"+si+"/o"+oi;
            for (int di=0; di<5; di++) {
                double delta=new double[]{-1e-8,-1e-12,0,1e-12,1e-8}[di];
                Circle a=new Circle(s), b=new Circle(0.5*s);
                Transform ta=at(ox,oy), tb=at(ox+s*(1.5+delta),oy);
                for (String algorithm: List.of("SAT","GJK")) for(int order=0;order<2;order++)
                    pair("P/G-boundary/circle"+suffix+"/d"+di+"/"+algorithm+"/"+order,
                        algorithm, order==0?a:b,order==0?ta:tb,order==0?b:a,order==0?tb:ta,
                        s,ox,oy,delta);
            }
            for (int hi=0;hi<3;hi++) triangle("P/G-boundary/triangle"+suffix+"/h"+hi,
                s,ox,oy,new double[]{1e-4,1e-8,1e-12}[hi]);
            for(String algorithm:List.of("SAT","GJK")) {
                Circle a=new Circle(s),b=new Circle(0.5*s);
                Transform ta=at(ox,oy),tb=at(ox,oy);
                for(int stage=0;stage<4;stage++) {
                    if(stage==1 || stage==3) ta.translate(-s,0);
                    if(stage==2) tb.translate(0,1.5*s);
                    for(int order=0;order<2;order++) pair("G-circle/detect"+algorithm+suffix+"/stage"+stage+"/"+order,
                        algorithm,order==0?a:b,order==0?ta:tb,order==0?b:a,order==0?tb:ta,s,ox,oy,0);
                }
            }
        }
    }
    private static Transform at(double x,double y) { Transform t=new Transform(); t.translate(x,y); return t; }
    private static void pair(String id,String algorithm,Circle a,Transform ta,Circle b,Transform tb,
                             double scale,double ox,double oy,double delta) {
        Map<String,Object> p=new LinkedHashMap<>();
        p.put("algorithm",algorithm); p.put("scale",scale); p.put("origin",new Vector2(ox,oy));
        p.put("nominalDelta",delta);p.put("radius1",a.getRadius());p.put("radius2",b.getRadius());
        p.put("transform1",ta);p.put("transform2",tb);
        Penetration penetration=new Penetration();
        NarrowphaseDetector detector=algorithm.equals("SAT")?new Sat():new Gjk();
        if(detector instanceof Gjk gjk) {
            gjk.setDistanceEpsilon(gjk.getDistanceEpsilon()*scale*scale);
            gjk.setRaycastEpsilon(gjk.getRaycastEpsilon()*scale*scale);
            Epa epa=(Epa)gjk.getMinkowskiPenetrationSolver();
            epa.setDistanceEpsilon(epa.getDistanceEpsilon()*scale);
        }
        p.put("detected",detector.detect(a,ta,b,tb,penetration));
        p.put("booleanOnlyDetected",detector.detect(a,ta,b,tb));
        p.put("penetrationNormal",penetration.getNormal());p.put("penetrationDepth",penetration.getDepth());
        if(detector instanceof Gjk gjk) {
            Separation separation=new Separation();
            p.put("distanceAvailable",gjk.distance(a,ta,b,tb,separation));
            p.put("distance",separation.getDistance());p.put("separationNormal",separation.getNormal());
            p.put("point1",separation.getPoint1());p.put("point2",separation.getPoint2());
            p.put("point1FrameLocal",separation.getPoint1().difference(new Vector2(ox,oy)));
            p.put("point2FrameLocal",separation.getPoint2().difference(new Vector2(ox,oy)));
            p.put("detectorSettings",gjk);
            p.put("penetrationSolverSettings",gjk.getMinkowskiPenetrationSolver());
        }
        Capture.query(id,p);
    }
    private static void triangle(String id,double scale,double ox,double oy,double h) {
        Vector2 a=new Vector2(ox,oy),b=new Vector2(ox+scale,oy),c=new Vector2(ox+0.5*scale,oy+h*scale);
        Map<String,Object> p=new LinkedHashMap<>();
        p.put("scale",scale);p.put("origin",new Vector2(ox,oy));p.put("nominalHeight",h);
        p.put("vertices",List.of(a,b,c));
        p.put("winding",Geometry.getWinding(a,b,c));
        p.put("segmentLocation",Segment.getLocation(c,a,b));
        p.put("robustLocation",RobustGeometry.getLocation(c,a,b));
        Triangle triangle;
        try { triangle=new Triangle(a.copy(),b.copy(),c.copy()); }
        catch(IllegalArgumentException e) {
            p.put("constructionAccepted",false);p.put("exceptionClass",e.getClass().getName());p.put("exceptionMessage",e.getMessage());
            Capture.query(id,p);Capture.rejected(id,e.getClass().getName()+": "+e.getMessage());return;
        }
        p.put("constructionAccepted",true);p.put("area",triangle.getArea());p.put("center",triangle.getCenter());
        p.put("centerFrameLocal",triangle.getCenter().difference(new Vector2(ox,oy)));
        Capture.query(id,p);
    }
}
