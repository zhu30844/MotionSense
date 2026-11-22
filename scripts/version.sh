#!/bin/bash
# Prints the version of this checkout: $MS_VERSION if set, else the tag on
# HEAD, else dev-<short sha>; -dirty with uncommitted changes.
[ -n "${MS_VERSION:-}" ] && { echo "$MS_VERSION"; exit 0; }
cd "$(dirname "$(realpath "$0")")/.." || exit 1
v=$(git describe --tags --exact-match 2>/dev/null) \
    || v=dev-$(git rev-parse --short HEAD 2>/dev/null) || v=dev
[ -z "$(git status --porcelain --untracked-files=no 2>/dev/null)" ] || v=$v-dirty
echo "$v"
