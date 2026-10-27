"""manual_edit - the Edit shapes window: TinkerCAD-style hand editing (R800).

One small, non-modal tool window (the same look as Dimensions), opened from
the view bar's Edit shapes button or the R key, that follows the selection:

    SHAPES      Box, Cylinder, Sphere, Cone, Torus, Roof: a 20 mm shape set
                down beside what is there, selected, ready to size
    SIZE        W x D x H in mm, typed (Enter applies), with a lock that
                keeps the proportions (change one, the others follow).
                Works for imported STEP / STL parts too: they are scaled.
    POSITION    X, Y (footprint centre) and Elevation (the bottom), mm;
                nudge with the arrow keys (Shift: up/down) by the Step
    TURN        90 degree turns about Z, and tilts about X / Y
    SOLID/HOLE  a hole is cut out of the solids it is combined with
    Combine / Ungroup / Duplicate / Delete

Parts the agent built, and Atech hardware, say why their size is not typed
here (shape_edit.why_not) and offer Dimensions instead. All the geometry is
shape_edit's; this module is the window.
"""
from . import shape_edit as se

_OPEN = {}
NUDGE_STEPS = (0.5, 1.0, 5.0, 10.0)


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[manual_edit] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def _doc():
    try:
        import FreeCAD
        return FreeCAD.ActiveDocument
    except Exception:                                  # noqa: BLE001
        return None


def _selection():
    try:
        import FreeCADGui
        return [o for o in FreeCADGui.Selection.getSelection()
                if getattr(o, "Document", None) is _doc()]
    except Exception:                                  # noqa: BLE001
        return []


def _select(obj):
    try:
        import FreeCADGui
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(obj)
    except Exception:                                  # noqa: BLE001
        pass


def _new_doc_if_needed():
    d = _doc()
    if d is not None:
        return d
    import FreeCAD
    return FreeCAD.newDocument("Untitled")


