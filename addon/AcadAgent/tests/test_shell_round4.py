"""Round-4 WS-SHELL items (release PRD R59, R82, R106, R108, R109), headless.

    R109  shell._hide_dead_subwindows (the round-3 GUI-pass fix): a
          widgetless sub-window out of subWindowList() is hidden after
          restyle() and uninstall(), never deleted; live sub-windows and
          ones still holding a view are left alone. A sabotage case proves
          the test can fail.
    R82   fit_camera's FIT_MARGIN breath, checked with Coin's own projection;
          a board arriving in a LATER build still gets the module-face turn,
          once per document.
    R106  the Terminal dock never opens zsh's first-run wizard (checked with
          a real zsh on a pty and an empty HOME) and its header names the
          shell, then the chat engine as such.
    R108  dark-mode uninstall keeps a dark background where the user had
          none (never passing it off as the user's), and the Atech meshes
          get two-sided lighting.
    R59   the icon/label gap on the top bar and view bar buttons, measured
          in rendered pixels.

    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \
        -m unittest discover -s addon/AcadAgent/tests -p 'test_shell_round4.py' -v
"""
import json
import math
import os
import random
import shutil
import tempfile
import time
import types
import unittest

import _shell_fakes as F
from PySide6 import QtCore, QtWidgets

from test_shell_lifecycle import ShellCase

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
VIEW = "User parameter:BaseApp/Preferences/View"
OWN = "User parameter:BaseApp/Preferences/Mod/AcadAgent"


def _alive(obj):
    import shiboken6
    return shiboken6.isValid(obj)


# ------------------------------------------------------------------ R109
class TestDeadSubwindows(ShellCase):
    def setUp(self):
        super().setUp()
        self.mdi = self.mw.centralWidget()
        self.live = self.mdi.subWindowList()[0]

    def dead(self):
        """FreeCAD's leftover: a QMdiSubWindow child of the MDI viewport,
        no widget, not in subWindowList(), shown again by a sheet change."""
        d = QtWidgets.QMdiSubWindow(self.mdi.viewport())
        d.setGeometry(0, 0, 400, 300)
        d.show()
        F.pump(10)
        self.assertIsNone(d.widget())
        self.assertNotIn(d, self.mdi.subWindowList(), "precondition")
        self.assertTrue(d.isVisible(), "precondition")
        return d

    def test_restyle_hides_it_and_never_deletes_it(self):
        self.shell.install()
        F.pump(30)
        d = self.dead()
        self.shell.restyle()
        F.pump(30)                                     # deleteLater would run
        self.assertTrue(_alive(d), "FreeCAD's object was deleted")
        self.assertFalse(d.isVisible())
        self.assertTrue(self.live.isVisible(), "a live sub-window was hidden")
        self.assertIn(self.live, self.mdi.subWindowList())

    def test_a_subwindow_that_still_holds_a_view_is_left_alone(self):
        self.shell.install()
        F.pump(30)
        held = QtWidgets.QMdiSubWindow(self.mdi.viewport())
        held.setWidget(QtWidgets.QLabel("view"))
        held.show()
        self.assertNotIn(held, self.mdi.subWindowList())
        self.shell.restyle()
        self.assertTrue(held.isVisible())

    def test_uninstall_hides_it_too(self):
        # uninstall() puts FreeCAD's sheets back: the same re-show.
        self.shell.install()
        F.pump(30)
        d = self.dead()
        self.shell.uninstall()
        F.pump(30)
        self.assertTrue(_alive(d))
        self.assertFalse(d.isVisible())
        self.assertTrue(self.live.isVisible())

    def test_sabotage_without_the_fix_it_stays_visible(self):
        self.shell.install()
        F.pump(30)
        d = self.dead()
        orig = self.shell._hide_dead_subwindows
        self.shell._hide_dead_subwindows = lambda: 0
        try:
            self.shell.restyle()
        finally:
            self.shell._hide_dead_subwindows = orig
        self.assertTrue(d.isVisible(), "the test could not fail")

    def test_returns_what_it_hid(self):
        self.shell.install()
        F.pump(30)
        self.dead()
        self.assertEqual(self.shell._hide_dead_subwindows(), 1)
        self.assertEqual(self.shell._hide_dead_subwindows(), 0)


