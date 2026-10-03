"""Round-8 WS-SHELL items R180 and R90, headless.

    R180  restore_view_prefs() with a snapshot written before a key joined
          VIEW_KEYS (AxisLetterColor, R161) used to REMOVE the user's
          current value: snap.get(key) is None for "never recorded" as well
          as for "recorded as absent". A missing key is now left alone.
          Sabotage: the old loop, run against the same state, removes it.
    R90   viewport.crane_parts() globbed *.brep in a build dir that is never
          cleaned, so parts of an earlier crane design loaded too. On the
          repo fixture tip_sheave (2026-08-22, not in parts.json) sits
          163.64 mm from every current part: the floating sheave of GUI shot
          r2_06. The build's parts.json now decides which files load.

    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest discover -s addon/AcadAgent/tests -p 'test_shell_round8.py' -v
"""
import json
import os
import shutil
import tempfile
import unittest

import _shell_fakes as F
from PySide6 import QtWidgets

from test_shell_lifecycle import ShellCase

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
VIEW = "User parameter:BaseApp/Preferences/View"
OWN = "User parameter:BaseApp/Preferences/Mod/AcadAgent"
USER_INK = 0x123456FF


# ------------------------------------------------------------------ R180
class TestOldSnapshotRestore(ShellCase):
    def keys(self):
        return {n: val for _k, n, val in
                (self.fc.ParamGet(VIEW).GetContents() or [])}

    def old_snapshot(self):
        """A snapshot as a pre-R161 build wrote it: every VIEW_KEY but
        AxisLetterColor, the user having no background of their own."""
        snap = {k: None for k, _kind in self.viewport.VIEW_KEYS
                if k != "AxisLetterColor"}
        self.fc.ParamGet(OWN).SetString(self.viewport._SNAP_KEY,
                                        json.dumps(snap, sort_keys=True))
        return snap

    def test_missing_key_keeps_users_value(self):
        self.old_snapshot()
        self.fc.ParamGet(VIEW).SetUnsigned("AxisLetterColor", USER_INK)
        self.assertTrue(self.viewport.restore_view_prefs())
        self.assertEqual(self.keys().get("AxisLetterColor"), USER_INK)

    def test_recorded_absent_is_still_removed(self):
        """A key the snapshot DID record as absent (None) goes, as before."""
        snap = self.old_snapshot()
        snap["AxisLetterColor"] = None
        self.fc.ParamGet(OWN).SetString(self.viewport._SNAP_KEY,
                                        json.dumps(snap, sort_keys=True))
        self.style_mode = self.style.mode
        self.style.mode = lambda: "light"
        try:
            self.fc.ParamGet(VIEW).SetUnsigned("AxisLetterColor", USER_INK)
            self.viewport.restore_view_prefs()
        finally:
            self.style.mode = self.style_mode
        self.assertNotIn("AxisLetterColor", self.keys())

    def test_recorded_value_is_still_given_back(self):
        snap = self.old_snapshot()
        snap["AxisLetterColor"] = ["Unsigned", 0x0A0B0CFF]
        self.fc.ParamGet(OWN).SetString(self.viewport._SNAP_KEY,
                                        json.dumps(snap, sort_keys=True))
        self.fc.ParamGet(VIEW).SetUnsigned("AxisLetterColor", USER_INK)
        self.viewport.restore_view_prefs()
        self.assertEqual(self.keys().get("AxisLetterColor"), 0x0A0B0CFF)

    def test_old_snapshot_then_apply_gives_users_value_back(self):
        """The real path to an old snapshot: a pre-R161 session crashed,
        so its snapshot is kept, and THIS session's apply_view_theme()
        writes the Studio ink over the user's AxisLetterColor. Skipping
        the key on restore alone would leave the Studio ink behind for
        good; the kept snapshot must learn the user's value first."""
        self.old_snapshot()
        self.fc.ParamGet(VIEW).SetUnsigned("AxisLetterColor", USER_INK)
        self.assertTrue(self.viewport.apply_view_theme())
        self.assertNotEqual(self.keys().get("AxisLetterColor"), USER_INK,
                            "apply did not overwrite: the check cannot fail")
        self.assertTrue(self.viewport.restore_view_prefs())
        self.assertEqual(self.keys().get("AxisLetterColor"), USER_INK)

    def test_old_snapshot_then_apply_absent_key_removed(self):
        """User had no AxisLetterColor: the upgraded snapshot records it
        as absent, so restore removes the Studio ink again."""
        self.old_snapshot()
        self.style_mode = self.style.mode
        self.style.mode = lambda: "light"
        try:
            self.viewport.apply_view_theme()
            self.assertIn("AxisLetterColor", self.keys())
            self.viewport.restore_view_prefs()
        finally:
            self.style.mode = self.style_mode
        self.assertNotIn("AxisLetterColor", self.keys())

    def test_sabotage_old_loop_removes_it(self):
        """The pre-fix loop, on the same state, loses the user's value -
        so the check above can fail."""
        snap = self.old_snapshot()
        p = self.fc.ParamGet(VIEW)
        p.SetUnsigned("AxisLetterColor", USER_INK)
        for key, kind in self.viewport.VIEW_KEYS:
            entry = snap.get(key)
            if entry is None:
                getattr(p, "Rem" + kind)(key)
        self.assertNotIn("AxisLetterColor", self.keys())


