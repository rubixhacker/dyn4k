package org.dyn4j.collision.narrowphase

import kotlin.math.PI
import kotlin.test.Test
import org.dyn4j.collision.manifold.ClippingManifoldSolver
import org.dyn4j.collision.manifold.IndexedManifoldPointId
import org.dyn4j.collision.manifold.Manifold
import org.dyn4j.geometry.Capsule
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Segment
import org.dyn4j.geometry.Slice
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

class WindowsCollisionIntermediateDiagnosticTest {
    @Test fun capsuleSlice() = fixture("CapsuleSlice", Capsule(1.0, 0.5), Slice(0.5, 50.0 / 180.0 * PI), -0.25, "gjk")
    @Test fun circlePolygon() = fixture("CirclePolygon", Circle(1.0), Geometry.createUnitCirclePolygon(6, 0.5), -1.0, "gjk")
    @Test fun circleSegment() = fixture("CircleSegment", Circle(1.0), Segment(Vector2(-0.5, 0.0), Vector2(0.5, 0.0)), -1.0, "gjk")
    @Test fun circleSlice() = fixture("CircleSlice", Circle(0.5), Slice(0.5, 50.0 / 180.0 * PI), -0.25, "gjk")
    @Test fun polygonCapsule() = fixture("PolygonCapsule", Geometry.createUnitCirclePolygon(5, 0.5), Capsule(1.0, 0.5), -0.5, "sat")
    @Test fun polygonPolygon() = fixture("PolygonPolygon", Geometry.createUnitCirclePolygon(5, 1.0), Geometry.createUnitCirclePolygon(6, 0.5), -1.0, "sat")

    private fun fixture(name: String, first: Convex, second: Convex, shiftX: Double, detector: String) {
        val t1 = Transform()
        val t2 = Transform()
        val epa = EdgeRecordingEpa()
        val gjk = Gjk(epa)
        val sat = Sat()
        val selected = if (detector == "gjk") gjk else sat
        val p = Penetration()
        var step = 0
        fun detect(a: Convex, ta: Transform, b: Convex, tb: Transform, order: String, phase: String) {
            p.clear()
            epa.reset()
            val hit = selected.detect(a, ta, b, tb, p)
            val booleanHit = selected.detect(a, ta, b, tb)
            emit(name, if (detector == "gjk") "detectGjk" else "detectSat", phase, order, step++, a, ta, b, tb, hit, booleanHit, p, null, null, epa, detector)
        }
        detect(first, t1, second, t2, "forward", "center")
        detect(second, t2, first, t1, "reverse", "center")
        t1.translate(shiftX, 0.0)
        detect(first, t1, second, t2, "forward", "shifted")
        detect(second, t2, first, t1, "reverse", "shifted")

        t1.identity()
        val m = Manifold()
        val clip = ClippingManifoldSolver()
        fun clipWith(a: Convex, ta: Transform, b: Convex, tb: Transform, order: String, phase: String, algorithm: String) {
            p.clear()
            m.clear()
            epa.reset()
            val found = (if (algorithm == "gjk") gjk else sat).detect(a, ta, b, tb, p)
            val clipped = if (found) clip.getManifold(p, a, ta, b, tb, m) else false
            emit(name, "getClipManifold", phase, order, step++, a, ta, b, tb, found, null, p, clipped, m, epa, algorithm)
        }
        for (phase in arrayOf("center", "shifted")) {
            if (phase == "shifted") t1.translate(shiftX, 0.0)
            for (algorithm in arrayOf("gjk", "sat")) {
                clipWith(first, t1, second, t2, "forward", phase, algorithm)
                clipWith(second, t2, first, t1, "reverse", phase, algorithm)
            }
        }
    }

