package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlin.test.assertEquals

/**
 * `PythonJson`: the renderer the inventory, the run summary and the comparison report are written
 * with. The recorded text is `json.dumps`'s own output, so the comparison covers separators, key
 * order, indentation and the `ensure_ascii` escaping of everything outside printable ASCII.
 */
val JsonRenderCases by testSuite {
    test("compact rendering matches json.dumps") {
        for (element in Vectors.json.array("dumps")) {
            val case = element.jsonObject
            val value = case["value"]!!
            assertEquals(
                case.str("compact"),
                PythonJson.render(value, sortKeys = case.bool("sort_keys")),
                case.str("compact"),
            )
            // The rendered text must parse back to the value it was recorded from.
            assertEquals(value, Json.parseToJsonElement(PythonJson.render(value, sortKeys = case.bool("sort_keys"))))
        }
    }

    test("indented rendering matches json.dumps(indent=2)") {
        for (element in Vectors.json.array("dumps")) {
            val case = element.jsonObject
            assertEquals(
                case.str("indented"),
                PythonJson.renderIndented(case["value"]!!, sortKeys = case.bool("sort_keys")),
                case.str("indented"),
            )
        }
    }

    test("keys sort by code point when sort_keys is set") {
        val value = Json.parseToJsonElement("""{"b": 1, "A": 2, "a": 3, "\u00e9": 4}""")
        assertEquals("""{"A": 2, "a": 3, "b": 1, "\u00e9": 4}""", PythonJson.render(value, sortKeys = true))
        assertEquals("""{"b": 1, "A": 2, "a": 3, "\u00e9": 4}""", PythonJson.render(value))
    }
}
