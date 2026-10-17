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
    }

    private static final class ExposedAABB extends AABB {
        ExposedAABB(double minX, double minY, double maxX, double maxY) {
            super(minX, minY, maxX, maxY);
        }
        @Override public double getWidth() { return 7.0; }
    }
}
