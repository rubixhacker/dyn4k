#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import os
import sys
import time
from pathlib import Path

from runner import sha256


def observe_browser(pid: int, selected: Path, attestation: Path,
                    token: str, runtime: str) -> None:
    allowed = {selected}
    if runtime == "firefox":
        allowed.add(selected.with_name("firefox-bin"))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            image = Path(os.readlink(f"/proc/{pid}/exe")).resolve()
            if image in allowed:
                digest = sha256(Path(f"/proc/{pid}/exe"))
                if digest == sha256(image):
                    record = {
                        "token": token,
                        "runtime": runtime,
                        "selected_binary": str(selected),
                        "selected_sha256": sha256(selected),
                        "process_executable": str(image),
                        "process_sha256": digest,
                        "pid": pid,
                    }
                    with attestation.open("a") as stream:
                        fcntl.flock(stream, fcntl.LOCK_EX)
                        stream.write(json.dumps(record, sort_keys=True) + "\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                        fcntl.flock(stream, fcntl.LOCK_UN)
                    return
        except (FileNotFoundError, PermissionError):
            pass
        time.sleep(0.01)
    print("selected browser process image was not observed", file=sys.stderr)


def main() -> None:
    selected = Path(os.environ["DYN4K_BROWSER_SELECTED_BINARY"]).resolve()
    attestation = Path(os.environ["DYN4K_BROWSER_ATTESTATION"])
    token = os.environ["DYN4K_BROWSER_TOKEN"]
    runtime = os.environ["DYN4K_BROWSER_RUNTIME"]
    pid = os.getpid()
    if os.fork() == 0:
        try:
            observe_browser(pid, selected, attestation, token, runtime)
        finally:
            os._exit(0)
    os.execv(str(selected), [str(selected), *sys.argv[1:]])


if __name__ == "__main__":
    main()
