package org.dyn4j.world

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.ContinuousDetectionMode
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.contact.SequentialImpulses
import org.dyn4j.dynamics.contact.TimeOfImpactSolver
import org.dyn4j.dynamics.joint.PinJoint
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.continuous.TimeOfImpactDetector
import org.dyn4j.collision.broadphase.BroadphaseDetector
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.listener.StepListenerAdapter
import org.dyn4j.world.listener.StepListener
import org.dyn4j.world.listener.ContactListenerAdapter
import org.dyn4j.world.listener.DestructionListenerAdapter
import org.dyn4j.dynamics.joint.Joint

val PhysicsWorldJourneyTest by testSuite {
    test("kotlinSubclassKeepsProtectedStateAndFactoryDispatch") { PhysicsWorldJourneyTestFixture().run { kotlinSubclassKeepsProtectedStateAndFactoryDispatch() } }
    test("elapsedTimeStepsAndCarriesTheRemainder") { PhysicsWorldJourneyTestFixture().run { elapsedTimeStepsAndCarriesTheRemainder() } }
    test("removingBodyClearsOwnershipAndWorldState") { PhysicsWorldJourneyTestFixture().run { removingBodyClearsOwnershipAndWorldState() } }
    test("jointIteratorRemovesTheJointFromTheWorld") { PhysicsWorldJourneyTestFixture().run { jointIteratorRemovesTheJointFromTheWorld() } }
    test("savedStepListenerViewIteratorRejectsStructuralChangeOnly") { PhysicsWorldJourneyTestFixture().run { savedStepListenerViewIteratorRejectsStructuralChangeOnly() } }
    test("savedJointViewIteratorRejectsStructuralChangeOnly") { PhysicsWorldJourneyTestFixture().run { savedJointViewIteratorRejectsStructuralChangeOnly() } }
    test("protectedBackingIteratorsRejectStructuralChangeOnly") { PhysicsWorldJourneyTestFixture().run { protectedBackingIteratorsRejectStructuralChangeOnly() } }
    test("publicSubListsRejectStructuralChangeOnly") { PhysicsWorldJourneyTestFixture().run { publicSubListsRejectStructuralChangeOnly() } }
    test("protectedSubListsRejectStructuralChangeOnly") { PhysicsWorldJourneyTestFixture().run { protectedSubListsRejectStructuralChangeOnly() } }
    test("emptyProtectedSubListClearInvalidatesSavedWorldTraversals") { PhysicsWorldJourneyTestFixture().run { emptyProtectedSubListClearInvalidatesSavedWorldTraversals() } }
    test("trackedSortInvalidatesSavedIteratorsAndSubLists") { PhysicsWorldJourneyTestFixture().run { trackedSortInvalidatesSavedIteratorsAndSubLists() } }
    test("trackedReplaceAllInvalidatesSavedIteratorsAndSubLists") { PhysicsWorldJourneyTestFixture().run { trackedReplaceAllInvalidatesSavedIteratorsAndSubLists() } }
    test("trackedRemoveIfDoesNotPartiallyRemoveWhenPredicateThrows") { PhysicsWorldJourneyTestFixture().run { trackedRemoveIfDoesNotPartiallyRemoveWhenPredicateThrows() } }
    test("protectedNestedSubListChangesKeepParentLiveAndInvalidateSiblings") { PhysicsWorldJourneyTestFixture().run { protectedNestedSubListChangesKeepParentLiveAndInvalidateSiblings() } }
    test("publicSubListsUseBaselineRangeErrors") { PhysicsWorldJourneyTestFixture().run { publicSubListsUseBaselineRangeErrors() } }
    test("worldListsAndSubListsMarkRandomAccess") { PhysicsWorldJourneyTestFixture().run { worldListsAndSubListsMarkRandomAccess() } }
    test("allWorldAndGraphPublicViewsKeepIdentityAndRandomAccess") { PhysicsWorldJourneyTestFixture().run { allWorldAndGraphPublicViewsKeepIdentityAndRandomAccess() } }
    test("emptyPublicViewRejectsDefaultMutations") { PhysicsWorldJourneyTestFixture().run { emptyPublicViewRejectsDefaultMutations() } }
    test("removingBodyDestroysAttachedJointAndNotifiesListeners") { PhysicsWorldJourneyTestFixture().run { removingBodyDestroysAttachedJointAndNotifiesListeners() } }
    test("stepListenersObserveTheBaselineStageOrder") { PhysicsWorldJourneyTestFixture().run { stepListenersObserveTheBaselineStageOrder() } }
    test("overlappingBodiesReachContactListenersAndCustomSolver") { PhysicsWorldJourneyTestFixture().run { overlappingBodiesReachContactListenersAndCustomSolver() } }
    test("nullableListenerEntriesFollowTheBaselineListContract") { PhysicsWorldJourneyTestFixture().run { nullableListenerEntriesFollowTheBaselineListContract() } }
    test("sleepingBodyWakesAndMovesAfterImpulse") { PhysicsWorldJourneyTestFixture().run { sleepingBodyWakesAndMovesAfterImpulse() } }
    test("configuredTimeOfImpactSolverReceivesBulletCollision") { PhysicsWorldJourneyTestFixture().run { configuredTimeOfImpactSolverReceivesBulletCollision() } }
}

