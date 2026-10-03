"""AcadAgent — an AI agent workbench living inside FreeCAD.

Registers the workbench (shown to users as "Atech") and, on activation,
mounts the Atech Atelier shell. Geometry NEVER comes from this panel: it
writes a model script and the build measures what it made.
"""
import os as _os
import sys as _sys

try:
    _ADDON_DIR = _os.path.dirname(_os.path.abspath(__file__))
except NameError:
    import inspect as _inspect
    _ADDON_DIR = _os.path.dirname(_os.path.abspath(_inspect.getfile(_inspect.currentframe())))

if _ADDON_DIR not in _sys.path:
    _sys.path.insert(0, _ADDON_DIR)

# Renamed from "Atech Studio" (ADR-005): copy the trust store and chat index
# out of the old user-data folder once, before anything reads them. Never
# raises; the old folder is never touched.
try:
    from acadagent import migrate as _migrate
    _migrate.migrate()
except Exception:                                      # noqa: BLE001
    pass


class AcadAgentWorkbench(Workbench):  # noqa: F821 - injected by FreeCAD
    # User-facing names (R27). The class name and command ids stay: they are
    # internal keys FreeCAD persists (last workbench, shortcuts).
    MenuText = "Atech"
    ToolTip = "Describe a part to the agent; it builds and measures it"

    def Initialize(self):
        from acadagent import commands
        commands.register()
        view = ["AcadAgent_OpenReference", "AcadAgent_FitView",
                "AcadAgent_SpinView"]
        agent = ["AcadAgent_ShowPanel", "AcadAgent_CaptureView",
                 "AcadAgent_Terminal", "AcadAgent_AskView",
                 "AcadAgent_Settings"]
        # No toolbars: the workbench runs with the toolbar rows hidden
        # (chrome.py). Every command lives in the Atech menu.
        self.appendMenu("Atech", agent + ["Separator"] + view
                        + ["Separator", "AcadAgent_Credits"])
        # FreeCAD's own Help menu ("&Help", StdWorkbench) is merged by name,
        # so the credits also sit where users look for an About box.
        self.appendMenu("&Help", ["AcadAgent_Credits"])
        # Projects get their own submenu, one entry per buildable project.
        # Empty when the module library is not on this machine — an absent
        # library yields an absent menu, never a broken entry.
        projects = ["AcadAgent_Project_%s" % commands._safe(k)
                    for k in commands.project_command_ids()]
        if projects:
            self.appendMenu(["Atech", "New Project"], projects)

    def Activated(self):
        from acadagent import shell, viewport
        # Mouse orbit / scroll-zoom first; report-only, never blocks the shell.
        # The user's own view preferences are snapshotted before the first
        # write and restored on Deactivated / quit (R31).
        viewport.apply_view_theme()
        # The whole window: top bar, Chat | Model sidebar, view bar, empty
        # state. The sidebar is built once and re-shown here (R18).
        shell.install()

    def Deactivated(self):
        from acadagent import shell
        # Hands FreeCAD its chrome, toolbars and view preferences back and
        # hides the sidebar; the chat and any running turn survive (R18).
        shell.uninstall()

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(AcadAgentWorkbench())  # noqa: F821 - injected by FreeCAD
