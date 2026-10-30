package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

private const val SURFACE = "public class p.Sample\n" +
    "  minor version: 0\n" +
    "  flags: (0x0021) ACC_PUBLIC, ACC_SUPER\n" +
    "{\n" +
    "  public java.lang.String name;\n" +
    "    descriptor: Ljava/lang/String;\n" +
    "    flags: ACC_PUBLIC\n" +
    "\n" +
    "  public p.Sample();\n" +
    "    descriptor: ()V\n" +
    "    flags: ACC_PUBLIC\n" +
    "\n" +
    "  public java.lang.String greet(java.lang.String...);\n" +
    "    descriptor: ([Ljava/lang/String;)Ljava/lang/String;\n" +
    "    flags: ACC_PUBLIC, ACC_VARARGS\n" +
    "}\n"

val BaselineOracleAdapter by testSuite {
    test("the oracle reports the return type the baseline port computes") {
        val (header, records) = BaselineOracle.memberInventory(SURFACE)
        assertEquals("public class p.Sample", header)
        val greet = records.first { (it["name"] as kotlinx.serialization.json.JsonPrimitive).content == "greet" }
        assertEquals(
            "java.lang.String",
            (greet["return_type"] as kotlinx.serialization.json.JsonPrimitive).content,
        )
    }

    test("the oracle normalises a varargs parameter as the baseline port does") {
        val (_, records) = BaselineOracle.memberInventory(SURFACE)
        val greet = records.first { (it["name"] as kotlinx.serialization.json.JsonPrimitive).content == "greet" }
        assertEquals(
            "java.lang.String[]",
            (greet["source_parameters"] as kotlinx.serialization.json.JsonPrimitive).content,
        )
    }

    test("the oracle keeps the surface member keys the execution probe reads") {
        val surface = assertNotNull(BaselineOracle.surface(SURFACE))
        assertEquals("public class p.Sample", surface.first)
        assertTrue(surface.second.keys.any { it.first == "greet" })
    }

    test("a private type has no surface") {
        assertEquals(null, BaselineOracle.surface(SURFACE.replace("public class", "private class")))
    }}
