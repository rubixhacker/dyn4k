package io.github.rubixhacker.harness.compatibility

import io.github.rubixhacker.harness.baseline.memberInventory as baselineMemberInventory
import io.github.rubixhacker.harness.baseline.surface as baselineSurface
import kotlinx.serialization.json.JsonObject

/** The two `javap -v` readers `execution_probe.declarations` needs from `tools/baseline/verify.py`. */
interface SurfaceOracle {
    val binarySha256: String

    /** The type header and the public/protected members of a strict `javap` surface. */
    fun surface(verbose: String): Pair<String, Map<Pair<String, String>, List<String>>>?

    /** The type header and every class-file member record of a verbose `javap` surface. */
    fun memberInventory(verbose: String): Pair<String, List<JsonObject>>
}

/**
 * Delegates to the `:baseline` port of `verify.type_header` / `surface` / `member_inventory`.
 *
 * These three functions used to be duplicated here, and the copy reported an empty `return_type` for
 * every method because it kept the separating space in the declaring text. The `:baseline` port is
 * checked against recorded `javap` output from the Python implementation, so this object is now an
 * adapter rather than a second implementation.
 */
object BaselineOracle : SurfaceOracle {
    override val binarySha256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"

    override fun surface(verbose: String): Pair<String, Map<Pair<String, String>, List<String>>>? =
        baselineSurface(verbose)?.let { api ->
            api.header to api.members.entries.associate { (key, declarations) ->
                (key.name to key.parameterTypes) to declarations
            }
        }

    override fun memberInventory(verbose: String): Pair<String, List<JsonObject>> =
        baselineMemberInventory(verbose).let { (header, records) -> header to records.map { it.toJson() } }
}
