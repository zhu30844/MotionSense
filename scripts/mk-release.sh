#!/bin/bash
# Assemble the release bundle for one board from a finished SDK build.
#
# Produces <out>/MotionSense-<version>-<slug>-img.zip with the same layout as
# the v1.0.0 release: the flashable images, LICENSE, THIRD-PARTY.md, the
# licence texts, a SOURCES.md naming the exact revisions, and SHA256SUMS.
#
# The same script runs locally and in CI, so a hand-made release and a
# tagged one are byte-for-byte the same shape. It never builds anything; run
# ./build.sh in the SDK first.
#
# Usage: scripts/mk-release.sh [--sdk DIR] [--board BoardConfig_X] [--slug NAME]
#                              [--version vX.Y.Z] [--out DIR]
#
#   --sdk      SDK checkout; default: three levels up from this repository.
#   --board    directory under project/cfg/ the images were built for;
#              default: whatever .BoardConfig.mk points at. The build is
#              checked against it so a bundle cannot be labelled for one
#              board and carry another's images.
#   --slug     board name for the file name; default from the table below.
#   --version  default: the tag on HEAD, else dev-<short sha>.
#   --out      default: <sdk>/output/release
set -euo pipefail

HERE=$(cd "$(dirname "$(realpath "$0")")" && pwd)
APP_DIR=$(dirname "$HERE")
SDK=$(cd "$APP_DIR/../../.." && pwd)
BOARD="" SLUG="" VERSION="" OUT=""

die() { echo "mk-release: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --sdk)     SDK=$(cd "$2" && pwd); shift 2 ;;
        --board)   BOARD=$2; shift 2 ;;
        --slug)    SLUG=$2; shift 2 ;;
        --version) VERSION=$2; shift 2 ;;
        --out)     OUT=$2; shift 2 ;;
        -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

# Board slugs for the file name. A new board gets a line here; anything not
# listed falls back to its directory name.
slug_for() {
    case "$1" in
        BoardConfig_MotionSense) echo luckfox-pico-pro-max ;;
        *) echo "$1" | sed 's/^BoardConfig_//' | tr 'A-Z_' 'a-z-' ;;
    esac
}

# ---- what was built -------------------------------------------------------
IMG_DIR=$SDK/output/image
[ -L "$SDK/.BoardConfig.mk" ] || die "$SDK/.BoardConfig.mk missing: the SDK has not been lunched"
BUILT_CFG=$(realpath "$SDK/.BoardConfig.mk")
BUILT_BOARD=$(basename "$(dirname "$BUILT_CFG")")
[ -n "$BOARD" ] || BOARD=$BUILT_BOARD
[ "$BOARD" = "$BUILT_BOARD" ] || die "asked for $BOARD but the SDK is built for $BUILT_BOARD ($BUILT_CFG)"
[ -n "$SLUG" ] || SLUG=$(slug_for "$BOARD")

if [ -z "$VERSION" ]; then
    VERSION=$(git -C "$APP_DIR" describe --tags --exact-match 2>/dev/null \
              || echo "dev-$(git -C "$APP_DIR" rev-parse --short HEAD)")
fi
case "$VERSION" in */*|*' '*|'') die "bad version '$VERSION'" ;; esac
[ -n "$OUT" ] || OUT=$SDK/output/release

for f in update.img oem.img rootfs.img boot.img uboot.img idblock.img env.img userdata.img download.bin; do
    [ -s "$IMG_DIR/$f" ] || die "$IMG_DIR/$f missing or empty: run ./build.sh first"
done

# ---- did the app actually make it into the oem partition? -----------------
# build.sh packages whatever is in output/out/app_out; when build_app fails
# part-way that directory is empty and the firmware step still "succeeds".
# Compare the staged oem tree against the binaries the app build produced.
for b in MotionSense motionsense-agent; do
    built=$SDK/project/app/out/bin/$b
    staged=$SDK/output/out/oem/usr/bin/$b
    [ -s "$built" ]  || die "$built missing: the app stage did not run"
    [ -s "$staged" ] || die "$staged missing: oem was packaged without the app"
    [ "$(md5sum < "$built")" = "$(md5sum < "$staged")" ] \
        || die "$b in output/out/oem differs from project/app/out: stale oem.img"
done
[ "$IMG_DIR/oem.img" -nt "$SDK/output/out/oem/usr/bin/MotionSense" ] \
    || die "oem.img is older than the staged MotionSense binary: re-run ./build.sh firmware"

# ---- revisions for SOURCES.md ---------------------------------------------
APP_REV=$(git -C "$APP_DIR" rev-parse HEAD)
SDK_REV=$(git -C "$SDK" rev-parse HEAD)
dirty() { [ -z "$(git -C "$1" status --porcelain --untracked-files=no)" ] || echo " (with uncommitted changes)"; }
APP_DIRTY=$(dirty "$APP_DIR"); SDK_DIRTY=$(dirty "$SDK")
BUILD_DATE=$(date -u +%Y-%m-%d)

# ---- assemble --------------------------------------------------------------
NAME=MotionSense-$VERSION-$SLUG-img
STAGE=$OUT/$NAME
TOP=$STAGE/MotionSense-$VERSION
rm -rf "$STAGE" "$OUT/$NAME.zip" "$OUT/$NAME.zip.sha256"
mkdir -p "$TOP/images" "$TOP/licences"

for f in "$IMG_DIR"/*; do
    case "$(basename "$f")" in .*) continue ;; esac   # .env.txt is a build-tree detail
    cp "$f" "$TOP/images/"
done
cp "$APP_DIR/LICENSE"                 "$TOP/LICENSE"
cp "$APP_DIR/docs/THIRD-PARTY.md"     "$TOP/THIRD-PARTY.md"
cp "$APP_DIR/licences/Apache-2.0.txt" "$TOP/licences/Apache-2.0.txt"
cp "$APP_DIR/3rdparty/osd/LICENSE"    "$TOP/licences/Rockchip-OSD-BSD-3-Clause.txt"

fill() {  # fill <template> <dest>
    sed -e "s|@VERSION@|$VERSION|g" -e "s|@SLUG@|$SLUG|g" -e "s|@BOARD@|$BOARD|g" \
        -e "s|@APP_REV@|$APP_REV$APP_DIRTY|g" -e "s|@SDK_REV@|$SDK_REV$SDK_DIRTY|g" \
        -e "s|@BOARD_CFG@|${BUILT_CFG#$SDK/}|g" -e "s|@BUILD_DATE@|$BUILD_DATE|g" \
        "$1" > "$2"
}
fill "$HERE/release/README.md.in"  "$TOP/README.md"
fill "$HERE/release/SOURCES.md.in" "$TOP/SOURCES.md"

(cd "$TOP" && find . -type f ! -name SHA256SUMS | sed 's|^\./||' | LC_ALL=C sort | xargs sha256sum > SHA256SUMS)

# zip is not in the devcontainer image; python is everywhere we build.
python3 - "$STAGE" "MotionSense-$VERSION" "$OUT/$NAME.zip" <<'PY'
import os, sys, zipfile
stage, top, dest = sys.argv[1:]
with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, dirs, files in os.walk(os.path.join(stage, top)):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, stage))
PY
(cd "$OUT" && sha256sum "$NAME.zip" > "$NAME.zip.sha256")

echo "release bundle: $OUT/$NAME.zip"
echo "  version $VERSION, board $BOARD ($SLUG)"
echo "  MotionSense $APP_REV$APP_DIRTY"
echo "  SDK         $SDK_REV$SDK_DIRTY"
du -h "$OUT/$NAME.zip" | cut -f1 | sed 's/^/  size /'
