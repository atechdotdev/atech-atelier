"""export_tools - editing, export and sharing for the Atech shell (PRD W4).

    R340  hand edits survive rebuilds: colour, transparency, visibility and
          placement changes the user makes on agent-built parts are recorded
          in the document property AtechOverrides (JSON) and re-applied to
          the part with the same label after the next build
          (capture_overrides() before a build, reapply_overrides() after);
          overrides_for_brief() tells the agent about them.
    R341  colour menu: the cad.color palette (agent_kit/atech_detail.py
          MATERIALS, read from source so no FreeCAD is needed), a custom
          colour and a transparency slider (ColourMenu).
    R342  Export for print: whole product / selection / one file per part;
          STL, 3MF (with colours), STEP; mesh deviation Draft 0.1, Fine 0.02
          (default), Ultra 0.01 mm; Atech board, module and cable parts left
          out by default (their models are CC BY-NC) (export_for_print,
          ExportDialog).
    R343  print prep: each part laid on its largest flat face, overhangs
          steeper than 45 deg and walls under 0.8 mm flagged (print_report).
    R344  Open in slicer: Bambu Studio / PrusaSlicer found in /Applications
          or ~/Applications (find_slicers, open_in_slicer).
    R345  exploded view: a slider that pushes parts out from the middle;
          display only, every placement is put back when it closes
          (Exploder, ExplodeDialog).
    R346  BOM: printed parts (volume, mass, colour, count) and Atech
          hardware (board, modules with ports, cables with length), CSV
          export (bom, bom_csv, BomDialog).
    R347  share image: lives in capture.py (share_image, share_sheet); the
          view-bar button and menu action here call it.

The logic runs headless (freecadcmd) and on plain objects; Qt is imported
only by the widgets. Nothing here edits shell.py: view_bar_buttons() and
menu_actions() are factories the shell wires in.
"""
import ast
import csv
import io
import json
import math
import os
import re
import subprocess
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT_DIR = os.path.join(HERE, "agent_kit")

#: The document property that carries the hand edits (R340).
DOC_PROP = "AtechOverrides"
PREVIOUS = "[previous build]"

#: Colour equality: within 1.5 of 255 per channel, as build._colour.
COLOUR_TOL = 1.5 / 255.0
POS_TOL = 1e-4                     # mm
ROT_TOL = 1e-6                     # quaternion component

#: R342 mesh deviation presets, mm (linear) and radians (angular).
DEVIATIONS = (("Draft", 0.1, 0.35), ("Fine", 0.02, 0.2), ("Ultra", 0.01, 0.1))
DEFAULT_DEVIATION = "Fine"
FORMATS = ("STL", "3MF", "STEP")
SCOPES = (("product", "Whole product"), ("selection", "Selection"),
          ("parts", "One file per part"))

#: R343 print limits.
OVERHANG_DEG = 45.0
MIN_WALL_MM = 0.8
KEEP_BOTTOM_SHARE = 0.8         # the current bottom is kept when this big vs the largest
BED_TOL = 0.05                     # mm: a facet this close to z=0 lies on the bed
OVERHANG_FLAG_MM2 = 10.0           # smaller overhang areas are noise
OVERHANG_FLAG_SHARE = 0.01         # ... and so is under 1 % of the surface

#: R346 PLA density, g/cm3 (PRD W3 default).
PLA_DENSITY = 1.24

#: R344 the slicers we can hand a file to (macOS app bundle names).
SLICERS = (("Bambu Studio", ("BambuStudio.app", "Bambu Studio.app")),
           ("PrusaSlicer", ("PrusaSlicer.app", "Original Prusa Drivers/PrusaSlicer.app")))


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintMessage("AcadAgent export: %s\n" % msg)
    except Exception:                                     # noqa: BLE001
        pass


# ===================================================================
# palette (R341)
# ===================================================================
_FALLBACK_PALETTE = {
    "matte_white": (0.93, 0.93, 0.91), "matte_black": (0.13, 0.13, 0.14),
    "signal_red": (0.80, 0.11, 0.10), "toy_yellow": (0.98, 0.78, 0.10),
    "toy_blue": (0.12, 0.42, 0.86), "toy_green": (0.20, 0.66, 0.32),
}
_PALETTE = None


