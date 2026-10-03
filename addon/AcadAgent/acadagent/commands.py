"""commands — FreeCAD command registration."""
import FreeCADGui


class ShowPanel:
    def GetResources(self):
        return {"MenuText": "Show Chat",
                "ToolTip": "Open the chat"}

    def Activated(self):
        from . import panel
        panel.ensure_panel()

    def IsActive(self):
        return True


class Settings:
    def GetResources(self):
        return {"MenuText": "Agent Settings",
                "ToolTip": "Choose the agent and its model"}

    def Activated(self):
        from . import settings, shell
        # The open chat's workspaces are never "old" (R69): Clear old chat
        # workspaces rmtree'd the live folder, model.py included.
        settings.open_dialog(shell.chat_panel(),
                             keep_workspaces=shell.keep_workspaces())

    def IsActive(self):
        return True


class CaptureView:
    """Put the viewport into the transcript.

    This is the wire between capture.capture_to_panel and the UI. Both existed
    before this command did, with no call path between them — a producer, a
    hook, and nothing joining them, which reads as a working feature until you
    look for the caller.
    """

    def GetResources(self):
        return {"MenuText": "Send Viewport to Agent",
                "ToolTip": "Capture the 3D view and add it to the chat"}

    def Activated(self):
        from . import capture, panel
        # ensure_panel() returns the AgentPanel itself (the shell owns the
        # dock), which is where the add_shot hook lives.
        capture.capture_to_panel(panel.ensure_panel())

    def IsActive(self):
        # Capture needs a document and an active 3D view; without one the
        # command would raise CaptureError into a menu click.
        import FreeCAD
        return FreeCAD.ActiveDocument is not None


class OpenReferenceModel:
    """Put the reference machine in the viewport.

    The branded build opened on an empty black viewport — correct (no document)
    but indistinguishable from broken. This gives the 3D view something real to
    show: the sample crane, loaded from the .brep files the fixture builds.

    View-only. It loads and frames geometry; it never computes a number.
    """

    def GetResources(self):
        return {"MenuText": "Open Sample Crane",
                "ToolTip": "Load a sample crane assembly"}

    def Activated(self):
        import FreeCAD
        from . import viewport
        try:
            doc, made, skipped = viewport.open_reference_model()
        except RuntimeError as exc:
            # Absent stays absent: say what is missing, never substitute a box.
            FreeCAD.Console.PrintError("Atech: %s\n" % exc)
            from . import shell
            shell._notify("Sample crane not available", shell._sentence(exc))
            return
        msg = "Atech: loaded %s (%d parts)" % (doc.Name, made)
        if skipped:
            msg += "; %d skipped: %s" % (len(skipped), ", ".join(skipped[:3]))
        FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        from . import viewport
        # Greyed out rather than failing on click when the fixture is unbuilt.
        return bool(viewport.crane_parts())


class SpinView:
    """Start/stop continuous rotation of the 3D view."""

    def GetResources(self):
        return {"MenuText": "Spin View",
                "ToolTip": "Rotate the model continuously (click again to stop)"}

    def Activated(self):
        from . import viewport
        # Toggle on this class, so the menu item is its own state.
        SpinView._on = not getattr(SpinView, "_on", False)
        if not viewport.spin(SpinView._on):
            import FreeCAD
            SpinView._on = False
            FreeCAD.Console.PrintWarning(
                "Atech: no active 3D view to spin\n")

    def IsActive(self):
        import FreeCAD
        return FreeCAD.ActiveDocument is not None


class FitView:
    """Frame everything in the view."""

    def GetResources(self):
        return {"MenuText": "Fit and Frame",
                "ToolTip": "Fit all geometry and return to the isometric view"}

    def Activated(self):
        from . import viewport
        viewport.iso_and_fit()

    def IsActive(self):
        import FreeCAD
        return FreeCAD.ActiveDocument is not None


class Credits:
    """Credit every open-source project Atech Atelier is built on.

    Shows CREDITS.md as installed in the image (credits.py resolves it), so
    the menu and the shipped file cannot disagree.
    """

    def GetResources(self):
        return {"MenuText": "Credits && Open-Source Licences",
                "ToolTip": "Atech Atelier, powered by FreeCAD: the open-source "
                           "projects it is built on and their licences"}

    def Activated(self):
        from . import credits
        credits.open_dialog()

    def IsActive(self):
        return True


def register():
    FreeCADGui.addCommand("AcadAgent_ShowPanel", ShowPanel())
    FreeCADGui.addCommand("AcadAgent_Credits", Credits())
    FreeCADGui.addCommand("AcadAgent_Settings", Settings())
    FreeCADGui.addCommand("AcadAgent_CaptureView", CaptureView())
    FreeCADGui.addCommand("AcadAgent_OpenReference", OpenReferenceModel())
    FreeCADGui.addCommand("AcadAgent_SpinView", SpinView())
    FreeCADGui.addCommand("AcadAgent_FitView", FitView())
    FreeCADGui.addCommand("AcadAgent_Terminal", OpenTerminal())
    FreeCADGui.addCommand("AcadAgent_AskView", AskClaudeAboutView())
    # One command per project, so each appears in the menu by its real name
    # rather than behind a chooser dialog.
    for key in project_command_ids():
        FreeCADGui.addCommand("AcadAgent_Project_%s" % _safe(key),
                              NewModuleProject(key))


def _safe(key):
    return "".join(c if c.isalnum() else "_" for c in key)


def project_command_ids():
    """Project keys the library can actually build, or [] when it is absent."""
    try:
        from . import projects
        return projects.project_keys() if projects.library_available() else []
    except Exception:
        return []


class OpenTerminal:
    """A real shell in the dock.

    Runs on a stdlib pty, so `claude`, `bin/cad` and git all see a tty and
    stream normally. It is NOT a full VT100: cursor-addressing sequences are
    stripped, so a full-screen TUI (vim, htop) will not render correctly.
    That limit is stated rather than discovered.
    """

    def GetResources(self):
        return {"MenuText": "Open Terminal",
                "ToolTip": "Open a terminal"}

    def Activated(self):
        from . import terminal_dock
        terminal_dock.ensure_terminal()

    def IsActive(self):
        return True


class AskClaudeAboutView:
    """Capture the live viewport and ask the agent about it, in the chat.

    The same path as the view bar's "Ask about this view" button (R95): the
    ACTUAL 3D view is captured into the chat workspace, shown inline, and
    the question goes out as a normal chat turn.
    """

    def GetResources(self):
        return {"MenuText": "Ask About This View",
                "ToolTip": "Capture the 3D view and ask the agent about "
                           "what it shows"}

    def Activated(self):
        from . import shell
        shell._ask_view()

    def IsActive(self):
        # Needs a viewport to capture; the chat reports its own engine
        # state, like the view bar button this mirrors.
        import FreeCAD
        return FreeCAD.ActiveDocument is not None


class NewModuleProject:
    """Build a project from real Atech modules.

    Geometry and dimensions come from the module library's own presets.yaml
    ("never guess"), and every placement is measured against it. A module the
    library does not define is reported, never approximated.
    """

    def __init__(self, key=None):
        self._key = key

    def GetResources(self):
        from . import projects
        p = projects.project_info(self._key)
        return {"MenuText": p["title"] if p else "New Module Project…",
                "ToolTip": p["purpose"] if p else
                           "Assemble a board and modules from the Atech library"}

    def Activated(self):
        from . import projects
        projects.build_and_show(self._key)

    def IsActive(self):
        from . import projects
        return projects.library_available()
