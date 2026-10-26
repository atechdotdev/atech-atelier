"""dimensions - change the model's numbers by hand (R700).

The agent describes every model as a script (model.py) whose parameter
block at the top holds every dimension. This window lists those numbers
with the script's own comments as their descriptions, under the script's
own section headings, so a hand edit is "type 80 where it says 60", not
"find line 9 of a Python file":

    a box per dimension (mm, degrees, or a plain count), changed ones marked;
    Rebuild (Enter) writes only those numbers into model.py and builds it
    as a new build: one undo step, "Go back to this build" on its card;
    Reset puts the boxes back to what the script holds;
    Open the script... opens model.py in the system editor for anything
    more; Rebuild then builds what was saved there.

The agent's next brief lists the values the user set (params.brief_lines),
so it keeps them instead of "fixing" them back.

The work is the chat panel's (AgentPanel.dimensions_target /
apply_dimensions): it owns the chat workspace and the build. `panel_fn`
returns that panel; tests pass a fake.
"""
from . import export_tools, params
from . import visibility  # noqa: F401  (the "sliders" icon)

FILTER_FROM = 12          # a filter box when the script has more numbers


def _panel():
    from . import shell
    return shell.chat_panel()


def _step(value, is_int):
    if is_int:
        return 1
    a = abs(float(value))
    return 1.0 if a >= 20 else 0.5 if a >= 5 else 0.1 if a >= 1 else 0.05


def _decimals(value):
    s = params.fmt(value, False)
    return max(2, min(4, len(s.split(".")[1]) if "." in s else 0))


