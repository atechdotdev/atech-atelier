"""board_look - the Atech board and modules in the 3D view as studio.atech.dev
draws them: the real models (atech-module-renders GLBs) with their own
materials - black shells, navy PCBs, gold pins, clear lids, lit LEDs, the
"Atech" screen - instead of single-colour STL blocks.

DISPLAY ONLY. Every board and module object keeps its STL mesh: check(),
the fit tests, export and the agent all measure that mesh, exactly as
before. Inside the object's own scene graph (so the picture moves with its
placement) this module:
  * puts an INVISIBLE draw style first in the mesh's "Shaded" branch: the
    mesh is not drawn but is still ray-picked, so a click selects the
    object exactly as before (MEASURED: hiding it with Transparency 100
    instead made clicks fall through to the board, and that property is
    saved with the document);
  * adds the GLB's coloured scene after it, unpickable, so every pick goes
    to the mesh FreeCAD knows how to report. FreeCAD's selection highlight
    still shows: it colours the object's whole subtree, the look included
    (MEASURED: a selected module glows selection green).
Both are scene-graph nodes only: nothing is written to the document, and
the look is re-applied whenever a document opens.

FRAMES. The GLBs are in metres, +y up, footprint centre at the origin (the
renders' README). Each library STL is the same CAD in millimetres, +y up,
shifted by a pure translation, OFFSETS_MM. Every module follows one rule:
the GLB origin (its connector, on the cell centre) lands at x = 10 mm per
port + 0.15, y = -2.54, z = 10.0; a table entry that breaks it is a red
flag (tests/test_board_look.py).
  * Every module but usbc comes from the atech-module-simready dataset
    (models/SIMREADY.json): projects/import_simready.py writes its STL from
    the dataset's meshes WITH this rule, and its GLB is the renders v1.7
    file the dataset was built from (sha256 checked), so GLB and STL are
    the same triangles and the rule holds exactly.
  * The four DERIVED modules (pir, scd40_air_quality, robot_arm,
    stepper_motor: no Atech CAD exists) have no renders GLB; the import
    writes one from the same dataset meshes.
  * usbc is not in the dataset: its STL and GLB are still the v1.5 pair,
    MEASURED 2026-10-20 (median nearest-vertex 0.03-0.12 mm), z = 9.875.
The board's offset is the one atech_ports measures from the same GLB
(measure_board()["offset_glb_to_stl"]), so board and housings agree.

COLOUR. glTF colours are linear; Coin's are display (sRGB) values, so each
is converted. PBR has no Coin equivalent: metallic surfaces get a specular
of their own colour, rough ones a dull one; transmission/BLEND becomes
Coin transparency; emissive (LEDs, the screen) is emissiveColor, so they
read lit whatever the scene lighting.

Setting: BaseApp/Preferences/Mod/AcadAgent/StudioLook (default on).
"""
import json
import os
import struct

import numpy as np

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/AcadAgent"
SETTING = "StudioLook"
GLB_TAG = "atech_board_look"         # name of the node we add (and find again)
HIDE_TAG = "atech_board_look_hide"   # the draw style that hides the mesh

