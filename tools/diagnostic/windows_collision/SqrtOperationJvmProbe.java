package org.dyn4j.geometry;

public final class SqrtOperationJvmProbe {
    private static volatile double sink;
    private record Input(String id, long xBits, long yBits, long expectedRootBits) {}

    private static final Input[] INPUTS = {
        new Input("CirclePolygon.edge3", -4621899953565315924L, -4625196817309499400L, 4602678819172646911L),
        new Input("CapsuleSlice.epa4", 4603460912955918154L, -4617903595553423057L, 4607182418800017407L),
        new Input("CirclePolygon.epa3", -4619490269450149183L, -4618227961596862473L, 4607182418800017407L),
        new Input("CircleSegment.epa2", -4621644133008675367L, -4617140533381304871L, 4607182418800017407L),
        new Input("CircleSlice.epa35", 4606804953716818183L, 4598831979030654181L, 4607182418800017407L),
        new Input("PolygonCapsule.sat1", -4624133661653997234L, 4606741575090066687L, 4607182418800017407L),
        new Input("PolygonCapsule.sat4", 4605462196814083239L, -4619902518423102882L, 4607182418800017407L)
    };

    private static void equal(String id, long expected, double actual) {
        long bits = Double.doubleToRawLongBits(actual);
        if (bits != expected) throw new AssertionError(id + " expected=" + expected + " actual=" + bits);
    }

    private static void checkInput(Input input) {
        double x = Double.longBitsToDouble(input.xBits());
        double y = Double.longBitsToDouble(input.yBits());
        double squared = x * x + y * y;
        double baseline = StrictMath.sqrt(squared);
        equal(input.id() + ".oracle", input.expectedRootBits(), baseline);
        equal(input.id() + ".corrected", input.expectedRootBits(), NearestSqrtPlatformKt.nearestSqrt(squared));
        equal(input.id() + ".forcedUp", input.expectedRootBits(),
            NearestSqrtKt.nearestSqrtFromCandidate(squared, Double.longBitsToDouble(input.expectedRootBits() + 1)));
        equal(input.id() + ".forcedDown", input.expectedRootBits(),
            NearestSqrtKt.nearestSqrtFromCandidate(squared, Double.longBitsToDouble(input.expectedRootBits() - 1)));
        Vector2 vector = new Vector2(x, y);
        equal(input.id() + ".magnitude", input.expectedRootBits(), vector.getMagnitude());
        equal(input.id() + ".distance", input.expectedRootBits(), new Vector2().distance(vector));
        equal(input.id() + ".normalize", input.expectedRootBits(), vector.normalize());
        double forcedUp = Double.longBitsToDouble(input.expectedRootBits() + 1);
        System.out.printf("input\t%s\t%d\t%d\t%d\t%d\t%d%n", input.id(),
            Double.doubleToRawLongBits(squared), Double.doubleToRawLongBits(baseline),
            Double.doubleToRawLongBits(forcedUp),
            Double.doubleToRawLongBits(NearestSqrtKt.nearestSqrtFromCandidate(squared, forcedUp)),
            Double.doubleToRawLongBits(NearestSqrtPlatformKt.nearestSqrt(squared)));
    }

