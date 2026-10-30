package io.github.rubixhacker.harness.migration

/**
 * The replay stream contract of `tools/migration/fixed_replay.py`.
 *
 * Every function here mirrors one Python function over the same JSON values, including the order
 * in which channels are checked and the exact failure path it reports.
 */
object ReplayContract {
    val IDENTITY = listOf(
        "sample_revision", "source_manifest_sha256", "power", "angle", "dt",
        "prelude_steps", "steps", "ccd", "observation_stride", "cue_velocity",
        "jvm_identity_hash_mode", "jvm_identity_hash_probe", "jvm_input_arguments",
        "reset_state", "prelude_state", "prelude_pairs",
    )
    const val HASH_MODE = 2L
    val HASH_FLAGS = listOf("-XX:+UnlockExperimentalVMOptions", "-XX:hashCode=2")

    /** Field tolerances: `absolute` bound and `unit`, in the order `LIMITS` records them. */
    val LIMITS = linkedMapOf(
        "x" to (1e-4 to "m"),
        "y" to (1e-4 to "m"),
        "vx" to (1e-3 to "m/s"),
        "vy" to (1e-3 to "m/s"),
        "angle" to (1e-4 to "rad"),
        "omega" to (1e-3 to "rad/s"),
        "depth" to (1e-4 to "m"),
        "time" to (1e-6 to "step fraction"),
    )

    val STEP_FIELDS = listOf(
        "kind", "step", "body_count", "joint_count", "gravity", "bodies", "contacts",
        "toi_events", "ccd_pairs", "ccd_candidates", "contact_begin", "contact_persist",
        "contact_end", "toi_calls", "toi_hits", "toi_listener_hits",
    )

    val BODY_FIELDS = listOf(
        "i", "x", "y", "vx", "vy", "angle", "omega", "rest", "bullet", "fixtures",
        "mass", "inertia", "linear_damping", "angular_damping", "identity_hash",
        "fixture_identity_hashes",
    )
}

/** `fixed_replay.read_stream` through `fixed_replay.compare`. */
object ReplayComparison {
    /** Returns the parsed rows and the first stream divergence, if any. */
    fun readStream(
        rows: List<PyValue>,
        provider: String,
        expectedSha: String,
    ): Pair<List<PyValue>, PyValue?> {
        if (rows.isEmpty() || (rows[0].getOrNull("kind") != PyValue.Text("input"))) {
            throw MigrationFailure("$provider stream lacks input identity")
        }
        val header = rows[0]
        if (!pyEquals(header.getOrNull("provider") ?: PyValue.Null, PyValue.Text(provider))) {
            throw MigrationFailure("$provider stream has wrong provider")
        }
        if (!pyEquals(header.getOrNull("artifact_sha256") ?: PyValue.Null, PyValue.Text(expectedSha))) {
            return rows to pyMap(
                "path" to pyText("input.artifact_sha256"),
                "baseline" to pyText(expectedSha),
                "candidate" to (header.getOrNull("artifact_sha256") ?: PyValue.Null),
            )
        }
        for ((key, expected) in listOf(
            "jvm_identity_hash_mode" to pyInt(ReplayContract.HASH_MODE),
            "jvm_identity_hash_probe" to pyInt(1),
            "jvm_input_arguments" to pyList(ReplayContract.HASH_FLAGS.map(::pyText)),
        )) {
            if (!pyEquals(header.getOrNull(key) ?: PyValue.Null, expected)) {
                return rows to pyMap(
                    "path" to pyText("$provider.input.$key"),
                    "expected" to expected,
                    "observed" to (header.getOrNull(key) ?: PyValue.Null),
                )
            }
        }
        val expectedJar = if (provider == "baseline") "dyn4j-6.0.0.jar" else Journeys.CANDIDATE_JAR
        for ((key, expected) in listOf(
            "world_code_source" to pyText("file:/work/lib/$expectedJar"),
            "java_home" to pyText("/jdk"),
        )) {
            if (!pyEquals(header.getOrNull(key) ?: PyValue.Null, expected)) {
                return rows to pyMap(
                    "path" to pyText("$provider.input.$key"),
                    "expected" to expected,
                    "observed" to (header.getOrNull(key) ?: PyValue.Null),
                )
            }
        }
        val version = header.getOrNull("java_version")
        if (version !is PyValue.Text || !version.value.startsWith("21.")) {
            return rows to pyMap(
                "path" to pyText("$provider.input.java_version"),
                "expected" to pyText("JDK 21"),
                "observed" to (version ?: PyValue.Null),
            )
        }
        for ((key, step) in listOf("reset_state" to -120L, "prelude_state" to -1L)) {
            val state = header.getOrNull(key)
            if (state !is PyValue.Map ||
                !pyEquals(state.getOrNull("kind") ?: PyValue.Null, PyValue.Text("step")) ||
                !pyEquals(state.getOrNull("step") ?: PyValue.Null, PyValue.Int(step))
            ) {
                return rows to pyMap(
                    "path" to pyText("$provider.input.$key"),
                    "reason" to pyText("missing or invalid state"),
                )
            }
        }
        for ((index, row) in rows.drop(1).withIndex()) {
            if (!pyEquals(row.getOrNull("kind") ?: PyValue.Null, PyValue.Text("step")) ||
                !pyEquals(row.getOrNull("step") ?: PyValue.Null, PyValue.Int(index.toLong()))
            ) {
                return rows to pyMap(
                    "path" to pyText("step.sequence"),
                    "expected" to pyInt(index),
                    "observed" to (row.getOrNull("step") ?: PyValue.Null),
                )
            }
        }
        val steps = when (val recorded = header.getOrNull("steps")) {
            null -> -1L
            is PyValue.Int -> recorded.value
            else -> throw PyTypeError(
                "unsupported operand type(s) for +: '${recorded.typeName}' and 'int'",
            )
        }
        if (rows.size.toLong() != steps + 2) {
            return rows to pyMap(
                "path" to pyText("step.sequence"),
                "expected" to pyInt(steps + 1),
                "observed" to pyInt((rows.size - 1).toLong()),
            )
        }
        return rows to null
    }

