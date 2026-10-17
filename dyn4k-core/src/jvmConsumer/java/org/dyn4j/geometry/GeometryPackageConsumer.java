package org.dyn4j.geometry;

public final class GeometryPackageConsumer {
    public static void run() {
        AdaptiveDecimal decimal = AdaptiveDecimal.fromProduct(0.1, 0.2);
        if (!decimal.checkInvariants() || decimal.copy() == decimal)
            throw new AssertionError("AdaptiveDecimal");
        if (RobustGeometry.SPLITTER <= 1 || RobustGeometry.cross(1.0, 0.0, 0.0, 1.0).getEstimation() != 1.0)
            throw new AssertionError("Robust cross");
        Vector2[] vertices = { new Vector2(-1.0, -1.0), new Vector2(1.0, -1.0), new Vector2(1.0, 1.0), new Vector2(-1.0, 1.0) };
        Polygon polygon = new Polygon(new Vector2(), Math.sqrt(2.0), vertices, Geometry.getCounterClockwiseEdgeNormals(vertices));
        if (polygon.getFarthestVertexIndex(new Vector2(1.0, 0.0)) < 0)
            throw new AssertionError("Polygon package method");
        WoundIterator iterator = new WoundIterator(vertices);
        if (iterator.vectors != vertices || iterator.index != 0 || iterator.next() == vertices[0])
            throw new AssertionError("Wound iterator package fields or copies");
        if (Ellipse.getFarthestPointOnEllipse(2.0, 1.0, new Vector2()).getMagnitude() <= 0.0)
            throw new AssertionError("Ellipse package helper");
        if (new ExposedAABB(-1.0, -1.0, 1.0, 1.0).getWidth() != 7.0)
            throw new AssertionError("AABB virtual method");
        verifyShapeCopyExtensions();
    }

    private static void verifyShapeCopyExtensions() {
        GetterEllipse ellipse = new GetterEllipse();
        ellipse.translate(3.0, 4.0);
        Ellipse ellipseCopy = ellipse.copy();
        if (ellipse.calls != 0 || ellipseCopy.getHalfWidth() != 1.0 || ellipseCopy.getHalfHeight() != 2.0 ||
            ellipseCopy.getCenter() == ellipse.getCenter() || ellipseCopy.getCenter().x != 3.0)
            throw new AssertionError("Ellipse copy field state or getter dispatch");

        GetterHalfEllipse halfEllipse = new GetterHalfEllipse();
        HalfEllipse halfEllipseCopy = halfEllipse.copy();
        if (halfEllipse.calls != 0 || halfEllipseCopy.getHalfWidth() != 1.0 ||
            halfEllipseCopy.getCenter() == halfEllipse.getCenter())
            throw new AssertionError("HalfEllipse copy field state or getter dispatch");

        GetterSlice slice = new GetterSlice();
        Slice sliceCopy = slice.copy();
        if (slice.calls != 0 || sliceCopy.getTheta() != 0.7 || sliceCopy.getCenter() == slice.getCenter())
            throw new AssertionError("Slice copy field state or getter dispatch");

        CopyCapsule capsule = new CopyCapsule();
        CopyCapsule capsuleCopy = new CopyCapsule(capsule);
        Vector2 copiedFocus = capsuleCopy.firstFocus();
        if (!(copiedFocus instanceof TaggedVector) || copiedFocus.x != 11.0 || copiedFocus.y != 22.0 ||
            copiedFocus == capsule.firstFocus())
            throw new AssertionError("Capsule copy virtual focus dispatch");

        CopySlice vertexSlice = new CopySlice();
        CopySlice vertexSliceCopy = new CopySlice(vertexSlice);
        Vector2 copiedVertex = vertexSliceCopy.firstVertex();
        Vector2 copiedNormal = vertexSliceCopy.firstNormal();
        if (!(copiedVertex instanceof TaggedVector) || copiedVertex.x != 11.0 || copiedVertex.y != 22.0 ||
            !(copiedNormal instanceof TaggedVector) || copiedNormal.x != 13.0 || copiedNormal.y != 24.0 ||
            copiedVertex == vertexSlice.firstVertex())
            throw new AssertionError("Slice copy virtual vertex or normal dispatch");
    }

    private static final class GetterEllipse extends Ellipse {
        int calls;
        GetterEllipse() { super(2.0, 4.0); }
        @Override public double getWidth() { calls++; return 100.0; }
        @Override public double getHeight() { calls++; return 200.0; }
    }

    private static final class GetterHalfEllipse extends HalfEllipse {
        int calls;
        GetterHalfEllipse() { super(2.0, 4.0); }
        @Override public double getWidth() { calls++; return 100.0; }
    }

    private static final class GetterSlice extends Slice {
        int calls;
        GetterSlice() { super(2.0, 0.7); }
        @Override public double getTheta() { calls++; return 1.4; }
    }

    private static final class TaggedVector extends Vector2 {
        TaggedVector(double x, double y) { super(x, y); }
        @Override public Vector2 copy() { return new TaggedVector(x + 10.0, y + 20.0); }
    }

    private static final class CopyCapsule extends Capsule {
        CopyCapsule() { super(2.0, 4.0); foci[0] = new TaggedVector(1.0, 2.0); }
        CopyCapsule(Capsule source) { super(source); }
        Vector2 firstFocus() { return foci[0]; }
    }

    private static final class CopySlice extends Slice {
        CopySlice() {
            super(2.0, 0.7);
            vertices[0] = new TaggedVector(1.0, 2.0);
            normals[0] = new TaggedVector(3.0, 4.0);
        }
        CopySlice(Slice source) { super(source); }
        Vector2 firstVertex() { return vertices[0]; }
        Vector2 firstNormal() { return normals[0]; }
    }

    private static final class ExposedAABB extends AABB {
        ExposedAABB(double minX, double minY, double maxX, double maxY) {
            super(minX, minY, maxX, maxY);
        }
        @Override public double getWidth() { return 7.0; }
    }
}
