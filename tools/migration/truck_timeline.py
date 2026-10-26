import hashlib
import json
import subprocess
from pathlib import Path


FRAMES = ("initial", "drive-0", *("drive-%d" % i for i in range(1, 7)),
          "drive", "brake-mid", "after-input")
FOLLOW_PIXELS = (10, 10, 20, 20, 40, 40, 50, 60, 70, 80, 100, 110, 120)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_WIDTH = 1024
PNG_HEIGHT = 768
MAX_PNG_BYTES = 16 * 1024 * 1024


def valid_png(data):
    if (len(data) > MAX_PNG_BYTES or len(data) < 24 or
            not data.startswith(PNG_SIGNATURE) or
            int.from_bytes(data[16:20], "big") != PNG_WIDTH or
            int.from_bytes(data[20:24], "big") != PNG_HEIGHT):
        return False
    try:
        result = subprocess.run(
            ["identify", "-regard-warnings", "-limit", "memory", "64MiB", "-limit", "map", "64MiB",
             "-limit", "disk", "0", "-format", "%w %h", "PNG:-"],
            input=data, capture_output=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return (result.returncode == 0 and result.stdout == b"1024 768" and
            not result.stderr)


def validate(directory):
    directory = Path(directory)
    try:
        rows = [json.loads(line) for line in (directory / "truck-timeline.jsonl").read_text().splitlines()]
    except (OSError, ValueError) as error:
        return False, str(error)
    if not rows or rows[0].get("kind") != "run" or rows[0].get("name") != "Truck":
        return False, "wrong or absent Truck run"
    for row in rows:
        if not isinstance(row.get("start_ns"), int) or not isinstance(row.get("end_ns"), int):
            return False, "missing monotonic boundary"
        if row["start_ns"] > row["end_ns"] or row.get("error"):
            return False, "invalid or failed operation"
    cameras = ("setup", *("follow-%02d" % i for i in range(1, 14)),
               "brake-follow-1", "brake-follow-2")
    expected = {("run", "Truck"),
                *(("camera", name) for name in cameras),
                *(("pointer", name + suffix) for name in cameras
                  for suffix in ("-position", "-down", "-up")),
                *(("frame", name) for name in FRAMES),
                *(("frame_hash", name) for name in FRAMES),
                *(("key", name) for name in ("keydown-Right", "keyup-Right", "keydown-s", "keyup-s"))}
    if len(rows) != len(expected) or {(row.get("kind"), row.get("name")) for row in rows} != expected:
        return False, "missing, repeated, or unexpected input operation"
    def one(kind, name):
        matches = [row for row in rows if row.get("kind") == kind and row.get("name") == name]
        if len(matches) != 1:
            raise ValueError("missing or repeated %s %s" % (kind, name))
        return matches[0]
    try:
        right_down = one("key", "keydown-Right")
        right_up = one("key", "keyup-Right")
        brake_down = one("key", "keydown-s")
        brake_up = one("key", "keyup-s")
        setup = one("camera", "setup")
        follows = [one("camera", "follow-%02d" % i) for i in range(1, 14)]
        brake_follows = [one("camera", "brake-follow-%d" % i) for i in (1, 2)]
        gestures = [setup, *follows, *brake_follows]
        pointer_events = [
            (one("pointer", row["name"] + "-position"),
             one("pointer", row["name"] + "-down"), row,
             one("pointer", row["name"] + "-up"))
            for row in gestures
        ]
        frames = [one("frame", name) for name in FRAMES]
        hashes = [one("frame_hash", name) for name in FRAMES]
    except ValueError as error:
        return False, str(error)
    if (setup.get("from_x"), setup.get("to_x"), setup.get("from_y"), setup.get("to_y")) != (300, 650, 80, 80):
        return False, "setup camera path changed"
    if any((row.get("from_x"), row.get("to_x"), row.get("from_y"), row.get("to_y")) != (650, 650 - pixels, 80, 80)
           for row, pixels in zip(follows, FOLLOW_PIXELS)):
        return False, "follow camera path changed"
    if [(row.get("from_x"), row.get("to_x"), row.get("from_y"), row.get("to_y"))
        for row in brake_follows] != [(650, 530, 80, 80), (650, 530, 240, 80)]:
        return False, "brake camera path changed"
    if any(not (position["start_ns"] <= position["end_ns"] <= down["start_ns"]
                <= down["end_ns"] <= move["start_ns"] <= move["end_ns"]
                <= up["start_ns"] <= up["end_ns"])
           for position, down, move, up in pointer_events):
        return False, "camera pointer gesture out of order"
    if any(previous[3]["end_ns"] > following[0]["start_ns"]
           for previous, following in zip(pointer_events, pointer_events[1:])):
        return False, "camera pointer gestures overlap"
    if not (setup["end_ns"] < frames[0]["start_ns"] < right_down["start_ns"]
            <= right_down["end_ns"] < frames[1]["start_ns"]):
        return False, "setup or drive start out of order"
    if not all(right_down["end_ns"] <= row["start_ns"] < row["end_ns"] <= right_up["end_ns"]
               for row in follows):
        return False, "camera gesture outside drive"
    if not all(a["end_ns"] <= b["start_ns"] for a, b in zip(follows, follows[1:])):
        return False, "camera gestures out of order"
    for index, row in enumerate(follows, 1):
        target = right_down["end_ns"] + index * 500_000_000
        if abs(row["start_ns"] - target) > 150_000_000:
            return False, "late or early camera gesture"
    if not (right_up["end_ns"] <= frames[-3]["start_ns"]
            <= frames[-3]["end_ns"] <= brake_down["start_ns"]
            <= brake_down["end_ns"] < brake_up["start_ns"]
            <= brake_up["end_ns"] <= frames[-1]["start_ns"]):
        return False, "drive and brake out of order"
    if not (brake_down["end_ns"] < brake_follows[0]["start_ns"]
            < brake_follows[0]["end_ns"] < frames[-2]["start_ns"]
            < frames[-2]["end_ns"] < brake_follows[1]["start_ns"]
            < brake_follows[1]["end_ns"] < brake_up["start_ns"]):
        return False, "brake camera or frame out of order"
    for index in range(1, 7):
        if not (follows[index * 2 - 1]["end_ns"] <= frames[index + 1]["start_ns"]
                < frames[index + 1]["end_ns"] < right_up["start_ns"]):
            return False, "drive frame out of order"
    if frames[1]["start_ns"] - right_down["end_ns"] > 200_000_000:
        return False, "drive start frame late"
    for index in range(1, 7):
        target = right_down["end_ns"] + index * 1_000_000_000
        if not 0 <= frames[index + 1]["start_ns"] - target <= 200_000_000:
            return False, "drive frame late or early"
    if (frames[-3]["start_ns"] - right_up["end_ns"] > 200_000_000 or
            frames[-1]["start_ns"] - brake_up["end_ns"] > 200_000_000 or
            abs(frames[-2]["start_ns"] - (brake_down["end_ns"] + 500_000_000)) > 150_000_000):
        return False, "drive or brake frame late"
    for key, down, up, duration in (("Right", right_down, right_up, 7_000_000_000),
                                    ("s", brake_down, brake_up, 1_000_000_000)):
        lower = up["start_ns"] - down["end_ns"]
        upper = up["end_ns"] - down["start_ns"]
        if not (duration - 150_000_000 <= lower <= duration + 150_000_000 and
                duration - 150_000_000 <= upper <= duration + 150_000_000):
            return False, "%s hold outside bounded duration: %d..%d ns" % (key, lower, upper)
    if any(a["end_ns"] >= b["start_ns"] for a, b in zip(frames, frames[1:])):
        return False, "frames missing or out of order"
    if any(row["end_ns"] - row["start_ns"] > 250_000_000 for row in frames):
        return False, "slow frame capture"
    for frame, digest in zip(frames, hashes):
        name = frame["name"] + ".png"
        path = directory / name
        try:
            with path.open("rb") as image:
                data = image.read(MAX_PNG_BYTES + 1)
        except OSError:
            return False, "missing frame " + name
        if (frame.get("file") != name or digest.get("file") != name or
                not valid_png(data) or
                digest.get("sha256") != hashlib.sha256(data).hexdigest()):
            return False, "invalid or changed frame " + name
        if frame["end_ns"] > digest["start_ns"]:
            return False, "frame hash before capture completion"
    return True, "11 timestamped frames, 16 recorded upper-canvas drags, bounded 7 s drive and 1 s brake; visual review separate"
