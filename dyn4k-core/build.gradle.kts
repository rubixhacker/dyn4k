@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import java.security.MessageDigest
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream
import org.objectweb.asm.ClassReader
import org.objectweb.asm.ClassVisitor
import org.objectweb.asm.ClassWriter
import org.objectweb.asm.FieldVisitor
import org.objectweb.asm.MethodVisitor
import org.objectweb.asm.Opcodes
import org.objectweb.asm.Type

plugins {
    kotlin("multiplatform")
    id("com.android.kotlin.multiplatform.library")
    `maven-publish`
}

data class JvmApiSpec(
    val publicFields: Set<String> = emptySet(),
    val protectedFields: Set<String> = emptySet(),
    val packageFields: Set<String> = emptySet(),
    val staticMethods: Set<String> = emptySet(),
    val varargMethods: Set<String> = emptySet(),
    val packageMethods: Set<String> = emptySet(),
    val packageMethodSignatures: Set<String> = emptySet(),
    val packageConstructorDescriptors: Set<String> = emptySet(),
    val protectedConstructorDescriptors: Set<String> = emptySet(),
    val packageType: Boolean = false,
    val packageNodeMethods: Boolean = false,
    val protectedMethods: Set<String> = emptySet(),
    val appendIterable: Boolean = false
)

