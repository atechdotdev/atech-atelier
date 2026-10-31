"""simulate - see the design work, and take it into a simulator (R811).

The Simulate button on the view bar opens the Simulation card:

    Play / Pause   the design runs in the 3D view: every motor turns what
                   its shaft drives (a wheel, a fan, a rotor), each light
                   glows, a distance sensor shows its beam, a screen lights
    Motor speed    rpm of the motors, live
    Run physics    (R813) the export below, opened in MuJoCo's viewer in a
                   child process: the design on a floor, free to move, a
                   speed servo per shaft. MuJoCo is pip-installed once,
                   hash-pinned (MUJOCO_REQUIREMENTS), after the user agrees.
    Export for simulators...
                   a URDF package (robot.urdf + meshes/*.stl + README.md):
                   one fixed body, and a link with a continuous joint for
                   each part a motor turns, masses from the volumes (PLA).
                   Gazebo, NVIDIA Isaac Sim, MuJoCo, PyBullet and ROS read it.
                   Beside it, scene.xml + run_sim.py: the MuJoCo scene that
                   runs (_write_mjcf).

plan(doc) reads the design without a GUI (tests run it under freecadcmd):
a motor is an Atech dc_motor or stepper module; its shaft is the
module's measured working face (atech_ports.working_faces, "out" for a
dc_motor), else the opposite of its slide axis; a part it DRIVES touches
the shaft's end (within DRIVE_GAP_MM) and has its middle near the shaft
line. Display only, as the exploded view: Simulation keeps every
placement it changes and puts it back on stop - on close, before a build,
a save or an export (export_tools.restore_exploded calls stop_all) - and
draws the glows and beams in the scene graph, never in the document.
"""
import math
import os
import re
import struct

#: modules whose shaft turns
MOTOR_MODULES = ("dc_motor", "stepper_motor", "nema17_stepper")
LIGHT_MODULES = ("light",)
SCREEN_MODULES = ("screen", "big_screen")
SENSOR_MODULES = ("distance_sensor",)
#: a part this close to a shaft's end (mm) is on the shaft
DRIVE_GAP_MM = 3.0
#: the distance sensor's beam: length (mm), half-angle (deg), as a VL53L1
BEAM_MM = 160.0
BEAM_HALF_DEG = 13.5
DEFAULT_RPM = 40.0
#: the exported MuJoCo scene's motor speed (a hobby gear motor under load)
DRIVE_RPM = 120.0
#: a 1:48 gear motor's rotor inertia seen at its shaft (kg m2): it keeps
#: the speed servo on a light part (a 4 g sprocket) stable
MOTOR_ARMATURE = 2e-4
PLA_KG_PER_MM3 = 1.24e-6
#: faces per exported mesh (MuJoCo's STL reader stops at 200 000)
MAX_FACES = 150000
#: an Atech module's mass when the mesh gives no volume (kg)
MODULE_KG = 0.012

_RUNNING = {}           # id(doc) -> Simulation
#: MuJoCo installs still running: a QThread destroyed while it runs aborts
#: the app, so they are held here, not by the card, until they finish
_INSTALLS = []


def _product():
    try:
        from . import style
        return style.PRODUCT
    except Exception:                                     # noqa: BLE001
        return "Atech Atelier"


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("Atech simulate: %s\n" % msg)
    except Exception:                                     # noqa: BLE001
        pass


# ------------------------------------------------------------- vectors
def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return tuple(x / n for x in a) if n > 1e-12 else None


def _perp(p, origin, axis):
    """Distance of p from the line origin + t * axis (axis a unit)."""
    d = _sub(p, origin)
    t = _dot(d, axis)
    return math.sqrt(max(0.0, _dot(d, d) - t * t))


def _vec(v):
    return (float(v.x), float(v.y), float(v.z))


# ------------------------------------------------------------- reading
def _visible(o):
    try:
        return bool(o.Visibility)
    except Exception:                                     # noqa: BLE001
        return True


def _bbox(o):
    try:
        bb = o.Mesh.BoundBox if o.TypeId.startswith("Mesh::") else o.Shape.BoundBox
        if not bb.isValid():
            return None
        return (bb.XMin, bb.YMin, bb.ZMin), (bb.XMax, bb.YMax, bb.ZMax)
    except Exception:                                     # noqa: BLE001
        return None


def _centre(bb):
    return tuple((bb[0][i] + bb[1][i]) / 2.0 for i in range(3))


def _diag(bb):
    return math.sqrt(sum((bb[1][i] - bb[0][i]) ** 2 for i in range(3)))


def _points(o):
    """World points of a module mesh (Mesh features hand them back placed)."""
    try:
        return [_vec(p) for p in o.Mesh.Points]
    except Exception:                                     # noqa: BLE001
        return []


def _face_dir(o, words):
    """World unit vector of the module's working face, the first of
    `words` it has; None when unknown."""
    try:
        import atech_ports as ap
        faces = ap.working_faces(o.AtechModule, o.Placement)
        for w in words:
            for f in faces:
                if f.get("word") == w and f.get("world"):
                    return _unit(tuple(f["world"]))
        if faces and faces[0].get("world") and words == ("up",):
            return _unit(tuple(faces[0]["world"]))
    except Exception as exc:                              # noqa: BLE001
        _log("working face of %s: %r" % (getattr(o, "Name", "?"), exc))
    return None


def _tip(points, axis):
    """The middle of the points furthest along axis (within 0.5 mm)."""
    if not points:
        return None
    proj = [_dot(p, axis) for p in points]
    top = max(proj)
    near = [p for p, t in zip(points, proj) if t >= top - 0.5]
    return tuple(sum(p[i] for p in near) / len(near) for i in range(3))


def _is_product_part(o):
    """A printed (or the user's) solid: not the board, a module or a cable."""
    if getattr(o, "AtechRole", None) in ("board", "module"):
        return False
    if getattr(o, "AtechCableModule", ""):
        return False
    try:
        return o.TypeId.startswith("Part::") and not o.Shape.isNull() and bool(o.Shape.Solids)
    except Exception:                                     # noqa: BLE001
        return False


def _dist(shape, p):
    try:
        import FreeCAD
        import Part
        return shape.distToShape(Part.Vertex(FreeCAD.Vector(*p)))[0]
    except Exception:                                     # noqa: BLE001
        return float("inf")


def _top_level(o):
    """Not an input of a boolean (export_tools' rule)."""
    try:
        from . import export_tools
        return export_tools._top_level(o)
    except Exception:                                     # noqa: BLE001
        return True


