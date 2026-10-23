import hashlib
import io
import re
import stat
import zipfile
from decimal import Decimal, InvalidOperation

from numeric_producer import SYSCALLS, trace_arguments
from numeric_producer_trace import _events, quoted
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
V6_FD_START = re.compile(r"([0-9]+)<")
V6_FILE = re.compile(r"/[^<>\r\n\"(),]+(?:<char [0-9]+:[0-9]+>)?")
V6_SOCKET = re.compile(
    r"(?:TCP|TCPv6|UDPv6):\[(?:->|[0-9A-Za-z:.%_\[\]-])+\]")
V6_UNIX_SOCKET = re.compile(r"UNIX-STREAM:\[[0-9]+->[0-9]+\]")
V6_PIPE = re.compile(r"pipe:\[[0-9]+\]")
V6_ANON_INODE = re.compile(r"anon_inode:(?:\[[0-9A-Za-z_-]+\]|[0-9A-Za-z_-]+)")
V6_EVENTFD = re.compile(
    r"\{eventfd-count=(?:0x)?[0-9a-f]+, eventfd-id=[0-9]+, "
    r"eventfd-semaphore=[0-9]+\}")
CALL = re.compile(r"([a-z][a-z0-9_]*)\(")
MAX_READER_BYTES = 128 * 1024 * 1024
V6_RAW_MAX_BYTES = 256 * 1024 * 1024
V6_RAW_MAX_MEMBERS = 1024
V6_RAW_MAX_LINES = 2000000
V6_RAW_MAX_RECORD_BYTES = 1024 * 1024
ENVIRONMENT_SENTINEL = b"DYN4K_CAPTURE_ENV_SENTINEL=portable-capture-check"
FORBIDDEN_ENVIRONMENT_KEY = b"OLLAMA_API_KEY"
QUOTED_BYTES = re.compile(rb'"(?:[^"\\]|\\.)*"')


def trace_exposes_environment(raw):
    if type(raw) is not bytes:
        raise TraceRejected("trace privacy input differs")
    if ENVIRONMENT_SENTINEL in raw or FORBIDDEN_ENVIRONMENT_KEY in raw:
        return True
    if b"\\" not in raw:
        return False
    for line in raw.splitlines():
        if b"\\" not in line:
            continue
        fragments = []
        for token in QUOTED_BYTES.finditer(line):
            try:
                decoded = quoted(token.group().decode("ascii", errors="backslashreplace"))
            except Rejected as error:
                raise TraceRejected("trace privacy string is malformed") from error
            if ENVIRONMENT_SENTINEL in decoded or FORBIDDEN_ENVIRONMENT_KEY in decoded:
                return True
            fragments.append(decoded)
        combined = b"".join(fragments)
        if ENVIRONMENT_SENTINEL in combined or FORBIDDEN_ENVIRONMENT_KEY in combined:
            return True
    return False


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
        previous = Decimal(0)
        terminal = False
        aborting = False
        for line in lines:
            record = re.fullmatch(r"([0-9]+\.[0-9]+) (.+)", line)
            if record is None or terminal:
                raise TraceRejected("rich raw timestamp or terminal order differs")
            try:
                stamp = Decimal(record[1])
            except InvalidOperation as error:
                raise TraceRejected("rich raw timestamp differs") from error
            if stamp < previous:
                raise TraceRejected("rich raw timestamp moved backwards")
            previous = stamp
            if record[2].startswith(("+++ exited with ", "+++ killed by ")):
                terminal = True
            if aborting and not record[2].startswith(("--- SIG", "+++ exited with ")):
                raise TraceRejected("rich abandoned syscall lifecycle differs")
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
                aborting = True
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
            if pending is not None and not record[2].startswith((
                    "--- SIG", "+++ exited with ")):
                raise TraceRejected("rich split syscall lifecycle differs")
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


