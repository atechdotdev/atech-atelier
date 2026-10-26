"""navbar - the sidebar's top: the project picker and the 3D CAD | Atech
modules switch.

Both are taken from studio.atech.dev rather than invented:

  PillTabs      Studio's "two equal tabs over one sliding thumb" (the Design
                stage's Simple / Advanced control, #vp-modetabs): a rounded
                track with a hairline border, equal-width tabs, and ONE black
                (light) / white (dark) thumb that slides to the chosen tab
                with Studio's overshoot curve, cubic-bezier(0.34, 1.56, 0.64,
                1) over 300 ms. Label weight never changes with the choice
                (Studio's rule: the fill is the signal, bold is not a second
                one).
  ProjectPicker Studio's project switcher, as Atelier has projects: one per
                document (each document already has its own chat, keyed by
                its Uid in sessions.json), so choosing a project activates
                its document and the chat follows. The menu lists the open
                projects (the current one checked), recent files, a new
                project and Open file (R456: no starter-projects submenu).

project_entries() is the menu as data, so it is testable without Qt.

R360-R372 (projects as files, projects_store.py): the picker also shows an
unsaved dot, and its menu acts on the current project: Save, Rename,
Duplicate, Show in Finder, Export for sharing, Move to Trash
(project_actions() is that section as data). SaveButton is the round Save
button beside the picker; new_project_flow asks for a name and saves the
new project into the projects folder at once.
"""
import os

from PySide6 import QtCore, QtGui, QtWidgets

from . import projects_store, style

#: Studio's thumb easing, cubic-bezier(0.34, 1.56, 0.64, 1): Qt's OutBack with
#: this overshoot traces the same overshoot-and-settle.
_EASE = QtCore.QEasingCurve(QtCore.QEasingCurve.OutBack)
_EASE.setOvershoot(1.2)
SLIDE_MS = 300
RECENT_MAX = 10                     # R370
RECENT_PARAM = "User parameter:BaseApp/Preferences/RecentFiles"