val jvmApi = mapOf(
    "org/dyn4j/Copyable" to JvmApiSpec(),
    "org/dyn4j/Version" to JvmApiSpec(
        staticMethods = setOf("getVersion", "getVersionNumbers", "getMajorNumber", "getMinorNumber", "getRevisionNumber", "main")
    ),
    "org/dyn4j/AVLTree" to JvmApiSpec(
        packageFields = setOf("root", "size"),
        packageNodeMethods = true,
        packageMethods = setOf("get"),
        appendIterable = true
    ),
    "org/dyn4j/BinarySearchTree" to JvmApiSpec(),
    "org/dyn4j/BinarySearchTreeSearchCriteria" to JvmApiSpec(),
    "org/dyn4j/Reference" to JvmApiSpec(publicFields = setOf("value")),
    "org/dyn4j/BinarySearchTreeNode" to JvmApiSpec(
        packageType = true,
        packageFields = setOf("comparable", "parent", "left", "right"),
        packageMethods = setOf("isLeftChild")
    ),
    "org/dyn4j/BinarySearchTreeIterator" to JvmApiSpec(
        packageType = true,
        protectedMethods = setOf("pushLeftFrom", "pushLeft", "pushRight")
    ),
    "org/dyn4j/Epsilon" to JvmApiSpec(
        publicFields = setOf("E"), staticMethods = setOf("compute")
    ),
    "org/dyn4j/geometry/Vector2" to JvmApiSpec(
        publicFields = setOf("x", "y", "X_AXIS", "Y_AXIS", "INV_X_AXIS", "INV_Y_AXIS"),
        staticMethods = setOf("create", "tripleProduct")
    ),
    "org/dyn4j/geometry/Vector3" to JvmApiSpec(
        publicFields = setOf("x", "y", "z"), staticMethods = setOf("tripleProduct")
    ),
    "org/dyn4j/geometry/Rotation" to JvmApiSpec(
        protectedFields = setOf("cost", "sint"),
        staticMethods = setOf(
            "of", "ofDegrees", "rotation0", "rotation45", "rotation90", "rotation135",
            "rotation180", "rotation225", "rotation270", "rotation315",
            "getNormalizedAngle", "getShortestDistance", "isAngleBetween"
        )
    ),
    "org/dyn4j/geometry/Matrix22" to JvmApiSpec(
        publicFields = setOf("m00", "m01", "m10", "m11")
    ),
    "org/dyn4j/geometry/Matrix33" to JvmApiSpec(
        publicFields = setOf("m00", "m01", "m02", "m10", "m11", "m12", "m20", "m21", "m22")
    ),
    "org/dyn4j/geometry/Transform" to JvmApiSpec(
        protectedFields = setOf("cost", "sint", "x", "y")
    ),
    "org/dyn4j/geometry/AABB" to JvmApiSpec(
        protectedFields = setOf("minX", "minY", "maxX", "maxY"),
        staticMethods = setOf("createFromPoints", "setFromPoints")
    ),
    "org/dyn4j/geometry/Interval" to JvmApiSpec(
        protectedFields = setOf("min", "max"), staticMethods = setOf("clamp")
    ),
    "org/dyn4j/geometry/Ray" to JvmApiSpec(
        protectedFields = setOf("start", "direction")
    ),
    "org/dyn4j/geometry/Mass" to JvmApiSpec(
        packageFields = setOf("type", "center", "mass", "inertia", "invMass", "invInertia"),
        staticMethods = setOf("create")
    ),
    "org/dyn4j/geometry/Feature" to JvmApiSpec(
        packageFields = setOf("index")
    ),
    "org/dyn4j/geometry/PointFeature" to JvmApiSpec(
        packageFields = setOf("point")
    ),
    "org/dyn4j/geometry/EdgeFeature" to JvmApiSpec(
        packageFields = setOf("vertex1", "vertex2", "max", "edge")
    ),
    "org/dyn4j/geometry/AbstractShape" to JvmApiSpec(
        protectedFields = setOf("center", "radius", "userData")
    ),
    "org/dyn4j/geometry/Polygon" to JvmApiSpec(
        packageFields = setOf("vertices", "normals"),
        packageMethods = setOf("getFarthestVertexIndex"),
        packageConstructorDescriptors = setOf(
            "(Lorg/dyn4j/geometry/Vector2;D[Lorg/dyn4j/geometry/Vector2;[Lorg/dyn4j/geometry/Vector2;)V"
        )
    ),
    "org/dyn4j/geometry/AdaptiveDecimal" to JvmApiSpec(
        packageType = true,
        staticMethods = setOf(
            "valueOf", "fromSum", "fromDiff", "fromProduct", "getErrorComponentFromSum",
            "getErrorComponentFromDifference", "getErrorComponentFromProduct"
        ),
        packageMethods = setOf("sumEpilogue", "getErrorComponentFromSum", "getErrorComponentFromDifference"),
        packageMethodSignatures = setOf(
            "fromDiff(DDDDLorg/dyn4j/geometry/AdaptiveDecimal;)Lorg/dyn4j/geometry/AdaptiveDecimal;"
        )
    ),
    "org/dyn4j/geometry/RobustGeometry" to JvmApiSpec(
        packageFields = setOf("SPLITTER"),
        packageMethods = setOf("cross"),
        staticMethods = setOf("cross", "getLocation")
    ),
    "org/dyn4j/geometry/WoundIterator" to JvmApiSpec(
        packageType = true,
        packageFields = setOf("vectors", "index")
    ),
    "org/dyn4j/geometry/Geometry" to JvmApiSpec(
        publicFields = setOf("INV_SQRT_3"),
        varargMethods = setOf(
            "getWinding", "reverseWinding", "getAverageCenter", "getAreaWeightedCenter",
            "getRotationRadius", "getCounterClockwiseEdgeNormals", "cleanse",
            "createPolygon", "createPolygonAtOrigin"
        ),
        staticMethods = setOf(
            "getWinding", "reverseWinding", "getAverageCenter", "getAreaWeightedCenter",
            "getRotationRadius", "getCounterClockwiseEdgeNormals", "createUnitCirclePolygon",
            "createPolygonalCircle", "createPolygonalSlice", "createPolygonalSliceAtOrigin",
            "createPolygonalEllipse", "createPolygonalHalfEllipse", "createPolygonalHalfEllipseAtOrigin",
            "createPolygonalCapsule", "createSquare", "createRectangle", "createCircle", "createPolygon",
            "createPolygonAtOrigin", "createTriangle", "createTriangleAtOrigin", "createRightTriangle",
            "createIsoscelesTriangle", "createEquilateralTriangle", "createSegment", "createSegmentAtOrigin",
            "createHorizontalSegment", "createVerticalSegment", "createCapsule", "createSlice",
            "createSliceAtOrigin", "createEllipse", "createHalfEllipse", "createHalfEllipseAtOrigin",
            "cleanse", "flipAlongTheXAxis", "flipAlongTheYAxis", "flip", "minkowskiSum", "scale",
            "createLinks", "getIntersection"
        )
    ),
    "org/dyn4j/geometry/Rectangle" to JvmApiSpec(
        packageFields = setOf("width", "height")
    ),
    "org/dyn4j/geometry/Capsule" to JvmApiSpec(
        packageFields = setOf("length", "capRadius", "foci", "localXAxis"),
        protectedFields = setOf("EDGE_FEATURE_SELECTION_CRITERIA", "EDGE_FEATURE_EXPANSION_FACTOR")
    ),
    "org/dyn4j/geometry/Ellipse" to JvmApiSpec(
        packageFields = setOf("halfWidth", "halfHeight", "rotation"),
        staticMethods = setOf("getFarthestPointOnEllipse", "getFarthestPointOnBoundedEllipse"),
        packageMethods = setOf("getFarthestPointOnEllipse", "getFarthestPointOnBoundedEllipse")
    ),
    "org/dyn4j/geometry/HalfEllipse" to JvmApiSpec(
        packageFields = setOf("height", "halfWidth", "rotation", "ellipseCenter", "vertexLeft", "vertexRight")
    ),
    "org/dyn4j/geometry/Slice" to JvmApiSpec(
        packageFields = setOf("alpha", "cosAlpha", "sliceRadius", "vertices", "normals", "rotation")
    ),
    "org/dyn4j/geometry/Segment" to JvmApiSpec(
        packageFields = setOf("vertices", "normals", "length"),
        staticMethods = setOf(
            "getLocation", "getPointOnLineClosestToPoint", "getPointOnSegmentClosestToPoint",
            "getLineIntersection", "getSegmentIntersection", "getFarthestFeature", "getFarthestPoint"
        )
    ),
    "org/dyn4j/geometry/Link" to JvmApiSpec(
        packageFields = setOf("point0", "point3")
    ),
    "org/dyn4j/collision/Filter" to JvmApiSpec(publicFields = setOf("DEFAULT_FILTER")),
    "org/dyn4j/collision/CategoryFilter" to JvmApiSpec(protectedFields = setOf("category", "mask")),
    "org/dyn4j/collision/Fixture" to JvmApiSpec(
        protectedFields = setOf("shape", "filter", "sensor", "userData")
    ),
    "org/dyn4j/collision/AbstractBounds" to JvmApiSpec(protectedFields = setOf("transform")),
    "org/dyn4j/collision/AxisAlignedBounds" to JvmApiSpec(protectedFields = setOf("aabb")),
    "org/dyn4j/collision/AbstractCollisionBody" to JvmApiSpec(
        protectedFields = setOf(
            "transform", "transform0", "fixtures", "fixturesUnmodifiable", "radius", "userData",
            "enabled", "fixtureModificationHandler", "owner"
        )
    ),
    "org/dyn4j/collision/broadphase/AABBBroadphaseProxy" to JvmApiSpec(
        packageType = true, packageFields = setOf("item", "aabb")
    ),
    "org/dyn4j/collision/broadphase/BroadphasePair" to JvmApiSpec(
        packageType = true, packageFields = setOf("first", "second"),
        packageConstructorDescriptors = setOf("()V")
    ),
    "org/dyn4j/collision/broadphase/BroadphaseItem" to JvmApiSpec(
        packageType = true, packageFields = setOf("body", "fixture"),
        protectedConstructorDescriptors = setOf("(Lorg/dyn4j/collision/broadphase/BroadphaseItem;)V")
    ),
    "org/dyn4j/collision/broadphase/DynamicAABBTreeNode" to JvmApiSpec(
        packageType = true, packageFields = setOf("left", "right", "parent", "height", "aabb")
    ),
    "org/dyn4j/collision/broadphase/DynamicAABBTreeLeaf" to JvmApiSpec(
        packageType = true, packageFields = setOf("item")
    ),
    "org/dyn4j/collision/broadphase/DynamicAABBTree" to JvmApiSpec(
        packageMethods = setOf("isValid")
    ),
    "org/dyn4j/collision/broadphase/Sap" to JvmApiSpec(
        packageMethods = setOf("insert"),
        packageMethodSignatures = setOf("update(Lorg/dyn4j/collision/broadphase/AABBBroadphaseProxy;Ljava/lang/Object;)V")
    ),
    "org/dyn4j/collision/broadphase/AbstractBroadphaseDetector" to JvmApiSpec(
        protectedFields = setOf("AABB_REDUCTION_RATIO", "aabbProducer", "aabbExpansionMethod", "broadphaseFilter", "updateTrackingEnabled"),
        staticMethods = setOf("raycast"),
        packageMethodSignatures = setOf("raycast(Lorg/dyn4j/geometry/Vector2;DDDLorg/dyn4j/geometry/AABB;)Z")
    ),
    "org/dyn4j/collision/broadphase/BroadphaseDetectorDecoratorAdapter" to JvmApiSpec(
        protectedFields = setOf("detector")
    ),
    "org/dyn4j/collision/narrowphase/ExpandingSimplexEdge" to JvmApiSpec(
        packageType = true, packageFields = setOf("point1", "point2", "normal", "distance")
    ),
    "org/dyn4j/collision/narrowphase/ExpandingSimplex" to JvmApiSpec(packageType = true),
    "org/dyn4j/collision/narrowphase/MinkowskiSumPoint" to JvmApiSpec(
        packageFields = setOf("supportPoint1", "supportPoint2", "point")
    ),
    "org/dyn4j/collision/narrowphase/MinkowskiSum" to JvmApiSpec(
        packageFields = setOf("convex1", "convex2", "transform1", "transform2")
    ),
    "org/dyn4j/collision/narrowphase/AbstractFallbackCondition" to JvmApiSpec(
        packageFields = setOf("sortIndex")
    ),
    "org/dyn4j/collision/narrowphase/FallbackNarrowphaseDetector" to JvmApiSpec(
        protectedFields = setOf("primaryNarrowphaseDetector", "fallbackNarrowphaseDetector", "fallbackConditions")
    ),
    "org/dyn4j/collision/narrowphase/Penetration" to JvmApiSpec(protectedFields = setOf("normal", "depth")),
    "org/dyn4j/collision/narrowphase/Separation" to JvmApiSpec(
        protectedFields = setOf("normal", "distance", "point1", "point2")
    ),
    "org/dyn4j/collision/narrowphase/Raycast" to JvmApiSpec(
        protectedFields = setOf("point", "normal", "distance")
    ),
    "org/dyn4j/collision/narrowphase/Containment" to JvmApiSpec(
        protectedFields = setOf("aContainedInB", "bContainedInA")
    ),
    "org/dyn4j/collision/narrowphase/CircleDetector" to JvmApiSpec(
        staticMethods = setOf("detect", "distance", "contains", "raycast")
    ),
    "org/dyn4j/collision/narrowphase/SegmentDetector" to JvmApiSpec(staticMethods = setOf("raycast")),
    "org/dyn4j/collision/narrowphase/Epa" to JvmApiSpec(
        protectedFields = setOf("maxIterations", "distanceEpsilon")
    ),
    "org/dyn4j/collision/narrowphase/Gjk" to JvmApiSpec(
        protectedFields = setOf(
            "minkowskiPenetrationSolver", "maxDetectIterations", "maxDistanceIterations",
            "maxRaycastIterations", "detectEpsilon", "distanceEpsilon", "raycastEpsilon"
        )
    ),
    "org/dyn4j/collision/manifold/IndexedManifoldPointId" to JvmApiSpec(
        protectedFields = setOf("referenceEdgeIndex", "incidentEdgeIndex", "incidentVertexIndex", "flipped")
    ),
    "org/dyn4j/collision/manifold/ManifoldPoint" to JvmApiSpec(
        protectedFields = setOf("id", "point", "depth"),
        protectedConstructorDescriptors = setOf("(Lorg/dyn4j/collision/manifold/ManifoldPointId;Lorg/dyn4j/geometry/Vector2;D)V")
    ),
    "org/dyn4j/collision/manifold/Manifold" to JvmApiSpec(protectedFields = setOf("points", "normal")),
    "org/dyn4j/collision/continuous/TimeOfImpact" to JvmApiSpec(protectedFields = setOf("time", "separation")),
    "org/dyn4j/collision/continuous/ConservativeAdvancement" to JvmApiSpec(
        protectedFields = setOf("distanceDetector", "distanceEpsilon", "maxIterations")
    )
)

