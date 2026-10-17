#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from runner import sha256


def main() -> int:
    selected = Path(os.environ["DYN4K_BROWSER_SELECTED_BINARY"]).resolve()
    attestation = Path(os.environ["DYN4K_BROWSER_ATTESTATION"])
    token = os.environ["DYN4K_BROWSER_TOKEN"]
    runtime = os.environ["DYN4K_BROWSER_RUNTIME"]
    allowed = {selected}
    if runtime == "firefox":
        allowed.add(selected.with_name("firefox-bin"))

    child = subprocess.Popen([str(selected), *sys.argv[1:]])
    observed = None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and child.poll() is None:
        try:
            image = Path(os.readlink(f"/proc/{child.pid}/exe")).resolve()
            if image in allowed:
                digest = sha256(Path(f"/proc/{child.pid}/exe"))
                if digest == sha256(image):
                    observed = (image, digest)
                    break
        except (FileNotFoundError, PermissionError):
            pass
        time.sleep(0.01)
    if observed is None:
        if child.poll() is None:
            child.terminate()
        child.wait()
        print("selected browser process image was not observed", file=sys.stderr)
        return 1

    record = {
        "token": token,
        "runtime": runtime,
        "selected_binary": str(selected),
        "selected_sha256": sha256(selected),
        "process_executable": str(observed[0]),
        "process_sha256": observed[1],
        "pid": child.pid,
    }
    with attestation.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream, fcntl.LOCK_UN)
    return child.wait()


if __name__ == "__main__":
    sys.exit(main())