    /** `fixed_replay.finite_tree`. */
    fun finiteTree(value: PyValue): Boolean = when (value) {
        is PyValue.Real -> value.value.isFinite()
        is PyValue.Seq -> value.items.all(::finiteTree)
        is PyValue.Map -> value.entries.values.all(::finiteTree)
        else -> true
    }

    /** `fixed_replay.whole_count`: a non-negative `int`, excluding `bool`. */
    fun wholeCount(value: PyValue): Boolean = value is PyValue.Int && value.value >= 0

    /** `fixed_replay.body_pair`. */
    fun bodyPair(pair: PyValue, bodyCount: Long): Boolean =
        pair is PyValue.Seq && pair.items.size == 2 && pair.items.all {
            it is PyValue.Int && it.value >= 0 && it.value < bodyCount
        }

    /** `fixed_replay.validate_step`. Returns the error and the running TOI event count. */
    fun validateStep(
        row: PyValue,
        path: String,
        contactCounts: MutableMap<String, Long>,
        toiCount: Long,
    ): Pair<PyValue?, Long> {
        for (field in ReplayContract.STEP_FIELDS) {
            if (row.getOrNull(field) == null) {
                return pyMap(
                    "path" to pyText("$path.$field"),
                    "reason" to pyText("missing channel"),
                ) to toiCount
            }
        }
        for (field in listOf(
            "step", "body_count", "joint_count", "contact_begin", "contact_persist",
            "contact_end", "toi_calls", "toi_hits", "toi_listener_hits",
        )) {
            val value = row.get(field)
            if (value !is PyValue.Int || (field != "step" && value.value < 0)) {
                return pyMap(
                    "path" to pyText("$path.$field"),
                    "reason" to pyText("invalid count"),
                ) to toiCount
            }
        }
        if (!pyEquals(row.get("kind"), PyValue.Text("step"))) {
            return pyMap(
                "path" to pyText("$path.kind"),
                "reason" to pyText("invalid state kind"),
            ) to toiCount
        }
        val gravity = row.get("gravity")
        if (gravity !is PyValue.Seq || gravity.items.size != 2 ||
            gravity.items.any { !it.isNumber() }
        ) {
            return pyMap(
                "path" to pyText("$path.gravity"),
                "reason" to pyText("invalid gravity"),
            ) to toiCount
        }
        val bodyCount = (row.get("body_count") as PyValue.Int).value
        val bodies = row.get("bodies")
        if (bodies !is PyValue.Seq || bodies.items.size.toLong() != bodyCount) {
            return pyMap(
                "path" to pyText("$path.bodies"),
                "reason" to pyText("body count mismatch"),
            ) to toiCount
        }
        for ((index, body) in bodies.items.withIndex()) {
            val bodyPath = "$path.bodies[$index]"
            if (body !is PyValue.Map ||
                !pyEquals(body.getOrNull("i") ?: PyValue.Null, PyValue.Int(index.toLong()))
            ) {
                return pyMap(
                    "path" to pyText("$bodyPath.i"),
                    "reason" to pyText("body order mismatch"),
                ) to toiCount
            }
            for (field in ReplayContract.BODY_FIELDS) {
                if (body.getOrNull(field) == null) {
                    return pyMap(
                        "path" to pyText("$bodyPath.$field"),
                        "reason" to pyText("missing channel"),
                    ) to toiCount
                }
            }
            for (field in listOf(
                "x", "y", "vx", "vy", "angle", "omega", "mass", "inertia",
                "linear_damping", "angular_damping",
            )) {
                if (!body.get(field).isNumber()) {
                    return pyMap(
                        "path" to pyText("$bodyPath.$field"),
                        "reason" to pyText("invalid body value"),
                    ) to toiCount
                }
            }
            for (field in listOf("rest", "bullet")) {
                if (body.get(field) !is PyValue.Bool) {
                    return pyMap(
                        "path" to pyText("$bodyPath.$field"),
                        "reason" to pyText("invalid body flag"),
                    ) to toiCount
                }
            }
            val fixtures = body.get("fixtures")
            if (!wholeCount(fixtures)) {
                return pyMap(
                    "path" to pyText("$bodyPath.fixtures"),
                    "reason" to pyText("invalid fixture count"),
                ) to toiCount
            }
            val identityHash = body.get("identity_hash")
            val fixtureHashes = body.get("fixture_identity_hashes")
            val fixtureCount = (fixtures as PyValue.Int).value
            if (identityHash !is PyValue.Int || identityHash.value != 1L ||
                fixtureHashes !is PyValue.Seq || fixtureHashes.items.size.toLong() != fixtureCount ||
                fixtureHashes.items.any { it !is PyValue.Int || it.value != 1L }
            ) {
                return pyMap(
                    "path" to pyText("$bodyPath.identity_hash"),
                    "reason" to pyText("constant identity-hash behavior absent"),
                ) to toiCount
            }
        }
        for (field in listOf("ccd_pairs", "ccd_candidates")) {
            val pairs = row.get(field)
            if (pairs !is PyValue.Seq || pairs.items.any { !bodyPair(it, bodyCount) }) {
                return pyMap(
                    "path" to pyText("$path.$field"),
                    "reason" to pyText("CCD pair order channel incomplete"),
                ) to toiCount
            }
        }
        val contacts = row.get("contacts")
        if (contacts !is PyValue.Seq) {
            return pyMap(
                "path" to pyText("$path.contacts"),
                "reason" to pyText("contact events missing"),
            ) to toiCount
        }
        for (event in contacts.items) {
            val valid = event is PyValue.Map &&
                setOf("kind", "a", "b", "x", "y", "depth").all { event.entries.containsKey(it) } &&
                (event.getOrNull("kind") as? PyValue.Text)?.value in contactCounts &&
                bodyPair(
                    PyValue.Seq(listOf(event.get("a"), event.get("b"))),
                    bodyCount,
                ) &&
                listOf("x", "y", "depth").all { event.get(it).isNumber() }
            if (!valid) {
                return pyMap(
                    "path" to pyText("$path.contacts"),
                    "reason" to pyText("contact event incomplete"),
                ) to toiCount
            }
            val kind = (event.get("kind") as PyValue.Text).value
            contactCounts[kind] = contactCounts.getValue(kind) + 1
        }
        for ((kind, count) in contactCounts) {
            if (!pyEquals(row.get("contact_$kind"), PyValue.Int(count))) {
                return pyMap(
                    "path" to pyText("$path.contacts"),
                    "reason" to pyText("contact counter differs from events"),
                ) to toiCount
            }
        }
        val toiEvents = row.get("toi_events")
        if (toiEvents !is PyValue.Seq) {
            return pyMap(
                "path" to pyText("$path.toi_events"),
                "reason" to pyText("TOI events missing"),
            ) to toiCount
        }
        var count = toiCount
        for (event in toiEvents.items) {
            val valid = event is PyValue.Map &&
                setOf("a", "b", "time").all { event.entries.containsKey(it) } &&
                bodyPair(PyValue.Seq(listOf(event.get("a"), event.get("b"))), bodyCount) &&
                event.get("time").isNumber()
            if (!valid) {
                return pyMap(
                    "path" to pyText("$path.toi_events"),
                    "reason" to pyText("TOI event incomplete"),
                ) to count
            }
            count += 1
        }
        if (!pyEquals(row.get("toi_listener_hits"), PyValue.Int(count))) {
            return pyMap(
                "path" to pyText("$path.toi_events"),
                "reason" to pyText("TOI counter differs from events"),
            ) to count
        }
        return null to count
    }

