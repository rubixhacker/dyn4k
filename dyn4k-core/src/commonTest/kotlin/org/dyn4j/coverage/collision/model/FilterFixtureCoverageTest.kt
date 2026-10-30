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
package org.dyn4j.coverage.collision.model

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.CategoryFilter
import org.dyn4j.collision.AbstractBounds
import org.dyn4j.collision.AbstractCollisionBody
import org.dyn4j.collision.AbstractCollisionItem
import org.dyn4j.collision.AbstractCollisionPair
import org.dyn4j.collision.AxisAlignedBounds
import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.CollisionBody
import org.dyn4j.collision.Filter
import org.dyn4j.collision.Fixture
import org.dyn4j.collision.TypeFilter
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Ellipse
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Rectangle
import org.dyn4j.geometry.Segment
import org.dyn4j.geometry.Triangle
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.Rotation
import org.dyn4j.Unsafe
import org.dyn4j.exception.CopyException
import org.dyn4j.UnitConversion
import org.dyn4j.collision.Collisions
import org.dyn4j.exception.EmptyCollectionException
import org.dyn4j.exception.InvalidIndexException
import org.dyn4j.exception.NullElementException
import org.dyn4j.exception.SameObjectException
import org.dyn4j.exception.ValueOutOfRangeException

val FilterFixtureCoverageTest by testSuite {
    test("categoryCreate") { FilterFixtureCoverageTestFixture().run { categoryCreate() } }
    test("categoryEqualsAndHashCode") { FilterFixtureCoverageTestFixture().run { categoryEqualsAndHashCode() } }
    test("categoryFilter") { FilterFixtureCoverageTestFixture().run { categoryFilter() } }
    test("categoryTostring") { FilterFixtureCoverageTestFixture().run { categoryTostring() } }
    test("categoryCopy") { FilterFixtureCoverageTestFixture().run { categoryCopy() } }
    test("defaultFilter") { FilterFixtureCoverageTestFixture().run { defaultFilter() } }
    test("defaultTostring") { FilterFixtureCoverageTestFixture().run { defaultTostring() } }
    test("defaultCopy") { FilterFixtureCoverageTestFixture().run { defaultCopy() } }
    test("typeFilter") { FilterFixtureCoverageTestFixture().run { typeFilter() } }
    test("typeCopy") { FilterFixtureCoverageTestFixture().run { typeCopy() } }
    test("fixtureCreateSuccess") { FilterFixtureCoverageTestFixture().run { fixtureCreateSuccess() } }
    test("fixtureCreateNullFixture") { FilterFixtureCoverageTestFixture().run { fixtureCreateNullFixture() } }
    test("fixtureGetShape") { FilterFixtureCoverageTestFixture().run { fixtureGetShape() } }
    test("fixtureTostring") { FilterFixtureCoverageTestFixture().run { fixtureTostring() } }
    test("fixtureGetSetFilter") { FilterFixtureCoverageTestFixture().run { fixtureGetSetFilter() } }
    test("fixtureSetNullFilter") { FilterFixtureCoverageTestFixture().run { fixtureSetNullFilter() } }
    test("fixtureGetSetSensor") { FilterFixtureCoverageTestFixture().run { fixtureGetSetSensor() } }
    test("fixtureGetSetUserData") { FilterFixtureCoverageTestFixture().run { fixtureGetSetUserData() } }
    test("fixtureCopy") { FilterFixtureCoverageTestFixture().run { fixtureCopy() } }
}

val CollisionSupportCoverageTest by testSuite {
    test("estimates") { CollisionSupportCoverageTestFixture().run { estimates() } }
    test("footMeter") { CollisionSupportCoverageTestFixture().run { footMeter() } }
    test("slugKilogram") { CollisionSupportCoverageTestFixture().run { slugKilogram() } }
    test("poundKilogram") { CollisionSupportCoverageTestFixture().run { poundKilogram() } }
    test("mpsToFps") { CollisionSupportCoverageTestFixture().run { mpsToFps() } }
    test("poundNewton") { CollisionSupportCoverageTestFixture().run { poundNewton() } }
    test("footPoundNewtonMeter") { CollisionSupportCoverageTestFixture().run { footPoundNewtonMeter() } }
    test("newCannotBeEqualException") { CollisionSupportCoverageTestFixture().run { newCannotBeEqualException() } }
    test("newCannotBeEqualException2") { CollisionSupportCoverageTestFixture().run { newCannotBeEqualException2() } }
    test("newEmptyCollectionException") { CollisionSupportCoverageTestFixture().run { newEmptyCollectionException() } }
    test("newGreaterThanException") { CollisionSupportCoverageTestFixture().run { newGreaterThanException() } }
    test("newGreaterThanOrEqualException") { CollisionSupportCoverageTestFixture().run { newGreaterThanOrEqualException() } }
    test("newIndexOutOfBoundsException") { CollisionSupportCoverageTestFixture().run { newIndexOutOfBoundsException() } }
    test("newLessThanException") { CollisionSupportCoverageTestFixture().run { newLessThanException() } }
    test("newLessThanOrEqualException") { CollisionSupportCoverageTestFixture().run { newLessThanOrEqualException() } }
    test("newNullElementException") { CollisionSupportCoverageTestFixture().run { newNullElementException() } }
    test("newNullElementExceptionWithIndex") { CollisionSupportCoverageTestFixture().run { newNullElementExceptionWithIndex() } }
    test("newNullPointerException") { CollisionSupportCoverageTestFixture().run { newNullPointerException() } }
    test("newObjectsEqualException") { CollisionSupportCoverageTestFixture().run { newObjectsEqualException() } }
    test("newValueLessThanValueException") { CollisionSupportCoverageTestFixture().run { newValueLessThanValueException() } }
    test("newValueGreaterThanValueException") { CollisionSupportCoverageTestFixture().run { newValueGreaterThanValueException() } }
}

val BoundsCoverageTest by testSuite {
    test("abstractCreate") { BoundsCoverageTestFixture().run { abstractCreate() } }
    test("abstractTranslation") { BoundsCoverageTestFixture().run { abstractTranslation() } }
    test("abstractShiftCoordinates") { BoundsCoverageTestFixture().run { abstractShiftCoordinates() } }
    test("axisCreate") { BoundsCoverageTestFixture().run { axisCreate() } }
    test("axisCreateZeroWidth") { BoundsCoverageTestFixture().run { axisCreateZeroWidth() } }
    test("axisCreateZeroHeight") { BoundsCoverageTestFixture().run { axisCreateZeroHeight() } }
    test("axisCreateNegativeWidth") { BoundsCoverageTestFixture().run { axisCreateNegativeWidth() } }
    test("axisCreateNegativeHeight") { BoundsCoverageTestFixture().run { axisCreateNegativeHeight() } }
    test("axisGetBounds") { BoundsCoverageTestFixture().run { axisGetBounds() } }
    test("axisPrint") { BoundsCoverageTestFixture().run { axisPrint() } }
    test("axisIsOutsideCircle") { BoundsCoverageTestFixture().run { axisIsOutsideCircle() } }
    test("axisIsOutsideEllipse") { BoundsCoverageTestFixture().run { axisIsOutsideEllipse() } }
    test("axisIsOutsideRectangle") { BoundsCoverageTestFixture().run { axisIsOutsideRectangle() } }
    test("axisIsOutsidePolygon") { BoundsCoverageTestFixture().run { axisIsOutsidePolygon() } }
    test("axisIsOutsideTriangle") { BoundsCoverageTestFixture().run { axisIsOutsideTriangle() } }
    test("axisIsOutsideSegment") { BoundsCoverageTestFixture().run { axisIsOutsideSegment() } }
    test("axisIsOutsideAABB") { BoundsCoverageTestFixture().run { axisIsOutsideAABB() } }
    test("axisCopy") { BoundsCoverageTestFixture().run { axisCopy() } }
}

