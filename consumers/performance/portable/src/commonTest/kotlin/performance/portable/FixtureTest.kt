package performance.portable

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertTrue

val FixtureTest by testSuite {
    test("everyFrozenSmallVariantBuildsOnBothApis") { FixtureTestFixture().run { everyFrozenSmallVariantBuildsOnBothApis() } }
    test("directAndCompatibilityUseTheSameSeparatedWorkload") { FixtureTestFixture().run { directAndCompatibilityUseTheSameSeparatedWorkload() } }
    test("lifecycleReplacementKeepsBodyAndJointCounts") { FixtureTestFixture().run { lifecycleReplacementKeepsBodyAndJointCounts() } }
}

private class FixtureTestFixture  {
fun everyFrozenSmallVariantBuildsOnBothApis() {
        val jointVariants = listOf(
            "angle_free", "angle_limits", "angle_ratio",
            "distance_limits", "distance_rigid", "distance_spring", "distance_spring_damper",
            "friction_friction", "mixed_all_types", "motor_offset",
            "pin_spring", "pin_spring_damper",
            "prismatic_free", "prismatic_limits", "prismatic_motor",
            "prismatic_spring", "prismatic_spring_damper",
            "pulley_ratio", "pulley_slack", "pulley_taut",
            "revolute_free", "revolute_limits", "revolute_motor",
            "weld_limits", "weld_rigid", "weld_spring", "weld_spring_damper",
            "wheel_limits", "wheel_motor", "wheel_spring", "wheel_spring_damper",
        )
        val variants = jointVariants.map { Triple("joint", it, 50) } + listOf(
            Triple("separated", "default", 100), Triple("pile", "default", 100),
            Triple("ccd", "default", 25), Triple("lifecycle", "settle", 100),
            Triple("lifecycle", "wake", 100), Triple("lifecycle", "replace", 100),
        )
        for (api in listOf("direct_kotlin", "compatibility")) {
            for ((family, variant, count) in variants) {
                val fixture = Fixture(family, variant, count, 30, api)
                fixture.world.step(1, 1.0 / 30.0)
                assertEquals(count, fixture.dynamic.size, "$family.$variant.$api")
                assertTrue(fixture.world.getBodyCount() >= count, "$family.$variant.$api")
            }
        }
    }

fun directAndCompatibilityUseTheSameSeparatedWorkload() {
        val direct = Fixture("separated", "default", 100, 30, "direct_kotlin")
        val shim = Fixture("separated", "default", 100, 30, "compatibility")
        for (step in 0..30) {
            direct.mutate(step)
            shim.mutate(step)
            direct.world.step(1, 1.0 / 30.0)
            shim.world.step(1, 1.0 / 30.0)
        }
        assertEquals(100, direct.world.getBodyCount())
        assertEquals(100, shim.world.getBodyCount())
        assertEquals(direct.dynamic[0].getWorldCenter().x,
            shim.dynamic[0].getWorldCenter().x, 1e-12)
        assertTrue(direct.activity().first > 0)
    }

fun lifecycleReplacementKeepsBodyAndJointCounts() {
        for (api in listOf("direct_kotlin", "compatibility")) {
            val fixture = Fixture("lifecycle", "replace", 100, 30, api)
            val bodies = fixture.world.getBodyCount()
            val joints = fixture.world.getJointCount()
            fixture.mutate(30)
            fixture.world.step(1, 1.0 / 30.0)
            assertEquals(bodies, fixture.world.getBodyCount())
            assertEquals(joints, fixture.world.getJointCount())
        }
    }
}