# ------------------------------------------------------------------ R82
def _coin():
    from pivy import coin
    return coin


# R163: pip PySide6 (CI) has no pivy; the bundled python does. A skip,
# never a looser assertion: these tests measure with Coin's own camera.
try:
    import importlib.util as _ilu
    HAVE_PIVY = _ilu.find_spec("pivy") is not None
except (ImportError, ValueError):
    HAVE_PIVY = False
NO_PIVY = "pivy (Coin) is not installed: bundled python only"


@unittest.skipUnless(HAVE_PIVY, NO_PIVY)
class TestFitMargin(unittest.TestCase):
    """The margin, measured with Coin's projection: every point of the
    sphere stays at least ~margin away from the band's top and bottom."""

    def project(self, radius, w, h, reserve, ortho, margin):
        from acadagent import viewport as vp
        coin = _coin()
        center, look, up = (5.0, 2.0, 40.0), (-0.577, 0.577, -0.577), (0, 0, 1)
        cam = coin.SoOrthographicCamera() if ortho \
            else coin.SoPerspectiveCamera()
        cam.orientation.setValue(coin.SbRotation(*vp.look_quaternion(look, up)))
        pos, size = vp.fit_camera(center, radius, look, up, w, h, reserve,
                                  ortho=ortho, margin=margin)
        cam.position.setValue(coin.SbVec3f(*pos))
        if ortho:
            cam.height.setValue(size)
        cam.focalDistance.setValue(radius * 3.0 if ortho else size)
        cam.nearDistance.setValue(0.001)
        cam.farDistance.setValue(1e6)
        vv = cam.getViewVolume(w / h)
        if w < h:
            vv.scale(h / w)
        rnd = random.Random(4)
        ys = []
        for _ in range(800):
            d = [rnd.gauss(0, 1) for _ in range(3)]
            n = math.sqrt(sum(c * c for c in d))
            p = [center[i] + radius * d[i] / n for i in range(3)]
            ys.append(vv.projectToScreen(coin.SbVec3f(*p)).getValue()[1])
        return min(ys), max(ys)

    def test_tall_fit_keeps_a_breath_top_and_bottom(self):
        from acadagent import viewport as vp
        m = vp.FIT_MARGIN
        self.assertGreater(m, 0.0)
        for ortho in (True, False):
            reserve = 70 / 900.0
            lo, hi = self.project(60.0, 1400, 900, reserve, ortho, m)
            band = 1.0 - reserve
            tag = "ortho=%s" % ortho
            # ortho: exact (radius*m of a band that holds 2*radius*(1+m))
            want = band * m / (2 * (1 + m)) * (0.9 if ortho else 0.5)
            self.assertGreaterEqual(1.0 - hi, want, tag + " flush at the top")
            self.assertGreaterEqual(lo - reserve, want,
                                    tag + " flush on the pill")

    def test_without_margin_the_sphere_touches_the_edge(self):
        # proves the check above can fail: margin 0 is flush (< 0.5 %)
        lo, hi = self.project(60.0, 1400, 900, 70 / 900.0, True, 0.0)
        self.assertLess(1.0 - hi, 0.005)


class _BB:
    def __init__(self, lo, hi):
        (self.XMin, self.YMin, self.ZMin), (self.XMax, self.YMax, self.ZMax) \
            = lo, hi


class _Shape:
    def __init__(self, lo, hi):
        self.BoundBox = _BB(lo, hi)

    def isNull(self):                                  # noqa: N802
        return False


def _obj(role, lo, hi, **kw):
    return types.SimpleNamespace(AtechRole=role, Shape=_Shape(lo, hi), **kw)


