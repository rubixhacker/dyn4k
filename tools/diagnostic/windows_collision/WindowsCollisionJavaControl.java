package org.dyn4j.collision.narrowphase;

import org.dyn4j.collision.manifold.ClippingManifoldSolver;
import org.dyn4j.collision.manifold.IndexedManifoldPointId;
import org.dyn4j.collision.manifold.Manifold;
import org.dyn4j.collision.manifold.ManifoldPoint;
import org.dyn4j.collision.manifold.ManifoldPointId;
import org.dyn4j.geometry.Capsule;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.Segment;
import org.dyn4j.geometry.Slice;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector2;

public final class WindowsCollisionJavaControl {
    private WindowsCollisionJavaControl() {}

    public static void main(String[] args) {
        fixture("CapsuleSlice", new Capsule(1.0, 0.5), new Slice(0.5, Math.toRadians(50.0)), -0.25, "gjk");
        fixture("CirclePolygon", new Circle(1.0), Geometry.createUnitCirclePolygon(6, 0.5), -1.0, "gjk");
        fixture("CircleSegment", new Circle(1.0), new Segment(new Vector2(-0.5, 0.0), new Vector2(0.5, 0.0)), -1.0, "gjk");
        fixture("CircleSlice", new Circle(0.5), new Slice(0.5, Math.toRadians(50.0)), -0.25, "gjk");
        fixture("PolygonCapsule", Geometry.createUnitCirclePolygon(5, 0.5), new Capsule(1.0, 0.5), -0.5, "sat");
        fixture("PolygonPolygon", Geometry.createUnitCirclePolygon(5, 1.0), Geometry.createUnitCirclePolygon(6, 0.5), -1.0, "sat");
    }

    private static void fixture(String name, Convex first, Convex second, double shiftX, String detector) {
        Transform t1 = new Transform();
        Transform t2 = new Transform();
        WindowsCollisionJavaTrace.RecordingEpa epa = new WindowsCollisionJavaTrace.RecordingEpa();
        Gjk gjk = new Gjk(epa);
        Sat sat = new Sat();
        NarrowphaseDetector selected = detector.equals("gjk") ? gjk : sat;
        Penetration p = new Penetration();
        int step = 0;
        step = detect(name, detector, "center", "forward", step, first, t1, second, t2, selected, p, epa);
        step = detect(name, detector, "center", "reverse", step, second, t2, first, t1, selected, p, epa);
        t1.translate(shiftX, 0.0);
        step = detect(name, detector, "shifted", "forward", step, first, t1, second, t2, selected, p, epa);
        step = detect(name, detector, "shifted", "reverse", step, second, t2, first, t1, selected, p, epa);

        t1.identity();
        Manifold m = new Manifold();
        ClippingManifoldSolver clip = new ClippingManifoldSolver();
        for (String phase : new String[] {"center", "shifted"}) {
            if (phase.equals("shifted")) t1.translate(shiftX, 0.0);
            for (String algorithm : new String[] {"gjk", "sat"}) {
                NarrowphaseDetector d = algorithm.equals("gjk") ? gjk : sat;
                step = clip(name, phase, "forward", algorithm, step, first, t1, second, t2, d, clip, p, m, epa);
                step = clip(name, phase, "reverse", algorithm, step, second, t2, first, t1, d, clip, p, m, epa);
            }
        }
    }

    private static int detect(String fixture, String algorithm, String phase, String order, int step,
                              Convex a, Transform ta, Convex b, Transform tb, NarrowphaseDetector detector, Penetration p,
                              WindowsCollisionJavaTrace.RecordingEpa epa) {
        p.clear();
        epa.reset();
        boolean hit = detector.detect(a, ta, b, tb, p);
        boolean booleanHit = detector.detect(a, ta, b, tb);
        emit(fixture, algorithm.equals("gjk") ? "detectGjk" : "detectSat", phase, order, step, algorithm, a, ta, b, tb,
             hit, Boolean.valueOf(booleanHit), p, null, null, epa);
        return step + 1;
    }

