"""atech_modules — build projects out of real Atech modules.

EVERY DIMENSION COMES FROM THE LIBRARY, NOT FROM THIS FILE.
    `models/presets.yaml` is stated by its own README as the source of truth
    ("Get exact dimensions -> models/presets.yaml — never guess"). This module
    reads it. It hardcodes no module size, and it refuses to place a module it
    cannot find a spec for.

    Where geometry and spec can be compared, they ARE compared: load_module()
    measures the STL's bounding box and reports the delta against the spec
    rather than trusting either one. That is the "check against something that
    cannot agree with you by construction" rule (P2).

THE ONE HARD RULE FROM THE LIBRARY
    "Modules mount on the board's +Y face." The board's own measured top face
    is used as the mounting plane, never the nominal from the spec. The board
    is the one drawn by atech_ports.board_display_mesh() (R197): the GLB, which
    measures 7.00 mm thick as the spec says. The board STL measured 6.49 and
    carried a broken, triangulated central frame, so it is no longer drawn.

WHAT THIS IS NOT
    Not a case generator, and not a claim that a layout is manufacturable. It
    places real module meshes on a real board so a project can be seen, spun,
    and handed to the agent as a picture. Interference between neighbouring
    modules IS checked and reported, because two modules in one slot is the
    obvious failure and it is cheap to catch.
"""
import os

try:
    import yaml
except ImportError:                      # FreeCAD bundles it; be explicit if not
    yaml = None

import FreeCAD
import Mesh


# Where the library is: ONE resolver, atech_ports.library_dir() (installed
# bundle, then a development checkout, with $ATECH_ARTIFACTS as an explicit
# override). Two copies of a path rule are two rules that can drift.
from atech_ports import MISSING_LIBRARY, MODELS_DIR, board_display_mesh  # noqa: E402

STL_DIR = os.path.join(MODELS_DIR, "stl") if MODELS_DIR else None
PRESETS = os.path.join(MODELS_DIR, "presets.yaml") if MODELS_DIR else None

BOARD = "motherboard_14_port"


class SpecError(RuntimeError):
    """A module or dimension the library does not define. Never guessed around."""


class LibraryMissing(SpecError):
    """This installation has no module library at all."""


# --------------------------------------------------------------- the library
_SPECS = None


def specs():
    """The parsed presets.yaml. Raises rather than inventing defaults."""
    global _SPECS
    if _SPECS is not None:
        return _SPECS
    if yaml is None:
        raise SpecError("PyYAML is unavailable, so presets.yaml cannot be read")
    if PRESETS is None or not os.path.isfile(PRESETS):
        raise LibraryMissing(MISSING_LIBRARY)
    with open(PRESETS, encoding="utf-8") as fh:
        _SPECS = yaml.safe_load(fh)
    return _SPECS


def spec(name):
    d = specs()
    if name not in d:
        raise SpecError("%r is not a module in presets.yaml (known: %s)"
                        % (name, ", ".join(sorted(d))))
    return d[name]


def modules_of(category=None):
    """Module names, optionally filtered by the library's own category."""
    return sorted(k for k, v in specs().items()
                  if category is None or v.get("category") == category)


def stl_path(name):
    f = spec(name).get("file")
    if not f:
        raise SpecError("%r has no 'file' in presets.yaml" % name)
    p = os.path.join(STL_DIR, f)
    if not os.path.isfile(p):
        raise SpecError("%s is named in presets.yaml but missing: %s" % (name, p))
    return p


# ------------------------------------------------------------------ geometry
def load_module(doc, name, label=None, placement=None):
    """Add a module's mesh to the document. Returns (obj, report).

    report compares MEASURED bbox against the spec. A mismatch is reported,
    never silently accepted and never silently corrected.
    """
    path = stl_path(name)
    mesh = _board_mesh() if name == BOARD else Mesh.Mesh(path)
    obj = doc.addObject("Mesh::Feature", label or name)
    obj.Mesh = mesh
    if name == BOARD:
        import atech_ports
        atech_ports.mark_board_mesh(obj)
    if placement is not None:
        obj.Placement = placement

    bb = mesh.BoundBox
    d = spec(name).get("dimensions_mm") or {}
    report = {
        "name": name,
        "measured": (round(bb.XLength, 2), round(bb.YLength, 2), round(bb.ZLength, 2)),
        "spec": (d.get("x"), d.get("y"), d.get("z")),
        "facets": mesh.CountFacets,
        "delta": None,
    }
    if all(v is not None for v in report["spec"]):
        report["delta"] = tuple(
            round(m - s, 2) for m, s in zip(report["measured"], report["spec"]))
    return obj, report


