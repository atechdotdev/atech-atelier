"""visibility - Show and hide, one click from the view bar (R701).

The view's everyday controls were spread out: Hide / Isolate / Show all /
See-through only in the right-click menu (inspect_tools), the exploded view
behind its own dialog (export_tools), and no list of the parts beside the
3D view. Show and hide puts them in one popover under its view-bar button:

    every part, ticked when shown: untick to hide it, tick to bring it back;
    picking rows selects the parts in 3D (and the 3D selection is picked
    when the popover opens), double-click a row to show only that part;
    Hide, Isolate, See-through (on the picked parts) and Show all;
    the exploded view's slider, live.

The same actions have keys (shell.SHORTCUTS): H hide, I isolate, Shift+H
show all, T see-through, E explode / put back. Nothing new is stored: the
popover drives inspect_tools and export_tools, so the brief, the hand edits
that survive a rebuild (R340) and Undo work as they did.
"""
from . import export_tools, inspect_tools, style

#: Lucide "eye" and "sliders-horizontal" (ISC, see style.PATHS).
style.PATHS.setdefault(
    "eye", '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 '
    '1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>')
style.PATHS.setdefault(
    "sliders", '<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/>'
    '<path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/>'
    '<path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>')

POPOVER_QSS = """
#AtechTool QListWidget {{
    background: {panel}; color: {text}; border: 1px solid {line}; border-radius: 10px;
    padding: 4px; outline: none;
}}
#AtechTool QListWidget::item {{ padding: 3px 4px; border-radius: 6px; }}
#AtechTool QListWidget::item:selected {{ background: {hover}; color: {text}; }}
#AtechTool QPushButton {{ padding: 0 10px; }}
"""


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("Atech visibility: %s\n" % msg)
    except Exception:                                     # noqa: BLE001
        pass


def _active_doc():
    try:
        import FreeCAD
        return FreeCAD.ActiveDocument
    except Exception:                                     # noqa: BLE001
        return None


def parts(doc):
    """The parts the list shows, in document order: inspect_tools'
    end parts (no Cut inputs, no previous build)."""
    if doc is None:
        return []
    try:
        return inspect_tools.end_parts(doc)
    except Exception as exc:                              # noqa: BLE001
        _log("parts: %r" % (exc,))
        return []


def _undoable(doc, name, fn):
    if doc is None:
        return None
    doc.openTransaction(name)
    try:
        return fn()
    finally:
        doc.commitTransaction()


def set_shown(doc, objs, on):
    """Show or hide `objs` as one undo step (a row's tick)."""
    return _undoable(doc, "Show" if on else "Hide",
                     lambda: (inspect_tools.show if on else inspect_tools.hide)(objs))


def _select(doc, objs):
    try:
        import FreeCADGui
        FreeCADGui.Selection.clearSelection()
        for o in objs:
            FreeCADGui.Selection.addSelection(doc.Name, o.Name)
    except Exception as exc:                              # noqa: BLE001
        _log("select: %r" % (exc,))


def _selected_names():
    try:
        import FreeCADGui
        return {o.Name for o in FreeCADGui.Selection.getSelection()}
    except Exception:                                     # noqa: BLE001
        return set()


