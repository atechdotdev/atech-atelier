"""fc_build - the freecadcmd half of the build-quality benchmark.

Runs INSIDE freecadcmd (FreeCAD's Python 3.11). Never run it with system
python. The job is passed through the environment, not argv (freecadcmd
treats extra argv as files to open):

    EVAL_JOB=<path to job.json>  freecadcmd fc_build.py

job.json:
    {"mode": "sysprompt", "workspace": "...", "out": "result.json",
     "request": "<the user request>" | null}
    {"mode": "argv", "workspace_root": "..." (or "workspace": "..."),
     "out": "result.json", "message": "<placeholder>",
     "request": "<the user request>" | null,
     "session": "<placeholder>", "seed": null}
    {"mode": "build", "workspace": "...", "out": "result.json",
     "expect": {...}, "render": "render.png" | null,
     "prompt": "<the user request>", "seed": "<seed script>" | null,
     "preview": false}

PREVIEW (S46): "preview": true is a live-preview build - what the panel runs
when model.py changes mid-turn: build.apply + build.failures + the document
brief, then it stops (no expectation or fitness checks, no render), so its
build_seconds is the production build time. run_eval hands it a COPY of the
workspace.

MODE argv (release PRD S15): the claude argv comes from PRODUCTION code,
never a hand-copied list: AgentPanel._turn_args(ws) run for real (a
stand-in self resolving everything from the class), then ClaudeRun built
with what it returned - since S16 ClaudeRun(system_prompt=, agent=), whose
flags come from claude_cli.agent_argv; before S16 ClaudeRun(extra_args=).
That is the pair of calls panel._send_claude makes. The prompt and session are placeholders the caller substitutes per
turn; the prompt goes wherever ClaudeRun puts it (stdin since R35). Computed inside freecadcmd because the system
prompt's Atech section and the ATECH_ASSEMBLY.md copy resolve here exactly as
in Studio (panel imports PySide6, which this Python has).

R111: "request" is the user's request TEXT (the argv keeps the message
placeholder). _turn_args gets text=request, doc=<the seeded document>, the
two arguments panel._send_claude passes, so a plain prompt gets the plain
system prompt and no ATECH_ASSEMBLY.md copy, and an Atech prompt the Atech
one - whatever the shipped _turn_args decides, not the harness. With no
request (the harness's system_prompt.txt probe) it is called as before.

ADDON (S41): EVAL_ADDON=<dir> imports acadagent from that addon tree (an
earlier revision extracted by run_eval --rescore) instead of this one.

SEED: a script run into the fresh document BEFORE the agent's model.py, the
way a user's existing part is already there (stand_for_existing_part). It
gets `doc`, `App`, `FreeCAD`. Seed objects are not the agent's: expectation
checks ignore them, fitness checks (overlap, below-desk) include them.

FITNESS CHECKS (S15) are reported in `fitness`, separate from `checks`, so
the 12-prompt expectation score stays comparable with earlier runs:
    no_overlap        every pair of shape objects (agent's end results +
                      seed) has common volume <= OVERLAP_TOL_MM3, unless the
                      pair is listed in expect["allow_overlap"]
    not_below_desk    when the prompt says "on a desk" (or expect["on_desk"]):
                      no Part shape or mesh reaches below z = -DESK_TOL_MM
    gear_teeth        expect["gear_teeth"]: teeth counted on the section of
                      the largest object at mid-height of its thinnest axis
    atech_ports_check expect["atech_check"]: every verdict of
                      atech_ports.check(doc, fitted_after=...) is PASS
                      (CANNOT DETERMINE fails). fitted_after (R136/R137,
                      round 5) is read from the workspace's intent.json the
                      way production ./check reads it: production tells the
                      agent to CLOSE the case and declare its end caps there,
                      so ignoring it failed every closed case by construction.
                      Guarded (P2): only labels of the agent's own non-Atech
                      Part shapes count, and a declaration that would leave
                      no agent part as an obstacle is not honoured. The
                      strict verdict (nothing fitted after) is kept in the
                      detail as `strict_pass` for comparison with rounds <= 4.
  Atech prompts (S35), all read off the document, never the agent's prose:
    atech_modules     expect["atech_modules"] ["button", ...]: each named
                      module is seated (an AtechRole="module" object whose
                      AtechModule is that name; a repeated name needs as many)
    board_upright     expect["board_upright"]: the board's plane is within
                      UPRIGHT_TOL_DEG of vertical. The plane normal is the
                      least-variance axis of the board mesh's world vertices
                      (orientation-free, no assumption about the STL frame)
    modules_inside    expect["modules_inside"] ["speaker", ...]: each such
                      seated module's world mesh box lies inside the box of
                      the agent's Part shapes (the case) within INSIDE_TOL_MM.
                      A box test is a NECESSARY condition (a module poking out
                      of the case fails it), not proof of enclosure.
    open_along        R173 / D64: expect["open_along"] [{"module", "toward":
                      "socket" | "face", "min_open_pct"}] - the share of a
                      ray grid that leaves the product without meeting an
                      agent part: from the USB-C receptacle's mouth along
                      ITS axis (the receptacle is the mesh component with the
                      mouth's cross-section that sticks out of the module
                      body), or from the module's face along the board normal
    closed_around_board  R173: rays from the board's centre plane along +-
                      each board axis (5 x 5 per direction); a direction with
                      more than half of them out is an open end
  A missing board or module FAILS these checks; it is never a pass.

R173 EXPECTATION KEYS that need the shapes (geometry_checks, appended to
`checks`): 'overall_z' (Z length of the tight world box of all the agent's
parts - D65), 'channels_open' {count, d} (round channels open along their
length: a C at every section, not an O - D67), 'open_from_above'
{min_depth_frac} (a ray down the centre of every large object goes that deep
- D66). All R173 probes use OCCT sections of Part.makeLine / Shape.slice,
never production's ray caster or intent.json, so ./check cannot agree with
them by construction (P2).

ROUND 9 KEYS (R191 / R192 regressions, the same rule): 'volume_mm3'
[lo, hi] (summed volume of the agent's parts), 'notches_open' {count, w,
min_depth, through, exact} (rectangular notches open to a face - D74, the
toothbrush holder ./check read as round channels), 'insertion_path'
{section_mm [W, t], min_depth_mm, min_mouth_mm} (the held object can reach
its seat: the widest mouth, across t, that stays free to min_depth_mm over a
stretch of W from any axis face - D73, the cradle whose lips left 5 mm for a
9 mm phone), and 'no_failed_verdict' (production's build.failures() on the
final build is empty: Studio shows no red "build still fails").

ROUND 10 KEY (R202, the same rule): 'hinge_opens' {bore_d, range_deg} - the
pin axis is measured on the parts (a bore of bore_d on one axis line in two
or more parts), the parts on it other than the largest are swept about it
over range_deg in HINGE_STEP_DEG steps, and the check FAILS at the first
angle where they share more than OVERLAP_TOL_MM3 with a part that does not
move (D77: the S6-5 lid, 10.2 mm3 against the back wall at 5 deg).

ROUND 11 KEYS (R213 / R212, the same rule): 'mates' {board, thick_mm,
hole_d, pitch, peg_d, min_pegs} - the reference object the prompt fully
specifies (a pegboard) is modelled where the part installs: its front face on
the flat face the pegs stand out of, its normal the peg axis, its hole grid
through the pegs; the part's common with it outside the holes must be <=
OVERLAP_TOL_MM3 (D79: the S7 c2n3 hook, arm root 4.9 mm into the board).
'parts_engage' {min_parts, slide_mm} - every part but the largest that lies
within slide_mm of another is slid slide_mm in 26 directions; one whose
blocked directions fit in an open hemisphere is only held from one side (a
face touch: no lip, plug or hook inside the opening) and fails (D78: the S7
c1n4 / c2n4 flat "push-fit" end caps).

WHY THESE MARKERS: freecadcmd exits 0 even when the script raised, and
sys.exit() under FreeCAD loses stdout. So the result is written to a file, a
single FC_BUILD_DONE=<path> or FC_BUILD_CRASH=<reason> line is printed,
stdout is flushed, and we leave through os._exit. The caller treats anything
without FC_BUILD_DONE as a crash of the harness, not of the agent's model.

THE BUILD IS PRODUCTION'S BUILD. It calls acadagent.build.apply() on a fresh
document - the exact function the Studio panel calls when a turn ends - so
the transaction, the exec() environment, the "added nothing" rule and the
measurement all come from the shipped code, not a re-implementation.

ONE HEADLESS DIFFERENCE, handled explicitly: freecadcmd has no GUI, so
obj.ViewObject is None and FreeCADGui has no active document. A script that
sets a colour works in Studio but raises here. When the traceback points at
a line that touches ViewObject / Gui, the script is re-run once with those
statements wrapped in try/except (AST rewrite), on a fresh document, and the
result says headless_patched=true. Any other failure is the agent's.
"""
import json
import math
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.environ.get("EVAL_ADDON") or \
    os.path.normpath(os.path.join(HERE, "..", ".."))
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402


OVERLAP_TOL_MM3 = 0.01
DESK_TOL_MM = 0.01
MAX_OVERLAP_OBJECTS = 40
UPRIGHT_TOL_DEG = 30.0
INSIDE_TOL_MM = 0.5


def _done(out_path, payload):
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, default=str)
    print("FC_BUILD_DONE=%s" % out_path)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


def _crash(reason):
    print("FC_BUILD_CRASH=%s" % " ".join(str(reason).split())[:2000])
    sys.stdout.flush()
    os._exit(3)


# ------------------------------------------------------------ measurement
def _tight_bbox(shape):
    """Shape.BoundBox is a loose BOUND on curved bodies; optimalBoundingBox
    is tight to the geometry. Still axis-aligned."""
    try:
        return shape.optimalBoundingBox(True, False)
    except Exception:                                   # noqa: BLE001
        return shape.BoundBox


def _holes(shape, min_arc_deg=330):
    """Full concave cylinders: bores/drilled holes, not fillets or slot ends.

    A cylindrical face is concave when its outward normal points TOWARD the
    axis. Faces are grouped by (axis line, radius); a group whose summed arc
    reaches 330 deg is a hole (OCCT often splits a hole into two 180 deg faces).
    """
    groups = {}
    for f in shape.Faces:
        s = f.Surface
        if not isinstance(s, Part.Cylinder):
            continue
        try:
            u0, u1, v0, v1 = f.ParameterRange
            um, vm = 0.5 * (u0 + u1), 0.5 * (v0 + v1)
            p = f.valueAt(um, vm)
            n = f.normalAt(um, vm)
            ax = App.Vector(s.Axis)
            ax.normalize()
            c = App.Vector(s.Center)
            d = p - c
            radial = d - ax * d.dot(ax)
            if radial.Length < 1e-9 or n.dot(radial) >= 0:
                continue                                # convex: a boss, a wheel
            # canonical axis line: direction sign-fixed, foot point nearest origin
            comps = [ax.x, ax.y, ax.z]
            k = max(range(3), key=lambda i: abs(comps[i]))
            if comps[k] < 0:
                ax = ax * -1
            foot = c - ax * c.dot(ax)
            key = (round(s.Radius, 2), round(ax.x, 3), round(ax.y, 3), round(ax.z, 3),
                   round(foot.x, 1), round(foot.y, 1), round(foot.z, 1))
            groups[key] = groups.get(key, 0.0) + abs(u1 - u0)
        except Exception:                               # noqa: BLE001
            continue
    return sorted(round(2 * k[0], 2) for k, arc in groups.items()
                  if arc >= math.radians(min_arc_deg))


