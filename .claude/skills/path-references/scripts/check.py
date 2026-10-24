#!/usr/bin/env python3
"""Check that paths cited in docs and comments exist, that Markdown anchors
resolve, and that every English doc and its Simplified Chinese twin agree.

Standard library only, so it runs unchanged on the host and in the SDK
devcontainer (which has python3 but no node). Run from anywhere inside the
MotionSense checkout:

    python3 .claude/skills/path-references/scripts/check.py            # all checks
    python3 .claude/skills/path-references/scripts/check.py --refs     # paths and links
    python3 .claude/skills/path-references/scripts/check.py --anchors  # #anchors
    python3 .claude/skills/path-references/scripts/check.py --pairs    # X.md vs X_cn.md

Exits 1 when it reports anything.
"""

import os
import posixpath
import re
import subprocess
import sys
from urllib.parse import unquote


def git(args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


ROOT = git(["rev-parse", "--show-toplevel"], os.getcwd()).strip()
# MotionSense is a submodule of the SDK fork, and its docs cite SDK files
# (build.sh, rkflash.sh, the board configs) relative to the SDK root.
SUPER = git(["rev-parse", "--show-superproject-working-tree"], ROOT).strip()
SUB_PREFIX = posixpath.relpath(ROOT, SUPER) + "/" if SUPER else None

HERE = os.path.dirname(os.path.abspath(__file__))

# Files whose contents are not checked. Vendored and third-party trees are not
# ours to edit; this skill's own files cite missing paths on purpose, as
# examples.
IGNORED_SOURCES = [
    re.compile(p)
    for p in (
        r"^3rdparty/",
        r"^vendor/",
        r"^agent/static/js/video-js-",
        r"\.min\.(js|css)$",
        r"^\.claude/skills/path-references/",
    )
]

# Tokens that look like paths but name things that are never committed:
# build output, and the SDK's generated trees.
IGNORED_TARGETS = [
    re.compile(p)
    for p in (
        r"(^|/)(output|out|build)(/|$)",
        r"^https?:",
        # Product names: Video.js, Node.js, ...
        r"^[A-Z][A-Za-z]*\.js$",
    )
]


def load_allowed():
    allowed = set()
    with open(os.path.join(HERE, "allowed-tokens.txt"), encoding="utf-8") as f:
        for line in f:
            token = line.split("#", 1)[0].strip()
            if token:
                allowed.add(token)
    return allowed


ALLOWED = load_allowed()

CODE_EXT = re.compile(r"\.(c|h|go|sh|py|ya?ml|cmake|mk|js|css|html)$")
CODE_NAMES = {"CMakeLists.txt", "Makefile", "S99motionsense"}
HASH_COMMENT = re.compile(r"(\.(sh|py|ya?ml|cmake|mk)$|(^|/)(CMakeLists\.txt|Makefile|S99\w+)$)")
TEXT_EXT = re.compile(r"\.md$")

# ASCII on purpose: in Python, \w matches CJK, and a path written straight
# after Chinese text ("见BUILD.md") must still be found.
FILE_TOKEN = re.compile(
    r"(?<![\w@/.~$*<>{}-])"
    r"((?:\.{1,2}/)*(?:[\w@.-]+/)*[\w-][\w.-]*"
    r"\.(?:md|c|h|go|sh|py|ya?ml|json|cmake|mk|html|js|css|txt|conf|fragment))"
    r"(?![\w/*<>{}-])",
    re.ASCII,
)
DIR_TOKEN = re.compile(
    r"(?<![\w@/.*<>{}-])((?:\.[\w-]+|[\w-]+)(?:/[\w.@-]+)+)/?(?![\w/*<>{}-])",
    re.ASCII,
)
MD_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
FENCE = re.compile(r"^\s*(```|~~~)")


class Tree:
    """The files git knows about in one repo, with their directories."""

    def __init__(self, root, tracked_only=False):
        def run(*args):
            return [f for f in git(["ls-files", "-z", *args], root).split("\0") if f]

        files = set(run("--cached"))
        # Nested submodules (3rdparty/media-server) are one entry to plain
        # ls-files; their contents are real files a comment may cite.
        files |= set(run("--cached", "--recurse-submodules"))
        if not tracked_only:
            # A file you just created counts; one deleted but unstaged does not.
            files |= set(run("--others", "--exclude-standard"))
            files -= set(run("--deleted"))
        self.files = files
        self.dirs = set()
        self.basenames = set()
        for f in files:
            self.basenames.add(posixpath.basename(f))
            d = posixpath.dirname(f)
            while d and d not in self.dirs:
                self.dirs.add(d)
                d = posixpath.dirname(d)
        self.top = {d for d in self.dirs if "/" not in d}

    def exists(self, p):
        return p in self.files or p in self.dirs

    def ends_with(self, suffix):
        tail = "/" + suffix
        return any(f.endswith(tail) for f in self.files) or any(
            d.endswith(tail) for d in self.dirs
        )


TREE = Tree(ROOT)
# Tracked files only: SDK build output is untracked and differs per machine.
SUPER_TREE = Tree(SUPER, tracked_only=True) if SUPER else None
TOP_DIRS = TREE.top | (SUPER_TREE.top if SUPER_TREE else set())


def resolves(token, from_file):
    """A reference is satisfied the way a reader would resolve it: relative to
    the file it sits in, to the MotionSense root, to the SDK root, as a path
    inside some subdirectory, or, for a bare filename, anywhere at all."""
    clean = token.rstrip("/")
    here = posixpath.dirname(from_file)
    joined = posixpath.normpath(posixpath.join(here, clean))
    if clean.startswith(("./", "../")):
        if TREE.exists(joined):
            return True
        # Commands in the docs run from the SDK root ("./build.sh"), and
        # ../../.. from inside the submodule lands there too.
        return bool(SUPER_TREE) and (
            in_super(posixpath.join(SUB_PREFIX, joined)) or in_super(clean)
        )
    if "/" not in clean:
        return (
            clean in TREE.basenames
            or TREE.exists(joined)
            or bool(SUPER_TREE) and clean in SUPER_TREE.basenames
        )
    return (
        TREE.exists(joined)
        or TREE.exists(clean)
        or TREE.ends_with(clean)
        or bool(SUPER_TREE) and in_super(clean)
    )


def in_super(p):
    p = posixpath.normpath(p)
    if p.startswith(SUB_PREFIX):
        return TREE.exists(p[len(SUB_PREFIX):])
    return SUPER_TREE.exists(p)


def is_code(f):
    return bool(CODE_EXT.search(f)) or posixpath.basename(f) in CODE_NAMES


def comments(lines, f):
    """Yield (line number, comment text). In code only comments are prose;
    string literals are includes, URLs and formats the build already checks."""
    if HASH_COMMENT.search(f):
        for i, line in enumerate(lines):
            m = re.search(r"(^|\s)#", line)
            if m and not line.lstrip().startswith("#!"):
                yield i, line[m.end():]
        return
    if f.endswith(".html"):
        in_c = False
        for i, line in enumerate(lines):
            if "<!--" in line or in_c:
                yield i, line
                in_c = "-->" not in line.split("<!--")[-1] if "<!--" in line else "-->" not in line
        return
    # C-like: // and /* */, skipping string and char literals.
    in_block = False
    for i, line in enumerate(lines):
        out, j, quote = [], 0, None
        while j < len(line):
            c, nxt = line[j], line[j + 1 : j + 2]
            if in_block:
                if c == "*" and nxt == "/":
                    in_block, j = False, j + 2
                    continue
                out.append(c)
            elif quote:
                if c == "\\":
                    j += 1
                elif c == quote:
                    quote = None
            elif c in "\"'`":
                quote = c
            elif c == "/" and nxt == "/":
                out.append(line[j + 2 :])
                break
            elif c == "/" and nxt == "*":
                in_block, j = True, j + 2
                continue
            j += 1
        if out:
            yield i, "".join(out)


def sources():
    for f in sorted(TREE.files):
        if any(p.search(f) for p in IGNORED_SOURCES):
            continue
        if TEXT_EXT.search(f) or is_code(f):
            try:
                with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                    yield f, fh.read().split("\n")
            except (OSError, UnicodeDecodeError):
                continue


def check_refs():
    problems = []
    for f, lines in sources():
        def report(token, kind, i):
            if token in ALLOWED or any(p.search(token) for p in IGNORED_TARGETS):
                return
            if not resolves(token, f):
                problems.append(f"{f}:{i + 1}  {kind} {token}")

        if TEXT_EXT.search(f):
            texts, in_fence = [], False
            for i, line in enumerate(lines):
                if FENCE.match(line):
                    in_fence = not in_fence
                    continue
                if not in_fence:
                    for target in MD_LINK.findall(line):
                        if re.match(r"([a-z][\w+.-]*:|#)", target, re.I):
                            continue
                        bare = unquote(re.sub(r"[#?].*$", "", target))
                        if bare:
                            report(bare, "broken link", i)
                texts.append((i, MD_LINK.sub("", line), in_fence))
        else:
            texts = [(i, t, False) for i, t in comments(lines, f)]

        for i, text, in_fence in texts:
            seen = set()
            for token in FILE_TOKEN.findall(text):
                # Fenced code is mostly commands and sample output; only trust
                # paths there that start at a real top-level directory.
                if in_fence and token.split("/")[0] not in TOP_DIRS:
                    continue
                seen.add(token)
                report(token, "missing file", i)
            # Directories have no extension to anchor on, so only trust ones
            # that start at a real top-level directory.
            for token in DIR_TOKEN.findall(text):
                token = token.rstrip(".")  # a full stop ends the sentence
                if token in seen or token.split("/")[0] not in TOP_DIRS:
                    continue
                last = token.split("/")[-1]
                if re.search(r"[.:]\d|\.\w+$", last):
                    continue
                report(token, "missing path", i)
    return problems


def slug(text):
    """GitHub's heading anchor: drop inline markup, lowercase, delete every
    character that is not a letter, digit, _, - or space, then spaces to -.
    Unicode letters (Chinese) survive; full-width punctuation and emoji do
    not, so "## 🔧 故障排除" becomes "-故障排除"."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("`", "").replace("**", "").replace("*", "")
    text = re.sub(r"[^\w\- ]", "", text.strip().lower())
    return text.replace(" ", "-")


def headings(lines):
    """[(line index, level, text)] of ATX headings outside code fences."""
    out, in_fence = [], False
    for i, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        m = None if in_fence else re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            out.append((i, len(m.group(1)), m.group(2)))
    return out


_anchor_cache = {}


def anchors(path):
    if path not in _anchor_cache:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        found, counts = set(), {}
        for _, _, text in headings(lines):
            s = slug(text)
            n = counts.get(s, 0)
            counts[s] = n + 1
            found.add(s if n == 0 else f"{s}-{n}")
        for line in lines:
            found.update(re.findall(r"<a\s+(?:id|name)=\"([^\"]+)\"", line))
        _anchor_cache[path] = found
    return _anchor_cache[path]


def check_anchors():
    problems = []
    for f, lines in sources():
        if not TEXT_EXT.search(f):
            continue
        in_fence = False
        for i, line in enumerate(lines):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for target in MD_LINK.findall(line):
                if "#" not in target or re.match(r"[a-z][\w+.-]*:", target, re.I):
                    continue
                path, anchor = target.split("#", 1)
                path = unquote(path)
                tgt = posixpath.normpath(posixpath.join(posixpath.dirname(f), path)) if path else f
                if not tgt.endswith(".md") or tgt not in TREE.files:
                    continue  # a missing file is --refs' job
                if unquote(anchor) not in anchors(tgt):
                    problems.append(f"{f}:{i + 1}  broken anchor {target}")
    return problems


EN_DATE = re.compile(r"^Last edited: (\d{4}-\d{2}-\d{2})\s*$")
CN_DATE = re.compile(r"^最后编辑：(\d{4}-\d{2}-\d{2})\s*$")


def fences(lines):
    return sum(1 for line in lines if FENCE.match(line))


def check_pairs():
    """Every doc has an English X.md and a Simplified Chinese X_cn.md. Both
    carry their last edited date under the title, the Chinese one links back,
    and the two have the same heading levels and the same number of code
    fences. A Chinese copy dated before its English source is stale."""
    problems = []
    docs = {f: lines for f, lines in sources() if TEXT_EXT.search(f)}
    docs = {f: l for f, l in docs.items() if not f.startswith(".claude/")}

    def date(f, pattern):
        for i, line in enumerate(docs[f][:10]):
            m = pattern.match(line)
            if m:
                return m.group(1)
        problems.append(f"{f}:1  no '{pattern.pattern[1:-6]}' line under the title")
        return None

    for f in sorted(docs):
        if f.endswith("_cn.md"):
            en = f[: -len("_cn.md")] + ".md"
            if en not in docs:
                problems.append(f"{f}:1  no English source {en}")
            continue
        cn = f[: -len(".md")] + "_cn.md"
        if cn not in docs:
            problems.append(f"{f}:1  no Chinese copy {cn}")
            continue
        en_lines, cn_lines = docs[f], docs[cn]

        en_date, cn_date = date(f, EN_DATE), date(cn, CN_DATE)
        if en_date and cn_date and cn_date < en_date:
            problems.append(
                f"{cn}:1  Chinese copy dated {cn_date}, English edited {en_date}: stale"
            )

        back = f"[English]({posixpath.basename(f)}) | 简体中文"
        if not any(line.strip() == back for line in cn_lines[:6]):
            problems.append(f"{cn}:1  missing '{back}' under the title")
        if f == "README.md" and "[简体中文](README_cn.md)" not in "\n".join(en_lines[:6]):
            problems.append(f"{f}:1  missing the [简体中文](README_cn.md) link")

        en_h = [lvl for _, lvl, _ in headings(en_lines)]
        cn_h = [lvl for _, lvl, _ in headings(cn_lines)]
        if en_h != cn_h:
            hs = headings(en_lines)
            n = next((k for k, (a, b) in enumerate(zip(en_h, cn_h)) if a != b), min(len(en_h), len(cn_h)))
            where = f"{f}:{hs[n][0] + 1}" if n < len(hs) else f"{f}:{len(en_lines)}"
            problems.append(
                f"{where}  heading {n + 1} onwards differs from {cn} "
                f"(levels {en_h[n:n + 3]} vs {cn_h[n:n + 3]}; {len(en_h)} vs {len(cn_h)} headings)"
            )
        if fences(en_lines) != fences(cn_lines):
            problems.append(
                f"{cn}:1  {fences(cn_lines)} code fences, {f} has {fences(en_lines)}"
            )
    return problems


def sort_key(problem):
    loc = problem.split()[0]
    f, _, line = loc.rpartition(":")
    return (f, int(line) if line.isdigit() else 0, problem)


CHECKS = [
    ("--refs", "Path references", check_refs),
    ("--anchors", "Anchors", check_anchors),
    ("--pairs", "English/Chinese pairs", check_pairs),
]


def main(argv):
    unknown = [a for a in argv if a not in {flag for flag, _, _ in CHECKS}]
    if unknown:
        print(__doc__, file=sys.stderr)
        return 2
    selected = [c for c in CHECKS if c[0] in argv] or CHECKS
    failed = False
    for _, name, fn in selected:
        problems = fn()
        if problems:
            failed = True
            print(f"{name}: {len(problems)} problem(s)")
            for p in sorted(problems, key=sort_key):
                print("  " + p)
        else:
            print(f"{name}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
