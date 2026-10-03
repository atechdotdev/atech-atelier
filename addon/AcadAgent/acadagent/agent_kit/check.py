"""check - run model.py headless, measure what it built, render check.png.

RUN IT IN THE WORKSPACE, WITH THE BUNDLED freecadcmd (never system python):

    <freecadcmd> check.py

It builds ./model.py in a FRESH, EMPTY document (the same names model.py gets
in Studio: doc, App, FreeCAD), then prints ONE line:

    ATECH_CHECK={"ok": true, "objects": [...], "png": ".../check.png", ...}

  ok            false when model.py raised or added nothing
  error         the traceback; error_lines = [{"line": N, "code": "..."}]
                pointing into model.py (innermost last)
  objects       one entry per END RESULT (objects nothing else consumes):
                label, valid, solids, volume_mm3, bbox_min/max, size (a tight
                optimalBoundingBox - not the loose Shape.BoundBox)
  warnings      things that are legal but usually a mistake (2 solids in one
                object, a body touching nothing else)
  problems      things Studio will send back as a fix: an invalid shape, a
                body with no solid, a stray fragment solid, an overlap
                between bodies not listed in INTENDED_OVERLAPS, a miss
                against intent.json (the same comparison Studio makes), a
                failed Atech port check, and - when there is an Atech board -
                parts or modules below the desk, a module sticking out of
                the case, a board not oriented as intent.json "board" says
  atech         when model.py used the Atech library: the board (placement)
                and every seated module (module, ports, label, seeded=True
                for the user's own) - Studio seats the same ones in the
                document (PRD R92)
  png           check.png: two isometric views. Read it and LOOK at it.
                Not drawn when the check found problems (S39): the stale
                picture is removed and render_skipped says why.

intent.json and the user (R151): Studio writes .atech_turn.json when a turn
starts - {"fix": false, "request": <the user's message>} for the user's own
turn, fix=true for Studio's auto-fix turn (atech_geom.start_turn). In the
user's turn the agent may change intent.json (the user's message wins over
it); ./check only fails a model.py that writes intent.json while it runs. In
a fix turn intent.json is frozen as it stood when the fix turn started
("INTENT CHANGED"), except that a value from the user's message is always
accepted. With no .atech_turn.json (an older Studio) the pre-R151 rule
holds: recorded (.intent_first.json, read-only) at the turn's first check,
BEFORE model.py runs, frozen after (S37). A model.py that deletes or
rewrites the record, or the turn file, fails too (they are put back - R135).

intent.json "fitted_after": ["End_Cap_L", "End_Cap_R"] names parts fitted
AFTER the modules (end caps, a lid): the Atech slide-path check ignores
them, so the case can be closed; seated and interference still test them in
their closed position (R137). A name model.py has not built (yet) is a NOTE
and "fitted_after_missing" (S50: the draft names its caps before it builds
them) in the agent's ./check; Studio's own build (ATECH_CHECK_OUT set) still
fails on it, so a turn that never builds the part fails.

intent.json "motion": [{"part": "Lid", "axis": [[x, y, z], [dx, dy, dz]],
"range_deg": [0, 90]}] declares a part that turns (a hinged lid): it is
swept about the axis (right-hand rule, <= 10 deg steps) and the check FAILS
at the first angle it shares more than 0.01 mm3 with another part, naming
it (R202, D77); "motion_problems" carries that verdict for Studio. Each
round channel's wrap angle is printed as a CHANNEL line (S62); a clip or
holder whose channel wraps under 240 deg gets a WARNING (it holds nothing).

The user's objects (ATECH_CHECK_CONTEXT, below) are compared with every
body model.py builds: an overlap with one fails like any other, the user's
object named as such (R128). INTENDED_OVERLAPS never excuses it (R156): a
part that seats on the user's object needs a clearance, not an overlap.

intent.json is compared with the build (atech_geom.intent_problems, the
same comparison Studio makes). An overall size the user's message gives
("80 x 50 x 30 mm") is measured over ALL parts together, however
intent.json splits them per part (R168). A size miss names the axis, where
it runs and the part at each end (S52). Round channels open along their
length (a push-in slot) are reported as channels: counted as the intended
holes they are a NOTE, and intent.json may declare them as "slots" (R170).
A container's mouth (a jar's neck over its wider body) is not a hole
(R183). A target the user's message never states - a hole count when it
names no holes or slots, a size_mm number it never gives, a hole diameter
it never gives when the count is right - is the agent's own: its miss is a
NOTE, never a PROBLEM (S54). The line after an intent miss is Studio's own
(atech_geom.INTENT_RULE == build.INTENT_FIX_RULE, R170): it asks which side
is wrong, never "change model.py until the build meets it".

DESK (R177): when the user's message stands the product on a desk, table,
floor or shelf (or calls it a stand) and nothing hangs or clamps it, a
part reaching below z = 0 by more than a first layer (0.2 mm) is a PROBLEM
naming the part and its z min. With an Atech board the layout check judges
the desk instead.

A hole that goes through more than one wall on its axis (one
`cad.hole(..., through=True)` through a hollow case's front AND back wall)
is a WARNING naming each wall (R181); `through="wall"` stops at the first.

With an Atech board and seated modules, OPEN lines give, per module, the
share of a 13 x 13 grid of rays from its working face that leaves the
product within 200 mm (R152). The working face is the side away from the
board, except for a USB-C module: its socket mouth, measured from the mesh
(R164) - a slot over the module's cover lets no plug in. A light, screen,
button, speaker, sensor or USB-C socket that is 0 % open while the user's
message asks for one is a PROBLEM.

CONTAINER lines (R169): a part named as a container (pot, cup, planter,
mug, bowl...) that no ray into its middle gets half-way into - from above,
nor from any side (a wall planter lying on its side opens to the front) -
is a PROBLEM naming the z range that closes it from above (a WARNING for
an ambiguous name like "box", or when the request says closed).

WALL gives the thinnest wall a sampled, time-capped ray probe measured
(R154): a WARNING below 0.8 mm (2 x a 0.4 mm FDM nozzle), never a failure.
Per part it also gives the side walls' thickness as measured, normal to
the wall (R194: a 14 deg tapered wall offset 1.46 sideways is 1.41 thick),
and a NOTE when that differs from intent.json "wall_mm" - quote it.

Rectangular notches (R191) are declared as "slots": {"count": n, "w_mm":
w} (optional "depth_mm"): measured as two flat walls w apart with air
between and open past the part; a count that does not match is a NOTE
(CANNOT DETERMINE), never a failure. "slots" with "d_mm" stays a round
channel; rectangular notches of that width counted there are a NOTE.

HOLDS (R192): intent.json "holds": {"size_mm": [x, y, z], "enters": "+Z"}
declares a held object (its X, Y, Z as it sits in the part, and the side
it goes in from). Its box is pushed straight in from every side: a seat
it has room in but no side lets it reach is a PROBLEM naming the stop and
the measured mouth; the named side blocked while another is open, or a
way in whose measured mouth is narrower than the object (a snap fit at
best), is a WARNING; a part the probe could not judge is a NOTE (CANNOT
DETERMINE), never a silent pass.

A part named lid / cover / cap filling more than 85 % of its tight box
(and thicker than a plate) is a NOTE: a solid plug, where a lid's lip is
a ring (S58).

With an Atech board, MARGIN lines give each module's (and the board's)
measured outline margin to the part that encloses it, per side (R141):
quote these, never an estimate.

Human-readable OBJECT / MARGIN / OPEN / CONTAINER / WALL / HOLDS / NOTE /
PROBLEM / FLOATING / WARNING lines come first, then the ATECH_CHECK= line, and the LAST line is exactly
`CHECK PASS` or `CHECK FAIL: <reasons>`.

model.py may set  INTENDED_OVERLAPS = ["Label", ("A", "B"), ...]  to declare
bodies that are meant to intersect (a peg in a hole modelled line-on-line):
a single label may overlap anything, a pair only each other.

Headless there is no 3D view, so obj.ViewObject is None. Direct
`X.ViewObject.attr = value` assignments are RECORDED instead of executed
(objects[i]["view"], so Studio can apply the colours the script chose). Any
other line that touches the GUI and fails is handled by re-running once with
such lines skipped; the result then says headless_patched=true. Every other
error is real. headless_patched=true whenever any GUI line was rewritten
(recorded or skipped); headless_rerun=true only for the re-run.

Environment (all optional; Studio's sandbox uses them):
    ATECH_CHECK_SCRIPT    script to run            (default ./model.py)
    ATECH_CHECK_PNG       render target, '' = none (default: check.png next
                          to the script)
    ATECH_CHECK_OUT       directory: write result.json and one <Name>.brep
                          per end result into it
    ATECH_CHECK_TIMEOUT   seconds before the script is stopped (default 60)
    ATECH_CHECK_PATH      extra import dirs (os.pathsep-separated)
    ATECH_CHECK_CONTEXT   JSON list [{"name", "label", "brep"}]: the user's
                          objects, loaded into the fresh document first so
                          model.py sees what it would see in Studio. They are
                          not results; deleting or changing one fails the
                          build (Studio could not carry that over). An item
                          may say "role": "user" (a solid of the user's the
                          build must not run through) or any other role
                          (construction - a boolean's inputs): once any item
                          carries a role, only "user" ones are compared.
                          Untagged, the agent's ./check compares them all,
                          and Studio's build child (ATECH_CHECK_OUT) leaves
                          them to Studio's own user_overlaps (R128). Items
                          {"atech": "board", "placement"} and {"atech":
                          "module", "module", "ports", "label"} re-create the
                          Atech board and the user's seated modules with the
                          library (the board's placement may change).

Exit code: 0 ok, 1 model.py failed, 3 the checker itself crashed.
"""
import json
import math
import os
import re
import signal
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
MARK = "ATECH_CHECK="
_GUI_TOKENS = ("ViewObject", "FreeCADGui", "Gui.", "Gui)", "SendMsgToActiveView")


