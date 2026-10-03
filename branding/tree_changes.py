#!/usr/bin/env python3
"""Measure what the build changed in the upstream tree (release PRD R06).

A hand-written "files we added" list goes stale the first time someone adds a
file to the build and forgets the notice. This one cannot: it records the
upstream tree right after extraction and diffs the built tree against it.

    tree_changes.py snapshot ROOT MANIFEST.json
    tree_changes.py diff     ROOT MANIFEST.json  > changes.txt
    tree_changes.py prune-bytecode ROOT MANIFEST.json

prune-bytecode deletes every *.pyc that is NOT in the upstream snapshot, then
any __pycache__ directory left empty. Running freecadcmd inside the tree
writes them (MEASURED 2026-09-25: FreeCAD's embedded interpreter ignores
PYTHONDONTWRITEBYTECODE), and they would otherwise ship, undeclared.

A file is identified by its path relative to ROOT; its content by sha256
(regular files) or by its link target (symlinks). Directories are not
listed -- only the files in them.
"""
import hashlib
import json
import os
import sys


def _entry(path):
    if os.path.islink(path):
        return "link:" + os.readlink(path)
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def scan(root):
    """{relpath: identity} for every file and symlink under root."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # A symlink to a directory is recorded as a link, not descended into.
        for d in list(dirnames):
            full = os.path.join(dirpath, d)
            if os.path.islink(full):
                dirnames.remove(d)
                out[os.path.relpath(full, root)] = _entry(full)
        for f in filenames:
            full = os.path.join(dirpath, f)
            out[os.path.relpath(full, root)] = _entry(full)
    return out


def diff(before, after):
    """(added, removed, modified) as sorted path lists."""
    b, a = set(before), set(after)
    added = sorted(a - b)
    removed = sorted(b - a)
    modified = sorted(p for p in a & b if before[p] != after[p])
    return added, removed, modified


def prune_bytecode(root, before):
    """Remove .pyc files absent from `before`; return how many."""
    n = 0
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for f in filenames:
            if not f.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, f)
            if os.path.relpath(full, root) not in before and not os.path.islink(full):
                os.remove(full)
                n += 1
        if os.path.basename(dirpath) == "__pycache__" and not os.listdir(dirpath) \
                and os.path.relpath(dirpath, root) not in before:
            os.rmdir(dirpath)
    return n


def render(added, removed, modified):
    lines = []
    for title, paths in (("ADDED", added), ("REMOVED", removed),
                         ("MODIFIED", modified)):
        lines.append("%s (%d file%s):" % (title, len(paths),
                                          "" if len(paths) == 1 else "s"))
        lines.extend("  " + p for p in paths)
        if not paths:
            lines.append("  (none)")
        lines.append("")
    return "\n".join(lines)


def main(argv):
    if len(argv) != 4 or argv[1] not in ("snapshot", "diff", "prune-bytecode"):
        sys.exit(__doc__)
    cmd, root, manifest = argv[1:]
    if not os.path.isdir(root):
        sys.exit("FAIL no such tree: %s" % root)
    if cmd == "snapshot":
        snap = scan(root)
        with open(manifest, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, sort_keys=True)
        print("snapshot: %d files" % len(snap), file=sys.stderr)
        return
    with open(manifest, encoding="utf-8") as fh:
        before = json.load(fh)
    if cmd == "prune-bytecode":
        print("pruned %d .pyc file(s)" % prune_bytecode(root, before))
        return
    sys.stdout.write(render(*diff(before, scan(root))))


if __name__ == "__main__":
    main(sys.argv)
