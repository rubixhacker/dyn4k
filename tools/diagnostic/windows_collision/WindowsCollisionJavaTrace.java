package org.dyn4j.collision.narrowphase;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.dyn4j.geometry.Capsule;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.EdgeFeature;
import org.dyn4j.geometry.Feature;
import org.dyn4j.geometry.Interval;
import org.dyn4j.geometry.PointFeature;
import org.dyn4j.geometry.Polygon;
import org.dyn4j.geometry.Rotation;
import org.dyn4j.geometry.Segment;
import org.dyn4j.geometry.Slice;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.geometry.Wound;

final class WindowsCollisionJavaTrace {
    private WindowsCollisionJavaTrace() {}

    static String number(double value) {
        return Double.toString(value) + "@" + Long.toString(Double.doubleToRawLongBits(value));
    }

    static String vector(Vector2 value) {
        return number(value.x) + "," + number(value.y);
    }

    static String vectors(Vector2[] values) {
        if (values == null) return "null";
        List<String> result = new ArrayList<String>();
        for (Vector2 value : values) result.add(vector(value));
        return join(result, ";");
    }

    static String values(double[] values) {
        List<String> result = new ArrayList<String>();
        for (double value : values) result.add(number(value));
        return join(result, ",");
    }

    static String polygonEdges(Convex shape) {
        if (!(shape instanceof Polygon)) return "na";
        Polygon polygon = (Polygon) shape;
        Vector2[] vertices = polygon.getVertices();
        Vector2[] normals = polygon.getNormals();
        List<String> result = new ArrayList<String>();
        for (int index = 0; index < vertices.length; index++) {
            Vector2 next = vertices[(index + 1) % vertices.length];
            double dx = next.x - vertices[index].x;
            double dy = next.y - vertices[index].y;
            double nx = dy;
            double ny = -dx;
            double xx = nx * nx;
            double yy = ny * ny;
            double sum = xx + yy;
            double root = Math.sqrt(sum);
            double reciprocal = 1.0 / root;
            Vector2 normalized = new Vector2(nx, ny);
            double returnedRoot = normalized.normalize();
            result.add(index + ":" + number(dx) + ":" + number(dy) + ":" + number(xx) + ":" + number(yy)
                    + ":" + number(sum) + ":" + number(root) + ":" + number(reciprocal)
                    + ":" + number(nx * reciprocal) + "," + number(ny * reciprocal)
                    + ":" + number(returnedRoot) + ":" + vector(normalized) + ":" + vector(normals[index]));
        }
        return join(result, ";");
    }

    static String shape(Convex shape) {
        List<String> parts = new ArrayList<String>();
        parts.add("kind=" + shape.getClass().getSimpleName());
        parts.add("center=" + vector(shape.getCenter()));
        parts.add("radius=" + number(shape.getRadius()));
        if (shape instanceof Circle) parts.add("circle.radius=" + number(shape.getRadius()));
        if (shape instanceof Capsule) {
            Capsule capsule = (Capsule) shape;
            Rotation rotation = capsule.getRotation();
            parts.add("capsule.length=" + number(capsule.getLength()));
            parts.add("capsule.capRadius=" + number(capsule.getCapRadius()));
            parts.add("capsule.localFoci=" + vectors(capsule.getFoci(new Transform())));
            parts.add("capsule.localAxis=" + number(rotation.getCost()) + "," + number(rotation.getSint()));
        }
        if (shape instanceof Slice) {
            Slice slice = (Slice) shape;
            parts.add("slice.radius=" + number(slice.getSliceRadius()));
            parts.add("slice.theta=" + number(slice.getTheta()));
            parts.add("slice.circleCenter=" + vector(slice.getCircleCenter()));
            Rotation rotation = slice.getRotation();
            parts.add("slice.rotation=" + number(rotation.getCost()) + "," + number(rotation.getSint()));
            parts.add("slice.upperEdge=" + feature(slice.getFarthestFeature(new Vector2(0.0, 1.0), new Transform())));
            parts.add("slice.lowerEdge=" + feature(slice.getFarthestFeature(new Vector2(0.0, -1.0), new Transform())));
        }
        if (shape instanceof Segment) parts.add("segment.length=" + number(((Segment) shape).getLength()));
        if (shape instanceof Wound) {
            Wound wound = (Wound) shape;
            parts.add("vertices=" + vectors(wound.getVertices()));
            parts.add("normals=" + vectors(wound.getNormals()));
        }
        return join(parts, "|");
    }