# ------------------------------------------------------------- pill tabs
class PillTabs(QtWidgets.QWidget):
    """Equal tabs over one sliding thumb. Emits changed(index)."""

    changed = QtCore.Signal(int)

    PAD = 4
    HEIGHT = 36

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName("PillTabs")
        self._labels = list(labels)
        self._icons = [None] * len(self._labels)
        self._index = 0
        self._pos = 0.0                       # thumb position, in tabs
        self._hover = -1
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(SLIDE_MS)
        self._anim.setEasingCurve(_EASE)
        self._anim.valueChanged.connect(self._on_anim)
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.TabFocus)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Fixed)
        self.setAccessibleName("View")

    # -- api
    def index(self):
        return self._index

    def label(self, i):
        return self._labels[i]

    def set_icons(self, icons):
        self._icons = list(icons) + [None] * (len(self._labels) - len(icons))
        self.update()

    def set_index(self, i, animate=True, emit=False):
        i = max(0, min(len(self._labels) - 1, int(i)))
        changed = i != self._index
        self._index = i
        self._anim.stop()
        if animate and self.isVisible() and changed:
            self._anim.setStartValue(float(self._pos))
            self._anim.setEndValue(float(i))
            self._anim.start()
        else:
            self._pos = float(i)
            self.update()
        if changed and emit:
            self.changed.emit(i)

    def sizeHint(self):                                 # noqa: N802
        fm = QtGui.QFontMetrics(self._font())
        w = max(fm.horizontalAdvance(t) for t in self._labels) + 44
        return QtCore.QSize(w * len(self._labels) + 2 * self.PAD, self.HEIGHT)

    # -- internals
    def _font(self):
        f = QtGui.QFont(self.font())
        f.setFamily(style._pick(style.UI_FAMILIES).strip("'"))
        f.setPixelSize(12)
        f.setWeight(QtGui.QFont.DemiBold)
        return f

    def _on_anim(self, v):
        self._pos = float(v)
        self.update()

    def _tab_rect(self, i, pos=None):
        n = len(self._labels)
        inner = self.rect().adjusted(self.PAD, self.PAD, -self.PAD, -self.PAD)
        w = inner.width() / float(n)
        x = inner.x() + w * (i if pos is None else pos)
        return QtCore.QRectF(x, inner.y(), w, inner.height())

    def _at(self, p):
        for i in range(len(self._labels)):
            if self._tab_rect(i).contains(QtCore.QPointF(p)):
                return i
        return -1

    def paintEvent(self, _ev):                         # noqa: N802
        t = style.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        track = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        r = track.height() / 2.0
        p.setPen(QtGui.QPen(QtGui.QColor(t["line"]), 1))
        p.setBrush(QtGui.QColor(t["track"]))
        p.drawRoundedRect(track, r, r)
        thumb = self._tab_rect(0, self._pos)
        tr = thumb.height() / 2.0
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 20))                   # soft drop
        p.drawRoundedRect(thumb.translated(0, 1), tr, tr)
        p.setBrush(QtGui.QColor(t["btn_bg"]))
        p.drawRoundedRect(thumb, tr, tr)
        p.setFont(self._font())
        for i, text in enumerate(self._labels):
            rect = self._tab_rect(i)
            on = abs(self._pos - i) < 0.5
            col = t["btn_text"] if on else (t["text"] if i == self._hover else t["muted"])
            p.setPen(QtGui.QColor(col))
            ico = self._icons[i]
            fm = QtGui.QFontMetrics(p.font())
            tw = fm.horizontalAdvance(text)
            iw = 14 + 6 if ico is not None else 0
            x0 = rect.center().x() - (tw + iw) / 2.0
            if ico is not None:
                ico.paint(p, QtCore.QRect(int(x0), int(rect.center().y() - 7), 14, 14),
                          QtCore.Qt.AlignCenter,
                          QtGui.QIcon.Normal if not on else QtGui.QIcon.Selected)
            p.drawText(QtCore.QRectF(x0 + iw, rect.y(), tw + 2, rect.height()),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)
        if self.hasFocus():
            p.setPen(QtGui.QPen(QtGui.QColor(t["accent"]), 2))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawRoundedRect(track.adjusted(1, 1, -1, -1), r, r)
        p.end()

    def mouseMoveEvent(self, ev):                      # noqa: N802
        h = self._at(ev.position().toPoint())
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, _ev):                         # noqa: N802
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, ev):                   # noqa: N802
        i = self._at(ev.position().toPoint())
        if i >= 0:
            self.set_index(i, emit=True)

    def keyPressEvent(self, ev):                       # noqa: N802
        k = ev.key()
        if k in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right):
            step = -1 if k == QtCore.Qt.Key_Left else 1
            self.set_index((self._index + step) % len(self._labels), emit=True)
        else:
            super().keyPressEvent(ev)


# ------------------------------------------------------------- projects
def recent_files(limit=RECENT_MAX):
    """R370: Atech's recent projects, then FreeCAD's recent-files list,
    most recent first: existing files only, one entry per file however it
    was reached (deduped by realpath: /tmp/x and /private/tmp/x are one)."""
    try:
        return projects_store.recent_files(limit)
    except Exception:                                  # noqa: BLE001
        return []


