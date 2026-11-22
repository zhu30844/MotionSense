#!/bin/bash
# Day-to-day commands for a board on adb and for the simulator. Run it with
# no arguments for the list.
set -euo pipefail

APP=$(cd "$(dirname "$(realpath "$0")")" && pwd)
SDK=$(cd "$APP/../../.." && pwd)

die() { echo "ms: $*" >&2; exit 1; }
say() { echo "==> $*"; }

usage() {
    cat <<'EOF'
usage: ./ms <command>

  On the board, over adb:
    status        what is running, safe mode, boot count, storage, clock
    logs [which]  follow the logs; which = sys, agent or lib, default all three
    start         start the service
    stop          stop the service; nothing is restarted until start
    restart       stop, then start
    time          set the board's clock and RTC from this machine
    shell         a shell on the board
    deploy        build both programs and the web pages, push them, restart

  On this machine:
    sim           run the simulator and the web dev server together

Everything runs inside the SDK devcontainer; started from the host, ms moves
itself there. adb is only ever used from the container: a host adb server
would hold the board and the container's could not see it.
EOF
}

# ---- always in the devcontainer ---------------------------------------------
if [ ! -e /.dockerenv ]; then
    id=$(docker ps -q --filter "label=devcontainer.local_folder=$SDK")
    [ -n "$id" ] || die "the SDK devcontainer is not running: open $SDK in VS Code first"
    [ "$(echo "$id" | wc -l)" = 1 ] || die "more than one devcontainer for $SDK"
    inside=$(docker inspect -f "{{range .Mounts}}{{if eq .Source \"$SDK\"}}{{.Destination}}{{end}}{{end}}" "$id")
    [ -n "$inside" ] || die "container $id does not mount $SDK"
    tty=-i; [ -t 0 ] && tty=-it
    exec docker exec $tty -u dev -w "$inside/${APP#"$SDK"/}" "$id" ./ms "$@"
fi

# ---- board -------------------------------------------------------------------
INIT=/etc/init.d/S99motionsense
BIN=/oem/usr/bin

need_board() {
    [ "$(adb get-state 2>/dev/null)" = device ] ||
        die "no board on adb (is a host adb server holding it? run 'adb kill-server' on the host)"
}

# "<storage root>/MotionSense", from the board file like the programs do.
data_dir() {
    local root
    root=$(adb shell 'sed -n "s/.*\"root\" *: *\"\([^\"]*\)\".*/\1/p" /etc/motionsense/board.json 2>/dev/null' | tr -d '\r')
    echo "${root:-/mnt/sdcard}/MotionSense"
}

cmd_status() {
    need_board
    local now; now=$(date -u +%s)
    adb shell "
        $INIT status
        echo \"boot count: \$(cat /userdata/motionsense/boot_count 2>/dev/null || echo 0) (recording is left off above 5)\"
        grep -q ' $(dirname "$(data_dir)") ' /proc/mounts && echo 'storage: mounted' || echo 'storage: NOT mounted'
        d=\$(( \$(date -u +%s) - $now ))
        echo \"clock: \$(date '+%F %T %Z'), \${d}s from this machine\"
        echo \"uptime: \$(cut -d. -f1 /proc/uptime)s\"
        printf 'agent: '; wget -qO- http://127.0.0.1/api/status || echo 'no answer'
        echo
    "
}

# One adb per log, each line marked with where it came from.
follow() {  # follow <mark> <file> [filter]
    adb shell "tail -n 15 -F $2 2>/dev/null" |
        grep -a --line-buffered -i -- "${3:-}" | sed -u "s/^/$1 | /" &
}

cmd_logs() {
    need_board
    local which=${1:-all} data; data=$(data_dir)
    trap 'kill $(jobs -p) 2>/dev/null' EXIT
    case "$which" in sys|all)   follow 'sys  ' /var/log/messages motionsense ;; esac
    case "$which" in agent|all) follow 'agent' "$data/agent.log" ;; esac
    case "$which" in lib|all)   follow 'lib  ' "$data/motionsense.log" ;; esac
    [ -n "$(jobs -p)" ] || die "logs: sys, agent or lib"
    wait
}

cmd_time() {
    need_board
    adb shell "date -u -s '$(date -u '+%Y-%m-%d %H:%M:%S')' >/dev/null && hwclock -w -u && date"
}

cmd_deploy() {
    need_board
    local out=$APP/build/deploy

    say "building the web pages"
    "$APP/scripts/build-web.sh" >/dev/null

    say "building the daemon"
    cmake -S "$APP" -B "$APP/build" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 >/dev/null
    make -C "$APP/build" -j"$(nproc)" install >/dev/null

    say "building the agent"
    (cd "$APP/agent" && GOOS=linux GOARCH=arm GOARM=7 CGO_ENABLED=0 \
        go build -trimpath -buildvcs=false \
            -ldflags="-s -w -X github.com/motionsense/agent/internal/server.Version=$("$APP/scripts/version.sh")" \
            -o "$out/motionsense-agent" .)

    say "stopping the service"
    adb shell "$INIT stop"

    # adb push can report success and leave a short file: compare checksums.
    push() {  # push <local> <remote>
        adb push "$1" "$2" >/dev/null
        local want got
        want=$(md5sum < "$1" | cut -d' ' -f1)
        got=$(adb shell "sync; md5sum < $2" | cut -d' ' -f1)
        [ "$want" = "$got" ] || die "$2 on the board does not match $1"
        echo "    $2"
    }
    say "pushing"
    push "$APP/install/MotionSense/MotionSense" "$BIN/MotionSense"
    push "$out/motionsense-agent"               "$BIN/motionsense-agent"
    push "$APP/S99motionsense"                  "$INIT"
    adb shell "chmod 755 $BIN/MotionSense $BIN/motionsense-agent $INIT"

    say "starting the service"
    adb shell "$INIT start" >/dev/null
    sleep 8
    cmd_status
}

# ---- simulator ---------------------------------------------------------------
cmd_sim() {
    "$APP/scripts/build-web.sh" >/dev/null   # the dev server needs node_modules
    local ip; ip=$(hostname -i | cut -d' ' -f1)
    trap 'kill $(jobs -p) 2>/dev/null' EXIT
    "$APP/scripts/pcsim.sh" &
    (cd "$APP/agent/web" && exec npm run dev -- --clearScreen false) &
    cat <<EOF

  new pages, updating as you save   http://$ip:5173/v2/
  current pages, from the agent     http://$ip:3000/
  ctrl-c stops both

EOF
    wait -n
}

case "${1:-}" in
    status)  cmd_status ;;
    logs)    cmd_logs "${2:-}" ;;
    start)   need_board; adb shell "$INIT start" ;;
    stop)    need_board; adb shell "$INIT stop" ;;
    restart) need_board; adb shell "$INIT restart" ;;
    time)    cmd_time ;;
    shell)   need_board; exec adb shell ;;
    deploy)  cmd_deploy ;;
    sim)     cmd_sim ;;
    ''|-h|--help|help) usage ;;
    *) usage >&2; exit 1 ;;
esac