private class PhysicsWorldJourneyTestFixture  {
    private class ExtendedWorld : World<Body>() {
        var created = 0

        fun replaceStepListener(index: Int, listener: StepListener<Body>) {
            stepListeners[index] = listener
        }

        fun replaceJoint(index: Int, joint: Joint<Body>) {
            joints[index] = joint
        }

        fun stepBackingIterator(): MutableIterator<StepListener<Body>?> = stepListeners.iterator()
        fun jointBackingIterator(): MutableIterator<Joint<Body>> = joints.iterator()
        fun stepBackingSubList(): MutableList<StepListener<Body>?> = stepListeners.subList(0, 1)
        fun jointBackingSubList(): MutableList<Joint<Body>> = joints.subList(0, 1)
        fun clearEmptyStepSubList() { stepListeners.subList(0, 0).clear() }
        fun backingListsHaveRandomAccess(): Boolean =
            stepListeners is RandomAccess && joints is RandomAccess

        fun protectedStateMatchesPublic(): Boolean =
            settings === getSettings() && gravity === getGravity() &&
                contactConstraintSolver === getContactConstraintSolver()

        protected override fun createCollisionData(
            pair: CollisionPair<org.dyn4j.collision.CollisionItem<Body, org.dyn4j.dynamics.BodyFixture>>
        ): WorldCollisionData<Body> {
            created++
            return super.createCollisionData(pair)
        }
    }

fun kotlinSubclassKeepsProtectedStateAndFactoryDispatch() {
        val world = ExtendedWorld()
        world.setGravity(0.0, 0.0)
        assertTrue(world.protectedStateMatchesPublic())
        val moving = Body()
        moving.addFixture(Circle(1.0))
        moving.setMass(MassType.NORMAL)
        val fixed = Body()
        fixed.addFixture(Circle(1.0))
        world.addBody(moving)
        world.addBody(fixed)

        world.step(1)
        assertTrue(world.created > 0)
        assertTrue(world.protectedStateMatchesPublic())
    }

fun elapsedTimeStepsAndCarriesTheRemainder() {
        val world = World<Body>()
        val frequency = world.getSettings().getStepFrequency()

        assertFalse(world.update(frequency / 2.0))
        assertEquals(frequency / 2.0, world.getAccumulatedTime(), 1.0e-12)
        assertTrue(world.update(frequency / 2.0))
        assertEquals(0.0, world.getAccumulatedTime(), 1.0e-12)
    }

fun removingBodyClearsOwnershipAndWorldState() {
        val world = World<Body>()
        val body = Body()
        body.addFixture(Circle(1.0))
        world.addBody(body)

        assertSame(world, body.getOwner())
        assertTrue(world.removeBody(body))
        assertEquals(null, body.getOwner())
        assertTrue(world.isEmpty())
    }

fun jointIteratorRemovesTheJointFromTheWorld() {
        val world = World<Body>()
        val body = Body()
        world.addBody(body)
        val joint = PinJoint(body, Vector2())
        world.addJoint(joint)
        val view = world.getJoints()
        val iterator = world.getJointIterator()

        assertSame(joint, iterator.next())
        iterator.remove()
        assertFailsWith<IllegalStateException> { iterator.remove() }
        assertTrue(view.isEmpty())
        assertEquals(null, joint.getOwner())
    }

fun savedStepListenerViewIteratorRejectsStructuralChangeOnly() {
        val world = ExtendedWorld()
        val first = StepListenerAdapter<Body>()
        val replacement = StepListenerAdapter<Body>()
        world.addStepListener(first)
        val view = world.getStepListeners()
        assertSame(view, world.getStepListeners())
        val afterSet = view.iterator()
        world.replaceStepListener(0, replacement)
        assertSame(replacement, afterSet.next())

        val beforeAdd = view.iterator()
        world.addStepListener(StepListenerAdapter())
        assertEquals(2, view.size)
        assertFailsWith<ConcurrentModificationException> { beforeAdd.next() }
    }

fun savedJointViewIteratorRejectsStructuralChangeOnly() {
        val world = ExtendedWorld()
        val body = Body()
        world.addBody(body)
        val first = PinJoint(body, Vector2())
        world.addJoint(first)
        val view = world.getJoints()
        assertSame(view, world.getJoints())
        val afterSet = view.iterator()
        world.replaceJoint(0, first)
        assertSame(first, afterSet.next())

        val beforeAdd = view.iterator()
        world.addJoint(PinJoint(body, Vector2()))
        assertEquals(2, view.size)
        assertFailsWith<ConcurrentModificationException> { beforeAdd.next() }
    }

fun protectedBackingIteratorsRejectStructuralChangeOnly() {
        val world = ExtendedWorld()
        val first = StepListenerAdapter<Body>()
        val replacement = StepListenerAdapter<Body>()
        world.addStepListener(first)
        val afterStepSet = world.stepBackingIterator()
        world.replaceStepListener(0, replacement)
        assertSame(replacement, afterStepSet.next())
        val beforeStepAdd = world.stepBackingIterator()
        world.addStepListener(StepListenerAdapter())
        assertFailsWith<ConcurrentModificationException> { beforeStepAdd.next() }

        val body = Body()
        world.addBody(body)
        val joint = PinJoint(body, Vector2())
        world.addJoint(joint)
        val afterJointSet = world.jointBackingIterator()
        world.replaceJoint(0, joint)
        assertSame(joint, afterJointSet.next())
        val beforeJointAdd = world.jointBackingIterator()
        world.addJoint(PinJoint(body, Vector2()))
        assertFailsWith<ConcurrentModificationException> { beforeJointAdd.next() }
    }

fun publicSubListsRejectStructuralChangeOnly() {
        val world = ExtendedWorld()
        val first = StepListenerAdapter<Body>()
        val replacement = StepListenerAdapter<Body>()
        world.addStepListener(first)
        val listeners = world.getStepListeners()
        val stepSubList = listeners.subList(0, 1)
        world.replaceStepListener(0, replacement)
        assertSame(replacement, stepSubList[0])
        world.addStepListener(StepListenerAdapter())
        assertEquals(2, listeners.size)
        assertFailsWith<ConcurrentModificationException> { stepSubList[0] }

        val body = Body()
        world.addBody(body)
        val joint = PinJoint(body, Vector2())
        world.addJoint(joint)
        val joints = world.getJoints()
        val jointSubList = joints.subList(0, 1)
        world.replaceJoint(0, joint)
        assertSame(joint, jointSubList[0])
        world.addJoint(PinJoint(body, Vector2()))
        assertEquals(2, joints.size)
        assertFailsWith<ConcurrentModificationException> { jointSubList[0] }
    }

fun protectedSubListsRejectStructuralChangeOnly() {
        val world = ExtendedWorld()
        val first = StepListenerAdapter<Body>()
        val replacement = StepListenerAdapter<Body>()
        world.addStepListener(first)
        val steps = world.stepBackingSubList()
        world.replaceStepListener(0, replacement)
        assertSame(replacement, steps[0])
        world.addStepListener(StepListenerAdapter())
        assertFailsWith<ConcurrentModificationException> { steps[0] }
        assertFailsWith<ConcurrentModificationException> { steps.size }

        val body = Body()
        world.addBody(body)
        val joint = PinJoint(body, Vector2())
        world.addJoint(joint)
        val joints = world.jointBackingSubList()
        world.replaceJoint(0, joint)
        assertSame(joint, joints[0])
        world.addJoint(PinJoint(body, Vector2()))
        assertFailsWith<ConcurrentModificationException> { joints[0] }
        assertFailsWith<ConcurrentModificationException> { joints.size }
    }

fun emptyProtectedSubListClearInvalidatesSavedWorldTraversals() {
        val world = ExtendedWorld()
        val first = StepListenerAdapter<Body>()
        world.addStepListener(first)
        val view = world.getStepListeners()
        val iterator = world.stepBackingIterator()
        val protectedSublist = world.stepBackingSubList()
        val publicSublist = view.subList(0, 1)
        world.clearEmptyStepSubList()
        assertSame(view, world.getStepListeners())
        assertSame(first, view[0])
        val iteratorOutcome = worldNestedViewOutcome(WorldViewOperation.EMPTY_CLEAR_ROOT_ITERATOR)
        val iteratorValue = assertWorldViewOutcome(iteratorOutcome) { iterator.next() }
        if (iteratorOutcome == WorldViewOutcome.VALUE) assertSame(first, iteratorValue)
        val protectedOutcome = worldNestedViewOutcome(WorldViewOperation.EMPTY_CLEAR_SIBLING_READ)
        val protectedValue = assertWorldViewOutcome(protectedOutcome) { protectedSublist[0] }
        if (protectedOutcome == WorldViewOutcome.VALUE) assertSame(first, protectedValue)
        val publicOutcome = worldNestedViewOutcome(WorldViewOperation.EMPTY_CLEAR_PUBLIC_READ)
        val publicValue = assertWorldViewOutcome(publicOutcome) { publicSublist[0] }
        if (publicOutcome == WorldViewOutcome.VALUE) assertSame(first, publicValue)
    }

fun trackedSortInvalidatesSavedIteratorsAndSubLists() {
        val backing = WorldTrackedArrayList<StepListener<Body>?>()
        val listener = StepListenerAdapter<Body>()
        backing.add(listener)
        val publicView = backing.liveView()
        val iterator = backing.iterator()
        val protectedSublist = backing.subList(0, 1)
        val publicSublist = publicView.subList(0, 1)
        backing.sortElements(Comparator { _, _ -> 0 })
        assertSame(listener, publicView[0])
        assertFailsWith<ConcurrentModificationException> { iterator.next() }
        assertFailsWith<ConcurrentModificationException> { protectedSublist[0] }
        assertFailsWith<ConcurrentModificationException> { publicSublist[0] }
    }

fun trackedReplaceAllInvalidatesSavedIteratorsAndSubLists() {
        val backing = WorldTrackedArrayList<StepListener<Body>?>()
        val listener = StepListenerAdapter<Body>()
        backing.add(listener)
        val publicView = backing.liveView()
        val iterator = backing.iterator()
        val protectedSublist = backing.subList(0, 1)
        val publicSublist = publicView.subList(0, 1)
        backing.replaceAllElements { it }
        assertSame(listener, publicView[0])
        assertFailsWith<ConcurrentModificationException> { iterator.next() }
        assertFailsWith<ConcurrentModificationException> { protectedSublist[0] }
        assertFailsWith<ConcurrentModificationException> { publicSublist[0] }
    }

fun trackedRemoveIfDoesNotPartiallyRemoveWhenPredicateThrows() {
        val backing = WorldTrackedArrayList<StepListener<Body>?>()
        val first = StepListenerAdapter<Body>()
        val second = StepListenerAdapter<Body>()
        backing.add(first)
        backing.add(second)
        val publicView = backing.liveView()
        val iterator = backing.iterator()
        val protectedSublist = backing.subList(0, 1)
        var visited = 0
        assertFailsWith<IllegalStateException> {
            backing.removeIfElements {
                if (visited++ == 1) throw IllegalStateException()
                true
            }
        }
        assertEquals(2, publicView.size)
        assertSame(first, iterator.next())
        assertSame(first, protectedSublist[0])
        val beforeRemoval = backing.iterator()
        assertTrue(backing.removeIfElements { it === first })
        assertSame(second, publicView[0])
        assertFailsWith<ConcurrentModificationException> { beforeRemoval.next() }
    }

fun protectedNestedSubListChangesKeepParentLiveAndInvalidateSiblings() {
        val world = ExtendedWorld()
        val first = StepListenerAdapter<Body>()
        val added = StepListenerAdapter<Body>()
        world.addStepListener(first)
        val parent = world.stepBackingSubList()
        val nested = parent.subList(0, 1)
        val sibling = parent.subList(0, 1)
        nested.add(added)
        assertEquals(2, parent.size)
        assertSame(added, parent[1])
        assertSame(added, world.getStepListeners()[1])
        assertFailsWith<ConcurrentModificationException> { sibling[0] }
        val iterator = nested.listIterator()
        assertSame(first, iterator.next())
        iterator.remove()
        assertEquals(1, parent.size)
        assertSame(added, world.getStepListeners()[0])
    }

fun publicSubListsUseBaselineRangeErrors() {
        val world = World<Body>()
        world.addStepListener(StepListenerAdapter())
        val views: List<List<*>> = listOf(world.getStepListeners(), world.getJoints())
        for (view in views) {
            assertFailsWith<IllegalArgumentException> { view.subList(1, 0) }
            assertFailsWith<IndexOutOfBoundsException> { view.subList(-1, 0) }
        }
    }

fun worldListsAndSubListsMarkRandomAccess() {
        val world = ExtendedWorld()
        val body = Body()
        world.addBody(body)
        world.addStepListener(StepListenerAdapter())
        world.addJoint(PinJoint(body, Vector2()))
        assertTrue(world.backingListsHaveRandomAccess())
        val views = listOf(world.getStepListeners(), world.getJoints())
        for (view in views) {
            assertTrue(view is RandomAccess)
            assertTrue(view.subList(0, 1) is RandomAccess)
        }
    }

fun allWorldAndGraphPublicViewsKeepIdentityAndRandomAccess() {
        val world = World<Body>()
        val graph = ConstraintGraph<Body>()
        val graphBody = Body()
        graph.addBody(graphBody)
        val node = graph.getNode(graphBody)!!
        val getters: List<() -> List<*>> = listOf(
            { world.getBodies() }, { world.getCollisionListeners() }, { world.getBoundsListeners() },
            { world.getJoints() }, { world.getContactListeners() }, { world.getDestructionListeners() },
            { world.getTimeOfImpactListeners() }, { world.getStepListeners() },
            { node.getContactConstraints() }, { node.getJoints() }
        )
        for (getView in getters) {
            val view = getView()
            assertSame(view, getView())
            assertTrue(view is RandomAccess)
            assertTrue(view.subList(0, 0) is RandomAccess)
        }
        val bodies = world.getBodies()
        val body = Body()
        world.addBody(body)
        assertSame(bodies, world.getBodies())
        assertSame(body, bodies[0])
    }

fun emptyPublicViewRejectsDefaultMutations() {
        val world = World<Body>()
        val graph = ConstraintGraph<Body>()
        val body = Body()
        graph.addBody(body)
        val node = graph.getNode(body)!!
        val views: List<List<*>> = listOf(
            world.getStepListeners(), world.getJoints(), node.getContactConstraints(), node.getJoints()
        )
        for (view in views) {
            val mutableView = view as MutableList<*>
            assertFailsWith<UnsupportedOperationException> { mutableView.removeAll(emptyList()) }
            assertFailsWith<UnsupportedOperationException> { mutableView.clear() }
        }
    }

fun removingBodyDestroysAttachedJointAndNotifiesListeners() {
        val world = World<Body>()
        val body = Body()
        world.addBody(body)
        val joint = PinJoint(body, Vector2())
        world.addJoint(joint)
        var destroyed = 0
        world.addDestructionListener(object : DestructionListenerAdapter<Body>() {
            override fun destroyed(joint: Joint<Body>?) {
                destroyed++
            }
        })

        assertTrue(world.removeBody(body, true))
        assertEquals(1, destroyed)
        assertEquals(0, world.getJointCount())
        assertEquals(null, joint.getOwner())
    }

fun stepListenersObserveTheBaselineStageOrder() {
        val world = World<Body>()
        val stages = ArrayList<String>()
        world.addStepListener(object : StepListenerAdapter<Body>() {
            override fun begin(step: org.dyn4j.dynamics.TimeStep?, world: PhysicsWorld<Body, *>?) {
                stages.add("begin")
            }

            override fun updatePerformed(step: org.dyn4j.dynamics.TimeStep?, world: PhysicsWorld<Body, *>?) {
                stages.add("update")
            }

            override fun postSolve(step: org.dyn4j.dynamics.TimeStep?, world: PhysicsWorld<Body, *>?) {
                stages.add("postSolve")
            }

            override fun end(step: org.dyn4j.dynamics.TimeStep?, world: PhysicsWorld<Body, *>?) {
                stages.add("end")
            }
        })

        world.step(1)
        assertEquals(listOf("begin", "update", "postSolve", "end"), stages)
        stages.clear()
        world.step(1)
        assertEquals(listOf("begin", "postSolve", "end"), stages)
    }

fun overlappingBodiesReachContactListenersAndCustomSolver() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val dynamic = Body()
        dynamic.addFixture(Circle(1.0))
        dynamic.setMass(MassType.NORMAL)
        val fixed = Body()
        fixed.addFixture(Circle(1.0))
        world.addBody(dynamic)
        world.addBody(fixed)