    /** `fixed_replay.missing_channel`. */
    fun missingChannel(rows: List<PyValue>, provider: String): PyValue? {
        for (key in listOf("reset_state", "prelude_state")) {
            val (error, _) = validateStep(
                rows[0].get(key),
                "$provider.input.$key",
                linkedMapOf("begin" to 0L, "persist" to 0L, "end" to 0L),
                0,
            )
            if (error != null) return error
        }
        val preludePairs = rows[0].getOrNull("prelude_pairs")
        val resetBodyCount = (rows[0].get("reset_state").get("body_count") as PyValue.Int).value
        val preludeSteps = rows[0].getOrNull("prelude_steps")
        if (!pyEquals(preludeSteps ?: PyValue.Null, PyValue.Int(120)) ||
            preludePairs !is PyValue.Seq || preludePairs.items.size != 120 ||
            preludePairs.items.any { pairs ->
                pairs !is PyValue.Seq || pairs.items.any { !bodyPair(it, resetBodyCount) }
            }
        ) {
            return pyMap(
                "path" to pyText("$provider.input.prelude_pairs"),
                "reason" to pyText("missing or invalid pair order"),
            )
        }
        val contactCounts = linkedMapOf("begin" to 0L, "persist" to 0L, "end" to 0L)
        var toiCount = 0L
        for ((index, row) in rows.drop(1).withIndex()) {
            val (error, nextCount) = validateStep(row, "$provider.step[$index]", contactCounts, toiCount)
            toiCount = nextCount
            if (error != null) return error
        }
        return null
    }

