package org.dyn4j.geometry.simplify;

public final class AddedNodeAccessor extends SegmentTreeNode {
    public String getLeft() {
        return "existing consumer method";
    }

    public static void main(String[] args) {
        if (!"existing consumer method".equals(new AddedNodeAccessor().getLeft())) {
            throw new AssertionError();
        }
    }
}
