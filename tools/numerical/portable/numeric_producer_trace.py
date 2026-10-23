"""Replay bounded strace transport. Unsupported or ambiguous evidence stays unbound."""
import ast
import hashlib
import re
from decimal import Decimal
from itertools import groupby

from receipt import Rejected


class Unbound(Rejected):
    """Well formed evidence does not establish every execution premise."""


MAX_TRACE_BYTES = 2 * 1024 * 1024 * 1024
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
        try:
            lines = data.decode("utf-8").splitlines()
        except UnicodeDecodeError as error:
            raise Rejected("trace record is not UTF-8") from error
        previous = Decimal(0)
        for index, line in enumerate(lines):
            match = re.fullmatch(r"([0-9]+\.[0-9]+) (.+)", line)
            if match is None:
                raise Rejected("trace timestamp or syscall record is malformed")
            stamp, call = match.groups()
            if "<unfinished ...>" in call or "resumed>" in call:
                raise Unbound("trace syscall ordering is ambiguous")
            if Decimal(stamp) < previous:
                raise Rejected("trace thread time moved backwards")
            previous = Decimal(stamp)
            events.append((previous, tid, index, call))
        if not data.endswith(b"\n"):
            raise Unbound("trace final record is truncated")
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


def verify_stable_input(traces, path, expected_identity, worker, jar):
    events = _events(traces, (path,))
    groups = {}
    descriptors = {}
    path_identity = False
    worker_started = False
    worker_finished = False
    opened = []
    for _, tid, _, call in events:
        groups.setdefault(tid, tid)
        descriptors.setdefault(tid, {})
        if tid == worker and call.startswith(("execve(", "execveat(")) and call.endswith(" = 0"):
            worker_started = True
        if tid == worker and call.startswith(("+++ exited with ", "+++ killed by ")):
            worker_finished = True
        if worker_finished and groups[tid] == worker and path in call:
            raise Rejected("agent input access followed worker exit")
        child = re.match(r"(?:clone|clone3|fork|vfork)\(.*\) = ([1-9][0-9]*)$", call)
        if child:
            groups[child[1]] = groups[tid] if "CLONE_THREAD" in call else child[1]
            descriptors[child[1]] = (descriptors[tid] if "CLONE_FILES" in call
                                     else dict(descriptors[tid]))
        opening = re.fullmatch(r'open(?:at|at2)?\((.*?)\) = ' + FD, call)
        if opening:
            args, fd, opened_path = opening.groups()
            descriptors[tid].pop(fd, None)
            if opened_path == path:
                if (('"' + path + '"') not in args or groups[tid] != worker or
                        not worker_started or worker_finished or "O_RDONLY" not in args or
                        any(flag in args for flag in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC"))):
                    raise Rejected("agent input provider or open mode differs")
                item = {"verified": False, "position": 0, "reads": 0, "maps": 0,
                        "pending_maps": []}
                descriptors[tid][fd] = item
                opened.append(item)
        duplicate = re.fullmatch(r'(?:dup|dup2|dup3|fcntl)\(' + FD + r'(.*?)\) = ' + FD, call)
        if duplicate:
            old, old_path, args, new, new_path = duplicate.groups()
            if not call.startswith("fcntl(") or "F_DUPFD" in args:
                if old in descriptors[tid]:
                    if old_path != path or new_path != path:
                        raise Rejected("agent input alias path differs")
                    descriptors[tid][new] = descriptors[tid][old]
                else:
                    descriptors[tid].pop(new, None)
        if path not in call:
            continue
        statx_path = re.fullmatch(r'statx\(AT_FDCWD(?:<[^>]+>)?, "' +
                                  re.escape(path) + r'", .*\) = 0', call)
        if statx_path:
            major = re.search(r'stx_dev_major=([0-9]+)', call)
            minor = re.search(r'stx_dev_minor=([0-9]+)', call)
            inode = re.search(r'stx_ino=([0-9]+)', call)
            size = re.search(r'stx_size=([0-9]+)', call)
            if (groups[tid] != worker or not worker_started or worker_finished or
                    not all((major, minor, inode, size)) or
                    "stx_mode=S_IFREG" not in call):
                raise Unbound("agent input path identity unavailable")
            actual = {"device_major": int(major[1]), "device_minor": int(minor[1]),
                      "inode": int(inode[1]), "size": int(size[1])}
            if actual != expected_identity:
                raise Rejected("agent input path identity differs")
            path_identity = True
        writer = re.match(r'(?:write|writev|pwrite64|pwritev|ftruncate)\(' + FD, call)
        mapped_writer = re.match(r'mmap\(.*' + FD + r', [0-9]+\) = ', call)
        if (call.startswith(("rename", "unlink", "truncate", "sendfile",
                             "copy_file_range", "splice")) or
                (writer is not None and writer[2] == path) or
                (mapped_writer is not None and mapped_writer[2] == path and
                 "PROT_WRITE" in call and "MAP_SHARED" in call)):
            raise Rejected("agent input was changed or mapped writable")
        identity = re.fullmatch(r'(?:fstat|newfstatat|statx)\(' + FD + r', (.*)\) = 0', call)
        if identity and identity[1] in descriptors[tid]:
            device = re.search(r'st_dev=makedev\(([^)]+)\)', identity[3])
            inode = re.search(r'st_ino=([0-9]+)', identity[3])
            size = re.search(r'st_size=([0-9]+)', identity[3])
            if not device or not inode or not size or "S_IFREG" not in identity[3]:
                raise Unbound("agent input descriptor identity unavailable")
            parts = [item.strip() for item in device[1].split(",")]
            if len(parts) != 2 or any(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", item) is None
                                     for item in parts):
                raise Unbound("agent input device identity unavailable")
            major, minor = (int(item, 16 if item.startswith("0x") else 10) for item in parts)
            actual = {"device_major": major, "device_minor": minor,
                      "inode": int(inode[1]), "size": int(size[1])}
            if actual != expected_identity:
                raise Rejected("agent input file identity differs")
            descriptors[tid][identity[1]]["verified"] = True
        seeking = re.match(r'lseek\(' + FD + r',', call)
        if seeking and seeking[2] == path:
            if seeking[1] not in descriptors[tid]:
                raise Unbound("agent input seek descriptor is unavailable")
            seek = re.fullmatch(r'lseek\(' + FD +
                                r', (-?[0-9]+), SEEK_(SET|CUR|END)\) = (-?[0-9]+)', call)
            if seek is None:
                if not re.search(r'\) = -[0-9]+(?: |$)', call):
                    raise Unbound("agent input seek mode or offset is unsupported")
            elif int(seek[5]) >= 0:
                current = descriptors[tid][seek[1]]["position"]
                requested = int(seek[3])
                expected = (requested if seek[4] == "SET" else
                            current + requested if seek[4] == "CUR" else
                            len(jar) + requested)
                if int(seek[5]) != expected:
                    raise Rejected("agent input seek result differs")
                descriptors[tid][seek[1]]["position"] = expected
        transfer = re.match(r'(read|pread64|readv|preadv)\(' + FD + r',', call)
        if transfer and transfer[3] == path:
            operation, fd, observed_path = transfer.groups()
            item = descriptors[tid].get(fd)
            if item is None or observed_path != path:
                raise Unbound("agent input read descriptor is unavailable")
            if groups[tid] != worker or not worker_started:
                continue
            result = re.search(r'\) = (-?[0-9]+)(?: |$)', call)
            if result is None:
                raise Unbound("agent input read result is unavailable")
            count = int(result[1])
            if count > 0:
                complete = re.fullmatch(r'(?:read|pread64|readv|preadv)\(' + FD +
                                        r', (.*)\) = ([0-9]+)', call)
                if complete is None:
                    raise Unbound("agent input returned bytes are unavailable")
                value, offset = _buffer(complete[3], operation.endswith("v"))
                if len(value) != count:
                    raise Unbound("agent input returned byte count differs")
                position = offset if operation.startswith("pread") else item["position"]
                if position is None or position < 0 or jar[position:position + count] != value:
                    raise Rejected("agent input returned bytes or offset differ")
                item["reads"] += 1
                if not operation.startswith("pread"):
                    item["position"] += count
        mapped = re.match(r'mmap\(.*' + FD + r',', call)
        if mapped and mapped[2] == path:
            item = descriptors[tid].get(mapped[1])
            if item is None or mapped[2] != path:
                raise Unbound("agent input mapping descriptor is unavailable")
            if groups[tid] != worker or not worker_started:
                continue
            if re.search(r'\) = -[0-9]+(?: |$)', call):
                continue
            mapping = re.fullmatch(r'mmap\([^,]+, ([0-9]+), (PROT_[A-Z|]+), '
                                   r'(MAP_[A-Z_|]+), ' + FD + r', (0x[0-9a-f]+|[0-9]+)\) = 0x[0-9a-f]+',
                                   call)
            if mapping is None:
                raise Unbound("agent input mapping proof is unsupported")
            length, protection, flags, offset = mapping[1], mapping[2], mapping[3], mapping[6]
            start = int(offset, 0)
            if (protection != "PROT_READ" or flags != "MAP_SHARED" or
                    int(length) <= 0 or start < 0 or start + int(length) > len(jar)):
                raise Rejected("agent input mapping mode or bounds differ")
            item["pending_maps"].append((start, int(length)))
        closed = re.fullmatch(r'close\(' + FD + r'\) = 0', call)
        if closed:
            descriptors[tid].pop(closed[1], None)
        if call.startswith("close_range(") and descriptors[tid]:
            raise Unbound("agent input close range is unsupported")
    if len(jar) != expected_identity["size"]:
        raise Rejected("agent input rebuilt JAR size differs")
    if not worker_started or not worker_finished:
        raise Unbound("agent input worker execution or completion is unavailable")
    for item in opened:
        if item["reads"] or item["pending_maps"]:
            if not (item["verified"] or path_identity):
                raise Unbound("agent input open identity is unavailable")
            if item["pending_maps"] and not item["reads"]:
                raise Unbound("agent input mapping lacks checked read bytes")
            item["maps"] = len(item["pending_maps"])
    read_buffers = sum(item["reads"] for item in opened)
    read_only_maps = sum(item["maps"] for item in opened)
    if not read_buffers:
        raise Unbound("agent input read and stable identity unavailable")
    return {"reads": read_buffers, "read_buffers": read_buffers,
            "read_only_maps": read_only_maps, "identity": expected_identity,
            "identity_mode": "descriptor" if all(item["verified"] for item in opened
                                                  if item["reads"] or item["maps"]) else "path"}


def verify_transport(traces, destination, mirror, response_path=None, response=None, *,
                     exclusive=True, ordered=True, mirror_identity=None,
                     shared_writers=False):
    events = _events(traces, (destination, response_path))
    workers = []
    parents, groups, tables, exits = {}, {}, {}, {}
    outputs, writers, response_reads, identities = [], set(), [], set()
    opened = False
    final_mirror_identity = None
    final_mirror_stat_index = -1
    last_mirror_write_index = -1
    worker = None
    worker_argv = None
    for event_index, (_, tid, _, call) in enumerate(events):
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
                    if exclusive and not all(flag in args for flag in ("O_CREAT", "O_EXCL")):
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
            if descriptor["path"] == destination:
                final_mirror_identity = descriptor["identity"]
                final_mirror_stat_index = event_index
        seek_descriptor = re.match(r'lseek\(([0-9]+)(?:<([^>]+)>)?,', call)
        if seek_descriptor and (seek_descriptor[2] == destination or
                tables[tid].get(seek_descriptor[1], {}).get("path") == destination):
            initial_log_seek = (not exclusive and not ordered and not outputs and
                tables[tid].get(seek_descriptor[1], {}).get("path") == destination and
                re.fullmatch(r'lseek\(' + FD + r', 0, SEEK_END\) = 0', call) is not None)
            if not initial_log_seek:
                raise Rejected("mirror seek invalidates sequential output proof")
        if response_path is not None and call.startswith("lseek(") and seek_descriptor and (
                seek_descriptor[2] == response_path or
                tables[tid].get(seek_descriptor[1], {}).get("path") == response_path):
            seek = re.fullmatch(r'lseek\(' + FD + r', ([0-9]+), SEEK_SET\) = ([0-9]+)', call)
            if seek is None:
                raise Unbound("response seek mode or offset is unsupported")
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
                last_mirror_write_index = event_index
            else:
                raise Rejected("unexpected transfer to protected file")
        closed = re.fullmatch(r'close\(' + FD + r'\) = 0', call)
        if closed:
            tables[tid].pop(closed[1], None)
        if call.startswith("close_range(") and any(tables[tid].values()):
            raise Unbound("protected descriptor close range is unsupported")
        if response_path and response_path in call and call.startswith(("unlink(", "unlinkat(")) and exits.get(worker) == 0:
            continue
        initial_log_truncate = (not exclusive and not ordered and not outputs and
            (match := re.fullmatch(r'ftruncate\(' + FD + r', 0\) = 0', call)) is not None and
            match[2] == destination and
            tables[tid].get(match[1], {}).get("path") == destination)
        if not initial_log_truncate and any(name in call for name in (destination, response_path) if name) and any(
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
    if not opened or not writers or (ordered and len(writers) != 1 and
                                     (not shared_writers or len({fd for _, fd in writers}) != 1)):
        raise Unbound("mirror writer ordering is ambiguous")
    if (b"".join(outputs) != mirror if ordered else
            sorted(b"".join(outputs).splitlines()) != sorted(mirror.splitlines())):
        raise Rejected("mirror output bytes differ")
    if mirror_identity is not None:
        if final_mirror_identity is None or final_mirror_stat_index <= last_mirror_write_index:
            raise Unbound("mirror file identity unavailable after final write")
        dev, inode, size = final_mirror_identity
        parts = [part.strip() for part in dev.split(",")]
        if len(parts) != 2 or any(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", part) is None
                                   for part in parts):
            raise Unbound("mirror device identity is malformed")
        major, minor = (int(part, 16 if part.startswith("0x") else 10) for part in parts)
        observed = {"device_major": major, "device_minor": minor,
                    "inode": int(inode), "size": size}
        if observed != mirror_identity or size != len(mirror):
            raise Rejected("mirror file identity differs")
    chain, current = [], worker
    while current in parents:
        current = parents[current]
        chain.append(current)
    writer, fd = sorted(writers)[0]
    result = {"worker_pid": worker, "parent_pids": chain,
              "worker_argv_sha256": hashlib.sha256(worker_argv.encode()).hexdigest(),
              "worker_exit": exits[worker], "mirror_writer_tid": writer, "mirror_fd": fd,
              "mirror_destination": destination, "mirror_sha256": hashlib.sha256(mirror).hexdigest()}
    if shared_writers:
        result["writer_tids"] = sorted({tid for tid, _ in writers})
    return result
