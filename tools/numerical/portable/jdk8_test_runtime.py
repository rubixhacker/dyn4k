import os
from pathlib import Path
import subprocess


ENV = "DYN4K_TEST_JDK8_HOME"


def selected_test_jdk8_home():
    value = os.environ.get(ENV, "")
    if not value:
        raise RuntimeError(ENV + " must name a real Java 8 JDK")
    home = Path(value)
    if (not home.is_absolute() or home.resolve() != home or not home.is_dir() or
            any(not (home / "bin" / tool).is_file() or
                not os.access(home / "bin" / tool, os.X_OK)
                for tool in ("java", "javac"))):
        raise RuntimeError(ENV + " must name a real Java 8 JDK")
    for tool, marker in (("java", 'version "1.8.'), ("javac", "javac 1.8.")):
        result = subprocess.run([str(home / "bin" / tool), "-version"],
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode or marker not in result.stdout + result.stderr:
            raise RuntimeError(ENV + " has the wrong " + tool + " version")
    return home