def _emit(payload, code):
    """Print the one result line and leave. freecadcmd exits 0 even when a
    script raised, and sys.exit() loses stdout under FreeCAD, hence os._exit."""
    out = os.environ.get("ATECH_CHECK_OUT")
    line = json.dumps(payload, default=str)
    if out:
        try:
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass
    # __stdout__: the watchdog thread emits while model.py's print() is still
    # redirected into a buffer, where the line would be lost.
    stream = sys.__stdout__ or sys.stdout
    stream.write("\n" + MARK + line + "\n")
    reasons = _fail_reasons(payload)
    stream.write(("CHECK FAIL: %s" % "; ".join(reasons)) if reasons else "CHECK PASS")
    stream.write("\n")
    stream.flush()
    sys.stderr.flush()
    os._exit(code)


def _fail_reasons(payload):
    if payload.get("checker_crash"):
        return ["the checker itself crashed"]
    out = []
    if not payload.get("ok"):
        el = payload.get("error_lines") or []
        where = (" (model.py line %d)" % el[-1]["line"]) if el else ""
        first = (payload.get("error") or "model.py failed").strip().splitlines()
        out.append((first[-1] if first else "model.py failed")[:300] + where)
    out.extend(payload.get("problems") or [])
    return out


def _source_context(code, line, around=2):
    """The failing line of model.py with `around` lines either side."""
    lines = code.splitlines()
    lo, hi = max(1, line - around), min(len(lines), line + around)
    return "\n".join("%s%4d | %s" % (">" if n == line else " ", n, lines[n - 1])
                     for n in range(lo, hi + 1))


# ------------------------------------------------------------------ timeout
class ScriptTimeout(BaseException):
    """BaseException, not Exception: a model.py that wraps its loop in
    `try: ... except Exception: pass` must not be able to swallow the stop."""


_WATCHDOG = [None]
_CPU_SOFT = [None]      # the soft RLIMIT_CPU before _arm_timeout lowered it


def _arm_timeout(seconds, res=None):
    """Three layers, each catching what the one before cannot:
      1. SIGALRM raises ScriptTimeout in model.py (gives a line number);
      2. a wall-clock watchdog thread emits a timed-out result and exits
         `seconds + 10` later, for a script that swallows even that (e.g.
         `except BaseException`) or blocks in a sleep - no CPU is used there,
         so the CPU limit would never fire;
      3. RLIMIT_CPU kills the process inside a long OCCT call, where neither
         a signal handler nor another Python thread gets to run.
    The CPU limit counts from the CPU already used, so a second run (the
    headless re-run) gets the full budget again."""
    def on_alarm(signum, frame):
        raise ScriptTimeout("model.py ran longer than %g s and was stopped" % seconds)
    try:
        signal.signal(signal.SIGALRM, on_alarm)
        signal.setitimer(signal.ITIMER_REAL, seconds)
    except (ValueError, AttributeError, OSError):
        pass
    try:
        import threading

        def bite():
            payload = dict(res or {})
            payload.update(ok=False, timed_out=True, error=(
                "model.py ran longer than %g s, ignored the stop and was "
                "killed (an endless loop that catches every exception?)" % seconds))
            _emit(payload, 1)
        t = threading.Timer(seconds + 10.0, bite)
        t.daemon = True
        t.start()
        _WATCHDOG[0] = t
    except Exception:                                   # noqa: BLE001
        pass
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_SELF)
        used = ru.ru_utime + ru.ru_stime
        soft, hard = resource.getrlimit(resource.RLIMIT_CPU)
        want = int(used + seconds) + 15
        if hard == resource.RLIM_INFINITY or hard > want:
            if _CPU_SOFT[0] is None:
                _CPU_SOFT[0] = soft
            resource.setrlimit(resource.RLIMIT_CPU, (want, hard))
    except Exception:                                   # noqa: BLE001
        pass


def _disarm_timeout():
    try:
        signal.setitimer(signal.ITIMER_REAL, 0)
    except (ValueError, AttributeError, OSError):
        pass
    if _WATCHDOG[0] is not None:
        _WATCHDOG[0].cancel()
        _WATCHDOG[0] = None
    # The CPU limit guards model.py only. Left in place it also killed the
    # checker's own work after it (SIGXCPU, exit 152, NO output - MEASURED
    # on an Atech case whose walls block the modules' slide paths); the
    # wrapper's `timeout` and Studio's backstop still bound the whole run.
    if _CPU_SOFT[0] is not None:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (
                _CPU_SOFT[0], resource.getrlimit(resource.RLIMIT_CPU)[1]))
        except Exception:                               # noqa: BLE001
            pass
        _CPU_SOFT[0] = None


# ------------------------------------------------------------------ running
def _error_lines(tb_text, script_path, code):
    lines = code.splitlines()
    out = []
    pat = r'File "%s", line (\d+)' % re.escape(script_path)
    for m in re.finditer(pat, tb_text):
        n = int(m.group(1))
        src = lines[n - 1].strip() if 1 <= n <= len(lines) else ""
        out.append({"line": n, "code": src})
    return out


def _gui_failure(tb_text, script_path, code):
    el = _error_lines(tb_text, script_path, code)
    if el and any(t in el[-1]["code"] for t in _GUI_TOKENS):
        return True
    return "ActiveDocument" in tb_text and "Gui" in tb_text


def _headless_patch(code):
    """Wrap each simple statement that touches the GUI in try/except: pass.
    (Same idea as tests/eval/fc_build.py; written again here on purpose -
    this file ships to the agent's workspace and must stand alone.)"""
    import ast
    tree = ast.parse(code)
    lines = code.splitlines()

    def touches(node):
        seg = "\n".join(lines[node.lineno - 1:getattr(node, "end_lineno", node.lineno)])
        return any(t in seg for t in _GUI_TOKENS)

    simple = (ast.Expr, ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Import,
              ast.ImportFrom)

    class T(ast.NodeTransformer):
        def generic_visit(self, node):
            super().generic_visit(node)
            for field in ("body", "orelse", "finalbody"):
                seq = getattr(node, field, None)
                if not isinstance(seq, list):
                    continue
                new = []
                for st in seq:
                    if isinstance(st, simple) and touches(st):
                        h = ast.ExceptHandler(type=ast.Name("Exception", ast.Load()),
                                              name=None, body=[ast.Pass()])
                        st = ast.copy_location(
                            ast.Try(body=[st], handlers=[h], orelse=[], finalbody=[]), st)
                    new.append(st)
                setattr(node, field, new)
            return node

    tree = T().visit(tree)
    import atech_geom
    tree = atech_geom._ViewRewrite().visit(tree)
    ast.fix_missing_locations(tree)
    return tree        # compiled directly: line numbers stay the agent's


def _load_context(App, doc, path):
    """Seed the fresh document with the user's objects (Studio's sandbox
    passes them). Returns {Name: fingerprint} of what was loaded."""
    import Part
    with open(path, encoding="utf-8") as fh:
        items = json.load(fh)
    seeded = {}
    atech = [it for it in items if it.get("atech")]
    tagged = any("role" in it for it in items if not it.get("atech"))
    del _USER_SEEDS[:]
    for it in items:
        if it.get("atech"):
            continue
        shape = Part.Shape()
        shape.read(it["brep"])
        o = doc.addObject("Part::Feature", it.get("name") or "Context")
        o.Shape = shape
        if it.get("label"):
            o.Label = it["label"]
        if (it.get("role") == "user") if tagged else not os.environ.get("ATECH_CHECK_OUT"):
            _USER_SEEDS.append(o.Name)
    if atech:
        _seed_atech(App, doc, atech)
    doc.recompute()
    for o in doc.Objects:
        seeded[o.Name] = _seed_fp(o)
    return seeded