# ------------------------------------------- R173 geometry probes (shift 4)
# Each probe measures the document with OCCT (Part sections, Part.makeLine),
# never with production's tessellated ray caster or its intent.json, so a
# ./check that is wrong cannot agree with the benchmark by construction (P2).
RAY_FAR_MM = 200.0          # a ray that meets no part within this is open
SOCKET_GRID = 7             # rays per side over the USB-C receptacle mouth
SOCKET_INSET_MM = 0.3       # grid kept this far inside the mouth's outline
FACE_GRID = 9               # rays per side over a module's working face
FACE_INSET_MM = 1.0
RAY_LIFT_MM = 0.2           # rays start this far off the module
CLOSED_GRID = 5             # rays per side, per direction, over the board
CLOSED_INSET = 0.1          # share of the board's extent kept free at each side
CLOSED_MAX_OPEN = 0.5       # a direction with more rays out than this is open
CHANNEL_STATIONS = 9        # sections along each channel
CHANNEL_MIN_ARC_DEG = 180   # a slotted Ø6 channel with a 4.5 slot is ~263 deg
# The USB-C receptacle is found in the module's mesh by its size: the USB
# Type-C receptacle shell is about 8.9 x 3.3 mm (USB-IF Type-C spec); the
# Atech usbc mesh's shell component MEASURES 10.0 x 3.5 mm (2026-09-25,
# ports 1 / 12 / 7), so the window below takes both.
USBC_MOUTH_MM = ((2.5, 4.5), (8.0, 11.0))


def _seg_box(bb, p, d, far):
    """Does the segment p .. p + far*d meet the (loose) box bb? Slab test;
    a cheap filter before an OCCT section."""
    lo = (bb.XMin - 0.01, bb.YMin - 0.01, bb.ZMin - 0.01)
    hi = (bb.XMax + 0.01, bb.YMax + 0.01, bb.ZMax + 0.01)
    t0, t1 = 0.0, far
    for k in range(3):
        pk, dk = (p.x, p.y, p.z)[k], (d.x, d.y, d.z)[k]
        if abs(dk) < 1e-12:
            if pk < lo[k] or pk > hi[k]:
                return False
            continue
        a, b = (lo[k] - pk) / dk, (hi[k] - pk) / dk
        if a > b:
            a, b = b, a
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return False
    return True


def ray_first_hit(shapes, p, d, far=RAY_FAR_MM):
    """(distance, index) of the first of `shapes` the segment p .. p+far*d
    meets, measured by an OCCT section of the shape with that line; (None,
    None) when it meets nothing. `d` is a unit App.Vector."""
    best = (None, None)
    q = p + d * far
    line = None
    for i, sh in enumerate(shapes):
        if not _seg_box(sh.BoundBox, p, d, far):
            continue
        line = line or Part.makeLine(p, q)
        try:
            sec = sh.section(line)
        except Exception:                               # noqa: BLE001
            continue
        for v in sec.Vertexes:
            t = (v.Point - p).dot(d)
            if t >= -1e-6 and (best[0] is None or t < best[0]):
                best = (t, i)
    return best


def overall_box(shapes):
    """Tight world box of the union of shapes -> [X, Y, Z] lengths, box."""
    bb = _tight_bbox(Part.makeCompound(list(shapes)))
    return [bb.XLength, bb.YLength, bb.ZLength], bb


def channel_groups(shape, d_lo, d_hi, min_arc_deg=CHANNEL_MIN_ARC_DEG):
    """Concave cylinders with a diameter in [d_lo, d_hi] whose faces sum to
    at least min_arc_deg about one axis line: a round channel, closed (a
    bore) or slotted (a C). -> [{"d", "ax", "foot", "t": [lo, hi], "arc_deg"}]
    with t measured along ax from the foot point (the axis point nearest the
    origin, so ax . foot = 0)."""
    groups = []
    for f in shape.Faces:
        s = f.Surface
        if not isinstance(s, Part.Cylinder):
            continue
        if not (d_lo <= 2 * s.Radius <= d_hi):
            continue
        try:
            u0, u1, v0, v1 = f.ParameterRange
            um, vm = 0.5 * (u0 + u1), 0.5 * (v0 + v1)
            p, n = f.valueAt(um, vm), f.normalAt(um, vm)
            ax = App.Vector(s.Axis)
            ax.normalize()
            c = App.Vector(s.Center)
            dd = p - c
            radial = dd - ax * dd.dot(ax)
            if radial.Length < 1e-9 or n.dot(radial) >= 0:
                continue                                # convex
            comps = [ax.x, ax.y, ax.z]
            k = max(range(3), key=lambda i: abs(comps[i]))
            if comps[k] < 0:
                ax = ax * -1
            foot = c - ax * c.dot(ax)
            ts = [(f.valueAt(um, v) - foot).dot(ax) for v in (v0, v1)]
        except Exception:                               # noqa: BLE001
            continue
        for g in groups:
            if abs(g["d"] - 2 * s.Radius) < 0.02 and abs(abs(g["ax"].dot(ax)) - 1) < 1e-4 \
                    and (g["foot"] - foot).Length < 0.05:
                g["arc_deg"] += math.degrees(abs(u1 - u0))
                g["t"] = [min(g["t"][0], *ts), max(g["t"][1], *ts)]
                break
        else:
            groups.append({"d": 2 * s.Radius, "ax": ax, "foot": foot,
                           "t": [min(ts), max(ts)],
                           "arc_deg": math.degrees(abs(u1 - u0))})
    return [g for g in groups if g["arc_deg"] >= min_arc_deg]


def channel_open_along(shape, g, stations=CHANNEL_STATIONS):
    """A push-in channel is open along its whole length: at every section
    across its axis, the channel's centre lies in no closed loop of the
    section (a C, not an O). -> (open stations, [t of closed stations])."""
    t0, t1 = g["t"]
    inset = min(0.5, 0.1 * (t1 - t0))
    a, b = t0 + inset, t1 - inset
    ts = [a + (b - a) * i / float(stations - 1) for i in range(stations)] \
        if stations > 1 and b > a else [0.5 * (t0 + t1)]
    closed = []
    for t in ts:
        c = g["foot"] + g["ax"] * t
        shut = False
        for w in shape.slice(g["ax"], t):
            if not w.isClosed():
                continue
            try:
                if Part.Face(w).isInside(c, 1e-6, True):
                    shut = True
                    break
            except Exception:                           # noqa: BLE001
                continue
        if shut:
            closed.append(round(t, 2))
    return len(ts) - len(closed), closed


def channels_check(e, objs):
    """expect["channels_open"] = {"count", "d": [lo, hi]}: at least `count`
    round channels of that diameter, each open along its whole length."""
    spec = e["channels_open"]
    lo, hi = spec.get("d", [0, 1e9])
    rows = []
    for o in objs:
        for g in channel_groups(o.Shape, lo, hi):
            n_open, closed = channel_open_along(o.Shape, g)
            rows.append({"object": o.Label, "d": round(g["d"], 2),
                         "length": round(g["t"][1] - g["t"][0], 2),
                         "arc_deg": round(g["arc_deg"], 1),
                         "open_stations": n_open, "closed_at_t": closed})
    good = [r for r in rows if not r["closed_at_t"]]
    return len(good) >= spec["count"], {"open_channels": len(good), "want": spec["count"],
                                        "channels": rows}


def open_from_above_check(e, objs):
    """expect["open_from_above"] = {"min_depth_frac"}: a vertical ray down
    the XY centre of every large object (XY box >= 25 % of the product's)
    travels at least min_depth_frac of the product's height before it meets
    any part - a pot, cup or planter that a solid cap closes fails."""
    frac = e["open_from_above"].get("min_depth_frac", 0.3)
    shapes = [o.Shape for o in objs]
    _dims, bb = overall_box(shapes)
    H = bb.ZLength
    area = max(bb.XLength * bb.YLength, 1e-9)
    rows, ok = [], bool(objs) and H > 0
    for o in objs:
        ob = _tight_bbox(o.Shape)
        if ob.XLength * ob.YLength < 0.25 * area:
            continue
        p = App.Vector(ob.Center.x, ob.Center.y, bb.ZMax + 1.0)
        t, i = ray_first_hit(shapes, p, App.Vector(0, 0, -1), H + 2.0)
        depth = H if t is None else max(0.0, t - 1.0)
        rows.append({"object": o.Label, "xy": [round(p.x, 2), round(p.y, 2)],
                     "depth_mm": round(depth, 2),
                     "first_hit": objs[i].Label if i is not None else None})
        ok = ok and depth >= frac * H
    return ok and bool(rows), {"height_mm": round(H, 2), "min_depth_mm": round(frac * H, 2),
                               "rays": rows}


AXES = "XYZ"
NOTCH_INSET_MM = 0.5        # the across-line runs this far inside the open face
INSERT_STEP_MM = 0.5        # insertion_path grid across the held object's thickness
INSERT_STEP_WIDE_MM = 1.0   # ... and along its width


def _bb_lo_hi(bb):
    return [bb.XMin, bb.YMin, bb.ZMin], [bb.XMax, bb.YMax, bb.ZMax]


def line_hits(shapes, p, d, far):
    """Sorted distances along d (unit, axis-aligned) from p at which the
    segment p .. p+far*d crosses the surface of any of `shapes`, measured
    by an OCCT section with Part.makeLine (never a ray caster, P2).
    Crossings closer than 1e-4 mm are merged."""
    q = p + d * far
    line = None
    ts = []
    for sh in shapes:
        if not _seg_box(sh.BoundBox, p, d, far):
            continue
        line = line or Part.makeLine(p, q)
        try:
            sec = sh.section(line)
        except Exception:                               # noqa: BLE001
            continue
        ts += [(v.Point - p).dot(d) for v in sec.Vertexes]
    ts.sort()
    out = []
    for t in ts:
        if not out or t - out[-1] > 1e-4:
            out.append(t)
    return out


def _axis_point(vals):
    return App.Vector(vals[0], vals[1], vals[2])


def notch_rows(shape, A, D, side, spec):
    """The open rectangular notches of one orientation: a line across axis
    A, NOTCH_INSET_MM inside the D face on `side` (+1 / -1), at mid height
    of the third axis H; each gap between two material stretches of that
    line whose width is in spec["w"] is a notch. Its depth is a ray from
    outside that face inward (along -side*D) at the gap's centre; `through`
    = a line along H at half that depth meets nothing."""
    H = 3 - A - D
    bb = _tight_bbox(shape)
    lo, hi = _bb_lo_hi(bb)
    face = hi[D] if side > 0 else lo[D]
    mid_h = 0.5 * (lo[H] + hi[H])
    p = [0.0, 0.0, 0.0]
    p[A], p[D], p[H] = lo[A] - 1.0, face - side * NOTCH_INSET_MM, mid_h
    dA = [0.0, 0.0, 0.0]
    dA[A] = 1.0
    far = hi[A] - lo[A] + 2.0
    hits = line_hits([shape], _axis_point(p), _axis_point(dA), far)
    if len(hits) % 2:
        return None                                     # a tangency: not read
    w_lo, w_hi = spec.get("w", [0, 1e9])
    rows = []
    for i in range(1, len(hits) - 1, 2):
        w = hits[i + 1] - hits[i]
        if not (w_lo <= w <= w_hi):
            continue
        c = lo[A] - 1.0 + 0.5 * (hits[i] + hits[i + 1])
        q = [0.0, 0.0, 0.0]
        q[A], q[D], q[H] = c, face + side * 1.0, mid_h
        dD = [0.0, 0.0, 0.0]
        dD[D] = -side
        ext = hi[D] - lo[D]
        t, _i = ray_first_hit([shape], _axis_point(q), _axis_point(dD), ext + 2.0)
        depth = ext if t is None else max(0.0, t - 1.0)
        r = [0.0, 0.0, 0.0]
        r[A], r[D], r[H] = c, face - side * 0.5 * max(depth, 0.2), lo[H] - 1.0
        dH = [0.0, 0.0, 0.0]
        dH[H] = 1.0
        through = not line_hits([shape], _axis_point(r), _axis_point(dH),
                                hi[H] - lo[H] + 2.0)
        rows.append({"w_mm": round(w, 2), "at_mm": round(c, 2),
                     "depth_mm": round(depth, 2), "through": through})
    return rows


