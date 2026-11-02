#!/bin/bash
set -euo pipefail
cleanup() { kill $(jobs -pr) 2>/dev/null || true; }
trap cleanup EXIT
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
for attempt in $(seq 1 50); do
    if xdpyinfo -display :99 >/dev/null 2>&1; then break; fi
    sleep .1
done
openbox >/dev/null 2>&1 &
x11vnc -display :99 -rfbport 5901 -localhost -forever -shared -nopw -quiet >/dev/null 2>&1 &
websockify --web /usr/share/novnc 127.0.0.1:6080 127.0.0.1:5901 &
wait -n
