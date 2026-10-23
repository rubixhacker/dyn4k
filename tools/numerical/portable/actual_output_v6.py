import hashlib
import io
import json
import re
import zipfile

from actual_trace import (_arguments, _project_descriptors, _validate_calls,
                          _version6_fd_token, normalize_rich_traces,
                          trace_exposes_environment)
from boolean_rotation_jdi import jdi_bridge
from numeric_producer_trace import _buffer, _events, quoted, successful_execve
from receipt import Rejected


ROLES = ("mirror", "worker_arguments", "worker_class_load", "helper_arguments")
OBSERVER_SOURCE = (
    "import os,sys\n"
    "if len(sys.argv)!=5: raise SystemExit(2)\n"
    "for path in sys.argv[1:]:\n"
    " fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)\n"
    " try: os.fstat(fd)\n"
    " finally: os.close(fd)\n"
)
_FD = r"([0-9]+)<([^<>]+)>"
_STATUS = re.compile(r"(?:fstat|newfstatat)\(" + _FD +
                     r", (.*)\) = 0")
_OPEN = re.compile(r"openat\(AT_FDCWD, (\"(?:\\.|[^\"\\])*\"), "
                   r"([^,)]*)(?:, 0?[0-7]+)?\) = ([0-9]+)")
_WRITE = re.compile(r"(write|writev)\(" + _FD + r", (.*)\) = ([0-9]+)")
_CLOSE = re.compile(r"close\(" + _FD + r"\) = 0")
_SOCKET = re.compile(r"socket\(AF_INET6?, SOCK_STREAM(?:\|SOCK_(?:CLOEXEC|NONBLOCK))*"
                     r", IPPROTO_(?:TCP|IP)\) = " + _FD)


def _require(condition, reason):
    if not condition:
        raise Rejected(reason)


def _identity(call):
    device = re.search(r"st_dev=makedev\(([^)]+)\)", call)
    inode = re.search(r"st_ino=([0-9]+)", call)
    size = re.search(r"st_size=([0-9]+)", call)
    _require(device is not None and inode is not None and size is not None and
             "S_IFREG" in call, "version 6 output identity is incomplete")
    parts = [part.strip() for part in device[1].split(",")]
    _require(len(parts) == 2 and all(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", part)
                                     for part in parts),
             "version 6 output device differs")
    major, minor = (int(part, 16 if part.startswith("0x") else 10)
                    for part in parts)
    return {"device_major": major, "device_minor": minor,
            "inode": int(inode[1]), "size": int(size[1])}


def _opening(call):
    if not call.startswith("openat("):
        return None
    projected = _project_descriptors(call, version6_raw=True)
    match = _OPEN.fullmatch(projected)
    if match is None:
        return None
    result_at = call.rfind(") = ")
    _require(result_at >= 0, "version 6 output open return differs")
    fd, end = _version6_fd_token(call, result_at + 4)
    _require(end == len(call) and fd == match[3],
             "version 6 output open descriptor differs")
    token = call[result_at + 4 + len(fd) + 1:end - 1]
    return match[1], match[2], fd, token


def _protected_observer_operand(call, paths):
    operand = _first_descriptor(call)
    if operand is not None and operand[1] in paths:
        return True
    name = call.split("(", 1)[0]
    if name not in ("open", "openat", "openat2", "stat", "lstat",
                    "newfstatat", "statx", "rename", "renameat",
                    "renameat2", "unlink", "unlinkat", "truncate"):
        return False
    for argument in _arguments(call):
        if (argument.startswith('"') and argument.endswith('"') and
                quoted(argument).decode("utf-8") in paths):
            return True
        if any(argument.endswith("<" + path + ">") for path in paths):
            return True
    return False


def observer_command(interpreter, paths):
    _require(type(interpreter) is str and interpreter.startswith("/") and
             type(paths) is tuple and len(paths) == 4 and
             all(type(path) is str and path.startswith("/") for path in paths),
             "version 6 observer command differs")
    return (interpreter, "-B", "-I", "-c", OBSERVER_SOURCE, *paths)


