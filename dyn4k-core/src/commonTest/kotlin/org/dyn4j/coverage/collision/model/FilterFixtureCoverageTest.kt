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

import kotlin.test.Test
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

class FilterFixtureCoverageTest {
    private open class Parent : TypeFilter()
    private class Child : Parent()
    private class Sibling : Parent()
    private class Unrelated : TypeFilter()

    @Test fun categoryCreate() {
        val filter = CategoryFilter()
        assertEquals(1L, filter.getCategory())
        assertEquals(Long.MAX_VALUE, filter.getMask())
    }

    @Test fun categoryEqualsAndHashCode() {
        val first = CategoryFilter()
        val equal = CategoryFilter(1, Long.MAX_VALUE)
        val different = CategoryFilter(1, 2)
        assertEquals(first, equal)
        assertEquals(first.hashCode(), equal.hashCode())
        assertFalse(first == different)
        assertFalse(first.hashCode() == different.hashCode())
        assertFalse(first.equals(null))
    }

    @Test fun categoryFilter() {
        val all = CategoryFilter(1, Long.MAX_VALUE)
        val two = CategoryFilter(2, 3)
        val four = CategoryFilter(4, 7)
        assertTrue(all.isAllowed(two))
        assertTrue(two.isAllowed(all))
        assertFalse(two.isAllowed(four))
        assertFalse(four.isAllowed(two))
        assertTrue(two.isAllowed(Filter.DEFAULT_FILTER))
    }

    @Test fun categoryTostring() { assertTrue(CategoryFilter().toString().contains("Category=1")) }

    @Test fun categoryCopy() {
        val first = CategoryFilter(1, 5)
        val copy = first.copy()
        assertNotSame(first, copy)
        assertEquals(first, copy)
    }

    @Test fun defaultFilter() {
        val fixture = Fixture(Circle(1.0))
        val other = Fixture(Rectangle(1.0, 1.0))
        other.setFilter(CategoryFilter())
        assertTrue(fixture.getFilter().isAllowed(other.getFilter()))
        other.setFilter(Parent())
        assertTrue(fixture.getFilter().isAllowed(other.getFilter()))
    }

    @Test fun defaultTostring() { assertEquals("DefaultFilter[]", Filter.DEFAULT_FILTER.toString()) }
    @Test fun defaultCopy() { assertSame(Filter.DEFAULT_FILTER, Filter.DEFAULT_FILTER.copy()) }

