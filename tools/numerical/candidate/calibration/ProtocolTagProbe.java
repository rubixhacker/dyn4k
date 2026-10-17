import org.dyn4j.collision.manifold.ManifoldPointId;
import java.util.IdentityHashMap;

public final class ProtocolTagProbe {
    private static final String DISTANCE_TAG = "org.dyn4j.collision.manifold.ManifoldPointId$1";

    public static void main(String[] args) {
        String singleton = (String) Capture.props(ManifoldPointId.DISTANCE).get("type");
        if (!DISTANCE_TAG.equals(singleton)) {
            throw new AssertionError("distance singleton tag: " + singleton);
        }
        String singletonRecord = Capture.json(ManifoldPointId.DISTANCE, 0, new IdentityHashMap<>());
        if (!singletonRecord.equals("{\"type\":\"" + DISTANCE_TAG + "\"}")) {
            throw new AssertionError("distance singleton record: " + singletonRecord);
        }

        ManifoldPointId lookalike = new ManifoldPointId() {
            @Override public ManifoldPointId copy() { return this; }
            @Override public String toString() { return ManifoldPointId.DISTANCE.toString(); }
        };
        String custom = (String) Capture.props(lookalike).get("type");
        if (!custom.equals(lookalike.getClass().getName()) || DISTANCE_TAG.equals(custom)) {
            throw new AssertionError("custom ID was relabelled: " + custom);
        }
        String customRecord = Capture.json(lookalike, 0, new IdentityHashMap<>());
        if (!customRecord.equals("{\"type\":\"" + custom + "\"}")) {
            throw new AssertionError("custom ID record was relabelled: " + customRecord);
        }
        System.out.println("DISTANCE_RECORD=" + singletonRecord + " CUSTOM_RECORD=" + customRecord);
    }
}