def palette():
    """[(key, display name, (r, g, b), transparency)] in MATERIALS order.

    Read from agent_kit/atech_detail.py's source (ast), so the shell needs
    no FreeCAD import for it and stays in step with cad.color()."""
    global _PALETTE
    if _PALETTE is not None:
        return list(_PALETTE)
    out = []
    try:
        with open(os.path.join(KIT_DIR, "atech_detail.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, "id", None) == "MATERIALS" for t in node.targets):
                mats = ast.literal_eval(node.value)
                for key, v in mats.items():
                    out.append((key, display_name(key), tuple(float(c) for c in v["ShapeColor"]),
                                int(v.get("Transparency", 0))))
                break
    except Exception as exc:                              # noqa: BLE001
        _log("palette unreadable: %r" % (exc,))
    if not out:
        out = [(k, display_name(k), c, 0) for k, c in _FALLBACK_PALETTE.items()]
    _PALETTE = out
    return list(out)


def display_name(key):
    """'toy_yellow' -> 'Toy yellow'; 'led_red' -> 'LED red'."""
    words = str(key).split("_")
    words = ["LED" if w == "led" else w for w in words]
    s = " ".join(words)
    return s[:1].upper() + s[1:]


def hex_colour(rgb):
    return "#%02x%02x%02x" % tuple(int(round(max(0.0, min(1.0, float(c))) * 255))
                                   for c in tuple(rgb)[:3])


def colour_name(rgb):
    """The palette name of a colour (within 1.5/255), else its #rrggbb."""
    if rgb is None:
        return ""
    for _k, name, c, _t in palette():
        if _same_colour(c, rgb):
            return name
    return hex_colour(rgb)


def _same_colour(a, b):
    if a is None or b is None:
        return a is None and b is None
    return all(abs(float(x) - float(y)) <= COLOUR_TOL + 1e-9
               for x, y in zip(tuple(a)[:3], tuple(b)[:3]))


# ===================================================================
# placements as plain tuples (x, y, z, qx, qy, qz, qw)
# ===================================================================
IDENTITY = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def _qinv(q):
    return (-q[0], -q[1], -q[2], q[3])


def _qrot(q, v):
    p = _qmul(_qmul(q, (v[0], v[1], v[2], 0.0)), _qinv(q))
    return p[:3]


def pl_mul(a, b):
    """a * b (apply b, then a), like FreeCAD's Placement.multiply."""
    qa, qb = a[3:], b[3:]
    t = _qrot(qa, b[:3])
    q = _qmul(qa, qb)
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return (a[0] + t[0], a[1] + t[1], a[2] + t[2]) + tuple(c / n for c in q)


def pl_inv(a):
    qi = _qinv(a[3:])
    t = _qrot(qi, a[:3])
    return (-t[0], -t[1], -t[2]) + qi


def pl_same(a, b):
    if any(abs(x - y) > POS_TOL for x, y in zip(a[:3], b[:3])):
        return False
    qa, qb = a[3:], b[3:]
    d = abs(sum(x * y for x, y in zip(qa, qb)))          # q and -q are one rotation
    return d > 1.0 - ROT_TOL


def pl_tuple(pl):
    """FreeCAD Placement (or a 7-tuple) -> 7-tuple."""
    if pl is None:
        return IDENTITY
    if isinstance(pl, (tuple, list)):
        return tuple(float(c) for c in pl)
    b, q = pl.Base, pl.Rotation.Q
    return (float(b.x), float(b.y), float(b.z)) + tuple(float(c) for c in q)


def _pl_value(t, like=None):
    """7-tuple -> what the object's Placement takes (a FreeCAD Placement
    when FreeCAD is there and `like` is one)."""
    if like is not None and isinstance(like, (tuple, list)):
        return tuple(t)
    try:
        import FreeCAD
        return FreeCAD.Placement(FreeCAD.Vector(*t[:3]), FreeCAD.Rotation(*t[3:]))
    except ImportError:
        return tuple(t)


# ===================================================================
# R340 hand-edit overrides
# ===================================================================
def is_hardware(o):
    """Atech board / module / cable (their models are CC BY-NC)."""
    return bool(getattr(o, "AtechRole", None) or getattr(o, "AtechCableModule", None))


def agent_parts(doc):
    """The current build's agent-built bodies (not Atech hardware, not a
    previous build on its way out)."""
    if doc is None:
        return []
    return [o for o in doc.Objects
            if getattr(o, "AtechAgentBuilt", False) and not is_hardware(o)
            and PREVIOUS not in (getattr(o, "Label", "") or "")]


def _vo(o):
    try:
        return getattr(o, "ViewObject", None)
    except Exception:                                     # noqa: BLE001
        return None


def part_state(o):
    """{"color", "transparency", "visible", "placement"} of an object; the
    view values are None without a ViewObject (headless)."""
    vo = _vo(o)
    colour = transparency = None
    if vo is not None:
        try:
            colour = [round(float(c), 4) for c in tuple(vo.ShapeColor)[:3]]
        except Exception:                                 # noqa: BLE001
            colour = None
        try:
            transparency = int(vo.Transparency)
        except Exception:                                 # noqa: BLE001
            transparency = None
    try:
        visible = bool(o.Visibility)
    except Exception:                                     # noqa: BLE001
        visible = None
    return {"color": colour, "transparency": transparency, "visible": visible,
            "placement": list(pl_tuple(getattr(o, "Placement", None)))}


def _load(doc):
    raw = ""
    try:
        raw = getattr(doc, DOC_PROP, "") or ""
    except Exception:                                     # noqa: BLE001
        raw = ""
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        _log("AtechOverrides is not JSON: starting fresh")
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("v", 1)
    data.setdefault("parts", {})
    data.setdefault("base", {})
    return data


def _save(doc, data):
    text = json.dumps(data, sort_keys=True)
    props = getattr(doc, "PropertiesList", None)
    if props is not None and DOC_PROP not in props:
        try:
            doc.addProperty("App::PropertyString", DOC_PROP, "Atech",
                            "hand edits (colour, visibility, placement) kept across agent builds")
            try:
                doc.setEditorMode(DOC_PROP, 2)            # hidden from the property view
            except Exception:                             # noqa: BLE001
                pass
        except Exception as exc:                          # noqa: BLE001
            _log("cannot add %s: %r" % (DOC_PROP, exc))
    if getattr(doc, DOC_PROP, None) != text:
        setattr(doc, DOC_PROP, text)


def overrides(doc):
    """{label: {"color", "transparency", "visible", "move"}} recorded."""
    return _load(doc)["parts"] if doc is not None else {}


def snapshot_base(doc, labels=None):
    """Record what the build itself made (colour, visibility, placement)
    for each agent part, so later hand edits can be told apart."""
    data = _load(doc)
    for o in agent_parts(doc):
        if labels is None or o.Label in labels:
            data["base"][o.Label] = part_state(o)
    _save(doc, data)
    return data["base"]


def ensure_base(doc):
    """A document opened from disk whose parts have no recorded build
    values yet: take the current values as the build's (call on open)."""
    data = _load(doc)
    missing = [o.Label for o in agent_parts(doc) if o.Label not in data["base"]]
    if missing:
        snapshot_base(doc, set(missing))
    return missing


def _diff(state, base):
    """The fields of `state` the user changed from `base`."""
    out = {}
    if state["color"] is not None and base.get("color") is not None \
            and not _same_colour(state["color"], base["color"]):
        out["color"] = state["color"]
    if state["transparency"] is not None and base.get("transparency") is not None \
            and int(state["transparency"]) != int(base["transparency"]):
        out["transparency"] = int(state["transparency"])
    if state["visible"] is not None and base.get("visible") is not None \
            and bool(state["visible"]) != bool(base["visible"]):
        out["visible"] = bool(state["visible"])
    cur = tuple(state["placement"])
    b = tuple(base.get("placement") or IDENTITY)
    if not pl_same(cur, b):
        out["move"] = [round(c, 9) for c in pl_mul(cur, pl_inv(b))]
    return out


def capture_overrides(doc):
    """Call BEFORE each agent build: read every agent part's colour,
    transparency, visibility and placement, and record what differs from
    what the build made. A part whose values are back to the build's loses
    its override. Exploded views are put back first (R345: never recorded
    as a move). Returns the overrides."""
    if doc is None:
        return {}
    restore_exploded(doc)
    data = _load(doc)
    for o in agent_parts(doc):
        base = data["base"].get(o.Label)
        if base is None:
            continue
        d = _diff(part_state(o), base)
        old = data["parts"].get(o.Label, {})
        keep = {k: v for k, v in old.items() if k in ("t",)}
        if d:
            keep.update(d)
            keep.setdefault("t", time.time())
            data["parts"][o.Label] = keep
        else:
            data["parts"].pop(o.Label, None)
    _save(doc, data)
    return data["parts"]


def record_override(doc, obj, **fields):
    """Record a hand edit made through Atech's own UI right away (the colour
    menu): fields color=(r,g,b), transparency=int, visible=bool."""
    data = _load(doc)
    rec = data["parts"].setdefault(obj.Label, {})
    for k, v in fields.items():
        if v is None:
            continue
        if k == "color":
            rec["color"] = [round(float(c), 4) for c in tuple(v)[:3]]
        elif k == "transparency":
            rec["transparency"] = int(v)
        elif k == "visible":
            rec["visible"] = bool(v)
        else:
            raise ValueError("unknown override field %r" % k)
    rec["t"] = time.time()
    _save(doc, data)
    return rec


def clear_override(doc, label=None):
    """Forget the hand edits of one label (or all)."""
    data = _load(doc)
    if label is None:
        n = len(data["parts"])
        data["parts"] = {}
    else:
        n = 1 if data["parts"].pop(label, None) is not None else 0
    _save(doc, data)
    return n


def _apply_view(o, rec):
    vo = _vo(o)
    if vo is None:
        return []
    done = []
    if "color" in rec:
        try:
            vo.ShapeColor = tuple(float(c) for c in rec["color"][:3])
            done.append("color")
        except Exception as exc:                          # noqa: BLE001
            _log("%s colour: %r" % (o.Label, exc))
    if "transparency" in rec:                             # last (R233)
        try:
            vo.Transparency = int(rec["transparency"])
            done.append("transparency")
        except Exception as exc:                          # noqa: BLE001
            _log("%s transparency: %r" % (o.Label, exc))
    return done


def reapply_overrides(doc):
    """Call AFTER each agent build (after its colours are applied): record
    the build's own values, then put every recorded hand edit back on the
    part with the same label. Returns {label: [fields applied]}; labels the
    build did not make keep their record (the part may come back)."""
    if doc is None:
        return {}
    data = _load(doc)
    parts = agent_parts(doc)
    for o in parts:
        data["base"][o.Label] = part_state(o)
    _save(doc, data)
    applied = {}
    for o in parts:
        rec = data["parts"].get(o.Label)
        if not rec:
            continue
        done = _apply_view(o, rec)
        if "visible" in rec:
            try:
                o.Visibility = bool(rec["visible"])
                done.append("visible")
            except Exception as exc:                      # noqa: BLE001
                _log("%s visibility: %r" % (o.Label, exc))
        if "move" in rec:
            try:
                cur = getattr(o, "Placement", None)
                new = pl_mul(tuple(rec["move"]), pl_tuple(cur))
                o.Placement = _pl_value(new, cur)
                done.append("move")
            except Exception as exc:                      # noqa: BLE001
                _log("%s placement: %r" % (o.Label, exc))
        if done:
            applied[o.Label] = done
    return applied


def _move_words(move):
    t = move[:3]
    q = move[3:]
    ang = math.degrees(2 * math.acos(max(-1.0, min(1.0, abs(q[3])))))
    bits = []
    if any(abs(c) > POS_TOL for c in t):
        bits.append("moved by (%.2f, %.2f, %.2f) mm" % tuple(t))
    if ang > 0.01:
        s = math.sqrt(max(1e-12, 1 - q[3] * q[3]))
        ax = tuple((c / s) * (1 if q[3] >= 0 else -1) for c in q[:3])
        bits.append("turned %.1f deg about (%.2f, %.2f, %.2f)" % ((ang,) + ax))
    return " and ".join(bits) or "moved"


def overrides_for_brief(doc):
    """Plain lines for the agent's document brief ('' when there are none):
    what the user changed by hand, which Studio puts back after each build."""
    data = _load(doc) if doc is not None else {"parts": {}}
    if not data["parts"]:
        return ""
    present = {o.Label for o in agent_parts(doc)}
    lines = ["Hand edits the user made (Studio re-applies them after every build "
             "to the part with the same label; keep the labels to keep them):"]
    for label in sorted(data["parts"]):
        rec = data["parts"][label]
        bits = []
        if "color" in rec:
            bits.append("colour %s" % colour_name(rec["color"]))
        if "transparency" in rec:
            bits.append("transparency %d %%" % rec["transparency"])
        if "visible" in rec:
            bits.append("shown" if rec["visible"] else "hidden")
        if "move" in rec:
            bits.append(_move_words(rec["move"]))
        tail = "" if label in present else " (not in the current build)"
        lines.append("- %s: %s%s" % (json.dumps(label), ", ".join(bits) or "edited", tail))
    return "\n".join(lines)


def set_colour(doc, objs, color=None, transparency=None):
    """Colour menu action (R341): set colour / transparency on objs and
    record each as a hand edit (agent parts only - other objects simply
    keep the change, FreeCAD saves it). Returns how many were changed."""
    n = 0
    agent = {id(o) for o in agent_parts(doc)}
    for o in objs:
        rec = {}
        if color is not None:
            rec["color"] = tuple(float(c) for c in tuple(color)[:3])
        if transparency is not None:
            rec["transparency"] = max(0, min(100, int(transparency)))
        if not rec:
            continue
        done = _apply_view(o, rec)
        if not done and _vo(o) is None:
            continue
        n += 1
        if id(o) in agent:
            record_override(doc, o, **rec)
    return n


def reset_colour(doc, objs):
    """Put the build's own colour back on objs and drop their colour edits."""
    data = _load(doc)
    for o in objs:
        base = data["base"].get(getattr(o, "Label", None)) or {}
        rec = {k: base[k] for k in ("color", "transparency") if base.get(k) is not None}
        _apply_view(o, rec)
        p = data["parts"].get(o.Label)
        if p:
            p.pop("color", None)
            p.pop("transparency", None)
            if not [k for k in p if k != "t"]:
                data["parts"].pop(o.Label, None)
    _save(doc, data)


# ===================================================================
# targets (R342)
# ===================================================================
def _has_solid(o):
    try:
        sh = o.Shape
        return bool(sh.Solids) and not sh.isNull()
    except Exception:                                     # noqa: BLE001
        return False


def _is_mesh(o):
    return getattr(o, "TypeId", "") == "Mesh::Feature"


def _top_level(o):
    """Not an input of another object (a boolean's tool)."""
    try:
        return not [p for p in o.InList if not getattr(p, "TypeId", "").startswith("App::")]
    except Exception:                                     # noqa: BLE001
        return True


def _visible(o):
    try:
        return bool(o.Visibility)
    except Exception:                                     # noqa: BLE001
        return True


def export_targets(doc, scope="product", selection=None, include_atech=False):
    """(objects to export, Atech parts left out). scope 'product' / 'parts'
    = every visible top-level solid; 'selection' = the selected ones."""
    if doc is None:
        return [], []
    if scope == "selection":
        pool = list(selection or [])
    else:
        pool = [o for o in doc.Objects if _visible(o) and _top_level(o)
                and PREVIOUS not in (getattr(o, "Label", "") or "")]
    out, left = [], []
    for o in pool:
        if not (_has_solid(o) or (_is_mesh(o) and is_hardware(o))):
            continue
        if is_hardware(o) and not include_atech:
            left.append(o.Label)
            continue
        out.append(o)
    return out, left


def object_colour(o, colours=None):
    """(rgb, transparency) shown for o: its ViewObject, else `colours`
    {label: (rgb, transparency)} (headless), else the recorded override."""
    vo = _vo(o)
    if vo is not None:
        try:
            return tuple(float(c) for c in tuple(vo.ShapeColor)[:3]), int(vo.Transparency)
        except Exception:                                 # noqa: BLE001
            pass
    if colours and o.Label in colours:
        c, t = colours[o.Label]
        return tuple(c)[:3], int(t or 0)
    doc = getattr(o, "Document", None)
    if doc is not None:
        data = _load(doc)
        rec = data["parts"].get(o.Label) or {}
        base = data["base"].get(o.Label) or {}
        c = rec.get("color") or base.get("color")
        if c:
            return tuple(c), int(rec.get("transparency", base.get("transparency") or 0) or 0)
    return None, 0


# ===================================================================
# meshes and writers (R342)
# ===================================================================
def deviation(name):
    for n, lin, ang in DEVIATIONS:
        if n.lower() == str(name).lower():
            return lin, ang
    raise ValueError("unknown mesh quality %r (Draft, Fine or Ultra)" % (name,))


def _mesh_ok(m, want):
    """(good, relative volume error): closed, oriented, manifold and its
    volume near the exact solid's."""
    try:
        vol = float(m.Volume)
    except Exception:                                     # noqa: BLE001
        return False, 1.0
    err = abs(vol - want) / want if want > 0 else 0.0
    try:
        good = bool(m.isSolid()) and not m.hasNonManifolds() and vol > 0
    except Exception:                                     # noqa: BLE001
        good = vol > 0
    return good, err


#: R342 MEASURED (toy car, FreeCAD 1.1.3): BRepMesh at 0.02 mm / 0.2 rad
#: left holes in the five-window rims (open mesh, 39-95 % of the volume
#: missing); 0.02 / 0.5 rad and 0.01 / 0.1 rad meshed them closed. So a mesh
#: is checked and re-made with other settings (never coarser than asked).
MESH_RETRIES = ((1.0, 1.0), (1.0, 2.5), (0.5, 0.5), (0.75, 1.5), (0.5, 2.5), (0.35, 1.0))
MESH_VOLUME_TOL = 0.02


def shape_mesh(shape, quality=DEFAULT_DEVIATION, report=None):
    """A closed Mesh.Mesh of a world-placed shape at the preset deviation
    (or finer: see MESH_RETRIES). `report` (a dict) gets "mesh_retries" and
    "mesh_ok"."""
    import Mesh
    import MeshPart
    lin, ang = deviation(quality)
    want = abs(float(shape.Volume)) if shape.Solids else 0.0
    best = None
    for k, (fl, fa) in enumerate(MESH_RETRIES):
        s = shape.cleaned() if hasattr(shape, "cleaned") else shape.copy()
        m = Mesh.Mesh(MeshPart.meshFromShape(Shape=s, LinearDeflection=lin * fl,
                                             AngularDeflection=min(0.5, ang * fa),
                                             Relative=False))
        good, err = _mesh_ok(m, want) if want else (True, 0.0)
        if good and err <= MESH_VOLUME_TOL:
            if report is not None:
                report["mesh_retries"] = k
                report["mesh_ok"] = True
            return m
        if best is None or (good, -err) > (best[1], -best[2]):
            best = (m, good, err)
    _log("mesh of a %.1f mm3 solid stays imperfect (error %.2f %%)" % (want, 100 * best[2]))
    if report is not None:
        report["mesh_retries"] = len(MESH_RETRIES)
        report["mesh_ok"] = False
    return best[0]


def object_mesh(o, quality=DEFAULT_DEVIATION):
    """World-space mesh of a Part or Mesh object."""
    if _is_mesh(o):
        # MEASURED (freecadcmd 1.1.3): a Mesh::Feature's Mesh carries the
        # object's Placement; Topology gives the points already placed.
        import Mesh
        pts, tris = o.Mesh.Topology
        out = Mesh.Mesh()
        out.addFacets([[pts[i] for i in t] for t in tris])
        return out
    return shape_mesh(o.Shape, quality)


def _mesh_arrays(m):
    pts, tris = m.Topology
    return [(p.x, p.y, p.z) for p in pts], [tuple(int(i) for i in t) for t in tris]


def mesh_volume(points, tris):
    """Signed volume of a closed triangle mesh (divergence theorem), mm3."""
    v = 0.0
    for a, b, c in tris:
        p, q, r = points[a], points[b], points[c]
        v += (p[0] * (q[1] * r[2] - q[2] * r[1]) - p[1] * (q[0] * r[2] - q[2] * r[0])
              + p[2] * (q[0] * r[1] - q[1] * r[0]))
    return v / 6.0


def write_stl(items, path):
    """items: [(name, Mesh.Mesh, colour, transparency)] -> one binary STL."""
    import Mesh
    out = Mesh.Mesh()
    for _name, m, _c, _t in items:
        out.addMesh(m)
    out.write(path)
    return path


def _xml(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def write_3mf(items, path):
    """items: [(name, Mesh.Mesh | (points, tris), rgb | None, transparency)]
    -> a 3MF file with one object per item and its colour as a 3MF base
    material (displaycolor #RRGGBBAA), which Bambu Studio, PrusaSlicer and
    Orca read as the object's colour."""
    mats, objs = [], []
    for name, m, c, t in items:
        pts, tris = m if isinstance(m, tuple) else _mesh_arrays(m)
        pindex = None
        if c is not None:
            alpha = int(round(255 * (1 - max(0, min(100, int(t or 0))) / 100.0)))
            mats.append('<base name="%s" displaycolor="%s%02X"/>' % (
                _xml(name), hex_colour(c).upper(), alpha))
            pindex = len(mats) - 1
        objs.append((name, pts, tris, pindex))
    buf = io.StringIO()
    w = buf.write
    w('<?xml version="1.0" encoding="UTF-8"?>\n')
    w('<model unit="millimeter" xml:lang="en-US" '
      'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n')
    w('<metadata name="Application">Atech Atelier</metadata>\n<resources>\n')
    if mats:
        w('<basematerials id="1">\n%s\n</basematerials>\n' % "\n".join(mats))
    for k, (name, pts, tris, pindex) in enumerate(objs):
        oid = k + 2
        attrs = ' pid="1" pindex="%d"' % pindex if pindex is not None else ""
        w('<object id="%d" type="model" name="%s"%s>\n<mesh>\n<vertices>\n'
          % (oid, _xml(name), attrs))
        for p in pts:
            w('<vertex x="%.6f" y="%.6f" z="%.6f"/>\n' % p)
        w('</vertices>\n<triangles>\n')
        for a, b, c in tris:
            w('<triangle v1="%d" v2="%d" v3="%d"/>\n' % (a, b, c))
        w('</triangles>\n</mesh>\n</object>\n')
    w('</resources>\n<build>\n')
    for k in range(len(objs)):
        w('<item objectid="%d"/>\n' % (k + 2))
    w('</build>\n</model>\n')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType='
                   '"application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="model" ContentType='
                   '"application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type='
                   '"http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
                   '</Relationships>')
        z.writestr("3D/3dmodel.model", buf.getvalue())
    return path


def read_3mf(path):
    """[{"name", "color" (#RRGGBBAA or None), "points", "tris"}] of a 3MF
    (what write_3mf writes; enough to check a file, not a full reader)."""
    import xml.etree.ElementTree as ET
    ns = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    mats = {}
    for bm in root.iter(ns + "basematerials"):
        mats[bm.get("id")] = [b.get("displaycolor") for b in bm.findall(ns + "base")]
    out = []
    for ob in root.iter(ns + "object"):
        mesh = ob.find(ns + "mesh")
        pts = [(float(v.get("x")), float(v.get("y")), float(v.get("z")))
               for v in mesh.find(ns + "vertices")]
        tris = [(int(t.get("v1")), int(t.get("v2")), int(t.get("v3")))
                for t in mesh.find(ns + "triangles")]
        col = None
        if ob.get("pid") in mats:
            col = mats[ob.get("pid")][int(ob.get("pindex", 0))]
        out.append({"name": ob.get("name"), "color": col, "points": pts, "tris": tris})
    return out


#: R342 MEASURED (toy car chassis, FreeCAD 1.1.3 / OCC): exportStep wrote
#: 149 of the solid's 159 faces - the 8 SurfaceOfExtrusion faces (and 2
#: planes bounded by them) were dropped, so the file read back as 5 open
#: shells and no solid (64 % of the volume "lost"). Such surfaces are turned
#: into B-splines first (toNurbs: 0.006 % volume change) and the written
#: face count is checked against the solids'.
STEP_RISKY_SURFACES = ("SurfaceOfExtrusion", "SurfaceOfRevolution", "OffsetSurface")


def step_safe(shape):
    """shape, or a B-spline copy when it has a surface kind the STEP
    writer drops."""
    try:
        if any(f.Surface.__class__.__name__ in STEP_RISKY_SURFACES for f in shape.Faces):
            return shape.toNurbs()
    except Exception as exc:                              # noqa: BLE001
        _log("step_safe: %r" % (exc,))
    return shape


def step_face_count(path):
    with open(path, "r", encoding="latin-1") as fh:
        return len(re.findall(r"=\s*ADVANCED_FACE\s*\(", fh.read()))


def _step_complete(path, want):
    """Every face of the solids made it into the file."""
    return step_face_count(path) == want


def write_step(entries, path):
    """entries: [(name, shape, obj or None)]. Every part as its own named
    solid; in the GUI with every obj present, unmoved and safe, FreeCAD's
    ImportGui keeps the colours too. The file is checked: as many faces
    written as the solids have, else it is written again as B-splines."""
    import Part
    shapes = [step_safe(e[1]) for e in entries]
    want = sum(len(s.Faces) for s in shapes)
    objs = [e[2] for e in entries]
    plain = all(o is not None for o in objs) and all(
        s is e[1] for s, e in zip(shapes, entries))
    wrote = False
    try:
        import FreeCAD
        if plain and FreeCAD.GuiUp:
            import ImportGui
            ImportGui.export(objs, path)
            wrote = True
        else:
            import Import
            active = FreeCAD.ActiveDocument
            tmp = FreeCAD.newDocument("AtechStepExport", hidden=True)
            try:
                feats = []
                for (name, _s, _o), s in zip(entries, shapes):
                    f = tmp.addObject("Part::Feature", "Part")
                    f.Label = name
                    f.Shape = s
                    feats.append(f)
                Import.export(feats, path)
                wrote = True
            finally:
                FreeCAD.closeDocument(tmp.Name)
                if active is not None:
                    try:
                        FreeCAD.setActiveDocument(active.Name)
                    except Exception:                     # noqa: BLE001
                        pass
    except Exception as exc:                              # noqa: BLE001
        _log("STEP via Import failed, writing a compound: %r" % (exc,))
    if not wrote:
        comp = shapes[0] if len(shapes) == 1 else Part.makeCompound(shapes)
        comp.exportStep(path)
    if not _step_complete(path, want):
        _log("STEP wrote %d of %d faces: writing B-splines" % (step_face_count(path), want))
        nurbs = [s.toNurbs() for s in shapes]
        comp = nurbs[0] if len(nurbs) == 1 else Part.makeCompound(nurbs)
        comp.exportStep(path)
    return path


def safe_name(label):
    s = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(label)).strip(" .")
    return s or "part"


# ===================================================================
# R343 print prep
# ===================================================================
def _sample_points(shape):
    pts = [tuple(v.Point) for v in shape.Vertexes]
    try:
        p, _t = (shape.cleaned() if hasattr(shape, "cleaned") else shape.copy()).tessellate(0.5)
        pts += [(q.x, q.y, q.z) for q in p]
    except Exception:                                     # noqa: BLE001
        pass
    return pts


def flat_faces(shape, tol=0.02):
    """[(area, (nx, ny, nz) outward, d)] of the planar SUPPORTING planes:
    the part can rest on them (nothing of it lies beyond the plane), with
    coplanar faces' areas added. Largest first."""
    pts = _sample_points(shape)
    groups = []
    for f in shape.Faces:
        try:
            if f.Surface.__class__.__name__ != "Plane":
                continue
            u0, u1, v0, v1 = f.ParameterRange
            n = f.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        except Exception:                                 # noqa: BLE001
            continue
        nn = (n.x, n.y, n.z)
        p0 = f.Vertexes[0].Point if f.Vertexes else f.CenterOfMass
        for sgn in (1, -1):
            nv = tuple(sgn * c for c in nn)
            d = nv[0] * p0.x + nv[1] * p0.y + nv[2] * p0.z
            if all(nv[0] * q[0] + nv[1] * q[1] + nv[2] * q[2] <= d + tol for q in pts):
                for g in groups:
                    if sum(a * b for a, b in zip(g[1], nv)) > 1 - 1e-6 and abs(g[2] - d) < tol:
                        g[0] += f.Area
                        break
                else:
                    groups.append([f.Area, nv, d])
                break
    groups.sort(key=lambda g: -g[0])
    return [(a, n, d) for a, n, d in groups]


def _rotation_to_down(n):
    """Quaternion (x, y, z, w) turning unit vector n onto (0, 0, -1)."""
    t = (0.0, 0.0, -1.0)
    dot = sum(a * b for a, b in zip(n, t))
    if dot > 1 - 1e-9:
        return (0.0, 0.0, 0.0, 1.0)
    if dot < -1 + 1e-9:
        return (1.0, 0.0, 0.0, 0.0)                       # 180 deg about X
    ax = (n[1] * t[2] - n[2] * t[1], n[2] * t[0] - n[0] * t[2], n[0] * t[1] - n[1] * t[0])
    s = math.sqrt(2 * (1 + dot))
    return (ax[0] / s, ax[1] / s, ax[2] / s, s / 2)


def orient_for_print(shape):
    """(laid-flat copy of shape on z = 0 centred on x = y = 0, info). The
    largest flat side the part can rest on goes down; a part with none
    keeps its orientation and just drops onto the bed."""
    import FreeCAD
    faces = flat_faces(shape)
    q = (0.0, 0.0, 0.0, 1.0)
    area = 0.0
    if faces:
        area, n, _d = faces[0]
        # the side it already stands on wins when it is nearly as big:
        # no needless turn for a part the agent modelled flat-bottomed
        down = [f for f in faces if f[1][2] < -1 + 1e-6]
        if down and down[0][0] >= KEEP_BOTTOM_SHARE * area:
            area, n, _d = down[0]
        q = _rotation_to_down(n)
    s = shape.copy()
    s.Placement = FreeCAD.Placement(FreeCAD.Vector(), FreeCAD.Rotation(*q)).multiply(s.Placement)
    bb = s.BoundBox
    s.translate(FreeCAD.Vector(-(bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2, -bb.ZMin))
    ang = math.degrees(2 * math.acos(max(-1.0, min(1.0, abs(q[3])))))
    return s, {"flat_face_mm2": round(area, 1), "turned_deg": round(ang, 1),
               "rotation": list(q)}


def arrange_on_bed(shapes, gap=5.0):
    """Lay several laid-flat shapes side by side in rows (no overlap)."""
    import FreeCAD
    if not shapes:
        return []
    total = sum((s.BoundBox.XLength + gap) * (s.BoundBox.YLength + gap) for s in shapes)
    row_w = max(max(s.BoundBox.XLength for s in shapes), math.sqrt(total))
    out, x, y, row_h = [], 0.0, 0.0, 0.0
    for s in shapes:
        bb = s.BoundBox
        if x > 0 and x + bb.XLength > row_w:
            x, y, row_h = 0.0, y + row_h + gap, 0.0
        c = s.copy()
        c.translate(FreeCAD.Vector(x - bb.XMin, y - bb.YMin, 0))
        out.append(c)
        x += bb.XLength + gap
        row_h = max(row_h, bb.YLength)
    return out


def overhangs(mesh_or_arrays, angle=OVERHANG_DEG, bed_tol=BED_TOL):
    """(overhang area mm2, total area mm2) of a mesh as it will print:
    facets facing down steeper than `angle` from vertical that are not on
    the bed (z = 0)."""
    if isinstance(mesh_or_arrays, tuple):
        pts, tris = mesh_or_arrays
    else:
        pts, tris = _mesh_arrays(mesh_or_arrays)
    lim = -math.cos(math.radians(angle))
    over = tot = 0.0
    for a, b, c in tris:
        p, q, r = pts[a], pts[b], pts[c]
        u = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
        v = (r[0] - p[0], r[1] - p[1], r[2] - p[2])
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        if ln <= 0:
            continue
        area = ln / 2
        tot += area
        if n[2] / ln < lim and max(p[2], q[2], r[2]) > bed_tol:
            over += area
    return over, tot


def _geom():
    if KIT_DIR not in sys.path:
        sys.path.append(KIT_DIR)
    import atech_geom
    return atech_geom


def print_report(objs, quality="Draft", walls=True, wall_budget_s=6.0):
    """R343: per part, how it lies on the bed and what to watch.
    [{"label", "flat_face_mm2", "turned_deg", "overhang_mm2", "overhang_pct",
      "thin_mm", "flags": [plain sentences]}]."""
    rows, shapes = [], []
    for o in objs:
        if not _has_solid(o):
            continue
        s, info = orient_for_print(o.Shape)
        m = shape_mesh(s, quality)
        over, tot = overhangs(m)
        row = {"label": o.Label, "overhang_mm2": round(over, 1),
               "overhang_pct": round(100.0 * over / tot, 1) if tot else 0.0,
               "thin_mm": None, "flags": []}
        row.update(info)
        if not info["flat_face_mm2"]:
            row["flags"].append("No flat side to rest on: it needs supports or a brim.")
        if over > max(OVERHANG_FLAG_MM2, OVERHANG_FLAG_SHARE * tot):
            row["flags"].append("Overhangs steeper than 45 deg: %.0f mm2 needs supports."
                                % over)
        rows.append(row)
        shapes.append({"label": o.Label, "shape": s})
    if walls and shapes:
        try:
            res = _geom().thin_walls(shapes, budget_s=wall_budget_s)
            by = {r["label"]: r for r in res.get("parts", [])}
            for row in rows:
                r = by.get(row["label"])
                if r and r.get("mm") is not None:
                    row["thin_mm"] = round(float(r["mm"]), 2)
                    if r["mm"] < MIN_WALL_MM:
                        row["flags"].append("Thinnest wall %.2f mm, under 0.8 mm: it may not print."
                                            % r["mm"])
        except Exception as exc:                          # noqa: BLE001
            _log("wall probe: %r" % (exc,))
    return rows


# ===================================================================
# R342 export
# ===================================================================
def export_for_print(doc, path, fmt="3MF", scope="product", quality=DEFAULT_DEVIATION,
                     include_atech=False, lay_flat=None, selection=None, colours=None):
    """Write the export. `path` is a file, or a folder for scope 'parts'.
    lay_flat (default: on for 'parts') lays each part on its largest flat
    side; several laid-flat parts in one file are set side by side.
    Returns {"files", "parts", "left_out" (Atech labels), "skipped",
    "volumes" {label: mm3 of the exact solid}}."""
    fmt = str(fmt).upper()
    if fmt not in FORMATS:
        raise ValueError("format must be one of %s" % ", ".join(FORMATS))
    deviation(quality)
    # R720: a print is of the product, never of an exploded picture of it
    restore_exploded(doc)
    if lay_flat is None:
        lay_flat = scope == "parts"
    objs, left = export_targets(doc, scope, selection, include_atech)
    if not objs:
        raise ValueError("Nothing to export: no visible solid parts%s."
                         % (" in the selection" if scope == "selection" else ""))
    entries, skipped = [], []
    for o in objs:
        c, t = object_colour(o, colours)
        if _is_mesh(o):
            if fmt == "STEP":
                skipped.append(o.Label)
                continue
            entries.append({"label": o.Label, "obj": o, "shape": None, "colour": c, "t": t})
            continue
        shape = o.Shape.copy()
        moved = False
        if lay_flat:
            shape, _info = orient_for_print(shape)
            moved = True
        entries.append({"label": o.Label, "obj": None if moved else o, "shape": shape,
                        "colour": c, "t": t})
    if lay_flat and scope != "parts":
        placed = arrange_on_bed([e["shape"] for e in entries if e["shape"] is not None])
        k = 0
        for e in entries:
            if e["shape"] is not None:
                e["shape"] = placed[k]
                k += 1
    ext = {"STL": ".stl", "3MF": ".3mf", "STEP": ".step"}[fmt]

    def write(group, out_path):
        if fmt == "STEP":
            write_step([(e["label"], e["shape"], e["obj"]) for e in group], out_path)
        else:
            items = []
            for e in group:
                m = (object_mesh(e["obj"]) if e["shape"] is None
                     else shape_mesh(e["shape"], quality))
                items.append((e["label"], m, e["colour"], e["t"]))
            (write_stl if fmt == "STL" else write_3mf)(items, out_path)
        return out_path

    files = []
    if scope == "parts":
        os.makedirs(path, exist_ok=True)
        used = set()
        for e in entries:
            base = safe_name(e["label"])
            name, k = base, 2
            while name.lower() in used:
                name, k = "%s_%d" % (base, k), k + 1
            used.add(name.lower())
            files.append(write([e], os.path.join(path, name + ext)))
    else:
        if not path.lower().endswith(ext):
            path += ext
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)   # R515
        files.append(write(entries, path))
    vols = {}
    for e in entries:
        if e["shape"] is not None:
            vols[e["label"]] = float(e["shape"].Volume)
    return {"files": files, "parts": [e["label"] for e in entries], "left_out": left,
            "skipped": skipped, "volumes": vols, "format": fmt, "quality": quality}


def reimport_volume(path):
    """Volume (mm3) of an exported file read back: STL/3MF through
    FreeCAD's Mesh reader, STEP through Part."""
    p = path.lower()
    if p.endswith(".step") or p.endswith(".stp"):
        import Part
        s = Part.Shape()
        s.read(path)
        return float(sum(abs(x.Volume) for x in s.Solids))
    import Mesh
    return float(abs(Mesh.Mesh(path).Volume))


# ===================================================================
# R344 slicers
# ===================================================================
def find_slicers(roots=None):
    """[{"name", "path"}] of the slicers installed (macOS app bundles)."""
    if roots is None:
        roots = ["/Applications", os.path.expanduser("~/Applications")]
    out = []
    for name, bundles in SLICERS:
        for r in roots:
            hit = next((os.path.join(r, b) for b in bundles
                        if os.path.isdir(os.path.join(r, b))), None)
            if hit:
                out.append({"name": name, "path": hit})
                break
    return out


def open_in_slicer(files, slicer, runner=None):
    """Hand exported files to a slicer app: `open -a <app> files...`.
    Returns the command run."""
    if isinstance(files, str):
        files = [files]
    app = slicer["path"] if isinstance(slicer, dict) else slicer
    cmd = ["open", "-a", app] + list(files)
    (runner or (lambda c: subprocess.Popen(c)))(cmd)
    return cmd


# ===================================================================
# R345 exploded view
# ===================================================================
_EXPLODERS = {}


class Exploder(object):
    """Pushes parts away from the product's middle. DISPLAY ONLY: every
    placement it changes is kept and put back by restore() / close (and by
    capture_overrides before a build, so a rebuild never records it)."""

    SPREAD = 1.2                   # at 1.0 each part is this many times as far out

    def __init__(self, doc, objs=None):
        self.doc = doc
        # R720: one exploded view per document. A second one would take the
        # first one's pulled-apart placements as "where the parts belong"
        # (and that is what a save then wrote), so put the first one back.
        old = _EXPLODERS.get(id(doc))
        if old is not None and old is not self:
            old.restore()
        if objs is None:
            objs = [o for o in doc.Objects if _visible(o) and _top_level(o)
                    and (_has_solid(o) or _is_mesh(o))
                    and getattr(o, "AtechRole", None) != "board"]
        self.objs = list(objs)
        #: R720: by Name - an object deleted meanwhile is skipped, never used
        self.names = [o.Name for o in self.objs]
        self.saved = {o.Name: o.Placement for o in self.objs}
        self.saved = {k: (v.copy() if hasattr(v, "copy") else v) for k, v in self.saved.items()}
        #: R720: the placement this exploder last gave each part. A part
        #: whose placement differs from it was moved by someone else (a hand
        #: edit or Undo) while apart, and restore() keeps that move.
        self.applied = {}
        self.factor = 0.0
        boxes = [self._centre(o) for o in self.objs]
        self.centres = boxes
        pts = [c for c in boxes if c is not None]
        if pts:
            self.middle = tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))
            span = max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))
        else:
            self.middle, span = (0.0, 0.0, 0.0), 0.0
        self.span = max(span, 10.0)
        _EXPLODERS[id(doc)] = self

    @staticmethod
    def _centre(o):
        try:
            bb = o.Shape.BoundBox if not _is_mesh(o) else o.Mesh.BoundBox
            return ((bb.XMin + bb.XMax) / 2, (bb.YMin + bb.YMax) / 2, (bb.ZMin + bb.ZMax) / 2)
        except Exception:                                 # noqa: BLE001
            return None

    def offset(self, k, factor):
        c = self.centres[k]
        if c is None:
            return (0.0, 0.0, 0.0)
        d = tuple(c[i] - self.middle[i] for i in range(3))
        if math.sqrt(sum(x * x for x in d)) < 1e-6:
            return (0.0, 0.0, 0.3 * self.span * factor)
        return tuple(x * self.SPREAD * factor for x in d)

    def _live(self):
        """(k, name, object) of each part still in the document."""
        out = []
        for k, name in enumerate(self.names):
            try:
                o = self.doc.getObject(name)
            except Exception:                             # noqa: BLE001
                o = None
            if o is not None:
                out.append((k, name, o))
        return out

    def _moved(self, name, o):
        """True when `o` is no longer where this exploder put it."""
        was = self.applied.get(name)
        if was is None:
            return False
        try:
            return not o.Placement.isSame(was, 1e-7)
        except Exception:                                 # noqa: BLE001
            return False

    def absorb(self, assembled_space=False):
        """R720: take in moves made by someone else while apart, so they
        survive. A hand edit (Edit shapes, the property editor) is made on
        the part where it shows, so its own offset comes off; Undo / Redo
        put back a value from before, which is already where the part
        belongs (assembled_space=True)."""
        import FreeCAD
        for k, name, o in self._live():
            if not self._moved(name, o):
                continue
            pl = o.Placement.copy()
            if not assembled_space:
                pl.Base = pl.Base - FreeCAD.Vector(*self.offset(k, self.factor))
            self.saved[name] = pl
            self.applied.pop(name, None)

    def set_factor(self, factor):
        import FreeCAD
        self.absorb()
        self.factor = max(0.0, min(1.0, float(factor)))
        for k, name, o in self._live():
            base = self.saved[name]
            off = self.offset(k, self.factor)
            pl = base.copy()
            pl.Base = pl.Base + FreeCAD.Vector(*off)
            o.Placement = pl
            self.applied[name] = pl.copy()
        try:
            self.doc.recompute()
        except Exception:                                 # noqa: BLE001
            pass

    def restore(self):
        self.absorb()
        for _k, name, o in self._live():
            try:
                o.Placement = self.saved[name]
            except Exception as exc:                      # noqa: BLE001
                _log("restore %s: %r" % (name, exc))
        self.factor = 0.0
        self.applied = {}
        if _EXPLODERS.get(id(self.doc)) is self:
            _EXPLODERS.pop(id(self.doc), None)