def ShowHidePopover(parent=None, doc_fn=_active_doc, select_fn=None):
    """The popover. `select_fn(doc, objs)` puts the picked rows in the 3D
    selection (default: FreeCADGui.Selection); tests pass their own."""
    from PySide6 import QtCore, QtWidgets

    select_fn = select_fn or _select
    d = export_tools._tool_dialog(QtWidgets.QDialog, parent, "Show and hide")
    d.setWindowFlags(QtCore.Qt.Popup)
    d.setStyleSheet(d.styleSheet() + style.qss(POPOVER_QSS, reset=False))
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    t = QtWidgets.QLabel("Show and hide", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    sub = QtWidgets.QLabel("Untick a part to hide it. Pick parts here or in "
                           "3D for the buttons; double-click one to see only "
                           "it.", d)
    sub.setObjectName("ToolMuted")
    sub.setWordWrap(True)
    lay.addWidget(sub)

    d.list = QtWidgets.QListWidget(d)
    d.list.setAccessibleName("Parts")
    d.list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    d.list.setMinimumHeight(120)
    lay.addWidget(d.list, 1)

    row = QtWidgets.QHBoxLayout()
    row.setSpacing(6)
    d.buttons = {}
    for key, text, tip in (("hide", "Hide", "Hide the picked parts (H)"),
                           ("isolate", "Isolate", "Show only the picked parts (I)"),
                           ("see", "See-through", "Make the picked parts "
                            "see-through, or solid again (T)"),
                           ("all", "Show all", "Show every part again (Shift+H)")):
        b = QtWidgets.QPushButton(text, d)
        b.setToolTip(tip)
        b.setAccessibleName(text)
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setAutoDefault(False)
        row.addWidget(b)
        d.buttons[key] = b
    lay.addLayout(row)

    xrow = QtWidgets.QHBoxLayout()
    xl = QtWidgets.QLabel("Exploded view", d)
    xrow.addWidget(xl)
    d.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, d)
    d.slider.setRange(0, 100)
    d.slider.setAccessibleName("How far apart")
    d.slider.setToolTip("Pull the parts apart to see inside (E toggles). "
                        "Only the picture changes: a build or a save puts "
                        "every part back.")
    xrow.addWidget(d.slider, 1)
    lay.addLayout(xrow)
    keys = QtWidgets.QLabel("H hide · I isolate · T see-through "
                            "· ⇧H show all · E explode", d)
    keys.setObjectName("ToolMuted")
    lay.addWidget(keys)

    d._names = []
    d._filling = False

    def picked():
        doc = doc_fn()
        if doc is None:
            return doc, []
        objs = [doc.getObject(it.data(QtCore.Qt.UserRole))
                for it in d.list.selectedItems()]
        return doc, [o for o in objs if o is not None]

    def fill():
        d._filling = True
        try:
            doc = doc_fn()
            sel = _selected_names()
            d.list.clear()
            d._names = []
            for o in parts(doc):
                it = QtWidgets.QListWidgetItem(o.Label)
                it.setData(QtCore.Qt.UserRole, o.Name)
                it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
                it.setCheckState(QtCore.Qt.Checked if o.Visibility
                                 else QtCore.Qt.Unchecked)
                it.setToolTip("%s - tick to show, untick to hide" % o.Label)
                d.list.addItem(it)
                d._names.append(o.Name)
                if o.Name in sel:
                    it.setSelected(True)
            if not d._names:
                it = QtWidgets.QListWidgetItem(
                    "No parts yet." if doc is not None else "No document is open.")
                it.setFlags(QtCore.Qt.NoItemFlags)
                d.list.addItem(it)
            d.slider.blockSignals(True)
            d.slider.setValue(int(round(export_tools.explode_amount(doc) * 100)))
            d.slider.blockSignals(False)
            sync_buttons()
        finally:
            d._filling = False

    def sync_buttons():
        doc, objs = picked()
        for k in ("hide", "isolate", "see"):
            d.buttons[k].setEnabled(bool(objs))
        d.buttons["all"].setEnabled(doc is not None and inspect_tools.enabled(
            "Atech_ShowAll", doc, []))
        d.slider.setEnabled(doc is not None and bool(d._names))

    def ticked(it):
        if d._filling:
            return
        doc = doc_fn()
        o = doc.getObject(it.data(QtCore.Qt.UserRole)) if doc is not None else None
        if o is None:
            return
        set_shown(doc, [o], it.checkState() == QtCore.Qt.Checked)
        sync_buttons()

    def selection_changed():
        if d._filling:
            return
        doc, objs = picked()
        if doc is not None:
            select_fn(doc, objs)
        sync_buttons()

    def isolate_one(it):
        doc = doc_fn()
        o = doc.getObject(it.data(QtCore.Qt.UserRole)) if doc is not None else None
        if o is not None:
            _undoable(doc, "Isolate", lambda: inspect_tools.isolate(doc, [o]))
            fill()

    def act(key):
        doc, objs = picked()
        if doc is None:
            return
        if key == "hide":
            _undoable(doc, "Hide", lambda: inspect_tools.hide(objs))
        elif key == "isolate":
            _undoable(doc, "Isolate", lambda: inspect_tools.isolate(doc, objs))
        elif key == "see":
            _undoable(doc, "See-through", lambda: inspect_tools.toggle_see_through(objs))
        elif key == "all":
            _undoable(doc, "Show all", lambda: inspect_tools.show_all(doc))
        fill()

    def moved(v):
        export_tools.set_explode(doc_fn(), v / 100.0)

    d.list.itemChanged.connect(ticked)
    d.list.itemSelectionChanged.connect(selection_changed)
    d.list.itemDoubleClicked.connect(isolate_one)
    for k, b in d.buttons.items():
        b.clicked.connect(lambda _=False, k=k: export_tools._guard(lambda: act(k)))
    d.slider.valueChanged.connect(lambda v: export_tools._guard(lambda: moved(v)))
    d.fill, d.act, d.picked = fill, act, picked
    fill()
    d.resize(340, 380)
    return d


