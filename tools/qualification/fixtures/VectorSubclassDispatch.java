package qualification;

import org.dyn4j.geometry.Vector2;
import org.dyn4j.geometry.Vector3;

public final class VectorSubclassDispatch {
    private static final class Probe2 extends Vector2 {
        int scalarDistanceCalls;
        int scalarSquaredCalls;
        int magnitudeCalls;
        int zeroCalls;
        int zeroCheckCalls;

        Probe2() { super(3.0, 4.0); }

        @Override public double distance(double x, double y) {
            scalarDistanceCalls++;
            return 777.0;
        }

        @Override public double distanceSquared(double x, double y) {
            scalarSquaredCalls++;
            return 888.0;
        }

        @Override public double getMagnitude() {
            magnitudeCalls++;
            return 10.0;
        }

        @Override public Vector2 zero() {
            zeroCalls++;
            return this;
        }

        @Override public boolean isZero() {
            zeroCheckCalls++;
            return false;
        }
    }

    private static final class Probe3 extends Vector3 {
        int scalarDistanceCalls;
        int scalarSquaredCalls;
        int magnitudeCalls;
        int zeroCalls;
        int zeroCheckCalls;

        Probe3() { super(3.0, 4.0, 0.0); }

        @Override public double distance(double x, double y, double z) {
            scalarDistanceCalls++;
            return 777.0;
        }

        @Override public double distanceSquared(double x, double y, double z) {
            scalarSquaredCalls++;
            return 888.0;
        }

        @Override public double getMagnitude() {
            magnitudeCalls++;
            return 10.0;
        }

        @Override public Vector3 zero() {
            zeroCalls++;
            return this;
        }

        @Override public boolean isZero() {
            zeroCheckCalls++;
            return false;
        }
    }

    private static void require(boolean value, String reason) {
        if (!value) throw new AssertionError(reason);
    }

