"""The sidebar's project picker (navbar.ProjectPicker): Recent, Open file...,
and no starter-projects submenu (R456).

User bug: clicking a RECENT entry does nothing ("these projects don't open").
This scenario seeds FreeCAD's RecentFiles (the isolated profile's) with real
.FCStd files given in $ATECH_GUI_RECENT (os.pathsep-separated; include a
/tmp/... and a /private/tmp/... spelling of one file), opens the picker's
menu the way a click does (QMenu.popup + aboutToShow), triggers each Recent
action, and records whether a document opened, became active, has a
visible 3D view, and what the picker's title says. sys.excepthook and the
Report view are captured: ProjectPicker._run has try/finally without
except, so an exception there only reaches the Report view.

Then "Open file..." (with Qt's own file dialog, DontUseNativeDialog, so the
dialog is a QWidget the harness can see and drive), and that the old
"Atech starter projects" submenu is gone (R456: default projects are files).
"""
import os
import sys
import time

sys.path.insert(0, os.environ["ATECH_GUI_HARNESS"])
from scenario_base import Scenario, widget_info  # noqa: E402

import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6 import QtCore, QtWidgets  # noqa: E402

RECENT = [p for p in os.environ.get("ATECH_GUI_RECENT", "").split(os.pathsep) if p]


def view_state(s, picker):
    """What the user would see after an action."""
    mdi = s.mw.findChild(QtWidgets.QMdiArea)
    sub = mdi.activeSubWindow() if mdi is not None else None
    w = sub.widget() if sub is not None else None
    home = [h.objectName() for h in s.find(object_name="HomeView") + s.find(object_name="EmptyView")
            if h.isVisible()]
    ad = App.ActiveDocument
    return {
        "docs": sorted(App.listDocuments()),
        "active_doc": ad.Name if ad else None,
        "active_doc_file": getattr(ad, "FileName", None) if ad else None,
        "active_doc_objects": len(ad.Objects) if ad else 0,
        "active_subwindow": sub.windowTitle() if sub is not None else None,
        "active_view_class": w.metaObject().className() if w is not None else None,
        "active_view_visible": bool(w is not None and w.isVisible()),
        "active_view_size": [w.width(), w.height()] if w is not None else None,
        "home_or_empty_visible": home,
        "picker_text": picker.text(),
        "mdi_subwindows": [x.windowTitle() for x in mdi.subWindowList()] if mdi else [],
    }


