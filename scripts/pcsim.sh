#!/bin/bash
# Build and run the daemon and the agent on this machine against vendor/pcsim.
set -euo pipefail
APP=$(cd "$(dirname "$(realpath "$0")")/.." && pwd)
OUT=$APP/build/pcsim

# The paths in config.h are fixed, so they have to exist here too.
sudo mkdir -p /mnt/sdcard/DCIM /mnt/sdcard/MotionSense /oem/usr/share/MotionSense/fonts
sudo chown -R "$(id -u):$(id -g)" /mnt/sdcard
sudo cp "$APP/3rdparty/osd/DejaVuSansMono.ttf" /oem/usr/share/MotionSense/fonts/

cmake -S "$APP" -B "$OUT" -DMS_PLATFORM=pcsim >/dev/null
cmake --build "$OUT" -j"$(nproc)" >/dev/null
(cd "$APP/agent" && go build -buildvcs=false -o "$OUT/agent" .)

trap 'kill $(jobs -p) 2>/dev/null' EXIT
"$OUT/MotionSense" &
"$OUT/agent" &
wait -n