        var began = 0
        var initialized = 0
        world.addContactListener(object : ContactListenerAdapter<Body>() {
            override fun begin(collision: ContactCollisionData<Body>?, contact: Contact?) {
                began++
            }
        })
        world.setContactConstraintSolver(object : SequentialImpulses<Body>() {
            override fun initialize(contactConstraints: List<ContactConstraint<Body>>, step: TimeStep, settings: Settings) {
                initialized++
                super.initialize(contactConstraints, step, settings)
            }
        })

        world.step(1)
        assertTrue(began > 0)
        assertTrue(initialized > 0)
    }

fun nullableListenerEntriesFollowTheBaselineListContract() {
        val world = World<Body>()
        val listeners = world.getContactListeners()

        assertTrue(world.addContactListener(null))
        assertEquals(1, listeners.size)
        assertNull(listeners[0])
        assertTrue(world.removeContactListener(null))
        assertTrue(listeners.isEmpty())
    }

fun sleepingBodyWakesAndMovesAfterImpulse() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val body = Body()
        body.addFixture(Circle(0.5))
        body.setMass(MassType.NORMAL)
        world.addBody(body)

        body.setAtRest(true)
        assertTrue(body.isAtRest())
        body.applyImpulse(Vector2(1.0, 0.0))
        assertFalse(body.isAtRest())
        world.step(1)
        assertTrue(body.getTransform().getTranslationX() > 0.0)
    }