    private fun emit(
        fixture: String, method: String, phase: String, order: String, step: Int,
        a: Convex, ta: Transform, b: Convex, tb: Transform, hit: Boolean, booleanHit: Boolean?,
        p: Penetration, clipped: Boolean?, m: Manifold?, epa: EdgeRecordingEpa, algorithm: String
    ) {
        val fields = mutableListOf(
            "DYN4K_COLLISION_DIAGNOSTIC", "v2", "provider=dyn4k", "fixture=$fixture", "method=$method",
            "phase=$phase", "order=$order", "step=$step", "algorithm=$algorithm",
            "a.transform=${values(ta.getValues())}", "b.transform=${values(tb.getValues())}",
            "a.center.local=${vector(a.getCenter())}", "b.center.local=${vector(b.getCenter())}",
            "a.center.world=${vector(ta.getTransformed(a.getCenter()))}",
            "b.center.world=${vector(tb.getTransformed(b.getCenter()))}",
            "hit=$hit", "booleanHit=${booleanHit ?: "na"}",
            "penetration.normal=${vector(p.getNormal())}", "penetration.depth=${number(p.getDepth())}",
            "selection=${if (algorithm == "sat") "satSourceReplay" else if (epa.edge != null) "epaSourceReplay" else "unavailable"}",
            "clipped=${clipped ?: "na"}", "manifold.normal=${m?.let { vector(it.getNormal()) } ?: "na"}",
            "manifold.count=${m?.getPoints()?.size ?: "na"}"
        )
        fields += WindowsCollisionTrace.pairInputs(a, ta, b, tb, if (hit) p.getNormal() else null)
        if (algorithm == "sat") fields += WindowsCollisionTrace.sat(a, ta, b, tb, p, hit).fields
        fields += epa.fields(p)
        m?.getPoints()?.forEachIndexed { i, point ->
            val id = point.getId()
            fields += "manifold.point.$i.position=${vector(point.getPoint())}"
            fields += "manifold.point.$i.depth=${number(point.getDepth())}"
            fields += "manifold.point.$i.id=${if (id is IndexedManifoldPointId) "indexed:${id.getReferenceEdgeIndex()}:${id.getIncidentEdgeIndex()}:${id.getIncidentVertexIndex()}:${id.isFlipped()}" else "distance"}"
        }
        println(fields.joinToString("\t"))
    }

    private fun number(value: Double) = WindowsCollisionTrace.number(value)
    private fun values(values: DoubleArray) = WindowsCollisionTrace.values(values)
    private fun vector(value: Vector2) = WindowsCollisionTrace.vector(value)

    private class EdgeRecordingEpa : MinkowskiPenetrationSolver {
        private data class MirrorEdge(val id: Int, val edge: ExpandingSimplexEdge)

        private val delegate = Epa()
        var edge: ExpandingSimplexEdge? = null
        private var support: Vector2? = null
        private var projection: Double? = null
        private var delta: Double? = null
        private var iteration = 0
        private var stopReason = "notRun"
        private var simplexPoints: List<Vector2> = emptyList()
        private val iterationRecords = mutableListOf<String>()
        private var queueMirrorMatches = true

        fun reset() {
            edge = null
            support = null
            projection = null
            delta = null
            iteration = 0
            stopReason = "notRun"
            simplexPoints = emptyList()
            iterationRecords.clear()
            queueMirrorMatches = true
        }

