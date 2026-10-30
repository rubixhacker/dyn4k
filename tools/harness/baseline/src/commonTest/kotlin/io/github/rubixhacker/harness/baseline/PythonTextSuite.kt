package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals

/**
 * `verify.py` parses `javap` text with Python string primitives. These are the recorded outputs of
 * `str.splitlines`, `str.strip`, `str.split()`, `sorted`, `repr` and `repr(list)` over the cases the
 * verifier's inputs and messages actually contain.
 *
 * `str.splitlines` is the one the port cannot take from the standard library: it breaks on
 * `\v`, `\f`, `\x1c`-`\x1e`, `\x85`, `\u2028` and `\u2029` as well as `\r\n` and `\r`.
 */
val PythonTextCases by testSuite {
    test("splitlines matches the recorded Python boundaries") {
        for (element in Vectors.text.array("splitlines")) {
            val case = element.jsonObject
            assertEquals(
                case.array("lines").map { it.jsonPrimitive.content },
                pySplitLines(case.str("input")),
                "splitlines(${pythonStrRepr(case.str("input"))})",
            )
        }
    }

    test("strip removes the recorded whitespace set") {
        for (element in Vectors.text.array("strip")) {
            val case = element.jsonObject
            assertEquals(case.str("stripped"), pyStrip(case.str("input")))
        }
    }

    test("split without an argument splits on whitespace runs") {
        for (element in Vectors.text.array("split_whitespace")) {
            val case = element.jsonObject
            assertEquals(case.array("parts").map { it.jsonPrimitive.content }, pySplitWhitespace(case.str("input")))
        }
    }

    test("sorted orders by code point, not by UTF-16 code unit") {
        for (element in Vectors.text.array("sorted")) {
            val case = element.jsonObject
            val input = case.array("input").map { it.jsonPrimitive.content }
            assertEquals(case.array("sorted").map { it.jsonPrimitive.content }, sortedByCodePoint(input))
        }
    }

    test("string repr matches the recorded Python escaping") {
        for (element in Vectors.text.array("repr")) {
            val case = element.jsonObject
            assertEquals(case.str("repr"), pythonStrRepr(case.str("value")))
        }
    }

    test("list repr matches the recorded Python rendering") {
        for (element in Vectors.text.array("list_repr")) {
            val case = element.jsonObject
            val values = case.array("values").map { it.jsonPrimitive.content }
            assertEquals(case.str("repr"), pythonListRepr(values))
        }
    }

    test("an rsplit keeps the whole string when the separator is absent") {
        assertEquals(listOf("abc"), "abc".rsplitPython(")", 1))
        assertEquals(listOf("a", "b"), "a)b".rsplitPython(")", 1))
        assertEquals(listOf("a)b", "c"), "a)b)c".rsplitPython(")", 1))
    }

    test("partition after the first separator is empty when it is absent") {
        assertEquals("", "abc".partitionAfter("\nInnerClasses:\n"))
        assertEquals("body", "head\nInnerClasses:\nbody".partitionAfter("\nInnerClasses:\n"))
    }
}