def notches_check(e, objs):
    """expect["notches_open"] = {"count", "w": [lo, hi], "min_depth",
    "through", "exact"} (D74): rectangular notches cut into a face - a gap
    of width w between two walls on a line across the part just inside the
    open face, at least min_depth deep from that face, and (through: true)
    open along the third axis. Every axis triple and both faces are tried
    per object; the orientation with the most good notches counts.
    `exact`: the count must match, not just be reached."""
    spec = e["notches_open"]
    need_through = bool(spec.get("through"))
    min_depth = spec.get("min_depth", 0.0)
    best_total, per_obj = 0, []
    for o in objs:
        best = None
        for A in range(3):
            for D in range(3):
                if D == A:
                    continue
                for side in (1, -1):
                    rows = notch_rows(o.Shape, A, D, side, spec)
                    if rows is None:
                        continue
                    good = [r for r in rows if r["depth_mm"] >= min_depth - 1e-6
                            and (r["through"] or not need_through)]
                    # most good notches; on a tie the most candidates, so a
                    # miss still shows the notches it measured
                    if best is None or (len(good), len(rows)) > \
                            (best["open_notches"], len(best["notches"])):
                        best = {"object": o.Label, "across": AXES[A],
                                "open_face": ("+" if side > 0 else "-") + AXES[D],
                                "open_notches": len(good), "notches": rows}
        if best:
            per_obj.append(best)
            best_total += best["open_notches"]
    want = spec["count"]
    ok = (best_total == want) if spec.get("exact") else (best_total >= want)
    return ok, {"open_notches": best_total, "want": want, "exact": bool(spec.get("exact")),
                "objects": per_obj}


def insertion_path_check(e, objs):
    """expect["insertion_path"] = {"section_mm": [W, t], "min_depth_mm",
    "min_mouth_mm"} (D73): the held object (a phone: W wide, t thick, its
    length along the way in) must be able to reach its seat. For each axis
    direction (+-X, +-Y, +-Z) and each way of laying W and t across the
    other two axes, a grid of lines along the entry axis (INSERT_STEP_WIDE_MM
    along W, INSERT_STEP_MM along t, inside the product's box) gives how deep
    each column is free from that face; the MOUTH is the widest run of
    columns, across t, that stays free to min_depth_mm over a stretch of W
    (one grid step of tolerance). Pass: the best mouth >= min_mouth_mm minus
    one step. A necessary condition measured on the parts, not the agent's
    prose or intent.json (P2)."""
    spec = e["insertion_path"]
    W, t_obj = spec["section_mm"]
    min_depth = spec.get("min_depth_mm", 1.0)
    min_mouth = spec.get("min_mouth_mm", t_obj)
    shapes = [o.Shape for o in objs]
    if not shapes:
        return False, {"error": "no parts"}
    _dims, bb = overall_box(shapes)
    lo, hi = _bb_lo_hi(bb)
    L = [hi[k] - lo[k] for k in range(3)]
    rows, best = [], None
    for k in range(3):
        for a in range(3):
            if a == k:
                continue
            b = 3 - k - a
            if L[a] < W - INSERT_STEP_WIDE_MM or L[b] <= 0:
                continue                                # W cannot lie along a
            na = max(1, int(round(L[a] / INSERT_STEP_WIDE_MM)))
            nb = max(1, int(round(L[b] / INSERT_STEP_MM)))
            sa, sb = L[a] / na, L[b] / nb
            need = max(1, int(math.ceil((W - sa) / sa - 1e-9)))
            if need > na:
                continue
            depth = {1: [[0.0] * nb for _ in range(na)], -1: [[0.0] * nb for _ in range(na)]}
            dk = [0.0, 0.0, 0.0]
            dk[k] = 1.0
            far = L[k] + 2.0
            for i in range(na):
                for j in range(nb):
                    p = [0.0, 0.0, 0.0]
                    p[a], p[b], p[k] = lo[a] + (i + 0.5) * sa, lo[b] + (j + 0.5) * sb, lo[k] - 1.0
                    hits = line_hits(shapes, _axis_point(p), _axis_point(dk), far)
                    if not hits:
                        depth[1][i][j] = depth[-1][i][j] = L[k]
                    else:
                        depth[-1][i][j] = max(0.0, hits[0] - 1.0)          # from -k
                        depth[1][i][j] = max(0.0, far - 1.0 - hits[-1])    # from +k
            for sign in (1, -1):
                free = [[depth[sign][i][j] >= min_depth - 1e-6 for j in range(nb)]
                        for i in range(na)]
                mouth = 0
                for i0 in range(na - need + 1):
                    run = 0
                    for j in range(nb):
                        if all(free[i][j] for i in range(i0, i0 + need)):
                            run += 1
                            mouth = max(mouth, run)
                        else:
                            run = 0
                row = {"enter": ("+" if sign > 0 else "-") + AXES[k], "width_along": AXES[a],
                       "mouth_mm": round(mouth * sb, 2), "step_mm": round(sb, 3)}
                rows.append(row)
                if best is None or row["mouth_mm"] > best["mouth_mm"]:
                    best = row
    if best is None:
        return False, {"error": "the product is narrower than the held object's %g mm" % W,
                       "box_mm": [round(x, 2) for x in L]}
    ok = best["mouth_mm"] >= min_mouth - best["step_mm"] - 1e-6
    return ok, {"mouth_mm": best["mouth_mm"], "enter": best["enter"],
                "min_mouth_mm": min_mouth, "min_depth_mm": min_depth,
                "section_mm": [W, t_obj], "directions": rows}


HINGE_STEP_DEG = 5.0        # hinge_opens sweep step (D77: blocked from 5 deg)
HINGE_MIN_ARC_DEG = 180     # a knuckle bore; OCCT may split it into halves
HINGE_AXIS_TOL_MM = 0.1     # bores on one axis line in different parts
HINGE_SIGN_DEG = 10.0       # trial rotation that picks the opening direction


def hinge_axis(objs, d_lo, d_hi):
    """The pin axis MEASURED on the parts (D77): concave cylinders of a
    diameter in [d_lo, d_hi] (channel_groups) that lie on one axis line in
    at least two different parts - the knuckle bores. Of several such lines
    the one threading the most parts, then the longest, wins.
    -> {"point", "dir", "objects": [index], "bores": [...]} or None."""
    lines = []
    for i, o in enumerate(objs):
        for g in channel_groups(o.Shape, d_lo, d_hi, HINGE_MIN_ARC_DEG):
            for ln in lines:
                if abs(abs(ln["dir"].dot(g["ax"])) - 1) < 1e-4 and \
                        (ln["point"] - g["foot"]).Length < HINGE_AXIS_TOL_MM:
                    break
            else:
                ln = {"point": g["foot"], "dir": g["ax"], "objects": [], "bores": [],
                      "len": 0.0}
                lines.append(ln)
            if i not in ln["objects"]:
                ln["objects"].append(i)
            ln["bores"].append({"object": o.Label, "d": round(g["d"], 3),
                                "t": [round(g["t"][0], 2), round(g["t"][1], 2)]})
            ln["len"] += g["t"][1] - g["t"][0]
    lines = [ln for ln in lines if len(ln["objects"]) >= 2]
    if not lines:
        return None
    return max(lines, key=lambda ln: (len(ln["objects"]), ln["len"]))


def _com(shapes):
    """Volume-weighted centre of mass of solids (None when there is no volume)."""
    tot, acc = 0.0, App.Vector(0, 0, 0)
    for sh in shapes:
        for s in sh.Solids:
            v = s.Volume
            tot += v
            acc = acc + s.CenterOfMass * v
    return acc * (1.0 / tot) if tot > 1e-9 else None


def hinge_opens_check(e, objs):
    """expect["hinge_opens"] = {"bore_d": [lo, hi], "range_deg": [a, b]}
    (R202 / D77, the S6-5 lid that hit the back wall from 5 deg): find the
    pin axis on the parts (hinge_axis), take the largest part on it as the
    fixed body and the other parts on it as the moving leaf, and sweep the
    leaf about the axis from a to b in HINGE_STEP_DEG steps. The opening
    sense is the one that carries the leaf's centre of mass AWAY from the
    fixed body's (a +-HINGE_SIGN_DEG trial) - geometry, never the overlap it
    is about to measure. FAIL at the first angle where the leaf's common
    volume with any part that does not move exceeds OVERLAP_TOL_MM3. Measured
    on the parts with OCCT, never ./check's motion sweep or intent.json (P2)."""
    spec = e["hinge_opens"]
    lo, hi = spec.get("bore_d", [0.0, 1e9])
    a0, a1 = spec.get("range_deg", [0.0, 90.0])
    if not objs:
        return False, {"error": "no parts"}
    ax = hinge_axis(objs, lo, hi)
    if ax is None:
        return False, {"error": "no bore of d in [%g, %g] shared by two parts: no pin axis"
                       % (lo, hi)}
    on = ax["objects"]
    fixed = max(on, key=lambda i: objs[i].Shape.Volume)
    moving = [i for i in on if i != fixed]
    still = [i for i in range(len(objs)) if i not in moving]
    P, D = ax["point"], ax["dir"]
    leaf = [objs[i].Shape for i in moving]

    def turned(deg):
        out = []
        for sh in leaf:
            c = sh.copy()
            c.rotate(P, D, deg)
            out.append(c)
        return out
    c_fixed, c_leaf = _com([objs[fixed].Shape]), _com(leaf)
    if c_fixed is None or c_leaf is None:
        return False, {"error": "a hinge part has no volume"}
    dist = {s: (_com(turned(s * HINGE_SIGN_DEG)) - c_fixed).Length for s in (1, -1)}
    sign = 1 if dist[1] >= dist[-1] else -1
    n = max(1, int(math.ceil((a1 - a0) / HINGE_STEP_DEG - 1e-9)))
    sweep, first = [], None
    for k in range(n + 1):
        deg = a0 + (a1 - a0) * k / float(n)
        worst = (0.0, None)
        for sh, i in zip(turned(sign * deg), moving):
            for j in still:
                other = objs[j].Shape
                bb = sh.BoundBox
                bb.enlarge(0.5)     # a bound, not a measurement: only skip clear misses
                if not bb.intersect(other.BoundBox):
                    continue
                v = sh.common(other).Volume
                if v > worst[0]:
                    worst = (v, "%s/%s" % (objs[i].Label, objs[j].Label))
        sweep.append([round(deg, 2), round(worst[0], 3)] + ([worst[1]] if worst[1] else []))
        if first is None and worst[0] > OVERLAP_TOL_MM3:
            first = round(deg, 2)
    return first is None, {
        "axis": {"point": [round(P.x, 3), round(P.y, 3), round(P.z, 3)],
                 "dir": [round(D.x, 4), round(D.y, 4), round(D.z, 4)],
                 "bores": ax["bores"]},
        "fixed": objs[fixed].Label, "moving": [objs[i].Label for i in moving],
        "open_sign": sign, "range_deg": [a0, a1], "step_deg": round((a1 - a0) / n, 3),
        "first_blocked_deg": first,
        "max_common_mm3": max(r[1] for r in sweep), "sweep": sweep}


MATE_ROOT_TOL_MM = 0.05     # a peg's root end lies on the flat face it stands out of
MATE_ROOT_AREA = 2.0        # ... whose area is at least this x the peg's section
MATE_ROOT_GAP = 0.5         # ... or up to this x the peg's d away (a root fillet / chamfer)
MATE_MARGIN_PITCHES = 1     # the modelled board reaches this far past the part