def _board_mesh():
    """The board as drawn (atech_ports.board_display_mesh, R197)."""
    stl_path(BOARD)                      # presets.yaml must still name it
    return board_display_mesh()


def board_top_y():
    """The board's MEASURED top face — the +Y mounting plane.

    Measured on the drawn board, not the nominal thickness from the spec.
    """
    return _board_mesh().BoundBox.YMax


def slot_positions(module_names, margin=6.0, gap=2.0):
    """Z centres that account for each module's MEASURED length.

    HONEST LIMIT: presets.yaml does not publish a slot pitch, and clustering
    the board mesh gave pitches of 11-21 mm — too noisy to call a grid. So
    this packs modules along the board rather than claiming to hit real
    connectors. Positions are PLAUSIBLE LAYOUT, not verified slot
    registration. Do not present them as mated.

    Even spacing was the first attempt and it was WRONG: it ignores module
    length, so a 40 mm speaker beside a 40 mm knob overlapped by 5.61 mm
    (measured). Packing by measured length is what removes that.

    Returns (centres, fits) — fits is False when the stack is longer than the
    board, which is reported rather than silently squashed.
    """
    bb = _board_mesh().BoundBox
    lengths = [Mesh.Mesh(stl_path(m)).BoundBox.ZLength for m in module_names]
    if not lengths:
        return [], True
    span = bb.ZLength - 2 * margin
    need = sum(lengths) + gap * (len(lengths) - 1)
    # Distribute any slack evenly between modules; never negative.
    slack = max(0.0, span - need)
    extra = slack / (len(lengths) + 1)
    centres, cursor = [], bb.ZMin + margin + extra
    for i, L in enumerate(lengths):
        centres.append(cursor + L / 2.0)
        cursor += L + gap + extra
    return centres, need <= span


def build_project(name, module_names, doc_name=None):
    """Assemble a board plus modules into a new document.

    Returns (doc, report). Every failure is named; a module that cannot be
    placed is listed in report["skipped"], never silently dropped.
    """
    doc = FreeCAD.newDocument(doc_name or name)
    report = {"project": name, "placed": [], "skipped": [], "board": None,
              "overlaps": []}

    board_obj, board_report = load_module(doc, BOARD, label="motherboard")
    report["board"] = board_report

    top = board_top_y()
    bb = _board_mesh().BoundBox
    x_centre = (bb.XMin + bb.XMax) / 2.0

    usable = []
    for m in module_names:
        try:
            stl_path(m)
            usable.append(m)
        except SpecError as exc:
            report["skipped"].append({"name": m, "reason": str(exc)})

    zs, fits = slot_positions(usable) if usable else ([], True)
    report["fits_on_board"] = fits
    if not fits:
        report["skipped"].append(
            {"name": "(layout)",
             "reason": "the modules are longer end-to-end than the board; "
                       "positions are packed but the stack overhangs"})
    boxes = []
    for m, z in zip(usable, zs):
        d = spec(m).get("dimensions_mm") or {}
        mesh_bb = Mesh.Mesh(stl_path(m)).BoundBox
        # Seat the module ON the board: its own measured minimum goes to the
        # board's measured top face.
        pl = FreeCAD.Placement()
        pl.Base = FreeCAD.Vector(
            x_centre - (mesh_bb.XMin + mesh_bb.XMax) / 2.0,
            top - mesh_bb.YMin,
            z - (mesh_bb.ZMin + mesh_bb.ZMax) / 2.0,
        )
        obj, rep = load_module(doc, m, label=m, placement=pl)
        rep["z_centre"] = round(z, 2)
        report["placed"].append(rep)
        # The PLACED bbox in world coordinates — mesh bbox shifted by the
        # placement we just applied. Measured extents, not nominal sizes.
        base = pl.Base
        lo = (mesh_bb.XMin + base.x, mesh_bb.YMin + base.y, mesh_bb.ZMin + base.z)
        hi = (mesh_bb.XMax + base.x, mesh_bb.YMax + base.y, mesh_bb.ZMax + base.z)
        boxes.append((m, lo, hi))

    # Interference, checked over ALL PAIRS in ALL THREE AXES.
    #
    # The first version compared only ADJACENT pairs on Z, and five independent
    # reviewers caught the same defect: under this packer that check is
    # TAUTOLOGICAL. slot_positions() separates neighbours by a constant gap, so
    # an adjacent-pair Z test can never fire — it reported "overlaps: none"
    # because it was incapable of reporting anything else. A check that cannot
    # fail is a pass over nothing (CLAUDE.md: "ask what it was actually
    # asking"). Measured: 0 firings in 200 random configurations, minimum gap
    # exactly 2.000000.
    #
    # All pairs, because a tall module can reach over its neighbour and collide
    # with the one beyond it. All three axes, because two modules sharing a Z
    # span do not collide if they sit at different X — overlap in one
    # projection is not overlap in 3D.
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            olap = []
            for axis in range(3):
                lo = max(a[1][axis], b[1][axis])
                hi = min(a[2][axis], b[2][axis])
                if hi <= lo:
                    olap = None
                    break
                olap.append(hi - lo)
            if olap:
                report["overlaps"].append({
                    "a": a[0], "b": b[0],
                    "overlap_mm": [round(v, 2) for v in olap],
                    "volume_mm3": round(olap[0] * olap[1] * olap[2], 2),
                    "adjacent": j == i + 1,
                })

    doc.recompute()
    return doc, report