def DimensionsDialog(parent=None, panel_fn=_panel):
    from PySide6 import QtCore, QtGui, QtWidgets

    d = export_tools._tool_dialog(QtWidgets.QDialog, parent, "Dimensions")
    d.setModal(False)
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(8)
    t = QtWidgets.QLabel("Dimensions", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    sub = QtWidgets.QLabel("The numbers this model is built from. Change any "
                           "of them and press Rebuild: the agent keeps your "
                           "values.", d)
    sub.setObjectName("ToolMuted")
    sub.setWordWrap(True)
    lay.addWidget(sub)
    d.filter = QtWidgets.QLineEdit(d)
    d.filter.setPlaceholderText("Find a dimension")
    d.filter.setAccessibleName("Find a dimension")
    d.filter.setClearButtonEnabled(True)
    lay.addWidget(d.filter)
    d.scroll = QtWidgets.QScrollArea(d)
    d.scroll.setWidgetResizable(True)
    d.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
    lay.addWidget(d.scroll, 1)
    d.status = QtWidgets.QLabel("", d)
    d.status.setObjectName("ToolMuted")
    d.status.setWordWrap(True)
    lay.addWidget(d.status)
    row = QtWidgets.QHBoxLayout()
    d.btn_script = QtWidgets.QPushButton("Open the script...", d)
    d.btn_script.setToolTip("Open model.py in your text editor for any other "
                            "change; save it, then press Rebuild here")
    d.btn_script.setAutoDefault(False)
    row.addWidget(d.btn_script)
    row.addStretch(1)
    d.btn_reset = QtWidgets.QPushButton("Reset", d)
    d.btn_reset.setToolTip("Put the boxes back to what the script holds")
    d.btn_reset.setAutoDefault(False)
    row.addWidget(d.btn_reset)
    d.btn_apply = QtWidgets.QPushButton("Rebuild", d)
    d.btn_apply.setObjectName("ToolPrimary")
    d.btn_apply.setAccessibleName("Rebuild")
    d.btn_apply.setDefault(True)
    row.addWidget(d.btn_apply)
    lay.addLayout(row)

    d.boxes = {}          # name -> spin box
    d.rows = {}           # name -> (widgets of the row)
    d.params = []
    d.path = None

    def say(text):
        d.status.setText(text or "")

    def changes():
        out = {}
        for p in d.params:
            box = d.boxes.get(p.name)
            if box is None:
                continue
            v = box.value()
            if params.fmt(v, p.is_int) != params.fmt(p.value, p.is_int):
                out[p.name] = int(v) if p.is_int else float(v)
        return out

    def mark():
        ch = changes()
        for p in d.params:
            name_lbl = d.rows[p.name][0]
            f = name_lbl.font()
            f.setBold(p.name in ch)
            name_lbl.setFont(f)
            name_lbl.setText(("● " if p.name in ch else "") + p.name)
        d.btn_reset.setEnabled(bool(ch))
        n = len(ch)
        d.btn_apply.setText("Rebuild" if not n else "Rebuild (%d change%s)"
                            % (n, "" if n == 1 else "s"))

    def load():
        target = panel_fn().dimensions_target()
        d.params = list(target.get("params") or [])
        d.path = target.get("path")
        d.boxes, d.rows = {}, {}
        body = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(body)
        grid.setContentsMargins(0, 4, 4, 4)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)
        r, section = 0, None
        for p in d.params:
            if p.section and p.section != section:
                h = QtWidgets.QLabel(p.section.upper(), body)
                h.setObjectName("ToolMuted")
                grid.addWidget(h, r, 0, 1, 3)
                r += 1
            section = p.section
            name = QtWidgets.QLabel(p.name, body)
            desc = QtWidgets.QLabel(p.comment, body)
            desc.setObjectName("ToolMuted")
            desc.setWordWrap(True)
            desc.setToolTip("model.py line %d" % p.line)
            if p.is_int:
                box = QtWidgets.QSpinBox(body)
                box.setRange(min(-100000, int(p.value)), max(100000, int(p.value)))
            else:
                box = QtWidgets.QDoubleSpinBox(body)
                box.setDecimals(_decimals(p.value))
                box.setRange(min(-100000.0, p.value), max(100000.0, p.value))
            box.setSingleStep(_step(p.value, p.is_int))
            box.setValue(p.value)
            box.setKeyboardTracking(False)
            box.setSuffix({"mm": " mm", "deg": "°"}.get(p.unit, ""))
            box.setAccessibleName("%s %s" % (p.name, p.comment)
                                  if p.comment else p.name)
            box.setMinimumWidth(110)
            box.valueChanged.connect(lambda _v: mark())
            grid.addWidget(name, r, 0)
            grid.addWidget(desc, r, 1)
            grid.addWidget(box, r, 2)
            d.boxes[p.name] = box
            d.rows[p.name] = (name, desc, box)
            r += 1
        grid.setRowStretch(r, 1)
        d.scroll.setWidget(body)
        d.filter.setVisible(len(d.params) > FILTER_FROM)
        d.btn_apply.setEnabled(bool(d.params) or d.path is not None)
        d.btn_script.setEnabled(d.path is not None)
        say("" if d.params else target.get("why", ""))
        mark()
        apply_filter(d.filter.text())

    def apply_filter(text):
        text = (text or "").strip().lower()
        for p in d.params:
            hit = not text or text in p.name.lower() or text in p.comment.lower() \
                or text in p.section.lower()
            for w in d.rows[p.name]:
                w.setVisible(hit)

    def rebuild():
        d.btn_apply.setEnabled(False)

        def done(ok):
            try:
                load()
                say("Rebuilt." if ok else "Rebuilt, with problems: see the chat.")
            except RuntimeError:        # the window was closed meanwhile
                pass
        started, msg = panel_fn().apply_dimensions(changes(), then=done)
        say(msg)
        if not started:
            d.btn_apply.setEnabled(True)
        return started

    def open_script():
        if d.path:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(d.path))
            say("Save the script in your editor, then press Rebuild.")

    d.filter.textChanged.connect(apply_filter)
    d.btn_apply.clicked.connect(lambda _=False: export_tools._guard(rebuild))
    d.btn_reset.clicked.connect(lambda _=False: export_tools._guard(load))
    d.btn_script.clicked.connect(lambda _=False: export_tools._guard(open_script))
    d.load, d.changes, d.rebuild = load, changes, rebuild
    load()
    d.resize(520, 520)
    return d


def open_dialog(parent=None, panel_fn=_panel):
    """One Dimensions window, brought back to the front (and reloaded)
    when it is already open."""
    from PySide6 import QtWidgets
    if parent is None:
        try:
            from . import shell
            parent = shell._mw_or_none()
        except Exception:                                 # noqa: BLE001
            parent = None
    d = _OPEN.get("dlg")
    try:
        alive = d is not None and d.isVisible()
    except RuntimeError:
        alive = False
    if alive:
        d.load()
    else:
        d = DimensionsDialog(parent or QtWidgets.QApplication.activeWindow(),
                             panel_fn)
        _OPEN["dlg"] = d
    d.show()
    d.raise_()
    d.activateWindow()
    return d


_OPEN = {}


def view_bar_button(parent=None):
    """The view bar's Dimensions button (objectName VBtn, icon-only)."""
    from PySide6 import QtCore, QtWidgets
    b = QtWidgets.QPushButton("", parent)
    b.setObjectName("VBtn")
    b.setCursor(QtCore.Qt.PointingHandCursor)
    b.setToolTip("Dimensions: change the model's numbers by hand (D)")
    b.setAccessibleName("Dimensions")
    b.setIconSize(QtCore.QSize(16, 16))
    b.setFixedWidth(34)
    b.setProperty("atech_icon", "sliders")
    b.clicked.connect(lambda _=False: export_tools._guard(
        lambda: open_dialog(b.window())))
    return b

