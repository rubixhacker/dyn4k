package org.dyn4j.dynamics.contact

import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep

// Type declaration needed by the unchanged generic Java solver; contacts are outside this probe.
class ContactConstraint<T : PhysicsBody>
interface ContactConstraintSolver<T : PhysicsBody> {
    fun initialize(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings)
    fun solveVelocityContraints(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings)
    fun solvePositionContraints(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings): Boolean
}
