"""Round-5 WS-SHELL item R130, headless: the round-4 GUI-pass fixes in shell.py.

    R130a ClickCard.set_compact() invalidates the card's layout, so a
          compact -> full round trip puts the title back where a fresh
          full card has it (GUI round 4: title 10 px high after launch).
    R130b EmptyView._fit_height() drops the mark, then the subtitle, then
          whole card rows in a short view, so nothing overlaps and nothing
          spills out of the view (GUI round 4: cards overlapped at 243 px).
    R130c uninstall() gives the status-bar brand mark back only in light
          mode: in dark Part the dark-ink mark is an invisible smudge. A
          mark hidden by a dark uninstall still comes back in a later light
          one (the flag lives on the widget, not in _S).

Each has a sabotage case that removes the fix and shows the check failing.

    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \
        -m unittest discover -s addon/AcadAgent/tests -p 'test_shell_round5.py' -v
"""
import inspect
import textwrap
import unittest

import _shell_fakes as F
from PySide6 import QtCore, QtWidgets

from test_shell_lifecycle import ShellCase

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _without_line(func, needle):
    """`func` recompiled with every source line containing `needle` removed:
    the sabotage build of a fix, from the shipped source, not a copy."""
    src = textwrap.dedent(inspect.getsource(func))
    kept = [ln for ln in src.splitlines() if needle not in ln]
    assert len(kept) < len(src.splitlines()), "sabotage removed nothing"
    ns = {}
    exec("\n".join(kept), func.__globals__, ns)        # noqa: S102
    return ns[func.__name__]


# ------------------------------------------------------------------ R130a
class TestCardCompactRoundTrip(unittest.TestCase):
    def setUp(self):
        F.install_fakes(QtWidgets.QMainWindow())
        from acadagent import shell
        self.shell = shell
        self.host = QtWidgets.QWidget()
        self.host.resize(500, 400)
        self.host.show()
        self.orig = shell.ClickCard.set_compact

    def tearDown(self):
        self.shell.ClickCard.set_compact = self.orig
        self.host.close()
        self.host.deleteLater()
        F.pump(10)

    def card(self, x=0):
        c = self.shell.ClickCard("cube", "Title", "Sub text.", self.host)
        c.move(x, 0)
        c.show()
        F.pump(20)
        return c

    @staticmethod
    def title_y(c):
        F.pump(20)
        return c.findChild(QtWidgets.QLabel, "CardTitle").geometry().y()

    def round_trip(self):
        fresh = self.title_y(self.card(0))
        c = self.card(250)
        self.assertEqual(self.title_y(c), fresh, "precondition")
        c.set_compact(True)
        compact = self.title_y(c)
        c.set_compact(False)
        return fresh, compact, self.title_y(c), c

    def test_round_trip_puts_the_title_back(self):
        fresh, compact, back, c = self.round_trip()
        print("\nR130a title y fresh/compact/back: %d/%d/%d"
              % (fresh, compact, back))
        self.assertLess(compact, fresh, "compact card should drop icon+gap")
        self.assertEqual(back, fresh)
        self.assertEqual(c.height(), 150)

    def test_compact_title_sits_at_the_top_margin(self):
        c = self.card()
        c.set_compact(True)
        self.assertEqual(self.title_y(c), c.layout().contentsMargins().top())
        self.assertEqual(c.height(), 100)

    def test_sabotage_without_invalidate_the_title_stays_high(self):
        self.shell.ClickCard.set_compact = _without_line(
            self.orig, "self.layout().invalidate()")
        fresh, _compact, back, _c = self.round_trip()
        print("\nR130a sabotage title y fresh/back: %d/%d" % (fresh, back))
        self.assertNotEqual(back, fresh, "the invalidate is not load-bearing")


# ------------------------------------------------------------------ R130b
SIZES = [(900, 600), (900, 400), (900, 243), (900, 200), (900, 120),
         (600, 600), (600, 400), (600, 243), (600, 180), (400, 243),
         (250, 600), (250, 243), (900, 60)]