    static String feature(Feature feature) {
        if (feature instanceof PointFeature) {
            PointFeature point = (PointFeature) feature;
            return "point:" + point.getIndex() + ":" + vector(point.getPoint());
        }
        if (feature instanceof EdgeFeature) {
            EdgeFeature edge = (EdgeFeature) feature;
            return "edge:" + edge.getIndex() + ":" + edge.getVertex1().getIndex() + ":" + vector(edge.getVertex1().getPoint())
                    + ":" + edge.getVertex2().getIndex() + ":" + vector(edge.getVertex2().getPoint())
                    + ":" + edge.getMaximum().getIndex() + ":" + vector(edge.getMaximum().getPoint()) + ":" + vector(edge.getEdge());
        }
        return "unknown:" + feature.getIndex();
    }

    static List<String> pairInputs(Convex a, Transform ta, Convex b, Transform tb, Vector2 resultNormal) {
        Vector2[] fociA = a.getFoci(ta);
        Vector2[] fociB = b.getFoci(tb);
        Vector2[] axesA = a.getAxes(fociB, ta);
        Vector2[] axesB = b.getAxes(fociA, tb);
        Vector2 centerDirection = ta.getTransformed(a.getCenter()).to(tb.getTransformed(b.getCenter()));
        Vector2 initialDirection = centerDirection.isZero() ? new Vector2(1.0, 0.0) : centerDirection.copy();
        List<String> fields = new ArrayList<String>();
        fields.add("a.shape.local=" + shape(a));
        fields.add("b.shape.local=" + shape(b));
        fields.add("a.polygon.edgeArithmetic=" + polygonEdges(a));
        fields.add("b.polygon.edgeArithmetic=" + polygonEdges(b));
        fields.add("a.foci.world=" + vectors(fociA));
        fields.add("b.foci.world=" + vectors(fociB));
        fields.add("a.axes.withB=" + vectors(axesA));
        fields.add("b.axes.withA=" + vectors(axesB));
        fields.add("gjk.initial.centerDirection=" + vector(centerDirection));
        fields.add("gjk.initial.effectiveDirection=" + vector(initialDirection));
        fields.add("clip.probe.feature.a=" + (resultNormal == null ? "na" : feature(a.getFarthestFeature(resultNormal.copy(), ta))));
        fields.add("clip.probe.feature.b=" + (resultNormal == null ? "na" : feature(b.getFarthestFeature(resultNormal.getNegative(), tb))));
        Vector2[] directions = new Vector2[] {new Vector2(1.0, 0.0), new Vector2(-1.0, 0.0),
                new Vector2(0.0, 1.0), new Vector2(0.0, -1.0), initialDirection,
                resultNormal == null ? initialDirection.copy() : resultNormal.copy()};
        for (int i = 0; i < directions.length; i++) {
            Vector2 direction = directions[i];
            Vector2 supportA = a.getFarthestPoint(direction.copy(), ta);
            Vector2 supportB = b.getFarthestPoint(direction.getNegative(), tb);
            fields.add("support." + i + ".direction=" + vector(direction));
            fields.add("support." + i + ".a=" + vector(supportA));
            fields.add("support." + i + ".b.negated=" + vector(supportB));
            fields.add("support." + i + ".minkowski=" + vector(supportA.difference(supportB)));
        }
        return fields;
    }