def declared_environment_hash(environment):
    _require(type(environment) is dict and all(type(key) is str and
             type(value) is str for key, value in environment.items()),
             "version 6 observer environment differs")
    return hashlib.sha256(json.dumps(environment, sort_keys=True,
                                   separators=(",", ":")).encode()).hexdigest()


def _terminal_stamp(events):
    by_thread = {}
    for stamp, tid, _, call in events:
        if call.startswith("+++ exited with "):
            _require(call == "+++ exited with 0 +++" and tid not in by_thread,
                     "version 6 producer exit differs")
            by_thread[tid] = stamp
        elif call.startswith("+++ killed by "):
            raise Rejected("version 6 producer was killed")
    _require(by_thread and {tid for _, tid, _, _ in events} == set(by_thread),
             "version 6 producer terminal inventory differs")
    return max(by_thread.values())


def verify_observer(raw_zip, interpreter, paths, identities, worker_events,
                    helper_events):
    _require(type(raw_zip) is bytes and not trace_exposes_environment(raw_zip),
             "version 6 observer privacy differs")
    try:
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
            names = archive.namelist()
            _require(len(names) == 1 and re.fullmatch(r"trace\.[1-9][0-9]*", names[0])
                     and archive.testzip() is None and len(raw_zip) <= 128 * 1024 * 1024
                     and archive.getinfo(names[0]).file_size <= 128 * 1024 * 1024,
                     "version 6 observer trace inventory differs")
            with archive.open(names[0]) as member:
                raw = member.read(128 * 1024 * 1024 + 1)
                _require(len(raw) == archive.getinfo(names[0]).file_size and
                         not member.read(1),
                         "version 6 observer trace size differs")
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
        if isinstance(error, Rejected):
            raise
        raise Rejected("version 6 observer trace is malformed") from error
    _require(not trace_exposes_environment(raw),
             "version 6 observer privacy differs")
    traces, aborted = normalize_rich_traces({names[0][6:]: raw})
    _require(not aborted, "version 6 observer syscall is incomplete")
    events = _events(traces, paths)
    _validate_calls(events, set(paths))
    expected_command = observer_command(interpreter, paths)
    execs = [(stamp, call) for stamp, _, _, call in events
             if call.startswith(("execve(", "execveat("))]
    _require(len(execs) == 1 and successful_execve(execs[0][1]) ==
             (interpreter, expected_command),
             "version 6 observer executable or argv differs")
    start = execs[0][0]
    _require(_terminal_stamp(worker_events) < start and
             _terminal_stamp(helper_events) < start,
             "version 6 observer preceded producer exit")
    _require(_terminal_stamp(events) > start,
             "version 6 observer exit differs")
    active = None
    observed = {}
    next_role = 0
    started = False
    for _, _, _, call in events:
        if not started and call != execs[0][1]:
            _require(not _protected_observer_operand(call, paths),
                     "version 6 observer protected launch action differs")
            continue
        if call == execs[0][1]:
            started = True
            continue
        opened = _opening(call)
        if opened and quoted(opened[0]).decode("utf-8") in paths:
            path = quoted(opened[0]).decode("utf-8")
            _require(active is None and next_role < 4 and path == paths[next_role] and
                     set(opened[1].split("|")) == {
                         "O_RDONLY", "O_CLOEXEC", "O_NOFOLLOW"} and
                     opened[3] == path,
                     "version 6 observer protected open differs")
            active = (opened[2], path, None)
            continue
        status = _STATUS.fullmatch(call)
        if status and active is not None and (status[1], status[2]) == active[:2]:
            _require(active[2] is None, "version 6 observer repeated identity")
            active = (active[0], active[1], _identity(status[3]))
            continue
        closed = _CLOSE.fullmatch(call)
        if closed and active is not None and (closed[1], closed[2]) == active[:2]:
            _require(active[2] == identities[ROLES[next_role]],
                     "version 6 observer output identity differs")
            observed[ROLES[next_role]] = active[2]
            next_role += 1
            active = None
            continue
        if call.startswith("fcntl("):
            operand = _first_descriptor(call)
            projected = _project_descriptors(call, version6_raw=True)
            if (operand is not None and operand[1] not in paths and
                    (active is None or operand[0] != active[0]) and
                    re.fullmatch(r"fcntl\(" + re.escape(operand[0]) +
                                 r", F_GETFD\) = [^\r\n]+", projected)):
                continue
        if (call.startswith(("clone(", "clone3(", "fork(", "vfork(",
                             "dup(", "dup2(", "dup3(", "fcntl(", "write(",
                             "writev(", "pwrite", "rename(", "unlink(",
                             "truncate(", "ftruncate(", "close_range(",
                             "socket(", "sendto(", "sendmsg(")) or
                _protected_observer_operand(call, paths)):
            raise Rejected("version 6 observer protected action differs: " +
                           call.split("(", 1)[0])
    _require(next_role == 4 and active is None and set(observed) == set(ROLES),
             "version 6 observer file inventory differs")
    return {"status": "PROVED_V6_OUTPUT_OBSERVER", "identities": observed,
            "trace_sha256": hashlib.sha256(raw_zip).hexdigest()}