fun configuredTimeOfImpactSolverReceivesBulletCollision() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        world.getSettings().setContinuousDetectionMode(ContinuousDetectionMode.ALL)
        world.getSettings().setMaximumTranslation(20.0)
        val bullet = Body()
        bullet.addFixture(Circle(0.5))
        bullet.setMass(MassType.NORMAL)
        bullet.setBullet(true)
        bullet.setLinearVelocity(600.0, 0.0)
        val target = Body()
        target.addFixture(Circle(0.5))
        target.translate(5.0, 0.0)
        world.addBody(bullet)
        world.addBody(target)

        val originalBroadphase = world.getContinuousCollisionDetectionBroadphaseDetector()
        world.setContinuousCollisionDetectionBroadphaseDetector(object : BroadphaseDetector<Body> by originalBroadphase {
            override fun detectIterator(): MutableIterator<CollisionPair<Body>> =
                mutableListOf<CollisionPair<Body>>(BasicCollisionPair(bullet, target)).iterator()

            override fun detect(a: Body, b: Body): Boolean = true
        })
        world.setTimeOfImpactDetector(object : TimeOfImpactDetector {
            override fun getTimeOfImpact(
                convex1: Convex, transform1: Transform, dp1: Vector2, da1: Double,
                convex2: Convex, transform2: Transform, dp2: Vector2, da2: Double,
                toi: TimeOfImpact
            ): Boolean = getTimeOfImpact(convex1, transform1, dp1, da1, convex2, transform2, dp2, da2, 0.0, 1.0, toi)

            override fun getTimeOfImpact(
                convex1: Convex, transform1: Transform, dp1: Vector2, da1: Double,
                convex2: Convex, transform2: Transform, dp2: Vector2, da2: Double,
                t1: Double, t2: Double, toi: TimeOfImpact
            ): Boolean {
                toi.setTime(0.5)
                toi.getSeparation().setDistance(0.01)
                return true
            }
        })

        var resolved = 0
        world.setTimeOfImpactSolver(object : TimeOfImpactSolver<Body> {
            override fun solve(body1: Body, body2: Body, timeOfImpact: TimeOfImpact, settings: Settings) {
                resolved++
            }
        })

        world.step(1)
        assertTrue(resolved > 0)
    }
}