    /** `fixed_replay.first_difference`. */
    fun firstDifference(
        left: PyValue,
        right: PyValue,
        path: String = "",
        limits: Map<String, Pair<Double, String>> = ReplayContract.LIMITS,
    ): PyValue? {
        if (left.typeName != right.typeName) {
            return pyMap(
                "path" to pyText(path),
                "baseline" to left,
                "candidate" to right,
            )
        }
        if (left is PyValue.Map) {
            val other = right as PyValue.Map
            if (left.entries.keys != other.entries.keys) {
                return pyMap(
                    "path" to pyText("$path.keys"),
                    "baseline" to left.sortedKeys(),
                    "candidate" to other.sortedKeys(),
                )
            }
            for ((key, value) in left.entries) {
                val difference = firstDifference(
                    value,
                    other.entries.getValue(key),
                    if (path.isEmpty()) key else "$path.$key",
                    limits,
                )
                if (difference != null) return difference
            }
            return null
        }
        if (left is PyValue.Seq) {
            val other = right as PyValue.Seq
            if (left.items.size != other.items.size) {
                return pyMap(
                    "path" to pyText("$path.length"),
                    "baseline" to pyInt(left.items.size),
                    "candidate" to pyInt(other.items.size),
                )
            }
            for (index in left.items.indices) {
                val difference = firstDifference(left.items[index], other.items[index], "$path[$index]", limits)
                if (difference != null) return difference
            }
            return null
        }
        val field = path.split('.').last()
        val limit = limits[field]
        if (limit != null && left.isNumber()) {
            val (bound, unit) = limit
            val difference = kotlin.math.abs(pyRealOf(left) - pyRealOf(right))
            if (difference > bound) {
                return pyMap(
                    "path" to pyText(path),
                    "baseline" to left,
                    "candidate" to right,
                    "absolute_difference" to pyReal(difference),
                    "limit" to pyReal(bound),
                    "unit" to pyText(unit),
                )
            }
        } else if (!pyEquals(left, right)) {
            return pyMap(
                "path" to pyText(path),
                "baseline" to left,
                "candidate" to right,
            )
        }
        return null
    }

