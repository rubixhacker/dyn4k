import io
import hashlib
from decimal import Decimal
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import jdi_bridge
from actual_trace import checked_projection
from jdi_bridge import (EvidenceRejected, compile_helper, parse_call_sites, verify_body_map,
                        verify_jdi_archive, verify_jdi_file_writes, verify_loader_bridge,
                        verify_jdi_transport, verify_jdi_transport_v6)
from witness import read_probe_events


BODY = """
  private static final kotlin.Unit integratePosition$lambda$0(org.dyn4j.dynamics.AbstractPhysicsBody, double);
    Code:
       2: invokevirtual #461 // Method rotateAboutCenter:(D)V
    LineNumberTable:
      line 264: 0
"""
JOINT = """
  public boolean solvePositionConstraints(org.dyn4j.dynamics.TimeStep, org.dyn4j.dynamics.Settings);
    Code:
     247: invokeinterface #453, 3 // InterfaceMethod org/dyn4j/dynamics/PhysicsBody.rotateAboutCenter:(D)V
     261: invokeinterface #453, 3 // InterfaceMethod org/dyn4j/dynamics/PhysicsBody.rotateAboutCenter:(D)V
     550: invokeinterface #453, 3 // InterfaceMethod org/dyn4j/dynamics/PhysicsBody.rotateAboutCenter:(D)V
     588: invokeinterface #453, 3 // InterfaceMethod org/dyn4j/dynamics/PhysicsBody.rotateAboutCenter:(D)V
    LineNumberTable:
      line 250: 237
      line 251: 252
      line 267: 535
      line 269: 574
"""


def archive(rows):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as output:
        for name, payload in rows.items():
            output.writestr(name, payload)
    return data.getvalue()


TEST_HOME = str(Path.home() / "boolean-jdi-test")
HELPER_ARGS = ["/tmp/dyn4k-tools/jdk21/bin/java", "--add-modules", "jdk.jdi",
               f"-Djava.io.tmpdir={TEST_HOME}/tmp", "-cp", f"{TEST_HOME}/helper-classes",
               "RotationJdiProbe", "attach", f"{TEST_HOME}/jdi", "127.0.0.1",
               "40001", "org.dyn4j.geometry.Transform", "1800", "600"]
WORKER_EXEC = (b'execve("/tmp/dyn4k-tools/jdk21/bin/java", '
               b'["java", "GradleWorkerMain"], 0x7f) = 0\n')
THREAD_CLONE = (b'clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|'
                b'CLONE_SIGHAND|CLONE_THREAD, exit_signal=0}, 88) = 124\n')
SOCKET_BIND = (b'bind(9, {sa_family=AF_INET, sin_port=htons(40001), '
               b'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n')
SOCKET_LISTEN = b'listen(9, 1) = 0\n'
HELPER_SOCKET_TRACE = (
    'execve("/tmp/dyn4k-tools/jdk21/bin/java", '
    + str(HELPER_ARGS).replace("'", '"') + ', 0x7f /* 1 var */) = 0\n'
    'connect(7, {sa_family=AF_INET, sin_port=htons(40001), '
    'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n').encode()


