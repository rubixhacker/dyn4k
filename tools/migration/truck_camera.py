#!/usr/bin/env python3
import hashlib
import json
import subprocess
import sys
import threading
import time
from pathlib import Path


DRIVE_NS = 7_000_000_000
BRAKE_NS = 1_000_000_000
FOLLOW_NS = 500_000_000
BLANK_Y = 80
FOLLOW_PIXELS = (10, 10, 20, 20, 40, 40, 50, 60, 70, 80, 100, 110, 120)


class TruckRun:
    def __init__(self, window, evidence):
        self.window = window
        self.evidence = Path(evidence)
        self.lock = threading.Lock()
        self.pressed = set()
        self.mouse_down = False
        self.timeline = self.evidence / "truck-timeline.jsonl"
        self.timeline.write_text("")

    def record(self, kind, name, start, end, **details):
        row = {"kind": kind, "name": name, "start_ns": start, "end_ns": end, **details}
        with self.lock:
            with self.timeline.open("a") as stream:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
        return row

    def command(self, kind, name, command, **details):
        start = time.monotonic_ns()
        try:
            subprocess.run(command, check=True, timeout=5)
        except BaseException as error:
            self.record(kind, name, start, time.monotonic_ns(), error=str(error), **details)
            raise
        return self.record(kind, name, start, time.monotonic_ns(), **details)

    def xdotool(self, kind, name, *args, **details):
        return self.command(kind, name, ["xdotool", *map(str, args)], **details)

    def drag(self, name, start_x, end_x, start_y=BLANK_Y, end_y=BLANK_Y):
        self.xdotool("pointer", name + "-position", "mousemove", "--window", self.window, start_x, start_y)
        try:
            down = self.xdotool("pointer", name + "-down", "mousedown", 1)
            self.mouse_down = True
            move = self.xdotool("camera", name, "mousemove", "--window", self.window, end_x, end_y,
                                from_x=start_x, to_x=end_x, from_y=start_y, to_y=end_y)
        finally:
            if self.mouse_down:
                self.xdotool("pointer", name + "-up", "mouseup", 1)
                self.mouse_down = False
        return down, move

    def frame(self, name):
        path = self.evidence / (name + ".png")
        row = self.command("frame", name, ["import", "-window", "root", str(path)], file=path.name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.record("frame_hash", name, row["end_ns"], time.monotonic_ns(), sha256=digest, file=path.name)

    def keydown(self, key):
        row = self.xdotool("key", "keydown-" + key, "keydown", key)
        with self.lock:
            self.pressed.add(key)
        return row

    def keyup(self, key):
        row = self.xdotool("key", "keyup-" + key, "keyup", key)
        with self.lock:
            self.pressed.discard(key)
        return row

    def hold(self, key, duration_ns, work):
        down = self.keydown(key)
        deadline = down["end_ns"] + duration_ns
        failures = []

        def release():
            try:
                self.wait_until(deadline)
                self.keyup(key)
            except BaseException as error:
                failures.append(error)

        timer = threading.Thread(target=release, name="truck-key-release")
        timer.start()
        try:
            work(down["end_ns"], deadline)
        finally:
            timer.join()
        if failures:
            raise failures[0]

    @staticmethod
    def wait_until(deadline):
        while True:
            remaining = (deadline - time.monotonic_ns()) / 1_000_000_000
            if remaining <= 0:
                return
            time.sleep(remaining)

    def drive_work(self, start, deadline):
        self.frame("drive-0")
        for index, pixels in enumerate(FOLLOW_PIXELS, 1):
            self.wait_until(start + index * FOLLOW_NS)
            self.drag("follow-%02d" % index, 650, 650 - pixels)
            if index % 2 == 0:
                self.frame("drive-%d" % (index // 2))

    def brake_work(self, start, deadline):
        self.wait_until(start + 400_000_000)
        self.drag("brake-follow-1", 650, 530)
        self.wait_until(start + 500_000_000)
        self.frame("brake-mid")
        self.wait_until(start + 800_000_000)
        self.drag("brake-follow-2", 650, 530, 240, 80)

    def run(self):
        self.record("run", "Truck", time.monotonic_ns(), time.monotonic_ns(),
                    window=self.window, camera_y=BLANK_Y, drive_ns=DRIVE_NS, brake_ns=BRAKE_NS)
        try:
            self.drag("setup", 300, 650)
            time.sleep(0.15)
            self.frame("initial")
            self.hold("Right", DRIVE_NS, self.drive_work)
            self.frame("drive")
            self.hold("s", BRAKE_NS, self.brake_work)
            self.frame("after-input")
        finally:
            if self.mouse_down:
                self.xdotool("pointer", "cleanup-up", "mouseup", 1)
                self.mouse_down = False
            for key in tuple(self.pressed):
                self.keyup(key)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: truck_camera.py WINDOW EVIDENCE_DIR")
    TruckRun(sys.argv[1], sys.argv[2]).run()


if __name__ == "__main__":
    main()
