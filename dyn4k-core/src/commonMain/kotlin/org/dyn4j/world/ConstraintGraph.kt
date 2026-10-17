/*
 * Copyright (c) 2010-2022 William Bittle  http://www.dyn4j.org/
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

import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.contact.ContactConstraintSolver
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.geometry.Vector2

class ConstraintGraph<T : PhysicsBody> {
    private val graph: MutableMap<T, ConstraintGraphNode<T>>
    private val stack: ArrayDeque<ConstraintGraphNode<T>>
    private val onIsland: MutableSet<Any>
    private val staticOnIsland: MutableSet<Any>
    private val island: Island<T>

    constructor() : this(64, 16)

    constructor(initialBodyCount: Int, initialJointCount: Int) {
        val bodyCount = if (initialBodyCount <= 0) 64 else initialBodyCount
        val jointCount = if (initialJointCount <= 0) 16 else initialJointCount
        graph = LinkedHashMap(bodyCount)
        stack = ArrayDeque()
        onIsland = HashSet()
        staticOnIsland = HashSet()
        island = Island(bodyCount, jointCount)
    }

    fun addBody(body: T) {
        if (graph[body] == null) graph[body] = ConstraintGraphNode(body)
    }

    fun addContactConstraint(contactConstraint: ContactConstraint<T>) {
        val body1 = contactConstraint.getBody1()
        val body2 = contactConstraint.getBody2()
        val node1 = graph.getOrPut(body1) { ConstraintGraphNode(body1) }
        val node2 = graph.getOrPut(body2) { ConstraintGraphNode(body2) }
        node1.mutableContacts().add(contactConstraint)
        node2.mutableContacts().add(contactConstraint)
    }

    fun addJoint(joint: Joint<T>) {
        for (i in 0 until joint.getBodyCount()) {
            val body = joint.getBody(i)
            graph.getOrPut(body) { ConstraintGraphNode(body) }.mutableJoints().add(joint)
        }
    }

    fun containsBody(body: T?): Boolean = graph.containsKey(body)

    fun removeBody(body: T): ConstraintGraphNode<T> {
        val node = graph.remove(body)!!
        for (joint in node.mutableJoints()) {
            for (i in 0 until joint.getBodyCount()) {
                graph[joint.getBody(i)]?.mutableJoints()?.remove(joint)
            }
        }
        for (constraint in node.mutableContacts()) {
            graph[constraint.getOtherBody(body)!!]!!.mutableContacts().remove(constraint)
        }
        return node
    }

    fun containsJoint(joint: Joint<T>): Boolean {
        val first = graph[joint.getBody(0)]
        var bodiesExist = first != null
        var jointLinksExist = first?.mutableJoints()?.contains(joint) == true
        for (i in 1 until joint.getBodyCount()) {
            val node = graph[joint.getBody(i)]
            bodiesExist = bodiesExist && node != null
            if (node != null) jointLinksExist = jointLinksExist && node.mutableJoints().contains(joint)
        }
        return bodiesExist && jointLinksExist
    }

    fun containsContactConstraint(contactConstraint: ContactConstraint<T>): Boolean {
        val body1 = contactConstraint.getBody1()
        val body2 = contactConstraint.getBody2()
        val first = if (body1 == null) null else graph[body1]
        val second = if (body2 == null) null else graph[body2]
        return first?.mutableContacts()?.contains(contactConstraint) == true &&
            second?.mutableContacts()?.contains(contactConstraint) == true
    }

    fun removeJoint(joint: Joint<T>) {
        for (i in 0 until joint.getBodyCount()) {
            graph[joint.getBody(i)]?.mutableJoints()?.remove(joint)
        }
    }

    fun removeContactConstraint(contactConstraint: ContactConstraint<T>) {
        val body1 = contactConstraint.getBody1()
        val body2 = contactConstraint.getBody2()
        if (body1 != null) graph[body1]?.mutableContacts()?.remove(contactConstraint)
        if (body2 != null) graph[body2]?.mutableContacts()?.remove(contactConstraint)
    }

    fun getNode(body: T?): ConstraintGraphNode<T>? = graph[body]

    fun removeAllContactConstraints() {
        for (node in graph.values) node.mutableContacts().clear()
    }

    fun removeAllJoints() {
        for (node in graph.values) node.mutableJoints().clear()
    }

    fun clear() { graph.clear() }
    fun size(): Int = graph.size

    fun isInContact(body1: T, body2: T): Boolean {
        val contacts = graph[body1]?.mutableContacts() ?: return false
        for (constraint in contacts) {
            if (constraint.getBody1() === body2 || constraint.getBody2() === body2) return true
        }
        return false
    }

    fun getContacts(body: T?): List<ContactConstraint<T>> =
        graph[body]?.getContactConstraints() ?: ArrayList()

    fun getInContactBodies(body: T?, includeSensedContact: Boolean): List<T> {
        val bodies = ArrayList<T>()
        val contacts = graph[body]?.mutableContacts() ?: return bodies
        for (constraint in contacts) {
            if (!includeSensedContact && constraint.isSensor()) continue
            val other = constraint.getOtherBody(body)!!
            if (!bodies.contains(other)) bodies.add(other)
        }
        return bodies
    }

    fun isJointCollisionAllowed(body1: T?, body2: T?): Boolean {
        if (body1 == null || body2 == null) return false
        val node1 = graph[body1] ?: return false
        if (graph[body2] == null) return false
        val joints = node1.mutableJoints()
        if (joints.isEmpty()) return true
        var connected = false
        for (joint in joints) {
            if (joint.isMember(body2)) {
                connected = true
                if (joint.isCollisionAllowed()) return true
            }
        }
        return !connected
    }

    fun isJoined(body1: T?, body2: T?): Boolean {
        if (body1 == null || body2 == null) return false
        val joints = graph[body1]?.mutableJoints() ?: return false
        for (joint in joints) if (joint.isMember(body2)) return true
        return false
    }

    fun getJoints(body: T?): List<Joint<T>> = graph[body]?.getJoints() ?: ArrayList()

    fun getJoinedBodies(body: T?): List<T> {
        val bodies = ArrayList<T>()
        val joints = graph[body]?.mutableJoints() ?: return bodies
        for (joint in joints) {
            for (i in 0 until joint.getBodyCount()) {
                val other = joint.getBody(i)
                if (other === body) continue
                if (!bodies.contains(other)) bodies.add(other)
            }
        }
        return bodies
    }

    fun solve(solver: ContactConstraintSolver<T>, gravity: Vector2, step: TimeStep, settings: Settings) {
        stack.clear()
        onIsland.clear()
        staticOnIsland.clear()

        for (seed in graph.values) {
            val seedBody = seed.getBody()
            if (onIsland.contains(seedBody) || seedBody.isAtRest() || !seedBody.isEnabled() || seedBody.isStatic()) {
                continue
            }

            island.clear()
            stack.clear()
            stack.addFirst(seed)
            while (stack.isNotEmpty()) {
                val node = stack.removeFirst()
                val body = node.getBody()
                if (onIsland.contains(body) || staticOnIsland.contains(body)) continue

                island.add(body)
                body.setAtRest(false)
                if (body.isStatic()) {
                    staticOnIsland.add(body)
                    continue
                }
                onIsland.add(body)

                for (constraint in node.mutableContacts()) {
                    if (!constraint.isEnabled() || constraint.isSensor() || onIsland.contains(constraint)) continue
                    val other = constraint.getOtherBody(body)!!
                    island.add(constraint)
                    onIsland.add(constraint)
                    if (!onIsland.contains(other) && !staticOnIsland.contains(other)) {
                        stack.addFirst(graph[other]!!)
                    }
                }

                for (joint in node.mutableJoints()) {
                    if (!joint.isEnabled() || onIsland.contains(joint)) continue
                    island.add(joint)
                    onIsland.add(joint)
                    for (i in 0 until joint.getBodyCount()) {
                        val other = joint.getBody(i)
                        if (other === body || !other.isEnabled()) continue
                        if (!onIsland.contains(other) && !staticOnIsland.contains(other)) {
                            stack.addFirst(graph[other]!!)
                        }
                    }
                }
            }

            island.solve(solver, gravity, step, settings)
            staticOnIsland.clear()
        }

        stack.clear()
        island.clear()
        onIsland.clear()
    }
}
