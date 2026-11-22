#!/bin/sh
# Installed in recovery as /usr/bin/RkLunch.sh, which its init runs at boot.
# Flashes the package ms-update left in /userdata.
# The mark in misc is cleared last, so a power loss starts the flash over.

DIR=/userdata/update
PKG=$DIR/update.tar
LOG=$DIR/recovery.log
RESULT=$DIR/result
TRIES=$DIR/tries
MAX_TRIES=3
BY_NAME=/dev/block/by-name
# Fast blink while flashing, slow blink on success, steady on failure.
LED=/sys/class/leds/work
BLINK_FAST_US=50000
BLINK_SLOW_US=500000
SHOW_S=5
blinker=

led_steady() {
    [ -n "$blinker" ] && kill "$blinker" 2>/dev/null
    blinker=
    [ -d "$LED" ] || return 0
    echo none > "$LED/trigger"
    echo 1 > "$LED/brightness"
}

# $1 = microseconds on, and the same off
led_blink() {
    led_steady
    [ -d "$LED" ] || return 0
    while :; do
        echo 0 > "$LED/brightness"; usleep "$1"
        echo 1 > "$LED/brightness"; usleep "$1"
    done &
    blinker=$!
}

# Synced, so the log still says how far it got after a power loss.
say() {
    echo "recovery: $*"
    [ -d "$DIR" ] && echo "$(cut -d' ' -f1 /proc/uptime) $*" >> "$LOG" && sync
}

# Clear the mark and boot the main system. $1 is the line left for the agent.
finish() {
    say "$1"
    [ -d "$DIR" ] && echo "$1" > "$RESULT"
    rm -f "$TRIES"
    flash_eraseall "$BY_NAME/misc" || say "could not erase misc"
    rm -f "$PKG"
    sync
    # Everything is settled by now, so losing power during the show is harmless.
    case "$1" in
        ok*) led_blink "$BLINK_SLOW_US" ;;
        *)   led_steady ;;
    esac
    sleep "$SHOW_S"
    reboot
    exit 0
}

# Reboot with the mark still set, so the flash starts over. Only failures
# count as tries; a power loss does not come through here.
retry() {
    n=$(cat "$TRIES" 2>/dev/null)
    case "$n" in ''|*[!0-9]*) n=0 ;; esac
    n=$((n + 1))
    [ "$n" -lt "$MAX_TRIES" ] || finish "failed: $1, gave up after $MAX_TRIES tries"
    echo "$n" > "$TRIES"
    say "$1; try $n of $MAX_TRIES failed, will retry"
    sync
    reboot
    exit 1
}

sum_of() { tar -xOf "$PKG" "$1" 2>/dev/null | sha256sum | cut -d' ' -f1; }

[ -f "$PKG" ] || finish "failed: no package"

# Check everything before erasing anything, so a bad package changes nothing.
tar -xOf "$PKG" SHA256SUMS > /tmp/sums 2>/dev/null
parts=
while read -r want file; do
    part=${file%.img}
    # Never uboot: a power loss while writing it leaves no way back here.
    case "$part" in
        boot|rootfs|oem) ;;
        *) finish "failed: package carries $file" ;;
    esac
    [ -e "$BY_NAME/$part" ] || finish "failed: no $part partition"
    [ "$(sum_of "$file")" = "$want" ] || finish "failed: $file is damaged"
    parts="$parts $part"
done < /tmp/sums
[ -n "$parts" ] || finish "failed: package is empty"

[ -d "$LED" ] || say "no LED at $LED"
led_blink "$BLINK_FAST_US"
for part in $parts; do
    dev=$(realpath "$BY_NAME/$part")
    say "writing $part to $dev"
    flash_eraseall "$dev" || retry "erasing $part failed"
    tar -xOf "$PKG" "$part.img" | nandwrite -p "$dev" || retry "writing $part failed"
done

finish "ok:$parts"
