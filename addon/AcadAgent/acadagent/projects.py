"""projects — build Atech-module projects inside Atech Atelier.

The builder itself lives in the repo at projects/atech_modules.py so it can be
run headlessly by the gate. This module is the thin GUI side: locate it, run
it, style the result, frame it, and report honestly.
"""
import os
import sys

import FreeCAD


MISSING_LIBRARY = ("Atech modules are missing from this installation. "
                   "Reinstall Atech Atelier.")


def _builder_candidates(here=None):
    """Where atech_modules.py may live, in lookup order — relative to this
    addon only, never to one developer's home (R08):

      1. the installed bundle: usr/Mod/AcadAgent/acadagent/ -> ../projects
      2. a development checkout: <repo>/addon/AcadAgent/acadagent/ ->
         <repo>/projects (through the symlink too, if the addon is linked
         into a FreeCAD Mod folder)
    """
    heres = [here] if here else []
    if not heres:
        for h in (os.path.dirname(os.path.abspath(__file__)),
                  os.path.dirname(os.path.realpath(__file__))):
            if h not in heres:
                heres.append(h)
    out = []
    for h in heres:
        for rel in (("..", "projects"), ("..", "..", "..", "projects")):
            c = os.path.normpath(os.path.join(h, *rel))
            if c not in out:
                out.append(c)
    return out


def _builder_dir(here=None):
    """Where atech_modules.py lives — bundled copy or repo checkout."""
    for cand in _builder_candidates(here):
        if (os.path.isfile(os.path.join(cand, "atech_modules.py"))
                and os.path.isfile(os.path.join(cand, "atech_ports.py"))):
            return cand
    return None


def _mod():
    d = _builder_dir()
    if d is None:
        return None
    if d not in sys.path:
        sys.path.insert(0, d)
    import atech_modules
    return atech_modules


def library_available():
    try:
        m = _mod()
        return m is not None and bool(m.specs())
    except Exception:
        return False


def project_keys():
    m = _mod()
    return sorted(m.PROJECTS) if m else []


def project_info(key):
    m = _mod()
    if m is None or key not in (m.PROJECTS if m else {}):
        return None
    return m.PROJECTS[key]


def _ports_lib():
    """atech_ports from this installation's projects/ folder (or None)."""
    if _mod() is None:
        return None
    import atech_ports
    return atech_ports


# ------------------------------------------------- free parts (R305)
#: The Atech role of a part placed by hand that plugs into no port (the N20
#: wheel; the NEMA 17 stepper; any part whose mesh has no pin header). It is
#: not "module" (atech_ports.occupied() counts modules by their AtechPorts).
FREE_ROLE = "part"
FREE_GAP_MM = 12.0


def free_parts(seatable=None):
    """Library parts that can only be placed by hand, never seated: every
    presets.yaml entry that is not the board and not in `seatable`
    (atech_ports.seatable(); measured when None). Sorted by name."""
    m = _mod()
    ap = _ports_lib()
    if m is None or ap is None:
        return []
    names = [n for n, sp in m.specs().items() if sp.get("category") != "board"]
    if seatable is None:
        seatable = ap.seatable(sorted(names))
    return sorted(n for n in names if n not in seatable)


def _world_bbox(o):
    try:
        if hasattr(o, "Mesh"):
            return o.Mesh.BoundBox
        sh = getattr(o, "Shape", None)
        if sh is not None and not sh.isNull():
            return sh.BoundBox
    except Exception:                               # noqa: BLE001
        pass
    return None


def free_part_placement(doc, name):
    """Where a free part goes when added by hand: beside everything already
    in the document (+X), clear of it by FREE_GAP_MM, centred on the board
    (or the origin) in Y and Z. A Placement, in the mesh's own frame."""
    import Mesh
    m = _mod()
    mbb = Mesh.Mesh(m.stl_path(name)).BoundBox
    xmax, centre = None, FreeCAD.Vector(0, 0, 0)
    for o in doc.Objects:
        bb = _world_bbox(o)
        if bb is None or not bb.isValid():
            continue
        xmax = bb.XMax if xmax is None else max(xmax, bb.XMax)
        if getattr(o, "AtechRole", None) == "board":
            centre = bb.Center
    x = (xmax + FREE_GAP_MM if xmax is not None else 0.0) - mbb.XMin
    return FreeCAD.Placement(
        FreeCAD.Vector(x, centre.y - (mbb.YMin + mbb.YMax) / 2.0,
                       centre.z - (mbb.ZMin + mbb.ZMax) / 2.0),
        FreeCAD.Rotation())