def peg_groups(shape, d_lo, d_hi):
    """CONVEX cylinders of a diameter in [d_lo, d_hi] grouped by axis line
    (the mirror of channel_groups): pegs, pins, round bars.
    -> [{"d", "ax", "foot", "t": [lo, hi]}], t along ax from the foot."""
    groups = []
    for f in shape.Faces:
        s = f.Surface
        if not isinstance(s, Part.Cylinder) or not (d_lo <= 2 * s.Radius <= d_hi):
            continue
        try:
            u0, u1, v0, v1 = f.ParameterRange
            um, vm = 0.5 * (u0 + u1), 0.5 * (v0 + v1)
            p, n = f.valueAt(um, vm), f.normalAt(um, vm)
            ax = App.Vector(s.Axis)
            ax.normalize()
            c = App.Vector(s.Center)
            dd = p - c
            radial = dd - ax * dd.dot(ax)
            if radial.Length < 1e-9 or n.dot(radial) <= 0:
                continue                                # concave: a hole
            comps = [ax.x, ax.y, ax.z]
            k = max(range(3), key=lambda i: abs(comps[i]))
            if comps[k] < 0:
                ax = ax * -1
            foot = c - ax * c.dot(ax)
            ts = [(f.valueAt(um, v) - foot).dot(ax) for v in (v0, v1)]
        except Exception:                               # noqa: BLE001
            continue
        for g in groups:
            if abs(g["d"] - 2 * s.Radius) < 0.02 and abs(abs(g["ax"].dot(ax)) - 1) < 1e-4 \
                    and (g["foot"] - foot).Length < 0.05:
                g["t"] = [min(g["t"][0], *ts), max(g["t"][1], *ts)]
                break
        else:
            groups.append({"d": 2 * s.Radius, "ax": ax, "foot": foot,
                           "t": [min(ts), max(ts)]})
    return groups


def peg_root(shape, g):
    """A peg stands out of a FLAT face: the end of the cylinder (t lo or t
    hi) that lies on a planar face with its normal along the axis and an
    area of at least MATE_ROOT_AREA x the peg's section is its root (a
    backplate, not the peg's own end cap). A filleted or chamfered root
    leaves the cylinder short of the face: a face up to MATE_ROOT_GAP x d
    beyond the end counts when it reaches within r + gap of the axis there
    (the fillet's edge on it), the nearest such face first.
    -> (root t on the face, tip sign +1 / -1, gap mm) or None (a bar, a
    curl's tail: no flat face at either end)."""
    r = 0.5 * g["d"]
    need = MATE_ROOT_AREA * math.pi * r * r
    reach = MATE_ROOT_GAP * g["d"]
    found = []
    for f in shape.Faces:
        s = f.Surface
        if not isinstance(s, Part.Plane):
            continue
        n = App.Vector(s.Axis)
        if abs(abs(n.dot(g["ax"])) - 1) > 1e-4 or f.Area < need:
            continue
        t_face = (App.Vector(s.Position) - g["foot"]).dot(g["ax"])
        for t_end, sign in ((g["t"][0], 1), (g["t"][1], -1)):
            gap = (t_end - t_face) * sign               # > 0: the face is beyond the end
            if not -MATE_ROOT_TOL_MM <= gap <= reach + MATE_ROOT_TOL_MM:
                continue
            gap = max(gap, 0.0)
            if gap > MATE_ROOT_TOL_MM:
                try:
                    near = f.distToShape(Part.Vertex(g["foot"] + g["ax"] * t_face))[0]
                except Exception:                       # noqa: BLE001
                    continue
                if near > r + gap + MATE_ROOT_TOL_MM:
                    continue                            # a parallel face elsewhere
            else:
                t_face, gap = t_end, 0.0
            found.append((t_face, sign, gap, f.Area))
    if not found:
        return None
    t_face, sign, gap, _a = min(found, key=lambda x: (round(x[2], 3), -x[3]))
    return t_face, sign, gap


def _root_lift(shape, point, d, r, gap, hole_d, T):
    """A root fillet holds the board off the root face: the least lift h in
    [0, gap] along d at which a ring (hole_d .. r + gap + 0.1, T long) from
    point + d*h has no common with the part, by bisection (0.001 mm)."""
    r_out = r + gap + 0.1
    if r_out <= 0.5 * hole_d:
        return 0.0

    def hits(h):
        p0 = point + d * h
        ring = Part.makeCylinder(r_out, T, p0, d).cut(Part.makeCylinder(0.5 * hole_d, T, p0, d))
        return shape.common(ring).Volume > OVERLAP_TOL_MM3
    if not hits(0.0):
        return 0.0
    lo, hi = 0.0, gap
    while hi - lo > 1e-3:
        mid = 0.5 * (lo + hi)
        if hits(mid):
            lo = mid
        else:
            hi = mid
    return hi


def pegboard_shape(origin, d, u, T, hole_d, pitch, span_u, span_w):
    """A pegboard plate T thick from `origin`'s plane along d, holes of
    hole_d on a square grid of `pitch` through `origin` along u and w = d x u,
    covering span_u / span_w = (lo, hi) in grid steps."""
    w = d.cross(u)
    w.normalize()
    lo_u, hi_u = span_u[0] - 0.5, span_u[1] + 0.5
    lo_w, hi_w = span_w[0] - 0.5, span_w[1] + 0.5
    corners = [origin + u * (a * pitch) + w * (b * pitch)
               for a, b in ((lo_u, lo_w), (hi_u, lo_w), (hi_u, hi_w), (lo_u, hi_w))]
    plate = Part.Face(Part.makePolygon(corners + [corners[0]])).extrude(d * T)
    holes = [Part.makeCylinder(0.5 * hole_d, T + 2.0,
                               origin + u * (i * pitch) + w * (j * pitch) - d * 1.0, d)
             for i in range(span_u[0], span_u[1] + 1)
             for j in range(span_w[0], span_w[1] + 1)]
    return plate.cut(Part.makeCompound(holes)) if holes else plate


def mates_check(e, objs):
    """expect["mates"] = {"board": "pegboard", "thick_mm", "hole_d", "pitch",
    "peg_d": [lo, hi], "min_pegs"} (R213 / D79, the S7 c2n3 hook whose arm
    root ran 4.9 mm into the board): the reference object the prompt fully
    specifies is MODELLED and placed where the part installs, then the part's
    common with it must be <= OVERLAP_TOL_MM3 (pegs pass through its holes,
    so only material outside the holes counts).
    Placement, measured on the parts, never read from intent.json (P2): the
    pegs are convex cylinders of peg_d standing out of a flat face
    (peg_root); the board's front face is that face, lifted where a root
    fillet meets the hole's edge (_root_lift) (when the pegs
    disagree, the root farthest along the pegs: a board slid on from the
    tips stops at the first face it meets), its normal the peg axis, its hole grid through the
    first peg's axis and along the line between two pegs (one peg: along
    world Z projected into the board plane, world X when the peg is
    vertical)."""
    spec = e["mates"]
    T = spec.get("thick_mm", 5.0)
    hole_d = spec.get("hole_d", 6.35)
    pitch = spec.get("pitch", 25.4)
    lo, hi = spec.get("peg_d", [0.5 * hole_d, hole_d])
    if not objs:
        return False, {"error": "no parts"}
    pegs = []
    for o in objs:
        for g in peg_groups(o.Shape, lo, hi):
            root = peg_root(o.Shape, g)
            if root is None:
                continue
            t_root, sign, gap = root
            d = g["ax"] * sign                          # root -> tip
            point = g["foot"] + g["ax"] * t_root
            lift = _root_lift(o.Shape, point, d, 0.5 * g["d"], gap, hole_d, T) \
                if gap > 0 else 0.0
            pegs.append({"object": o.Label, "d_mm": round(g["d"], 3), "dir": d,
                         "point": point + d * lift, "lift_mm": round(lift, 3),
                         "length_mm": round(g["t"][1] - g["t"][0], 2)})
    if not pegs:
        return False, {"error": "no peg: no convex cylinder of d in [%g, %g] standing out "
                                "of a flat face" % (lo, hi)}
    # the pegs of one board share a direction: the largest such family
    fams = []
    for p in pegs:
        for f in fams:
            if f[0]["dir"].dot(p["dir"]) > 1 - 1e-4:
                f.append(p)
                break
        else:
            fams.append([p])
    fam = max(fams, key=lambda f: (len(f), sum(p["length_mm"] for p in f)))
    d = App.Vector(fam[0]["dir"])
    seat = max(fam, key=lambda p: p["point"].dot(d))    # where a board slid on stops
    s = seat["point"].dot(d)
    origin = fam[0]["point"] + d * (s - fam[0]["point"].dot(d))
    u = None
    for p in fam[1:]:
        v = p["point"] - fam[0]["point"]
        v = v - d * v.dot(d)
        if v.Length > 1e-3:
            u = v
            break
    if u is None:
        ref = App.Vector(0, 0, 1) if abs(d.z) < 0.9 else App.Vector(1, 0, 0)
        u = ref - d * ref.dot(d)
    u.normalize()
    w = d.cross(u)
    w.normalize()
    shapes = [o.Shape for o in objs]
    bb = _tight_bbox(Part.makeCompound(shapes))
    cu, cw = [], []
    for x in (bb.XMin, bb.XMax):
        for y in (bb.YMin, bb.YMax):
            for z in (bb.ZMin, bb.ZMax):
                q = App.Vector(x, y, z) - origin
                cu.append(q.dot(u) / pitch)
                cw.append(q.dot(w) / pitch)
    m = MATE_MARGIN_PITCHES
    span_u = (int(math.floor(min(cu))) - m, int(math.ceil(max(cu))) + m)
    span_w = (int(math.floor(min(cw))) - m, int(math.ceil(max(cw))) + m)
    board = pegboard_shape(origin, d, u, T, hole_d, pitch, span_u, span_w)
    rows, total, where = [], 0.0, None
    for o in objs:
        bb = o.Shape.BoundBox
        bb.enlarge(0.5)     # a bound, not a measurement: only skip clear misses
        if not bb.intersect(board.BoundBox):
            continue
        c = o.Shape.common(board)
        v = c.Volume
        if v > OVERLAP_TOL_MM3:
            cb = _tight_bbox(c)
            depth = max((vx.Point - origin).dot(d) for vx in c.Vertexes) if c.Vertexes else None
            rows.append({"object": o.Label, "common_mm3": round(v, 3),
                         "box_mm": [[round(cb.XMin, 2), round(cb.YMin, 2), round(cb.ZMin, 2)],
                                    [round(cb.XMax, 2), round(cb.YMax, 2), round(cb.ZMax, 2)]],
                         "into_board_mm": round(depth, 2) if depth is not None else None})
        total += v
    ok = total <= OVERLAP_TOL_MM3 and len(fam) >= spec.get("min_pegs", 1)
    if rows:
        where = rows[0]
    return ok, {"common_mm3": round(total, 3), "tol_mm3": OVERLAP_TOL_MM3, "worst": where,
                "overlaps": rows, "pegs": len(fam), "min_pegs": spec.get("min_pegs", 1),
                "board": {"front_point": [round(origin.x, 3), round(origin.y, 3),
                                          round(origin.z, 3)],
                          "normal": [round(d.x, 4), round(d.y, 4), round(d.z, 4)],
                          "grid_u": [round(u.x, 4), round(u.y, 4), round(u.z, 4)],
                          "thick_mm": T, "hole_d": hole_d, "pitch": pitch,
                          "holes": (span_u[1] - span_u[0] + 1) * (span_w[1] - span_w[0] + 1)},
                "peg_list": [{"object": p["object"], "d_mm": p["d_mm"],
                              "root": [round(p["point"].x, 3), round(p["point"].y, 3),
                                       round(p["point"].z, 3)],
                              "lift_mm": p["lift_mm"],
                              "length_mm": p["length_mm"]} for p in fam]}