val patchJvmArchive: (File) -> Unit = { jar ->
        val temporary = jar.resolveSibling(jar.name + ".patched")
        ZipFile(jar).use { input ->
            val companionMethods = jvmApi.mapValues { (owner, spec) ->
                val entry = input.getEntry(owner + "\$Companion.class")
                if (entry == null) emptyList() else {
                    val methods = mutableListOf<Triple<String, String, String?>>()
                    ClassReader(input.getInputStream(entry).use { it.readBytes() }).accept(
                        object : ClassVisitor(Opcodes.ASM9) {
                            override fun visitMethod(
                                access: Int, name: String, descriptor: String,
                                signature: String?, exceptions: Array<out String>?
                            ): MethodVisitor? {
                                if (name in spec.staticMethods && access and Opcodes.ACC_PUBLIC != 0) {
                                    methods += Triple(name, descriptor, signature)
                                }
                                return null
                            }
                        },
                        ClassReader.SKIP_CODE or ClassReader.SKIP_DEBUG or ClassReader.SKIP_FRAMES
                    )
                    methods
                }
            }
            ZipOutputStream(temporary.outputStream().buffered()).use { output ->
                for (entry in input.entries().asSequence()) {
                    val owner = entry.name.removeSuffix(".class")
                    val bytes = input.getInputStream(entry).use { it.readBytes() }
                    val spec = if (entry.name.endsWith(".class")) jvmApi[owner] else null
                    val content = if (spec == null) bytes else {
                        val writer = ClassWriter(ClassWriter.COMPUTE_MAXS)
                        val visitor = object : ClassVisitor(Opcodes.ASM9, writer) {
                            val present = mutableSetOf<Pair<String, String>>()
                            override fun visit(
                                version: Int, access: Int, name: String, signature: String?,
                                superName: String?, interfaces: Array<out String>?
                            ) {
                                val visibility = Opcodes.ACC_PUBLIC or Opcodes.ACC_PROTECTED or Opcodes.ACC_PRIVATE
                                val revisedAccess = if (spec.packageType) access and visibility.inv() else access
                                val extra = if (spec.appendIterable) arrayOf("java/lang/Iterable") else emptyArray()
                                val revisedInterfaces = (interfaces.orEmpty().toList() + extra).distinct().toTypedArray()
                                var revisedSignature = signature?.replace(
                                    "Ljava/lang/Comparable<-TE;>;", "Ljava/lang/Comparable<TE;>;"
                                )
                                if (spec.appendIterable && revisedSignature?.contains("Ljava/lang/Iterable<TE;>;") != true) {
                                    revisedSignature += "Ljava/lang/Iterable<TE;>;"
                                }
                                super.visit(version, revisedAccess, name, revisedSignature, superName, revisedInterfaces)
                            }
                            override fun visitField(
                                access: Int, name: String, descriptor: String,
                                signature: String?, value: Any?
                            ): FieldVisitor {
                                val visibility = Opcodes.ACC_PUBLIC or Opcodes.ACC_PROTECTED or Opcodes.ACC_PRIVATE
                                val revised = when (name) {
                                    in spec.publicFields -> (access and visibility.inv()) or Opcodes.ACC_PUBLIC
                                    in spec.protectedFields -> (access and visibility.inv()) or Opcodes.ACC_PROTECTED
                                    in spec.packageFields -> access and visibility.inv()
                                    else -> access
                                }
                                return super.visitField(revised, name, descriptor, signature, value)
                            }
                            override fun visitMethod(
                                access: Int, name: String, descriptor: String,
                                signature: String?, exceptions: Array<out String>?
                            ): MethodVisitor {
                                present += name to descriptor
                                val visibility = Opcodes.ACC_PUBLIC or Opcodes.ACC_PROTECTED or Opcodes.ACC_PRIVATE
                                val isVararg = name in spec.varargMethods &&
                                    Type.getArgumentTypes(descriptor).lastOrNull()?.sort == Type.ARRAY
                                var revised = if (isVararg) access or Opcodes.ACC_VARARGS else access
                                if (name in spec.packageMethods || name + descriptor in spec.packageMethodSignatures ||
                                    (spec.packageNodeMethods && descriptor.startsWith("(Lorg/dyn4j/BinarySearchTreeNode;")) ||
                                    (name == "<init>" && descriptor in spec.packageConstructorDescriptors)) {
                                    revised = revised and visibility.inv() and Opcodes.ACC_FINAL.inv()
                                }
                                if (name in spec.protectedMethods) {
                                    revised = ((revised and visibility.inv()) or Opcodes.ACC_PROTECTED) and Opcodes.ACC_FINAL.inv()
                                }
                                if (name == "<init>" && descriptor in spec.protectedConstructorDescriptors) {
                                    revised = (revised and visibility.inv()) or Opcodes.ACC_PROTECTED
                                }
                                if (owner == "org/dyn4j/BinarySearchTreeNode" && name == "getComparable") {
                                    revised = revised and Opcodes.ACC_FINAL.inv()
                                }
                                if (owner.startsWith("org/dyn4j/geometry/") && name != "<init>" &&
                                    access and Opcodes.ACC_STATIC == 0 && access and Opcodes.ACC_PRIVATE == 0
                                ) revised = revised and Opcodes.ACC_FINAL.inv()
                                val revisedSignature = signature?.replace(
                                    "Ljava/lang/Comparable<-TE;>;", "Ljava/lang/Comparable<TE;>;"
                                )
                                val method = super.visitMethod(revised, name, descriptor, revisedSignature, exceptions)
                                // The baseline permits a null center in this protected constructor.
                                if (owner == "org/dyn4j/geometry/AbstractShape" && name == "<init>" &&
                                    descriptor == "(Lorg/dyn4j/geometry/Vector2;D)V") {
                                    return object : MethodVisitor(Opcodes.ASM9, method) {
                                        override fun visitMethodInsn(
                                            opcode: Int, methodOwner: String, methodName: String,
                                            methodDescriptor: String, isInterface: Boolean
                                        ) {
                                            if (methodOwner == "kotlin/jvm/internal/Intrinsics" &&
                                                methodName == "checkNotNullParameter") {
                                                super.visitInsn(Opcodes.POP)
                                                super.visitInsn(Opcodes.POP)
                                            } else {
                                                super.visitMethodInsn(
                                                    opcode, methodOwner, methodName, methodDescriptor, isInterface
                                                )
                                            }
                                        }
                                    }
                                }
                                return method
                            }
                            override fun visitEnd() {
                                for ((name, descriptor, signature) in companionMethods[owner].orEmpty()) {
                                    if ((name to descriptor) in present) continue
                                    val visibility = if (name in spec.packageMethods ||
                                        name + descriptor in spec.packageMethodSignatures) 0 else Opcodes.ACC_PUBLIC
                                    val method = super.visitMethod(
                                        visibility or Opcodes.ACC_STATIC or
                                            (if (owner == "org/dyn4j/Version") Opcodes.ACC_FINAL else 0) or
                                            (if (name in spec.varargMethods &&
                                                Type.getArgumentTypes(descriptor).lastOrNull()?.sort == Type.ARRAY
                                            ) Opcodes.ACC_VARARGS else 0),
                                        name, descriptor,
                                        signature?.replace("+Lorg/dyn4j/geometry/", "Lorg/dyn4j/geometry/"),
                                        null
                                    )
                                    method.visitCode()
                                    method.visitFieldInsn(
                                        Opcodes.GETSTATIC, owner, "Companion", "L" + owner + "\$Companion;"
                                    )
                                    var index = 0
                                    for (argument in Type.getArgumentTypes(descriptor)) {
                                        method.visitVarInsn(argument.getOpcode(Opcodes.ILOAD), index)
                                        index += argument.size
                                    }
                                    method.visitMethodInsn(
                                        Opcodes.INVOKEVIRTUAL, owner + "\$Companion",
                                        name, descriptor, false
                                    )
                                    method.visitInsn(Type.getReturnType(descriptor).getOpcode(Opcodes.IRETURN))
                                    method.visitMaxs(0, 0)
                                    method.visitEnd()
                                }
                                super.visitEnd()
                            }
                        }
                        ClassReader(bytes).accept(visitor, 0)
                        writer.toByteArray()
                    }
                    val replacement = ZipEntry(entry.name)
                    replacement.time = entry.time
                    output.putNextEntry(replacement)
                    output.write(content)
                    output.closeEntry()
                }
            }
        }
        Files.move(temporary.toPath(), jar.toPath(), StandardCopyOption.REPLACE_EXISTING)
}

