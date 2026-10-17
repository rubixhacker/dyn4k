import java.io.InputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Scanner;

import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Polygon;
import org.dyn4j.geometry.Triangle;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.exception.ArgumentNullException;
import org.dyn4j.geometry.decompose.AbstractDecomposer;
import org.dyn4j.geometry.decompose.Bayazit;
import org.dyn4j.geometry.decompose.Decomposer;
import org.dyn4j.geometry.decompose.EarClipping;
import org.dyn4j.geometry.decompose.SweepLine;
import org.dyn4j.geometry.decompose.Triangulator;
import org.dyn4j.geometry.hull.DivideAndConquer;
import org.dyn4j.geometry.hull.AbstractHullGenerator;
import org.dyn4j.geometry.hull.GiftWrap;
import org.dyn4j.geometry.hull.GrahamScan;
import org.dyn4j.geometry.hull.HullGenerator;
import org.dyn4j.geometry.hull.MonotoneChain;
import org.dyn4j.geometry.simplify.DouglasPeucker;
import org.dyn4j.geometry.simplify.Simplifier;
import org.dyn4j.geometry.simplify.VertexClusterReduction;
import org.dyn4j.geometry.simplify.Visvalingam;

public final class PolygonAlgorithmConsumer {
    private static final class CustomHullGenerator implements HullGenerator {
        @Override public Vector2[] generate(Vector2... points) { return points; }
        @Override public List<Vector2> generate(List<Vector2> points) { return points; }
    }
    private static final class CustomAbstractHull extends AbstractHullGenerator {
        @Override public Vector2[] generate(Vector2... points) { return points; }
        @Override public List<Vector2> generate(List<Vector2> points) { return points; }
    }
    private static final class CustomDecomposer implements Decomposer {
        @Override public List<Convex> decompose(Vector2... points) { return new ArrayList<>(); }
        @Override public List<Convex> decompose(List<Vector2> points) { return new ArrayList<>(); }
    }
    private static final class CustomAbstractDecomposer extends AbstractDecomposer {
        @Override public List<Convex> decompose(Vector2... points) { return new ArrayList<>(); }
        @Override public List<Convex> decompose(List<Vector2> points) { return new ArrayList<>(); }
    }
    private static final class CustomSimplifier implements Simplifier {
        @Override public Vector2[] simplify(Vector2... points) { return points; }
        @Override public List<Vector2> simplify(List<Vector2> points) { return points; }
    }
    private static final class CustomBayazit extends Bayazit {
        private boolean called;
        @Override protected void decomposePolygon(List<Vector2> polygon, List<Convex> pieces) {
            called = true;
            super.decomposePolygon(polygon, pieces);
        }
    }
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

