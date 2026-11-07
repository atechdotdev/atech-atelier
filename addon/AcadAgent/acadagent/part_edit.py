"""part_edit - the Edit part window: granular edits on one part (R885).

Edit shapes (manual_edit, R) sizes and places whole parts. Edit part (F)
changes a part's own faces and edges, the way a CAD file brought in from
elsewhere needs: click a face or edges in the 3D view, then

    FACE      Push / pull it by a distance (out adds, in cuts); drill a
              hole where it was clicked (diameter, depth or through)
    EDGES     Fillet or chamfer the selected edges (a selected face: all
              its edges)
    PART      Hollow it (the selected faces are left open), mirror, or
              split it in half on X / Y / Z
    EDITS     every edit made to it, in order: undo the last, remove any
              one (the later ones are made again without it), or go back
              to the part as it was brought in
    SOURCE    the file, the link, who made it and its licence; and "Let the
              design agent edit it"

A mesh (STL, 3MF, OBJ) is converted to a solid first; a TinkerCAD shape is
made a plain solid. The geometry is part_ops'; this module is the window.
"""
from . import part_ops as po
from . import shape_edit as se

_OPEN = {}


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[part_edit] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def _doc():
    try:
        import FreeCAD
        return FreeCAD.ActiveDocument
    except Exception:                                  # noqa: BLE001
        return None


def picked():
    """(object, [face numbers], [edge numbers], picked point or None) of
    the 3D view's selection: the first object and its sub-elements."""
    try:
        import FreeCADGui
        sel = [s for s in FreeCADGui.Selection.getSelectionEx()
               if getattr(s.Object, "Document", None) is _doc()]
    except Exception:                                  # noqa: BLE001
        return None, [], [], None
    if not sel:
        return None, [], [], None
    s = sel[0]
    faces, edges = parse_subs(getattr(s, "SubElementNames", ()) or ())
    pts = list(getattr(s, "PickedPoints", ()) or ())
    return s.Object, faces, edges, (pts[-1] if pts else None)


def parse_subs(names):
    """("Face3", "Edge5", "Edge7") -> ([3], [5, 7])."""
    faces, edges = [], []
    for n in names:
        n = str(n).rsplit(".", 1)[-1]
        for prefix, out in (("Face", faces), ("Edge", edges)):
            if n.startswith(prefix) and n[len(prefix):].isdigit():
                out.append(int(n[len(prefix):]))
    return faces, edges


def _vec_list(p):
    return [float(p.x), float(p.y), float(p.z)] if p is not None else None


