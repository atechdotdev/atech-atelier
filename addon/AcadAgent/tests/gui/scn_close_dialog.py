"""The "Save all changes to document 'Unnamed' before closing?" dialog.

User bug: with the Atech shell active, closing a modified document shows
FreeCAD's save prompt (with an "Apply to all" check box) whose buttons are
broken: "Don't Save" clipped to "n't S", Save / Cancel drawn as empty white
and black squares ~60 px (device pixels) tall.

Phase 1, triggers: the same modified document is closed in every way a
user can (close-all, the sub-window's close, Cmd+W, quitting the app). Each
prompt is recorded (buttons' text, size, sizeHint, minimumSize, font,
stylesheet chain), grabbed (trigger_<name>.png) and Cancelled.

Phase 2, variants: the prompt that shows the bug (Std_CloseAllWindows, the
one parented to the main window, with "Apply to all") is opened under each
stylesheet state, taking one layer away at a time
(close_<variant>.png), to find the layer that breaks it.
"""
import os
import re
import sys

sys.path.insert(0, os.environ["ATECH_GUI_HARNESS"])
from scenario_base import Scenario, press_button  # noqa: E402

import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6 import QtGui, QtWidgets  # noqa: E402


def _btns(info):
    return [{"text": b.get("text"), "size": b["size"], "sizeHint": b["sizeHint"],
             "minimumSize": b["minimumSize"], "minimumSizeHint": b["minimumSizeHint"]}
            for b in info["buttons"]]


def _clipped(info):
    """Push buttons drawn narrower than their own sizeHint (the bug)."""
    return [b.get("text") for b in info["buttons"]
            if b["class"] == "QPushButton" and b["size"][0] < b["sizeHint"][0]]


def main(s):
    s.step("wait for Atech shell", s.wait_shell)
    from acadagent import style
    app, mw = s.app, s.mw
    saved = {"mw": mw.styleSheet(), "app": app.styleSheet()}
    d = s.result["data"]
    d["mw_styleSheet"] = saved["mw"]
    d["app_styleSheet_len"] = len(saved["app"])
    d["style_RESET"] = style.RESET
    with open(os.path.join(s.out, "app_stylesheet.qss"), "w") as f:
        f.write(saved["app"])

    doc = s.step("new document", lambda: s.new_doc("Unnamed"))
    s.step("modify it", lambda: s.modify_doc(doc))
    # MEASURED: FreeCAD adds the "Apply to all" check box only when MORE THAN
    # ONE document has unsaved changes; the second document is opened just
    # before the triggers that need it.
    docs = {"second": None}

    def second_doc():
        d2 = s.new_doc("Unnamed1")
        s.modify_doc(d2)
        docs["second"] = d2
        return d2.Name

    def prompt(name, trigger):
        App.setActiveDocument(doc.Name)
        s.pump(100)
        w = s.expect_modal(press_button("Cancel"), timeout_s=6, name=name)
        trigger()
        s.wait_until(lambda: w.done, 8, "save prompt")
        if w.error:
            raise RuntimeError(w.error)
        return w.info

    # ------------------------------------------------------- phase 1
    def sub_close():
        mdi = mw.findChild(QtWidgets.QMdiArea)
        (mdi.activeSubWindow() or mdi.subWindowList()[0]).close()

    def cmd_w():
        from PySide6.QtTest import QTest
        mdi = mw.findChild(QtWidgets.QMdiArea)
        sub = mdi.activeSubWindow() or mdi.subWindowList()[0]
        tgt = sub.widget()
        tgt.setFocus()
        s.pump(50)
        QTest.keySequence(app.focusWidget() or tgt, QtGui.QKeySequence(QtGui.QKeySequence.Close))

    triggers = [
        ("Std_CloseActiveWindow", lambda: Gui.runCommand("Std_CloseActiveWindow")),
        ("subwindow_close", sub_close),
        ("cmd_w", cmd_w),
        ("Std_CloseAllWindows, 1 modified doc", lambda: Gui.runCommand("Std_CloseAllWindows")),
        ("main_window_close (quit), 1 modified doc", lambda: mw.close()),
        ("+ second modified document", None),
        ("Std_CloseAllWindows, 2 modified docs", lambda: Gui.runCommand("Std_CloseAllWindows")),
        ("main_window_close (quit), 2 modified docs", lambda: mw.close()),
    ]
    tsum = {}
    for name, trig in triggers:
        if trig is None:
            s.step("second modified document", second_doc)
            continue

        def one(name=name, trig=trig):
            info = prompt("trigger_" + re.sub(r"\W+", "_", name).strip("_"), trig)
            tsum[name] = {"parent": info["parent"], "checkbox": info.get("checkbox"),
                          "clipped": _clipped(info), "buttons": _btns(info)}
            return "clipped=%s" % tsum[name]["clipped"]
        s.step("trigger: " + name, one)
    d["by_trigger"] = tsum

    # ------------------------------------------------------- phase 2
    # (two modified documents are open from here on: the buggy prompt)
    def no_pushbutton(qss):
        return re.sub(r"(?s)[^{}]*QPushButton[^{}]*\{[^{}]*\}", "\n", qss)

    no_reset = saved["mw"].replace(style.RESET, "")
    variants = [
        ("baseline", lambda: None),
        ("mw_qss_empty", lambda: mw.setStyleSheet("")),
        ("mw_qss_without_RESET (proposed fix)", lambda: mw.setStyleSheet(no_reset)),
        ("mw_qss_RESET_only", lambda: mw.setStyleSheet(style.RESET)),
        ("app_qss_empty", lambda: app.setStyleSheet("")),
        ("app_qss_without_QPushButton", lambda: app.setStyleSheet(no_pushbutton(saved["app"]))),
        ("shell_uninstalled (Part workbench)", lambda: Gui.activateWorkbench("PartWorkbench")),
        ("upstream_like: app qss, no mw qss, no shell",
         lambda: (Gui.activateWorkbench("PartWorkbench"), mw.setStyleSheet(""))),
    ]

    def restore():
        if Gui.activeWorkbench().name() != "AcadAgentWorkbench":
            Gui.activateWorkbench("AcadAgentWorkbench")
            s.pump(300)
        if app.styleSheet() != saved["app"]:
            app.setStyleSheet(saved["app"])
        if mw.styleSheet() != saved["mw"]:
            mw.setStyleSheet(saved["mw"])
        s.pump(100)

    vsum = {}
    for name, apply in variants:
        def one(name=name, apply=apply):
            apply()
            s.pump(150)
            state = {"mw_qss_len": len(mw.styleSheet()), "app_qss_len": len(app.styleSheet()),
                     "mw_has_RESET": style.RESET.strip() in mw.styleSheet(),
                     "workbench": Gui.activeWorkbench().name()}
            info = prompt("close_" + re.sub(r"\W+", "_", name).strip("_"),
                          lambda: Gui.runCommand("Std_CloseAllWindows"))
            vsum[name] = dict(state, clipped=_clipped(info), buttons=_btns(info),
                              dialog_size=info["size"])
            return "clipped=%s" % vsum[name]["clipped"]
        s.step("variant: " + name, one)
        s.step("restore after " + name, restore)
    d["by_variant"] = vsum
    s.step("document still open after every Cancel", lambda: doc.Name in App.listDocuments())


Scenario("close_dialog", timeout_s=150).run(main)
