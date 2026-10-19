#!/usr/bin/env python3
import ctypes
import fcntl
import hashlib
import json
import os
import sys
import time
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_path(pid):
    libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
    buffer = ctypes.create_string_buffer(4096)
    size = libproc.proc_pidpath(pid, buffer, len(buffer))
    return Path(os.fsdecode(buffer.value)).resolve() if size > 0 else None


def observe(pid, selected, record, token):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        image = image_path(pid)
        if image == selected:
            fingerprint = digest(image)
            if fingerprint == digest(selected):
                row = {"token": token, "runtime": "safari",
                       "selected_binary": str(selected), "selected_sha256": fingerprint,
                       "process_executable": str(image), "process_sha256": fingerprint,
                       "pid": pid}
                with record.open("a") as stream:
                    fcntl.flock(stream, fcntl.LOCK_EX)
                    stream.write(json.dumps(row, sort_keys=True) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    fcntl.flock(stream, fcntl.LOCK_UN)
                return
        time.sleep(0.01)
    print("selected Safari process image was not observed", file=sys.stderr)


def main():
    selected = Path(os.environ["DYN4K_BROWSER_SELECTED_BINARY"]).resolve()
    record = Path(os.environ["DYN4K_BROWSER_ATTESTATION"])
    pid = os.getpid()
    if os.fork() == 0:
        try:
            observe(pid, selected, record, os.environ["DYN4K_BROWSER_TOKEN"])
        finally:
            os._exit(0)
    os.execv(str(selected), [str(selected), *sys.argv[1:]])


if __name__ == "__main__":
    main()