def _version6_fd_token(call, index, *, directory=False):
    if directory:
        if not call.startswith("AT_FDCWD<", index):
            raise TraceRejected("version 6 directory descriptor differs")
        number = "AT_FDCWD"
        beginning = index + len("AT_FDCWD<")
    else:
        match = V6_FD_START.match(call, index)
        if match is None:
            raise TraceRejected("version 6 descriptor decoration is incomplete")
        number = match[1]
        beginning = match.end()
    socket = call.startswith(("TCP:", "TCPv6:", "UDPv6:",
                              "UNIX-STREAM:"), beginning)
    cursor = beginning
    nested = False
    while cursor < len(call):
        if call.startswith("->", cursor) and socket:
            cursor += 2
            continue
        char = call[cursor]
        if char == ">":
            break
        if char == "<":
            inner = re.match(r"<char [0-9]+:[0-9]+>", call[cursor:])
            if socket or nested or inner is None:
                raise TraceRejected("version 6 descriptor nesting differs")
            nested = True
            cursor += inner.end()
            continue
        if char in '"\r\n':
            raise TraceRejected("version 6 descriptor decoration is incomplete")
        cursor += 1
    if cursor == len(call):
        raise TraceRejected("version 6 descriptor decoration is incomplete")
    decoration = call[beginning:cursor]
    if directory:
        valid = V6_FILE.fullmatch(decoration) is not None and not nested
    elif decoration.startswith(("TCP:", "TCPv6:", "UDPv6:")):
        valid = V6_SOCKET.fullmatch(decoration) is not None
        valid = valid and decoration.count("->") <= 1
        valid = valid and (not decoration.startswith("UDPv6:") or
                           "->" not in decoration)
        depth = 0
        for char in decoration[decoration.index(":") + 1:]:
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth < 0:
                    valid = False
        valid = valid and depth == 0
    else:
        valid = any(pattern.fullmatch(decoration) is not None for pattern in (
            V6_FILE, V6_UNIX_SOCKET, V6_PIPE, V6_ANON_INODE, V6_EVENTFD))
    if not valid:
        raise TraceRejected("version 6 descriptor decoration differs")
    end = cursor + 1
    if decoration.startswith("/") and call.startswith("(deleted)", end):
        end += len("(deleted)")
    if end < len(call) and call[end] not in ",)]":
        raise TraceRejected("version 6 descriptor has a trailing fragment")
    return number, end


def _project_descriptors(call, *, version6_raw=False, descriptors=None):
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
        if call.startswith("AT_FDCWD<", index):
            if version6_raw:
                _, end = _version6_fd_token(call, index, directory=True)
            else:
                end = call.find(">", index)
                if end < 0:
                    raise TraceRejected("rich directory descriptor is incomplete")
                end += 1
            if descriptors is not None:
                descriptors.append(("AT_FDCWD", call[index + len("AT_FDCWD<"):end - 1]))
            output.append("AT_FDCWD")
            index = end
            continue
        if version6_raw and V6_FD_START.match(call, index):
            number, end = _version6_fd_token(call, index)
            if descriptors is not None:
                closing = end - (len("(deleted)") if call[index:end].endswith(
                    "(deleted)") else 0)
                descriptors.append((number, call[index + len(number) + 1:closing - 1]))
            output.append(number)
            index = end
            continue
        match = FD_TOKEN.match(call, index) if not version6_raw else None
        if match:
            if descriptors is not None:
                descriptors.append((match[1], match[2]))
            output.append(match[1])
            index = match.end()
            continue
        if version6_raw and char.isdigit():
            end = index
            while end < len(call) and call[end].isdigit():
                end += 1
            if end < len(call) and call[end] == "<":
                raise TraceRejected("version 6 descriptor decoration is unsupported")
        output.append(char)
        index += 1
    if quoted:
        raise TraceRejected("trace quoted record is incomplete")
    return "".join(output)


