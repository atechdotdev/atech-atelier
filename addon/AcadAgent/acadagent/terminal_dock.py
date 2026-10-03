"""terminal_dock — mounts the terminal: a real shell in a dock.

    ensure_terminal()   a real shell in the dock (terminal.py on a pty)

"Ask about this view" is NOT answered here any more (R95): its answer
belongs in the chat, where the user reads it (shell._ask_view ->
vision.ask_in_chat). ask_about_view() below only forwards there, for old
callers and macros.

GUI-THREAD RULE (runner.py states it; this file obeys it)
    The status probe runs on a QThread and emits a signal. Every widget
    touch below happens in a slot on the main thread.
"""
import os

from PySide6 import QtCore, QtWidgets

from . import claude_cli, engine, style, terminal


_DOCK = None
_QUIT_HOOKED = [False]
_PROBES = set()   # status workers in flight: no Qt parent, joined at quit


class _StatusProbe(QtCore.QThread):
    """engine.status_line() can start `claude --version` (10 s timeout), so
    it runs here, never on the GUI thread (R20)."""

    done = QtCore.Signal(str)

    def run(self):
        try:
            line = engine.status_line()
        except Exception:                              # noqa: BLE001
            try:
                v = claude_cli.version()
                line = ("claude %s" % v.split()[0]) if v else "claude not found"
            except Exception:                          # noqa: BLE001
                line = "Claude status unknown"
        self.done.emit(line)


def shutdown(timeout_ms=3000):
    """aboutToQuit: end the shell session and join every thread this module
    started, so Qt never destroys a running QThread (R20). Idempotent."""
    ok = True
    dock = _DOCK
    if dock is not None:
        try:
            body = dock.widget()
            if body is not None:
                ok = body.term.close_session() and ok
        except RuntimeError:                           # C++ side gone
            pass
    for probe in list(_PROBES):
        ok = probe.wait(timeout_ms) and ok
    return ok


def _hook_quit():
    if not _QUIT_HOOKED[0]:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(shutdown)
            _QUIT_HOOKED[0] = True


def _main_window():
    import FreeCADGui
    return FreeCADGui.getMainWindow()


def ensure_terminal():
    """Create or raise the terminal dock. Returns the QDockWidget."""
    global _DOCK
    mw = _main_window()
    if mw is None:
        return None
    if _DOCK is not None:
        try:
            _DOCK.show()
            _DOCK.raise_()
            return _DOCK
        except RuntimeError:
            # The C++ side was deleted (dock closed); rebuild rather than
            # handing back a dangling wrapper.
            _DOCK = None

    dock = QtWidgets.QDockWidget("Terminal", mw)
    dock.setObjectName("AcadAgentTerminal")
    dock.setTitleBarWidget(QtWidgets.QWidget())
    body = _TerminalBody(dock)
    dock.setWidget(body)
    mw.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock)
    dock.show()
    _hook_quit()
    body.term.start()
    body.term.inp.setFocus()
    _DOCK = dock
    return dock


def ask_about_view(question=None, views=None):
    """Forwarded to the chat (R95): the view is captured into the chat
    workspace and the question asked as a chat turn. Returns what
    vision.ask_in_chat returns (True when the turn started).

    views None = vision.views_for decides (R145/R162: the module face of
    an Atech board, the isometric corner otherwise)."""
    from . import shell, vision
    return vision.ask_in_chat(question, views=views, panel=shell.show_chat())


class _TerminalBody(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QtWidgets.QWidget()
        bar.setObjectName("TermHead")
        bar.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        bl = QtWidgets.QHBoxLayout(bar)
        bl.setContentsMargins(14, 6, 8, 6)
        bl.setSpacing(10)

        title = QtWidgets.QLabel("Terminal")
        title.setObjectName("TermTitle")
        bl.addWidget(title)

        self.status = QtWidgets.QLabel("Checking Claude…")
        self.status.setObjectName("TermStatus")
        self._engine = None           # the probe's line, once it answers
        self._ended = None            # the shell's exit code, once it exits
        bl.addWidget(self.status)
        bl.addStretch(1)

        # The dock's own title bar is replaced by this header (see
        # ensure_terminal), so the close control lives here.
        self.btn_close = QtWidgets.QPushButton()
        self.btn_close.setObjectName("TermClose")
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setToolTip("Close the terminal")
        self.btn_close.setIcon(style.icon("x", style.tokens()["muted"], 14))
        self.btn_close.clicked.connect(lambda: self.parent().hide()
                                       if self.parent() else None)
        bl.addWidget(self.btn_close)
        lay.addWidget(bar)

        self.term = terminal.TerminalWidget(cwd=_repo_dir(), parent=self)
        self.term.ended.connect(self._on_shell_ended)
        lay.addWidget(self.term, 1)
        self._show_status()
        self._probe_status()

        self.setStyleSheet(style.qss(style.TERMINAL_QSS))

    # ------------------------------------------------------------- status
    def _probe_status(self):
        # Reports the SELECTED engine and whether it can actually run, not
        # just whether the claude binary happens to exist. Off the GUI
        # thread: the probe can start a process.
        probe = _StatusProbe()
        _PROBES.add(probe)
        probe.done.connect(self._on_status)
        probe.finished.connect(lambda p=probe: _PROBES.discard(p))
        probe.start()

    def _on_status(self, line):
        self._engine = line
        self._show_status()

    def _on_shell_ended(self, code):
        self._ended = code
        self._show_status()

    def _show_status(self):
        try:
            self.status.setText(header_status(
                self.term.shell_name, self._engine, self._ended))
        except RuntimeError:                           # widget gone
            pass

    def _write(self, s):
        self.term._append(s)


def header_status(shell_name, engine_line=None, ended=None):
    """The dock header's status: what runs HERE (a shell), then the chat
    engine's state, labelled as such. The header used to show the engine
    line alone ("Claude Code 2.1.232 — ready") over a shell that was sitting
    in zsh's first-run menu (R106): the line described the chat, not this
    session."""
    shell = shell_name or "shell"
    here = ("%s exited (%s)" % (shell, ended)) if ended is not None \
        else "%s shell" % shell
    if engine_line is None:
        return "%s · checking the chat engine…" % here
    return "%s · chat engine: %s" % (here, engine_line)


def _repo_dir():
    """Where the shell starts: the open chat's workspace (where model.py
    and the captures are), else the repo the addon came from when it is one
    (a dev checkout), else the user's home."""
    try:
        from . import vision
        ws = vision.chat_workspace()
    except Exception:                                  # noqa: BLE001
        ws = None
    if ws and os.path.isdir(ws):
        return ws
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.normpath(os.path.join(here, "..", "..", ".."))
    return cand if os.path.isdir(os.path.join(cand, ".git")) \
        else os.path.expanduser("~")
