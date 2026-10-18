package performance;

import com.sun.management.ThreadMXBean;
import java.lang.reflect.Proxy;

public final class SustainedAllocationProbeControl {
    private SustainedAllocationProbeControl() {
    }

    public static void main(String[] args) {
        if (args.length != 1) throw new IllegalArgumentException("unsupported or negative");
        ThreadMXBean bean = (ThreadMXBean) Proxy.newProxyInstance(
                ThreadMXBean.class.getClassLoader(), new Class<?>[]{ThreadMXBean.class},
                (proxy, method, values) -> switch (method.getName()) {
                    case "isThreadAllocatedMemorySupported" -> !args[0].equals("unsupported");
                    case "isThreadAllocatedMemoryEnabled" -> true;
                    case "getThreadAllocatedBytes" -> -1L;
                    default -> throw new UnsupportedOperationException(method.getName());
                });
        try {
            SustainedSidecars.AllocationProbe.require(bean);
            throw new AssertionError("unsupported allocation probe was accepted");
        } catch (IllegalStateException expected) {
            if (!expected.getMessage().contains("allocation")) throw expected;
            System.out.println(expected.getMessage());
        }
    }
}