tasks.withType<Jar>().configureEach {
    if (name == "jvmJar") doLast { patchJvmArchive(archiveFile.get().asFile) }
}

tasks.matching {
    it.name == "bundleAndroidMainClassesToCompileJar" ||
        it.name == "bundleAndroidMainClassesToRuntimeJar" ||
        it.name == "syncAndroidMainLibJars"
}.configureEach {
    doLast {
        outputs.files.files.flatMap { output ->
            if (output.isDirectory) output.walkTopDown().filter { it.extension == "jar" }.toList()
            else listOf(output)
        }.filter { it.extension == "jar" && ZipFile(it).use { zip ->
            zip.getEntry("org/dyn4j/geometry/Vector2.class") != null
        } }.forEach(patchJvmArchive)
    }
}

kotlin {
    jvmToolchain(21)
    jvm {
        compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) }
    }
    android {
        namespace = "org.dyn4j"
        compileSdk = 36
        minSdk = 21
        withHostTest {}
        compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) }
    }
    js { nodejs() }
    wasmJs { nodejs() }
    wasmWasi { nodejs() }
    linuxX64()
    linuxArm64()
    mingwX64()
    macosArm64()
    iosArm64()
    iosSimulatorArm64()
    iosX64()
    tvosArm64()
    tvosSimulatorArm64()
    watchosArm64()
    watchosDeviceArm64()
    watchosSimulatorArm64()
    androidNativeArm32()
    androidNativeArm64()
    androidNativeX86()
    androidNativeX64()

    sourceSets {
        commonTest.dependencies { implementation(kotlin("test")) }
    }
}

