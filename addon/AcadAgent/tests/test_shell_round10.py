"""Round-10 WS-SHELL items R195 and R196, headless.

    R195  The Model tab hosts FreeCAD's tree + property view, whose vertical
          splitter FreeCAD keeps about 50:50 (GUI r9_07: the 25-part crane
          tree scrolled after 13 rows over an empty property editor). While
          hosted the tree gets two thirds; on hand-back FreeCAD's own split
          is restored, or an even split when the captured one read [0, 0]
          (the window not shown yet at startup, measured r9).
          Sabotage: the pre-fix set_model_widget/take_model_widget (no
          split handling), run against the same widget, fails both checks.
    R196  The sample crane opened as "SampleCrane : 1*". Headless the App
          document is clean after the load (isTouched() False - measured
          under freecadcmd, and re-checked by the last test here when the
          bundle is present); the flag is Gui::Document's, which FreeCAD
          sets on every new object. open_reference_model() now clears it.
          Sabotage: with _mark_unmodified a no-op the flag stays True.

    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest discover -s addon/AcadAgent/tests -p 'test_shell_round10.py' -v
"""
import os
import subprocess
import tempfile
import types
import unittest
from unittest import mock

import _shell_fakes as F
from PySide6 import QtCore, QtWidgets

from test_shell_lifecycle import ShellCase

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
REPO = os.path.abspath(os.path.join(F.ADDON, "..", ".."))
FREECADCMD = os.path.join(REPO, "dist", "build", "squashfs-root", "usr",
                          "bin", "freecadcmd")


def combo_view():
    """Shaped like FreeCAD's Model dock content: a tree over a property
    view in one vertical splitter, split evenly the way FreeCAD keeps it."""
    w = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    sp = QtWidgets.QSplitter(QtCore.Qt.Vertical)
    tree = QtWidgets.QTreeWidget()
    tree.setObjectName("ModelTree")
    sp.addWidget(tree)
    sp.addWidget(QtWidgets.QTableWidget(4, 2))
    lay.addWidget(sp)
    return w, sp


def tree_share(sp):
    s = sp.sizes()
    return s[0] / float(sum(s)) if sum(s) else None


# ------------------------------------------------------------------ R195
class TestModelSplit(ShellCase):
    def setUp(self):
        super().setUp()
        self.md = self.mw.findChild(QtWidgets.QDockWidget, "Model")
        self.combo, self.sp = combo_view()
        self.md.setWidget(self.combo)
        F.pump(30)
        self.sp.setSizes([400, 400])
        F.pump(30)
        self.before = self.sp.sizes()

    def host_and_return(self):
        s = self.shell
        s.install()
        F.pump(50)
        body = s._S["body"]
        body.show_page(1)                       # the Model tab
        F.pump(50)
        hosted = tree_share(self.sp)
        s.uninstall()
        F.pump(50)
        return hosted, tree_share(self.sp)

    def test_captured_split_is_even(self):
        """The fixture is the state R195 describes, not an assumption."""
        self.assertGreater(sum(self.before), 0)
        self.assertAlmostEqual(tree_share(self.sp), 0.5, delta=0.02)

    def test_tree_two_thirds_hosted_and_split_restored(self):
        hosted, back = self.host_and_return()
        self.assertIs(self.md.widget(), self.combo, "not handed back")
        self.assertAlmostEqual(hosted, 2 / 3.0, delta=0.02)
        self.assertAlmostEqual(back, tree_share_of(self.before), delta=0.02)

    def test_ten_switches_do_not_drift(self):
        """Each install re-captures; the restore must not ratchet toward
        the hosted two thirds."""
        for _ in range(10):
            hosted, back = self.host_and_return()
            self.assertAlmostEqual(hosted, 2 / 3.0, delta=0.02)
            self.assertAlmostEqual(back, 0.5, delta=0.02)

    def test_sabotage_old_code_fails_both_checks(self):
        Sidebar = self.shell.Sidebar

        def old_set(self_, w):
            self_.model_widget = w
            self_._model_lay.addWidget(w, 1)
            w.show()
            self_._has_doc = None
            self_.sync_model_hint()

        def old_take(self_):
            w, self_.model_widget = self_.model_widget, None
            if w is not None:
                self_._model_lay.removeWidget(w)
                w.show()
            return w

        with mock.patch.object(Sidebar, "set_model_widget", old_set), \
                mock.patch.object(Sidebar, "take_model_widget", old_take):
            hosted, _back = self.host_and_return()
        # without the fix the tree keeps half: the hosted check would fail
        self.assertGreater(abs(hosted - 2 / 3.0), 0.1)
        # and a hosted-only fix with no hand-back leaves Part at 2/3
        self.shell.install()
        F.pump(50)
        with mock.patch.object(Sidebar, "take_model_widget", old_take):
            self.shell.uninstall()
        F.pump(50)
        self.assertGreater(abs(tree_share(self.sp) - 0.5), 0.1)


def tree_share_of(sizes):
    return sizes[0] / float(sum(sizes))