#: presets.yaml name -> GLB file (the atech.dev slug, as studio's
#: hw_models.MODULE_SLUG).
SLUG = {
    "motherboard_14_port": "frame-2",
    "button": "button", "light": "led-grid", "usbc": "usb-c",
    "screen": "screen", "speaker": "speaker", "dc_motor": "dc-motor",
    "orientation": "orientation-sensor", "temp_humidity": "temp-sensor",
    "distance_sensor": "distance-sensor", "knob": "knob",
    "microphone": "microphone",
    # derived (import_simready.py writes these GLBs; no Atech CAD exists)
    "pir": "pir", "scd40_air_quality": "scd40-air-quality",
    "robot_arm": "robot-arm", "stepper_motor": "stepper-motor",
}
#: GLB frame -> STL frame, mm (see the module docstring). The board's comes
#: from atech_ports.measure_board() at run time.
_ONE, _TWO = (10.15, -2.54, 10.0), (20.15, -2.54, 10.0)
OFFSETS_MM = {
    "button": _ONE, "light": _ONE, "usbc": (10.15, -2.54, 9.875),
    "screen": _TWO, "speaker": _TWO, "dc_motor": _ONE, "orientation": _ONE,
    "temp_humidity": _ONE, "distance_sensor": _ONE, "knob": _TWO,
    "microphone": _TWO, "pir": _ONE, "scd40_air_quality": _ONE,
    "robot_arm": _TWO, "stepper_motor": _TWO,
}
#: Board materials not drawn: under the central cover, invisible from
#: outside (atech_ports.HIDDEN_MATERIALS, measured by ray casting there).
BOARD_HIDDEN = ("grey", "satin")

_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16,
       5125: np.uint32, 5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


# ------------------------------------------------------------------ files
def glb_dir():
    """models/glb of this installation's module library, or None."""
    try:
        from . import projects
        if projects._mod() is None:
            return None
        import atech_ports
        d = getattr(atech_ports, "MODELS_DIR", None)
        return os.path.join(d, "glb") if d else None
    except Exception:                                  # noqa: BLE001
        return None


def glb_path(module, base=None):
    slug = SLUG.get(module)
    base = base or glb_dir()
    if not slug or not base:
        return None
    p = os.path.join(base, slug + ".glb")
    return p if os.path.isfile(p) else None


# ------------------------------------------------------------------ reader
def read_glb(path):
    """The GLB as drawing data: {"materials": [glTF material dicts],
    "images": {index: bytes}, "prims": [(material index, positions (n,3)
    float mm in the GLB frame, triangles (m,3) int, uv (n,2) or None)]}.
    Supports what the renders use: KHR_mesh_quantization (normalized
    integer attributes) and node transforms; anything else that is
    REQUIRED is refused."""
    with open(path, "rb") as fh:
        b = fh.read()
    magic, _ver, length = struct.unpack("<III", b[:12])
    if magic != 0x46546C67:
        raise ValueError("%s is not a GLB" % path)
    off, js, binc = 12, None, b""
    while off < length:
        cl, ct = struct.unpack("<II", b[off:off + 8])
        chunk = b[off + 8:off + 8 + cl]
        if ct == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif ct == 0x004E4942:
            binc = chunk
        off += 8 + cl
    unknown = set(js.get("extensionsRequired") or []) - {"KHR_mesh_quantization"}
    if unknown:
        raise ValueError("GLB needs %s (use the glb_plain files)" % sorted(unknown))

    def view(i):
        bv = js["bufferViews"][i]
        s = bv.get("byteOffset", 0)
        return binc[s:s + bv["byteLength"]], bv.get("byteStride", 0)

    def acc(i):
        a = js["accessors"][i]
        data, stride = view(a["bufferView"])
        dt, n = _CT[a["componentType"]], _NC[a["type"]]
        cnt, start = a["count"], a.get("byteOffset", 0)
        isz = np.dtype(dt).itemsize * n
        if stride and stride != isz:
            raw = np.frombuffer(data, np.uint8, count=stride * cnt,
                                offset=start).reshape(cnt, stride)[:, :isz]
            arr = np.frombuffer(raw.tobytes(), dt).reshape(cnt, n)
        else:
            arr = np.frombuffer(data, dt, count=cnt * n, offset=start).reshape(cnt, n)
        arr = arr.astype(np.float64)
        if a.get("normalized"):
            arr = np.maximum(arr / float(np.iinfo(dt).max), -1.0)
        return arr

    def node_mat(n):
        if "matrix" in n:
            return np.array(n["matrix"], float).reshape(4, 4).T
        x, y, z, w = n.get("rotation", [0, 0, 0, 1])
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M = np.eye(4)
        M[:3, :3] = R @ np.diag(n.get("scale", [1, 1, 1]))
        M[:3, 3] = n.get("translation", [0, 0, 0])
        return M

    prims = []

    def walk(ni, parent):
        n = js["nodes"][ni]
        M = parent @ node_mat(n)
        if "mesh" in n:
            for pr in js["meshes"][n["mesh"]]["primitives"]:
                if pr.get("mode", 4) != 4:
                    continue
                at = pr["attributes"]
                pos = acc(at["POSITION"])
                pos = (pos @ M[:3, :3].T + M[:3, 3]) * 1000.0
                idx = (acc(pr["indices"]).ravel().astype(np.int64)
                       if "indices" in pr else np.arange(len(pos)))
                uv = acc(at["TEXCOORD_0"]) if "TEXCOORD_0" in at else None
                prims.append((pr.get("material", -1), pos, idx.reshape(-1, 3), uv))
        for c in n.get("children", []):
            walk(c, M)

    scene = js["scenes"][js.get("scene", 0)]
    for ni in scene["nodes"]:
        walk(ni, np.eye(4))
    images = {}
    for i, im in enumerate(js.get("images") or []):
        if "bufferView" in im:
            images[i] = view(im["bufferView"])[0]
    return {"materials": js.get("materials") or [], "images": images,
            "textures": js.get("textures") or [], "prims": prims}