def plan(doc):
    """What a simulation of doc animates. Returns
    {"motors": [{"name", "label", "module", "axis", "tip", "drives": [Name]}],
     "lights": [{"name", "kind": "light" | "screen", "at", "dir", "size"}],
     "sensors": [{"name", "at", "dir"}],
     "parts": [Name of every product part]}."""
    out = {"motors": [], "lights": [], "sensors": [], "parts": []}
    if doc is None:
        return out
    objs = [o for o in doc.Objects if _visible(o) and _top_level(o)]
    parts = [o for o in objs if _is_product_part(o)]
    out["parts"] = [o.Name for o in parts]
    boxes = {o.Name: _bbox(o) for o in parts}
    allb = [b for b in boxes.values() if b is not None]
    model_diag = 0.0
    if allb:
        lo = tuple(min(b[0][i] for b in allb) for i in range(3))
        hi = tuple(max(b[1][i] for b in allb) for i in range(3))
        model_diag = _diag((lo, hi))
    taken = set()
    for o in objs:
        if getattr(o, "AtechRole", None) != "module":
            continue
        kind = getattr(o, "AtechModule", "")
        pts = _points(o)
        if kind in MOTOR_MODULES:
            axis = _face_dir(o, ("out",))
            if axis is None:
                try:
                    a = _unit(_vec(o.AtechSlideAxis))
                    axis = tuple(-x for x in a) if a else None
                except Exception:                         # noqa: BLE001
                    axis = None
            tip = _tip(pts, axis) if axis else None
            if tip is None:
                continue
            drives = []
            for p in parts:
                bb = boxes.get(p.Name)
                if bb is None or p.Name in taken:
                    continue
                if model_diag and _diag(bb) > 0.7 * model_diag:
                    continue              # the body the motor sits in
                c = _centre(bb)
                if _perp(c, tip, axis) > max(3.0, 0.3 * _diag(bb)):
                    continue
                if _dot(_sub(c, tip), axis) < -0.25 * _diag(bb):
                    continue              # behind the shaft: the motor's side
                if _dist(p.Shape, tip) > DRIVE_GAP_MM:
                    continue
                drives.append(p.Name)
            # R811: what sits on a driven part round the same axis turns
            # with it (the tyre on the rim)
            grow = list(drives)
            while grow:
                hub = doc.getObject(grow.pop())
                for p in parts:
                    bb = boxes.get(p.Name)
                    if bb is None or p.Name in taken or p.Name in drives:
                        continue
                    if model_diag and _diag(bb) > 0.7 * model_diag:
                        continue
                    if _perp(_centre(bb), tip, axis) > max(3.0, 0.15 * _diag(bb)):
                        continue
                    try:
                        gap = p.Shape.distToShape(hub.Shape)[0]
                    except Exception:                     # noqa: BLE001
                        continue
                    if gap <= 0.5:
                        drives.append(p.Name)
                        grow.append(p.Name)
            taken.update(drives)
            out["motors"].append({"name": o.Name, "label": o.Label, "module": kind,
                                  "axis": axis, "tip": tip, "drives": drives})
        elif kind in LIGHT_MODULES + SCREEN_MODULES + SENSOR_MODULES:
            d = _face_dir(o, ("up",))
            if d is None and allb:
                # no library to measure the face: out from the design's middle
                bb = _bbox(o)
                d = _unit(_sub(_centre(bb), _centre((lo, hi)))) if bb else None
            at = _tip(pts, d) if d else None
            if at is None:
                continue
            bb = _bbox(o)
            size = 0.25 * _diag(bb) if bb else 6.0
            if kind in SENSOR_MODULES:
                out["sensors"].append({"name": o.Name, "at": at, "dir": d})
            else:
                out["lights"].append({"name": o.Name, "kind": "screen" if kind in SCREEN_MODULES
                                      else "light", "at": at, "dir": d, "size": size})
    return out


def summary(p):
    """One line per kind for the card ("2 motors turn 4 parts", ...)."""
    lines = []
    turning = sum(len(m["drives"]) for m in p["motors"])
    if p["motors"]:
        lines.append("%d motor%s turn%s %d part%s" % (
            len(p["motors"]), "s" if len(p["motors"]) != 1 else "",
            "" if len(p["motors"]) != 1 else "s",
            turning, "s" if turning != 1 else ""))
        idle = [m["label"] for m in p["motors"] if not m["drives"]]
        if idle:
            lines.append("Nothing on the shaft of %s" % ", ".join(idle))
    n_l = sum(1 for x in p["lights"] if x["kind"] == "light")
    n_s = sum(1 for x in p["lights"] if x["kind"] == "screen")
    if n_l:
        lines.append("%d light%s glow%s" % (n_l, "s" if n_l != 1 else "", "" if n_l != 1 else "s"))
    if n_s:
        lines.append("%d screen%s on" % (n_s, "s" if n_s != 1 else ""))
    if p["sensors"]:
        lines.append("%d distance sensor%s sweep%s its beam" % (
            len(p["sensors"]), "s" if len(p["sensors"]) != 1 else "",
            "" if len(p["sensors"]) != 1 else "s"))
    return lines


def has_motion(p):
    return any(m["drives"] for m in p["motors"]) or bool(p["lights"]) or bool(p["sensors"])


# ------------------------------------------------------------- the run
class Simulation(object):
    """Turns the driven parts. DISPLAY ONLY: every placement it changes is
    kept and put back by stop()."""

    def __init__(self, doc, p=None):
        self.doc = doc
        old = _RUNNING.get(id(doc))
        if old is not None and old is not self:
            old.stop()
        try:
            from . import export_tools
            export_tools.restore_exploded(doc)        # from where parts belong
        except Exception as exc:                          # noqa: BLE001
            _log("exploded view: %r" % (exc,))
        self.plan = p or plan(doc)
        self.rpm = DEFAULT_RPM
        self.angle = 0.0
        self.t = 0.0
        self.saved = {}
        for m in self.plan["motors"]:
            for n in m["drives"]:
                o = doc.getObject(n)
                if o is not None:
                    self.saved[n] = o.Placement.copy()
        self.deco = None
        _RUNNING[id(doc)] = self

    def step(self, dt):
        """Advance dt seconds."""
        import FreeCAD
        self.t += dt
        self.angle = (self.angle + self.rpm * 6.0 * dt) % 360.0
        ref = self.plan["motors"][0]["axis"] if self.plan["motors"] else None
        for m in self.plan["motors"]:
            # shafts facing each other (a car's left and right wheels) turn
            # opposite ways round their own axes, so the wheels roll the same
            # way, as the firmware drives them
            ang = self.angle if _dot(m["axis"], ref) >= -1e-9 else -self.angle
            rot = FreeCAD.Rotation(FreeCAD.Vector(*m["axis"]), ang)
            spin = FreeCAD.Placement(FreeCAD.Vector(), rot, FreeCAD.Vector(*m["tip"]))
            for n in m["drives"]:
                o = self.doc.getObject(n)
                base = self.saved.get(n)
                if o is None or base is None:
                    continue
                o.Placement = spin.multiply(base)
        if self.deco is not None:
            self.deco.pulse(self.t)

    def stop(self):
        for n, pl in self.saved.items():
            o = self.doc.getObject(n)
            if o is not None:
                try:
                    o.Placement = pl
                except Exception as exc:                  # noqa: BLE001
                    _log("put back %s: %r" % (n, exc))
        self.saved = {}
        if self.deco is not None:
            self.deco.remove()
            self.deco = None
        if _RUNNING.get(id(self.doc)) is self:
            _RUNNING.pop(id(self.doc), None)