class TestLateBoardFacing(unittest.TestCase):
    def setUp(self):
        F.install_fakes(QtWidgets.QMainWindow())
        from acadagent import viewport
        self.vp = viewport
        self.calls = []
        vp = viewport
        self.saved = (vp._view, vp.look_from, vp.fit_all, vp.iso_and_fit,
                      vp.in_view)
        vp._view = lambda: object()
        vp.look_from = lambda x, y, z, v=None: \
            self.calls.append(("look", (x, y, z))) or True
        vp.fit_all = lambda *a: self.calls.append(("fit",)) or True
        vp.iso_and_fit = lambda: self.calls.append(("iso",)) or True
        vp.in_view = lambda v, objs, reserve=None: True

    def tearDown(self):
        (self.vp._view, self.vp.look_from, self.vp.fit_all,
         self.vp.iso_and_fit, self.vp.in_view) = self.saved

    def test_board_in_a_later_build_is_faced_once(self):
        vp = self.vp
        doc = types.SimpleNamespace(Name="LateBoard%d" % id(self), Objects=[
            _obj(None, (0, 0, 0), (10, 10, 10))])
        vp.frame_if_needed([], first=True, doc=doc)      # no board yet
        self.assertEqual(self.calls, [("iso",)])
        self.calls.clear()
        doc.Objects += [_obj("board", (0, 0, 0), (100, 3, 60)),
                        _obj("module", (10, 3, 10), (40, 20, 40))]
        self.assertTrue(vp.frame_if_needed([], first=False, doc=doc))
        self.assertEqual(self.calls, [("look", (0.6, 1.0, 0.5)), ("fit",)])
        self.calls.clear()
        # the user orbits; the next preview must not yank the camera back
        self.assertFalse(vp.frame_if_needed([], first=False, doc=doc))
        self.assertEqual(self.calls, [])

    def test_first_build_with_a_board_counts_as_faced(self):
        vp = self.vp
        doc = types.SimpleNamespace(Name="FirstBoard%d" % id(self), Objects=[
            _obj("board", (0, 0, 0), (100, 3, 60)),
            _obj("module", (10, -20, 10), (40, 0, 40))])
        vp.frame_if_needed([], first=True, doc=doc)
        self.assertEqual(self.calls, [("look", (0.6, -1.0, 0.5)), ("fit",)])
        self.calls.clear()
        self.assertFalse(vp.frame_if_needed([], first=False, doc=doc))


# ------------------------------------------------------------------ R106
ZSH = shutil.which("zsh")


class TestShellCommand(unittest.TestCase):
    def setUp(self):
        from acadagent import terminal
        self.t = terminal
        self.home = tempfile.mkdtemp(prefix="atech-home-")
        self.fb = tempfile.mkdtemp(prefix="atech-zdot-")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.fb, ignore_errors=True)

    def env(self, shell, **kw):
        e = {"HOME": self.home, "SHELL": shell, "PATH": "/usr/bin:/bin"}
        e.update(kw)
        return e

    def test_zsh_without_startup_files_gets_the_fallback(self):
        argv, env, name = self.t.shell_command(self.env("/usr/bin/zsh"),
                                               fallback_dir=self.fb)
        self.assertEqual(argv, ["/usr/bin/zsh", "-i"])
        self.assertEqual(name, "zsh")
        self.assertEqual(env["ZDOTDIR"], self.fb)

    def test_a_user_with_any_startup_file_keeps_their_own(self):
        for f in self.t.ZSH_STARTUP:
            p = os.path.join(self.home, f)
            open(p, "w").close()
            _a, env, _n = self.t.shell_command(self.env("/usr/bin/zsh"),
                                               fallback_dir=self.fb)
            self.assertNotIn("ZDOTDIR", env, f)
            os.remove(p)

    def test_the_users_zdotdir_is_where_zsh_looks(self):
        zd = os.path.join(self.home, "zconf")
        os.makedirs(zd)
        open(os.path.join(zd, ".zshrc"), "w").close()
        _a, env, _n = self.t.shell_command(
            self.env("/usr/bin/zsh", ZDOTDIR=zd), fallback_dir=self.fb)
        self.assertEqual(env["ZDOTDIR"], zd)

    def test_bash_and_explicit_commands_untouched(self):
        _a, env, name = self.t.shell_command(self.env("/bin/bash"),
                                             fallback_dir=self.fb)
        self.assertNotIn("ZDOTDIR", env)
        self.assertEqual(name, "bash")
        argv, env, _n = self.t.shell_command(self.env("/bin/bash"),
                                             ["/bin/sh", "-i"], self.fb)
        self.assertEqual(argv, ["/bin/sh", "-i"])

    def test_fallback_dir_is_private_and_holds_the_rc(self):
        d = self.t._zsh_fallback_dir()
        self.assertTrue(d and os.path.isdir(d))
        self.assertEqual(os.stat(d).st_mode & 0o777, 0o700)
        with open(os.path.join(d, ".zshrc"), encoding="utf-8") as f:
            self.assertEqual(f.read(), self.t.ZSH_FALLBACK_RC)
        self.assertFalse(d.startswith(os.path.expanduser("~") + os.sep))


