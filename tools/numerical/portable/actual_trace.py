import hashlib
import io
import re
import stat
import zipfile

from numeric_producer import SYSCALLS, trace_arguments
from numeric_producer_trace import _events
from receipt import Rejected


class TraceRejected(Rejected):
    pass


SOCKET_SYSCALLS = (
    "socket", "socketpair", "bind", "listen", "connect", "accept", "accept4",
    "getsockname", "getpeername", "shutdown", "sendto", "recvfrom", "sendmsg",
    "recvmsg")
PROCESS_SYSCALLS = (
    "clone", "clone3", "fork", "vfork", "execve", "execveat", "wait4",
    "waitid", "exit", "exit_group", "setpgid", "setsid", "unshare", "setns",
    "pidfd_open", "pidfd_send_signal", "kill", "tkill", "tgkill")
ALLOWED = set(SYSCALLS.split(",")) - {"process"} | set(SOCKET_SYSCALLS) | set(PROCESS_SYSCALLS)
FD_TOKEN = re.compile(r"([0-9]+)<([^<>\r\n]+)>")
CALL = re.compile(r"([a-z][a-z0-9_]*)\(")
MAX_READER_BYTES = 128 * 1024 * 1024


def normalize_rich_traces(traces):
    normalized = {}
    aborted = []
    for tid, data in traces.items():
        if type(data) is not bytes or not data.endswith(b"\n"):
            raise TraceRejected("rich trace final record is incomplete")
        try:
            lines = data.decode("utf-8").splitlines()
        except UnicodeError as error:
            raise TraceRejected("rich trace encoding differs") from error
        pending = None
        direct_aborted = []
        output = []
        for line in lines:
            abandoned = re.fullmatch(
                r"([0-9]+\.[0-9]+) (([a-z][a-z0-9_]*)\(.*) <unfinished \.\.\.>\) = \?",
                line)
            unfinished = re.fullmatch(
                r"([0-9]+\.[0-9]+) (([a-z][a-z0-9_]*)\(.*) <unfinished \.\.\.>",
                line)
            resumed = re.fullmatch(
                r"([0-9]+\.[0-9]+) <\.\.\. ([a-z][a-z0-9_]*) resumed>(.*)",
                line)
            if abandoned:
                if pending is not None or abandoned[3] not in (
                        "accept", "accept4", "wait4", "waitid"):
                    raise TraceRejected("rich abandoned syscall differs")
                direct_aborted.append(abandoned[3])
                continue
            if unfinished:
                if pending is not None or unfinished[3] not in ALLOWED:
                    raise TraceRejected("rich split syscall start is ambiguous")
                pending = (unfinished[3], unfinished[2])
                continue
            if resumed:
                if pending is None or pending[0] != resumed[2]:
                    raise TraceRejected("rich split syscall completion differs")
                output.append(resumed[1] + " " + pending[1] + resumed[3])
                pending = None
                continue
            output.append(line)
        if pending is not None:
            if pending[0] not in ("accept", "accept4", "wait4", "waitid") or not any(
                    line.endswith(" +++ exited with 0 +++") for line in output):
                raise TraceRejected("rich protected syscall has no completion")
            aborted.append((tid, pending[0]))
        if direct_aborted:
            if not any(line.endswith(" +++ exited with 0 +++") for line in output):
                raise TraceRejected("rich abandoned syscall has no terminal exit")
            aborted.extend((tid, name) for name in direct_aborted)
        normalized[tid] = ("\n".join(output) + "\n").encode()
    return normalized, aborted


def rich_trace_arguments():
    args = trace_arguments()
    args[-1] = args[-1] + "," + ",".join(SOCKET_SYSCALLS)
    return args


def _project_descriptors(call):
    output = []
    quoted = False
    escaped = False
    index = 0
    while index < len(call):
        char = call[index]
        if quoted:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            quoted = True
            output.append(char)
            index += 1
            continue
        match = FD_TOKEN.match(call, index)
        if match:
            output.append(match[1])
            index = match.end()
            continue
        output.append(char)
        index += 1
    if quoted:
        raise TraceRejected("trace quoted record is incomplete")
    return "".join(output)


