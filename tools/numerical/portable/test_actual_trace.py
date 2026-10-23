import io
import unittest
import zipfile

from actual_trace import checked_projection, TraceRejected


def archived(rows):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in rows.items():
            archive.writestr(name, value)
    return output.getvalue()


class ActualTraceTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
