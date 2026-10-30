package io.github.rubixhacker.dyn4k

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.Copyable
import org.dyn4j.Epsilon

val FoundationTest by testSuite {
    test("mutableVectorsAndTransformsShareObjects") { FoundationTestFixture().run { mutableVectorsAndTransformsShareObjects() } }
    test("vectorMatrixAndRotationUseDoublePrecision") { FoundationTestFixture().run { vectorMatrixAndRotationUseDoublePrecision() } }
    test("matrix33SolvesAndInverts") { FoundationTestFixture().run { matrix33SolvesAndInverts() } }
    test("inverseTransformRestoresThePoint") { FoundationTestFixture().run { inverseTransformRestoresThePoint() } }
    test("rotationAndTransformExposeMutableCompatibilityValues") { FoundationTestFixture().run { rotationAndTransformExposeMutableCompatibilityValues() } }
    test("copyableAcceptsParentWhoseCopyIsAChild") { FoundationTestFixture().run { copyableAcceptsParentWhoseCopyIsAChild() } }
    test("epsilonAndVectorOperationsMatchWorkedValues") { FoundationTestFixture().run { epsilonAndVectorOperationsMatchWorkedValues() } }
}

private open class CopyParent(val value: Int) : Copyable<CopyChild> {
    override fun copy() = CopyChild(value)
}

private class CopyChild(value: Int) : CopyParent(value)

private class CopyOther : Copyable<CopyParent> {
    override fun copy(): CopyParent = CopyChild(17)
}

private fun copyParent(value: Copyable<CopyParent>): CopyParent = value.copy()

private class FoundationTestFixture  {
fun mutableVectorsAndTransformsShareObjects() {
        val point = Vector2(3.0, 4.0)
        val samePoint: org.dyn4j.geometry.Vector2 = point
        assertSame(point, samePoint)
        assertEquals(5.0, point.getMagnitude(), 1e-12)
        val transform = Transform()
        transform.translate(2.0, -1.0)
        assertEquals(5.0, transform.getTransformed(point).x, 1e-12)
        assertEquals(3.0, transform.getTransformed(point).y, 1e-12)
    }

fun vectorMatrixAndRotationUseDoublePrecision() {
        val vector = Vector3(1.0, 2.0, 3.0)
        assertEquals(14.0, vector.getMagnitudeSquared(), 1e-12)
        val matrix = Matrix22(2.0, 0.0, 0.0, 4.0)
        val solved = matrix.solve(Vector2(6.0, 8.0))
        assertEquals(3.0, solved.x, 1e-12)
        assertEquals(2.0, solved.y, 1e-12)
        val rotated = Vector2(1.0, 0.0).rotate(Rotation.rotation90())
        assertEquals(0.0, rotated.x, 1e-12)
        assertEquals(1.0, rotated.y, 1e-12)
    }

fun matrix33SolvesAndInverts() {
        val matrix = Matrix33(2.0, 0.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 4.0)
        val solved = matrix.solve33(Vector3(4.0, 9.0, 16.0))
        assertEquals(2.0, solved.x, 1e-12)
        assertEquals(3.0, solved.y, 1e-12)
        assertEquals(4.0, solved.z, 1e-12)
        val inverse = matrix.getInverse()
        assertEquals(0.5, inverse.m00, 1e-12)
        assertEquals(1.0 / 3.0, inverse.m11, 1e-12)
        assertEquals(0.25, inverse.m22, 1e-12)
    }

fun inverseTransformRestoresThePoint() {
        val transform = Transform()
        transform.rotate(Rotation.rotation90())
        transform.translate(5.0, -2.0)
        val point = Vector2(3.0, 4.0)
        val moved = transform.getTransformed(point)
        assertEquals(1.0, moved.x, 1e-12)
        assertEquals(1.0, moved.y, 1e-12)
        val restored = transform.getInverseTransformed(moved)
        assertEquals(3.0, restored.x, 1e-12)
        assertEquals(4.0, restored.y, 1e-12)
    }

fun rotationAndTransformExposeMutableCompatibilityValues() {
        val rotation = Rotation()
        val sameRotation: org.dyn4j.geometry.Rotation = rotation
        assertSame(rotation, rotation.set(kotlin.math.PI / 2.0))
        assertSame(rotation, sameRotation)
        assertEquals(0.0, rotation.getCost(), 1e-12)
        assertEquals(1.0, rotation.getSint(), 1e-12)

        val transform = Transform()
        val sameTransform: org.dyn4j.geometry.Transform = transform
        transform.setRotation(rotation)
        assertSame(transform, sameTransform)
        assertEquals(0.0, transform.getCost(), 1e-12)
        assertEquals(1.0, transform.getSint(), 1e-12)
        transform.identity()
        assertEquals(1.0, sameTransform.getCost(), 1e-12)
        assertEquals(0.0, sameTransform.getSint(), 1e-12)
    }

fun copyableAcceptsParentWhoseCopyIsAChild() {
        val parent = CopyParent(3)
        assertEquals(3, parent.copy().value)
        val copiedParent = copyParent(CopyOther())
        assertEquals(17, copiedParent.value)
        assertTrue(copiedParent is CopyChild)
    }

fun epsilonAndVectorOperationsMatchWorkedValues() {
        assertEquals(1.1102230246251565e-16, Epsilon.E, 0.0)
        val projected = Vector2(3.0, 4.0).project(Vector2(1.0, 0.0))
        assertEquals(3.0, projected.x, 1e-12)
        assertEquals(0.0, projected.y, 1e-12)
        val crossed = Vector3(1.0, 0.0, 0.0).cross(Vector3(0.0, 1.0, 0.0))
        assertEquals(0.0, crossed.x, 1e-12)
        assertEquals(0.0, crossed.y, 1e-12)
        assertEquals(1.0, crossed.z, 1e-12)
    }
}
