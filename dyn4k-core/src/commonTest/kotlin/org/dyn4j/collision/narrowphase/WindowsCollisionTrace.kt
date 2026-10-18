package org.dyn4j.collision.narrowphase

import kotlin.math.abs
import org.dyn4j.geometry.Capsule
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.EdgeFeature as GeometryEdgeFeature
import org.dyn4j.geometry.Feature
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.PointFeature
import org.dyn4j.geometry.Segment
import org.dyn4j.geometry.Slice
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.Wound

internal object WindowsCollisionTrace {
    fun number(value: Double) = "${value}@${value.toRawBits()}"
    fun vector(value: Vector2) = "${number(value.x)},${number(value.y)}"
    fun vectors(values: Array<Vector2>?) = values?.joinToString(";") { vector(it) } ?: "null"
    fun values(values: DoubleArray) = values.joinToString(",") { number(it) }

    fun shape(shape: Convex): String {
        val parts = mutableListOf("kind=${shape::class.simpleName}", "center=${vector(shape.getCenter())}", "radius=${number(shape.getRadius())}")
        when (shape) {
            is Circle -> parts += "circle.radius=${number(shape.getRadius())}"
            is Capsule -> {
                val rotation = shape.getRotation()
                parts += "capsule.length=${number(shape.getLength())}"
                parts += "capsule.capRadius=${number(shape.getCapRadius())}"
                parts += "capsule.localFoci=${vectors(shape.getFoci(Transform()))}"
                parts += "capsule.localAxis=${number(rotation.getCost())},${number(rotation.getSint())}"
            }
            is Slice -> {
                parts += "slice.radius=${number(shape.getSliceRadius())}"
                parts += "slice.theta=${number(shape.getTheta())}"
                parts += "slice.circleCenter=${vector(shape.getCircleCenter())}"
                val rotation = shape.getRotation()
                parts += "slice.rotation=${number(rotation.getCost())},${number(rotation.getSint())}"
                parts += "slice.upperEdge=${feature(shape.getFarthestFeature(Vector2(0.0, 1.0), Transform()))}"
                parts += "slice.lowerEdge=${feature(shape.getFarthestFeature(Vector2(0.0, -1.0), Transform()))}"
            }
            is Segment -> parts += "segment.length=${number(shape.getLength())}"
        }
        if (shape is Wound) {
            parts += "vertices=${vectors(shape.getVertices())}"
            parts += "normals=${vectors(shape.getNormals())}"
        }
        return parts.joinToString("|")
    }

    fun feature(feature: Feature): String = when (feature) {
        is PointFeature -> "point:${feature.getIndex()}:${vector(feature.getPoint()!!)}"
        is GeometryEdgeFeature -> "edge:${feature.getIndex()}:${feature.getVertex1()!!.getIndex()}:${vector(feature.getVertex1()!!.getPoint()!!)}:${feature.getVertex2()!!.getIndex()}:${vector(feature.getVertex2()!!.getPoint()!!)}:${feature.getMaximum()!!.getIndex()}:${vector(feature.getMaximum()!!.getPoint()!!)}:${vector(feature.getEdge()!!)}"
        else -> "unknown:${feature.getIndex()}"
    }

    fun pairInputs(a: Convex, ta: Transform, b: Convex, tb: Transform, resultNormal: Vector2?): List<String> {
        val fociA = a.getFoci(ta)
        val fociB = b.getFoci(tb)
        val axesA = a.getAxes(fociB, ta)
        val axesB = b.getAxes(fociA, tb)
        val centerDirection = ta.getTransformed(a.getCenter()).to(tb.getTransformed(b.getCenter()))
        val initialDirection = if (centerDirection.isZero()) Vector2(1.0, 0.0) else centerDirection.copy()
        val fields = mutableListOf(
            "a.shape.local=${shape(a)}", "b.shape.local=${shape(b)}",
            "a.foci.world=${vectors(fociA)}", "b.foci.world=${vectors(fociB)}",
            "a.axes.withB=${vectors(axesA)}", "b.axes.withA=${vectors(axesB)}",
            "gjk.initial.centerDirection=${vector(centerDirection)}", "gjk.initial.effectiveDirection=${vector(initialDirection)}",
            "clip.probe.feature.a=${resultNormal?.let { feature(a.getFarthestFeature(it.copy(), ta)) } ?: "na"}",
            "clip.probe.feature.b=${resultNormal?.let { feature(b.getFarthestFeature(it.getNegative(), tb)) } ?: "na"}"
        )
        val directions = arrayOf(Vector2(1.0, 0.0), Vector2(-1.0, 0.0), Vector2(0.0, 1.0), Vector2(0.0, -1.0), initialDirection, resultNormal?.copy() ?: initialDirection.copy())
        for ((index, direction) in directions.withIndex()) {
            val supportA = a.getFarthestPoint(direction.copy(), ta)
            val supportB = b.getFarthestPoint(direction.getNegative(), tb)
            fields += "support.$index.direction=${vector(direction)}"
            fields += "support.$index.a=${vector(supportA)}"
            fields += "support.$index.b.negated=${vector(supportB)}"
            fields += "support.$index.minkowski=${vector(supportA.difference(supportB))}"
        }
        return fields
    }