def _wait(pred, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        F.pump(50)
        if pred():
            return True
    return False


@unittest.skipUnless(ZSH, "zsh is not installed")
class TestRealZshOnAPty(unittest.TestCase):
    """End to end: the dock's own start() with SHELL=zsh and an empty HOME."""

    def run_zsh(self, fallback):
        from acadagent import terminal
        home = tempfile.mkdtemp(prefix="atech-home-")
        saved_env = dict(os.environ)
        saved_fb = terminal._zsh_fallback_dir
        os.environ.update(HOME=home, SHELL=ZSH)
        os.environ.pop("ZDOTDIR", None)
        if not fallback:
            terminal._zsh_fallback_dir = lambda: None
        t = terminal.TerminalWidget(cwd=home)
        try:
            self.assertTrue(t.start())
            F.pump(800)
            t.write("q\n")                 # quits the wizard, if it is there
            t.write("echo READY-$((20+22))\n")
            _wait(lambda: "READY-42" in t.out.toPlainText(), 10)
            return t.out.toPlainText(), sorted(os.listdir(home))
        finally:
            t.close_session()
            t.deleteLater()
            terminal._zsh_fallback_dir = saved_fb
            os.environ.clear()
            os.environ.update(saved_env)
            shutil.rmtree(home, ignore_errors=True)

    def test_no_first_run_wizard(self):
        out, home_files = self.run_zsh(fallback=True)
        self.assertIn("READY-42", out)
        self.assertNotIn("zsh-newuser-install", out)
        self.assertEqual(home_files, [], "wrote into the user's home")

    def test_sabotage_without_the_fallback_the_wizard_runs(self):
        out, _h = self.run_zsh(fallback=False)
        self.assertIn("zsh-newuser-install", out, "the test could not fail")


class TestTerminalHeader(unittest.TestCase):
    def test_header_names_the_shell_then_the_engine(self):
        from acadagent import terminal_dock as td
        self.assertEqual(td.header_status("zsh"),
                         "zsh shell · checking the chat engine…")
        self.assertEqual(td.header_status("zsh", "Claude Code 2.1.232 — ready"),
                         "zsh shell · chat engine: Claude Code 2.1.232 — ready")
        self.assertEqual(td.header_status("bash", "Claude Code — ready", 0),
                         "bash exited (0) · chat engine: Claude Code — ready")

    def test_dock_header_follows_the_session(self):
        mw = QtWidgets.QMainWindow()
        F.install_fakes(mw)
        from acadagent import engine, terminal_dock
        orig = engine.status_line
        engine.status_line = lambda: "Claude Code — ready"
        try:
            body = terminal_dock._TerminalBody()
            body.term._command = ["/bin/sh", "-c", "exit 3"]
            body.term.shell_name = "sh"
            self.assertTrue(body.term.start())
            self.assertTrue(_wait(lambda: "exited" in body.status.text()),
                            body.status.text())
            self.assertTrue(_wait(lambda: "Claude Code" in body.status.text()))
            self.assertEqual(body.status.text(),
                             "sh exited (3) · chat engine: Claude Code — ready")
            for p in list(terminal_dock._PROBES):
                p.wait(3000)
            body.term.close_session()
            body.deleteLater()
        finally:
            engine.status_line = orig
            mw.deleteLater()
            F.pump(20)


# ------------------------------------------------------------------ R108
class TestDarkRestore(ShellCase):
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

    def test_dark_uninstall_keeps_a_dark_background_the_user_never_set(self):
        self.set_mode("dark")
        self.viewport.apply_view_theme()
        written = {k: self.keys()[k] for k in self.viewport.BACKGROUND_KEYS}
        self.shell.install()
        self.shell.uninstall()
        after = self.keys()
        for k, v in written.items():
            self.assertEqual(after.get(k), v, k)
        self.assertNotIn("OrbitStyle", after, "other absent keys still go")
        seeded = json.loads(self.fc.ParamGet(OWN).GetString(
            self.viewport._SEEDED_KEY, ""))
        self.assertEqual(seeded, written)

    def test_the_kept_background_never_passes_for_the_users(self):
        self.set_mode("dark")
        self.viewport.apply_view_theme()
        self.shell.install()
        self.shell.uninstall()                 # dark values seeded
        self.chrome._ACTIVE[0] = False
        self.style.mode = lambda: "light"      # next activation is light
        self.viewport.apply_view_theme()
        snap = self.viewport.saved_view_prefs()
        for k in self.viewport.BACKGROUND_KEYS:
            self.assertIsNone(snap[k], k)
        self.shell._S.clear()
        self.shell.install()
        self.shell.uninstall()                 # light: FreeCAD's default
        after = self.keys()
        for k in self.viewport.BACKGROUND_KEYS:
            self.assertNotIn(k, after, k)
        self.assertEqual(self.fc.ParamGet(OWN).GetString(
            self.viewport._SEEDED_KEY, ""), "")

    def test_a_background_the_user_set_always_comes_back(self):
        self.set_mode("dark")
        v = self.fc.ParamGet(VIEW)
        v.SetBool("Gradient", False)
        v.SetUnsigned("BackgroundColor", 0x336699FF)
        self.viewport.apply_view_theme()
        self.shell.install()
        self.shell.uninstall()
        after = self.keys()
        self.assertEqual(after["Gradient"], False)
        self.assertEqual(after["BackgroundColor"], 0x336699FF)
        self.assertNotIn("BackgroundColor2", after)

    def test_light_uninstall_is_unchanged(self):
        self.set_mode("light")
        self.viewport.apply_view_theme()
        self.shell.install()
        self.shell.uninstall()
        after = self.keys()
        for k in self.viewport.BACKGROUND_KEYS:
            self.assertNotIn(k, after, k)


class _VO:
    def __init__(self, lighting="One side"):
        self.Lighting = lighting


class TestTwoSideMeshes(unittest.TestCase):
    def setUp(self):
        F.install_fakes(QtWidgets.QMainWindow())
        from acadagent import viewport
        self.vp = viewport

    def test_only_atech_meshes_change(self):
        board = types.SimpleNamespace(AtechRole="board", TypeId="Mesh::Feature",
                                      ViewObject=_VO(), Name="Board")
        mod = types.SimpleNamespace(AtechRole="module", TypeId="Mesh::Feature",
                                    ViewObject=_VO(), Name="Mod")
        user = types.SimpleNamespace(TypeId="Mesh::Feature", ViewObject=_VO(),
                                     Name="Scan")
        part = types.SimpleNamespace(AtechRole="case", TypeId="Part::Feature",
                                     ViewObject=_VO(), Name="Case")
        console = types.SimpleNamespace(AtechRole="board",
                                        TypeId="Mesh::Feature", Name="NoGui")
        doc = types.SimpleNamespace(Objects=[board, mod, user, part, console])
        self.assertEqual(self.vp.two_side_meshes(doc), 2)
        self.assertEqual(board.ViewObject.Lighting, "Two side")
        self.assertEqual(mod.ViewObject.Lighting, "Two side")
        self.assertEqual(user.ViewObject.Lighting, "One side")
        self.assertEqual(part.ViewObject.Lighting, "One side")
        self.assertEqual(self.vp.two_side_meshes(doc), 0, "idempotent")

    def test_modified_flag_is_kept(self):
        """A view property change marks the GUI document modified; a clean
        saved document must not start asking 'save changes?' (review)."""
        import sys

        class _GDoc:
            def __init__(self, m):
                self.Modified = m

        class _MarkingVO:                  # FreeCAD's behaviour on a set
            def __init__(self, g):
                self.__dict__["g"] = g
                self.__dict__["Lighting"] = "One side"

            def __setattr__(self, k, v):
                self.__dict__[k] = v
                self.g.Modified = True

        gui = sys.modules["FreeCADGui"]
        orig = gui.getDocument
        try:
            for start in (False, True):
                g = _GDoc(start)
                gui.getDocument = lambda name, g=g: g
                board = types.SimpleNamespace(
                    AtechRole="board", TypeId="Mesh::Feature",
                    ViewObject=_MarkingVO(g), Name="Board")
                doc = types.SimpleNamespace(Name="D", Objects=[board])
                self.assertEqual(self.vp.two_side_meshes(doc), 1)
                self.assertEqual(board.ViewObject.Lighting, "Two side")
                self.assertIs(g.Modified, start, start)
        finally:
            gui.getDocument = orig


class TestTickLightsMeshes(ShellCase):
    def test_tick_applies_it_to_the_active_document(self):
        board = types.SimpleNamespace(AtechRole="board", TypeId="Mesh::Feature",
                                      ViewObject=_VO(), Name="Board")
        self.fc.ActiveDocument = types.SimpleNamespace(Objects=[board])
        self.shell.install()
        self.shell._tick()
        self.assertEqual(board.ViewObject.Lighting, "Two side")


# ------------------------------------------------------------------ R59
def _ink_runs(img):
    """Column runs that differ from the button's background (left edge)."""
    bg = img.pixelColor(1, img.height() // 2)
    cols = []
    for x in range(img.width()):
        ink = False
        for y in range(img.height()):
            c = img.pixelColor(x, y)
            if abs(c.red() - bg.red()) + abs(c.green() - bg.green()) \
                    + abs(c.blue() - bg.blue()) > 60:
                ink = True
                break
        cols.append(ink)
    runs, s = [], None
    for x, i in enumerate(cols + [False]):
        if i and s is None:
            s = x
        if not i and s is not None:
            runs.append((s, x - 1))
            s = None
    return runs


class TestIconLabelGap(ShellCase):
    """Rendered pixels: the gap between an icon's last ink column and the
    label's first. Qt alone leaves 2-3 px (measured here on the bare text);
    icon_label brings it to 5-6 px."""

    def gap(self, b, text):
        b.setText(text)
        F.pump(10)
        runs = _ink_runs(b.grab().toImage())
        self.assertGreaterEqual(len(runs), 2, (b.accessibleName(), runs))
        icon = b.iconSize().width()
        first = runs[0]
        self.assertLessEqual(first[1] - first[0] + 1, icon + 1, runs)
        return runs[1][0] - first[1] - 1

    def buttons(self):
        s = self.shell
        s.install()
        F.pump(50)
        out = [b for b, _n in s._S["topbar"]["btns"] if b.accessibleName()
               in ("Workbench", "Terminal")]
        out.append(s._S["overlay"].bar.btn_ask)
        return out

    def test_gap_is_five_to_seven_px(self):
        gaps = {}
        for b in self.buttons():
            name = b.accessibleName()
            with_space = self.gap(b, self.shell.icon_label(name))
            bare = self.gap(b, name)
            gaps[name] = (bare, with_space)
            self.assertLessEqual(bare, 3, (name, gaps[name]))
            self.assertGreaterEqual(with_space, 5, (name, gaps[name]))
            self.assertLessEqual(with_space, 7, (name, gaps[name]))
        print("\nR59 icon/label gap px (bare -> icon_label): %s" % gaps)


if __name__ == "__main__":
    unittest.main()