def PartEditor(parent=None):
    from PySide6 import QtCore, QtWidgets
    from . import design_import as di
    from . import export_tools

    d = export_tools._tool_dialog(QtWidgets.QDialog, parent, "Edit part")
    d.setModal(False)
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(8)
    t = QtWidgets.QLabel("Edit part", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    d.name = QtWidgets.QLabel("", d)
    d.name.setObjectName("ToolTitle")
    lay.addWidget(d.name)
    d.note = QtWidgets.QLabel("", d)
    d.note.setObjectName("ToolMuted")
    d.note.setWordWrap(True)
    lay.addWidget(d.note)
    d.btn_convert = QtWidgets.QPushButton("Convert to solid", d)
    d.btn_convert.setToolTip("Turn the mesh's triangles into a solid with "
                             "faces you can pick")
    lay.addWidget(d.btn_convert)

    def title(text):
        lab = QtWidgets.QLabel(text, d)
        lab.setObjectName("ToolMuted")
        lay.addWidget(lab)
        return lab

    def spin(lo, hi, val, tip, suffix=" mm"):
        b = QtWidgets.QDoubleSpinBox(d)
        b.setRange(lo, hi)
        b.setDecimals(2)
        b.setValue(val)
        b.setSuffix(suffix)
        b.setToolTip(tip)
        b.setAccessibleName(tip)
        return b

    def row(*widgets):
        r = QtWidgets.QHBoxLayout()
        for w in widgets:
            if isinstance(w, str):
                lab = QtWidgets.QLabel(w, d)
                lab.setObjectName("ToolMuted")
                r.addWidget(lab)
            else:
                r.addWidget(w)
        r.addStretch(1)
        lay.addLayout(r)
        return r

    d.t_face = title("FACE: click one in the 3D view")
    d.pull = spin(-1000, 1000, 2.0, "How far: + pulls out, - pushes in")
    d.btn_pull = QtWidgets.QPushButton("Push / pull", d)
    row(d.pull, d.btn_pull)
    d.hole_d = spin(0.1, 1000, 3.0, "Hole diameter")
    d.hole_depth = spin(0.1, 1000, 5.0, "Hole depth")
    d.through = QtWidgets.QCheckBox("Through", d)
    d.through.setChecked(True)
    d.btn_hole = QtWidgets.QPushButton("Drill hole", d)
    d.btn_hole.setToolTip("A hole into the face, where you clicked it")
    row("⌀", d.hole_d, d.through, d.hole_depth, d.btn_hole)

    d.t_edges = title("EDGES: Cmd/Ctrl-click to pick several")
    d.round = spin(0.01, 500, 1.0, "Fillet radius or chamfer size")
    d.btn_fillet = QtWidgets.QPushButton("Fillet", d)
    d.btn_chamfer = QtWidgets.QPushButton("Chamfer", d)
    row(d.round, d.btn_fillet, d.btn_chamfer)

    title("PART")
    d.wall = spin(0.1, 100, 2.0, "Wall thickness")
    d.btn_hollow = QtWidgets.QPushButton("Hollow", d)
    d.btn_hollow.setToolTip("Hollow it out; the selected faces are left open")
    row(d.wall, d.btn_hollow)
    d.btn_mirror = {}
    d.btn_split = {}
    mr = []
    for ax in ("x", "y", "z"):
        b = QtWidgets.QPushButton("Mirror %s" % ax.upper(), d)
        b.setToolTip("Flip the part about its own centre, across %s" % ax.upper())
        d.btn_mirror[ax] = b
        mr.append(b)
    row(*mr)
    d.keep = QtWidgets.QComboBox(d)
    d.keep.addItem("keep below", "below")
    d.keep.addItem("keep above", "above")
    sr = []
    for ax in ("x", "y", "z"):
        b = QtWidgets.QPushButton("Split %s" % ax.upper(), d)
        b.setToolTip("Cut the part in half across %s, through its middle" % ax.upper())
        d.btn_split[ax] = b
        sr.append(b)
    row(*(sr + [d.keep]))

    title("EDITS")
    d.steps = QtWidgets.QListWidget(d)
    d.steps.setMaximumHeight(110)
    d.steps.setAccessibleName("Edits made to this part")
    lay.addWidget(d.steps)
    d.btn_undo = QtWidgets.QPushButton("Undo last", d)
    d.btn_remove = QtWidgets.QPushButton("Remove", d)
    d.btn_remove.setToolTip("Take the selected edit out; the later ones are "
                            "made again without it")
    d.btn_reset = QtWidgets.QPushButton("Back to original", d)
    row(d.btn_undo, d.btn_remove, d.btn_reset)

    title("SOURCE")
    d.source = QtWidgets.QLabel("", d)
    d.source.setObjectName("ToolMuted")
    d.source.setWordWrap(True)
    d.source.setOpenExternalLinks(True)
    lay.addWidget(d.source)
    d.btn_source = QtWidgets.QPushButton("Edit source…", d)
    d.agent = QtWidgets.QCheckBox("Let the design agent edit it", d)
    d.agent.setToolTip("Ask in the chat (\"make the tabs 2 mm thicker\"): the "
                       "agent's changes come in as edits here, each one undoable")
    row(d.agent, d.btn_source)

    d.status = QtWidgets.QLabel("", d)
    d.status.setObjectName("ToolMuted")
    d.status.setWordWrap(True)
    lay.addWidget(d.status)
    lay.addStretch(1)
    for b in d.findChildren(QtWidgets.QPushButton):
        b.setAutoDefault(False)
        b.setDefault(False)

    state = {"obj": None, "faces": [], "edges": [], "point": None,
             "loading": False}

    def say(text):
        d.status.setText(text)

    def run(fn, what):
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

    def reselect(o):
        try:
            import FreeCADGui
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.Selection.addSelection(o)
        except Exception:                              # noqa: BLE001
            pass

    def edit(step, what):
        o = state["obj"]
        if o is None:
            say("Select a part first.")
            return
        if run(lambda: po.apply(o, step, frame="world"), what) is not None:
            reselect(o)
        load()

    def one_face():
        if len(state["faces"]) != 1:
            say("Click one face of the part first.")
            return None
        return state["faces"][0]

    def pull():
        f = one_face()
        if f is not None:
            edit({"op": "push_pull", "face": f, "distance": d.pull.value()},
                 "push or pull it")

    def hole():
        f = one_face()
        if f is None:
            return
        st = {"op": "hole", "face": f, "diameter": d.hole_d.value(),
              "depth": None if d.through.isChecked() else d.hole_depth.value()}
        if state["point"] is not None:
            st["at"] = _vec_list(state["point"])
        edit(st, "drill the hole")

    def edges_step(op):
        key = "radius" if op == "fillet" else "size"
        if state["edges"]:
            ref = list(state["edges"])
        elif len(state["faces"]) == 1:
            ref = "face:%d" % state["faces"][0]
        else:
            say("Click the edges (or one face) to %s first." % op)
            return
        edit({"op": op, "edges": ref, key: d.round.value()}, op)

    def hollow():
        edit({"op": "hollow", "thickness": d.wall.value(),
              "open": list(state["faces"])}, "hollow it")

    def convert():
        o = state["obj"]
        notes = []
        new = run(lambda: po.make_editable(o, notes), "convert it")
        if new is not None:
            reselect(new)
            load()
            say("Now a solid with %d faces%s." % (
                len(new.Shape.Faces), ("; " + notes[0]) if notes else ""))
            return
        load()

    def history(fn, what):
        o = state["obj"]
        if o is not None and run(lambda: fn(o), what) is not None:
            reselect(o)
        load()

    def remove():
        i = d.steps.currentRow()
        if i < 0:
            say("Pick the edit to remove in the list.")
            return
        history(lambda o: po.remove_step(o, i), "remove that edit")

    def set_agent(on):
        o = state["obj"]
        if state["loading"] or o is None:
            return
        run(lambda: po.set_agent_editable(o, on), "change that")
        say("The agent may now edit %s when you ask in the chat." % o.Label
            if on else "The agent designs around %s again." % o.Label)

    def edit_source():
        o = state["obj"]
        if o is None:
            return
        s = di.source(o)
        dlg = QtWidgets.QDialog(d)
        dlg.setWindowTitle("Source of %s" % o.Label)
        form = QtWidgets.QFormLayout(dlg)
        url = QtWidgets.QLineEdit(s["url"], dlg)
        author = QtWidgets.QLineEdit(s["author"], dlg)
        lic = QtWidgets.QComboBox(dlg)
        for k in di.LICENCE_ORDER:
            lic.addItem(di.LICENCES[k][0], k)
        lic.setCurrentIndex(max(0, list(di.LICENCE_ORDER).index(s["licence"])
                                if s["licence"] in di.LICENCE_ORDER else 0))
        form.addRow("Found at", url)
        form.addRow("Made by", author)
        form.addRow("Licence", lic)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                        | QtWidgets.QDialogButtonBox.Cancel, dlg)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            run(lambda: di.set_source(o, url.text(), author.text(),
                                      lic.currentData()), "save the source")
            load()

    d.btn_pull.clicked.connect(lambda _=False: pull())
    d.btn_hole.clicked.connect(lambda _=False: hole())
    d.btn_fillet.clicked.connect(lambda _=False: edges_step("fillet"))
    d.btn_chamfer.clicked.connect(lambda _=False: edges_step("chamfer"))
    d.btn_hollow.clicked.connect(lambda _=False: hollow())
    for ax, b in d.btn_mirror.items():
        b.clicked.connect(lambda _=False, a=ax: edit(
            {"op": "mirror", "plane": a}, "mirror it"))
    for ax, b in d.btn_split.items():
        b.clicked.connect(lambda _=False, a=ax: edit(
            {"op": "split", "plane": a, "keep": d.keep.currentData()}, "split it"))
    d.btn_convert.clicked.connect(lambda _=False: convert())
    d.btn_undo.clicked.connect(lambda _=False: history(po.undo_step, "undo"))
    d.btn_remove.clicked.connect(lambda _=False: remove())
    d.btn_reset.clicked.connect(lambda _=False: history(po.reset, "go back"))
    d.agent.toggled.connect(set_agent)
    d.btn_source.clicked.connect(lambda _=False: edit_source())
    d.through.toggled.connect(lambda on: d.hole_depth.setEnabled(not on))
    d.hole_depth.setEnabled(False)

    def load():
        o, faces, edges, pt = picked()
        state.update(obj=o if (o is not None and se.kind(o) is not None) else None,
                     faces=faces, edges=edges, point=pt)
        o = state["obj"]
        state["loading"] = True
        try:
            editable = o is not None and po.can_edit(o)
            k = se.kind(o) if o is not None else None
            if o is None:
                d.name.setText("No part selected")
                d.note.setText("Click a face or an edge of a part in the 3D "
                               "view. To bring in a part of your own: Add file "
                               "to design.")
            else:
                d.name.setText(o.Label)
                if editable:
                    bits = []
                    if faces:
                        bits.append("face %s" % ", ".join(str(f) for f in faces))
                    if edges:
                        bits.append("%d edge%s" % (len(edges), "" if len(edges) == 1 else "s"))
                    d.note.setText(("Selected: " + ", ".join(bits)) if bits else
                                   "Click a face or edges of it in the 3D view.")
                else:
                    d.note.setText(po.why_not(o))
            convertible = k in ("mesh", "box", "cylinder", "sphere", "cone",
                                "torus", "wedge", "group")
            d.btn_convert.setVisible(convertible)
            d.btn_convert.setText("Convert to solid" if k == "mesh" else "Make editable")
            for b in (d.btn_pull, d.btn_hole):
                b.setEnabled(editable and len(faces) == 1)
            for b in (d.btn_fillet, d.btn_chamfer):
                b.setEnabled(editable and bool(edges or len(faces) == 1))
            for b in [d.btn_hollow] + list(d.btn_mirror.values()) + \
                    list(d.btn_split.values()):
                b.setEnabled(editable)
            st = po.steps(o) if editable else []
            d.steps.clear()
            for i, s in enumerate(st, 1):
                d.steps.addItem("%d. %s" % (i, po.describe_step(s)))
            if not st:
                d.steps.addItem("No edits yet" if editable else "")
            d.btn_undo.setEnabled(bool(st))
            d.btn_remove.setEnabled(bool(st))
            d.btn_reset.setEnabled(bool(st))
            d.agent.setEnabled(editable)
            d.agent.setChecked(bool(o is not None and getattr(o, po.EDITABLE, False)))
            d.btn_source.setEnabled(o is not None and k not in ("agent", "hardware"))
            if o is not None and di.is_import(o):
                s = di.source(o)
                text = "From %s" % (s["file"] or "a file")
                if s["author"]:
                    text += " by %s" % s["author"]
                text += ". Licence: %s." % s["licence_label"]
                if s["url"]:
                    text += ' <a href="%s">Open its page</a>' % s["url"].replace('"', "%22")
                d.source.setText(text)
            else:
                d.source.setText("Made here." if o is not None else "")
        except Exception as exc:                       # noqa: BLE001
            _log("load: %r" % (exc,))
        finally:
            state["loading"] = False

    d.load = load

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
    d.resize(440, 640)
    load()
    return d


