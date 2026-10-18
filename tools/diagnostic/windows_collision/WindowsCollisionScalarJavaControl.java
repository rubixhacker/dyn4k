package org.dyn4j.collision.narrowphase;

public final class WindowsCollisionScalarJavaControl {
    private static final Object[][] INPUTS = new Object[][] {
        {"CirclePolygon.edge3", -4621899953565315924L, -4625196817309499400L},
        {"CapsuleSlice.epa4", 4603460912955918154L, -4617903595553423057L},
        {"CirclePolygon.epa3", -4619490269450149183L, -4618227961596862473L},
        {"CircleSegment.epa2", -4621644133008675367L, -4617140533381304871L},
        {"CircleSlice.epa35", 4606804953716818183L, 4598831979030654181L},
        {"PolygonCapsule.sat1", -4624133661653997234L, 4606741575090066687L},
        {"PolygonCapsule.sat4", 4605462196814083239L, -4619902518423102882L}
    };

    private WindowsCollisionScalarJavaControl() {}

    private static String number(double value) {
        return Double.toString(value) + "@" + Long.toString(Double.doubleToRawLongBits(value));
    }

    public static void main(String[] args) {
        for (Object[] input : INPUTS) {
            double x = Double.longBitsToDouble((Long) input[1]);
            double y = Double.longBitsToDouble((Long) input[2]);
            double xx = x * x;
            double yy = y * y;
            double sum = xx + yy;
            double root = Math.sqrt(sum);
            double reciprocal = 1.0 / root;
            System.out.println("DYN4K_COLLISION_SCALAR\tv1\tprovider=java\tid=" + input[0]
                    + "\tx=" + number(x) + "\ty=" + number(y)
                    + "\txSquared=" + number(xx) + "\tySquared=" + number(yy)
                    + "\tsum=" + number(sum) + "\tsqrt=" + number(root)
                    + "\treciprocal=" + number(reciprocal)
                    + "\tnormalized=" + number(x * reciprocal) + "," + number(y * reciprocal));
        }
    }
}