def ShapeEditor(parent=None):
    from PySide6 import QtCore, QtWidgets
    from . import export_tools

    d = export_tools._tool_dialog(QtWidgets.QDialog, parent, "Edit shapes")
    d.setModal(False)
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(10)
    t = QtWidgets.QLabel("Edit shapes", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)

    # -- shapes palette
    pal_title = QtWidgets.QLabel("ADD A SHAPE", d)
    pal_title.setObjectName("ToolMuted")
    lay.addWidget(pal_title)
    pal = QtWidgets.QGridLayout()
    pal.setSpacing(6)
    d.shape_buttons = {}
    for i, k in enumerate(se.SHAPE_ORDER):
        b = QtWidgets.QPushButton(se.SHAPES[k][1], d)
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setToolTip("Add a 20 mm %s beside the model" % se.SHAPES[k][1].lower())
        b.clicked.connect(lambda _=False, kk=k: add(kk))
        pal.addWidget(b, i // 3, i % 3)
        d.shape_buttons[k] = b
    lay.addLayout(pal)

    # -- selected part
    d.name = QtWidgets.QLabel("", d)
    d.name.setObjectName("ToolTitle")
    lay.addWidget(d.name)
    d.note = QtWidgets.QLabel("", d)
    d.note.setObjectName("ToolMuted")
    d.note.setWordWrap(True)
    lay.addWidget(d.note)

    form = QtWidgets.QGridLayout()
    form.setHorizontalSpacing(8)
    form.setVerticalSpacing(6)

    def spin(lo, hi, tip):
        b = QtWidgets.QDoubleSpinBox(d)
        b.setRange(lo, hi)
        b.setDecimals(2)
        b.setSuffix(" mm")
        b.setKeyboardTracking(False)          # apply on Enter / focus out
        b.setToolTip(tip)
        b.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        return b

    row = 0
    size_title = QtWidgets.QLabel("SIZE", d)
    size_title.setObjectName("ToolMuted")
    form.addWidget(size_title, row, 0, 1, 4)
    row += 1
    d.size = [spin(se.MIN_MM, 10000, "Width (X)"), spin(se.MIN_MM, 10000, "Depth (Y)"),
              spin(se.MIN_MM, 10000, "Height (Z)")]
    srow = QtWidgets.QHBoxLayout()
    for lab, box in zip(("W", "D", "H"), d.size):
        l = QtWidgets.QLabel(lab, d)
        l.setObjectName("ToolMuted")
        srow.addWidget(l)
        srow.addWidget(box, 1)
    d.lock = QtWidgets.QCheckBox("Keep proportions", d)
    d.lock.setToolTip("Change one size and the other two follow")
    form.addLayout(srow, row, 0, 1, 4)
    row += 1
    form.addWidget(d.lock, row, 0, 1, 4)
    row += 1

    pos_title = QtWidgets.QLabel("POSITION", d)
    pos_title.setObjectName("ToolMuted")
    form.addWidget(pos_title, row, 0, 1, 4)
    row += 1
    d.pos = [spin(-100000, 100000, "X: the centre of its footprint"),
             spin(-100000, 100000, "Y: the centre of its footprint"),
             spin(-100000, 100000, "Elevation: the height of its bottom")]
    prow = QtWidgets.QHBoxLayout()
    for lab, box in zip(("X", "Y", "Elev."), d.pos):
        l = QtWidgets.QLabel(lab, d)
        l.setObjectName("ToolMuted")
        prow.addWidget(l)
        prow.addWidget(box, 1)
    form.addLayout(prow, row, 0, 1, 4)
    row += 1
    step_row = QtWidgets.QHBoxLayout()
    sl = QtWidgets.QLabel("Arrow-key step", d)
    sl.setObjectName("ToolMuted")
    d.step = QtWidgets.QComboBox(d)
    for s in NUDGE_STEPS:
        d.step.addItem("%s mm" % se.fmt_mm(s), s)
    d.step.setCurrentIndex(1)
    step_row.addWidget(sl)
    step_row.addWidget(d.step)
    step_row.addStretch(1)
    form.addLayout(step_row, row, 0, 1, 4)
    row += 1
    lay.addLayout(form)

    turn_title = QtWidgets.QLabel("TURN", d)
    turn_title.setObjectName("ToolMuted")
    lay.addWidget(turn_title)
    trow = QtWidgets.QHBoxLayout()
    d.turn_buttons = []
    for text, axis, deg, tip in (("↺ 90°", "z", 90, "Turn left about Z"),
                                 ("↻ 90°", "z", -90, "Turn right about Z"),
                                 ("Tilt X", "x", 90, "Tilt 90° about X"),
                                 ("Tilt Y", "y", 90, "Tilt 90° about Y")):
        b = QtWidgets.QPushButton(text, d)
        b.setToolTip(tip)
        b.clicked.connect(lambda _=False, a=axis, g=deg: act(lambda o: se.turn(o, a, g)))
        trow.addWidget(b)
        d.turn_buttons.append(b)
    lay.addLayout(trow)

    hrow = QtWidgets.QHBoxLayout()
    d.btn_solid = QtWidgets.QPushButton("Solid", d)
    d.btn_hole = QtWidgets.QPushButton("Hole", d)
    for b in (d.btn_solid, d.btn_hole):
        b.setCheckable(True)
        hrow.addWidget(b)
    d.btn_solid.setToolTip("A solid part")
    d.btn_hole.setToolTip("A hole: cut out of the solids it is combined with")
    d.btn_solid.clicked.connect(lambda _=False: act(lambda o: se.set_hole(o, False)))
    d.btn_hole.clicked.connect(lambda _=False: act(lambda o: se.set_hole(o, True)))
    lay.addLayout(hrow)

    brow = QtWidgets.QHBoxLayout()
    d.btn_combine = QtWidgets.QPushButton("Combine", d)
    d.btn_combine.setToolTip("Fuse the selected solids and cut the holes out of them")
    d.btn_ungroup = QtWidgets.QPushButton("Ungroup", d)
    d.btn_dup = QtWidgets.QPushButton("Duplicate", d)
    d.btn_del = QtWidgets.QPushButton("Delete", d)
    d.btn_dims = QtWidgets.QPushButton("Dimensions…", d)
    d.btn_dims.setToolTip("Change the numbers the agent built this model from")
    for b in (d.btn_combine, d.btn_ungroup, d.btn_dup, d.btn_del, d.btn_dims):
        brow.addWidget(b)
    lay.addLayout(brow)
    d.status = QtWidgets.QLabel("", d)
    d.status.setObjectName("ToolMuted")
    d.status.setWordWrap(True)
    lay.addWidget(d.status)
    lay.addStretch(1)

    state = {"obj": None, "loading": False, "size": None}

    def say(text):
        d.status.setText(text)

    def run(fn, what):
        """Run an edit; a refusal is said in the window, never raised."""
        try:
            out = fn()
            say("")
            return out
        except se.EditRefused as exc:
            say(str(exc))
        except Exception as exc:                       # noqa: BLE001
            _log("%s: %r" % (what, exc))
            say("Could not %s: %s" % (what, exc))
        return None

    def act(fn):
        o = state["obj"]
        if o is None:
            say("Select a part first.")
            return
        out = run(lambda: fn(o), "change it")
        if out is not None and out is not o:
            _select(out)
        load()

    def add(k):
        doc = _new_doc_if_needed()
        o = run(lambda: se.add_shape(doc, k), "add the shape")
        if o is not None:
            _select(o)
            try:
                from . import viewport
                viewport.fit_all()
            except Exception:                          # noqa: BLE001
                pass
        load()

    def apply_size(axis):
        o = state["obj"]
        if state["loading"] or o is None or not se.can_resize(o):
            return
        want = [b.value() for b in d.size]
        old = state["size"] or tuple(want)
        if d.lock.isChecked():
            want = list(se.same_ratio(old, axis, want[axis]))
        if all(abs(a - b) < 1e-6 for a, b in zip(want, old)):
            return
        was = se.SHAPES.get(se.kind(o) or "", ("", "shape", None))[1].lower()
        out = run(lambda: se.resize(o, *want), "resize it")
        if out is not None and out is not o:
            _select(out)
            load()
            say("Now a plain solid of exactly this size: a %s cannot have "
                "different width and depth." % was)
            return
        load()

    def apply_pos(_axis):
        o = state["obj"]
        if state["loading"] or o is None or not se.can_move(o):
            return
        x, y, z = (b.value() for b in d.pos)
        run(lambda: se.move_to(o, x, y, z), "move it")
        load()

    for i, b in enumerate(d.size):
        b.valueChanged.connect(lambda _v, ax=i: apply_size(ax))
    for i, b in enumerate(d.pos):
        b.valueChanged.connect(lambda _v, ax=i: apply_pos(ax))

    def combine():
        doc = _doc()
        sel = _selection()
        g = run(lambda: se.combine(doc, sel), "combine")
        if g is not None:
            _select(g)
        load()

    def ungroup():
        o = state["obj"]
        parts = run(lambda: se.ungroup(o), "ungroup")
        if parts:
            try:
                import FreeCADGui
                FreeCADGui.Selection.clearSelection()
                for p in parts:
                    FreeCADGui.Selection.addSelection(p)
            except Exception:                          # noqa: BLE001
                pass
        load()

    def duplicate():
        o = state["obj"]
        n = run(lambda: se.duplicate(o), "duplicate")
        if n is not None:
            _select(n)
        load()

    def delete():
        o = state["obj"]
        if o is None:
            return
        run(lambda: se.remove(o), "delete")
        load()

    def dims():
        try:
            from . import dimensions
            dimensions.open_dialog(d.parent())
        except Exception as exc:                       # noqa: BLE001
            say("Dimensions is not available here: %s" % exc)

    d.btn_combine.clicked.connect(lambda _=False: combine())
    d.btn_ungroup.clicked.connect(lambda _=False: ungroup())
    d.btn_dup.clicked.connect(lambda _=False: duplicate())
    d.btn_del.clicked.connect(lambda _=False: delete())
    d.btn_dims.clicked.connect(lambda _=False: dims())

    def load():
        """Show the selected part (the first one) and enable what it takes."""
        sel = _selection()
        o = sel[0] if sel else None
        try:
            if o is not None and se.kind(o) is None:
                o = None
        except Exception:                              # noqa: BLE001
            o = None
        state["obj"] = o
        state["loading"] = True
        try:
            k = se.kind(o) if o is not None else None
            if o is None:
                d.name.setText("No part selected")
                d.note.setText("Click a part in the 3D view, or add a shape above.")
            else:
                d.name.setText(o.Label)
                d.note.setText(se.why_not(o) or
                               ("%d parts selected; sizes show the first. Combine "
                                "makes them one." % len(sel) if len(sel) > 1 else
                                "Type a size or position and press Enter."))
            sizable = o is not None and se.can_resize(o) and k != "group"
            movable = o is not None and se.can_move(o)
            for b in d.size:
                b.setEnabled(sizable)
            for b in d.pos:
                b.setEnabled(movable)
            d.lock.setEnabled(sizable)
            for b in d.turn_buttons:
                b.setEnabled(movable)
            d.btn_solid.setEnabled(sizable or k == "group")
            d.btn_hole.setEnabled(sizable or k == "group")
            d.btn_dup.setEnabled(movable and k != "agent")
            d.btn_del.setEnabled(o is not None and k != "hardware")
            d.btn_ungroup.setEnabled(k == "group")
            d.btn_combine.setEnabled(len(sel) >= 2)
            d.btn_dims.setVisible(k == "agent")
            hole = o is not None and se.is_hole(o)
            d.btn_hole.setChecked(hole)
            d.btn_solid.setChecked(o is not None and not hole)
            if o is not None:
                sz = se.size(o)
                state["size"] = sz
                for b, v in zip(d.size, sz):
                    b.setValue(v)
                for b, v in zip(d.pos, se.position(o)):
                    b.setValue(v)
            else:
                state["size"] = None
        except Exception as exc:                       # noqa: BLE001
            _log("load: %r" % (exc,))
        finally:
            state["loading"] = False

    d.load = load

    def nudge(dx, dy, dz):
        o = state["obj"]
        if o is None or not se.can_move(o):
            return
        s = float(d.step.currentData() or 1.0)
        run(lambda: se.nudge(o, dx * s, dy * s, dz * s), "move it")
        load()

    def key_press(ev, _orig=d.keyPressEvent):
        k, mod = ev.key(), ev.modifiers()
        focus = QtWidgets.QApplication.focusWidget()
        typing = isinstance(focus, (QtWidgets.QAbstractSpinBox, QtWidgets.QLineEdit))
        if not typing and k in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right,
                                QtCore.Qt.Key_Up, QtCore.Qt.Key_Down):
            up = bool(mod & QtCore.Qt.ShiftModifier)
            m = {QtCore.Qt.Key_Left: (-1, 0, 0), QtCore.Qt.Key_Right: (1, 0, 0),
                 QtCore.Qt.Key_Up: (0, 0, 1) if up else (0, 1, 0),
                 QtCore.Qt.Key_Down: (0, 0, -1) if up else (0, -1, 0)}[k]
            nudge(*m)
            return
        _orig(ev)
    d.keyPressEvent = key_press

    # Follow the selection while the window is open.
    class _Sel(object):
        def _any(self, *_a):
            QtCore.QTimer.singleShot(0, load)
        addSelection = removeSelection = setSelection = clearSelection = _any

    obs = _Sel()
    try:
        import FreeCADGui
        FreeCADGui.Selection.addObserver(obs)
    except Exception as exc:                           # noqa: BLE001
        _log("selection observer: %r" % (exc,))

    def finished(_r=0):
        try:
            import FreeCADGui
            FreeCADGui.Selection.removeObserver(obs)
        except Exception:                              # noqa: BLE001
            pass
        _OPEN.pop("dlg", None)
    d.finished.connect(finished)
    d.destroyed.connect(lambda *_a: finished())
    d.resize(420, 560)
    load()
    return d