# ------------------------------------------------------------------ colour
def srgb(c):
    """One linear colour channel -> display value."""
    c = max(0.0, min(1.0, float(c)))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def coin_material(m):
    """A glTF material as Coin values: {diffuse, emissive, specular,
    shininess, transparency, texture (image index or None)}."""
    pb = m.get("pbrMetallicRoughness") or {}
    base = (pb.get("baseColorFactor") or [1, 1, 1, 1])
    rgb = tuple(srgb(c) for c in base[:3])
    alpha = float(base[3]) if len(base) > 3 else 1.0
    ext = m.get("extensions") or {}
    metal = float(pb.get("metallicFactor", 1.0) or 0.0)
    rough = float(pb.get("roughnessFactor", 1.0) if pb.get("roughnessFactor") is not None else 1.0)
    em = m.get("emissiveFactor") or [0, 0, 0]
    # The screens' art is an EMISSIVE texture (a lit display) over a black
    # base; prefer it. KHR_texture_transform carries the quantized UVs'
    # scale (MEASURED: 16.0037 on screen_art), so it is kept with the index.
    tex, xform = None, None
    for ref in (m.get("emissiveTexture"), pb.get("baseColorTexture")):
        if ref:
            tex = ref.get("index")
            xform = (ref.get("extensions") or {}).get("KHR_texture_transform")
            break
    transparency = 0.0
    if "KHR_materials_transmission" in ext:
        transparency = 0.6
    elif m.get("alphaMode") == "BLEND":
        transparency = 1.0 - alpha
    if "KHR_materials_unlit" in ext:              # board silkscreen: flat
        return {"diffuse": (0, 0, 0), "emissive": rgb, "specular": (0, 0, 0),
                "shininess": 0.0, "transparency": 0.0, "texture": None}
    if tex is not None:
        # Self-lit: Coin MODULATEs the texture by the lit colour, so a white
        # emissive and no diffuse shows the art at its own colours.
        return {"diffuse": (0, 0, 0), "emissive": (1, 1, 1), "specular": (0, 0, 0),
                "shininess": 0.0, "transparency": 0.0, "texture": tex,
                "uv_transform": xform}
    # Black plastic reads as a hole under Coin's one headlight; studio's
    # environment light shows it charcoal (its sprites, rendered from these
    # GLBs: #3a3a3a). Lift the floor to that.
    diffuse = tuple(max(c, 0.20) for c in rgb)
    spec = tuple(0.15 + 0.6 * metal * c for c in rgb) if metal > 0.3 else \
        (0.25 * (1 - rough),) * 3
    return {"diffuse": diffuse, "emissive": tuple(srgb(c) for c in em[:3]),
            "specular": spec, "shininess": max(0.05, 1.0 - rough),
            "transparency": transparency, "texture": None, "uv_transform": None}