def project_entries(open_docs, active, recent, starters=None):
    """The picker's menu as data, top to bottom.

    open_docs  [(name, label, file_path or "")] in FreeCAD's order
    active     the active document's name, or None
    recent     [file path], most recent first
    starters   ignored (R456: the old "Atech starter projects" submenu is
               gone; the default projects are files in the projects folder
               and Home's "Start from an example" row)

    Returns [(kind, payload, text, checked)], kinds: "header", "open",
    "recent", "new", "file", "sep". A recent file that is already open is
    listed once, as open."""
    out = []
    open_paths = {os.path.realpath(p) for _n, _l, p in open_docs if p}
    if open_docs:
        out.append(("header", None, "Open projects", False))
        for name, label, _path in open_docs:
            out.append(("open", name, label or name, name == active))
    rec = [p for p in recent if os.path.realpath(p) not in open_paths]
    if rec:
        out.append(("sep", None, "", False))
        out.append(("header", None, "Recent", False))
        stems = [os.path.splitext(os.path.basename(p))[0] for p in rec]
        for p, stem in zip(rec, stems):
            # Two files with one name: say which folder each is in.
            text = stem if stems.count(stem) == 1 else "%s  (%s)" % (
                stem, os.path.basename(os.path.dirname(p)) or "/")
            out.append(("recent", p, text, False))
    out.append(("sep", None, "", False))
    out.append(("new", None, "New project", False))
    out.append(("file", None, "Open file…", False))
    return out


def current_title(open_docs, active):
    for name, label, _p in open_docs:
        if name == active:
            return label or name
    return "No project open"


def _open_docs():
    try:
        import FreeCAD
        docs = FreeCAD.listDocuments()
        act = FreeCAD.ActiveDocument
        return ([(n, d.Label, getattr(d, "FileName", "") or "") for n, d in docs.items()],
                act.Name if act is not None else None)
    except Exception:                                  # noqa: BLE001
        return [], None


def activate_document(name):
    """Bring document `name` to the front: its 3D view becomes the active
    MDI window (the chat follows the active document).

    R384: matched by the document's Name through the shell
    (shell.activate_document / pick_subwindow, R302), never by a window
    title prefix: "Box" no longer picks "Box001", and a relabelled
    document is still found. Without the shell (a test, no main window)
    the 3D view is activated directly."""
    import FreeCAD
    try:
        from . import shell
        if shell.activate_document(name):
            return True
    except Exception:                                  # noqa: BLE001
        pass
    try:
        import FreeCADGui
        FreeCAD.setActiveDocument(name)
        gdoc = FreeCADGui.getDocument(name)
        views = gdoc.mdiViewsOfType("Gui::View3DInventor") if gdoc else []
        if views:
            FreeCADGui.getMainWindow().setActiveWindow(views[0])
            return True
    except Exception:                                  # noqa: BLE001
        pass
    return False


# ------------------------------------------------- this project (R367)
#: (key, text) of the current project's actions, in menu order.
PROJECT_ACTIONS = (
    ("save", "Save"),
    ("rename", "Rename…"),
    ("duplicate", "Duplicate"),
    ("reveal", "Show in Finder"),
    ("export", "Export for sharing…"),
    ("trash", "Move to Trash…"),
)


def project_actions(has_doc, has_file):
    """The "This project" section as data: [(key, text, enabled)]. Save
    works on any open project (one without a file asks for a name); the
    others need the project's file."""
    if not has_doc:
        return []
    return [(key, text, key == "save" or bool(has_file))
            for key, text in PROJECT_ACTIONS]


def _active_doc():
    try:
        import FreeCAD
        return FreeCAD.ActiveDocument
    except Exception:                                  # noqa: BLE001
        return None


def _ask_name(parent, title, label, default):
    """A one-line name prompt. None when cancelled."""
    dlg = QtWidgets.QInputDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setLabelText(label)
    dlg.setTextValue(default)
    dlg.setOkButtonText("Save" if title.startswith("New") else "OK")
    dlg.setAccessibleName(title)
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return None
    return dlg.textValue()