def place_free_part(doc, name, placement=None, label=None):
    """Add library part `name` (n20_wheel, nema17_stepper, ...) to doc
    as a free part through atech_modules.load_module, tagged AtechRole
    "part" and AtechModule <name>. Returns the object. It plugs into no
    port; atech_ports.check() still counts it as an obstacle."""
    m = _mod()
    if m is None:
        raise RuntimeError(MISSING_LIBRARY)
    pl = placement if placement is not None else free_part_placement(doc, name)
    obj, _rep = m.load_module(doc, name, label=label or name, placement=pl)
    for prop, txt in (("AtechRole", "board | module | part"),
                      ("AtechModule", "presets.yaml module name")):
        if prop not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", prop, "Atech", txt)
    obj.AtechRole = FREE_ROLE
    obj.AtechModule = name
    doc.recompute()
    return obj


def placed_free_parts(doc):
    """[obj] of the free parts in doc, in document order."""
    if doc is None:
        return []
    return [o for o in doc.Objects if getattr(o, "AtechRole", None) == FREE_ROLE]


# --------------------------------------------- starter projects (R306)
#: The order starter modules take ports in: the side columns first, then
#: the top edge; 8 (USB-C, bottom middle) and 12 (Reset) last, as the
#: board's own docs describe them. USB-C goes to 8 first.
STARTER_PORT_ORDER = (1, 2, 3, 4, 5, 6, 9, 10, 11, 13, 14, 7, 12, 8)
STARTER_PREFERRED = {"usbc": (8,)}


def _all_pass(res):
    return all((v or {}).get("verdict") == "PASS" for v in res.values())


def seat_starter(doc, module_names, ap=None):
    """Seat module_names on the board of doc, each on the first port (pair,
    for a two-connector module) in STARTER_PORT_ORDER whose check passes
    with everything seated before it. Modules with no pin header become
    free parts beside the board. Returns a report: placed [{name, ports,
    object}], free [{name, object}], skipped [{name, reason}]."""
    ap = ap or _ports_lib()
    rep = {"placed": [], "free": [], "skipped": []}
    seatable = ap.seatable(sorted(set(module_names)))
    reserved = dict(getattr(ap, "RESERVED", {}) or {})
    ap.board_object(doc)
    for name in module_names:
        if name not in seatable:
            try:
                o = place_free_part(doc, name)
                rep["free"].append({"name": name, "object": o.Name})
            except Exception as exc:                # noqa: BLE001
                rep["skipped"].append({"name": name, "reason": str(exc)})
            continue
        order = list(STARTER_PREFERRED.get(name, ())) + [
            n for n in STARTER_PORT_ORDER if n not in STARTER_PREFERRED.get(name, ())]
        done, last = None, "no free port"
        for n in order:
            occ = ap.occupied(doc)
            if n in occ or n in reserved:
                continue
            try:
                arg = (n if seatable[name] == 1
                       else ap.pair_for(doc, name, n, reserved=reserved))
                o = ap.seat(doc, name, arg)
            except Exception as exc:                # noqa: BLE001
                last = str(exc)
                continue
            res = ap.check(doc, only=[o.Name]).get(o.Name, {})
            if _all_pass(res):
                done = o
                break
            last = "port %s: %s" % (n, ap.first_why(res))
            ap.remove(doc, int(o.AtechPorts[0]))
        if done is None:
            rep["skipped"].append({"name": name, "reason": last})
        else:
            rep["placed"].append({"name": name, "object": done.Name,
                                  "ports": [int(p) for p in done.AtechPorts]})
    doc.recompute()
    return rep