publishing {
    publications.withType<MavenPublication>().configureEach {
        artifact(rootProject.file("LICENSE.md")) {
            classifier = "license"
            extension = "md"
        }
        pom {
            name = "dyn4k core"
            description = "Kotlin Multiplatform dyn4j 6.0.0 compatible foundation"
            url = "https://github.com/rubixhacker/dyn4k"
            licenses {
                license {
                    name = "BSD 3-Clause License"
                    url = "https://opensource.org/licenses/BSD-3-Clause"
                }
            }
            scm { url = "https://github.com/rubixhacker/dyn4k" }
            developers { developer { id = "rubixhacker"; name = "Stewart Boling" } }
        }
    }
    repositories { maven { name = "staging"; url = uri(rootProject.layout.buildDirectory.dir("staging-repository")) } }
}

tasks.withType<Jar>().configureEach {
    from(rootProject.file("LICENSE.md")) { into("META-INF") }
}

val baseline = configurations.create("baselineOracle")
dependencies { baseline("org.dyn4j:dyn4j:6.0.0") }
val baselineSources = configurations.create("baselineSources")
dependencies { baselineSources("org.dyn4j:dyn4j:6.0.0:sources") }
val upstreamTestRuntime = configurations.create("upstreamTestRuntime")
dependencies { upstreamTestRuntime("junit:junit:4.13.1") }

val verifyBaseline by tasks.registering {
    val files = baseline
    inputs.files(files)
    doLast {
        val jar = files.singleFile
        val digest = MessageDigest.getInstance("SHA-256").digest(jar.readBytes())
            .joinToString("") { "%02x".format(it) }
        check(digest == "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e") {
            "dyn4j 6.0.0 binary SHA-256 differs: $digest"
        }
        println("Baseline SHA-256 verified: $digest")
    }
}