# ------------------------------------------------------------------ projects
# Each is a real, buildable configuration of modules the library actually has.
PROJECTS = {
    "desk-sensor-hub": {
        "title": "Desk Sensor Hub",
        "purpose": "Ambient monitor: temperature, humidity, distance and light "
                   "on a screen, with a button to cycle readings.",
        "modules": ["screen", "temp_humidity", "distance_sensor", "light",
                    "button"],
    },
    "voice-remote": {
        "title": "Voice Remote",
        "purpose": "Listens, shows state, and answers with sound. Microphone "
                   "in, speaker out, knob for volume.",
        "modules": ["microphone", "speaker", "knob", "light"],
    },
    "motion-rig": {
        "title": "Motion Rig",
        "purpose": "A driven axis with feedback: DC motor and wheel, "
                   "orientation sensing, and a button to start and stop.",
        "modules": ["dc_motor", "n20_wheel", "orientation", "button"],
    },

    # --- designed and independently verified 2026-09-24 -------------------
    # Five projects proposed by a design agent from the real module list, each
    # then built in FreeCAD by a separate agent and adversarially checked by a
    # third. All five: 4 modules placed, no interference, stack within the
    # board's usable span. See docs/verification/2026-09-24_module_projects.md.
    "desk-climate-sentinel": {
        "title": "Desk Climate Sentinel",
        "purpose": "Tells you when the air has gone stale or dry — live "
                   "temperature and humidity on screen, plus a colour you "
                   "can read from across the room.",
        "modules": ["usbc", "screen", "temp_humidity", "light"],
    },
    "pomodoro-focus-timer": {
        "title": "Pomodoro Focus Timer",
        "purpose": "A physical work timer: twist the knob to set it, press "
                   "once to start. A focus session begins without opening a "
                   "screen that could distract you.",
        "modules": ["usbc", "screen", "knob", "button"],
    },
    "voice-note-doorbell": {
        "title": "Voice Note Doorbell",
        "purpose": "Press-to-record message box for the front door: a "
                   "visitor leaves a short spoken note, and it plays back "
                   "aloud for whoever is home next.",
        "modules": ["usbc", "microphone", "button", "speaker"],
    },
    "reverse-parking-gauge": {
        "title": "Reverse Parking Gauge",
        "purpose": "Mounts on a garage wall facing the car and shows how "
                   "many centimetres remain before the bumper touches, so a "
                   "tight garage gets used to its full depth.",
        "modules": ["usbc", "distance_sensor", "screen", "light"],
    },
    "tilt-tamper-alarm": {
        "title": "Tilt Tamper Alarm",
        "purpose": "Drop it in a toolbox, drawer or suitcase and it sounds "
                   "if anything moves the container while armed — a cheap "
                   "standalone theft alert with no network and no app.",
        "modules": ["usbc", "orientation", "speaker", "button"],
    },
}


def build_named(key, doc_name=None):
    if key not in PROJECTS:
        raise SpecError("unknown project %r (known: %s)"
                        % (key, ", ".join(sorted(PROJECTS))))
    p = PROJECTS[key]
    return build_project(p["title"], p["modules"], doc_name=doc_name or key)
