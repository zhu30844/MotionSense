#!/bin/bash
# Regenerate the samples from Big Buck Bunny. Needs curl and ffmpeg with libx264.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"

URL=https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4
SRC=$(mktemp --suffix=.mp4)
trap 'rm -f "$SRC"' EXIT
curl -fsSL -o "$SRC" "$URL"

# Re-encoded like the board's encoder: no B-frames, a keyframe every 60.
# One slice per frame and an AUD before each: stream.c splits frames on the AUD.
ffmpeg -v error -y -i "$SRC" -an -pix_fmt yuv420p \
    -c:v libx264 -profile:v baseline -preset slow -b:v 500k -g 60 -bf 0 \
    -x264-params "aud=1:slices=1:repeat-headers=1:scenecut=0" \
    -f h264 sample.h264

ffmpeg -v error -y -i "$SRC" -an -r 15 -pix_fmt yuvj420p \
    -c:v mjpeg -q:v 20 -f mjpeg sample.mjpeg

ls -l sample.h264 sample.mjpeg
