"""user_parts — parts the user brings: electronics and hardware that are not
Atech modules (an Arduino, a Raspberry Pi, a battery pack, a servo, a
third-party sensor board, a custom PCB).

WHERE THEY LIVE
    A folder next to Atech's library, never inside it (an update replaces the
    library; the user's parts survive it):

        <parts dir>/parts.yaml        same schema as models/presets.yaml
        <parts dir>/stl/<name>.stl    the mesh every fit and seat check uses
        <parts dir>/source/<file>     the file the user imported, kept as-is

    parts_dir() is $ATELIER_PARTS when set (the sandboxed build child gets it
    from the parent: its own home is a scratch folder), else
    <FreeCAD user data>/parts.

HOW THEY JOIN THE LIBRARY
    atech_modules.specs() merges these entries after Atech's own; an Atech name
    always wins (a user part can never shadow a real module). atech_modules
    and atech_ports both fall back to stl_path() here for a name the library
    has no mesh for. So:
      - a part whose mesh carries a real Atech 6-pin header (a custom board
        built to the Atech connector) is measured and SEATS like any module;
      - any other part is a free part: placed by hand or by the agent with
        am.load_module(doc, name, placement=...), an obstacle for check().

WHAT IS MEASURED, WHAT IS DECLARED
    dimensions_mm is measured from the mesh at import, never typed in. The
    `electrical` mapping (interface, voltage, how it is wired) and the notes
    are the user's declarations: shown to the agent as such, checked by
    nothing. Atech firmware drives none of these parts.

This module imports FreeCAD only to import and mesh a file; reading the
catalog needs PyYAML alone.
"""
import datetime
import hashlib
import os
import re
import shutil

try:
    import yaml
except ImportError:                      # FreeCAD bundles it; be explicit if not
    yaml = None

PARTS_ENV = "ATELIER_PARTS"
PARTS_FILE = "parts.yaml"
FORMAT = 1

#: Categories a user part may take. "module" is only honoured for a mesh with
#: a measurable Atech header (atech_ports.seatable decides, not this list).
CATEGORIES = ("electronics", "power", "motor", "wheel", "mechanical", "module")
INTERFACES = ("none", "power", "gpio", "analog", "pwm", "i2c", "spi", "uart",
              "usb", "other")

#: What import_part() reads. STEP/IGES are meshed at MESH_DEFLECTION.
MESH_EXTS = (".stl", ".obj", ".ply", ".off", ".amf", ".3mf")
CAD_EXTS = (".step", ".stp", ".iges", ".igs", ".brep", ".brp")
IMPORT_EXTS = CAD_EXTS + MESH_EXTS
MESH_DEFLECTION = 0.05      # mm: chord error of the STEP -> STL mesh
ANGULAR_DEFLECTION = 0.3    # rad

#: A part outside these sizes is almost always a units mistake (metres or
#: inches read as mm). Refused unless the caller passes a scale.
SANE_MM = (0.5, 2000.0)

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")


class PartError(RuntimeError):
    """A user part that cannot be read, imported or named as asked."""


# ------------------------------------------------------------- location
def parts_dir(environ=None):
    """The user parts folder (it may not exist yet), or None when neither
    $ATELIER_PARTS nor FreeCAD's user data folder is known."""
    environ = os.environ if environ is None else environ
    env = (environ.get(PARTS_ENV) or "").strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    try:
        import FreeCAD
        return os.path.join(FreeCAD.getUserAppDataDir(), "parts")
    except Exception:                                  # noqa: BLE001
        return None


def _catalog_path(d=None):
    d = d or parts_dir()
    return os.path.join(d, PARTS_FILE) if d else None


# -------------------------------------------------------------- catalog
_CACHE = {}       # path -> (mtime, size, specs)


def specs(d=None):
    """{name: entry} from parts.yaml; {} when there is none. Re-read when the
    file changes, so a part imported in Studio is seen without a restart."""
    p = _catalog_path(d)
    if not p or not os.path.isfile(p):
        return {}
    if yaml is None:
        raise PartError("PyYAML is unavailable, so %s cannot be read" % p)
    st = os.stat(p)
    hit = _CACHE.get(p)
    if hit and hit[:2] == (st.st_mtime, st.st_size):
        return hit[2]
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise PartError("%s is not a mapping of parts" % p)
    data.pop("format", None)
    out = {}
    for name, sp in data.items():
        if isinstance(sp, dict):
            sp = dict(sp)
            sp["user"] = True
            out[str(name)] = sp
    _CACHE[p] = (st.st_mtime, st.st_size, out)
    return out