val CollisionItemPairCoverageTest by testSuite {
    test("abstractItemHashCodeTest") { CollisionItemPairCoverageTestFixture().run { abstractItemHashCodeTest() } }
    test("abstractItemEqualsTest") { CollisionItemPairCoverageTestFixture().run { abstractItemEqualsTest() } }
    test("abstractItemMapTest") { CollisionItemPairCoverageTestFixture().run { abstractItemMapTest() } }
    test("basicItemCreate") { CollisionItemPairCoverageTestFixture().run { basicItemCreate() } }
    test("basicItemCopy") { CollisionItemPairCoverageTestFixture().run { basicItemCopy() } }
    test("abstractBodyPairHashCodeTest") { CollisionItemPairCoverageTestFixture().run { abstractBodyPairHashCodeTest() } }
    test("abstractBodyPairEqualsTest") { CollisionItemPairCoverageTestFixture().run { abstractBodyPairEqualsTest() } }
    test("abstractBodyPairMapTest") { CollisionItemPairCoverageTestFixture().run { abstractBodyPairMapTest() } }
    test("basicBodyPairCreate") { CollisionItemPairCoverageTestFixture().run { basicBodyPairCreate() } }
    test("basicBodyPairHashcodeEquals") { CollisionItemPairCoverageTestFixture().run { basicBodyPairHashcodeEquals() } }
    test("basicBodyPairCopy") { CollisionItemPairCoverageTestFixture().run { basicBodyPairCopy() } }
    test("abstractItemPairHashCodeTest") { CollisionItemPairCoverageTestFixture().run { abstractItemPairHashCodeTest() } }
    test("abstractItemPairEqualsTest") { CollisionItemPairCoverageTestFixture().run { abstractItemPairEqualsTest() } }
    test("abstractItemPairMapTest") { CollisionItemPairCoverageTestFixture().run { abstractItemPairMapTest() } }
    test("basicItemPairCreate") { CollisionItemPairCoverageTestFixture().run { basicItemPairCreate() } }
    test("basicItemPairHashcodeEquals") { CollisionItemPairCoverageTestFixture().run { basicItemPairHashcodeEquals() } }
    test("basicItemPairCopy") { CollisionItemPairCoverageTestFixture().run { basicItemPairCopy() } }
    test("supplementalItemEqualityGetterOrder") { CollisionItemPairCoverageTestFixture().run { supplementalItemEqualityGetterOrder() } }
    test("supplementalPairEqualityGetterOrderAndNullPointOfUse") { CollisionItemPairCoverageTestFixture().run { supplementalPairEqualityGetterOrderAndNullPointOfUse() } }
    test("supplementalPairHashUsesFirstBeforeNull") { CollisionItemPairCoverageTestFixture().run { supplementalPairHashUsesFirstBeforeNull() } }
}

val CollisionBodyCoverageTest by testSuite {
    test("create") { CollisionBodyCoverageTestFixture().run { create() } }
    test("addFixture") { CollisionBodyCoverageTestFixture().run { addFixture() } }
    test("addNullConvex") { CollisionBodyCoverageTestFixture().run { addNullConvex() } }
    test("addNullFixture") { CollisionBodyCoverageTestFixture().run { addNullFixture() } }
    test("containsPoint") { CollisionBodyCoverageTestFixture().run { containsPoint() } }
    test("containsFixture") { CollisionBodyCoverageTestFixture().run { containsFixture() } }
    test("createAABB") { CollisionBodyCoverageTestFixture().run { createAABB() } }
    test("getFixtureByPoint") { CollisionBodyCoverageTestFixture().run { getFixtureByPoint() } }
    test("getFixtureByIndex") { CollisionBodyCoverageTestFixture().run { getFixtureByIndex() } }
    test("getFixtureCount") { CollisionBodyCoverageTestFixture().run { getFixtureCount() } }
    test("getFixtureIterator") { CollisionBodyCoverageTestFixture().run { getFixtureIterator() } }
    test("getFixtureIteratorFailures") { CollisionBodyCoverageTestFixture().run { getFixtureIteratorFailures() } }
    test("getSetFixtureModificationHandler") { CollisionBodyCoverageTestFixture().run { getSetFixtureModificationHandler() } }
    test("getFixtures") { CollisionBodyCoverageTestFixture().run { getFixtures() } }
    test("getFixturesAndAdd") { CollisionBodyCoverageTestFixture().run { getFixturesAndAdd() } }
    test("getFixturesAndRemove") { CollisionBodyCoverageTestFixture().run { getFixturesAndRemove() } }
    test("getFixturesByPoint") { CollisionBodyCoverageTestFixture().run { getFixturesByPoint() } }
    test("getLocalPoint") { CollisionBodyCoverageTestFixture().run { getLocalPoint() } }
    test("getLocalVector") { CollisionBodyCoverageTestFixture().run { getLocalVector() } }
    test("getSetOwner") { CollisionBodyCoverageTestFixture().run { getSetOwner() } }
    test("getSetRotationDiscRadius") { CollisionBodyCoverageTestFixture().run { getSetRotationDiscRadius() } }
    test("getSetTransform") { CollisionBodyCoverageTestFixture().run { getSetTransform() } }
    test("getSetPreviousTransform") { CollisionBodyCoverageTestFixture().run { getSetPreviousTransform() } }
    test("getSetUserData") { CollisionBodyCoverageTestFixture().run { getSetUserData() } }
    test("getWorldCenter") { CollisionBodyCoverageTestFixture().run { getWorldCenter() } }
    test("getWorldPoint") { CollisionBodyCoverageTestFixture().run { getWorldPoint() } }
    test("getWorldVector") { CollisionBodyCoverageTestFixture().run { getWorldVector() } }
    test("getSetEnabled") { CollisionBodyCoverageTestFixture().run { getSetEnabled() } }
    test("removeAllFixtures") { CollisionBodyCoverageTestFixture().run { removeAllFixtures() } }
    test("removeFixture") { CollisionBodyCoverageTestFixture().run { removeFixture() } }
    test("removeFixtureNotFound") { CollisionBodyCoverageTestFixture().run { removeFixtureNotFound() } }
    test("removeFixtureByPoint") { CollisionBodyCoverageTestFixture().run { removeFixtureByPoint() } }
    test("removeFixtureByIndexOutOfBounds") { CollisionBodyCoverageTestFixture().run { removeFixtureByIndexOutOfBounds() } }
    test("removeFixtureIndexNegative") { CollisionBodyCoverageTestFixture().run { removeFixtureIndexNegative() } }
    test("rotate") { CollisionBodyCoverageTestFixture().run { rotate() } }
    test("shiftCoordinates") { CollisionBodyCoverageTestFixture().run { shiftCoordinates() } }
    test("translate") { CollisionBodyCoverageTestFixture().run { translate() } }
    test("copy") { CollisionBodyCoverageTestFixture().run { copy() } }
    test("copyNotOverridden") { CollisionBodyCoverageTestFixture().run { copyNotOverridden() } }
    test("supplementalLiveViewAndFailFastIterator") { CollisionBodyCoverageTestFixture().run { supplementalLiveViewAndFailFastIterator() } }
    test("supplementalNestedViewAndProtectedSubListFailFast") { CollisionBodyCoverageTestFixture().run { supplementalNestedViewAndProtectedSubListFailFast() } }
    test("supplementalProtectedSubListMutatesAndInvalidatesIterator") { CollisionBodyCoverageTestFixture().run { supplementalProtectedSubListMutatesAndInvalidatesIterator() } }
    test("supplementalNullPointIsDeferredUntilShapeUse") { CollisionBodyCoverageTestFixture().run { supplementalNullPointIsDeferredUntilShapeUse() } }
    test("supplementalCallbackOrderAndReentry") { CollisionBodyCoverageTestFixture().run { supplementalCallbackOrderAndReentry() } }
    test("supplementalVirtualFixtureGetterControlsCopy") { CollisionBodyCoverageTestFixture().run { supplementalVirtualFixtureGetterControlsCopy() } }
}