def _confirm(parent, title, text, ok_text):
    box = QtWidgets.QMessageBox(parent)
    box.setIcon(QtWidgets.QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    ok = box.addButton(ok_text, QtWidgets.QMessageBox.DestructiveRole)
    cancel = box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() is ok


def _ask_save_path(parent, title, start):
    path, _f = QtWidgets.QFileDialog.getSaveFileName(
        parent, title, start, "FreeCAD project (*.FCStd)")
    return path or None


def _warn(parent, title, text):
    QtWidgets.QMessageBox.warning(parent, title, text)


def new_project_flow(parent=None, ask=None, folder=None, warn=None):
    """R361: "New project" asks for a name ("Untitled N" offered) and saves
    the new project into the projects folder at once. A name that cannot
    be used is explained (warn) and asked again. Returns the document, or
    None when cancelled."""
    folder = folder or projects_store.ensure_projects_dir()
    default = projects_store.default_name(folder)
    ask = ask or (lambda d: _ask_name(parent, "New project",
                                      "Name of the new project:", d))
    warn = warn or (lambda t, x: _warn(parent, t, x))
    while True:
        name = ask(default)
        if name is None:
            return None
        why = projects_store.name_problem(name, folder)
        if not why:
            return projects_store.create_project(name, folder)
        warn("Choose another name", why)
        default = projects_store.clean_name(name) or default


def save_active(parent=None, ask=None):
    """R362: Save for the picker and the Save button. A project without a
    file is given a name and saved into the projects folder. True when
    saved."""
    doc = _active_doc()
    if doc is None:
        return False
    if getattr(doc, "FileName", ""):
        return projects_store.save(doc)
    folder = projects_store.ensure_projects_dir()
    label = getattr(doc, "Label", "") or ""
    default = label if label and not label.startswith("Unnamed") else \
        projects_store.default_name(folder)
    ask = ask or (lambda d: _ask_name(parent, "Save project",
                                      "Name of the project:", d))
    name = ask(default)
    if name is None:
        return False
    projects_store.save_new(doc, name, folder)
    return True


class ProjectPicker(QtWidgets.QToolButton):
    """The current project's name in a pill; click for the menu. A dot
    after the name says the project has unsaved changes (R362)."""

    DOT = 7

    def __init__(self, on_new=None, on_open_file=None, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectPicker")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Fixed)
        self.setAccessibleName("Project")
        self._on_new = on_new
        self._on_open_file = on_open_file
        self._modified = False
        # Dialogs, replaceable in tests: ask_name(title, label, default),
        # confirm(title, text, ok_text), ask_save_path(title, start),
        # warn(title, text).
        self.ask_name = lambda t, l, d: _ask_name(self.window(), t, l, d)
        self.confirm = lambda t, x, o: _confirm(self.window(), t, x, o)
        self.ask_save_path = lambda t, s: _ask_save_path(self.window(), t, s)
        self.warn = lambda t, x: _warn(self.window(), t, x)
        self.reveal = projects_store.reveal_in_finder
        self._menu = QtWidgets.QMenu(self)
        # The button is right-to-left only to put its chevron on the right.
        self._menu.setLayoutDirection(QtCore.Qt.LeftToRight)
        self._menu.aboutToShow.connect(self._fill)
        self.setMenu(self._menu)
        self.refresh()

    def modified(self):
        return self._modified

    def refresh(self):
        docs, act = _open_docs()
        title = current_title(docs, act)
        doc = _active_doc()
        mod = bool(doc is not None and projects_store.is_modified(doc))
        changed = mod != self._modified or title != self.text()
        self._modified = mod
        self.setText(title)
        self.setToolTip("Project: %s%s. Click to switch projects." % (
            title, " (unsaved changes)" if mod else ""))
        self.setAccessibleDescription("Unsaved changes" if mod else "")
        t = style.tokens()
        self.setIcon(style.icon("chevron-down", t["muted"], 14))
        self.setLayoutDirection(QtCore.Qt.RightToLeft)     # chevron on the right
        if changed:
            self.update()

    def dot_rect(self):
        """Where the unsaved dot is drawn: just left of the chevron."""
        d = self.DOT
        x = self.width() - 14 - self.iconSize().width() - 8 - d
        return QtCore.QRectF(x, (self.height() - d) / 2.0, d, d)

    def paintEvent(self, ev):                          # noqa: N802
        super().paintEvent(ev)
        if not self._modified:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(style.tokens()["warn"]))
        p.drawEllipse(self.dot_rect())
        p.end()

    def _fill(self):
        self._menu.clear()
        docs, act = _open_docs()
        for kind, payload, text, checked in project_entries(
                docs, act, recent_files()):
            if kind == "sep":
                self._menu.addSeparator()
            elif kind == "header":
                a = self._menu.addAction(text.upper())
                a.setEnabled(False)
            else:
                a = self._menu.addAction(text)
                if kind == "open":
                    a.setCheckable(True)
                    a.setChecked(checked)
                    a.triggered.connect(lambda _c=False, n=payload: self._run(activate_document, n))
                elif kind == "recent":
                    a.setToolTip(payload)
                    a.triggered.connect(lambda _c=False, p=payload: self._run(_open_path, p))
                elif kind == "new":
                    a.triggered.connect(lambda _c=False: self._run(self._new))
                elif kind == "file":
                    a.triggered.connect(lambda _c=False: self._run(self._on_open_file))
        doc = _active_doc()
        acts = project_actions(doc is not None,
                               bool(doc is not None and
                                    getattr(doc, "FileName", "")))
        if acts:
            self._menu.addSeparator()
            h = self._menu.addAction("THIS PROJECT")
            h.setEnabled(False)
            for key, text, on in acts:
                a = self._menu.addAction(text)
                a.setObjectName("project-" + key)
                a.setEnabled(on)
                if key == "save":
                    # Shown in the menu, live only while the menu is open:
                    # Cmd+S everywhere else stays FreeCAD's Std_Save (two
                    # window-wide owners would make the key do nothing).
                    a.setShortcut(QtGui.QKeySequence(QtGui.QKeySequence.Save))
                    a.setShortcutContext(QtCore.Qt.WidgetShortcut)
                    a.setShortcutVisibleInContextMenu(True)
                a.triggered.connect(lambda _c=False, k=key: self._run(self.act, k))

    def _new(self):
        if self._on_new is not None:
            return self._on_new()
        return self.act("new")

    # -- the current project's actions (R361, R367, R369)
    def act(self, key, doc=None):
        """Run one project action on `doc` (default: the active one).
        Returns its result; a ProjectError is shown in words and returns
        None."""
        doc = doc if doc is not None else _active_doc()
        try:
            return getattr(self, "_do_" + key)(doc)
        except projects_store.ProjectError as exc:
            self.warn("That did not work", str(exc))
        except OSError as exc:
            self.warn("That did not work",
                      "The file could not be changed: %s." % (
                          exc.strerror or exc))
        return None

    def _do_new(self, _doc):
        def ask(d):
            return self.ask_name("New project", "Name of the new project:", d)
        return new_project_flow(self.window(), ask=ask, warn=self.warn)

    def _do_save(self, doc):
        if doc is None:
            return False
        def ask(d):
            return self.ask_name("Save project", "Name of the project:", d)
        return save_active(self.window(), ask=ask)

    def _do_rename(self, doc):
        path = getattr(doc, "FileName", "") if doc is not None else ""
        if not path:
            return None
        stem = os.path.splitext(os.path.basename(path))[0]
        name = self.ask_name("Rename project", "New name:", stem)
        if name is None or projects_store.clean_name(name) == stem:
            return None
        return projects_store.rename_project(doc, name)

    def _do_duplicate(self, doc):
        path = getattr(doc, "FileName", "") if doc is not None else ""
        if not path:
            return None
        if projects_store.is_modified(doc):
            projects_store.save(doc)
        new = projects_store.duplicate_project(doc)
        _open_path(new)
        return new

    def _do_reveal(self, doc):
        path = getattr(doc, "FileName", "") if doc is not None else ""
        if path:
            self.reveal(path)
        return path or None

    def _do_export(self, doc):
        path = getattr(doc, "FileName", "") if doc is not None else ""
        if not path:
            return None
        stem = os.path.splitext(os.path.basename(path))[0]
        start = os.path.join(os.path.expanduser("~/Desktop"),
                             stem + " (shared).FCStd")
        dest = self.ask_save_path("Export project for sharing", start)
        if not dest:
            return None
        if not dest.lower().endswith(".fcstd"):
            dest += ".FCStd"
        if os.path.exists(dest) and os.path.samefile(dest, path):
            raise projects_store.ProjectError(
                "Choose another file: the export must not replace the "
                "project itself.")
        projects_store.export_for_sharing(doc, dest)
        return dest

    def _do_trash(self, doc):
        path = getattr(doc, "FileName", "") if doc is not None else ""
        if not path:
            return None
        name = getattr(doc, "Label", "") or os.path.basename(path)
        if not self.confirm(
                "Move to Trash",
                "Move “%s” to the Trash? Its chat is deleted with "
                "it. You can get the file back from the Trash." % name,
                "Move to Trash"):
            return None
        return projects_store.trash_project(doc)

    def _run(self, fn, *args):
        if fn is None:
            return
        try:
            fn(*args)
        finally:
            QtCore.QTimer.singleShot(0, self.refresh)


# ------------------------------------------------------- save button
SAVE_PATH = ('<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 '
             '2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
             '<path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/>'
             '<path d="M7 3v4a1 1 0 0 0 1 1h7"/>')     # Lucide "save"
style.PATHS.setdefault("save", SAVE_PATH)

SAVE_QSS = """
#SaveBtn {{
    background: {track}; border: 1px solid {line}; border-radius: 18px;
}}
#SaveBtn:hover {{ background: {hover}; }}
#SaveBtn:disabled {{ background: transparent; }}
"""


class SaveButton(QtWidgets.QToolButton):
    """R362: the round Save button beside the project picker (the
    toolbars are hidden, so this is the visible Save; Cmd+S stays
    FreeCAD's). Enabled while the active project has unsaved changes or
    no file yet."""

    def __init__(self, picker=None, parent=None):
        super().__init__(parent)
        self.setObjectName("SaveBtn")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setIconSize(QtCore.QSize(16, 16))
        self.setFixedSize(36, 36)
        self.setAccessibleName("Save project")
        self._picker = picker
        self.clicked.connect(self._save)
        self.restyle()
        self.refresh()

    def restyle(self):
        self._mode = style.mode()
        self.setStyleSheet(style.qss(SAVE_QSS))
        self.setIcon(style.icon("save", style.tokens()["text"], 16))

    def refresh(self):
        if style.mode() != getattr(self, "_mode", None):
            self.restyle()              # the theme flipped
        doc = _active_doc()
        need = doc is not None and (not getattr(doc, "FileName", "")
                                    or projects_store.is_modified(doc))
        self.setEnabled(bool(need))
        self.setToolTip("Save the project (⌘S)" if need else
                        "All changes are saved")

    def _save(self):
        if self._picker is not None:
            self._picker._run(self._picker.act, "save")
        else:
            save_active(self.window())
        QtCore.QTimer.singleShot(0, self.refresh)


def picker_row(picker, save_button=None):
    """The picker and the Save button on one row (for the sidebar head).
    The Save button follows the picker's refreshes."""
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    btn = save_button or SaveButton(picker)
    lay.addWidget(picker, 1)
    lay.addWidget(btn)
    orig = picker.refresh

    def refresh():
        orig()
        try:
            btn.refresh()
        except RuntimeError:                           # deleted
            pass
    picker.refresh = refresh
    w.save_button = btn
    return w


def _open_path(path):
    """R391: see shell.open_file (FreeCADGui.open ignores .FCStd in 1.1.3)."""
    if str(path).lower().endswith(".fcstd"):
        import FreeCAD
        FreeCAD.openDocument(path)
        return
    import FreeCADGui
    FreeCADGui.open(path)
