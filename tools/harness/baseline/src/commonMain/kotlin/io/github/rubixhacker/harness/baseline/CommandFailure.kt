package io.github.rubixhacker.harness.baseline

/** The command failure `subprocess.CompletedProcess`'s `check=True` raises. */
class CommandFailure(
    val command: List<String>,
    val exitCode: Int,
) : Exception("Command '${pythonListRepr(command)}' returned non-zero exit status $exitCode.")

/** `os.environ` filtered the way `verify.git_environment` filters it. */
fun gitEnvironment(
    environment: Map<String, String> = System.getenv(),
    networkAuth: Boolean = false,
): Map<String, String> = environment.filter { (key, _) ->
    !key.startsWith("GIT_") || (networkAuth && key in GIT_NETWORK_AUTH_ENV)
}

private val GIT_NETWORK_AUTH_ENV = setOf(
    "GIT_ASKPASS",
    "GIT_SSH",
    "GIT_SSH_COMMAND",
    "GIT_SSH_VARIANT",
    "GIT_TERMINAL_PROMPT",
)