_USER_SEEDS = []    # Names of the seeded objects that are the USER's solids (R128)


def _placement(App, values):
    x, y, z, q0, q1, q2, q3 = [float(v) for v in values]
    return App.Placement(App.Vector(x, y, z), App.Rotation(q0, q1, q2, q3))


def placement_list(pl):
    return [round(float(v), 9) for v in tuple(pl.Base) + tuple(pl.Rotation.Q)]


def _seed_atech(App, doc, items):
    """The Atech board and the user's seated modules, re-created with the
    library itself (meshes have no BREP to pass) - PRD R92."""
    import atech_ports as ap
    for it in items:
        if it["atech"] == "board":
            b = ap.board_object(doc)
            if it.get("label"):
                b.Label = it["label"]
            if it.get("placement"):
                b.Placement = _placement(App, it["placement"])
    for it in items:
        if it["atech"] == "module":
            ports = [int(p) for p in it["ports"]]
            ap.seat(doc, str(it["module"]), ports[0] if len(ports) == 1 else tuple(ports),
                    label=it.get("label") or None)


def _seed_fp(o):
    """What 'unchanged' means for a context object: the shape's fingerprint;
    for a Mesh feature (Atech part) its module, ports and placement."""
    import atech_geom
    if getattr(o, "AtechRole", None) or not hasattr(o, "Shape"):
        return ("mesh", getattr(o, "AtechModule", None),
                tuple(getattr(o, "AtechPorts", ()) or ()), tuple(placement_list(o.Placement)))
    return atech_geom.fingerprint(o.Shape)


def _run(App, code_or_tree, script_path, timeout, res=None, context=None):
    """Exec in a fresh document. Returns (doc, error or None, stdout, env,
    {Name: fingerprint} of the seeded context objects, recorded view props)."""
    import io
    import contextlib
    import atech_geom
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    doc = App.newDocument("Check")
    App.setActiveDocument(doc.Name)
    seeded = _load_context(App, doc, context) if context else {}
    view = {}
    env = {"FreeCAD": App, "App": App, "doc": doc, "__name__": "__agent__",
           atech_geom.VIEW_FN: atech_geom.view_recorder(view)}
    buf = io.StringIO()
    err = None
    _arm_timeout(timeout, res)
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code_or_tree, script_path, "exec"), env)   # noqa: S102
            doc.recompute()
    except BaseException:                               # noqa: BLE001
        err = traceback.format_exc()
    finally:
        _disarm_timeout()
    return doc, err, buf.getvalue(), env, seeded, view


def _results(created):
    """END results: created objects no other created object consumes;
    sketches and 2D construction are not parts."""
    names = {o.Name for o in created}
    out = []
    for o in created:
        if any(u.Name in names for u in o.InList):
            continue
        if o.TypeId.startswith("Sketcher::") or o.isDerivedFrom("Part::Part2DObject"):
            continue
        sh = getattr(o, "Shape", None)
        if sh is None or sh.isNull():
            continue
        out.append(o)
    return out


def _tight(shape):
    try:
        return shape.optimalBoundingBox(True, False)
    except Exception:                                   # noqa: BLE001
        return shape.BoundBox


def _facts(o):
    sh = o.Shape
    f = {"name": o.Name, "label": o.Label}
    try:
        bb = _tight(sh)
        f.update(valid=bool(sh.isValid()), solids=len(sh.Solids),
                 volume_mm3=round(sh.Volume, 2), faces=len(sh.Faces),
                 bbox_min=[round(bb.XMin, 3), round(bb.YMin, 3), round(bb.ZMin, 3)],
                 bbox_max=[round(bb.XMax, 3), round(bb.YMax, 3), round(bb.ZMax, 3)],
                 size=[round(bb.XLength, 3), round(bb.YLength, 3), round(bb.ZLength, 3)])
    except Exception as exc:                            # noqa: BLE001
        f.update(valid=False, error="measure failed: %s" % exc)
    return f


# ------------------------------------------------------------------ render
RENDER_LINEAR = 0.004       # mesh deviation, x the body's diagonal
RENDER_ANGULAR = 0.35       # rad; Shape.tessellate() uses a far finer angle


def _triangles(shape):
    """(points Nx3, faces Mx3) of a shape for the picture. MeshPart with an
    angular deflection: MEASURED S39 on the rpi4_case, 13 940 triangles
    where Shape.tessellate() gave 120 104 - the same picture at a ninth of
    the work. tessellate() is the fallback."""
    import numpy as np
    diag = max(shape.BoundBox.DiagonalLength, 1.0)
    try:
        import MeshPart
        m = MeshPart.meshFromShape(Shape=shape, LinearDeflection=diag * RENDER_LINEAR,
                                   AngularDeflection=RENDER_ANGULAR, Relative=False)
        pts, faces = m.Topology
    except Exception:                                   # noqa: BLE001
        pts, faces = shape.tessellate(diag * RENDER_LINEAR)
    if not pts or not faces:
        return None, None
    return (np.array([[p.x, p.y, p.z] for p in pts], dtype=float),
            np.array([list(f) for f in faces], dtype=int))


def render(shapes, path, meshes=()):
    """Two flat-shaded isometric views of `shapes` (and of `meshes`: the
    seated Atech board and modules, in grey) to a PNG. Returns None or the
    reason nothing was drawn.

    Projected and depth-sorted here, drawn as ONE flat 2D collection per
    view: MEASURED S39 (rpi4_case) 16.8 s with matplotlib's 3D axes, 0.35 s
    this way. Painter's order (triangle centres, far to near) - a view to
    judge shape and placement by, not a measuring instrument."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    import numpy as np

    palette = [(0.35, 0.64, 1.0), (0.88, 0.69, 0.32), (0.37, 0.73, 0.55),
               (0.60, 0.42, 1.0), (0.85, 0.40, 0.40)]
    tris, cols = [], []
    for i, sh in enumerate(shapes):
        P, F = _triangles(sh)
        if P is None:
            continue
        tris.append(P[F])
        cols.append(np.tile(palette[i % len(palette)], (len(F), 1)))
    for mesh in meshes:
        pts, faces = mesh.Topology
        if not pts or not faces:
            continue
        P = np.array([[p.x, p.y, p.z] for p in pts], dtype=float)
        F = np.array([list(f) for f in faces], dtype=int)
        tris.append(P[F])
        cols.append(np.tile((0.62, 0.62, 0.62), (len(F), 1)))
    if not tris:
        return "nothing to render"
    T = np.concatenate(tris)
    C = np.concatenate(cols)
    allP = T.reshape(-1, 3)
    T, C = _subdivide(T, C, np.linalg.norm(allP.max(0) - allP.min(0)) / 30.0)
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    ln = np.linalg.norm(n, axis=1)
    ln[ln == 0] = 1
    n = n / ln[:, None]
    mn, mx = allP.min(0), allP.max(0)
    fig = plt.figure(figsize=(10, 5), dpi=90)
    for k, (elev, azim) in enumerate(((28, -60), (28, 120))):
        ax = fig.add_subplot(1, 2, k + 1)
        e, a = math.radians(elev), math.radians(azim)
        view = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a),
                         math.sin(e)])                  # toward the viewer
        right = np.array([-math.sin(a), math.cos(a), 0.0])
        up = np.cross(view, right)
        light = view + np.array([0.3, -0.2, 0.6])
        light = light / np.linalg.norm(light)
        shade = 0.35 + 0.65 * np.abs(n @ light)
        order = np.argsort((T @ view).mean(axis=1))    # far first
        xy = np.stack([T @ right, T @ up], axis=-1)[order]
        fc = np.clip(C * shade[:, None], 0, 1)[order]
        ax.add_collection(PolyCollection(xy, facecolors=fc, edgecolors=fc,
                                         linewidths=0.2))
        ax.autoscale_view()
        ax.set_aspect("equal")
        ax.axis("off")
        _triad(ax, right, up)
        ax.set_title("from %s" % ("front-left" if k == 0 else "back-right"), fontsize=8)
    fig.suptitle("size %.1f x %.1f x %.1f mm (X x Y x Z)"
                 % tuple(mx - mn), fontsize=9)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return None


def _subdivide(T, C, limit, rounds=12):
    """Halve triangles across their longest edge until no edge is longer
    than `limit`: the painter's order sorts by triangle centre, which puts
    a large flat face (a case wall is two triangles) behind what it hides.
    Bisection, not 4-way splits: the long thin slivers of a vented wall
    need one cut each, not a quadrupling (MEASURED S39: rpi4_case)."""
    import numpy as np
    for _ in range(rounds):
        e = np.stack([np.linalg.norm(T[:, 1] - T[:, 0], axis=1),
                      np.linalg.norm(T[:, 2] - T[:, 1], axis=1),
                      np.linalg.norm(T[:, 0] - T[:, 2], axis=1)], axis=1)
        big = e.max(axis=1) > limit
        if not big.any() or len(T) > 300000:
            break
        B, k = T[big], e[big].argmax(axis=1)
        # rotate each triangle so its longest edge is v0 -> v1
        idx = np.stack([k, (k + 1) % 3, (k + 2) % 3], axis=1)
        R = np.take_along_axis(B, idx[:, :, None], axis=1)
        m = (R[:, 0] + R[:, 1]) / 2
        T = np.concatenate([T[~big], np.stack([R[:, 0], m, R[:, 2]], axis=1),
                            np.stack([m, R[:, 1], R[:, 2]], axis=1)])
        C = np.concatenate([C[~big], C[big], C[big]])
    return T, C


def _triad(ax, right, up):
    """X/Y/Z arrows in the view's lower-left corner (axes fraction)."""
    ox, oy, L = 0.06, 0.08, 0.07
    for vec, name, col in (((1, 0, 0), "X", "#c33"), ((0, 1, 0), "Y", "#3a3"),
                           ((0, 0, 1), "Z", "#36c")):
        dx = float(sum(v * r for v, r in zip(vec, right)))
        dy = float(sum(v * u for v, u in zip(vec, up)))
        ax.annotate("", xy=(ox + L * dx, oy + L * dy), xytext=(ox, oy),
                    xycoords="axes fraction",
                    arrowprops=dict(arrowstyle="->", color=col, lw=1.2))
        ax.text(ox + 1.35 * L * dx, oy + 1.35 * L * dy, name, color=col,
                fontsize=7, transform=ax.transAxes, ha="center", va="center")