ENGAGE_SLIDE_MM = 1.0       # parts_engage: trial slide of each joined part
ENGAGE_MARGIN = 1e-3        # ... a blocked direction set inside an open hemisphere


def _slide_dirs():
    """26 unit directions: the axes, face and corner diagonals."""
    out = []
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for k in (-1, 0, 1):
                if i or j or k:
                    v = App.Vector(i, j, k)
                    v.normalize()
                    out.append(v)
    return out


def _dir_label(v):
    return "".join(("+" if c > 0 else "-") + a for c, a in zip((v.x, v.y, v.z), AXES)
                   if abs(c) > 1e-9)


def in_open_hemisphere(dirs, iters=500):
    """Is there an m with d . m > ENGAGE_MARGIN |m| for every unit d? The
    classic perceptron: m accumulates UNnormalised (renormalising each step
    voids its convergence bound - that version missed 10907 of 74380
    subsets of hemisphere sets of the 26 slide directions; this one misses
    none of 247948, in <= 14 updates). -> unit m or None."""
    if not dirs:
        return None
    m = App.Vector(0, 0, 0)
    for d in dirs:
        m = m + d
    for _ in range(iters):
        n = m.Length
        bad = [d for d in dirs if d.dot(m) <= ENGAGE_MARGIN * n] if n > 1e-9 else list(dirs)
        if not bad:
            m = App.Vector(m)
            m.normalize()
            return m
        m = m + bad[0]
    return None


def parts_engage_check(e, objs):
    """expect["parts_engage"] = {"min_parts", "slide_mm"} (R212 / D78, the
    S7 c1n4 / c2n4 "push-fit" end caps that were flat 2 mm plates only
    touching the case): every part but the largest that lies within slide_mm
    of another part is slid by slide_mm in 26 directions; a direction is
    BLOCKED when the moved part then shares more than OVERLAP_TOL_MM3 more
    with a part within reach than it did at rest. A part whose blocked
    directions all fit in one open hemisphere is held only from one side - a
    face touch, with no lip, plug or hook inside the opening - and FAILS; a
    lip or hook also blocks the
    slides along the joint face. Frame-free (no world-axis assumption), and
    measured with OCCT on the parts, never intent.json (P2). Parts farther
    than slide_mm from everything are listed, not judged; fewer than
    min_parts judged parts fails (min_parts 0: a one-part design has no
    joint to judge and passes, saying judged 0)."""
    spec = e["parts_engage"]
    slide = spec.get("slide_mm", ENGAGE_SLIDE_MM)
    want = spec.get("min_parts", 1)
    if len(objs) < 2:
        return want <= 0 and bool(objs), {
            "error": "fewer than two parts: nothing to engage", "parts": len(objs),
            "judged": 0, "min_parts": want}
    main = max(range(len(objs)), key=lambda i: objs[i].Shape.Volume)
    dirs = _slide_dirs()
    rows, separate = [], []
    for i, o in enumerate(objs):
        if i == main:
            continue
        sh = o.Shape
        near = []
        for j, other in enumerate(objs):
            if j == i:
                continue
            bb = sh.BoundBox
            bb.enlarge(slide + 0.1)
            if not bb.intersect(other.Shape.BoundBox):
                continue
            gap = sh.distToShape(other.Shape)[0]
            if gap <= slide + 1e-6:
                near.append((j, gap))
        if not near:
            separate.append(o.Label)
            continue
        rest = {j: sh.common(objs[j].Shape).Volume for j, _g in near}
        static = sum(rest.values())
        blocked = []
        for dv in dirs:
            c = sh.copy()
            c.translate(dv * slide)
            for j, _g in near:
                # blocked: the slide drives it further INTO a part (a part
                # that already overlaps is not thereby held from every side)
                if c.common(objs[j].Shape).Volume > rest[j] + OVERLAP_TOL_MM3:
                    blocked.append(dv)
                    break
        m = in_open_hemisphere(blocked)
        engaged = bool(blocked) and m is None
        row = {"object": o.Label, "near": [objs[j].Label for j, _g in near],
               "gap_mm": round(min(g for _j, g in near), 3),
               "common_mm3": round(static, 3),
               "blocked": len(blocked), "of": len(dirs), "engaged": engaged}
        if not engaged:
            free = [dv for dv in dirs if all((dv - b).Length > 1e-9 for b in blocked)]
            row["only_touches"] = True
            row["free"] = [_dir_label(dv) for dv in free]
            if m is not None:
                row["held_only_from"] = [round(m.x, 3), round(m.y, 3), round(m.z, 3)]
        rows.append(row)
    ok = len(rows) >= want and all(r["engaged"] for r in rows)
    return ok, {"main": objs[main].Label, "judged": len(rows), "min_parts": want,
                "slide_mm": slide, "parts": rows, "separate": separate,
                "only_touch": [r["object"] for r in rows if not r["engaged"]]}


def geometry_checks(expect, objs):
    """R173 expectation checks that need the shapes, not just the facts.
    -> [{check, pass, detail}]. Missing data fails."""
    e = expect or {}
    out = []

    def add(name, ok, detail):
        out.append({"check": name, "pass": bool(ok), "detail": detail})
    if "overall_z" in e:
        lo, hi = e["overall_z"]
        try:
            dims, _bb = overall_box([o.Shape for o in objs]) if objs else (None, None)
            z = round(dims[2], 2) if dims else None
            add("overall_z in [%g,%g]" % (lo, hi), z is not None and lo <= z <= hi,
                {"overall_xyz_mm": [round(v, 2) for v in dims] if dims else None})
        except Exception as exc:                        # noqa: BLE001
            add("overall_z in [%g,%g]" % (lo, hi), False, "measure failed: %s" % exc)
    if "volume_mm3" in e:
        lo, hi = e["volume_mm3"]
        try:
            v = round(sum(o.Shape.Volume for o in objs), 1) if objs else None
        except Exception as exc:                        # noqa: BLE001
            v = None
            add("volume_mm3 in [%g,%g]" % (lo, hi), False, "measure failed: %s" % exc)
        else:
            add("volume_mm3 in [%g,%g]" % (lo, hi), v is not None and lo <= v <= hi,
                {"volume_mm3": v})
    for key, fn in (("channels_open", channels_check),
                    ("open_from_above", open_from_above_check),
                    ("notches_open", notches_check),
                    ("insertion_path", insertion_path_check),
                    ("hinge_opens", hinge_opens_check),
                    ("mates", mates_check),
                    ("parts_engage", parts_engage_check)):
        if key not in e:
            continue
        try:
            ok, detail = fn(e, objs)
        except Exception as exc:                        # noqa: BLE001
            ok, detail = False, "measure failed: %s" % exc
        name = key
        if key == "channels_open":
            name = "channels_open >= %d x d%s" % (e[key]["count"], e[key].get("d"))
        elif key == "notches_open":
            name = "notches_open %s %d x w%s" % ("==" if e[key].get("exact") else ">=",
                                                e[key]["count"], e[key].get("w"))
        elif key == "insertion_path":
            name = "insertion_path mouth >= %g" % e[key].get(
                "min_mouth_mm", e[key]["section_mm"][1])
        elif key == "hinge_opens":
            name = "hinge_opens %g..%g deg" % tuple(e[key].get("range_deg", [0, 90]))
        elif key == "mates":
            name = "mates %s" % e[key].get("board", "reference")
        elif key == "parts_engage":
            name = "parts_engage >= %d" % e[key].get("min_parts", 1)
        add(name, ok, detail)
    return out


def _object_facts(obj):
    sh = obj.Shape
    bb = _tight_bbox(sh)
    dims = sorted([bb.XLength, bb.YLength, bb.ZLength], reverse=True)
    vol = sh.Volume
    box_vol = dims[0] * dims[1] * dims[2]
    return {
        "name": obj.Name, "label": obj.Label,
        "valid": bool(sh.isValid()),
        "solids": len(sh.Solids),
        "faces": len(sh.Faces),
        "volume_mm3": round(vol, 1),
        "dims_sorted_mm": [round(x, 2) for x in dims],
        "fill_ratio": round(vol / box_vol, 3) if box_vol > 1e-9 else None,
        "holes_d_mm": _holes(sh),
        # >= 240 deg: also a C-shaped channel (cable clip, snap-in bore)
        "bores_d_mm": _holes(sh, 240),
    }


def _check(expect, facts, whole_dims):
    """Every expectation -> (name, pass, detail). Missing data -> fail, not pass."""
    out = []

    def add(name, ok, detail):
        out.append({"check": name, "pass": bool(ok), "detail": detail})

    objs = facts
    add("all_valid", objs and all(o["valid"] for o in objs),
        [o["valid"] for o in objs])
    add("every_object_has_solid", objs and all(o["solids"] >= 1 for o in objs),
        [o["solids"] for o in objs])
    total_solids = sum(o["solids"] for o in objs)
    e = expect or {}
    if "min_solids" in e:
        add("min_solids>=%d" % e["min_solids"], total_solids >= e["min_solids"], total_solids)
    if "min_objects" in e:
        add("min_objects>=%d" % e["min_objects"], len(objs) >= e["min_objects"], len(objs))
    if e.get("single_solid_per_object"):
        add("single_solid_per_object", objs and all(o["solids"] == 1 for o in objs),
            {o["label"]: o["solids"] for o in objs})
    if "max_dim" in e:
        lo, hi = e["max_dim"]
        add("max_dim in [%g,%g]" % (lo, hi), whole_dims and lo <= whole_dims[0] <= hi,
            whole_dims[0] if whole_dims else None)
    if "any_dims" in e:
        free = list(whole_dims or [])
        ok = True
        for lo, hi in e["any_dims"]:
            hit = next((d for d in free if lo <= d <= hi), None)
            if hit is None:
                ok = False
            else:
                free.remove(hit)
        add("dims include %s" % e["any_dims"], ok, whole_dims)
    if "object_dims" in e:
        rng = e["object_dims"]
        hit = [o["label"] for o in objs
               if all(lo <= d <= hi for d, (lo, hi) in zip(o["dims_sorted_mm"], rng))]
        add("an object sized %s" % rng, bool(hit),
            hit or {o["label"]: o["dims_sorted_mm"] for o in objs})
    all_holes = [d for o in objs for d in o["holes_d_mm"]]
    if "min_holes" in e:
        lo, hi = e.get("hole_d", [0, 1e9])
        n = len([d for d in all_holes if lo <= d <= hi])
        add("holes d[%g,%g] >= %d" % (lo, hi, e["min_holes"]), n >= e["min_holes"],
            {"matching": n, "all_hole_d": all_holes})
    if "min_bores" in e:
        lo, hi = e.get("bore_d", [0, 1e9])
        bores = [d for o in objs for d in o.get("bores_d_mm", [])]
        n = len([d for d in bores if lo <= d <= hi])
        add("bores(>=240deg) d[%g,%g] >= %d" % (lo, hi, e["min_bores"]), n >= e["min_bores"],
            {"matching": n, "all_bore_d": bores})
    if "min_faces" in e:
        mf = max((o["faces"] for o in objs), default=0)
        add("faces>=%d" % e["min_faces"], mf >= e["min_faces"], mf)
    if "max_fill_ratio" in e:
        big = max(objs, key=lambda o: o["volume_mm3"]) if objs else None
        fr = big["fill_ratio"] if big else None
        add("fill_ratio<=%g" % e["max_fill_ratio"],
            fr is not None and fr <= e["max_fill_ratio"], fr)
    if "min_aspect" in e:
        a = (whole_dims[0] / whole_dims[2]) if whole_dims and whole_dims[2] > 1e-9 else None
        add("aspect>=%g" % e["min_aspect"], a is not None and a >= e["min_aspect"],
            round(a, 2) if a else None)
    return out


