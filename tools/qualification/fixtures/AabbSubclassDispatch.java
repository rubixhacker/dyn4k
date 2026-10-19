import org.dyn4j.geometry.AABB;

public final class AabbSubclassDispatch {
    private static final class Dimensions extends AABB {
        Dimensions() { super(0.0, 0.0, 3.0, 4.0); }

        @Override public double getWidth() { return 100.0; }
        @Override public double getHeight() { return 200.0; }
    }

    private static class Zero extends AABB {
        int zeroCalls;

        Zero() { super(0.0, 0.0, 3.0, 4.0); }

        @Override public void zero() { zeroCalls++; }
    }

    private static final class PairIntersection extends Zero {
        int pairCalls;

        @Override public AABB intersection(AABB first, AABB second) {
            pairCalls++;
            return new AABB(90.0, 90.0, 99.0, 99.0);
        }
    }

    private static String bounds(AABB box) {
        return box.getMinX() + "," + box.getMinY() + "," + box.getMaxX() + "," + box.getMaxY();
    }

    public static void main(String[] args) {
        System.out.println("provider=" + AABB.class.getProtectionDomain().getCodeSource().getLocation());
        System.out.println("area=" + new Dimensions().getArea());
        System.out.println("perimeter=" + new Dimensions().getPerimeter());

        PairIntersection single = new PairIntersection();
        System.out.println("intersection=" + bounds(single.intersection(new AABB(1.0, 1.0, 5.0, 5.0)))
                + ",pairCalls=" + single.pairCalls + ",zeroCalls=" + single.zeroCalls);

        Zero disjointSingle = new Zero();
        System.out.println("zero_single=" + bounds(disjointSingle.intersection(
                new AABB(10.0, 10.0, 20.0, 20.0))) + ",zeroCalls=" + disjointSingle.zeroCalls);

        Zero disjointPair = new Zero();
        System.out.println("zero_pair=" + bounds(disjointPair.intersection(
                new AABB(0.0, 0.0, 3.0, 4.0), new AABB(10.0, 10.0, 20.0, 20.0)))
                + ",zeroCalls=" + disjointPair.zeroCalls);
    }
}
