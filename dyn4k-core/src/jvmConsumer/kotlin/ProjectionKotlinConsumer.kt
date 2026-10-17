package org.dyn4j.geometry.simplify

import org.dyn4j.dynamics.ContinuousDetectionMode
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Rotation
import org.dyn4j.geometry.Vector2

object ProjectionKotlinConsumer {
    @JvmStatic
    fun main(args: Array<String>) {
        val named = Vector2(x = 3.0, y = 4.0)
        val created = Vector2.create(2.0, 0.0)
        check(named.x == 3.0 && named.y == 4.0)
        check(created.x == 2.0 && created.y == 0.0)
        check(Vector2.Companion.create(1.0, 0.0).x == 1.0)
        check(Rotation.ofDegrees(90.0).getSint() > 0.99)
        check(ContinuousDetectionMode.entries.size == 3)
        check(MassType.entries.contains(MassType.NORMAL))

        val node = SegmentTreeNode()
        node.left = SegmentTreeNode()
        check(node.left !== null)
        val vertex = SimplePolygonVertex(index = 2, point = named)
        vertex.next = SimplePolygonVertex(index = 3, point = created)
        check(vertex.point === named && vertex.next?.index == 3)
        println("PROJECTION_KOTLIN_CONSUMER_OK")
    }
}
