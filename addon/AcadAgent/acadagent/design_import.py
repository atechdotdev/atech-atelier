"""design_import - bring a CAD file into the open design (R880).

Opening a STEP or STL from Home still makes a new project of it (R309).
"Add file to design..." (and a file dropped on an open project) puts it in
the design that is open instead, set down beside what is there:

    STEP / STP / IGES / IGS / BREP / BRP   a solid (Part::Feature), one per
                                           body when the file holds several
    STL / 3MF / OBJ / PLY / OFF / AMF      a mesh (Mesh::Feature); Convert to
                                           solid (part_ops) makes it editable

in the units the file was drawn in (millimetres, inches, ...). Each part
remembers where it came from - the file, its checksum, the link, the
author and the licence (AtechImport* / AtechSource*) - so a credit and a
licence check go with the design when it is shared (credits(),
licence_problem(); R900 Publish to MakerWorld reads them). A solid gets
its original shape stored for granular edits (part_ops.ensure_props), and
"Let the agent edit it" (AtechAgentEditable) is the user's to tick.

add_file() is headless; AddFileDialog is the window.
"""
import hashlib
import os

from . import shape_edit as se

SOLID_EXT = (".step", ".stp", ".iges", ".igs", ".brep", ".brp")
MESH_EXT = (".stl", ".3mf", ".obj", ".ply", ".off", ".amf")
ADD_EXT = SOLID_EXT + MESH_EXT
FILE_FILTER = ("CAD files (*.step *.stp *.iges *.igs *.brep *.brp *.stl *.3mf "
               "*.obj *.ply *.off *.amf);;All files (*)")
#: (label, scale to mm)
UNITS = (("Millimetres", 1.0), ("Inches", 25.4), ("Centimetres", 10.0),
         ("Metres", 1000.0))
#: More bodies than this in one STEP stay one part (a compound).
MAX_BODIES = 50
#: A mesh bigger than this many triangles is said to be slow to edit.
BIG_MESH = 200000

#: key -> (label, may be remixed, may be shared, non-commercial, share-alike)
LICENCES = {
    "own": ("My own design", True, True, False, False),
    "cc0": ("CC0 (public domain)", True, True, False, False),
    "cc-by": ("CC BY", True, True, False, False),
    "cc-by-sa": ("CC BY-SA", True, True, False, True),
    "cc-by-nc": ("CC BY-NC", True, True, True, False),
    "cc-by-nc-sa": ("CC BY-NC-SA", True, True, True, True),
    "cc-by-nd": ("CC BY-ND (no derivatives)", False, True, False, False),
    "cc-by-nc-nd": ("CC BY-NC-ND (no derivatives)", False, True, True, False),
    "sdfl": ("MakerWorld Standard Digital File License", False, False, True, False),
    "unknown": ("Not stated", None, None, None, None),
}
LICENCE_ORDER = ("unknown", "own", "cc0", "cc-by", "cc-by-sa", "cc-by-nc",
                 "cc-by-nc-sa", "cc-by-nd", "cc-by-nc-nd", "sdfl")

