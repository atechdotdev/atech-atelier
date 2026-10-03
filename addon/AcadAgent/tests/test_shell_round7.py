"""Round-7 WS-SHELL items R161, R162 and R172, headless.

    R161  the corner axis letters (X/Y/Z) are FreeCAD's drawing, coloured by
          View/AxisLetterColor (default black). apply_view_theme() now sets
          it from the text token, so it reads on either ground: contrast
          >= 4.5:1 against both gradient stops, where black on the dark
          ground MEASURES ~1.1:1. It is snapshotted and restored with the
          background (a dark ground kept for Part keeps its light letters).
    R162  terminal_dock.ask_about_view no longer forces the isometric view:
          with no `views` it hands None on, so vision.views_for decides (the
          module face for an Atech board). Sabotage: the old default.
    R172  a Python traceback reaches FreeCAD's notification bell once per
          sys.stderr.write (OutputStderr -> Console error). CPython's hook
          writes an exception raised in a Qt slot in 25 pieces, 8 of them
          non-blank = 8 bell entries; shell.hook_tracebacks() makes it one.

    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest discover -s addon/AcadAgent/tests -p 'test_shell_round7.py' -v
"""
import inspect
import json
import sys
import unittest

import _shell_fakes as F
from PySide6 import QtCore, QtWidgets

from test_shell_lifecycle import ShellCase

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
VIEW = "User parameter:BaseApp/Preferences/View"
OWN = "User parameter:BaseApp/Preferences/Mod/AcadAgent"


def _lum(rgb):
    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _unpack(v):
    """FreeCAD's packed RGBA uint32 -> (r, g, b) floats."""
    return tuple(((v >> s) & 0xFF) / 255.0 for s in (24, 16, 8))


# ------------------------------------------------------------------ R161
class TestAxisLetters(ShellCase):
    def set_mode(self, m):
        self.style_mode = self.style.mode
        self.style.mode = lambda: m

    def tearDown(self):
        if hasattr(self, "style_mode"):
            self.style.mode = self.style_mode
        super().tearDown()

    def keys(self):
        return {n: val for _k, n, val in
                (self.fc.ParamGet(VIEW).GetContents() or [])}

    def test_letters_read_on_both_grounds(self):
        for mode in ("dark", "light"):
            self.set_mode(mode)
            self.assertTrue(self.viewport.apply_view_theme())
            k = self.keys()
            ink = _unpack(k["AxisLetterColor"])
            t = self.style.tokens()
            for stop in ("view_top", "view_bot"):
                bg = self.viewport._hex(t[stop])
                self.assertGreaterEqual(_contrast(ink, bg), 4.5,
                                        "%s %s" % (mode, stop))
            self.style.mode = self.style_mode

    def test_freecad_default_black_fails_the_same_check(self):
        """The check can fail: FreeCAD's default (0x00000000, black) on the
        dark ground is the defect as seen in GUI shots r5_11 / r6_21."""
        self.set_mode("dark")
        bg = self.viewport._hex(self.style.tokens()["view_bot"])
        self.assertLess(_contrast(_unpack(0x00000000), bg), 1.5)

    def test_letters_follow_a_mode_switch(self):
        self.set_mode("dark")
        self.viewport.apply_view_theme()
        dark = self.keys()["AxisLetterColor"]
        self.style.mode = lambda: "light"
        self.viewport.apply_view_theme()
        light = self.keys()["AxisLetterColor"]
        self.assertNotEqual(dark, light)
        self.assertEqual(light, self.viewport._pack(
            self.viewport._hex(self.style.tokens()["text"])))

    def test_users_own_letter_colour_comes_back(self):
        self.set_mode("light")
        self.fc.ParamGet(VIEW).SetUnsigned("AxisLetterColor", 0x123456FF)
        self.viewport.apply_view_theme()
        self.shell.install()
        self.shell.uninstall()
        self.assertEqual(self.keys()["AxisLetterColor"], 0x123456FF)

    def test_light_uninstall_removes_ours(self):
        self.set_mode("light")
        self.viewport.apply_view_theme()
        self.shell.install()
        self.shell.uninstall()
        self.assertNotIn("AxisLetterColor", self.keys())

    def test_dark_kept_ground_keeps_its_letters(self):
        """R108 keeps a dark ground the user never set; the letters drawn on
        it stay light with it, and are seeded so they never pass for the
        user's own on the next snapshot."""
        self.set_mode("dark")
        self.viewport.apply_view_theme()
        ours = self.keys()["AxisLetterColor"]
        self.shell.install()
        self.shell.uninstall()
        self.assertEqual(self.keys().get("AxisLetterColor"), ours)
        seeded = json.loads(self.fc.ParamGet(OWN).GetString(
            self.viewport._SEEDED_KEY, ""))
        self.assertEqual(seeded.get("AxisLetterColor"), ours)