        fun fields(penetration: Penetration): List<String> {
            val candidate = edge
            val normalMatches = candidate?.let { it.normal.x.toRawBits() == penetration.getNormal().x.toRawBits() && it.normal.y.toRawBits() == penetration.getNormal().y.toRawBits() }
            val depthMatches = projection?.toRawBits() == penetration.getDepth().toRawBits()
            return listOf(
                "epa.replay.identity=unobserved", "epa.replay.simplex=${simplexPoints.joinToString(";") { WindowsCollisionTrace.vector(it) }}",
                "epa.replay.iteration=$iteration", "epa.replay.stop=$stopReason",
                "epa.replay.epsilon=${WindowsCollisionTrace.number(delegate.getDistanceEpsilon())}",
                "epa.replay.maxIterations=${delegate.getMaxIterations()}",
                "epa.iteration.schema=index:edgeId:edgeA:edgeB:normalBefore:normalAfter:distance:support:projection:delta:stop:equalDistanceEdgeIds:mirrorMatches",
                "epa.iteration.records=${iterationRecords.joinToString(";")}",
                "epa.queue.reconstructedMatches=$queueMirrorMatches",
                "epa.edge.a=${candidate?.let { WindowsCollisionTrace.vector(it.point1) } ?: "na"}",
                "epa.edge.b=${candidate?.let { WindowsCollisionTrace.vector(it.point2) } ?: "na"}",
                "epa.edge.normal=${candidate?.let { WindowsCollisionTrace.vector(it.normal) } ?: "na"}",
                "epa.edge.distance=${candidate?.let { WindowsCollisionTrace.number(it.distance) } ?: "na"}",
                "epa.terminal.support=${support?.let(WindowsCollisionTrace::vector) ?: "na"}",
                "epa.terminal.projection=${projection?.let(WindowsCollisionTrace::number) ?: "na"}",
                "epa.terminal.delta=${delta?.let(WindowsCollisionTrace::number) ?: "na"}",
                "epa.replay.normalMatchesResult=${normalMatches ?: "na"}",
                "epa.replay.depthMatchesResult=${if (projection == null) "na" else depthMatches}"
            )
        }

        override fun getPenetration(simplex: List<Vector2>, minkowskiSum: MinkowskiSum, penetration: Penetration) {
            delegate.getPenetration(simplex, minkowskiSum, penetration)
            simplexPoints = simplex.map { it.copy() }
            val expanding = ExpandingSimplex(simplex)
            val active = simplex.indices.mapTo(mutableListOf()) { index ->
                MirrorEdge(index, ExpandingSimplexEdge(simplex[index], simplex[(index + 1) % simplex.size], expanding.getWinding()))
            }
            var nextEdgeId = simplex.size
            for (i in 0 until delegate.getMaxIterations()) {
                val candidate = expanding.getClosestEdge()
                val normalBefore = candidate.normal.copy()
                val selectedIndex = if (queueMirrorMatches && active.size == expanding.size()) active.indexOfFirst {
                    it.edge.point1 === candidate.point1 && it.edge.point2 === candidate.point2 &&
                        it.edge.distance.toRawBits() == candidate.distance.toRawBits()
                } else -1
                if (selectedIndex < 0) queueMirrorMatches = false
                val equalIds = if (queueMirrorMatches) active.filter { it.edge.compareTo(candidate) == 0 }.map { it.id } else emptyList()
                val point = minkowskiSum.getSupportPoint(candidate.normal)
                edge = candidate
                support = point
                projection = point.dot(candidate.normal)
                delta = projection!! - candidate.distance
                iteration = i + 1
                val decision = when {
                    delta!! < delegate.getDistanceEpsilon() -> "epsilon"
                    iteration == delegate.getMaxIterations() -> "iterationLimit"
                    else -> "continue"
                }
                iterationRecords += listOf(
                    iteration.toString(), if (selectedIndex < 0) "na" else active[selectedIndex].id.toString(),
                    WindowsCollisionTrace.vector(candidate.point1), WindowsCollisionTrace.vector(candidate.point2),
                    WindowsCollisionTrace.vector(normalBefore), WindowsCollisionTrace.vector(candidate.normal),
                    WindowsCollisionTrace.number(candidate.distance), WindowsCollisionTrace.vector(point),
                    WindowsCollisionTrace.number(projection!!), WindowsCollisionTrace.number(delta!!), decision,
                    if (queueMirrorMatches) equalIds.joinToString(",") else "na", queueMirrorMatches.toString()
                ).joinToString(":")
                if (delta!! < delegate.getDistanceEpsilon()) { stopReason = "epsilon"; return }
                expanding.expand(point)
                if (queueMirrorMatches) {
                    active.removeAt(selectedIndex)
                    active += MirrorEdge(nextEdgeId++, ExpandingSimplexEdge(candidate.point1, point, expanding.getWinding()))
                    active += MirrorEdge(nextEdgeId++, ExpandingSimplexEdge(point, candidate.point2, expanding.getWinding()))
                }
            }
            stopReason = "iterationLimit"
        }
    }
}
