---
name: path-references
description: Use when creating, renaming, moving or deleting a file or directory in MotionSense, when a comment or doc cites a path, when adding or editing a Markdown link or #anchor, and when editing any doc or its Chinese twin (X.md / X_cn.md). Checks that every path cited in docs and in C/Go/shell/CMake comments exists (in MotionSense or the SDK fork around it), that every anchor resolves, and that each English doc and its Simplified Chinese copy still match.
---

# Path references

Paths are cited from more places than `#include`: comments such as
`See docs/adaptive-timelapse-pts.md` in `src/media.c`, doc links, and anchors
like `docs/BUILD.md#the-sd-card`. The compiler checks includes; nothing
checked the rest. `media.c` and `storage.c` cited the time-lapse design note
for months before it existed.

Every doc also has a Simplified Chinese twin, `X_cn.md`. A twin that is not
updated with its source drifts silently, so the same script checks the pairs.

## The check script

Python 3, standard library only: it runs on the host and in the SDK
devcontainer, which has `python3` but no node.

```bash
python3 .claude/skills/path-references/scripts/check.py            # all checks
python3 .claude/skills/path-references/scripts/check.py --refs     # paths and links
python3 .claude/skills/path-references/scripts/check.py --anchors  # #anchors
python3 .claude/skills/path-references/scripts/check.py --pairs    # X.md vs X_cn.md
```

Run it from anywhere inside the MotionSense checkout. It exits 1 when it
reports anything. In the devcontainer, run it as the host user so git writes
nothing as root (see the SDK's `devcontainer` skill):

```bash
docker exec -u 1000:1000 -w /workspaces/luckfox-pico-sdk/project/app/motionsense <container> \
    python3 -I -B .claude/skills/path-references/scripts/check.py
```

What each check reports:

- **`--refs`**: a Markdown link to a missing file, and a path-like token in
  prose or in a code comment that resolves to nothing git knows about.
  A token resolves relative to its file, to the MotionSense root, to the
  SDK root (docs give commands such as `./build.sh` from there), as a path
  under some subdirectory, or, for a bare filename, anywhere. Files in the
  nested `3rdparty/media-server` submodule count. String literals are not
  scanned; absolute paths (`/oem/...`, `/mnt/sdcard/...`) are device paths
  and are skipped.
- **`--anchors`**: a `file.md#anchor` or `#anchor` link whose anchor is not
  a heading in the target. Slugs follow GitHub: Chinese characters stay,
  full-width punctuation and emoji are dropped, so `## 🔧 故障排除` is
  `#-故障排除`, with the leading hyphen.
- **`--pairs`**: for every doc,
    - `X.md` has `X_cn.md` and the reverse;
    - `Last edited: YYYY-MM-DD` / `最后编辑：YYYY-MM-DD` under each title;
    - `[English](X.md) | 简体中文` under the Chinese title, and the root
      README links `[简体中文](README_cn.md)`;
    - the same sequence of heading levels and the same number of code
      fences in both;
    - **a Chinese copy dated before its English source is reported as
      stale.**

Not checked: `3rdparty/`, `vendor/`, the vendored Video.js tree, minified
files, and this skill's own files.

A reported token that is genuinely not a path in either repo (a library
name, a file only on the board, a tree the build extracts) goes in
`scripts/allowed-tokens.txt` with a one-line reason. Do not add one to
silence a real stale reference.

## Workflow

### A reference points at a path that is gone

Do not edit anything yet; the user decides. Give them the evidence:

1. `git log --diff-filter=D --name-status -- '<path>'` finds the commit that
   removed it; `git log --follow -- '<path>'` follows a rename.
2. Read the last version, `git show <commit>^:<path>`, at least the part the
   reference relies on.
3. For each reference, recommend either **repoint** it at where that content
   lives now (name the section heading, since anchors break when headings
   change) or **remove** it, writing the fact it needed into the comment
   itself if the comment does not make sense without it.
4. Show one table: reference (file:line), what it relies on, where that
   content is now, recommendation. Apply only what the user approves.

### Before renaming, moving or deleting

Search for the old path and its bare name; comments often cite just the
name. Every hit is updated in the same change.

```bash
git grep -n -e 'docs/old-name.md' -e 'old-name.md'
```

Renaming a doc renames its twin too (`X.md` and `X_cn.md`).

### Editing a doc

1. Edit the English and the Chinese file in the same change, and set both
   dates to today. A translation of unreviewed text is still a translation:
   when the English changes, the Chinese changes with it.
2. Do not hard-wrap Chinese paragraphs. GitHub renders a soft line break as
   a space, which shows between Chinese characters.
3. If a heading changes, the anchor changes: the check finds the links that
   used it.

### Before committing

Run the check and fix what it reports, or allow-list a token with a reason.
Then grep once more for any old name: prose such as "the time-lapse note" is
invisible to a path matcher.
