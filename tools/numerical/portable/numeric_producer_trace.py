"""Replay bounded strace transport. Unsupported or ambiguous evidence stays unbound."""
import ast
import hashlib
import re
from decimal import Decimal
from itertools import groupby

from receipt import Rejected


class Unbound(Rejected):
    """Well formed evidence does not establish every execution premise."""


MAX_TRACE_BYTES = 128 * 1024 * 1024
MAX_THREADS = 1024
STRING = r'"(?:[^"\\]|\\.)*"'
FD = r'([0-9]+)<([^>]+)>'


def quoted(value):
    try:
        result = ast.literal_eval("b" + value)
    except (ValueError, SyntaxError) as error:
        raise Rejected("trace string is malformed") from error
    if type(result) is not bytes:
        raise Rejected("trace string type differs")
    return result


def _events(traces, protected):
    if not traces or len(traces) > MAX_THREADS or sum(map(len, traces.values())) > MAX_TRACE_BYTES:
        raise Rejected("trace budget or inventory differs")
    events = []
    for tid, data in traces.items():
        if re.fullmatch(r"[1-9][0-9]*", tid) is None:
            raise Rejected("trace thread identity differs")
        if not data.endswith(b"\n"):
            raise Unbound("trace final record is truncated")
        previous = Decimal(0)
        for index, line in enumerate(data.decode("utf-8").splitlines()):
            match = re.fullmatch(r"([0-9]+\.[0-9]+) (.*)", line)
            if match is None:
                raise Unbound("trace timestamp or complete syscall unavailable")
            stamp, call = match.groups()
            if "<unfinished ...>" in call or "resumed>" in call:
                raise Unbound("trace syscall ordering is ambiguous")
            if Decimal(stamp) < previous:
                raise Rejected("trace thread time moved backwards")
            previous = Decimal(stamp)
            events.append((previous, tid, index, call))
    events.sort()
    for _, bucket in groupby(events, key=lambda row: row[0]):
        rows = list(bucket)
        protected_rows = [row for row in rows if any(path in row[3] for path in protected if path)]
        descriptor_rows = [row for row in rows if row[3].startswith((
            "open", "close", "dup", "fcntl", "clone", "fork", "vfork", "execve"))]
        if protected_rows and len({row[1] for row in protected_rows + descriptor_rows}) > 1:
            raise Unbound("trace protected-descriptor ordering is ambiguous")
    return events


def _buffer(call, vector=False):
    if vector:
        match = re.fullmatch(r'\[([^]]*)\], ([0-9]+)(?:, ([0-9]+))?', call)
        if match is None:
            raise Unbound("trace vector buffer is incomplete")
        items = re.findall(r'\{iov_base=(' + STRING + r'), iov_len=([0-9]+)\}', match[1])
        if len(items) != int(match[2]):
            raise Unbound("trace vector buffer count differs")
        chunks = [quoted(value) for value, size in items]
        if any(len(value) != int(size) for value, (_, size) in zip(chunks, items)):
            raise Unbound("trace vector buffer is truncated")
        return b"".join(chunks), int(match[3]) if match[3] else None
    match = re.fullmatch(r'(' + STRING + r'), ([0-9]+)(?:, ([0-9]+))?', call)
    if match is None:
        raise Unbound("trace buffer is incomplete")
    value = quoted(match[1])
    return value, int(match[3]) if match[3] else None