private class FilterFixtureCoverageTestFixture  {
    private open class Parent : TypeFilter()
    private class Child : Parent()
    private class Sibling : Parent()
    private class Unrelated : TypeFilter()

fun categoryCreate() {
        val filter = CategoryFilter()
        assertEquals(1L, filter.getCategory())
        assertEquals(Long.MAX_VALUE, filter.getMask())
    }

fun categoryEqualsAndHashCode() {
        val first = CategoryFilter()
        val equal = CategoryFilter(1, Long.MAX_VALUE)
        val different = CategoryFilter(1, 2)
        assertEquals(first, equal)
        assertEquals(first.hashCode(), equal.hashCode())
        assertFalse(first == different)
        assertFalse(first.hashCode() == different.hashCode())
        assertFalse(first.equals(null))
    }

fun categoryFilter() {
        val all = CategoryFilter(1, Long.MAX_VALUE)
        val two = CategoryFilter(2, 3)
        val four = CategoryFilter(4, 7)
        assertTrue(all.isAllowed(two))
        assertTrue(two.isAllowed(all))
        assertFalse(two.isAllowed(four))
        assertFalse(four.isAllowed(two))
        assertTrue(two.isAllowed(Filter.DEFAULT_FILTER))
    }

fun categoryTostring() { assertTrue(CategoryFilter().toString().contains("Category=1")) }

fun categoryCopy() {
        val first = CategoryFilter(1, 5)
        val copy = first.copy()
        assertNotSame(first, copy)
        assertEquals(first, copy)
    }

fun defaultFilter() {
        val fixture = Fixture(Circle(1.0))
        val other = Fixture(Rectangle(1.0, 1.0))
        other.setFilter(CategoryFilter())
        assertTrue(fixture.getFilter().isAllowed(other.getFilter()))
        other.setFilter(Parent())
        assertTrue(fixture.getFilter().isAllowed(other.getFilter()))
    }

fun defaultTostring() { assertEquals("DefaultFilter[]", Filter.DEFAULT_FILTER.toString()) }
fun defaultCopy() { assertSame(Filter.DEFAULT_FILTER, Filter.DEFAULT_FILTER.copy()) }

fun typeFilter() {
        val parent = Parent()
        val child = Child()
        val sibling = Sibling()
        val unrelated = Unrelated()
        assertTrue(parent.isAllowed(parent))
        assertTrue(parent.isAllowed(child))
        assertTrue(parent.isAllowed(sibling))
        assertTrue(child.isAllowed(parent))
        assertTrue(sibling.isAllowed(parent))
        assertFalse(child.isAllowed(sibling))
        assertFalse(sibling.isAllowed(child))
        assertFalse(parent.isAllowed(unrelated))
        assertFalse(unrelated.isAllowed(parent))
        assertFalse(parent.isAllowed(null))
        assertFalse(parent.isAllowed(CategoryFilter()))
    }

fun typeCopy() {
        val parent = Parent()
        val child = Child()
        assertSame(parent, parent.copy())
        assertSame(child, child.copy())
        assertTrue(child.toString().startsWith("TypeFilter[ClassName="))
    }

fun fixtureCreateSuccess() { assertTrue(Fixture(Circle(1.0)).getShape() is Circle) }

fun fixtureCreateNullFixture() {
        assertEquals("shape cannot be null", assertFailsWith<ArgumentNullException> { Fixture(null) }.message)
    }

fun fixtureGetShape() {
        val shape = Circle(1.0)
        assertSame(shape, Fixture(shape).getShape())
    }

fun fixtureTostring() { assertTrue(Fixture(Circle(1.0)).toString().contains("Shape=")) }

fun fixtureGetSetFilter() {
        val fixture = Fixture(Circle(1.0))
        val filter = CategoryFilter()
        fixture.setFilter(filter)
        assertSame(filter, fixture.getFilter())
    }

fun fixtureSetNullFilter() {
        assertEquals("filter cannot be null", assertFailsWith<ArgumentNullException> {
            Fixture(Circle(1.0)).setFilter(null)
        }.message)
    }

fun fixtureGetSetSensor() {
        val fixture = Fixture(Circle(1.0))
        assertFalse(fixture.isSensor())
        fixture.setSensor(true)
        assertTrue(fixture.isSensor())
        fixture.setSensor(false)
        assertFalse(fixture.isSensor())
    }

fun fixtureGetSetUserData() {
        val fixture = Fixture(Circle(1.0))
        val data = Any()
        assertEquals(null, fixture.getUserData())
        fixture.setUserData(data)
        assertSame(data, fixture.getUserData())
        fixture.setUserData(null)
        assertEquals(null, fixture.getUserData())
    }

fun fixtureCopy() {
        val fixture = Fixture(Circle(1.0))
        fixture.setFilter(CategoryFilter(2, 6))
        fixture.setSensor(true)
        fixture.setUserData(Any())
        val copy = fixture.copy()
        assertNotSame(fixture, copy)
        assertNotSame(fixture.getShape(), copy.getShape())
        assertNotSame(fixture.getFilter(), copy.getFilter())
        assertEquals(fixture.getFilter(), copy.getFilter())
        assertTrue(copy.isSensor())
        assertEquals(null, copy.getUserData())
    }
}