class TestZeroCapture(ShellCase):
    """At startup the splitter is not shown and reads [0, 0]."""

    def test_zero_capture_hands_back_even_split(self):
        combo, sp = combo_view()                  # never shown
        self.assertEqual(sp.sizes(), [0, 0])
        body = self.shell.Sidebar(QtWidgets.QWidget(), combo)
        self.assertIsNone(body._model_split[1])
        w = body.take_model_widget()
        self.assertIs(w, combo)
        host = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(host)
        lay.addWidget(w)
        host.resize(300, 800)
        host.show()
        F.pump(50)
        self.assertAlmostEqual(tree_share(sp), 0.5, delta=0.02)
        host.close()
        body.deleteLater()
        host.deleteLater()

    def test_zero_capture_hosted_gets_two_thirds(self):
        combo, sp = combo_view()
        body = self.shell.Sidebar(QtWidgets.QWidget(), combo)
        body.resize(300, 900)
        body.show()
        body.show_page(1)
        F.pump(50)
        self.assertAlmostEqual(tree_share(sp), 2 / 3.0, delta=0.02)
        body.take_model_widget()
        body.close()
        body.deleteLater()


# ------------------------------------------------------------------ R196
class _GuiDoc:
    def __init__(self):
        self.Modified = True           # what FreeCAD's slotNewObject leaves


class _Doc:
    def __init__(self, name):
        self.Name = name
        self.Objects = []

    def addObject(self, _t, name):                     # noqa: N802
        o = types.SimpleNamespace(Name=name, ViewObject=None, Shape=None)
        self.Objects.append(o)
        return o

    def recompute(self):
        pass


class _Shape:
    def read(self, _f):
        pass

    def isNull(self):                                  # noqa: N802
        return False

    Solids = [object()]


class TestSampleOpensUnmodified(ShellCase):
    def load(self, sabotage=False):
        vp = self.viewport
        gdocs = {}

        def get_doc(name):
            return gdocs.setdefault(name, _GuiDoc())

        docs = {}

        def new_doc(name):
            docs[name] = _Doc(name)
            return docs[name]

        part = types.ModuleType("Part")
        part.Shape = _Shape
        patches = [
            mock.patch.object(vp, "crane_parts",
                              lambda: ["/x/base.brep", "/x/boom.brep"]),
            mock.patch.object(vp, "iso_and_fit", lambda: True),
            mock.patch.object(self.gui, "getDocument", get_doc,
                              create=True),
            mock.patch.object(self.fc, "newDocument", new_doc),
            mock.patch.dict("sys.modules", {"Part": part}),
        ]
        if sabotage:
            patches.append(mock.patch.object(vp, "_mark_unmodified",
                                             lambda d: None))
        for p in patches:
            p.start()
        try:
            doc, made, skipped = vp.open_reference_model("SampleCrane")
        finally:
            for p in reversed(patches):
                p.stop()
        return doc, made, skipped, get_doc(doc.Name)

    def test_not_modified_after_open(self):
        doc, made, skipped, gdoc = self.load()
        self.assertEqual((made, skipped), (2, []))
        self.assertFalse(gdoc.Modified)

    def test_sabotage_flag_stays(self):
        _doc, _m, _s, gdoc = self.load(sabotage=True)
        self.assertTrue(gdoc.Modified)

    def test_no_gui_is_harmless(self):
        doc = _Doc("D")
        with mock.patch.object(self.viewport, "_gui", lambda: None):
            self.assertFalse(self.viewport._mark_unmodified(doc))

    def test_raising_gui_is_logged_not_raised(self):
        class Bad:
            @property
            def Modified(self):                        # noqa: N802
                raise RuntimeError("document closed")

            @Modified.setter
            def Modified(self, v):                     # noqa: N802
                raise RuntimeError("document closed")

        with mock.patch.object(self.gui, "getDocument", lambda n: Bad(),
                               create=True):
            self.assertFalse(self.viewport._mark_unmodified(_Doc("D")))
        self.assertTrue(any("sample left modified" in ln
                            for ln in self.fc.Console.lines))


PROBE = r'''
import sys
sys.path.insert(0, %r)
from acadagent import viewport as V
doc, n, sk = V.open_reference_model("R196Probe")
print("R196 n=%%d touched=%%s objs=%%d" %% (n, doc.isTouched(),
      sum(1 for o in doc.Objects if o.State and "Touched" in o.State)))
import FreeCAD
FreeCAD.closeDocument(doc.Name)
'''


@unittest.skipUnless(os.access(FREECADCMD, os.X_OK), "no bundled freecadcmd")
class TestAppDocumentClean(unittest.TestCase):
    """The real load, headless: the App side of the document is clean, so
    the "*" is the GUI flag the fix clears (the cause is FreeCAD's)."""

    def test_app_document_untouched_after_load(self):
        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(d, "probe.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write(PROBE % F.ADDON)
            env = dict(os.environ)
            env.pop("QT_QPA_PLATFORM", None)
            out = subprocess.run([FREECADCMD, script], cwd=d, env=env,
                                 capture_output=True, text=True, timeout=300)
        lines = [ln for ln in out.stdout.splitlines()
                 if ln.startswith("R196 ")]
        if not lines:
            self.fail("probe printed nothing:\n" + out.stdout[-2000:]
                      + out.stderr[-2000:])
        n = int(lines[0].split("n=")[1].split()[0])
        if n == 0:
            self.skipTest("sample crane not built in this checkout")
        self.assertIn("touched=False", lines[0])
        self.assertIn("objs=0", lines[0])


if __name__ == "__main__":
    unittest.main()