def restore_exploded(doc=None):
    """Put back every exploded view (of doc, or all). Call before saving."""
    for key, ex in list(_EXPLODERS.items()):
        if doc is None or ex.doc is doc:
            ex.restore()
            _explode_changed(ex.doc, 0.0)


def explode_after_undo(doc):
    """R720: Undo / Redo while apart: the values they put back are where
    the parts belong; keep them and show the parts apart again from there."""
    ex = _EXPLODERS.get(id(doc)) if doc is not None else None
    if ex is None:
        return
    ex.absorb(assembled_space=True)
    ex.set_factor(ex.factor)


def forget_exploded(doc):
    """R720: doc is closing - drop its exploded view (keyed by id(doc), so
    a later document could otherwise find it)."""
    for key, ex in list(_EXPLODERS.items()):
        if ex.doc is doc:
            _EXPLODERS.pop(key, None)


# R701: one exploded state per document that the view-bar toggle, the
# Show and hide slider and the E key share.
#: How far apart a one-click explode puts the parts (0..1).
DEFAULT_EXPLODE = 0.6
_LAST_EXPLODE = {"factor": DEFAULT_EXPLODE}
_EXPLODE_LISTENERS = []


def on_explode_changed(fn):
    """Call fn(doc, factor) whenever an exploded view changes."""
    if fn not in _EXPLODE_LISTENERS:
        _EXPLODE_LISTENERS.append(fn)


