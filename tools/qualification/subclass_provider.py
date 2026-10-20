"""Convert local JAR provider URIs using the path rules of the runtime host."""

import nturl2path
import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import unquote, unquote_to_bytes, urlsplit


def local_file_uri_path(uri, *, windows=None):
    if (not isinstance(uri, str) or not uri or any(ord(char) < 32 or ord(char) == 127 for char in uri)
            or "?" in uri or "#" in uri or "\\" in uri
            or re.search(r"%(?![0-9A-Fa-f]{2})|%2f|%5c", uri, re.IGNORECASE)):
        raise ValueError("invalid provider URI")
    parsed = urlsplit(uri)
    if parsed.scheme != "file" or parsed.netloc or not parsed.path:
        raise ValueError("invalid provider URI")
    unquote_to_bytes(parsed.path).decode("utf-8")
    if windows is None:
        windows = os.name == "nt"
    if windows:
        if not re.fullmatch(r"/[A-Za-z]:/.*", parsed.path):
            raise ValueError("invalid provider URI")
        return PureWindowsPath(nturl2path.url2pathname(parsed.path))
    if not parsed.path.startswith("/") or parsed.path.startswith("//"):
        raise ValueError("invalid provider URI")
    decoded = unquote(parsed.path, errors="strict")
    if re.match(r"/[A-Za-z]:/", decoded):
        raise ValueError("invalid provider URI")
    return PurePosixPath(decoded)


def matches_provider(uri, provider):
    return Path(local_file_uri_path(uri)).resolve() == provider.resolve()
