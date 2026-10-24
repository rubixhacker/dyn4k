import json
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import actual_capture_receipt as focused_receipt
import actual_output_v6
import capture_actual
from actual_capture_receipt import (FILE_NAMES, FocusedRejected,
                                    _expected_classes, _helper_members, _xml_mirror,
                                    verify_boolean_startup, verify_helper_startup,
                                    load_version6_archive, verify_existing,
                                    verify_launcher_input)
from actual_trace import checked_projection, TraceRejected
from boolean_rotation_jdi import jdi_bridge
from boolean_rotation_jdi.jdi_bridge import verify_jdi_file_writes
from prospective_compare import verify_arithmetic_captures
from receipt import Rejected


class FocusedReplayTest(unittest.TestCase):
    def test_failed_observer_raw_stays_private_and_counted(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            scratch = root / "scratch"
            private = root / "private"
            output = root / "output"
            for path in (scratch, private, output):
                path.mkdir(mode=0o700)
            raw = scratch / "output-observer-trace.41"
            raw.write_bytes(b"synthetic rejected trace\n")
            budget = capture_actual.CaptureBudget(
                output, scratch, (), private=private, limit_bytes=100)
            before = budget.check()
            original = capture_actual.CaptureRejected("original observer failure")
            capture_actual.retain_observer_diagnostics(
                scratch, private, budget, original)
            retained = private / raw.name
            self.assertFalse(raw.exists())
            self.assertEqual(retained.read_bytes(), b"synthetic rejected trace\n")
            self.assertEqual(retained.stat().st_mode & 0o777, 0o600)
            self.assertEqual(before, budget.check())
            self.assertEqual(str(original), "original observer failure")
            second = capture_actual.CaptureRejected("original budget failure")
            next_raw = scratch / "output-observer-trace.42"
            next_raw.write_bytes(b"synthetic second rejection\n")
            small = capture_actual.CaptureBudget(
                output, scratch, (), private=private, limit_bytes=1)
            capture_actual.retain_observer_diagnostics(
                scratch, private, small, second)
            self.assertEqual((private / next_raw.name).read_bytes(),
                             b"synthetic second rejection\n")
            self.assertEqual(str(second), "original budget failure")
            self.assertTrue(any("retention failed" in note
                                for note in second.__notes__))

    def test_version6_original_writer_identity_and_close(self):
        path = str(Path.home() / "focused-output-proof-test")
        identity = {"device_major": 0, "device_minor": 42, "inode": 19,
                    "size": 4}
        status = "{st_dev=makedev(0, 42), st_ino=19, st_mode=S_IFREG|0644, st_size=4}"
        raw = (
            '1.000001 execve("/jdk/java", ["/jdk/java"], 0x0) = 0\n'
            f'1.000002 openat(AT_FDCWD, "{path}", O_WRONLY|O_CREAT|O_EXCL, '
            f'0666) = 59<{path}>\n'
            f'1.000003 write(59<{path}>, "abc\\n", 4) = 4\n'
            f'1.000004 fstat(59<{path}>, {status}) = 0\n'
            f'1.000005 close(59<{path}>) = 0\n'
            '1.000006 +++ exited with 0 +++\n').encode()
        from numeric_producer_trace import _events
        events = _events({"41": raw}, {path})
        result = actual_output_v6.prove_file_lifetime(
            {"41": raw}, events, "41", path, b"abc\n", identity, "mirror")
        self.assertEqual(result["writer_identity"], identity)
        for label, changed in (
                ("lost_stat", raw.replace(
                    f'1.000004 fstat(59<{path}>, {status}) = 0\n'.encode(), b"")),
                ("lost_close", raw.replace(
                    f'1.000005 close(59<{path}>) = 0\n'.encode(), b"")),
                ("alias", raw.replace(
                    f'1.000004 fstat(59<{path}>, {status}) = 0\n'.encode(),
                    (f'1.0000031 dup(59<{path}>) = 60<{path}>\n'
                     f'1.000004 fstat(59<{path}>, {status}) = 0\n').encode())),
                ("late_seek", raw.replace(
                    f'1.000004 fstat(59<{path}>, {status}) = 0\n'.encode(),
                    (f'1.0000031 lseek(59<{path}>, 0, SEEK_SET) = 0\n'
                     f'1.000004 fstat(59<{path}>, {status}) = 0\n').encode())),
                ("early_close", raw.replace(
                    f'1.000004 fstat(59<{path}>, {status}) = 0\n'.encode(),
                    f'1.000004 close(59<{path}>) = 0\n'.encode()).replace(
                    f'1.000005 close(59<{path}>) = 0\n'.encode(), b"")),
                ("wrong_object", raw.replace(b"st_ino=19", b"st_ino=20"))):
            with self.subTest(change=label), self.assertRaises(Rejected):
                actual_output_v6.prove_file_lifetime(
                    {"41": changed}, _events({"41": changed}, {path}), "41",
                    path, b"abc\n", identity, "mirror")
        for label, extra, before in (
                ("changed_path_after_close",
                 f'1.0000051 rename("{path}", "{path}.old") = 0\n',
                 b'1.000006 +++ exited with 0 +++\n'),
                ("changed_final_identity",
                 f'1.0000041 fstat(59<{path}>, '
                 '{st_dev=makedev(0, 42), st_ino=20, '
                 'st_mode=S_IFREG|0644, st_size=4}) = 0\n',
                 f'1.000005 close(59<{path}>) = 0\n'.encode())):
            changed = raw.replace(before, extra.encode() + before)
            with self.subTest(change=label), self.assertRaises(Rejected):
                actual_output_v6.prove_file_lifetime(
                    {"41": changed}, _events({"41": changed}, {path}), "41",
                    path, b"abc\n", identity, "mirror")

    def test_version6_observer_requires_four_ordered_read_only_identities(self):
        paths = tuple(str(Path.home() / f"focused-observer-{number}")
                      for number in range(4))
        interpreter = "/usr/bin/python3"
        argv = actual_output_v6.observer_command(interpreter, paths)
        identities = {role: {"device_major": 0, "device_minor": 42,
                              "inode": number + 1, "size": number + 4}
                      for number, role in enumerate(actual_output_v6.ROLES)}
        rows = [f'2.000001 execve("{interpreter}", '
                f'[{", ".join(json.dumps(item) for item in argv)}], 0x0) = 0']
        for number, path in enumerate(paths):
            stamp = 2 + number * 3
            rows.extend((
                f'2.{stamp:06d} openat(AT_FDCWD, "{path}", '
                f'O_RDONLY|O_CLOEXEC|O_NOFOLLOW) = 3<{path}>',
                f'2.{stamp + 1:06d} fstat(3<{path}>, '
                '{st_dev=makedev(0, 42), '
                f'st_ino={number + 1}, st_mode=S_IFREG|0644, '
                f'st_size={number + 4}' + '}) = 0',
                f'2.{stamp + 2:06d} close(3<{path}>) = 0'))
        rows.append('2.000020 +++ exited with 0 +++')
        def packed(values, comment=b""):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr("trace.51", ("\n".join(values) + "\n").encode())
                archive.comment = comment
            return buffer.getvalue()
        producer = [(1, "41", 0, "+++ exited with 0 +++")]
        valid_zip = packed(rows)
        result = actual_output_v6.verify_observer(
            valid_zip, interpreter, paths, identities, producer, producer)
        self.assertEqual(result["status"], "PROVED_V6_OUTPUT_OBSERVER")
        self.assertEqual(result["trace_sha256"], hashlib.sha256(valid_zip).hexdigest())
        with patch.object(actual_output_v6, "MAX_OBSERVER_ARCHIVE_BYTES",
                          len(valid_zip) - 1), patch.object(
                              zipfile, "ZipFile",
                              side_effect=AssertionError("oversized ZIP was parsed")):
            with self.assertRaisesRegex(Rejected, "observer archive size"):
                actual_output_v6.verify_observer(
                    valid_zip, interpreter, paths, identities,
                    producer, producer)
        declared_oversize = bytearray(valid_zip)
        local_header = declared_oversize.find(b"PK\x03\x04")
        central_header = declared_oversize.rfind(b"PK\x01\x02")
        self.assertGreaterEqual(local_header, 0)
        self.assertGreaterEqual(central_header, 0)
        oversized_size = 128 * 1024 * 1024 + 1
        declared_oversize[local_header + 22:local_header + 26] = \
            oversized_size.to_bytes(4, "little")
        declared_oversize[central_header + 24:central_header + 28] = \
            oversized_size.to_bytes(4, "little")
        with patch.object(zipfile.ZipExtFile, "read",
                          side_effect=AssertionError(
                              "member read before size rejection")) as member_read:
            with self.assertRaisesRegex(Rejected, "observer trace inventory"):
                actual_output_v6.verify_observer(
                    bytes(declared_oversize), interpreter, paths, identities,
                    producer, producer)
        member_read.assert_not_called()
        corrupt_crc = bytearray(valid_zip)
        corrupt_crc[local_header + 14] ^= 0x01
        corrupt_crc[central_header + 16] ^= 0x01
        with self.assertRaisesRegex(Rejected, "observer trace is malformed"):
            actual_output_v6.verify_observer(
                bytes(corrupt_crc), interpreter, paths, identities,
                producer, producer)
        self.assertEqual(actual_output_v6.verify_observer(
            packed(rows, comment=b'"\\xZZ"'), interpreter, paths,
            identities, producer, producer)["status"],
            "PROVED_V6_OUTPUT_OBSERVER")
        with self.assertRaisesRegex(Rejected, "observer privacy"):
            actual_output_v6.verify_observer(
                packed(rows, comment=b"OLLAMA_API_KEY"), interpreter, paths,
                identities, producer, producer)
        protected_transfers = (
            f'sendfile(1<pipe:[8]>, 3<{paths[0]}>, NULL, 1) = 1',
            f'mmap(NULL, 4096, PROT_READ, MAP_PRIVATE, 3<{paths[0]}>, 0) = 0x1000',
            f'copy_file_range(1<pipe:[8]>, NULL, 3<{paths[0]}>, NULL, 1, 0) = 1',
            f'splice(1<pipe:[8]>, NULL, 3<{paths[0]}>, NULL, 1, 0) = 1',
        )
        for transfer in protected_transfers:
            with self.subTest(protected_transfer=transfer.split("(", 1)[0]):
                with self.assertRaisesRegex(Rejected, "observer protected action"):
                    actual_output_v6.verify_observer(
                        packed([*rows[:2], "2.000002 " + transfer, *rows[2:]]),
                        interpreter, paths, identities, producer, producer)
        for operation in (
                f'renameat(AT_FDCWD, "/usr/lib/loader", AT_FDCWD, "{paths[0]}") = 0',
                f'unlinkat(AT_FDCWD, "{paths[0]}", 0) = 0'):
            with self.subTest(protected_path=operation.split("(", 1)[0]):
                with self.assertRaisesRegex(Rejected, "observer protected action"):
                    actual_output_v6.verify_observer(
                        packed([*rows[:2], "2.000002 " + operation, *rows[2:]]),
                        interpreter, paths, identities, producer, producer)
        with self.assertRaisesRegex(Rejected, "observer protected action"):
            actual_output_v6.verify_observer(
                packed([*rows[:2],
                        '2.000002 read(7</usr/lib/loader>, "x", 1) = 1',
                        *rows[2:]]), interpreter, paths, identities,
                producer, producer)
        for transfer in (
                'sendfile(1<pipe:[8]>, 7</usr/lib/loader>, NULL, 1) = 1',
                'mmap(NULL, 4096, PROT_READ, MAP_PRIVATE, '
                '7</usr/lib/loader>, 0) = 0x1000',
                'copy_file_range(1<pipe:[8]>, NULL, '
                '7</usr/lib/loader>, NULL, 1, 0) = 1',
                'splice(1<pipe:[8]>, NULL, '
                '7</usr/lib/loader>, NULL, 1, 0) = 1'):
            with self.subTest(unprotected_transfer=transfer.split("(", 1)[0]):
                launch = (
                    '1.000001 openat(AT_FDCWD, "/usr/lib/loader", O_RDONLY) = '
                    '7</usr/lib/loader>',
                    '1.000002 ' + transfer,
                    '1.000003 close(7</usr/lib/loader>) = 0')
                self.assertEqual(actual_output_v6.verify_observer(
                    packed([*launch, *rows]), interpreter, paths, identities,
                    producer, producer)["status"], "PROVED_V6_OUTPUT_OBSERVER")
        for label, changed in (
                ("early", [rows[0].replace("2.000001", "0.000001"), *rows[1:]]),
                ("wrong_flags", [line.replace("O_NOFOLLOW", "O_TRUNC")
                                 for line in rows]),
                ("wrong_literal", [rows[0].replace(
                    "import os,sys", "import os,time"), *rows[1:]]),
                ("missing_stat", [line for line in rows if "fstat(" not in line]),
                ("extra_write", [*rows[:-1],
                                 '2.000019 write(1<pipe:[42]>, "x", 1) = 1',
                                 rows[-1]]),
                ("wrong_role", [rows[0], *rows[4:7], *rows[1:4], *rows[7:]])):
            with self.subTest(change=label), self.assertRaises(Rejected):
                actual_output_v6.verify_observer(
                    packed(changed), interpreter, paths, identities,
                    producer, producer)
        for label, added in (
                ("extra_exec", '2.000000 execve("/other", ["/other"], 0x0) = -1 ENOENT'),
                ("protected_query", f'2.000003 fcntl(3<{paths[0]}>, F_GETFD) = 1')):
            with self.subTest(change=label), self.assertRaises(Rejected):
                actual_output_v6.verify_observer(
                    packed([rows[0], added, *rows[1:]]), interpreter,
                    paths, identities, producer, producer)
        prefix = (
            f'1.000001 openat(AT_FDCWD, "{paths[0]}", O_RDONLY) = 7<{paths[0]}>',
            f'1.000002 read(7<{paths[0]}>, "x", 1) = 1',
            f'1.000003 close(7<{paths[0]}>) = 0')
        with self.assertRaises(Rejected):
            actual_output_v6.verify_observer(
                packed([*prefix, *rows]), interpreter, paths, identities,
                producer, producer)
        with self.assertRaises(Rejected):
            actual_output_v6.verify_observer(
                packed([*(line.replace("1.00000", "2.00000") for line in prefix),
                        *rows]), interpreter, paths, identities,
                producer, producer)
        unprotected = (
            '1.000001 openat(AT_FDCWD, "/usr/lib/loader", O_RDONLY) = '
            '7</usr/lib/loader>',
            '1.000002 read(7</usr/lib/loader>, "x", 1) = 1',
            '1.000003 close(7</usr/lib/loader>) = 0')
        self.assertEqual(actual_output_v6.verify_observer(
            packed([*unprotected, *rows]), interpreter, paths, identities,
            producer, producer)["status"], "PROVED_V6_OUTPUT_OBSERVER")
        unprotected_status = ('1.000002 newfstatat(AT_FDCWD, '
                              '"/usr/lib/loader", {st_mode=S_IFREG}, 0) = 0')
        self.assertEqual(actual_output_v6.verify_observer(
            packed([unprotected[0], unprotected_status, unprotected[2], *rows]),
            interpreter, paths, identities, producer, producer)["status"],
            "PROVED_V6_OUTPUT_OBSERVER")
        parent = str(Path(paths[0]).parent)
        basename = Path(paths[0]).name
        relative_prefix = (
            f'1.000001 openat(AT_FDCWD, "{parent}", O_RDONLY|O_DIRECTORY) = 7<{parent}>',
            f'1.000002 renameat(7<{parent}>, "{basename}", '
            f'7<{parent}>, "{basename}.held") = 0',
            f'1.000003 renameat(7<{parent}>, "{basename}.held", '
            f'7<{parent}>, "{basename}") = 0',
            f'1.000004 close(7<{parent}>) = 0')
        with self.subTest(relative_rename=True):
            with self.assertRaisesRegex(Rejected, "observer protected launch action"):
                actual_output_v6.verify_observer(
                    packed([*relative_prefix, *rows]), interpreter, paths,
                    identities, producer, producer)
        for operation in (
                f'newfstatat(7<{parent}>, "{basename}", '
                '{st_mode=S_IFREG}, 0) = 0',
                f'statx(7<{parent}>, "{basename}", 0, STATX_BASIC_STATS, '
                '{stx_mode=S_IFREG}) = 0'):
            with self.subTest(relative_status=operation.split("(", 1)[0]):
                with self.assertRaisesRegex(Rejected, "observer protected launch action"):
                    actual_output_v6.verify_observer(
                        packed([relative_prefix[0], "1.000002 " + operation,
                                relative_prefix[-1].replace("1.000004", "1.000003"),
                                *rows]), interpreter, paths, identities,
                        producer, producer)
        for label, operation in (
                ("relative_cwd", f'stat("{basename}", {{st_mode=S_IFREG}}) = 0'),
                ("empty_path", 'newfstatat(7</usr/lib/loader>, "", '
                 '{st_mode=S_IFREG}, AT_EMPTY_PATH) = 0'),
                ("lexical_absolute", f'rename("{parent}/./{basename}", '
                 '"/usr/lib/loader") = 0'),
                ("double_slash", f'stat("/{paths[0]}", '
                 '{st_mode=S_IFREG}) = 0')):
            with self.subTest(path_form=label):
                with self.assertRaisesRegex(Rejected, "observer protected launch action"):
                    actual_output_v6.verify_observer(
                        packed([unprotected[0], "1.000002 " + operation,
                                unprotected[2], *rows]), interpreter, paths,
                        identities, producer, producer)
        equal_time_status = (f'2.000004 newfstatat(7<{parent}>, "{basename}", '
                             '{st_mode=S_IFREG}, 0) = 0')
        with self.assertRaisesRegex(Rejected, "observer protected action"):
            actual_output_v6.verify_observer(
                packed([relative_prefix[0], *rows[:4], equal_time_status,
                        relative_prefix[-1].replace("1.000004", "2.000004"),
                        *rows[4:]]), interpreter, paths, identities,
                producer, producer)
        live_mention = '7<' + paths[0] + '>'
        harmless = (f'1.000002 write(1<pipe:[8]>, {json.dumps(live_mention)}, '
                    f'{len(live_mention)}) = {len(live_mention)}')
        self.assertEqual(actual_output_v6.verify_observer(
            packed([unprotected[0], harmless, unprotected[2], *rows]),
            interpreter, paths, identities, producer, producer)["status"],
            "PROVED_V6_OUTPUT_OBSERVER")
        with self.assertRaisesRegex(Rejected, "protected descriptor"):
            actual_output_v6.verify_observer(
                packed([unprotected[0],
                        f'1.000002 read(7<{paths[0]}>, "x", 1) = 1',
                        unprotected[2], *rows]), interpreter, paths,
                identities, producer, producer)
        mention = (f'1.000004 write(1<pipe:[8]>, '
                   f'{json.dumps(paths[0])}, {len(paths[0])}) = {len(paths[0])}')
        self.assertEqual(actual_output_v6.verify_observer(
            packed([*unprotected, mention, *rows]), interpreter, paths,
            identities, producer, producer)["status"],
            "PROVED_V6_OUTPUT_OBSERVER")
        fd_mention = '3<' + paths[0] + '> ->'
        quoted_mention = ('1.000004 write(1<pipe:[8]>, ' +
                          json.dumps(fd_mention) + ', ' +
                          str(len(fd_mention)) + ') = ' + str(len(fd_mention)))
        self.assertEqual(actual_output_v6.verify_observer(
            packed([*unprotected, quoted_mention, *rows]), interpreter,
            paths, identities, producer, producer)["status"],
            "PROVED_V6_OUTPUT_OBSERVER")
        for label, prefix_call in (
                ("child", 'clone(flags=CLONE_VM|CLONE_FILES) = 90'),
                ("alias", 'dup(7</usr/lib/loader>) = 8</usr/lib/loader>'),
                ("control_alias", 'fcntl(7</usr/lib/loader>, F_DUPFD, 0) = '
                 '8</usr/lib/loader>'),
                ("control_transfer", 'sendmsg(1<pipe:[8]>, '
                 '{msg_control=[{cmsg_type=SCM_RIGHTS, '
                 'cmsg_data=[7</usr/lib/loader>]}]}, 0) = 1')):
            with self.subTest(prefix=label):
                with self.assertRaisesRegex(Rejected,
                                            "observer protected launch action"):
                    actual_output_v6.verify_observer(
                        packed([*unprotected[:1], '1.000002 ' + prefix_call,
                                *unprotected[1:], *rows]), interpreter, paths,
                        identities, producer, producer)

    def test_version6_auxiliary_socket_requires_shared_live_object(self):
        payload = b"NUMERICAL_JSON {}\n"
        direct = f'write(59</home/mirror>, {json.dumps(payload.decode())}, '
        direct += f'{len(payload)}) = {len(payload)}'
        copy = b"framed" + payload
        outgoing = f'write(56<TCP:[local->remote]>, {json.dumps(copy.decode())}, '
        outgoing += f'{len(copy)}) = {len(copy)}'
        parent = (
            '1.000001 execve("/jdk/java", ["/jdk/java"], 0x0) = 0\n'
            '1.000002 clone(flags=CLONE_THREAD|CLONE_VM|CLONE_FILES) = 42\n'
            '1.000003 socket(AF_INET, SOCK_STREAM, IPPROTO_TCP) = 56<TCP:[local]>\n'
            '1.000004 connect(56<TCP:[local]>, {sa_family=AF_INET}, 16) = '
            '-1 EINPROGRESS (Operation now in progress)\n'
            f'1.000005 {direct}\n'
            '1.000009 +++ exited with 0 +++\n').encode()
        child = (f'1.000006 {outgoing}\n'
                 '1.000007 close(56<TCP:[local->remote]>) = 0\n'
                 '1.000008 +++ exited with 0 +++\n').encode()
        def check(worker, writer):
            from numeric_producer_trace import _events
            traces = {"41": worker, "42": writer}
            return actual_output_v6.prove_socket_writers(
                traces, _events(traces, ()), "41", ("41", "59"))
        selected, proof = check(parent, child)
        self.assertEqual(selected, frozenset({("42", "56")}))
        self.assertEqual(proof[0]["writes"], 1)
        for label, worker, writer in (
                ("copied_table", parent.replace(b"CLONE_FILES", b"CLONE_FS"), child),
                ("wrong_provider", parent.replace(b"IPPROTO_TCP", b"IPPROTO_UDP"), child),
                ("alias", parent.replace(
                    b'1.000004 connect(', b'1.0000031 dup(56<TCP:[local]>) = '
                    b'100<TCP:[local]>\n1.000004 connect('), child),
                ("lost_close", parent, child.replace(
                    b'1.000007 close(56<TCP:[local->remote]>) = 0\n', b""))):
            with self.subTest(change=label), self.assertRaises(Rejected):
                check(worker, writer)
        for label, added in (
                ("sendto", 'sendto(56<TCP:[local->remote]>, "x", 1, 0, '
                 'NULL, 0) = 1'),
                ("writev", 'writev(56<TCP:[local->remote]>, '
                 '[{iov_base="x", iov_len=1}], 1) = 1'),
                ("sendfile", 'sendfile(56<TCP:[local->remote]>, '
                 '9<pipe:[7]>, NULL, 1) = 1'),
                ("splice", 'splice(9<pipe:[7]>, NULL, '
                 '56<TCP:[local->remote]>, NULL, 1, 0) = 1'),
                ("copy_file_range", 'copy_file_range(9<pipe:[7]>, NULL, '
                 '56<TCP:[local->remote]>, NULL, 1, 0) = 1'),
                ("pwrite64", 'pwrite64(56<TCP:[local->remote]>, '
                 '"x", 1, 0) = 1'),
                ("pwritev", 'pwritev(56<TCP:[local->remote]>, '
                 '[{iov_base="x", iov_len=1}], 1, 0) = 1'),
                ("sendmsg", 'sendmsg(56<TCP:[local->remote]>, '
                 '{msg_iov=[{iov_base="x", iov_len=1}]}, 0) = 1')):
            with self.subTest(change=label), self.assertRaises(Rejected):
                check(parent, child.replace(
                    b'1.000007 close(',
                    f'1.0000061 {added}\n1.000007 close('.encode()))
        extra = ('1.0000061 write(56<TCP:[local->remote]>, "x", 1) = 1\n'
                 '1.000008 +++ exited with 0 +++\n').encode()
        copied_parent = parent.replace(
            b'1.000003 socket(',
            b'1.0000021 clone(flags=CLONE_VM) = 43\n'
            b'1.000003 socket(')
        with self.assertRaises(Rejected):
            traces = {"41": copied_parent, "42": child, "43": extra}
            from numeric_producer_trace import _events
            actual_output_v6.prove_socket_writers(
                traces, _events(traces, ()), "41", ("41", "59"))
        shared_parent = parent.replace(
            b'1.000003 socket(',
            b'1.0000021 clone(flags=CLONE_THREAD|CLONE_VM|CLONE_FILES) = 43\n'
            b'1.000003 socket(')
        traces = {"41": shared_parent, "42": child, "43": extra}
        from numeric_producer_trace import _events
        selected, proof = actual_output_v6.prove_socket_writers(
            traces, _events(traces, ()), "41", ("41", "59"))
        self.assertEqual(selected, frozenset({("42", "56")}))
        self.assertEqual(proof[0]["writes"], 2)
        self.assertEqual(proof[0]["writer_threads"], ["42", "43"])
        self.assertFalse(proof[0]["projected_bound"])
        after_close = extra.replace(b"1.0000061 write(", b"1.0000071 write(")
        with self.assertRaises(Rejected):
            late_traces = {"41": shared_parent, "42": child, "43": after_close}
            actual_output_v6.prove_socket_writers(
                late_traces, _events(late_traces, ()), "41", ("41", "59"))
        reused = child.replace(
            b'1.000008 +++ exited',
            b'1.0000071 socket(AF_INET, SOCK_STREAM, IPPROTO_TCP) = '
            b'56<TCP:[new]>\n1.0000072 write(56<TCP:[new->remote]>, '
            b'"x", 1) = 1\n1.000008 +++ exited')
        with self.assertRaisesRegex(Rejected, "socket provider differs"):
            reused_traces = {"41": parent, "42": reused}
            actual_output_v6.prove_socket_writers(
                reused_traces, _events(reused_traces, ()), "41", ("41", "59"))
        def projected(extra_payload=b"x", include_extra=True):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("trace.42", "write(56, " +
                                 json.dumps(copy.decode()) + ", " +
                                 str(len(copy)) + ") = " + str(len(copy)) + "\n")
                archive.writestr("trace.43", ("write(56, " +
                    json.dumps(extra_payload.decode()) + ", " +
                    str(len(extra_payload)) + ") = " +
                    str(len(extra_payload)) + "\n") if include_extra else "")
            return output.getvalue()
        _, bound = actual_output_v6.prove_socket_writers(
            traces, _events(traces, ()), "41", ("41", "59"),
            projected_archive=projected())
        self.assertTrue(bound[0]["projected_bound"])
        for changed in (projected(include_extra=False), projected(b"y")):
            with self.assertRaisesRegex(Rejected, "projected socket stream differs"):
                actual_output_v6.prove_socket_writers(
                    traces, _events(traces, ()), "41", ("41", "59"),
                    projected_archive=changed)
        split = child.replace(
            json.dumps(copy.decode()).encode(),
            json.dumps((copy + b"NUMERICAL_").decode()).encode()).replace(
            f'{len(copy)}) = {len(copy)}'.encode(),
            f'{len(copy) + 10}) = {len(copy) + 10}'.encode())
        split_extra = extra.replace(b'"x", 1) = 1', b'"JSON {}\\n", 8) = 8')
        with self.assertRaisesRegex(Rejected, "socket marker crosses writes"):
            split_traces = {"41": shared_parent, "42": split, "43": split_extra}
            actual_output_v6.prove_socket_writers(
                split_traces, _events(split_traces, ()), "41", ("41", "59"))
        child_extra = child.replace(
            b'1.000007 close(',
            b'1.0000061 write(56<TCP:[local->remote]>, "x", 1) = 1\n'
            b'1.000007 close(')
        traces = {"41": parent, "42": child_extra}
        _, proof = actual_output_v6.prove_socket_writers(
            traces, _events(traces, ()), "41", ("41", "59"))
        self.assertEqual(proof[0]["writes"], 2)
        unmodelled = extra.replace(
            b'write(56<TCP:[local->remote]>, "x", 1) = 1',
            b'sendto(56<TCP:[local->remote]>, "x", 1, 0, NULL, 0) = 1')
        traces = {"41": shared_parent, "42": child, "43": unmodelled}
        with self.assertRaises(Rejected):
            actual_output_v6.prove_socket_writers(
                traces, _events(traces, ()), "41", ("41", "59"))
        unrelated = ('1.0000061 sendto(560<TCP:[other]>, "x", 1, 0, '
                     'NULL, 0) = 1\n'
                     '1.0000062 write(9<pipe:[7]>, '
                     '"56<TCP:[local->remote]>", 23) = 23\n')
        traces = {"41": parent, "42": child.replace(
            b'1.000007 close(', unrelated.encode() + b'1.000007 close(')}
        _, proof = actual_output_v6.prove_socket_writers(
            traces, _events(traces, ()), "41", ("41", "59"))
        self.assertEqual(proof[0]["writes"], 1)

    def test_version6_source_binding_precedes_legacy_writer_selection(self):
        commit = "a" * 40
        path = str(Path.home() / "focused-order-test")
        metadata = {key: path for key in (
            "response_path", "agent_path", "witness_path", "mirror_path",
            "class_load_path", "argument_path", "helper_argument_path")}
        metadata.update({key: {} for key in (
            "agent_identity", "witness_identity", "mirror_identity",
            "argument_identity", "class_load_identity", "response_identity",
            "agent_after_identity", "artifact_identity",
            "artifact_after_identity", "runtime_identity",
            "runtime_after_identity", "launcher_identity",
            "launcher_after_identity", "helper_class_before",
            "helper_class_after", "helper_argument_identity",
            "observer_interpreter_identity",
            "observer_interpreter_after_identity")})
        metadata.update({"schema": "focused-arithmetic-capture/6",
                         "command": [], "trace_arguments": [],
                         "launcher_sha256": "", "observer_interpreter_path": path,
                         "observer_interpreter_sha256": "",
                         "observer_command": [],
                         "observer_environment_sha256": "",
                         "observer_exit_code": 0,
                         "worker_pid": 41, "exit_code": 0})
        transport = {"schema": "boolean-jdi-transport/1", "port": 41234,
                     "worker_pid": 41, "helper_pid": 42,
                     "helper_classes_path": path, "output_path": path,
                     "temp_path": path, "live_socket_owner": True}
        files = {key: b"raw" for key in FILE_NAMES}
        files.update(worker_class_load=b"class", worker_arguments=b"arguments",
                     source=b"source", metadata=json.dumps(metadata).encode(),
                     jdi_transport=json.dumps(transport).encode())
        binding = focused_receipt.actual_arithmetic.V6WriterBinding(
            "b" * 64, ("41", "59"), frozenset({("42", "56")}))
        order = []
        def outputs(*args):
            order.append("raw output")
            return {}, {"status": "PROVED_V6_OUTPUT_OBSERVER"}, [], binding
        def legacy(*args, **kwargs):
            order.append("legacy writer")
            self.assertIs(kwargs["v6_writer_binding"], binding)
            return {"status": "legacy"}
        def proof(*args):
            order.append("focused proof")
            return {"status": "PASSED_FOCUSED_METHOD_EVIDENCE"}
        with patch("capture_actual.child_environment", return_value={}), \
                patch("capture_actual.clean_source", return_value=commit), \
                patch.object(focused_receipt.actual_arithmetic, "_source_archive",
                             return_value=b"source"), \
                patch.object(focused_receipt, "_helper_members", return_value=({}, {})), \
                patch.object(focused_receipt, "_trace_map", return_value={}), \
                patch.object(focused_receipt, "normalize_rich_traces",
                             return_value=({}, [])), \
                patch.object(focused_receipt, "_events", return_value=[]), \
                patch.object(focused_receipt, "_validate_calls"), \
                patch.object(focused_receipt, "verify_launcher_input"), \
                patch.object(jdi_bridge, "verify_worker_launch_v6"), \
                patch.object(focused_receipt, "_expected_classes",
                             return_value=({}, {})), \
                patch.object(focused_receipt, "read_witness",
                             return_value={"definitions": []}), \
                patch.object(focused_receipt, "_raw_projections",
                             return_value=({"legacy_zip": b"projected"}, {})), \
                patch.object(focused_receipt, "_verified_compiled_marker_reads",
                             return_value=(frozenset(), set())), \
                patch.object(focused_receipt, "_output_proof", side_effect=outputs), \
                patch.object(focused_receipt, "make_capture_receipt",
                             side_effect=legacy), \
                patch.object(focused_receipt, "_proof", side_effect=proof):
            result = focused_receipt.make_version6_receipt(files, commit)
        self.assertEqual(order, ["raw output", "legacy writer", "focused proof"])
        self.assertEqual(result["qualification"], "UNPASSED")

    def test_compiled_marker_read_requires_bound_input_bytes_and_lifetime(self):
        name = "portable/NumericalRecorder"
        root = Path.home() / "focused-class-input-test"
        path = root / (name + ".class")
        data = b"class-prefix NUMERICAL_JSON class-suffix"
        identity = (f'{{st_dev=makedev(0, 0), st_ino=42, '
                    f'st_mode=S_IFREG|0644, st_size={len(data)}}}')
        literal = json.dumps(data.decode())
        trace = (
            '1.000001 execve("/jdk/java", ["/jdk/java", "GradleWorkerMain"], 0x0) = 0\n'
            f'1.000002 stat("{path}", {identity}) = 0\n'
            f'1.000003 openat(AT_FDCWD, "{path}", O_RDONLY) = 7<{path}>\n'
            f'1.000004 fstat(7<{path}>, {identity}) = 0\n'
            f'1.000005 read(7<{path}>, {literal}, {len(data)}) = {len(data)}\n'
            f'1.000006 close(7<{path}>) = 0\n'
            '1.000007 +++ exited with 0 +++\n').encode()
        def archive(raw):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as packed:
                packed.writestr("trace.41", raw)
            return {"worker_write_traces": output.getvalue()}
        selected = ("41", "/jdk/java", ("/jdk/java", "GradleWorkerMain"))
        witness = {name: {"origin": root.as_uri()}}
        with patch.object(focused_receipt, "select_worker_exec", return_value=selected):
            trusted, paths = focused_receipt._verified_compiled_marker_reads(
                archive(trace), 41, {name: data}, {name: root}, witness)
            self.assertEqual(trusted, frozenset({("41", 4)}))
            self.assertEqual(paths, {str(path)})
            for label, changed in (
                    ("wrong_bytes", trace.replace(
                        data, b"wrong-input NUMERICAL_JSON wrong-input")),
                    ("lost_close", trace.replace(f'close(7<{path}>) = 0'.encode(),
                                  b'close(7) = 0')),
                    ("lost_fstat", trace.replace(
                        f'1.000004 fstat(7<{path}>, {identity}) = 0\n'.encode(), b'')),
                    ("wrong_provider", trace.replace(
                        f'openat(AT_FDCWD, "{path}"'.encode(),
                        b'openat(AT_FDCWD, "/home/other"'))):
                with self.subTest(change=label), \
                        self.assertRaises((FocusedRejected, Rejected)):
                    focused_receipt._verified_compiled_marker_reads(
                        archive(changed), 41, {name: data}, {name: root}, witness)

    def test_receipt_projects_both_raw_archives_with_version6_profile(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as output:
            output.writestr("trace.41", b"1.000001 +++ exited with 0 +++\n")
        worker, helper = focused_receipt._raw_projections(
            {"worker_write_traces": raw.getvalue(),
             "jdi_helper_traces": raw.getvalue()}, set(), set())
        self.assertEqual((worker["threads"], helper["threads"]), (1, 1))
        with patch("actual_trace.V6_RAW_MAX_BYTES", len(raw.getvalue()) - 1):
            with self.assertRaises(TraceRejected):
                focused_receipt._raw_projections(
                    {"worker_write_traces": raw.getvalue(),
                     "jdi_helper_traces": raw.getvalue()}, set(), set())

    def test_pinned_launcher_identity_and_bytes(self):
        launcher_bytes = b"bounded pinned launcher source test"
        identity = {"device_major": 0, "device_minor": 56,
                    "inode": 42, "size": len(launcher_bytes)}
        digest = hashlib.sha256(launcher_bytes).hexdigest()
        metadata = {"launcher_identity": identity,
                    "launcher_after_identity": identity,
                    "launcher_sha256": digest}
        with patch("actual_capture_receipt.captured_file_identity", return_value=identity), \
                patch.object(Path, "read_bytes", return_value=launcher_bytes), \
                patch.object(jdi_bridge, "JSPAWNHELPER_SHA256", digest):
            self.assertEqual(verify_launcher_input(metadata), digest)
            wrong_size = identity | {"size": len(launcher_bytes) + 1}
            with patch("actual_capture_receipt.captured_file_identity",
                       return_value=wrong_size), self.assertRaises(FocusedRejected):
                verify_launcher_input(metadata | {
                    "launcher_identity": wrong_size,
                    "launcher_after_identity": wrong_size})
            for changed in ({"launcher_sha256": "0" * 64},
                            {"launcher_identity": identity | {"size": identity["size"] + 1}},
                            {"launcher_after_identity": identity | {"inode": identity["inode"] + 1}}):
                with self.subTest(changed=changed), self.assertRaises(FocusedRejected):
                    verify_launcher_input(metadata | changed)

    def test_helper_output_destination_is_checked_before_byte_accounting(self):
        def packed(entries):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for name, value in entries.items():
                    archive.writestr(name, value)
            return output.getvalue()

        root = str(Path.home() / "focused-jdi-output")
        file_path = root + "/complete.txt"
        files = {"jdi_helper_classes": packed({"RotationJdiProbe.class": b"class"}),
                 "jdi_evidence": packed({"complete.txt": b"abc"})}
        transport = {"helper_classes_path": str(Path.home() / "helper-classes"),
                     "output_path": root}
        classes, outputs = _helper_members(files, transport)
        protected = set(classes) | set(outputs)
        good = (f'1.000001 openat(AT_FDCWD, "{file_path}", '
                f'O_WRONLY|O_CREAT|O_TRUNC, 0666) = 7<{file_path}>\n'
                f'1.000002 write(7<{file_path}>, "abc", 3) = 3\n'
                f'1.000003 close(7<{file_path}>) = 0\n'
                '1.000004 +++ exited with 0 +++\n').encode()
        projected = checked_projection(packed({"trace.41": good}), protected,
                                       strict_outputs=set(outputs))
        self.assertEqual(verify_jdi_file_writes(
            projected["legacy_zip"], files["jdi_evidence"], root)["files"], 1)
        redirected = good.replace(
            f'1.000002 write(7<{file_path}>, "abc", 3) = 3'.encode(),
            (f'1.000002 dup2(8</home/other>, 7<{file_path}>) = 7</home/other>\n'
             '1.0000021 write(7</home/other>, "abc", 3) = 3').encode())
        with self.assertRaises(TraceRejected):
            checked_projection(packed({"trace.41": redirected}), protected,
                               strict_outputs=set(outputs))
        replaced = good.replace(
            b'1.000004 +++ exited with 0 +++\n',
            f'1.0000031 rename("{file_path}", "{root}/other.txt") = 0\n'
            '1.000004 +++ exited with 0 +++\n'.encode())
        with self.assertRaises(TraceRejected):
            checked_projection(packed({"trace.41": replaced}), protected,
                               strict_outputs=set(outputs))

    def test_worker_and_helper_effective_agent_inventory(self):
        home = str(Path.home())
        metadata = {"agent_path": home + "/agent.jar",
                    "witness_path": home + "/witness.log",
                    "mirror_path": home + "/mirror.log"}
        agent = "-javaagent:" + metadata["agent_path"] + "=boolean:" + metadata["witness_path"]
        jdwp = ("-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,"
                 "address=127.0.0.1:40001")
        flags = agent + " " + jdwp + " -XX:+DisableAttachMechanism -Xshare:off " + \
            "-Dportable.booleanMirror=" + metadata["mirror_path"] + \
            " -Djdk.lang.Process.launchMechanism=FORK"
        prefix = "[41][info][arguments] "
        def worker_log(options):
            return ("\n".join(prefix + row for row in (
                "VM Arguments:", "jvm_args: " + options,
                "java_command: worker.org.gradle.process.internal.worker.GradleWorkerMain 1",
                "java_class_path (initial): /home/classes",
                "Launcher Type: SUN_STANDARD")) + "\n").encode()
        selected = ("41", "/tmp/dyn4k-tools/jdk21/bin/java",
                    ("java", agent, jdwp, "GradleWorkerMain"))
        verify_boolean_startup(worker_log(flags), selected, metadata, 40001)
        for changed in (flags.replace(" -Djdk.lang.Process.launchMechanism=FORK", ""),
                        flags + " -Djdk.lang.Process.launchMechanism=FORK",
                        flags.replace("=FORK", "=POSIX_SPAWN")):
            with self.subTest(launch=changed), self.assertRaises(FocusedRejected):
                verify_boolean_startup(worker_log(changed), selected, metadata, 40001)
        for option in ("-javaagent:/home/other.jar", "-agentlib:other=1"):
            with self.subTest(option=option), self.assertRaises(FocusedRejected):
                verify_boolean_startup(worker_log(flags + " " + option), selected,
                                       metadata, 40001)
            forged = (selected[0], selected[1], selected[2][:-1] +
                      (option, selected[2][-1]))
            with self.subTest(option=option), self.assertRaises(FocusedRejected):
                verify_boolean_startup(worker_log(flags), forged, metadata, 40001)
        helper_path = home + "/helper-arguments.log"
        helper_argv = ["/tmp/dyn4k-tools/jdk21/bin/java", "--add-modules", "jdk.jdi",
                       "-Djava.io.tmpdir=" + home, "-cp", home + "/helper-classes",
                       "RotationJdiProbe", "attach", home + "/output", "127.0.0.1",
                       "40001", "org.dyn4j.geometry.Transform", "1800", "600"]
        helper_prefix = "[42][info][arguments] "
        helper_flags = helper_argv[3] + " -Xlog:arguments=info:file=" + \
            helper_path + ":pid,level,tags:filecount=0"
        def helper_log(options):
            return ("\n".join(helper_prefix + row for row in (
                "VM Arguments:", "jvm_args: " + options,
                "java_command: " + " ".join(helper_argv[6:]),
                "java_class_path (initial): " + helper_argv[5],
                "Launcher Type: SUN_STANDARD")) + "\n").encode()
        verify_helper_startup(helper_log(helper_flags), 42, helper_argv, helper_path)
        for option in ("-javaagent:/home/other.jar", "-agentlib:other=1"):
            with self.subTest(option=option), self.assertRaises(FocusedRejected):
                verify_helper_startup(helper_log(helper_flags + " " + option), 42,
                                      helper_argv, helper_path)

    def test_full_mirror_requires_order_and_final_newline(self):
        xml = (b'<testsuite><system-out>first\nsecond\n'
               b'</system-out></testsuite>')
        self.assertEqual(_xml_mirror({"xml": xml, "mirror": b"first\nsecond\n"}),
                         hashlib.sha256(b"first\nsecond\n").hexdigest())
        for changed in (b"second\nfirst\n", b"first\nsecond", b"first\nSECOND\n"):
            with self.subTest(mirror=changed), self.assertRaises(FocusedRejected):
                _xml_mirror({"xml": xml, "mirror": changed})

    def test_duplicate_compiled_provider_and_engine_shadow_fail(self):
        def packed(entries):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for name, value in sorted(entries):
                    item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    item.compress_type = zipfile.ZIP_STORED
                    archive.writestr(item, value)
            return output.getvalue()

        artifact = packed([("org/dyn4j/geometry/Transform.class", b"engine")])
        base = [("main/portable/NumericalRecorder.class", b"recorder"),
                ("test/portable/NumericProbeMatrixTest.class", b"probe"),
                ("test/portable/PortableMatrixTest.class", b"matrix")]
        good = packed(base + [("test/portable/Fixture.class", b"fixture")])
        expected, _ = _expected_classes({"portable_classes": good,
                                         "artifact": artifact})
        self.assertEqual(expected["org/dyn4j/geometry/Transform"], b"engine")
        for duplicate in (
                [("test/portable/Fixture.class", b"fixture"),
                 ("main/portable/Fixture.class", b"shadow")],
                [("test/org/dyn4j/geometry/Transform.class", b"shadow")]):
            with self.subTest(duplicate=duplicate), self.assertRaises(FocusedRejected):
                _expected_classes({"portable_classes": packed(base + duplicate),
                                   "artifact": artifact})

    def test_public_replay_compares_exact_case_after_validated_whole_lane(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            archive = root / "capture"
            lane = root / "jvm"
            baseline = root / "baseline"
            attestation = root / "attestation.json"
            for path in (archive, lane / "cases", baseline):
                path.mkdir(parents=True)
            attestation.write_text("{}")
            case = b'{"id":"joint-Revolute-LimitsEnabled-false"}\n'
            name = "joint-Revolute-LimitsEnabled-false.jsonl"
            (archive / name).write_bytes(case)
            (lane / "cases" / name).write_bytes(case)
            (archive / "receipt.json").write_bytes(b"receipt\n")
            (lane / "receipt.json").write_text(json.dumps({
                "candidate_commit": "a" * 40,
                "artifact_sha256": {"target": "b" * 64},
                "runtime": {"executable_sha256": "c" * 64}}))
            focused = {"candidate_commit": "a" * 40,
                       "source_archive_sha256": "d" * 64,
                       "artifact_sha256": "b" * 64,
                       "runtime_sha256": "c" * 64,
                       "case_sha256": hashlib.sha256(case).hexdigest()}
            with patch("actual_capture_receipt.compare_host", return_value={
                    "status": "FAILED_PHYSICAL",
                    "candidate_source_sha256": "d" * 64}) as whole, \
                    patch("actual_capture_receipt.replay_version6",
                          return_value=focused), \
                    patch("actual_capture_receipt.comparison_coverage",
                          return_value={"frozen_case_ids": ["frozen"]}):
                result = verify_existing(archive, lane, baseline, attestation)
            self.assertEqual(result["qualification"], "UNPASSED")
            self.assertEqual(result["whole_lane_status"], "FAILED_PHYSICAL")
            self.assertIsNone(whole.call_args.kwargs["arithmetic_captures"])
            (lane / "cases" / name).write_bytes(case + b" ")
            with patch("actual_capture_receipt.compare_host", return_value={
                    "status": "FAILED_PHYSICAL",
                    "candidate_source_sha256": "d" * 64}), \
                    patch("actual_capture_receipt.replay_version6",
                          return_value=focused), \
                    patch("actual_capture_receipt.comparison_coverage",
                          return_value={"frozen_case_ids": ["frozen"]}):
                with self.assertRaises(FocusedRejected):
                    verify_existing(archive, lane, baseline, attestation)

    def test_version6_inventory_and_old_status_forgery_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            for name in FILE_NAMES.values():
                (root / name).write_bytes(b"raw")
            (root / "worker-class-load-41.log").write_bytes(b"class")
            (root / "worker-arguments-41.log").write_bytes(b"arguments")
            receipt = root / "receipt.json"
            receipt.write_text('{"schema":"portable-arithmetic-capture-receipt/5",'
                               '"status":"PASSED_FOCUSED_METHOD_EVIDENCE"}')
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)
            receipt.write_text('{"schema":"portable-arithmetic-capture-receipt/6",'
                               '"schema":"portable-arithmetic-capture-receipt/6"}')
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)
            receipt.write_text('{"schema":"portable-arithmetic-capture-receipt/6"}')
            self.assertEqual(load_version6_archive(root)[0]["schema"],
                             "portable-arithmetic-capture-receipt/6")
            (root / "extra.txt").write_bytes(b"extra")
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)
            (root / "extra.txt").unlink()
            (root / "mirror.log").unlink()
            (root / "mirror.log").symlink_to(root / "capture.xml")
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)

    def test_version6_loader_rejects_oversized_observer_before_reading_it(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            root = Path(directory)
            for name in FILE_NAMES.values():
                path = root / name
                if name != FILE_NAMES["output_observer_traces"]:
                    path.write_bytes(b"safe")
            for name in ("worker-class-load-42.log", "worker-arguments-42.log"):
                (root / name).write_bytes(b"safe")
            (root / "receipt.json").write_text(
                json.dumps({"schema": "portable-arithmetic-capture-receipt/6"}))
            observer = root / FILE_NAMES["output_observer_traces"]
            with observer.open("wb") as stream:
                stream.truncate(128 * 1024 * 1024 + 1)
            with patch.object(Path, "read_bytes",
                              side_effect=AssertionError(
                                  "observer read_bytes is unbounded")) as read_bytes:
                with self.assertRaisesRegex(
                        FocusedRejected, "observer archive exceeds compressed size limit"):
                    load_version6_archive(root)
            read_bytes.assert_not_called()
            observer.write_bytes(b"safe")
            original_open = Path.open

            def grown_open(path, *args, **kwargs):
                if path == observer:
                    return io.BytesIO(b"x" * 11)
                return original_open(path, *args, **kwargs)

            with patch.object(actual_output_v6, "MAX_OBSERVER_ARCHIVE_BYTES", 10), \
                    patch.object(Path, "open", grown_open):
                with self.assertRaisesRegex(
                        FocusedRejected, "observer archive exceeds compressed size limit"):
                    load_version6_archive(root)

    def test_boolean_only_root_still_fails_global_method_inventory(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            (root / "captureRevoluteLimitsFalse").mkdir()
            with self.assertRaisesRegex(Rejected, "method inventory"):
                verify_arithmetic_captures(root, root, "a" * 40,
                                           "b" * 64, "c" * 64)

    def test_public_replay_validates_whole_lane_first_without_capture_override(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            archive = root / "capture"
            lane = root / "jvm"
            baseline = root / "baseline"
            attestation = root / "attestation.json"
            for path in (archive, lane, baseline):
                path.mkdir()
            attestation.write_text("{}")
            (lane / "receipt.json").write_text(json.dumps({
                "candidate_commit": "a" * 40, "artifact_sha256": {"target": "b" * 64},
                "runtime": {"executable_sha256": "c" * 64}}))
            order = []

            def whole(*args, **kwargs):
                order.append("whole")
                self.assertIsNone(kwargs["arithmetic_captures"])
                return {"candidate_source_sha256": "d" * 64,
                        "operation_binding": "UNPASSED_NOT_EXECUTED"}

            def focused(*args, **kwargs):
                order.append("focused")
                return {"candidate_commit": "a" * 40,
                        "source_archive_sha256": "d" * 64,
                        "artifact_sha256": "b" * 64,
                        "runtime_sha256": "c" * 64,
                        "case_sha256": "e" * 64}

            with patch("actual_capture_receipt.compare_host", side_effect=whole), \
                    patch("actual_capture_receipt.replay_version6", side_effect=focused), \
                    patch("actual_capture_receipt.comparison_coverage",
                          return_value={"frozen_case_ids": ["frozen"]}):
                with self.assertRaises(FocusedRejected):
                    verify_existing(archive, lane, baseline, attestation)
            self.assertEqual(order, ["whole", "focused"])


class FocusedWorkerIdentityProofTest(unittest.TestCase):
    class ProofContinued(Exception):
        pass

    @staticmethod
    def _metadata(worker_pid):
        keys = (
            "schema", "command", "trace_arguments", "response_path", "agent_path",
            "witness_path", "mirror_path", "class_load_path", "argument_path",
            "agent_identity", "witness_identity", "mirror_identity",
            "argument_identity", "class_load_identity", "response_identity",
            "agent_after_identity", "artifact_identity", "artifact_after_identity",
            "runtime_identity", "runtime_after_identity", "launcher_identity",
            "launcher_after_identity", "launcher_sha256", "helper_class_before",
            "helper_class_after", "helper_argument_path", "helper_argument_identity",
            "observer_interpreter_path", "observer_interpreter_identity",
            "observer_interpreter_after_identity", "observer_interpreter_sha256",
            "observer_command", "observer_environment_sha256", "observer_exit_code",
            "worker_pid", "exit_code")
        metadata = dict.fromkeys(keys)
        metadata.update({
            "schema": "focused-arithmetic-capture/6",
            "trace_arguments": focused_receipt.rich_trace_arguments(),
            "worker_pid": worker_pid,
            "exit_code": 0,
        })
        return metadata

    def _run_proof(self, selected_pid, metadata_pid, legacy_pid):
        trace = (
            f'1.000001 execve("{focused_receipt._PINNED_JAVA}", '
            '["java", "worker.org.gradle.process.internal.worker.GradleWorkerMain", "1"], '
            '0x0) = 0\n').encode()
        with patch.object(focused_receipt, "verify_build_runtime",
                          side_effect=self.ProofContinued):
            focused_receipt._proof(
                {}, {"worker_pid": legacy_pid}, self._metadata(metadata_pid), {},
                {selected_pid: trace}, [], {}, {}, [], {}, {}, [], {})

    def test_matching_producer_pid_representations_pass_identity_condition(self):
        with self.assertRaises(self.ProofContinued):
            self._run_proof("41", 41, "41")

    def test_each_independently_wrong_worker_identity_is_rejected(self):
        for selected_pid, metadata_pid, legacy_pid in (
                ("42", 41, "41"), ("41", 42, "41"), ("41", 41, "42")):
            with self.subTest(selected=selected_pid, metadata=metadata_pid,
                              legacy=legacy_pid), \
                    self.assertRaisesRegex(FocusedRejected,
                                           "selected worker identity differs"):
                self._run_proof(selected_pid, metadata_pid, legacy_pid)

    def test_worker_identity_rejects_noncanonical_or_nonpositive_values(self):
        invalid_selected = ("0", "-41", "+41", " 41", "041", "４１")
        for selected_pid in invalid_selected:
            with self.subTest(source="selected", pid=selected_pid), \
                    self.assertRaisesRegex(FocusedRejected,
                                           "selected worker identity differs"):
                self._run_proof(selected_pid, 41, selected_pid)

        for metadata_pid in (True, 41.0, 0, -41):
            with self.subTest(source="metadata", pid=metadata_pid), \
                    self.assertRaisesRegex(FocusedRejected,
                                           "selected worker identity differs"):
                self._run_proof("41", metadata_pid, "41")

        invalid_legacy = (True, 41.0, 0, -41, "0", "-41", "+41", " 41", "041", "４１")
        for legacy_pid in invalid_legacy:
            with self.subTest(source="legacy", pid=legacy_pid), \
                    self.assertRaisesRegex(FocusedRejected,
                                           "selected worker identity differs"):
                self._run_proof("41", 41, legacy_pid)


if __name__ == "__main__":
    unittest.main()
