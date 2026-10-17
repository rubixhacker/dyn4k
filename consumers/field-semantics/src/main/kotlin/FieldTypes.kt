import org.dyn4j.Reference
import org.dyn4j.geometry.Matrix22
import org.dyn4j.geometry.Matrix33
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.Vector3

fun main() {
    val failures = mutableListOf<String>()
    fun verify(name: String, actual: Any?, expected: Any?) {
        if (actual != expected) failures += "$name: expected=$expected actual=$actual"
    }

    val vector2 = FieldChildren.Vector2Child()
    val vector2Base: Vector2 = vector2
    verify("vector2 child read", vector2.x, 4.0)
    verify("vector2 base read", vector2Base.x, 4.0)
    vector2.x = 7.0
    verify("vector2 child write", vector2Base.x, 7.0)
    verify("vector2 explicit bean", vector2.readBean(), 14.0)

    val vector3 = FieldChildren.Vector3Child()
    val vector3Base: Vector3 = vector3
    verify("vector3 child read", vector3.z, 1.0)
    verify("vector3 base read", vector3Base.z, 1.0)
    vector3.z = 7.0
    verify("vector3 child write", vector3Base.z, 7.0)
    verify("vector3 explicit bean", vector3.readBean(), 14.0)

    val matrix22 = FieldChildren.Matrix22Child()
    val matrix22Base: Matrix22 = matrix22
    verify("matrix22 child read", matrix22.m00, 4.0)
    verify("matrix22 base read", matrix22Base.m00, 4.0)
    matrix22.m00 = 7.0
    verify("matrix22 child write", matrix22Base.m00, 7.0)
    verify("matrix22 explicit bean", matrix22.readBean(), 14.0)

    val matrix33 = FieldChildren.Matrix33Child()
    val matrix33Base: Matrix33 = matrix33
    verify("matrix33 child read", matrix33.m22, 4.0)
    verify("matrix33 base read", matrix33Base.m22, 4.0)
    matrix33.m22 = 7.0
    verify("matrix33 child write", matrix33Base.m22, 7.0)
    verify("matrix33 explicit bean", matrix33.readBean(), 14.0)

    val reference = FieldChildren.ReferenceChild()
    val referenceBase: Reference<String> = reference
    verify("reference child read", reference.value, "raw")
    verify("reference base read", referenceBase.value, "raw")
    reference.value = "next"
    verify("reference child write", referenceBase.value, "next")
    verify("reference explicit bean", reference.readBean(), "next-bean")

    if (failures.isNotEmpty()) error(failures.joinToString("\n"))
    println("FieldTypes: 20 same-source field and bean checks passed")
}
