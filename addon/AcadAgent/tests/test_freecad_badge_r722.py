"""R722: "Based on FreeCAD" with the official wordmark.

  The in-app wordmark files are byte-for-byte the FPA logo kit copies in
  docs/brand/freecad/ (the FPA's rules: use them unaltered); the badge
  renders the logo and a click opens freecad.org; the root licence carries
  the credit term.

    QT_QPA_PLATFORM=offscreen python -m unittest -v test_freecad_badge_r722
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
except ImportError:
    QtWidgets = None

NAMES = ("FreeCAD-wordmark.svg", "FreeCAD-wordmark-light.svg")


class TestFiles(unittest.TestCase):
    def test_wordmark_unaltered(self):
        for n in NAMES:
            with open(os.path.join(ADDON, "acadagent", "brand_freecad", n), "rb") as a, \
                    open(os.path.join(REPO, "docs", "brand", "freecad", n), "rb") as b:
                self.assertEqual(a.read(), b.read(), n)

    def test_licence_credit_term(self):
        with open(os.path.join(REPO, "LICENSE"), encoding="utf-8") as fh:
            self.assertIn("Version 3, 29 June 2007", fh.read())
        with open(os.path.join(REPO, "LICENSE-ATTRIBUTION.md"), encoding="utf-8") as fh:
            t = fh.read()
        self.assertIn("section 7(b)", t)
        self.assertIn("Based on Atech Atelier by Atech", t)
        self.assertIn("built on FreeCAD", t)


@unittest.skipIf(QtWidgets is None, "PySide6 not available (run with the bundled python)")
class TestBadge(unittest.TestCase):
    def test_logo_and_link(self):
        from acadagent import shell, style
        for m in ("light", "dark"):
            pm = style.freecad_wordmark(16, m)
            self.assertIsNotNone(pm, m)
            self.assertGreater(pm.width() / pm.height(), 3)
        b = shell.FreeCadBadge(16)
        self.assertFalse(b.logo.pixmap().isNull())
        opened = []
        real = QtGui.QDesktopServices.openUrl
        QtGui.QDesktopServices.openUrl = lambda u: opened.append(u.toString())
        try:
            ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonRelease, QtCore.QPointF(3, 3),
                                   QtCore.QPointF(3, 3), QtCore.Qt.LeftButton,
                                   QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
            b.mouseReleaseEvent(ev)
        finally:
            QtGui.QDesktopServices.openUrl = real
        self.assertEqual(opened, ["https://www.freecad.org"])

    def test_home_shows_it(self):
        from acadagent import shell
        h = shell.HomeView()
        h.restyle()
        self.assertFalse(h.based_on.logo.pixmap().isNull())


if __name__ == "__main__":
    unittest.main()