    private fun pyRealOf(value: PyValue): Double = when (value) {
        is PyValue.Int -> value.value.toDouble()
        is PyValue.Real -> value.value
        is PyValue.Bool -> if (value.value) 1.0 else 0.0
        else -> throw PyTypeError("must be real number, not ${value.typeName}")
    }

    /** `fixed_replay.repeatability_difference`. */
    fun repeatabilityDifference(first: List<PyValue>, second: List<PyValue>): PyValue? {
        if (first.size != second.size) {
            return pyMap(
                "path" to pyText("step.sequence"),
                "first_count" to pyInt(first.size - 1),
                "repeat_count" to pyInt(second.size - 1),
            )
        }
        for ((index, pair) in first.zip(second).withIndex()) {
            val (left, right) = pair
            val difference = firstDifference(
                left,
                right,
                if (index == 0) "input" else "step[${index - 1}]",
                emptyMap(),
            )
            if (difference != null) return difference
        }
        return null
    }

    /** `fixed_replay.process_identity`. */
    fun processIdentity(stderr: String): String {
        val markers = stderr.split('\n').filter { it.startsWith("REPLAY_PROCESS ") }
        if (markers.size != 1 || " start_ms=" !in markers[0]) {
            throw MigrationFailure("replay process identity missing or ambiguous")
        }
        return markers[0]
    }

    /** `fixed_replay.ordering_difference`. */
    fun orderingDifference(left: PyValue, right: PyValue, index: Int): PyValue? {
        val leftBodies = (left.get("bodies") as PyValue.Seq).items
        val rightBodies = (right.get("bodies") as PyValue.Seq).items
        for ((bodyIndex, pair) in leftBodies.zip(rightBodies).withIndex()) {
            val (bodyA, bodyB) = pair
            for (field in listOf("identity_hash", "fixture_identity_hashes")) {
                val difference = firstDifference(
                    bodyA.get(field),
                    bodyB.get(field),
                    "step[$index].bodies[$bodyIndex].$field",
                    emptyMap(),
                )
                if (difference != null) return difference
            }
        }
        for (field in listOf("ccd_pairs", "ccd_candidates")) {
            val difference = firstDifference(
                left.get(field),
                right.get(field),
                "step[$index].$field",
                emptyMap(),
            )
            if (difference != null) return difference
        }
        return null
    }