class TestEmptyViewFit(unittest.TestCase):
    def setUp(self):
        F.install_fakes(QtWidgets.QMainWindow())
        from acadagent import shell, viewport
        self.shell, self.viewport = shell, viewport
        self.orig_fit = shell.EmptyView._fit_height
        self.orig_crane = viewport.crane_parts
        viewport.crane_parts = lambda: ["crane"]      # all three cards
        self.host = QtWidgets.QWidget()
        self.host.resize(1000, 700)
        self.host.show()

    def tearDown(self):
        self.shell.EmptyView._fit_height = self.orig_fit
        self.viewport.crane_parts = self.orig_crane
        self.host.close()
        self.host.deleteLater()
        F.pump(10)

    def view(self):
        v = self.shell.EmptyView(self.host)
        v.restyle()
        v.show()
        F.pump(20)
        return v

    @staticmethod
    def pieces(v):
        out = [("mark", v.mark), ("title", v.title), ("sub", v.sub)]
        out += [("card%d" % i, c) for i, c in enumerate(v.cards)]
        return [(n, w) for n, w in out if w.isVisible()]

    def layout_at(self, v, w, h):
        v.resize(w, h)
        F.pump(30)
        v.layout().activate()
        return self.pieces(v)

    def defects(self, v, w, h):
        shown = self.layout_at(v, w, h)
        bad = []
        rect = v.rect()
        for n, wd in shown:
            if not rect.contains(wd.geometry()):
                bad.append("%s %r outside %r" % (n, wd.geometry(), rect))
        for i, (n1, w1) in enumerate(shown):
            for n2, w2 in shown[i + 1:]:
                if w1.geometry().intersects(w2.geometry()):
                    bad.append("%s overlaps %s" % (n1, n2))
        return bad, [n for n, _ in shown]

    def test_no_overlap_and_nothing_outside_at_any_size(self):
        v = self.view()
        for w, h in SIZES:
            bad, shown = self.defects(v, w, h)
            print("\nR130b %dx%d shows %s" % (w, h, shown), end="")
            self.assertEqual(bad, [], "%dx%d" % (w, h))
            self.assertIn("title", shown, "%dx%d: the title always stays"
                          % (w, h))

    def test_tall_view_shows_everything(self):
        v = self.view()
        _bad, shown = self.defects(v, 900, 600)
        self.assertEqual(shown, ["mark", "title", "sub",
                                 "card0", "card1", "card2"])
        _bad, shown = self.defects(v, 600, 600)       # two rows, compact
        self.assertEqual(len([n for n in shown if n.startswith("card")]), 3)

    def test_drop_order_mark_then_sub_then_rows(self):
        v = self.view()
        seen = []
        for h in range(700, 40, -7):
            _bad, shown = self.defects(v, 600, h)
            state = ("mark" in shown, "sub" in shown,
                     len([n for n in shown if n.startswith("card")]))
            if not seen or seen[-1] != state:
                seen.append(state)
        # Shrinking never brings a dropped piece back.
        for a, b in zip(seen, seen[1:]):
            self.assertGreaterEqual(a[0], b[0], seen)
            self.assertGreaterEqual(a[1], b[1], seen)
            self.assertGreaterEqual(a[2], b[2], seen)
            if b[2] < a[2]:
                self.assertFalse(b[0] or b[1],
                                 "a card row went before mark/sub: %r" % seen)
            if b[1] < a[1]:
                self.assertFalse(b[0], "sub went before the mark: %r" % seen)
        # Whole rows only (2 per row at 600 px, 3 cards).
        self.assertTrue({s[2] for s in seen} <= {0, 2, 3}, seen)
        print("\nR130b drop sequence at 600 px (mark, sub, cards): %r" % seen)

    def test_growing_back_restores_everything(self):
        v = self.view()
        self.defects(v, 600, 120)
        _bad, shown = self.defects(v, 900, 600)
        self.assertEqual(shown, ["mark", "title", "sub",
                                 "card0", "card1", "card2"])

    def test_no_crane_keeps_its_card_hidden(self):
        self.viewport.crane_parts = lambda: []
        v = self.view()
        for w, h in ((900, 600), (600, 243), (600, 120)):
            bad, shown = self.defects(v, w, h)
            self.assertEqual(bad, [])
            self.assertNotIn("card0", shown)

    def test_sabotage_without_the_fit_cards_overlap(self):
        self.shell.EmptyView._fit_height = lambda self, h: None
        v = self.view()
        bad, shown = self.defects(v, 600, 243)
        print("\nR130b sabotage 600x243: %s" % bad)
        self.assertNotEqual(bad, [], "the fit is not load-bearing")