def running(doc):
    return _RUNNING.get(id(doc)) if doc is not None else None


def stop_all(doc=None):
    """Put back every running simulation (of doc, or all)."""
    for _k, sim in list(_RUNNING.items()):
        if doc is None or sim.doc is doc:
            sim.stop()


class _Decorations(object):
    """Glows and beams in the active view's scene graph (pivy). Nothing
    goes into the document."""

    def __init__(self, p, view=None):
        from pivy import coin
        if view is None:
            import FreeCADGui
            view = FreeCADGui.ActiveDocument.ActiveView
        self.view = view
        self.root = coin.SoSeparator()
        self.mats = []
        for x in p["lights"]:
            self.root.addChild(self._glow(coin, x))
        for s in p["sensors"]:
            self.root.addChild(self._beam(coin, s))
        self.view.getSceneGraph().addChild(self.root)

    def _material(self, coin, rgb, transp):
        m = coin.SoMaterial()
        m.diffuseColor.setValue(*rgb)
        m.emissiveColor.setValue(*rgb)
        m.transparency.setValue(transp)
        return m

    def _glow(self, coin, x):
        sep = coin.SoSeparator()
        rgb = (1.0, 0.85, 0.45) if x["kind"] == "light" else (0.55, 0.8, 1.0)
        m = self._material(coin, rgb, 0.45)
        self.mats.append((m, 0.45, x["kind"]))
        tr = coin.SoTranslation()
        tr.translation.setValue(*x["at"])
        sep.addChild(m)
        sep.addChild(tr)
        sph = coin.SoSphere()
        sph.radius.setValue(max(3.0, x["size"]))
        sep.addChild(sph)
        return sep

    def _beam(self, coin, s):
        sep = coin.SoSeparator()
        m = self._material(coin, (0.3, 0.9, 0.6), 0.75)
        self.mats.append((m, 0.75, "beam"))
        sep.addChild(m)
        tf = coin.SoTransform()
        # SoCone points +Y with its middle at the origin: turn +Y onto the
        # sensor's direction, the apex at the sensor
        d = s["dir"]
        rot = coin.SbRotation(coin.SbVec3f(0, -1, 0), coin.SbVec3f(*d))
        tf.rotation.setValue(rot)
        mid = tuple(s["at"][i] + d[i] * BEAM_MM / 2.0 for i in range(3))
        tf.translation.setValue(*mid)
        sep.addChild(tf)
        cone = coin.SoCone()
        cone.height.setValue(BEAM_MM)
        cone.bottomRadius.setValue(BEAM_MM * math.tan(math.radians(BEAM_HALF_DEG)))
        cone.parts.setValue(coin.SoCone.SIDES)
        sep.addChild(cone)
        return sep

    def pulse(self, t):
        for m, base, kind in self.mats:
            if kind == "light":
                v = base + 0.25 * math.sin(t * 4.0)
            elif kind == "beam":
                v = base + 0.12 * math.sin(t * 9.0)
            else:
                v = base
            m.transparency.setValue(max(0.0, min(0.95, v)))

    def remove(self):
        try:
            self.view.getSceneGraph().removeChild(self.root)
        except Exception as exc:                          # noqa: BLE001
            _log("remove glows: %r" % (exc,))


# ------------------------------------------------------------- URDF
def _safe(name):
    s = re.sub(r"[^A-Za-z0-9_]+", "_", str(name or "")).strip("_")
    return s or "part"


def _triangles(o):
    """World triangles [(p0, p1, p2)] of a Part or Mesh object."""
    try:
        if o.TypeId.startswith("Mesh::"):
            m = o.Mesh
            pts = [_vec(p) for p in m.Points]
            return [tuple(pts[i] for i in f) for f in m.Topology[1]]
        # MuJoCo reads at most 200 000 faces a mesh: coarser until under
        # (a fresh copy each time: a shape keeps its first triangulation)
        for tol in (0.1, 0.25, 0.6, 1.5, 4.0):
            try:
                sh = o.Shape.copy(True, False)
            except TypeError:
                sh = o.Shape.copy()
            pts, tris = sh.tessellate(tol)
            if len(tris) <= MAX_FACES:
                break
        pts = [_vec(p) for p in pts]
        return [(pts[a], pts[b], pts[c]) for a, b, c in tris]
    except Exception as exc:                              # noqa: BLE001
        _log("triangles of %s: %r" % (getattr(o, "Name", "?"), exc))
        return []


def write_stl(path, tris, origin=(0.0, 0.0, 0.0), scale=0.001):
    """Binary STL of tris moved by -origin and scaled (mm -> m)."""
    with open(path, "wb") as fh:
        fh.write(_product().encode("ascii", "replace")[:80].ljust(80, b" "))
        fh.write(struct.pack("<I", len(tris)))
        for tri in tris:
            q = [tuple((p[i] - origin[i]) * scale for i in range(3)) for p in tri]
            u, v = _sub(q[1], q[0]), _sub(q[2], q[0])
            n = _unit((u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
                       u[0] * v[1] - u[1] * v[0])) or (0.0, 0.0, 0.0)
            fh.write(struct.pack("<3f", *n))
            for p in q:
                fh.write(struct.pack("<3f", *p))
            fh.write(b"\0\0")
    return path


def _mass(o):
    try:
        if o.TypeId.startswith("Mesh::"):
            v = abs(o.Mesh.Volume)
            return v * PLA_KG_PER_MM3 * 1.5 if v > 1.0 else MODULE_KG
        return max(1e-4, o.Shape.Volume * PLA_KG_PER_MM3)
    except Exception:                                     # noqa: BLE001
        return MODULE_KG