def show_popover(anchor, doc_fn=_active_doc):
    """Open the popover under `anchor` (a view-bar button)."""
    d = getattr(anchor, "_popover", None)
    try:
        alive = d is not None and d.parent() is not None
    except RuntimeError:
        alive = False
    if not alive:
        d = ShowHidePopover(anchor.window(), doc_fn)
        anchor._popover = d
    d.fill()
    d.move(popover_pos(anchor, d.size()))
    d.show()
    return d


def popover_pos(anchor, size, gap=6):
    """R720: where a popover of `size` opens for `anchor`: under it, or
    above it when there is no room below (the view bar sits at the bottom
    of the window, so "under" was off the screen), kept on the screen."""
    from PySide6 import QtCore, QtGui
    below = anchor.mapToGlobal(anchor.rect().bottomLeft())
    above = anchor.mapToGlobal(anchor.rect().topLeft())
    x, y = below.x(), below.y() + gap
    screen = QtGui.QGuiApplication.screenAt(below) or anchor.screen()
    if screen is None:
        return QtCore.QPoint(x, y)
    area = screen.availableGeometry()
    if y + size.height() > area.bottom() and \
            above.y() - gap - size.height() >= area.top():
        y = above.y() - gap - size.height()
    x = max(area.left(), min(x, area.right() - size.width()))
    y = max(area.top(), min(y, area.bottom() - size.height()))
    return QtCore.QPoint(x, y)


def view_bar_button(parent=None, doc_fn=_active_doc):
    """The view bar's Show and hide button (objectName VBtn, icon-only)."""
    from PySide6 import QtCore, QtWidgets
    b = QtWidgets.QPushButton("", parent)
    b.setObjectName("VBtn")
    b.setCursor(QtCore.Qt.PointingHandCursor)
    b.setToolTip("Show and hide parts, isolate, see-through, exploded view")
    b.setAccessibleName("Show and hide")
    b.setIconSize(QtCore.QSize(16, 16))
    b.setFixedWidth(34)
    b.setProperty("atech_icon", "eye")
    b.clicked.connect(lambda _=False: export_tools._guard(
        lambda: show_popover(b, doc_fn)))
    return b


# ------------------------------------------------------------ the keys
def key_hide():
    return inspect_tools.cmd_hide()


def key_isolate():
    return inspect_tools.cmd_isolate()


def key_show_all():
    return inspect_tools.cmd_show_all()


def key_see_through():
    return inspect_tools.cmd_see_through()


def key_explode():
    return export_tools.toggle_explode(_active_doc())