    static List<String> sat(Convex a, Transform ta, Convex b, Transform tb, Penetration penetration, boolean productionHit) {
        Vector2[] fociA = a.getFoci(ta);
        Vector2[] fociB = b.getFoci(tb);
        Vector2[][] axisSets = new Vector2[][] {a.getAxes(fociB, ta), b.getAxes(fociA, tb)};
        List<String> candidates = new ArrayList<String>();
        Vector2 best = null;
        String bestSource = "na";
        int bestIndex = -1;
        double depth = Double.MAX_VALUE;
        for (int source = 0; source < axisSets.length; source++) {
            Vector2[] axes = axisSets[source];
            if (axes == null) continue;
            for (int index = 0; index < axes.length; index++) {
                Vector2 axis = axes[index];
                if (axis.isZero()) {
                    candidates.add(source + ":" + index + ":zero:" + vector(axis));
                    continue;
                }
                Vector2 rawAxis = axis.copy();
                Interval intervalA = a.project(axis, ta);
                Interval intervalB = b.project(axis, tb);
                if (!intervalA.overlaps(intervalB)) {
                    candidates.add(source + ":" + index + ":separated:" + vector(rawAxis) + ":" + interval(intervalA) + ":" + interval(intervalB));
                    List<String> fields = new ArrayList<String>();
                    fields.add("sat.replay.hit=false");
                    fields.add("sat.replay.matchesResult=" + !productionHit);
                    fields.add("sat.candidates=" + join(candidates, ";"));
                    fields.add("sat.winner.source=" + source);
                    fields.add("sat.winner.index=" + index);
                    return fields;
                }
                double rawOverlap = intervalA.getOverlap(intervalB);
                double adjustedOverlap = rawOverlap;
                boolean contained = intervalA.containsExclusive(intervalB) || intervalB.containsExclusive(intervalA);
                boolean containmentFlip = false;
                Double maxDifference = null;
                Double minDifference = null;
                if (contained) {
                    double max = Math.abs(intervalA.getMax() - intervalB.getMax());
                    double min = Math.abs(intervalA.getMin() - intervalB.getMin());
                    maxDifference = max;
                    minDifference = min;
                    if (max > min) { axis.negate(); adjustedOverlap += min; containmentFlip = true; }
                    else adjustedOverlap += max;
                }
                boolean selected = adjustedOverlap < depth;
                if (selected) {
                    depth = adjustedOverlap;
                    best = axis;
                    bestSource = source == 0 ? "a" : "b";
                    bestIndex = index;
                }
                candidates.add(source + ":" + index + ":" + vector(rawAxis) + ":" + interval(intervalA) + ":" + interval(intervalB)
                        + ":" + number(rawOverlap) + ":" + contained + ":" + containmentFlip + ":"
                        + (maxDifference == null ? "na" : number(maxDifference)) + ":"
                        + (minDifference == null ? "na" : number(minDifference)) + ":"
                        + number(adjustedOverlap) + ":" + vector(axis) + ":" + selected);
            }
        }
        Vector2 preOrientation = best.copy();
        double centerDot = ta.getTransformed(a.getCenter()).to(tb.getTransformed(b.getCenter())).dot(best);
        boolean orientationFlip = centerDot < 0.0;
        if (orientationFlip) best.negate();
        boolean matches = productionHit
                && Double.doubleToRawLongBits(best.x) == Double.doubleToRawLongBits(penetration.getNormal().x)
                && Double.doubleToRawLongBits(best.y) == Double.doubleToRawLongBits(penetration.getNormal().y)
                && Double.doubleToRawLongBits(depth) == Double.doubleToRawLongBits(penetration.getDepth());
        List<String> fields = new ArrayList<String>();
        fields.add("sat.replay.hit=true");
        fields.add("sat.replay.matchesResult=" + matches);
        fields.add("sat.candidates=" + join(candidates, ";"));
        fields.add("sat.winner.source=" + bestSource);
        fields.add("sat.winner.index=" + bestIndex);
        fields.add("sat.winner.preOrientation=" + vector(preOrientation));
        fields.add("sat.winner.centerDot=" + number(centerDot));
        fields.add("sat.winner.orientationFlip=" + orientationFlip);
        fields.add("sat.winner.finalAxis=" + vector(best));
        fields.add("sat.winner.depth=" + number(depth));
        return fields;
    }

    private static String interval(Interval value) {
        return number(value.getMin()) + "," + number(value.getMax());
    }

    private static String join(List<String> values, String delimiter) {
        StringBuilder result = new StringBuilder();
        for (String value : values) {
            if (result.length() != 0) result.append(delimiter);
            result.append(value);
        }
        return result.toString();
    }

    static final class RecordingEpa implements MinkowskiPenetrationSolver {
        private static final class MirrorEdge {
            final int id;
            final ExpandingSimplexEdge edge;

            MirrorEdge(int id, ExpandingSimplexEdge edge) {
                this.id = id;
                this.edge = edge;
            }
        }

        private final Epa delegate = new Epa();
        ExpandingSimplexEdge edge;
        private Vector2 support;
        private Double projection;
        private Double delta;
        private int iteration;
        private String stopReason = "notRun";
        private List<Vector2> simplexPoints = Collections.emptyList();
        private final List<String> iterationRecords = new ArrayList<String>();
        private boolean queueMirrorMatches = true;

        void reset() {
            edge = null;
            support = null;
            projection = null;
            delta = null;
            iteration = 0;
            stopReason = "notRun";
            simplexPoints = Collections.emptyList();
            iterationRecords.clear();
            queueMirrorMatches = true;
        }

