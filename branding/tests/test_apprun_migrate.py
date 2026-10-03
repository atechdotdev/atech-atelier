#!/usr/bin/env python3
"""ADR-005: AppRun copies the user's profile from "Atech Studio" to "Atech Atelier".

Runs branding/apprun_migrate_block.sh under real bash with HOME pointed at a
temporary directory (never the real one) and checks:

  - old data + config trees, no new ones: both copied, the OLD trees are
    byte-for-byte unchanged (copy, not move), the theme name and absolute
    paths are rewritten in the COPY's user.cfg only;
  - a new tree that already exists is never touched;
  - no old tree: nothing created;
  - ATECH_MIGRATE=0: nothing happens;
  - XDG_DATA_HOME / XDG_CONFIG_HOME are honoured;
  - a second launch changes nothing;
  - an old folder that is a SYMLINK is copied as a real folder, and the
    rewrite never reaches the link target (the old profile);
  - sabotage: a copy of the block with `cp -a` swapped for `mv` fails the
    "old tree unchanged" check, so the test can tell a move from a copy.

    python3 branding/tests/test_apprun_migrate.py -> APPRUN_MIGRATE_TESTS_OK
"""
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK = os.path.join(os.path.dirname(HERE), "apprun_migrate_block.sh")
OLD, NEW = "Atech Studio", "Atech Atelier"


def tree_digest(root):
    """{relpath: sha256 or 'dir' or 'link->target'} for everything under root."""
    out = {}
    for dp, dns, fns in os.walk(root):
        for d in dns:
            p = os.path.join(dp, d)
            out[os.path.relpath(p, root)] = ("link->" + os.readlink(p)
                                             if os.path.islink(p) else "dir")
        for f in fns:
            p = os.path.join(dp, f)
            if os.path.islink(p):
                out[os.path.relpath(p, root)] = "link->" + os.readlink(p)
            else:
                with open(p, "rb") as fh:
                    out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