# -------------------------------------------------------------------- main
def main():
    t0 = time.time()
    sys.dont_write_bytecode = True     # no __pycache__ in the workspace or kit
    for p in [HERE] + [p for p in os.environ.get("ATECH_CHECK_PATH", "").split(os.pathsep) if p]:
        if p not in sys.path:
            sys.path.insert(0, p)
    script = os.environ.get("ATECH_CHECK_SCRIPT") or os.path.join(os.getcwd(), "model.py")
    if not os.path.isfile(script) and not os.environ.get("ATECH_CHECK_SCRIPT"):
        beside = os.path.join(HERE, "model.py")
        if os.path.isfile(beside):
            script = beside
    script = os.path.abspath(script)
    ws = os.path.dirname(script)
    if ws not in sys.path:
        sys.path.insert(0, ws)
    png = os.environ.get("ATECH_CHECK_PNG")
    png = os.path.join(ws, "check.png") if png is None else png
    timeout = float(os.environ.get("ATECH_CHECK_TIMEOUT") or 60)
    out_dir = os.environ.get("ATECH_CHECK_OUT")
    res = {"ok": False, "script": script, "error": None, "error_lines": [],
           "objects": [], "warnings": [], "problems": [], "notes": [], "png": None,
           "headless_patched": False, "stdout": ""}
    try:
        # utf-8-sig: an editor's byte-order mark is not a syntax error
        # (MEASURED dogfood D45: a BOM at line 1 cost a check round).
        with open(script, encoding="utf-8-sig") as fh:
            code = fh.read()
    except OSError as exc:
        res["error"] = "cannot read %s: %s" % (script, exc)
        _emit(res, 1)

    import FreeCAD as App
    try:
        compile(code, script, "exec")
    except SyntaxError:
        res["error"] = traceback.format_exc(limit=0)
        res["error_lines"] = _error_lines(res["error"], script, code)
        _explain_error(res, code)
        res["seconds"] = round(time.time() - t0, 2)
        _emit(res, 1)

    import atech_geom
    context = os.environ.get("ATECH_CHECK_CONTEXT") or None
    t_run = time.time()
    counts = {}
    tree = atech_geom.record_view(code, counts)
    # headless_patched: some GUI line was rewritten to run headless (view
    # properties recorded, or - after a GUI failure - skipped on a re-run).
    res["view_recorded"] = counts.get("rewritten", 0)
    res["headless_patched"] = bool(res["view_recorded"])
    # S37/R135: the turn's intent record is taken BEFORE model.py runs, so
    # model.py can neither edit intent.json first nor delete the record
    intent_before = atech_geom.intent_record(ws, record=True)
    turn_before = atech_geom._read_regular(os.path.join(ws, atech_geom.TURN))
    doc, err, out, env, seeded, view = _run(App, tree, script, timeout, res, context)
    if err and _gui_failure(err, script, code):
        res["headless_first_error"] = err[-1500:]
        doc, err, out, env, seeded, view = _run(
            App, _headless_patch(code), script, timeout, res, context)
        res["headless_patched"] = True
        res["headless_rerun"] = True
    res["run_seconds"] = round(time.time() - t_run, 2)
    # R135: whatever model.py did - even when it then raised - the record
    # it deleted or rewrote is put back now, before anything can emit
    touched = atech_geom.intent_guard(ws, intent_before)
    if touched:
        res["problems"].append(touched)
        res["intent_problems"] = [touched]
    turned = _turn_guard(ws, turn_before)
    if turned:
        res["problems"].append(turned)
        res["intent_problems"] = res.get("intent_problems", []) + [turned]
    res["stdout"] = out[-4000:]
    if err:
        res["error"] = err[-6000:]
        res["error_lines"] = _error_lines(err, script, code)
        res["timed_out"] = "ScriptTimeout" in err
        _explain_error(res, code)
        res["seconds"] = round(time.time() - t0, 2)
        _emit(res, 1)

    # The user's objects (context) are Studio's to change, not model.py's:
    # an edit made here could never be carried over (R16's rule, sandboxed).
    if seeded:
        gone = sorted(n for n in seeded if doc.getObject(n) is None)
        # The board is a shared fixture model.py may orient (as in Studio's
        # own document); every other context object must stay as it was.
        changed = sorted(n for n in seeded if doc.getObject(n) is not None
                         and getattr(doc.getObject(n), "AtechRole", None) != "board"
                         and _seed_fp(doc.getObject(n)) != seeded[n])
        # ...unless the user's own modules sit on it: seat() places a module
        # once from the board's placement, so turning the board would leave
        # their modules hanging where the board was (in Studio too).
        if not gone and not changed:
            users_mods = [n for n in seeded if getattr(
                doc.getObject(n), "AtechRole", None) == "module"]
            moved = [n for n in seeded if getattr(
                doc.getObject(n), "AtechRole", None) == "board"
                and _seed_fp(doc.getObject(n)) != seeded[n]]
            if users_mods and moved:
                changed = [n + " (the board: the user's modules are seated on "
                           "it, so model.py must not move it)" for n in moved]
        if gone or changed:
            res["error"] = ("model.py %s objects it does not own (the user's): %s. "
                            "Build new objects instead; never delete or edit the "
                            "user's." % ("deleted" if gone else "changed",
                                         ", ".join(gone or changed)))
            res["foreign_objects"] = {"deleted": gone, "changed": changed}
            res["seconds"] = round(time.time() - t0, 2)
            _emit(res, 1)

    res["intended_overlaps"] = atech_geom.sanitize_intended(
        env.get("INTENDED_OVERLAPS"))
    created = [o for o in doc.Objects if o.Name not in seeded]
    ends = _results(created)
    atech = _atech_report(doc, seeded)
    if atech:
        res["atech"] = atech
    if not ends and not (atech and any(not m["seeded"] for m in atech["modules"])):
        res["error"] = ("model.py ran without error but added nothing to the "
                        "document (it added no shape). Add each body with "
                        "doc.addObject('Part::Feature', 'Name').Shape = shape")
        res["seconds"] = round(time.time() - t0, 2)
        _emit(res, 1)
    problems = res.setdefault("problems", [])
    for o in ends:
        f = _facts(o)
        if o.Name in view:
            f["view"] = view[o.Name]
        if f.get("valid") is False:
            res["warnings"].append("%s: shape is INVALID" % o.Label)
            problems.append("%s: shape is INVALID" % o.Label)
        if f.get("solids") == 0:
            res["warnings"].append("%s: no solid (a surface or wire only)" % o.Label)
            problems.append("%s: no solid" % o.Label)
        elif (f.get("solids") or 0) > 1:
            res["warnings"].append(
                "%s: %d separate solids in one object - fine for a pair of "
                "parts, a bug if it was meant to be one fused body"
                % (o.Label, f["solids"]))
            frag = atech_geom.fragments(o.Shape)
            if frag:
                f["fragment"] = frag
                problems.append(
                    "%s: a stray %s mm3 solid beside the %s mm3 body (a fuse that "
                    "did not join?)" % (o.Label, frag["smallest_mm3"], frag["largest_mm3"]))
        if out_dir:
            try:
                os.makedirs(out_dir, exist_ok=True)
                bp = os.path.join(out_dir, "%s.brep" % o.Name)
                o.Shape.exportBrep(bp)
                f["brep"] = bp
            except Exception as exc:                    # noqa: BLE001
                f["brep_error"] = str(exc)
        res["objects"].append(f)

    items = [{"name": o.Name, "label": o.Label, "shape": o.Shape,
              "role": getattr(o, "AtechRole", None) or None} for o in ends]
    items += [{"name": o.Name, "label": o.Label, "mesh": o.Mesh,
               "role": getattr(o, "AtechRole", None),
               "module": str(getattr(o, "AtechModule", "") or "") or None,
               "axes": _axes(App, o)}
              for o in doc.Objects if o.TypeId == "Mesh::Feature"
              and getattr(o, "AtechRole", None)]
    t_g = time.time()
    hits, note = atech_geom.overlaps(items, res["intended_overlaps"])
    if note:
        res["warnings"].append(note)
    users = _user_items(doc, seeded)
    uhits, unote = _user_overlaps(users, ends, doc, seeded, res["intended_overlaps"])
    if unote:
        res["warnings"].append(unote)
    res["overlaps"] = hits + uhits
    for h in hits:
        problems.append("OVERLAP " + atech_geom.overlap_text(h))
    for h in uhits:
        problems.append("OVERLAP " + atech_geom.overlap_text(h) + (
            " (%s is the USER's object, already in the document: move your part "
            "clear of it - a part that seats on or around it needs a clearance "
            "(0.1 mm is enough), not an overlap%s)" % (
                h["user"], ". INTENDED_OVERLAPS does not excuse an overlap with "
                "the user's object, so listing the pair there changes nothing"
                if h.get("declared") else "")))
    ulabels = {u["label"] for u in users}
    res["floating"] = [f for f in atech_geom.floating(items + users)
                       if f["label"] not in ulabels]
    _intent(res, ws, ends)
    _layout(res, doc, ends, items)
    _desk(res, ends, items, ws)
    _wall_holes(res, ends, ws)
    _face_open(res, ends, items, ws)
    _containers(res, ends, items, ws)
    _lids(res, ends, ws)
    _holds(res, ends, ws)
    _motion(res, ends, ws)
    _mates(res, ends, ws)
    _joints(res, ends, ws)
    _channels(res, ends, ws)
    res["geometry_seconds"] = round(time.time() - t_g, 3)
    _walls(res, ends, ws)
    _atech_port_check(doc, res)
    try:
        import Part
        if ends:
            bb = _tight(Part.makeCompound([o.Shape for o in ends]))
            res["whole_size"] = [round(bb.XLength, 3), round(bb.YLength, 3),
                                 round(bb.ZLength, 3)]
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("whole bbox: %s" % exc)
    res["ok"] = True
    if png and res.get("problems"):
        # S39: a failed check is followed by an edit, never by a look at the
        # picture (eval round 3), and rendering cost up to 14 s. No picture
        # then - and no stale one from an earlier run to be mistaken for it.
        res["render_skipped"] = "the check failed: fix the problems first"
        try:
            if os.path.isfile(png) and not os.path.islink(png):
                os.unlink(png)
        except OSError:
            pass
    elif png:
        t_r = time.time()
        try:
            why = render([o.Shape for o in ends], png,
                         [it["mesh"] for it in items if it.get("mesh") is not None])
            res["png"] = None if why else os.path.abspath(png)
            if why:
                res["warnings"].append("render: " + why)
        except Exception as exc:                        # noqa: BLE001
            res["warnings"].append("render failed: %s" % exc)
        res["render_seconds"] = round(time.time() - t_r, 2)
    res["seconds"] = round(time.time() - t0, 2)
    _say_summary(res)
    _emit(res, 0)