def _explode_changed(doc, factor):
    for fn in list(_EXPLODE_LISTENERS):
        try:
            fn(doc, factor)
        except Exception as exc:                          # noqa: BLE001
            _log("explode listener: %r" % (exc,))
            _EXPLODE_LISTENERS.remove(fn)


def explode_amount(doc):
    """How far apart doc's parts are now (0: assembled)."""
    ex = _EXPLODERS.get(id(doc)) if doc is not None else None
    return ex.factor if ex is not None else 0.0


def set_explode(doc, factor):
    """Explode doc to `factor` (0..1); 0 puts every part back. Display
    only, as Exploder."""
    if doc is None:
        return 0.0
    factor = max(0.0, min(1.0, float(factor)))
    ex = _EXPLODERS.get(id(doc))
    if factor <= 0.0:
        if ex is not None:
            ex.restore()
            try:
                doc.recompute()
            except Exception:                             # noqa: BLE001
                pass
        _explode_changed(doc, 0.0)
        return 0.0
    if ex is None:
        ex = Exploder(doc)
    ex.set_factor(factor)
    _LAST_EXPLODE["factor"] = factor
    _explode_changed(doc, factor)
    return factor


def toggle_explode(doc):
    """Apart at the last amount used, or back together. Returns the new
    amount."""
    if explode_amount(doc) > 0.0:
        return set_explode(doc, 0.0)
    return set_explode(doc, _LAST_EXPLODE["factor"] or DEFAULT_EXPLODE)