    private static void checkVector2Overloads() {
        final int[] mutationCalls = {0};
        Vector2 mutated = new Vector2(2.0, 3.0) {
            @Override public Vector2 set(double x, double y) {
                mutationCalls[0]++;
                return this;
            }
            @Override public Vector2 add(double x, double y) {
                mutationCalls[0]++;
                return this;
            }
            @Override public Vector2 subtract(double x, double y) {
                mutationCalls[0]++;
                return this;
            }
        };
        require(mutated.set(new Vector2(3.0, 4.0)) == mutated &&
                mutated.add(new Vector2(2.0, 1.0)) == mutated &&
                mutated.subtract(new Vector2(1.0, 2.0)) == mutated &&
                mutated.x == 4.0 && mutated.y == 3.0 && mutationCalls[0] == 0,
                "Vector2 object mutation dispatch");
        mutated.set(1.0, 1.0);
        mutated.add(1.0, 1.0);
        mutated.subtract(1.0, 1.0);
        require(mutationCalls[0] == 3, "Vector2 scalar mutation override");

        final int[] resultCalls = {0};
        Vector2 results = new Vector2(3.0, 4.0) {
            @Override public Vector2 sum(double x, double y) {
                resultCalls[0]++;
                return new Vector2(777.0, 777.0);
            }
            @Override public Vector2 difference(double x, double y) {
                resultCalls[0]++;
                return new Vector2(777.0, 777.0);
            }
            @Override public Vector2 to(double x, double y) {
                resultCalls[0]++;
                return new Vector2(777.0, 777.0);
            }
        };
        Vector2 sum = results.sum(new Vector2(2.0, 1.0));
        Vector2 difference = results.difference(new Vector2(2.0, 1.0));
        Vector2 to = results.to(new Vector2(2.0, 1.0));
        require(sum.x == 5.0 && sum.y == 5.0 && difference.x == 1.0 &&
                difference.y == 3.0 && to.x == -1.0 && to.y == -3.0 &&
                resultCalls[0] == 0, "Vector2 object result dispatch");
        results.sum(2.0, 1.0);
        results.difference(2.0, 1.0);
        results.to(2.0, 1.0);
        require(resultCalls[0] == 3, "Vector2 scalar result override");

        final int[] productCalls = {0};
        Vector2 products = new Vector2(3.0, 4.0) {
            @Override public double dot(double x, double y) {
                productCalls[0]++;
                return 777.0;
            }
            @Override public double cross(double x, double y) {
                productCalls[0]++;
                return 777.0;
            }
        };
        require(products.dot(new Vector2(3.0, 4.0)) == 25.0 &&
                products.cross(new Vector2(4.0, 3.0)) == -7.0 &&
                products.isOrthogonal(4.0, -3.0) && productCalls[0] == 0,
                "Vector2 object products and scalar orthogonality");
        products.dot(3.0, 4.0);
        products.cross(4.0, 3.0);
        require(productCalls[0] == 2, "Vector2 scalar product override");

        final int[] orthogonalCalls = {0};
        Vector2 orthogonal = new Vector2(3.0, 4.0) {
            @Override public boolean isOrthogonal(double x, double y) {
                orthogonalCalls[0]++;
                return false;
            }
        };
        require(orthogonal.isOrthogonal(new Vector2(4.0, -3.0)) &&
                !orthogonal.isOrthogonal(new Vector2(3.0, 4.0)) &&
                orthogonalCalls[0] == 0, "Vector2 object orthogonality");
        require(!orthogonal.isOrthogonal(4.0, -3.0) && orthogonalCalls[0] == 1,
                "Vector2 scalar orthogonality override");

        final int[] equalityCalls = {0};
        Vector2 equal = new Vector2(3.0, 4.0) {
            @Override public boolean equals(double x, double y, double epsilon) {
                equalityCalls[0]++;
                return false;
            }
        };
        require(equal.equals(new Vector2(3.0, 4.0), 0.0) &&
                !equal.equals(new Vector2(3.0, 5.0), 0.0) &&
                !equal.equals((Vector2) null, 0.0) && equal.equals(equal, 0.0) &&
                equalityCalls[0] == 0, "Vector2 object tolerance equality");
        require(!equal.equals(3.0, 4.0, 0.0) && equalityCalls[0] == 1,
                "Vector2 scalar tolerance override");

        final int[] rotationCalls = {0};
        Vector2 routed = new Vector2(3.0, 4.0) {
            @Override public Vector2 rotate(double theta, double x, double y) {
                rotationCalls[0]++;
                return this;
            }
            @Override public double dot(Vector2 vector) { return 10.0; }
        };
        Vector2 projected = routed.project(new Vector2(2.0, 0.0));
        require(routed.rotate(1.0, new Vector2(2.0, 0.0)) == routed &&
                rotationCalls[0] == 1 && projected.x == 5.0 && projected.y == 0.0,
                "Vector2 intentional virtual rotation and projection");
    }

