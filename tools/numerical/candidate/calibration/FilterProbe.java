public final class FilterProbe {
    private FilterProbe() {}

    public static void main(String[] args) {
        Capture.filter = "L-&&s0.01-o0.0,0.0-hz30";
        require(Capture.accepts("L-spring-dampertrue-s0.01-o0.0,0.0-hz30"));
        require(!Capture.accepts("CCD-world-circle-ALL-s0.01-o0.0,0.0-hz30"));
        require(!Capture.accepts("L-spring-dampertrue-s0.01-o1000.0,1000.0-hz30"));

        Capture.filter = "CCD-world-&&s0.01-o0.0,0.0-hz30";
        require(Capture.accepts("CCD-world-circle-ALL-s0.01-o0.0,0.0-hz30"));
        require(!Capture.accepts("L-spring-dampertrue-s0.01-o0.0,0.0-hz30"));
        System.out.println("FILTER_PROBE_PASSED");
    }

    private static void require(boolean condition) {
        if (!condition) throw new AssertionError("fixture family filter admitted the wrong case");
    }
}