        @Override public void getPenetration(List<Vector2> simplex, MinkowskiSum sum, Penetration penetration) {
            delegate.getPenetration(simplex, sum, penetration);
            simplexPoints = new ArrayList<Vector2>();
            for (Vector2 point : simplex) simplexPoints.add(point.copy());
            ExpandingSimplex expanding = new ExpandingSimplex(simplex);
            List<MirrorEdge> active = new ArrayList<MirrorEdge>();
            for (int i = 0; i < simplex.size(); i++) {
                active.add(new MirrorEdge(i, new ExpandingSimplexEdge(simplex.get(i), simplex.get((i + 1) % simplex.size()), expanding.getWinding())));
            }
            int nextEdgeId = simplex.size();
            for (int i = 0; i < delegate.getMaxIterations(); i++) {
                ExpandingSimplexEdge candidate = expanding.getClosestEdge();
                Vector2 normalBefore = candidate.normal.copy();
                int selectedIndex = -1;
                if (queueMirrorMatches && active.size() == expanding.size()) {
                    for (int j = 0; j < active.size(); j++) {
                        ExpandingSimplexEdge mirror = active.get(j).edge;
                        if (mirror.point1 == candidate.point1 && mirror.point2 == candidate.point2
                                && Double.doubleToRawLongBits(mirror.distance) == Double.doubleToRawLongBits(candidate.distance)) {
                            selectedIndex = j;
                            break;
                        }
                    }
                }
                if (selectedIndex < 0) queueMirrorMatches = false;
                List<String> equalIds = new ArrayList<String>();
                if (queueMirrorMatches) {
                    for (MirrorEdge mirror : active) {
                        if (mirror.edge.compareTo(candidate) == 0) equalIds.add(Integer.toString(mirror.id));
                    }
                }
                Vector2 point = sum.getSupportPoint(candidate.normal);
                edge = candidate;
                support = point;
                projection = point.dot(candidate.normal);
                delta = projection - candidate.distance;
                iteration = i + 1;
                String decision = delta < delegate.getDistanceEpsilon() ? "epsilon"
                        : iteration == delegate.getMaxIterations() ? "iterationLimit" : "continue";
                iterationRecords.add(iteration + ":" + (selectedIndex < 0 ? "na" : active.get(selectedIndex).id)
                        + ":" + vector(candidate.point1) + ":" + vector(candidate.point2)
                        + ":" + vector(normalBefore) + ":" + vector(candidate.normal)
                        + ":" + number(candidate.distance) + ":" + vector(point)
                        + ":" + number(projection) + ":" + number(delta) + ":" + decision
                        + ":" + (queueMirrorMatches ? join(equalIds, ",") : "na") + ":" + queueMirrorMatches);
                if (delta < delegate.getDistanceEpsilon()) { stopReason = "epsilon"; return; }
                expanding.expand(point);
                if (queueMirrorMatches) {
                    active.remove(selectedIndex);
                    active.add(new MirrorEdge(nextEdgeId++, new ExpandingSimplexEdge(candidate.point1, point, expanding.getWinding())));
                    active.add(new MirrorEdge(nextEdgeId++, new ExpandingSimplexEdge(point, candidate.point2, expanding.getWinding())));
                }
            }
            stopReason = "iterationLimit";
        }

        List<String> fields(Penetration penetration) {
            List<String> fields = new ArrayList<String>();
            List<String> simplex = new ArrayList<String>();
            for (Vector2 point : simplexPoints) simplex.add(vector(point));
            Boolean normalMatches = edge == null ? null : Boolean.valueOf(
                    Double.doubleToRawLongBits(edge.normal.x) == Double.doubleToRawLongBits(penetration.getNormal().x)
                    && Double.doubleToRawLongBits(edge.normal.y) == Double.doubleToRawLongBits(penetration.getNormal().y));
            Boolean depthMatches = projection == null ? null : Boolean.valueOf(
                    Double.doubleToRawLongBits(projection) == Double.doubleToRawLongBits(penetration.getDepth()));
            fields.add("epa.replay.identity=unobserved");
            fields.add("epa.replay.simplex=" + join(simplex, ";"));
            fields.add("epa.replay.iteration=" + iteration);
            fields.add("epa.replay.stop=" + stopReason);
            fields.add("epa.replay.epsilon=" + number(delegate.getDistanceEpsilon()));
            fields.add("epa.replay.maxIterations=" + delegate.getMaxIterations());
            fields.add("epa.iteration.schema=index:edgeId:edgeA:edgeB:normalBefore:normalAfter:distance:support:projection:delta:stop:equalDistanceEdgeIds:mirrorMatches");
            fields.add("epa.iteration.records=" + join(iterationRecords, ";"));
            fields.add("epa.queue.reconstructedMatches=" + queueMirrorMatches);
            fields.add("epa.edge.a=" + (edge == null ? "na" : vector(edge.point1)));
            fields.add("epa.edge.b=" + (edge == null ? "na" : vector(edge.point2)));
            fields.add("epa.edge.normal=" + (edge == null ? "na" : vector(edge.normal)));
            fields.add("epa.edge.distance=" + (edge == null ? "na" : number(edge.distance)));
            fields.add("epa.terminal.support=" + (support == null ? "na" : vector(support)));
            fields.add("epa.terminal.projection=" + (projection == null ? "na" : number(projection)));
            fields.add("epa.terminal.delta=" + (delta == null ? "na" : number(delta)));
            fields.add("epa.replay.normalMatchesResult=" + (normalMatches == null ? "na" : normalMatches));
            fields.add("epa.replay.depthMatchesResult=" + (depthMatches == null ? "na" : depthMatches));
            return fields;
        }
    }
}