def open_editor(parent=None):
    """One Edit part window, brought to the front when already open."""
    from PySide6 import QtWidgets
    if parent is None:
        try:
            from . import shell
            parent = shell._mw_or_none()
        except Exception:                              # noqa: BLE001
            parent = None
    try:
        from . import export_tools
        export_tools.restore_exploded(_doc())
    except Exception:                                  # noqa: BLE001
        pass
    d = _OPEN.get("dlg")
    try:
        alive = d is not None and d.isVisible()
    except RuntimeError:
        alive = False
    if alive:
        d.load()
    else:
        d = PartEditor(parent or QtWidgets.QApplication.activeWindow())
        _OPEN["dlg"] = d
        d.show()
    d.raise_()
    d.activateWindow()
    return d


def view_bar_button(parent=None):
    """The view bar's Edit part button (objectName VBtn, icon-only)."""
    from PySide6 import QtCore, QtWidgets
    from . import export_tools
    b = QtWidgets.QPushButton("", parent)
    b.setObjectName("VBtn")
    b.setCursor(QtCore.Qt.PointingHandCursor)
    b.setToolTip("Edit part: push/pull faces, holes, fillets, hollow (F)")
    b.setAccessibleName("Edit part")
    b.setIconSize(QtCore.QSize(16, 16))
    b.setFixedWidth(34)
    b.setProperty("atech_icon", "edit")
    b.clicked.connect(lambda _=False: export_tools._guard(
        lambda: open_editor(b.window())))
    return b
