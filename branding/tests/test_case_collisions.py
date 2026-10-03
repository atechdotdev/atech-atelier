#!/usr/bin/env python3
"""R64: no two paths in the repository may differ only in letter case.

On a case-insensitive filesystem (default macOS APFS, Windows NTFS) such a
pair collapses to one file on clone, silently. brand/assets/source used to
carry atech_black_logo.png and Atech_Black_Logo.png -- two different images
that build_brand.py both reads.

The set checked is what a commit of the working tree would contain: tracked
and untracked-but-not-ignored files, minus files deleted in the working tree.

    python3 branding/tests/test_case_collisions.py   -> CASE_COLLISIONS_TESTS_OK
"""
import os
import subprocess
import sys
import unittest
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def _git(*args):
    out = subprocess.run(["git", "-C", REPO] + list(args), check=True,
                         capture_output=True).stdout
    return [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]


def paths():
    live = set(_git("ls-files", "-z", "--cached", "--others",
                    "--exclude-standard"))
    live -= set(_git("ls-files", "-z", "--deleted"))
    # Directories collide too (Brand/x vs brand/y), so include every prefix.
    out = set()
    for p in live:
        parts = p.split("/")
        for i in range(1, len(parts) + 1):
            out.add("/".join(parts[:i]))
    return out


def collisions(names):
    groups = defaultdict(set)
    for n in names:
        groups[n.lower()].add(n)
    return sorted(sorted(g) for g in groups.values() if len(g) > 1)


class CaseCollisions(unittest.TestCase):
    def test_detector_bites(self):
        self.assertEqual(collisions(["a/Logo.png", "a/logo.png", "b"]),
                         [["a/Logo.png", "a/logo.png"]])

    def test_repository_has_none(self):
        self.assertEqual(collisions(paths()), [])


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    if r.wasSuccessful():
        print("CASE_COLLISIONS_TESTS_OK")
    sys.exit(0 if r.wasSuccessful() else 1)
