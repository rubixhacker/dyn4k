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
import org.objectweb.asm.Label
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
    val nonFinalStaticMethods: Set<String> = emptySet(),
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
        publicFields = setOf("x", "y"),
        packageFields = setOf("X_AXIS", "Y_AXIS", "INV_X_AXIS", "INV_Y_AXIS"),
        packageMethodSignatures = setOf(
            "rotate(DD)Lorg/dyn4j/geometry/Vector2;",
            "rotate(DDDD)Lorg/dyn4j/geometry/Vector2;"
        ),
        staticMethods = setOf("create", "tripleProduct")
    ),
    "org/dyn4j/geometry/Vector3" to JvmApiSpec(
        publicFields = setOf("x", "y", "z"), staticMethods = setOf("tripleProduct")
    ),
    "org/dyn4j/geometry/Rotation" to JvmApiSpec(
        protectedFields = setOf("cost", "sint"),
        packageMethodSignatures = setOf(
            "rotate45Helper(DD)Lorg/dyn4j/geometry/Rotation;",
            "getRotated45Helper(DD)Lorg/dyn4j/geometry/Rotation;",
            "rotate(DD)Lorg/dyn4j/geometry/Rotation;",
            "dot(Lorg/dyn4j/geometry/Vector2;)D",
            "cross(Lorg/dyn4j/geometry/Vector2;)D"
        ),
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
        protectedFields = setOf("cost", "sint", "x", "y"),
        packageMethodSignatures = setOf("rotate(DD)V", "rotate(DDDD)V")
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
        protectedFields = setOf("vertices", "normals"),
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
        protectedFields = setOf(
            "length", "capRadius", "foci", "localXAxis",
            "EDGE_FEATURE_SELECTION_CRITERIA", "EDGE_FEATURE_EXPANSION_FACTOR"
        )
    ),
    "org/dyn4j/geometry/Ellipse" to JvmApiSpec(
        protectedFields = setOf("halfWidth", "halfHeight", "rotation"),
        staticMethods = setOf("getFarthestPointOnEllipse", "getFarthestPointOnBoundedEllipse"),
        packageMethods = setOf("getFarthestPointOnEllipse", "getFarthestPointOnBoundedEllipse")
    ),
    "org/dyn4j/geometry/HalfEllipse" to JvmApiSpec(
        protectedFields = setOf("height", "halfWidth", "rotation", "ellipseCenter", "vertexLeft", "vertexRight")
    ),
    "org/dyn4j/geometry/Slice" to JvmApiSpec(
        protectedFields = setOf("alpha", "cosAlpha", "sliceRadius", "vertices", "normals", "rotation")
    ),
    "org/dyn4j/geometry/Segment" to JvmApiSpec(
        protectedFields = setOf("vertices", "normals", "length"),
        staticMethods = setOf(
            "getLocation", "getPointOnLineClosestToPoint", "getPointOnSegmentClosestToPoint",
            "getLineIntersection", "getSegmentIntersection", "getFarthestFeature", "getFarthestPoint"
        )
    ),
    "org/dyn4j/geometry/Link" to JvmApiSpec(
        packageFields = setOf("point0", "point3")
    ),
    "org/dyn4j/collision/AbstractCollisionItem" to JvmApiSpec(
        nonFinalStaticMethods = setOf("getHashCode", "equals")
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
    ),
    "org/dyn4j/dynamics/joint/AbstractJoint" to JvmApiSpec(
        protectedFields = setOf("bodies", "collisionAllowed", "userData", "owner"),
        staticMethods = setOf(
            "getFrequency", "getNaturalFrequency", "getSpringDampingCoefficient", "getSpringStiffness",
            "getConstraintImpulseMixing", "getErrorReductionParameter"
        ),
        protectedMethods = setOf(
            "getFrequency", "getNaturalFrequency", "getSpringDampingCoefficient", "getSpringStiffness",
            "getConstraintImpulseMixing", "getErrorReductionParameter"
        )
    ),
    "org/dyn4j/dynamics/joint/AbstractPairedBodyJoint" to JvmApiSpec(protectedFields = setOf("body1", "body2")),
    "org/dyn4j/dynamics/joint/AbstractSingleBodyJoint" to JvmApiSpec(protectedFields = setOf("body")),
    "org/dyn4j/dynamics/joint/AngleJoint" to JvmApiSpec(
        protectedFields = setOf("ratio", "limitsEnabled", "lowerLimit", "upperLimit", "referenceAngle"),
        packageFields = setOf(
            "limitOffset", "adjustedLowerLimit", "adjustedUpperLimit", "angle", "axialMass",
            "fixedRotation", "impulse", "lowerLimitImpulse", "upperLimitImpulse"
        )
    ),
    "org/dyn4j/dynamics/joint/DistanceJoint" to JvmApiSpec(
        protectedFields = setOf(
            "localAnchor1", "localAnchor2", "restDistance", "springEnabled", "springMode",
            "springFrequency", "springStiffness", "springDamperEnabled", "springDampingRatio",
            "springMaximumForceEnabled", "springMaximumForce", "upperLimit", "lowerLimit",
            "upperLimitEnabled", "lowerLimitEnabled"
        ),
        packageFields = setOf(
            "currentDistance", "damping", "n", "gamma", "bias", "mass", "softMass", "impulse",
            "upperLimitImpulse", "lowerLimitImpulse"
        )
    ),
    "org/dyn4j/dynamics/joint/FrictionJoint" to JvmApiSpec(
        protectedFields = setOf("localAnchor1", "localAnchor2", "maximumForce", "maximumTorque"),
        packageFields = setOf("K", "angularMass", "linearImpulse", "angularImpulse")
    ),
    "org/dyn4j/dynamics/joint/MotorJoint" to JvmApiSpec(
        protectedFields = setOf("linearTarget", "angularTarget", "correctionFactor", "maximumForce", "maximumTorque"),
        packageFields = setOf("r1", "r2", "K", "angularMass", "linearError", "angularError", "linearImpulse", "angularImpulse")
    ),
    "org/dyn4j/dynamics/joint/PinJoint" to JvmApiSpec(
        protectedFields = setOf(
            "target", "localAnchor", "springEnabled", "springMode", "springFrequency", "springStiffness",
            "springDamperEnabled", "springDampingRatio", "springMaximumForceEnabled", "springMaximumForce",
            "correctionFactor", "correctionMaximumForce"
        ),
        packageFields = setOf("r", "damping", "bias", "gamma", "K", "linearError", "impulse")
    ),
    "org/dyn4j/dynamics/joint/PrismaticJoint" to JvmApiSpec(
        protectedFields = setOf(
            "localAnchor1", "localAnchor2", "xAxis", "yAxis", "referenceAngle", "upperLimitEnabled",
            "lowerLimitEnabled", "upperLimit", "lowerLimit", "motorEnabled", "motorSpeed",
            "maximumMotorForceEnabled", "maximumMotorForce", "springEnabled", "springDamperEnabled",
            "springMode", "springFrequency", "springStiffness", "springDampingRatio",
            "springMaximumForceEnabled", "springMaximumForce", "springRestOffset"
        ),
        packageFields = setOf(
            "damping", "bias", "gamma", "K", "axialMass", "springMass", "perp", "axis", "s1",
            "s2", "a1", "a2", "translation", "impulse", "springImpulse", "motorImpulse",
            "lowerLimitImpulse", "upperLimitImpulse"
        )
    ),
    "org/dyn4j/dynamics/joint/PulleyJoint" to JvmApiSpec(
        protectedFields = setOf("pulleyAnchor1", "pulleyAnchor2", "localAnchor1", "localAnchor2", "ratio", "slackEnabled"),
        packageFields = setOf("overLength", "length", "n1", "n2", "invK", "impulse")
    ),
    "org/dyn4j/dynamics/joint/RevoluteJoint" to JvmApiSpec(
        protectedFields = setOf(
            "localAnchor1", "localAnchor2", "limitsEnabled", "lowerLimit", "upperLimit", "referenceAngle",
            "limitOffset", "adjustedLowerLimit", "adjustedUpperLimit", "motorEnabled", "motorSpeed",
            "motorMaximumTorqueEnabled", "motorMaximumTorque"
        ),
        packageFields = setOf(
            "angle", "axialMass", "fixedRotation", "r1", "r2", "K", "impulse", "motorImpulse",
            "lowerLimitImpulse", "upperLimitImpulse"
        )
    ),
    "org/dyn4j/dynamics/joint/WeldJoint" to JvmApiSpec(
        protectedFields = setOf(
            "localAnchor1", "localAnchor2", "limitsEnabled", "lowerLimit", "upperLimit", "referenceAngle",
            "limitOffset", "adjustedLowerLimit", "adjustedUpperLimit", "springEnabled", "springDamperEnabled",
            "springMode", "springFrequency", "springStiffness", "springDampingRatio",
            "springMaximumTorqueEnabled", "springMaximumTorque"
        ),
        packageFields = setOf(
            "angle", "r1", "r2", "K", "axialMass", "springMass", "damping", "bias", "gamma",
            "impulse", "springImpulse", "lowerLimitImpulse", "upperLimitImpulse"
        )
    ),
    "org/dyn4j/dynamics/joint/WheelJoint" to JvmApiSpec(
        protectedFields = setOf(
            "localAnchor1", "localAnchor2", "xAxis", "yAxis", "upperLimitEnabled", "lowerLimitEnabled",
            "upperLimit", "lowerLimit", "motorEnabled", "motorSpeed", "motorMaximumTorqueEnabled",
            "motorMaximumTorque", "springEnabled", "springDamperEnabled", "springMode", "springFrequency",
            "springStiffness", "springDampingRatio", "springMaximumForceEnabled", "springMaximumForce",
            "springRestOffset"
        ),
        packageFields = setOf(
            "damping", "bias", "gamma", "translation", "invK", "axialMass", "springMass",
            "motorMass", "wyAxis", "wxAxis", "s1y", "s2y", "s1x", "s2x", "impulse",
            "lowerLimitImpulse", "upperLimitImpulse", "springImpulse", "motorImpulse"
        )
    ),
    "org/dyn4j/world/Island" to JvmApiSpec(
        packageFields = setOf("bodies", "joints", "contactConstraints")
    ),
    "org/dyn4j/world/CollisionItemAdapter" to JvmApiSpec(packageType = true),
    "org/dyn4j/world/AbstractPhysicsWorld" to JvmApiSpec(
        protectedFields = setOf(
            "settings", "timeStep", "gravity", "valueMixer", "contactConstraintSolver",
            "timeOfImpactSolver", "ccdBroadphase", "joints", "jointsUnmodifiable",
            "contactListeners", "contactListenersUnmodifiable", "destructionListeners",
            "destructionListenersUnmodifiable", "timeOfImpactListeners", "timeOfImpactListenersUnmodifiable",
            "stepListeners", "stepListenersUnmodifiable", "time", "updateRequired",
            "constraintGraph", "contactCollisions", "ccdCollisionData"
        ),
        protectedMethods = setOf("handleFixtureRemoved", "handleAllFixturesRemoved")
    ),
    "org/dyn4j/world/World" to JvmApiSpec(protectedMethods = setOf("createCollisionData")),
    "org/dyn4j/world/result/DetectResult" to JvmApiSpec(protectedFields = setOf("body", "fixture")),
    "org/dyn4j/world/result/ConvexDetectResult" to JvmApiSpec(protectedFields = setOf("penetration")),
    "org/dyn4j/world/result/ConvexCastResult" to JvmApiSpec(protectedFields = setOf("timeOfImpact")),
    "org/dyn4j/world/result/RaycastResult" to JvmApiSpec(protectedFields = setOf("raycast")),
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
    ),
    "org/dyn4j/exception/CopyException" to JvmApiSpec(),
    "org/dyn4j/geometry/hull/HullGenerator" to JvmApiSpec(),
    "org/dyn4j/geometry/hull/AbstractHullGenerator" to JvmApiSpec(),
    "org/dyn4j/geometry/hull/MonotoneChain" to JvmApiSpec(),
    "org/dyn4j/geometry/hull/GrahamScan" to JvmApiSpec(),
    "org/dyn4j/geometry/hull/GiftWrap" to JvmApiSpec(),
    "org/dyn4j/geometry/hull/DivideAndConquer" to JvmApiSpec(packageMethods = setOf("divide")),
    "org/dyn4j/geometry/hull/LinkedVertex" to JvmApiSpec(
        packageType = true, packageFields = setOf("point", "next", "prev")
    ),
    "org/dyn4j/geometry/hull/LinkedVertexHull" to JvmApiSpec(
        packageType = true, packageFields = setOf("leftMost", "rightMost", "size"), staticMethods = setOf("merge")
    ),
    "org/dyn4j/geometry/hull/MinXYPointComparator" to JvmApiSpec(
        packageType = true, packageConstructorDescriptors = setOf("()V")
    ),
    "org/dyn4j/geometry/hull/ReferencePointComparator" to JvmApiSpec(
        packageType = true, packageFields = setOf("reference")
    ),
    "org/dyn4j/geometry/decompose/ClosestEdgeToVertexSearchCriteria" to JvmApiSpec(
        packageType = true, packageFields = setOf("vertex", "closest")
    ),
    "org/dyn4j/geometry/decompose/DoubleEdgeList" to JvmApiSpec(
        packageType = true, packageFields = setOf("vertices", "edges", "faces"),
        packageMethods = setOf("getReferenceFace", "getPreviousEdge", "getYMonotonePolygons", "triangulateYMonotonePolygon", "isReflex"),
        packageMethodSignatures = setOf(
            "addHalfEdges(Lorg/dyn4j/geometry/decompose/DoubleEdgeListVertex;Lorg/dyn4j/geometry/decompose/DoubleEdgeListVertex;)V",
            "removeHalfEdges(Lorg/dyn4j/geometry/decompose/DoubleEdgeListHalfEdge;)V",
            "removeHalfEdges(ILorg/dyn4j/geometry/decompose/DoubleEdgeListHalfEdge;)V"
        )
    ),
    "org/dyn4j/geometry/decompose/DoubleEdgeListFace" to JvmApiSpec(
        packageType = true, packageFields = setOf("edge"), packageConstructorDescriptors = setOf("()V")
    ),
    "org/dyn4j/geometry/decompose/DoubleEdgeListHalfEdge" to JvmApiSpec(
        packageType = true, packageFields = setOf("origin", "twin", "next", "face"),
        packageConstructorDescriptors = setOf("()V")
    ),
    "org/dyn4j/geometry/decompose/DoubleEdgeListVertex" to JvmApiSpec(
        packageType = true, packageFields = setOf("point", "leaving")
    ),
    "org/dyn4j/geometry/decompose/Decomposer" to JvmApiSpec(),
    "org/dyn4j/geometry/decompose/AbstractDecomposer" to JvmApiSpec(),
    "org/dyn4j/geometry/decompose/Bayazit" to JvmApiSpec(),
    "org/dyn4j/geometry/decompose/EarClipping" to JvmApiSpec(
        packageMethods = setOf("createTriangulation", "isReflex", "isEar"), varargMethods = setOf("createTriangulation")
    ),
    "org/dyn4j/geometry/decompose/EarClippingVertex" to JvmApiSpec(
        packageType = true, packageFields = setOf("point", "prev", "next", "ear", "reflex", "index")
    ),
    "org/dyn4j/geometry/decompose/MonotoneChainType" to JvmApiSpec(packageType = true),
    "org/dyn4j/geometry/decompose/MonotonePolygonType" to JvmApiSpec(packageType = true),
    "org/dyn4j/geometry/decompose/MonotonePolygon" to JvmApiSpec(
        packageType = true, packageFields = setOf("type", "vertices")
    ),
    "org/dyn4j/geometry/decompose/MonotoneVertex" to JvmApiSpec(
        packageType = true, packageFields = setOf("data", "next", "previous", "chainType")
    ),
    "org/dyn4j/geometry/decompose/SweepLine" to JvmApiSpec(
        packageMethods = setOf("createTriangulation", "start", "end", "split", "merge", "regular"),
        varargMethods = setOf("createTriangulation")
    ),
    "org/dyn4j/geometry/decompose/SweepLineEdge" to JvmApiSpec(
        packageType = true, packageFields = setOf("referenceY", "v0", "v1", "helper", "slope")
    ),
    "org/dyn4j/geometry/decompose/SweepLineState" to JvmApiSpec(
        packageType = true, packageFields = setOf("referenceY", "tree", "dcel"),
        packageMethods = setOf("getType")
    ),
    "org/dyn4j/geometry/decompose/SweepLineVertex" to JvmApiSpec(
        packageType = true, packageFields = setOf("point", "index", "type", "next", "prev", "left", "right"),
        packageMethods = setOf("isLeft")
    ),
    "org/dyn4j/geometry/decompose/SweepLineVertexType" to JvmApiSpec(packageType = true),
    "org/dyn4j/geometry/simplify/SegmentTree" to JvmApiSpec(
        packageType = true, packageConstructorDescriptors = setOf("()V")
    ),
    "org/dyn4j/geometry/simplify/Simplifier" to JvmApiSpec(),
    "org/dyn4j/geometry/simplify/AbstractSimplifier" to JvmApiSpec(varargMethods = setOf("simplify")),
    "org/dyn4j/geometry/simplify/VertexClusterReduction" to JvmApiSpec(),
    "org/dyn4j/geometry/simplify/DouglasPeucker" to JvmApiSpec(),
    "org/dyn4j/geometry/simplify/Visvalingam" to JvmApiSpec(),
    "org/dyn4j/geometry/simplify/SegmentTreeNode" to JvmApiSpec(
        packageType = true, packageFields = setOf("left", "right", "parent", "height", "aabb")
    ),
    "org/dyn4j/geometry/simplify/SegmentTreeLeaf" to JvmApiSpec(
        packageType = true, packageFields = setOf("point1", "point2", "index1", "index2")
    ),
    "org/dyn4j/geometry/simplify/SimplePolygonVertex" to JvmApiSpec(
        packageType = true, packageFields = setOf("index", "point", "prev", "next", "prevSegment", "nextSegment")
    ),
    "org/dyn4j/geometry/simplify/DouglasPeucker\$FarthestVertex" to JvmApiSpec(
        packageFields = setOf("index", "distance")
    ),
    "org/dyn4j/geometry/simplify/Visvalingam\$AreaTrackedVertex" to JvmApiSpec(
        packageFields = setOf("area")
    )
)