# ------------------------------------------------------------------ R162
class TestAskAboutViewViews(unittest.TestCase):
    def setUp(self):
        F.install_fakes(QtWidgets.QMainWindow())
        from acadagent import shell, terminal_dock, vision
        self.shell, self.td, self.vision = shell, terminal_dock, vision
        self.orig = (vision.ask_in_chat, shell.show_chat)
        self.seen = []

        def fake_ask(question=None, views=None, panel=None):
            self.seen.append(views)
            return True
        vision.ask_in_chat = fake_ask
        shell.show_chat = lambda: object()

    def tearDown(self):
        self.vision.ask_in_chat, self.shell.show_chat = self.orig

    def test_no_forced_view(self):
        self.assertIsNone(
            inspect.signature(self.td.ask_about_view).parameters["views"].default)
        self.assertTrue(self.td.ask_about_view("what is this?"))
        self.assertEqual(self.seen, [None],
                         "None is handed on, so views_for decides")

    def test_board_document_gets_the_module_face(self):
        """What views None resolves to in ask_in_chat: the module face for
        a board document, isometric otherwise."""
        board = type("D", (), {"Objects": [type("O", (), {"AtechRole": "board"})()]})()
        plain = type("D", (), {"Objects": []})()
        self.assertEqual(self.vision.views_for(board),
                         (self.vision.capture.MODULE_FACE,))
        self.assertEqual(self.vision.views_for(plain), ("Isometric",))

    def test_sabotage_old_default_is_caught(self):
        def old(question=None, views=("Isometric",)):
            return self.vision.ask_in_chat(question, views=views,
                                           panel=self.shell.show_chat())
        old("q")
        self.assertNotEqual(self.seen, [None], "the check could not fail")


# ------------------------------------------------------------------ R172
class _Sink:
    def __init__(self):
        self.chunks = []

    def write(self, s):
        self.chunks.append(s)
        return len(s)

    def flush(self):
        pass


def _bell_entries(chunks):
    """What NotificationAreaObserver::SendLog + pushNotification keep:
    each write trimmed, empty ones dropped, a repeat of the latest merged
    (Gui/NotificationArea.cpp)."""
    kept = [c.strip() for c in chunks if c.strip()]
    return [c for i, c in enumerate(kept) if i == 0 or c != kept[i - 1]]


class _Emitter(QtCore.QObject):
    fire = QtCore.Signal()


def _bad_slot():
    d = {}
    d["a"]["b"] = 1


class TestOneBellEntryPerTraceback(unittest.TestCase):
    def setUp(self):
        from acadagent import shell
        self.shell = shell
        self.orig_hook = sys.excepthook
        self.orig_err = sys.stderr

    def tearDown(self):
        sys.excepthook = self.orig_hook
        sys.stderr = self.orig_err

    def slot_error_chunks(self):
        e = _Emitter()
        e.fire.connect(_bad_slot)
        sink = _Sink()
        sys.stderr = sink
        try:
            e.fire.emit()               # PySide reports it via sys.excepthook
        finally:
            sys.stderr = self.orig_err
        return sink.chunks

    def test_default_hook_fragments_the_bell(self):
        """The measured defect, so the fix's check can fail."""
        sys.excepthook = sys.__excepthook__
        entries = _bell_entries(self.slot_error_chunks())
        self.assertGreaterEqual(len(entries), 5, entries)

    def test_hooked_traceback_is_one_entry_with_everything(self):
        sys.excepthook = sys.__excepthook__
        self.assertTrue(self.shell.hook_tracebacks())
        chunks = self.slot_error_chunks()
        self.assertEqual(len(chunks), 1, chunks)
        (entry,) = _bell_entries(chunks)
        self.assertTrue(entry.startswith("Traceback (most recent call last):"))
        self.assertIn("_bad_slot", entry)
        self.assertTrue(entry.endswith("KeyError: 'a'"), entry)

    def test_idempotent_and_leaves_a_foreign_hook(self):
        sys.excepthook = sys.__excepthook__
        self.assertTrue(self.shell.hook_tracebacks())
        self.assertTrue(self.shell.hook_tracebacks())
        self.assertIs(sys.excepthook, self.shell._one_write_excepthook)

        def theirs(*a):
            pass
        sys.excepthook = theirs
        self.assertFalse(self.shell.hook_tracebacks())
        self.assertIs(sys.excepthook, theirs)


class TestInstallHooksTracebacks(ShellCase):
    def test_install_installs_the_hook(self):
        orig = sys.excepthook
        sys.excepthook = sys.__excepthook__
        try:
            self.shell.install()
            self.assertIs(sys.excepthook, self.shell._one_write_excepthook)
        finally:
            sys.excepthook = orig

    def test_uninstall_gives_the_hook_back(self):
        orig = sys.excepthook
        sys.excepthook = sys.__excepthook__
        try:
            self.shell.install()
            self.shell.uninstall()
            self.assertIs(sys.excepthook, sys.__excepthook__)

            def theirs(*a):
                pass
            sys.excepthook = theirs
            self.shell.uninstall()
            self.assertIs(sys.excepthook, theirs, "a foreign hook is kept")
        finally:
            sys.excepthook = orig


if __name__ == "__main__":
    unittest.main()
