"""credits — the "Credits & open-source licences" dialog.

Shows CREDITS.md exactly as it ships: the build installs the repo's root
CREDITS.md to usr/share/doc/<doc dir>/CREDITS.md (build_appimage.sh, gated
by verify_tree.py). The doc dir is "atech-atelier" after the rename to Atech
Atelier (ADR-005); "atech-studio" is still looked in so an image built before
the build script follows the rename keeps showing its credits. In a development checkout the repo root copy
is used. Nothing here writes a credit of its own: an absent file is reported as
absent, never replaced by a summary that could drift from the real one.
"""
import os

DOC_DIRS = ("atech-atelier", "atech-studio")
DOC_REL = os.path.join("share", "doc", DOC_DIRS[0], "CREDITS.md")
DOC_RELS = tuple(os.path.join("share", "doc", d, "CREDITS.md") for d in DOC_DIRS)
HEADER = "Atech Atelier, powered by FreeCAD"


def candidates():
    """Where CREDITS.md may live, most authoritative first."""
    out = []
    try:
        import FreeCAD
        # getHomePath() is the AppImage's usr/ (branding.xml resolves there).
        out += [os.path.join(FreeCAD.getHomePath(), r) for r in DOC_RELS]
    except Exception:
        pass
    here = os.path.dirname(os.path.realpath(__file__))   # .../acadagent
    addon = os.path.dirname(here)                         # .../AcadAgent
    # Installed: usr/Mod/AcadAgent/acadagent -> usr/
    out += [os.path.join(os.path.dirname(os.path.dirname(addon)), r)
            for r in DOC_RELS]
    # Repo checkout: addon/AcadAgent/acadagent -> repo root.
    out.append(os.path.join(os.path.dirname(os.path.dirname(addon)), "CREDITS.md"))
    seen, uniq = set(), []
    for c in out:
        c = os.path.normpath(c)
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def credits_path():
    """The CREDITS.md the dialog shows, or None when none is readable."""
    for c in candidates():
        if os.path.isfile(c) and os.access(c, os.R_OK):
            return c
    return None


def read_credits():
    """(path, text). path is None when no copy exists; text then says so."""
    p = credits_path()
    if p is None:
        return None, ("# Credits not found\n\nCREDITS.md was not found in any "
                      "of:\n\n" + "\n".join("- `%s`" % c for c in candidates()))
    with open(p, encoding="utf-8") as fh:
        return p, fh.read()


_QSS = """
QDialog {{ background: {panel}; }}
QLabel#creditsTitle {{ color: {text}; font-family: "{UI}"; font-size: 15px;
                       font-weight: 600; }}
QLabel#creditsSource {{ color: {muted}; font-family: "{UI}"; font-size: 11px; }}
QTextBrowser {{ background: {panel}; color: {text}; border: 1px solid {line};
                border-radius: 6px; padding: 8px; font-family: "{UI}"; }}
"""


def open_dialog(parent=None):
    """Show the credits, modal, scrollable, rendered as markdown."""
    from PySide6 import QtCore, QtWidgets
    from . import style

    if parent is None:
        try:
            import FreeCADGui
            parent = FreeCADGui.getMainWindow()
        except Exception:
            parent = None
    path, text = read_credits()

    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("Credits & open-source licences")
    dlg.resize(820, 640)
    try:
        dlg.setStyleSheet(style.qss(_QSS))
    except Exception:
        pass     # unstyled is still readable; never fail the credits on theme
    lay = QtWidgets.QVBoxLayout(dlg)

    title = QtWidgets.QLabel(HEADER)
    title.setObjectName("creditsTitle")
    lay.addWidget(title)
    src = QtWidgets.QLabel(path or "CREDITS.md not found")
    src.setObjectName("creditsSource")
    src.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    lay.addWidget(src)

    view = QtWidgets.QTextBrowser()
    view.setOpenExternalLinks(True)
    view.setMarkdown(text)
    lay.addWidget(view, 1)

    buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    dlg.exec()