    /** `fixed_replay.compare`. */
    fun compare(
        baselineRows: List<PyValue>,
        candidateRows: List<PyValue>,
        baselineSha: String,
        candidateSha: String,
    ): PyValue {
        val (baseline, badBaseline) = readStream(baselineRows, "baseline", baselineSha)
        val (candidate, badCandidate) = readStream(candidateRows, "candidate", candidateSha)
        var divergence = badBaseline ?: badCandidate
        if (divergence == null) {
            divergence = missingChannel(baseline, "baseline") ?: missingChannel(candidate, "candidate")
        }
        if (divergence == null) {
            for ((name, rows) in listOf("baseline" to baseline, "candidate" to candidate)) {
                if (!finiteTree(PyValue.Seq(rows))) {
                    divergence = pyMap(
                        "path" to pyText("$name.nonfinite"),
                        "reason" to pyText("non-finite number"),
                    )
                    break
                }
                val last = rows.last()
                val toiHits = last.get("toi_hits")
                val toiListenerHits = last.get("toi_listener_hits")
                if (pyLessThanOrEqual(toiHits, 0) || pyLessThanOrEqual(toiListenerHits, 0)) {
                    divergence = pyMap(
                        "path" to pyText("$name.ccd_activity"),
                        "reason" to pyText("no observed TOI hit"),
                    )
                    break
                }
                if (pyLessThanOrEqual(last.get("contact_begin"), 0)) {
                    divergence = pyMap(
                        "path" to pyText("$name.contact_activity"),
                        "reason" to pyText("no observed contact begin"),
                    )
                    break
                }
            }
        }
        val schemaValid = divergence == null
        if (divergence == null) {
            val baselineHeader = baseline[0] as PyValue.Map
            val candidateHeader = candidate[0] as PyValue.Map
            for (key in ReplayContract.IDENTITY) {
                if (!baselineHeader.entries.containsKey(key) ||
                    !candidateHeader.entries.containsKey(key)
                ) {
                    divergence = pyMap(
                        "path" to pyText("input.$key"),
                        "baseline" to (baseline[0].getOrNull(key) ?: PyValue.Null),
                        "candidate" to (candidate[0].getOrNull(key) ?: PyValue.Null),
                    )
                    break
                }
                divergence = firstDifference(baseline[0].get(key), candidate[0].get(key), "input.$key", emptyMap())
                if (divergence != null) break
            }
        }
        var orderingDivergence: PyValue? = null
        if (schemaValid &&
            !pyEquals(baseline[0].get("prelude_pairs"), candidate[0].get("prelude_pairs"))
        ) {
            orderingDivergence = firstDifference(
                baseline[0].get("prelude_pairs"),
                candidate[0].get("prelude_pairs"),
                "input.prelude_pairs",
                emptyMap(),
            )
        }
        if (divergence == null) {
            val ignored = setOf("toi_calls")
            for ((index, pair) in baseline.drop(1).zip(candidate.drop(1)).withIndex()) {
                val (a, b) = pair
                val stepOrdering = orderingDifference(a, b, index)
                if (orderingDivergence == null) orderingDivergence = stepOrdering
                if (divergence == null) {
                    divergence = stepOrdering ?: firstDifference(
                        PyValue.Map(
                            LinkedHashMap((a as PyValue.Map).entries.filterKeys { it !in ignored }),
                        ),
                        PyValue.Map(
                            LinkedHashMap((b as PyValue.Map).entries.filterKeys { it !in ignored }),
                        ),
                        "step[$index]",
                    )
                }
            }
        }
        val orderingStatus = when {
            divergence != null && orderingDivergence == null -> "NOT_RUN"
            orderingDivergence != null -> "FAILED"
            else -> "PASSED"
        }
        val rules = PyValue.Map(
            LinkedHashMap(
                ReplayContract.LIMITS.mapValues { (_, limit) ->
                    pyMap("absolute" to pyReal(limit.first), "unit" to pyText(limit.second))
                },
            ),
        )
        fun calls(rows: List<PyValue>): PyValue = pyList(
            rows.drop(1).map { it.getOrNull("toi_calls") ?: PyValue.Null },
        )
        return pyMap(
            "status" to pyText(if (divergence != null) "FAILED" else "PASSED"),
            "first_divergence" to (divergence ?: PyValue.Null),
            "ordering_identity" to pyMap(
                "status" to pyText(orderingStatus),
                "first_divergence" to (orderingDivergence ?: PyValue.Null),
            ),
            "compared_observations" to pyInt(minOf(baseline.size, candidate.size) - 1),
            "rules" to rules,
            "toi_detector_calls" to pyMap("baseline" to calls(baseline), "candidate" to calls(candidate)),
        )
    }

    /** Python's `left <= right` for the integer channels the activity checks read. */
    private fun pyLessThanOrEqual(value: PyValue, bound: Long): Boolean = when (value) {
        is PyValue.Int -> value.value <= bound
        is PyValue.Bool -> (if (value.value) 1L else 0L) <= bound
        is PyValue.Real -> value.value <= bound
        else -> throw PyTypeError("'<=' not supported between instances of '${value.typeName}' and 'int'")
    }
}
