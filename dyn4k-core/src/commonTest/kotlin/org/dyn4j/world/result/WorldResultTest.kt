package org.dyn4j.world.result

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertNotSame
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.collision.narrowphase.Raycast
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.geometry.Geometry

val WorldResultTest by testSuite {
    test("kotlinResultSubclassesKeepProtectedDetailObjects") { WorldResultTestFixture().run { kotlinResultSubclassesKeepProtectedDetailObjects() } }
    test("kotlinDetectSubclassKeepsProtectedBodyAndFixture") { WorldResultTestFixture().run { kotlinDetectSubclassKeepsProtectedBodyAndFixture() } }
    test("detectResultSharesBodyAndFixtureAcrossCopies") { WorldResultTestFixture().run { detectResultSharesBodyAndFixtureAcrossCopies() } }
    test("detailedResultsCopyValuesAndKeepLiveDetailObjects") { WorldResultTestFixture().run { detailedResultsCopyValuesAndKeepLiveDetailObjects() } }
    test("rayAndCastResultsOrderByDistanceAndTime") { WorldResultTestFixture().run { rayAndCastResultsOrderByDistanceAndTime() } }
}

private class WorldResultTestFixture  {
    private class ExtendedResult : DetectResult<Body, BodyFixture>() {
        fun protectedValuesMatchPublic(): Boolean = body === getBody() && fixture === getFixture()
        fun replaceProtected(bodyValue: Body, fixtureValue: BodyFixture) {
            body = bodyValue
            fixture = fixtureValue
        }
    }

    private class ExtendedCast : ConvexCastResult<Body, BodyFixture>() {
        fun protectedDetailMatchesPublic(): Boolean = timeOfImpact === getTimeOfImpact()
    }

    private class ExtendedDetect : ConvexDetectResult<Body, BodyFixture>() {
        fun protectedDetailMatchesPublic(): Boolean = penetration === getPenetration()
    }

    private class ExtendedRay : RaycastResult<Body, BodyFixture>() {
        fun protectedDetailMatchesPublic(): Boolean = raycast === getRaycast()
    }

fun kotlinResultSubclassesKeepProtectedDetailObjects() {
        assertTrue(ExtendedCast().protectedDetailMatchesPublic())
        assertTrue(ExtendedDetect().protectedDetailMatchesPublic())
        assertTrue(ExtendedRay().protectedDetailMatchesPublic())
    }

fun kotlinDetectSubclassKeepsProtectedBodyAndFixture() {
        val body = Body()
        val fixture = BodyFixture(Geometry.createCircle(0.5))
        val result = ExtendedResult()
        assertTrue(result.protectedValuesMatchPublic())
        result.replaceProtected(body, fixture)
        assertTrue(result.protectedValuesMatchPublic())
        assertSame(body, result.getBody())
        assertSame(fixture, result.getFixture())
        val copy = result.copy()
        assertSame(body, copy.getBody())
        assertSame(fixture, copy.getFixture())
    }

fun detectResultSharesBodyAndFixtureAcrossCopies() {
        val body = Body()
        val fixture = BodyFixture(Geometry.createCircle(0.5))
        val source = DetectResult<Body, BodyFixture>()
        assertNull(source.getBody())
        assertNull(source.getFixture())
        source.setBody(body)
        source.setFixture(fixture)

        val copy = source.copy()
        assertSame(body, copy.getBody())
        assertSame(fixture, copy.getFixture())
        val target = DetectResult<Body, BodyFixture>()
        target.set(source)
        assertSame(body, target.getBody())
        assertSame(fixture, target.getFixture())
        target.setBody(null)
        assertSame(body, source.getBody())
    }

fun detailedResultsCopyValuesAndKeepLiveDetailObjects() {
        val body = Body()
        val fixture = BodyFixture(Geometry.createCircle(0.5))
        val penetration = Penetration().apply { setDepth(5.0) }
        val raycast = Raycast().apply { setDistance(4.0) }
        val toi = TimeOfImpact().apply { setTime(0.5) }

        val detect = ConvexDetectResult<Body, BodyFixture>()
        val ray = RaycastResult<Body, BodyFixture>()
        val cast = ConvexCastResult<Body, BodyFixture>()
        detect.setBody(body)
        detect.setFixture(fixture)
        detect.setPenetration(penetration)
        ray.setBody(body)
        ray.setFixture(fixture)
        ray.setRaycast(raycast)
        cast.setBody(body)
        cast.setFixture(fixture)
        cast.setTimeOfImpact(toi)

        val detectCopy = detect.copy()
        val rayCopy = ray.copy()
        val castCopy = cast.copy()
        assertSame(body, detectCopy.getBody())
        assertSame(fixture, rayCopy.getFixture())
        assertSame(body, castCopy.getBody())
        assertNotSame(detect.getPenetration(), detectCopy.getPenetration())
        assertNotSame(ray.getRaycast(), rayCopy.getRaycast())
        assertNotSame(cast.getTimeOfImpact(), castCopy.getTimeOfImpact())
        detect.getPenetration().setDepth(1.0)
        ray.getRaycast().setDistance(2.0)
        cast.getTimeOfImpact().setTime(0.7)
        assertEquals(5.0, detectCopy.getPenetration().getDepth())
        assertEquals(4.0, rayCopy.getRaycast().getDistance())
        assertEquals(0.5, castCopy.getTimeOfImpact().getTime())

        val target = ConvexDetectResult<Body, BodyFixture>()
        val detail = target.getPenetration()
        target.set(detectCopy)
        assertSame(detail, target.getPenetration())
        assertEquals(5.0, detail.getDepth())

        val rayTarget = RaycastResult<Body, BodyFixture>()
        val rayDetail = rayTarget.getRaycast()
        rayTarget.set(rayCopy)
        assertSame(rayDetail, rayTarget.getRaycast())
        assertEquals(4.0, rayDetail.getDistance())

        val castTarget = ConvexCastResult<Body, BodyFixture>()
        val castDetail = castTarget.getTimeOfImpact()
        castTarget.set(castCopy)
        assertSame(castDetail, castTarget.getTimeOfImpact())
        assertEquals(0.5, castDetail.getTime())
    }

fun rayAndCastResultsOrderByDistanceAndTime() {
        val near = RaycastResult<Body, BodyFixture>()
        val far = RaycastResult<Body, BodyFixture>()
        near.getRaycast().setDistance(1.0)
        far.getRaycast().setDistance(2.0)
        assertEquals(-1, near.compareTo(far))
        assertEquals(1, far.compareTo(near))
        assertEquals(0, near.compareTo(near.copy()))

        val early = ConvexCastResult<Body, BodyFixture>()
        val late = ConvexCastResult<Body, BodyFixture>()
        early.getTimeOfImpact().setTime(0.25)
        late.getTimeOfImpact().setTime(0.75)
        assertEquals(-1, early.compareTo(late))
        assertEquals(1, late.compareTo(early))
        assertEquals(0, early.compareTo(early.copy()))
    }
}
