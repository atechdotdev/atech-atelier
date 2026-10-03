"""First-run migration from "Atech Studio" to "Atech Atelier" (ADR-005).

Every case builds its own old and new user-data trees in a temp dir; the
real ~/.local/share is never read or written. No FreeCAD, no Qt.

RUN
    python3 -m unittest addon/AcadAgent/tests/test_migrate.py -v
    (or the image's usr/bin/python, the interpreter that ships)
"""
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(HERE, ".."))
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

from acadagent import migrate  # noqa: E402

TRUST = os.path.join("AcadAgent", "trusted_builds.json")
SESS = os.path.join("agent", "sessions.json")


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _tree(root):
    """{relative path: sha256} of every file under root."""
    out = {}
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, root)] = _sha(p)
    return out


class Base(unittest.TestCase):
    def setUp(self):
        os.environ.pop("ATECH_MIGRATE", None)
        self.tmp = tempfile.mkdtemp(prefix="migrate-")
        share = os.path.join(self.tmp, "share")
        self.old = os.path.join(share, "Atech Studio", "v1-1")
        self.new = os.path.join(share, "Atech Atelier", "v1-1")
        self.chat = os.path.join(self.old, "agent", "chat-20260925-141505")

    def tearDown(self):
        for dp, dn, fn in os.walk(self.tmp):
            for n in dn + fn:
                try:
                    os.chmod(os.path.join(dp, n), 0o700)
                except OSError:
                    pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, root, rel, data, mode=0o600):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.chmod(p, mode)
        return p

    def _old_tree(self):
        os.makedirs(self.chat)
        with open(os.path.join(self.chat, "model.py"), "w") as fh:
            fh.write("# a chat\n")
        self._write(self.old, TRUST, {"doc-uid": {"t": 1, "objs": {}}})
        self._write(self.old, SESS, {"doc-uid": {"ws": self.chat, "sid": "s1"}})
        self._write(self.old, "freecad_mcp_settings.json", {"x": 1}, 0o644)


class TestOldRoot(Base):
    def test_versioned(self):
        self.assertEqual(migrate.old_root_for(self.new), self.old)

    def test_trailing_slash(self):
        # getUserAppDataDir() ends in a separator.
        self.assertEqual(migrate.old_root_for(self.new + os.sep), self.old)

    def test_no_rename_means_no_old_root(self):
        self.assertIsNone(migrate.old_root_for(self.old))
        self.assertIsNone(migrate.old_root_for(self.old + os.sep))

    def test_unversioned(self):
        new = os.path.join(self.tmp, "share", "Atech Atelier")
        self.assertEqual(migrate.old_root_for(new),
                         os.path.join(self.tmp, "share", "Atech Studio"))

    def test_none(self):
        self.assertIsNone(migrate.old_root_for(None))


