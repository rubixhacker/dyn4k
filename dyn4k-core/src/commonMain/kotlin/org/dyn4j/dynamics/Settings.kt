/*
 * Copyright (c) 2010-2024 William Bittle  http://www.dyn4j.org/
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without modification, are permitted
 * provided that the following conditions are met:
 *
 *   * Redistributions of source code must retain the above copyright notice, this list of conditions
 *     and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above copyright notice, this list of conditions
 *     and the following disclaimer in the documentation and/or other materials provided with the
 *     distribution.
 *   * Neither the name of the copyright holder nor the names of its contributors may be used to endorse or
 *     promote products derived from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
 * FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
 * IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
 * OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
package org.dyn4j.dynamics

import org.dyn4j.Copyable
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import kotlin.math.PI

open class Settings : Copyable<Settings> {
    private var stepFrequency = DEFAULT_STEP_FREQUENCY
    private var maximumTranslation = DEFAULT_MAXIMUM_TRANSLATION
    private var maximumTranslationSquared = maximumTranslation * maximumTranslation
    private var maximumRotation = DEFAULT_MAXIMUM_ROTATION
    private var maximumRotationSquared = maximumRotation * maximumRotation
    private var atRestDetectionEnabled = true
    private var maximumAtRestLinearVelocity = DEFAULT_MAXIMUM_AT_REST_LINEAR_VELOCITY
    private var maximumAtRestLinearVelocitySquared = maximumAtRestLinearVelocity * maximumAtRestLinearVelocity
    private var maximumAtRestAngularVelocity = DEFAULT_MAXIMUM_AT_REST_ANGULAR_VELOCITY
    private var maximumAtRestAngularVelocitySquared = maximumAtRestAngularVelocity * maximumAtRestAngularVelocity
    private var minimumAtRestTime = DEFAULT_MINIMUM_AT_REST_TIME
    private var velocityConstraintSolverIterations = DEFAULT_VELOCITY_CONSTRAINT_SOLVER_ITERATIONS
    private var positionConstraintSolverIterations = DEFAULT_POSITION_CONSTRAINT_SOLVER_ITERATIONS
    private var warmStartingEnabled = true
    private var maximumWarmStartDistance = DEFAULT_MAXIMUM_WARM_START_DISTANCE
    private var maximumWarmStartDistanceSquared = maximumWarmStartDistance * maximumWarmStartDistance
    private var linearTolerance = DEFAULT_LINEAR_TOLERANCE
    private var linearToleranceSquared = linearTolerance * linearTolerance
    private var angularTolerance = DEFAULT_ANGULAR_TOLERANCE
    private var angularToleranceSquared = angularTolerance * angularTolerance
    private var maximumLinearCorrection = DEFAULT_MAXIMUM_LINEAR_CORRECTION
    private var maximumLinearCorrectionSquared = maximumLinearCorrection * maximumLinearCorrection
    private var maximumAngularCorrection = DEFAULT_MAXIMUM_ANGULAR_CORRECTION
    private var maximumAngularCorrectionSquared = maximumAngularCorrection * maximumAngularCorrection
    private var baumgarte = DEFAULT_BAUMGARTE
    private var continuousDetectionMode = ContinuousDetectionMode.ALL

    open fun reset() { assign(Settings()) }
    override fun copy() = Settings().also { it.set(this) }
    @Deprecated("Use set")
    open fun copy(settings: Settings?) = set(settings)
    open fun set(settings: Settings?) {
        assign(settings!!)
    }
    private fun assign(source: Settings) {
        stepFrequency = source.stepFrequency
        maximumTranslation = source.maximumTranslation
        maximumTranslationSquared = source.maximumTranslationSquared
        maximumRotation = source.maximumRotation
        maximumRotationSquared = source.maximumRotationSquared
        atRestDetectionEnabled = source.atRestDetectionEnabled
        maximumAtRestLinearVelocity = source.maximumAtRestLinearVelocity
        maximumAtRestLinearVelocitySquared = source.maximumAtRestLinearVelocitySquared
        maximumAtRestAngularVelocity = source.maximumAtRestAngularVelocity
        maximumAtRestAngularVelocitySquared = source.maximumAtRestAngularVelocitySquared
        minimumAtRestTime = source.minimumAtRestTime
        velocityConstraintSolverIterations = source.velocityConstraintSolverIterations
        positionConstraintSolverIterations = source.positionConstraintSolverIterations
        warmStartingEnabled = source.warmStartingEnabled
        maximumWarmStartDistance = source.maximumWarmStartDistance
        maximumWarmStartDistanceSquared = source.maximumWarmStartDistanceSquared
        linearTolerance = source.linearTolerance
        linearToleranceSquared = source.linearToleranceSquared
        angularTolerance = source.angularTolerance
        angularToleranceSquared = source.angularToleranceSquared
        maximumLinearCorrection = source.maximumLinearCorrection
        maximumLinearCorrectionSquared = source.maximumLinearCorrectionSquared
        maximumAngularCorrection = source.maximumAngularCorrection
        maximumAngularCorrectionSquared = source.maximumAngularCorrectionSquared
        baumgarte = source.baumgarte
        continuousDetectionMode = source.continuousDetectionMode
    }

    open fun getStepFrequency() = stepFrequency
    open fun setStepFrequency(value: Double) { positive("stepFrequency", value); stepFrequency = value }
    open fun getMaximumTranslation() = maximumTranslation
    open fun getMaximumTranslationSquared() = maximumTranslationSquared
    open fun setMaximumTranslation(value: Double) { nonnegative("maximumTranslation", value); maximumTranslation = value; maximumTranslationSquared = value * value }
    open fun getMaximumRotation() = maximumRotation
    open fun getMaximumRotationSquared() = maximumRotationSquared
    open fun setMaximumRotation(value: Double) { nonnegative("maximumRotation", value); maximumRotation = value; maximumRotationSquared = value * value }
    open fun isAtRestDetectionEnabled() = atRestDetectionEnabled
    open fun setAtRestDetectionEnabled(flag: Boolean) { atRestDetectionEnabled = flag }
    open fun getMaximumAtRestLinearVelocity() = maximumAtRestLinearVelocity
    open fun getMaximumAtRestLinearVelocitySquared() = maximumAtRestLinearVelocitySquared
    open fun setMaximumAtRestLinearVelocity(value: Double) { nonnegative("maximumAtRestLinearVelocity", value); maximumAtRestLinearVelocity = value; maximumAtRestLinearVelocitySquared = value * value }
    open fun getMaximumAtRestAngularVelocity() = maximumAtRestAngularVelocity
    open fun getMaximumAtRestAngularVelocitySquared() = maximumAtRestAngularVelocitySquared
    open fun setMaximumAtRestAngularVelocity(value: Double) { nonnegative("maximumAtRestAngularVelocity", value); maximumAtRestAngularVelocity = value; maximumAtRestAngularVelocitySquared = value * value }
    open fun getMinimumAtRestTime() = minimumAtRestTime
    open fun setMinimumAtRestTime(value: Double) { nonnegative("minimumAtRestTime", value); minimumAtRestTime = value }
    open fun getVelocityConstraintSolverIterations() = velocityConstraintSolverIterations
    open fun setVelocityConstraintSolverIterations(value: Int) { atLeastOne("velocityConstraintSolverIterations", value); velocityConstraintSolverIterations = value }
    open fun getPositionConstraintSolverIterations() = positionConstraintSolverIterations
    open fun setPositionConstraintSolverIterations(value: Int) { atLeastOne("positionConstraintSolverIterations", value); positionConstraintSolverIterations = value }
    open fun getMaximumWarmStartDistance() = maximumWarmStartDistance
    open fun getMaximumWarmStartDistanceSquared() = maximumWarmStartDistanceSquared
    open fun setMaximumWarmStartDistance(value: Double) { nonnegative("maximumWarmStartDistance", value); maximumWarmStartDistance = value; maximumWarmStartDistanceSquared = value * value }
    open fun isWarmStartingEnabled() = warmStartingEnabled
    open fun setWarmStartingEnabled(flag: Boolean) { warmStartingEnabled = flag }
    open fun getLinearTolerance() = linearTolerance
    open fun getLinearToleranceSquared() = linearToleranceSquared
    open fun setLinearTolerance(value: Double) { nonnegative("linearTolerance", value); linearTolerance = value; linearToleranceSquared = value * value }
    open fun getAngularTolerance() = angularTolerance
    open fun getAngularToleranceSquared() = angularToleranceSquared
    open fun setAngularTolerance(value: Double) { nonnegative("angularTolerance", value); angularTolerance = value; angularToleranceSquared = value * value }
    open fun getMaximumLinearCorrection() = maximumLinearCorrection
    open fun getMaximumLinearCorrectionSquared() = maximumLinearCorrectionSquared
    open fun setMaximumLinearCorrection(value: Double) { nonnegative("maximumLinearCorrection", value); maximumLinearCorrection = value; maximumLinearCorrectionSquared = value * value }
    open fun getMaximumAngularCorrection() = maximumAngularCorrection
    open fun getMaximumAngularCorrectionSquared() = maximumAngularCorrectionSquared
    open fun setMaximumAngularCorrection(value: Double) { nonnegative("maximumAngularCorrection", value); maximumAngularCorrection = value; maximumAngularCorrectionSquared = value * value }
    open fun getBaumgarte() = baumgarte
    open fun setBaumgarte(value: Double) { nonnegative("baumgarte", value); baumgarte = value }
    open fun getContinuousDetectionMode() = continuousDetectionMode
    open fun setContinuousDetectionMode(mode: ContinuousDetectionMode?) { continuousDetectionMode = mode ?: throw ArgumentNullException("mode") }

    override fun toString() = "Settings[StepFrequency=$stepFrequency|MaximumTranslation=$maximumTranslation|MaximumRotation=$maximumRotation|AutoSleepingEnabled=$atRestDetectionEnabled|AtRestLinearVelocity=$maximumAtRestLinearVelocity|AtRestAngularVelocity=$maximumAtRestAngularVelocity|AtRestTime=$minimumAtRestTime|VelocityConstraintSolverIterations=$velocityConstraintSolverIterations|PositionConstraintSolverIterations=$positionConstraintSolverIterations|WarmStartingEnabled=$warmStartingEnabled|MaximumWarmStartDistance=$maximumWarmStartDistance|LinearTolerance=$linearTolerance|AngularTolerance=$angularTolerance|MaximumLinearCorrection=$maximumLinearCorrection|MaximumAngularCorrection=$maximumAngularCorrection|Baumgarte=$baumgarte|ContinuousDetectionMode=$continuousDetectionMode]"

    private fun nonnegative(name: String, value: Double) {
        if (value < 0.0) throw ValueOutOfRangeException(name, value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
    }
    private fun positive(name: String, value: Double) {
        if (value <= 0.0) throw ValueOutOfRangeException(name, value, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
    }
    private fun atLeastOne(name: String, value: Int) {
        if (value < 1) throw ValueOutOfRangeException(name, value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 1)
    }

    companion object {
        const val DEFAULT_STEP_FREQUENCY = 1.0 / 60.0
        const val DEFAULT_MAXIMUM_TRANSLATION = 2.0
        const val DEFAULT_MAXIMUM_ROTATION = 0.5 * PI
        const val DEFAULT_MAXIMUM_AT_REST_LINEAR_VELOCITY = 0.01
        @kotlin.jvm.JvmField val DEFAULT_MAXIMUM_AT_REST_ANGULAR_VELOCITY = 2.0 / 180.0 * PI
        const val DEFAULT_MINIMUM_AT_REST_TIME = 0.5
        @Deprecated("Use separate velocity and position iteration constants")
        const val DEFAULT_SOLVER_ITERATIONS = 10
        const val DEFAULT_VELOCITY_CONSTRAINT_SOLVER_ITERATIONS = 6
        const val DEFAULT_POSITION_CONSTRAINT_SOLVER_ITERATIONS = 2
        const val DEFAULT_MAXIMUM_WARM_START_DISTANCE = 1.0e-2
        const val DEFAULT_LINEAR_TOLERANCE = 0.005
        @kotlin.jvm.JvmField val DEFAULT_ANGULAR_TOLERANCE = 2.0 / 180.0 * PI
        const val DEFAULT_MAXIMUM_LINEAR_CORRECTION = 0.2
        @kotlin.jvm.JvmField val DEFAULT_MAXIMUM_ANGULAR_CORRECTION = 8.0 / 180.0 * PI
        const val DEFAULT_BAUMGARTE = 0.2
    }
}
