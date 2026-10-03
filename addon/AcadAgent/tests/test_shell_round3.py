"""Round-3 WS-SHELL items (release PRD R59, R82, R95, R96, R99), headless.

    R95  "Ask about this view" answers IN THE CHAT (vision.ask_in_chat), not
         in the Terminal dock; the dock's dev strings are gone.
    R96  terminal.clean_env() applies the pre-AppRun snapshot (R61), checked
         end to end against a real bash run of a patched AppRun.
    R99  the GUI-pass fixes: notification button matched by objectName
         `notificationArea`, status bar pinned to STATUS_H across a Part round
         trip and restored on uninstall, nav-style icon replaced and restored.
         (R59 is the user-visible half of the same fixes.)
    R82  fit_camera leaves the view bar's band free, checked with Coin's OWN
         projection (pivy), not with the formula under test; the first build
         with an Atech board looks at the module face.

    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \
        -m unittest discover -s addon/AcadAgent/tests -p 'test_shell_round3.py' -v

Measured names used by the fakes: `notificationArea` is a UTF-16 string
literal in usr/lib/libFreeCADGui.so (FreeCAD 1.1.3); `NavigationIndicator`
is set by usr/Mod/Tux/NavigationIndicatorGui.py:668 on a QPushButton
subclass whose icon setCurrent() replaces on a navigation-style change.
"""
import math
import os
import random
import subprocess
import sys
import tempfile
import shutil
import types
import unittest

import _shell_fakes as F
from PySide6 import QtGui, QtWidgets

from test_shell_lifecycle import ShellCase

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
BRANDING = os.path.join(REPO, "branding")
APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _solid_icon(color):
    pm = QtGui.QPixmap(16, 16)
    pm.fill(QtGui.QColor(color))
    return QtGui.QIcon(pm)


def _img(icon):
    return icon.pixmap(16, 16).toImage()


# ------------------------------------------------------------------ R95
class TestAskAboutViewGoesToChat(ShellCase):
    def setUp(self):
        super().setUp()
        from acadagent import vision
        self.vision = vision
        self.calls = []
        self._orig = vision.ask_in_chat
        vision.ask_in_chat = lambda *a, **k: self.calls.append((a, k)) or True

    def tearDown(self):
        self.vision.ask_in_chat = self._orig
        super().tearDown()

    def test_view_bar_button_asks_in_the_chat(self):
        from acadagent import terminal_dock
        self.shell.install()
        F.pump(30)
        btn = self.shell._S["overlay"].bar.btn_ask
        btn.click()
        self.assertEqual(len(self.calls), 1)
        panel = self.calls[0][1].get("panel")
        self.assertIs(panel, self.shell.chat_panel())
        self.assertIsNone(terminal_dock._DOCK, "the Terminal dock was opened")

    def test_menu_command_takes_the_same_path(self):
        from acadagent import commands, terminal_dock
        self.shell.install()
        commands.AskClaudeAboutView().Activated()
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(terminal_dock._DOCK)

    def test_terminal_dock_entry_point_forwards_to_the_chat(self):
        from acadagent import terminal_dock
        self.shell.install()
        terminal_dock.ask_about_view("what is it?")
        self.assertEqual(self.calls[0][0][0], "what is it?")
        self.assertIsNone(terminal_dock._DOCK)

    def test_a_failure_is_a_notice_in_the_chat(self):
        def boom(*a, **k):
            raise RuntimeError("no 3D view")
        self.vision.ask_in_chat = boom
        self.shell.install()
        self.shell._ask_view()
        notes = self.shell.chat_panel().notices
        self.assertEqual(notes[-1][0], "Could not ask about this view")
        self.assertIn("no 3D view", notes[-1][2])


class TestAskInChatWithTheRealVision(ShellCase):
    """The unstubbed vision.ask_in_chat, with capture faked: the question
    becomes a chat turn after the shot lands in the chat."""

    def test_capture_then_turn(self):
        from acadagent import capture
        self.shell.install()
        p = self.shell.chat_panel()
        order = []
        p.ask = lambda text: order.append(("ask", text)) or True
        orig = capture.capture_to_panel
        capture.capture_to_panel = (
            lambda panel, view_name="Isometric", **k:
            order.append(("shot", view_name)) or "/tmp/x.png")
        try:
            self.shell._ask_view()
        finally:
            capture.capture_to_panel = orig
        from acadagent import vision
        self.assertEqual(order, [("shot", "Isometric"),
                                 ("ask", vision.DEFAULT_QUESTION)])