# ---------------------------------------------------------------- fitness
def _says_on_desk(prompt, expect):
    if (expect or {}).get("on_desk"):
        return True
    return "on a desk" in " ".join(str(prompt or "").lower().split())


def _is_mesh(o):
    return getattr(o, "TypeId", "") == "Mesh::Feature"


def _has_shape(o):
    sh = getattr(o, "Shape", None)
    return sh is not None and not sh.isNull() and not _is_mesh(o)


def overlaps(objs, allow=()):
    """Pairwise common volume of shape objects. Returns (pairs over the
    tolerance, meshes skipped). A bound-box test first: common() is only run
    where the boxes meet."""
    allowed = {frozenset(p) for p in (allow or [])}
    shp = [o for o in objs if _has_shape(o)][:MAX_OVERLAP_OBJECTS]
    bad = []
    for i in range(len(shp)):
        for j in range(i + 1, len(shp)):
            a, b = shp[i], shp[j]
            if frozenset((a.Label, b.Label)) in allowed or \
                    frozenset((a.Name, b.Name)) in allowed:
                continue
            if not a.Shape.BoundBox.intersect(b.Shape.BoundBox):
                continue
            try:
                v = a.Shape.common(b.Shape).Volume
            except Exception as exc:                    # noqa: BLE001
                bad.append({"pair": [a.Label, b.Label], "error": str(exc)})
                continue
            if v > OVERLAP_TOL_MM3:
                bad.append({"pair": [a.Label, b.Label], "common_mm3": round(v, 3)})
    return bad, [o.Label for o in objs if _is_mesh(o)]


def lowest_z(objs):
    """(lowest z, label) over Part shapes (tight box) and meshes."""
    best = None
    for o in objs:
        try:
            if _is_mesh(o):
                z = o.Mesh.BoundBox.ZMin
            elif _has_shape(o):
                z = _tight_bbox(o.Shape).ZMin
            else:
                continue
        except Exception:                               # noqa: BLE001
            continue
        if best is None or z < best[0]:
            best = (z, o.Label)
    return best


def tooth_count(shape):
    """Teeth on the outline of the section at mid-height of the thinnest
    axis: upward crossings of the mid radius along the outer wire. Returns
    (count | None, detail)."""
    bb = _tight_bbox(shape)
    lens = [bb.XLength, bb.YLength, bb.ZLength]
    k = lens.index(min(lens))
    axis = [App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1)][k]
    lo_hi = [(bb.XMin, bb.XMax), (bb.YMin, bb.YMax), (bb.ZMin, bb.ZMax)][k]
    mid = 0.5 * (lo_hi[0] + lo_hi[1])
    wires = shape.slice(axis, mid)
    if not wires:
        return None, "no section at mid-height"

    def area(w):
        try:
            return Part.Face(w).Area
        except Exception:                               # noqa: BLE001
            return 0.0                                  # an open wire: not the outline
    outer = max(wires, key=area)
    pts = outer.discretize(Number=4000)
    c = App.Vector(bb.Center)
    radii = []
    for p in pts:
        d = p - c
        d = d - axis * d.dot(axis)
        radii.append(d.Length)
    r_lo, r_hi = min(radii), max(radii)
    if r_hi <= 0 or (r_hi - r_lo) < 0.02 * r_hi:
        return 0, {"r_min": round(r_lo, 3), "r_max": round(r_hi, 3)}
    thr = 0.5 * (r_lo + r_hi)
    above = [r > thr for r in radii]
    n = sum(1 for i in range(len(above)) if above[i] and not above[i - 1])
    return n, {"r_min": round(r_lo, 3), "r_max": round(r_hi, 3), "axis": "XYZ"[k]}


def atech_parts(doc):
    """(board object | None, [seated module objects]) by their Atech role."""
    board, mods = None, []
    for o in doc.Objects:
        role = getattr(o, "AtechRole", None)
        if role == "board" and board is None:
            board = o
        elif role == "module":
            mods.append(o)
    return board, mods


def _world_points(o):
    """World vertices of a Mesh::Feature as an (n, 3) array. The feature's
    Mesh already carries its own Placement; a parent container's placement
    (App::Part) is applied on top."""
    import numpy as np
    P = np.array([[p.x, p.y, p.z] for p in o.Mesh.Points], dtype=float)
    try:
        extra = o.getGlobalPlacement().multiply(o.Placement.inverse())
    except Exception:                                   # noqa: BLE001
        extra = None
    if extra is not None and not extra.isIdentity():
        M = extra.toMatrix()
        R = np.array([[M.A11, M.A12, M.A13], [M.A21, M.A22, M.A23], [M.A31, M.A32, M.A33]])
        P = P @ R.T + np.array([M.A14, M.A24, M.A34])
    return P


def plane_normal(P):
    """Unit normal of a flat point cloud: its least-variance principal axis."""
    import numpy as np
    Q = P - P.mean(axis=0)
    w, V = np.linalg.eigh(Q.T @ Q)
    n = V[:, 0]
    return n / np.linalg.norm(n), w


def board_tilt_deg(board):
    """Angle (deg) of the board's plane from vertical: 0 = standing upright,
    90 = lying flat. Also returns the normal."""
    n, _ = plane_normal(_world_points(board))
    tilt = math.degrees(math.asin(min(1.0, abs(float(n[2])))))
    return tilt, [round(float(x), 4) for x in n]


def _box_of_points(P):
    return [float(v) for v in P.min(axis=0)] + [float(v) for v in P.max(axis=0)]


def outside_mm(inner, outer):
    """How far box `inner` sticks out of box `outer`, per side (mm, > 0 is
    outside). Boxes are [xmin, ymin, zmin, xmax, ymax, zmax]."""
    sides = ("-x", "-y", "-z", "+x", "+y", "+z")
    out = {}
    for k in range(3):
        out[sides[k]] = round(outer[k] - inner[k], 3)
        out[sides[k + 3]] = round(inner[k + 3] - outer[k + 3], 3)
    return out


def _extra_xf(o):
    """(R, t) numpy transform of a parent container's placement on top of
    the feature's own (already in o.Mesh), or None."""
    import numpy as np
    try:
        extra = o.getGlobalPlacement().multiply(o.Placement.inverse())
    except Exception:                                   # noqa: BLE001
        return None
    if extra.isIdentity():
        return None
    M = extra.toMatrix()
    return (np.array([[M.A11, M.A12, M.A13], [M.A21, M.A22, M.A23], [M.A31, M.A32, M.A33]]),
            np.array([M.A14, M.A24, M.A34]))


def _module_axes(o):
    """The module's own three axes in world coordinates (global rotation)."""
    import numpy as np
    try:
        rot = o.getGlobalPlacement().Rotation
    except Exception:                                   # noqa: BLE001
        rot = o.Placement.Rotation
    return [np.array(list(rot.multVec(App.Vector(*e)))) for e in
            ((1, 0, 0), (0, 1, 0), (0, 0, 1))]


def usbc_socket(o):
    """The USB-C receptacle of a seated module, found in its MESH: the
    connected component whose cross-section across one of the module's axes
    is the mouth size (USBC_MOUTH_MM) and which sticks out past the module's
    main body along that axis. -> {"dir", "points"} or None."""
    import numpy as np
    xf = _extra_xf(o)
    comps = []
    for c in o.Mesh.getSeparateComponents():
        P = np.array([[p.x, p.y, p.z] for p in c.Points], dtype=float).reshape(-1, 3)
        if xf is not None:
            P = P @ xf[0].T + xf[1]
        if len(P):
            comps.append(P)
    if len(comps) < 2:
        return None
    comps.sort(key=len, reverse=True)
    main = comps[0]
    axes = _module_axes(o)
    best = None
    for P in comps[1:]:
        for k in range(3):
            others = [axes[j] for j in range(3) if j != k]
            spans = sorted(float(np.ptp(P @ a)) for a in others)
            (alo, ahi), (blo, bhi) = USBC_MOUTH_MM
            if not (alo <= spans[0] <= ahi and blo <= spans[1] <= bhi):
                continue
            for sgn in (1.0, -1.0):
                d = sgn * axes[k]
                out = float((P @ d).max() - (main @ d).max())
                if out > 0.05 and (best is None or out > best[0]):
                    best = (out, d, P)
    if best is None:
        return None
    return {"dir": best[1], "points": best[2], "protrudes_mm": round(best[0], 3)}


def _ray_grid(P, d, grid, inset):
    """Ray origins over the outline of points P seen along unit d: a
    grid x grid lattice inset from the outline, lifted off P's front."""
    import numpy as np
    a = np.cross(d, [0.0, 0.0, 1.0])
    if np.linalg.norm(a) < 1e-6:
        a = np.cross(d, [1.0, 0.0, 0.0])
    a = a / np.linalg.norm(a)
    b = np.cross(d, a)
    pa, pb, pd = P @ a, P @ b, P @ d

    def axis(lo, hi):
        lo, hi = lo + inset, hi - inset
        return np.linspace(lo, hi, grid) if hi > lo else np.array([(lo + hi) / 2.0])
    front = pd.max() + RAY_LIFT_MM
    return [a * u + b * v + d * front for u in axis(pa.min(), pa.max())
            for v in axis(pb.min(), pb.max())]


def open_rays(shapes, origins, d, far=RAY_FAR_MM):
    """(open, total, {label index: blocked count}) of rays along d."""
    dv = App.Vector(*[float(x) for x in d])
    n_open, blocked = 0, {}
    for q in origins:
        t, i = ray_first_hit(shapes, App.Vector(*[float(x) for x in q]), dv, far)
        if t is None:
            n_open += 1
        else:
            blocked[i] = blocked.get(i, 0) + 1
    return n_open, len(origins), blocked


def _dir_text(d):
    k = max(range(3), key=lambda i: abs(d[i]))
    if abs(abs(d[k]) - 1.0) < 0.02:
        return ("+" if d[k] > 0 else "-") + "XYZ"[k]
    return "(%.2f, %.2f, %.2f)" % tuple(float(x) for x in d)


def open_along_rows(board, mods, parts, specs):
    """expect["open_along"] = [{"module", "toward": "socket" | "face",
    "min_open_pct"}]: the share of rays that leave the product without
    meeting one of the agent's parts - from the USB-C receptacle's mouth
    along its axis ("socket"), or from the module's face away from the board
    along the board's normal ("face")."""
    import numpy as np
    shapes = [p.Shape for p in parts]
    rows = []
    for spec in specs:
        name, toward = spec["module"], spec.get("toward", "face")
        want = float(spec.get("min_open_pct", 1))
        hits = [m for m in mods if getattr(m, "AtechModule", "") == name]
        if not hits:
            rows.append({"module": name, "toward": toward, "pass": False,
                         "why": "not seated"})
            continue
        for m in hits:
            row = {"module": name, "label": m.Label, "toward": toward,
                   "min_open_pct": want}
            if toward == "socket":
                sock = usbc_socket(m)
                if sock is None:
                    row.update({"pass": False, "why": "no receptacle found in the mesh"})
                    rows.append(row)
                    continue
                d, P = sock["dir"], sock["points"]
                origins = _ray_grid(P, d, SOCKET_GRID, SOCKET_INSET_MM)
            else:
                if board is None:
                    row.update({"pass": False, "why": "no Atech board"})
                    rows.append(row)
                    continue
                BP = _world_points(board)
                n, _w = plane_normal(BP)
                P = _world_points(m)
                d = n if float(np.dot(P.mean(axis=0) - BP.mean(axis=0), n)) >= 0 else -n
                origins = _ray_grid(P, d, FACE_GRID, FACE_INSET_MM)
            k, total, blocked = open_rays(shapes, origins, d)
            pct = 100.0 * k / total if total else 0.0
            row.update({"dir": _dir_text(d), "open": k, "rays": total,
                        "open_pct": round(pct, 1),
                        "blocked_by": {parts[i].Label: c for i, c in blocked.items()},
                        "pass": pct >= want})
            rows.append(row)
    return rows


