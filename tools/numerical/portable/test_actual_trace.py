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


if __name__ == "__main__":
    unittest.main()
