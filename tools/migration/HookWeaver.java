import javassist.ClassPool;
import javassist.CtClass;
import javassist.CtMethod;

public final class HookWeaver {
    public static void main(String[] args) throws Exception {
        String classes = args[0];
        ClassPool pool = ClassPool.getDefault();
        pool.insertClassPath(classes);
        CtClass frame = pool.get("org.dyn4j.samples.framework.SimulationFrame");
        CtMethod loop = frame.getDeclaredMethod("gameLoop");
        loop.insertBefore("org.dyn4j.samples.framework.SceneObserver.onLoopEnter(this);");
        loop.insertAfter("org.dyn4j.samples.framework.SceneObserver.tick(this);");
        frame.writeFile(classes);
        frame.detach();
    }
}