def _shared_threads(traces, root, events):
    plain = {int(pid): "\n".join(line.split(" ", 1)[1]
             for line in data.decode().splitlines()) + "\n"
             for pid, data in traces.items()}
    _require(int(root) in plain, "version 6 output process is missing")
    births = {}
    shared = jdi_bridge._worker_thread_ids(
        plain, int(root), shared=True, timed_events=events, births=births)
    for stamp, tid, _, call in events:
        owner = int(tid)
        while owner != int(root):
            parent = births.get(owner)
            _require(parent is not None and parent[1] <= stamp,
                     "version 6 output thread birth is unproved")
            owner, stamp = parent
    return {str(tid) for tid in shared}


def _write_payload(call):
    operation = "writev" if call.startswith("writev(") else "write"
    if not call.startswith(operation + "("):
        return None
    fd, end = _version6_fd_token(call, len(operation) + 1)
    decoration = call[len(operation) + 2 + len(fd):end - 1]
    match = re.fullmatch(r"(write|writev)\(([0-9]+), (.*)\) = ([0-9]+)",
                         _project_descriptors(call, version6_raw=True))
    if match is None:
        return None
    operation, parsed_fd, arguments, count = match.groups()
    _require(parsed_fd == fd, "version 6 output descriptor projection differs")
    payload, _ = _buffer(arguments, operation == "writev")
    _require(len(payload) == int(count), "version 6 output write is incomplete")
    return fd, decoration, payload


def _first_descriptor(call):
    opening = re.match(r"[a-z][a-z0-9_]*\(", call)
    if opening is None or re.match(r"[0-9]+<", call[opening.end():]) is None:
        return None
    fd, end = _version6_fd_token(call, opening.end())
    decoration = call[opening.end() + len(fd) + 1:end - 1]
    return fd, decoration


def _socket_output_operand(call, fd):
    name = call.split("(", 1)[0]
    position = ({"write": 0, "writev": 0, "pwrite64": 0,
                 "pwritev": 0, "sendto": 0, "sendmsg": 0,
                 "sendfile": 0, "copy_file_range": 2,
                 "splice": 2}.get(name))
    if position is None:
        return False
    projected = _project_descriptors(call, version6_raw=True)
    arguments = _arguments(projected)
    _require(position < len(arguments),
             "version 6 socket transfer arguments differ")
    return arguments[position] == fd


