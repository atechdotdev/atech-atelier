"""In-app side of the GUI harness: runs INSIDE the real Atech app (Cocoa).

app_driver.py launches the app with a scenario file (scn_*.py) on the
command line; FreeCAD executes it as a macro once the GUI is up. A scenario
looks like:

    import os, sys
    sys.path.insert(0, os.environ["ATECH_GUI_HARNESS"])
    from scenario_base import Scenario

    def main(s):
        s.wait_shell()
        s.step("new document", lambda: s.new_doc())
        s.grab(s.mw, "main")

    Scenario("smoke").run(main)

Everything is driven from the GUI thread (Scenario.run defers main() with a
QTimer so the event loop is running). Modal dialogs are handled by a polling
QTimer that keeps firing inside the dialog's own nested event loop
(expect_modal / ModalWatcher). Pixels come ONLY from QWidget.grab() of the
app's own widgets: the user's desktop is never captured.

Output (directory $ATECH_GUI_OUT): result.json, *.png. A marker line
"ATECH_GUI_RESULT <path>" is written to the process's real stdout (fd 1);
FreeCAD redirects sys.stdout to the Report view, so os.write is used.
"""
import json
import os
import sys
import threading
import time
import traceback

from PySide6 import QtCore, QtGui, QtWidgets

import FreeCAD as App
import FreeCADGui as Gui

OUT = os.environ.get("ATECH_GUI_OUT") or os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "atech-gui-out")
T_PROCESS0 = float(os.environ.get("ATECH_GUI_T0", "0") or 0)  # driver's launch time (epoch)


def _raw_print(line):
    try:
        os.write(1, (line.rstrip("\n") + "\n").encode("utf-8", "replace"))
    except OSError:
        pass


def _rect(r):
    return [r.x(), r.y(), r.width(), r.height()]


def _size(s):
    return [s.width(), s.height()]


def font_info(f):
    return {"family": f.family(), "families": list(f.families()) if hasattr(f, "families") else [],
            "pointSizeF": f.pointSizeF(), "pixelSize": f.pixelSize(),
            "weight": int(f.weight()) if not hasattr(f.weight(), "value") else f.weight().value,
            "resolved_family": QtGui.QFontInfo(f).family(),
            "resolved_pixel": QtGui.QFontInfo(f).pixelSize()}


def widget_info(w):
    d = {"class": type(w).__name__, "meta": w.metaObject().className(),
         "objectName": w.objectName(), "visible": w.isVisible(),
         "geometry": _rect(w.geometry()), "size": _size(w.size()),
         "sizeHint": _size(w.sizeHint()), "minimumSizeHint": _size(w.minimumSizeHint()),
         "minimumSize": _size(w.minimumSize()), "maximumSize": _size(w.maximumSize()),
         "font": font_info(w.font()), "styleSheet": w.styleSheet(),
         "style": w.style().metaObject().className()}
    for attr in ("text", "windowTitle"):
        fn = getattr(w, attr, None)
        if callable(fn):
            try:
                d[attr] = fn()
            except Exception:                              # noqa: BLE001
                pass
    if isinstance(w, QtWidgets.QPushButton):
        d["default"] = w.isDefault()
        d["autoDefault"] = w.autoDefault()
        d["flat"] = w.isFlat()
    return d


def stylesheet_chain(w):
    """The stylesheets that reach `w`: its own, every ancestor's, the app's."""
    chain = []
    p = w
    while p is not None:
        chain.append({"class": type(p).__name__, "meta": p.metaObject().className(),
                      "objectName": p.objectName(), "len": len(p.styleSheet()),
                      "styleSheet": p.styleSheet()})
        p = p.parentWidget()
    app = QtWidgets.QApplication.instance()
    chain.append({"class": "QApplication", "len": len(app.styleSheet()),
                  "styleSheet_head": app.styleSheet()[:400]})
    return chain


