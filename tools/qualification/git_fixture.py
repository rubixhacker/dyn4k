"""Git fixture helpers the qualification suites share.

`test_safari_yarn_lock.py` used to define these. Its cases now live in
`:qualification`'s `SafariYarnLock*` suites, but `test_full_hosted.py` still builds
loose objects with them, so the helpers outlive the suite that introduced them.
"""
import os
import subprocess
import zlib
from pathlib import Path


def replace_loose_object(repository, advertised, source, kind):
    raw = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "cat-file", kind, source])
    write_loose_object(repository, advertised, raw, kind)


def write_loose_object(repository, advertised, raw, kind):
    slot = Path(repository) / ".git/objects" / advertised[:2] / advertised[2:]
    slot.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt" and slot.exists():
        slot.chmod(0o666)
    elif slot.exists():
        slot.unlink()
    slot.write_bytes(zlib.compress(kind.encode() + b" " + str(len(raw)).encode()
                                   + b"\0" + raw))


def git_oid(repository, revision):
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "rev-parse", revision],
        text=True).strip()