    public static void main(String[] args) {
        for (Input input : INPUTS) checkInput(input);
        long[] centers = {4598175219545276415L, 4607182418800017407L};
        for (int center = 0; center < centers.length; center++) {
            for (long offset = -4; offset <= 4; offset++) {
                long bits = centers[center] + offset;
                double value = Double.longBitsToDouble(bits);
                long expected = Double.doubleToRawLongBits(StrictMath.sqrt(value));
                equal("neighbor." + center + "." + offset, expected, NearestSqrtPlatformKt.nearestSqrt(value));
                equal("neighborUp." + center + "." + offset, expected,
                    NearestSqrtKt.nearestSqrtFromCandidate(value, Double.longBitsToDouble(expected + 1)));
                equal("neighborDown." + center + "." + offset, expected,
                    NearestSqrtKt.nearestSqrtFromCandidate(value, Double.longBitsToDouble(expected - 1)));
                System.out.printf("neighbor\t%d\t%d\t%d\t%d%n", center, offset, bits, expected);
            }
        }
        long[] positiveEdges = {1L, 2L, 0x000fffffffffffffL, 0x0010000000000000L,
            0x3fd0000000000000L, 0x3ff0000000000000L, 0x7fefffffffffffffL};
        for (long bits : positiveEdges) {
            double value = Double.longBitsToDouble(bits);
            long expected = Double.doubleToRawLongBits(StrictMath.sqrt(value));
            equal("edge." + bits, expected, NearestSqrtPlatformKt.nearestSqrt(value));
            System.out.printf("edge\t%d\t%d%n", bits, expected);
        }
        for (long bits : centers) {
            double value = Double.longBitsToDouble(bits);
            long expected = Double.doubleToRawLongBits(StrictMath.sqrt(value));
            equal("fallbackZero." + bits, expected, NearestSqrtKt.nearestSqrtFromCandidate(value, 0.0));
            equal("fallbackInfinity." + bits, expected,
                NearestSqrtKt.nearestSqrtFromCandidate(value, Double.POSITIVE_INFINITY));
            equal("fallbackFar." + bits, expected,
                NearestSqrtKt.nearestSqrtFromCandidate(value, Double.longBitsToDouble(expected + 6)));
        }
        equal("positiveZero", 0L, NearestSqrtPlatformKt.nearestSqrt(0.0));
        equal("negativeZero", Long.MIN_VALUE, NearestSqrtPlatformKt.nearestSqrt(-0.0));
        equal("positiveInfinity", 0x7ff0000000000000L,
            NearestSqrtPlatformKt.nearestSqrt(Double.POSITIVE_INFINITY));
        if (!Double.isNaN(NearestSqrtPlatformKt.nearestSqrt(Double.NaN)) ||
            !Double.isNaN(NearestSqrtPlatformKt.nearestSqrt(-1.0)) ||
            !Double.isNaN(NearestSqrtPlatformKt.nearestSqrt(Double.NEGATIVE_INFINITY))) {
            throw new AssertionError("NaN and negative inputs");
        }
        long state = 0x1d0f5eed12345678L;
        for (int index = 0; index < 10000; index++) {
            state ^= state << 13;
            state ^= state >>> 7;
            state ^= state << 17;
            long bits = state & 0x7fefffffffffffffL;
            if (bits == 0L) bits = 1L;
            double value = Double.longBitsToDouble(bits);
            long expected = Double.doubleToRawLongBits(StrictMath.sqrt(value));
            equal("random." + index, expected, NearestSqrtPlatformKt.nearestSqrt(value));
            equal("randomUp." + index, expected,
                NearestSqrtKt.nearestSqrtFromCandidate(value, Double.longBitsToDouble(expected + 1)));
            equal("randomDown." + index, expected,
                NearestSqrtKt.nearestSqrtFromCandidate(value, Double.longBitsToDouble(expected - 1)));
        }
        System.out.println("PASS inputs=7 neighbors=18 edges=7 specials=6 random=10000 fallback=6 forcedDirections=both");
        if (args.length == 1 && args[0].equals("--bench")) benchmark();
    }

    private static void benchmark() {
        double[] values = new double[4096];
        for (int index = 0; index < values.length; index++) {
            values[index] = 0.25 + index / 4096.0;
        }
        for (int round = 0; round < 5; round++) {
            double sum = 0.0;
            long start = System.nanoTime();
            for (int index = 0; index < 1_000_000; index++) {
                sum += StrictMath.sqrt(values[index & 4095]);
            }
            long strictNanos = System.nanoTime() - start;
            sink = sum;
            sum = 0.0;
            start = System.nanoTime();
            for (int index = 0; index < 1_000_000; index++) {
                sum += NearestSqrtPlatformKt.nearestSqrt(values[index & 4095]);
            }
            long correctedNanos = System.nanoTime() - start;
            sink = sum;
            System.out.printf("bench\t%d\t%d\t%d%n", round, strictNanos, correctedNanos);
        }
    }
}