def stl_path(name, d=None):
    """The mesh of user part `name`, or None when there is no such part or
    its file is missing."""
    d = d or parts_dir()
    sp = specs(d).get(name)
    if not d or sp is None:
        return None
    p = os.path.join(d, "stl", sp.get("file") or name + ".stl")
    return p if os.path.isfile(p) else None


def _write(entries, d):
    os.makedirs(d, exist_ok=True)
    clean = {}
    for name, sp in sorted(entries.items()):
        sp = {k: v for k, v in sp.items() if k != "user"}
        clean[name] = sp
    head = ("# Parts imported into Atech Atelier (not Atech modules).\n"
            "# Same schema as the Atech library's presets.yaml; dimensions_mm is\n"
            "# measured from the mesh. Edit the notes freely; re-import to change\n"
            "# the geometry.\n")
    p = _catalog_path(d)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(head)
        yaml.safe_dump({"format": FORMAT}, fh, sort_keys=False)
        if clean:
            yaml.safe_dump(clean, fh, sort_keys=False, allow_unicode=True,
                           width=78)
    os.replace(tmp, p)
    _CACHE.pop(p, None)


# --------------------------------------------------------------- naming
def slug(text):
    """A catalog name from free text: 'Arduino Nano 33' -> 'arduino_nano_33'."""
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    if s and not s[0].isalpha():
        s = "part_" + s
    return s[:48] or "part"


def check_name(name, reserved=()):
    """Raise PartError unless `name` is a usable new catalog name: lowercase
    letters, digits and _, and not a name Atech's library already uses."""
    if not NAME_RE.match(name or ""):
        raise PartError("%r is not a part name: use 2-48 lowercase letters, "
                        "digits and _, starting with a letter" % (name,))
    if name in reserved:
        raise PartError("%r is already an Atech module; pick another name"
                        % name)


def _library_names():
    try:
        import atech_modules
        return set(atech_modules.library_specs())
    except Exception:                                  # noqa: BLE001
        return set()