# ===================================================================
# R346 BOM
# ===================================================================
_MODULE_NAMES = {}


def module_name(key):
    """R515: an Atech module's name as the library and the Modules page say
    it ("DC Motor", "USB-C"), not the slug title-cased ("Dc motor"); the
    slug's display_name() when the library has none."""
    key = str(key or "")
    if key not in _MODULE_NAMES:
        name = None
        try:
            from . import projects
            d = projects._builder_dir()
            if d is not None:
                if d not in sys.path:
                    sys.path.insert(0, d)
                import atech_modules
                name = (atech_modules.spec(key) or {}).get("display_name")
        except Exception:                                 # noqa: BLE001
            name = None
        _MODULE_NAMES[key] = name or display_name(key)
    return _MODULE_NAMES[key]


def bom(doc, density=PLA_DENSITY, colours=None):
    """{"printed": [{"part", "count", "names", "volume_cm3", "mass_g",
    "colour"}], "hardware": [{"kind", "name", "ports", "length_mm"}]}.
    Identical printed parts (same volume, area and colour) are one row."""
    printed, hardware, groups = [], [], {}
    if doc is None:
        return {"printed": printed, "hardware": hardware}
    for o in doc.Objects:
        if PREVIOUS in (getattr(o, "Label", "") or ""):
            continue
        role = getattr(o, "AtechRole", None)
        if role == "board":
            hardware.append({"kind": "Board", "name": "Atech board", "ports": "",
                             "length_mm": None, "label": o.Label})
            continue
        if role == "module":
            ports = list(getattr(o, "AtechPorts", []) or [])
            hardware.append({"kind": "Module",
                             "name": module_name(getattr(o, "AtechModule", "") or o.Label),
                             "ports": ", ".join(str(p) for p in ports),
                             "length_mm": None, "label": o.Label})
            continue
        if getattr(o, "AtechCableModule", None):
            mod = doc.getObject(o.AtechCableModule) if hasattr(doc, "getObject") else None
            name = module_name(getattr(mod, "AtechModule", "") or o.AtechCableModule)
            hardware.append({"kind": "Cable", "name": "Cable to %s" % name,
                             "ports": str(int(getattr(o, "AtechCablePort", 0) or 0)),
                             "length_mm": round(float(getattr(o, "AtechCableLength", 0) or 0), 1),
                             "label": o.Label})
            continue
        if not (_has_solid(o) and _top_level(o)):
            continue
        vol = float(o.Shape.Volume)
        c, _t = object_colour(o, colours)
        key = (round(vol, 1), round(float(o.Shape.Area), 0), hex_colour(c) if c else "")
        if key in groups:
            groups[key]["count"] += 1
            groups[key]["names"].append(o.Label)
            continue
        row = {"part": re.sub(r"[_ ]?(\d+|[LR]|[FR][LR])$", "", o.Label) or o.Label,
               "count": 1, "names": [o.Label], "volume_cm3": round(vol / 1000.0, 2),
               "mass_g": round(vol / 1000.0 * density, 1),
               "colour": colour_name(c) if c else ""}
        groups[key] = row
        printed.append(row)
    for row in printed:
        if row["count"] == 1:
            row["part"] = row["names"][0]
    order = {"Board": 0, "Module": 1, "Cable": 2}
    hardware.sort(key=lambda r: (order[r["kind"]], r["ports"]))
    return {"printed": printed, "hardware": hardware}