class Migrate(unittest.TestCase):
    block = BLOCK

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.home = self._td.name
        self.data = os.path.join(self.home, ".local", "share")
        self.conf = os.path.join(self.home, ".config")

    def tearDown(self):
        self._td.cleanup()

    def seed(self, data=None, conf=None):
        data = data or self.data
        conf = conf or self.conf
        od, oc = os.path.join(data, OLD), os.path.join(conf, OLD)
        write(os.path.join(od, "v1-1", "Macro", "m.FCMacro"), "print(1)\n")
        write(os.path.join(od, "agent", "chat-1", "design.py"), "x = 1\n")
        os.symlink("chat-1", os.path.join(od, "agent", "latest"))
        cfg = ('<?xml version="1.0"?>\n<FCParameters>\n'
               '  <FCText Name="Theme">Atech Studio Dark</FCText>\n'
               '  <FCText Name="MacroPath">%s/v1-1/Macro/</FCText>\n'
               '  <FCText Name="Note">Atech Studio is the old name</FCText>\n'
               '</FCParameters>\n' % od)
        write(os.path.join(oc, "v1-1", "user.cfg"), cfg)
        write(os.path.join(oc, "v1-1", "system.cfg"), "<FCParameters/>\n")
        return od, oc

    def run_block(self, **env):
        e = {"HOME": self.home, "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        e.update(env)
        r = subprocess.run(["bash", "-c", '. "$1"', "bash", self.block],
                           env=e, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_copies_and_keeps_old(self):
        od, oc = self.seed()
        before = (tree_digest(od), tree_digest(oc))
        r = self.run_block()
        nd, nc = os.path.join(self.data, NEW), os.path.join(self.conf, NEW)
        self.assertEqual((tree_digest(od), tree_digest(oc)), before,
                         "the OLD profile changed: that is a move, not a copy")
        self.assertTrue(os.path.isfile(os.path.join(nd, "v1-1", "Macro", "m.FCMacro")))
        self.assertTrue(os.path.isfile(os.path.join(nd, "agent", "chat-1", "design.py")))
        self.assertEqual(os.readlink(os.path.join(nd, "agent", "latest")), "chat-1")
        cfg = read(os.path.join(nc, "v1-1", "user.cfg"))
        self.assertIn(">Atech Atelier Dark<", cfg)
        self.assertIn("%s/v1-1/Macro/" % nd, cfg)
        self.assertNotIn("%s/" % od, cfg)
        # free text is NOT rewritten: only the theme value and paths are
        self.assertIn("Atech Studio is the old name", cfg)
        self.assertIn("copied your profile", r.stderr)
        # no temporary directories left behind
        leftovers = [f for d in (self.data, self.conf) for f in os.listdir(d)
                     if "migrating" in f]
        self.assertEqual(leftovers, [])

    def test_second_launch_changes_nothing(self):
        self.seed()
        self.run_block()
        nd, nc = os.path.join(self.data, NEW), os.path.join(self.conf, NEW)
        snap = (tree_digest(nd), tree_digest(nc))
        r = self.run_block()
        self.assertEqual((tree_digest(nd), tree_digest(nc)), snap)
        self.assertNotIn("copied", r.stderr)

    def test_existing_new_profile_untouched(self):
        self.seed()
        nd = os.path.join(self.data, NEW)
        write(os.path.join(nd, "v1-1", "mine.txt"), "keep\n")
        snap = tree_digest(nd)
        self.run_block()
        self.assertEqual(tree_digest(nd), snap)
        # the config tree had no new copy yet, so it IS migrated on its own
        self.assertTrue(os.path.isfile(os.path.join(self.conf, NEW, "v1-1", "user.cfg")))

    def test_nothing_to_migrate(self):
        self.run_block()
        self.assertFalse(os.path.exists(os.path.join(self.data, NEW)))
        self.assertFalse(os.path.exists(os.path.join(self.conf, NEW)))

    def test_opt_out(self):
        self.seed()
        self.run_block(ATECH_MIGRATE="0")
        self.assertFalse(os.path.exists(os.path.join(self.data, NEW)))
        self.assertFalse(os.path.exists(os.path.join(self.conf, NEW)))

    def test_xdg_dirs_honoured(self):
        xd, xc = os.path.join(self.home, "xd"), os.path.join(self.home, "xc")
        od, oc = self.seed(data=xd, conf=xc)
        self.run_block(XDG_DATA_HOME=xd, XDG_CONFIG_HOME=xc)
        self.assertTrue(os.path.isdir(os.path.join(xd, NEW, "v1-1")))
        cfg = read(os.path.join(xc, NEW, "v1-1", "user.cfg"))
        self.assertIn("%s/v1-1/Macro/" % os.path.join(xd, NEW), cfg)
        self.assertFalse(os.path.exists(os.path.join(self.data, NEW)))

    def test_symlinked_old_profile_is_not_edited(self):
        # dotfile managers often make ~/.config/<app> a symlink
        real = os.path.join(self.home, "dotfiles", "atech")
        cfg_text = '<x><FCText Name="Theme">Atech Studio Dark</FCText></x>\n'
        write(os.path.join(real, "v1-1", "user.cfg"), cfg_text)
        os.makedirs(self.conf, exist_ok=True)
        os.symlink(real, os.path.join(self.conf, OLD))
        before = tree_digest(real)
        self.run_block()
        nc = os.path.join(self.conf, NEW)
        self.assertEqual(tree_digest(real), before,
                         "the rewrite edited the OLD profile through a symlink")
        self.assertFalse(os.path.islink(nc), "the new profile is a link to the old one")
        self.assertIn(">Atech Atelier Dark<", read(os.path.join(nc, "v1-1", "user.cfg")))


class Sabotage(unittest.TestCase):
    """The copy-not-move check must be able to fail."""

    def test_move_is_detected(self):
        src = read(BLOCK)
        self.assertEqual(src.count('cp -a "$_old/." "$_tmp/"'), 1)
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "moved.sh")
            write(bad, src.replace('cp -a "$_old/." "$_tmp/"', 'mv "$_old"/* "$_tmp/"'))
            case = Migrate("test_copies_and_keeps_old")
            case.block = bad
            res = unittest.TestResult()
            case.run(res)
            self.assertEqual(len(res.failures) + len(res.errors), 1,
                             "a moving block passed the copy check")


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    if r.wasSuccessful():
        print("APPRUN_MIGRATE_TESTS_OK")
    sys.exit(0 if r.wasSuccessful() else 1)
