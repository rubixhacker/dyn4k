import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import org.dyn4j.geometry.AABB;
import org.dyn4j.geometry.Capsule;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Ellipse;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.HalfEllipse;
import org.dyn4j.geometry.Interval;
import org.dyn4j.geometry.Link;
import org.dyn4j.geometry.Mass;
import org.dyn4j.geometry.Polygon;
import org.dyn4j.geometry.Ray;
import org.dyn4j.geometry.Rectangle;
import org.dyn4j.geometry.RobustGeometry;
import org.dyn4j.geometry.Segment;
import org.dyn4j.geometry.Shape;
import org.dyn4j.geometry.Slice;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Triangle;
import org.dyn4j.geometry.Vector2;

public final class GeometryConsumer {
    public static void main(String[] args) {
        AABB bounds = new AABB(-2.0, -1.0, 2.0, 1.0);
        if (!bounds.contains(new Vector2(2.0, 1.0)) || bounds.copy() == bounds)
            throw new AssertionError("AABB identity or containment");
        Interval interval = new Interval(-1.0, 2.0);
        if (!interval.includesInclusive(2.0) || interval.includesExclusive(2.0))
            throw new AssertionError("Interval boundary");
        Ray ray = new Ray(new Vector2(1.0, 2.0), new Vector2(3.0, 4.0));
        if (ray.getStart() != ray.getStart() || ray.copy().getStart() == ray.getStart())
            throw new AssertionError("Ray identity");
        Mass mass = new Mass(new Vector2(0.0, 1.0), 2.0, 3.0);
        if (mass.getCenter() != mass.getCenter() || mass.copy().getCenter() == mass.getCenter())
            throw new AssertionError("Mass identity");
        Circle circle = Geometry.createCircle(2.0);
        Capsule capsule = Geometry.createCapsule(4.0, 2.0);
        Ellipse ellipse = Geometry.createEllipse(4.0, 2.0);
        HalfEllipse halfEllipse = Geometry.createHalfEllipse(4.0, 2.0);
        Slice slice = Geometry.createSlice(2.0, Math.PI / 2.0);
        Shape[] curved = { circle, capsule, ellipse, halfEllipse, slice };
        for (Shape shape : curved) {
            if (!shape.contains(shape.getCenter()) || shape.copy() == shape)
                throw new AssertionError("Curved shape query or copy: " + shape.getClass());
            if (shape.createAABB().getWidth() <= 0.0)
                throw new AssertionError("Curved AABB: " + shape.getClass());
            Convex convex = (Convex) shape;
            if (convex.getFarthestPoint(new Vector2(1.0, 0.0), new Transform()) == null)
                throw new AssertionError("Curved support point: " + shape.getClass());
        }
        Polygon polygon = Geometry.createSquare(2.0);
        Vector2[] vertices = polygon.getVertices();
        if (vertices != polygon.getVertices() || polygon.copy().getVertices()[0] == vertices[0])
            throw new AssertionError("Polygon live array or copy");
        Rectangle rectangle = Geometry.createRectangle(4.0, 2.0);
        Triangle triangle = Geometry.createRightTriangle(2.0, 2.0);
        Segment segment = Geometry.createSegment(new Vector2(-1.0, 0.0), new Vector2(1.0, 0.0));
        Link link = Geometry.createLinks(Arrays.asList(new Vector2(-1.0, 0.0), new Vector2(1.0, 0.0)), false).get(0);
        if (rectangle.getArea() != 8.0 || triangle.getArea() != 2.0 || segment.getLength() != 2.0 || link.getPoint0() != null)
            throw new AssertionError("Straight shape factory");
        if (Geometry.getWinding(vertices) <= 0.0 || Geometry.getWinding(Arrays.asList(vertices)) <= 0.0)
            throw new AssertionError("Winding overloads");
        List<Vector2> immutableEmpty = Collections.emptyList();
        if (Geometry.cleanse(immutableEmpty) != immutableEmpty)
            throw new AssertionError("Immutable empty list identity");
        List<Vector2> mutableEmpty = new ArrayList<>();
        if (Geometry.cleanse(mutableEmpty) != mutableEmpty)
            throw new AssertionError("Mutable empty list identity");
        Vector2[] emptyArray = new Vector2[0];
        Vector2[] cleansedEmptyArray = Geometry.cleanse(emptyArray);
        if (cleansedEmptyArray == emptyArray || cleansedEmptyArray.length != 0)
            throw new AssertionError("Empty vararg array copy");
        Vector2 first = new Vector2(0.0, 0.0);
        List<Vector2> nonempty = Arrays.asList(first, new Vector2(1.0, 0.0), new Vector2(0.0, 1.0));
        List<Vector2> cleansed = Geometry.cleanse(nonempty);
        cleansed.add(new Vector2(2.0, 2.0));
        if (cleansed == nonempty || cleansed.size() != 4 || nonempty.size() != 3 || cleansed.get(0) != first)
            throw new AssertionError("Nonempty list copy, mutability, or point identity");
        try {
            Geometry.cleanse((List<Vector2>) null);
            throw new AssertionError("Null list exception missing");
        } catch (org.dyn4j.exception.ArgumentNullException expected) {
            if (!"points cannot be null".equals(expected.getMessage()))
                throw new AssertionError("Null list exception message", expected);
        }
        try {
            Geometry.cleanse(Arrays.asList(new Vector2(), null, new Vector2()));
            throw new AssertionError("Null element exception missing");
        } catch (org.dyn4j.exception.NullElementException expected) {
            if (!"points contains a null element at index 1".equals(expected.getMessage()))
                throw new AssertionError("Null element exception message", expected);
        }
        if (Geometry.getRotationRadius((Vector2[]) null) != 0.0 || Geometry.getCounterClockwiseEdgeNormals((Vector2[]) null) != null)
            throw new AssertionError("Nullable radius and normals");
        if (Geometry.getRotationRadius(new Vector2(), new Vector2[] {new Vector2(1.0, 0.0), new Vector2(0.0, 2.0)}) != 2.0)
            throw new AssertionError("Varargs radius");
        if (Geometry.createPolygonalEllipse(6, 4.0, 2.0).getVertices().length != 6 ||
            Geometry.createPolygonalCapsule(2, 4.0, 2.0).getVertices().length != 8)
            throw new AssertionError("Polygonal factories");
        if (Geometry.minkowskiSum(polygon, circle, 2).getVertices().length != 16)
            throw new AssertionError("Minkowski rounding");
        if (Geometry.scale(circle, 2.0).getRadius() != 4.0)
            throw new AssertionError("Scale");
        Polygon inner = Geometry.createSquare(1.0);
        if (Geometry.getIntersection(polygon, new Transform(), inner, new Transform()) != inner)
            throw new AssertionError("Intersection");
        if (RobustGeometry.getLocation(new Vector2(0.0, 1.0), new Vector2(), new Vector2(1.0, 0.0)) == 0.0)
            throw new AssertionError("Robust side");
        try {
            new AABB(1.0, 0.0, 0.0, 1.0);
            throw new AssertionError("AABB range exception missing");
        } catch (org.dyn4j.exception.ValueOutOfRangeException expected) {
            if (!expected.getMessage().contains("minX must be less than or equal to maxX"))
                throw new AssertionError("AABB range exception message", expected);
        }
        for (double value : new double[] {Double.MIN_VALUE, 1.0e-7, 5.0e-7, 1.2345675, 1.0e20, Double.MAX_VALUE, -0.0}) {
            String range = new org.dyn4j.exception.ValueOutOfRangeException("radius", value).getMessage();
            if (!range.equals(String.format("radius cannot be %f", value)))
                throw new AssertionError("Range exception number: " + range);
        }
        org.dyn4j.geometry.GeometryPackageConsumer.run();
        System.out.println("GeometryConsumer: 25 checks passed");
    }
}