def bom_csv(b, density=PLA_DENSITY):
    """The BOM as CSV text (one table: printed parts, then hardware)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Section", "Item", "Count", "Volume (cm3)",
                "Mass PLA %.2f g/cm3 (g)" % density, "Colour", "Ports", "Length (mm)",
                "Objects"])
    for r in b["printed"]:
        w.writerow(["Printed", r["part"], r["count"], "%.2f" % r["volume_cm3"],
                    "%.1f" % r["mass_g"], r["colour"], "", "", "; ".join(r["names"])])
    for r in b["hardware"]:
        w.writerow(["Atech hardware", r["name"], 1, "", "", "", r["ports"],
                    "" if r["length_mm"] is None else "%.1f" % r["length_mm"], r["label"]])
    return buf.getvalue()


def write_bom_csv(doc, path, density=PLA_DENSITY):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(bom_csv(bom(doc, density), density))
    return path


# ===================================================================
# Qt widgets (imported lazily)
# ===================================================================
#: Icons added for these buttons. SOURCE AND LICENCE as style.PATHS: path
#: data from Lucide (https://github.com/lucide-icons/lucide, ISC; palette,
#: download, maximize-2, image, list), the licence texts ship with the app.
ICONS = {
    "palette": '<circle cx="13.5" cy="6.5" r="1" fill="{c}"/><circle cx="17.5" cy="10.5" r="1" '
               'fill="{c}"/><circle cx="8.5" cy="7.5" r="1" fill="{c}"/><circle cx="6.5" '
               'cy="12.5" r="1" fill="{c}"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.9 0 '
               '1.6-.7 1.6-1.7 0-.4-.2-.8-.4-1.1-.3-.3-.4-.7-.4-1.1a1.6 1.6 0 0 1 1.7-1.7h2'
               'c3 0 5.5-2.5 5.5-5.5C22 6 17.5 2 12 2z"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/>'
                '<path d="M12 15V3"/>',
    "explode": '<path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/>'
               '<path d="M3 21l7-7"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/>'
             '<path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
    "list": '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/>'
            '<path d="M3 12h.01"/><path d="M3 18h.01"/>',
}


def icon(name, color, size=16):
    """A QIcon of one of ICONS, drawn like style.icon()."""
    from PySide6 import QtCore, QtGui, QtSvg
    from . import style
    body = ICONS[name].replace("{c}", color)
    svg = style._SVG.format(c=color, w=2.0, body=body).encode("utf-8")
    ren = QtSvg.QSvgRenderer(QtCore.QByteArray(svg))
    scale = style.pixel_scale()
    img = QtGui.QImage(size * scale, size * scale, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    ren.render(p)
    p.end()
    pm = QtGui.QPixmap.fromImage(img)
    pm.setDevicePixelRatio(scale)
    return QtGui.QIcon(pm)


DIALOG_QSS = """
QDialog#AtechTool {{ background: {panel}; color: {text}; font-family: {UI}; font-size: 13px; }}
#AtechTool QLabel {{ color: {text}; }}
#AtechTool QLabel#ToolMuted {{ color: {muted}; font-size: 12px; }}
#AtechTool QLabel#ToolTitle {{ font-size: 15px; font-weight: 600; }}
#AtechTool QPushButton {{
    background: {sunken}; color: {text}; border: 1px solid {line}; border-radius: 15px;
    padding: 0 14px; min-height: 30px;
}}
#AtechTool QPushButton:hover {{ background: {hover}; }}
#AtechTool QPushButton#ToolPrimary {{
    background: {btn_bg}; color: {btn_text}; border: none; font-weight: 600;
}}
#AtechTool QPushButton#ToolPrimary:hover {{ background: {btn_bg_hover}; }}
#AtechTool QPushButton:checked {{ background: {btn_bg}; color: {btn_text}; border: none; }}
#AtechTool QTableWidget {{
    background: {panel}; color: {text}; border: 1px solid {line}; border-radius: 10px;
    gridline-color: {line};
}}
#AtechTool QHeaderView::section {{
    background: {sunken}; color: {muted}; border: none; padding: 4px 6px;
}}
#AtechTool QCheckBox {{ color: {text}; }}
"""


def _qss(template):
    from . import style
    return style.qss(template)


def _active_doc():
    try:
        import FreeCAD
        return FreeCAD.ActiveDocument
    except Exception:                                     # noqa: BLE001
        return None


def _selected():
    try:
        import FreeCADGui
        return list(FreeCADGui.Selection.getSelection())
    except Exception:                                     # noqa: BLE001
        return []


def _pills(parent, options, current):
    """A row of checkable buttons, one checked (PillTabs-like), returns
    (row widget, QButtonGroup)."""
    from PySide6 import QtWidgets
    row = QtWidgets.QWidget(parent)
    lay = QtWidgets.QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    grp = QtWidgets.QButtonGroup(row)
    grp.setExclusive(True)
    for key, text in options:
        b = QtWidgets.QPushButton(text, row)
        b.setCheckable(True)
        b.setAccessibleName(text)
        b.setProperty("key", key)
        b.setChecked(key == current)
        grp.addButton(b)
        lay.addWidget(b)
    lay.addStretch(1)
    return row, grp


def _checked_key(grp):
    b = grp.checkedButton()
    return b.property("key") if b is not None else None


def _tool_dialog(cls_base, parent, title):
    d = cls_base(parent)
    d.setObjectName("AtechTool")
    d.setWindowTitle(title)
    d.setAccessibleName(title)
    try:
        d.setStyleSheet(_qss(DIALOG_QSS))
    except Exception as exc:                              # noqa: BLE001
        _log("dialog style: %r" % (exc,))
    return d


def ColourMenu(parent=None, doc_fn=_active_doc, targets_fn=_selected):
    """R341: a QMenu with the palette swatches, a custom colour, a
    transparency slider and a reset. Acts on targets_fn() (default: the 3D
    selection) and records the edits as hand edits."""
    from PySide6 import QtCore, QtGui, QtWidgets

    menu = QtWidgets.QMenu(parent)
    menu.setObjectName("AtechColourMenu")
    menu.setTitle("Colour")
    menu.setAccessibleName("Colour")

    def apply(color=None, transparency=None):
        doc, objs = doc_fn(), targets_fn()
        if not objs:
            _log("colour: nothing selected")
            return 0
        n = set_colour(doc, objs, color=color, transparency=transparency)
        try:
            doc.recompute()
        except Exception:                                 # noqa: BLE001
            pass
        return n

    grid_w = QtWidgets.QWidget(menu)
    grid = QtWidgets.QGridLayout(grid_w)
    grid.setContentsMargins(10, 8, 10, 4)
    grid.setSpacing(4)
    menu.swatches = []
    for i, (_key, name, rgb, tr) in enumerate(palette()):
        b = QtWidgets.QToolButton(grid_w)
        b.setFixedSize(22, 22)
        b.setToolTip(name)
        b.setAccessibleName(name)
        b.setStyleSheet("QToolButton { background: %s; border: 1px solid rgba(0,0,0,60);"
                        " border-radius: 11px; } QToolButton:hover { border: 2px solid"
                        " palette(highlight); }" % hex_colour(rgb))
        b.clicked.connect(lambda _=False, c=rgb, t=tr: (apply(c, t), menu.close()))
        grid.addWidget(b, i // 9, i % 9)
        menu.swatches.append(b)
    wa = QtWidgets.QWidgetAction(menu)
    wa.setDefaultWidget(grid_w)
    menu.addAction(wa)

    custom = menu.addAction("Custom colour...")

    def pick():
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor("#ffffff"), parent, "Custom colour")
        if c.isValid():
            apply((c.redF(), c.greenF(), c.blueF()))
    custom.triggered.connect(pick)
    menu.custom_action = custom

    tw = QtWidgets.QWidget(menu)
    tl = QtWidgets.QHBoxLayout(tw)
    tl.setContentsMargins(12, 4, 12, 6)
    lab = QtWidgets.QLabel("Transparency", tw)
    sl = QtWidgets.QSlider(QtCore.Qt.Horizontal, tw)
    sl.setRange(0, 90)
    sl.setSingleStep(5)
    sl.setAccessibleName("Transparency")
    val = QtWidgets.QLabel("0 %", tw)
    val.setMinimumWidth(36)
    objs0 = targets_fn()
    try:
        sl.setValue(int(objs0[0].ViewObject.Transparency) if objs0 else 0)
    except Exception:                                     # noqa: BLE001
        pass
    val.setText("%d %%" % sl.value())
    sl.valueChanged.connect(lambda v: val.setText("%d %%" % v))
    sl.sliderReleased.connect(lambda: apply(transparency=sl.value()))
    tl.addWidget(lab)
    tl.addWidget(sl, 1)
    tl.addWidget(val)
    wt = QtWidgets.QWidgetAction(menu)
    wt.setDefaultWidget(tw)
    menu.addAction(wt)
    menu.transparency_slider = sl

    menu.addSeparator()
    reset = menu.addAction("Use the agent's colour again")
    reset.triggered.connect(lambda: reset_colour(doc_fn(), targets_fn()))
    menu.reset_action = reset
    menu.apply = apply
    return menu


def ExportDialog(parent=None, doc_fn=_active_doc, selection_fn=_selected,
                 save_name=None, slicers_fn=find_slicers, opener=None):
    """R342-R344: scope, format, mesh quality, Atech parts, lay flat; a
    printability check; Export; Open in <slicer> for the exported file.
    save_name(fmt, scope) -> path or None (default: a QFileDialog)."""
    from PySide6 import QtWidgets

    d = _tool_dialog(QtWidgets.QDialog, parent, "Export for print")
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(10)
    t = QtWidgets.QLabel("Export for print", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)

    def section(text):
        lab = QtWidgets.QLabel(text, d)
        lab.setObjectName("ToolMuted")
        lay.addWidget(lab)

    section("What to export")
    row, d.scope = _pills(d, SCOPES, "product")
    lay.addWidget(row)
    section("File type")
    row, d.fmt = _pills(d, [(f, f + (" (with colours)" if f == "3MF" else "")) for f in FORMATS],
                        "3MF")
    lay.addWidget(row)
    section("Mesh quality (how far the mesh may stray from the true surface)")
    row, d.quality = _pills(d, [(n, "%s %g mm" % (n, lin)) for n, lin, _a in DEVIATIONS],
                            DEFAULT_DEVIATION)
    lay.addWidget(row)
    d.flat = QtWidgets.QCheckBox("Lay each part flat on the bed (largest flat side down)", d)
    d.flat.setAccessibleName("Lay each part flat on the bed")
    lay.addWidget(d.flat)
    d.atech = QtWidgets.QCheckBox(
        "Include the Atech board, modules and cables (their models are for personal, "
        "non-commercial use: CC BY-NC)", d)
    d.atech.setAccessibleName("Include the Atech board, modules and cables")
    d.atech.setChecked(False)
    lay.addWidget(d.atech)

    def scope_changed(*_):
        d.flat.setChecked(_checked_key(d.scope) == "parts")
        d.quality.buttons()[0].parentWidget().setEnabled(_checked_key(d.fmt) != "STEP")
    d.scope.buttonClicked.connect(scope_changed)
    d.fmt.buttonClicked.connect(scope_changed)
    scope_changed()

    d.report = QtWidgets.QTableWidget(0, 4, d)
    d.report.setHorizontalHeaderLabels(["Part", "Turned", "Overhang", "Notes"])
    d.report.setAccessibleName("Printability")
    d.report.horizontalHeader().setStretchLastSection(True)
    d.report.verticalHeader().setVisible(False)
    d.report.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    d.report.setVisible(False)
    lay.addWidget(d.report, 1)
    d.status = QtWidgets.QLabel("", d)
    d.status.setObjectName("ToolMuted")
    d.status.setWordWrap(True)
    lay.addWidget(d.status)

    btns = QtWidgets.QHBoxLayout()
    d.btn_check = QtWidgets.QPushButton("Check printability", d)
    d.btn_check.setAccessibleName("Check printability")
    btns.addWidget(d.btn_check)
    d.slicer_buttons = []
    btns.addStretch(1)
    d.btn_export = QtWidgets.QPushButton("Export...", d)
    d.btn_export.setObjectName("ToolPrimary")
    d.btn_export.setAccessibleName("Export")
    d.btn_export.setDefault(True)
    btns.addWidget(d.btn_export)
    lay.addLayout(btns)
    d.slicer_row = QtWidgets.QHBoxLayout()
    lay.addLayout(d.slicer_row)
    d.result = None

    def options():
        return dict(fmt=_checked_key(d.fmt), scope=_checked_key(d.scope),
                    quality=_checked_key(d.quality), include_atech=d.atech.isChecked(),
                    lay_flat=d.flat.isChecked())

    def check():
        doc = doc_fn()
        o = options()
        objs, _left = export_targets(doc, o["scope"], selection_fn(), o["include_atech"])
        rows = print_report([x for x in objs if not _is_mesh(x)])
        d.report.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [r["label"], "%.0f deg" % r["turned_deg"],
                    "%.0f mm2 (%.1f %%)" % (r["overhang_mm2"], r["overhang_pct"]),
                    " ".join(r["flags"]) or "Looks printable."]
            for j, v in enumerate(vals):
                d.report.setItem(i, j, QtWidgets.QTableWidgetItem(v))
        d.report.setVisible(True)
        d.status.setText("%d parts checked. Overhangs are judged with each part laid flat."
                         % len(rows))
        d.report_rows = rows
        return rows

    def ask_path(fmt, scope):
        if save_name is not None:
            return save_name(fmt, scope)
        doc = doc_fn()
        base = safe_name(getattr(doc, "Label", "") or "export")
        if scope == "parts":
            return QtWidgets.QFileDialog.getExistingDirectory(d, "Folder for the part files")
        ext = {"STL": "stl", "3MF": "3mf", "STEP": "step"}[fmt]
        p, _f = QtWidgets.QFileDialog.getSaveFileName(
            d, "Export for print", os.path.join(os.path.expanduser("~/Desktop"),
                                                "%s.%s" % (base, ext)),
            "%s files (*.%s)" % (fmt, ext))
        return p

    def do_export():
        o = options()
        path = ask_path(o["fmt"], o["scope"])
        if not path:
            return None
        try:
            res = export_for_print(doc_fn(), path, selection=selection_fn(), **o)
        except Exception as exc:                          # noqa: BLE001
            d.status.setText("Export failed: %s" % exc)
            return None
        d.result = res
        bits = ["Saved %d file%s." % (len(res["files"]), "" if len(res["files"]) == 1 else "s")]
        if res["left_out"]:
            bits.append("Left out %d Atech part%s." % (
                len(res["left_out"]), "" if len(res["left_out"]) == 1 else "s"))
        if res["skipped"]:
            bits.append("STEP cannot hold the Atech meshes: %s." % ", ".join(res["skipped"]))
        d.status.setText(" ".join(bits))
        for b in d.slicer_buttons:
            b.deleteLater()
        d.slicer_buttons = []
        if o["fmt"] != "STEP":
            for s in slicers_fn():
                b = QtWidgets.QPushButton("Open in %s" % s["name"], d)
                b.setAccessibleName("Open in %s" % s["name"])
                b.clicked.connect(lambda _=False, s=s: open_in_slicer(res["files"], s, opener))
                d.slicer_row.addWidget(b)
                d.slicer_buttons.append(b)
        return res

    d.btn_check.clicked.connect(check)
    d.btn_export.clicked.connect(do_export)
    d.options, d.check, d.do_export = options, check, do_export
    d.resize(620, 420)
    return d


def ExplodeDialog(parent=None, doc_fn=_active_doc):
    """R345: a small non-modal window with a slider; closing it puts every
    part back where it was."""
    from PySide6 import QtCore, QtWidgets

    d = _tool_dialog(QtWidgets.QDialog, parent, "Exploded view")
    d.setModal(False)
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 16, 20, 16)
    t = QtWidgets.QLabel("Exploded view", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    sub = QtWidgets.QLabel("Only the picture changes: every part goes back when you close this.",
                           d)
    sub.setObjectName("ToolMuted")
    sub.setWordWrap(True)
    lay.addWidget(sub)
    d.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, d)
    d.slider.setRange(0, 100)
    d.slider.setAccessibleName("How far apart")
    lay.addWidget(d.slider)
    close = QtWidgets.QPushButton("Done", d)
    close.setObjectName("ToolPrimary")
    close.setAccessibleName("Done")
    close.clicked.connect(d.close)
    row = QtWidgets.QHBoxLayout()
    row.addStretch(1)
    row.addWidget(close)
    lay.addLayout(row)
    # R720: the window drives the document's one exploded state (the view
    # bar's toggle, the E key and Show and hide use the same), never its
    # own Exploder: two of them put "where the parts belong" out of step.
    d.doc = None
    sync = {"busy": False}

    def moved(v):
        if sync["busy"]:
            return
        doc = d.doc or doc_fn()
        if doc is None:
            return
        d.doc = doc
        sync["busy"] = True
        try:
            set_explode(doc, v / 100.0)
        finally:
            sync["busy"] = False
    d.slider.valueChanged.connect(moved)

    def follow(doc, factor):
        """E, the view bar or Show and hide changed it: show the amount."""
        if sync["busy"] or d.doc is None or doc is not d.doc:
            return
        try:
            sync["busy"] = True
            d.slider.setValue(int(round(factor * 100)))
        except RuntimeError:                              # the window is gone
            pass
        finally:
            sync["busy"] = False
    on_explode_changed(follow)
    d.slider.setValue(int(round(explode_amount(doc_fn()) * 100)))

    def finished(*_):
        if d.doc is not None:
            set_explode(d.doc, 0.0)
            d.doc = None
    d.finished.connect(finished)
    orig_close = d.closeEvent

    def close_event(ev):
        finished()
        orig_close(ev)
    d.closeEvent = close_event
    d.resize(360, 150)
    return d


def BomDialog(parent=None, doc_fn=_active_doc, save_name=None):
    """R346: the bill of materials as a table, with Save as CSV."""
    from PySide6 import QtWidgets

    d = _tool_dialog(QtWidgets.QDialog, parent, "Bill of materials")
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 16, 20, 16)
    t = QtWidgets.QLabel("Bill of materials", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    b = bom(doc_fn())
    d.bom = b
    cols = ["Item", "Count", "Volume", "Mass (PLA)", "Colour", "Ports", "Cable length"]
    d.table = QtWidgets.QTableWidget(len(b["printed"]) + len(b["hardware"]), len(cols), d)
    d.table.setHorizontalHeaderLabels(cols)
    d.table.setAccessibleName("Bill of materials")
    d.table.verticalHeader().setVisible(False)
    d.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    i = 0
    for r in b["printed"]:
        vals = [r["part"], str(r["count"]), "%.2f cm3" % r["volume_cm3"], "%.1f g" % r["mass_g"],
                r["colour"], "", ""]
        for j, v in enumerate(vals):
            d.table.setItem(i, j, QtWidgets.QTableWidgetItem(v))
        i += 1
    for r in b["hardware"]:
        vals = [r["name"], "1", "", "", "", r["ports"],
                "" if r["length_mm"] is None else "%.0f mm" % r["length_mm"]]
        for j, v in enumerate(vals):
            d.table.setItem(i, j, QtWidgets.QTableWidgetItem(v))
        i += 1
    d.table.resizeColumnsToContents()
    lay.addWidget(d.table, 1)
    total = sum(r["mass_g"] * r["count"] for r in b["printed"])
    note = QtWidgets.QLabel("Printed parts: %d, about %.0f g of PLA (%.2f g/cm3)." % (
        sum(r["count"] for r in b["printed"]), total, PLA_DENSITY), d)
    note.setObjectName("ToolMuted")
    lay.addWidget(note)
    row = QtWidgets.QHBoxLayout()
    row.addStretch(1)
    save = QtWidgets.QPushButton("Save as CSV...", d)
    save.setObjectName("ToolPrimary")
    save.setAccessibleName("Save as CSV")
    row.addWidget(save)
    lay.addLayout(row)

    def do_save():
        doc = doc_fn()
        if save_name is not None:
            p = save_name()
        else:
            base = safe_name(getattr(doc, "Label", "") or "parts")
            p, _f = QtWidgets.QFileDialog.getSaveFileName(
                d, "Save the bill of materials",
                os.path.join(os.path.expanduser("~/Desktop"), "%s BOM.csv" % base),
                "CSV files (*.csv)")
        if not p:
            return None
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(bom_csv(b))
        return p
    save.clicked.connect(do_save)
    d.save_csv = do_save
    d.resize(640, 420)
    return d


def share_now(parent=None, doc_fn=_active_doc, out_dir=None):
    """R347: save the hero image to Pictures and copy it; returns (path,
    plain message)."""
    from . import capture
    try:
        p = capture.share_image(doc_fn(), out_dir=out_dir)
        return p, "Saved to Pictures > Atech Atelier and copied, ready to paste."
    except Exception as exc:                              # noqa: BLE001
        _log("share image: %r" % (exc,))
        return None, capture.user_message(exc)


def _say(widget, text):
    try:
        from PySide6 import QtWidgets
        if widget is not None:
            QtWidgets.QToolTip.showText(widget.mapToGlobal(widget.rect().bottomLeft()), text,
                                        widget)
        else:
            _log(text)
    except Exception:                                     # noqa: BLE001
        _log(text)


def view_bar_buttons(parent=None, doc_fn=_active_doc, selection_fn=_selected):
    """Factory for the view bar (shell.ViewBar): {"colour", "explode",
    "export", "share"} -> QPushButton objectName "VBtn" (the view bar's own
    QSS styles them), icon-only, 34 px, accessible names. Call
    restyle_buttons(buttons) from ViewBar.restyle()."""
    from PySide6 import QtCore, QtWidgets

    spec = (("colour", "palette", "Colour"),
            ("explode", "explode", "Exploded view"),
            ("export", "download", "Export for print"),
            ("share", "image", "Save a share image"))
    out = {}
    for key, ic, tip in spec:
        b = QtWidgets.QPushButton("", parent)
        b.setObjectName("VBtn")
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.setAccessibleName(tip)
        b.setIconSize(QtCore.QSize(16, 16))
        b.setFixedWidth(34)
        b.setProperty("atech_icon", ic)
        out[key] = b

    def colour():
        m = ColourMenu(out["colour"], doc_fn, selection_fn)
        out["colour"]._menu = m
        m.popup(out["colour"].mapToGlobal(out["colour"].rect().bottomLeft()))

    # R701: Exploded view is one click: apart, and back together. How far
    # apart is the slider in Show and hide.
    xb = out["explode"]
    xb.setCheckable(True)
    xb.setToolTip("Exploded view: pull the parts apart, click again to put "
                  "them back (E)")

    def explode():
        on = toggle_explode(doc_fn()) > 0.0
        xb.blockSignals(True)
        xb.setChecked(on)
        xb.blockSignals(False)

    def follow(doc, factor):
        try:
            if doc is not doc_fn():
                return
            xb.blockSignals(True)
            xb.setChecked(factor > 0.0)
            xb.blockSignals(False)
        except RuntimeError:            # the button is gone
            raise
    on_explode_changed(follow)

    def export():
        d = ExportDialog(out["export"].window(), doc_fn, selection_fn)
        out["export"]._dlg = d
        d.show()

    def share():
        _p, msg = share_now(out["share"], doc_fn)
        _say(out["share"], msg)

    for key, fn in (("colour", colour), ("explode", explode), ("export", export),
                    ("share", share)):
        out[key].clicked.connect(lambda _=False, f=fn: _guard(f))
    return out


def _guard(fn):
    try:
        return fn()
    except Exception as exc:                              # noqa: BLE001
        _log("action failed: %r" % (exc,))
        return None


def restyle_buttons(buttons):
    """Icons in the current mode's muted colour (as ViewBar.restyle)."""
    from . import style
    t = style.tokens()
    for b in buttons.values():
        b.setIcon(icon(b.property("atech_icon"), t["muted"], 16))


