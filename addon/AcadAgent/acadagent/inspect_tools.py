"""inspect_tools - Hide, Show all, Isolate and See-through for the 3D view's
right-click menu (PRD W3, R313-R316).

FreeCAD 1.1 has Hide / Show all but no Isolate; its Show all also brings
back every hidden input of a Cut or a Body's features. Atech's versions:

  hide(objs)          hide the picked parts
  isolate(doc, objs)  show only the picked parts (Atech board and modules
                      included in what is hidden); remembers what it hid
  show_all(doc)       show every part again: everything Hide / Isolate hid,
                      plus every END part (not consumed by another shape
                      object). Construction a build hid on purpose (a Cut's
                      tool, a fused input) stays hidden.
  set_transparency(objs, pct) / toggle_see_through(objs)
  hidden_parts(doc)   the end parts hidden now (for the agent's brief, W6)

The visibility functions work headless (obj.Visibility); transparency needs
the GUI (ViewObject). Nothing here touches what build.py owns: hiding is a
view state, the objects stay.

Menu wiring: register_commands() adds the FreeCAD commands; context_menu(
workbench, recipient) appends them to the 3D view's right-click menu from a
Workbench.ContextMenu; add_actions(qmenu) fills any QMenu (tests, a custom
menu).
"""
SEE_THROUGH_PCT = 70

#: command id -> (menu text, tooltip, function name)
COMMANDS = (
    ("Atech_Hide", "Hide", "Hide the selected parts", "cmd_hide"),
    ("Atech_Isolate", "Isolate", "Show only the selected parts", "cmd_isolate"),
    ("Atech_ShowAll", "Show all", "Show every part again", "cmd_show_all"),
    ("Atech_SeeThrough", "See-through", "Make the selected parts see-through, "
     "or solid again", "cmd_see_through"),
)
CONTEXT_COMMANDS = [c[0] for c in COMMANDS]

# doc.Name -> set of object Names this module hid (Hide and Isolate)
_HIDDEN = {}
# doc.Name -> True while an isolate is on
_ISOLATED = {}
# (doc.Name, obj.Name) -> transparency before see-through
_BEFORE = {}


def _is_part(o):
    """A thing the user sees as a part: a shape object or an Atech mesh;
    not a group, a measurement, a datum, a sketch's construction."""
    t = o.TypeId
    if t.startswith("App::") or t.startswith("Sketcher::"):
        return False
    if t == "Mesh::Feature":
        return True
    return getattr(o, "Shape", None) is not None


def _consumed(o):
    """True when another shape object uses o as an input (a Cut's base or
    tool, a Body's feature): its visibility is the parent's business."""
    for u in o.InList:
        if u.TypeId.startswith("App::"):
            continue
        if getattr(u, "Shape", None) is not None or u.TypeId.startswith("PartDesign::"):
            return True
    return False


def end_parts(doc):
    """Every part the user would call a part: not consumed, not a leftover
    of a previous build."""
    return [o for o in doc.Objects if _is_part(o) and not _consumed(o)
            and not o.Label.endswith("[previous build]")]


def _set_visible(o, on):
    try:
        if bool(o.Visibility) != bool(on):
            o.Visibility = bool(on)
        return True
    except Exception:                                   # noqa: BLE001
        return False


def hide(objs):
    """R313: hide these parts. Returns how many were hidden."""
    n = 0
    for o in objs:
        if o is None:
            continue
        if getattr(o, "Visibility", False):
            _set_visible(o, False)
            _HIDDEN.setdefault(o.Document.Name, set()).add(o.Name)
            n += 1
    return n


def show(objs):
    """R701: show these parts again (one row's eye in Show and hide).
    Returns how many were shown."""
    n = 0
    for o in objs:
        if o is None:
            continue
        if not getattr(o, "Visibility", True):
            _set_visible(o, True)
            n += 1
        _HIDDEN.get(o.Document.Name, set()).discard(o.Name)
    return n


def isolate(doc, objs):
    """R314: show only `objs` (their containers stay visible); every other
    end part is hidden. Returns the labels hidden."""
    keep = {o.Name for o in objs if o is not None}
    if not keep:
        return []
    for o in list(objs):                     # a Body's tip etc.: keep parents
        for p in getattr(o, "InList", []):
            if p.TypeId.startswith(("App::Part", "PartDesign::Body")):
                keep.add(p.Name)
    hidden = []
    for o in end_parts(doc):
        if o.Name in keep:
            _set_visible(o, True)
            continue
        if getattr(o, "Visibility", False):
            _set_visible(o, False)
            _HIDDEN.setdefault(doc.Name, set()).add(o.Name)
            hidden.append(o.Label)
    _ISOLATED[doc.Name] = True
    return hidden


def is_isolated(doc):
    return bool(_ISOLATED.get(doc.Name))