def closed_around_board(board, parts):
    """Is the product closed around the board? Along +- each of the board's
    principal axes, a CLOSED_GRID x CLOSED_GRID lattice of rays starts on
    the plane through the board's centre, spread over the board's extent
    (inset CLOSED_INSET of it). A direction is open when more than
    CLOSED_MAX_OPEN of its rays leave without meeting an agent part: a
    missing end or side is open, a window or a plug slot is not (one ray
    from the centre called a slot on the centre line an open end)."""
    import numpy as np
    P = _world_points(board)
    ctr = 0.5 * (P.min(axis=0) + P.max(axis=0))
    Q = P - P.mean(axis=0)
    _w, V = np.linalg.eigh(Q.T @ Q)
    shapes = [p.Shape for p in parts]
    rows = []
    for k in range(3):
        others = [V[:, j] for j in range(3) if j != k]
        spans = []
        for a in others:
            pa = (P - ctr) @ a
            lo, hi = pa.min(), pa.max()
            pad = CLOSED_INSET * (hi - lo)
            spans.append(np.linspace(lo + pad, hi - pad, CLOSED_GRID))
        origins = [ctr + others[0] * u + others[1] * v for u in spans[0] for v in spans[1]]
        for sgn in (1.0, -1.0):
            d = sgn * V[:, k]
            n_open, total, blocked = open_rays(shapes, origins, d, far=1000.0)
            rows.append({"dir": _dir_text(d), "open": n_open, "rays": total,
                         "closed": n_open <= CLOSED_MAX_OPEN * total,
                         "blocked_by": {parts[i].Label: c for i, c in blocked.items()}})
    return all(r["closed"] for r in rows), rows


def atech_fitness(doc, ends, e, add):
    """The S35 Atech checks (see the module docstring)."""
    board, mods = atech_parts(doc)
    parts = [o for o in ends if _has_shape(o) and not getattr(o, "AtechRole", None)]
    if "open_along" in e:
        rows = open_along_rows(board, mods, parts, e["open_along"])
        add("open_along %s" % "+".join("%s:%s" % (s["module"], s.get("toward", "face"))
                                       for s in e["open_along"]),
            bool(rows) and all(r["pass"] for r in rows), rows)
    if e.get("closed_around_board"):
        if board is None:
            add("closed_around_board", False, "no Atech board in the document")
        elif not parts:
            add("closed_around_board", False, "no case: the agent made no Part shape")
        else:
            ok, rows = closed_around_board(board, parts)
            add("closed_around_board", ok, rows)
    if "atech_modules" in e:
        seated = [str(getattr(m, "AtechModule", "")) for m in mods]
        missing, pool = [], list(seated)
        for name in e["atech_modules"]:
            if name in pool:
                pool.remove(name)
            else:
                missing.append(name)
        add("atech_modules %s" % "+".join(e["atech_modules"]), not missing,
            {"seated": seated, "missing": missing})
    if e.get("board_upright"):
        if board is None:
            add("board_upright", False, "no Atech board in the document")
        else:
            tilt, n = board_tilt_deg(board)
            add("board_upright", tilt <= UPRIGHT_TOL_DEG,
                {"tilt_from_vertical_deg": round(tilt, 2), "normal": n,
                 "tol_deg": UPRIGHT_TOL_DEG, "board": board.Label})
    if "modules_inside" in e:
        case = [o for o in ends if _has_shape(o)]
        if not case:
            add("modules_inside", False, "no case: the agent made no Part shape")
        else:
            bb = _tight_bbox(Part.makeCompound([o.Shape for o in case]))
            box = [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax]
            detail, ok = {"case_box_mm": [round(v, 2) for v in box],
                          "tol_mm": INSIDE_TOL_MM}, True
            for name in e["modules_inside"]:
                hits = [m for m in mods if getattr(m, "AtechModule", "") == name]
                if not hits:
                    detail[name] = "not seated"
                    ok = False
                    continue
                for m in hits:
                    out = outside_mm(_box_of_points(_world_points(m)), box)
                    worst = max(out.values())
                    detail[m.Label] = {"worst_outside_mm": round(worst, 3),
                                       "outside": {k: v for k, v in out.items() if v > 0}}
                    ok = ok and worst <= INSIDE_TOL_MM
            add("modules_inside %s" % "+".join(e["modules_inside"]), ok, detail)


def fitted_after_labels(doc, ends, seeds, workspace):
    """(labels, note) of intent.json "fitted_after" in `workspace`, resolved
    the way production ./check resolves it (agent_kit check._fitted_after:
    Name or Label of a non-Atech object with a Shape), restricted to the
    agent's own end results (never a seed, never a module). Not honoured -
    labels [] and a note saying why - when it names nothing buildable or
    when it would leave none of the agent's Part shapes as an obstacle."""
    if not workspace:
        return [], None
    path = os.path.join(workspace, "intent.json")
    if not os.path.isfile(path) or os.path.islink(path):
        return [], None
    try:
        with open(path, encoding="utf-8-sig") as fh:
            want = (json.load(fh) or {}).get("fitted_after")
    except (OSError, ValueError, AttributeError) as exc:
        return [], "intent.json unreadable: %s" % exc
    if want is None:
        return [], None
    if isinstance(want, str):
        want = [want]
    if not isinstance(want, list):
        return [], "fitted_after is not a list: %r" % (want,)
    seed_set = set(id(o) for o in seeds)
    parts = [o for o in ends if id(o) not in seed_set and _has_shape(o)
             and not getattr(o, "AtechRole", None)]
    out, missing = [], []
    for name in want:
        hit = [o for o in parts if name in (o.Name, o.Label)]
        if hit:
            if hit[0].Label not in out:
                out.append(hit[0].Label)
        else:
            missing.append(str(name))
    note = ("names no agent part: %s" % ", ".join(missing)) if missing else None
    if out and len(out) >= len(parts):
        return [], ("NOT honoured: %s would leave no agent part as an obstacle"
                    % ", ".join(out))
    return out, note


def fitness(doc, ends, seeds, expect, prompt, workspace=None):
    """S15 fitness checks -> list of {check, pass, detail}."""
    e = expect or {}
    out = []

    def add(name, ok, detail):
        out.append({"check": name, "pass": bool(ok), "detail": detail})

    objs = list(ends) + [o for o in seeds if o not in ends]
    bad, meshes = overlaps(objs, e.get("allow_overlap"))
    add("no_overlap", not bad, {"over_tol": bad, "tol_mm3": OVERLAP_TOL_MM3,
                                "shapes": len([o for o in objs if _has_shape(o)]),
                                "meshes_not_measured": meshes})
    if _says_on_desk(prompt, e):
        low = lowest_z(objs)
        add("not_below_desk", low is not None and low[0] >= -DESK_TOL_MM,
            {"lowest_z_mm": round(low[0], 3), "object": low[1]} if low else None)
    if "gear_teeth" in e:
        shp = [o for o in ends if _has_shape(o)]
        big = max(shp, key=lambda o: o.Shape.Volume) if shp else None
        n, detail = tooth_count(big.Shape) if big else (None, "no shape")
        add("gear_teeth==%d" % e["gear_teeth"], n == e["gear_teeth"],
            {"counted": n, "object": big.Label if big else None, "section": detail})
    if e.get("atech_check"):
        try:
            import atech_ports as ap
            fa, fa_note = fitted_after_labels(doc, ends, seeds, workspace)

            def run(fitted):
                kw = {"fitted_after": fitted} if fitted else {}
                res = ap.check(doc, **kw)
                verdicts = {name: {k: v.get("verdict") for k, v in r.items()}
                            for name, r in res.items()}
                flat = [v for r in verdicts.values() for v in r.values()]
                return verdicts, bool(flat) and all(v == "PASS" for v in flat)

            verdicts, ok = run(fa)
            if fa or fa_note:
                strict_v, strict_ok = run(None) if fa else (verdicts, ok)
                detail = {"verdicts": verdicts or "no Atech modules in the document",
                          "fitted_after": fa, "fitted_after_note": fa_note,
                          "strict_pass": strict_ok,
                          "strict_verdicts": strict_v}
            else:
                detail = verdicts or "no Atech modules in the document"
            add("atech_ports_check", ok, detail)
        except Exception as exc:                        # noqa: BLE001
            add("atech_ports_check", False, "check failed: %s" % exc)
    if any(k in e for k in ("atech_modules", "board_upright", "modules_inside",
                            "open_along", "closed_around_board")):
        try:
            atech_fitness(doc, [o for o in ends if o not in seeds], e, add)
        except Exception as exc:                        # noqa: BLE001
            add("atech_geometry", False, "check failed: %s" % exc)
    return out