PROPS = (
    # name, type, doc
    ("AtechImport", "App::PropertyBool", "Brought in from a file"),
    ("AtechImportFile", "App::PropertyString", "The file it came from"),
    ("AtechImportSha256", "App::PropertyString", "That file's checksum"),
    ("AtechImportUnits", "App::PropertyFloat", "mm per unit of the file"),
    ("AtechSourceUrl", "App::PropertyString", "Where it was found"),
    ("AtechSourceAuthor", "App::PropertyString", "Who made it"),
    ("AtechSourceLicence", "App::PropertyString", "Its licence (key)"),
)


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[design_import] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def addable(paths):
    return [p for p in paths if p and os.path.isfile(p)
            and p.lower().endswith(ADD_EXT)]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _label(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.replace("_", " ").strip() or "Imported part"


def is_import(obj):
    return bool(getattr(obj, "AtechImport", False))


def _tag(obj, path, units, digest, source):
    for name, typ, doc in PROPS:
        if not hasattr(obj, name):
            obj.addProperty(typ, name, "Atech", doc)
    obj.AtechImport = True
    obj.AtechImportFile = os.path.basename(path)
    obj.AtechImportSha256 = digest
    obj.AtechImportUnits = float(units)
    set_source(obj, **(source or {}))


def set_source(obj, url=None, author=None, licence=None):
    """Record where a part came from (None leaves a field as it is)."""
    for name, typ, doc in PROPS:
        if not hasattr(obj, name):
            obj.addProperty(typ, name, "Atech", doc)
    if url is not None:
        obj.AtechSourceUrl = str(url).strip()
    if author is not None:
        obj.AtechSourceAuthor = str(author).strip()
    if licence is not None:
        lic = str(licence).strip().lower()
        obj.AtechSourceLicence = lic if lic in LICENCES else "unknown"


def source(obj):
    """{"file", "url", "author", "licence", "licence_label"} of a part."""
    lic = getattr(obj, "AtechSourceLicence", "") or "unknown"
    return {"file": getattr(obj, "AtechImportFile", ""),
            "url": getattr(obj, "AtechSourceUrl", ""),
            "author": getattr(obj, "AtechSourceAuthor", ""),
            "licence": lic,
            "licence_label": LICENCES.get(lic, LICENCES["unknown"])[0]}


def _read_solid(path, units):
    import Part
    shape = Part.read(path)
    if shape.isNull():
        raise se.EditRefused("%s holds no shape." % os.path.basename(path))
    if units != 1.0:
        shape.scale(float(units))
    return shape


def _read_mesh(path, units):
    import FreeCAD
    import Mesh
    try:
        m = Mesh.Mesh(path)
    except Exception as exc:                           # noqa: BLE001
        if not path.lower().endswith(".3mf"):
            raise
        _log("FreeCAD's 3MF reader: %r" % (exc,))
        m = Mesh.Mesh()
    if m.CountFacets == 0 and path.lower().endswith(".3mf"):
        # R900: a Bambu Studio / MakerWorld 3MF keeps its objects in
        # 3D/Objects/*.model, which FreeCAD's reader does not follow
        from . import makerworld
        try:
            m = makerworld.mesh_from_3mf(path)
        except (ValueError, KeyError, OSError) as exc:
            raise se.EditRefused("%s could not be read: %s"
                                 % (os.path.basename(path), exc))
        except Exception as exc:                       # noqa: BLE001
            raise se.EditRefused("%s is not a 3MF Atelier can read (%s)."
                                 % (os.path.basename(path), exc))
    if m.CountFacets == 0:
        raise se.EditRefused("%s holds no triangles." % os.path.basename(path))
    if units != 1.0:
        mat = FreeCAD.Matrix()
        mat.scale(float(units), float(units), float(units))
        m.transform(mat)
    return m


def _set_down(objs, others):
    """Move the new parts together: beside what is there, on the floor."""
    import FreeCAD
    boxes = [se._world_bbox(o) for o in objs]
    xmin = min(b.XMin for b in boxes)
    xmax = max(b.XMax for b in boxes)
    ymin = min(b.YMin for b in boxes)
    ymax = max(b.YMax for b in boxes)
    zmin = min(b.ZMin for b in boxes)
    w = xmax - xmin
    tx, ty, _tz = se._beside(others, w)
    shift = FreeCAD.Vector(tx - (xmin + xmax) / 2.0, ty - (ymin + ymax) / 2.0,
                           -zmin)
    for o in objs:
        p = o.Placement
        o.Placement = FreeCAD.Placement(p.Base + shift, p.Rotation)


def add_file(doc, path, units=1.0, source=None, agent_editable=False,
             label=None):
    """Put the file's geometry in `doc` (one undo step). Returns the new
    objects. `source`: {"url", "author", "licence"}."""
    low = path.lower()
    if not low.endswith(ADD_EXT):
        raise se.EditRefused("Atelier adds STEP, IGES, BREP, STL, 3MF, OBJ, "
                             "PLY, OFF or AMF files, not %s."
                             % (os.path.splitext(path)[1] or "this file"))
    if not os.path.isfile(path):
        raise se.EditRefused("%s is not there any more." % path)
    try:
        units = float(units)
    except (TypeError, ValueError):
        units = 1.0
    if not 0 < units <= 10000:
        raise se.EditRefused("Units must be a positive scale to mm.")
    digest = sha256(path)
    name = label or _label(path)
    is_mesh = low.endswith(MESH_EXT)
    geom = _read_mesh(path, units) if is_mesh else _read_solid(path, units)
    others = [o for o in doc.Objects]
    se._open(doc, "Add %s" % os.path.basename(path))
    made = []
    try:
        if is_mesh:
            o = doc.addObject("Mesh::Feature", "Imported")
            o.Mesh = geom
            made.append(o)
        else:
            solids = geom.Solids
            pieces = solids if 1 < len(solids) <= MAX_BODIES else [geom]
            for s in pieces:
                o = doc.addObject("Part::Feature", "Imported")
                o.Shape = s
                made.append(o)
        for i, o in enumerate(made, 1):
            o.Label = name if len(made) == 1 else "%s %d" % (name, i)
            _tag(o, path, units, digest, source)
        doc.recompute()
        _set_down(made, others)
        from . import part_ops
        for o in made:
            if not is_mesh:
                part_ops.ensure_props(o)
                o.AtechAgentEditable = bool(agent_editable)
            elif agent_editable:
                o.addProperty("App::PropertyBool", part_ops.EDITABLE, "Atech",
                              "The design agent may edit this part")
                setattr(o, part_ops.EDITABLE, True)
        doc.recompute()
    except Exception:
        se._abort(doc)
        raise
    doc.commitTransaction()
    return made


def notes(objs):
    """Words for the user about what was added."""
    out = []
    for o in objs:
        if se.kind(o) == "mesh" and o.Mesh.CountFacets > BIG_MESH:
            out.append("%s is a big mesh (%d triangles): converting it to a "
                       "solid simplifies it." % (o.Label, o.Mesh.CountFacets))
    if objs and se.kind(objs[0]) == "mesh":
        out.append("STL, 3MF and OBJ are meshes: Edit part > Convert to solid "
                   "makes faces you can pick.")
    return out


# ------------------------------------------------------------------ licences
def licence_problem(obj, purpose="publish"):
    """Words when the part's licence forbids `purpose` ("publish": sharing
    a design that contains it, edited or not; "sell"), else ""."""
    if not is_import(obj):
        return ""
    s = source(obj)
    lic = LICENCES.get(s["licence"], LICENCES["unknown"])
    _label_, remix, share, nc, _sa = lic
    who = s["author"] or "its maker"
    if purpose == "publish":
        if share is False:
            return ("%s is under the %s, which does not allow sharing it. "
                    "Take it out, or ask %s." % (obj.Label, lic[0], who))
        if remix is False and _edited(obj):
            return ("%s is under %s, which does not allow changes to it, and "
                    "it has been edited." % (obj.Label, lic[0]))
        if share is None:
            return ("%s's licence is not stated. Add it (Edit part > Source) "
                    "before you publish." % obj.Label)
    if purpose == "sell" and nc:
        return "%s is non-commercial (%s)." % (obj.Label, lic[0])
    return ""


def _edited(obj):
    try:
        from . import part_ops
        return bool(part_ops.steps(obj))
    except Exception:                                  # noqa: BLE001
        return False


def strictest_licence(objs):
    """The licence a design that contains these parts must carry at least:
    share-alike and non-commercial terms carry over (CC BY-NC-SA wins over
    CC BY-SA and CC BY-NC). None when nothing imported asks for one."""
    sa = nc = by = False
    for o in objs:
        if not is_import(o):
            continue
        lic = source(o)["licence"]
        if lic in ("own", "unknown", "cc0"):
            continue
        _l, _r, _s, n, a = LICENCES[lic]
        by = True
        sa = sa or bool(a)
        nc = nc or bool(n)
    if not by:
        return None
    return "cc-by" + ("-nc" if nc else "") + ("-sa" if sa else "")


def credits(doc):
    """One line per imported part with an author or a link: the credit a
    published design carries ("Bracket by Ana (CC BY), makerworld.com/...")."""
    out, seen = [], set()
    for o in getattr(doc, "Objects", []):
        if not is_import(o):
            continue
        s = source(o)
        if s["licence"] == "own" or not (s["author"] or s["url"]):
            continue
        key = (s["file"], s["url"], s["author"])
        if key in seen:
            continue
        seen.add(key)
        name = _label(s["file"]) if s["file"] else o.Label
        text = name
        if s["author"]:
            text += " by %s" % s["author"]
        if s["licence"] != "unknown":
            text += " (%s)" % s["licence_label"]
        if s["url"]:
            text += ", %s" % s["url"]
        out.append(text)
    return out


def brief_lines(doc):
    """R880: imported parts for the agent's brief: file, source, editable."""
    out = []
    for o in getattr(doc, "Objects", []):
        if not is_import(o):
            continue
        s = source(o)
        bits = ["%s: imported from %s" % (o.Label, s["file"] or "a file")]
        if s["author"]:
            bits.append("by %s" % s["author"])
        if s["licence"] != "unknown":
            bits.append(s["licence_label"])
        bits.append("you may edit it (EDITABLE PARTS)"
                    if getattr(o, "AtechAgentEditable", False)
                    else "the user's: never change or rebuild it")
        out.append(", ".join(bits))
    return out


# ------------------------------------------------------------------ window
def AddFileDialog(parent=None, path=None):
    """Choose a file, its units and (optionally) where it came from."""
    from PySide6 import QtWidgets
    from . import export_tools

    d = export_tools._tool_dialog(QtWidgets.QDialog, parent, "Add file to design")
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(10)
    t = QtWidgets.QLabel("Add file to design", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    sub = QtWidgets.QLabel("STEP, IGES and BREP come in as solids you can edit "
                           "face by face. STL, 3MF and OBJ come in as meshes.", d)
    sub.setObjectName("ToolMuted")
    sub.setWordWrap(True)
    lay.addWidget(sub)

    frow = QtWidgets.QHBoxLayout()
    d.path = QtWidgets.QLineEdit(path or "", d)
    d.path.setPlaceholderText("Choose a file…")
    d.path.setAccessibleName("File")
    d.browse = QtWidgets.QPushButton("Choose…", d)
    frow.addWidget(d.path, 1)
    frow.addWidget(d.browse)
    lay.addLayout(frow)

    form = QtWidgets.QFormLayout()
    d.units = QtWidgets.QComboBox(d)
    for lab, k in UNITS:
        d.units.addItem(lab, k)
    d.units.setToolTip("The unit the file was drawn in. STL files carry no "
                       "unit; most are millimetres.")
    form.addRow("Units", d.units)
    d.url = QtWidgets.QLineEdit(d)
    d.url.setPlaceholderText("https://makerworld.com/en/models/…  (optional)")
    form.addRow("Found at", d.url)
    d.author = QtWidgets.QLineEdit(d)
    d.author.setPlaceholderText("Who made it (optional)")
    form.addRow("Made by", d.author)
    d.licence = QtWidgets.QComboBox(d)
    for k in LICENCE_ORDER:
        d.licence.addItem(LICENCES[k][0], k)
    form.addRow("Licence", d.licence)
    lay.addLayout(form)
    d.editable = QtWidgets.QCheckBox("Let the design agent edit it", d)
    d.editable.setToolTip("The agent may then change this part when you ask "
                          "in the chat (each change is a step you can undo). "
                          "Otherwise it designs around it.")
    lay.addWidget(d.editable)
    d.status = QtWidgets.QLabel("", d)
    d.status.setObjectName("ToolMuted")
    d.status.setWordWrap(True)
    lay.addWidget(d.status)

    bb = QtWidgets.QDialogButtonBox(d)
    d.ok = bb.addButton("Add to design", QtWidgets.QDialogButtonBox.AcceptRole)
    bb.addButton(QtWidgets.QDialogButtonBox.Cancel)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)

    def browse():
        p, _f = QtWidgets.QFileDialog.getOpenFileName(d, "Add file to design",
                                                      d.path.text(), FILE_FILTER)
        if p:
            d.path.setText(p)

    def url_changed(text):
        try:
            from . import makerworld
            info = makerworld.parse_link(text)
        except Exception:                              # noqa: BLE001
            info = None
        if info:
            d.status.setText("A MakerWorld model: set the licence it shows on "
                             "its page; the author and link go in the credits.")

    def check():
        p = d.path.text().strip()
        ok = bool(p) and p.lower().endswith(ADD_EXT) and os.path.isfile(p)
        d.ok.setEnabled(ok)
        if p and not ok:
            d.status.setText("Choose a STEP, IGES, BREP, STL, 3MF, OBJ, PLY, "
                             "OFF or AMF file.")
        elif ok and not d.url.text().strip():
            d.status.setText("")
        d.editable.setEnabled(ok)

    def values():
        return {"path": d.path.text().strip(),
                "units": float(d.units.currentData() or 1.0),
                "source": {"url": d.url.text(), "author": d.author.text(),
                           "licence": d.licence.currentData()},
                "agent_editable": d.editable.isChecked()}

    d.browse.clicked.connect(lambda _=False: browse())
    d.path.textChanged.connect(lambda _t: check())
    d.url.textChanged.connect(url_changed)
    d.values = values
    check()
    d.resize(480, 0)
    return d


def add_to_active(path=None, parent=None):
    """The menu / view-bar action: ask, then add. Returns the new objects."""
    from PySide6 import QtWidgets
    import FreeCAD
    d = AddFileDialog(parent, path)
    if not path:
        d.browse.click()
        if not d.path.text().strip():
            return []
    if d.exec() != QtWidgets.QDialog.Accepted:
        return []
    v = d.values()
    doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("Untitled")
    try:
        made = add_file(doc, v["path"], v["units"], v["source"],
                        v["agent_editable"])
    except Exception as exc:                           # noqa: BLE001
        _log("add %s: %r" % (v["path"], exc))
        QtWidgets.QMessageBox.warning(parent, "Could not add the file",
                                      "%s could not be added: %s"
                                      % (os.path.basename(v["path"]), exc))
        return []
    _show(made)
    return made


def add_dropped(paths):
    """Files dropped on an open project: added with no questions (mm, no
    source; Edit part > Source fills that in later)."""
    import FreeCAD
    doc = FreeCAD.ActiveDocument
    made = []
    for p in addable(paths):
        try:
            made += add_file(doc, p)
        except Exception as exc:                       # noqa: BLE001
            _log("drop %s: %r" % (p, exc))
            try:
                from . import shell
                shell._notify("Could not add the file",
                              "%s could not be added. The details are in the "
                              "Report view." % os.path.basename(p), exc)
            except Exception:                          # noqa: BLE001
                pass
    _show(made)
    return made


def _show(made):
    if not made:
        return
    try:
        import FreeCADGui
        FreeCADGui.Selection.clearSelection()
        for o in made:
            FreeCADGui.Selection.addSelection(o)
        from . import viewport
        viewport.fit_all()
    except Exception:                                  # noqa: BLE001
        pass