private class CollisionSupportCoverageTestFixture  {
fun estimates() {
        assertEquals(0, Collisions.getEstimatedCollisionPairs(0))
        assertTrue(Collisions.getEstimatedCollisionPairs(2) > 0)
        assertTrue(Collisions.getEstimatedCollisionsPerObject() > 0)
        assertEquals(1, Collisions.getEstimatedRaycastCollisions(0))
        assertTrue(Collisions.getEstimatedRaycastCollisions(2) > 0)
    }

fun footMeter() {
        assertEquals(1.0, UnitConversion.FOOT_TO_METER * UnitConversion.METER_TO_FOOT, 1e-12)
        assertEquals(2.5, UnitConversion.feetToMeters(UnitConversion.metersToFeet(2.5)), 1e-9)
    }
fun slugKilogram() {
        assertEquals(1.0, UnitConversion.SLUG_TO_KILOGRAM * UnitConversion.KILOGRAM_TO_SLUG, 1e-12)
        assertEquals(2.5, UnitConversion.kilogramsToSlugs(UnitConversion.slugsToKilograms(2.5)), 1e-9)
    }
fun poundKilogram() {
        assertEquals(1.0, UnitConversion.POUND_TO_KILOGRAM * UnitConversion.KILOGRAM_TO_POUND, 1e-12)
        assertEquals(2.5, UnitConversion.kilogramsToPounds(UnitConversion.poundsToKilograms(2.5)), 1e-9)
    }
fun mpsToFps() {
        assertEquals(2.5, UnitConversion.feetPerSecondToMetersPerSecond(
            UnitConversion.metersPerSecondToFeetPerSecond(2.5)), 1e-9)
    }
fun poundNewton() {
        assertEquals(1.0, UnitConversion.POUND_TO_NEWTON * UnitConversion.NEWTON_TO_POUND, 1e-12)
        assertEquals(2.5, UnitConversion.newtonsToPounds(UnitConversion.poundsToNewtons(2.5)), 1e-9)
    }
fun footPoundNewtonMeter() {
        assertEquals(1.0, UnitConversion.FOOT_POUND_TO_NEWTON_METER * UnitConversion.NEWTON_METER_TO_FOOT_POUND, 1e-12)
        assertEquals(2.5, UnitConversion.newtonMetersToFootPounds(UnitConversion.footPoundsToNewtonMeters(2.5)), 1e-9)
    }

fun newCannotBeEqualException() {
        assertEquals("test cannot be 0.000000", ValueOutOfRangeException("test", 0.0).message)
    }
fun newCannotBeEqualException2() {
        assertEquals("test cannot be 2", ValueOutOfRangeException("test", 2).message)
    }
fun newEmptyCollectionException() {
        assertEquals("test cannot be empty", EmptyCollectionException("test").message)
    }
fun newGreaterThanException() {
        assertEquals("-1.000000 was supplied for test: test must be greater than 0.000000",
            ValueOutOfRangeException("test", -1.0, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0).message)
    }
fun newGreaterThanOrEqualException() {
        assertEquals("-1.000000 was supplied for test: test must be greater than or equal to 0.000000",
            ValueOutOfRangeException("test", -1.0, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0).message)
    }
fun newIndexOutOfBoundsException() {
        assertEquals("The index 5 is out of bounds", InvalidIndexException(5).message)
    }
fun newLessThanException() {
        assertEquals("5.000000 was supplied for test: test must be less than 3.000000",
            ValueOutOfRangeException("test", 5.0, ValueOutOfRangeException.MUST_BE_LESS_THAN, 3.0).message)
    }
fun newLessThanOrEqualException() {
        assertEquals("5.000000 was supplied for test: test must be less than or equal to 0.000000",
            ValueOutOfRangeException("test", 5.0, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, 0.0).message)
    }
fun newNullElementException() {
        assertEquals("test contains a null element", NullElementException("test").message)
    }
fun newNullElementExceptionWithIndex() {
        assertEquals("test contains a null element at index 2", NullElementException("test", 2).message)
    }
fun newNullPointerException() {
        assertEquals("test cannot be null", ArgumentNullException("test").message)
    }
fun newObjectsEqualException() {
        assertEquals("test1 and test2 cannot be the same object. Both were: hello",
            SameObjectException("test1", "test2", "hello").message)
    }
fun newValueLessThanValueException() {
        assertEquals("test1 must be less than test2: test1 was 5.000000 and test2 was 3.000000",
            ValueOutOfRangeException("test1", 5.0, ValueOutOfRangeException.MUST_BE_LESS_THAN, "test2", 3.0).message)
    }
fun newValueGreaterThanValueException() {
        assertEquals("test1 must be greater than test2: test1 was 5 and test2 was 3",
            ValueOutOfRangeException("test1", 5, ValueOutOfRangeException.MUST_BE_GREATER_THAN, "test2", 3).message)
    }
}

internal open class CoverageBody : AbstractCollisionBody<Fixture> {
    constructor() : super()
    constructor(capacity: Int) : super(capacity)
    protected constructor(body: CoverageBody) : super(body)
    override fun addFixture(convex: Convex?): Fixture = Fixture(convex).also { addFixture(it) }
    override fun getLocalCenter() = Vector2()
    override fun copy() = CoverageBody(this)
    fun addDirect(fixture: Fixture) { fixtures.add(fixture) }
    fun directFixtures(): MutableList<Fixture> = fixtures
    fun updateRadius(center: Vector2?) { setRotationDiscRadius(center) }
}

private class CoverageBounds : AbstractBounds {
    constructor() : super()
    constructor(x: Double, y: Double) : super(x, y)
    constructor(point: Vector2) : super(point)
    private constructor(other: CoverageBounds) : super(other)
    override fun copy() = CoverageBounds(this)
    override fun isOutside(body: CollisionBody<*>) = false
    override fun isOutside(aabb: AABB) = false
    override fun isOutside(aabb: AABB, transform: Transform?, fixture: Fixture?) = false
}

private class BoundsCoverageTestFixture  {
fun abstractCreate() {
        assertEquals(Vector2(), CoverageBounds().getTranslation())
        assertEquals(Vector2(1.0, 2.0), CoverageBounds(1.0, 2.0).getTranslation())
        assertEquals(Vector2(1.0, 2.0), CoverageBounds(Vector2(1.0, 2.0)).getTranslation())
    }
fun abstractTranslation() {
        val bounds = CoverageBounds()
        bounds.translate(1.0, 0.0)
        bounds.translate(5.0, 6.0)
        assertEquals(Vector2(6.0, 6.0), bounds.getTranslation())
        bounds.translate(Vector2(-2.0, 1.0))
        assertEquals(Vector2(4.0, 7.0), bounds.getTranslation())
    }
fun abstractShiftCoordinates() {
        val bounds = CoverageBounds()
        bounds.shift(Vector2(1.0, 1.0))
        assertEquals(Vector2(1.0, 1.0), bounds.getTranslation())
    }
fun axisCreate() {
        val bounds = AxisAlignedBounds(10.0, 7.0)
        assertEquals(10.0, bounds.getWidth())
        assertEquals(7.0, bounds.getHeight())
    }
fun axisCreateZeroWidth() { assertFailsWith<IllegalArgumentException> { AxisAlignedBounds(0.0, 7.0) } }
fun axisCreateZeroHeight() { assertFailsWith<IllegalArgumentException> { AxisAlignedBounds(10.0, 0.0) } }
fun axisCreateNegativeWidth() { assertFailsWith<IllegalArgumentException> { AxisAlignedBounds(-10.0, 7.0) } }
fun axisCreateNegativeHeight() { assertFailsWith<IllegalArgumentException> { AxisAlignedBounds(10.0, -40.0) } }
fun axisGetBounds() {
        val bounds = AxisAlignedBounds(20.0, 20.0)
        assertEquals(AABB(-10.0, -10.0, 10.0, 10.0), bounds.getBounds())
        bounds.translate(1.0, -2.0)
        assertEquals(AABB(-9.0, -12.0, 11.0, 8.0), bounds.getBounds())
    }
fun axisPrint() { assertTrue(AxisAlignedBounds(20.0, 20.0).toString().isNotEmpty()) }

