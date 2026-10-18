import hashlib
import os
import re
import subprocess
from pathlib import Path


JDK_HOME = "/tmp/dyn4k-tools/jdk21"
GRADLE_VERSION = "9.5.0"


def validate_build_jdk(raw, require_marker=True):
    daemon = (rf"(?m)^Starting process 'Gradle build daemon'.*?Command: "
              rf"{re.escape(JDK_HOME)}/bin/java .*?"
              rf"org\.gradle\.launcher\.daemon\.bootstrap\.GradleDaemon {re.escape(GRADLE_VERSION)}$")
    marker = (f"DYN4K_BUILD_JDK javaHome={JDK_HOME} javaVersion=21 "
              f"gradleVersion={GRADLE_VERSION}")
    if not re.search(daemon, raw) or "BUILD SUCCESSFUL" not in raw or \
            (require_marker and raw.count(marker) != 1):
        raise ValueError("wrong JDK 21 or Gradle 9.5.0 daemon build identity")
    return {"java_home": JDK_HOME, "java_version": "21", "gradle_version": GRADLE_VERSION}


def current_java():
    if os.environ.get("JAVA_HOME") != JDK_HOME:
        raise ValueError("wrong pinned JAVA_HOME")
    binary = Path(JDK_HOME) / "bin/java"
    if not binary.is_file():
        raise ValueError("pinned JDK 21 binary missing")
    output = subprocess.run([str(binary), "-version"], text=True, capture_output=True, check=True)
    versions = re.findall(r'(?m)^openjdk version "21\.[^\r\n]*', output.stderr)
    if len(versions) != 1:
        raise ValueError("wrong pinned JDK version")
    return {"java_home": JDK_HOME, "java_version": versions[0],
            "gradle_version": GRADLE_VERSION}


def build_log_identity(path, require_marker=False):
    raw = path.read_text()
    validated = validate_build_jdk(raw, require_marker=require_marker)
    matches = re.findall(r"(?m)The daemon log file: (\S+/daemon-\d+\.out\.log)$", raw)
    if len(matches) != 1:
        raise ValueError("Gradle daemon log identity missing")
    daemon = Path(matches[0])
    daemon_raw = daemon.read_text()
    if not re.search(rf"javaHome={re.escape(JDK_HOME)},javaVersion=21(?:,|\b)", daemon_raw):
        raise ValueError("wrong raw Gradle daemon javaHome or version")
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "daemon_log": {"path": str(daemon),
                           "sha256": hashlib.sha256(daemon.read_bytes()).hexdigest()},
            **validated}


def verify_build_log_identity(record, require_marker=False):
    path = Path(record["path"])
    if build_log_identity(path, require_marker=require_marker) != record:
        raise ValueError("build JDK log identity changed")
    return record
