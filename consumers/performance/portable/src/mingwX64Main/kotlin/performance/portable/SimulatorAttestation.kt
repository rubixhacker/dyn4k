package performance.portable

internal actual fun awaitSimulatorAttestation(source: String, nonce: String, dataContainer: String,
                                              commitment: String): Unit =
    error("simulator attestation is unavailable on Windows Native")
