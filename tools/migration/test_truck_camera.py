import hashlib
import json
import struct
import tempfile
import time
import unittest
import zlib
from pathlib import Path

from tools.migration.truck_camera import TruckRun
from tools.migration.truck_timeline import FOLLOW_PIXELS, FRAMES, validate


def _png_chunk(kind, data):
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def valid_png():
    header = struct.pack(">IIBBBBB", 1024, 768, 8, 2, 0, 0, 0)
    row = b"\x00" + b"\x00\x00\x00" * 1024
    pixels = zlib.compress(row * 768)
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header)
            + _png_chunk(b"IDAT", pixels) + _png_chunk(b"IEND", b""))


class TruckTimelineTest(unittest.TestCase):
    def make_evidence(self, directory):
        base = 1_000_000_000
        rows = []
        def add(kind, name, start, end, **extra):
            row = {"kind": kind, "name": name, "start_ns": base + start,
                   "end_ns": base + end, **extra}
            rows.append(row)
            if kind == "camera":
                for suffix, boundary in (("-position", start - 3), ("-down", start - 2),
                                         ("-up", end + 1)):
                    rows.append({"kind": "pointer", "name": name + suffix,
                                 "start_ns": base + boundary, "end_ns": base + boundary + 1})
            return row
        add("run", "Truck", 0, 0)
        add("camera", "setup", 100, 200, from_x=300, to_x=650, from_y=80, to_y=80)
        add("frame", "initial", 300, 400, file="initial.png")
        add("key", "keydown-Right", 900, 1000)
        add("frame", "drive-0", 1_010, 1_020, file="drive-0.png")
        for index, pixels in enumerate(FOLLOW_PIXELS, 1):
            when = 1000 + index * 500_000_000
            add("camera", "follow-%02d" % index, when, when + 10_000_000,
                from_x=650, to_x=650 - pixels, from_y=80, to_y=80)
            if index % 2 == 0:
                name = "drive-%d" % (index // 2)
                add("frame", name, when + 20_000_000, when + 30_000_000, file=name + ".png")
        right_up = 1000 + 7_000_000_000
        add("key", "keyup-Right", right_up, right_up + 10_000_000)
        add("frame", "drive", right_up + 20_000_000, right_up + 30_000_000, file="drive.png")
        brake_down = right_up + 40_000_000
        add("key", "keydown-s", brake_down, brake_down + 10_000_000)
        add("camera", "brake-follow-1", brake_down + 410_000_000,
            brake_down + 420_000_000, from_x=650, to_x=530, from_y=80, to_y=80)
        add("frame", "brake-mid", brake_down + 510_000_000,
            brake_down + 520_000_000, file="brake-mid.png")
        add("camera", "brake-follow-2", brake_down + 810_000_000,
            brake_down + 820_000_000, from_x=650, to_x=530, from_y=240, to_y=80)
        brake_up = brake_down + 1_010_000_000
        add("key", "keyup-s", brake_up, brake_up + 10_000_000)
        add("frame", "after-input", brake_up + 20_000_000,
            brake_up + 30_000_000, file="after-input.png")
        png = valid_png()
        for name in FRAMES:
            (directory / (name + ".png")).write_bytes(png)
            frame = next(row for row in rows if row["kind"] == "frame" and row["name"] == name)
            add("frame_hash", name, frame["end_ns"] - base,
                frame["end_ns"] - base + 1, file=name + ".png", sha256=hashlib.sha256(png).hexdigest())
        return rows

    def write_rows(self, directory, rows):
        (directory / "truck-timeline.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows))

    def test_complete_timeline_reports_integrity_without_visual_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            rows = self.make_evidence(directory)
            self.write_rows(directory, rows)
            passed, evidence = validate(directory)
            self.assertTrue(passed, evidence)
            self.assertIn("visual review separate", evidence)

    def test_missing_late_or_wrong_scene_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            rows = self.make_evidence(directory)
            for change in ("missing", "late", "scene", "short", "extended"):
                changed = [dict(row) for row in rows]
                if change == "missing":
                    changed = [row for row in changed if not (row["kind"] == "frame" and row["name"] == "drive-4")]
                elif change == "late":
                    next(row for row in changed if row["kind"] == "frame" and row["name"] == "drive-4")["start_ns"] += 300_000_000
                elif change == "scene":
                    changed[0]["name"] = "Crank"
                else:
                    row = next(row for row in changed if row["kind"] == "key" and row["name"] == "keyup-s")
                    row["start_ns"] += -500_000_000 if change == "short" else 500_000_000
                    row["end_ns"] += -500_000_000 if change == "short" else 500_000_000
                self.write_rows(directory, changed)
                self.assertFalse(validate(directory)[0], change)

    def test_pointer_gesture_rejects_reversal_overlap_and_wrong_association(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            rows = self.make_evidence(directory)
            camera = next(row for row in rows if row["kind"] == "camera" and row["name"] == "follow-01")
            down = next(row for row in rows if row["kind"] == "pointer" and row["name"] == "follow-01-down")
            down["start_ns"] = camera["end_ns"] + 1
            down["end_ns"] = down["start_ns"] + 1
            self.write_rows(directory, rows)
            self.assertFalse(validate(directory)[0], "press after its camera move")

            rows = self.make_evidence(directory)
            position = next(row for row in rows if row["kind"] == "pointer" and row["name"] == "follow-01-position")
            down = next(row for row in rows if row["kind"] == "pointer" and row["name"] == "follow-01-down")
            position["end_ns"] = down["start_ns"] + 1
            self.write_rows(directory, rows)
            self.assertFalse(validate(directory)[0], "overlapping position and press")

            rows = self.make_evidence(directory)
            up = next(row for row in rows if row["kind"] == "pointer" and row["name"] == "follow-01-up")
            up["name"] = "follow-02-up"
            self.write_rows(directory, rows)
            self.assertFalse(validate(directory)[0], "release associated with another gesture")

    def test_pointer_gesture_rejects_missing_or_duplicate_intervals(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            rows = self.make_evidence(directory)
            rows = [row for row in rows if row["name"] != "follow-01-position"]
            self.write_rows(directory, rows)
            self.assertFalse(validate(directory)[0], "missing position event")

            rows = self.make_evidence(directory)
            release = next(row for row in rows if row["kind"] == "pointer" and row["name"] == "follow-01-up")
            rows.append(dict(release))
            self.write_rows(directory, rows)
            self.assertFalse(validate(directory)[0], "duplicate release event")

    def test_camera_gesture_may_overlap_timestamped_key_release(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            rows = self.make_evidence(directory)
            camera = next(row for row in rows if row["kind"] == "camera" and row["name"] == "follow-13")
            key_up = next(row for row in rows if row["kind"] == "key" and row["name"] == "keyup-Right")
            pointer_up = next(row for row in rows if row["kind"] == "pointer" and row["name"] == "follow-13-up")
            camera["end_ns"] = key_up["start_ns"] + 1
            pointer_up["start_ns"] = camera["end_ns"]
            pointer_up["end_ns"] = pointer_up["start_ns"] + 1
            self.write_rows(directory, rows)
            self.assertTrue(validate(directory)[0])

    def test_png_requires_complete_valid_pixels_crc_and_bounded_size(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            rows = self.make_evidence(directory)
            self.write_rows(directory, rows)
            self.assertTrue(validate(directory)[0], "complete generated PNG")

            original = valid_png()
            corrupt_payload = bytearray(original)
            corrupt_payload[41] ^= 1
            idat_crc = 41 + int.from_bytes(original[33:37], "big")
            corrupt_payload[idat_crc:idat_crc + 4] = zlib.crc32(
                corrupt_payload[37:idat_crc]).to_bytes(4, "big")
            cases = {
                "truncated": original[:-12],
                "corrupt IDAT payload": bytes(corrupt_payload),
                "corrupt IDAT CRC": original[:-16] + bytes([original[-16] ^ 1]) + original[-15:],
                "malformed chunk": original[:33] + b"\xff\xff\xff\xff" + original[37:],
                "oversized": original + b"x" * (16 * 1024 * 1024),
            }
            digest = next(row for row in rows if row["kind"] == "frame_hash" and row["name"] == "initial")
            path = directory / "initial.png"
            for name, data in cases.items():
                path.write_bytes(data)
                digest["sha256"] = hashlib.sha256(data).hexdigest()
                self.write_rows(directory, rows)
                self.assertFalse(validate(directory)[0], name)

    def test_slow_camera_work_does_not_extend_key_hold(self):
        with tempfile.TemporaryDirectory() as temp:
            run = TruckRun("1", temp)
            def fake_xdotool(kind, name, *args, **details):
                start = time.monotonic_ns()
                return run.record(kind, name, start, time.monotonic_ns(), **details)
            run.xdotool = fake_xdotool
            work_end = []
            def slow_work(start, deadline):
                time.sleep(0.35)
                work_end.append(time.monotonic_ns())
            run.hold("Right", 100_000_000, slow_work)
            rows = [json.loads(line) for line in run.timeline.read_text().splitlines()]
            release = next(row for row in rows if row["name"] == "keyup-Right")
            self.assertLess(release["end_ns"], work_end[0])
            self.assertLess(release["start_ns"] - rows[0]["end_ns"], 250_000_000)


if __name__ == "__main__":
    unittest.main()