class TestMigrate(Base):
    def test_copies_once_and_leaves_old_tree_untouched(self):
        self._old_tree()
        before = _tree(self.old)
        rec = migrate.migrate(new=self.new + os.sep)
        self.assertEqual(rec["status"], migrate.DONE, rec)
        self.assertEqual(sorted(rec["copied"]), sorted([TRUST, SESS]))
        for rel in (TRUST, SESS):
            self.assertEqual(_sha(os.path.join(self.new, rel)),
                             _sha(os.path.join(self.old, rel)))
            # 0600 stays 0600 (the trust store is private).
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.new, rel)).st_mode),
                             0o600)
        # Only the two named files (plus the marker) - not FreeCAD's or
        # another addon's files, not the chat folders.
        self.assertEqual(sorted(_tree(self.new)),
                         sorted([TRUST, SESS, os.path.join("AcadAgent", migrate.MARKER)]))
        self.assertEqual(_tree(self.old), before)
        # The copied index still points at a chat folder that exists.
        with open(os.path.join(self.new, SESS), encoding="utf-8") as fh:
            ws = json.load(fh)["doc-uid"]["ws"]
        self.assertTrue(os.path.isdir(ws))
        marker = migrate.read_marker(self.new)
        self.assertEqual(marker["status"], migrate.DONE)
        self.assertEqual(marker["from"], os.path.normpath(self.old))

    def test_second_run_does_nothing(self):
        self._old_tree()
        migrate.migrate(new=self.new)
        # The user's new state changes; the old tree changes too. A second
        # start must not copy the old one over the new one.
        self._write(self.new, TRUST, {"newer": {}})
        self._write(self.old, SESS, {"changed": {}})
        rec = migrate.migrate(new=self.new)
        self.assertEqual(rec["status"], "already")
        with open(os.path.join(self.new, TRUST), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"newer": {}})
        with open(os.path.join(self.new, SESS), encoding="utf-8") as fh:
            self.assertIn("doc-uid", json.load(fh))

    def test_new_dir_already_in_use_is_never_overwritten(self):
        self._old_tree()
        self._write(self.new, SESS, {"mine": {}})
        rec = migrate.migrate(new=self.new)
        self.assertEqual(rec["status"], migrate.SKIPPED)
        self.assertFalse(os.path.exists(os.path.join(self.new, TRUST)))
        with open(os.path.join(self.new, SESS), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"mine": {}})
        self.assertEqual(migrate.migrate(new=self.new)["status"], "already")

    def test_atech_migrate_0_turns_it_off(self):
        self._old_tree()
        os.environ["ATECH_MIGRATE"] = "0"
        try:
            self.assertEqual(migrate.migrate(new=self.new)["status"], "nothing")
        finally:
            del os.environ["ATECH_MIGRATE"]
        self.assertFalse(os.path.exists(self.new))

    def test_tree_copied_by_apprun_is_only_recorded(self):
        """AppRun (apprun_migrate_block.sh) copied the whole old tree first:
        nothing is copied again, the marker says skipped."""
        self._old_tree()
        shutil.copytree(self.old, self.new, symlinks=True)
        before = _tree(self.new)
        rec = migrate.migrate(new=self.new)
        self.assertEqual(rec["status"], migrate.SKIPPED)
        after = _tree(self.new)
        after.pop(os.path.join("AcadAgent", migrate.MARKER))
        self.assertEqual(after, before)

    def test_no_old_data_writes_nothing(self):
        rec = migrate.migrate(new=self.new)
        self.assertEqual(rec["status"], "nothing")
        self.assertFalse(os.path.exists(self.new))

    def test_old_tree_without_addon_data_writes_nothing(self):
        self._write(self.old, "freecad_mcp_settings.json", {"x": 1})
        self.assertEqual(migrate.migrate(new=self.new)["status"], "nothing")
        self.assertFalse(os.path.exists(self.new))

    def test_same_folder_is_not_a_migration(self):
        self._old_tree()
        before = _tree(self.old)
        rec = migrate.migrate(new=self.old)
        self.assertEqual(rec["status"], "nothing")
        self.assertEqual(_tree(self.old), before)

    def test_only_what_exists_is_copied(self):
        self._write(self.old, TRUST, {"a": {}})
        rec = migrate.migrate(new=self.new)
        self.assertEqual(rec["status"], migrate.DONE)
        self.assertEqual(rec["copied"], [TRUST])
        self.assertFalse(os.path.exists(os.path.join(self.new, SESS)))

    def test_symlink_in_old_tree_is_not_followed(self):
        target = self._write(self.tmp, "secret.json", {"s": 1})
        os.makedirs(os.path.join(self.old, "AcadAgent"))
        os.symlink(target, os.path.join(self.old, TRUST))
        rec = migrate.migrate(new=self.new)
        self.assertEqual(rec["status"], "nothing")
        self.assertFalse(os.path.exists(os.path.join(self.new, TRUST)))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0,
                     "root ignores directory permissions")
    def test_partial_copy_is_retried_and_never_raises(self):
        self._old_tree()
        # The agent/ folder in the new tree cannot be written: the index
        # copy fails, the trust store copy succeeds.
        os.makedirs(os.path.join(self.new, "agent"))
        os.chmod(os.path.join(self.new, "agent"), 0o500)
        rec = migrate.migrate(new=self.new)
        self.assertEqual(rec["status"], migrate.PARTIAL, rec)
        self.assertEqual(rec["copied"], [TRUST])
        self.assertEqual(rec["failed"], [SESS])
        # Next start: the folder is writable again; only what is missing is
        # copied, and the trust store copied last time is kept.
        os.chmod(os.path.join(self.new, "agent"), 0o700)
        self._write(self.new, TRUST, {"used since": {}})
        rec = migrate.migrate(new=self.new)
        self.assertEqual(rec["status"], migrate.DONE, rec)
        self.assertIn(SESS, rec["copied"])
        with open(os.path.join(self.new, TRUST), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"used since": {}})

    def test_unexpected_error_is_reported_not_raised(self):
        self._old_tree()
        rec = migrate.migrate(new=self.new, items=None)   # not iterable
        self.assertEqual(rec["status"], "error")

    def test_paths_match_the_modules_that_read_them(self):
        """ITEMS must be where build and panel actually look - checked
        against their own path functions, not a copy of the strings."""
        src = {}
        for name in ("build.py", "panel.py"):
            with open(os.path.join(ADDON, "acadagent", name), encoding="utf-8") as fh:
                src[name] = fh.read()
        self.assertIn('TRUST_FILE = "trusted_builds.json"', src["build.py"])
        self.assertIn('os.path.join(_user_root(), "AcadAgent", TRUST_FILE)', src["build.py"])
        self.assertIn('os.path.join(cfgmod.chat_workspace_root(), "sessions.json")',
                      src["panel.py"])
        with open(os.path.join(ADDON, "acadagent", "settings.py"), encoding="utf-8") as fh:
            self.assertIn('return os.path.join(root, "agent")', fh.read())


if __name__ == "__main__":
    unittest.main()