    private static void checkVector3Overloads() {
        final int[] squaredCalls = {0};
        Vector3 scalarDistance = new Vector3() {
            @Override public double distanceSquared(double x, double y, double z) {
                squaredCalls[0]++;
                return 777.0;
            }
        };
        require(scalarDistance.distance(3.0, 4.0, 0.0) == 5.0 &&
                squaredCalls[0] == 0, "Vector3 direct scalar distance");
        scalarDistance.distanceSquared(3.0, 4.0, 0.0);
        require(squaredCalls[0] == 1, "Vector3 squared distance override");

        final int[] mutationCalls = {0};
        Vector3 mutated = new Vector3(2.0, 3.0, 4.0) {
            @Override public Vector3 set(double x, double y, double z) {
                mutationCalls[0]++;
                return this;
            }
            @Override public Vector3 add(double x, double y, double z) {
                mutationCalls[0]++;
                return this;
            }
            @Override public Vector3 subtract(double x, double y, double z) {
                mutationCalls[0]++;
                return this;
            }
        };
        require(mutated.set(new Vector3(3.0, 4.0, 5.0)) == mutated &&
                mutated.add(new Vector3(2.0, 1.0, 3.0)) == mutated &&
                mutated.subtract(new Vector3(1.0, 2.0, 3.0)) == mutated &&
                mutated.x == 4.0 && mutated.y == 3.0 && mutated.z == 5.0 &&
                mutationCalls[0] == 0, "Vector3 object mutation dispatch");
        mutated.set(1.0, 1.0, 1.0);
        mutated.add(1.0, 1.0, 1.0);
        mutated.subtract(1.0, 1.0, 1.0);
        require(mutationCalls[0] == 3, "Vector3 scalar mutation override");

        final int[] resultCalls = {0};
        Vector3 results = new Vector3(3.0, 4.0, 5.0) {
            @Override public Vector3 sum(double x, double y, double z) {
                resultCalls[0]++;
                return new Vector3(777.0, 777.0, 777.0);
            }
            @Override public Vector3 difference(double x, double y, double z) {
                resultCalls[0]++;
                return new Vector3(777.0, 777.0, 777.0);
            }
            @Override public Vector3 to(double x, double y, double z) {
                resultCalls[0]++;
                return new Vector3(777.0, 777.0, 777.0);
            }
        };
        Vector3 sum = results.sum(new Vector3(2.0, 1.0, 3.0));
        Vector3 difference = results.difference(new Vector3(2.0, 1.0, 3.0));
        Vector3 to = results.to(new Vector3(2.0, 1.0, 3.0));
        require(sum.x == 5.0 && sum.y == 5.0 && sum.z == 8.0 &&
                difference.x == 1.0 && difference.y == 3.0 && difference.z == 2.0 &&
                to.x == -1.0 && to.y == -3.0 && to.z == -2.0 &&
                resultCalls[0] == 0, "Vector3 object result dispatch");
        results.sum(2.0, 1.0, 3.0);
        results.difference(2.0, 1.0, 3.0);
        results.to(2.0, 1.0, 3.0);
        require(resultCalls[0] == 3, "Vector3 scalar result override");

        final int[] productCalls = {0};
        Vector3 products = new Vector3(1.0, 2.0, 3.0) {
            @Override public double dot(double x, double y, double z) {
                productCalls[0]++;
                return 777.0;
            }
            @Override public Vector3 cross(double x, double y, double z) {
                productCalls[0]++;
                return new Vector3(777.0, 777.0, 777.0);
            }
        };
        Vector3 cross = products.cross(new Vector3(4.0, 5.0, 6.0));
        require(products.dot(new Vector3(4.0, 5.0, 6.0)) == 32.0 &&
                cross.x == -3.0 && cross.y == 6.0 && cross.z == -3.0 &&
                products.isOrthogonal(2.0, -1.0, 0.0) && productCalls[0] == 0,
                "Vector3 object products and scalar orthogonality");
        products.dot(4.0, 5.0, 6.0);
        products.cross(4.0, 5.0, 6.0);
        require(productCalls[0] == 2, "Vector3 scalar product override");

        final int[] orthogonalCalls = {0};
        Vector3 orthogonal = new Vector3(1.0, 2.0, 3.0) {
            @Override public boolean isOrthogonal(double x, double y, double z) {
                orthogonalCalls[0]++;
                return false;
            }
        };
        require(orthogonal.isOrthogonal(new Vector3(2.0, -1.0, 0.0)) &&
                !orthogonal.isOrthogonal(new Vector3(1.0, 2.0, 3.0)) &&
                orthogonalCalls[0] == 0, "Vector3 object orthogonality");
        require(!orthogonal.isOrthogonal(2.0, -1.0, 0.0) && orthogonalCalls[0] == 1,
                "Vector3 scalar orthogonality override");

        final int[] equalityCalls = {0};
        Vector3 equal = new Vector3(3.0, 4.0, 5.0) {
            @Override public boolean equals(double x, double y, double z,
                                            double epsilon) {
                equalityCalls[0]++;
                return false;
            }
        };
        require(equal.equals(new Vector3(3.0, 4.0, 5.0), 0.0) &&
                !equal.equals(new Vector3(3.0, 4.0, 6.0), 0.0) &&
                !equal.equals((Vector3) null, 0.0) && equal.equals(equal, 0.0) &&
                equalityCalls[0] == 0, "Vector3 object tolerance equality");
        require(!equal.equals(3.0, 4.0, 5.0, 0.0) && equalityCalls[0] == 1,
                "Vector3 scalar tolerance override");

        Vector3 projected = new Vector3(3.0, 4.0, 5.0) {
            @Override public double dot(Vector3 vector) { return 10.0; }
        }.project(new Vector3(2.0, 0.0, 0.0));
        require(projected.x == 5.0 && projected.y == 0.0 && projected.z == 0.0,
                "Vector3 intentional virtual projection");
    }