def _inertia(objs, origin):
    """objs together: (mass kg, centre m from origin, (ixx, iyy, izz)) of a
    solid box over their bounding box, or None when nothing has a size."""
    mass, c, lo, hi = 0.0, [0.0, 0.0, 0.0], [1e18] * 3, [-1e18] * 3
    for o in objs:
        bb = _bbox(o)
        if bb is None:
            continue
        m = _mass(o)
        mass += m
        cc = _centre(bb)
        for i in range(3):
            c[i] += m * cc[i]
            lo[i] = min(lo[i], bb[0][i])
            hi[i] = max(hi[i], bb[1][i])
    if mass <= 0.0:
        return None
    c = [(c[i] / mass - origin[i]) * 0.001 for i in range(3)]
    sx, sy, sz = [max(1e-3, (hi[i] - lo[i]) * 0.001) for i in range(3)]
    return (mass, c, (mass * (sy * sy + sz * sz) / 12.0,
                      mass * (sx * sx + sz * sz) / 12.0,
                      mass * (sx * sx + sy * sy) / 12.0))


def _inertial(objs, origin):
    """URDF <inertial> of objs together (_inertia)."""
    ine = _inertia(objs, origin)
    if ine is None:
        return '    <inertial><mass value="0.001"/><inertia ixx="1e-7" ixy="0" ixz="0" ' \
               'iyy="1e-7" iyz="0" izz="1e-7"/></inertial>\n'
    mass, c, (ixx, iyy, izz) = ine
    return ('    <inertial>\n      <origin xyz="%.6f %.6f %.6f" rpy="0 0 0"/>\n'
            '      <mass value="%.6f"/>\n      <inertia ixx="%.4g" ixy="0" ixz="0" '
            'iyy="%.4g" iyz="0" izz="%.4g"/>\n    </inertial>\n'
            % (c[0], c[1], c[2], mass, ixx, iyy, izz))


def _rgba(o):
    try:
        c = o.ViewObject.ShapeColor
        return "%.3f %.3f %.3f 1" % tuple(c[:3])
    except Exception:                                     # noqa: BLE001
        return "0.8 0.8 0.8 1" if not getattr(o, "AtechRole", None) else "0.2 0.2 0.2 1"