def menu_actions(parent=None, doc_fn=_active_doc, selection_fn=_selected):
    """Factory for the Atech menu / the 3D right-click menu: [QAction]:
    Colour (a submenu), Export for print..., Exploded view (E), Bill of
    materials..., Save share image, Save review sheet."""
    from PySide6 import QtGui

    acts = []
    colour = QtGui.QAction("Colour", parent)
    colour.setMenu(ColourMenu(parent, doc_fn, selection_fn))
    acts.append(colour)

    def add(text, fn):
        a = QtGui.QAction(text, parent)
        a.triggered.connect(lambda _=False: _guard(fn))
        acts.append(a)
        return a

    keep = {}
    add("Export for print...", lambda: keep.__setitem__(
        "export", ExportDialog(parent, doc_fn, selection_fn)) or keep["export"].show())
    add("Exploded view (E)", lambda: toggle_explode(doc_fn()))
    add("Bill of materials...", lambda: keep.__setitem__(
        "bom", BomDialog(parent, doc_fn)) or keep["bom"].show())
    add("Save share image", lambda: _say(None, share_now(parent, doc_fn)[1]))

    def sheet():
        from . import capture
        p = capture.share_sheet(doc_fn())
        _say(None, "Review sheet saved: %s" % p)
    add("Save review sheet", sheet)
    for a in acts:
        a.setObjectName("atech_" + re.sub(r"\W+", "_", a.text().lower()).strip("_"))
    acts[0]._keep = keep
    return acts