def prove_file_lifetime(traces, events, root, path, data, identity, role):
    _require(role in ROLES and type(data) is bytes and type(identity) is dict,
             "version 6 output role differs")
    shared = _shared_threads(traces, root, events)
    active = None
    opened = False
    closed = False
    initial = None
    final = None
    writes = []
    writers = set()
    last_write = -1
    last_stamp = None
    writer_fd = None
    for index, (stamp, tid, _, call) in enumerate(events):
        if (call.startswith(("rename(", "renameat(", "renameat2(",
                             "unlink(", "unlinkat(", "truncate(")) and
                ('"' + path + '"') in call):
            raise Rejected("version 6 output path changed")
        opening = _opening(call)
        if opening and quoted(opening[0]).decode("utf-8") == path:
            _require(tid in shared and not opened and not closed and
                     opening[3] == path and active is None,
                     "version 6 output provider differs")
            active = opening[2]
            writer_fd = active
            opened = True
            continue
        if active is None:
            if (call.startswith(("write(", "writev(", "close(", "fstat(")) and
                    (operand := _first_descriptor(call)) is not None and
                    operand[1] == path):
                raise Rejected("version 6 output used before open or after close")
            continue
        if (call.startswith(("clone(", "clone3(", "fork(", "vfork(")) and
                re.search(r"\) = [1-9][0-9]*$", call) and
                "CLONE_FILES" not in call):
            raise Rejected("version 6 output descriptor was copied")
        if (re.match(r"(?:dup|dup2|dup3|fcntl)\(" + re.escape(active) + r"(?=[<,)])", call) or
                re.match(r"(?:dup2|dup3)\([^,]+, " + re.escape(active) + r"(?=[<,)])", call) or
                call.startswith("close_range(") or
                "SCM_RIGHTS" in call or
                call.startswith(("rename(", "renameat(", "renameat2(",
                                 "unlink(", "unlinkat(", "truncate(")) and
                ('"' + path + '"') in call):
            raise Rejected("version 6 output descriptor lifetime differs")
        if tid not in shared:
            if ((operand := _first_descriptor(call)) is not None and
                    operand[1] == path):
                raise Rejected("version 6 output shared writer differs")
            continue
        if last_stamp == stamp and tid != previous_tid and (
                '<' + path + '>' in call or call.startswith("clone(")):
            raise Rejected("version 6 output equal-time order is ambiguous")
        if '<' + path + '>' in call:
            last_stamp, previous_tid = stamp, tid
        status = _STATUS.fullmatch(call)
        if status and (status[1], status[2]) == (active, path):
            observed = _identity(status[3])
            if not writes:
                _require(initial is None or observed == initial,
                         "version 6 output initial identity differs")
                initial = observed
            else:
                _require(final is None or observed == final[1],
                         "version 6 output final identity differs")
                final = (index, observed)
            continue
        transfer = (_write_payload(call) if call.startswith((
            "write(" + active + "<" + path + ">,",
            "writev(" + active + "<" + path + ">,")) else None)
        if transfer and transfer[:2] == (active, path):
            writes.append(transfer[2])
            writers.add(tid)
            last_write = index
            continue
        closing = _CLOSE.fullmatch(call)
        if closing and closing.groups() == (active, path):
            _require(writes and (role != "mirror" or
                     final is not None and final[0] > last_write),
                     "version 6 output original identity or close differs")
            active = None
            closed = True
            continue
        if (re.search(r"\) = " + re.escape(active) + r"<", call) or
                re.match(r"(?:close|shutdown|lseek|ftruncate|pwrite64|pwritev)\(" +
                         re.escape(active) + r"(?=[<,)])", call)):
            seek = re.fullmatch(r"lseek\(" + re.escape(active) + "<" +
                                re.escape(path) + r">, 0, SEEK_END\) = 0", call)
            initial_truncate = re.fullmatch(
                r"ftruncate\(" + re.escape(active) + "<" +
                re.escape(path) + r">, 0\) = 0", call)
            if not (role != "mirror" and not writes and
                    (seek is not None or initial_truncate is not None)):
                raise Rejected("version 6 output offset or descriptor changed")
    _require(opened and closed and active is None and b"".join(writes) == data and
             all(trace.rstrip().endswith(b"+++ exited with 0 +++")
                 for trace in traces.values()),
             "version 6 output bytes, close or producer exit differs")
    writer_identity = final[1] if role == "mirror" else initial
    _require(writer_identity is not None and
             writer_identity["device_major"] == identity["device_major"] and
             writer_identity["device_minor"] == identity["device_minor"] and
             writer_identity["inode"] == identity["inode"] and
             (role != "mirror" or writer_identity == identity) and
             identity["size"] == len(data),
             "version 6 output original object differs")
    _require(role != "mirror" or len(writers) == 1,
             "version 6 mirror writer is ambiguous")
    return {"role": role, "writer_fd": writer_fd,
            "writer_tid": next(iter(writers)) if len(writers) == 1 else None,
            "writer_threads": sorted(writers, key=int),
            "writer_identity": writer_identity, "write_count": len(writes),
            "sha256": hashlib.sha256(data).hexdigest()}