    public static void main(String[] args) {
        checkVector2Overloads();
        checkVector3Overloads();
        Probe2 two = new Probe2();
        require(two.distance(new Vector2()) == 5.0, "Vector2 object distance");
        require(two.distanceSquared(new Vector2()) == 25.0, "Vector2 object squared distance");
        require(two.scalarDistanceCalls == 0 && two.scalarSquaredCalls == 0,
                "Vector2 object overload dispatch");
        Vector2 normalizedTwo = two.getNormalized();
        require(Double.doubleToLongBits(normalizedTwo.x) ==
                Double.doubleToLongBits(3.0 * (1.0 / 10.0)), "Vector2 normalized x");
        require(Double.doubleToLongBits(normalizedTwo.y) ==
                Double.doubleToLongBits(4.0 * (1.0 / 10.0)), "Vector2 normalized y");
        require(two.magnitudeCalls == 1, "Vector2 intentional magnitude dispatch");

        Probe2 scaledTwo = new Probe2();
        scaledTwo.setMagnitude(10.0);
        require(scaledTwo.x == 6.0 && scaledTwo.y == 8.0,
                "Vector2 direct magnitude");
        require(scaledTwo.magnitudeCalls == 0 && scaledTwo.zeroCheckCalls == 1,
                "Vector2 magnitude dispatch");
        Probe2 directedTwo = new Probe2();
        directedTwo.setDirection(0.0);
        require(directedTwo.x == 5.0 && directedTwo.y == 0.0 &&
                directedTwo.magnitudeCalls == 0, "Vector2 direction dispatch");
        Probe2 zeroTwo = new Probe2();
        zeroTwo.setMagnitude(0.0);
        require(zeroTwo.x == 0.0 && zeroTwo.y == 0.0 && zeroTwo.zeroCalls == 0,
                "Vector2 direct zero fields");

        Probe3 three = new Probe3();
        require(three.distance(new Vector3()) == 5.0, "Vector3 object distance");
        require(three.distanceSquared(new Vector3()) == 25.0,
                "Vector3 object squared distance");
        require(three.scalarDistanceCalls == 0 && three.scalarSquaredCalls == 0,
                "Vector3 object overload dispatch");
        Vector3 normalizedThree = three.getNormalized();
        require(Double.doubleToLongBits(normalizedThree.x) ==
                Double.doubleToLongBits(3.0 * (1.0 / 5.0)), "Vector3 normalized x");
        require(Double.doubleToLongBits(normalizedThree.y) ==
                Double.doubleToLongBits(4.0 * (1.0 / 5.0)), "Vector3 normalized y");
        require(three.magnitudeCalls == 0, "Vector3 normalized dispatch");

        Probe3 normalThree = new Probe3();
        require(normalThree.normalize() == 5.0, "Vector3 original magnitude");
        require(Double.doubleToLongBits(normalThree.x) ==
                Double.doubleToLongBits(3.0 * (1.0 / 5.0)), "Vector3 normalized field x");
        require(Double.doubleToLongBits(normalThree.y) ==
                Double.doubleToLongBits(4.0 * (1.0 / 5.0)), "Vector3 normalized field y");
        require(normalThree.magnitudeCalls == 0, "Vector3 direct normalize");
        final int[] zeroMagnitudeCalls = {0};
        Vector3 zeroNormalization = new Vector3() {
            @Override public double getMagnitude() {
                zeroMagnitudeCalls[0]++;
                return 10.0;
            }
        };
        Vector3 normalizedZero = zeroNormalization.getNormalized();
        require(normalizedZero != zeroNormalization && normalizedZero.equals(new Vector3()) &&
                zeroNormalization.normalize() == 0.0 &&
                new Vector3(zeroNormalization).equals(new Vector3()) &&
                zeroMagnitudeCalls[0] == 0, "Vector3 zero normalization dispatch");
        Probe3 scaledThree = new Probe3();
        scaledThree.setMagnitude(10.0);
        require(scaledThree.x == 6.0 && scaledThree.y == 8.0 &&
                scaledThree.magnitudeCalls == 0 && scaledThree.zeroCheckCalls == 1,
                "Vector3 direct magnitude");
        Probe3 zeroThree = new Probe3();
        zeroThree.setMagnitude(0.0);
        require(zeroThree.x == 0.0 && zeroThree.y == 0.0 && zeroThree.z == 0.0 &&
                zeroThree.zeroCalls == 0, "Vector3 direct zero fields");

        System.out.println("vector subclass dispatch passed");
    }
}