    @Test fun typeFilter() {
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

    @Test fun typeCopy() {
        val parent = Parent()
        val child = Child()
        assertSame(parent, parent.copy())
        assertSame(child, child.copy())
        assertTrue(child.toString().startsWith("TypeFilter[ClassName="))
    }

    @Test fun fixtureCreateSuccess() { assertTrue(Fixture(Circle(1.0)).getShape() is Circle) }

    @Test fun fixtureCreateNullFixture() {
        assertEquals("shape cannot be null", assertFailsWith<ArgumentNullException> { Fixture(null) }.message)
    }

    @Test fun fixtureGetShape() {
        val shape = Circle(1.0)
        assertSame(shape, Fixture(shape).getShape())
    }

    @Test fun fixtureTostring() { assertTrue(Fixture(Circle(1.0)).toString().contains("Shape=")) }

    @Test fun fixtureGetSetFilter() {
        val fixture = Fixture(Circle(1.0))
        val filter = CategoryFilter()
        fixture.setFilter(filter)
        assertSame(filter, fixture.getFilter())
    }

    @Test fun fixtureSetNullFilter() {
        assertEquals("filter cannot be null", assertFailsWith<ArgumentNullException> {
            Fixture(Circle(1.0)).setFilter(null)
        }.message)
    }

    @Test fun fixtureGetSetSensor() {
        val fixture = Fixture(Circle(1.0))
        assertFalse(fixture.isSensor())
        fixture.setSensor(true)
        assertTrue(fixture.isSensor())
        fixture.setSensor(false)
        assertFalse(fixture.isSensor())
    }

    @Test fun fixtureGetSetUserData() {
        val fixture = Fixture(Circle(1.0))
        val data = Any()
        assertEquals(null, fixture.getUserData())
        fixture.setUserData(data)
        assertSame(data, fixture.getUserData())
        fixture.setUserData(null)
        assertEquals(null, fixture.getUserData())
    }

    @Test fun fixtureCopy() {
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

class CollisionSupportCoverageTest {
    @Test fun estimates() {
        assertEquals(0, Collisions.getEstimatedCollisionPairs(0))
        assertTrue(Collisions.getEstimatedCollisionPairs(2) > 0)
        assertTrue(Collisions.getEstimatedCollisionsPerObject() > 0)
        assertEquals(1, Collisions.getEstimatedRaycastCollisions(0))
        assertTrue(Collisions.getEstimatedRaycastCollisions(2) > 0)
    }

    @Test fun footMeter() {
        assertEquals(1.0, UnitConversion.FOOT_TO_METER * UnitConversion.METER_TO_FOOT, 1e-12)
        assertEquals(2.5, UnitConversion.feetToMeters(UnitConversion.metersToFeet(2.5)), 1e-9)
    }
    @Test fun slugKilogram() {
        assertEquals(1.0, UnitConversion.SLUG_TO_KILOGRAM * UnitConversion.KILOGRAM_TO_SLUG, 1e-12)
        assertEquals(2.5, UnitConversion.kilogramsToSlugs(UnitConversion.slugsToKilograms(2.5)), 1e-9)
    }
    @Test fun poundKilogram() {
        assertEquals(1.0, UnitConversion.POUND_TO_KILOGRAM * UnitConversion.KILOGRAM_TO_POUND, 1e-12)
        assertEquals(2.5, UnitConversion.kilogramsToPounds(UnitConversion.poundsToKilograms(2.5)), 1e-9)
    }
    @Test fun mpsToFps() {
        assertEquals(2.5, UnitConversion.feetPerSecondToMetersPerSecond(
            UnitConversion.metersPerSecondToFeetPerSecond(2.5)), 1e-9)
    }
    @Test fun poundNewton() {
        assertEquals(1.0, UnitConversion.POUND_TO_NEWTON * UnitConversion.NEWTON_TO_POUND, 1e-12)
        assertEquals(2.5, UnitConversion.newtonsToPounds(UnitConversion.poundsToNewtons(2.5)), 1e-9)
    }
    @Test fun footPoundNewtonMeter() {
        assertEquals(1.0, UnitConversion.FOOT_POUND_TO_NEWTON_METER * UnitConversion.NEWTON_METER_TO_FOOT_POUND, 1e-12)
        assertEquals(2.5, UnitConversion.newtonMetersToFootPounds(UnitConversion.footPoundsToNewtonMeters(2.5)), 1e-9)
    }

    @Test fun newCannotBeEqualException() {
        assertEquals("test cannot be 0.000000", ValueOutOfRangeException("test", 0.0).message)
    }
    @Test fun newCannotBeEqualException2() {
        assertEquals("test cannot be 2", ValueOutOfRangeException("test", 2).message)
    }
    @Test fun newEmptyCollectionException() {
        assertEquals("test cannot be empty", EmptyCollectionException("test").message)
    }
    @Test fun newGreaterThanException() {
        assertEquals("-1.000000 was supplied for test: test must be greater than 0.000000",
            ValueOutOfRangeException("test", -1.0, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0).message)
    }
    @Test fun newGreaterThanOrEqualException() {
        assertEquals("-1.000000 was supplied for test: test must be greater than or equal to 0.000000",
            ValueOutOfRangeException("test", -1.0, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0).message)
    }
    @Test fun newIndexOutOfBoundsException() {
        assertEquals("The index 5 is out of bounds", InvalidIndexException(5).message)
    }
    @Test fun newLessThanException() {
        assertEquals("5.000000 was supplied for test: test must be less than 3.000000",
            ValueOutOfRangeException("test", 5.0, ValueOutOfRangeException.MUST_BE_LESS_THAN, 3.0).message)
    }
    @Test fun newLessThanOrEqualException() {
        assertEquals("5.000000 was supplied for test: test must be less than or equal to 0.000000",
            ValueOutOfRangeException("test", 5.0, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, 0.0).message)
    }
    @Test fun newNullElementException() {
        assertEquals("test contains a null element", NullElementException("test").message)
    }
    @Test fun newNullElementExceptionWithIndex() {
        assertEquals("test contains a null element at index 2", NullElementException("test", 2).message)
    }
    @Test fun newNullPointerException() {
        assertEquals("test cannot be null", ArgumentNullException("test").message)
    }
    @Test fun newObjectsEqualException() {
        assertEquals("test1 and test2 cannot be the same object. Both were: hello",
            SameObjectException("test1", "test2", "hello").message)
    }
    @Test fun newValueLessThanValueException() {
        assertEquals("test1 must be less than test2: test1 was 5.000000 and test2 was 3.000000",
            ValueOutOfRangeException("test1", 5.0, ValueOutOfRangeException.MUST_BE_LESS_THAN, "test2", 3.0).message)
    }
    @Test fun newValueGreaterThanValueException() {
        assertEquals("test1 must be greater than test2: test1 was 5 and test2 was 3",
            ValueOutOfRangeException("test1", 5, ValueOutOfRangeException.MUST_BE_GREATER_THAN, "test2", 3).message)
    }
}

internal open class CoverageBody : AbstractCollisionBody<Fixture> {
    constructor() : super()
    constructor(capacity: Int) : super(capacity)
    protected constructor(body: CoverageBody) : super(body)
    override fun addFixture(convex: Convex): Fixture = Fixture(convex).also { addFixture(it) }
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

class BoundsCoverageTest {
    @Test fun abstractCreate() {
        assertEquals(Vector2(), CoverageBounds().getTranslation())
        assertEquals(Vector2(1.0, 2.0), CoverageBounds(1.0, 2.0).getTranslation())
        assertEquals(Vector2(1.0, 2.0), CoverageBounds(Vector2(1.0, 2.0)).getTranslation())
    }
    @Test fun abstractTranslation() {
        val bounds = CoverageBounds()
        bounds.translate(1.0, 0.0)
        bounds.translate(5.0, 6.0)
        assertEquals(Vector2(6.0, 6.0), bounds.getTranslation())
        bounds.translate(Vector2(-2.0, 1.0))
        assertEquals(Vector2(4.0, 7.0), bounds.getTranslation())
    }
    @Test fun abstractShiftCoordinates() {
        val bounds = CoverageBounds()
        bounds.shift(Vector2(1.0, 1.0))
        assertEquals(Vector2(1.0, 1.0), bounds.getTranslation())
    }
    @Test fun axisCreate() {
        val bounds = AxisAlignedBounds(10.0, 7.0)
        assertEquals(10.0, bounds.getWidth())
        assertEquals(7.0, bounds.getHeight())
    }
    @Test fun axisCreateZeroWidth() { assertFailsWith<IllegalArgumentException> { AxisAlignedBounds(0.0, 7.0) } }
    @Test fun axisCreateZeroHeight() { assertFailsWith<IllegalArgumentException> { AxisAlignedBounds(10.0, 0.0) } }
    @Test fun axisCreateNegativeWidth() { assertFailsWith<IllegalArgumentException> { AxisAlignedBounds(-10.0, 7.0) } }
    @Test fun axisCreateNegativeHeight() { assertFailsWith<IllegalArgumentException> { AxisAlignedBounds(10.0, -40.0) } }
    @Test fun axisGetBounds() {
        val bounds = AxisAlignedBounds(20.0, 20.0)
        assertEquals(AABB(-10.0, -10.0, 10.0, 10.0), bounds.getBounds())
        bounds.translate(1.0, -2.0)
        assertEquals(AABB(-9.0, -12.0, 11.0, 8.0), bounds.getBounds())
    }
    @Test fun axisPrint() { assertTrue(AxisAlignedBounds(20.0, 20.0).toString().isNotEmpty()) }

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
    @Test fun axisIsOutsideCircle() = shapeOutside(Circle(1.0))
    @Test fun axisIsOutsideEllipse() = shapeOutside(Ellipse(1.0, 0.5))
    @Test fun axisIsOutsideRectangle() = shapeOutside(Rectangle(1.0, 1.0))
    @Test fun axisIsOutsidePolygon() = shapeOutside(Geometry.createUnitCirclePolygon(6, 0.5))
    @Test fun axisIsOutsideTriangle() = shapeOutside(Triangle(Vector2(0.0, 0.5), Vector2(-0.5, -0.5), Vector2(0.5, -0.5)))
    @Test fun axisIsOutsideSegment() = shapeOutside(Segment(Vector2(0.5, -0.5), Vector2(-0.5, 0.5)))
    @Test fun axisIsOutsideAABB() {
        val bounds = AxisAlignedBounds(20.0, 20.0)
        val aabb = AABB(0.0, 0.0, 1.0, 1.0)
        assertFalse(bounds.isOutside(aabb))
        assertFalse(bounds.isOutside(aabb, null, null))
        aabb.translate(12.0, 0.0)
        assertTrue(bounds.isOutside(aabb))
        bounds.translate(3.0, 0.0)
        assertFalse(bounds.isOutside(aabb))
    }
    @Test fun axisCopy() {
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

class CollisionItemPairCoverageTest {
    private fun body() = CoverageBody().also { it.addFixture(Circle(1.0)) }
    private fun item(body: CoverageBody, fixture: Fixture) = BasicCollisionItem(body, fixture)

    @Test fun abstractItemHashCodeTest() {
        val body = body()
        val first = body.getFixture(0)
        val second = Fixture(Circle(1.0))
        assertEquals(AbstractCollisionItem.getHashCode(body, first), AbstractCollisionItem.getHashCode(body, first))
        assertFalse(AbstractCollisionItem.getHashCode(body, first) == AbstractCollisionItem.getHashCode(body, second))
    }
    @Test fun abstractItemEqualsTest() {
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
    @Test fun abstractItemMapTest() {
        val body = body()
        val key = item(body, body.getFixture(0))
        val value = Any()
        val map = mutableMapOf<BasicCollisionItem<CoverageBody, Fixture>, Any>(key to value)
        assertSame(value, map[item(body, body.getFixture(0))])
    }
    @Test fun basicItemCreate() {
        val body = body()
        val fixture = body.getFixture(0)
        val item = item(body, fixture)
        assertSame(body, item.getBody())
        assertSame(fixture, item.getFixture())
        assertFalse(item.hashCode() == 0)
    }
    @Test fun basicItemCopy() {
        val body = body()
        val fixture = body.getFixture(0)
        val first = item(body, fixture)
        val copy = first.copy()
        assertNotSame(first, copy)
        assertSame(body, copy.getBody())
        assertSame(fixture, copy.getFixture())
        assertEquals(first, copy)
    }

    @Test fun abstractBodyPairHashCodeTest() {
        val first = body(); val second = body()
        val pair = BasicCollisionPair(first, second)
        assertEquals(AbstractCollisionPair.getHashCode(first, second), AbstractCollisionPair.getHashCode(second, first))
        assertEquals(pair.hashCode(), BasicCollisionPair(second, first).hashCode())
    }
    @Test fun abstractBodyPairEqualsTest() {
        val first = body(); val second = body()
        val pair = BasicCollisionPair(first, second)
        assertTrue(AbstractCollisionPair.equals(pair, BasicCollisionPair(second, first)))
        assertFalse(AbstractCollisionPair.equals(pair, BasicCollisionPair(first, body())))
        assertFalse(AbstractCollisionPair.equals(pair, null))
    }
    @Test fun abstractBodyPairMapTest() {
        val first = body(); val second = body(); val value = Any()
        val map = mutableMapOf(BasicCollisionPair(first, second) to value)
        assertSame(value, map[BasicCollisionPair(second, first)])
    }
    @Test fun basicBodyPairCreate() {
        val first = body(); val second = body(); val pair = BasicCollisionPair(first, second)
        assertSame(first, pair.getFirst()); assertSame(second, pair.getSecond())
    }
    @Test fun basicBodyPairHashcodeEquals() {
        val first = body(); val second = body()
        val pair = BasicCollisionPair(first, second)
        val reverse = BasicCollisionPair(second, first)
        assertEquals(pair, reverse); assertEquals(pair.hashCode(), reverse.hashCode())
    }
    @Test fun basicBodyPairCopy() {
        val first = body(); val second = body(); val pair = BasicCollisionPair(first, second)
        val copy = pair.copy()
        assertNotSame(pair, copy)
        assertSame(first, copy.getFirst()); assertSame(second, copy.getSecond())
    }

    @Test fun abstractItemPairHashCodeTest() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        assertEquals(AbstractCollisionPair.getHashCode(first, second), AbstractCollisionPair.getHashCode(second, first))
    }
    @Test fun abstractItemPairEqualsTest() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        assertTrue(AbstractCollisionPair.equals(BasicCollisionPair(first, second), BasicCollisionPair(second, first)))
        assertFalse(AbstractCollisionPair.equals(BasicCollisionPair(first, second), BasicCollisionPair(first, first)))
    }
    @Test fun abstractItemPairMapTest() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        val value = Any()
        val map = mutableMapOf(BasicCollisionPair(first, second) to value)
        assertSame(value, map[BasicCollisionPair(second, first)])
    }
    @Test fun basicItemPairCreate() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        val pair = BasicCollisionPair(first, second)
        assertSame(first, pair.getFirst()); assertSame(second, pair.getSecond())
    }
    @Test fun basicItemPairHashcodeEquals() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        assertEquals(BasicCollisionPair(first, second), BasicCollisionPair(second, first))
    }
    @Test fun basicItemPairCopy() {
        val body = body(); val first = item(body, body.getFixture(0)); val second = item(body, Fixture(Circle(1.0)))
        val pair = BasicCollisionPair(first, second); val copy = pair.copy()
        assertNotSame(pair, copy)
        assertSame(first, copy.getFirst()); assertSame(second, copy.getSecond())
    }

    @Test fun supplementalItemEqualityGetterOrder() {
        val calls = mutableListOf<String>()
        class Observed(private val tag: String) : org.dyn4j.collision.CollisionItem<CoverageBody, Fixture> {
            override fun getBody(): CoverageBody? { calls.add("$tag.body"); return null }
            override fun getFixture(): Fixture? { calls.add("$tag.fixture"); return null }
            override fun copy(): org.dyn4j.collision.CollisionItem<CoverageBody, Fixture> = this
        }
        assertTrue(AbstractCollisionItem.equals(Observed("first"), Observed("second")))
        assertEquals(listOf("second.body", "first.body", "second.fixture", "first.fixture"), calls)
    }

    @Test fun supplementalPairEqualityGetterOrderAndNullPointOfUse() {
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

    @Test fun supplementalPairHashUsesFirstBeforeNull() {
        val calls = mutableListOf<String>()
        class Token { override fun hashCode(): Int { calls.add("first"); return 7 } }
        assertFailsWith<NullPointerException> { AbstractCollisionPair.getHashCode(Token(), null) }
        assertEquals(listOf("first"), calls)
    }
}

class CollisionBodyCoverageTest {
    private fun bodyWithTwo(): CoverageBody = CoverageBody().also {
        it.addFixture(Circle(1.0))
        it.addFixture(Rectangle(1.0, 1.0))
    }

    @Test fun create() {
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
    @Test fun addFixture() {
        val body = CoverageBody()
        val first = body.addFixture(Circle(1.0))
        assertSame(body, body.addFixture(Fixture(Rectangle(1.0, 1.0))))
        assertEquals(2, body.getFixtureCount())
        assertSame(first, body.getFixture(0))
    }
    @Test fun addNullConvex() { assertFailsWith<NullPointerException> { Fixture(null) } }
    @Test fun addNullFixture() { assertFailsWith<NullPointerException> { CoverageBody().addFixture(null as Fixture?) } }
    @Test fun containsPoint() {
        val body = bodyWithTwo()
        assertTrue(body.contains(Vector2()))
        assertTrue(body.contains(Vector2(0.5, 0.0)))
        assertFalse(body.contains(Vector2(2.0, 2.0)))
    }
    @Test fun containsFixture() {
        val body = bodyWithTwo()
        assertTrue(body.containsFixture(body.getFixture(0)))
        assertFalse(body.containsFixture(Fixture(Circle(1.0))))
    }
    @Test fun createAABB() {
        val body = CoverageBody()
        assertEquals(AABB(0.0, 0.0, 0.0, 0.0), body.createAABB())
        body.addFixture(Circle(0.5))
        assertEquals(AABB(-0.5, -0.5, 0.5, 0.5), body.createAABB())
        body.addFixture(Rectangle(1.0, 1.0)).getShape().translate(-0.5, 0.0)
        assertEquals(AABB(-1.0, -0.5, 0.5, 0.5), body.createAABB())
        val translated = Transform().also { it.translate(0.2, 0.5) }
        assertEquals(AABB(-0.8, 0.0, 0.7, 1.0), body.createAABB(translated))
    }
    @Test fun getFixtureByPoint() {
        val body = bodyWithTwo()
        assertEquals(null, body.getFixture(Vector2(2.0, 2.0)))
        assertSame(body.getFixture(0), body.getFixture(Vector2()))
    }
    @Test fun getFixtureByIndex() {
        val body = bodyWithTwo()
        assertSame(body.getFixtures()[1], body.getFixture(1))
        assertFailsWith<IndexOutOfBoundsException> { body.getFixture(2) }
    }
    @Test fun getFixtureCount() {
        val body = CoverageBody()
        assertEquals(0, body.getFixtureCount())
        body.addFixture(Circle(1.0)); assertEquals(1, body.getFixtureCount())
        body.addFixture(Circle(0.5)); assertEquals(2, body.getFixtureCount())
    }
    @Test fun getFixtureIterator() {
        val body = bodyWithTwo()
        val iterator = body.getFixtureIterator()
        assertSame(body.getFixture(0), iterator.next())
        iterator.remove()
        assertSame(body.getFixture(0), iterator.next())
        iterator.remove()
        assertEquals(0, body.getFixtureCount())
    }
    @Test fun getFixtureIteratorFailures() {
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
    @Test fun getSetFixtureModificationHandler() {
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
    @Test fun getFixtures() {
        val body = CoverageBody()
        val view = body.getFixtures()
        assertTrue(view.isEmpty())
        val first = body.addFixture(Circle(1.0))
        assertSame(first, view[0])
        body.addFixture(Circle(0.5))
        assertEquals(2, view.size)
    }
    @Test fun getFixturesAndAdd() {
        val view = CoverageBody().getFixtures()
        assertFalse(view is MutableList<*>)
    }
    @Test fun getFixturesAndRemove() {
        val body = bodyWithTwo()
        val view = body.getFixtures()
        assertFalse(view is MutableList<*>)
        assertEquals(2, body.getFixtureCount())
    }
    @Test fun getFixturesByPoint() {
        val body = bodyWithTwo()
        assertTrue(body.getFixtures(Vector2(3.0, 3.0)).isEmpty())
        assertEquals(2, body.getFixtures(Vector2()).size)
        assertSame(body.getFixture(0), body.getFixtures(Vector2(0.75, 0.0)).single())
    }
    @Test fun getLocalPoint() {
        val body = CoverageBody()
        body.translate(2.0, 3.0)
        assertEquals(Vector2(1.0, 1.0), body.getLocalPoint(Vector2(3.0, 4.0)))
        val destination = Vector2()
        body.getLocalPoint(Vector2(3.0, 4.0), destination)
        assertEquals(Vector2(1.0, 1.0), destination)
    }
    @Test fun getLocalVector() {
        val body = CoverageBody()
        body.translate(2.0, 3.0)
        assertEquals(Vector2(1.0, 1.0), body.getLocalVector(Vector2(1.0, 1.0)))
        val destination = Vector2()
        body.getLocalVector(Vector2(1.0, 1.0), destination)
        assertEquals(Vector2(1.0, 1.0), destination)
    }
    @Test fun getSetOwner() {
        val body = CoverageBody(); val owner = Any()
        assertEquals(null, body.getOwner())
        body.setOwner(owner); assertSame(owner, body.getOwner())
        body.setOwner(null); assertEquals(null, body.getOwner())
    }
    @Test fun getSetRotationDiscRadius() {
        val body = CoverageBody()
        assertEquals(0.0, body.getRotationDiscRadius())
        body.addFixture(Circle(1.0))
        body.updateRadius(Vector2())
        assertEquals(1.0, body.getRotationDiscRadius())
    }
    @Test fun getSetTransform() {
        val body = CoverageBody(); val transform = Transform().also { it.translate(2.0, 3.0) }
        val original = body.getTransform()
        body.setTransform(transform)
        assertSame(original, body.getTransform())
        assertEquals(Vector2(2.0, 3.0), body.getTransform().getTranslation())
        body.setTransform(null)
        assertEquals(Vector2(2.0, 3.0), body.getTransform().getTranslation())
    }
    @Test fun getSetPreviousTransform() {
        val body = CoverageBody(); val previous = body.getPreviousTransform()
        previous.translate(1.0, 2.0)
        assertSame(previous, body.getPreviousTransform())
        assertEquals(Vector2(1.0, 2.0), body.getPreviousTransform().getTranslation())
    }
    @Test fun getSetUserData() {
        val body = CoverageBody(); val data = Any()
        assertEquals(null, body.getUserData())
        body.setUserData(data); assertSame(data, body.getUserData())
        body.setUserData(null); assertEquals(null, body.getUserData())
    }
    @Test fun getWorldCenter() {
        val body = CoverageBody()
        body.translate(2.0, 3.0)
        assertEquals(Vector2(2.0, 3.0), body.getWorldCenter())
    }
    @Test fun getWorldPoint() {
        val body = CoverageBody(); body.translate(2.0, 3.0)
        assertEquals(Vector2(3.0, 4.0), body.getWorldPoint(Vector2(1.0, 1.0)))
        val destination = Vector2()
        body.getWorldPoint(Vector2(1.0, 1.0), destination)
        assertEquals(Vector2(3.0, 4.0), destination)
    }
    @Test fun getWorldVector() {
        val body = CoverageBody(); body.translate(2.0, 3.0)
        assertEquals(Vector2(1.0, 1.0), body.getWorldVector(Vector2(1.0, 1.0)))
        val destination = Vector2()
        body.getWorldVector(Vector2(1.0, 1.0), destination)
        assertEquals(Vector2(1.0, 1.0), destination)
    }
    @Test fun getSetEnabled() {
        val body = CoverageBody()
        assertTrue(body.isEnabled())
        body.setEnabled(false); assertFalse(body.isEnabled())
        body.setEnabled(true); assertTrue(body.isEnabled())
    }
    @Test fun removeAllFixtures() {
        val body = bodyWithTwo(); val originals = body.getFixtures().toList()
        val removed = body.removeAllFixtures()
        assertEquals(originals, removed)
        assertEquals(0, body.getFixtureCount())
        assertEquals(2, removed.size)
    }
    @Test fun removeFixture() {
        val body = bodyWithTwo(); val first = body.getFixture(0); val second = body.getFixture(1)
        assertTrue(body.removeFixture(first))
        assertSame(second, body.removeFixture(0))
        assertTrue(body.getFixtures().isEmpty())
    }
    @Test fun removeFixtureNotFound() {
        val body = bodyWithTwo()
        assertFalse(body.removeFixture(null as Fixture?))
        assertFalse(body.removeFixture(Fixture(Circle(1.0))))
        assertEquals(2, body.getFixtureCount())
    }
    @Test fun removeFixtureByPoint() {
        val body = bodyWithTwo()
        assertEquals(null, body.removeFixture(Vector2(3.0, 3.0)))
        assertSame(body.getFixture(0), body.removeFixture(Vector2(0.75, 0.0)))
        assertEquals(1, body.getFixtureCount())
        assertEquals(1, body.removeFixtures(Vector2()).size)
        assertEquals(0, body.getFixtureCount())
    }
    @Test fun removeFixtureByIndexOutOfBounds() {
        assertFailsWith<IndexOutOfBoundsException> { CoverageBody().removeFixture(0) }
    }
    @Test fun removeFixtureIndexNegative() {
        assertFailsWith<IndexOutOfBoundsException> { bodyWithTwo().removeFixture(-2) }
    }
    @Test fun rotate() {
        val body = CoverageBody(); val angle = kotlin.math.PI / 6.0
        body.rotate(angle)
        assertEquals(angle, body.getTransform().getRotationAngle(), 1e-15)
        body.rotate(Rotation(angle))
        assertEquals(2.0 * angle, body.getTransform().getRotationAngle(), 1e-15)
        body.getTransform().identity()
        body.rotate(angle, Vector2(1.0, 1.0))
        assertEquals(0.6339745962155612, body.getTransform().getTranslationX(), 1e-12)
        body.getTransform().identity()
        body.translate(1.0, 1.0)
        body.rotateAboutCenter(angle)
        assertEquals(Vector2(1.0, 1.0), body.getTransform().getTranslation())
    }
    @Test fun shiftCoordinates() {
        val body = CoverageBody(); body.shift(Vector2(-2.0, 1.0))
        assertEquals(Vector2(-2.0, 1.0), body.getTransform().getTranslation())
    }
    @Test fun translate() {
        val body = CoverageBody()
        body.translate(1.0, 1.0)
        body.translate(Vector2(2.0, -1.0))
        assertEquals(Vector2(3.0, 0.0), body.getTransform().getTranslation())
        body.translateToOrigin()
        assertEquals(Vector2(), body.getTransform().getTranslation())
    }
    @Test fun copy() {
        val body = bodyWithTwo()
        val owner = Any(); val data = Any()
        body.setOwner(owner); body.setUserData(data)
        body.setEnabled(false)
        body.getFixture(0).setFilter(CategoryFilter(1, 3))
        body.getFixture(0).setSensor(true)
        body.getFixture(0).setUserData(Any())
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
        assertFalse(copy.isEnabled())
        assertTrue(copy.getFixture(0).isSensor())
        assertEquals(null, copy.getOwner())
        assertEquals(null, copy.getUserData())
        assertEquals(null, copy.getFixture(0).getUserData())
    }
    @Test fun copyNotOverridden() {
        class UncopiedFixture : Fixture(Circle(1.0))
        val body = CoverageBody()
        body.addFixture(UncopiedFixture())
        assertFailsWith<CopyException> { body.copy() }
    }

    @Test fun supplementalLiveViewAndFailFastIterator() {
        val body = CoverageBody()
        val view = body.getFixtures()
        val first = body.addFixture(Circle(1.0))
        assertSame(first, view.single())
        val iterator = view.iterator()
        body.addFixture(Circle(2.0))
        assertEquals(2, view.size)
        assertFailsWith<ConcurrentModificationException> { iterator.next() }
    }

    @Test fun supplementalNestedViewAndProtectedSubListFailFast() {
        val body = bodyWithTwo()
        val nested = body.getFixtures().subList(0, 2).subList(0, 1)
        val protectedSubList = body.directFixtures().subList(0, 1)
        val protectedIterator = protectedSubList.iterator()
        body.addFixture(Circle(0.25))
        assertFailsWith<ConcurrentModificationException> { nested[0] }
        assertFailsWith<ConcurrentModificationException> { protectedIterator.next() }
    }

    @Test fun supplementalProtectedSubListMutatesAndInvalidatesIterator() {
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

    @Test fun supplementalNullPointIsDeferredUntilShapeUse() {
        val empty = CoverageBody()
        assertEquals(null, empty.getFixture(null))
        assertTrue(empty.getFixtures(null).isEmpty())
        assertEquals(null, empty.removeFixture(null as Vector2?))
        assertTrue(empty.removeFixtures(null).isEmpty())
        assertFalse(empty.contains(null))
        empty.addFixture(Circle(1.0))
        assertFailsWith<NullPointerException> { empty.getFixture(null) }
    }

    @Test fun supplementalCallbackOrderAndReentry() {
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

    @Test fun supplementalVirtualFixtureGetterControlsCopy() {
        val replacement = Fixture(Circle(2.0))
        class SubstitutingBody : AbstractCollisionBody<Fixture> {
            constructor() : super()
            private constructor(body: SubstitutingBody) : super(body)
            override fun getFixture(index: Int): Fixture = replacement
            override fun addFixture(convex: Convex): Fixture = Fixture(convex).also { addFixture(it) }
            override fun getLocalCenter() = Vector2()
            override fun copy() = SubstitutingBody(this)
        }
        val body = SubstitutingBody()
        body.addFixture(Circle(1.0))
        assertEquals(2.0, body.copy().getFixtures()[0].getShape().getRadius(Vector2()))
    }
}
