#!/bin/bash
# Packs the update package that update/ms-update takes, from a finished build.
#
# Usage: scripts/mk-update.sh --slug NAME --version V [--sdk DIR] [--only "oem"]
#                             [--out FILE]
#
#   --slug     board name; must equal "name" in the board's board.json.
#   --version  recorded in the manifest.
#   --sdk      SDK checkout; default: three levels up from this repository.
#   --only     partitions to carry; default: "recovery boot rootfs oem".
#   --out      default: <sdk>/output/release/MotionSense-<version>-<slug>-update.tar
set -euo pipefail

HERE=$(cd "$(dirname "$(realpath "$0")")" && pwd)
SDK=$(cd "$HERE/../../../.." && pwd)
SLUG="" VERSION="" OUT="" PARTS="recovery boot rootfs oem"

die() { echo "mk-update: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --sdk)     SDK=$(cd "$2" && pwd); shift 2 ;;
        --slug)    SLUG=$2; shift 2 ;;
        --version) VERSION=$2; shift 2 ;;
        --only)    PARTS=$2; shift 2 ;;
        --out)     OUT=$2; shift 2 ;;
        -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done
[ -n "$SLUG" ] && [ -n "$VERSION" ] || die "--slug and --version are required"
[ -n "$OUT" ] || OUT=$SDK/output/release/MotionSense-$VERSION-$SLUG-update.tar

IMG_DIR=$SDK/output/image
STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
files=()
for part in $PARTS; do
    case "$part" in boot|rootfs|oem|recovery) ;; *) die "$part is never updated" ;; esac
    [ -s "$IMG_DIR/$part.img" ] || die "$IMG_DIR/$part.img missing or empty: run ./build.sh first"
    # -L: rootfs.img and oem.img are symlinks to the variant for this flash
    cp -L "$IMG_DIR/$part.img" "$STAGE/"
    files+=("$part.img")
done
[ ${#files[@]} -gt 0 ] || die "nothing to pack"

printf 'board=%s\nversion=%s\n' "$SLUG" "$VERSION" > "$STAGE/manifest"
(cd "$STAGE" && sha256sum "${files[@]}" > SHA256SUMS)

mkdir -p "$(dirname "$OUT")"
tar -C "$STAGE" --owner=0 --group=0 --numeric-owner -cf "$OUT" manifest SHA256SUMS "${files[@]}"
echo "update package: $OUT"
du -h "$OUT" | cut -f1 | sed 's/^/  size /'