# ------------------------------------------------------------------ scene
# NOTHING Coin is shared or cached. Only the decoded drawing data is cached
# (_DATA: plain lists and the texture's PNG bytes); every object gets its
# own new scene, textures included, which lives and dies with that object's
# view provider. An earlier version cached ONE scene per part and hung it
# under every object in every document; closing several documents at once
# then crashed the app (SIGSEGV on Close All / quit with 2+ unsaved
# documents, reported 2026-10-20), the shared SoTexture2 outliving the GL
# contexts that had used it.
_DATA = {}


def _clean(pos, tri):
    """Drop zero-area triangles (the quantized export has many)."""
    a = pos[tri[:, 1]] - pos[tri[:, 0]]
    b = pos[tri[:, 2]] - pos[tri[:, 0]]
    keep = np.linalg.norm(np.cross(a, b), axis=1) > 1e-9
    return tri[keep]


def prepare(data, offset, hidden=()):
    """`data` (read_glb) as plain drawing data, no Coin: {"offset": (x, y,
    z), "parts": [{"look": coin_material, "points": [[x, y, z], ...],
    "index": [i, j, k, -1, ...], "uv": [[u, v], ...] or None, "png": bytes
    or None}]}. This is what is cached; scenes are built from it."""
    parts = []
    mats = data["materials"]
    for mi, pos, tri, uv in data["prims"]:
        m = mats[mi] if 0 <= mi < len(mats) else {}
        if m.get("name") in hidden:
            continue
        tri = _clean(pos, tri)
        if not len(tri):
            continue
        look = coin_material(m)
        png = _texture_bytes(data, look["texture"]) if uv is not None else None
        uvt = None
        if png is not None:
            uvt = [[float(u), 1.0 - float(v)]
                   for u, v in uv_transformed(uv, look.get("uv_transform"))]
        idx = np.hstack([tri, -np.ones((len(tri), 1), np.int64)]).ravel()
        parts.append({"look": look, "points": pos.astype(float).tolist(),
                      "index": idx.tolist(), "uv": uvt, "png": png})
    return {"offset": tuple(float(v) for v in offset), "parts": parts}


def build_scene(prep):
    """A NEW Coin SoSeparator drawing `prep` (prepare()). Never shared."""
    from pivy import coin
    root = coin.SoSeparator()
    root.setName(GLB_TAG)
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    root.addChild(pick)
    # The mesh's mode switch and its branches are SoGroups, not separators,
    # so the INVISIBLE style that hides the mesh is still in force here
    # (MEASURED: without this the whole object vanished). Set our own.
    style = coin.SoDrawStyle()
    style.style = coin.SoDrawStyle.FILLED
    root.addChild(style)
    hints = coin.SoShapeHints()
    hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
    hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
    hints.creaseAngle = 0.6
    root.addChild(hints)
    tr = coin.SoTranslation()
    tr.translation.setValue(*prep["offset"])
    root.addChild(tr)
    for part in prep["parts"]:
        look = part["look"]
        sep = coin.SoSeparator()
        cm = coin.SoMaterial()
        cm.diffuseColor.setValue(*look["diffuse"])
        cm.emissiveColor.setValue(*look["emissive"])
        cm.specularColor.setValue(*look["specular"])
        cm.shininess.setValue(look["shininess"])
        cm.transparency.setValue(look["transparency"])
        sep.addChild(cm)
        if part["png"] is not None and part["uv"]:
            t2 = _texture_node(part["png"])
            if t2 is not None:
                sep.addChild(t2)
                tc = coin.SoTextureCoordinate2()
                tc.point.setValues(0, len(part["uv"]), part["uv"])
                sep.addChild(tc)
        co = coin.SoCoordinate3()
        co.point.setValues(0, len(part["points"]), part["points"])
        sep.addChild(co)
        fs = coin.SoIndexedFaceSet()
        fs.coordIndex.setValues(0, len(part["index"]), part["index"])
        sep.addChild(fs)
        root.addChild(sep)
    return root