def main(s):
    s.step("wait for Atech shell", s.wait_shell)
    d = s.result["data"]
    from acadagent import navbar, projects_store
    picker = s.step("find ProjectPicker", lambda: s.find_one(object_name="ProjectPicker"))
    if picker is None:
        return

    # ------------------------------------------------------------ seed
    def seed():
        grp = App.ParamGet(projects_store.RECENT_PARAM)
        for i, p in enumerate(RECENT):
            grp.SetString("MRU%d" % i, p)
        grp.SetInt("RecentFiles", max(10, len(RECENT)))
        return {"seeded": RECENT, "recent_files()": navbar.recent_files(),
                "exists": {p: os.path.isfile(p) for p in RECENT}}
    d["seed"] = s.step("seed RecentFiles", seed)
    s.grab(s.mw, "before")

    def open_menu():
        m = picker.menu()
        m.popup(picker.mapToGlobal(QtCore.QPoint(0, picker.height())))
        s.pump(250)
        return m

    def entries(m):
        out = []
        for a in m.actions():
            out.append({"text": a.text(), "enabled": a.isEnabled(), "tip": a.toolTip(),
                        "sep": a.isSeparator(), "submenu": bool(a.menu())})
        return out

    m = s.step("open picker menu", open_menu)
    if m is not None:
        s.grab(m, "picker_menu")
        d["menu_first"] = entries(m)
        m.hide()
        s.pump(50)

    # ---------------------------------------------------- recent entries
    results = []
    report0 = s.report_text() or ""
    n_exc0 = len(s.result["exceptions"])
    recent_list = navbar.recent_files()
    for i, path in enumerate(recent_list):
        def one(i=i, path=path):
            m = open_menu()
            acts = [a for a in m.actions() if a.toolTip() == path]
            if not acts:
                m.hide()
                raise LookupError("no Recent action for %s (already open, so listed as open?)" % path)
            before = view_state(s, picker)
            t = time.perf_counter()
            acts[0].trigger()
            m.hide()
            s.pump(1500)
            after = view_state(s, picker)
            rep = s.report_text() or ""
            rec = {"path": path, "action_text": acts[0].text(),
                   "ms": round((time.perf_counter() - t) * 1000), "before": before, "after": after,
                   "opened": len(after["docs"]) > len(before["docs"]),
                   "became_active": after["active_doc"] != before["active_doc"],
                   "new_exceptions": s.result["exceptions"][n_exc0:],
                   "report_added": rep[len(report0):][-3000:] if rep.startswith(report0[:200]) else rep[-3000:]}
            results.append(rec)
            s.grab(s.mw, "after_recent_%d" % i)
            if not rec["opened"]:
                raise RuntimeError("Recent entry opened nothing: %s" % path)
            return {"opened": rec["opened"], "active": after["active_doc"], "picker": after["picker_text"],
                    "view_visible": after["active_view_visible"]}
        s.step("recent %d: %s" % (i, os.path.basename(path)), one)
    d["recent_results"] = results

    # direct control: the same call the action makes, outside the menu
    def direct():
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        s.pump(200)
        if not recent_list:
            raise LookupError("no recent files")
        before = view_state(s, picker)
        try:
            navbar._open_path(recent_list[0])
            err = None
        except Exception as exc:                           # noqa: BLE001
            err = "%s: %s" % (type(exc).__name__, exc)
        s.pump(1000)
        after = view_state(s, picker)
        d["direct_open_path"] = {"path": recent_list[0], "error": err, "before": before, "after": after}
        s.grab(s.mw, "after_direct_open_path")
        if err:
            raise RuntimeError(err)
        if not after["docs"]:
            raise RuntimeError("navbar._open_path opened nothing (Report view: %r)"
                               % (s.report_text() or "")[-200:])
        return after["docs"]
    s.step("control: navbar._open_path(recent[0]) called directly", direct)

    # proposed fix, tried IN THE RUNNING APP ONLY (no product file changes):
    # navbar._open_path swapped for FreeCAD.openDocument, then a Recent entry
    # is triggered through the real menu again.
    def fixed_recent():
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        s.pump(200)
        orig = navbar._open_path

        def _open_path_fixed(path):
            App.openDocument(path)
        navbar._open_path = _open_path_fixed
        try:
            res = []
            for i, path in enumerate(navbar.recent_files()):
                m = open_menu()
                acts = [a for a in m.actions() if a.toolTip() == path]
                if not acts:
                    m.hide()
                    continue
                before = view_state(s, picker)
                acts[0].trigger()
                m.hide()
                s.pump(1500)
                after = view_state(s, picker)
                res.append({"path": path, "before_docs": before["docs"], "after": after,
                            "opened": len(after["docs"]) > len(before["docs"])})
                s.grab(s.mw, "after_recent_FIXED_%d" % i)
                s.grab_3d("after_recent_FIXED_%d_3dview" % i)
            d["fixed_recent_results"] = res
            if not res or not all(r["opened"] for r in res):
                raise RuntimeError("fixed _open_path still opened nothing")
            return [r["after"]["active_doc"] for r in res]
        finally:
            navbar._open_path = orig
    s.step("PROPOSED FIX: Recent via FreeCAD.openDocument", fixed_recent)

    # ---------------------------------------------------- Open file...
    def open_file():
        App.ParamGet("User parameter:BaseApp/Preferences/Dialog").SetBool("DontUseNativeDialog", True)
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        s.pump(200)
        target = RECENT[-1] if RECENT else None
        seen = {}

        def handler(scn, dlg, info):
            seen["dialog"] = {"class": info["meta"], "title": info.get("windowTitle")}
            if isinstance(dlg, QtWidgets.QFileDialog) and target:
                dlg.selectFile(target)
                s.pump(100)
                dlg.accept()
            else:
                dlg.reject()
        w = s.expect_modal(handler, timeout_s=8, name="open_file_dialog", settle_ms=400)
        m = open_menu()
        acts = [a for a in m.actions() if a.text().lower().startswith("open file")]
        if not acts:
            m.hide()
            raise LookupError("no 'Open file…' entry: %r" % [a.text() for a in m.actions()])
        acts[0].trigger()
        m.hide()
        s.wait_until(lambda: w.done, 10, "file dialog")
        s.pump(1500)
        # a modal still up after the handler ran (MEASURED once: the file
        # dialog again) is recorded, grabbed and rejected, never left hanging
        extra = []
        for _ in range(3):
            m2 = s.app.activeModalWidget()
            if m2 is None:
                break
            extra.append(widget_info(m2))
            s.grab(m2, "open_file_extra_modal_%d" % len(extra))
            m2.reject() if hasattr(m2, "reject") else m2.close()
            s.pump(500)
        seen["extra_modals"] = [{"meta": e["meta"], "title": e.get("windowTitle")} for e in extra]
        after = view_state(s, picker)
        d["open_file"] = {"target": target, "dialog": seen.get("dialog"), "watch_error": w.error,
                          "extra_modals": seen.get("extra_modals"),
                          "after": after}
        s.grab(s.mw, "after_open_file")
        if w.error:
            raise RuntimeError(w.error)
        return after["docs"]
    s.step("Open file… (Qt file dialog)", open_file)

    # ------------------------------------- no starter submenu (R456)
    def no_starters():
        m = open_menu()
        subs = [a.text() for a in m.actions() if a.menu() is not None]
        texts = [a.text() for a in m.actions()]
        m.hide()
        d["starter"] = {"submenus": subs}
        if subs or any("starter" in t.lower() for t in texts):
            raise RuntimeError("the picker still has a starter submenu: %s" % subs)
        return "none"
    s.step("no starter-projects submenu (R456)", no_starters)
    d["report_tail"] = (s.report_text() or "")[-4000:]


Scenario("open_recent", timeout_s=170).run(main)