def _arguments(call):
    start = call.find("(")
    if start < 0:
        raise TraceRejected("protected syscall arguments are missing")
    values = []
    depth = 0
    quoted = False
    escaped = False
    beginning = start + 1
    for index in range(start + 1, len(call)):
        char = call[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            if char == ")" and depth == 0:
                values.append(call[beginning:index].strip())
                return values
            depth -= 1
            if depth < 0:
                break
        elif char == "," and depth == 0:
            values.append(call[beginning:index].strip())
            beginning = index + 1
    raise TraceRejected("protected syscall arguments are incomplete")


def _check_operand(value, table, protected):
    match = re.fullmatch(r"([0-9]+)(?:<([^<>\r\n]+)>)?", value)
    if match is None:
        raise TraceRejected("protected descriptor operand is unsupported")
    known = table.get(match[1])
    if (known in protected and match[2] != known or
            match[2] in protected and known != match[2]):
        raise TraceRejected("protected descriptor operand differs")


def _validate_calls(events, protected, strict_outputs=(), *, version6_raw=False):
    tables = {}
    written = set()
    output_owners = {}
    first_fd = {"read", "pread64", "readv", "preadv", "write", "writev",
                "pwrite64", "pwritev", "lseek", "fstat", "fcntl", "close",
                "dup", "dup2", "dup3", "ftruncate", "mmap", "sendfile",
                "copy_file_range", "splice", "sendto", "recvfrom", "sendmsg",
                "recvmsg", "bind", "listen", "connect", "accept", "accept4",
                "getsockname", "getpeername", "shutdown"}
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
        if name.startswith(("rename", "unlink", "truncate")) and any(
                path in call for path in strict_outputs):
            raise TraceRejected("protected output was replaced after capture")
        leading = re.match(r"[a-z][a-z0-9_]*\(([0-9]+)(?:<([^<>\r\n]+)>)?(?=[,)])", call)
        if name in first_fd and leading:
            fd, decorated = leading.groups()
            known = table.get(fd)
            if known in protected and decorated != known:
                raise TraceRejected("protected descriptor use lost its destination")
            if decorated in protected and known != decorated:
                raise TraceRejected("protected descriptor creation is unavailable")
            if known in strict_outputs and output_owners.get(known) != tid:
                raise TraceRejected("protected output crossed a trace thread")
            if known in strict_outputs:
                if name not in ("write", "close", "fstat", "ftruncate"):
                    raise TraceRejected("protected output operation is unbound")
                if name == "ftruncate" and (
                        not re.fullmatch(r'ftruncate\(' + fd + r'<' +
                                         re.escape(known) + r'>, 0\) = 0', call) or
                        known in written):
                    raise TraceRejected("protected output truncate differs")
                if name == "write" and re.search(r'\) = [1-9][0-9]*$', call):
                    written.add(known)
        if name in ("openat", "openat2", "newfstatat", "statx", "unlinkat",
                    "renameat", "renameat2"):
            args = _arguments(call)
            positions = (0, 2) if name.startswith("renameat") else (0,)
            if len(args) <= max(positions):
                raise TraceRejected("protected directory descriptor is incomplete")
            for position in positions:
                if re.match(r"[0-9]+(?:<|$)", args[position]):
                    _check_operand(args[position], table, protected)
        if name in ("mmap", "sendfile", "copy_file_range", "splice"):
            if any(path in call for path in strict_outputs):
                raise TraceRejected("protected output transfer is unsupported")
            args = _arguments(call)
            positions = ((4,) if name == "mmap" else
                         (0, 1) if name == "sendfile" else (0, 2))
            if len(args) <= max(positions):
                raise TraceRejected("protected transfer arguments differ")
            for position in positions:
                if args[position] == "-1" and name == "mmap":
                    continue
                _check_operand(args[position], table, protected)
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
            if (table.get(old_fd, old_path) != old_path or old_path != new_path or
                    old_path in protected and table.get(old_fd) != old_path):
                raise TraceRejected("duplicated descriptor path differs")
            prior_target = table.get(new_fd)
            if (prior_target in protected and prior_target != old_path or
                    old_path in strict_outputs or prior_target in strict_outputs):
                raise TraceRejected("protected descriptor reassignment is unbound")
            table[new_fd] = old_path
            continue
        if name in ("dup2", "dup3"):
            target = re.match(r"dup[23]\([^,]+, ([0-9]+)(?:<([^<>\r\n]+)>)?", call)
            if target and table.get(target[1]) in protected:
                raise TraceRejected("protected descriptor reassignment is incomplete")
        descriptors = []
        _project_descriptors(call, version6_raw=version6_raw,
                             descriptors=descriptors)
        for fd, path in descriptors:
            prior = table.get(fd)
            if path in protected and prior is not None and prior != path:
                raise TraceRejected("protected descriptor identity changed")
        if name in ("open", "openat", "openat2", "creat"):
            opened = re.search(r" = ([0-9]+)<([^<>\r\n]+)>$", call)
            if any(path in call for path in protected) and opened is None:
                raise TraceRejected("protected input open is incomplete")
            if opened:
                requested = re.search(r'"([^"\r\n]+)"', call)
                if (opened[2] in protected or
                        requested is not None and requested[1] in protected) and (
                        requested is None or requested[1] != opened[2]):
                    raise TraceRejected("protected open returned another destination")
                if table.get(opened[1]) in protected:
                    raise TraceRejected("protected descriptor was reassigned by open")
                table[opened[1]] = opened[2]
                if opened[2] in strict_outputs:
                    if opened[2] in output_owners:
                        raise TraceRejected("protected output was opened again")
                    output_owners[opened[2]] = tid
        elif name == "close":
            closing = re.match(r"close\(([0-9]+)(?:<[^<>\r\n]+>)?\) = 0$", call)
            if closing:
                table.pop(closing[1], None)
        elif name == "close_range":
            closed = re.fullmatch(r"close_range\(([0-9]+), ([0-9]+), 0\) = 0", call)
            if closed:
                for fd in list(table):
                    if int(closed[1]) <= int(fd) <= int(closed[2]):
                        if table[fd] in strict_outputs:
                            raise TraceRejected("protected output close range is unbound")
                        table.pop(fd)
            elif any(path in protected for path in table.values()):
                raise TraceRejected("protected close range is ambiguous")
        elif name.startswith("dup") or name == "fcntl":
            if any(path in call for path in protected):
                raise TraceRejected("protected descriptor duplication is unbound")
    return tables


def validate_version6_raw_archive(raw, archive):
    if type(raw) is not bytes or not raw or len(raw) > V6_RAW_MAX_BYTES:
        raise TraceRejected("version 6 raw archive exceeds reader bound")
    members = archive.infolist()
    names = [member.filename for member in members]
    if (not names or len(names) > V6_RAW_MAX_MEMBERS or
            len(names) != len(set(names)) or
            any(re.fullmatch(r"trace\.[1-9][0-9]*", name) is None
                for name in names) or
            any(stat.S_ISLNK(member.external_attr >> 16) for member in members)):
        raise TraceRejected("version 6 raw member inventory differs")
    if sum(member.file_size for member in members) > V6_RAW_MAX_BYTES:
        raise TraceRejected("version 6 raw declared decoded total exceeds reader bound")
    decoded = 0
    lines = 0
    for member in members:
        actual = 0
        with archive.open(member) as stream:
            while record := stream.readline(V6_RAW_MAX_RECORD_BYTES + 1):
                if len(record) > V6_RAW_MAX_RECORD_BYTES or not record.endswith(b"\n"):
                    raise TraceRejected("version 6 raw record exceeds bound or is incomplete")
                actual += len(record)
                decoded += len(record)
                lines += 1
                if decoded > V6_RAW_MAX_BYTES:
                    raise TraceRejected("version 6 raw actual decoded total exceeds reader bound")
                if lines > V6_RAW_MAX_LINES:
                    raise TraceRejected("version 6 raw physical line count exceeds bound")
        if actual != member.file_size:
            raise TraceRejected("version 6 raw actual decoded size differs")
    return members


def checked_projection(raw, protected=(), *, strict_outputs=(), version6_raw=False):
    if (type(version6_raw) is not bool or type(raw) is not bytes or not raw or
            len(raw) > (V6_RAW_MAX_BYTES if version6_raw else MAX_READER_BYTES)):
        raise TraceRejected("rich trace archive exceeds reader bound")
    if not isinstance(protected, (set, frozenset, tuple, list)) or any(
            type(path) is not str or not path.startswith("/") for path in protected):
        raise TraceRejected("protected trace path inventory differs")
    if (not isinstance(strict_outputs, (set, frozenset, tuple, list)) or
            not set(strict_outputs) <= set(protected)):
        raise TraceRejected("protected output path inventory differs")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = (validate_version6_raw_archive(raw, archive) if version6_raw
                       else archive.infolist())
            names = [member.filename for member in members]
            if (not version6_raw and (not names or len(names) != len(set(names)) or
                    any(re.fullmatch(r"trace\.[1-9][0-9]*", name) is None
                        for name in names) or archive.testzip() is not None or
                    sum(member.file_size for member in members) > MAX_READER_BYTES or
                    any(stat.S_ISLNK(member.external_attr >> 16) for member in members))):
                raise TraceRejected("rich trace member inventory differs")
            traces = {name.removeprefix("trace."): archive.read(name) for name in names}
        if any(trace_exposes_environment(data) for data in traces.values()):
            raise TraceRejected("rich trace exposed the environment")
        normalized, aborted = normalize_rich_traces(traces)
        events = _events(normalized, tuple(protected))
        _validate_calls(events, set(protected), set(strict_outputs),
                        version6_raw=version6_raw)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as legacy:
            for tid in sorted(normalized, key=int):
                projected = []
                for line in normalized[tid].decode("utf-8").splitlines():
                    _, call = line.split(" ", 1)
                    projected.append(_project_descriptors(call,
                        version6_raw=version6_raw))
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
