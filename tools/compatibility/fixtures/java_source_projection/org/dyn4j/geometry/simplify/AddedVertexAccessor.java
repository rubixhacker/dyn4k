package org.dyn4j.geometry.simplify;

import org.dyn4j.geometry.Vector2;

public final class AddedVertexAccessor extends SimplePolygonVertex {
    public AddedVertexAccessor() {
        super(0, new Vector2());
    }

    public String getPoint() {
        return "existing consumer method";
    }

    public static void main(String[] args) {
        if (!"existing consumer method".equals(new AddedVertexAccessor().getPoint())) {
            throw new AssertionError();
        }
    }
}