def uv_transformed(uv, xf):
    """KHR_texture_transform applied to (n,2) UVs: scale, then rotate,
    then offset (the extension's order)."""
    uv = np.asarray(uv, float)
    if not xf:
        return uv
    sx, sy = (xf.get("scale") or [1, 1])[:2]
    r = float(xf.get("rotation") or 0.0)
    ox, oy = (xf.get("offset") or [0, 0])[:2]
    u, v = uv[:, 0] * sx, uv[:, 1] * sy
    c, s_ = np.cos(r), np.sin(r)
    return np.stack([c * u + s_ * v + ox, -s_ * u + c * v + oy], axis=1)


def _texture_bytes(data, tex):
    if tex is None:
        return None
    try:
        src = data["textures"][tex].get("source")
        return data["images"].get(src)
    except (IndexError, KeyError, AttributeError):
        return None


def _texture_node(png):
    """SoTexture2 from PNG/JPEG bytes (decoded by Qt), or None."""
    try:
        from pivy import coin
        from PySide6 import QtGui
        img = QtGui.QImage.fromData(png)
        if img.isNull():
            return None
        img = img.convertToFormat(QtGui.QImage.Format_RGBA8888).mirrored(False, True)
        w, h = img.width(), img.height()
        raw = bytes(img.constBits())[:w * h * 4]
        t = coin.SoTexture2()
        t.image.setValue(coin.SbVec2s(w, h), 4, raw)
        t.model = coin.SoTexture2.MODULATE
        return t
    except Exception:                                  # noqa: BLE001
        return None


def board_offset():
    import atech_ports
    off = np.asarray(atech_ports.measure_board()["offset_glb_to_stl"], float).ravel()
    return tuple(off[:3])


def prepared(module):
    """The cached drawing data (prepare()) of library part `module`, or
    None when it has no GLB or the GLB cannot be read."""
    if module in _DATA:
        return _DATA[module]
    path = glb_path(module)
    prep = None
    if path:
        try:
            data = read_glb(path)
            if module == "motherboard_14_port":
                prep = prepare(data, board_offset(), BOARD_HIDDEN)
            elif module in OFFSETS_MM:
                prep = prepare(data, OFFSETS_MM[module])
        except Exception as exc:                       # noqa: BLE001
            _log("look for %s: %r" % (module, exc))
            prep = None
    _DATA[module] = prep
    return prep


def scene_for(module):
    """A NEW scene of library part `module` (one per object), or None."""
    prep = prepared(module)
    return build_scene(prep) if prep is not None else None


# ------------------------------------------------------------------ attach
def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[board_look] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def enabled():
    try:
        import FreeCAD
        return FreeCAD.ParamGet(PARAM_PATH).GetBool(SETTING, True)
    except Exception:                                  # noqa: BLE001
        return True


def module_of(obj):
    """The library part an object draws, or None: the board (AtechRole
    "board") or a module/part (AtechModule)."""
    if getattr(obj, "AtechRole", None) == "board":
        return "motherboard_14_port"
    mod = getattr(obj, "AtechModule", None)
    return mod if mod in SLUG else None


def _ours(root):
    if root is None:
        return -1
    for i in range(root.getNumChildren()):
        c = root.getChild(i)
        if c.getName() == GLB_TAG:
            return i
    return -1


def _shaded_group(root):
    """The mesh's "Shaded" branch: child 0 of its display-mode switch."""
    from pivy import coin
    for i in range(root.getNumChildren()):
        c = root.getChild(i)
        if c.isOfType(coin.SoSwitch.getClassTypeId()) and c.getNumChildren():
            return c.getChild(0)
    return None