    private fun shapeOutside(shape: Convex) {
        val bounds = AxisAlignedBounds(20.0, 20.0)
        val body = CoverageBody()
        body.addFixture(shape)
        assertFalse(bounds.isOutside(body))
        body.translate(9.5, 0.0)
        assertFalse(bounds.isOutside(body))
        body.translate(3.0, 0.0)
        assertTrue(bounds.isOutside(body))
        bounds.translate(3.0, 0.0)
        assertFalse(bounds.isOutside(body))
    }
fun axisIsOutsideCircle() = shapeOutside(Circle(1.0))
fun axisIsOutsideEllipse() = shapeOutside(Ellipse(1.0, 0.5))
fun axisIsOutsideRectangle() = shapeOutside(Rectangle(1.0, 1.0))
fun axisIsOutsidePolygon() = shapeOutside(Geometry.createUnitCirclePolygon(6, 0.5))
fun axisIsOutsideTriangle() = shapeOutside(Triangle(Vector2(0.0, 0.5), Vector2(-0.5, -0.5), Vector2(0.5, -0.5)))
fun axisIsOutsideSegment() = shapeOutside(Segment(Vector2(0.5, -0.5), Vector2(-0.5, 0.5)))
fun axisIsOutsideAABB() {
        val bounds = AxisAlignedBounds(20.0, 20.0)
        val aabb = AABB(0.0, 0.0, 1.0, 1.0)
        assertFalse(bounds.isOutside(aabb))
        assertFalse(bounds.isOutside(aabb, null, null))
        aabb.translate(12.0, 0.0)
        assertTrue(bounds.isOutside(aabb))
        bounds.translate(3.0, 0.0)
        assertFalse(bounds.isOutside(aabb))
    }
fun axisCopy() {
        val bounds = AxisAlignedBounds(4.0, 6.0)
        bounds.translate(2.0, 3.0)
        val copy = bounds.copy()
        assertNotSame(bounds, copy)
        assertEquals(bounds.getBounds(), copy.getBounds())
        assertNotSame(bounds.getTranslation(), copy.getTranslation())
        bounds.translate(1.0, 0.0)
        assertEquals(Vector2(2.0, 3.0), copy.getTranslation())
    }
}

private class CollisionItemPairCoverageTestFixture  {
    private fun body() = CoverageBody().also { it.addFixture(Circle(1.0)) }
    private fun item(body: CoverageBody, fixture: Fixture) = BasicCollisionItem(body, fixture)

fun abstractItemHashCodeTest() {
        val body = body()
        val first = body.getFixture(0)
        val second = Fixture(Circle(1.0))
        assertEquals(AbstractCollisionItem.getHashCode(body, first), AbstractCollisionItem.getHashCode(body, first))
        assertFalse(AbstractCollisionItem.getHashCode(body, first) == AbstractCollisionItem.getHashCode(body, second))
    }
fun abstractItemEqualsTest() {
        val body = body()
        val first = item(body, body.getFixture(0))
        val same = item(body, body.getFixture(0))
        val different = item(body, Fixture(Circle(1.0)))
        assertTrue(AbstractCollisionItem.equals(first, same))
        assertFalse(AbstractCollisionItem.equals(first, different))
        assertFalse(AbstractCollisionItem.equals(first, null))
        assertFalse(AbstractCollisionItem.equals(null, first))
        assertTrue(AbstractCollisionItem.equals(null, null))
    }
fun abstractItemMapTest() {
        val body = body()
        val key = item(body, body.getFixture(0))
        val value = Any()
        val map = mutableMapOf<BasicCollisionItem<CoverageBody, Fixture>, Any>(key to value)
        assertSame(value, map[item(body, body.getFixture(0))])
    }
fun basicItemCreate() {
        val body = body()
        val fixture = body.getFixture(0)
        val item = item(body, fixture)
        assertSame(body, item.getBody())
        assertSame(fixture, item.getFixture())
        assertFalse(item.hashCode() == 0)
    }
fun basicItemCopy() {
        val body = body()
        val fixture = body.getFixture(0)
        val first = item(body, fixture)
        val copy = first.copy()
        assertNotSame(first, copy)
        assertSame(body, copy.getBody())
        assertSame(fixture, copy.getFixture())
        assertEquals(first, copy)
    }

fun abstractBodyPairHashCodeTest() {
        val first = body(); val second = body()
        val pair = BasicCollisionPair(first, second)
        assertEquals(AbstractCollisionPair.getHashCode(first, second), AbstractCollisionPair.getHashCode(second, first))
        assertEquals(pair.hashCode(), BasicCollisionPair(second, first).hashCode())
    }
fun abstractBodyPairEqualsTest() {
        val first = body(); val second = body()
        val pair = BasicCollisionPair(first, second)
        assertTrue(AbstractCollisionPair.equals(pair, BasicCollisionPair(second, first)))
        assertFalse(AbstractCollisionPair.equals(pair, BasicCollisionPair(first, body())))
        assertFalse(AbstractCollisionPair.equals(pair, null))
    }
fun abstractBodyPairMapTest() {
        val first = body(); val second = body(); val value = Any()
        val map = mutableMapOf(BasicCollisionPair(first, second) to value)
        assertSame(value, map[BasicCollisionPair(second, first)])
    }
fun basicBodyPairCreate() {
        val first = body(); val second = body(); val pair = BasicCollisionPair(first, second)
        assertSame(first, pair.getFirst()); assertSame(second, pair.getSecond())
    }
fun basicBodyPairHashcodeEquals() {
        val first = body(); val second = body()
        val pair = BasicCollisionPair(first, second)
        val reverse = BasicCollisionPair(second, first)
        assertEquals(pair, reverse); assertEquals(pair.hashCode(), reverse.hashCode())
    }
fun basicBodyPairCopy() {
        val first = body(); val second = body(); val pair = BasicCollisionPair(first, second)
        val copy = pair.copy()
        assertNotSame(pair, copy)
        assertSame(first, copy.getFirst()); assertSame(second, copy.getSecond())
    }

fun abstractItemPairHashCodeTest() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        assertEquals(AbstractCollisionPair.getHashCode(first, second), AbstractCollisionPair.getHashCode(second, first))
    }
fun abstractItemPairEqualsTest() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        assertTrue(AbstractCollisionPair.equals(BasicCollisionPair(first, second), BasicCollisionPair(second, first)))
        assertFalse(AbstractCollisionPair.equals(BasicCollisionPair(first, second), BasicCollisionPair(first, first)))
    }
fun abstractItemPairMapTest() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        val value = Any()
        val map = mutableMapOf(BasicCollisionPair(first, second) to value)
        assertSame(value, map[BasicCollisionPair(second, first)])
    }
fun basicItemPairCreate() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        val pair = BasicCollisionPair(first, second)
        assertSame(first, pair.getFirst()); assertSame(second, pair.getSecond())
    }
fun basicItemPairHashcodeEquals() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        assertEquals(BasicCollisionPair(first, second), BasicCollisionPair(second, first))
    }
fun basicItemPairCopy() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        val pair = BasicCollisionPair(first, second); val copy = pair.copy()
        assertNotSame(pair, copy)
        assertSame(first, copy.getFirst()); assertSame(second, copy.getSecond())
    }