class Scenario:
    def __init__(self, name, timeout_s=None):
        self.name = name
        self.out = OUT
        os.makedirs(self.out, exist_ok=True)
        self.timeout_s = timeout_s or float(os.environ.get("ATECH_GUI_TIMEOUT", "120"))
        self.t0 = time.time()
        self.result = {"scenario": name, "ok": None, "steps": [], "grabs": [],
                       "dialogs": [], "exceptions": [], "data": {},
                       "t_macro_start_s": round(self.t0 - T_PROCESS0, 3) if T_PROCESS0 else None,
                       "env": {"platform": sys.platform, "qt": QtCore.qVersion(),
                               "freecad": ".".join(App.Version()[:3])}}
        self.app = QtWidgets.QApplication.instance()
        self.mw = Gui.getMainWindow()
        self._hook_exceptions()
        self._finished = False

    # ----------------------------------------------------------- plumbing
    def _hook_exceptions(self):
        prev = sys.excepthook

        def hook(etype, value, tb):
            self.result["exceptions"].append(
                {"t": round(time.time() - self.t0, 3), "type": etype.__name__,
                 "msg": str(value), "tb": "".join(traceback.format_exception(etype, value, tb))[-4000:]})
            try:
                prev(etype, value, tb)
            except Exception:                              # noqa: BLE001
                pass
        sys.excepthook = hook

    def log(self, msg):
        App.Console.PrintMessage("[gui-harness] %s\n" % msg)
        _raw_print("ATECH_GUI_LOG %s" % msg)

    def pump(self, ms=0):
        """Process events for `ms` milliseconds (at least once)."""
        end = time.time() + ms / 1000.0
        while True:
            self.app.processEvents(QtCore.QEventLoop.AllEvents, 20)
            if time.time() >= end:
                break
            time.sleep(0.005)

    def wait_until(self, pred, timeout_s=10.0, what="condition"):
        t = time.time()
        while time.time() - t < timeout_s:
            try:
                v = pred()
            except Exception:                              # noqa: BLE001
                v = None
            if v:
                return v
            self.pump(20)
        raise TimeoutError("timed out after %.1fs waiting for %s" % (timeout_s, what))

    def step(self, name, fn=None, *a, **kw):
        """Run fn, record wall time and outcome. Returns fn's value (None on error)."""
        rec = {"name": name, "t_start_s": round(time.time() - self.t0, 3)}
        t = time.perf_counter()
        val = None
        try:
            val = fn(*a, **kw) if fn else None
            rec["ok"] = True
        except Exception as exc:                           # noqa: BLE001
            rec["ok"] = False
            rec["error"] = "%s: %s" % (type(exc).__name__, exc)
            rec["tb"] = traceback.format_exc()[-3000:]
        rec["ms"] = round((time.perf_counter() - t) * 1000, 1)
        if val is not None and isinstance(val, (str, int, float, bool, list, dict)):
            rec["value"] = val
        self.result["steps"].append(rec)
        self.log("step %-40s %s %7.1f ms%s" % (name, "ok " if rec["ok"] else "ERR", rec["ms"],
                                               "" if rec["ok"] else "  " + rec["error"]))
        return val

    # -------------------------------------------------------------- shell
    def shell(self):
        from acadagent import shell
        return shell

    def wait_shell(self, timeout_s=60.0):
        """Until the Atech shell is installed (_S filled) and its sidebar dock shows."""
        def ready():
            sh = self.shell()
            if not sh._S:
                return False
            dock = sh._S.get("dock")
            return dock is not None and dock.isVisible()
        t = time.time()
        self.wait_until(ready, timeout_s, "Atech shell")
        self.pump(200)          # let the first layout settle
        self.result["data"]["shell_wait_s"] = round(time.time() - t, 3)
        if T_PROCESS0:
            self.result["data"]["launch_to_shell_s"] = round(time.time() - T_PROCESS0, 3)
        return True

    # ------------------------------------------------------------ widgets
    def find(self, object_name=None, text=None, cls=QtWidgets.QWidget, root=None, visible=None):
        """All widgets under root (default: every top level) matching the filters."""
        roots = [root] if root is not None else self.app.topLevelWidgets()
        hits = []
        for r in roots:
            cands = [r] + r.findChildren(cls)
            for w in cands:
                if not isinstance(w, cls):
                    continue
                if object_name is not None and w.objectName() != object_name:
                    continue
                if text is not None:
                    tf = getattr(w, "text", None)
                    try:
                        t = tf() if callable(tf) else None
                    except Exception:                      # noqa: BLE001
                        t = None
                    if t is None or text not in t:
                        continue
                if visible is not None and w.isVisible() != visible:
                    continue
                if w not in hits:
                    hits.append(w)
        return hits

    def find_one(self, **kw):
        hits = self.find(**kw)
        if not hits:
            raise LookupError("no widget matches %r" % (kw,))
        vis = [w for w in hits if w.isVisible()]
        return (vis or hits)[0]

    def click(self, w):
        from PySide6.QtTest import QTest
        QTest.mouseClick(w, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, w.rect().center())
        self.pump(30)

    def type_text(self, w, text):
        from PySide6.QtTest import QTest
        w.setFocus()
        QTest.keyClicks(w, text)
        self.pump(30)

    def grab(self, w, name):
        """PNG of one widget, from the app's own rendering (never the desktop)."""
        path = os.path.join(self.out, "%s.png" % name)
        try:
            pm = w.grab()
            ok = pm.save(path, "PNG")
        except Exception as exc:                           # noqa: BLE001
            ok, path = False, "%s (%s)" % (path, exc)
        rec = {"name": name, "path": path, "ok": bool(ok),
               "size": _size(w.size()), "dpr": w.devicePixelRatioF()}
        self.result["grabs"].append(rec)
        return path

    def grab_3d(self, name, width=1200, height=800):
        """PNG of the active 3D view rendered offscreen by Coin (saveImage).
        QWidget.grab() of the main window shows the OpenGL viewport blank
        (MEASURED: empty grey area with a document open), so model pixels
        come from here. For module colours, set
        BaseApp/Preferences/Mod/AcadAgent StudioLook=False first (the studio
        look draws GLB scenes instead of the STL meshes)."""
        path = os.path.join(self.out, "%s.png" % name)
        ok = False
        try:
            v = Gui.ActiveDocument.ActiveView if Gui.ActiveDocument else None
            if v is not None and hasattr(v, "saveImage"):
                v.saveImage(path, width, height, "Current")
                ok = os.path.isfile(path)
        except Exception as exc:                           # noqa: BLE001
            path = "%s (%s)" % (path, exc)
        self.result["grabs"].append({"name": name, "path": path, "ok": ok, "kind": "3d"})
        return path

    # -------------------------------------------------------- documents
    def new_doc(self, name="Unnamed"):
        doc = App.newDocument(name)
        self.pump(100)
        return doc

    def modify_doc(self, doc):
        """A real, undoable modification (the document becomes 'modified')."""
        box = doc.addObject("Part::Box", "Box")
        doc.recompute()
        self.pump(50)
        return box.Name

    # ---------------------------------------------------------- report view
    def report_text(self):
        for d in self.mw.findChildren(QtWidgets.QDockWidget):
            if d.objectName() in ("Report view", "ReportView"):
                te = d.findChild(QtWidgets.QTextEdit) or d.findChild(QtWidgets.QPlainTextEdit)
                if te is not None:
                    return te.toPlainText()
        return None

    # --------------------------------------------------------------- modals
    def expect_modal(self, handler=None, timeout_s=10.0, name="modal", settle_ms=250):
        """Arm a watcher BEFORE triggering a modal dialog.

        When QApplication.activeModalWidget() appears, after `settle_ms` the
        watcher records it (dialog_info), grabs it, then calls
        handler(scenario, dlg, info); with no handler the dialog is rejected.
        Returns the ModalWatcher; its .info is filled when handled."""
        return ModalWatcher(self, handler, timeout_s, name, settle_ms)

    def dialog_info(self, dlg):
        info = widget_info(dlg)
        if isinstance(dlg, QtWidgets.QMessageBox):
            info["mb_text"] = dlg.text()
            info["mb_informative"] = dlg.informativeText()
            cb = dlg.checkBox()
            info["checkbox"] = cb.text() if cb is not None else None
        info["buttons"] = []
        for b in dlg.findChildren(QtWidgets.QAbstractButton):
            bi = widget_info(b)
            bi["chain"] = [c["meta"] + ("#" + c["objectName"] if c["objectName"] else "")
                           for c in stylesheet_chain(b)[:-1]]
            bi["rendered_fm_width"] = QtGui.QFontMetrics(b.font()).horizontalAdvance(b.text() if hasattr(b, "text") else "")
            info["buttons"].append(bi)
        info["stylesheet_chain"] = stylesheet_chain(dlg)
        info["parent"] = (dlg.parentWidget().metaObject().className()
                          if dlg.parentWidget() is not None else None)
        return info

    # --------------------------------------------------------------- finish
    def write(self):
        self.result["t_total_s"] = round(time.time() - self.t0, 3)
        try:
            rt = self.report_text()
            self.result["report_view_tail"] = rt[-6000:] if rt else rt
        except Exception as exc:                           # noqa: BLE001
            self.result["report_view_tail"] = "unavailable: %r" % (exc,)
        if self.result["ok"] is None:
            self.result["ok"] = all(s.get("ok") for s in self.result["steps"]) \
                and not self.result["exceptions"]
        path = os.path.join(self.out, "result.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.result, f, indent=2, default=str)
        _raw_print("ATECH_GUI_RESULT %s" % path)
        return path

    def quit(self):
        """Close every document WITHOUT saving, then close the window."""
        for name in list(App.listDocuments()):
            try:
                App.closeDocument(name)
            except Exception:                              # noqa: BLE001
                pass
        self.pump(100)
        # hard backstop: never leave the app hanging after the result exists
        # (daemon: a non-daemon timer would itself hold the interpreter's
        # shutdown for its full 20 s, MEASURED)
        t = threading.Timer(20.0, lambda: os._exit(3))
        t.daemon = True
        t.start()
        QtCore.QTimer.singleShot(0, self.mw.close)
        QtCore.QTimer.singleShot(3000, self.app.quit)

    def run(self, main):
        """Defer main(self) into the running event loop; always write + quit."""
        # watchdog in case main() blocks forever (a modal no watcher caught)
        def watchdog():
            if not self._finished:
                self.result["ok"] = False
                self.result["exceptions"].append({"type": "Timeout", "msg": "scenario watchdog %.0fs" % self.timeout_s})
                try:
                    m = self.app.activeModalWidget()
                    if m is not None:
                        self.result["data"]["stuck_modal"] = widget_info(m)
                        self.grab(m, "stuck_modal")
                        m.close()
                except Exception:                          # noqa: BLE001
                    pass
                self.write()
                os._exit(4)
        wd = QtCore.QTimer(self.app)
        wd.setSingleShot(True)
        wd.timeout.connect(watchdog)
        wd.start(int(self.timeout_s * 1000))
        self._wd = wd

        def go():
            try:
                main(self)
            except Exception as exc:                       # noqa: BLE001
                self.result["ok"] = False
                self.result["exceptions"].append({"type": type(exc).__name__, "msg": str(exc),
                                                  "tb": traceback.format_exc()[-4000:]})
            self._finished = True
            self.write()
            if os.environ.get("ATECH_GUI_KEEP_OPEN") != "1":
                self.quit()
        QtCore.QTimer.singleShot(0, go)


class ModalWatcher:
    def __init__(self, scn, handler, timeout_s, name, settle_ms):
        self.scn, self.handler, self.name, self.settle_ms = scn, handler, name, settle_ms
        self.info = None
        self.error = None
        self.seen_at = None
        self.t_armed = time.time()
        self.deadline = self.t_armed + timeout_s
        self.timer = QtCore.QTimer(scn.app)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    @property
    def done(self):
        return self.info is not None or self.error is not None

    def _poll(self):
        if time.time() > self.deadline:
            self.timer.stop()
            self.error = "no modal dialog within the timeout"
            return
        dlg = self.scn.app.activeModalWidget()
        if dlg is None or not dlg.isVisible():
            return
        if self.seen_at is None:
            self.seen_at = time.time()
            return
        if (time.time() - self.seen_at) * 1000 < self.settle_ms:
            return
        self.timer.stop()
        try:
            info = self.scn.dialog_info(dlg)
            info["t_to_show_ms"] = round((self.seen_at - self.t_armed) * 1000, 1)
            info["grab"] = self.scn.grab(dlg, self.name)
            self.info = info
            self.scn.result["dialogs"].append(dict(info, name=self.name))
            if self.handler is not None:
                self.handler(self.scn, dlg, info)
            else:
                dlg.reject() if hasattr(dlg, "reject") else dlg.close()
        except Exception as exc:                           # noqa: BLE001
            self.error = "%s: %s" % (type(exc).__name__, exc)
            self.scn.result["exceptions"].append({"type": "ModalHandler", "msg": self.error,
                                                  "tb": traceback.format_exc()[-3000:]})
            try:
                dlg.reject()
            except Exception:                              # noqa: BLE001
                pass


def press_button(text_or_role):
    """A modal handler that clicks the dialog button whose text contains the
    string (or whose QDialogButtonBox role matches)."""
    def h(scn, dlg, info):
        for b in dlg.findChildren(QtWidgets.QAbstractButton):
            if isinstance(text_or_role, str) and text_or_role.lower() in b.text().lower():
                b.click()
                return
        if isinstance(dlg, QtWidgets.QMessageBox) and not isinstance(text_or_role, str):
            btn = dlg.button(text_or_role)
            if btn is not None:
                btn.click()
                return
        dlg.reject()
    return h
