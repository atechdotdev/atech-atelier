"""Smoke scenario: launch -> Atech shell ready, the main chrome present.

Records: launch-to-shell time, the sidebar, the hardware switch
(objectName "HardwareSwitch"), the view bar's buttons, a grab of the Home /
empty view and of the whole main window.
"""
import os
import sys

sys.path.insert(0, os.environ["ATECH_GUI_HARNESS"])
from scenario_base import Scenario, widget_info  # noqa: E402

from PySide6 import QtWidgets  # noqa: E402


def main(s):
    s.step("wait for Atech shell", s.wait_shell)
    sh = s.shell()
    mw = s.mw
    d = s.result["data"]
    d["window_title"] = mw.windowTitle()
    d["mw_size"] = [mw.width(), mw.height()]
    d["active_workbench"] = __import__("FreeCADGui").activeWorkbench().name()

    def sidebar():
        dock = sh._S["dock"]
        d["sidebar"] = {"visible": dock.isVisible(), "geometry": list(dock.geometry().getRect()),
                        "objectName": dock.objectName()}
        return dock.isVisible()
    s.step("sidebar present", sidebar)

    def hw_switch():
        hits = s.find(object_name="HardwareSwitch")
        if not hits:
            raise LookupError("no widget with objectName HardwareSwitch")
        d["hardware_switch"] = [widget_info(w) for w in hits]
        return len(hits)
    s.step("hardware switch present", hw_switch)

    def view_bar():
        bars = s.find(object_name="ViewBar")
        if not bars:
            raise LookupError("no ViewBar")
        out = []
        for b in bars[0].findChildren(QtWidgets.QAbstractButton):
            out.append({"objectName": b.objectName(), "text": b.text(),
                        "toolTip": b.toolTip(), "accessibleName": b.accessibleName(),
                        "visible": b.isVisible(), "enabled": b.isEnabled(),
                        "geometry": list(b.geometry().getRect())})
        d["view_bar"] = {"visible": bars[0].isVisible(), "buttons": out}
        return len(out)
    s.step("view bar buttons", view_bar)

    def home():
        for name in ("HomeView", "EmptyView"):
            hits = [w for w in s.find(object_name=name) if w.isVisible()]
            if hits:
                d["home_view"] = name
                return s.grab(hits[0], "home_view")
        d["home_view"] = None
        raise LookupError("neither HomeView nor EmptyView is visible")
    s.step("grab home/empty view", home)
    s.step("grab sidebar", lambda: s.grab(sh._S["dock"], "sidebar"))
    s.step("grab main window", lambda: s.grab(mw, "main_window"))


Scenario("smoke").run(main)