def prove_socket_writers(traces, events, root, mirror,
                         verified_class_reads=frozenset()):
    from actual_arithmetic import _WITNESS_PREFIXES

    _require(type(mirror) is tuple and len(mirror) == 2,
             "version 6 mirror writer selection differs")
    shared = _shared_threads(traces, root, events)
    marked = set()
    for _, tid, line_index, call in events:
        if not any(prefix.decode() in call for prefix in _WITNESS_PREFIXES):
            continue
        if (tid, line_index) in verified_class_reads:
            _require(call.startswith("read("),
                     "version 6 verified class input is not a read")
            continue
        _require(call.startswith("write("),
                 "version 6 marked socket write is incomplete")
        transfer = _write_payload(call)
        if transfer is None:
            raise Rejected("version 6 marked socket write is incomplete")
        fd, _, payload = transfer
        if any(prefix in payload for prefix in _WITNESS_PREFIXES):
            _require(call.startswith("write(") and tid in shared,
                     "version 6 marked socket writer differs")
            marked.add((tid, fd))
    _require(mirror in marked, "version 6 proved mirror writer is unmarked")
    sockets = marked - {mirror}
    _require(sockets, "version 6 non-mirror socket stream is missing")
    by_fd = {}
    for tid, fd in sockets:
        by_fd.setdefault(fd, set()).add(tid)
    proofs = []
    for fd, writers in by_fd.items():
        marked_indices = [index for index, (_, tid, _, call) in enumerate(events)
                          if (tid, fd) in sockets and call.startswith("write(") and
                          any(prefix.decode() in call for prefix in _WITNESS_PREFIXES)]
        providers = [index for index, (_, tid, _, call) in enumerate(events)
                     if index < min(marked_indices) and tid in shared and
                     (match := _SOCKET.fullmatch(call)) is not None and
                     match[1] == fd and match[2].startswith(("TCP:[", "TCPv6:["))]
        _require(providers, "version 6 socket provider differs")
        provider_index = providers[-1]
        active = None
        provider_count = 0
        connects = 0
        closed = False
        marked_on_object = set()
        all_writes = 0
        last_stamp = None
        last_tid = None
        for index, (stamp, tid, _, call) in enumerate(events):
            if index < provider_index:
                continue
            provider = _SOCKET.fullmatch(call)
            if provider and provider[1] == fd and tid in shared:
                _require(active is None and not closed and
                         provider[2].startswith(("TCP:[", "TCPv6:[")),
                         "version 6 socket provider differs")
                active = True
                provider_count += 1
                continue
            if active is None:
                if tid in shared and _socket_output_operand(call, fd):
                    raise Rejected("version 6 socket write preceded provider")
                continue
            if (call.startswith(("clone(", "clone3(", "fork(", "vfork(")) and
                    re.search(r"\) = [1-9][0-9]*$", call) and
                    "CLONE_FILES" not in call):
                raise Rejected("version 6 socket reference was copied")
            operand = r"\(" + re.escape(fd) + r"(?=[<,)])"
            if re.match(r"fcntl" + operand, call):
                projected = _project_descriptors(call, version6_raw=True)
                if (re.fullmatch(r"fcntl\(" + re.escape(fd) +
                        r", F_GETFL\) = [^\r\n]+", projected) or
                        re.fullmatch(r"fcntl\(" + re.escape(fd) +
                        r", F_SETFL, [A-Z_0-9|]+\) = 0", projected)):
                    continue
            if (re.match(r"(?:dup|dup2|dup3|fcntl)" + operand, call) or
                    re.match(r"(?:dup2|dup3)\([^,]+, " + re.escape(fd) +
                             r"(?=[<,)])", call) or
                    call.startswith("close_range(") or
                    "SCM_RIGHTS" in call or
                    re.match(r"(?:shutdown|unshare|setns)\(", call) and
                    call.endswith(" = 0")):
                raise Rejected("version 6 socket reference changed: " +
                               call.split("(", 1)[0] +
                               (":" + operation[1] if (operation := re.search(
                                   r", (F_[A-Z0-9_]+)", call)) else ""))
            if tid not in shared:
                if (_socket_output_operand(call, fd) or
                        re.match(r"(?:close|connect)" + operand, call)):
                    raise Rejected("version 6 socket writer table differs")
                continue
            if last_stamp == stamp and last_tid != tid and (
                    re.match(r"(?:write|close|connect)" + operand, call) or
                    re.match(r"(?:socket|dup|clone)\(", call)):
                raise Rejected("version 6 socket equal-time order is ambiguous")
            if re.match(r"(?:write|close|connect)" + operand, call):
                last_stamp, last_tid = stamp, tid
            connect = re.match(r"connect" + operand, call)
            if connect:
                _require(connects == 0 and (call.endswith(" = 0") or
                         "EINPROGRESS" in call),
                         "version 6 socket connect differs")
                connects += 1
                continue
            output = _socket_output_operand(call, fd)
            if output and not call.startswith("write("):
                raise Rejected("version 6 socket transfer is unsupported")
            transfer = _write_payload(call) if output else None
            if output and transfer is None:
                raise Rejected("version 6 socket write is incomplete")
            if transfer and transfer[0] == fd:
                _require((tid, fd) in sockets,
                         "version 6 socket writer is outside the proved stream")
                _require(connects == 1 and
                         transfer[1].startswith(("TCP:[", "TCPv6:[")),
                         "version 6 socket write lacked live connection")
                all_writes += 1
                if any(prefix in transfer[2] for prefix in _WITNESS_PREFIXES):
                    marked_on_object.add((tid, fd))
                continue
            closing = (call.startswith("close(") and
                       _project_descriptors(call, version6_raw=True) ==
                       "close(" + fd + ") = 0")
            if closing:
                _require(connects == 1 and all_writes and
                         marked_on_object == {(tid, fd) for tid in writers} and
                         ("<TCP:[" in call or "<TCPv6:[" in call),
                         "version 6 socket output or close differs")
                active = None
                closed = True
                continue
            if (re.search(r"\) = " + re.escape(fd) + r"<", call) or
                    re.match(r"(?:close|shutdown|sendmsg|recvmsg)" + operand, call)):
                raise Rejected("version 6 socket descriptor changed")
        _require(provider_count == 1 and connects == 1 and closed and
                 active is None and all_writes >= len(writers),
                 "version 6 socket lifetime is incomplete")
        proofs.append({"fd": fd, "writes": all_writes,
                       "writers": sorted(writers, key=int),
                       "scope": "local socket object; peer and protocol unproved"})
    _terminal_stamp(events)
    return frozenset(sockets), proofs
