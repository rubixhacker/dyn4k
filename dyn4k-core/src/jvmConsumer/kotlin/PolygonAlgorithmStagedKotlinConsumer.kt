import org.dyn4j.geometry.Polygon
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.decompose.Bayazit
import org.dyn4j.geometry.decompose.EarClipping
import org.dyn4j.geometry.hull.MonotoneChain
import org.dyn4j.geometry.simplify.VertexClusterReduction

private class StagedPolygonExtension : VertexClusterReduction(0.1) {
    fun getClusterTolerance(): String = "extension"
}

fun main() {
    var checks = 0
    fun checkResult(condition: Boolean) {
        check(condition)
        checks++
    }

    val cloud = arrayOf(
        Vector2(0.0, 0.0), Vector2(2.0, 0.0), Vector2(2.0, 2.0),
        Vector2(0.0, 2.0), Vector2(1.0, 1.0)
    )
    val hull = MonotoneChain().generate(*cloud)
    checkResult(hull.size == 4)
    checkResult(kotlin.math.abs(Polygon(*hull).getArea() - 4.0) < 1e-12)

    val concave = arrayOf(
        Vector2(0.0, 0.0), Vector2(2.0, 0.0), Vector2(2.0, 1.0),
        Vector2(1.0, 1.0), Vector2(1.0, 2.0), Vector2(0.0, 2.0)
    )
    checkResult(kotlin.math.abs(Bayazit().decompose(*concave).sumOf { it.getArea() } - 3.0) < 1e-12)
    checkResult(EarClipping().triangulate(*concave).size == 4)

    val result = VertexClusterReduction(0.0).simplify(listOf(Vector2(1.0, 2.0)))!!
    val mutable = result as MutableList<Vector2>
    mutable.add(Vector2(3.0, 4.0))
    checkResult(mutable.size == 2)
    val extension = StagedPolygonExtension()
    checkResult(extension.clusterTolerance == 0.1)
    checkResult(extension.getClusterTolerance() == "extension")
    println("PolygonAlgorithmStagedKotlinConsumer: $checks checks passed")
}
