package org.dyn4j.calibration;

import java.lang.reflect.InvocationTargetException;
import java.util.function.IntConsumer;
import org.dyn4j.world.World;
import org.dyn4j.dynamics.*;
import org.dyn4j.geometry.*;
import org.dyn4j.collision.narrowphase.*;
import org.dyn4j.collision.continuous.*;

/** Passive instrumentation bridge for unchanged upstream test package access. */
public final class Bridge {
    public static String id;
    public static void record(String event, Object... values) {
        try {
            Class.forName("Capture").getMethod("record", String.class, String.class, Object[].class)
                .invoke(null, id, event, values);
        } catch (ReflectiveOperationException e) { throw failure(e); }
    }
    private static RuntimeException failure(ReflectiveOperationException e) {
        Throwable cause = e instanceof InvocationTargetException ? e.getCause() : e;
        if (cause instanceof RuntimeException r) return r;
        if (cause instanceof Error a) throw a;
        return new IllegalStateException(cause);
    }
    public static void step(World<Body> w, int count) { step(w, count, w.getSettings().getStepFrequency()); }
    public static void step(World<Body> w, int count, double dt) {
        try {
            Class.forName("Capture").getMethod("run", String.class, World.class, int.class, double.class,
                double.class, double.class, double.class, IntConsumer.class)
                .invoke(null, id, w, count, dt, 1.0, 0.0, 0.0, (IntConsumer) n -> {});
        } catch (ReflectiveOperationException e) { throw failure(e); }
    }
    public static boolean detect(NarrowphaseDetector detector, Convex a, Transform ta, Convex b, Transform tb) {
        record("query-input", detector, a, ta, b, tb);
        boolean found = detector.detect(a, ta, b, tb);
        record("query-output", found);
        return found;
    }
    public static boolean detect(NarrowphaseDetector detector, Convex a, Transform ta, Convex b, Transform tb, Penetration p) {
        record("query-input", detector, a, ta, b, tb);
        boolean found = detector.detect(a, ta, b, tb, p);
        record("query-output", found, p.getNormal().x, p.getNormal().y, p.getDepth());
        return found;
    }
    public static boolean toi(TimeOfImpactDetector detector, Convex a, Transform ta, Vector2 da, double aa, Convex b, Transform tb, Vector2 db, double ab, TimeOfImpact result) {
        record("toi-input", detector, a, ta, da, aa, b, tb, db, ab);
        boolean found = detector.getTimeOfImpact(a, ta, da, aa, b, tb, db, ab, result);
        record("toi-output", found, result.getTime(), result.getSeparation(), ta.lerped(da, aa, result.getTime()));
        return found;
    }
    public static void velocity(AbstractPhysicsBody b, Vector2 g, TimeStep dt, Settings settings) {
        record("integrateVelocity-input", b, g, dt, settings);
        b.integrateVelocity(g, dt, settings);
        record("integrateVelocity-output", b);
    }
    public static void position(AbstractPhysicsBody b, TimeStep dt, Settings settings) {
        record("integratePosition-input", b, dt, settings);
        b.integratePosition(dt, settings);
        record("integratePosition-output", b);
    }
}