    public static void main(String[] args) throws Exception {
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
        List<Vector2> customPoints = new ArrayList<>();
        check(new CustomHullGenerator().generate(customPoints) == customPoints, "hull interface list override");
        check(new CustomAbstractHull().generate(customPoints) == customPoints, "abstract hull list override");
        check(new CustomDecomposer().decompose(customPoints).isEmpty(), "decomposer list override");
        check(new CustomAbstractDecomposer().decompose(customPoints).isEmpty(), "abstract decomposer list override");
        check(new CustomSimplifier().simplify(customPoints) == customPoints, "simplifier list override");
        for (HullGenerator generator : generators) {
            expectNullPoints(() -> generator.generate((Vector2[]) null));
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
        CustomBayazit customBayazit = new CustomBayazit();
        customBayazit.decompose(polygon.clone());
        check(customBayazit.called, "Bayazit protected list override dispatch");
        Decomposer[] decomposers = {new Bayazit(), new EarClipping(), new SweepLine()};
        for (Decomposer decomposer : decomposers) {
            expectNullPoints(() -> decomposer.decompose((Vector2[]) null));
        }
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
            expectNullPoints(() -> triangulator.triangulate((Vector2[]) null));
        }
        checkPackageNullPoints(EarClipping.class);
        checkPackageNullPoints(SweepLine.class);
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
            for (List<Vector2> input : Arrays.asList(
                new ArrayList<Vector2>(java.util.Collections.singletonList(null)),
                new ArrayList<>(java.util.Collections.singletonList(new Vector2(1, 2))))) {
                List<Vector2> output = simplifier.simplify(input);
                check(output instanceof ArrayList, "short simplifier result uses ArrayList");
                output.add(new Vector2(3, 4));
                check(output.size() == (input.get(0) == null ? 1 : 2), "short simplifier result is mutable");
            }
        }
        checkSupportInitialStates();
        System.out.println("PolygonAlgorithmConsumer: " + checks + " checks passed");
    }

    private static void expectNullPoints(Runnable action) {
        try {
            action.run();
            throw new AssertionError("null points must fail");
        } catch (ArgumentNullException expected) {
            check("points cannot be null".equals(expected.getMessage()), "null points diagnostic");
        }
    }

    private static void checkPackageNullPoints(Class<?> owner) throws Exception {
        Method method = owner.getDeclaredMethod("createTriangulation", Vector2[].class);
        method.setAccessible(true);
        try {
            method.invoke(owner.getDeclaredConstructor().newInstance(), (Object) null);
            throw new AssertionError("null points must fail in createTriangulation");
        } catch (InvocationTargetException expected) {
            check(expected.getCause() instanceof ArgumentNullException &&
                "points cannot be null".equals(expected.getCause().getMessage()),
                "package triangulation null array diagnostic");
        }
    }

    private static void checkSupportInitialStates() throws Exception {
        Class<?> linkedVertex = Class.forName("org.dyn4j.geometry.hull.LinkedVertex");
        Constructor<?> linkedConstructor = linkedVertex.getDeclaredConstructor(Vector2.class);
        linkedConstructor.setAccessible(true);
        Object vertex = linkedConstructor.newInstance(new Vector2());
        Field next = linkedVertex.getDeclaredField("next");
        Field prev = linkedVertex.getDeclaredField("prev");
        next.setAccessible(true);
        prev.setAccessible(true);
        check(next.get(vertex) == null && prev.get(vertex) == null, "unlinked hull vertex state");
        Class<?> hullType = Class.forName("org.dyn4j.geometry.hull.LinkedVertexHull");
        Constructor<?> hullConstructor = hullType.getDeclaredConstructor(Vector2.class);
        hullConstructor.setAccessible(true);
        Object onePointHull = hullConstructor.newInstance(new Vector2(5, 6));
        Method toArray = hullType.getDeclaredMethod("toArray");
        toArray.setAccessible(true);
        check(((Vector2[]) toArray.invoke(onePointHull)).length == 1, "unlinked single-point hull traversal");

        Class<?> faceType = Class.forName("org.dyn4j.geometry.decompose.DoubleEdgeListFace");
        Constructor<?> faceConstructor = faceType.getDeclaredConstructor();
        faceConstructor.setAccessible(true);
        check("Face[Edge=null]".equals(faceConstructor.newInstance().toString()), "unlinked face string");

        Class<?> monotoneType = Class.forName("org.dyn4j.geometry.decompose.MonotoneVertex");
        Constructor<?> monotoneConstructor = monotoneType.getDeclaredConstructor(Object.class);
        monotoneConstructor.setAccessible(true);
        Object first = monotoneConstructor.newInstance("a");
        Object second = monotoneConstructor.newInstance("b");
        Method isAdjacent = monotoneType.getDeclaredMethod("isAdjacent", monotoneType);
        isAdjacent.setAccessible(true);
        check(Boolean.FALSE.equals(isAdjacent.invoke(first, second)), "unlinked monotone vertices are not adjacent");

        Class<?> polygonVertexType = Class.forName("org.dyn4j.geometry.simplify.SimplePolygonVertex");
        Constructor<?> polygonVertexConstructor = polygonVertexType.getDeclaredConstructor(int.class, Vector2.class);
        polygonVertexConstructor.setAccessible(true);
        Object polygonVertex = polygonVertexConstructor.newInstance(2, new Vector2(1, 2));
        for (String link : new String[] {"next", "nextSegment", "prev", "prevSegment"}) {
            check(readPolygonVertexLink(polygonVertexType, polygonVertex, link) == null,
                "unlinked polygon vertex " + link);
        }
    }

    private static Object readPolygonVertexLink(Class<?> type, Object vertex, String link) throws Exception {
        try {
            Method getter = type.getDeclaredMethod("get" + Character.toUpperCase(link.charAt(0)) + link.substring(1));
            getter.setAccessible(true);
            return getter.invoke(vertex);
        } catch (NoSuchMethodException baselineField) {
            Field field = type.getDeclaredField(link);
            field.setAccessible(true);
            return field.get(vertex);
        }
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