def _intent(res, ws, ends):
    """intent.json vs this build: the SAME comparison Studio makes after the
    build (atech_geom.intent_problems), so ./check and Studio cannot
    disagree about it (PRD S30). The user's message (Studio's turn file)
    goes with it: an overall size it gives is measured over all parts
    together, whatever intent.json splits (R168). Round channels counted
    as the intended holes are a NOTE (R170), and so is a miss on a target
    the message never states (S54, R183)."""
    import atech_geom
    intent, bad = atech_geom.read_intent(ws)
    ends = [o for o in ends if not getattr(o, "AtechRole", None)]
    notes = []
    bad = bad + atech_geom.intent_problems(
        intent, [o.Shape for o in ends], request=_turn_request(ws),
        labels=[o.Label for o in ends], notes=notes)
    res.setdefault("notes", []).extend(notes)
    moved = atech_geom.intent_changed(ws, record=True)       # S37
    if moved:
        bad = [moved] + bad
    if bad:
        res["intent_problems"] = res.get("intent_problems", []) + bad
        res.setdefault("problems", []).extend(bad)
        res["warnings"].append(atech_geom.INTENT_RULE)


def _layout(res, doc, ends, items):
    """S36: with an Atech board in the document, the agent's parts against
    the board and the seated modules (atech_geom.atech_layout)."""
    import atech_geom
    board = next(({"label": it["label"], "mesh": it["mesh"]} for it in items
                  if it.get("role") == "board" and it.get("mesh") is not None), None)
    if board is None:
        return
    mods = [{"label": it["label"], "name": it["name"], "mesh": it["mesh"]}
            for it in items if it.get("role") == "module" and it.get("mesh") is not None]
    parts = [{"label": o.Label, "shape": o.Shape} for o in ends
             if not getattr(o, "AtechRole", None)]
    intent, _bad = atech_geom.read_intent(os.path.dirname(res["script"]))
    try:
        bad, facts = atech_geom.atech_layout(parts, board, mods, intent,
                                             res.get("intended_overlaps"))
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("Atech layout check could not run: %s" % exc)
        return
    res["atech_layout"] = facts
    if bad:
        res["layout_problems"] = bad
        res.setdefault("problems", []).extend(bad)


def _desk(res, ends, items, ws):
    """R177: a request that stands the product on a desk / table / floor -
    no part the agent built may reach below z = 0 (atech_geom.below_desk).
    With an Atech board the layout check already judges the desk (R126)."""
    import atech_geom
    if any(it.get("role") == "board" for it in items):
        return
    parts = [{"label": o.Label, "shape": o.Shape} for o in ends
             if not getattr(o, "AtechRole", None)]
    try:
        bad, facts = atech_geom.below_desk(parts, _turn_request(ws))
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("desk check could not run: %s" % exc)
        return
    if facts:
        res["desk"] = facts
    if bad:
        res["desk_problems"] = bad
        res.setdefault("problems", []).extend(bad)


def _wall_holes(res, ends, ws):
    """R181 (D69): a hole that goes through more than one wall (a hollow
    case's front AND back wall) - a WARNING naming each wall, never a
    failure (a pin through a clevis is meant to)."""
    import atech_geom
    request = _turn_request(ws)
    rows = []
    for o in ends:
        if getattr(o, "AtechRole", None):
            continue
        try:
            found = atech_geom.wall_crossings(o.Shape, request)
        except Exception as exc:                        # noqa: BLE001
            res["warnings"].append("wall-crossing probe could not run on %s: %s"
                                   % (o.Label, exc))
            continue
        for b in found:
            b = dict(b, label=o.Label)
            rows.append(b)
            res["warnings"].append(atech_geom.wall_crossing_text(o.Label, b))
    if rows:
        res["wall_crossings"] = rows


def _turn_guard(ws, before):
    """R151 + R135: model.py must not delete, plant or rewrite Studio's turn
    file (.atech_turn.json) - it decides whether intent.json may change.
    Put back as it was before the run; a problem when it moved."""
    import atech_geom
    path = os.path.join(ws, atech_geom.TURN)
    now = atech_geom._read_regular(path)
    if now == before and (before is not None or not os.path.lexists(path)):
        return None
    try:
        if os.path.lexists(path):
            if os.path.isdir(path) and not os.path.islink(path):
                import shutil
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.unlink(path)
        if before is not None:
            atech_geom._write_record(path, before)
    except OSError:
        pass
    return ("%s: model.py %s %s, Atelier's turn file (put back). model.py builds "
            "the part; it must not touch intent.json or its records"
            % (atech_geom.INTENT_CHANGED,
               "planted" if before is None else "deleted" if now is None
               else "rewrote", atech_geom.TURN))