val baselineFinalPolygonMethods = mapOf(
    "org/dyn4j/geometry/hull/DivideAndConquer" to setOf("divide"),
    "org/dyn4j/geometry/hull/LinkedVertexHull" to setOf("toArray", "merge"),
    "org/dyn4j/geometry/decompose/DoubleEdgeList" to setOf(
        "addHalfEdges", "getPreviousEdge", "getReferenceFace", "removeHalfEdges",
        "triangulateYMonotonePolygon", "getYMonotonePolygons"
    ),
    "org/dyn4j/geometry/decompose/EarClipping" to setOf("createTriangulation", "isReflex", "isEar"),
    "org/dyn4j/geometry/decompose/SweepLine" to setOf(
        "createTriangulation", "start", "end", "split", "merge", "regular"
    ),
    "org/dyn4j/geometry/decompose/SweepLineState" to setOf("getType"),
    "org/dyn4j/geometry/decompose/SweepLineVertex" to setOf("isLeft"),
    "org/dyn4j/geometry/simplify/AbstractSimplifier" to setOf(
        "buildSegmentTree", "buildResult", "isSelfIntersectionProduced", "intersects"
    ),
    "org/dyn4j/geometry/simplify/VertexClusterReduction" to setOf("buildVertexList")
)

val noOpJointShiftTypes = setOf(
    "AngleJoint", "DistanceJoint", "FrictionJoint", "MotorJoint", "PrismaticJoint",
    "RevoluteJoint", "WeldJoint", "WheelJoint"
).map { "org/dyn4j/dynamics/joint/$it" }.toSet()

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
                                if (name in spec.staticMethods &&
                                    access and (Opcodes.ACC_PUBLIC or Opcodes.ACC_PROTECTED) != 0) {
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
                    val detectionType = owner.startsWith("org/dyn4j/collision/broadphase/") ||
                        owner.startsWith("org/dyn4j/collision/narrowphase/") ||
                        owner.startsWith("org/dyn4j/collision/manifold/") ||
                        owner.startsWith("org/dyn4j/collision/continuous/")
                    val sourceProjectionType = entry.name.endsWith(".class") &&
                        owner.startsWith("org/dyn4j/") &&
                        (input.getEntry(owner + "\$Companion.class") != null ||
                            ClassReader(bytes).superName == "java/lang/Enum")
                    val spec = if (entry.name.endsWith(".class"))
                        jvmApi[owner] ?: if (detectionType || sourceProjectionType) JvmApiSpec() else null
                    else null
                    val content = if (spec == null) bytes else {
                        val writer = ClassWriter(ClassWriter.COMPUTE_MAXS)
                        val visitor = object : ClassVisitor(Opcodes.ASM9, writer) {
                            val present = mutableSetOf<Pair<String, String>>()
                            var enumType = false
                            override fun visit(
                                version: Int, access: Int, name: String, signature: String?,
                                superName: String?, interfaces: Array<out String>?
                            ) {
                                enumType = superName == "java/lang/Enum"
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
                                val hiddenCompanion = name == "Companion" &&
                                    descriptor == "L" + owner + "\$Companion;" &&
                                    access and Opcodes.ACC_STATIC != 0
                                return super.visitField(
                                    if (hiddenCompanion) revised or Opcodes.ACC_SYNTHETIC else revised,
                                    name, descriptor, signature, value
                                )
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
                                val hiddenEnumEntries = enumType && name == "getEntries" &&
                                    descriptor == "()Lkotlin/enums/EnumEntries;" &&
                                    access and Opcodes.ACC_STATIC != 0
                                if (hiddenEnumEntries) {
                                    revised = revised or Opcodes.ACC_SYNTHETIC
                                }
                                if (owner == "org/dyn4j/exception/CopyException" && name == "<init>" &&
                                    descriptor == "(Ljava/lang/String;Ljava/lang/String;)V") {
                                    revised = revised or Opcodes.ACC_SYNTHETIC
                                }
                                if (name in spec.nonFinalStaticMethods && access and Opcodes.ACC_STATIC != 0) {
                                    revised = revised and Opcodes.ACC_FINAL.inv()
                                }
                                if (name in spec.packageMethods || name + descriptor in spec.packageMethodSignatures ||
                                    (spec.packageNodeMethods && descriptor.startsWith("(Lorg/dyn4j/BinarySearchTreeNode;")) ||
                                    (name == "<init>" && descriptor in spec.packageConstructorDescriptors)) {
                                    revised = revised and visibility.inv() and Opcodes.ACC_FINAL.inv()
                                }
                                if (name in spec.protectedMethods) {
                                    revised = (revised and visibility.inv()) or Opcodes.ACC_PROTECTED
                                    if (access and Opcodes.ACC_STATIC == 0) revised = revised and Opcodes.ACC_FINAL.inv()
                                }
                                if (name == "<init>" && descriptor in spec.protectedConstructorDescriptors) {
                                    revised = (revised and visibility.inv()) or Opcodes.ACC_PROTECTED
                                }
                                if (owner == "org/dyn4j/BinarySearchTreeNode" && name == "getComparable") {
                                    revised = revised and Opcodes.ACC_FINAL.inv()
                                }
                                val baselineFinalLinkMethod = owner == "org/dyn4j/geometry/Link" &&
                                    ((name == "rotate" && descriptor == "(DDD)V") ||
                                        (name == "translate" && descriptor == "(DD)V"))
                                if (owner.startsWith("org/dyn4j/geometry/") && name != "<init>" &&
                                    access and Opcodes.ACC_STATIC == 0 && access and Opcodes.ACC_PRIVATE == 0 &&
                                    !baselineFinalLinkMethod
                                ) revised = revised and Opcodes.ACC_FINAL.inv()
                                if (name in baselineFinalPolygonMethods[owner].orEmpty() &&
                                    !(owner == "org/dyn4j/geometry/decompose/DoubleEdgeList" &&
                                        revised and Opcodes.ACC_PUBLIC != 0)
                                ) revised = revised or Opcodes.ACC_FINAL
                                val revisedSignature = signature
                                    ?.replace("Ljava/lang/Comparable<-TE;>;", "Ljava/lang/Comparable<TE;>;")
                                    ?.let { value ->
                                        if (owner.startsWith("org/dyn4j/geometry/hull/") ||
                                            owner.startsWith("org/dyn4j/geometry/decompose/") ||
                                            owner.startsWith("org/dyn4j/geometry/simplify/")) {
                                            value.replace("+Lorg/dyn4j/geometry/Vector2;", "Lorg/dyn4j/geometry/Vector2;")
                                        } else value
                                    }
                                val method = super.visitMethod(revised, name, descriptor, revisedSignature, exceptions)
                                val nullPointArrayMethod = descriptor.startsWith("([Lorg/dyn4j/geometry/Vector2;)") &&
                                    when (owner) {
                                        "org/dyn4j/geometry/hull/MonotoneChain",
                                        "org/dyn4j/geometry/hull/GrahamScan",
                                        "org/dyn4j/geometry/hull/GiftWrap",
                                        "org/dyn4j/geometry/hull/DivideAndConquer" -> name == "generate"
                                        "org/dyn4j/geometry/decompose/Bayazit" -> name == "decompose"
                                        "org/dyn4j/geometry/decompose/EarClipping",
                                        "org/dyn4j/geometry/decompose/SweepLine" ->
                                            name == "decompose" || name == "triangulate" || name == "createTriangulation"
                                        else -> false
                                    }
                                if (nullPointArrayMethod) {
                                    return object : MethodVisitor(Opcodes.ASM9, method) {
                                        override fun visitCode() {
                                            super.visitCode()
                                            val nonNull = Label()
                                            super.visitVarInsn(Opcodes.ALOAD, 1)
                                            super.visitJumpInsn(Opcodes.IFNONNULL, nonNull)
                                            super.visitTypeInsn(Opcodes.NEW, "org/dyn4j/exception/ArgumentNullException")
                                            super.visitInsn(Opcodes.DUP)
                                            super.visitLdcInsn("points")
                                            super.visitMethodInsn(
                                                Opcodes.INVOKESPECIAL, "org/dyn4j/exception/ArgumentNullException",
                                                "<init>", "(Ljava/lang/String;)V", false
                                            )
                                            super.visitInsn(Opcodes.ATHROW)
                                            super.visitLabel(nonNull)
                                            super.visitFrame(Opcodes.F_SAME, 0, null, 0, null)
                                        }
                                    }
                                }
                                val nullableShapeCenter = owner == "org/dyn4j/geometry/AbstractShape" &&
                                    name == "<init>" && descriptor == "(Lorg/dyn4j/geometry/Vector2;D)V"
                                val noOpJointShift = owner in noOpJointShiftTypes && name == "shift" &&
                                    descriptor == "(Lorg/dyn4j/geometry/Vector2;)V"
                                if (nullableShapeCenter || noOpJointShift) {
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
                                if (owner == "org/dyn4j/exception/CopyException" && name == "<init>" &&
                                    descriptor == "(Ljava/lang/Class;Ljava/lang/Class;)V") {
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
                                if (owner == "org/dyn4j/geometry/simplify/AbstractSimplifier" &&
                                    name == "simplify" && descriptor == "([Lorg/dyn4j/geometry/Vector2;)[Lorg/dyn4j/geometry/Vector2;") {
                                    return object : MethodVisitor(Opcodes.ASM9, method) {
                                        override fun visitCode() {
                                            super.visitCode()
                                            val nonNull = Label()
                                            super.visitVarInsn(Opcodes.ALOAD, 1)
                                            super.visitJumpInsn(Opcodes.IFNONNULL, nonNull)
                                            super.visitInsn(Opcodes.ACONST_NULL)
                                            super.visitInsn(Opcodes.ARETURN)
                                            super.visitLabel(nonNull)
                                            super.visitFrame(Opcodes.F_SAME, 0, null, 0, null)
                                        }
                                    }
                                }
                                if (detectionType) {
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
                                if (owner == "org/dyn4j/geometry/decompose/SweepLineState") {
                                    val method = super.visitMethod(
                                        Opcodes.ACC_FINAL, "initialize",
                                        "([Lorg/dyn4j/geometry/Vector2;)Ljava/util/PriorityQueue;",
                                        "([Lorg/dyn4j/geometry/Vector2;)Ljava/util/PriorityQueue<Lorg/dyn4j/geometry/decompose/SweepLineVertex;>;",
                                        null
                                    )
                                    method.visitCode()
                                    method.visitTypeInsn(Opcodes.NEW, "java/util/PriorityQueue")
                                    method.visitInsn(Opcodes.DUP)
                                    method.visitVarInsn(Opcodes.ALOAD, 0)
                                    method.visitVarInsn(Opcodes.ALOAD, 1)
                                    method.visitMethodInsn(
                                        Opcodes.INVOKEVIRTUAL, owner, "initializeSorted",
                                        "([Lorg/dyn4j/geometry/Vector2;)Ljava/util/List;", false
                                    )
                                    method.visitMethodInsn(
                                        Opcodes.INVOKESPECIAL, "java/util/PriorityQueue", "<init>",
                                        "(Ljava/util/Collection;)V", false
                                    )
                                    method.visitInsn(Opcodes.ARETURN)
                                    method.visitMaxs(0, 0)
                                    method.visitEnd()
                                }
                                for ((name, descriptor, signature) in companionMethods[owner].orEmpty()) {
                                    if ((name to descriptor) in present) continue
                                    val visibility = when {
                                        name in spec.packageMethods || name + descriptor in spec.packageMethodSignatures -> 0
                                        name in spec.protectedMethods -> Opcodes.ACC_PROTECTED
                                        else -> Opcodes.ACC_PUBLIC
                                    }
                                    val method = super.visitMethod(
                                        visibility or Opcodes.ACC_STATIC or
                                            (if (owner == "org/dyn4j/Version" ||
                                                name in spec.protectedMethods ||
                                                name in baselineFinalPolygonMethods[owner].orEmpty()
                                            ) Opcodes.ACC_FINAL else 0) or
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

val jvmModuleInfo by tasks.registering(JavaCompile::class) {
    val jvmMain = kotlin.targets.getByName("jvm").compilations.getByName("main")
    dependsOn(tasks.named("compileKotlinJvm"))
    source("src/jvmModule/java/module-info.java")
    destinationDirectory.set(layout.buildDirectory.dir("classes/java/jvmModule"))
    classpath = files()
    inputs.files(jvmMain.output.classesDirs, requireNotNull(jvmMain.runtimeDependencyFiles))
    options.release.set(9)
    modularity.inferModulePath.set(false)
    doFirst {
        options.compilerArgs.addAll(listOf(
            "--module-path", requireNotNull(jvmMain.runtimeDependencyFiles).asPath,
            "--patch-module", "org.dyn4j=${jvmMain.output.classesDirs.asPath}"
        ))
    }
}

tasks.withType<Jar>().configureEach {
    if (name == "jvmJar") {
        dependsOn(jvmModuleInfo)
        from(jvmModuleInfo.flatMap { it.destinationDirectory })
    }
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
    js {
        nodejs()
        browser {
            testTask {
                useKarma {
                    if (System.getenv("DYN4K_BROWSER") == "firefox") useFirefoxHeadless()
                    else useChromeHeadless()
                }
            }
        }
    }
    wasmJs {
        nodejs()
        browser {
            testTask {
                useKarma {
                    if (System.getenv("DYN4K_BROWSER") == "firefox") useFirefoxHeadless()
                    else useChromeHeadless()
                }
            }
        }
    }
    wasmWasi { nodejs(); wasmtime() }
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

if (providers.gradleProperty("qualificationProduction").orNull == "true") {
    tasks.named<org.jetbrains.kotlin.gradle.targets.js.testing.KotlinJsTest>("jsBrowserTest") {
        dependsOn("jsTestTestProductionExecutableCompileSync")
        inputFileProperty.set(layout.buildDirectory.file(
            "compileSync/js/test/testProductionExecutable/kotlin/${rootProject.name}-${project.name}-test.js"
        ))
        doFirst { logger.lifecycle("qualification test input: ${inputFileProperty.get().asFile}") }
    }
    tasks.named<org.jetbrains.kotlin.gradle.targets.js.testing.KotlinJsTest>("wasmJsBrowserTest") {
        dependsOn("compileTestProductionExecutableKotlinWasmJsOptimize")
        inputFileProperty.set(layout.buildDirectory.file(
            "compileSync/wasmJs/test/testProductionExecutable/optimized/${rootProject.name}-${project.name}-test.mjs"
        ))
        doFirst { logger.lifecycle("qualification test input: ${inputFileProperty.get().asFile}") }
    }
}

tasks.named<org.gradle.jvm.tasks.Jar>("jvmSourcesJar") {
    from(file("src/jvmModule/java/module-info.java")) { into("jvmModule") }
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

val polygonTestNames = mapOf(
    "hull" to listOf("DivideAndConquerTest", "GiftWrapTest", "GrahamScanTest", "MonotoneChainTest"),
    "decompose" to listOf("BayazitTest", "EarClippingTest", "SweepLineTest"),
    "simplify" to listOf(
        "DouglasPeuckerTest", "SegmentTreeTest", "SimplePolygonVertexTest",
        "VertexClusterReductionTest", "VisvalingamTest"
    )
)
val polygonTestSources = polygonTestNames.flatMap { (packageName, names) ->
    (names + when (packageName) {
        "decompose" -> listOf("AbstractDecomposeTest")
        "simplify" -> listOf("AbstractSimplifyTest")
        else -> emptyList()
    }).map { upstreamCheckout.map { dir ->
        dir.file("src/test/java/org/dyn4j/geometry/$packageName/$it.java")
    } }
} + listOf(upstreamCheckout.map { it.file("src/test/java/org/dyn4j/geometry/RobustGeometryTest.java") })
val compileUpstreamPolygonTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(polygonTestSources)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-polygon-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamPolygonTests") {
    dependsOn(compileUpstreamPolygonTests)
    classpath(
        compileUpstreamPolygonTests.flatMap { it.destinationDirectory },
        tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime,
        file("src/upstreamPolygonTest/resources")
    )
    mainClass.set("org.junit.runner.JUnitCore")
    args(polygonTestNames.flatMap { (packageName, names) ->
        names.map { "org.dyn4j.geometry.$packageName.$it" }
    })
}
tasks.register<Exec>("verifyPolygonJvmApi") {
    dependsOn(verifyBaseline, tasks.named("jvmJar"))
    doFirst {
        environment("JAVA_HOME", System.getenv("JAVA_HOME"))
        commandLine(
            "python3", rootProject.file("scripts/verify-polygon-jvm-api.py").absolutePath,
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

val detectionParitySource = file("src/jvmConsumer/java/DetectionParityConsumer.java")
val baselineDetectionParityConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(detectionParitySource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/detection-parity-baseline-classes"))
    options.release.set(8)
}
val candidateDetectionParityConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(detectionParitySource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/detection-parity-candidate-classes"))
    options.release.set(8)
}
val baselineDetectionParityOutput = layout.buildDirectory.file("consumer/detection-parity-baseline.tsv")
val candidateDetectionParityOutput = layout.buildDirectory.file("consumer/detection-parity-candidate.tsv")
tasks.register<JavaExec>("runBaselineDetectionParity") {
    dependsOn(baselineDetectionParityConsumer)
    classpath(baselineDetectionParityConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("DetectionParityConsumer")
    outputs.file(baselineDetectionParityOutput)
    doFirst { standardOutput = baselineDetectionParityOutput.get().asFile.outputStream() }
    doLast { standardOutput.close() }
}
tasks.register<JavaExec>("runCandidateDetectionParity") {
    dependsOn(candidateDetectionParityConsumer)
    classpath(candidateDetectionParityConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("DetectionParityConsumer")
    outputs.file(candidateDetectionParityOutput)
    doFirst { standardOutput = candidateDetectionParityOutput.get().asFile.outputStream() }
    doLast { standardOutput.close() }
}
tasks.register<Exec>("verifyDetectionParity") {
    dependsOn("runBaselineDetectionParity", "runCandidateDetectionParity")
    doFirst {
        commandLine(
            "python3", rootProject.file("scripts/verify-detection-parity.py").absolutePath,
            baselineDetectionParityOutput.get().asFile.absolutePath,
            candidateDetectionParityOutput.get().asFile.absolutePath
        )
    }
}

val collisionModelConsumerSource = file("src/jvmConsumer/java/CollisionModelConsumer.java")
val collisionModelStaticHideSource = file("src/jvmConsumer/java/Issue35StaticHideConsumer.java")
val copyExceptionAmbiguitySource = file("src/jvmConsumer/java/CopyExceptionAmbiguity.java")
val baselineCollisionModelConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(collisionModelConsumerSource, collisionModelStaticHideSource, copyExceptionAmbiguitySource)
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
    source(collisionModelConsumerSource, collisionModelStaticHideSource, copyExceptionAmbiguitySource)
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
    source(collisionModelConsumerSource, collisionModelStaticHideSource, copyExceptionAmbiguitySource)
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
    source(collisionModelConsumerSource, collisionModelStaticHideSource, copyExceptionAmbiguitySource)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/collision-model-android"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidCollisionModelConsumer") {
    dependsOn(androidCollisionModelConsumer, androidRuntimeJar)
    classpath(androidCollisionModelConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("CollisionModelConsumer")
}
val dynamicsTestNames = listOf(
    "AbstractPhysicsBodyTest", "BodyFixtureTest", "BodyTest", "ForceTest",
    "SettingsTest", "TimeStepTest", "TorqueTest"
)
val compileBaselineDynamicsTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, verifyBaseline)
    source(dynamicsTestNames.map {
        upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/dynamics/$it.java") }
    })
    classpath = files(baseline, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-dynamics-tests/baseline-classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineDynamicsTests") {
    dependsOn(compileBaselineDynamicsTests)
    classpath(compileBaselineDynamicsTests.flatMap { it.destinationDirectory }, baseline, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(dynamicsTestNames.map { "org.dyn4j.dynamics.$it" })
}
val compileUpstreamDynamicsTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(dynamicsTestNames.map {
        upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/dynamics/$it.java") }
    })
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-dynamics-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamDynamicsTests") {
    dependsOn(compileUpstreamDynamicsTests)
    classpath(compileUpstreamDynamicsTests.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(dynamicsTestNames.map { "org.dyn4j.dynamics.$it" })
}
val dynamicsConsumerSource = files("src/jvmConsumer/java/DynamicsConsumer.java", "src/jvmConsumer/java/DynamicsNullProbe.java")
val baselineDynamicsConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(dynamicsConsumerSource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/dynamics-baseline"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineDynamicsConsumer") {
    dependsOn(baselineDynamicsConsumer)
    classpath(baselineDynamicsConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("DynamicsConsumer")
}
tasks.register<JavaExec>("runBaselineDynamicsNullProbe") {
    dependsOn(baselineDynamicsConsumer)
    classpath(baselineDynamicsConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("DynamicsNullProbe")
}
val candidateDynamicsConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(dynamicsConsumerSource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/dynamics-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runCandidateDynamicsConsumer") {
    dependsOn(candidateDynamicsConsumer)
    classpath(candidateDynamicsConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("DynamicsConsumer")
}
tasks.register<JavaExec>("runCandidateDynamicsNullProbe") {
    dependsOn(candidateDynamicsConsumer)
    classpath(candidateDynamicsConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("DynamicsNullProbe")
}
val stagedDynamicsConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    source(dynamicsConsumerSource)
    classpath = stagedGeometryClasspath
    destinationDirectory.set(layout.buildDirectory.dir("consumer/dynamics-staged"))
    options.release.set(8)
}
tasks.register<JavaExec>("runStagedDynamicsConsumer") {
    dependsOn(stagedDynamicsConsumer)
    classpath(stagedDynamicsConsumer.flatMap { it.destinationDirectory }, stagedGeometryClasspath)
    mainClass.set("DynamicsConsumer")
}
val stagedDynamicsKotlinConsumer = tasks.register<JavaExec>("stagedDynamicsKotlinConsumer") {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    classpath(configurations.getByName("kotlinCompilerClasspath"))
    mainClass.set("org.jetbrains.kotlin.cli.jvm.K2JVMCompiler")
    val output = layout.buildDirectory.dir("consumer/dynamics-staged-kotlin")
    inputs.file(file("src/jvmConsumer/kotlin/DynamicsKotlinConsumer.kt"))
    inputs.files(stagedGeometryClasspath)
    outputs.dir(output)
    doFirst {
        args("-no-stdlib", "-no-reflect", "-jvm-target", "1.8", "-classpath", stagedGeometryClasspath.asPath,
            "-d", output.get().asFile.absolutePath,
            file("src/jvmConsumer/kotlin/DynamicsKotlinConsumer.kt").absolutePath)
    }
}
tasks.register<JavaExec>("runStagedDynamicsKotlinConsumer") {
    dependsOn(stagedDynamicsKotlinConsumer)
    classpath(layout.buildDirectory.dir("consumer/dynamics-staged-kotlin"), stagedGeometryClasspath)
    mainClass.set("DynamicsKotlinConsumer")
}
val androidDynamicsConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(androidCompileJar)
    source(dynamicsConsumerSource)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/dynamics-android"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidDynamicsConsumer") {
    dependsOn(androidDynamicsConsumer, androidRuntimeJar)
    classpath(androidDynamicsConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("DynamicsConsumer")
}

val contactTestNames = listOf(
    "ContactConstraintTest", "ForceCollisionTimeOfImpactSolverTest",
    "SequentialImpulsesTest", "SolvableContactTest"
)
val compileBaselineContactTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, verifyBaseline)
    source(contactTestNames.map { upstreamCheckout.map { dir ->
        dir.file("src/test/java/org/dyn4j/dynamics/contact/$it.java")
    } })
    classpath = files(baseline, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-contact-tests/baseline-classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineContactTests") {
    dependsOn(compileBaselineContactTests)
    classpath(compileBaselineContactTests.flatMap { it.destinationDirectory }, baseline, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(contactTestNames.map { "org.dyn4j.dynamics.contact.$it" })
}
val compileUpstreamContactTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(contactTestNames.map { upstreamCheckout.map { dir ->
        dir.file("src/test/java/org/dyn4j/dynamics/contact/$it.java")
    } })
    source(upstreamCheckout.map { it.file("src/main/java/org/dyn4j/world/ValueMixer.java") })
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-contact-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamContactTests") {
    dependsOn(compileUpstreamContactTests)
    classpath(compileUpstreamContactTests.flatMap { it.destinationDirectory }, tasks.named("jvmJar"),
        jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(contactTestNames.map { "org.dyn4j.dynamics.contact.$it" })
}
val compileUpstreamContactAndroidTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, androidCompileJar)
    source(contactTestNames.map { upstreamCheckout.map { dir ->
        dir.file("src/test/java/org/dyn4j/dynamics/contact/$it.java")
    } })
    source(upstreamCheckout.map { it.file("src/main/java/org/dyn4j/world/ValueMixer.java") })
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-contact-android-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamContactAndroidTests") {
    dependsOn(compileUpstreamContactAndroidTests, androidRuntimeJar)
    classpath(compileUpstreamContactAndroidTests.flatMap { it.destinationDirectory }, androidRuntimeJar,
        jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(contactTestNames.map { "org.dyn4j.dynamics.contact.$it" })
}

val contactConsumerSource = file("src/jvmConsumer/java/ContactConsumer.java")
val baselineContactConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(contactConsumerSource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/contact-baseline"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineContactConsumer") {
    dependsOn(baselineContactConsumer)
    classpath(baselineContactConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("ContactConsumer")
}
val candidateContactConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(contactConsumerSource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/contact-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runCandidateContactConsumer") {
    dependsOn(candidateContactConsumer)
    classpath(candidateContactConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("ContactConsumer")
}
val stagedContactConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    source(contactConsumerSource)
    classpath = stagedGeometryClasspath
    destinationDirectory.set(layout.buildDirectory.dir("consumer/contact-staged"))
    options.release.set(8)
}
tasks.register<JavaExec>("runStagedContactConsumer") {
    dependsOn(stagedContactConsumer)
    classpath(stagedContactConsumer.flatMap { it.destinationDirectory }, stagedGeometryClasspath)
    mainClass.set("ContactConsumer")
}
val stagedContactKotlinConsumer = tasks.register<JavaExec>("stagedContactKotlinConsumer") {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    classpath(configurations.getByName("kotlinCompilerClasspath"))
    mainClass.set("org.jetbrains.kotlin.cli.jvm.K2JVMCompiler")
    val output = layout.buildDirectory.dir("consumer/contact-staged-kotlin")
    inputs.file(file("src/jvmConsumer/kotlin/ContactKotlinConsumer.kt"))
    inputs.files(stagedGeometryClasspath)
    outputs.dir(output)
    doFirst {
        args("-no-stdlib", "-no-reflect", "-jvm-target", "1.8", "-classpath", stagedGeometryClasspath.asPath,
            "-d", output.get().asFile.absolutePath,
            file("src/jvmConsumer/kotlin/ContactKotlinConsumer.kt").absolutePath)
    }
}
tasks.register<JavaExec>("runStagedContactKotlinConsumer") {
    dependsOn(stagedContactKotlinConsumer)
    classpath(layout.buildDirectory.dir("consumer/contact-staged-kotlin"), stagedGeometryClasspath)
    mainClass.set("ContactKotlinConsumer")
}
val androidContactConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(androidCompileJar)
    source(contactConsumerSource)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/contact-android"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidContactConsumer") {
    dependsOn(androidContactConsumer, androidRuntimeJar)
    classpath(androidContactConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("ContactConsumer")
}

tasks.register<Exec>("verifyContactJvmApi") {
    dependsOn(verifyBaseline, tasks.named("jvmJar"))
    doFirst {
        commandLine("python3", rootProject.file("scripts/verify-contact-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            tasks.named<Jar>("jvmJar").get().archiveFile.get().asFile.absolutePath)
    }
}
tasks.register<Exec>("verifyContactAndroidApi") {
    dependsOn(verifyBaseline, androidCompileJar)
    doFirst {
        commandLine("python3", rootProject.file("scripts/verify-contact-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            layout.buildDirectory.file("intermediates/compile_library_classes_jar/androidMain/bundleAndroidMainClassesToCompileJar/classes.jar").get().asFile.absolutePath)
    }
}
tasks.register<Exec>("verifyContactAndroidRuntimeApi") {
    dependsOn(verifyBaseline, androidRuntimeJar)
    doFirst {
        commandLine("python3", rootProject.file("scripts/verify-contact-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            layout.buildDirectory.file("intermediates/runtime_library_classes_jar/androidMain/bundleAndroidMainClassesToRuntimeJar/classes.jar").get().asFile.absolutePath)
    }
}

val jointTestNames = listOf(
    "AbstractJointTest", "AbstractPairedBodyJointTest", "AbstractSingleBodyJointTest",
    "AngleJointTest", "DistanceJointTest", "FrictionJointTest", "MotorJointTest",
    "PinJointTest", "PrismaticJointTest", "PulleyJointTest", "RevoluteJointTest",
    "WeldJointTest", "WheelJointTest"
)
val worldTestNames = listOf(
    "AbstractCollisionWorldTest", "AbstractPhysicsWorldTest", "BroadphaseFilterAdapterTest",
    "CollisionBodyBroadphaseFilterTest", "CollisionItemAdapterTest", "ConstraintGraphTest",
    "DetectFilterTest", "IslandTest", "PhysicsBodyBroadphaseFilterTest",
    "PhysicsBodySweptAABBProducerTest", "ValueMixerTest", "WorldTest"
)
val worldTestClasses = worldTestNames.map { "org.dyn4j.world.$it" } + listOf(
    "org.dyn4j.world.listener.ListenerAdaptersTest", "org.dyn4j.world.result.DetectResultTest"
)
val worldTestSources = worldTestNames.map { name ->
    upstreamCheckout.map { it.file("src/test/java/org/dyn4j/world/$name.java") }
} + listOf(
    upstreamCheckout.map { it.file("src/test/java/org/dyn4j/world/listener/ListenerAdaptersTest.java") },
    upstreamCheckout.map { it.file("src/test/java/org/dyn4j/world/result/DetectResultTest.java") }
)
val compileBaselineWorldTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, verifyBaseline)
    source(worldTestSources)
    classpath = files(baseline, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-world-tests/baseline-classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineWorldTests") {
    dependsOn(compileBaselineWorldTests)
    classpath(compileBaselineWorldTests.flatMap { it.destinationDirectory }, baseline, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(worldTestClasses)
}
val compileUpstreamWorldTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(worldTestSources)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-world-tests/candidate-classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamWorldTests") {
    dependsOn(compileUpstreamWorldTests)
    classpath(compileUpstreamWorldTests.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(worldTestClasses)
}
val compileAndroidWorldTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, androidCompileJar)
    source(worldTestSources)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-world-tests/android-classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidWorldTests") {
    dependsOn(compileAndroidWorldTests, androidRuntimeJar)
    classpath(compileAndroidWorldTests.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(worldTestClasses)
}
val worldConsumerSource = files(
    "src/jvmConsumer/java/WorldConsumer.java", "src/jvmConsumer/java/WorldAdvancedConsumer.java",
    "src/jvmConsumer/java/WorldQualityConsumer.java"
)
val baselineWorldConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(worldConsumerSource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/world-baseline"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineWorldConsumer") {
    dependsOn(baselineWorldConsumer)
    classpath(baselineWorldConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("WorldConsumer")
}
tasks.register<JavaExec>("runBaselineWorldAdvancedConsumer") {
    dependsOn(baselineWorldConsumer)
    classpath(baselineWorldConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("WorldAdvancedConsumer")
}
tasks.register<JavaExec>("runBaselineWorldQualityConsumer") {
    dependsOn(baselineWorldConsumer)
    classpath(baselineWorldConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("WorldQualityConsumer")
}
val candidateWorldConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(worldConsumerSource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/world-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runCandidateWorldConsumer") {
    dependsOn(candidateWorldConsumer)
    classpath(candidateWorldConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("WorldConsumer")
}
tasks.register<JavaExec>("runCandidateWorldAdvancedConsumer") {
    dependsOn(candidateWorldConsumer)
    classpath(candidateWorldConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("WorldAdvancedConsumer")
}
tasks.register<JavaExec>("runCandidateWorldQualityConsumer") {
    dependsOn(candidateWorldConsumer)
    classpath(candidateWorldConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("WorldQualityConsumer")
}
val stagedWorldConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    source(worldConsumerSource)
    classpath = stagedGeometryClasspath
    destinationDirectory.set(layout.buildDirectory.dir("consumer/world-staged"))
    options.release.set(8)
}
tasks.register<JavaExec>("runStagedWorldConsumer") {
    dependsOn(stagedWorldConsumer)
    classpath(stagedWorldConsumer.flatMap { it.destinationDirectory }, stagedGeometryClasspath)
    mainClass.set("WorldConsumer")
}
tasks.register<JavaExec>("runStagedWorldAdvancedConsumer") {
    dependsOn(stagedWorldConsumer)
    classpath(stagedWorldConsumer.flatMap { it.destinationDirectory }, stagedGeometryClasspath)
    mainClass.set("WorldAdvancedConsumer")
}
tasks.register<JavaExec>("runStagedWorldQualityConsumer") {
    dependsOn(stagedWorldConsumer)
    classpath(stagedWorldConsumer.flatMap { it.destinationDirectory }, stagedGeometryClasspath)
    mainClass.set("WorldQualityConsumer")
}
val stagedWorldKotlinConsumer = tasks.register<JavaExec>("stagedWorldKotlinConsumer") {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    classpath(configurations.getByName("kotlinCompilerClasspath"))
    mainClass.set("org.jetbrains.kotlin.cli.jvm.K2JVMCompiler")
    val output = layout.buildDirectory.dir("consumer/world-staged-kotlin")
    inputs.file(file("src/jvmConsumer/kotlin/WorldKotlinConsumer.kt"))
    inputs.files(stagedGeometryClasspath)
    outputs.dir(output)
    doFirst {
        args("-no-stdlib", "-no-reflect", "-jvm-target", "1.8", "-classpath", stagedGeometryClasspath.asPath,
            "-d", output.get().asFile.absolutePath,
            file("src/jvmConsumer/kotlin/WorldKotlinConsumer.kt").absolutePath)
    }
}
tasks.register<JavaExec>("runStagedWorldKotlinConsumer") {
    dependsOn(stagedWorldKotlinConsumer)
    classpath(layout.buildDirectory.dir("consumer/world-staged-kotlin"), stagedGeometryClasspath)
    mainClass.set("WorldKotlinConsumer")
}
val projectionKotlinSource = file("src/jvmConsumer/kotlin/ProjectionKotlinConsumer.kt")
val stagedProjectionKotlinClasses = layout.buildDirectory.dir("consumer/projection-staged-kotlin")
val stagedProjectionKotlinConsumer by tasks.registering(JavaExec::class) {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    classpath(configurations.getByName("kotlinCompilerClasspath"))
    mainClass.set("org.jetbrains.kotlin.cli.jvm.K2JVMCompiler")
    inputs.file(projectionKotlinSource)
    inputs.files(stagedGeometryClasspath)
    outputs.dir(stagedProjectionKotlinClasses)
    doFirst {
        args("-no-stdlib", "-no-reflect", "-jvm-target", "1.8", "-classpath", stagedGeometryClasspath.asPath,
            "-d", stagedProjectionKotlinClasses.get().asFile.absolutePath, projectionKotlinSource.absolutePath)
    }
}
tasks.register<JavaExec>("runStagedProjectionKotlinConsumer") {
    dependsOn(stagedProjectionKotlinConsumer)
    classpath(stagedProjectionKotlinClasses, stagedGeometryClasspath)
    mainClass.set("org.dyn4j.geometry.simplify.ProjectionKotlinConsumer")
}
val androidProjectionKotlinClasses = layout.buildDirectory.dir("consumer/projection-android-kotlin")
val androidProjectionKotlinClasspath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
val androidProjectionKotlinConsumer by tasks.registering(JavaExec::class) {
    dependsOn(androidCompileJar)
    classpath(configurations.getByName("kotlinCompilerClasspath"))
    mainClass.set("org.jetbrains.kotlin.cli.jvm.K2JVMCompiler")
    inputs.file(projectionKotlinSource)
    inputs.files(androidProjectionKotlinClasspath)
    outputs.dir(androidProjectionKotlinClasses)
    doFirst {
        args("-no-stdlib", "-no-reflect", "-jvm-target", "1.8", "-classpath", androidProjectionKotlinClasspath.asPath,
            "-d", androidProjectionKotlinClasses.get().asFile.absolutePath, projectionKotlinSource.absolutePath)
    }
}
tasks.register<JavaExec>("runAndroidProjectionKotlinConsumer") {
    dependsOn(androidProjectionKotlinConsumer, androidRuntimeJar)
    classpath(androidProjectionKotlinClasses, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("org.dyn4j.geometry.simplify.ProjectionKotlinConsumer")
}
val androidWorldConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(androidCompileJar)
    source(worldConsumerSource)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/world-android"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidWorldConsumer") {
    dependsOn(androidWorldConsumer, androidRuntimeJar)
    classpath(androidWorldConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("WorldConsumer")
}
tasks.register<JavaExec>("runAndroidWorldAdvancedConsumer") {
    dependsOn(androidWorldConsumer, androidRuntimeJar)
    classpath(androidWorldConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("WorldAdvancedConsumer")
}
tasks.register<JavaExec>("runAndroidWorldQualityConsumer") {
    dependsOn(androidWorldConsumer, androidRuntimeJar)
    classpath(androidWorldConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("WorldQualityConsumer")
}
tasks.register<Exec>("verifyWorldJvmApi") {
    dependsOn(verifyBaseline, tasks.named("jvmJar"))
    doFirst {
        commandLine("python3", rootProject.file("scripts/verify-world-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            tasks.named<Jar>("jvmJar").get().archiveFile.get().asFile.absolutePath)
    }
}
tasks.register<Exec>("verifyWorldAndroidApi") {
    dependsOn(verifyBaseline, androidCompileJar)
    doFirst {
        commandLine("python3", rootProject.file("scripts/verify-world-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            layout.buildDirectory.file("intermediates/compile_library_classes_jar/androidMain/bundleAndroidMainClassesToCompileJar/classes.jar").get().asFile.absolutePath)
    }
}
tasks.register<Exec>("verifyWorldAndroidRuntimeApi") {
    dependsOn(verifyBaseline, androidRuntimeJar)
    doFirst {
        commandLine("python3", rootProject.file("scripts/verify-world-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            layout.buildDirectory.file("intermediates/runtime_library_classes_jar/androidMain/bundleAndroidMainClassesToRuntimeJar/classes.jar").get().asFile.absolutePath)
    }
}
val jointTestSourceNames = jointTestNames + listOf(
    "BaseJointTest", "TestAbstractJoint", "TestAbstractPairedBodyJoint", "TestAbstractSingleBodyJoint"
)
val compileBaselineJointTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, verifyBaseline)
    source(jointTestSourceNames.map {
        upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/dynamics/joint/$it.java") }
    })
    classpath = files(baseline, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-joint-tests/baseline-classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineJointTests") {
    dependsOn(compileBaselineJointTests)
    classpath(compileBaselineJointTests.flatMap { it.destinationDirectory }, baseline, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(jointTestNames.map { "org.dyn4j.dynamics.joint.$it" })
}
val compileUpstreamJointTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(jointTestSourceNames.map {
        upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/dynamics/joint/$it.java") }
    })
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-joint-tests/candidate-classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamJointTests") {
    dependsOn(compileUpstreamJointTests)
    classpath(compileUpstreamJointTests.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(jointTestNames.map { "org.dyn4j.dynamics.joint.$it" })
}

val jointSimulationTestNames = listOf(
    "AngleJointSimulationTest", "DistanceJointSimulationTest", "FrictionJointSimulationTest",
    "MotorJointSimulationTest", "PinJointSimulationTest", "PrismaticJointSimulationTest",
    "PulleyJointSimulationTest", "RevoluteJointSimulationTest", "WeldJointSimulationTest",
    "WheelJointSimulationTest"
)
val compileBaselineJointSimulationTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, verifyBaseline)
    source(jointSimulationTestNames.map {
        upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/simulation/$it.java") }
    })
    classpath = files(baseline, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-joint-simulation-tests/baseline-classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineJointSimulationTests") {
    dependsOn(compileBaselineJointSimulationTests)
    classpath(compileBaselineJointSimulationTests.flatMap { it.destinationDirectory }, baseline, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(jointSimulationTestNames.map { "org.dyn4j.simulation.$it" })
}
val compileUpstreamJointSimulationTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(jointSimulationTestNames.map {
        upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/simulation/$it.java") }
    })
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-joint-simulation-tests/candidate-classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamJointSimulationTests") {
    dependsOn(compileUpstreamJointSimulationTests)
    classpath(compileUpstreamJointSimulationTests.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(jointSimulationTestNames.map { "org.dyn4j.simulation.$it" })
}

val jointConsumerSource = file("src/jvmConsumer/java/JointConsumer.java")
val baselineJointConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(jointConsumerSource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/joint-baseline"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineJointConsumer") {
    dependsOn(baselineJointConsumer)
    classpath(baselineJointConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("JointConsumer")
}
val candidateJointConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(jointConsumerSource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/joint-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runCandidateJointConsumer") {
    dependsOn(candidateJointConsumer)
    classpath(candidateJointConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("JointConsumer")
}
val stagedJointConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    source(jointConsumerSource)
    classpath = stagedGeometryClasspath
    destinationDirectory.set(layout.buildDirectory.dir("consumer/joint-staged"))
    options.release.set(8)
}
tasks.register<JavaExec>("runStagedJointConsumer") {
    dependsOn(stagedJointConsumer)
    classpath(stagedJointConsumer.flatMap { it.destinationDirectory }, stagedGeometryClasspath)
    mainClass.set("JointConsumer")
}
val stagedJointKotlinConsumer = tasks.register<JavaExec>("stagedJointKotlinConsumer") {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    classpath(configurations.getByName("kotlinCompilerClasspath"))
    mainClass.set("org.jetbrains.kotlin.cli.jvm.K2JVMCompiler")
    val output = layout.buildDirectory.dir("consumer/joint-staged-kotlin")
    inputs.file(file("src/jvmConsumer/kotlin/JointKotlinConsumer.kt"))
    inputs.files(stagedGeometryClasspath)
    outputs.dir(output)
    doFirst {
        args("-no-stdlib", "-no-reflect", "-jvm-target", "1.8", "-classpath", stagedGeometryClasspath.asPath,
            "-d", output.get().asFile.absolutePath,
            file("src/jvmConsumer/kotlin/JointKotlinConsumer.kt").absolutePath)
    }
}
tasks.register<JavaExec>("runStagedJointKotlinConsumer") {
    dependsOn(stagedJointKotlinConsumer)
    classpath(layout.buildDirectory.dir("consumer/joint-staged-kotlin"), stagedGeometryClasspath)
    mainClass.set("JointKotlinConsumer")
}
val androidJointConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(androidCompileJar)
    source(jointConsumerSource)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/joint-android"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidJointConsumer") {
    dependsOn(androidJointConsumer, androidRuntimeJar)
    classpath(androidJointConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("JointConsumer")
}

val jointMechanismConsumerSource = file("src/jvmConsumer/java/JointMechanismConsumer.java")
val baselineJointMechanismConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(jointMechanismConsumerSource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/joint-mechanism-baseline"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineJointMechanismConsumer") {
    dependsOn(baselineJointMechanismConsumer)
    classpath(baselineJointMechanismConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("JointMechanismConsumer")
}
val candidateJointMechanismConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(jointMechanismConsumerSource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/joint-mechanism-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runCandidateJointMechanismConsumer") {
    dependsOn(candidateJointMechanismConsumer)
    classpath(candidateJointMechanismConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("JointMechanismConsumer")
}

val polygonConsumerSource = file("src/jvmConsumer/java/PolygonAlgorithmConsumer.java")
val baselinePolygonConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(polygonConsumerSource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("polygon-consumer/baseline"))
    options.release.set(8)
}
val candidatePolygonConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(polygonConsumerSource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("polygon-consumer/candidate"))
    options.release.set(8)
}
val stagedPolygonConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(":dyn4k-core:publishJvmPublicationToStagingRepository", ":dyn4k:publishJvmPublicationToStagingRepository")
    source(polygonConsumerSource)
    classpath = stagedGeometryClasspath
    destinationDirectory.set(layout.buildDirectory.dir("polygon-consumer/staged"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselinePolygonConsumer") {
    dependsOn(baselinePolygonConsumer)
    classpath(
        baselinePolygonConsumer.flatMap { it.destinationDirectory }, baseline,
        file("src/upstreamPolygonTest/resources")
    )
    mainClass.set("PolygonAlgorithmConsumer")
}
tasks.register<JavaExec>("runCandidatePolygonConsumer") {
    dependsOn(candidatePolygonConsumer)
    classpath(
        candidatePolygonConsumer.flatMap { it.destinationDirectory },
        tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles,
        file("src/upstreamPolygonTest/resources")
    )
    mainClass.set("PolygonAlgorithmConsumer")
}
tasks.register<JavaExec>("runStagedPolygonConsumer") {
    dependsOn(stagedPolygonConsumer)
    classpath(
        stagedPolygonConsumer.flatMap { it.destinationDirectory }, stagedGeometryClasspath,
        file("src/upstreamPolygonTest/resources")
    )
    mainClass.set("PolygonAlgorithmConsumer")
}