def open_editor(parent=None):
    """One Edit shapes window, brought to the front when already open."""
    from PySide6 import QtWidgets
    if parent is None:
        try:
            from . import shell
            parent = shell._mw_or_none()
        except Exception:                              # noqa: BLE001
            parent = None
    d = _OPEN.get("dlg")
    try:
        alive = d is not None and d.isVisible()
    except RuntimeError:
        alive = False
    if alive:
        d.load()
    else:
        d = ShapeEditor(parent or QtWidgets.QApplication.activeWindow())
        _OPEN["dlg"] = d
        d.show()
    d.raise_()
    d.activateWindow()
    return d


def view_bar_button(parent=None):
    """The view bar's Edit shapes button (objectName VBtn, icon-only)."""
    from PySide6 import QtCore, QtWidgets
    from . import export_tools
    b = QtWidgets.QPushButton("", parent)
    b.setObjectName("VBtn")
    b.setCursor(QtCore.Qt.PointingHandCursor)
    b.setToolTip("Edit shapes: add shapes, type exact sizes, holes (R)")
    b.setAccessibleName("Edit shapes")
    b.setIconSize(QtCore.QSize(16, 16))
    b.setFixedWidth(34)
    b.setProperty("atech_icon", "cube")
    b.clicked.connect(lambda _=False: export_tools._guard(
        lambda: open_editor(b.window())))
    return b