# ------------------------------------------------------------------ R130c
class TestStatusMarkByMode(ShellCase):
    def setUp(self):
        super().setUp()
        self.orig_mode = self.style.mode
        self.orig_uninstall = self.shell.uninstall

    def tearDown(self):
        self.style.mode = self.orig_mode
        self.shell.uninstall = self.orig_uninstall
        super().tearDown()

    def mark(self):
        for lbl in self.mw.statusBar().findChildren(QtWidgets.QLabel):
            pm = lbl.pixmap()
            if pm is not None and not pm.isNull():
                return lbl
        self.fail("fixture has no status-bar mark")

    def cycle(self, mode):
        self.style.mode = lambda: mode
        self.shell._S.clear()
        self.shell.install()
        F.pump(30)
        self.shell._hide_status_mark()
        self.assertFalse(self.mark().isVisible(), "installed: mark hidden")
        self.shell.uninstall()
        F.pump(10)
        return self.mark().isVisible()

    def test_light_part_gets_the_mark_back(self):
        self.assertTrue(self.cycle("light"))

    def test_dark_part_keeps_it_hidden(self):
        self.assertFalse(self.cycle("dark"))

    def test_hidden_in_dark_still_comes_back_in_light(self):
        self.assertFalse(self.cycle("dark"))
        self.assertTrue(self.mark().property("atechStatusMark"))
        self.chrome._ACTIVE[0] = False
        self.assertTrue(self.cycle("light"),
                        "a mark a dark uninstall hid was never given back")

    def test_other_status_labels_untouched(self):
        others = [l for l in self.mw.statusBar().findChildren(QtWidgets.QLabel)
                  if l is not self.mark()]
        self.cycle("dark")
        self.assertTrue(all(l.isVisible() for l in others))

    def test_sabotage_always_visible_shows_the_smudge_in_dark(self):
        src = textwrap.dedent(inspect.getsource(self.orig_uninstall))
        assert "lbl.setVisible(not dark)" in src
        src = src.replace("lbl.setVisible(not dark)", "lbl.setVisible(True)")
        ns = {}
        exec(src, self.orig_uninstall.__globals__, ns)  # noqa: S102
        self.shell.uninstall = ns["uninstall"]
        self.assertTrue(self.cycle("dark"),
                        "the mode test is not load-bearing")

    def test_sabotage_without_the_widget_flag_light_never_gets_it_back(self):
        orig = self.shell._hide_status_mark
        src = textwrap.dedent(inspect.getsource(orig))
        assert "(lbl.isVisible() or ours)" in src
        ns = {}
        exec(src.replace("(lbl.isVisible() or ours)", "lbl.isVisible()"),
             orig.__globals__, ns)                     # noqa: S102
        self.shell._hide_status_mark = ns["_hide_status_mark"]
        try:
            self.assertFalse(self.cycle("dark"))
            self.chrome._ACTIVE[0] = False
            self.style.mode = lambda: "light"
            self.shell._S.clear()
            self.shell.install()
            F.pump(30)
            self.shell._hide_status_mark()
            self.shell.uninstall()
            self.assertFalse(self.mark().isVisible(),
                             "the widget flag is not load-bearing")
        finally:
            self.shell._hide_status_mark = orig


if __name__ == "__main__":
    unittest.main()
