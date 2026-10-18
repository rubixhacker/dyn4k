package portable

import org.dyn4j.collision.broadphase.CollisionItemBroadphaseDetectorAdapter
import org.dyn4j.collision.broadphase.DynamicAABBTree
import org.dyn4j.collision.broadphase.StaticValueAABBExpansionMethod
import org.dyn4j.collision.continuous.ConservativeAdvancement
import org.dyn4j.collision.manifold.ClippingManifoldSolver
import org.dyn4j.collision.narrowphase.Epa
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.contact.ForceCollisionTimeOfImpactSolver
import org.dyn4j.dynamics.contact.SequentialImpulses
import org.dyn4j.world.World

internal object FrozenConfiguration {
    fun settings(value: Settings): Map<String, Any?> = mapOf(
        "type" to "org.dyn4j.dynamics.Settings",
        "getStepFrequency" to value.getStepFrequency(),
        "getMaximumTranslation" to value.getMaximumTranslation(),
        "getMaximumTranslationSquared" to value.getMaximumTranslationSquared(),
        "getMaximumRotation" to value.getMaximumRotation(),
        "getMaximumRotationSquared" to value.getMaximumRotationSquared(),
        "isAtRestDetectionEnabled" to value.isAtRestDetectionEnabled(),
        "getMaximumAtRestLinearVelocity" to value.getMaximumAtRestLinearVelocity(),
        "getMaximumAtRestLinearVelocitySquared" to value.getMaximumAtRestLinearVelocitySquared(),
        "getMaximumAtRestAngularVelocity" to value.getMaximumAtRestAngularVelocity(),
        "getMaximumAtRestAngularVelocitySquared" to value.getMaximumAtRestAngularVelocitySquared(),
        "getMinimumAtRestTime" to value.getMinimumAtRestTime(),
        "getVelocityConstraintSolverIterations" to value.getVelocityConstraintSolverIterations(),
        "getPositionConstraintSolverIterations" to value.getPositionConstraintSolverIterations(),
        "getMaximumWarmStartDistance" to value.getMaximumWarmStartDistance(),
        "getMaximumWarmStartDistanceSquared" to value.getMaximumWarmStartDistanceSquared(),
        "isWarmStartingEnabled" to value.isWarmStartingEnabled(),
        "getLinearTolerance" to value.getLinearTolerance(),
        "getLinearToleranceSquared" to value.getLinearToleranceSquared(),
        "getAngularTolerance" to value.getAngularTolerance(),
        "getAngularToleranceSquared" to value.getAngularToleranceSquared(),
        "getMaximumLinearCorrection" to value.getMaximumLinearCorrection(),
        "getMaximumLinearCorrectionSquared" to value.getMaximumLinearCorrectionSquared(),
        "getMaximumAngularCorrection" to value.getMaximumAngularCorrection(),
        "getMaximumAngularCorrectionSquared" to value.getMaximumAngularCorrectionSquared(),
        "getBaumgarte" to value.getBaumgarte(),
        "getContinuousDetectionMode" to value.getContinuousDetectionMode().name,
    )

    private fun expansion(value: Any?): Map<String, Any?> {
        val method = value as? StaticValueAABBExpansionMethod<*>
            ?: error("unsupported AABB expansion: ${value?.let { it::class }}")
        return mapOf("type" to "org.dyn4j.collision.broadphase.StaticValueAABBExpansionMethod",
            "getExpansion" to method.getExpansion())
    }

    private fun tree(value: Any?): Map<String, Any?> {
        val detector = value as? DynamicAABBTree<*>
            ?: error("unsupported broadphase tree: ${value?.let { it::class }}")
        return mapOf("type" to "org.dyn4j.collision.broadphase.DynamicAABBTree",
            "getAABBExpansionMethod" to expansion(detector.getAABBExpansionMethod()),
            "getHeight" to detector.getHeight(),
            "getPerimeterRatio" to detector.getPerimeterRatio(),
            "isUpdateTrackingEnabled" to detector.isUpdateTrackingEnabled(),
            "isUpdateTrackingSupported" to detector.isUpdateTrackingSupported())
    }

    private fun gjk(value: Any?): Map<String, Any?> {
        val detector = value as? Gjk ?: error("unsupported distance detector: ${value?.let { it::class }}")
        val epa = detector.getMinkowskiPenetrationSolver() as? Epa
            ?: error("unsupported penetration solver")
        return mapOf("type" to "org.dyn4j.collision.narrowphase.Gjk",
            "getDetectEpsilon" to detector.getDetectEpsilon(),
            "getDistanceEpsilon" to detector.getDistanceEpsilon(),
            "getRaycastEpsilon" to detector.getRaycastEpsilon(),
            "getMaxDetectIterations" to detector.getMaxDetectIterations(),
            "getMaxDistanceIterations" to detector.getMaxDistanceIterations(),
            "getMaxRaycastIterations" to detector.getMaxRaycastIterations(),
            "getMinkowskiPenetrationSolver" to mapOf(
                "type" to "org.dyn4j.collision.narrowphase.Epa",
                "getDistanceEpsilon" to epa.getDistanceEpsilon(),
                "getMaxIterations" to epa.getMaxIterations()))
    }

    fun world(value: World<Body>): Map<String, Any?> {
        val broadphase = value.getBroadphaseDetector() as? CollisionItemBroadphaseDetectorAdapter<*, *>
            ?: error("unsupported collision broadphase")
        val ccd = value.getContinuousCollisionDetectionBroadphaseDetector()
        val toi = value.getTimeOfImpactDetector() as? ConservativeAdvancement
            ?: error("unsupported time-of-impact detector")
        require(value.getContactConstraintSolver() is SequentialImpulses<*>)
        require(value.getManifoldSolver() is ClippingManifoldSolver)
        require(value.getTimeOfImpactSolver() is ForceCollisionTimeOfImpactSolver<*>)
        return mapOf(
            "gravity" to listOf(value.getGravity().x, value.getGravity().y),
            "getBroadphaseDetector" to mapOf(
                "type" to "org.dyn4j.collision.broadphase.CollisionItemBroadphaseDetectorAdapter",
                "getAABBExpansionMethod" to expansion(broadphase.getAABBExpansionMethod()),
                "getDecoratedBroadphaseDetector" to tree(broadphase.getDecoratedBroadphaseDetector()),
                "isUpdateTrackingEnabled" to broadphase.isUpdateTrackingEnabled(),
                "isUpdateTrackingSupported" to broadphase.isUpdateTrackingSupported()),
            "getContinuousCollisionDetectionBroadphaseDetector" to tree(ccd),
            "getContactConstraintSolver" to mapOf("type" to "org.dyn4j.dynamics.contact.SequentialImpulses"),
            "getManifoldSolver" to mapOf("type" to "org.dyn4j.collision.manifold.ClippingManifoldSolver"),
            "getNarrowphaseDetector" to gjk(value.getNarrowphaseDetector()),
            "getRaycastDetector" to gjk(value.getRaycastDetector()),
            "getTimeOfImpactDetector" to mapOf(
                "type" to "org.dyn4j.collision.continuous.ConservativeAdvancement",
                "getDistanceDetector" to gjk(toi.getDistanceDetector()),
                "getDistanceEpsilon" to toi.getDistanceEpsilon(),
                "getMaxIterations" to toi.getMaxIterations()),
            "getTimeOfImpactSolver" to mapOf(
                "type" to "org.dyn4j.dynamics.contact.ForceCollisionTimeOfImpactSolver"),
        )
    }
}