def _hidden(group):
    if group is None:
        return -1
    for i in range(group.getNumChildren()):
        if group.getChild(i).getName() == HIDE_TAG:
            return i
    return -1


def attach(obj):
    """Draw obj with its studio look. True when the look is on it."""
    from pivy import coin
    mod = module_of(obj)
    vo = getattr(obj, "ViewObject", None)
    if mod is None or vo is None:
        return False
    root = vo.RootNode
    shaded = _shaded_group(root)
    if shaded is None:
        return False
    if _ours(shaded) >= 0:
        return True
    node = scene_for(mod)           # this object's own scene (never shared)
    if node is None:
        return False
    if _hidden(shaded) < 0:
        hide = coin.SoDrawStyle()
        hide.setName(HIDE_TAG)
        hide.style = coin.SoDrawStyle.INVISIBLE
        shaded.insertChild(hide, 0)
    # Inside the Shaded branch, after the hidden mesh: the look follows the
    # display mode. Wireframe / Flat Lines / Points show FreeCAD's own
    # drawing of the mesh, like every other object (2026-10-26: hung under
    # RootNode, the board stayed solid in a wireframe view).
    shaded.addChild(node)
    return True


def detach(obj):
    vo = getattr(obj, "ViewObject", None)
    if vo is None:
        return
    shaded = _shaded_group(vo.RootNode)
    if shaded is None:
        return
    i = _ours(shaded)
    if i >= 0:
        shaded.removeChild(i)
    j = _hidden(shaded)
    if j >= 0:
        shaded.removeChild(j)


def apply(doc=None):
    """Put the look on every board/module object of doc (default: every
    open document), or take it off when the setting is off. Returns how
    many objects carry it."""
    import FreeCAD
    docs = [doc] if doc is not None else list(FreeCAD.listDocuments().values())
    n = 0
    on = enabled()
    for d in docs:
        for o in d.Objects:
            if module_of(o) is None:
                continue
            if on:
                n += bool(attach(o))
            else:
                detach(o)
    return n


# ------------------------------------------------------------------ observer
class _Observer(object):
    """Re-apply when board/module objects appear or a document opens. The
    work is queued to the event loop: never inside FreeCAD's own calls."""

    def __init__(self):
        self._pending = set()

    def _queue(self, doc):
        try:
            from PySide6 import QtCore
        except ImportError:
            return
        name = doc.Name
        if name in self._pending:
            return
        self._pending.add(name)

        def run():
            # Never touch view objects while a modal is up: Close All runs
            # its "Save changes?" dialogs in a nested event loop while the
            # documents are being torn down. Try again once it is gone.
            try:
                from PySide6 import QtWidgets
                if QtWidgets.QApplication.activeModalWidget() is not None:
                    QtCore.QTimer.singleShot(250, run)
                    return
            except Exception:                          # noqa: BLE001
                pass
            self._pending.discard(name)
            try:
                import FreeCAD
                d = FreeCAD.listDocuments().get(name)
                if d is not None:
                    apply(d)
            except Exception as exc:                   # noqa: BLE001
                _log("apply: %r" % (exc,))
        QtCore.QTimer.singleShot(0, run)

    def slotCreatedObject(self, obj):                  # noqa: N802
        self._queue(obj.Document)

    def slotChangedObject(self, obj, prop):            # noqa: N802
        if prop in ("AtechModule", "AtechRole"):
            self._queue(obj.Document)

    def slotFinishRestoreDocument(self, doc):          # noqa: N802
        self._queue(doc)


_OBS = []


def install():
    """Start drawing boards and modules with the studio look (idempotent)."""
    if _OBS:
        return
    import FreeCAD
    obs = _Observer()
    FreeCAD.addDocumentObserver(obs)
    _OBS.append(obs)
    apply()


def uninstall():
    import FreeCAD
    while _OBS:
        try:
            FreeCAD.removeDocumentObserver(_OBS.pop())
        except Exception:                              # noqa: BLE001
            pass
