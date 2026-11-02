"""Keep the private login desktop tied to BT's managed service process on Linux."""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    if sys.platform != "linux":
        raise RuntimeError("此程序仅用于 Ubuntu 服务器宝塔项目。")
    stopping = False
    parent = os.getpid()

    def request_stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    def child_setup():
        # BT stops an extra service by killing its PID. Ask the kernel to also stop
        # the desktop shell, whose EXIT trap cleans up Xvfb/VNC/WebSocket children.
        if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
            os._exit(1)
        if os.getppid() != parent:
            os._exit(1)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stopping:
        child = subprocess.Popen(["/bin/bash", str(Path(__file__).with_name("desktop.sh"))],
                                 start_new_session=True, preexec_fn=child_setup)
        try:
            while not stopping and child.poll() is None:
                time.sleep(0.2)
        finally:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        if not stopping:
            time.sleep(1)


if __name__ == "__main__":
    main()