    data class SatReplay(val fields: List<String>)

    fun sat(a: Convex, ta: Transform, b: Convex, tb: Transform, penetration: Penetration, productionHit: Boolean): SatReplay {
        val fociA = a.getFoci(ta)
        val fociB = b.getFoci(tb)
        val axisSets = arrayOf(a.getAxes(fociB, ta), b.getAxes(fociA, tb))
        val candidates = mutableListOf<String>()
        var best: Vector2? = null
        var bestSource = "na"
        var bestIndex = -1
        var depth = Double.MAX_VALUE
        for ((source, axes) in axisSets.withIndex()) {
            if (axes == null) continue
            for ((index, axis) in axes.withIndex()) {
                if (axis.isZero()) {
                    candidates += "$source:$index:zero:${vector(axis)}"
                    continue
                }
                val rawAxis = axis.copy()
                val intervalA = a.project(axis, ta)
                val intervalB = b.project(axis, tb)
                if (!intervalA.overlaps(intervalB)) {
                    candidates += "$source:$index:separated:${vector(rawAxis)}:${interval(intervalA)}:${interval(intervalB)}"
                    return SatReplay(listOf("sat.replay.hit=false", "sat.replay.matchesResult=${!productionHit}", "sat.candidates=${candidates.joinToString(";")}", "sat.winner.source=$source", "sat.winner.index=$index"))
                }
                val rawOverlap = intervalA.getOverlap(intervalB)
                var adjustedOverlap = rawOverlap
                val contained = intervalA.containsExclusive(intervalB) || intervalB.containsExclusive(intervalA)
                var containmentFlip = false
                var maxDifference: Double? = null
                var minDifference: Double? = null
                if (contained) {
                    val max = abs(intervalA.getMax() - intervalB.getMax())
                    val min = abs(intervalA.getMin() - intervalB.getMin())
                    maxDifference = max
                    minDifference = min
                    if (max > min) { axis.negate(); adjustedOverlap += min; containmentFlip = true }
                    else adjustedOverlap += max
                }
                val selected = adjustedOverlap < depth
                if (selected) { depth = adjustedOverlap; best = axis; bestSource = if (source == 0) "a" else "b"; bestIndex = index }
                candidates += "$source:$index:${vector(rawAxis)}:${interval(intervalA)}:${interval(intervalB)}:${number(rawOverlap)}:$contained:$containmentFlip:${maxDifference?.let(::number) ?: "na"}:${minDifference?.let(::number) ?: "na"}:${number(adjustedOverlap)}:${vector(axis)}:$selected"
            }
        }
        val preOrientation = best!!.copy()
        val centerDot = ta.getTransformed(a.getCenter()).to(tb.getTransformed(b.getCenter())).dot(best)
        val orientationFlip = centerDot < 0.0
        if (orientationFlip) best.negate()
        val matches = productionHit && best.x.toRawBits() == penetration.getNormal().x.toRawBits() && best.y.toRawBits() == penetration.getNormal().y.toRawBits() && depth.toRawBits() == penetration.getDepth().toRawBits()
        return SatReplay(listOf(
            "sat.replay.hit=true", "sat.replay.matchesResult=$matches", "sat.candidates=${candidates.joinToString(";")}",
            "sat.winner.source=$bestSource", "sat.winner.index=$bestIndex",
            "sat.winner.preOrientation=${vector(preOrientation)}", "sat.winner.centerDot=${number(centerDot)}",
            "sat.winner.orientationFlip=$orientationFlip", "sat.winner.finalAxis=${vector(best)}", "sat.winner.depth=${number(depth)}"
        ))
    }

    private fun interval(value: Interval) = "${number(value.getMin())},${number(value.getMax())}"
}