    private static int clip(String fixture, String phase, String order, String algorithm, int step,
                            Convex a, Transform ta, Convex b, Transform tb, NarrowphaseDetector detector,
                            ClippingManifoldSolver clip, Penetration p, Manifold m, WindowsCollisionJavaTrace.RecordingEpa epa) {
        p.clear();
        m.clear();
        epa.reset();
        boolean hit = detector.detect(a, ta, b, tb, p);
        boolean clipped = hit && clip.getManifold(p, a, ta, b, tb, m);
        emit(fixture, "getClipManifold", phase, order, step, algorithm, a, ta, b, tb,
             hit, null, p, Boolean.valueOf(clipped), m, epa);
        return step + 1;
    }

    private static void emit(String fixture, String method, String phase, String order, int step, String algorithm,
                             Convex a, Transform ta, Convex b, Transform tb, boolean hit, Boolean booleanHit,
                             Penetration p, Boolean clipped, Manifold m, WindowsCollisionJavaTrace.RecordingEpa epa) {
        StringBuilder record = new StringBuilder("DYN4K_COLLISION_DIAGNOSTIC\tv2\tprovider=dyn4j-6.0.0");
        field(record, "fixture", fixture);
        field(record, "method", method);
        field(record, "phase", phase);
        field(record, "order", order);
        field(record, "step", Integer.toString(step));
        field(record, "algorithm", algorithm);
        field(record, "a.transform", values(ta.getValues()));
        field(record, "b.transform", values(tb.getValues()));
        field(record, "a.center.local", vector(a.getCenter()));
        field(record, "b.center.local", vector(b.getCenter()));
        field(record, "a.center.world", vector(ta.getTransformed(a.getCenter())));
        field(record, "b.center.world", vector(tb.getTransformed(b.getCenter())));
        field(record, "hit", Boolean.toString(hit));
        field(record, "booleanHit", booleanHit == null ? "na" : booleanHit.toString());
        field(record, "penetration.normal", vector(p.getNormal()));
        field(record, "penetration.depth", number(p.getDepth()));
        field(record, "selection", algorithm.equals("sat") ? "satSourceReplay" : epa.edge == null ? "unavailable" : "epaSourceReplay");
        field(record, "clipped", clipped == null ? "na" : clipped.toString());
        field(record, "manifold.normal", m == null ? "na" : vector(m.getNormal()));
        field(record, "manifold.count", m == null ? "na" : Integer.toString(m.getPoints().size()));
        for (String field : WindowsCollisionJavaTrace.pairInputs(a, ta, b, tb, hit ? p.getNormal() : null)) record.append('\t').append(field);
        if (algorithm.equals("sat")) {
            for (String field : WindowsCollisionJavaTrace.sat(a, ta, b, tb, p, hit)) record.append('\t').append(field);
        }
        for (String field : epa.fields(p)) record.append('\t').append(field);
        if (m != null) {
            for (int i = 0; i < m.getPoints().size(); i++) {
                ManifoldPoint point = m.getPoints().get(i);
                ManifoldPointId id = point.getId();
                String idValue = "distance";
                if (id instanceof IndexedManifoldPointId) {
                    IndexedManifoldPointId indexed = (IndexedManifoldPointId) id;
                    idValue = "indexed:" + indexed.getReferenceEdgeIndex() + ":" + indexed.getIncidentEdgeIndex()
                            + ":" + indexed.getIncidentVertexIndex() + ":" + indexed.isFlipped();
                }
                field(record, "manifold.point." + i + ".position", vector(point.getPoint()));
                field(record, "manifold.point." + i + ".depth", number(point.getDepth()));
                field(record, "manifold.point." + i + ".id", idValue);
            }
        }
        System.out.println(record);
    }

    private static void field(StringBuilder record, String key, String value) {
        record.append('\t').append(key).append('=').append(value);
    }

    private static String number(double value) {
        return WindowsCollisionJavaTrace.number(value);
    }

    private static String values(double[] values) {
        return WindowsCollisionJavaTrace.values(values);
    }

    private static String vector(Vector2 value) {
        return WindowsCollisionJavaTrace.vector(value);
    }
}