class JdiBridgeTest(unittest.TestCase):
    def test_version6_fork_parent_binds_daemon_and_thread_ancestry(self):
        events = [
            (Decimal("1.0"), "10", 0, 'execve("/project/gradlew", ["gradlew"], 0x1) = 0'),
            (Decimal("1.1"), "10", 1, 'clone(0) = 11'),
            (Decimal("1.2"), "11", 0, 'execve("/tmp/dyn4k-tools/jdk21/bin/java", '
             '["java", "-Djdk.lang.Process.launchMechanism=FORK", '
             '"org.gradle.launcher.daemon.bootstrap.GradleDaemon"], 0x1) = 0'),
            (Decimal("1.3"), "11", 1, 'clone(CLONE_THREAD|CLONE_FILES) = 12'),
            (Decimal("1.4"), "12", 0, 'clone(0) = 13'),
            (Decimal("1.4"), "13", 0, 'execve("/tmp/dyn4k-tools/jdk21/bin/java", '
             '["java", "worker.org.gradle.process.internal.worker.GradleWorkerMain"], '
             '0x1) = 0'),
        ]
        self.assertEqual(jdi_bridge.verify_gradle_fork_parent_v6(events, 13, 10), 11)
        for label, altered in (
                ("missing option", [(s, t, i, c.replace(
                    "-Djdk.lang.Process.launchMechanism=FORK", "-Dother=FORK"))
                    for s, t, i, c in events]),
                ("wrong parent", [(s, t, i, c.replace("GradleDaemon", "OtherMain"))
                    for s, t, i, c in events]),
                ("child before birth", events[:-1] + [(Decimal("1.399999"), *events[-1][1:])]),
                ("disconnected", events[:4] + [(events[4][0], "12", 0, "clone(0) = 14"),
                    events[5]]),
                ("intermediate image", events[:4] + [
                    (Decimal("1.35"), "12", 0,
                     'execve("/other", ["other"], 0x1) = 0'),
                    (Decimal("1.4"), "12", 1, 'clone(0) = 13'), events[5]])):
            with self.subTest(label=label), self.assertRaises(jdi_bridge.EvidenceRejected):
                jdi_bridge.verify_gradle_fork_parent_v6(altered, 13, 10)

    def test_version6_raw_transport_requires_live_accept_peer_and_exchange(self):
        worker = (
            b'1.000001 execve("/tmp/dyn4k-tools/jdk21/bin/java", '
            b'["java", "worker.org.gradle.process.internal.worker.GradleWorkerMain"], '
            b'0x7f) = 0\n'
            b'1.0000011 socket(AF_INET, SOCK_STREAM, IPPROTO_TCP) = 9<TCP:[90]>\n'
            b'1.000002 bind(9<TCP:[90]>, {sa_family=AF_INET, '
            b'sin_port=htons(40001), sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n'
            b'1.000003 listen(9<TCP:[127.0.0.1:40001]>, 1) = 0\n'
            b'1.000005 accept(9<TCP:[127.0.0.1:40001]>, '
            b'{sa_family=AF_INET, sin_port=htons(41000), '
            b'sin_addr=inet_addr("127.0.0.1")}, [128 => 16]) '
            b'= 10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>\n'
            b'1.000008 recvfrom(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>, '
            b'"JDWP-Handshake", 14, 0, NULL, NULL) = 14\n'
            b'1.000009 sendto(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>, '
            b'"JDWP-Handshake", 14, 0, NULL, 0) = 14\n'
            b'1.000012 recvfrom(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>, '
            b'"request", 7, 0, NULL, NULL) = 7\n'
            b'1.000013 sendto(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>, '
            b'"response", 8, 0, NULL, 0) = 8\n')
        helper = (
            b'1.000004 execve("/tmp/dyn4k-tools/jdk21/bin/java", ' +
            str(HELPER_ARGS).replace("'", '"').encode() + b', 0x7f) = 0\n'
            b'1.000006 socket(AF_INET, SOCK_STREAM, IPPROTO_IP) = 7<TCP:[91]>\n'
            b'1.000007 connect(7<TCP:[91]>, {sa_family=AF_INET, '
            b'sin_port=htons(40001), sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n'
            b'1.0000071 getsockname(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>, '
            b'{sa_family=AF_INET, sin_port=htons(41000), '
            b'sin_addr=inet_addr("127.0.0.1")}, [128 => 16]) = 0\n'
            b'1.0000072 write(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>, '
            b'"JDWP-Handshake", 14) = 14\n'
            b'1.000010 read(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>, '
            b'"JDWP-Handshake", 14) = 14\n'
            b'1.000011 write(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>, '
            b'"request", 7) = 7\n'
            b'1.000014 read(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>, '
            b'"response", 8) = 8\n')
        result = verify_jdi_transport_v6(archive({"trace.123": worker}),
                                          archive({"trace.456": helper}),
                                          40001, 123, 456, HELPER_ARGS)
        self.assertEqual(result["status"], "PROVED_JDI_RAW_EXCHANGE")
        launcher = (
            b'0.999999 execve("/tmp/dyn4k-tools/jdk21/lib/jspawnhelper", '
            b'["/tmp/dyn4k-tools/jdk21/lib/jspawnhelper", '
            b'"21.0.12.1+1-LTS", "540:541:543"], 0x7f) = 0\n')
        launcher_bytes = b"bounded pinned launcher source test"
        launcher_sha = hashlib.sha256(launcher_bytes).hexdigest()
        def check_launcher(*args, **kwargs):
            with patch.object(Path, "read_bytes", return_value=launcher_bytes), \
                    patch.object(jdi_bridge, "JSPAWNHELPER_SHA256", launcher_sha):
                return verify_jdi_transport_v6(*args, **kwargs)
        launched = launcher + worker
        self.assertEqual(check_launcher(
            archive({"trace.123": launched}), archive({"trace.456": helper}),
            40001, 123, 456, HELPER_ARGS, launcher_sha256=launcher_sha,
            protected_paths={"/home/stewart/boolean-jdi-test/agent.jar"})["status"],
            "PROVED_JDI_RAW_EXCHANGE")
        self.assertEqual(check_launcher(
            archive({"trace.123": launcher.replace(b"0.999999", b"1.000001") + worker}),
            archive({"trace.456": helper}), 40001, 123, 456, HELPER_ARGS,
            launcher_sha256=launcher_sha,
            protected_paths={"/home/stewart/boolean-jdi-test/agent.jar"})["status"],
            "PROVED_JDI_RAW_EXCHANGE")
        prelude_bad = (
            ("unknown launcher", launcher.replace(b"/lib/jspawnhelper",
                                                    b"/lib/other")),
            ("wrong launcher arguments", launcher.replace(
                b"540:541:543", b"540:541")),
            ("changed launcher bytes", launcher),
            ("extra execution", launcher + launcher.replace(
                b"0.999999", b"1.000000")),
            ("prelude socket", launcher +
             b'1.000000 socket(AF_INET, SOCK_STREAM, IPPROTO_TCP) = 7<TCP:[99]>\n'),
            ("prelude protected file", launcher +
             b'1.000000 read(7</home/stewart/boolean-jdi-test/agent.jar>, '
             b'"abc", 3) = 3\n'),
            ("prelude protected open", launcher +
             b'1.000000 openat(AT_FDCWD, '
             b'"/home/stewart/boolean-jdi-test/agent.jar", O_RDONLY) = 7\n'),
            ("prelude child", launcher +
             b'1.000000 clone3({flags=CLONE_FILES, exit_signal=0}, 88) = 900\n'),
        )
        for label, prelude in prelude_bad:
            with self.subTest(launcher=label):
                with self.assertRaises(EvidenceRejected):
                    check_launcher(
                        archive({"trace.123": prelude + worker}),
                        archive({"trace.456": helper}), 40001, 123, 456,
                        HELPER_ARGS,
                        launcher_sha256=("0" * 64 if label == "changed launcher bytes"
                                         else launcher_sha),
                        protected_paths={"/home/stewart/boolean-jdi-test/agent.jar"})
        with self.assertRaises(EvidenceRejected):
            check_launcher(
                archive({"trace.123": worker + launcher.replace(
                    b"0.999999", b"1.000015")}),
                archive({"trace.456": helper}), 40001, 123, 456,
                HELPER_ARGS, launcher_sha256=launcher_sha)
        with self.assertRaises(EvidenceRejected):
            check_launcher(
                archive({"trace.123": worker}),
                archive({"trace.456": helper + launcher.replace(
                    b"0.999999", b"1.000015")}),
                40001, 123, 456, HELPER_ARGS,
                launcher_sha256=launcher_sha)
        worker_packet = next(row for row in worker.splitlines(keepends=True)
                             if row.startswith(b'1.000012 recvfrom'))
        helper_packet = next(row for row in helper.splitlines(keepends=True)
                             if row.startswith(b'1.000014 read'))
        shared_clones = (b'1.000010 clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|'
                         b'CLONE_SIGHAND|CLONE_THREAD, exit_signal=0}, 88) = 124\n'
                         b'1.0000101 clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|'
                         b'CLONE_SIGHAND|CLONE_THREAD, exit_signal=0}, 88) = 125\n')
        worker_multi = worker.replace(worker_packet, b'').replace(
            b'1.000013 sendto', shared_clones + b'1.000013 sendto')
        helper_multi = helper.replace(helper_packet, b'').replace(
            b'1.000011 write',
            b'1.0000105 clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|'
            b'CLONE_SIGHAND|CLONE_THREAD, exit_signal=0}, 88) = 457\n'
            b'1.000011 write')
        worker_members = {
            "trace.123": worker_multi,
            "trace.124": worker_packet,
            "trace.125": next(row for row in worker.splitlines(keepends=True)
                              if row.startswith(b'1.000013 sendto')).replace(
                                  b'1.000013', b'1.0000125', 1),
        }
        helper_members = {"trace.456": helper_multi,
                          "trace.457": helper_packet}
        multi = verify_jdi_transport_v6(archive(worker_members),
                                        archive(helper_members),
                                        40001, 123, 456, HELPER_ARGS)
        self.assertEqual(multi["worker_packets"], {"send": 2, "receive": 1})
        self.assertEqual(multi["helper_packets"], {"send": 1, "receive": 1})
        first_clone = shared_clones.splitlines(keepends=True)[0]
        late_worker = worker_multi.replace(first_clone, b'').replace(
            b'1.000013 sendto',
            first_clone.replace(b'1.000010', b'1.0000128', 1) +
            b'1.000013 sendto')
        late_helper_clone = next(row for row in helper_multi.splitlines(keepends=True)
                                 if b'clone3(' in row)
        late_helper = (helper_multi.replace(late_helper_clone, b'') +
                       late_helper_clone.replace(b'1.0000105', b'1.000015', 1))
        nested_clone = (b'1.000011 clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|'
                        b'CLONE_SIGHAND|CLONE_THREAD, exit_signal=0}, 88) = 126\n')
        nested_workers = {**worker_members, "trace.124": nested_clone,
                          "trace.126": worker_packet}
        for label, workers, helpers in (
                ("worker packet precedes creation",
                 {**worker_members, "trace.123": late_worker}, helper_members),
                ("helper packet precedes creation", worker_members,
                 {**helper_members, "trace.456": late_helper}),
                ("packet precedes intermediate parent clone",
                 {**nested_workers, "trace.124": nested_clone.replace(
                     b'1.000011', b'1.0000128', 1)}, helper_members)):
            with self.subTest(birth=label):
                with self.assertRaises(EvidenceRejected):
                    verify_jdi_transport_v6(archive(workers), archive(helpers),
                                            40001, 123, 456, HELPER_ARGS)
        self.assertEqual(verify_jdi_transport_v6(
            archive(nested_workers), archive(helper_members),
            40001, 123, 456, HELPER_ARGS)["status"],
            "PROVED_JDI_RAW_EXCHANGE")
        during_clone = {**worker_members, "trace.124": worker_packet.replace(
            b'1.000012', b'1.00001005', 1)}
        self.assertEqual(verify_jdi_transport_v6(
            archive(during_clone), archive(helper_members),
            40001, 123, 456, HELPER_ARGS)["status"],
            "PROVED_JDI_RAW_EXCHANGE")
        tied_clone = worker_multi.replace(
            b'1.000010 clone3',
            b'1.0000095 fstat(1</dev/null>, {st_mode=S_IFCHR}) = 0\n'
            b'1.000010 clone3').replace(b') = 124\n', b') = 122\n')
        tied_workers = {"trace.123": tied_clone,
                        "trace.122": worker_packet.replace(
                            b'1.000012', b'1.000010', 1),
                        "trace.125": worker_members["trace.125"]}
        self.assertEqual(verify_jdi_transport_v6(
            archive(tied_workers), archive(helper_members),
            40001, 123, 456, HELPER_ARGS)["status"],
            "PROVED_JDI_RAW_EXCHANGE")

        early_clones = shared_clones.replace(b'1.0000101', b'1.0000072').replace(
            b'1.000010 clone3', b'1.0000071 clone3')
        split_parent = worker.replace(worker_packet, b'').replace(
            b'1.000008 recvfrom', early_clones + b'1.000008 recvfrom')
        packet_call = worker_packet.split(b' ', 1)[1].rstrip(b'\n')
        packet_start, packet_result = packet_call.rsplit(b') = ', 1)
        split_packet = (b'1.000011 ' + packet_start + b' <unfinished ...>\n'
                        b'1.000014 <... recvfrom resumed>) = ' +
                        packet_result + b'\n')
        split_workers = {
            "trace.123": split_parent,
            "trace.124": split_packet,
            "trace.125": worker_members["trace.125"].replace(
                b'1.0000125', b'1.0000145', 1),
        }
        split_clone = (b'1.000010 clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|'
                       b'CLONE_SIGHAND|CLONE_THREAD, exit_signal=0}, 88 '
                       b'<unfinished ...>\n'
                       b'1.000011 <... clone3 resumed>) = 124\n')
        split_clone_parent = worker.replace(worker_packet, b'').replace(
            b'1.000013 sendto', split_clone + b'1.000013 sendto')
        split_socket = worker.replace(
            b'1.0000011 socket(AF_INET, SOCK_STREAM, IPPROTO_TCP) = 9<TCP:[90]>\n',
            b'1.0000011 socket(AF_INET, SOCK_STREAM, IPPROTO_TCP '
            b'<unfinished ...>\n'
            b'1.0000015 <... socket resumed>) = 9<TCP:[90]>\n')
        split_close_parent = worker.replace(
            b'1.000008 recvfrom', first_clone.replace(
                b'1.000010', b'1.0000071', 1) + b'1.000008 recvfrom')
        split_close_child = (
            b'1.0000115 close(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]> '
            b'<unfinished ...>\n'
            b'1.000014 <... close resumed>) = 0\n')
        for label, workers in (
                ("packet entry precedes phase witness", split_workers),
                ("completed split clone has mixed time",
                 {"trace.123": split_clone_parent, "trace.124": worker_packet}),
                ("completed split socket provider has mixed time",
                 {"trace.123": split_socket}),
                ("completed split close has mixed lifetime time",
                 {"trace.123": split_close_parent,
                  "trace.124": split_close_child})):
            with self.subTest(split=label):
                with self.assertRaises(EvidenceRejected):
                    verify_jdi_transport_v6(archive(workers),
                                            archive({"trace.456": helper}),
                                            40001, 123, 456, HELPER_ARGS)
        helper_call = helper_packet.split(b' ', 1)[1].rstrip(b'\n')
        helper_start, helper_result = helper_call.rsplit(b') = ', 1)
        split_helper_packet = (
            b'1.0000105 ' + helper_start + b' <unfinished ...>\n'
            b'1.000015 <... read resumed>) = ' + helper_result + b'\n')
        split_helper_parent = helper.replace(helper_packet, b'').replace(
            b'1.0000072 write',
            b'1.00000715 clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|'
            b'CLONE_SIGHAND|CLONE_THREAD, exit_signal=0}, 88) = 457\n'
            b'1.0000072 write')
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport_v6(archive({"trace.123": worker}),
                                    archive({"trace.456": split_helper_parent,
                                             "trace.457": split_helper_packet}),
                                    40001, 123, 456, HELPER_ARGS)
        no_phase_helper = helper.replace(
            b'1.000011 write(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>, '
            b'"request", 7) = 7\n', b'').replace(helper_packet, b'').replace(
            b'1.0000072 write',
            b'1.00000715 clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|'
            b'CLONE_SIGHAND|CLONE_THREAD, exit_signal=0}, 88) = 457\n'
            b'1.00000716 clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|'
            b'CLONE_SIGHAND|CLONE_THREAD, exit_signal=0}, 88) = 458\n'
            b'1.0000072 write')
        no_phase_members = {
            "trace.456": no_phase_helper,
            "trace.457": helper_packet,
            "trace.458": next(row for row in helper.splitlines(keepends=True)
                              if row.startswith(b'1.000011 write')),
        }
        for label, workers, helpers in (
                ("cross-thread phase tie",
                 {**worker_members, "trace.124": worker_packet.replace(
                     b'1.000012', b'1.000010', 1)}, helper_members),
                ("no helper completion witness", worker_members,
                 no_phase_members),
                ("shared child closes socket",
                 {**worker_members, "trace.124":
                  b'1.0000115 close(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>) = 0\n'
                  + worker_packet}, helper_members),
                ("copied descriptor table",
                 {**worker_members, "trace.123": worker_multi.replace(
                     b'CLONE_FILES|', b'', 1)}, helper_members)):
            with self.subTest(multithread=label):
                with self.assertRaises(EvidenceRejected):
                    verify_jdi_transport_v6(archive(workers), archive(helpers),
                                            40001, 123, 456, HELPER_ARGS)

        valid_schedules = (
            ("blocking receives",
             worker.replace(b'1.000008 recvfrom', b'1.00000715 recvfrom'),
             helper.replace(b'1.000010 read', b'1.0000085 read')),
            ("equal per-thread timestamps",
             worker.replace(b'1.000002 bind', b'1.000003 bind').replace(
                b'1.000009 sendto', b'1.000008 sendto').replace(
                b'1.000012 recvfrom', b'1.000008 recvfrom'),
             helper.replace(b'1.000010 read', b'1.0000072 read').replace(
                b'1.000011 write', b'1.0000072 write')),
            ("connect enters before accept",
             worker.replace(b'1.000005 accept', b'1.0000075 accept'), helper),
        )
        for label, changed_worker, changed_helper in valid_schedules:
            with self.subTest(schedule=label):
                self.assertEqual(verify_jdi_transport_v6(
                    archive({"trace.123": changed_worker}),
                    archive({"trace.456": changed_helper}),
                    40001, 123, 456, HELPER_ARGS)["status"],
                    "PROVED_JDI_RAW_EXCHANGE")

        def reverse_calls(trace, first_stamp, second_stamp):
            rows = trace.splitlines(keepends=True)
            first = next(index for index, row in enumerate(rows)
                         if row.startswith(first_stamp + b' '))
            second = next(index for index, row in enumerate(rows)
                          if row.startswith(second_stamp + b' '))
            rows[first], rows[second] = (
                rows[second].replace(second_stamp, first_stamp, 1),
                rows[first].replace(first_stamp, second_stamp, 1))
            return b''.join(rows)

        for label, changed_worker, changed_helper in (
                ("worker listener order",
                 reverse_calls(worker, b'1.000002', b'1.000003'), helper),
                ("worker accept before listen on one thread",
                 reverse_calls(worker, b'1.000003', b'1.000005'), helper),
                ("worker handshake order",
                 reverse_calls(worker, b'1.000008', b'1.000009'), helper),
                ("helper handshake order",
                 worker, reverse_calls(helper, b'1.0000072', b'1.000010'))):
            with self.subTest(order=label):
                with self.assertRaises(EvidenceRejected):
                    verify_jdi_transport_v6(archive({"trace.123": changed_worker}),
                                             archive({"trace.456": changed_helper}),
                                             40001, 123, 456, HELPER_ARGS)
        for changed_worker, changed_helper in (
                (worker.replace(b'1.000005 accept',
                                b'1.0000031 close(9<TCP:[127.0.0.1:40001]>) = 0\n'
                                b'1.000005 accept'), helper),
                (worker.replace(b'accept(9', b'noaccept(9'), helper),
                (worker.replace(b'41000', b'41001'), helper),
                (worker.replace(b'JDWP-Handshake', b'JDWP-Xandshake'), helper),
                (worker, helper.replace(b'1.0000072 write', b'1.0000072 nowrite')),
                (worker, helper.replace(b'1.000011 write', b'1.000011 nowrite')),
                (worker, helper.replace(b'41000', b'41002')),
                (worker.replace(b'1.000012 recvfrom',
                                b'1.0000115 close(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>) = 0\n'
                                b'1.000012 recvfrom'), helper),
                (worker.replace(b'1.000012 recvfrom',
                                b'1.0000115 close_range(10, 10, 0) = 0\n'
                                b'1.000012 recvfrom'), helper),
                (worker, helper.replace(b'1.000011 write',
                    b'1.0000105 close(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>) = 0\n'
                    b'1.000011 write')),
                (worker, helper.replace(b'1.000011 write',
                    b'1.0000105 dup2(8</home/other>, 7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>) = 7</home/other>\n'
                    b'1.000011 write')),
                (worker.replace(b'1.000012 recvfrom',
                    b'1.0000115 fcntl(8</home/other>, F_DUPFD, 10) = 10</home/other>\n'
                    b'1.000012 recvfrom'), helper),
                (worker.replace(b'1.000012 recvfrom',
                    b'1.0000115 openat(AT_FDCWD, "/home/other", O_RDONLY) = 10</home/other>\n'
                    b'1.000012 recvfrom'), helper)):
            with self.subTest(worker=changed_worker, helper=changed_helper):
                with self.assertRaises(EvidenceRejected):
                    verify_jdi_transport_v6(archive({"trace.123": changed_worker}),
                                             archive({"trace.456": changed_helper}),
                                             40001, 123, 456, HELPER_ARGS)

        shared = worker.replace(
            b'1.000012 recvfrom',
            b'1.0000105 clone3({flags=CLONE_VM|CLONE_FILES, exit_signal=0}, 88) = 124\n'
            b'1.000012 recvfrom')
        child = (b'1.000011 close(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>) = 0\n'
                 b'1.000015 +++ exited with 0 +++\n')
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport_v6(archive({"trace.123": shared,
                                             "trace.124": child}),
                                    archive({"trace.456": helper}),
                                    40001, 123, 456, HELPER_ARGS)

        worker_token = b'TCP:[127.0.0.1:40001->127.0.0.1:41000]'
        helper_token = b'TCP:[127.0.0.1:41000->127.0.0.1:40001]'
        for side, original, marker, fd, token, child_id, clone_time, action_time in (
                ("worker", worker, b'1.000012 recvfrom', b'10', worker_token,
                 b'124', b'1.0000105', b'1.000011'),
                ("helper", helper, b'1.000011 write', b'7', helper_token,
                 b'457', b'1.0000105', b'1.0000107')):
            for shared_flag, operation in (
                    (b'SIGCHLD', b'shutdown(' + fd + b'<' + token +
                     b'>, SHUT_RDWR) = 0'),
                    (b'CLONE_FILES|SIGCHLD', b'shutdown(' + fd + b'<' + token +
                     b'>, SHUT_RDWR) = 0'),
                    (b'SIGCHLD', b'close(' + fd + b'<' + token +
                     b'>) = 0')):
                parent = original.replace(
                    marker, clone_time + b' clone(child_stack=NULL, flags=' +
                    shared_flag + b') = ' + child_id + b'\n' + marker)
                child = (action_time + b' ' + operation + b'\n'
                         b'1.000015 +++ exited with 0 +++\n')
                members = {"trace." + ("123" if side == "worker" else "456"): parent,
                           "trace." + child_id.decode(): child}
                changed = archive(members)
                workers = changed if side == "worker" else archive({"trace.123": worker})
                helpers = changed if side == "helper" else archive({"trace.456": helper})
                checked_projection(workers, set())
                checked_projection(helpers, set())
                with self.subTest(side=side, flags=shared_flag, operation=operation):
                    with self.assertRaises(EvidenceRejected):
                        verify_jdi_transport_v6(workers, helpers, 40001,
                                                123, 456, HELPER_ARGS)

            for alias in (
                    b'dup(' + fd + b'<' + token + b'>) = 100<' + token + b'>',
                    b'dup2(' + fd + b'<' + token + b'>, 100) = 100<' + token + b'>',
                    b'dup3(' + fd + b'<' + token + b'>, 100, 0) = 100<' + token + b'>',
                    b'fcntl(' + fd + b'<' + token + b'>, F_DUPFD, 100) = 100<' +
                    token + b'>',
                    b'fcntl(' + fd + b'<' + token + b'>, F_DUPFD_CLOEXEC, 100) = 100<' +
                    token + b'>'):
                changed = original.replace(
                    marker, clone_time + b' ' + alias + b'\n' +
                    action_time + b' shutdown(100<' + token +
                    b'>, SHUT_RDWR) = 0\n' + marker)
                workers = archive({"trace.123": changed if side == "worker" else worker})
                helpers = archive({"trace.456": changed if side == "helper" else helper})
                checked_projection(workers, set())
                checked_projection(helpers, set())
                with self.subTest(side=side, alias=alias), self.assertRaises(EvidenceRejected):
                    verify_jdi_transport_v6(workers, helpers, 40001,
                                            123, 456, HELPER_ARGS)

            alias_only = original.replace(
                marker, clone_time + b' dup3(' + fd + b'<' + token +
                b'>, 100, 0) = 100<' + token + b'>\n' + marker)
            workers = archive({"trace.123": alias_only if side == "worker" else worker})
            helpers = archive({"trace.456": alias_only if side == "helper" else helper})
            checked_projection(workers, set())
            checked_projection(helpers, set())
            with self.subTest(side=side, transition="alias without shutdown"):
                with self.assertRaises(EvidenceRejected):
                    verify_jdi_transport_v6(workers, helpers, 40001,
                                            123, 456, HELPER_ARGS)

            for source in (fd, fd + b'<' + token + b'>'):
                for operation in (
                        b'dup(' + source + b') = 100<' + token + b'>',
                        b'dup2(' + source + b', 100) = 100<' + token + b'>',
                        b'dup3(' + source + b', 100, 0) = 100<' + token + b'>',
                        b'fcntl(' + source + b', F_DUPFD, 100) = 100<' + token + b'>',
                        b'fcntl(' + source + b', F_DUPFD_CLOEXEC, 100) = 100<' + token + b'>',
                        b'shutdown(' + source + b', SHUT_RDWR) = 0',
                        b'close(' + source + b') = 0'):
                    changed = original.replace(
                        marker, action_time + b' ' + operation + b'\n' + marker)
                    workers = archive({"trace.123": changed if side == "worker" else worker})
                    helpers = archive({"trace.456": changed if side == "helper" else helper})
                    checked_projection(workers, set())
                    checked_projection(helpers, set())
                    with self.subTest(side=side, operation=operation):
                        with self.assertRaises(EvidenceRejected):
                            verify_jdi_transport_v6(workers, helpers, 40001,
                                                    123, 456, HELPER_ARGS)

            other_fd = fd + b'0'
            for operation in (
                    b'dup(' + other_fd + b'</home/other>) = 200</home/other>',
                    b'close(' + other_fd + b'</home/other>) = 0'):
                changed = original.replace(
                    marker, action_time + b' ' + operation + b'\n' + marker)
                workers = archive({"trace.123": changed if side == "worker" else worker})
                helpers = archive({"trace.456": changed if side == "helper" else helper})
                checked_projection(workers, set())
                checked_projection(helpers, set())
                with self.subTest(side=side, other_operation=operation):
                    self.assertEqual(verify_jdi_transport_v6(
                        workers, helpers, 40001, 123, 456, HELPER_ARGS)[
                        "status"], "PROVED_JDI_RAW_EXCHANGE")

            copied_at_last_packet = original.replace(
                b'1.000013 sendto' if side == "worker" else b'1.000014 read',
                (b'1.000013' if side == "worker" else b'1.000014') +
                b' clone(child_stack=NULL, flags=SIGCHLD) = ' + child_id + b'\n' +
                (b'1.000013 sendto' if side == "worker" else b'1.000014 read'))
            members = {"trace." + ("123" if side == "worker" else "456"):
                       copied_at_last_packet,
                       "trace." + child_id.decode():
                       b'1.000015 +++ exited with 0 +++\n'}
            workers = archive(members) if side == "worker" else archive({"trace.123": worker})
            helpers = archive(members) if side == "helper" else archive({"trace.456": helper})
            checked_projection(workers, set())
            checked_projection(helpers, set())
            with self.subTest(side=side, transition="copy tied to last packet"):
                with self.assertRaises(EvidenceRejected):
                    verify_jdi_transport_v6(workers, helpers, 40001,
                                            123, 456, HELPER_ARGS)

            changed = original.replace(
                marker, clone_time + b' close_range(100, 200, CLOSE_RANGE_UNSHARE) = 0\n' +
                marker)
            workers = archive({"trace.123": changed if side == "worker" else worker})
            helpers = archive({"trace.456": changed if side == "helper" else helper})
            checked_projection(workers, set())
            checked_projection(helpers, set())
            with self.subTest(side=side, transition="unshare outside selected fd"):
                with self.assertRaises(EvidenceRejected):
                    verify_jdi_transport_v6(workers, helpers, 40001,
                                            123, 456, HELPER_ARGS)

    def test_loader_bridge_joins_jvm_ids_and_observer_label_separately(self):
        raw = (b"transform\t41\nobserved\t41\nagent\t7\n"
               b"label\tL2\nordinal\t17\nprovider_count\t1\n")
        focus = {"name": "org/dyn4j/geometry/Transform", "loader": "L2",
                 "ordinal": 17}
        self.assertEqual(verify_loader_bridge(raw, 41, 7, focus)["loader_object_id"], 41)
        for broken in (raw.replace(b"observed\t41", b"observed\t42"),
                       raw.replace(b"label\tL2", b"label\tL1"),
                       raw.replace(b"ordinal\t17", b"ordinal\t18"),
                       raw.replace(b"provider_count\t1", b"provider_count\t2"),
                       raw + b"label\tL2\n"):
            with self.subTest(raw=broken), self.assertRaises(EvidenceRejected):
                verify_loader_bridge(broken, 41, 7, focus)

    def test_compile_helper_rejects_missing_javac_for_default_and_override(self):
        selected_jdks = (
            (None, Path("/default/jdk")),
            ("/ci/jdk", Path("/ci/jdk")),
        )
        with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
            temporary_root = Path(temporary)
            for configured_jdk, expected_jdk in selected_jdks:
                with self.subTest(configured_jdk=configured_jdk):
                    with patch.dict(os.environ):
                        os.environ.pop("DYN4K_JDI_JDK_HOME", None)
                        if configured_jdk is not None:
                            os.environ["DYN4K_JDI_JDK_HOME"] = configured_jdk
                        with patch.object(jdi_bridge, "JDK21", Path("/default/jdk")):
                            command = (str(expected_jdk / "bin/javac"), "-version")
                            with patch("jdi_bridge.subprocess.run",
                                       side_effect=FileNotFoundError("javac missing")) as run:
                                with self.assertRaises(EvidenceRejected):
                                    compile_helper(b"public class Probe {}",
                                                   temporary_root)
                            self.assertEqual(run.call_args.args[0], command)

    def test_compile_helper_rejects_unpinned_javac_versions(self):
        invalid_versions = (
            ("", "", 0),
            ("", "javac 21.0.12", 1),
            ("javac twenty-one", "", 0),
            ("javac 25.0.1", "", 0),
        )
        selected_jdks = (
            (None, Path("/default/jdk")),
            ("/ci/jdk", Path("/ci/jdk")),
        )
        with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
            temporary_root = Path(temporary)
            for configured_jdk, expected_jdk in selected_jdks:
                for stdout, stderr, returncode in invalid_versions:
                    with self.subTest(configured_jdk=configured_jdk,
                                      stdout=stdout, stderr=stderr,
                                      returncode=returncode):
                        with patch.dict(os.environ):
                            os.environ.pop("DYN4K_JDI_JDK_HOME", None)
                            if configured_jdk is not None:
                                os.environ["DYN4K_JDI_JDK_HOME"] = configured_jdk
                            with patch.object(jdi_bridge, "JDK21", Path("/default/jdk")):
                                command = (str(expected_jdk / "bin/javac"), "-version")
                                result = subprocess.CompletedProcess(
                                    command, returncode, stdout, stderr)
                                with patch("jdi_bridge.subprocess.run",
                                           return_value=result) as run:
                                    with self.assertRaises(EvidenceRejected):
                                        compile_helper(b"public class Probe {}",
                                                       temporary_root)
                                self.assertEqual(run.call_args.args[0], command)

    def test_aligned_strace_results_allow_closed_fd_reuse(self):
        output = Path(TEST_HOME) / "jdi"
        raw = archive({"first.txt": b"one\n", "second.txt": b"two\n"})
        trace = (
            f'openat(AT_FDCWD, "{output}/first.txt", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 7\n'
            'write(7, "one\\n", 4)                   = 4\n'
            'close(7)                                = 0\n'
            f'openat(AT_FDCWD, "{output}/second.txt", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 7\n'
            'write(7, "two\\n", 4)                   = 4\n'
            'close(7)                                = 0\n').encode()
        result = verify_jdi_file_writes(archive({"trace.456": trace}), raw, output)
        self.assertEqual(result["files"], 2)
        for changed in (trace.replace(b"close(7)                                = 0",
                                      b"close(7)                                = -1", 1),
                        trace.replace(b"write(7, \"two\\n\", 4)                   = 4",
                                      b"write(7, \"two\\n\", 4)                   = 3", 1)):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_file_writes(archive({"trace.456": changed}), raw, output)

    def test_output_bytes_require_complete_kernel_file_writes(self):
        output = Path(TEST_HOME) / "jdi"
        raw = archive({"events.tsv": b"one\ntwo\n", "complete.txt": b"vm-death\n"})
        trace = (
            f'openat(AT_FDCWD, "{output}/events.tsv", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 8\n'
            'write(8, "one\\ntwo\\n", 8) = 8\nclose(8) = 0\n'
            f'openat(AT_FDCWD, "{output}/complete.txt", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 8\n'
            'write(8, "vm-death\\n", 9) = 9\nclose(8) = 0\n').encode()
        helper = archive({"trace.456": trace})
        result = verify_jdi_file_writes(helper, raw, output)
        self.assertEqual(result["status"], "MATCHED_JDI_FILE_WRITES_UNPASSED_LOADER")
        for changed in (
                archive({"events.tsv": b"one\nTWO\n", "complete.txt": b"vm-death\n"}),
                archive({"events.tsv": b"one\ntwo\n"}),
                archive({"events.tsv": b"one\ntwo\n", "complete.txt": b"vm-death\n",
                         "forged.txt": b"forged"})):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_file_writes(helper, changed, output)
        for altered in (trace.replace(b"write(8,", b"write(9,", 1),
                        trace.replace(b") = 8", b") = 7", 1),
                        trace.replace(b"close(8) = 0", b"close(8) = -1", 1),
                        trace.replace(b"events.tsv", b"forged.tsv", 1)):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_file_writes(archive({"trace.456": altered}), raw, output)

    def test_body_map_is_independent_of_marker_token(self):
        mapping = b"b0\t10\nb1\t11\nintegrated\t11\n"
        calls = [{"receiver": 11}, {"receiver": 10}, {"receiver": 11}]
        self.assertEqual(verify_body_map(mapping, calls)["status"],
                         "MATCHED_BODY_RECEIVERS_UNPASSED_LOADER")
        for altered in (mapping.replace(b"integrated\t11", b"integrated\t10"),
                        mapping.replace(b"b0\t10", b"b0\t11"),
                        mapping + b"b2\t12\n"):
            with self.assertRaises(EvidenceRejected):
                verify_body_map(altered, calls)
        with self.assertRaises(EvidenceRejected):
            verify_body_map(mapping, [calls[1], calls[0], calls[2]])

    @unittest.skipUnless(os.environ.get("DYN4K_BOOLEAN_JDI_TOY"),
                         "No retained JDK21 body-map toy supplied")
    def test_toy_archive_requires_all_jdi_bytes(self):
        root = Path(os.environ["DYN4K_BOOLEAN_JDI_TOY"])
        output = root / "toy-1"
        original = {path.name: path.read_bytes() for path in output.iterdir()
                    if path.is_file()}
        class_bytes = (root / "toy-classes/ToyBooleanJdi$Rotation.class").read_bytes()
        markers = [{key: call[key] for key in ("pre", "trig", "post", "angle_bits")}
                   for call in read_probe_events(output, 3)]
        result = verify_jdi_archive(archive(original), class_bytes,
                                    "ToyBooleanJdi$Rotation", 3, markers)
        self.assertEqual(result["status"], "MATCHED_JDI_BYTES_UNPASSED_ORIGIN")
        self.assertEqual(result["qualification"], "UNPASSED")
        self.assertIn("artifact_class_sha256", result)
        self.assertNotIn("loaded_class_sha256", result)
        for changed in ({key: value for key, value in original.items()
                         if key != "body-map.tsv"},
                        {**original, "extra.txt": b"forged"},
                        {**original, "events.tsv": original["events.tsv"].replace(
                            b"8000000000000000", b"0000000000000000", 1)},
                        {**original, "constant-pool.bin": b"forged"}):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_archive(archive(changed), class_bytes,
                                   "ToyBooleanJdi$Rotation", 3, markers)

    def test_source_sites_select_captured_branch(self):
        self.assertEqual(parse_call_sites(BODY, JOINT), [2, 550, 588])
        with self.assertRaises(EvidenceRejected):
            parse_call_sites(BODY.replace("line 264", "line 263"), JOINT)
        with self.assertRaises(EvidenceRejected):
            parse_call_sites(BODY, JOINT.replace("line 269", "line 268"))

    def test_transport_needs_worker_bind_and_helper_connect(self):
        worker = archive({"trace.123": WORKER_EXEC + (
            'bind(9, {sa_family=AF_INET, sin_port=htons(40001), '
            'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n'
            'listen(9, 1) = 0\n').encode()})
        helper = archive({"trace.456": HELPER_SOCKET_TRACE})
        result = verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        self.assertEqual(result["status"], "MATCHED_JDI_SOCKET_SYSCALLS_UNPASSED_PROCESS")
        self.assertEqual(result["qualification"], "UNPASSED")
        for changed_worker, changed_helper, port in (
            (worker.replace(b"bind(", b"find("), helper, 40001),
            (worker.replace(b"listen(9", b"listen(8"), helper, 40001),
            (worker, helper.replace(b"connect(", b"bonnect("), 40001),
            (worker, helper, 40002),
        ):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(changed_worker, changed_helper, port, 123, 456,
                                     HELPER_ARGS)
        original_trace = zipfile.ZipFile(io.BytesIO(helper)).read("trace.456")
        for changed in (archive({"trace.456": original_trace.replace(
                            b"RotationJdiProbe", b"FakeJdiProbe")}),
                        archive({"trace.456": original_trace,
                                 "trace.999": b"forged\n"})):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(worker, changed, 40001, 123, 456, HELPER_ARGS)

    def test_helper_connect_requires_same_process_thread_ancestry(self):
        worker = archive({"trace.123": WORKER_EXEC + SOCKET_BIND + SOCKET_LISTEN})
        leader, connect = HELPER_SOCKET_TRACE.split(b"connect(", 1)
        connect = b"connect(" + connect
        clone = THREAD_CLONE.replace(b"124", b"457")
        helper = archive({"trace.456": leader + clone, "trace.457": connect})
        result = verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        self.assertEqual(result["helper_connector"], 457)
        nested = archive({"trace.456": leader + clone,
                          "trace.457": THREAD_CLONE.replace(b"124", b"458"),
                          "trace.458": connect})
        self.assertEqual(verify_jdi_transport(
            worker, nested, 40001, 123, 456, HELPER_ARGS)["helper_connector"], 458)
        for parent, member in (
                (leader + b"clone(child_stack=NULL, flags=SIGCHLD) = 457\n", connect),
                (leader + clone.replace(b"CLONE_FILES", b"CLONE_PARENT"), connect),
                (leader, connect),
                (leader + clone, connect + b'execveat(AT_FDCWD, "/home/stewart/other", '
                 b'["other"], 0x7f, 0) = 0\n')):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(
                    worker, archive({"trace.456": parent, "trace.457": member}),
                    40001, 123, 456, HELPER_ARGS)

    def test_mapped_ipv4_loopback_connect_requires_exact_sockaddr(self):
        port = 37177
        args = HELPER_ARGS.copy()
        args[10] = str(port)
        leader = HELPER_SOCKET_TRACE.split(b"connect(", 1)[0].replace(
            b"40001", str(port).encode())
        clone = THREAD_CLONE.replace(b"124", b"457")
        worker = archive({"trace.123": WORKER_EXEC + SOCKET_BIND.replace(
            b"40001", str(port).encode()) + SOCKET_LISTEN})
        connect = (
            b'connect(6, {sa_family=AF_INET6, sin6_port=htons(37177), '
            b'sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "::ffff:127.0.0.1", '
            b'&sin6_addr), sin6_scope_id=0}, 28) = 0\n')
        helper = archive({"trace.456": leader + clone, "trace.457": connect})
        result = verify_jdi_transport(worker, helper, port, 123, 456, args)
        self.assertEqual(result["helper_connector"], 457)
        self.assertEqual(result["qualification"], "UNPASSED")
        for old, new in (
                (b"::ffff:127.0.0.1", b"::1"),
                (b"::ffff:127.0.0.1", b"::"),
                (b"::ffff:127.0.0.1", b"::ffff:0.0.0.0"),
                (b"::ffff:127.0.0.1", b"::ffff:192.0.2.1"),
                (b"sa_family=AF_INET6", b"sa_family=AF_INET"),
                (b"inet_pton(AF_INET6", b"inet_pton(AF_INET"),
                (b"htons(37177)", b"htons(37178)"),
                (b"sin6_flowinfo=htonl(0)", b"sin6_flowinfo=htonl(1)"),
                (b"sin6_scope_id=0", b"sin6_scope_id=1"),
                (b"&sin6_addr", b"sin6_addr"),
                (b"}, 28)", b"}, 16)"),
                (b"}, 28)", b", extra=0}, 28)"),
                (b") = 0\n", b") = 0 extra\n")):
            with self.subTest(old=old, new=new):
                changed = connect.replace(old, new)
                self.assertNotEqual(changed, connect)
                with self.assertRaises(EvidenceRejected):
                    verify_jdi_transport(
                        worker, archive({"trace.456": leader + clone,
                                         "trace.457": changed}), port, 123, 456, args)
        fork = b"clone(child_stack=NULL, flags=SIGCHLD) = 457\n"
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(
                worker, archive({"trace.456": leader + fork,
                                 "trace.457": connect}), port, 123, 456, args)
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(
                worker, archive({"trace.456": leader + clone,
                                 "trace.457": connect + connect.replace(
                                     b"::ffff:127.0.0.1", b"::1")}),
                port, 123, 456, args)

    def test_selected_worker_bind_requires_thread_clone_chain(self):
        helper = archive({"trace.456": HELPER_SOCKET_TRACE})
        bind = ('bind(9, {sa_family=AF_INET, sin_port=htons(40001), '
                'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n'
                'listen(9, 1) = 0\n').encode()
        thread = ('clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND|'
                  'CLONE_THREAD, exit_signal=0}, 88) = 124\n').encode()
        fork = b'clone(child_stack=NULL, flags=SIGCHLD) = 124\n'
        good = archive({"trace.123": WORKER_EXEC + thread, "trace.124": bind})
        result = verify_jdi_transport(good, helper, 40001, 123, 456,
                                      HELPER_ARGS)
        self.assertEqual(result["worker_socket_writer"], 124)
        self.assertEqual(result["worker_socket_listener"], 124)
        self.assertEqual(result["worker_tgid"], 123)
        split = archive({"trace.123": WORKER_EXEC + thread + bind.split(b"listen(")[0],
                         "trace.124": b"listen(9, 1) = 0\n"})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(split, helper, 40001, 123, 456, HELPER_ARGS)
        for root in (fork, b"", thread.replace(b"CLONE_THREAD", b"CLONE_PARENT")):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(archive({"trace.123": WORKER_EXEC + root,
                                              "trace.124": bind}), helper,
                                     40001, 123, 456, HELPER_ARGS)
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(archive({"trace.123": WORKER_EXEC + thread,
                                          "trace.124": bind,
                                          "trace.125": b"unrelated\n"}), helper,
                                 40001, 123, 456, HELPER_ARGS)

    def test_successful_later_exec_rejects_worker_thread_attribution(self):
        helper = archive({"trace.456": HELPER_SOCKET_TRACE})
        replacement = (b'execve("/home/stewart/replacement", '
                       b'["replacement"], 0x7f) = 0\n')
        replacement_at = (b'execveat(AT_FDCWD, "/home/stewart/replacement", '
                          b'["replacement"], 0x7f, 0) = 0\n')
        for leader, member in (
                (WORKER_EXEC + THREAD_CLONE,
                 SOCKET_BIND + SOCKET_LISTEN + replacement),
                (WORKER_EXEC + THREAD_CLONE + replacement,
                 SOCKET_BIND + SOCKET_LISTEN),
                (WORKER_EXEC + THREAD_CLONE,
                 SOCKET_BIND + SOCKET_LISTEN + replacement_at)):
            worker = archive({"trace.123": leader, "trace.124": member})
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(worker, helper, 40001, 123, 456,
                                     HELPER_ARGS)
        failed = (b'execve("/home/stewart/missing", '
                  b'["missing"], 0x7f) = -1 ENOENT (No such file or directory)\n')
        worker = archive({"trace.123": WORKER_EXEC + THREAD_CLONE,
                          "trace.124": SOCKET_BIND + failed + SOCKET_LISTEN})
        self.assertEqual(verify_jdi_transport(
            worker, helper, 40001, 123, 456, HELPER_ARGS)["worker_socket_writer"], 124)
        worker = archive({"trace.123": WORKER_EXEC + failed + THREAD_CLONE,
                          "trace.124": SOCKET_BIND + SOCKET_LISTEN})
        self.assertEqual(verify_jdi_transport(
            worker, helper, 40001, 123, 456, HELPER_ARGS)["worker_tgid"], 123)
        worker = archive({"trace.123": THREAD_CLONE + WORKER_EXEC,
                          "trace.124": SOCKET_BIND + SOCKET_LISTEN})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)

    def test_helper_execveat_replacement_is_rejected(self):
        worker = archive({"trace.123": WORKER_EXEC + SOCKET_BIND + SOCKET_LISTEN})
        replacement = (b'execveat(AT_FDCWD, "/home/stewart/replacement", '
                       b'["replacement"], 0x7f, 0) = 0\n')
        helper = archive({"trace.456": HELPER_SOCKET_TRACE + replacement})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        aligned = replacement.replace(b") = 0\n", b")              = 0\n")
        helper = archive({"trace.456": HELPER_SOCKET_TRACE + aligned})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        helper = archive({"trace.456": HELPER_SOCKET_TRACE + b"clone(0) = 457\n",
                          "trace.457": replacement})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        helper = archive({"trace.456": HELPER_SOCKET_TRACE +
                          b'execve("/home/stewart/replacement", '
                          b'["replacement"], 0x7f) = 0\n'})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        failed = replacement.replace(b" = 0\n", b" = -1 ENOENT\n")
        helper = archive({"trace.456": HELPER_SOCKET_TRACE + failed})
        self.assertEqual(verify_jdi_transport(
            worker, helper, 40001, 123, 456, HELPER_ARGS)["qualification"],
            "UNPASSED")

    def test_reversed_listen_rejects_socket_attribution(self):
        helper = archive({"trace.456": HELPER_SOCKET_TRACE})
        for member in (SOCKET_LISTEN + SOCKET_BIND,
                       SOCKET_BIND + SOCKET_LISTEN + SOCKET_LISTEN):
            worker = archive({"trace.123": WORKER_EXEC + THREAD_CLONE,
                              "trace.124": member})
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(worker, helper, 40001, 123, 456,
                                     HELPER_ARGS)

    def test_cross_thread_listen_rejects_socket_attribution(self):
        helper = archive({"trace.456": HELPER_SOCKET_TRACE})
        for leader, member in (
                (WORKER_EXEC + THREAD_CLONE + SOCKET_BIND, SOCKET_LISTEN),
                (WORKER_EXEC + THREAD_CLONE + SOCKET_LISTEN,
                 SOCKET_BIND + SOCKET_LISTEN)):
            worker = archive({"trace.123": leader, "trace.124": member})
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(worker, helper, 40001, 123, 456,
                                     HELPER_ARGS)

    def test_vm_disconnect_is_not_vm_death(self):
        source = Path(__file__).resolve().parent
        configured_home = os.environ.get("DYN4K_JDI_JDK_HOME")
        if configured_home:
            java_home = Path(configured_home).expanduser().resolve()
            java = java_home / "bin" / "java"
            javac = java_home / "bin" / "javac"
            if not java.is_file() or not javac.is_file() or not os.access(java, os.X_OK) or \
                    not os.access(javac, os.X_OK):
                self.fail("DYN4K_JDI_JDK_HOME must contain executable Java 21 tools")
        else:
            java_name = shutil.which("java")
            javac_name = shutil.which("javac")
            if java_name is None or javac_name is None:
                self.skipTest(
                    "JDK 21 is unavailable; set DYN4K_JDI_JDK_HOME or provide java and javac"
                )
            java = Path(java_name).resolve()
            javac = Path(javac_name).resolve()
            if java.parent != javac.parent:
                self.skipTest("system java and javac do not share a toolchain")
            java_home = java.parent.parent

        for executable in (java, javac):
            version = subprocess.run((str(executable), "-version"), capture_output=True,
                                     text=True, timeout=10)
            self.assertEqual(version.returncode, 0, "Java tool version check failed")
            output = version.stdout + version.stderr
            token = next((part.strip('"') for part in output.split()
                          if part.strip('"')[:1].isdigit()), None)
            is_java_21 = token is not None and token.split(".", 1)[0].split("-", 1)[0] == "21"
            if not is_java_21:
                if configured_home:
                    self.fail("DYN4K_JDI_JDK_HOME does not point to Java 21")
                self.skipTest("system Java toolchain is not version 21")

        environment = os.environ.copy()
        environment.pop("OLLAMA_API_KEY", None)
        environment["JAVA_HOME"] = str(java_home)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home()))) as root:
            environment["TMPDIR"] = root
            build = subprocess.run((str(javac),
                                    "--add-modules", "jdk.jdi", "-d", root,
                                    str(source / "RotationJdiProbe.java"),
                                    str(source / "EndpointControl.java")),
                                   env=environment, capture_output=True, timeout=30)
            self.assertEqual(build.returncode, 0, "JDI endpoint control did not compile")
            run = subprocess.run((str(java), "--add-modules",
                                  "jdk.jdi", "-Djava.io.tmpdir=" + root, "-cp", root,
                                  "EndpointControl"), env=environment,
                                 capture_output=True, timeout=15)
            self.assertEqual(run.returncode, 0, "JDI endpoint control failed")

    @unittest.skipUnless(os.environ.get("DYN4K_JDI_RETAINED_JAR"),
                         "No retained source-compatible JAR supplied")
    def test_retained_jar_disassembly(self):
        from jdi_bridge import derive_call_sites
        raw = Path(os.environ["DYN4K_JDI_RETAINED_JAR"]).read_bytes()
        self.assertEqual(derive_call_sites(raw), [2, 550, 588])


if __name__ == "__main__":
    unittest.main()