USER_MAX = 30       # user objects compared with the build, at most


def _user_items(doc, seeded):
    """R128: the seeded context objects that are the user's solids, as
    overlap items. A body exported twice (a PartDesign Body and its tip
    feature have one shape) is compared once."""
    import atech_geom
    out, seen = [], set()
    for name in _USER_SEEDS:
        o = doc.getObject(name)
        sh = getattr(o, "Shape", None) if o is not None else None
        try:
            if sh is None or sh.isNull() or not sh.Solids:
                continue
        except Exception:                               # noqa: BLE001
            continue
        fp = seeded.get(name)
        if fp is not None and fp in seen:
            continue
        seen.add(fp)
        out.append({"name": o.Name, "label": o.Label, "shape": sh, "role": None})
    return out


def _user_overlaps(users, ends, doc, seeded, intended):
    """R128: every body model.py built (and every module it seated) against
    each of the user's solids - pair by pair, never user against user (the
    user's own arrangement is not the agent's to judge). The same rule as
    Studio's build.user_overlaps. Returns (hits, note); a hit carries
    "user": the user object's label, and "declared": True when
    INTENDED_OVERLAPS names the pair - which never excuses it (R156)."""
    import atech_geom
    if not users:
        return [], None
    note = None
    if len(users) > USER_MAX:
        note = "overlap check against your objects limited to %d of %d" % (
            USER_MAX, len(users))
        users = users[:USER_MAX]
    mine = [{"name": o.Name, "label": o.Label, "shape": o.Shape, "role": None}
            for o in ends if not getattr(o, "AtechRole", None)]
    mine += [{"name": o.Name, "label": o.Label, "mesh": o.Mesh, "role": None}
             for o in doc.Objects if o.TypeId == "Mesh::Feature"
             and getattr(o, "AtechRole", None) == "module" and o.Name not in seeded]
    hits = []
    for u in users:
        for a in mine:
            # R156: never silenced by INTENDED_OVERLAPS - the agent declared
            # Desk_Stand/Clock_Enclosure and passed ./check on a 36,970 mm3
            # overlap with the user's clock (eval r6). Studio's own gate
            # (build.user_overlaps) refuses such a declaration too.
            found, _n = atech_geom.overlaps([a, u], ())
            for h in found:
                h["user"] = u["label"]
                if atech_geom.declared(a, u, intended or ()):
                    h["declared"] = True
                hits.append(h)
    return hits, note


def _turn_request(ws):
    """The user's message of this turn (Studio's turn file), or None."""
    import atech_geom
    turn = atech_geom.read_turn(ws)
    return None if turn is None else turn["request"]


def _face_open(res, ends, items, ws):
    """R152: per seated module, how much of its working face can see out
    of the product (atech_geom.face_open)."""
    import atech_geom
    board = next(({"label": it["label"], "mesh": it["mesh"]} for it in items
                  if it.get("role") == "board" and it.get("mesh") is not None), None)
    mods = [it for it in items if it.get("role") == "module" and it.get("mesh") is not None]
    parts = [{"label": o.Label, "shape": o.Shape} for o in ends
             if not getattr(o, "AtechRole", None)]
    if board is None or not mods or not parts:
        return
    doc_mods = [{"label": it["label"], "name": it["name"], "mesh": it["mesh"],
                 "module": it.get("module"), "axes": it.get("axes")} for it in mods]
    t = time.time()
    try:
        rows = atech_geom.face_open(parts, board, doc_mods)
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("face-open probe could not run: %s" % exc)
        return
    res["face_open"] = rows
    res["face_open_seconds"] = round(time.time() - t, 3)
    skipped = sorted({u for r in rows for u in r.get("unmeasured") or ()})
    if skipped:
        res["warnings"].append(
            "face-open probe: %s left out (a face with too many holes to "
            "tessellate quickly) - rays pass through it as if it were not there, "
            "so an opening in it was not judged" % ", ".join(skipped))
    bad, warn = atech_geom.face_open_problems(rows, _turn_request(ws))
    if bad:
        res["face_open_problems"] = bad
    res.setdefault("problems", []).extend(bad)
    res["warnings"].extend(warn)


def _containers(res, ends, items, ws):
    """R169: a part named as a container (pot, cup, planter...) must be open
    from above (atech_geom.containers)."""
    import atech_geom
    parts = [{"label": o.Label, "shape": o.Shape} for o in ends
             if not getattr(o, "AtechRole", None)]
    if not parts:
        return
    intent, _bad = atech_geom.read_intent(ws)
    atech = any(it.get("role") == "board" for it in items)
    t = time.time()
    try:
        rows, bad, warn = atech_geom.containers(parts, intent, _turn_request(ws), atech)
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("container probe could not run: %s" % exc)
        return
    if not rows:
        return
    res["containers"] = rows
    res["containers_seconds"] = round(time.time() - t, 3)
    res.setdefault("problems", []).extend(bad)
    res["warnings"].extend(warn)