def build_starter(key, doc_name=None):
    """A starter project (atech_modules.PROJECTS[key]) as real hardware: the
    tagged board, each module seated through atech_ports on measured ports
    (AtechRole/AtechPorts, so the Modules page, check() and the agent see
    it), parts without a pin header as tagged free parts. Returns (doc,
    report) in the shape _summary() reads."""
    m = _mod()
    if m is None:
        raise RuntimeError(MISSING_LIBRARY)
    if key not in m.PROJECTS:
        raise KeyError(key)
    p = m.PROJECTS[key]
    doc = FreeCAD.newDocument(doc_name or key)
    rep = seat_starter(doc, p["modules"])
    report = {"project": p["title"], "overlaps": [], "fits_on_board": True,
              "placed": [{"name": r["name"], "ports": r["ports"], "delta": None}
                         for r in rep["placed"]] +
                        [{"name": r["name"], "ports": [], "delta": None}
                         for r in rep["free"]],
              "skipped": rep["skipped"], "seated": rep["placed"],
              "free": rep["free"]}
    return doc, report


# Atech brand: board neutral, modules on the blue ramp so the stack reads.
_BOARD_COLOR = (0.18, 0.20, 0.26)
_MODULE_COLORS = [(0.35, 0.64, 1.00), (0.60, 0.42, 1.00),
                  (0.37, 0.73, 0.55), (0.88, 0.69, 0.32),
                  (0.55, 0.60, 0.72)]


def build_and_show(key):
    """Build a named project, colour it, frame it. Returns (doc, report)."""
    m = _mod()
    if m is None:
        FreeCAD.Console.PrintError("Atech: %s\n" % MISSING_LIBRARY)
        return None, None
    try:
        # R306: seated on measured ports and tagged (AtechRole/AtechPorts),
        # not atech_modules.build_named's untagged meshes packed in a row
        doc, report = build_starter(key)
    except Exception as exc:
        FreeCAD.Console.PrintError("Atech: %s\n" % exc)
        return None, None

    _style(doc)
    # Frame AFTER the view has the new meshes. Calling fit_all() in the same
    # event-loop turn as the build leaves the camera on the old (empty) scene,
    # which renders the board edge-on and reads as "the geometry is wrong"
    # when the geometry is fine — measured: modules seated correctly at
    # Y 3.99..14.20 while the screenshot showed an edge-on board.
    def _frame():
        try:                    # the document may be gone by the next turn
            board = next((o for o in doc.Objects
                          if "motherboard" in o.Name.lower()), None)
        except Exception:                           # noqa: BLE001
            return
        frame_board(board.Placement if board is not None else None)
    try:
        from PySide6 import QtCore
        QtCore.QTimer.singleShot(0, _frame)
    except Exception:
        _frame()

    FreeCAD.Console.PrintMessage(_summary(report))
    return doc, report


# Camera for a board, in the BOARD's frame (measured, atech_ports): +Y is the
# face the modules sit on, ports 1-6 are the low-X ("left") column, port 7 is
# the low-Z ("top") edge. The page's board map is drawn the same way (low X
# left, port 7 up), so the 3D view is the map tilted back: the camera sits
# above the module face and toward the bottom edge, a little to the left.
#
# Why not setViewDirection: FreeCAD builds that camera as the SHORTEST
# rotation from -Z to the direction (View3DInventorViewer::setViewDirection,
# SbRotation(SbVec3f(0,0,-1), dir)), so the up vector is whatever falls out.
# For the old (-1,-1,-0.45) that left the board's top edge pointing down-
# right and the nav cube reading rear/bottom (release_prd R60, dogfood D13).
# Here up is chosen explicitly: the board's top edge (-Z) is screen-up and the
# left column is screen-left, so "slides in from the left" is true on screen.
# The nav cube still reads REAR: the module face IS the world +Y side.
#
# Screen-up is the owner's call by eye (R60): this camera puts the board's
# port-7 edge (world -Z for an unrotated board) at the top, so it matches the
# page's map but is world-Z-DOWN, while chat builds show world Z up. Both are
# kept, neither is deleted; the user parameter
#   User parameter:BaseApp/Preferences/Mod/AcadAgent  BoardCameraUp
# picks one ("port7" = default, "world_z" = world +Z up). In "world_z" the
# camera position is the same; only the roll differs, so ports 1-6 then show
# on screen-RIGHT and the map (low X left) reads mirrored against the view.
BOARD_CAMERA_FROM = (-0.30, 1.0, 0.70)   # camera offset, board frame (tilt only)
BOARD_SCREEN_UP = (0.0, 0.0, -1.0)       # board frame: port 7 edge
BOARD_CAMERA_UPS = {
    "port7": ("board", BOARD_SCREEN_UP),  # the page's map, upright
    "world_z": ("world", (0.0, 0.0, 1.0)),  # like chat builds
}
BOARD_CAMERA_DEFAULT = "port7"
_PARAM = "User parameter:BaseApp/Preferences/Mod/AcadAgent"
BOARD_CAMERA_KEY = "BoardCameraUp"


