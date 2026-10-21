import com.sun.jdi.event.Event;
import com.sun.jdi.event.VMDeathEvent;
import com.sun.jdi.event.VMDisconnectEvent;
import java.lang.reflect.Proxy;

public final class EndpointControl {
    private static Event event(Class<? extends Event> type) {
        return (Event) Proxy.newProxyInstance(EndpointControl.class.getClassLoader(),
            new Class<?>[] {type}, (proxy, method, arguments) -> null);
    }

    public static void main(String[] arguments) {
        if (!"vm-death".equals(RotationJdiProbe.terminalEvent(event(VMDeathEvent.class))) ||
            !"vm-disconnect".equals(
                RotationJdiProbe.terminalEvent(event(VMDisconnectEvent.class))))
            throw new IllegalStateException("JDI terminal events were conflated");
    }
}