def _axes(App, o):
    """A seated module's own X, Y, Z in world (its Placement), for the
    socket-mouth probe (R164)."""
    try:
        r = o.Placement.Rotation
        return [[round(c, 6) for c in r.multVec(App.Vector(*e))]
                for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    except Exception:                                   # noqa: BLE001
        return None


def _lids(res, ends, ws):
    """S58: a part named lid / cover / cap that is a solid plug - a NOTE
    (atech_geom.solid_lids)."""
    import atech_geom
    parts = [{"label": o.Label, "shape": o.Shape} for o in ends
             if not getattr(o, "AtechRole", None)]
    intent, _bad = atech_geom.read_intent(ws)
    try:
        rows, notes = atech_geom.solid_lids(parts, (intent or {}).get("wall_mm"))
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("lid probe could not run: %s" % exc)
        return
    if rows:
        res["lids"] = rows
    res.setdefault("notes", []).extend(notes)


def _holds(res, ends, ws):
    """R192 (D73): the held object intent.json "holds" declares must be able
    to reach its seat (atech_geom.hold_probe) - a PROBLEM only when no side
    lets it in and the measured mouth is narrower than the object."""
    import atech_geom
    intent, _bad = atech_geom.read_intent(ws)
    if not isinstance(intent, dict) or intent.get("holds") is None:
        return
    parts = [{"label": o.Label, "shape": o.Shape} for o in ends
             if not getattr(o, "AtechRole", None)]
    try:
        row, bad, warn, notes = atech_geom.hold_probe(parts, intent)
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("way-in probe could not run: %s" % exc)
        return
    if row is not None:
        res["holds"] = row
    res.setdefault("problems", []).extend(bad)
    res["warnings"].extend(warn)
    res.setdefault("notes", []).extend(notes)


def _motion(res, ends, ws):
    """R202 (D77): each part intent.json "motion" declares is swept about
    its axis through its range (atech_geom.motion_probe) - a PROBLEM at
    the first angle it hits another part. "motion_problems" is what
    Studio's build takes as the verdict (build._child_motion)."""
    import atech_geom
    intent, _bad = atech_geom.read_intent(ws)
    if not isinstance(intent, dict) or intent.get(atech_geom.MOTION) is None:
        return
    parts = [{"name": o.Name, "label": o.Label, "shape": o.Shape} for o in ends
             if not getattr(o, "AtechRole", None)]
    try:
        row, bad, warn, notes = atech_geom.motion_probe(
            parts, intent, res.get("intended_overlaps") or ())
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("motion sweep could not run: %s" % exc)
        return
    if row is not None:
        res["motion"] = row
    if os.environ.get("ATECH_CHECK_OUT"):
        # Studio's own build: a declared part that was never built fails
        # the turn (as fitted_after, S50); in ./check it is a NOTE while
        # the draft is still adding it
        bad = bad + [n for n in notes if n.startswith("motion: no part labelled")]
        notes = [n for n in notes if not n.startswith("motion: no part labelled")]
    res["motion_problems"] = list(bad)
    res.setdefault("problems", []).extend(bad)
    res["warnings"].extend(warn)
    res.setdefault("notes", []).extend(notes)


def _mates(res, ends, ws):
    """R213 (D79): the reference object intent.json "mates" declares (a
    pegboard: thickness, hole grid, where its front face is) is built and
    every part tested against it (atech_geom.mates_probe) - a PROBLEM for
    any volume shared with it beyond the pegs in their holes, named with
    its volume, depth and place. "mates_problems" is the verdict list for
    Studio's build."""
    import atech_geom
    intent, _bad = atech_geom.read_intent(ws)
    if not isinstance(intent, dict) or intent.get(atech_geom.MATES) is None:
        return
    parts = [{"name": o.Name, "label": o.Label, "shape": o.Shape} for o in ends
             if not getattr(o, "AtechRole", None)]
    t = time.time()
    try:
        rows, bad, notes = atech_geom.mates_probe(parts, intent)
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("mates check could not run: %s" % exc)
        return
    res["mates"] = rows
    res["mates_seconds"] = round(time.time() - t, 3)
    res["mates_problems"] = list(bad)
    res.setdefault("problems", []).extend(bad)
    res.setdefault("notes", []).extend(notes)


def _joints(res, ends, ws):
    """R212 (D78): a part whose every contact with the other parts is a
    face touch - 0 mm apart, nothing shared, no lip / plug / hook reaching
    into the other - falls off (atech_geom.joint_probe): a PROBLEM naming
    the part and saying it only touches. "joint_problems" is the verdict
    list for Studio's build."""
    import atech_geom
    parts = [{"name": o.Name, "label": o.Label, "shape": o.Shape} for o in ends
             if not getattr(o, "AtechRole", None)]
    if len(parts) < 2:
        return
    t = time.time()
    try:
        rows, bad, notes = atech_geom.joint_probe(parts, _turn_request(ws))
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("joint-engagement probe could not run: %s" % exc)
        return
    if rows:
        res["joints"] = rows
    res["joints_seconds"] = round(time.time() - t, 3)
    res["joint_problems"] = list(bad)
    res.setdefault("problems", []).extend(bad)
    res.setdefault("notes", []).extend(notes)


def _channels(res, ends, ws):
    """S62: each round channel's wrap angle (atech_geom.channel_wraps, summed
    as the benchmark sums it). A CHANNEL line each; a WARNING for one under
    CHANNEL_HOLD_DEG when the request or a label names a clip, holder,
    cable... - a trough that wraps half way round holds nothing."""
    import atech_geom
    rows = []
    request = _turn_request(ws)
    labels = [o.Label for o in ends if not getattr(o, "AtechRole", None)]
    holding = atech_geom.holds_something(request, labels)
    for o in ends:
        if getattr(o, "AtechRole", None):
            continue
        try:
            found = atech_geom.channel_wraps(o.Shape)
        except Exception as exc:                        # noqa: BLE001
            res["warnings"].append("channel probe could not run on %s: %s"
                                   % (o.Label, exc))
            continue
        for c in found:
            rows.append(dict(c, label=o.Label))
            # a notch through a thin wall (a cable EXIT, span < d/2) is not
            # a channel meant to grip: its line is printed, never warned
            gripping = (c["span"][1] - c["span"][0]) >= 0.5 * c["d_mm"]
            if holding and gripping and c["wrap_deg"] < atech_geom.CHANNEL_HOLD_DEG:
                res["warnings"].append(
                    "%s - under %g deg, so a cable or rod pressed in is not held: "
                    "make the entry slot NARROWER than the %g mm channel (at most "
                    "0.8 x d) so it wraps >= %g deg" % (
                        atech_geom.channel_text(o.Label, c),
                        atech_geom.CHANNEL_HOLD_DEG, c["d_mm"],
                        atech_geom.CHANNEL_HOLD_DEG))
    if rows:
        res["channels"] = rows


def _walls(res, ends, ws=None):
    """R154: the thinnest wall the sampled probe measured; a WARNING below
    atech_geom.WALL_FLOOR_MM, never a failure (it is an estimate). R194:
    each part's side walls as measured (normal to the wall), next to
    intent.json "wall_mm" - a NOTE when they differ, so the reply quotes
    the measured number."""
    import atech_geom
    parts = [{"label": o.Label, "shape": o.Shape} for o in ends
             if not getattr(o, "AtechRole", None)]
    if not parts:
        return
    try:
        w = atech_geom.thin_walls(parts)
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("wall probe could not run: %s" % exc)
        return
    res["walls"] = w
    intent, _bad = atech_geom.read_intent(ws) if ws else (None, [])
    want = (intent or {}).get("wall_mm") if isinstance(intent, dict) else None
    try:
        want = None if want is None or isinstance(want, bool) else float(want)
    except (TypeError, ValueError):
        want = None
    if want is not None:
        w["wall_mm"] = want
        for p in w.get("parts") or []:
            sd = p.get("side")
            if sd and abs(sd["mm"] - want) > max(0.1, 0.05 * want):
                res.setdefault("notes", []).append(
                    "%s: its side walls measure %.2f mm (%.2f .. %.2f, normal to the "
                    "wall), not the %g mm intent.json wall_mm - a NOTE, not a failure: "
                    "in your reply give the measured thickness, not %g" % (
                        p["label"], sd["mm"], sd["lo"], sd["hi"], want, want))
    m = w.get("min")
    if m is not None and m["mm"] < atech_geom.WALL_FLOOR_MM:
        res["warnings"].append(
            "%s: a wall only %.2f mm thick near (%s) - below %.1f mm (2 x a 0.4 mm "
            "FDM nozzle), it prints weak or not at all; thicken it or move the "
            "cut that thins it" % (m["label"], m["mm"],
                                   ", ".join("%.1f" % v for v in m["at"]),
                                   atech_geom.WALL_FLOOR_MM))


def _atech_report(doc, seeded):
    """The Atech board and seated modules as data Studio can replay with the
    library in its own document (PRD R92): meshes have no BREP."""
    board = None
    mods = []
    for o in doc.Objects:
        role = getattr(o, "AtechRole", None)
        if role == "board" and board is None:
            board = {"label": o.Label, "name": o.Name, "seeded": o.Name in seeded,
                     "placement": placement_list(o.Placement)}
        elif role == "module":
            mods.append({"module": str(getattr(o, "AtechModule", "")),
                         "ports": [int(p) for p in (getattr(o, "AtechPorts", ()) or ())],
                         "label": o.Label, "name": o.Name,
                         "seeded": o.Name in seeded})
    if board is None and not mods:
        return None
    return {"board": board, "modules": mods}


def _explain_error(res, code):
    """The failing model.py line with context, for the agent (PRD S13)."""
    el = res.get("error_lines") or []
    if el:
        res["error_context"] = _source_context(code, el[-1]["line"])
        _say("ERROR model.py line %d: %s" % (el[-1]["line"], el[-1]["code"]))
        _say(res["error_context"])
    err = (res.get("error") or "").strip().splitlines()
    if err:
        _say("ERROR " + err[-1])


def _atech_port_check(doc, res):
    """When model.py seated Atech modules, run the library's own check once
    (it is slow, so it lives here and in Studio, not in model.py - PRD S22)."""
    ap = sys.modules.get("atech_ports")
    if ap is None:
        return
    mods = [o for o in doc.Objects if getattr(o, "AtechRole", None) == "module"]
    if not mods:
        return
    t = time.time()
    fitted = _fitted_after(doc, res)
    kw = {}
    if fitted:
        import inspect
        try:
            takes = "fitted_after" in inspect.signature(ap.check).parameters
        except (TypeError, ValueError):
            takes = False
        if takes:
            kw["fitted_after"] = fitted
        else:
            res["warnings"].append(
                "intent.json fitted_after is not known to this Atech library: "
                "the slide paths were checked with those parts in place")
    try:
        verdicts = ap.check(doc, **kw)
    except Exception as exc:                            # noqa: BLE001
        res["warnings"].append("Atech port check could not run: %s" % exc)
        return
    res["atech_check"] = {}
    for name, checks in verdicts.items():
        o = doc.getObject(name)
        label = o.Label if o is not None else name
        res["atech_check"][label] = {k: v.get("verdict") for k, v in checks.items()}
        for k, v in checks.items():
            if v.get("verdict") == getattr(ap, "FAIL", "FAIL"):
                res.setdefault("problems", []).append(
                    "Atech %s: %s FAIL" % (label, k))
    res["atech_check_seconds"] = round(time.time() - t, 2)


def _fitted_after(doc, res):
    """R137: intent.json "fitted_after" -> the Labels of model.py's parts it
    names (end caps, a lid fitted after the modules). S50: a name model.py
    has not built is a NOTE while there is no such part - the draft writes
    intent.json with the caps it will add next (4/4 Atech first checks
    failed on that) - and "fitted_after_missing". In Studio's own build
    (ATECH_CHECK_OUT) it stays a problem, so the turn fails if the part
    never appears. Never silently dropped."""
    import atech_geom
    intent, _bad = atech_geom.read_intent(os.path.dirname(res["script"]))
    want = (intent or {}).get("fitted_after")
    if want is None:
        return []
    if isinstance(want, str):
        want = [want]
    if not isinstance(want, list) or not all(isinstance(x, str) for x in want):
        res.setdefault("problems", []).append(
            'intent.json fitted_after must be a list of part labels, e.g. '
            '["End_Cap_L", "End_Cap_R"]')
        return []
    parts = {}
    for o in doc.Objects:
        if getattr(o, "AtechRole", None) or not hasattr(o, "Shape"):
            continue
        parts[o.Name] = o.Label
        parts.setdefault(o.Label, o.Label)
    out, missing = [], []
    for name in want:
        if name in parts:
            if parts[name] not in out:
                out.append(parts[name])
        else:
            missing.append(name)
    if missing:
        res["fitted_after_missing"] = missing
        res.setdefault("notes", []).append(
            "intent.json fitted_after names %s: model.py has not built %s yet (the "
            "parts are: %s). Fine while you are still adding %s; Atelier fails the "
            "turn if %s still missing at the end" % (
                ", ".join(missing), "it" if len(missing) == 1 else "them",
                ", ".join(sorted(set(parts.values()))) or "none",
                "it" if len(missing) == 1 else "them",
                "it is" if len(missing) == 1 else "they are"))
        if os.environ.get("ATECH_CHECK_OUT"):
            # Studio's own build (the sandboxed child) is the one that must
            # still FAIL on it: a build.py that does not read
            # fitted_after_missing yet would otherwise pass a turn that
            # never built the part (before S50 this line failed it here)
            res.setdefault("problems", []).append(
                "intent.json fitted_after names %s: not a part model.py built "
                "(the parts are: %s)" % (", ".join(missing), ", ".join(sorted(
                    set(parts.values()))) or "none"))
    res["fitted_after"] = out
    return out


def _say(line):
    stream = sys.__stdout__ or sys.stdout
    stream.write(line + "\n")


def atech_geom_margin_text(mm):
    import atech_geom
    return atech_geom.margin_text(mm)


def atech_geom_normal_text(n):
    import atech_geom
    return atech_geom.normal_text(n)


def atech_geom_face_text(row):
    import atech_geom
    return atech_geom.face_text(row)


def atech_geom_hold_text(row):
    import atech_geom
    return atech_geom.hold_text(row)


def atech_geom_channel_text(c):
    import atech_geom
    return atech_geom.channel_text(c["label"], c)


def atech_geom_motion_text(m):
    import atech_geom
    return atech_geom.motion_text(m)


def atech_geom_mates_text(row):
    import atech_geom
    return atech_geom.mates_text(row)


def atech_geom_wall_probe():
    import atech_geom
    return atech_geom.WALL_PROBE_MM


def _say_summary(res):
    for f in res["objects"]:
        if f.get("error"):
            _say("OBJECT %s: %s" % (f.get("label"), f["error"]))
            continue
        _say("OBJECT %s: valid=%s solids=%s volume=%s mm3 size=%s mm" % (
            f.get("label"), f.get("valid"), f.get("solids"), f.get("volume_mm3"),
            " x ".join("%g" % v for v in f.get("size") or [])))
    at = res.get("atech") or {}
    for m in at.get("modules") or []:
        _say("ATECH module %s on port(s) %s%s" % (
            m["label"], ",".join(str(p) for p in m["ports"]),
            " (the user's)" if m.get("seeded") else ""))
    lay = res.get("atech_layout") or {}
    if lay.get("board_tilt_from_vertical_deg") is not None:
        _say("ATECH board plane %.0f deg from vertical (0 = upright, 90 = flat)"
             % lay["board_tilt_from_vertical_deg"])
    for m in lay.get("margins") or []:
        _say("MARGIN %s inside %s's outline: %s mm (measured box to box; "
             "negative = sticks out)" % (m["label"], m["part"],
                                         atech_geom_margin_text(m["mm"])))
    for m in lay.get("margins_all") or []:
        _say("MARGIN board + modules together inside %s's outline: %s mm"
             % (m["part"], atech_geom_margin_text(m["mm"])))
    if res.get("fitted_after"):
        _say("ATECH fitted after the modules (slide paths ignore them): %s"
             % ", ".join(res["fitted_after"]))
    for r in res.get("face_open") or []:
        _say("OPEN %s%s: %d of %d rays from its %s get out of the "
             "product (%g %%)%s" % (
                 r["label"], " (a %s)" % r["kind"] if r["kind"] else "", r["open"],
                 r["rays"], atech_geom_face_text(r), r["open_pct"],
                 "" if r["open"] or not r["blocked_by"]
                 else "; %s is in the way" % r["blocked_by"]))
    for c in res.get("containers") or []:
        if c.get("open") is None:
            _say("CONTAINER %s: not probed (%s)" % (c["label"], c.get("skipped")))
        elif c["open"]:
            _say("CONTAINER %s: open from %s - a ray into its middle gets %.2f "
                 "of its %.2f mm deep" % (
                     c["label"], "above" if c["side"] == "+Z" else "the %s side" % c["side"],
                     c["depth_mm"], c["height_mm"]))
        else:
            _say("CONTAINER %s: CLOSED on every side - from above, solid at z "
                 "%.2f .. %.2f mm" % (c["label"], c["blocked_z"][0], c["blocked_z"][1]))
    w = res.get("walls") or {}
    if w.get("min"):
        m = w["min"]
        _say("WALL thinnest measured: %s %.2f mm near (%s) (%d sampled rays, %.2f s%s; "
             "a sampled probe, not every wall)" % (
                 m["label"], m["mm"], ", ".join("%.1f" % v for v in m["at"]),
                 w["samples"], w["seconds"], "" if w["complete"] else ", time cap hit"))
    elif w.get("parts"):
        _say("WALL no wall under %g mm found (%d sampled rays, %.2f s%s)" % (
            atech_geom_wall_probe(), w["samples"], w["seconds"],
            "" if w["complete"] else ", time cap hit"))
    for p in (w.get("parts") or [])[:6]:
        if p.get("skipped"):
            _say("WALL %s not probed: %s" % (p["label"], p["skipped"]))
        elif p.get("side"):
            sd = p["side"]
            _say("WALL %s side walls: %.2f mm (%.2f .. %.2f, %d%% of the side-wall rays), "
                 "measured normal to the wall%s - the number to quote" % (p["label"], sd["mm"], sd["lo"], sd["hi"],
                               int(round(100 * sd["share"])),
                               "; intent.json wall_mm %g" % w["wall_mm"]
                               if w.get("wall_mm") is not None else ""))
    hd = res.get("holds") or {}
    if hd.get("verdict") == "PASS":
        _say("HOLDS " + atech_geom_hold_text(hd))
    elif hd.get("verdict"):
        _say("HOLDS %s: %s (see below)" % (hd.get("label") or "held object", hd["verdict"]))
    for c in (res.get("channels") or [])[:8]:
        _say("CHANNEL " + atech_geom_channel_text(c))
    for m in (res.get("motion") or {}).get("parts") or []:
        if m.get("verdict") == "PASS":
            _say("MOTION " + atech_geom_motion_text(m))
        elif m.get("verdict"):
            _say("MOTION %s: %s (see below)" % (m["part"], m["verdict"]))
    for r in res.get("mates") or []:
        if r.get("parts") and all(x.get("verdict") == "PASS" for x in r["parts"]):
            _say("MATES " + atech_geom_mates_text(r))
    for j in res.get("joints") or []:
        if j.get("engaged") and j.get("fastened"):
            _say("JOINT %s fastened to %s: %s" % (j["part"], j["engaged"], j["fastened"]))
        elif j.get("engaged") and j.get("depth_mm") is not None:
            _say("JOINT %s reaches %.2f mm into %s (engaged, not just touching)"
                 % (j["part"], j["depth_mm"], j["engaged"]))
    for n in res.get("notes") or []:
        _say("NOTE " + n)
    for p in res.get("problems") or []:
        _say("PROBLEM " + p)
    for fl in res.get("floating") or []:
        _say("FLOATING %s: %s%s mm from every other body (fine for separate "
             "parts, wrong for one assembly)" % (
                 fl["label"], "" if fl["exact"] else ">= ", fl["gap_mm"]))
    for w in res.get("warnings") or []:
        _say("WARNING " + w)
    if res.get("png"):
        _say("PNG %s  <- Read it and look at it" % res["png"])
    elif res.get("render_skipped"):
        _say("PNG not drawn: %s" % res["render_skipped"])


if __name__ in ("__main__", "check"):
    try:
        main()
    except BaseException:                               # noqa: BLE001
        sys.stdout.write("\n" + MARK + json.dumps(
            {"ok": False, "checker_crash": True, "error": traceback.format_exc()[-4000:]})
            + "\nCHECK FAIL: the checker itself crashed\n")
        sys.stdout.flush()
        os._exit(3)
