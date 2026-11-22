#!/bin/bash
# Build and run the daemon and the agent on this machine against vendor/pcsim.
set -euo pipefail
APP=$(cd "$(dirname "$(realpath "$0")")/.." && pwd)
OUT=$APP/build/pcsim

# The Rockchip headers are not in the repository.
[ -e "$APP/vendor/rockit/lib/librockit.so" ] || "$APP/scripts/sync-vendor.sh"

# Same layout as /oem/usr: the daemon finds its files from where it is.
cmake -S "$APP" -B "$OUT" -DMS_PLATFORM=pcsim \
    -DCMAKE_RUNTIME_OUTPUT_DIRECTORY="$OUT/bin" >/dev/null
cmake --build "$OUT" -j"$(nproc)" >/dev/null
"$APP/scripts/build-web.sh" >/dev/null
(cd "$APP/agent" && go build -buildvcs=false -o "$OUT/bin/agent" .)
install -D -m 644 -t "$OUT/share/MotionSense/fonts" "$APP/3rdparty/osd/DejaVuSansMono.ttf"

mkdir -p "$OUT/data"
export MS_BOARD_FILE=$OUT/board.json
cat >"$MS_BOARD_FILE" <<JSON
{ "storage": { "root": "$OUT/data", "removable": false } }
JSON

trap 'kill $(jobs -p) 2>/dev/null' EXIT
"$OUT/bin/MotionSense" &
"$OUT/bin/agent" &
wait -n
