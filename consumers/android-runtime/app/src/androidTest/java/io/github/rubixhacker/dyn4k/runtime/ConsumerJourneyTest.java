package io.github.rubixhacker.dyn4k.runtime;

import org.junit.Test;

public final class ConsumerJourneyTest {
    private void run(String name) throws Exception {
        try {
            Class.forName(name).getMethod("main", String[].class).invoke(null, (Object) new String[0]);
        } catch (java.lang.reflect.InvocationTargetException failure) {
            throw new AssertionError(name, failure.getCause());
        }
    }

    @Test public void geometryAndIdentity() throws Exception { run("GeometryConsumer"); }
    @Test public void collisionAndExtension() throws Exception { run("DetectionConsumer"); }
    @Test public void collisionModel() throws Exception { run("CollisionModelConsumer"); }
    @Test public void dynamicsAndErrors() throws Exception { run("DynamicsConsumer"); }
    @Test public void worldAndCallbacks() throws Exception { run("WorldConsumer"); }
    @Test public void jointsAndExtension() throws Exception { run("JointConsumer"); }
    @Test public void contacts() throws Exception { run("ContactConsumer"); }
}