# ----------------------------------------------------------------- render
def _render(objs, path):
    """Headless render: tessellate, flat-shade, two isometric views."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import numpy as np

    tris, all_pts = [], []
    palette = [(0.35, 0.64, 1.0), (0.88, 0.69, 0.32), (0.37, 0.73, 0.55),
               (0.60, 0.42, 1.0), (0.85, 0.40, 0.40)]
    cols = []
    for i, o in enumerate(objs):
        sh = o.Shape
        diag = max(sh.BoundBox.DiagonalLength, 1.0)
        pts, faces = sh.tessellate(diag * 0.004)
        P = np.array([[p.x, p.y, p.z] for p in pts]) if pts else np.zeros((0, 3))
        if len(P):
            all_pts.append(P)
        for f in faces:
            tris.append(P[list(f)])
            cols.append(palette[i % len(palette)])
    if not tris:
        return "nothing to render"
    T = np.array(tris)
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    ln = np.linalg.norm(n, axis=1)
    ln[ln == 0] = 1
    n = n / ln[:, None]
    allP = np.vstack(all_pts)
    mn, mx = allP.min(0), allP.max(0)
    ctr, half = (mn + mx) / 2, (mx - mn).max() / 2 or 1
    fig = plt.figure(figsize=(10, 5), dpi=90)
    for k, (elev, azim) in enumerate(((28, -60), (28, 120))):
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        e, a = math.radians(elev), math.radians(azim)
        light = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        light = light + np.array([0.3, -0.2, 0.6])
        light = light / np.linalg.norm(light)
        shade = 0.35 + 0.65 * np.abs(n @ light)
        fc = np.array(cols) * shade[:, None]
        pc = Poly3DCollection(T, facecolors=np.clip(fc, 0, 1), edgecolors="none")
        ax.add_collection3d(pc)
        for d, setter in enumerate((ax.set_xlim, ax.set_ylim, ax.set_zlim)):
            setter(ctr[d] - half, ctr[d] + half)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")
        ax.tick_params(labelsize=6)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return None


# ------------------------------------------------------ headless patching
_GUI_TOKENS = ("ViewObject", "FreeCADGui", "Gui.", "Gui)", "SendMsgToActiveView")


def _headless_patch(code):
    """Wrap every statement that touches the GUI in try/except: pass."""
    import ast
    tree = ast.parse(code)
    lines = code.splitlines()

    def touches(node):
        seg = "\n".join(lines[node.lineno - 1:getattr(node, "end_lineno", node.lineno)])
        return any(t in seg for t in _GUI_TOKENS)

    class T(ast.NodeTransformer):
        def generic_visit(self, node):
            super().generic_visit(node)
            for field in ("body", "orelse", "finalbody"):
                seq = getattr(node, field, None)
                if not isinstance(seq, list):
                    continue
                new = []
                for st in seq:
                    simple = isinstance(st, (ast.Expr, ast.Assign, ast.AugAssign,
                                             ast.AnnAssign, ast.Import, ast.ImportFrom))
                    if simple and touches(st):
                        new.append(ast.Try(
                            body=[st],
                            handlers=[ast.ExceptHandler(type=ast.Name("Exception", ast.Load()),
                                                        name=None, body=[ast.Pass()])],
                            orelse=[], finalbody=[]))
                    else:
                        new.append(st)
                setattr(node, field, new)
            return node

    tree = T().visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _gui_failure(error, code):
    """True when the failing line of <agent> touches the GUI."""
    import re
    lines = code.splitlines()
    nums = [int(m) for m in re.findall(r'File "<agent>", line (\d+)', error)]
    for n in nums[-1:]:
        if 1 <= n <= len(lines) and any(t in lines[n - 1] for t in _GUI_TOKENS):
            return True
    return "has no attribute 'ActiveDocument'" in error and "Gui" in error


# ------------------------------------------------------------------- modes
def mode_sysprompt(job):
    import inspect
    from acadagent import build
    doc = App.newDocument("Unnamed")
    kw = {}
    if job.get("request") is not None and \
            "request" in inspect.signature(build.system_prompt).parameters:
        kw["request"] = job["request"]
    return {"system_prompt": build.system_prompt(job["workspace"], **kw),
            "assembly_doc": build.assembly_doc(),
            "document_brief": build.document_brief(doc)}


def _run_seed(doc, seed):
    """Run a seed script into doc. Returns the objects it added."""
    before = {o.Name for o in doc.Objects}
    with open(seed, encoding="utf-8") as fh:
        code = fh.read()
    exec(compile(code, seed, "exec"), {"doc": doc, "App": App, "FreeCAD": App,
                                       "__name__": "__seed__"})
    doc.recompute()
    return [o for o in doc.Objects if o.Name not in before]


def _panel_turn_args(ws, text=None, doc=None):
    """AgentPanel._turn_args(ws, text=, doc=) run for real, without a panel
    widget, with the request text and the document production passes
    (R111; an older _turn_args without them gets ws only): a
    stand-in `self` that resolves every attribute from the AgentPanel class
    (methods bound to the stand-in, class constants as they are). So
    whatever _turn_args uses - the ATECH_ASSEMBLY.md copy (R14), library
    copies (S17), Agent Settings - is the shipped code, unmodified. Only
    instance state set in AgentPanel.__init__ would be missing, and that
    raises instead of being guessed."""
    import functools
    import types
    from acadagent import panel

    class _Self(object):
        def __getattr__(self, name):
            attr = getattr(panel.AgentPanel, name)
            if isinstance(attr, types.FunctionType):
                return functools.partial(attr, self)
            return attr
    import inspect
    params = inspect.signature(panel.AgentPanel._turn_args).parameters
    kw = {}
    if text is not None and "text" in params and "doc" in params:
        kw = {"text": text, "doc": doc}
    return panel.AgentPanel._turn_args(_Self(), ws, **kw)


def _sp_from_flags(extra):
    """Pre-S16 _turn_args returned flags: pull the system prompt out."""
    for flag in ("--append-system-prompt", "--append-system-prompt-file"):
        if flag in extra:
            v = extra[extra.index(flag) + 1]
            if flag.endswith("-file"):
                with open(v, encoding="utf-8") as fh:
                    return fh.read()
            return v
    return None


def mode_argv(job):
    """The claude command line production would run for this workspace:
    {"first"/"resume": argv, "stdin_first"/"stdin_resume": text written to
    the CLI's stdin (None when the prompt is on argv), "source",
    "private_dirs": temp dirs ClaudeRun made (system-prompt files) that the
    caller removes when the prompt is done, "document_brief"}."""
    import inspect
    from acadagent import build, claude_cli
    msg, sid = job["message"], job["session"]
    if job.get("workspace_root"):
        # The chat workspace made by PRODUCTION's build.new_workspace(), so
        # whatever it puts there (./check, S09) is there for the agent too -
        # rooted in the harness's temp dir instead of the user's data dir.
        root = job["workspace_root"]
        App.getUserAppDataDir = lambda: root.rstrip("/") + "/"
        ws = build.new_workspace()
    else:
        ws = job["workspace"]
    doc = App.newDocument("Unnamed")
    if job.get("seed"):
        _run_seed(doc, job["seed"])
    out = {"workspace": ws, "document_brief": build.document_brief(doc),
           "private_dirs": []}
    turn = _panel_turn_args(ws, text=job.get("request"), doc=doc)
    out["workspace_files"] = sorted(os.listdir(ws))
    params = inspect.signature(claude_cli.ClaudeRun.__init__).parameters
    if isinstance(turn, tuple):
        # S16 panel: _turn_args -> (system prompt, agent_argv kwargs), passed
        # as ClaudeRun(system_prompt=, agent=) - exactly _send_claude's call.
        sp, agent = turn
        out["source"] = ("panel.AgentPanel._turn_args -> ClaudeRun(system_prompt=, "
                         "agent=) -> claude_cli.agent_argv")
        kw = {"system_prompt": sp, "agent": agent}
    elif hasattr(claude_cli, "agent_argv") and "agent" in params:
        # claude_cli has S16 but the panel still returns flags: lean flags
        # from Agent Settings, the panel's system prompt.
        out["source"] = ("claude_cli.ClaudeRun(agent=claude_cli.agent_settings(), "
                         "system_prompt=<panel._turn_args>) -> agent_argv")
        kw = {"system_prompt": _sp_from_flags(turn),
              "agent": dict(claude_cli.agent_settings(), ws=ws)}
    else:
        out["source"] = "claude_cli.ClaudeRun._argv + panel.AgentPanel._turn_args"
        kw = {"extra_args": list(turn)}
    for key, session in (("first", None), ("resume", sid)):
        run = claude_cli.ClaudeRun(msg, cwd=ws, session_id=session,
                                   permission_mode="acceptEdits", **kw)
        try:
            out[key] = run._argv()
            on_argv = msg in out[key]
            out["stdin_" + key] = None if on_argv else (
                run.prompt_text() if hasattr(run, "prompt_text") else None)
            if getattr(run, "_private", None):
                out["private_dirs"].append(run._private)
            out["dropped_" + key] = list(getattr(run, "dropped", []) or [])
        finally:
            claude_cli.ClaudeRun._LIVE.discard(run)
    return out


def mode_build(job):
    from acadagent import build
    ws = job["workspace"]
    script = os.path.join(ws, build.SCRIPT)
    res_out = {"headless_patched": False}

    def run_once():
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        doc = App.newDocument("Unnamed")
        App.setActiveDocument(doc.Name)
        seeded = _run_seed(doc, job["seed"]) if job.get("seed") else []
        seeds[:] = [o.Name for o in seeded]
        t0 = time.time()
        r = build.apply(ws, [build.SCRIPT], None)
        return doc, r, time.time() - t0

    seeds = []
    doc, r, secs = run_once()
    if r is not None and not r.ok:
        with open(script, encoding="utf-8") as fh:
            code = fh.read()
        if _gui_failure(r.error, code):
            res_out["headless_first_error"] = r.error[-1500:]
            try:
                patched = _headless_patch(code)
                with open(script, "w", encoding="utf-8") as fh:
                    fh.write(patched)
                doc, r, secs = run_once()
                res_out["headless_patched"] = True
            finally:
                with open(script, "w", encoding="utf-8") as fh:
                    fh.write(code)                      # the agent's file, untouched
    res_out["build_seconds"] = round(secs, 3)
    if r is None:
        res_out.update(ok=False, error="nothing to build (no model.py)")
        return res_out
    res_out.update(ok=r.ok, error=r.error, created=r.created,
                   measurements=r.measurements, failures=build.failures(r) if r.ok else "",
                   document_brief=build.document_brief(doc))
    if job.get("preview") and r.ok and res_out["failures"]:
        # S49: Studio shows a preview short of intent.json only as "in
        # progress", not "check failed" - classified by production's own
        # AgentPanel._intent_only, not a copy of it.
        try:
            from acadagent import panel
            res_out["intent_only"] = bool(panel.AgentPanel._intent_only(r))
        except Exception as exc:                        # noqa: BLE001
            res_out["intent_only"] = None               # not measured, not False
            res_out["intent_only_error"] = repr(exc)[-300:]
    if not r.ok or job.get("preview"):
        return res_out
    ends = build._results([doc.getObject(n) for n in r.created if doc.getObject(n)])
    ends = [o for o in ends if getattr(o, "Shape", None) is not None and not o.Shape.isNull()]
    facts = []
    for o in ends:
        try:
            facts.append(_object_facts(o))
        except Exception as exc:                        # noqa: BLE001
            facts.append({"name": o.Name, "label": o.Label, "valid": False, "solids": 0,
                          "faces": 0, "volume_mm3": 0, "dims_sorted_mm": [0, 0, 0],
                          "fill_ratio": None, "holes_d_mm": [], "bores_d_mm": [],
                          "error": "measure failed: %s" % exc})
    whole = None
    try:
        comp = Part.makeCompound([o.Shape for o in ends])
        bb = _tight_bbox(comp)
        whole = [round(x, 2) for x in sorted([bb.XLength, bb.YLength, bb.ZLength], reverse=True)]
    except Exception as exc:                            # noqa: BLE001
        res_out["whole_bbox_error"] = str(exc)
    res_out["objects"] = facts
    res_out["whole_dims_sorted_mm"] = whole
    res_out["checks"] = _check(job.get("expect"), facts, whole) + \
        geometry_checks(job.get("expect"), ends)
    if (job.get("expect") or {}).get("no_failed_verdict"):
        # D74: production's own build.failures() (what Studio turns into the
        # red "build still fails") is empty on the final build
        res_out["checks"].append({"check": "no_failed_verdict",
                                  "pass": not res_out["failures"],
                                  "detail": res_out["failures"] or None})
    # fitness sees every end result, meshes included (seated Atech modules
    # are Mesh::Feature and have no Shape), plus the seed objects
    created = [doc.getObject(n) for n in r.created if doc.getObject(n)]
    all_ends = build._results(created)
    seed_objs = [doc.getObject(n) for n in seeds if doc.getObject(n)]
    t0 = time.time()
    try:
        res_out["fitness"] = fitness(doc, all_ends, seed_objs, job.get("expect"),
                                     job.get("prompt"), workspace=ws)
    except Exception as exc:                            # noqa: BLE001
        res_out["fitness"] = [{"check": "fitness", "pass": False,
                               "detail": "fitness failed: %s" % exc}]
    res_out["fitness_seconds"] = round(time.time() - t0, 3)
    res_out["seed_objects"] = [o.Label for o in seed_objs]
    if job.get("render"):
        t0 = time.time()
        try:
            why = _render(ends, job["render"])
            res_out["render"] = None if why else job["render"]
            res_out["render_note"] = why
        except Exception as exc:                        # noqa: BLE001
            res_out["render"] = None
            res_out["render_note"] = "render failed: %s" % exc
        res_out["render_seconds"] = round(time.time() - t0, 2)
    return res_out


def main():
    job_path = os.environ.get("EVAL_JOB")
    if not job_path:
        _crash("EVAL_JOB not set")
    with open(job_path, encoding="utf-8") as fh:
        job = json.load(fh)
    try:
        payload = {"sysprompt": mode_sysprompt, "argv": mode_argv,
                   "build": mode_build}[job["mode"]](job)
    except BaseException:                               # noqa: BLE001
        _crash(traceback.format_exc())
    _done(job["out"], payload)


main()