def verify_transport(traces, destination, mirror, response_path=None, response=None, *,
                     exclusive=True, ordered=True):
    events = _events(traces, (destination, response_path))
    workers = []
    parents, groups, tables, exits = {}, {}, {}, {}
    outputs, writers, response_reads, identities = [], set(), [], set()
    opened = False
    worker = None
    worker_argv = None
    for _, tid, _, call in events:
        tables.setdefault(tid, {})
        groups.setdefault(tid, tid)
        if call.startswith(("execve(", "execveat(")) and call.endswith(" = 0"):
            if worker is not None and groups[tid] == worker:
                raise Rejected("worker executable changed after startup")
            if "GradleWorkerMain" in call:
                workers.append(tid)
                worker = tid
                worker_argv = call
                if response_path is not None and ('"@' + response_path + '"') not in call:
                    raise Rejected("worker response argument differs")
        child = re.match(r"(?:clone|clone3|fork|vfork)\(.*\) = ([1-9][0-9]*)$", call)
        if child:
            pid = child[1]
            if pid in parents or pid in tables or pid not in traces:
                raise Rejected("child trace is missing or PID reused")
            parents[pid] = tid
            groups[pid] = groups[tid] if "CLONE_THREAD" in call else pid
            tables[pid] = tables[tid] if "CLONE_FILES" in call else dict(tables[tid])
        if call.startswith("+++ exited with "):
            exits[tid] = int(call.split()[3])
        if "+++ killed by" in call:
            raise Rejected("traced process was killed")
        opening = re.fullmatch(r'open(?:at|at2)?\((.*?)\) = ' + FD, call)
        if opening:
            args, fd, path = opening.groups()
            if path in (destination, response_path):
                if '"' + path + '"' not in args:
                    raise Unbound("opened descriptor path is ambiguous")
                if path == destination:
                    if opened or worker is None or groups[tid] != worker:
                        raise Rejected("mirror is replaced or created outside worker")
                    if exclusive and not all(flag in args for flag in ("O_CREAT", "O_EXCL", "O_NOFOLLOW")):
                        raise Unbound("mirror exclusive creation unavailable")
                    opened = True
                tables[tid][fd] = {"path": path, "position": 0, "identity": None}
            else:
                tables[tid].pop(fd, None)
        duplicate = re.fullmatch(r'(?:dup|dup2|dup3|fcntl)\(' + FD + r'(.*?)\) = ' + FD, call)
        if duplicate:
            old, path, args, new, new_path = duplicate.groups()
            if call.startswith("fcntl(") and "F_DUPFD" not in args:
                continue
            if old in tables[tid]:
                if tables[tid][old]["path"] != path or new_path != path:
                    raise Rejected("duplicated descriptor destination differs")
                tables[tid][new] = tables[tid][old]
            else:
                tables[tid].pop(new, None)
        identity = re.fullmatch(r'(?:fstat|newfstatat|statx)\(' + FD + r', (.*)\) = 0', call)
        if identity and identity[1] in tables[tid]:
            descriptor = tables[tid][identity[1]]
            dev = re.search(r'st_dev=makedev\(([^)]+)\)', identity[3])
            ino = re.search(r'st_ino=([0-9]+)', identity[3])
            size = re.search(r'st_size=([0-9]+)', identity[3])
            if not dev or not ino or not size or "S_IFREG" not in identity[3]:
                raise Unbound("descriptor file identity unavailable")
            descriptor["identity"] = (dev[1], ino[1], int(size[1]))
        seek_descriptor = re.match(r'lseek\(([0-9]+)(?:<([^>]+)>)?,', call)
        if seek_descriptor and (seek_descriptor[2] == destination or
                tables[tid].get(seek_descriptor[1], {}).get("path") == destination):
            raise Rejected("mirror seek invalidates sequential output proof")
        seek = re.fullmatch(r'lseek\(' + FD + r', ([0-9]+), SEEK_SET\) = ([0-9]+)', call)
        if seek and seek[1] in tables[tid]:
            if seek[3] != seek[4]:
                raise Rejected("response seek differs")
            tables[tid][seek[1]]["position"] = int(seek[3])
        transfer = re.fullmatch(r'(read|pread64|readv|preadv|write|writev)\(' + FD + r', (.*)\) = ([0-9]+)', call)
        if transfer:
            operation, fd, path, args, count = transfer.groups()
            if path not in (destination, response_path):
                continue
            descriptor = tables[tid].get(fd)
            if descriptor is None or descriptor["path"] != path:
                raise Unbound("transfer descriptor creation unavailable")
            if path == response_path and operation.startswith("write") and worker is None:
                continue
            if worker is None or groups[tid] != worker:
                raise Rejected("transfer occurred outside selected worker")
            value, offset = _buffer(args, operation.endswith("v"))
            count = int(count)
            if len(value) != count:
                raise Unbound("partial or truncated transfer")
            if operation.startswith(("read", "pread")) and path == response_path:
                if descriptor["identity"] is None:
                    raise Unbound("response read file identity unavailable")
                identities.add(descriptor["identity"])
                position = offset if operation.startswith("pread") else descriptor["position"]
                if position is None:
                    raise Unbound("response read offset unavailable")
                response_reads.append((position, value))
                if not operation.startswith("pread"):
                    descriptor["position"] += count
            elif operation.startswith("write") and path == destination:
                writers.add((tid, fd))
                outputs.append(value)
            else:
                raise Rejected("unexpected transfer to protected file")
        closed = re.fullmatch(r'close\(' + FD + r'\) = 0', call)
        if closed:
            tables[tid].pop(closed[1], None)
        if call.startswith("close_range(") and any(tables[tid].values()):
            raise Unbound("protected descriptor close range is unsupported")
        if response_path and response_path in call and call.startswith(("unlink(", "unlinkat(")) and exits.get(worker) == 0:
            continue
        if any(name in call for name in (destination, response_path) if name) and any(
                call.startswith(name + "(") for name in
                ("rename", "renameat", "renameat2", "unlink", "unlinkat", "truncate", "ftruncate",
                 "mmap", "pwrite64", "pwritev", "sendfile", "copy_file_range", "splice")):
            raise Rejected("protected file replacement or unsupported access")
    if len(workers) != 1 or worker is None or exits.get(worker) != 0:
        raise Rejected("selected worker count or exit differs")
    if len(set(traces) - set(parents)) != 1:
        raise Rejected("trace has unrelated process roots")
    members = {tid for tid in groups if groups[tid] == worker}
    if any(exits.get(tid) != 0 for tid in members):
        raise Unbound("worker thread completion unavailable")
    if response_path is not None:
        if response is None or not response_reads:
            raise Unbound("response bytes were not read by worker")
        if len(identities) != 1 or next(iter(identities))[2] != len(response):
            raise Rejected("response read file identity differs")
        covered = set()
        for offset, value in response_reads:
            if response[offset:offset + len(value)] != value or offset + len(value) > len(response):
                raise Rejected("response read bytes differ")
            covered.update(range(offset, offset + len(value)))
        if covered != set(range(len(response))):
            raise Unbound("response read bytes are incomplete")
    if not opened or not writers or (ordered and len(writers) != 1):
        raise Unbound("mirror writer ordering is ambiguous")
    if (b"".join(outputs) != mirror if ordered else
            sorted(b"".join(outputs).splitlines()) != sorted(mirror.splitlines())):
        raise Rejected("mirror output bytes differ")
    chain, current = [], worker
    while current in parents:
        current = parents[current]
        chain.append(current)
    writer, fd = sorted(writers)[0]
    return {"worker_pid": worker, "parent_pids": chain,
            "worker_argv_sha256": hashlib.sha256(worker_argv.encode()).hexdigest(),
            "worker_exit": exits[worker], "mirror_writer_tid": writer, "mirror_fd": fd,
            "mirror_destination": destination, "mirror_sha256": hashlib.sha256(mirror).hexdigest()}