def show_all(doc):
    """R315: show every end part again plus whatever Hide / Isolate hid.
    A Cut's inputs stay hidden. Returns how many were shown."""
    names = _HIDDEN.pop(doc.Name, set())
    _ISOLATED.pop(doc.Name, None)
    n = 0
    for name in names:
        o = doc.getObject(name)
        if o is not None and not o.Visibility:
            _set_visible(o, True)
            n += 1
    for o in end_parts(doc):
        if not o.Visibility:
            _set_visible(o, True)
            n += 1
    return n


def hidden_parts(doc):
    """Labels of the end parts that are hidden now (for the agent's brief:
    "the user hid ...")."""
    return [o.Label for o in end_parts(doc) if not getattr(o, "Visibility", True)]


def set_transparency(objs, pct):
    """R316: set the parts' transparency (0 solid .. 100 invisible). GUI
    only (ViewObject); returns how many changed."""
    pct = max(0, min(100, int(round(pct))))
    n = 0
    for o in objs:
        vo = getattr(o, "ViewObject", None)
        if vo is None or not hasattr(vo, "Transparency"):
            continue
        try:
            vo.Transparency = pct
            n += 1
        except Exception:                               # noqa: BLE001
            pass
    return n


def toggle_see_through(objs):
    """R316: see-through (SEE_THROUGH_PCT) on, or back to what each part
    was. Returns the new state (True: see-through)."""
    objs = [o for o in objs if getattr(getattr(o, "ViewObject", None), "Transparency",
                                       None) is not None]
    if not objs:
        return False
    on = any(o.ViewObject.Transparency < SEE_THROUGH_PCT for o in objs)
    for o in objs:
        key = (o.Document.Name, o.Name)
        if on:
            if o.ViewObject.Transparency < SEE_THROUGH_PCT:
                _BEFORE[key] = o.ViewObject.Transparency
            set_transparency([o], SEE_THROUGH_PCT)
        else:
            set_transparency([o], _BEFORE.pop(key, 0))
    return on


# ------------------------------------------------------------- selection
def _selection():
    try:
        import FreeCADGui
        return [o for o in FreeCADGui.Selection.getSelection() if _is_part(o)]
    except Exception:                                   # noqa: BLE001
        return []


def _doc():
    try:
        import FreeCAD
        return FreeCAD.ActiveDocument
    except Exception:                                   # noqa: BLE001
        return None


def _undoable(name, fn):
    doc = _doc()
    if doc is None:
        return None
    doc.openTransaction(name)
    try:
        return fn(doc)
    finally:
        doc.commitTransaction()


def cmd_hide():
    return _undoable("Hide", lambda d: hide(_selection()))


def cmd_isolate():
    return _undoable("Isolate", lambda d: isolate(d, _selection()))


def cmd_show_all():
    return _undoable("Show all", lambda d: show_all(d))


def cmd_see_through():
    return _undoable("See-through", lambda d: toggle_see_through(_selection()))


def enabled(cmd_id, doc=None, selection=None):
    """Whether a command makes sense now (pure: tests pass doc/selection)."""
    sel = _selection() if selection is None else selection
    doc = _doc() if doc is None else doc
    if doc is None:
        return False
    if cmd_id == "Atech_ShowAll":
        return bool(hidden_parts(doc)) or bool(_HIDDEN.get(doc.Name))
    return bool(sel)


class _Command(object):
    def __init__(self, cid, text, tip, fn):
        self.cid, self.text, self.tip, self.fn = cid, text, tip, fn

    def GetResources(self):                             # noqa: N802
        return {"MenuText": self.text, "ToolTip": self.tip}

    def Activated(self):                                # noqa: N802
        globals()[self.fn]()

    def IsActive(self):                                 # noqa: N802
        try:
            return enabled(self.cid)
        except Exception:                               # noqa: BLE001
            return False


def register_commands():
    """Add the four commands to FreeCAD (once; GUI only)."""
    import FreeCADGui
    have = set(FreeCADGui.listCommands())
    for cid, text, tip, fn in COMMANDS:
        if cid not in have:
            FreeCADGui.addCommand(cid, _Command(cid, text, tip, fn))


def context_menu(workbench, recipient):
    """Call from Workbench.ContextMenu(recipient): on the 3D view's menu
    ("View"), adds Hide / Isolate / Show all / See-through in one group."""
    if recipient != "View":
        return False
    register_commands()
    workbench.appendContextMenu("", ["Separator"] + CONTEXT_COMMANDS)
    return True


def add_actions(menu, doc_fn=None, selection_fn=None):
    """Add the four actions to a QMenu (enabled per enabled()). Returns
    {command id: QAction}."""
    doc = (doc_fn or _doc)()
    sel = (selection_fn or _selection)()
    out = {}
    menu.addSeparator()
    for cid, text, tip, fn in COMMANDS:
        a = menu.addAction(text)
        a.setToolTip(tip)
        a.setStatusTip(tip)
        a.setObjectName(cid)
        a.setEnabled(doc is not None and enabled(cid, doc, sel))
        a.triggered.connect(lambda _=False, f=fn: globals()[f]())
        out[cid] = a
    return out