tasks.register("verifyBaselineSources") {
    val files = baselineSources
    inputs.files(files)
    doLast {
        val jar = files.singleFile
        val digest = MessageDigest.getInstance("SHA-256").digest(jar.readBytes())
            .joinToString("") { "%02x".format(it) }
        check(digest == "83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223") {
            "dyn4j 6.0.0 sources SHA-256 differs: $digest"
        }
        println("Baseline sources SHA-256 verified: $digest")
    }
}

val javaConsumerSource = file("src/jvmConsumer/java/FoundationConsumer.java")
val baselineConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(javaConsumerSource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/baseline"))
    options.release.set(8)
}

val jvmMain = kotlin.targets.getByName("jvm").compilations.getByName("main")
tasks.register<Exec>("verifyJvmApi") {
    dependsOn(verifyBaseline, tasks.named("jvmJar"))
    doFirst {
        commandLine(
            "python3",
            rootProject.file("scripts/verify-foundation-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            tasks.named<Jar>("jvmJar").get().archiveFile.get().asFile.absolutePath
        )
    }
}
tasks.register<Exec>("verifyGeometryJvmApi") {
    dependsOn(verifyBaseline, tasks.named("jvmJar"))
    doFirst {
        commandLine(
            "python3", rootProject.file("scripts/verify-geometry-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            tasks.named<Jar>("jvmJar").get().archiveFile.get().asFile.absolutePath
        )
    }
}
tasks.register<Exec>("verifyTreeJvmApi") {
    dependsOn(verifyBaseline, tasks.named("jvmJar"))
    doFirst {
        commandLine(
            "python3",
            rootProject.file("scripts/verify-tree-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            tasks.named<Jar>("jvmJar").get().archiveFile.get().asFile.absolutePath
        )
    }
}
val candidateConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(javaConsumerSource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/candidate"))
    options.release.set(8)
}

tasks.register<JavaExec>("runBaselineConsumer") {
    dependsOn(baselineConsumer)
    classpath(baselineConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("FoundationConsumer")
}

tasks.register<JavaExec>("runCandidateConsumer") {
    dependsOn(candidateConsumer)
    classpath(candidateConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("FoundationConsumer")
}

val geometryConsumerSource = fileTree("src/jvmConsumer/java") {
    include("GeometryConsumer.java", "org/dyn4j/geometry/GeometryPackageConsumer.java")
}
val baselineGeometryConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(geometryConsumerSource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("geometry-consumer/baseline"))
    options.release.set(8)
}
val candidateGeometryConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(geometryConsumerSource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("geometry-consumer/candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineGeometryConsumer") {
    dependsOn(baselineGeometryConsumer)
    classpath(baselineGeometryConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("GeometryConsumer")
}
tasks.register<JavaExec>("runCandidateGeometryConsumer") {
    dependsOn(candidateGeometryConsumer)
    classpath(candidateGeometryConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("GeometryConsumer")
}

repositories {
    google()
    mavenCentral()
    maven { name = "stagedGeometryConsumer"; url = uri(rootProject.layout.buildDirectory.dir("staging-repository")) }
}
val stagedGeometryClasspath = configurations.create("stagedGeometryClasspath")
dependencies { stagedGeometryClasspath("io.github.rubixhacker:dyn4k-jvm:${project.version}") }
val stagedGeometryConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    source(geometryConsumerSource)
    classpath = stagedGeometryClasspath
    destinationDirectory.set(layout.buildDirectory.dir("geometry-consumer/staged"))
    options.release.set(8)
}
tasks.register<JavaExec>("runStagedGeometryConsumer") {
    dependsOn(stagedGeometryConsumer)
    classpath(stagedGeometryConsumer.flatMap { it.destinationDirectory }, stagedGeometryClasspath)
    mainClass.set("GeometryConsumer")
}

val androidCompileJar = tasks.matching { it.name == "bundleAndroidMainClassesToCompileJar" }
val androidRuntimeJar = tasks.matching { it.name == "bundleAndroidMainClassesToRuntimeJar" }
val androidCandidateConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(androidCompileJar)
    source(javaConsumerSource)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/android-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidCandidateConsumer") {
    dependsOn(androidCandidateConsumer, androidRuntimeJar)
    classpath(
        androidCandidateConsumer.flatMap { it.destinationDirectory },
        androidRuntimeJar,
        jvmMain.runtimeDependencyFiles
    )
    mainClass.set("FoundationConsumer")
}

val treeConsumerSources = files("src/jvmConsumer/java/TreeConsumer.java", "src/jvmConsumer/java/org/dyn4j/TreePackageConsumer.java")
val baselineTreeConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(treeConsumerSources)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/tree-baseline"))
    options.release.set(8)
}
val candidateTreeConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(treeConsumerSources)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/tree-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineTreeConsumer") {
    dependsOn(baselineTreeConsumer)
    classpath(baselineTreeConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("TreeConsumer")
}
tasks.register<JavaExec>("runBaselineTreePackageConsumer") {
    dependsOn(baselineTreeConsumer)
    classpath(baselineTreeConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("org.dyn4j.TreePackageConsumer")
}
tasks.register<JavaExec>("runCandidateTreePackageConsumer") {
    dependsOn(candidateTreeConsumer)
    classpath(candidateTreeConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("org.dyn4j.TreePackageConsumer")
}
tasks.register<JavaExec>("runCandidateTreeConsumer") {
    dependsOn(candidateTreeConsumer)
    classpath(candidateTreeConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("TreeConsumer")
}
val androidCandidateTreeConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(androidCompileJar)
    source(treeConsumerSources)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/tree-android-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidCandidateTreeConsumer") {
    dependsOn(androidCandidateTreeConsumer, androidRuntimeJar)
    classpath(androidCandidateTreeConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("TreeConsumer")
}
tasks.register<JavaExec>("runAndroidCandidateTreePackageConsumer") {
    dependsOn(androidCandidateTreeConsumer, androidRuntimeJar)
    classpath(androidCandidateTreeConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("org.dyn4j.TreePackageConsumer")
}

val upstreamCheckout = layout.buildDirectory.dir("upstream-dyn4j")
val foundationTestNames = listOf(
    "Vector2Test", "Vector3Test", "RotationTest", "Matrix22Test",
    "Matrix33Test", "TransformTest"
)
val fetchUpstreamTests by tasks.registering(Exec::class) {
    outputs.dir(upstreamCheckout)
    outputs.upToDateWhen { false }
    commandLine(
        rootProject.file("scripts/fetch-upstream-tests.sh").absolutePath,
        upstreamCheckout.get().asFile.absolutePath
    )
}
val compileUpstreamFoundationTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(foundationTestNames.map {
        upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/geometry/$it.java") }
    })
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamFoundationTests") {
    dependsOn(compileUpstreamFoundationTests)
    classpath(
        compileUpstreamFoundationTests.flatMap { it.destinationDirectory },
        tasks.named("jvmJar"),
        jvmMain.runtimeDependencyFiles,
        upstreamTestRuntime
    )
    mainClass.set("org.junit.runner.JUnitCore")
    args(foundationTestNames.map { "org.dyn4j.geometry.$it" })
}

val geometryTestNames = listOf(
    "AABBTest", "AbstractShapeTest", "IntervalTest", "RayTest", "CircleTest", "FeatureTest",
    "PolygonTest", "RectangleTest", "MassTest", "TriangleTest", "SegmentTest", "WoundTest", "LinkTest",
    "AdaptiveDecimalTest", "RobustGeometryTest", "CapsuleTest", "EllipseTest", "HalfEllipseTest", "SliceTest",
    "GeometryTest"
)
val compileUpstreamGeometryTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(geometryTestNames.map {
        upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/geometry/$it.java") }
    })
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-geometry-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamGeometryTests") {
    dependsOn(compileUpstreamGeometryTests)
    classpath(
        compileUpstreamGeometryTests.flatMap { it.destinationDirectory },
        tasks.named("jvmJar"),
        jvmMain.runtimeDependencyFiles,
        upstreamTestRuntime
    )
    mainClass.set("org.junit.runner.JUnitCore")
    args(geometryTestNames.map { "org.dyn4j.geometry.$it" })
}
val treeTestNames = listOf("AVLTreeTest", "ReferenceTest", "VersionTest")
val compileUpstreamTreeTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(treeTestNames.map { upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/$it.java") } })
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-tree-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamTreeTests") {
    dependsOn(compileUpstreamTreeTests)
    classpath(compileUpstreamTreeTests.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(treeTestNames.map { "org.dyn4j.$it" })
}

val collisionModelTestNames = listOf(
    "AbstractBoundsTest", "AbstractCollisionBodyTest", "AbstractCollisionItemTest",
    "AbstractCollisionPairCollisionBodyTest", "AbstractCollisionPairCollisionItemTest",
    "AxisAlignedBoundsTest", "BasicCollisionItemTest", "BasicCollisionPairCollisionBodyTest",
    "BasicCollisionPairCollisionItemTest", "CategoryFilterTest", "CollisionsTest",
    "DefaultFilterTest", "FixtureTest", "TypeFilterTest"
)
val compileUpstreamCollisionModelTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(collisionModelTestNames.map {
        upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/collision/$it.java") }
    })
    source(upstreamCheckout.map { it.file("src/test/java/org/dyn4j/collision/TestCollisionBody.java") })
    source(upstreamCheckout.map { it.file("src/test/java/org/dyn4j/UnitConversionTest.java") })
    source(upstreamCheckout.map { it.file("src/test/java/org/dyn4j/exception/ExceptionsTest.java") })
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-collision-model-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamCollisionModelTests") {
    dependsOn(compileUpstreamCollisionModelTests)
    classpath(
        compileUpstreamCollisionModelTests.flatMap { it.destinationDirectory },
        tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime
    )
    mainClass.set("org.junit.runner.JUnitCore")
    args(collisionModelTestNames.map { "org.dyn4j.collision.$it" } +
        listOf("org.dyn4j.UnitConversionTest", "org.dyn4j.exception.ExceptionsTest"))
}

val detectionTestPackages = listOf("broadphase", "narrowphase", "manifold", "continuous")
val compileUpstreamDetectionTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    val testRoot = upstreamCheckout.get().asFile.resolve("src/test/java/org/dyn4j/collision")
    detectionTestPackages.forEach { packageName ->
        source(fileTree(testRoot.resolve(packageName)) { include("*Test.java") })
    }
    source(upstreamCheckout.map { it.file("src/test/java/org/dyn4j/collision/TestCollisionBody.java") })
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-detection-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamDetectionTests") {
    dependsOn(compileUpstreamDetectionTests)
    classpath(compileUpstreamDetectionTests.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    doFirst {
        val testRoot = upstreamCheckout.get().asFile.resolve("src/test/java/org/dyn4j/collision")
        args(detectionTestPackages.flatMap { packageName ->
            testRoot.resolve(packageName).listFiles().orEmpty().filter { it.name.endsWith("Test.java") }
                .sortedBy { it.name }.map { "org.dyn4j.collision.$packageName.${it.name.removeSuffix(".java")}" }
        })
    }
}
val compileUpstreamDetectionAndroidTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, androidCompileJar)
    val testRoot = upstreamCheckout.get().asFile.resolve("src/test/java/org/dyn4j/collision")
    detectionTestPackages.forEach { packageName ->
        source(fileTree(testRoot.resolve(packageName)) { include("*Test.java") })
    }
    source(upstreamCheckout.map { it.file("src/test/java/org/dyn4j/collision/TestCollisionBody.java") })
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-detection-android-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamDetectionAndroidTests") {
    dependsOn(compileUpstreamDetectionAndroidTests, androidRuntimeJar)
    classpath(compileUpstreamDetectionAndroidTests.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    doFirst {
        val testRoot = upstreamCheckout.get().asFile.resolve("src/test/java/org/dyn4j/collision")
        args(detectionTestPackages.flatMap { packageName ->
            testRoot.resolve(packageName).listFiles().orEmpty().filter { it.name.endsWith("Test.java") }
                .sortedBy { it.name }.map { "org.dyn4j.collision.$packageName.${it.name.removeSuffix(".java")}" }
        })
    }
}

tasks.register<Exec>("verifyDetectionJvmApi") {
    dependsOn(verifyBaseline, tasks.named("jvmJar"))
    doFirst {
        commandLine(
            "python3", rootProject.file("scripts/verify-detection-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            tasks.named<Jar>("jvmJar").get().archiveFile.get().asFile.absolutePath
        )
    }
}
tasks.register<Exec>("verifyDetectionAndroidApi") {
    dependsOn(verifyBaseline, androidCompileJar)
    doFirst {
        commandLine(
            "python3", rootProject.file("scripts/verify-detection-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            layout.buildDirectory.file("intermediates/compile_library_classes_jar/androidMain/bundleAndroidMainClassesToCompileJar/classes.jar").get().asFile.absolutePath
        )
    }
}

val detectionConsumerSource = file("src/jvmConsumer/java/DetectionConsumer.java")
val baselineDetectionConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(detectionConsumerSource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/detection-baseline"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineDetectionConsumer") {
    dependsOn(baselineDetectionConsumer)
    classpath(baselineDetectionConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("DetectionConsumer")
}
val candidateDetectionConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(detectionConsumerSource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/detection-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runCandidateDetectionConsumer") {
    dependsOn(candidateDetectionConsumer)
    classpath(candidateDetectionConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("DetectionConsumer")
}
val stagedDetectionConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    source(detectionConsumerSource)
    classpath = stagedGeometryClasspath
    destinationDirectory.set(layout.buildDirectory.dir("consumer/detection-staged"))
    options.release.set(8)
}
tasks.register<JavaExec>("runStagedDetectionConsumer") {
    dependsOn(stagedDetectionConsumer)
    classpath(stagedDetectionConsumer.flatMap { it.destinationDirectory }, stagedGeometryClasspath)
    mainClass.set("DetectionConsumer")
}
val stagedKotlinDetectionClasses = layout.buildDirectory.dir("consumer/detection-kotlin-staged")
val stagedKotlinDetectionConsumer by tasks.registering(JavaExec::class) {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    classpath(configurations.getByName("kotlinCompilerClasspath"))
    mainClass.set("org.jetbrains.kotlin.cli.jvm.K2JVMCompiler")
    outputs.dir(stagedKotlinDetectionClasses)
    doFirst {
        stagedKotlinDetectionClasses.get().asFile.mkdirs()
        args(
            "-no-stdlib", "-no-reflect", "-jvm-target", "1.8",
            "-classpath", stagedGeometryClasspath.asPath,
            "-d", stagedKotlinDetectionClasses.get().asFile.absolutePath,
            file("src/jvmConsumer/kotlin/DetectionKotlinConsumer.kt").absolutePath
        )
    }
}
tasks.register<JavaExec>("runStagedKotlinDetectionConsumer") {
    dependsOn(stagedKotlinDetectionConsumer)
    classpath(stagedKotlinDetectionClasses, stagedGeometryClasspath)
    mainClass.set("DetectionKotlinConsumerKt")
}
val androidDetectionConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(androidCompileJar)
    source(detectionConsumerSource)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/detection-android"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidDetectionConsumer") {
    dependsOn(androidDetectionConsumer, androidRuntimeJar)
    classpath(androidDetectionConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("DetectionConsumer")
}

val collisionModelConsumerSource = file("src/jvmConsumer/java/CollisionModelConsumer.java")
val baselineCollisionModelConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(collisionModelConsumerSource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/collision-model-baseline"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineCollisionModelConsumer") {
    dependsOn(baselineCollisionModelConsumer)
    classpath(baselineCollisionModelConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("CollisionModelConsumer")
}
val candidateCollisionModelConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(collisionModelConsumerSource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/collision-model-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runCandidateCollisionModelConsumer") {
    dependsOn(candidateCollisionModelConsumer)
    classpath(candidateCollisionModelConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("CollisionModelConsumer")
}
val stagedCollisionModelConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    source(collisionModelConsumerSource)
    classpath = stagedGeometryClasspath
    destinationDirectory.set(layout.buildDirectory.dir("consumer/collision-model-staged"))
    options.release.set(8)
}
tasks.register<JavaExec>("runStagedCollisionModelConsumer") {
    dependsOn(stagedCollisionModelConsumer)
    classpath(stagedCollisionModelConsumer.flatMap { it.destinationDirectory }, stagedGeometryClasspath)
    mainClass.set("CollisionModelConsumer")
}
val androidCollisionModelConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(androidCompileJar)
    source(collisionModelConsumerSource)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/collision-model-android"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidCollisionModelConsumer") {
    dependsOn(androidCollisionModelConsumer, androidRuntimeJar)
    classpath(androidCollisionModelConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("CollisionModelConsumer")
}
