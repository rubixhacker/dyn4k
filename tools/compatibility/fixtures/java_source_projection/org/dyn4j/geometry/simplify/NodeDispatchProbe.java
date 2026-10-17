package org.dyn4j.geometry.simplify;

import org.dyn4j.geometry.Vector2;

public final class NodeDispatchProbe extends VertexClusterReduction {
    public NodeDispatchProbe() {
        super(0.01);
    }

    private static final class VertexHelper extends SimplePolygonVertex {
        VertexHelper() {
            super(0, new Vector2(1.0, 2.0));
        }

        public Vector2 getPoint() {
            return new Vector2(99.0, 99.0);
        }
    }

    public static void main(String[] args) {
        VertexHelper vertex = new VertexHelper();
        vertex.next = vertex;
        vertex.prev = vertex;
        Vector2 result = new NodeDispatchProbe().buildResult(vertex).get(0);
        System.out.println(result);
        if (result.x != 1.0 || result.y != 2.0) {
            throw new AssertionError("Stored vertex changed through a legacy helper method");
        }
    }
}