def _validate_calls(events, protected):
    tables = {}
    for _, tid, _, call in events:
        if call.startswith(("+++ exited with ", "+++ killed by ", "--- SIG")):
            continue
        match = CALL.match(call)
        if match is None or match[1] not in ALLOWED:
            raise TraceRejected("unsupported protected trace operation")
        name = match[1]
        if "<unfinished ...>" in call or "resumed>" in call:
            raise TraceRejected("protected syscall completion is ambiguous")
        table = tables.setdefault(tid, {})
        child = re.match(r"(?:clone|clone3|fork|vfork)\(.*\) = ([1-9][0-9]*)$", call)
        if child:
            if child[1] in tables:
                raise TraceRejected("rich child descriptor table is ambiguous")
            tables[child[1]] = table if "CLONE_FILES" in call else dict(table)
        duplicate = re.fullmatch(
            r"(?:dup|dup2|dup3|fcntl)\(([0-9]+)<([^>]+)>(.*?)\) = ([0-9]+)<([^>]+)>",
            call)
        if duplicate and (name != "fcntl" or "F_DUPFD" in duplicate[3]):
            old_fd, old_path, _, new_fd, new_path = duplicate.groups()
            if table.get(old_fd, old_path) != old_path or old_path != new_path:
                raise TraceRejected("duplicated descriptor path differs")
            table[new_fd] = old_path
            continue
        for fd, path in FD_TOKEN.findall(call):
            prior = table.get(fd)
            if path in protected and prior is not None and prior != path:
                raise TraceRejected("protected descriptor identity changed")
        if name in ("open", "openat", "openat2", "creat"):
            opened = re.search(r" = ([0-9]+)<([^<>\r\n]+)>$", call)
            if any(path in call for path in protected) and opened is None:
                raise TraceRejected("protected input open is incomplete")
            if opened:
                table[opened[1]] = opened[2]
        elif name == "close":
            closing = re.match(r"close\(([0-9]+)(?:<[^<>\r\n]+>)?\) = 0$", call)
            if closing:
                table.pop(closing[1], None)
        elif name == "close_range":
            closed = re.match(r"close_range\(([0-9]+), ([0-9]+),", call)
            if closed and call.endswith(" = 0"):
                for fd in list(table):
                    if int(closed[1]) <= int(fd) <= int(closed[2]):
                        table.pop(fd)
        elif name.startswith("dup") or name == "fcntl":
            if any(path in call for path in protected):
                raise TraceRejected("protected descriptor duplication is unbound")
    return tables


def checked_projection(raw, protected=()):
    if type(raw) is not bytes or not raw or len(raw) > MAX_READER_BYTES:
        raise TraceRejected("rich trace archive exceeds reader bound")
    if not isinstance(protected, (set, frozenset, tuple, list)) or any(
            type(path) is not str or not path.startswith("/") for path in protected):
        raise TraceRejected("protected trace path inventory differs")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if (not names or len(names) != len(set(names)) or
                    any(re.fullmatch(r"trace\.[1-9][0-9]*", name) is None
                        for name in names) or archive.testzip() is not None or
                    sum(member.file_size for member in members) > MAX_READER_BYTES or
                    any(stat.S_ISLNK(member.external_attr >> 16) for member in members)):
                raise TraceRejected("rich trace member inventory differs")
            traces = {name.removeprefix("trace."): archive.read(name) for name in names}
        normalized, aborted = normalize_rich_traces(traces)
        events = _events(normalized, tuple(protected))
        _validate_calls(events, set(protected))
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as legacy:
            for tid in sorted(normalized, key=int):
                projected = []
                for line in normalized[tid].decode("utf-8").splitlines():
                    _, call = line.split(" ", 1)
                    projected.append(_project_descriptors(call))
                legacy.writestr("trace." + tid, ("\n".join(projected) + "\n").encode())
        return {"raw_sha256": hashlib.sha256(raw).hexdigest(),
                "legacy_zip": output.getvalue(), "threads": len(traces),
                "raw_bytes": sum(map(len, traces.values())),
                "aborted_calls": len(aborted)}
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, RuntimeError,
            IndexError, Rejected) as error:
        if isinstance(error, TraceRejected):
            raise
        raise TraceRejected("rich trace is malformed or unbound") from error