def board_camera_mode():
    """The BoardCameraUp setting, or the default when unset / unknown."""
    try:
        v = FreeCAD.ParamGet(_PARAM).GetString(BOARD_CAMERA_KEY, "")
    except Exception:                               # noqa: BLE001
        v = ""
    return v if v in BOARD_CAMERA_UPS else BOARD_CAMERA_DEFAULT


def board_view_rotation(board_placement=None, mode=None):
    """FreeCAD.Rotation for View3DInventor.setCameraOrientation that shows a
    board (and whatever is seated on it) as described above. Pure math.
    mode: a BOARD_CAMERA_UPS key; None reads the BoardCameraUp setting."""
    import numpy as np
    if mode not in BOARD_CAMERA_UPS:
        mode = board_camera_mode()
    frame, up = BOARD_CAMERA_UPS[mode]
    R = np.eye(3)
    if board_placement is not None:
        m = board_placement.Rotation.toMatrix()
        R = np.array([[m.A11, m.A12, m.A13], [m.A21, m.A22, m.A23],
                      [m.A31, m.A32, m.A33]], float)
    c = R @ np.array(BOARD_CAMERA_FROM, float)     # world
    c /= np.linalg.norm(c)
    view = -c                                     # camera looks along this
    up = np.array(up, float)
    if frame == "board":
        up = R @ up
    up = up - (up @ view) * view
    if np.linalg.norm(up) < 1e-6:
        # world_z on a board turned so the camera looks along world Z: no
        # roll is defined by world up, so fall back to the board's own up
        up = R @ np.array(BOARD_SCREEN_UP, float)
        up = up - (up @ view) * view
    up /= np.linalg.norm(up)
    right = np.cross(view, up)
    m = FreeCAD.Matrix(right[0], up[0], c[0], 0,
                       right[1], up[1], c[1], 0,
                       right[2], up[2], c[2], 0,
                       0, 0, 0, 1)
    return FreeCAD.Rotation(m)


def frame_board(board_placement=None):
    """Point the active 3D view at the board (board_view_rotation) and fit
    everything. False when there is no view to point."""
    try:
        import FreeCADGui
        view = FreeCADGui.ActiveDocument.ActiveView
        view.setCameraOrientation(board_view_rotation(board_placement))
    except Exception:                               # noqa: BLE001
        return False
    try:
        # viewport.fit_all keeps the view bar's band free (R82); plain
        # fitAll() would slide the model under it
        from . import viewport
        if viewport.fit_all():
            return True
    except Exception:                               # noqa: BLE001
        pass
    try:
        view.fitAll()
    except Exception:                               # noqa: BLE001
        pass
    return True


def _style(doc):
    i = 0
    for obj in doc.Objects:
        vo = getattr(obj, "ViewObject", None)
        if vo is None:
            continue
        try:
            if "motherboard" in obj.Name.lower():
                vo.ShapeColor = _BOARD_COLOR
            else:
                vo.ShapeColor = _MODULE_COLORS[i % len(_MODULE_COLORS)]
                i += 1
        except Exception:
            continue


def _summary(report):
    """One honest paragraph. Overlaps and overhang are stated, not buried."""
    lines = ["Atech: built %s — %d module(s) placed"
             % (report.get("project"), len(report.get("placed") or []))]
    for s in report.get("skipped") or []:
        lines.append("  skipped %s: %s" % (s.get("name"), s.get("reason")))
    for o in report.get("overlaps") or []:
        lines.append("  OVERLAP %s/%s by %.2f mm"
                     % (o.get("a"), o.get("b"), o.get("overlap_mm")))
    if report.get("fits_on_board") is False:
        lines.append("  NOTE the module stack is longer than the board")
    # A measured-vs-spec disagreement is worth surfacing, not smoothing.
    for p in report.get("placed") or []:
        d = p.get("delta")
        if d and max(abs(v) for v in d) > 0.5:
            lines.append("  %s measures %s against spec %s (delta %s)"
                         % (p["name"], p["measured"], p["spec"], d))
    return "\n".join(lines) + "\n"
