/*
 * Copyright (c) 2010-2021 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.world

import org.dyn4j.JvmFieldBridge
import org.dyn4j.collision.Collisions
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.contact.ContactConstraintSolver
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.geometry.Vector2
import kotlin.math.min

class Island<T : PhysicsBody> {
    @JvmFieldBridge internal val bodies: MutableList<T>
    @JvmFieldBridge internal val joints: MutableList<Joint<T>>
    @JvmFieldBridge internal val contactConstraints: MutableList<ContactConstraint<T>>

    constructor() : this(64, 16)

    constructor(initialBodyCount: Int, initialJointCount: Int) {
        val bodyCount = if (initialBodyCount <= 0) 64 else initialBodyCount
        val jointCount = if (initialJointCount <= 0) 16 else initialJointCount
        bodies = ArrayList(bodyCount)
        joints = ArrayList(jointCount)
        contactConstraints = ArrayList(Collisions.getEstimatedCollisionPairs(bodyCount))
    }

    fun clear() {
        bodies.clear()
        joints.clear()
        contactConstraints.clear()
    }

    fun add(body: T) { bodies.add(body) }
    fun add(contactConstraint: ContactConstraint<T>) { contactConstraints.add(contactConstraint) }
    fun add(joint: Joint<T>) { joints.add(joint) }

    fun solve(solver: ContactConstraintSolver<T>, gravity: Vector2, step: TimeStep, settings: Settings) {
        val velocityIterations = settings.getVelocityConstraintSolverIterations()
        val positionIterations = settings.getPositionConstraintSolverIterations()
        val sleepTime = settings.getMinimumAtRestTime()
        val bodyCount = bodies.size
        val jointCount = joints.size
        val contactCount = contactConstraints.size

        for (i in 0 until bodyCount) bodies[i].integrateVelocity(gravity, step, settings)
        solver.initialize(contactConstraints, step, settings)
        for (i in 0 until jointCount) joints[i].initializeConstraints(step, settings)

        if (contactCount > 0 || jointCount > 0) {
            for (i in 0 until velocityIterations) {
                for (j in 0 until jointCount) joints[j].solveVelocityConstraints(step, settings)
                solver.solveVelocityContraints(contactConstraints, step, settings)
            }
        }

        for (i in 0 until bodyCount) bodies[i].integratePosition(step, settings)

        var positionConstraintsSolved = false
        for (i in 0 until positionIterations) {
            val contactsSolved = solver.solvePositionContraints(contactConstraints, step, settings)
            var jointsSolved = true
            for (j in 0 until jointCount) {
                val jointSolved = joints[j].solvePositionConstraints(step, settings)
                jointsSolved = jointsSolved && jointSolved
            }
            if (contactsSolved && jointsSolved) {
                positionConstraintsSolved = true
                break
            }
        }

        if (settings.isAtRestDetectionEnabled()) {
            var minSleepTime = Double.MAX_VALUE
            for (i in 0 until bodyCount) {
                val bodySleepTime = bodies[i].updateAtRestTime(step, settings)
                if (bodySleepTime < 0.0) continue
                minSleepTime = min(minSleepTime, bodySleepTime)
            }
            if (minSleepTime >= sleepTime && positionConstraintsSolved) {
                for (i in 0 until bodyCount) bodies[i].setAtRest(true)
            }
        }
    }
}