def export_urdf(doc, folder, p=None, rpm=DRIVE_RPM):
    """Write doc as a URDF package in folder (made if needed), and beside it
    a MuJoCo scene that runs (scene.xml + run_sim.py, _write_mjcf). Returns
    {"urdf": path, "mjcf": path, "run": path, "links": n, "joints": n,
    "meshes": n}."""
    stop_all(doc)
    try:
        from . import export_tools
        export_tools.restore_exploded(doc)
    except Exception as exc:                              # noqa: BLE001
        _log("exploded view: %r" % (exc,))
    p = p or plan(doc)
    name = _safe(getattr(doc, "Label", "") or getattr(doc, "Name", "design")).lower()
    mesh_dir = os.path.join(folder, "meshes")
    os.makedirs(mesh_dir, exist_ok=True)
    driven = {}
    for m in p["motors"]:
        for n in m["drives"]:
            driven[n] = m
    shown = [o for o in doc.Objects if _visible(o) and _top_level(o)
             and (_is_product_part(o) or getattr(o, "AtechRole", None) in ("board", "module")
                  or getattr(o, "AtechCableModule", ""))]
    base = [o for o in shown if o.Name not in driven]
    used = set()
    n_mesh = 0
    low = [None]                         # lowest point of the design, mm
    rec = {"base": [], "rotors": []}     # what _write_mjcf builds from

    def visual(o, origin, ind="    ", into=rec["base"]):
        nonlocal n_mesh
        fn = _safe(o.Label)
        while fn in used:
            fn += "_"
        used.add(fn)
        tris = _triangles(o)
        if not tris:
            return ""
        write_stl(os.path.join(mesh_dir, fn + ".stl"), tris, origin)
        n_mesh += 1
        z = min(q[2] for t in tris for q in t)
        low[0] = z if low[0] is None else min(low[0], z)
        into.append((fn, _rgba(o)))
        geom = '<geometry><mesh filename="meshes/%s.stl"/></geometry>' % fn
        return ('%s<visual name="%s">\n%s  %s\n%s  <material name="%s_c"><color rgba="%s"/>'
                '</material>\n%s</visual>\n%s<collision name="%s_collision">\n%s  %s\n%s</collision>\n'
                % (ind, fn, ind, geom, ind, fn, _rgba(o), ind, ind, fn, ind, geom, ind))

    xml = ['<?xml version="1.0"?>\n',
           '<!-- %s, exported by %s for simulators (URDF, metres, kg). -->\n'
           % (getattr(doc, "Label", name), _product()),
           '<robot name="%s">\n' % name,
           '  <link name="base_link">\n']
    for o in base:
        xml.append(visual(o, (0.0, 0.0, 0.0)))
    xml.append(_inertial(base, (0.0, 0.0, 0.0)))
    xml.append('  </link>\n')
    n_joint = 0
    for k, m in enumerate(p["motors"]):
        objs = [doc.getObject(n) for n in m["drives"]]
        objs = [o for o in objs if o is not None]
        if not objs:
            continue
        link = "%s_rotor" % _safe(m["label"]).lower()
        geoms = []
        xml.append('  <link name="%s">\n' % link)
        for o in objs:
            xml.append(visual(o, m["tip"], into=geoms))
        xml.append(_inertial(objs, m["tip"]))
        rec["rotors"].append({"link": link, "joint": "%s_shaft" % _safe(m["label"]).lower(),
                              "tip": m["tip"], "axis": m["axis"], "geoms": geoms,
                              "inertia": _inertia(objs, m["tip"])})
        xml.append('  </link>\n')
        xml.append('  <joint name="%s_shaft" type="continuous">\n'
                   '    <parent link="base_link"/>\n    <child link="%s"/>\n'
                   '    <origin xyz="%.6f %.6f %.6f" rpy="0 0 0"/>\n'
                   '    <axis xyz="%.6f %.6f %.6f"/>\n'
                   '    <limit effort="0.08" velocity="%.3f"/>\n'
                   '    <dynamics damping="0.0005" friction="0"/>\n  </joint>\n'
                   % (_safe(m["label"]).lower(), link,
                      m["tip"][0] * 0.001, m["tip"][1] * 0.001, m["tip"][2] * 0.001,
                      m["axis"][0], m["axis"][1], m["axis"][2],
                      200.0 * 2 * math.pi / 60.0))
        n_joint += 1
    xml.append('</robot>\n')
    path = os.path.join(folder, name + ".urdf")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(xml))
    rec["inertia"] = _inertia(base, (0.0, 0.0, 0.0))
    rec["lift"] = -(low[0] or 0.0) * 0.001 + 0.002
    mjcf = os.path.join(folder, "scene.xml")
    with open(mjcf, "w", encoding="utf-8") as fh:
        fh.write(_write_mjcf(name, getattr(doc, "Label", name), rec, rpm))
    run = os.path.join(folder, "run_sim.py")
    with open(run, "w", encoding="utf-8") as fh:
        fh.write(RUN_SIM % {"label": getattr(doc, "Label", name), "product": _product()})
    with open(os.path.join(folder, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(README % {"name": name, "label": getattr(doc, "Label", name),
                           "product": _product(),
                           "joints": n_joint, "rpm": rpm,
                           "lines": "\n".join("- " + s for s in summary(p)) or "- no motors"})
    return {"urdf": path, "mjcf": mjcf, "run": run, "links": 1 + n_joint,
            "joints": n_joint, "meshes": n_mesh}


def drive_signs(rotors):
    """+1/-1 per rotor so every shaft turns the same way about the first
    one's axis: the left and right motors of a car face each other, and the
    same speed about each shaft's own axis would spin the car on the spot."""
    ref = rotors[0]["axis"] if rotors else None
    return [1 if ref is None or _dot(r["axis"], ref) >= 0.0 else -1 for r in rotors]


def _mj_inertial(ine, ind):
    if ine is None:
        return '%s<inertial pos="0 0 0" mass="0.001" diaginertia="1e-7 1e-7 1e-7"/>\n' % ind
    mass, c, d = ine
    return ('%s<inertial pos="%.6f %.6f %.6f" mass="%.6f" diaginertia="%.4g %.4g %.4g"/>\n'
            % (ind, c[0], c[1], c[2], mass, d[0], d[1], d[2]))


def _write_mjcf(name, label, rec, rpm):
    """A MuJoCo scene of the export (rec from export_urdf): the design rests
    on a floor on a free joint, each motor's rotor turns on a hinge with a
    velocity servo held at rpm by the "drive" keyframe (run_sim.py loads
    it). The meshes are the URDF's; collisions are their convex hulls."""
    rad_s = rpm * 2.0 * math.pi / 60.0
    out = ['<?xml version="1.0"?>\n',
           '<!-- %s, exported by %s: a MuJoCo scene that runs (metres, kg).\n'
           '     Run it: python run_sim.py. In MuJoCo\'s own viewer, Load key\n'
           '     "drive" to start the motors. -->\n' % (label, _product()),
           '<mujoco model="%s">\n' % name,
           '  <compiler angle="radian" meshdir="meshes" autolimits="true"/>\n',
           '  <option timestep="0.001" integrator="implicitfast"/>\n',
           '  <visual><headlight diffuse=".6 .6 .6" ambient=".3 .3 .3"/>'
           '<global offwidth="1280" offheight="720"/></visual>\n',
           '  <default>\n    <geom friction="1 0.01 0.001" solref="0.004 1"/>\n'
           '    <joint damping="0.0005" armature="%g"/>\n  </default>\n' % MOTOR_ARMATURE,
           '  <asset>\n',
           '    <texture name="grid" type="2d" builtin="checker" width="512" height="512"'
           ' rgb1=".92 .92 .9" rgb2=".82 .82 .8"/>\n',
           '    <material name="grid" texture="grid" texrepeat="8 8" reflectance=".05"/>\n']
    for fn, _ in rec["base"] + [g for r in rec["rotors"] for g in r["geoms"]]:
        out.append('    <mesh name="%s" file="%s.stl"/>\n' % (fn, fn))
    out += ['  </asset>\n', '  <worldbody>\n',
            '    <light pos="0 0 2" dir="0 0 -1" diffuse=".8 .8 .8"/>\n',
            '    <geom name="floor" type="plane" size="0 0 0.05" material="grid"/>\n',
            '    <body name="base_link" pos="0 0 %.6f">\n' % rec["lift"],
            '      <freejoint name="base_free"/>\n',
            _mj_inertial(rec["inertia"], "      ")]
    for fn, rgba in rec["base"]:
        out.append('      <geom type="mesh" mesh="%s" rgba="%s"/>\n' % (fn, rgba))
    for r in rec["rotors"]:
        t, a = r["tip"], r["axis"]
        out.append('      <body name="%s" pos="%.6f %.6f %.6f">\n'
                   % (r["link"], t[0] * 0.001, t[1] * 0.001, t[2] * 0.001))
        out.append('        <joint name="%s" type="hinge" axis="%.6f %.6f %.6f"/>\n'
                   % (r["joint"], a[0], a[1], a[2]))
        out.append(_mj_inertial(r["inertia"], "        "))
        for fn, rgba in r["geoms"]:
            out.append('        <geom type="mesh" mesh="%s" rgba="%s"/>\n' % (fn, rgba))
        out.append('      </body>\n')
    out += ['    </body>\n', '  </worldbody>\n']
    if rec["rotors"]:
        # a hobby gear motor: about 0.08 N m stall, a speed servo up to that
        out.append('  <actuator>\n')
        for r in rec["rotors"]:
            out.append('    <velocity name="%s" joint="%s" kv="0.01" ctrlrange="%.3f %.3f"'
                       ' forcerange="-0.08 0.08"/>\n'
                       % (r["joint"], r["joint"], -2.0 * rad_s, 2.0 * rad_s))
        out.append('  </actuator>\n')
        out.append('  <keyframe>\n    <key name="drive" ctrl="%s"/>\n  </keyframe>\n'
                   % " ".join("%.4f" % (s * rad_s) for s in drive_signs(rec["rotors"])))
    out.append('</mujoco>\n')
    return "".join(out)


RUN_SIM = '''"""Run %(label)s in MuJoCo (exported by %(product)s).

    pip install mujoco
    python run_sim.py            the viewer, motors at the exported speed
    python run_sim.py --check 3  no window: run 3 s, print what moved
"""
import os
import sys

import mujoco

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    m = mujoco.MjModel.from_xml_path(os.path.join(HERE, "scene.xml"))
    d = mujoco.MjData(m)
    if m.nkey:
        mujoco.mj_resetDataKeyframe(m, d, 0)     # "drive": the motors on
    mujoco.mj_forward(m, d)
    return m, d


def check(seconds):
    m, d = load()
    start = d.qpos[:3].copy()
    for _ in range(int(seconds / m.opt.timestep)):
        mujoco.mj_step(m, d)
    moved = float(sum((d.qpos[i] - start[i]) ** 2 for i in range(2)) ** 0.5)
    spins = [abs(float(d.qvel[m.jnt_dofadr[j]])) for j in range(m.njnt)
             if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE]
    print("SIM_CHECK seconds=%%.2f travelled_m=%%.4f height_m=%%.4f shafts_rad_s=%%s ok=%%s"
          %% (seconds, moved, float(d.qpos[2]), [round(s, 2) for s in spins],
             bool(all(abs(float(v)) < 1e6 for v in d.qpos))))


if __name__ == "__main__":
    if "--check" in sys.argv:
        i = sys.argv.index("--check")
        check(float(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 3.0)
    else:
        import mujoco.viewer
        mujoco.viewer.launch(*load())
'''


README = """# %(label)s for simulators

Exported by %(product)s. `%(name)s.urdf` is the design in URDF (metres,
kilograms): `base_link` holds every part that does not turn, and each part
a motor turns is its own link on a continuous joint about the motor's
shaft (%(joints)d joint(s)). Masses come from the volumes at PLA density
(1.24 g/cm3); inertias are a solid box over each link. The meshes are in
`meshes/` and the URDF refers to them by relative path.

%(lines)s

## Run it

`scene.xml` is the same design ready to run in MuJoCo: it rests on a floor,
free to move, and each motor is a speed servo (%(rpm)g rpm, at most
0.08 N m, a hobby gear motor) that starts with the "drive" keyframe. The
motors on either side of a car turn the same way, so it drives straight.
Collisions use each part's convex hull.

    pip install mujoco
    python run_sim.py              # the viewer; drag the motor sliders
    python run_sim.py --check 3    # no window: run 3 s, print what moved

## Open the URDF in

- **MuJoCo**: `python -m mujoco.viewer --mjcf=%(name)s.urdf` (fixed base)
- **PyBullet**: `p.loadURDF("%(name)s.urdf")`
- **NVIDIA Isaac Sim**: Isaac Utils > Workflows > URDF Importer
- **Gazebo**: `gz sim`, then add it with `gz service ... /create` or a
  world file `<include><uri>file://%(name)s.urdf</uri></include>`
- **ROS 2**: `ros2 launch urdf_tutorial display.launch.py model:=$PWD/%(name)s.urdf`
"""


# ------------------------------------------------------------- MuJoCo
#: Run physics: MuJoCo (Apache-2.0) and what it needs, for the app's Python
#: (CPython 3.11; numpy is the app's own). Wheels only, every file's sha256
#: copied from PyPI on 2026-10-30 (macOS arm64/x86_64, Linux x86_64/aarch64,
#: Windows x64); pip --require-hashes refuses any other file. A new version
#: means new hashes here, never fetched at run time. About 30 MB to fetch.
MUJOCO_VERSION = "3.17.0"
MUJOCO_DIR_NAME = "mujoco-" + MUJOCO_VERSION
MUJOCO_REQUIREMENTS = """\
absl-py==2.5.1 \
    --hash=sha256:721200f2f0e9960f2ca9dc3a2a706b201f5f75d812c158f059cbbe29eeafbdb8
etils==1.14.0 \
    --hash=sha256:b5df7341f54dbe1405a4450b2741207b4a8c279780402b45f87202b94dfc52b4
fsspec==2026.9.0 \
    --hash=sha256:8dd6e646e99ea382bd85f97a45e6b526a442d79423a7dc673f1e2756d05fcb5f
glfw==2.11.0 \
    --hash=sha256:4f40b141657b014148893f3b8950906389f9d4d3b2bced41fbefcdcda776e9ad \
    --hash=sha256:7405d3e3041add442e40a15ef5a880178ff90f486d576a82e112240c66f59555 \
    --hash=sha256:de02fcb11126242a27f5f711b31ab83ae4dfe3567caa32dc2380e1f6050c59f1 \
    --hash=sha256:a08e1135d02c9408d7622db3d391e3e33e4187754ec45633e9a482c775f4846c \
    --hash=sha256:e2f6be6bb463f98b7468386ec2e5328ee5975800580c28816ec549b4c62825c4 \
    --hash=sha256:76484fae4a4ef0f778a05e02422ecbe6960ae23039087fe2e0ad9742ab8c7bbe \
    --hash=sha256:bd39c1adb57b7273813e33b9768bed88d1ea656abfc914b4a6424ec0c5d62674
mujoco==3.17.0 \
    --hash=sha256:6c324addca24a24a7b0beff2ec49300e9d4481fd8ccd611514ba7ea8e4a5e870 \
    --hash=sha256:91a70ed9979c383ff1f5c03f25cc2e1280a8254c1a8e558d5dd7f4184f01efc9 \
    --hash=sha256:d66928d86a2d1b601bbaa4dc11db50214d17d5301bb8afd84721313b67ff0874 \
    --hash=sha256:390c4820796e2b905f64f011ae3c307d686f8548a3571b7420da0001ee6faaf2
pyopengl==3.1.10 \
    --hash=sha256:794a943daced39300879e4e47bd94525280685f42dbb5a998d336cfff151d74f
typing-extensions==4.16.0 \
    --hash=sha256:481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8
websockets==17.3 \
    --hash=sha256:45cc1ccb12ced6d242335159e8221733c8696da5ad0b6ceef6debb0f5ce89110 \
    --hash=sha256:46ae05aa1aecd47d4d7de0f05ce2d1d2eb418f8de614964d754cc3b9a409c400 \
    --hash=sha256:43f270a5f21e12db08c73d83849a877c02ab7b7d0fb6e2718b5101d9c810212f \
    --hash=sha256:5ad409b7ea102339041281117cf2dadfe71edbb653dc48037cc55d516fb7f448 \
    --hash=sha256:56d43c311f3519fb1057b6114dc24e9060bc3fb6aedf4aa11160484154b66b63 \
    --hash=sha256:d338813a440bf6d2f0df55140d3f3080284410b1ebfe9df50e3847bcdb1a17bb \
    --hash=sha256:dc2b495a92b3971966bf102e73589f950db3ec1ca6713265355ce7771d97b199
zipp==4.1.2 \
    --hash=sha256:b30cb6cd253122169c47de245ca24a86bac2a5d3802ba15bf7ba6414eb9e144d
"""


class PhysicsError(RuntimeError):
    """MuJoCo cannot be installed or started."""


def python_exe():
    """A plain Python to run MuJoCo in: the app's own bin/python
    (FreeCAD's sys.executable is the FreeCAD binary), else this one."""
    import sys
    cands = []
    try:
        import FreeCAD
        cands.append(os.path.join(FreeCAD.getHomePath(), "bin", "python"))
    except Exception:                                     # noqa: BLE001
        pass
    exe = sys.executable or ""
    cands += [os.path.join(os.path.dirname(exe), n) for n in ("python", "python3")]
    if os.path.basename(exe).startswith("python"):
        cands.append(exe)
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise PhysicsError("no Python to run MuJoCo with")


def mujoco_dir():
    """Where MuJoCo is installed for the app ($ATELIER_MUJOCO_DIR overrides),
    beside usd-core in <user data>/pylibs."""
    env = (os.environ.get("ATELIER_MUJOCO_DIR") or "").strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    try:
        import FreeCAD
        return os.path.join(FreeCAD.getUserAppDataDir(), "pylibs", MUJOCO_DIR_NAME)
    except Exception:                                     # noqa: BLE001
        raise PhysicsError("no user data folder to install MuJoCo in")


def _boot(lib, code):
    """-c code for a child Python that sees lib first (-I: no user site,
    no PYTHON* variables)."""
    return "import sys; sys.path[:0] = [%r]; %s" % (lib, code)


def mujoco_available(python=None):
    """True when the app's Python can import the installed MuJoCo."""
    import subprocess
    try:
        r = subprocess.run([python or python_exe(), "-I", "-c",
                            _boot(mujoco_dir(), "import mujoco, glfw")],
                           capture_output=True, timeout=120)
        return r.returncode == 0
    except Exception:                                     # noqa: BLE001
        return False


def ensure_mujoco(progress=None, python=None):
    """Install the pinned MuJoCo into mujoco_dir() once (pip, wheels only,
    hash-checked). Returns the folder."""
    import shutil
    import subprocess
    import tempfile
    python = python or python_exe()
    d = mujoco_dir()
    if mujoco_available(python):
        return d
    if progress:
        progress("Installing MuJoCo (once, about 30 MB)…")
    tmp = tempfile.mkdtemp(prefix="atelier_mujoco_")
    try:
        req = os.path.join(tmp, "requirements.txt")
        with open(req, "w") as fh:
            fh.write(MUJOCO_REQUIREMENTS)
        stage = os.path.join(tmp, "site")
        r = subprocess.run(
            [python, "-I", "-m", "pip", "install", "--quiet", "--no-deps",
             "--only-binary", ":all:", "--require-hashes", "--no-cache-dir",
             "--disable-pip-version-check", "--target", stage, "-r", req],
            capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            raise PhysicsError("could not install MuJoCo: %s"
                               % (r.stderr or r.stdout).strip()[-600:])
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.move(stage, d)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not mujoco_available(python):
        raise PhysicsError("MuJoCo was installed but does not load")
    return d


def run_command(run_py, python=None, check=None):
    """argv that runs an export's run_sim.py with the installed MuJoCo:
    the viewer, or check=seconds without a window."""
    argv = [run_py] + (["--check", "%g" % check] if check else [])
    return [python or python_exe(), "-I", "-c",
            _boot(mujoco_dir(), "sys.argv = %r; import runpy; "
                  "runpy.run_path(%r, run_name='__main__')" % (argv, run_py))]


def launch_mujoco(run_py, python=None):
    """Open MuJoCo's viewer on an export in its own process. Returns it."""
    import subprocess
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    _log("physics: %s" % run_py)
    log = open(os.path.join(os.path.dirname(run_py), "physics.log"), "w")
    try:
        return subprocess.Popen(run_command(run_py, python), cwd=os.path.dirname(run_py),
                                env=env, start_new_session=True,
                                stdout=log, stderr=subprocess.STDOUT)
    finally:
        log.close()                    # the child keeps its own handle


# ------------------------------------------------------------- the card
def default_folder(doc):
    base = os.path.join(os.path.expanduser("~/Documents"), _product(), "Simulations")
    return os.path.join(base, _safe(getattr(doc, "Label", "") or "design"))


def SimulationCard(parent=None, doc_fn=None, gui=True):
    """The Simulation card (measure's floating card). gui=False: no timer
    playback in 3D decorations (plain Qt tests)."""
    from PySide6 import QtCore, QtWidgets
    from . import export_tools as et, measure

    doc_fn = doc_fn or et._active_doc
    Card = measure._card_class()

    class _SimCard(Card):
        def __init__(self):
            super().__init__("Simulation", parent)
            self.doc = None
            self.sim = None
            self.plan = None
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(33)
            self.timer.timeout.connect(self._tick)
            self._last = None
            hint = QtWidgets.QLabel("Watch the design work: motors turn what "
                                    "they drive, lights glow, sensors show "
                                    "their beam. Only the picture moves.")
            hint.setObjectName("MHint")
            hint.setWordWrap(True)
            self.lay.addWidget(hint)
            self.what = QtWidgets.QLabel("")
            self.what.setObjectName("MDetail")
            self.what.setWordWrap(True)
            self.lay.addWidget(self.what)
            sp = QtWidgets.QLabel("MOTOR SPEED")
            sp.setObjectName("MSub")
            self.lay.addWidget(sp)
            srow = QtWidgets.QHBoxLayout()
            self.speed = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            self.speed.setObjectName("MSlider")
            self.speed.setRange(5, 200)
            self.speed.setValue(int(DEFAULT_RPM))
            self.speed.setAccessibleName("Motor speed")
            self.speed.valueChanged.connect(self._on_speed)
            self.rpm = QtWidgets.QLabel("%d rpm" % DEFAULT_RPM)
            self.rpm.setObjectName("MDetail")
            self.rpm.setFixedWidth(56)
            srow.addWidget(self.speed, 1)
            srow.addWidget(self.rpm)
            self.lay.addLayout(srow)
            brow = QtWidgets.QHBoxLayout()
            brow.setSpacing(6)
            self.btn_export = QtWidgets.QPushButton("Export for simulators…")
            self.btn_export.setObjectName("MGhost")
            self.btn_export.setToolTip("A URDF package for Gazebo, Isaac Sim, "
                                       "MuJoCo, PyBullet and ROS")
            self.btn_physics = QtWidgets.QPushButton("Run physics")
            self.btn_physics.setObjectName("MGhost")
            self.btn_physics.setToolTip("Open the design in MuJoCo: it rests on a "
                                        "floor and the motors drive it")
            self.btn_play = QtWidgets.QPushButton("Play")
            self.btn_play.setObjectName("MPrimary")
            self.btn_play.setToolTip("Run the design (Space)")
            for b in (self.btn_export, self.btn_physics, self.btn_play):
                b.setCursor(QtCore.Qt.PointingHandCursor)
                b.setAccessibleName(b.text())
            self.btn_export.clicked.connect(lambda: et._guard(self.export))
            self.btn_play.clicked.connect(lambda: et._guard(self.toggle))
            self.btn_physics.clicked.connect(lambda: et._guard(self.run_physics))
            brow.addWidget(self.btn_export)
            brow.addWidget(self.btn_physics)
            brow.addStretch(1)
            brow.addWidget(self.btn_play)
            self.lay.addLayout(brow)
            self.status = QtWidgets.QLabel("")
            self.status.setObjectName("MHint")
            self.status.setWordWrap(True)
            self.status.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
            self.status.setOpenExternalLinks(True)
            self.lay.addWidget(self.status)
            self.closed.connect(self.stop)

        def place(self):
            p = self.parentWidget()
            if p is None:
                return
            self.adjustSize()
            h = min(self.sizeHint().height(), max(120, p.height() - 32))
            self.setGeometry(max(16, p.width() - self.width() - 16), 16, self.width(), h)
            self.raise_()

        def keyPressEvent(self, ev):                  # noqa: N802
            if ev.key() == QtCore.Qt.Key_Space:
                et._guard(self.toggle)
                return
            super().keyPressEvent(ev)

        def open_card(self):
            self.doc = doc_fn()
            self.plan = plan(self.doc)
            lines = summary(self.plan)
            if not has_motion(self.plan):
                lines = ["Nothing in this design moves yet. Add a dc_motor "
                         "whose shaft goes into a wheel, a fan or an arm, "
                         "a light or a distance sensor, and it runs here."] + lines
            self.what.setText("\n".join(lines))
            self.btn_play.setEnabled(has_motion(self.plan))
            self.btn_export.setEnabled(self.doc is not None)
            self.btn_physics.setEnabled(self.doc is not None)
            self.status.setText("")
            super().open_card()
            if has_motion(self.plan):
                self.play()

        def play(self):
            if self.doc is None:
                return
            if self.sim is None:
                self.sim = Simulation(self.doc, self.plan)
                self.sim.rpm = float(self.speed.value())
                if gui:
                    try:
                        self.sim.deco = _Decorations(self.plan)
                    except Exception as exc:              # noqa: BLE001
                        _log("glows: %r" % (exc,))
            self._last = None
            self.timer.start()
            self.btn_play.setText("Pause")

        def pause(self):
            self.timer.stop()
            self.btn_play.setText("Play")

        def toggle(self):
            (self.pause if self.timer.isActive() else self.play)()

        def stop(self):
            self.timer.stop()
            if self.sim is not None:
                self.sim.stop()
                self.sim = None
            self.btn_play.setText("Play")

        def _tick(self):
            import time
            now = time.monotonic()
            dt = 0.033 if self._last is None else min(0.1, now - self._last)
            self._last = now
            if self.sim is None or running(self.doc) is not self.sim:
                self.stop()                    # put back by a build or save
                return
            try:
                self.sim.step(dt)
            except Exception as exc:                      # noqa: BLE001
                _log("step: %r" % (exc,))
                self.stop()

        def _on_speed(self, v):
            self.rpm.setText("%d rpm" % v)
            if self.sim is not None:
                self.sim.rpm = float(v)

        def export(self, folder=None):
            if self.doc is None:
                return None
            if folder is None:
                start = default_folder(self.doc)
                os.makedirs(os.path.dirname(start), exist_ok=True)
                folder = QtWidgets.QFileDialog.getExistingDirectory(
                    self, "Export for simulators: choose a folder",
                    os.path.dirname(start))
                if not folder:
                    return None
                folder = os.path.join(folder, os.path.basename(start))
            was = self.timer.isActive()
            self.stop()
            res = export_urdf(self.doc, folder, self.plan, rpm=float(self.speed.value()))
            url = QtCore.QUrl.fromLocalFile(folder).toString()
            self.status.setText('Saved <a href="%s">%s</a>: %d link(s), %d joint(s).'
                                % (url, os.path.basename(res["urdf"]),
                                   res["links"], res["joints"]))
            if was:
                self.play()
            return res

        def run_physics(self, confirm=None, launch=None):
            """Export to the default folder and open it in MuJoCo, installing
            MuJoCo first (once, after asking). confirm() -> bool and
            launch(run_py) stand in for the dialog and the viewer in tests.
            Returns the export, or None when the user says no."""
            if self.doc is None:
                return None
            launch = launch or launch_mujoco
            self.stop()
            res = export_urdf(self.doc, default_folder(self.doc), self.plan,
                              rpm=float(self.speed.value()))

            def go():
                launch(res["run"])
                url = QtCore.QUrl.fromLocalFile(os.path.dirname(res["run"])).toString()
                self.status.setText('MuJoCo is opening in its own window (<a href="%s">'
                                    'the files</a>). Drag the motor sliders under '
                                    'Control to change speed.' % url)

            if mujoco_available():
                go()
                return res
            if confirm is None:
                def confirm():
                    b = QtWidgets.QMessageBox.question(
                        self, "Run physics",
                        "Physics runs in MuJoCo, a free simulator (Apache-2.0). "
                        "Download and install it now? Once, about 30 MB.")
                    return b == QtWidgets.QMessageBox.Yes
            if not confirm():
                self.status.setText("Not installed. Export for simulators… "
                                    "saves files that run anywhere MuJoCo is.")
                return None
            self.btn_physics.setEnabled(False)
            self.status.setText("Installing MuJoCo (once, about 30 MB)…")

            class _Install(QtCore.QThread):
                done = QtCore.Signal(str)

                def run(self):
                    try:
                        ensure_mujoco()
                        self.done.emit("")
                    except Exception as exc:              # noqa: BLE001
                        _log("install: %r" % (exc,))
                        self.done.emit(str(exc) or "install failed")

            def finished(err):
                if w in _INSTALLS:
                    _INSTALLS.remove(w)
                try:
                    self.btn_physics.setEnabled(True)
                    if err:
                        self.status.setText("Could not install MuJoCo: %s" % err)
                    else:
                        go()
                except RuntimeError:                       # the card is gone
                    pass

            w = _Install()
            _INSTALLS.append(w)
            w.done.connect(finished)
            w.start()
            return res

    return _SimCard()


def view_bar_button(parent=None, gui=True):
    """The view bar's Simulate button (checkable): opens the card."""
    from . import measure, style
    style.PATHS.setdefault("circle-play", '<circle cx="12" cy="12" r="10"/>'
                           '<polygon points="10 8 16 12 10 16 10 8"/>')
    b = measure._view_button(parent, "circle-play",
                             "Simulate: see the design work, export it for "
                             "simulators", "Simulate")
    host = measure._host(parent)
    return measure._attach(b, lambda: SimulationCard(host, gui=gui))