class TestTerminalDockStrings(unittest.TestCase):
    def test_dev_strings_are_gone(self):
        with open(os.path.join(HERE, "..", "acadagent", "terminal_dock.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        for s in ("Ask Claude about this view", "$ claude",
                  "using Claude Code for this view", "view round trip needs",
                  "a request is already running", "bin/cad"):
            self.assertNotIn(s, src)

    def test_terminal_header_has_no_ask_button(self):
        mw = QtWidgets.QMainWindow()
        F.install_fakes(mw)
        from acadagent import terminal_dock
        try:
            dock = terminal_dock.ensure_terminal()
            body = dock.widget()
            self.assertFalse(hasattr(body, "btn_ask"))
            texts = [b.text() for b in body.findChildren(QtWidgets.QPushButton)]
            self.assertFalse([t for t in texts if "Ask" in t], texts)
        finally:
            terminal_dock.shutdown(3000)
            terminal_dock._DOCK = None
            mw.deleteLater()
            F.pump(20)


# ------------------------------------------------------------------ R96
FIXTURE = r'''#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PREFIX=${HERE}/usr
# export LD_LIBRARY_PATH=${HERE}/usr/lib${LD_LIBRARY_PATH:+':'}$LD_LIBRARY_PATH
export PYTHONHOME=${HERE}/usr
export PATH_TO_FREECAD_LIBDIR=${HERE}/usr/lib
export FONTCONFIG_FILE=/etc/fonts/fonts.conf
export FONTCONFIG_PATH=/etc/fonts
export QT_QPA_PLATFORM=xcb
export SSL_CERT_FILE=$PREFIX/ssl/cacert.pem
export GIT_SSL_CAINFO=$HERE/usr/ssl/cacert.pem
MAIN="$HERE/usr/bin/$1" ; shift
"${MAIN}" "$@"
'''


def _apprun_env():
    sys.path.insert(0, BRANDING)
    try:
        import apprun_env
    finally:
        sys.path.remove(BRANDING)
    return apprun_env


def _run_apprun(caller):
    """Run a snapshot-patched upstream-shaped AppRun under real bash with
    `caller` as its environment; return what FreeCAD would inherit."""
    ae = _apprun_env()
    tmp = tempfile.mkdtemp(prefix="r96_")
    try:
        os.makedirs(os.path.join(tmp, "usr", "bin"))
        app = os.path.join(tmp, "AppRun")
        with open(app, "w", encoding="utf-8") as fh:
            fh.write(ae.insert_snapshot(FIXTURE))
        os.chmod(app, 0o755)
        dump = os.path.join(tmp, "usr", "bin", "envdump")
        with open(dump, "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\nexec env -0 > "$1"\n')
        os.chmod(dump, 0o755)
        out = os.path.join(tmp, "env.bin")
        subprocess.run([app, "envdump", out], env=caller, check=True,
                       capture_output=True, timeout=30)
        with open(out, "rb") as fh:
            raw = fh.read().decode("utf-8", "surrogateescape")
        child = dict(kv.split("=", 1) for kv in raw.split("\0") if "=" in kv)
        for k in ("PWD", "SHLVL", "_", "OLDPWD"):   # bash's, not AppRun's
            child.pop(k, None)
        return child
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class TestCleanEnvRestore(unittest.TestCase):
    MOUNT = "/tmp/.mount_AtechR96"

    def caller(self):
        # APPDIR/APPIMAGE come from the AppImage runtime, BEFORE AppRun.
        return {"PATH": "/home/u/.local/bin:/usr/bin:/bin",
                "HOME": "/home/u", "LANG": "C.UTF-8",
                "APPDIR": self.MOUNT, "APPIMAGE": "/opt/Atech.AppImage",
                "QT_QPA_PLATFORM": "wayland",            # the user's own
                "SSL_CERT_FILE": "/etc/corp/ca.pem",     # the user's own
                "FONTCONFIG_FILE": "/home/u/fonts.conf"}  # the user's own

    def test_end_to_end_user_values_come_back(self):
        from acadagent.terminal import clean_env
        caller = self.caller()
        inherited = _run_apprun(caller)
        self.assertEqual(inherited["QT_QPA_PLATFORM"], "xcb")   # AppRun ran
        got = clean_env(inherited)
        want = {k: v for k, v in caller.items()
                if k not in ("APPDIR", "APPIMAGE")}
        want["TERM"] = "dumb"
        self.assertEqual(got, want)

    def test_without_the_restore_the_user_value_is_lost(self):
        # The same run through the pre-R96 logic loses QT_QPA_PLATFORM:
        # proves the end-to-end test above can fail.
        from acadagent import terminal
        inherited = _run_apprun(self.caller())
        orig = terminal.apprun_restore
        terminal.apprun_restore = lambda env: (
            {k: v for k, v in env.items()
             if not k.startswith(terminal.SNAP_PREFIX)
             and k != terminal.SNAP_LIST}, set())
        try:
            got = terminal.clean_env(inherited)
        finally:
            terminal.apprun_restore = orig
        self.assertNotIn("QT_QPA_PLATFORM", got)
        self.assertNotIn("SSL_CERT_FILE", got)

    def test_user_pythonpath_restored_image_one_dropped(self):
        from acadagent.terminal import clean_env
        m = self.MOUNT
        env = {"APPDIR": m, "ATECH_APPRUN_SET": "PYTHONHOME PYTHONPATH PREFIX",
               "ATECH_PRE_APPRUN_PYTHONPATH": "/home/u/py",
               "PYTHONHOME": m + "/usr", "PYTHONPATH": m + "/usr/lib",
               "PREFIX": m + "/usr", "PATH": m + "/usr/bin:/usr/bin"}
        self.assertEqual(clean_env(env), {"PYTHONPATH": "/home/u/py",
                                          "PATH": "/usr/bin", "TERM": "dumb"})

    def test_a_restored_value_inside_the_image_is_still_dropped(self):
        from acadagent.terminal import clean_env
        m = self.MOUNT
        env = {"APPDIR": m, "ATECH_APPRUN_SET": "SSL_CERT_FILE",
               "ATECH_PRE_APPRUN_SSL_CERT_FILE": m + "/usr/ssl/cacert.pem",
               "SSL_CERT_FILE": m + "/usr/ssl/cacert.pem"}
        self.assertEqual(clean_env(env), {"TERM": "dumb"})

    def test_no_snapshot_keeps_the_old_behaviour(self):
        from acadagent.terminal import clean_env
        self.assertEqual(
            clean_env({"QT_QPA_PLATFORM": "wayland", "PYTHONPATH": "/x"}),
            {"QT_QPA_PLATFORM": "wayland", "TERM": "dumb"})

    def test_mirror_agrees_with_the_branding_reference(self):
        from acadagent.terminal import apprun_restore
        ae = _apprun_env()
        rnd = random.Random(96)
        names = ["PREFIX", "PYTHONHOME", "QT_QPA_PLATFORM", "SSL_CERT_FILE",
                 "HOME", "PATH"]
        for _ in range(300):
            env = {}
            listed = [n for n in names if rnd.random() < 0.5]
            if rnd.random() < 0.9:
                env[ae.LIST_VAR] = " ".join(listed)
            for n in names:
                if rnd.random() < 0.6:
                    env[n] = "v-" + n
                if rnd.random() < 0.4:
                    env[ae.PREFIX + n] = "pre-" + n
            got, _restored = apprun_restore(env)
            self.assertEqual(got, ae.restore(env), env)


# ------------------------------------------------------------------ R99 / R59
class StatusCase(ShellCase):
    def setUp(self):
        super().setUp()
        self.shell._NOTIFY_IDLE.clear()
        self.sb = self.mw.statusBar()
        # FreeCAD's own tall status-bar child (the 37 px first-install bar)
        # (a plain QWidget: a QSS min-height on a QPushButton resets an
        # explicit setMinimumHeight to 0 when the style sheet is removed)
        tall = QtWidgets.QWidget()
        tall.setMinimumHeight(34)
        self.sb.addPermanentWidget(tall)
        F.pump(20)

    def add_button(self, name, color):
        b = QtWidgets.QPushButton()
        b.setObjectName(name)
        b.setIcon(_solid_icon(color))
        self.sb.addPermanentWidget(b)
        return b


class TestNotificationIcon(StatusCase):
    def test_matched_by_objectname_on_a_plain_qpushbutton(self):
        # 1.1.3's NotificationArea has no Q_OBJECT: className is QPushButton
        self.shell.install()
        btn = self.add_button("notificationArea", "#1e90ff")
        other = self.add_button("someOtherButton", "#1e90ff")
        orig = btn.icon().cacheKey()
        F.pump(30)                                     # ChildAdded upkeep
        self.shell._status_upkeep()
        self.assertEqual(btn.metaObject().className(), "QPushButton")
        self.assertNotEqual(btn.icon().cacheKey(), orig, "bell not applied")
        bell = self.shell.style.icon("bell", self.shell.style.tokens()["muted"], 16)
        self.assertEqual(_img(btn.icon()), _img(bell))
        self.assertEqual(_img(other.icon()), _img(_solid_icon("#1e90ff")))
        self.shell.uninstall()
        self.assertEqual(btn.icon().cacheKey(), orig, "idle icon not restored")

    def test_a_state_icon_is_left_showing_and_idle_brings_the_bell_back(self):
        btn = self.add_button("notificationArea", "#1e90ff")
        idle = btn.icon()
        self.shell.install()
        self.shell._status_upkeep()
        btn.setIcon(_solid_icon("#ff0000"))            # missed notifications
        self.shell._status_upkeep()
        self.assertEqual(_img(btn.icon()), _img(_solid_icon("#ff0000")))
        btn.setIcon(idle)                              # FreeCAD: back to idle
        self.shell._status_upkeep()
        self.assertNotEqual(_img(btn.icon()), _img(idle))

    def test_alert_at_first_sighting_is_not_taken_for_idle(self):
        # startup warnings: the button shows FreeCAD's missed icon when the
        # shell first sees it. It stays; the bell comes once it goes idle.
        gui = sys.modules["FreeCADGui"]
        icons = {"InTray_missed_notifications": _solid_icon("#ff0000"),
                 "InTray": _solid_icon("#1e90ff")}
        gui.getIcon = icons.get
        try:
            btn = self.add_button("notificationArea", "#ff0000")
            self.shell.install()
            self.shell._status_upkeep()
            self.assertEqual(_img(btn.icon()), _img(_solid_icon("#ff0000")))
            idle = _solid_icon("#1e90ff")
            btn.setIcon(idle)                          # user read them
            self.shell._status_upkeep()
            bell = self.shell.style.icon(
                "bell", self.shell.style.tokens()["muted"], 16)
            self.assertEqual(_img(btn.icon()), _img(bell))
            btn.setIcon(_solid_icon("#ff0000"))        # a new alert
            self.shell._status_upkeep()
            self.assertEqual(_img(btn.icon()), _img(_solid_icon("#ff0000")))
            self.shell.uninstall()
        finally:
            del gui.getIcon

    def test_part_round_trip_does_not_cover_a_missed_alert(self):
        btn = self.add_button("notificationArea", "#1e90ff")
        self.shell.install()
        self.shell._status_upkeep()
        self.shell.uninstall()
        btn.setIcon(_solid_icon("#ff0000"))            # alert while in Part
        self.shell.install()
        self.shell._status_upkeep()
        self.assertEqual(_img(btn.icon()), _img(_solid_icon("#ff0000")))


class TestStatusBarHeight(StatusCase):
    def heights(self):
        F.pump(30)
        return (self.sb.height(), self.sb.minimumHeight(),
                self.sb.maximumHeight())

    def test_pinned_across_a_part_round_trip_and_restored(self):
        H = self.shell.STATUS_H
        before = (self.sb.minimumHeight(), self.sb.maximumHeight())
        natural = self.heights()[0]
        self.assertGreater(natural, H, "the fake bar must start taller")
        self.shell.install()
        first = self.heights()
        self.assertEqual(first, (H, H, H))
        self.shell.uninstall()
        self.assertEqual((self.sb.minimumHeight(), self.sb.maximumHeight()),
                         before, "limits not restored on uninstall")
        self.assertEqual(self.heights()[0], natural)
        self.shell.install()
        self.assertEqual(self.heights(), first, "height changed on round trip")

    def test_a_late_repolish_is_pinned_again(self):
        H = self.shell.STATUS_H
        self.shell.install()
        self.heights()
        # FreeCAD's late theme load drops the limits (GUI r2)
        self.sb.setMinimumHeight(0)
        self.sb.setMaximumHeight(16777215)
        self.sb.addPermanentWidget(QtWidgets.QLabel("late"))   # ChildAdded
        self.assertEqual(self.heights(), (H, H, H))


class TestNavIcon(StatusCase):
    def test_replaced_follows_freecad_and_restored(self):
        nav = self.add_button("NavigationIndicator", "#000000")
        self.shell.install()
        self.shell._status_upkeep()
        mouse = self.shell.style.icon("mouse",
                                      self.shell.style.tokens()["muted"], 16)
        self.assertEqual(_img(nav.icon()), _img(mouse))
        # a navigation-style change: Tux's setCurrent() sets its own icon
        newer = _solid_icon("#202020")
        nav.setIcon(newer)
        self.shell._status_upkeep()
        self.assertEqual(_img(nav.icon()), _img(mouse))
        self.shell.uninstall()
        self.assertEqual(nav.icon().cacheKey(), newer.cacheKey(),
                         "the latest FreeCAD icon must come back")

    def test_no_indicator_is_harmless(self):
        self.shell.install()
        self.shell._status_upkeep()
        self.shell.uninstall()


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
class TestFitCameraWithCoin(unittest.TestCase):
    """fit_camera's answer projected by Coin's own camera: every point of the
    sphere must land inside the view and above the reserved band, and the
    fit must be tight (not framed by zooming out)."""

    def project(self, center, radius, look, up, w, h, reserve, ortho):
        from acadagent import viewport as vp
        coin = _coin()
        cam = coin.SoOrthographicCamera() if ortho \
            else coin.SoPerspectiveCamera()
        q = vp.look_quaternion(look, up)
        cam.orientation.setValue(coin.SbRotation(*q))
        pos, size = vp.fit_camera(center, radius, look, up, w, h, reserve,
                                  ortho=ortho)
        cam.position.setValue(coin.SbVec3f(*pos))
        if ortho:
            cam.height.setValue(size)
        cam.focalDistance.setValue(radius * 2.0 + 1.0 if ortho else size)
        cam.nearDistance.setValue(0.001)
        cam.farDistance.setValue(1e6)
        vv = cam.getViewVolume(w / h)
        if w < h:                                      # ADJUST_CAMERA
            vv.scale(h / w)
        rnd = random.Random(82)
        pts = []
        for _ in range(600):
            d = [rnd.gauss(0, 1) for _ in range(3)]
            n = math.sqrt(sum(c * c for c in d))
            p = [center[i] + radius * d[i] / n for i in range(3)]
            pts.append(vv.projectToScreen(coin.SbVec3f(*p)).getValue())
        return pts

    def check(self, w, h, reserve, look, ortho):
        center, radius = (10.0, -5.0, 30.0), 50.0
        up = (0.0, 0.0, 1.0)
        pts = self.project(center, radius, look, up, w, h, reserve, ortho)
        slack = 0.01
        lo = min(p[1] for p in pts)
        hi = max(p[1] for p in pts)
        xl = min(p[0] for p in pts)
        xh = max(p[0] for p in pts)
        tag = "%dx%d reserve=%.2f ortho=%s" % (w, h, reserve, ortho)
        self.assertGreaterEqual(lo, reserve - slack, tag + " under the bar")
        self.assertLessEqual(hi, 1 + slack, tag + " off the top")
        self.assertGreaterEqual(xl, -slack, tag)
        self.assertLessEqual(xh, 1 + slack, tag)
        # tight: the model fills the band vertically or the view across
        fill = max((hi - lo) / (1.0 - reserve), xh - xl)
        self.assertGreater(fill, 0.85 if ortho else 0.75, tag + " too loose")

    def test_band_left_free(self):
        iso = (-0.577, 0.577, -0.577)
        for ortho in (True, False):
            for w, h in ((1200, 800), (800, 800), (700, 1000)):
                for reserve in (0.0, 0.12, 0.25):
                    self.check(w, h, reserve, iso, ortho)

    def test_pill_height_free_in_pixels(self):
        # 900 px view, a 44 px pill 18 px off the bottom + 8 px breath
        w, h, px = 1400, 900, 44 + 18 + 8
        reserve = px / float(h)
        pts = self.project((0, 0, 0), 80.0, (0.0, -1.0, 0.0), (0, 0, 1),
                           w, h, reserve, True)
        self.assertGreaterEqual(min(p[1] for p in pts) * h, px - 1)

    def test_without_reserve_the_old_fit_covers_the_band(self):
        # The same sphere fitted with reserve 0 (FreeCAD's ViewFit shape)
        # dips into a 0.2 band: proves the test above can fail.
        pts = self.project((0, 0, 0), 80.0, (0.0, -1.0, 0.0), (0, 0, 1),
                           1400, 900, 0.0, True)
        self.assertLess(min(p[1] for p in pts), 0.2)


class TestViewReserveFromTheShell(ShellCase):
    def test_reserve_covers_the_pill(self):
        self.shell.install()
        F.pump(50)
        ov = self.shell._S["overlay"]
        bar = ov.bar
        self.assertTrue(bar.isVisible())
        vp_h = ov.mdi.viewport().geometry().height()
        r = self.shell.view_reserve()
        self.assertGreater(r, 0.0)
        vp = ov.mdi.viewport().geometry()
        free_px = vp.y() + vp.height() - bar.geometry().top()
        self.assertGreaterEqual(r * vp_h, free_px)


class _BB:
    def __init__(self, lo, hi):
        (self.XMin, self.YMin, self.ZMin), (self.XMax, self.YMax, self.ZMax) \
            = lo, hi


class _Shape:
    def __init__(self, lo, hi):
        self.BoundBox = _BB(lo, hi)

    def isNull(self):                                  # noqa: N802
        return False


def _obj(role, lo, hi):
    return types.SimpleNamespace(AtechRole=role, Shape=_Shape(lo, hi))


class TestModuleFace(unittest.TestCase):
    def setUp(self):
        mw = QtWidgets.QMainWindow()
        F.install_fakes(mw)
        from acadagent import viewport
        self.vp = viewport

    def doc(self, side):
        board = _obj("board", (0, 0, 0), (100, 3, 60))       # stands in X/Z
        y0 = 3 if side > 0 else -20
        mod = _obj("module", (10, y0, 10), (40, y0 + 17, 40))
        return types.SimpleNamespace(Objects=[board, mod])

    def test_camera_on_the_module_side(self):
        self.assertEqual(self.vp.module_face_direction(self.doc(+1)),
                         (0.6, 1.0, 0.5))
        self.assertEqual(self.vp.module_face_direction(self.doc(-1)),
                         (0.6, -1.0, 0.5))

    def test_no_board_no_opinion(self):
        doc = types.SimpleNamespace(Objects=[_obj(None, (0, 0, 0), (1, 1, 1))])
        self.assertIsNone(self.vp.module_face_direction(doc))

    def test_first_build_looks_at_the_modules_then_fits(self):
        vp, calls = self.vp, []
        saved = (vp._view, vp.look_from, vp.fit_all, vp.iso_and_fit)
        vp._view = lambda: object()
        vp.look_from = lambda x, y, z, v=None: calls.append(("look", (x, y, z))) or True
        vp.fit_all = lambda *a: calls.append(("fit",)) or True
        vp.iso_and_fit = lambda: calls.append(("iso",)) or True
        try:
            self.assertTrue(vp.frame_if_needed([], first=True,
                                               doc=self.doc(+1)))
            self.assertEqual(calls, [("look", (0.6, 1.0, 0.5)), ("fit",)])
            calls.clear()
            vp.frame_if_needed([], first=True,
                               doc=types.SimpleNamespace(Objects=[]))
            self.assertEqual(calls, [("iso",)])
        finally:
            vp._view, vp.look_from, vp.fit_all, vp.iso_and_fit = saved

    @unittest.skipUnless(HAVE_PIVY, NO_PIVY)
    def test_look_from_puts_the_camera_on_that_side(self):
        # look_quaternion((-x,-y,-z)) must look TOWARD the model, i.e. the
        # camera sits on the (x, y, z) side: checked with Coin's rotation.
        coin = _coin()
        d = (0.6, 1.0, 0.5)
        q = self.vp.look_quaternion(tuple(-c for c in d))
        look = coin.SbRotation(*q).multVec(coin.SbVec3f(0, 0, -1)).getValue()
        n = math.sqrt(sum(c * c for c in d))
        for a, b in zip(look, d):
            self.assertAlmostEqual(a, -b / n, places=4)


if __name__ == "__main__":
    unittest.main()