fun supplementalItemEqualityGetterOrder() {
        val calls = mutableListOf<String>()
        class Observed(private val tag: String) : org.dyn4j.collision.CollisionItem<CoverageBody, Fixture> {
            override fun getBody(): CoverageBody? { calls.add("$tag.body"); return null }
            override fun getFixture(): Fixture? { calls.add("$tag.fixture"); return null }
            override fun copy(): org.dyn4j.collision.CollisionItem<CoverageBody, Fixture> = this
        }
        assertTrue(AbstractCollisionItem.equals(Observed("first"), Observed("second")))
        assertEquals(listOf("second.body", "first.body", "second.fixture", "first.fixture"), calls)
    }

fun supplementalPairEqualityGetterOrderAndNullPointOfUse() {
        val calls = mutableListOf<String>()
        class ObservedPair(private val tag: String) : org.dyn4j.collision.CollisionPair<String?> {
            override fun getFirst(): String? { calls.add("$tag.first"); return null }
            override fun getSecond(): String? { calls.add("$tag.second"); return "x" }
            override fun copy(): org.dyn4j.collision.CollisionPair<String?> = this
        }
        assertFailsWith<NullPointerException> {
            AbstractCollisionPair.equals(ObservedPair("first"), ObservedPair("second"))
        }
        assertEquals(listOf("first.first", "first.second", "second.first", "second.second"), calls)
    }

fun supplementalPairHashUsesFirstBeforeNull() {
        val calls = mutableListOf<String>()
        class Token { override fun hashCode(): Int { calls.add("first"); return 7 } }
        assertFailsWith<NullPointerException> { AbstractCollisionPair.getHashCode(Token(), null) }
        assertEquals(listOf("first"), calls)
    }
}

