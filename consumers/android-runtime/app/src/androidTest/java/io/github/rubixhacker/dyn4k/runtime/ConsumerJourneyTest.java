package io.github.rubixhacker.dyn4k.runtime;

import android.os.Build;
import org.junit.Test;

import static org.junit.Assert.assertEquals;

public final class ConsumerJourneyTest {
    private void run(String name) throws Exception {
        try {
            Class.forName(name).getMethod("main", String[].class).invoke(null, (Object) new String[0]);
        } catch (java.lang.reflect.InvocationTargetException failure) {
            throw new AssertionError(name, failure.getCause());
        }
    }

    @Test public void geometryAndIdentity() throws Exception {
        double boundary = 5.0e-7;
        assertEquals(0x3ea0c6f7a0b5ed8dL, Double.doubleToRawLongBits(boundary));
        String baselineMessage = String.format("radius cannot be %f", boundary);
        if (Build.VERSION.SDK_INT == 21) assertEquals("radius cannot be 0.000000", baselineMessage);
        assertEquals(baselineMessage, new org.dyn4j.exception.ValueOutOfRangeException("radius", boundary).getMessage());
        run("GeometryConsumer");
    }
    @Test public void collisionAndExtension() throws Exception { run("DetectionConsumer"); }
    @Test public void collisionModel() throws Exception { run("CollisionModelConsumer"); }
    @Test public void dynamicsAndErrors() throws Exception { run("DynamicsConsumer"); }
    @Test public void worldAndCallbacks() throws Exception { run("WorldConsumer"); }
    @Test public void jointsAndExtension() throws Exception { run("JointConsumer"); }
    @Test public void contacts() throws Exception { run("ContactConsumer"); }
}
