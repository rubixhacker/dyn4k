import os
from pathlib import Path
import signal
import sys
import time


child = os.fork()
if child == 0:
    if sys.argv[2] == "ignore":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    os.close(1)
    os.close(2)
    while True:
        time.sleep(1)
Path(sys.argv[1]).write_text(f"{child}\n")
print("parent complete", flush=True)
