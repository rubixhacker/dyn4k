import hashlib
import io
import struct
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch

import actual_trace
from actual_trace import checked_projection, TraceRejected, trace_exposes_environment
from boolean_rotation_jdi.jdi_bridge import verify_jdi_file_writes


def archived(rows):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in rows.items():
            archive.writestr(name, value)
    return output.getvalue()


class ActualTraceTest(unittest.TestCase):
    def test_structural_identity_ignores_quoted_live_descriptor_text(self):
        protected = "/home/test/protected-output"
        mentioned = f"7<{protected}>"
        prefix = (b'1.000001 openat(AT_FDCWD, "/usr/lib/loader", O_RDONLY) = '
                  b'7</usr/lib/loader>\n')
        payload = (f'1.000002 write(1<pipe:[8]>, "{mentioned}", '
                   f'{len(mentioned)}) = {len(mentioned)}\n').encode()
        suffix = (b'1.000003 close(7</usr/lib/loader>) = 0\n'
                  b'1.000004 +++ exited with 0 +++\n')
        for strict in (False, True):
            with self.subTest(version6_raw=strict):
                good = checked_projection(
                    archived({"trace.41": prefix + payload + suffix}),
                    (protected,), version6_raw=strict)
                self.assertEqual(good["threads"], 1)
                changed = (f'1.000002 read(7<{protected}>, "x", 1) = 1\n').encode()
                with self.assertRaisesRegex(TraceRejected,
                                            "protected descriptor"):
                    checked_projection(
                        archived({"trace.41": prefix + changed + suffix}),
                        (protected,), version6_raw=strict)

    def test_connected_socket_projection_keeps_complete_call(self):
        calls = (
            b'write(56<TCPv6:[[::ffff:127.0.0.1]:1234->[::ffff:127.0.0.1]:5678]>, "a->b", 4) = 4',
            b'write(57<TCP:[127.0.0.1:1234->127.0.0.1:5678]>, "ok", 2) = 2',
            b'listen(58<TCP:[127.0.0.1:1234]>, 16) = 0',
        )
        trace = b"".join(f"1.{index:06d} ".encode() + call + b"\n"
                         for index, call in enumerate(calls, 1)) + \
                b"1.000004 +++ exited with 0 +++\n"
        result = checked_projection(archived({"trace.41": trace}), version6_raw=True)
        with zipfile.ZipFile(io.BytesIO(result["legacy_zip"])) as projected:
            self.assertEqual(projected.read("trace.41").splitlines(), [
                b'write(56, "a->b", 4) = 4',
                b'write(57, "ok", 2) = 2',
                b'listen(58, 16) = 0',
                b'+++ exited with 0 +++',
            ])

    def test_version6_descriptor_projection_rejects_incomplete_socket_tokens(self):
        good = b'1.000001 write(56<TCPv6:[[::1]:1234->[::1]:5678]>, "<->", 3) = 3\n'
        good += b'1.000002 +++ exited with 0 +++\n'
        result = checked_projection(archived({"trace.41": good}), version6_raw=True)
        with zipfile.ZipFile(io.BytesIO(result["legacy_zip"])) as projected:
            self.assertIn(b'write(56, "<->", 3) = 3', projected.read("trace.41"))
        for changed in (
                good.replace(b'5678]>', b'5678>'),
                good.replace(b'5678]>', b'5678]>>'),
                good.replace(b'5678]>', b'5678]>tail'),
                good.replace(b'1234->[', b'1234-><['),
                good.replace(b'5678]>', b'5678]>, 99<')):
            with self.subTest(changed_hash=hashlib.sha256(changed).hexdigest()), \
                    self.assertRaises(TraceRejected):
                checked_projection(archived({"trace.41": changed}), version6_raw=True)

    def test_version6_projects_observed_native_descriptor_shapes(self):
        calls = (
            b'dup2(7<pipe:[12345]>, 8</dev/null<char 1:3>>) = 8<pipe:[12345]>',
            b'close(9<anon_inode:[eventpoll]>) = 0',
            b'close(16<anon_inode:inotify>) = 0',
            b'close(10<{eventfd-count=0, eventfd-id=12, eventfd-semaphore=0}>) = 0',
            b'close(17<{eventfd-count=0x0, eventfd-id=13, eventfd-semaphore=0}>) = 0',
            b'close(11<UNIX-STREAM:[123->456]>) = 0',
            b'close(12<UDPv6:[[::1]:4000]>) = 0',
            b'fstat(13</tmp/old>(deleted), {st_mode=S_IFREG}) = 0',
            b'openat(AT_FDCWD</tmp>, "/tmp/new", O_RDONLY) = 14</tmp/new>',
            b'write(15<TCPv6:[[::1]:4000->[::1]:5000]>, "<char 1:3> ->", 13) = 13',
        )
        trace = b"".join(f"1.{index:06d} ".encode() + call + b"\n"
                         for index, call in enumerate(calls, 1))
        trace += b"1.000011 +++ exited with 0 +++\n"
        result = checked_projection(archived({"trace.41": trace}), version6_raw=True)
        expected = (
            b'dup2(7, 8) = 8', b'close(9) = 0', b'close(16) = 0',
            b'close(10) = 0', b'close(17) = 0',
            b'close(11) = 0', b'close(12) = 0',
            b'fstat(13, {st_mode=S_IFREG}) = 0',
            b'openat(AT_FDCWD, "/tmp/new", O_RDONLY) = 14',
            b'write(15, "<char 1:3> ->", 13) = 13',
            b'+++ exited with 0 +++',
        )
        with zipfile.ZipFile(io.BytesIO(result["legacy_zip"])) as projected:
            self.assertEqual(projected.read("trace.41").splitlines(), list(expected))

    def test_version6_rejects_malformed_native_descriptor_neighbors(self):
        call = b'dup2(7<pipe:[12345]>, 8</dev/null<char 1:3>>) = 8<pipe:[12345]>'
        bad_calls = (
            call.replace(b'<char 1:3>', b'<char 1:3'),
            call.replace(b'<char 1:3>', b'<char 1:3><char 1:3>'),
            call.replace(b'<char 1:3>', b'<block X:Y>'),
            call.replace(b'8</dev/null<char 1:3>>', b'8</dev/null<char 1:3>>tail'),
            call.replace(b'8</dev/null<char 1:3>>', b'8</dev/null<char 1:3>>9<pipe:[5]>'),
            call.replace(b'8</dev/null<char 1:3>>', b'8</dev/null<char 1:3>> 9<pipe:[5]>'),
            call.replace(b'8</dev/null<char 1:3>>', b'8</dev/"null<char 1:3>>'),
            b'close(7<UNIX-STREAM:[12->]>) = 0',
            b'close(7<anon_inode:[]>) = 0',
            b'close(7<{eventfd-count=0, eventfd-id=12}>) = 0',
            b'close(7<{eventfd-count=0xg, eventfd-id=12, eventfd-semaphore=0}>) = 0',
            b'close(7</tmp/file>(renamed)) = 0',
            b'openat(AT_FDCWD</tmp>junk, "/tmp/new", O_RDONLY) = 14</tmp/new>',
        )
        for bad in bad_calls:
            trace = b"1.000001 " + bad + b"\n1.000002 +++ exited with 0 +++\n"
            with self.subTest(call_sha256=hashlib.sha256(bad).hexdigest()), \
                    self.assertRaises(TraceRejected):
                checked_projection(archived({"trace.41": trace}), version6_raw=True)

    def test_version6_raw_limits_and_legacy_selection(self):
        line = b"1.000001 +++ exited with 0 +++\n"
        one = archived({"trace.41": line})
        self.assertEqual(actual_trace.V6_RAW_MAX_BYTES, 268435456)
        self.assertEqual(actual_trace.V6_RAW_MAX_MEMBERS, 1024)
        self.assertEqual(actual_trace.V6_RAW_MAX_LINES, 2000000)
        self.assertEqual(actual_trace.V6_RAW_MAX_RECORD_BYTES, 1048576)
        self.assertEqual(checked_projection(one, version6_raw=True)["threads"], 1)
        with patch.object(actual_trace, "V6_RAW_MAX_BYTES", len(one)):
            self.assertEqual(checked_projection(one, version6_raw=True)["threads"], 1)
        with patch.object(actual_trace, "V6_RAW_MAX_BYTES", len(one) - 1):
            with self.assertRaises(TraceRejected):
                checked_projection(one, version6_raw=True)
            self.assertEqual(checked_projection(one)["threads"], 1)

    def test_version6_raw_independent_inventory_limits(self):
        line = b"1.000001 +++ exited with 0 +++\n"
        two = archived({"trace.41": line, "trace.42": line})
        with patch.object(actual_trace, "V6_RAW_MAX_MEMBERS", 1), \
                patch.object(actual_trace, "V6_RAW_MAX_LINES", 1), \
                patch.object(actual_trace, "V6_RAW_MAX_RECORD_BYTES", len(line)):
            self.assertEqual(checked_projection(archived({"trace.41": line}),
                                                version6_raw=True)["threads"], 1)
        with patch.object(actual_trace, "V6_RAW_MAX_MEMBERS", 1):
            with self.assertRaisesRegex(TraceRejected, "member"):
                checked_projection(two, version6_raw=True)
        with patch.object(actual_trace, "V6_RAW_MAX_LINES", 1):
            with self.assertRaisesRegex(TraceRejected, "line"):
                checked_projection(two, version6_raw=True)
        with patch.object(actual_trace, "V6_RAW_MAX_RECORD_BYTES", len(line) - 1):
            with self.assertRaisesRegex(TraceRejected, "record"):
                checked_projection(two, version6_raw=True)

        repeated = line * 20
        compressed = io.BytesIO()
        with zipfile.ZipFile(compressed, "w", compression=zipfile.ZIP_DEFLATED) as out:
            out.writestr("trace.41", repeated)
        packed = compressed.getvalue()
        self.assertLess(len(packed), len(repeated))
        with patch.object(actual_trace, "V6_RAW_MAX_BYTES", len(packed) + 1):
            with self.assertRaisesRegex(TraceRejected, "decoded"):
                checked_projection(packed, version6_raw=True)
        with zipfile.ZipFile(io.BytesIO(packed)) as reader, \
                patch.object(actual_trace, "V6_RAW_MAX_BYTES", len(repeated)):
            self.assertEqual(len(actual_trace.validate_version6_raw_archive(
                packed, reader)), 1)

        changed = bytearray(archived({"trace.41": line}))
        central = changed.index(b"PK\x01\x02")
        struct.pack_into("<I", changed, central + 24, len(line) + 1)
        with self.assertRaisesRegex(TraceRejected, "decoded size"):
            checked_projection(bytes(changed), version6_raw=True)

        duplicate = io.BytesIO()
        with zipfile.ZipFile(duplicate, "w") as output:
            output.writestr("trace.41", line)
            output.writestr("trace.41", line)
        with self.assertRaisesRegex(TraceRejected, "member"):
            checked_projection(duplicate.getvalue(), version6_raw=True)

    def test_privacy_decoder_rejects_escaped_pairs_and_keys(self):
        for token in (b'DYN4K_CAPTURE_ENV_SENTINEL\\x3dportable-capture-check',
                      b'OLLAMA_\\x41PI_KEY'):
            raw = b'1.000001 write(4, "' + token + b'", 55) = 55\n'
            with self.subTest(token=token):
                self.assertTrue(trace_exposes_environment(raw))
        self.assertFalse(trace_exposes_environment(
            b'1.000001 write(4, "portable-capture-check", 22) = 22\n'))
        with self.assertRaisesRegex(TraceRejected, "exposed the environment"):
            checked_projection(archived({"trace.41":
                b'1.000001 write(4, "OLLAMA_\\x41PI_KEY", 14) = 14\n'
                b'1.000002 +++ exited with 0 +++\n'}))

    def test_rich_trace_is_checked_before_legacy_projection(self):
        trace = (
            b'1.000001 execve("/jdk/java", ["java"], 0x7f) = 0\n'
            b'1.000002 openat(AT_FDCWD, "/home/input", O_RDONLY) = 7</home/input>\n'
            b'1.000003 read(7</home/input>, "abc", 3) = 3\n'
            b'1.000004 close(7</home/input>) = 0\n'
            b'1.000005 +++ exited with 0 +++\n')
        good = archived({"trace.41": trace})
        projected = checked_projection(good, {"/home/input"})
        with zipfile.ZipFile(io.BytesIO(projected["legacy_zip"])) as archive:
            self.assertIn(b'read(7, "abc", 3) = 3', archive.read("trace.41"))
        self.assertEqual(len(projected["raw_sha256"]), 64)
        for bad in (
            trace.replace(b"1.000003", b"0.000003"),
            trace.replace(b"read(7</home/input>", b"mystery(7</home/input>"),
            trace.replace(b"close(7</home/input>)", b"dup2(8, 7</home/input>)"),
        ):
            with self.subTest(bad=bad[:90]), self.assertRaises(TraceRejected):
                checked_projection(archived({"trace.41": bad}), {"/home/input"})

    def test_split_socket_call_requires_matching_completion_or_terminal_exit(self):
        paired = archived({"trace.41":
            b"1.000001 accept(5,  <unfinished ...>\n"
            b"1.000002 <... accept resumed>NULL, NULL) = 7\n"
            b"1.000003 +++ exited with 0 +++\n"})
        self.assertEqual(checked_projection(paired)["aborted_calls"], 0)
        aborted = archived({"trace.41":
            b"1.000001 accept(5,  <unfinished ...>\n"
            b"1.000002 +++ exited with 0 +++\n"})
        self.assertEqual(checked_projection(aborted)["aborted_calls"], 1)
        terminal = archived({"trace.41":
            b"1.000001 accept(5<TCP:[127.0.0.1:40001]> <unfinished ...>) = ?\n"
            b"1.000002 +++ exited with 0 +++\n"})
        self.assertEqual(checked_projection(terminal)["aborted_calls"], 1)
        for bad in (
            b"1.000001 accept(5,  <unfinished ...>\n"
            b"1.000002 <... connect resumed>NULL, NULL) = 7\n",
            b"1.000001 accept(5,  <unfinished ...>\n",
            b"1.000001 <... accept resumed>NULL, NULL) = 7\n"):
            with self.subTest(bad=bad), self.assertRaises(TraceRejected):
                checked_projection(archived({"trace.41": bad}))

    def test_protected_descriptor_requires_continuous_decoration(self):
        prefix = (b'1.000001 openat(AT_FDCWD, "/home/output", O_WRONLY|O_CREAT) '
                  b'= 7</home/output>\n')
        good = (prefix + b'1.000002 write(7</home/output>, "abc", 3) = 3\n'
                b'1.000003 close(7</home/output>) = 0\n'
                b'1.000004 +++ exited with 0 +++\n')
        self.assertEqual(checked_projection(archived({"trace.41": good}),
                                            {"/home/output"})["threads"], 1)
        for changed in (
                good.replace(b'write(7</home/output>', b'write(7'),
                good.replace(b'close(7</home/output>', b'close(7'),
                good.replace(b'write(7</home/output>', b'write(7</home/other>'),
                good.replace(b'= 7</home/output>', b'= 7</home/other>', 1),
                good.replace(b'write(7</home/output>, "abc", 3) = 3',
                             b'dup2(8</home/other>, 7</home/output>) = 7</home/other>\n'
                             b'1.000002 write(7</home/other>, "abc", 3) = 3')):
            with self.subTest(changed=changed), self.assertRaises(TraceRejected):
                checked_projection(archived({"trace.41": changed}), {"/home/output"})

    def test_aborted_accept_keeps_raw_timestamp_and_terminal_order(self):
        good = (b'1.000001 accept(5,  <unfinished ...>\n'
                b'1.000002 +++ exited with 0 +++\n')
        self.assertEqual(checked_projection(archived({"trace.41": good}))[
                         "aborted_calls"], 1)
        for bad in (
                good.replace(b'1.000001 accept', b'2.000001 accept'),
                good + b'1.000003 write(5, "x", 1) = 1\n',
                good.replace(b'1.000002 +++ exited', b'1.000000 +++ exited')):
            with self.subTest(bad=bad), self.assertRaises(TraceRejected):
                checked_projection(archived({"trace.41": bad}))

    def test_shared_and_duplicated_protected_descriptor_lifecycle(self):
        parent = (
            b'1.000001 openat(AT_FDCWD, "/home/output", O_WRONLY|O_CREAT) '
            b'= 7</home/output>\n'
            b'1.000002 dup(7</home/output>) = 8</home/output>\n'
            b'1.000003 clone3({flags=CLONE_VM|CLONE_FILES|CLONE_THREAD, '
            b'exit_signal=0}, 88) = 42\n'
            b'1.000008 +++ exited with 0 +++\n')
        child = (
            b'1.000004 write(8</home/output>, "ok", 2) = 2\n'
            b'1.000005 close_range(7, 8, 0) = 0\n'
            b'1.000006 openat(AT_FDCWD, "/home/other", O_WRONLY) = 7</home/other>\n'
            b'1.000007 write(7</home/other>, "x", 1) = 1\n'
            b'1.000009 +++ exited with 0 +++\n')
        self.assertEqual(checked_projection(archived({"trace.41": parent,
                                                     "trace.42": child}),
                                            {"/home/output"})["threads"], 2)
        for changed in (
                child.replace(b'write(8</home/output>', b'write(8'),
                child.replace(b'write(8</home/output>', b'write(8</home/other>'),
                child.replace(b'close_range(7, 8, 0)', b'close_range(7, 8, CLOSE_RANGE_UNSHARE)'),
                child.replace(b'close_range(7, 8, 0) = 0',
                              b'dup2(7</home/output>, 8) = 8</home/output>')):
            with self.subTest(changed=changed), self.assertRaises(TraceRejected):
                checked_projection(archived({"trace.41": parent,
                                             "trace.42": changed}), {"/home/output"})
        unbound_alias = (
            b'1.000001 dup(7</home/output>) = 8</home/output>\n'
            b'1.000002 write(8</home/output>, "x", 1) = 1\n'
            b'1.000003 +++ exited with 0 +++\n')
        with self.assertRaises(TraceRejected):
            checked_projection(archived({"trace.41": unbound_alias}), {"/home/output"})

    def test_transfer_operands_cannot_hide_protected_input(self):
        prefix = (b'1.000001 openat(AT_FDCWD, "/home/input", O_RDONLY) '
                  b'= 7</home/input>\n')
        suffix = (b'1.000004 close(7</home/input>) = 0\n'
                  b'1.000005 +++ exited with 0 +++\n')
        for good, bad in (
                (b'1.000002 sendfile(9<TCP:[1]>, 7</home/input>, NULL, 3) = 3\n',
                 b'1.000002 sendfile(9<TCP:[1]>, 7, NULL, 3) = 3\n'),
                (b'1.000002 copy_file_range(7</home/input>, [0], '
                 b'9</home/other>, [0], 3, 0) = 3\n',
                 b'1.000002 copy_file_range(7, [0], '
                 b'9</home/other>, [0], 3, 0) = 3\n'),
                (b'1.000002 mmap(NULL, 3, PROT_READ, MAP_SHARED, '
                 b'7</home/input>, 0) = 0x1000\n',
                 b'1.000002 mmap(NULL, 3, PROT_READ, MAP_SHARED, 7, 0) = 0x1000\n')):
            with self.subTest(good=good):
                checked_projection(archived({"trace.41": prefix + good + suffix}),
                                   {"/home/input"})
                with self.assertRaises(TraceRejected):
                    checked_projection(archived({"trace.41": prefix + bad + suffix}),
                                       {"/home/input"})

    def test_strict_output_rejects_valid_descriptor_redirection(self):
        target = "/home/output"
        prefix = (b'1.000001 openat(AT_FDCWD, "/home/output", O_WRONLY|O_CREAT|O_TRUNC) '
                  b'= 7</home/output>\n'
                  b'1.000002 openat(AT_FDCWD, "/home/other", O_WRONLY|O_CREAT|O_TRUNC) '
                  b'= 8</home/other>\n')
        suffix = (b'1.000004 write(7</home/other>, "abc", 3) = 3\n'
                  b'1.000005 close(7</home/other>) = 0\n'
                  b'1.000006 close(8</home/other>) = 0\n'
                  b'1.000007 +++ exited with 0 +++\n')
        transitions = (
            b'1.000003 dup2(8</home/other>, 7</home/output>) = 7</home/other>\n',
            b'1.000003 dup3(8</home/other>, 7</home/output>, O_CLOEXEC) = 7</home/other>\n',
            b'1.000003 fcntl(8</home/other>, F_DUPFD, 7) = 7</home/other>\n',
        )
        for transition in transitions:
            with self.subTest(transition=transition), self.assertRaises(TraceRejected):
                checked_projection(archived({"trace.41": prefix + transition + suffix}),
                                   {target}, strict_outputs={target})

    def test_strict_output_rejects_unmodelled_alias_and_close_range(self):
        prefix = (b'1.000001 openat(AT_FDCWD, "/home/output", O_WRONLY|O_CREAT) '
                  b'= 7</home/output>\n')
        for transition in (
            b'1.000002 dup(7</home/output>) = 8</home/output>\n',
            b'1.000002 close_range(7, 7, 0) = 0\n',
        ):
            with self.subTest(transition=transition), self.assertRaises(TraceRejected):
                checked_projection(archived({"trace.41": prefix + transition +
                    b'1.000003 +++ exited with 0 +++\n'}),
                    {"/home/output"}, strict_outputs={"/home/output"})

    def test_strict_output_rejects_shared_table_writer_in_other_thread(self):
        parent = (b'1.000001 openat(AT_FDCWD, "/home/output", O_WRONLY|O_CREAT) '
                  b'= 7</home/output>\n'
                  b'1.000002 clone3({flags=CLONE_VM|CLONE_FILES|CLONE_THREAD, '
                  b'exit_signal=0}, 88) = 42\n'
                  b'1.000004 write(7</home/output>, "abc", 3) = 3\n'
                  b'1.000005 close(7</home/output>) = 0\n'
                  b'1.000006 +++ exited with 0 +++\n')
        child = (b'1.000003 write(7</home/output>, "extra", 5) = 5\n'
                 b'1.000007 +++ exited with 0 +++\n')
        with self.assertRaises(TraceRejected):
            checked_projection(archived({"trace.41": parent, "trace.42": child}),
                               {"/home/output"}, strict_outputs={"/home/output"})

    def test_strict_output_rejects_uncredited_write_forms(self):
        prefix = (b'1.000001 openat(AT_FDCWD, "/home/output", O_WRONLY|O_CREAT) '
                  b'= 7</home/output>\n')
        suffix = (b'1.000003 close(7</home/output>) = 0\n'
                  b'1.000004 +++ exited with 0 +++\n')
        for operation in (
            b'1.000002 pwrite64(7</home/output>, "abc", 3, 0) = 3\n',
            b'1.000002 pwritev(7</home/output>, [{iov_base="abc", iov_len=3}], 1, 0) = 3\n',
            b'1.000002 writev(7</home/output>, [{iov_base="abc", iov_len=3}], 1) = 3\n',
        ):
            with self.subTest(operation=operation), self.assertRaises(TraceRejected):
                checked_projection(archived({"trace.41": prefix + operation + suffix}),
                                   {"/home/output"}, strict_outputs={"/home/output"})

    def test_strict_output_preserves_file_offset_before_byte_accounting(self):
        root = str(Path.home() / "focused-jdi-output")
        target = root + "/complete.txt"
        prefix = (f'1.000001 openat(AT_FDCWD, "{target}", '
                  f'O_WRONLY|O_CREAT|O_TRUNC, 0666) = 7<{target}>\n'
                  f'1.000002 write(7<{target}>, "abc", 3) = 3\n')
        suffix = (f'1.000004 write(7<{target}>, "def", 3) = 3\n'
                  f'1.000005 close(7<{target}>) = 0\n'
                  '1.000006 +++ exited with 0 +++\n')
        evidence = archived({"complete.txt": b"abcdef"})
        good = checked_projection(archived({"trace.41": (prefix + suffix).encode()}),
                                  {target}, strict_outputs={target})
        self.assertEqual(verify_jdi_file_writes(good["legacy_zip"], evidence, root)[
                         "files"], 1)
        for operation in (
            f'1.000003 lseek(7<{target}>, 0, SEEK_SET) = 0\n',
            f'1.000003 read(7<{target}>, "abc", 3) = 3\n',
        ):
            with self.subTest(operation=operation), self.assertRaises(TraceRejected):
                projected = checked_projection(
                    archived({"trace.41": (prefix + operation + suffix).encode()}),
                    {target}, strict_outputs={target})
                verify_jdi_file_writes(projected["legacy_zip"], evidence, root)


if __name__ == "__main__":
    unittest.main()