# --------------------------------------------------------------- import
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_mesh(path, scale=1.0):
    """A Mesh.Mesh of `path` (STEP/IGES/BREP meshed at MESH_DEFLECTION, mesh
    formats read as they are), scaled by `scale` about the origin."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMPORT_EXTS:
        raise PartError("cannot import %s files (use %s)"
                        % (ext or "extension-less", ", ".join(IMPORT_EXTS)))
    import Mesh
    if ext in CAD_EXTS:
        import Part
        import MeshPart
        shape = Part.Shape()
        shape.read(path)
        if shape.isNull() or not shape.Faces:
            raise PartError("%s holds no surfaces to mesh" % os.path.basename(path))
        mesh = MeshPart.meshFromShape(Shape=shape,
                                      LinearDeflection=MESH_DEFLECTION,
                                      AngularDeflection=ANGULAR_DEFLECTION,
                                      Relative=False)
    else:
        mesh = Mesh.Mesh(path)
    if mesh.CountFacets == 0:
        raise PartError("%s has no triangles" % os.path.basename(path))
    if scale != 1.0:
        import FreeCAD
        m = FreeCAD.Matrix()
        m.scale(scale, scale, scale)
        mesh.transform(m)
    return mesh


def import_part(src, name=None, display_name=None, category="electronics",
                description="", agent_notes="", electrical=None, licence="",
                source_url="", scale=1.0, recentre=False, replace=False,
                extra=None, d=None):
    """Import a CAD or mesh file as user part `name`. Returns its entry.

    src          STEP/IGES/BREP or STL/OBJ/PLY/3MF/AMF/OFF, in millimetres
                 unless `scale` says otherwise (25.4 for inches, 1000 for m).
    category     one of CATEGORIES (a mesh with an Atech header seats anyway).
    electrical   {"interface": one of INTERFACES, "voltage_v": 5,
                  "current_ma": 40, "wiring": "...", "connectors": "..."}:
                 the user's declaration, shown to the agent as one.
    recentre     move the mesh so its box sits at x, z centred on 0 and
                 y from 0 up (the way Atech meshes lie); False keeps the
                 file's own frame.
    replace      overwrite an existing user part of the same name.
    extra        more provenance to keep with the entry ({"simready": {...}}
                 from simready.py); it never replaces a measured field.
    """
    if yaml is None:
        raise PartError("PyYAML is unavailable")
    d = d or parts_dir()
    if not d:
        raise PartError("no folder for user parts (set %s)" % PARTS_ENV)
    if not os.path.isfile(src):
        raise PartError("no such file: %s" % src)
    display_name = (display_name or "").strip() or \
        os.path.splitext(os.path.basename(src))[0]
    name = name or slug(display_name)
    check_name(name, _library_names())
    if category not in CATEGORIES:
        raise PartError("category %r is not one of %s"
                        % (category, ", ".join(CATEGORIES)))
    elec = dict(electrical or {})
    iface = elec.get("interface")
    if iface is not None and iface not in INTERFACES:
        raise PartError("interface %r is not one of %s"
                        % (iface, ", ".join(INTERFACES)))
    have = dict(specs(d))
    if name in have and not replace:
        raise PartError("a part named %r already exists (replace=True "
                        "re-imports it)" % name)
    try:
        scale = float(scale)
    except (TypeError, ValueError):
        raise PartError("scale %r is not a number" % (scale,))
    if scale <= 0:
        raise PartError("scale must be positive")

    mesh = read_mesh(src, scale)
    bb = mesh.BoundBox
    size = (bb.XLength, bb.YLength, bb.ZLength)
    if max(size) > SANE_MM[1] or max(size) < SANE_MM[0]:
        raise PartError(
            "%s measures %s mm: that is not a desk-sized part. The file is "
            "probably in other units; import it again with scale=25.4 "
            "(inches) or scale=1000 (metres)"
            % (os.path.basename(src), " x ".join("%.3g" % v for v in size)))
    if recentre:
        mesh.translate(-(bb.XMin + bb.XMax) / 2.0, -bb.YMin,
                       -(bb.ZMin + bb.ZMax) / 2.0)
        bb = mesh.BoundBox
    if not mesh.isSolid():
        note = "the mesh is not closed: overlap checks treat it as a shell"
    else:
        note = None

    os.makedirs(os.path.join(d, "stl"), exist_ok=True)
    os.makedirs(os.path.join(d, "source"), exist_ok=True)
    stl = os.path.join(d, "stl", name + ".stl")
    mesh.write(stl)
    kept = os.path.join(d, "source", name + os.path.splitext(src)[1].lower())
    if os.path.realpath(src) != os.path.realpath(kept):
        shutil.copyfile(src, kept)

    entry = {
        "display_name": display_name,
        "category": category,
        "description": (description or "").strip()
        or "%s, imported by the user (not an Atech module)." % display_name,
        "file": name + ".stl",
        "dimensions_mm": {"x": round(bb.XLength, 2), "y": round(bb.YLength, 2),
                          "z": round(bb.ZLength, 2)},
        "source": {
            "file": os.path.basename(src),
            "kept_as": os.path.relpath(kept, d),
            "sha256": _sha256(src),
            "scale": scale,
            "recentred": bool(recentre),
            "imported": datetime.date.today().isoformat(),
        },
    }
    if source_url:
        entry["source"]["url"] = source_url
    if licence:
        entry["licence"] = licence
    if elec:
        entry["electrical"] = elec
    if note:
        entry["mesh_note"] = note
    if agent_notes:
        entry["agent_notes"] = agent_notes.strip() + "\n"
    for k, v in (extra or {}).items():
        entry.setdefault(k, v)
    have[name] = entry
    _write(have, d)
    return specs(d)[name]


def remove_part(name, d=None):
    """Delete user part `name`: its catalog entry, mesh and kept source."""
    d = d or parts_dir()
    have = dict(specs(d))
    sp = have.pop(name, None)
    if sp is None:
        raise PartError("no user part named %r" % name)
    for rel in (os.path.join("stl", sp.get("file") or name + ".stl"),
                (sp.get("source") or {}).get("kept_as")):
        if rel:
            p = os.path.join(d, rel)
            if os.path.isfile(p):
                os.remove(p)
    _write(have, d)


def electrical_line(sp):
    """One plain line of what the user declared about a part's wiring, or ''."""
    e = (sp or {}).get("electrical") or {}
    bits = []
    if e.get("interface"):
        bits.append(str(e["interface"]))
    if e.get("voltage_v") is not None:
        bits.append("%sV" % e["voltage_v"])
    if e.get("current_ma") is not None:
        bits.append("%s mA" % e["current_ma"])
    for k in ("connectors", "wiring"):
        if e.get(k):
            bits.append(str(e[k]).strip())
    return "; ".join(bits)
