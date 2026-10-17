import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Scanner;

import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Polygon;
import org.dyn4j.geometry.Triangle;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.geometry.decompose.Bayazit;
import org.dyn4j.geometry.decompose.Decomposer;
import org.dyn4j.geometry.decompose.EarClipping;
import org.dyn4j.geometry.decompose.SweepLine;
import org.dyn4j.geometry.decompose.Triangulator;
import org.dyn4j.geometry.hull.DivideAndConquer;
import org.dyn4j.geometry.hull.GiftWrap;
import org.dyn4j.geometry.hull.GrahamScan;
import org.dyn4j.geometry.hull.HullGenerator;
import org.dyn4j.geometry.hull.MonotoneChain;
import org.dyn4j.geometry.simplify.DouglasPeucker;
import org.dyn4j.geometry.simplify.Simplifier;
import org.dyn4j.geometry.simplify.VertexClusterReduction;
import org.dyn4j.geometry.simplify.Visvalingam;

public final class PolygonAlgorithmConsumer {
    private static final class CustomMonotoneChain extends MonotoneChain {
        @Override public Vector2[] generate(Vector2... points) { return super.generate(points); }
    }
    private static final class CustomGrahamScan extends GrahamScan {
        @Override public Vector2[] generate(Vector2... points) { return super.generate(points); }
    }
    private static final class CustomGiftWrap extends GiftWrap {
        @Override public Vector2[] generate(Vector2... points) { return super.generate(points); }
    }
    private static final class CustomDivideAndConquer extends DivideAndConquer {
        @Override public Vector2[] generate(Vector2... points) { return super.generate(points); }
    }

    private static int checks;

    public static void main(String[] args) {
        Vector2[] cloud = {
            new Vector2(1, 1), new Vector2(2, 0), new Vector2(0, 0),
            new Vector2(2, 2), new Vector2(0, 2), new Vector2(1, 1)
        };
        HullGenerator[] generators = {
            new CustomMonotoneChain(), new CustomGrahamScan(),
            new CustomGiftWrap(), new CustomDivideAndConquer()
        };
        for (HullGenerator generator : generators) {
            Vector2[] hull = generator.generate(cloud.clone());
            check(hull.length == 4, "hull vertex count");
            checkClose(new Polygon(hull).getArea(), 4.0, "hull area");
        }
        Vector2[][] shortClouds = {
            new Vector2[0], {null}, {new Vector2(0, 0), null}
        };
        for (HullGenerator generator : generators) {
            for (Vector2[] shortCloud : shortClouds) {
                check(generator.generate(shortCloud) == shortCloud, "short hull input identity");
            }
        }

        Vector2[] polygon = loadPolygon1();
        Decomposer[] decomposers = {new Bayazit(), new EarClipping(), new SweepLine()};
        for (Decomposer decomposer : decomposers) {
            List<Convex> pieces = decomposer.decompose(polygon.clone());
            check(pieces.size() > 1, "convex pieces");
            double area = 0.0;
            for (Convex piece : pieces) area += piece.getArea();
            checkClose(area, 1.41, "fixture area");
        }
        Vector2[] clockwise = clockwisePolygon();
        new Bayazit().decompose(clockwise);
        checkReversed(clockwise);
        for (Decomposer decomposer : new Decomposer[] {new EarClipping(), new SweepLine()}) {
            Vector2[] input = clockwisePolygon();
            decomposer.decompose(input);
            checkReversed(input);
        }
        for (Triangulator triangulator : new Triangulator[] {new EarClipping(), new SweepLine()}) {
            Vector2[] input = clockwisePolygon();
            triangulator.triangulate(input);
            checkReversed(input);
        }
        Triangulator[] triangulators = {new EarClipping(), new SweepLine()};
        for (Triangulator triangulator : triangulators) {
            List<Triangle> triangles = triangulator.triangulate(polygon.clone());
            check(triangles.size() == 15, "fixture triangulation count");
            double area = 0.0;
            for (Triangle triangle : triangles) area += triangle.getArea();
            checkClose(area, 1.41, "fixture triangulation area");
        }

        Vector2[] square = {
            new Vector2(0, 0), new Vector2(0.05, 0), new Vector2(2, 0),
            new Vector2(2, 2), new Vector2(0, 2)
        };
        Simplifier[] simplifiers = {
            new VertexClusterReduction(0.1), new DouglasPeucker(0.0, 0.1), new Visvalingam(0.0, 0.1)
        };
        for (Simplifier simplifier : simplifiers) {
            Vector2[] result = simplifier.simplify(square.clone());
            check(result.length == 4, "simplified vertex count");
            checkClose(new Polygon(result).getArea(), 4.0, "simplified area");
            check(simplifier.simplify((Vector2[]) null) == null, "null array behavior");
            List<Vector2> empty = new ArrayList<>();
            check(simplifier.simplify(empty) == empty, "empty list identity");
        }
        System.out.println("PolygonAlgorithmConsumer: " + checks + " checks passed");
    }

    private static Vector2[] loadPolygon1() {
        InputStream stream = PolygonAlgorithmConsumer.class.getResourceAsStream("/org/dyn4j/data/polygon1.dat");
        check(stream != null, "pinned fixture available");
        try (Scanner scanner = new Scanner(stream).useLocale(Locale.ROOT)) {
            int size = scanner.nextInt();
            check(size == 17, "pinned fixture size");
            Vector2[] points = new Vector2[size];
            for (int i = 0; i < size; i++) points[i] = new Vector2(scanner.nextDouble(), scanner.nextDouble());
            return points;
        }
    }

    private static Vector2[] clockwisePolygon() {
        return new Vector2[] {
            new Vector2(0, 2), new Vector2(1, 2), new Vector2(1, 1),
            new Vector2(2, 1), new Vector2(2, 0), new Vector2(0, 0)
        };
    }

    private static void checkReversed(Vector2[] polygon) {
        check(polygon[0].equals(new Vector2(0, 0)), "clockwise input first vertex");
        check(polygon[5].equals(new Vector2(0, 2)), "clockwise input last vertex");
    }

    private static void checkClose(double actual, double expected, String label) {
        check(Math.abs(actual - expected) <= 1e-12, label + ": " + actual);
    }

    private static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
        checks++;
    }
}