private class CollisionBodyCoverageTestFixture  {
    private fun bodyWithTwo(): CoverageBody = CoverageBody().also {
        it.addFixture(Circle(1.0))
        it.addFixture(Rectangle(1.0, 1.0))
    }

fun create() {
        val body = CoverageBody()
        assertEquals(0, body.getFixtureCount())
        assertEquals(null, body.getOwner())
        assertEquals(null, body.getUserData())
        assertTrue(body.isEnabled())
        assertEquals(null, body.getFixtureModificationHandler())
        assertEquals(Vector2(), body.getTransform().getTranslation())
        assertEquals(0, CoverageBody(-1).getFixtureCount())
        assertEquals(0, CoverageBody(5).getFixtureCount())
    }
fun addFixture() {
        val body = CoverageBody()
        val first = body.addFixture(Circle(1.0))
        assertSame(body, body.addFixture(Fixture(Rectangle(1.0, 1.0))))
        assertEquals(2, body.getFixtureCount())
        assertSame(first, body.getFixture(0))
    }
fun addNullConvex() {
        val body = CoverageBody()
        val failure = assertFailsWith<ArgumentNullException> { body.addFixture(null as Convex?) }
        assertEquals("shape cannot be null", failure.message)
        assertEquals(0, body.getFixtureCount())
    }
fun addNullFixture() { assertFailsWith<NullPointerException> { CoverageBody().addFixture(null as Fixture?) } }
fun containsPoint() {
        val body = bodyWithTwo()
        assertTrue(body.contains(Vector2()))
        assertTrue(body.contains(Vector2(0.5, 0.0)))
        assertFalse(body.contains(Vector2(2.0, 2.0)))
    }
fun containsFixture() {
        val body = bodyWithTwo()
        assertTrue(body.containsFixture(body.getFixture(0)))
        assertFalse(body.containsFixture(Fixture(Circle(1.0))))
    }
fun createAABB() {
        val body = CoverageBody()
        assertEquals(AABB(0.0, 0.0, 0.0, 0.0), body.createAABB())
        body.addFixture(Circle(0.5))
        assertEquals(AABB(-0.5, -0.5, 0.5, 0.5), body.createAABB())
        body.addFixture(Rectangle(1.0, 1.0)).getShape().translate(-0.5, 0.0)
        assertEquals(AABB(-1.0, -0.5, 0.5, 0.5), body.createAABB())
        val translated = Transform().also { it.translate(0.2, 0.5) }
        assertEquals(AABB(-0.8, 0.0, 0.7, 1.0), body.createAABB(translated))
    }
fun getFixtureByPoint() {
        val body = bodyWithTwo()
        assertEquals(null, body.getFixture(Vector2(2.0, 2.0)))
        assertSame(body.getFixture(0), body.getFixture(Vector2()))
        val polygon = body.addFixture(Geometry.createUnitCirclePolygon(5, 1.0))
        polygon.getShape().translate(0.5, 0.0)
        assertSame(polygon, body.getFixture(Vector2(1.25, 0.1)))
    }
fun getFixtureByIndex() {
        val body = bodyWithTwo()
        assertSame(body.getFixtures()[1], body.getFixture(1))
        assertFailsWith<IndexOutOfBoundsException> { body.getFixture(2) }
    }
fun getFixtureCount() {
        val body = CoverageBody()
        assertEquals(0, body.getFixtureCount())
        body.addFixture(Circle(1.0)); assertEquals(1, body.getFixtureCount())
        body.addFixture(Circle(0.5)); assertEquals(2, body.getFixtureCount())
    }
fun getFixtureIterator() {
        val body = bodyWithTwo()
        val iterator = body.getFixtureIterator()
        assertSame(body.getFixture(0), iterator.next())
        iterator.remove()
        assertSame(body.getFixture(0), iterator.next())
        iterator.remove()
        assertEquals(0, body.getFixtureCount())
    }
fun getFixtureIteratorFailures() {
        val body = bodyWithTwo()
        val iterator = body.getFixtureIterator()
        assertFailsWith<IllegalStateException> { iterator.remove() }
        iterator.next(); iterator.remove()
        assertFailsWith<IllegalStateException> { iterator.remove() }
        iterator.next()
        assertFailsWith<IndexOutOfBoundsException> { iterator.next() }
        body.removeAllFixtures()
        assertFailsWith<IndexOutOfBoundsException> { iterator.remove() }
    }
fun getSetFixtureModificationHandler() {
        val body = CoverageBody()
        val calls = mutableListOf<String>()
        val handler = object : org.dyn4j.collision.FixtureModificationHandler<Fixture> {
            override fun onFixtureAdded(fixture: Fixture) { calls.add("added") }
            override fun onFixtureRemoved(fixture: Fixture) { calls.add("removed") }
            override fun onAllFixturesRemoved() { calls.add("all") }
        }
        assertEquals(null, body.getFixtureModificationHandler())
        body.setFixtureModificationHandler(handler)
        assertSame(handler, body.getFixtureModificationHandler())
        val fixture = body.addFixture(Circle(1.0))
        body.removeFixture(fixture)
        body.removeAllFixtures()
        assertEquals(listOf("added", "removed", "all"), calls)
        body.setFixtureModificationHandler(null)
        assertEquals(null, body.getFixtureModificationHandler())
    }
fun getFixtures() {
        val body = CoverageBody()
        val view = body.getFixtures()
        assertTrue(view.isEmpty())
        val first = body.addFixture(Circle(1.0))
        assertSame(first, view[0])
        body.addFixture(Circle(0.5))
        assertEquals(2, view.size)
    }
fun getFixturesAndAdd() {
        val view = CoverageBody().getFixtures()
        assertFalse(view is MutableList<*>)
    }
fun getFixturesAndRemove() {
        val body = bodyWithTwo()
        val view = body.getFixtures()
        assertFalse(view is MutableList<*>)
        assertEquals(2, body.getFixtureCount())
    }
fun getFixturesByPoint() {
        val body = bodyWithTwo()
        assertTrue(body.getFixtures(Vector2(3.0, 3.0)).isEmpty())
        assertEquals(2, body.getFixtures(Vector2()).size)
        assertSame(body.getFixture(0), body.getFixtures(Vector2(0.75, 0.0)).single())
        val polygon = body.addFixture(Geometry.createUnitCirclePolygon(5, 1.0))
        polygon.getShape().translate(0.5, 0.0)
        assertEquals(3, body.getFixtures(Vector2()).size)
        assertSame(polygon, body.getFixtures(Vector2(1.25, 0.1)).single())
    }
fun getLocalPoint() {
        val body = CoverageBody()
        body.translate(2.0, 3.0)
        assertEquals(Vector2(1.0, 1.0), body.getLocalPoint(Vector2(3.0, 4.0)))
        val destination = Vector2()
        body.getLocalPoint(Vector2(3.0, 4.0), destination)
        assertEquals(Vector2(1.0, 1.0), destination)
        body.getTransform().identity()
        body.rotate(kotlin.math.PI / 2.0)
        body.translate(2.0, 3.0)
        val rotated = body.getLocalPoint(Vector2(2.0, 4.0))
        assertEquals(1.0, rotated.x, 1e-12)
        assertEquals(0.0, rotated.y, 1e-12)
    }
fun getLocalVector() {
        val body = CoverageBody()
        body.translate(2.0, 3.0)
        assertEquals(Vector2(1.0, 1.0), body.getLocalVector(Vector2(1.0, 1.0)))
        val destination = Vector2()
        body.getLocalVector(Vector2(1.0, 1.0), destination)
        assertEquals(Vector2(1.0, 1.0), destination)
        body.getTransform().identity()
        body.rotate(kotlin.math.PI / 2.0)
        val rotated = body.getLocalVector(Vector2(0.0, 1.0))
        assertEquals(1.0, rotated.x, 1e-12)
        assertEquals(0.0, rotated.y, 1e-12)
    }
fun getSetOwner() {
        val body = CoverageBody(); val owner = Any()
        assertEquals(null, body.getOwner())
        body.setOwner(owner); assertSame(owner, body.getOwner())
        body.setOwner(null); assertEquals(null, body.getOwner())
    }
fun getSetRotationDiscRadius() {
        val body = CoverageBody()
        assertEquals(0.0, body.getRotationDiscRadius())
        body.addFixture(Circle(1.0))
        body.updateRadius(Vector2())
        assertEquals(1.0, body.getRotationDiscRadius())
    }
fun getSetTransform() {
        val body = CoverageBody(); val transform = Transform().also { it.translate(2.0, 3.0) }
        val original = body.getTransform()
        body.setTransform(transform)
        assertSame(original, body.getTransform())
        assertEquals(Vector2(2.0, 3.0), body.getTransform().getTranslation())
        body.setTransform(null)
        assertEquals(Vector2(2.0, 3.0), body.getTransform().getTranslation())
    }
fun getSetPreviousTransform() {
        val body = CoverageBody(); val previous = body.getPreviousTransform()
        previous.translate(1.0, 2.0)
        assertSame(previous, body.getPreviousTransform())
        assertEquals(Vector2(1.0, 2.0), body.getPreviousTransform().getTranslation())
    }
fun getSetUserData() {
        val body = CoverageBody(); val data = Any()
        assertEquals(null, body.getUserData())
        body.setUserData(data); assertSame(data, body.getUserData())
        body.setUserData(null); assertEquals(null, body.getUserData())
    }
fun getWorldCenter() {
        val body = CoverageBody()
        body.translate(2.0, 3.0)
        assertEquals(Vector2(2.0, 3.0), body.getWorldCenter())
    }
fun getWorldPoint() {
        val body = CoverageBody(); body.translate(2.0, 3.0)
        assertEquals(Vector2(3.0, 4.0), body.getWorldPoint(Vector2(1.0, 1.0)))
        val destination = Vector2()
        body.getWorldPoint(Vector2(1.0, 1.0), destination)
        assertEquals(Vector2(3.0, 4.0), destination)
        body.getTransform().identity()
        body.rotate(kotlin.math.PI / 2.0)
        body.translate(2.0, 3.0)
        val rotated = body.getWorldPoint(Vector2(1.0, 0.0))
        assertEquals(2.0, rotated.x, 1e-12)
        assertEquals(4.0, rotated.y, 1e-12)
    }
fun getWorldVector() {
        val body = CoverageBody(); body.translate(2.0, 3.0)
        assertEquals(Vector2(1.0, 1.0), body.getWorldVector(Vector2(1.0, 1.0)))
        val destination = Vector2()
        body.getWorldVector(Vector2(1.0, 1.0), destination)
        assertEquals(Vector2(1.0, 1.0), destination)
        body.getTransform().identity()
        body.rotate(kotlin.math.PI / 2.0)
        val rotated = body.getWorldVector(Vector2(1.0, 0.0))
        assertEquals(0.0, rotated.x, 1e-12)
        assertEquals(1.0, rotated.y, 1e-12)
    }
fun getSetEnabled() {
        val body = CoverageBody()
        assertTrue(body.isEnabled())
        body.setEnabled(false); assertFalse(body.isEnabled())
        body.setEnabled(true); assertTrue(body.isEnabled())
    }
fun removeAllFixtures() {
        val body = bodyWithTwo(); val originals = body.getFixtures().toList()
        val removed = body.removeAllFixtures()
        assertEquals(originals, removed)
        assertEquals(0, body.getFixtureCount())
        assertEquals(2, removed.size)
    }
fun removeFixture() {
        val body = bodyWithTwo(); val first = body.getFixture(0); val second = body.getFixture(1)
        assertTrue(body.removeFixture(first))
        assertSame(second, body.removeFixture(0))
        assertTrue(body.getFixtures().isEmpty())
    }
fun removeFixtureNotFound() {
        val body = bodyWithTwo()
        assertFalse(body.removeFixture(null as Fixture?))
        assertFalse(body.removeFixture(Fixture(Circle(1.0))))
        assertEquals(2, body.getFixtureCount())
    }
fun removeFixtureByPoint() {
        val body = bodyWithTwo()
        assertEquals(null, body.removeFixture(Vector2(3.0, 3.0)))
        assertSame(body.getFixture(0), body.removeFixture(Vector2(0.75, 0.0)))
        assertEquals(1, body.getFixtureCount())
        assertEquals(1, body.removeFixtures(Vector2()).size)
        assertEquals(0, body.getFixtureCount())
        body.addFixture(Circle(1.0))
        body.addFixture(Circle(0.5))
        assertEquals(2, body.removeFixtures(Vector2()).size)
        assertEquals(0, body.getFixtureCount())
    }
fun removeFixtureByIndexOutOfBounds() {
        assertFailsWith<IndexOutOfBoundsException> { CoverageBody().removeFixture(0) }
    }
fun removeFixtureIndexNegative() {
        assertFailsWith<IndexOutOfBoundsException> { bodyWithTwo().removeFixture(-2) }
    }
fun rotate() {
        val body = CoverageBody(); val angle = kotlin.math.PI / 6.0
        body.rotate(angle)
        assertEquals(angle, body.getTransform().getRotationAngle(), 1e-15)
        body.rotate(Rotation(angle))
        assertEquals(2.0 * angle, body.getTransform().getRotationAngle(), 1e-15)
        body.getTransform().identity()
        body.rotate(angle, Vector2(1.0, 1.0))
        assertEquals(0.6339745962155612, body.getTransform().getTranslationX(), 1e-12)
        body.getTransform().identity()
        body.rotate(angle, 1.0, 1.0)
        assertEquals(-0.3660254037844386, body.getTransform().getTranslationY(), 1e-12)
        body.getTransform().identity()
        body.rotate(Rotation(angle), Vector2(1.0, 1.0))
        assertEquals(0.6339745962155612, body.getTransform().getTranslationX(), 1e-12)
        body.getTransform().identity()
        body.rotate(Rotation(angle), 1.0, 1.0)
        assertEquals(-0.3660254037844386, body.getTransform().getTranslationY(), 1e-12)
        body.getTransform().identity()
        body.translate(1.0, 1.0)
        body.rotateAboutCenter(angle)
        assertEquals(Vector2(1.0, 1.0), body.getTransform().getTranslation())
    }
fun shiftCoordinates() {
        val body = CoverageBody(); body.shift(Vector2(-2.0, 1.0))
        assertEquals(Vector2(-2.0, 1.0), body.getTransform().getTranslation())
    }
fun translate() {
        val body = CoverageBody()
        body.translate(1.0, 1.0)
        body.translate(Vector2(2.0, -1.0))
        assertEquals(Vector2(3.0, 0.0), body.getTransform().getTranslation())
        body.translateToOrigin()
        assertEquals(Vector2(), body.getTransform().getTranslation())
    }
fun copy() {
        val body = bodyWithTwo()
        val owner = Any(); val data = Any()
        body.setOwner(owner); body.setUserData(data)
        body.setEnabled(false)
        body.getFixture(0).setFilter(CategoryFilter(1, 3))
        body.getFixture(0).setSensor(true)
        body.getFixture(0).setUserData(Any())
        body.updateRadius(Vector2())
        body.setFixtureModificationHandler(object : org.dyn4j.collision.FixtureModificationHandler<Fixture> {
            override fun onFixtureAdded(fixture: Fixture) = Unit
            override fun onFixtureRemoved(fixture: Fixture) = Unit
            override fun onAllFixturesRemoved() = Unit
        })
        body.translate(2.0, 3.0)
        body.getPreviousTransform().set(body.getTransform())
        val copy = body.copy()
        assertNotSame(body, copy)
        assertNotSame(body.getTransform(), copy.getTransform())
        assertNotSame(body.getPreviousTransform(), copy.getPreviousTransform())
        assertNotSame(body.getFixture(0), copy.getFixture(0))
        assertNotSame(body.getFixture(0).getShape(), copy.getFixture(0).getShape())
        assertNotSame(body.getFixture(0).getFilter(), copy.getFixture(0).getFilter())
        assertEquals(body.getTransform().getTranslation(), copy.getTransform().getTranslation())
        assertEquals(body.getRotationDiscRadius(), copy.getRotationDiscRadius())
        assertFalse(copy.isEnabled())
        assertTrue(copy.getFixture(0).isSensor())
        assertEquals(null, copy.getFixtureModificationHandler())
        assertEquals(null, copy.getOwner())
        assertEquals(null, copy.getUserData())
        assertEquals(null, copy.getFixture(0).getUserData())
    }
fun copyNotOverridden() {
        class UncopiedFixture : Fixture(Circle(1.0))
        val body = CoverageBody()
        body.addFixture(UncopiedFixture())
        assertFailsWith<CopyException> { body.copy() }
    }

fun supplementalLiveViewAndFailFastIterator() {
        val body = CoverageBody()
        val view = body.getFixtures()
        val first = body.addFixture(Circle(1.0))
        assertSame(first, view.single())
        val iterator = view.iterator()
        body.addFixture(Circle(2.0))
        assertEquals(2, view.size)
        assertFailsWith<ConcurrentModificationException> { iterator.next() }
    }

fun supplementalNestedViewAndProtectedSubListFailFast() {
        val body = bodyWithTwo()
        val nested = body.getFixtures().subList(0, 2).subList(0, 1)
        val protectedSubList = body.directFixtures().subList(0, 1)
        val protectedIterator = protectedSubList.iterator()
        body.addFixture(Circle(0.25))
        assertFailsWith<ConcurrentModificationException> { nested[0] }
        assertFailsWith<ConcurrentModificationException> { protectedIterator.next() }
    }

fun supplementalProtectedSubListMutatesAndInvalidatesIterator() {
        val body = bodyWithTwo()
        val subList = body.directFixtures().subList(0, 1)
        val added = Fixture(Circle(2.0))
        subList.add(added)
        assertSame(added, body.getFixture(1))
        val iterator = subList.iterator()
        subList.removeAt(0)
        assertFailsWith<ConcurrentModificationException> { iterator.next() }
        assertSame(added, body.getFixture(0))
    }

fun supplementalNullPointIsDeferredUntilShapeUse() {
        val empty = CoverageBody()
        assertEquals(null, empty.getFixture(null))
        assertTrue(empty.getFixtures(null).isEmpty())
        assertEquals(null, empty.removeFixture(null as Vector2?))
        assertTrue(empty.removeFixtures(null).isEmpty())
        assertFalse(empty.contains(null))
        empty.addFixture(Circle(1.0))
        assertFailsWith<NullPointerException> { empty.getFixture(null) }
    }

fun supplementalCallbackOrderAndReentry() {
        val body = CoverageBody()
        val events = mutableListOf<String>()
        body.setFixtureModificationHandler(object : org.dyn4j.collision.FixtureModificationHandler<Fixture> {
            override fun onFixtureAdded(fixture: Fixture) {
                events.add("add:${body.getFixtureCount()}")
                if (body.getFixtureCount() == 1) body.addFixture(Circle(0.5))
            }
            override fun onFixtureRemoved(fixture: Fixture) { events.add("remove:${body.getFixtureCount()}") }
            override fun onAllFixturesRemoved() { events.add("all:${body.getFixtureCount()}") }
        })
        body.addFixture(Circle(1.0))
        assertEquals(listOf("add:1", "add:2"), events)
        body.removeAllFixtures()
        assertEquals(listOf("add:1", "add:2", "all:2"), events)
        assertEquals(0, body.getFixtureCount())
    }

fun supplementalVirtualFixtureGetterControlsCopy() {
        val replacement = Fixture(Circle(2.0))
        class SubstitutingBody : AbstractCollisionBody<Fixture> {
            constructor() : super()
            private constructor(body: SubstitutingBody) : super(body)
            override fun getFixture(index: Int): Fixture = replacement
            override fun addFixture(convex: Convex?): Fixture = Fixture(convex).also { addFixture(it) }
            override fun getLocalCenter() = Vector2()
            override fun copy() = SubstitutingBody(this)
        }
        val body = SubstitutingBody()
        body.addFixture(Circle(1.0))
        assertEquals(2.0, body.copy().getFixtures()[0].getShape().getRadius(Vector2()))
    }
}
