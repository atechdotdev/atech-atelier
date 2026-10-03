#!/usr/bin/env python3
"""R06: the change list is MEASURED, so a file nobody declared still shows up.

    python3 branding/tests/test_tree_changes.py   -> TREE_CHANGES_TESTS_OK
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "tree_changes.py")


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class TreeChanges(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tree_changes_")
        self.root = os.path.join(self.tmp, "squashfs-root")
        _w(os.path.join(self.root, "AppRun"), '"${MAIN}" "$@"\n')
        _w(os.path.join(self.root, "usr/bin/branding.txt"), "upstream\n")
        _w(os.path.join(self.root, "org.freecad.FreeCAD.desktop"), "[x]\n")
        os.symlink("org.freecad.FreeCAD.svg", os.path.join(self.root, ".DirIcon"))
        self.manifest = os.path.join(self.tmp, "m.json")
        subprocess.run([sys.executable, TOOL, "snapshot", self.root,
                        self.manifest], check=True, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _diff(self):
        return subprocess.run([sys.executable, TOOL, "diff", self.root,
                               self.manifest], check=True,
                              capture_output=True, text=True).stdout

    def test_unchanged_tree_reports_nothing(self):
        out = self._diff()
        self.assertIn("ADDED (0 files):\n  (none)", out)
        self.assertIn("REMOVED (0 files):\n  (none)", out)
        self.assertIn("MODIFIED (0 files):\n  (none)", out)

    def test_dummy_file_appears_without_editing_the_script(self):
        _w(os.path.join(self.root, "usr/share/dummy_nobody_declared.txt"), "x")
        out = self._diff()
        self.assertIn("  usr/share/dummy_nobody_declared.txt", out)
        self.assertIn("ADDED (1 file):", out)

    def test_apprun_rewrite_is_modified(self):
        _w(os.path.join(self.root, "AppRun"), 'trap x EXIT\n"${MAIN}" "$@"\n')
        out = self._diff()
        self.assertIn("MODIFIED (1 file):\n  AppRun", out)

    def test_removed_and_relinked(self):
        os.remove(os.path.join(self.root, "org.freecad.FreeCAD.desktop"))
        os.remove(os.path.join(self.root, ".DirIcon"))
        os.symlink("dev.atech.Atelier.svg", os.path.join(self.root, ".DirIcon"))
        out = self._diff()
        self.assertIn("REMOVED (1 file):\n  org.freecad.FreeCAD.desktop", out)
        self.assertIn("MODIFIED (1 file):\n  .DirIcon", out)

    def test_prune_removes_only_new_bytecode(self):
        _w(os.path.join(self.root, "usr/lib/__pycache__/old.cpython-311.pyc"), "u")
        subprocess.run([sys.executable, TOOL, "snapshot", self.root,
                        self.manifest], check=True, capture_output=True)
        _w(os.path.join(self.root, "usr/lib/__pycache__/new.cpython-311.pyc"), "b")
        _w(os.path.join(self.root, "usr/Mod/X/__pycache__/x.cpython-311.pyc"), "b")
        _w(os.path.join(self.root, "usr/Mod/X/keep.py"), "k")
        subprocess.run([sys.executable, TOOL, "prune-bytecode", self.root,
                        self.manifest], check=True, capture_output=True)
        self.assertTrue(os.path.exists(os.path.join(
            self.root, "usr/lib/__pycache__/old.cpython-311.pyc")))
        self.assertFalse(os.path.exists(os.path.join(
            self.root, "usr/lib/__pycache__/new.cpython-311.pyc")))
        self.assertFalse(os.path.exists(os.path.join(
            self.root, "usr/Mod/X/__pycache__")))
        out = self._diff()
        self.assertIn("ADDED (1 file):\n  usr/Mod/X/keep.py", out)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=1).result
    ok = r.wasSuccessful() and r.testsRun > 0
    print("TREE_CHANGES_TESTS_OK" if ok else "TREE_CHANGES_TESTS_FAILED")
    sys.exit(0 if ok else 1)