# ------------------------------------------------------------------ R90
class TestCranePartsManifest(unittest.TestCase):
    def setUp(self):
        F.install_fakes(QtWidgets.QMainWindow())
        from acadagent import viewport
        self.vp = viewport
        self.tmp = tempfile.mkdtemp(prefix="r90_")
        self.orig = viewport._crane_build_dir
        viewport._crane_build_dir = lambda: self.tmp
        for n in ("boom", "jib_sheave", "tip_sheave"):
            open(os.path.join(self.tmp, n + ".brep"), "w").close()

    def tearDown(self):
        self.vp._crane_build_dir = self.orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def manifest(self, parts):
        with open(os.path.join(self.tmp, "parts.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"parts": parts}, fh)

    def names(self):
        return [os.path.basename(f) for f in self.vp.crane_parts()]

    def test_stale_brep_not_loaded(self):
        self.manifest([{"id": "boom", "brep": "boom.brep"},
                       {"id": "jib_sheave", "brep": "jib_sheave.brep"}])
        self.assertEqual(self.names(), ["boom.brep", "jib_sheave.brep"])

    def test_listed_but_missing_file_is_absent(self):
        self.manifest([{"id": "boom", "brep": "boom.brep"},
                       {"id": "gone", "brep": "gone.brep"}])
        self.assertEqual(self.names(), ["boom.brep"])

    def test_no_manifest_falls_back_to_glob(self):
        self.assertEqual(self.names(),
                         ["boom.brep", "jib_sheave.brep", "tip_sheave.brep"])

    def test_broken_manifest_falls_back_to_glob(self):
        with open(os.path.join(self.tmp, "parts.json"), "w") as fh:
            fh.write("{not json")
        self.assertEqual(len(self.names()), 3)

    def test_sabotage_glob_loads_the_stale_sheave(self):
        self.manifest([{"id": "boom", "brep": "boom.brep"}])
        import glob
        old = sorted(os.path.basename(f) for f in
                     glob.glob(os.path.join(self.tmp, "*.brep")))
        self.assertIn("tip_sheave.brep", old, "the check could not fail")
        self.assertNotIn("tip_sheave.brep", self.names())


class TestRepoFixture(unittest.TestCase):
    """On the real fixture, when present: every loaded part is in the
    manifest and the stale tip_sheave is not loaded."""

    def test_repo_fixture(self):
        F.install_fakes(QtWidgets.QMainWindow())
        from acadagent import viewport
        d = viewport._crane_build_dir()
        if d is None or not os.path.isfile(os.path.join(d, "parts.json")):
            self.skipTest("crane fixture not built here")
        with open(os.path.join(d, "parts.json"), encoding="utf-8") as fh:
            listed = {p["brep"] for p in json.load(fh)["parts"]}
        got = {os.path.basename(f) for f in viewport.crane_parts()}
        self.assertEqual(got, listed)
        self.assertNotIn("tip_sheave.brep", got)


if __name__ == "__main__":
    unittest.main()
