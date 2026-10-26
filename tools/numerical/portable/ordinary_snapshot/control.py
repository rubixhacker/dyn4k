import array
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import time


MAX_PACKET = 65536
MAX_TIDS = 4096
PHASES = ("stage", "target", "helper", "observer")


class SnapshotIncomplete(ValueError):
    def __init__(self, phase, pid, reason, error=None):
        super().__init__("UNAVAILABLE")
        self.detail = {"phase": phase, "pid": pid, "reason": reason,
                       "errno": error.errno if isinstance(error, OSError) else None}


class SnapshotOwnedProcesses:
    def __init__(self, socket_dir, journal_dir, read_identity, pidfd_exited,
                 check_retained):
        self.socket_dir = Path(socket_dir)
        self.journal_dir = Path(journal_dir)
        self.read_identity = read_identity
        self.pidfd_exited = pidfd_exited
        self.check_retained = check_retained
        self.roots = {}
        self.servers = {}
        self.channels = {}
        self.closed = set()
        self.bound = {}
        self.threads = {}
        self.births = {}
        self.sequences = {}
        self.holds = {}
        self.snapshot_id = 0
        self.snapshot_info = None
        self.window_deadline = None

    def prepare(self, phase, environment):
        if phase not in PHASES or phase in self.servers:
            raise SnapshotIncomplete(phase, None, "PHASE_DUPLICATE")
        path = self.socket_dir / f"d4k-{os.getpid()}-{phase}.sock"
        if len(os.fsencode(path)) >= 108 or path.exists():
            raise SnapshotIncomplete(phase, None, "SOCKET_PATH")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        server.bind(str(path))
        path.chmod(0o600)
        server.listen(1)
        server.settimeout(5)
        self.servers[phase] = (server, path)
        return {**environment, "DYN4K_OWNED_SOCKET": str(path)}

    def _bind(self, phase, pid, ticks, parent, handle, creator_tgid=None):
        if pid in self.bound or handle is None:
            raise SnapshotIncomplete(phase, pid, "DUPLICATE_PID_OR_HANDLE")
        try:
            fdinfo = (Path("/proc/self/fdinfo") / str(handle)).read_text()
            field = [line.split(":", 1)[1].strip() for line in fdinfo.splitlines()
                     if line.startswith("Pid:")]
            if field != [str(pid)] or self.pidfd_exited(handle):
                raise SnapshotIncomplete(phase, pid, "PIDFD_IDENTITY")
            identity = self.read_identity(pid)
            if identity["start_ticks"] != ticks:
                raise SnapshotIncomplete(phase, pid, "PID_IDENTITY_CHANGED")
        except (OSError, ValueError, IndexError, KeyError) as error:
            if isinstance(error, SnapshotIncomplete):
                raise
            raise SnapshotIncomplete(phase, pid, "IDENTITY_READ_FAILED", error) from error
        self.bound[pid] = {"phase": phase, "parent": parent,
                           "identity": identity, "handle": handle,
                           "birth_start_ticks": ticks,
                           "creator_tgid": creator_tgid, "executed": False}

    def launch(self, phase, process, trace_prefix):
        if phase not in self.servers or phase in self.channels:
            raise SnapshotIncomplete(phase, process.pid, "LAUNCH_STATE")
        identity = self.read_identity(process.pid)
        handle = os.pidfd_open(process.pid)
        self._bind(phase, process.pid, identity["start_ticks"], None, handle)
        self.bound[process.pid]["executed"] = True
        self.roots[phase] = (process.pid, Path(trace_prefix))
        server, _ = self.servers[phase]
        try:
            channel, _ = server.accept()
            channel.setblocking(False)
            credentials = channel.getsockopt(socket.SOL_SOCKET,
                                               socket.SO_PEERCRED, 12)
            peer_pid, peer_uid, _ = struct.unpack("3i", credentials)
            if peer_pid != process.pid or peer_uid != os.getuid():
                raise SnapshotIncomplete(phase, process.pid, "SOCKET_PEER")
            self.channels[phase] = channel
            self.sequences[phase] = 0
            self.threads[phase] = {}
            self.births[phase] = {}
            deadline = time.monotonic() + 5
            while not self.threads[phase]:
                self._receive_wait(phase, deadline)
        except (OSError, TimeoutError) as error:
            raise SnapshotIncomplete(phase, process.pid, "SOCKET_ACCEPT", error) from error

    def _write(self, name, record):
        raw = (json.dumps(record, sort_keys=True, separators=(",", ":")) +
               "\n").encode("ascii")
        try:
            self.check_retained(raw, "jsonl")
            path = self.journal_dir / name
            with path.open("ab") as stream:
                if stream.write(raw) != len(raw):
                    raise OSError("snapshot journal write is incomplete")
                stream.flush()
                os.fsync(stream.fileno())
        except Exception as error:
            raise SnapshotIncomplete(record["phase"], None, "JOURNAL_WRITE",
                                     error) from error

    def _read_packet(self, phase):
        channel = self.channels[phase]
        try:
            packet, ancillary, flags, _ = channel.recvmsg(MAX_PACKET, 128)
        except BlockingIOError:
            return None
        if not packet:
            self.closed.add(phase)
            return None
        if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
            raise SnapshotIncomplete(phase, None, "EVENT_STREAM_CLOSED")
        try:
            value = packet.decode("ascii")
        except UnicodeError as error:
            raise SnapshotIncomplete(phase, None, "EVENT_ENCODING") from error
        if not value.endswith("\n") or len(value) > MAX_PACKET:
            raise SnapshotIncomplete(phase, None, "EVENT_LENGTH")
        handles = []
        for level, kind, data in ancillary:
            if (level != socket.SOL_SOCKET or kind != socket.SCM_RIGHTS or
                    len(data) != struct.calcsize("i")):
                raise SnapshotIncomplete(phase, None, "PIDFD_TRANSFER")
            handles.extend(array.array("i", data))
        if len(handles) > 1:
            for handle in handles:
                os.close(handle)
            raise SnapshotIncomplete(phase, None, "PIDFD_TRANSFER")
        return value.removesuffix("\n").split(" "), handles[0] if handles else None

    def _number(self, phase, text, *, positive=False):
        if not text.isascii() or not text.isdecimal() or len(text) > 20:
            raise SnapshotIncomplete(phase, None, "EVENT_NUMBER")
        value = int(text)
        if positive and value == 0:
            raise SnapshotIncomplete(phase, None, "EVENT_NUMBER")
        return value

    def _apply(self, phase, parts, handle):
        kind = parts[0]
        if kind == "ERROR":
            raise SnapshotIncomplete(phase, None, parts[1] if len(parts) == 2
                                     else "TRACER_ERROR")
        if len(parts) < 3 or kind not in {"ROOT", "BIRTH", "EXEC", "EXIT",
                                          "HELD", "RESUMED"}:
            raise SnapshotIncomplete(phase, None, "EVENT_KIND")
        sequence = self._number(phase, parts[1], positive=True)
        if sequence != self.sequences[phase] + 1:
            raise SnapshotIncomplete(phase, None, "EVENT_SEQUENCE")
        numbers = [self._number(phase, text) for text in parts[2:]
                   if ":" not in text]
        if kind == "ROOT":
            if len(parts) != 6 or self.threads[phase] or handle is None:
                raise SnapshotIncomplete(phase, None, "ROOT_RECORD")
            tid, tgid, ticks, rss = numbers
            if tid != tgid or not ticks:
                raise SnapshotIncomplete(phase, tid, "ROOT_IDENTITY")
            self._bind(phase, tid, ticks, self.roots[phase][0], handle,
                       self.roots[phase][0])
            self.threads[phase][tid] = {"tgid": tgid, "start_ticks": ticks,
                                         "creator_tid": None, "terminal": False}
        elif kind == "BIRTH":
            if len(parts) != 14:
                raise SnapshotIncomplete(phase, None, "BIRTH_RECORD")
            (ordinal, creator, creator_group, child, group, event, ticks, rss,
             ppid, boot_ns, stop_status, shared_vm) = numbers
            active = self.threads[phase]
            if (not ordinal or creator not in active or
                    active[creator]["tgid"] != creator_group or
                    child in active or child in self.births[phase] or
                    not ticks or not ppid or not boot_ns or not stop_status or
                    shared_vm not in {0, 1, 2} or event not in {1, 2, 3} or
                    (event == 1 and shared_vm != 0) or
                    (event == 2 and shared_vm != 1) or
                    (event == 3 and shared_vm != (1 if child != group else 2)) or
                    not os.WIFSTOPPED(stop_status) or
                    (child == group) != (handle is not None)):
                raise SnapshotIncomplete(phase, child, "BIRTH_IDENTITY")
            if ordinal != 1 + sum(row["creator_tid"] == creator for row in
                                  self.births[phase].values()):
                raise SnapshotIncomplete(phase, child, "BIRTH_ORDINAL")
            if group != child and group not in self.bound:
                raise SnapshotIncomplete(phase, child, "THREAD_GROUP")
            if handle is not None:
                self._bind(phase, child, ticks, creator, handle, creator_group)
                identity = self.bound[child]["identity"]
            else:
                identity = self.read_identity(child)
                if identity["start_ticks"] != ticks:
                    raise SnapshotIncomplete(phase, child, "THREAD_IDENTITY")
            if (identity["parent_pid"] != ppid or
                    abs(time.clock_gettime_ns(time.CLOCK_BOOTTIME) - boot_ns) >
                    2_000_000_000):
                raise SnapshotIncomplete(phase, child, "BIRTH_OBSERVATION")
            active[child] = {"tgid": group, "start_ticks": ticks,
                             "creator_tid": creator, "terminal": False}
            self.births[phase][child] = {**active[child], "ppid": ppid,
                "boot_ns": boot_ns, "stop_status": stop_status,
                "shared_vm": shared_vm, "creator_tgid": creator_group,
                "event": event, "ordinal": ordinal}
        elif kind == "EXEC":
            if len(parts) != 6 or handle is None:
                raise SnapshotIncomplete(phase, None, "EXEC_RECORD")
            current, former, group, ticks = numbers
            active = self.threads[phase]
            if (former not in active or group != current or not ticks or
                    current not in self.bound or
                    self.bound[current]["phase"] != phase):
                raise SnapshotIncomplete(phase, current, "EXEC_IDENTITY")
            fdinfo = (Path("/proc/self/fdinfo") / str(handle)).read_text()
            if (f"Pid:\t{current}\n" not in fdinfo or
                    self.pidfd_exited(handle)):
                raise SnapshotIncomplete(phase, current, "EXEC_PIDFD")
            identity = self.read_identity(current)
            if identity["start_ticks"] != ticks:
                raise SnapshotIncomplete(phase, current, "EXEC_START_TICKS")
            previous = self.bound[current]["handle"]
            self.bound[current]["handle"] = handle
            self.bound[current]["identity"] = identity
            os.close(previous)
            survivor = active.get(current, active[former])
            if former != current:
                for tid in tuple(active):
                    if active[tid]["tgid"] == group:
                        del active[tid]
            active[current] = survivor
            active[current]["start_ticks"] = ticks
            if current in self.bound:
                self.bound[current]["executed"] = True
        elif kind == "EXIT":
            if len(parts) != 5 or handle is not None:
                raise SnapshotIncomplete(phase, None, "EXIT_RECORD")
            tid, group, status = numbers
            active = self.threads[phase]
            if tid not in active or active[tid]["tgid"] != group:
                raise SnapshotIncomplete(phase, tid, "EXIT_IDENTITY")
            del active[tid]
        elif kind == "HELD":
            if (handle is not None or not self.holds.get(phase) or
                    len(parts) < 4 or numbers[0] != self.holds[phase]["id"]):
                raise SnapshotIncomplete(phase, None, "HELD_RECORD")
            roster = {}
            for text in parts[3:]:
                pair = text.split(":")
                if len(pair) != 2:
                    raise SnapshotIncomplete(phase, None, "HELD_MEMBER")
                tid, group = [self._number(phase, value, positive=True)
                              for value in pair]
                if tid in roster:
                    raise SnapshotIncomplete(phase, tid, "HELD_DUPLICATE")
                roster[tid] = group
            expected = {tid: row["tgid"] for tid, row in self.threads[phase].items()}
            if roster != expected:
                raise SnapshotIncomplete(phase, None, "HELD_MEMBERSHIP")
            self.holds[phase]["roster"] = roster
            self.holds[phase]["sequence"] = sequence
            self.holds[phase]["held"] = True
        else:
            if (len(parts) != 3 or handle is not None or
                    not self.holds.get(phase) or
                    numbers[0] != self.holds[phase]["id"]):
                raise SnapshotIncomplete(phase, None, "RESUMED_RECORD")
            self.holds[phase]["resumed"] = True
        self.sequences[phase] = sequence
        record = {"phase": phase, "sequence": sequence, "kind": kind,
                  "fields": parts[2:], "wall_ns": time.time_ns(),
                  "pidfd_pid": (numbers[0] if kind in {"ROOT", "EXEC"} else
                                numbers[3] if kind == "BIRTH" and handle is not None
                                else None)}
        self._write("snapshot-controls.jsonl" if kind in {"HELD", "RESUMED"}
                    else "ptrace-events.jsonl", record)
        try:
            self.channels[phase].sendall(f"ACK {sequence}\n".encode("ascii"))
        except OSError as error:
            raise SnapshotIncomplete(phase, None, "ACK_SEND", error) from error
        return kind

    def _receive(self, phase):
        value = self._read_packet(phase)
        if value is None:
            return None
        parts, handle = value
        try:
            return self._apply(phase, parts, handle)
        except Exception:
            if handle is not None and all(row["handle"] != handle
                                          for row in self.bound.values()):
                os.close(handle)
            raise

    def _receive_wait(self, phase, deadline):
        if phase in self.closed:
            raise SnapshotIncomplete(phase, None, "EVENT_STREAM_CLOSED")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SnapshotIncomplete(phase, None, "CONTROL_TIMEOUT")
        ready, _, _ = select.select([self.channels[phase]], [], [], remaining)
        if not ready:
            raise SnapshotIncomplete(phase, None, "CONTROL_TIMEOUT")
        result = self._receive(phase)
        if phase in self.closed:
            raise SnapshotIncomplete(phase, None, "EVENT_STREAM_CLOSED")
        return result

    def pump(self, phases=None):
        phases = (set(self.channels) if phases is None else set(phases)) - self.closed
        if not phases:
            return
        for _ in range(MAX_TIDS):
            phases -= self.closed
            if not phases:
                return
            ready, _, _ = select.select([self.channels[phase] for phase in phases],
                                        [], [], 0)
            if not ready:
                return
            for phase in phases:
                if self.channels[phase] in ready:
                    self._receive(phase)
        raise SnapshotIncomplete(None, None, "EVENT_DRAIN_LIMIT")

    def _command(self, phase, operation, snapshot_id):
        packet = f"{operation} {snapshot_id}\n".encode("ascii")
        try:
            if self.channels[phase].send(packet) != len(packet):
                raise SnapshotIncomplete(phase, None, "CONTROL_SEND")
        except OSError as error:
            raise SnapshotIncomplete(phase, None, "CONTROL_SEND", error) from error
        self._write("snapshot-controls.jsonl",
                    {"phase": phase, "operation": operation,
                     "snapshot_id": snapshot_id, "wall_ns": time.time_ns()})

    def _wait_all(self, phases, field, deadline):
        while not all(self.holds[phase].get(field) for phase in phases):
            if any(phase in self.closed for phase in phases):
                raise SnapshotIncomplete(None, None, "EVENT_STREAM_CLOSED")
            if time.monotonic() >= deadline:
                raise SnapshotIncomplete(None, None, "FREEZE_TIMEOUT")
            for phase in phases:
                if not self.holds[phase].get(field):
                    row = self.bound[self.roots[phase][0]]
                    if self.pidfd_exited(row["handle"]):
                        raise SnapshotIncomplete(phase, row["identity"]["pid"],
                                                 "TRACER_EXITED")
                    signal.pidfd_send_signal(row["handle"], signal.SIGUSR1)
            channels = [self.channels[phase] for phase in phases]
            ready, _, _ = select.select(channels, [], [], 0.01)
            for phase in phases:
                if self.channels[phase] in ready:
                    self._receive(phase)

    def freeze(self, phase):
        phases = ("stage",) if phase == "stage" else (
            "observer",) if phase == "observer" else ("target", "helper")
        phases = tuple(item for item in phases if item in self.channels)
        if not phases:
            raise SnapshotIncomplete(phase, None, "FREEZE_PHASE")
        self.window_deadline = time.monotonic() + 5
        self.pump(phases)
        self.snapshot_id += 1
        for item in phases:
            self.holds[item] = {"id": self.snapshot_id, "held": False,
                                "resumed": False}
            self._command(item, "FREEZE", self.snapshot_id)
        self._wait_all(phases, "held", self.window_deadline)
        groups = {group for item in phases
                  for group in self.holds[item]["roster"].values()}
        groups.update(self.roots[item][0] for item in phases)
        self.snapshot_info = {"snapshot_id": self.snapshot_id,
                              "held_sequences": {item: self.holds[item]["sequence"]
                                                 for item in phases},
                              "live_tgids": sorted(groups),
                              "phases": phases}
        return self.snapshot_info

    def resume(self):
        if self.snapshot_info is None:
            return
        phases = self.snapshot_info["phases"]
        for phase in phases:
            self._command(phase, "RESUME", self.snapshot_id)
        self._wait_all(phases, "resumed", self.window_deadline)
        self.snapshot_info = None
        self.window_deadline = None

    def refresh(self, phases):
        if self.snapshot_info is None:
            raise SnapshotIncomplete(None, None, "SAMPLE_WITHOUT_HOLD")
        selected = set(self.snapshot_info["live_tgids"])
        for pid in selected:
            row = self.bound.get(pid)
            if row is None or row["phase"] not in phases:
                raise SnapshotIncomplete(None, pid, "SAMPLE_MEMBERSHIP")
            if self.pidfd_exited(row["handle"]):
                raise SnapshotIncomplete(row["phase"], pid, "SAMPLE_EXITED")
            current = self.read_identity(pid)
            if current["start_ticks"] != row["identity"]["start_ticks"]:
                raise SnapshotIncomplete(row["phase"], pid, "PID_IDENTITY_CHANGED")
        return selected

    def validate_sample(self, pids):
        if self.snapshot_info is None or set(pids) != set(self.snapshot_info["live_tgids"]):
            raise SnapshotIncomplete(None, None, "SAMPLE_MEMBERSHIP")
        for pid in pids:
            row = self.bound[pid]
            if self.pidfd_exited(row["handle"]):
                raise SnapshotIncomplete(row["phase"], pid, "SAMPLE_EXITED")
            try:
                current = self.read_identity(pid)
            except (OSError, ValueError, IndexError) as error:
                raise SnapshotIncomplete(row["phase"], pid,
                                         "IDENTITY_READ_FAILED", error) from error
            if current["start_ticks"] != row["identity"]["start_ticks"]:
                raise SnapshotIncomplete(row["phase"], pid, "PID_IDENTITY_CHANGED")

    def evidence(self):
        return {phase: {str(pid): {"start_ticks": row["identity"]["start_ticks"],
                                   "birth_start_ticks": row["birth_start_ticks"],
                                   "parent_pid": row["parent"],
                                   "kernel_ppid": row["identity"]["parent_pid"],
                                   "creator_tgid": row["creator_tgid"]}
                        for pid, row in self.bound.items() if row["phase"] == phase}
                for phase in self.roots}

    def stop(self, phases=None, sample=None):
        phases = set(self.roots) if phases is None else set(phases)
        failure = None
        if sample is not None:
            try:
                sample()
            except Exception as error:
                failure = error
        for signum in (signal.SIGTERM, signal.SIGKILL):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    self.pump(phases)
                except SnapshotIncomplete as error:
                    failure = failure or error
                live = [(pid, row) for pid, row in self.bound.items()
                        if row["phase"] in phases and
                        not self.pidfd_exited(row["handle"])]
                if not live:
                    if any(self.threads.get(phase) for phase in phases):
                        missing = SnapshotIncomplete(None, None,
                                                     "TERMINAL_RECORD_MISSING")
                        if failure:
                            missing.detail["prior_failure"] = (
                                failure.detail if isinstance(failure, SnapshotIncomplete)
                                else type(failure).__name__)
                        raise missing
                    if failure:
                        raise failure
                    return
                for pid, row in reversed(live):
                    try:
                        current = self.read_identity(pid)
                        changed = (current["start_ticks"] !=
                                   row["identity"]["start_ticks"])
                    except (OSError, ValueError, IndexError, KeyError) as error:
                        failure = failure or SnapshotIncomplete(
                            row["phase"], pid, "CLEANUP_IDENTITY", error)
                        changed = False
                    if changed:
                        failure = failure or SnapshotIncomplete(
                            row["phase"], pid, "PID_IDENTITY_CHANGED")
                    try:
                        signal.pidfd_send_signal(row["handle"], signum)
                    except ProcessLookupError:
                        pass
                    except OSError as error:
                        failure = failure or SnapshotIncomplete(
                            row["phase"], pid, "CLEANUP_SIGNAL", error)
                time.sleep(0.01)
        survivor = SnapshotIncomplete(None, None, "CLEANUP_SURVIVOR")
        if failure:
            survivor.detail["prior_failure"] = (
                failure.detail if isinstance(failure, SnapshotIncomplete)
                else type(failure).__name__)
        raise survivor

    def close(self):
        for row in self.bound.values():
            os.close(row["handle"])
        for channel in self.channels.values():
            channel.close()
        for server, path in self.servers.values():
            server.close()
            path.unlink(missing_ok=True)
