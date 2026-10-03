"""atech_ports — seat Atech modules on the 14-port board, port by port.

WHAT THIS IS
    A headless library that puts a module on a numbered port at its SEATED
    position (male pins inside the port's female contacts, travel stopped),
    records the prismatic slide axis on the object, and checks the result.

EVERY NUMBER IS MEASURED AT RUN TIME FROM THE SHIPPED MESHES.
    Nothing below is a typed-in port position. measure_board() and
    measure_module() derive the frames from geometry every time; the only
    constants are tolerances and the recognition envelopes used to FIND the
    connector parts (e.g. "a housing is a 2.4 x 8.5 x 15.64 mm block"), and
    each of those is itself a measurement quoted in the verification record.

    Two meshes of the same board exist and they are NOT equally good:

    * models/stl/motherboard_14_port.stl — what FreeCAD used to display
      (no longer: board_display_mesh(), R197). Its housing
      ENVELOPES are right, but its triangulation is broken: the housing
      components report hasSelfIntersections() == True and their internal
      faces are fan-triangulated across concave outlines (a vertical ray
      through a housing finds a "floor" sloping from Y 0.09 to 2.09 mm). The
      central raised frame shows the same defect. No female contact exists in
      it at all.
    * models/glb/frame-2.glb — the same board ("Frame V2.1" in its
      silkscreen), exported with materials. Its `socket` material holds 14
      clean housings with chamfered entry holes AND 84 separate female fork
      contacts. This is the geometry of record for contacts and obstacles.

    The two are tied together by measurement, not assumption: the GLB is
    moved into the STL frame by the difference of the two bounding-box
    minima, and then every one of the 14 GLB housings must coincide with an
    STL housing to within MATCH_TOL on all six bbox faces, or GeometryMismatch
    is raised. (P2: two different exports have to agree, not one file with
    itself.)

PORT NUMBERING
    Neither mesh carries a machine-readable port number. The numbers are
    read off the board's own silkscreen text geometry (silk material of
    frame-2.glb, rendered top-down: docs/verification/
    2026-09-24_atech_ports_silkscreen.png). Read that way the board is a
    portrait board seen from +Y with -Z up: 1..6 down the left (-X) column,
    9..14 down the right (+X) column, 7 top-middle, 8 bottom-middle ("USB"),
    "12 reset". That agrees with backend/motherboard/board.yaml and
    atech_docs/.../14_port.md. _number_ports() encodes exactly that reading.

THE SEAT (measured, see docs/ATECH_ASSEMBLY.md "Measured")
    Board: each port is a 15.64 x 8.50 x 2.40 mm housing standing on the PCB,
    6 fork contacts at 2.54 mm pitch inside it, solder tails leaving the
    INBOARD face -> the mouth faces OUTBOARD. Module: a 6-pin 2.54 mm header
    (15.24 x 2.54 x 2.54 mm plastic body) lying flat under the module PCB,
    pins pointing at the mating edge. The first rigid contact on the way in
    is the header body's front face against the housing's mouth face; that
    is the stop, and it is the seated position.

THE API IN ONE PAGE
    api_card() prints the board frame, the port table, the measured module
    sizes and the call signatures, generated from the measurements here.

WHAT IT DOES NOT KNOW (raises UndefinedByLibrary rather than guessing)
    Pin-1 end of the row, retention, any board other than the 14-port, any
    module whose mesh carries no header (knob, n20_wheel).
"""
import json
import math
import os
import struct

import numpy as np

import FreeCAD as App
import Mesh


# ------------------------------------------------------------ BLAS threads (R149)
# The numpy bundled with FreeCAD links a pthreads OpenBLAS that splits every
# (n, 3) @ (3, 3) product across all cores. Those products are tiny and
# check() makes hundreds of them: measured on this box (24 cores, load ~14),
# a cold check of the board + 3 modules cost 10.3 s of CPU and 0.85 s wall
# with the default thread count, 0.55 s CPU and 0.47 s wall with one thread
# (the same results, bit for bit). So the heavy entry points run with one
# BLAS thread and put the count back afterwards. Where the library or its
# symbols cannot be found (another BLAS, another OS) this does nothing.
BLAS_THREADS = 1
_BLAS = []                              # [] = not looked yet; [None] = none found


def _openblas():
    if not _BLAS:
        found = None
        try:
            import ctypes
            paths = set()
            with open("/proc/self/maps", encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    path = ln.split()[-1] if ln.strip() else ""
                    base = os.path.basename(path).lower()
                    if path.startswith("/") and "openblas" in base and ".so" in base:
                        paths.add(path)
            paths = sorted(paths)
            for path in paths:
                try:
                    lib = ctypes.CDLL(path)
                    get, put = lib.openblas_get_num_threads, lib.openblas_set_num_threads
                except (OSError, AttributeError):
                    continue
                get.restype, get.argtypes = ctypes.c_int, []
                put.restype, put.argtypes = None, [ctypes.c_int]
                found = (get, put)
                break
        except Exception:                                # noqa: BLE001
            found = None
        _BLAS.append(found)
    return _BLAS[0]


def _few_blas_threads(fn):
    """Run fn with at most BLAS_THREADS OpenBLAS threads (see above)."""
    import functools

    @functools.wraps(fn)
    def run(*a, **kw):
        lib = _openblas() if BLAS_THREADS else None
        before = None
        if lib is not None:
            try:
                n = lib[0]()
                if n > BLAS_THREADS:
                    lib[1](BLAS_THREADS)
                    before = n
            except Exception:                            # noqa: BLE001
                before = None
        try:
            return fn(*a, **kw)
        finally:
            if before is not None:
                lib[1](before)
    return run


# ------------------------------------------------------------ the library
# WHERE THE MESHES ARE. Resolved, never hardcoded to one machine (R08).
# The "models directory" is the folder holding presets.yaml, stl/ and glb/
# (atech-artifacts/models in the source tree). Looked for, in order:
#
#   1. $ATECH_ARTIFACTS — an atech-artifacts checkout (…/models) or a models
#      directory itself. When set it is the ONLY place looked at: an explicit
#      override that is wrong must fail, not quietly fall through to some
#      other copy of the library.
#   2. The installed bundle (R07): this file sits in
#      usr/Mod/AcadAgent/projects/, the meshes in usr/Mod/AcadAgent/data/
#      (either data/ itself or data/models/).
#   3. A development checkout: <repo>/projects/ here, with atech-artifacts
#      checked out next to the repo's parent (…/atech/github/Acad and
#      …/atech/atech-artifacts).
#
# Nothing found -> MODELS_DIR is None and every call that needs a mesh raises
# LibraryMissing carrying MISSING_LIBRARY, the sentence the UI shows.
LIBRARY_ENV = "ATECH_ARTIFACTS"
LIBRARY_MARKER = "presets.yaml"
MISSING_LIBRARY = ("Atech modules are missing from this installation. "
                   "Reinstall Atech Atelier.")


def library_candidates(environ=None, here=None):
    """Candidate models directories, in lookup order (see above)."""
    environ = os.environ if environ is None else environ
    env = (environ.get(LIBRARY_ENV) or "").strip()
    if env:
        env = os.path.abspath(os.path.expanduser(env))
        return [os.path.join(env, "models"), env]
    heres = [here] if here else []
    if not heres:
        for h in (os.path.dirname(os.path.abspath(__file__)),
                  os.path.dirname(os.path.realpath(__file__))):
            if h not in heres:
                heres.append(h)
    out = []
    for h in heres:
        for rel in (("..", "data", "models"), ("..", "data"),
                    ("..", "..", "..", "atech-artifacts", "models")):
            c = os.path.normpath(os.path.join(h, *rel))
            if c not in out:
                out.append(c)
    return out


def library_dir(environ=None, here=None):
    """The models directory, or None when this installation has none."""
    for c in library_candidates(environ, here):
        if os.path.isfile(os.path.join(c, LIBRARY_MARKER)):
            return c
    return None


MODELS_DIR = library_dir()
STL_DIR = os.path.join(MODELS_DIR, "stl") if MODELS_DIR else None
BOARD_STL = os.path.join(STL_DIR, "motherboard_14_port.stl") if MODELS_DIR else None
BOARD_GLB = os.path.join(MODELS_DIR, "glb", "frame-2.glb") if MODELS_DIR else None
BOARD_NAME = "motherboard_14_port"


def _need_library():
    if MODELS_DIR is None:
        raise LibraryMissing(MISSING_LIBRARY)

# ------------------------------------------------------------ tolerances
# These are decisions, not measurements. Each is stated where it is used.
MATCH_TOL = 0.05      # STL housing bbox vs GLB housing bbox, every face (mm)
AXIAL_TOL = 0.05      # stop gap allowed either side of the mouth plane (mm)
ANGLE_TOL_DEG = 0.5   # module mating axis vs port insertion axis
CELL = 0.05           # raster cell for the swept-column test (mm)
SAMPLE_STEP = 0.2     # obstacle surface sampling pitch (mm)
PITCH_TOL = 0.02      # 2.54 mm pin / contact pitch
ENV_TOL = 0.1         # recognition envelope tolerance for connector parts

# Recognition envelopes (sorted bbox dims). MEASURED — see verification
# record; used only to FIND parts in a mesh, never to place anything.
HOUSING_DIMS = (2.40, 8.50, 15.64)   # board housing (STL and GLB)
CONTACT_DIMS = (1.40, 2.00, 9.90)    # GLB female fork contact incl. tail
HEADER_DIMS = (2.54, 2.54, 15.24)    # module 6-pin header body
PIN_SECTION = 0.64                   # module pin square section

PASS, FAIL, CANNOT = "PASS", "FAIL", "CANNOT DETERMINE"

# RESERVED PORTS: {port number: reason shown to the user}. EMPTY ON PURPOSE.
# backend/motherboard/board.yaml says "Ports 8 (USB-C, bottom middle) and 12
# (Reset, right column) are reserved and cannot host modules"; atech_docs
# 14_port.md says port 8 takes the USB-C module; both meshes carry full,
# identical housings on 8 and 12. docs/ATECH_ASSEMBLY.md lists this as OPEN,
# and the rule belongs to whoever owns the port map, so nothing is reserved
# until the owner decides. The decision is this one line, e.g.
#     RESERVED = {8: "USB-C", 12: "Reset"}
# pair_for() never picks a reserved port and the Modules page offers no
# module on one. seat() itself does not enforce it: the library measures
# geometry, and geometry allows both ports.
RESERVED = {}


# ---------------------------------------------------------------- errors
class AtechPortError(RuntimeError):
    """Base class. The message is for logs and tests; UIs read `info`
    (kind, module, ports, ...) to say it in their own words, so a module
    slug or an internal path never has to reach a user."""

    def __init__(self, msg="", **info):
        super().__init__(msg)
        self.info = info


class UndefinedByLibrary(AtechPortError):
    """The library (meshes, presets) does not define this. Never guessed."""


class UnknownPort(UndefinedByLibrary):
    """A port number the measured board does not have."""


class NoConnector(UndefinedByLibrary):
    """A module whose mesh carries no measurable 6-pin header."""


class LibraryMissing(UndefinedByLibrary):
    """This installation has no module library at all (see library_dir)."""


class GeometryMismatch(AtechPortError):
    """Two measurements that must agree do not."""


class PortSpecError(AtechPortError):
    """Ports given do not fit the module (count, column, alignment)."""


class PortOccupied(AtechPortError):
    pass


class PortEmpty(AtechPortError):
    pass


# ------------------------------------------------------------- small math
def _v(x):
    return np.asarray(x, dtype=float)


def _dims_match(dims, ref, tol=ENV_TOL):
    return all(abs(a - b) <= tol for a, b in zip(sorted(dims), ref))


def _bbox_dims(bb):
    return (bb.XLength, bb.YLength, bb.ZLength)


def _tris(mesh):
    pts, fac = mesh.Topology
    if not fac:
        return np.zeros((0, 3, 3))
    P = np.array([[p.x, p.y, p.z] for p in pts])
    return P[np.array(fac)]


def _ray_hits(T, origin, d):
    """Moller-Trumbore: sorted distances along unit d where the ray hits T."""
    d = _v(d)
    v0 = T[:, 0]
    e1 = T[:, 1] - v0
    e2 = T[:, 2] - v0
    p = np.cross(d, e2)
    det = (e1 * p).sum(1)
    ok = np.abs(det) > 1e-12
    v0, e1, e2, p, inv = v0[ok], e1[ok], e2[ok], p[ok], 1.0 / det[ok]
    s = _v(origin) - v0
    u = (s * p).sum(1) * inv
    q = np.cross(s, e1)
    w = (q @ d) * inv
    t = (q * e2).sum(1) * inv
    m = (u >= 0) & (w >= 0) & (u + w <= 1) & (t > 0)
    return np.unique(np.round(t[m], 5))


def _matrix(pl):
    """4x4 numpy matrix of an App.Placement."""
    m = pl.toMatrix()
    return np.array([[m.A11, m.A12, m.A13, m.A14],
                     [m.A21, m.A22, m.A23, m.A24],
                     [m.A31, m.A32, m.A33, m.A34],
                     [0, 0, 0, 1.0]])


def _xf(M, P):
    P = _v(P)
    return P @ M[:3, :3].T + M[:3, 3]


def _placement_from(R, t):
    m = App.Matrix(R[0, 0], R[0, 1], R[0, 2], t[0],
                   R[1, 0], R[1, 1], R[1, 2], t[1],
                   R[2, 0], R[2, 1], R[2, 2], t[2],
                   0, 0, 0, 1)
    return App.Placement(m)


# ------------------------------------------------------------ GLB reader
_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16,
       5125: np.uint32, 5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _glb_triangles(path):
    """{material_name: (n,3,3) triangles in mm}. glTF units are metres."""
    if not os.path.isfile(path):
        raise UndefinedByLibrary("board GLB missing: %s" % path)
    with open(path, "rb") as fh:
        b = fh.read()
    _, _, length = struct.unpack("<III", b[:12])
    off, js, binc = 12, None, None
    while off < length:
        cl, ct = struct.unpack("<II", b[off:off + 8])
        chunk = b[off + 8:off + 8 + cl]
        if ct == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        else:
            binc = chunk
        off += 8 + cl
    # KHR_mesh_quantization is implemented below (normalized integer
    # attributes + node transforms). Anything else is refused.
    unknown = set(js.get("extensionsRequired") or []) - {"KHR_mesh_quantization"}
    if unknown:
        raise UndefinedByLibrary("GLB requires extensions this reader does "
                                 "not implement: %s" % sorted(unknown))

    def acc(i):
        a = js["accessors"][i]
        bv = js["bufferViews"][a["bufferView"]]
        dt, n = _CT[a["componentType"]], _NC[a["type"]]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride, cnt = bv.get("byteStride", 0), a["count"]
        isz = np.dtype(dt).itemsize * n
        if stride and stride != isz:
            raw = np.frombuffer(binc, np.uint8, count=stride * cnt,
                                offset=start).reshape(cnt, stride)[:, :isz]
            arr = np.frombuffer(raw.tobytes(), dt).reshape(cnt, n)
        else:
            arr = np.frombuffer(binc, dt, count=cnt * n,
                                offset=start).reshape(cnt, n)
        arr = arr.astype(float)
        if a.get("normalized"):           # KHR_mesh_quantization
            arr = arr / float(np.iinfo(dt).max)
        return arr

    def node_mat(n):
        if "matrix" in n:
            return np.array(n["matrix"]).reshape(4, 4).T
        x, y, z, w = n.get("rotation", [0, 0, 0, 1])
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M = np.eye(4)
        M[:3, :3] = R @ np.diag(n.get("scale", [1, 1, 1]))
        M[:3, 3] = n.get("translation", [0, 0, 0])
        return M

    out = {}

    def walk(ni, parent):
        n = js["nodes"][ni]
        M = parent @ node_mat(n)
        if "mesh" in n:
            for pr in js["meshes"][n["mesh"]]["primitives"]:
                if pr.get("mode", 4) != 4:
                    continue
                pos = acc(pr["attributes"]["POSITION"])
                idx = (acc(pr["indices"]).ravel().astype(int)
                       if "indices" in pr else np.arange(len(pos)))
                p = pos @ M[:3, :3].T + M[:3, 3]
                name = (js["materials"][pr["material"]].get("name", "?")
                        if "material" in pr else "?")
                out.setdefault(name, []).append(p[idx].reshape(-1, 3, 3) * 1000.0)
        for c in n.get("children", []):
            walk(c, M)

    for r in js["scenes"][js.get("scene", 0)]["nodes"]:
        walk(r, np.eye(4))
    return {k: np.concatenate(v) for k, v in out.items()}


# ------------------------------------------------------------ the board
class Port(object):
    """One measured port. Coordinates are in the board STL frame (mm)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def as_dict(self):
        return dict(self.__dict__)

    def __repr__(self):
        return ("Port(%d, edge=%s, insert=%s, mouth=%.3f, row_centre=%.3f)"
                % (self.number, self.edge, tuple(self.insert_dir),
                   self.mouth, self.row_centre))


_BOARD = None


def _number_ports(housings):
    """Assign 1..14 by the silkscreen reading (see module docstring).

    housings: list of dicts with 'centre' and 'insert_dir'. The edge a port
    opens to is the side the module comes FROM, i.e. -insert_dir.
    """
    edge_of = {(1, 0): "left", (-1, 0): "right", (0, 1): "top", (0, -1): "bottom"}
    groups = {"left": [], "right": [], "top": [], "bottom": []}
    for h in housings:
        d = h["insert_dir"]
        key = (int(round(d[0])), int(round(d[2])))
        if key not in edge_of or abs(d[1]) > 1e-6:
            raise GeometryMismatch("housing at %s has insertion axis %s, which is "
                                   "not along a board edge" % (h["centre"], d))
        h["edge"] = edge_of[key]
        groups[h["edge"]].append(h)
    counts = {k: len(v) for k, v in groups.items()}
    if counts != {"left": 6, "right": 6, "top": 1, "bottom": 1}:
        raise GeometryMismatch("expected 6 left / 6 right / 1 top / 1 bottom "
                               "housings, measured %s" % counts)
    for h, n in zip(sorted(groups["left"], key=lambda h: h["centre"][2]), range(1, 7)):
        h["number"] = n
    groups["top"][0]["number"] = 7
    groups["bottom"][0]["number"] = 8
    for h, n in zip(sorted(groups["right"], key=lambda h: h["centre"][2]), range(9, 15)):
        h["number"] = n
    return housings


# ------------------------------------------------------------ board disk cache (R193)
# A cold measure_board() costs 0.7-3 s (mesh components + GLB parse), and the
# first Atech send reached it on the GUI thread (D72). The result is a pure
# function of three files: the board STL, the board GLB and THIS source file
# (tolerances, recognition envelopes and the measuring code all live here).
# So it is kept on disk keyed by the sha256 of all three: a changed mesh, a
# changed tolerance or a changed measurement re-measures, never serves a
# stale board. Stored as one .npz (allow_pickle=False: arrays plus a JSON
# blob, nothing executable). Any failure to read or write it is silent and
# falls back to measuring — the cache can make a call faster, never wrong.
#
# $ATECH_BOARD_CACHE overrides the directory; set it to "" (or "0") to turn
# the disk cache off. Default: FreeCAD's user cache path /AtechAtelier/board.
BOARD_CACHE_ENV = "ATECH_BOARD_CACHE"
BOARD_CACHE_FORMAT = 2                  # 2: + obstacle_drawn (R197)


def board_cache_dir(environ=None):
    """Directory of the board disk cache, or None when it is turned off."""
    environ = os.environ if environ is None else environ
    if BOARD_CACHE_ENV in environ:
        v = (environ.get(BOARD_CACHE_ENV) or "").strip()
        if v in ("", "0"):
            return None
        return os.path.abspath(os.path.expanduser(v))
    try:
        base = App.getUserCachePath()
    except Exception:                                    # noqa: BLE001
        base = None
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "AtechAtelier", "board")


def _sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def board_cache_key():
    """sha256 over (format, board STL, board GLB, this source file); None
    when any of them cannot be read (then nothing is cached)."""
    import hashlib
    try:
        src = os.path.abspath(__file__)
        if src.endswith((".pyc", ".pyo")):
            src = src[:-1]
        parts = ["fmt%d" % BOARD_CACHE_FORMAT]
        for p in (BOARD_STL, BOARD_GLB, src):
            parts.append("%s:%s" % (os.path.basename(p), _sha256_file(p)))
    except Exception:                                    # noqa: BLE001
        return None
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def board_cache_path(key=None):
    """File the board is cached in (None when caching is off/impossible)."""
    d = board_cache_dir()
    key = key or (board_cache_key() if d else None)
    if not d or not key:
        return None
    return os.path.join(d, "board-%s.npz" % key[:32])


_BOARD_ARRAYS = ("offset_glb_to_stl", "obstacle_tris", "obstacle_is_socket",
                 "obstacle_drawn")


def _board_to_disk(board, key):
    path = board_cache_path(key)
    if path is None:
        return None
    try:
        ports_js = {}
        for n, p in board["ports"].items():
            d = p.as_dict()
            ports_js[str(n)] = {"fields": d,
                                "tuples": sorted(k for k, v in d.items()
                                                 if isinstance(v, tuple))}
        meta = json.dumps({"key": key, "format": BOARD_CACHE_FORMAT,
                           "ports": ports_js,
                           "stl_bbox": list(board["stl_bbox"])})
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "wb") as fh:
            np.savez(fh, meta=np.frombuffer(meta.encode("utf-8"), dtype=np.uint8),
                     **{k: np.asarray(board[k]) for k in _BOARD_ARRAYS})
        os.replace(tmp, path)
        # One board per key: older entries are dead weight.
        for f in os.listdir(os.path.dirname(path)):
            q = os.path.join(os.path.dirname(path), f)
            if f.startswith("board-") and f.endswith(".npz") and q != path:
                try:
                    os.remove(q)
                except OSError:
                    pass
        return path
    except Exception:                                    # noqa: BLE001
        try:
            os.remove(tmp)
        except Exception:                                # noqa: BLE001
            pass
        return None


def _board_from_disk(key):
    path = board_cache_path(key)
    if path is None or not os.path.isfile(path):
        return None
    try:
        with np.load(path, allow_pickle=False) as z:
            meta = json.loads(bytes(z["meta"]).decode("utf-8"))
            arrs = {k: np.array(z[k]) for k in _BOARD_ARRAYS}
        if meta.get("key") != key or meta.get("format") != BOARD_CACHE_FORMAT:
            return None
        ports = {}
        for n, rec in meta["ports"].items():
            f = dict(rec["fields"])
            for k in rec["tuples"]:
                f[k] = tuple(f[k])
            ports[int(n)] = Port(**f)
        if sorted(ports) != list(range(1, 15)):
            return None
        tris = arrs["obstacle_tris"]
        if tris.ndim != 3 or tris.shape[1:] != (3, 3) or \
                arrs["obstacle_is_socket"].shape != (len(tris),) or \
                arrs["obstacle_drawn"].shape != (len(tris),):
            return None
        board = {"ports": ports, "stl_bbox": tuple(meta["stl_bbox"])}
        board.update(arrs)
        board["obstacle_is_socket"] = board["obstacle_is_socket"].astype(bool)
        board["obstacle_drawn"] = board["obstacle_drawn"].astype(bool)
        return board
    except Exception:                                    # noqa: BLE001
        return None


def measure_board(force=False):
    """Measure the 14-port board. Returns {port_number: Port}. Cached in
    memory, and on disk keyed by the meshes and this file (R193); force=True
    re-measures and rewrites the disk entry."""
    global _BOARD
    if _BOARD is not None and not force:
        return _BOARD
    _need_library()
    key = board_cache_key() if board_cache_dir() else None
    if key and not force:
        board = _board_from_disk(key)
        if board is not None:
            _BOARD = board
            return board
    board = _measure_board()
    if key:
        _board_to_disk(board, key)
    return board


@_few_blas_threads
def _measure_board():
    """The measurement itself (no cache lookup); sets _BOARD."""
    global _BOARD
    _need_library()
    if not os.path.isfile(BOARD_STL):
        raise UndefinedByLibrary("board STL missing: %s" % BOARD_STL)
    stl = Mesh.Mesh(BOARD_STL)
    stl_h = [c.BoundBox for c in stl.getSeparateComponents()
             if _dims_match(_bbox_dims(c.BoundBox), HOUSING_DIMS)]
    if len(stl_h) != 14:
        raise GeometryMismatch("STL: expected 14 housings, found %d" % len(stl_h))

    tris = _glb_triangles(BOARD_GLB)
    allp = np.concatenate([t.reshape(-1, 3) for t in tris.values()])
    sb = stl.BoundBox
    offset = np.array([sb.XMin, sb.YMin, sb.ZMin]) - allp.min(0)
    if "socket" not in tris:
        raise UndefinedByLibrary("GLB has no 'socket' material")
    sock = tris["socket"] + offset
    sock_mesh = Mesh.Mesh([[tuple(v) for v in t] for t in sock])
    housings, contacts = [], []
    for c in sock_mesh.getSeparateComponents():
        dims = _bbox_dims(c.BoundBox)
        if _dims_match(dims, HOUSING_DIMS):
            housings.append(c)
        elif _dims_match(dims, CONTACT_DIMS):
            contacts.append(c)
    if len(housings) != 14 or len(contacts) != 84:
        raise GeometryMismatch("GLB socket: expected 14 housings + 84 contacts, "
                               "found %d + %d" % (len(housings), len(contacts)))

    def bbarr(bb):
        return np.array([bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax])

    stl_arr = [bbarr(b) for b in stl_h]
    recs = []
    for h in housings:
        hb = bbarr(h.BoundBox)
        errs = [np.abs(hb - s).max() for s in stl_arr]
        k = int(np.argmin(errs))
        if errs[k] > MATCH_TOL:
            raise GeometryMismatch("GLB housing %s matches no STL housing "
                                   "(best max face error %.3f mm)" % (hb.round(2), errs[k]))
        lo, hi = hb[:3], hb[3:]
        centre = (lo + hi) / 2.0
        long_ax = 0 if (hi[0] - lo[0]) > (hi[2] - lo[2]) else 2
        short_ax = 2 - long_ax
        mine = []
        for c in contacts:
            cb = bbarr(c.BoundBox)
            cc = (cb[:3] + cb[3:]) / 2.0
            if lo[long_ax] <= cc[long_ax] <= hi[long_ax] and \
                    cb[short_ax] < hi[short_ax] and cb[short_ax + 3] > lo[short_ax]:
                mine.append(c)
        if len(mine) != 6:
            raise GeometryMismatch("housing at %s holds %d contacts, not 6"
                                   % (centre.round(2), len(mine)))
        # Tails leave the housing on the side the contacts overhang.
        c_all = np.array([bbarr(c.BoundBox) for c in mine])
        over_hi = c_all[:, short_ax + 3].max() - hi[short_ax]
        over_lo = lo[short_ax] - c_all[:, short_ax].min()
        if over_hi > 0.5 and over_lo < 0.01:
            sign = 1.0
        elif over_lo > 0.5 and over_hi < 0.01:
            sign = -1.0
        else:
            raise GeometryMismatch("cannot tell tail side of housing at %s "
                                   "(overhang +%.2f / -%.2f)" % (centre.round(2), over_hi, over_lo))
        d = np.zeros(3)
        d[short_ax] = sign                   # module travel: mouth -> tails
        recs.append({"centre": centre, "insert_dir": d, "lo": lo, "hi": hi,
                     "contacts": mine, "stl_err": errs[k], "housing": h})

    _number_ports(recs)
    up = np.array([0.0, 1.0, 0.0])
    ports = {}
    for h in recs:
        d = h["insert_dir"]
        r = np.cross(up, d)                  # row axis: module local +X maps here
        a_lo = min(h["lo"] @ d, h["hi"] @ d)
        cons = []
        for c in h["contacts"]:
            T = _tris(c)
            P = T.reshape(-1, 3)
            a = P @ d
            a0, a1 = a.min(), a.max()
            tine = P[a < a0 + 3.0]           # the fork, first 3 mm from its mouth end
            rowc = float(((P @ r).min() + (P @ r).max()) / 2.0)
            width = float((P @ r).max() - (P @ r).min())
            ylo, yhi = float(tine[:, 1].min()), float(tine[:, 1].max())
            # Fork base: first contact material along the pin centreline.
            o = r * rowc + up * ((ylo + yhi) / 2.0) + d * (a0 - 5.0)
            hitd = _ray_hits(T, o, d)
            fork = float(a0 - 5.0 + hitd[0]) if len(hitd) else None
            cons.append({"row": rowc, "width": width, "y_lo": ylo, "y_hi": yhi,
                         "a_start": float(a0), "a_end": float(a1),
                         "a_fork_base": fork})
        cons.sort(key=lambda c: c["row"])
        rows = [c["row"] for c in cons]
        pitches = np.diff(rows)
        if np.abs(pitches - 2.54).max() > PITCH_TOL:
            raise GeometryMismatch("port %d contact pitch %s != 2.54"
                                   % (h["number"], pitches.round(3)))
        hb = h["housing"].BoundBox
        region_lo = np.minimum(h["lo"], np.array([min(c.BoundBox.XMin for c in h["contacts"]),
                                                  hb.YMin, min(c.BoundBox.ZMin for c in h["contacts"])]))
        region_hi = np.maximum(h["hi"], np.array([max(c.BoundBox.XMax for c in h["contacts"]),
                                                  hb.YMax, max(c.BoundBox.ZMax for c in h["contacts"])]))
        n = h["number"]
        ports[n] = Port(
            number=n,
            edge=h["edge"],
            insert_dir=tuple(d.tolist()),
            outward=tuple((-d).tolist()),
            row_dir=tuple(r.tolist()),
            up=tuple(up.tolist()),
            mouth=float(a_lo),
            row_centre=float(np.mean(rows)),
            pcb_y=float(h["lo"][1]),
            housing_lo=tuple(h["lo"].round(4).tolist()),
            housing_hi=tuple(h["hi"].round(4).tolist()),
            socket_lo=tuple(region_lo.tolist()),
            socket_hi=tuple(region_hi.tolist()),
            contacts=cons,
            stl_glb_max_err=float(h["stl_err"]),
            sources={
                "number": "silkscreen text of frame-2.glb read top-down "
                          "(verification PNG); agrees with board.yaml, 14_port.md",
                "edge/insert_dir": "measured: side the 6 contact tails leave the "
                                   "GLB housing = inboard; module travels mouth->tails",
                "mouth": "measured: GLB housing face opposite the tails "
                         "(STL housing bbox agrees within %.3f mm)" % h["stl_err"],
                "row_centre": "measured: mean of the 6 GLB fork-contact centres",
                "pcb_y": "measured: underside of the GLB housing (sits on the PCB)",
                "contacts": "measured: GLB socket-material components, 1.40 x 2.00 x 9.90",
            },
        )
    # Obstacles: every GLB material except 'silk' (a zero-thickness print
    # layer 0.05 mm above the PCB, not a solid).
    obst = [(k, t + offset) for k, t in tris.items() if k != "silk"]
    obstacle_tris = np.concatenate([t for _, t in obst])
    board = {"ports": ports, "offset_glb_to_stl": offset,
             "obstacle_tris": obstacle_tris,
             "obstacle_is_socket": np.concatenate([np.full(len(t), k == "socket")
                                                   for k, t in obst]),
             "obstacle_drawn": _drawn_mask(obst, contacts),
             "stl_bbox": (sb.XMin, sb.YMin, sb.ZMin, sb.XMax, sb.YMax, sb.ZMax)}
    _BOARD = board
    return board


def ports():
    """{number: Port} for the 14-port board."""
    return measure_board()["ports"]


def port(n):
    p = ports().get(n)
    if p is None:
        raise UnknownPort("the measured board has ports %s; %r is not one"
                          % (sorted(ports()), n), kind="unknown_port", port=n)
    return p


# ------------------------------------------------------------ the board as drawn (R197)
# The board used to be drawn from motherboard_14_port.stl. Measured (R197,
# 2026-09-25): that STL's central raised frame is component 34 of 111, 68
# facets over x 17.24..41.94, z 18.04..102.49, y 0..3.85, self-intersecting
# — the triangulated blob in the middle of the GUI board; 135 vertical rays
# over it land anywhere from -1.60 to 3.88. The GLB holds the same frame as
# a 13460-facet cover (x 16.82..43.18, z 16.83..103.17) whose top is flat
# at 4.50 on all 135 rays. The STL is also 6.49 mm thick where presets.yaml
# says 7.0; the GLB measures 7.00. So the board is DRAWN from the GLB, from
# the triangles check() tests against (obstacle_tris), leaving out only
# what cannot be seen and would only cost time:
#   * zero-area triangles of the quantized export (72848 of 246388),
#   * the 84 female contacts, inside the housings (69022 facets),
#   * HIDDEN_MATERIALS, the parts under the central cover: of the rays
#     cast from them (17 directions, none downward into the PCB) 2-3 %
#     escape, grazing the PCB through the cover's base gaps.
# That leaves 55472 facets. Measured on the agent kit's check.png renderer:
# old STL 0.7-0.8 s, this 1.7-1.8 s, the whole GLB 3.4 s. check() still
# tests every triangle; only the picture is lighter. The board STL keeps its
# one job: the second export the GLB housings are matched against.
BOARD_DISPLAY_TAG = "frame-2.glb"
HIDDEN_MATERIALS = ("grey", "satin")


def _drawn_mask(obst, contacts):
    """Per obstacle triangle: drawn or not (see the block comment above).
    obst: [(material, triangles)] in obstacle_tris order; contacts: the
    84 contact Mesh components found in the socket material."""
    # Contact triangles are found by their vertices: a socket triangle whose
    # three corners are all contact-mesh points. Both sides go through
    # float32 (what the Mesh kernel stores) and a 10 um grid.
    def key(P):
        return np.round(np.asarray(P, np.float32).astype(float) * 100.0).astype(np.int64)
    ckeys = np.unique(key(np.concatenate([_tris(c).reshape(-1, 3) for c in contacts])), axis=0)
    out = []
    for k, t in obst:
        area2 = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
        m = area2 > 1e-12
        if k in HIDDEN_MATERIALS:
            m[:] = False
        elif k == "socket":
            hit = _rows_in(key(t.reshape(-1, 3)), ckeys).reshape(-1, 3).all(axis=1)
            m &= ~hit
        out.append(m)
    return np.concatenate(out)


def _rows_in(a, b):
    """Boolean per row of int array a: is that row one of b's rows."""
    dt = np.dtype((np.void, a.dtype.itemsize * a.shape[1]))
    av = np.ascontiguousarray(a).view(dt).ravel()
    bv = np.ascontiguousarray(b).view(dt).ravel()
    return np.isin(av, bv)


def _display_tris():
    b = measure_board()
    return b["obstacle_tris"][b["obstacle_drawn"]]


def _write_binary_stl(path, T):
    rec = np.zeros(len(T), dtype=[("n", "<f4", (3,)), ("v", "<f4", (9,)), ("a", "<u2")])
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    rec["n"] = n / np.linalg.norm(n, axis=1)[:, None]
    rec["v"] = T.reshape(-1, 9)
    with open(path, "wb") as fh:
        fh.write(b"atech_ports board display (frame-2.glb, STL frame)".ljust(80, b" "))
        fh.write(struct.pack("<I", len(T)))
        fh.write(rec.tobytes())


_BOARD_MESH = []


def _stl_via_file(T, path):
    """Mesh.Mesh of triangles T, written to `path` as binary STL first (the
    C++ reader takes 0.06 s for the board; Mesh.Mesh(list) takes 0.6 s and
    drops facets on its own)."""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        _write_binary_stl(tmp, T)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return Mesh.Mesh(path)


def board_display_mesh():
    """A new Mesh.Mesh of the board as it is drawn: the GLB board in the
    STL frame (see the block comment above). Built once per process; the
    file it is read from is kept next to the board cache entry."""
    if not _BOARD_MESH:
        import tempfile
        key = board_cache_key() if board_cache_dir() else None
        path = board_cache_path(key)
        path = path[:-len(".npz")] + "-display.stl" if path else None
        m = None
        if path and os.path.isfile(path):
            try:
                m = Mesh.Mesh(path)
            except Exception:                            # noqa: BLE001
                m = None
        if m is None or not m.CountFacets:
            T = _display_tris()
            m = None
            if path:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    m = _stl_via_file(T, path)
                    d, me = os.path.split(path)          # one file per board key
                    for f in os.listdir(d):
                        if f.startswith("board-") and f.endswith("-display.stl") \
                                and f != me:
                            try:
                                os.remove(os.path.join(d, f))
                            except OSError:
                                pass
                except Exception:                        # noqa: BLE001
                    m = None
            if m is None:
                fd, own = tempfile.mkstemp(suffix=".stl", prefix="atech_board_")
                os.close(fd)
                try:
                    m = _stl_via_file(T, own)
                finally:
                    try:
                        os.remove(own)
                    except OSError:
                        pass
        _BOARD_MESH.append(m)
    return _BOARD_MESH[0].copy()


def port_table():
    """Plain-data table (no numpy) for reports and UIs."""
    out = {}
    for n, p in sorted(ports().items()):
        d = p.as_dict()
        d["contacts"] = [{k: (round(v, 4) if isinstance(v, float) else v)
                          for k, v in c.items()} for c in d["contacts"]]
        out[n] = d
    return out


# ------------------------------------------------------------ the modules
def stl_path(name):
    _need_library()
    p = os.path.join(STL_DIR, name + ".stl")
    if not os.path.isfile(p):
        raise UndefinedByLibrary("no STL for module %r at %s" % (name, p),
                                 kind="no_mesh", module=name)
    return p


def measure_module_mesh(mesh, name="?"):
    """Find the 6-pin header(s) in a module mesh, in the MESH's own frame.

    Returns dict with local axes (r, u, d), header groups, pin data, and the
    facet index sets of pin components. Raises NoConnector if none.
    """
    comps = mesh.getSeparateComponents()
    pins, headers, body = [], [], []
    for c in comps:
        dims = sorted(_bbox_dims(c.BoundBox))
        if abs(dims[0] - PIN_SECTION) <= 0.03 and 5.0 < dims[2] < 20.0:
            pins.append(c)
        elif _dims_match(dims, HEADER_DIMS, 0.05):
            headers.append(c)
            body.append(c)
        else:
            body.append(c)
    if not headers or not pins:
        raise NoConnector("%s: mesh has %d header bodies and %d pins; no 6-pin "
                          "connector can be measured" % (name, len(headers), len(pins)))

    groups = []
    for h in headers:
        hb = h.BoundBox
        hlo = np.array([hb.XMin, hb.YMin, hb.ZMin])
        hhi = np.array([hb.XMax, hb.YMax, hb.ZMax])
        long_ax = int(np.argmax(hhi - hlo))
        mine = []
        for p in pins:
            pb = p.BoundBox
            plo = np.array([pb.XMin, pb.YMin, pb.ZMin])
            phi = np.array([pb.XMax, pb.YMax, pb.ZMax])
            if np.all(phi > hlo) and np.all(plo < hhi):
                mine.append(p)
        if len(mine) != 6:
            raise NoConnector("%s: header at %s holds %d pins, not 6"
                              % (name, hlo.round(2), len(mine)))
        groups.append({"lo": hlo, "hi": hhi, "long_ax": long_ax, "pins": mine})

    # Axes. Pin long axis = mating axis; the pin's free (mating) end is the
    # end whose section sits at header mid-height (the other end joggles up
    # to the module PCB as a solder tail). Up = away from the header.
    g0 = groups[0]
    P0 = _tris(g0["pins"][0]).reshape(-1, 3)
    span = P0.max(0) - P0.min(0)
    pin_ax = int(np.argmax(span))
    if pin_ax == g0["long_ax"]:
        raise NoConnector("%s: pins run along the header, not through it" % name)
    up_ax = 3 - pin_ax - g0["long_ax"]
    hmid = (g0["lo"] + g0["hi"]) / 2.0
    lo_end = P0[P0[:, pin_ax] < P0[:, pin_ax].min() + 0.3]
    hi_end = P0[P0[:, pin_ax] > P0[:, pin_ax].max() - 0.3]
    dlo = abs(lo_end[:, up_ax].mean() - hmid[up_ax])
    dhi = abs(hi_end[:, up_ax].mean() - hmid[up_ax])
    if min(dlo, dhi) > 0.25 or abs(dlo - dhi) < 0.1:
        raise NoConnector("%s: cannot tell the mating end of the pins "
                          "(end offsets %.2f / %.2f mm)" % (name, dlo, dhi))
    d = np.zeros(3)
    d[pin_ax] = 1.0 if dhi < dlo else -1.0
    bb = mesh.BoundBox
    mc = np.array([(bb.XMin + bb.XMax) / 2, (bb.YMin + bb.YMax) / 2, (bb.ZMin + bb.ZMax) / 2])
    u = np.zeros(3)
    u[up_ax] = 1.0 if mc[up_ax] > hmid[up_ax] else -1.0
    r = np.cross(u, d)

    out_groups = []
    for g in groups:
        corners = np.array([[x, y, z] for x in (g["lo"][0], g["hi"][0])
                            for y in (g["lo"][1], g["hi"][1])
                            for z in (g["lo"][2], g["hi"][2])])
        header_front = float((corners @ d).max())
        header_bottom = float((corners @ u).min())
        plist = []
        for p in g["pins"]:
            PP = _tris(p).reshape(-1, 3)
            a = PP @ d
            tip = float(a.max())
            near = PP[a > tip - 1.0]          # mating segment near the tip
            plist.append({"row": float(((near @ r).min() + (near @ r).max()) / 2),
                          "up": float(((near @ u).min() + (near @ u).max()) / 2),
                          "tip": tip})
        plist.sort(key=lambda q: q["row"])
        pitch = np.diff([q["row"] for q in plist])
        if np.abs(pitch - 2.54).max() > PITCH_TOL:
            raise NoConnector("%s: pin pitch %s != 2.54" % (name, pitch.round(3)))
        out_groups.append({"header_front": header_front,
                           "header_bottom": header_bottom,
                           "row_centre": float(np.mean([q["row"] for q in plist])),
                           "pins": plist})
    out_groups.sort(key=lambda g: g["row_centre"])
    fronts = [g["header_front"] for g in out_groups]
    if max(fronts) - min(fronts) > 0.01:
        raise NoConnector("%s: header fronts not coplanar %s" % (name, fronts))
    pin_tris = np.concatenate([_tris(p) for p in pins])
    body_t = [_tris(c) for c in body]
    body_tris = np.concatenate(body_t) if body else np.zeros((0, 3, 3))
    parts = [t.reshape(-1, 3) for c, t in zip(body, body_t)
             if not any(c is h for h in headers)]
    return {"r": r, "u": u, "d": d, "groups": out_groups,
            "pin_tris": pin_tris, "body_tris": body_tris,
            "faces": _faces_from_parts(parts, r, u, d)}


# ------------------------------------------------------------ working face (R165)
# Which way a module's working face points, MEASURED from its mesh, in the
# module's own axes (r along the row, u away from the board, d the slide).
# The module's CASE is its biggest body part (bbox volume). A body part that
# stands beyond the case on a side (+-r, +-d) by more than FACE_PROUD_TOL is
# a connector or shaft poking out of that side (usbc: the 10 x 3.5 mm
# receptacle shell 0.25 mm proud of the case at -d, i.e. toward the board
# edge; dc_motor: its shaft at -d). Those sides are the working faces. A
# module with nothing proud on a side works through its top, +u (light,
# button, screen, sensors). -u is the board side and is never a face.
FACE_PROUD_TOL = 0.1    # mm; the case's own faces agree to < 0.01 mm
FACE_WORDS = {("u", 1): "up", ("d", -1): "out", ("d", 1): "in",
              ("r", 1): "row+", ("r", -1): "row-"}


def _faces_from_parts(parts, r, u, d):
    """[{"axis": "d", "sign": -1, "word": "out", "local": [x, y, z],
    "proud_mm", "section_mm": (w, h)}] from the body parts' points (mesh
    frame). See the block comment above."""
    A = {"r": np.asarray(r, float), "u": np.asarray(u, float), "d": np.asarray(d, float)}
    parts = [P for P in parts if len(P)]
    if not parts:
        return []
    proj = [{k: P @ v for k, v in A.items()} for P in parts]
    vol = [np.prod([q[k].max() - q[k].min() for k in "rud"]) for q in proj]
    case = int(np.argmax(vol))
    out = []
    for ax in ("r", "d"):
        other = [k for k in "rud" if k != ax]
        for sign in (1, -1):
            reach = [float((q[ax] * sign).max()) for q in proj]
            lim = reach[case] + FACE_PROUD_TOL
            proud = [i for i in range(len(parts)) if reach[i] > lim]
            if not proud:
                continue
            sec = [max(proj[i][k].max() for i in proud) - min(proj[i][k].min() for i in proud)
                   for k in other]
            out.append({"axis": ax, "sign": sign, "word": FACE_WORDS[(ax, sign)],
                        "local": [float(x) for x in A[ax] * sign],
                        "proud_mm": round(max(reach[i] for i in proud) - reach[case], 3),
                        "section_mm": tuple(round(float(s), 3)
                                            for s in sorted(sec, reverse=True))})
    if not out:
        out.append({"axis": "u", "sign": 1, "word": "up",
                    "local": [float(x) for x in A["u"]],
                    "proud_mm": None, "section_mm": None})
    return out


def working_faces(module_name, placement=None):
    """The working face(s) of a library module, measured from its mesh
    (see FACE_PROUD_TOL). Each: {"word": "up" | "out" | "in" | "row+" |
    "row-", "local": unit vector in the mesh frame, "proud_mm",
    "section_mm"} and, when `placement` (the module's world Placement, e.g.
    obj.Placement of a seated module) is given, "world": that vector
    rotated into the world. "out" = toward the board edge the module slid
    in from (opposite its slide axis); "up" = away from the board.
    Raises what measure_module raises (no header -> NoConnector)."""
    faces = [dict(f) for f in measure_module(module_name)["faces"]]
    if placement is not None:
        R = _matrix(placement)[:3, :3]
        for f in faces:
            f["world"] = [float(x) + 0.0 for x in np.round(R @ _v(f["local"]), 9)]
    return faces


# ------------------------------------------------------------ caches (S20)
# Everything check() derives from geometry is memoised on a key that changes
# whenever that geometry or its placement changes, so a cached verdict can
# only be reused for exactly the configuration it was computed for:
#   _FEAT_CACHE  mesh signature -> measure_module_mesh() result (local frame)
#   _COL_CACHE   (mesh signature, slide axes in the module frame) -> columns
#   _HIT_CACHE   (module signature + world placement + slide travel + axes,
#                 obstacle Name + signature + world placement) -> hit record
#                 WITHOUT the label: labels are read at report time (R100)
#   _TESS_CACHE  Part obstacle signature -> world triangles
# A mesh signature is (points, facets, local bbox, area); a Part signature is
# (Name, face/edge/vertex count, volume, area, world bbox, vertex moments). Moving,
# rotating or editing anything changes its key; nothing is invalidated by
# hand. CACHE_STATS counts hits and misses so tests can prove reuse.
_MOD_CACHE = {}
_FEAT_CACHE = {}
_COL_CACHE = {}
_HIT_CACHE = {}
_TESS_CACHE = {}
_CACHE_MAX = 2048
CACHE_STATS = {"hit": 0, "miss": 0}


def clear_cache():
    """Forget every memoised measurement except the board and module specs."""
    for c in (_FEAT_CACHE, _COL_CACHE, _HIT_CACHE, _TESS_CACHE, _SOLID_INFO,
              _SHAPE_MEMO, _SIG_TRIS):
        c.clear()
    _MOD_CACHE.clear()
    CACHE_STATS.update(hit=0, miss=0)


def _remember(cache, key, value):
    if len(cache) >= _CACHE_MAX:
        cache.clear()
    cache[key] = value
    return value


def _r6(x):
    """Hashable, rounded copy of a float / array for cache keys."""
    a = np.round(np.asarray(x, dtype=float), 6) + 0.0      # + 0.0: no -0.0
    return tuple(a.ravel().tolist())


def _mesh_sig(mesh):
    """Signature of a mesh in its OWN frame (placement ignored)."""
    bb = mesh.BoundBox
    return (mesh.CountPoints, mesh.CountFacets,
            _r6([bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax]),
            round(float(mesh.Area), 4))


def _feat_for(mesh, name="?"):
    """measure_module_mesh(mesh) memoised on the mesh signature. A mesh that
    differs from the library's in any measured way gets its own entry, so
    an edited module mesh is re-measured, never served a stale answer."""
    sig = _mesh_sig(mesh)
    hit = _FEAT_CACHE.get(sig)
    if hit is not None:
        CACHE_STATS["hit"] += 1
        return sig, hit
    CACHE_STATS["miss"] += 1
    return sig, _remember(_FEAT_CACHE, sig, measure_module_mesh(mesh, name))


# ------------------------------------------------------------ module disk cache (R204)
# R193 cached the board; the first Atech send then still spent 1.2-2.1 s on
# the GUI thread in measure_module_mesh (api_card measures every library
# module; D72 residue). A module's measurement is a pure function of its STL
# and THIS source file, so it is kept next to the board entry, one file per
# module, keyed by the sha256 of both: a changed module mesh or a changed
# measuring rule re-measures. A module whose mesh has no header is cached as
# that verdict (NoConnector, message and info) and raised again, so knob and
# n20_wheel do not pay the measurement on every cold start either. Same
# switch as the board ($ATECH_BOARD_CACHE), same rule: any failure to read or
# write is silent and falls back to measuring.
MODULE_CACHE_FORMAT = 1
_MOD_ARRAYS = ("r", "u", "d", "pin_tris", "body_tris")
_SRC_SHA = []


def _source_sha():
    """sha256 of this source file, once per process (None if unreadable)."""
    if not _SRC_SHA:
        try:
            src = os.path.abspath(__file__)
            if src.endswith((".pyc", ".pyo")):
                src = src[:-1]
            _SRC_SHA.append(_sha256_file(src))
        except Exception:                                # noqa: BLE001
            _SRC_SHA.append(None)
    return _SRC_SHA[0]


def module_cache_key(name):
    """sha256 over (format, module name, its STL, this source file); None
    when either file cannot be read (then nothing is cached)."""
    import hashlib
    src = _source_sha()
    try:
        stl = _sha256_file(stl_path(name))
    except Exception:                                    # noqa: BLE001
        return None
    if not src:
        return None
    parts = ["fmt%d" % MODULE_CACHE_FORMAT, "module:%s" % name,
             "stl:%s" % stl, "src:%s" % src]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def module_cache_path(name, key=None):
    """File module `name` is cached in (None when caching is off/impossible)."""
    d = board_cache_dir()
    key = key or (module_cache_key(name) if d else None)
    if not d or not key:
        return None
    return os.path.join(d, "module-%s-%s.npz" % (name, key[:32]))


def _enc(v):
    """JSON-safe copy that keeps tuples apart from lists."""
    if isinstance(v, tuple):
        return {"__tuple__": [_enc(x) for x in v]}
    if isinstance(v, list):
        return [_enc(x) for x in v]
    if isinstance(v, dict):
        return {"__dict__": [[k, _enc(x)] for k, x in v.items()]}
    return v


def _dec(v):
    if isinstance(v, list):
        return [_dec(x) for x in v]
    if isinstance(v, dict):
        if "__tuple__" in v:
            return tuple(_dec(x) for x in v["__tuple__"])
        return {k: _dec(x) for k, x in v["__dict__"]}
    return v


def _module_to_disk(name, key, sig, feat=None, err=None):
    path = module_cache_path(name, key)
    if path is None:
        return None
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        meta = {"key": key, "format": MODULE_CACHE_FORMAT, "sig": _enc(sig)}
        arrs = {}
        if err is not None:
            meta["error"] = {"class": type(err).__name__, "msg": str(err),
                             "info": _enc(dict(getattr(err, "info", {}) or {}))}
        else:
            meta["feat"] = _enc({k: v for k, v in feat.items() if k not in _MOD_ARRAYS})
            arrs = {k: np.asarray(feat[k]) for k in _MOD_ARRAYS}
        meta = json.dumps(meta)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "wb") as fh:
            np.savez(fh, meta=np.frombuffer(meta.encode("utf-8"), dtype=np.uint8), **arrs)
        os.replace(tmp, path)
        # One entry per module: an older key is dead weight.
        pre = "module-%s-" % name
        for f in os.listdir(os.path.dirname(path)):
            q = os.path.join(os.path.dirname(path), f)
            if (f.startswith(pre) and f.endswith(".npz") and len(f) == len(pre) + 36
                    and q != path):
                try:
                    os.remove(q)
                except OSError:
                    pass
        return path
    except Exception:                                    # noqa: BLE001
        try:
            os.remove(tmp)
        except Exception:                                # noqa: BLE001
            pass
        return None


def _module_from_disk(name, key):
    """(sig, feat) or (sig, NoConnector) from the disk cache, or None."""
    path = module_cache_path(name, key)
    if path is None or not os.path.isfile(path):
        return None
    try:
        with np.load(path, allow_pickle=False) as z:
            meta = json.loads(bytes(z["meta"]).decode("utf-8"))
            if meta.get("key") != key or meta.get("format") != MODULE_CACHE_FORMAT:
                return None
            sig = _dec(meta["sig"])
            if "error" in meta:
                e = meta["error"]
                if e.get("class") != NoConnector.__name__:
                    return None
                return sig, NoConnector(e["msg"], **_dec(e["info"]))
            feat = _dec(meta["feat"])
            for k in _MOD_ARRAYS:
                feat[k] = np.array(z[k])
        for k in ("r", "u", "d"):
            if feat[k].shape != (3,):
                return None
        for k in ("pin_tris", "body_tris"):
            if feat[k].ndim != 3 or feat[k].shape[1:] != (3, 3):
                return None
        if not feat.get("groups"):
            return None
        return sig, feat
    except Exception:                                    # noqa: BLE001
        return None


def _module_entry(name):
    """(mesh signature, features) of a library module, cached by name in
    memory and on disk (R204). Raises NoConnector for a mesh without a
    header, from the disk verdict as from a fresh measurement."""
    if name not in _MOD_CACHE:
        key = module_cache_key(name) if board_cache_dir() else None
        hit = _module_from_disk(name, key) if key else None
        if hit is not None:
            sig, feat = hit
            if isinstance(feat, NoConnector):
                raise feat
            _MOD_CACHE[name] = (sig, _remember(_FEAT_CACHE, sig, feat))
        else:
            mesh = Mesh.Mesh(stl_path(name))
            try:
                _MOD_CACHE[name] = _feat_for(mesh, name)
            except NoConnector as exc:
                if key:
                    _module_to_disk(name, key, _mesh_sig(mesh), err=exc)
                raise
            if key:
                _module_to_disk(name, key, *_MOD_CACHE[name])
    return _MOD_CACHE[name]


def measure_module(name):
    return _module_entry(name)[1]


def seatable(names):
    """{name: connector count} for the modules in `names` that have a
    measurable 6-pin header. Modules without one (NoConnector) or without a
    mesh are left out; a missing library still raises LibraryMissing."""
    out = {}
    for n in names:
        try:
            out[n] = len(measure_module(n)["groups"])
        except LibraryMissing:
            raise
        except UndefinedByLibrary:
            continue
    return out


@_few_blas_threads
def warm(modules=None):
    """Pre-pay the measuring cost check() and seat() would otherwise pay on
    first use: the board (measured and as drawn), every module header, and each module's swept
    columns for its seated orientation. modules: names to warm (default:
    every STL in the library). Returns a small report; without a library it
    returns {'skipped': MISSING_LIBRARY} instead of raising."""
    import time
    t0 = time.time()
    try:
        measure_board()
    except LibraryMissing:
        return {"skipped": MISSING_LIBRARY}
    board_display_mesh()                 # the board as drawn (R197)
    if modules is None:
        modules = sorted(f[:-4] for f in os.listdir(STL_DIR)
                         if f.endswith(".stl") and f[:-4] != BOARD_NAME)
    ok, none = {}, []
    for n in modules:
        try:
            sig, feat = _module_entry(n)
        except UndefinedByLibrary:
            none.append(n)
            continue
        _columns(sig, feat, (feat["r"], feat["u"], feat["d"]))
        ok[n] = len(feat["groups"])
    return {"modules": ok, "no_connector": none,
            "seconds": round(time.time() - t0, 3)}


# ------------------------------------------------------------ placement
def _as_ports(port_arg):
    if isinstance(port_arg, (list, tuple)):
        ns = [int(x) for x in port_arg]
    else:
        ns = [int(port_arg)]
    if len(set(ns)) != len(ns):
        raise PortSpecError("port listed twice: %s" % ns, kind="port_twice",
                            ports=ns)
    return [port(n) for n in ns]


def seated_placement(module_name, port_arg, board_placement=None, feat=None):
    """World placement that seats module on port(s). Returns (Placement, info)."""
    feat = feat or measure_module(module_name)
    ps = _as_ports(port_arg)
    groups = feat["groups"]
    if len(ps) != len(groups):
        raise PortSpecError("%s has %d connector(s); %d port(s) given %s. Name "
                            "every port it plugs into." % (module_name, len(groups),
                                                          len(ps), [p.number for p in ps]),
                            kind="port_count", module=module_name,
                            connectors=len(groups), ports=[p.number for p in ps])
    d_p = _v(ps[0].insert_dir)
    for p in ps[1:]:
        if not np.allclose(_v(p.insert_dir), d_p):
            raise PortSpecError("ports %s do not share an insertion axis"
                                % [q.number for q in ps], kind="port_axis",
                                module=module_name, ports=[q.number for q in ps])
    up = _v(ps[0].up)
    r_p = np.cross(up, d_p)
    R = np.column_stack([r_p, up, d_p]) @ np.column_stack([feat["r"], feat["u"], feat["d"]]).T
    ps_sorted = sorted(ps, key=lambda p: p.row_centre)
    # translation, in port axes
    g0 = groups[0]
    # Travel stops at the FIRST mouth the (coplanar) header fronts reach.
    # For one connector that is its own mouth. For a rigid multi-connector
    # module on housings whose mouths are not coplanar (measured: ports 3,
    # 4, 5 sit 0.10 / 0.05 / 0.05 mm outboard of the others) the other
    # connector(s) stop short; check() reports that, it is not hidden here.
    first_mouth = min(p.mouth for p in ps)
    t_d = first_mouth - g0["header_front"]
    t_u = ps[0].pcb_y - g0["header_bottom"]         # header bottom onto PCB
    offs = [p.row_centre - g["row_centre"] for p, g in zip(ps_sorted, groups)]
    t_r = float(np.mean(offs))
    resid = [o - t_r for o in offs]
    # each group must land inside its port's contacts
    for p, g, e in zip(ps_sorted, groups, resid):
        slack = min(c["width"] for c in p.contacts) / 2.0 - PIN_SECTION / 2.0
        if abs(e) > slack:
            raise PortSpecError("%s connector %d misses port %d by %.3f mm along the "
                                "row (contact slack %.3f)" % (module_name, groups.index(g),
                                                             p.number, e, slack),
                                kind="port_miss", module=module_name, port=p.number,
                                miss_mm=abs(float(e)))
    t = r_p * t_r + up * t_u + d_p * t_d
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = t
    if board_placement is not None:
        M = _matrix(board_placement) @ M
    pl = _placement_from(M[:3, :3], M[:3, 3])
    return pl, {"row_residual_mm": [round(e, 4) for e in resid],
                "short_of_mouth_mm": {p.number: round(p.mouth - first_mouth, 4) for p in ps},
                "ports": [p.number for p in ps_sorted]}


# ------------------------------------------------------------ document
def board_object(doc, create=True):
    """The document's board (found by role, then by label), created when
    missing and create is True. With create, a board drawn from the old
    STL is redrawn from board_display_mesh() (R197) — same frame, so its
    Placement and every seated module stay where they are."""
    found = None
    for o in doc.Objects:
        if getattr(o, "AtechRole", None) == "board":
            found = o
            break
    if found is None:
        for o in doc.Objects:
            if o.Label == "motherboard" and o.TypeId == "Mesh::Feature":
                _tag_board(o)
                found = o
                break
    if found is not None:
        if create and getattr(found, "AtechBoardMesh", None) != BOARD_DISPLAY_TAG \
                and found.TypeId == "Mesh::Feature" and MODELS_DIR is not None:
            pl = found.Placement             # assigning .Mesh resets it
            found.Mesh = board_display_mesh()
            found.Placement = pl
            mark_board_mesh(found)
        return found
    if not create:
        return None
    _need_library()
    o = doc.addObject("Mesh::Feature", "motherboard")
    o.Mesh = board_display_mesh()
    _tag_board(o)
    mark_board_mesh(o)
    return o


def _tag_board(o):
    if "AtechRole" not in o.PropertiesList:
        o.addProperty("App::PropertyString", "AtechRole", "Atech", "board | module")
    o.AtechRole = "board"


def mark_board_mesh(o):
    """Record on o that its Mesh is board_display_mesh() (R197)."""
    if "AtechBoardMesh" not in o.PropertiesList:
        o.addProperty("App::PropertyString", "AtechBoardMesh", "Atech",
                      "what the board mesh was drawn from")
    o.AtechBoardMesh = BOARD_DISPLAY_TAG


def occupied(doc):
    """{port_number: object} for every Atech module in doc."""
    out = {}
    for o in doc.Objects:
        if getattr(o, "AtechRole", None) == "module":
            for n in o.AtechPorts:
                out[int(n)] = o
    return out


def _slide_out(feat, Mw, d_world, Bm):
    """mm to travel back along -d_world until the module (world matrix Mw)
    is entirely clear of the board (world matrix Bm)."""
    pts = _xf(Mw, np.concatenate([feat["body_tris"], feat["pin_tris"]]).reshape(-1, 3))
    board_pts = _xf(Bm, measure_board()["obstacle_tris"].reshape(-1, 3))
    return float((pts @ d_world).max() - (board_pts @ d_world).min())


@_few_blas_threads
def seat(doc, module_name, port_arg, label=None):
    """Add module_name to doc, seated on port_arg (int, or tuple for a
    multi-connector module). Returns the object.

    IDEMPOTENT: when the same module already sits on exactly those ports,
    that object is returned unchanged (nothing is added), so a script can
    run twice. A DIFFERENT module (or the same module on an overlapping but
    different set of ports) raises PortOccupied.

    The object is a Mesh::Feature: it has .Mesh, not .Shape. Use bbox(obj)
    for its world bounding box.

    Properties recorded on the object (group "Atech"):
      AtechModule, AtechPorts, AtechJoint="prismatic",
      AtechSlideAxis  — world unit vector the module TRAVELS to insert,
      AtechSlideOut   — mm to move back along -AtechSlideAxis until the
                        module is entirely clear of the board,
      AtechSeatPlacement — the seated placement (the travel limit).
    """
    b = board_object(doc)
    ps = _as_ports(port_arg)
    occ = occupied(doc)
    taken = [p.number for p in ps if p.number in occ]
    holders = {occ[n].Name: occ[n] for n in taken}
    if taken and len(holders) == 1:
        o = list(holders.values())[0]
        if (getattr(o, "AtechModule", None) == module_name
                and sorted(int(n) for n in o.AtechPorts) == sorted(p.number for p in ps)):
            return o
    if taken:
        raise PortOccupied("port(s) %s already hold %s"
                           % (taken, [occ[n].Label for n in taken]),
                           kind="occupied", ports=taken,
                           holders=[getattr(occ[n], "AtechModule", "") or occ[n].Label
                                    for n in taken])
    feat = measure_module(module_name)
    pl, info = seated_placement(module_name, port_arg, b.Placement, feat)
    o = doc.addObject("Mesh::Feature", label or "%s_p%s" % (
        module_name, "_".join(str(n) for n in info["ports"])))
    o.Mesh = Mesh.Mesh(stl_path(module_name))
    o.Placement = pl
    for typ, prop, doc_ in (
            ("App::PropertyString", "AtechRole", "board | module"),
            ("App::PropertyString", "AtechModule", "presets.yaml module name"),
            ("App::PropertyIntegerList", "AtechPorts", "ports this module occupies"),
            ("App::PropertyString", "AtechJoint", "joint type to the board"),
            ("App::PropertyVector", "AtechSlideAxis", "world insertion direction (unit)"),
            ("App::PropertyFloat", "AtechSlideOut", "travel (mm) from clear-of-board to seated"),
            ("App::PropertyPlacement", "AtechSeatPlacement", "seated placement = travel limit")):
        o.addProperty(typ, prop, "Atech", doc_)
    o.AtechRole = "module"
    o.AtechModule = module_name
    o.AtechPorts = info["ports"]
    o.AtechJoint = "prismatic"
    Bm = _matrix(b.Placement)
    d_world = Bm[:3, :3] @ _v(ps[0].insert_dir)
    o.AtechSlideAxis = App.Vector(*d_world.tolist())
    o.AtechSlideOut = _slide_out(feat, _matrix(pl), d_world, Bm)
    o.AtechSeatPlacement = pl
    doc.recompute()
    return o


def bbox(obj):
    """World bounding box (App.BoundBox, mm) of a seated module, or of any
    object with a Mesh or a Shape.

    Seated modules are Mesh::Feature objects: they have no .Shape, so
    `obj.Shape.BoundBox` raises AttributeError. A Mesh::Feature's Mesh
    carries the feature Placement, so obj.Mesh.BoundBox is already in world
    coordinates. Like every BoundBox it is a BOUND (axis-aligned), not a
    measurement of the material."""
    if hasattr(obj, "Mesh"):
        return App.BoundBox(obj.Mesh.BoundBox)
    shp = getattr(obj, "Shape", None)
    if shp is not None and not shp.isNull():
        return App.BoundBox(shp.BoundBox)
    raise TypeError("%s has neither a Mesh nor a Shape" % getattr(obj, "Label", obj))


def remove(doc, port_n):
    """Remove whatever module occupies port_n. Returns its name."""
    port(port_n)
    occ = occupied(doc)
    if port_n not in occ:
        raise PortEmpty("port %d is empty" % port_n, kind="empty", port=port_n)
    name = occ[port_n].Name
    doc.removeObject(name)
    doc.recompute()
    return name


def slide(obj, travel_out):
    """Set obj at travel_out mm back from its seat along its slide axis
    (0 = seated). For UIs animating the prismatic joint."""
    d = obj.AtechSlideAxis
    pl = App.Placement(obj.AtechSeatPlacement)
    pl.Base = pl.Base - d * float(travel_out)
    obj.Placement = pl


# ------------------------------------------------------------ checking
_BARY = {}


def _bary(k):
    """Barycentric grid (i/k, j/k), i + j <= k, in the order _sample always
    used. Built once per k (R122: the Python list comprehension was ~0.4 s
    of a cold check with a board + 3 modules)."""
    B = _BARY.get(k)
    if B is None:
        i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
        m = (i + j) <= k
        B = np.stack([i[m] / k, j[m] / k], 1)
        _BARY[k] = B
    return B


SAMPLE_BLOCK = 8      # _sample culls big triangles in blocks of 8x8 grid points


def _sample(T, step=SAMPLE_STEP, box=None):
    """Surface points of triangles T, spaced <= step.

    box: optional (lo, hi) corners. Grid blocks of a big triangle whose
    points all lie outside the box are not generated (R122): the board's PCB
    triangles span the whole board at a 0.2 mm grid, and generating them was
    most of a cold check. Every point that IS generated has exactly the
    coordinates it had before (same formula, same barycentric values), and
    every point inside the box is generated, so a caller that only cares
    about points in the box sees the same points."""
    if len(T) == 0:
        return np.zeros((0, 3))
    e = np.stack([np.linalg.norm(T[:, 1] - T[:, 0], axis=1),
                  np.linalg.norm(T[:, 2] - T[:, 1], axis=1),
                  np.linalg.norm(T[:, 0] - T[:, 2], axis=1)], 1).max(1)
    n = np.maximum(1, np.ceil(e / step)).astype(int)
    out = [T.reshape(-1, 3)]
    for k in np.unique(n):
        if k == 1:
            continue
        Tk = T[n == k]
        if box is not None and k > 2 * SAMPLE_BLOCK:
            out.append(_sample_blocks(Tk, int(k), box))
            continue
        B = _bary(int(k))
        P = (Tk[:, None, 0] * (1 - B[:, 0] - B[:, 1])[None, :, None]
             + Tk[:, None, 1] * B[None, :, 0, None]
             + Tk[:, None, 2] * B[None, :, 1, None])
        out.append(P.reshape(-1, 3))
    return np.concatenate(out)


def _sample_blocks(Tk, k, box, chunk=400000):
    """The k-grid points of triangles Tk (all with the same k), generated
    only in the SAMPLE_BLOCK x SAMPLE_BLOCK blocks of grid indices whose
    image can reach the box. A block's image is a parallelogram (the map
    from grid index to point is affine), so the bbox of its 4 corners
    bounds every point in it."""
    s = SAMPLE_BLOCK
    lo_b, hi_b = _v(box[0]), _v(box[1])
    nb = k // s + 1
    p, q = np.meshgrid(np.arange(nb), np.arange(nb), indexing="ij")
    m = (p * s + q * s) <= k
    ilo, jlo = (p[m] * s), (q[m] * s)
    ihi, jhi = np.minimum(ilo + s - 1, k), np.minimum(jlo + s - 1, k)
    ci = np.stack([ilo, ihi, ilo, ihi], 1) / k                  # (blocks, 4)
    cj = np.stack([jlo, jlo, jhi, jhi], 1) / k
    di, dj = np.meshgrid(np.arange(s), np.arange(s), indexing="ij")
    di, dj = di.ravel(), dj.ravel()
    out = []
    step_t = max(1, chunk // max(1, len(ilo)))
    for t0 in range(0, len(Tk), step_t):
        Tc = Tk[t0:t0 + step_t]
        C = (Tc[:, None, None, 0] * (1 - ci - cj)[None, :, :, None]
             + Tc[:, None, None, 1] * ci[None, :, :, None]
             + Tc[:, None, None, 2] * cj[None, :, :, None])      # (t, blocks, 4, 3)
        keep = np.all(C.max(2) >= lo_b, -1) & np.all(C.min(2) <= hi_b, -1)
        ti, bi = np.nonzero(keep)
        if not len(ti):
            continue
        I = ilo[bi][:, None] + di[None, :]
        J = jlo[bi][:, None] + dj[None, :]
        ok = (I <= ihi[bi][:, None]) & (J <= jhi[bi][:, None]) & (I + J <= k)
        tt = np.repeat(ti, len(di)).reshape(I.shape)[ok]
        b0, b1 = I[ok] / k, J[ok] / k
        V = Tc[tt]
        out.append(V[:, 0] * (1 - b0 - b1)[:, None]
                   + V[:, 1] * b0[:, None]
                   + V[:, 2] * b1[:, None])
    return np.concatenate(out) if out else np.zeros((0, 3))


def _sweep3(a, axis, op, pad):
    """op over each cell and its two neighbours along axis; cells beyond
    the edge count as pad."""
    out = a.copy()
    if a.shape[axis] < 2:
        return op(out, pad)
    lo = [slice(None)] * 2
    hi = [slice(None)] * 2
    lo[axis], hi[axis] = slice(0, -1), slice(1, None)
    lo, hi = tuple(lo), tuple(hi)
    op(out[lo], a[hi], out=out[lo])
    op(out[hi], a[lo], out=out[hi])
    edge = [slice(None)] * 2
    edge[axis] = 0
    out[tuple(edge)] = op(out[tuple(edge)], pad)
    edge[axis] = -1
    out[tuple(edge)] = op(out[tuple(edge)], pad)
    return out


class _Column(object):
    """Module silhouette on the plane normal to d, with the min/max axial
    coordinate of module surface per cell. Treats the module as FILLED
    between its first and last surface along d in each cell: conservative
    (it can FAIL a point in a hollow of the module; it cannot PASS a point
    inside its material)."""

    def __init__(self, T, e1, e2, d, base=None):
        """base: optional (column, triangles of T it was NOT built from).
        R149: the all-triangles column of a module is its body column plus
        the pins. When both share one grid (the pins lie inside the body's
        silhouette: every library module, measured), the body's raster is
        copied and only the pins are rasterised on top. Per-cell min / max
        do not depend on the order triangles arrive in, so the result is
        the same doubles as rasterising all of T."""
        self.e1, self.e2, self.d = e1, e2, d
        P = T.reshape(-1, 3)
        x, y = P @ e1, P @ e2
        self.x0, self.y0 = x.min() - 2 * CELL, y.min() - 2 * CELL
        nx = int(np.ceil((x.max() - self.x0) / CELL)) + 3
        ny = int(np.ceil((y.max() - self.y0) / CELL)) + 3
        if base is not None and base[0]._grid == (self.x0, self.y0, nx, ny):
            T = base[1]
            self.lmin, self.lmax = base[0]._raw[0].copy(), base[0]._raw[1].copy()
        else:
            self.lmin = np.full((nx, ny), np.inf)
            self.lmax = np.full((nx, ny), -np.inf)
        self._grid = (self.x0, self.y0, nx, ny)
        X = np.stack([T @ e1, T @ e2, T @ d], -1)          # (n,3,3)
        self._raster(X, nx, ny)
        self._raw = (self.lmin, self.lmax)                  # dropped by _columns
        # Lateral tolerance. A point counts as inside only if it is inside the
        # axial interval of EVERY cell in its 3x3 neighbourhood. This erodes
        # the silhouette edge AND every internal step between columns of
        # different depth — needed because a housing side face that is
        # exactly tangent to a module rail (both at 15.64 mm apart, measured)
        # otherwise lands in the rail's column and reads as 8 mm deep.
        # Effective lateral tolerance: 1-2 cells (0.05-0.10 mm).
        # R149: the 3x3 max / min is taken separably (rows, then columns;
        # cells off the grid count as empty), the same values as the 8
        # shifted copies it replaces in a quarter of the passes.
        lo_e = _sweep3(_sweep3(self.lmin, 0, np.maximum, np.inf), 1, np.maximum, np.inf)
        hi_e = _sweep3(_sweep3(self.lmax, 0, np.minimum, -np.inf), 1, np.minimum, -np.inf)
        self.lmin, self.lmax = lo_e, hi_e
        self.mask = lo_e <= hi_e
        self._reach = {}

    REACH_EPS = 1e-6      # mm, float slack of reach_box against lookup()

    def reach_box(self, s_out):
        """(lo, hi) corners, in the frame of the triangles, of a box holding
        every point lookup() can count as a seat or path hit for a slide
        travel s_out: the cells inside the mask, from the lowest lmin minus
        s_out to the highest lmax along d. None when the mask is empty.
        R149: _hits generates obstacle points only in this box (was the
        module's swept envelope plus 0.5 mm). A point outside it lands in a
        cell outside the mask or outside every cell's axial interval, so it
        can never be counted: the hits are the same numbers."""
        key = round(float(s_out), 6)
        hit = self._reach.get(key)
        if hit is not None or key in self._reach:
            return hit
        box = None
        if self.mask.any():
            ii = np.flatnonzero(self.mask.any(1))
            jj = np.flatnonzero(self.mask.any(0))
            xs = (self.x0 + ii[0] * CELL, self.x0 + (ii[-1] + 1) * CELL)
            ys = (self.y0 + jj[0] * CELL, self.y0 + (jj[-1] + 1) * CELL)
            # max(0, .): a seat hit needs only a > lmin, so a NEGATIVE travel
            # (a module moved in front of the board, or an edited
            # AtechSlideOut) must not raise the floor above the lowest lmin
            az = (float(self.lmin[self.mask].min()) - max(0.0, float(s_out)),
                  float(self.lmax[self.mask].max()))
            C = np.array([self.e1 * x + self.e2 * y + self.d * a
                          for x in xs for y in ys for a in az])
            box = (C.min(0) - self.REACH_EPS, C.max(0) + self.REACH_EPS)
        self._reach[key] = box
        return box

    # candidate cells per batch in _raster: bounds memory (~250 B / cell,
    # so ~75 MB at most)
    RASTER_BATCH = 300000

    def _raster(self, X, nx, ny):
        """Fill lmin / lmax with the axial coordinate of every triangle of X
        (n,3,3 in (e1, e2, d) coordinates) at each cell centre it covers.

        R122: vectorised form of the per-triangle loop (one Python iteration
        and one np.minimum.at per triangle, 0.8 s of a cold check). Same
        formulas, same order of operations per cell, so the same doubles;
        per-cell min / max are taken with a sort + reduceat instead of
        ufunc.at."""
        a, b, c = X[:, 0], X[:, 1], X[:, 2]
        den = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
        ok = np.abs(den) >= 1e-12
        a, b, c, den = a[ok], b[ok], c[ok], den[ok]
        if not len(den):
            return
        xs = np.stack([a[:, 0], b[:, 0], c[:, 0]], 1)
        ys = np.stack([a[:, 1], b[:, 1], c[:, 1]], 1)
        i0 = np.floor((xs.min(1) - self.x0) / CELL).astype(np.int64)
        i1 = np.ceil((xs.max(1) - self.x0) / CELL).astype(np.int64)
        j0 = np.floor((ys.min(1) - self.y0) / CELL).astype(np.int64)
        j1 = np.ceil((ys.max(1) - self.y0) / CELL).astype(np.int64)
        # R149: candidate cells by COLUMN of cells, not the whole bbox. For
        # each triangle and each cell column i, only the cells whose centre
        # lies within the triangle's y-range over the slab x = px +- m
        # (px the column's centre, m = SCAN_MARGIN), widened by m, are
        # tested - the bbox holds 2.2-2.4x the triangle's own cells on the
        # module meshes (measured). Every cell the barycentric test can
        # accept is among them (its centre lies in the triangle's y-range
        # at x = px; m = 0.5 um is ~10^9 x the rounding of these numbers),
        # and each candidate is tested with the same formulas as before,
        # so the same doubles (bit-identical to the bbox raster on every
        # seatable module, 3 axes: test_atech_round7.py).
        ni = i1 - i0 + 1
        tp = np.repeat(np.arange(len(ni)), ni)                 # (triangle, column) pairs
        ip = i0[tp] + (np.arange(int(ni.sum())) - np.repeat(np.cumsum(ni) - ni, ni))
        pxs = self.x0 + (ip + 0.5) * CELL
        sl_lo, sl_hi = pxs - self.SCAN_MARGIN, pxs + self.SCAN_MARGIN
        ylo = np.full(len(tp), np.inf)
        yhi = np.full(len(tp), -np.inf)
        for p, q in ((0, 1), (1, 2), (2, 0)):
            xa, ya, xb, yb = xs[tp, p], ys[tp, p], xs[tp, q], ys[tp, q]
            over = (np.minimum(xa, xb) <= sl_hi) & (np.maximum(xa, xb) >= sl_lo)
            dx = xb - xa
            vert = np.abs(dx) < 1e-12                  # edge along e2: its whole span
            with np.errstate(divide="ignore", invalid="ignore"):
                tl = np.clip((sl_lo - xa) / dx, 0.0, 1.0)
                tr = np.clip((sl_hi - xa) / dx, 0.0, 1.0)
            y_l = np.where(vert, ya, ya + tl * (yb - ya))
            y_r = np.where(vert, yb, ya + tr * (yb - ya))
            e_lo, e_hi = np.minimum(y_l, y_r), np.maximum(y_l, y_r)
            ylo = np.where(over, np.minimum(ylo, e_lo), ylo)
            yhi = np.where(over, np.maximum(yhi, e_hi), yhi)
        has = np.isfinite(ylo)
        jlo = np.zeros(len(tp), np.int64)
        jhi = np.full(len(tp), -1, np.int64)
        jlo[has] = np.ceil((ylo[has] - self.SCAN_MARGIN - self.y0) / CELL - 0.5).astype(np.int64)
        jhi[has] = np.floor((yhi[has] + self.SCAN_MARGIN - self.y0) / CELL - 0.5).astype(np.int64)
        jlo = np.maximum(jlo, j0[tp])
        jhi = np.minimum(jhi, j1[tp])
        cnt = np.maximum(jhi - jlo + 1, 0)
        ends = np.cumsum(cnt)
        lo_t = 0
        while lo_t < len(cnt):
            # pairs [lo_t, hi_t) in one batch (at least one pair)
            base = ends[lo_t - 1] if lo_t else 0
            hi_t = int(np.searchsorted(ends, base + self.RASTER_BATCH, "right"))
            hi_t = max(hi_t, lo_t + 1)
            sl = slice(lo_t, hi_t)
            tc = cnt[sl]
            if not tc.sum():
                lo_t = hi_t
                continue
            pr = np.repeat(np.arange(lo_t, hi_t), tc)
            off = np.arange(int(tc.sum())) - np.repeat(np.cumsum(tc) - tc, tc)
            t = tp[pr]
            ii = ip[pr]
            jj = jlo[pr] + off
            px = self.x0 + (ii + 0.5) * CELL
            py = self.y0 + (jj + 0.5) * CELL
            at, bt, ct, dt = a[t], b[t], c[t], den[t]
            w1 = ((bt[:, 1] - ct[:, 1]) * (px - ct[:, 0]) + (ct[:, 0] - bt[:, 0]) * (py - ct[:, 1])) / dt
            w2 = ((ct[:, 1] - at[:, 1]) * (px - ct[:, 0]) + (at[:, 0] - ct[:, 0]) * (py - ct[:, 1])) / dt
            w3 = 1 - w1 - w2
            m = (w1 >= 0) & (w2 >= 0) & (w3 >= 0)
            if m.any():
                ax = (w1 * at[:, 2] + w2 * bt[:, 2] + w3 * ct[:, 2])[m]
                flat = ii[m] * ny + jj[m]
                order = np.argsort(flat, kind="stable")
                flat, ax = flat[order], ax[order]
                starts = np.flatnonzero(np.r_[True, flat[1:] != flat[:-1]])
                cells = flat[starts]
                lmin = self.lmin.reshape(-1)
                lmax = self.lmax.reshape(-1)
                lmin[cells] = np.minimum(lmin[cells], np.minimum.reduceat(ax, starts))
                lmax[cells] = np.maximum(lmax[cells], np.maximum.reduceat(ax, starts))
            lo_t = hi_t

    def lateral_escape(self, P, max_mm=2.0, chunk=2048):
        """For points inside the module: smallest sideways move (along +-e1,
        +-e2, in CELL steps) that takes each point OUT of the module at its
        own axial coordinate. A sliver overlap on a side face reads small
        here even when its axial depth is large. Capped at max_mm.

        R122: every step of every direction is looked up in one call per
        chunk of points (was one Python-level lookup per step and direction:
        160 of them, 5 s of a colliding check, measured). Each shifted point
        is formed and looked up with the same arithmetic as before, and
        points are independent, so the result is the same."""
        P = np.asarray(P, float).reshape(-1, 3)
        K = int(round(max_mm / CELL))
        out = np.full(len(P), max_mm)
        if not len(P) or K < 1:
            return out
        steps = np.arange(1, K + 1) * CELL                  # k * CELL, k = 1..K
        a_all = P @ self.d
        # R149: the steps are walked in blocks, nearest first, and a point
        # leaves the walk in the block where any direction first gets out:
        # every later step is longer, so its answer cannot change. Each
        # shifted point is still formed as P + v * (k * CELL), the same
        # doubles as walking all K steps at once.
        B = max(1, int(self.STEP_BLOCK))
        for c0 in range(0, len(P), chunk):
            Pc = P[c0:c0 + chunk]
            ac = a_all[c0:c0 + chunk]
            best = np.full(len(Pc), max_mm)
            live = np.arange(len(Pc))
            for k0 in range(0, K, B):
                if not len(live):
                    break
                st = steps[k0:k0 + B]
                nb = len(st)
                aa = np.repeat(ac[live], nb)                # the point's own axial coordinate
                found = np.full(len(live), np.inf)
                for v in (self.e1, -self.e1, self.e2, -self.e2):
                    Q = (Pc[live][:, None, :] + (v[None, :] * st[:, None])[None, :, :]).reshape(-1, 3)
                    ins, lo, hi, _ = self.lookup(Q)
                    still = (ins & (aa > lo + AXIAL_TOL) & (aa < hi - AXIAL_TOL)).reshape(len(live), nb)
                    out_k = ~still
                    hit = out_k.any(1)
                    first = np.argmax(out_k, 1)
                    found[hit] = np.minimum(found[hit], st[first[hit]])
                done = np.isfinite(found)
                best[live[done]] = np.minimum(best[live[done]], found[done])
                live = live[~done]
            out[c0:c0 + chunk] = best
        return out

    STEP_BLOCK = 8      # lateral_escape steps per block (R149)
    SCAN_MARGIN = 0.01 * CELL   # _raster: slab half-width and y margin, mm (R149)

    def escape_bound(self, P, max_mm=2.0):
        """R149: an UPPER BOUND on lateral_escape(P, max_mm), per point,
        from the mask alone (cheap: one cell lookup per point).

        lateral_escape stops at step k when the shifted point is no longer
        'still' inside - in particular when it lands in a cell outside the
        mask or off the grid. The cell a shifted point lands in is the
        point's own cell moved k cells, give or take one cell in each index
        (floating-point rounding at a cell boundary, in the point's cell as
        well as in the shifted one). So if every cell of the 3x3 block
        around (own cell + k steps) is outside the mask, the point is out at
        step k whatever the rounding: escape <= k * CELL. The bound is the
        smallest such k over the four directions, capped at max_mm."""
        P = np.asarray(P, float).reshape(-1, 3)
        K = int(round(max_mm / CELL))
        if not len(P):
            return np.zeros(0)
        g = self._escape_steps()
        i = np.floor((P @ self.e1 - self.x0) / CELL).astype(int)
        j = np.floor((P @ self.e2 - self.y0) / CELL).astype(int)
        nx, ny = self.mask.shape
        ok = (i >= 0) & (j >= 0) & (i < nx) & (j < ny)
        k = np.full(len(P), K)                          # off the grid: no claim
        k[ok] = np.minimum(g[i[ok], j[ok]], K)
        return np.minimum(k * CELL, max_mm)

    def _escape_steps(self):
        """Per cell: the fewest steps along +-e1 / +-e2 to a cell whose 3x3
        block is wholly outside the mask (cells off the grid count as
        outside). Cached on the column."""
        g = getattr(self, "_esc_steps", None)
        if g is not None:
            return g
        nx, ny = self.mask.shape
        # pad by 2 cells of 'outside' so off-grid cells take part
        m = np.zeros((nx + 4, ny + 4), bool)
        m[2:-2, 2:-2] = self.mask
        near = _sweep3(_sweep3(m, 0, np.logical_or, False), 1, np.logical_or, False)
        Z = ~near                                       # 3x3 block all outside
        big = 1 << 30
        best = np.full(m.shape, big, dtype=np.int64)
        idx0 = np.arange(m.shape[0])[:, None] * np.ones((1, m.shape[1]), np.int64)
        idx1 = np.ones((m.shape[0], 1), np.int64) * np.arange(m.shape[1])[None, :]
        for idx, axis in ((idx0, 0), (idx1, 1)):
            n = m.shape[axis]
            # next Z strictly after, along +axis (beyond the grid: n + 1)
            fwd = np.where(Z, idx, big)
            fwd = np.flip(np.minimum.accumulate(np.flip(fwd, axis), axis=axis), axis)
            nxt = np.full(m.shape, n + 1, dtype=np.int64)
            sl_a = [slice(None)] * 2
            sl_b = [slice(None)] * 2
            sl_a[axis], sl_b[axis] = slice(0, -1), slice(1, None)
            nxt[tuple(sl_a)] = np.minimum(fwd[tuple(sl_b)], n + 1)
            # previous Z strictly before, along -axis (beyond the grid: -2)
            bwd = np.where(Z, idx, -big)
            bwd = np.maximum.accumulate(bwd, axis=axis)
            prv = np.full(m.shape, -2, dtype=np.int64)
            prv[tuple(sl_b)] = np.maximum(bwd[tuple(sl_a)], -2)
            best = np.minimum(best, np.minimum(nxt - idx, idx - prv))
        self._esc_steps = best[2:-2, 2:-2]
        return self._esc_steps

    def lookup(self, P):
        i = np.floor((P @ self.e1 - self.x0) / CELL).astype(int)
        j = np.floor((P @ self.e2 - self.y0) / CELL).astype(int)
        ok = (i >= 0) & (j >= 0) & (i < self.mask.shape[0]) & (j < self.mask.shape[1])
        inside = np.zeros(len(P), bool)
        lo = np.full(len(P), np.nan)
        hi = np.full(len(P), np.nan)
        inside[ok] = self.mask[i[ok], j[ok]]
        lo[inside] = self.lmin[i[inside], j[inside]]
        hi[inside] = self.lmax[i[inside], j[inside]]
        return inside, lo, hi, P @ self.d


def _local_mesh(obj):
    """obj.Mesh in the object's OWN frame. (A Mesh::Feature's Mesh carries
    the feature Placement: its Topology comes back already in world
    coordinates — measured; see verification record.)"""
    m = obj.Mesh.copy()
    m.Placement = App.Placement()
    return m


def _world_tris(obj):
    return _xf(_matrix(obj.Placement), _tris(_local_mesh(obj)).reshape(-1, 3)).reshape(-1, 3, 3)


def _check_seated(Mw, feat, ps, Binv):
    """Pins in contacts at the stop, for a module at world matrix Mw.
    Numbers in the board frame."""
    M = Binv @ Mw
    R, t = M[:3, :3], M[:3, 3]
    d_m = R @ feat["d"]
    u_m = R @ feat["u"]
    r_m = R @ feat["r"]
    rep = {"ports": []}
    verdict = PASS
    ps_sorted = sorted(ps, key=lambda p: p.row_centre)
    if len(ps_sorted) != len(feat["groups"]):
        return {"verdict": FAIL, "why": "connector count != port count"}
    for p, g in zip(ps_sorted, feat["groups"]):
        d_p, up = _v(p.insert_dir), _v(p.up)
        r_p = np.cross(up, d_p)
        ang = math.degrees(math.acos(max(-1.0, min(1.0, float(d_m @ d_p)))))
        ang_u = math.degrees(math.acos(max(-1.0, min(1.0, float(u_m @ up)))))
        # header front plane, in the board frame, along the port axis
        corner = t + R @ (feat["d"] * g["header_front"])
        front_a = float(corner @ d_p)
        gap = p.mouth - front_a                         # + short of seat, - past it
        pr = {"port": p.number, "axis_error_deg": round(ang, 3),
              "up_error_deg": round(ang_u, 3), "stop_gap_mm": round(gap, 4),
              "pins": []}
        ok = ang <= ANGLE_TOL_DEG and ang_u <= ANGLE_TOL_DEG and abs(gap) <= AXIAL_TOL
        why = []
        if ang > ANGLE_TOL_DEG or ang_u > ANGLE_TOL_DEG:
            why.append("module axes off the port axes by %.2f / %.2f deg" % (ang, ang_u))
        if gap > AXIAL_TOL:
            why.append("header front %.3f mm SHORT of the housing mouth" % gap)
        elif gap < -AXIAL_TOL:
            why.append("header front %.3f mm PAST the housing mouth (into it)" % -gap)
        for q, c in zip(g["pins"], p.contacts):
            tip = t + R @ (feat["d"] * q["tip"] + feat["r"] * q["row"] + feat["u"] * q["up"])
            row = float(tip @ r_p)
            yy = float(tip @ up)
            a = float(tip @ d_p)
            slack = c["width"] / 2.0 - PIN_SECTION / 2.0
            in_row = abs(row - c["row"]) <= slack
            in_y = c["y_lo"] <= yy <= c["y_hi"]
            engaged = a - c["a_start"]
            not_bottomed = c["a_fork_base"] is None or a <= c["a_fork_base"] + AXIAL_TOL
            pr["pins"].append({"row_err": round(row - c["row"], 4), "y": round(yy, 4),
                               "engagement_mm": round(engaged, 4),
                               "to_fork_base_mm": (None if c["a_fork_base"] is None
                                                   else round(c["a_fork_base"] - a, 4))})
            if not (in_row and in_y and engaged > 0 and not_bottomed):
                ok = False
                why.append("pin at row %.3f / y %.3f / engagement %.3f not in contact "
                           "(row slack %.3f, y %.3f..%.3f)" % (row, yy, engaged, slack,
                                                               c["y_lo"], c["y_hi"]))
        pr["why"] = why
        rep["ports"].append(pr)
        if not ok:
            verdict = FAIL
    rep["verdict"] = verdict
    return rep


# ------------------------------------------------------------ obstacles (R66)
# EVERY visible object in the document other than the board and the module
# being checked is an obstacle: seated modules and other meshes by their
# triangles, and anything with a Part Shape (a case, a stand, a PartDesign
# Body, a Link) tessellated to world triangles. A module inside a Part case
# wall is a collision whether or not the case is a mesh.
#
# Excluded, each for a stated reason:
#   hidden objects          not part of what is shown (a Cut's tool body is
#                           hidden once consumed); seated modules are never
#                           excluded this way — hidden or not, they are on
#                           the board
#   datums, origins, sketches  reference geometry, not material
#   features inside a PartDesign::Body   the Body's Shape stands for them
#   containers (App::Part, groups)       their children are enumerated
#   shapes with no faces    wires and points enclose nothing
# Anything else that should be geometry but cannot be read (a feature in
# error with a null Shape, a Link to a mesh, a shape that will not
# tessellate, a GeoFeature of an unknown kind) is UNTESTED, and an untested
# obstacle turns a would-be PASS into CANNOT DETERMINE. Never a soft PASS.
TESS_TOL = 0.05       # tessellation deviation for Part obstacles (mm) = CELL
_NOT_OBSTACLE_TYPES = {
    "App::Origin", "App::Plane", "App::Line", "App::Point",
    "App::LocalCoordinateSystem", "PartDesign::Plane", "PartDesign::Line",
    "PartDesign::Point", "PartDesign::CoordinateSystem",
    "PartDesign::ShapeBinder", "PartDesign::SubShapeBinder",
    "Sketcher::SketchObject", "App::Part", "App::DocumentObjectGroup",
}
CHECKS = ("seated", "interference", "slide_path")


def _visible(o):
    try:
        return bool(o.Visibility)
    except Exception:                                    # noqa: BLE001
        return True


def _world_shape(o):
    """o's Shape in WORLD coordinates (parent containers applied)."""
    import Part
    sh = Part.getShape(o)
    if sh.isNull():
        return sh
    pl = getattr(o, "Placement", None)
    if pl is not None and hasattr(o, "getGlobalPlacement"):
        parent = o.getGlobalPlacement().multiply(pl.inverse())
        if not parent.isIdentity():
            sh = sh.copy()
            sh.Placement = parent.multiply(sh.Placement)
    return sh


def _obstacles(doc, board_obj):
    """(obstacles, untested labels) for doc. See the block comment above."""
    obs, untested = [], []
    if doc is None:
        return obs, untested
    for q in doc.Objects:
        role = getattr(q, "AtechRole", None)
        if q is board_obj or role == "board":
            continue
        t = q.TypeId
        if t == "Mesh::Feature":
            if role != "module" and not _visible(q):
                continue
            lm = _local_mesh(q)
            # global: a mesh inside a moved App::Part is where it is SHOWN
            gp = q.getGlobalPlacement() if hasattr(q, "getGlobalPlacement") else q.Placement
            obs.append({"obj": q, "label": q.Label, "local": lm, "solids": (),
                        "world": _matrix(gp),
                        "key": ("mesh", q.Name, _mesh_sig(lm), _r6(_matrix(gp)))})
            continue
        if not _visible(q) or t in _NOT_OBSTACLE_TYPES or "Datum" in t:
            continue
        try:
            parent = q.getParentGeoFeatureGroup()
        except Exception:                                # noqa: BLE001
            parent = None
        if parent is not None and parent.TypeId == "PartDesign::Body":
            continue
        is_link = t.startswith("App::Link")
        if not (hasattr(q, "Shape") or is_link):
            try:
                geo = q.isDerivedFrom("App::GeoFeature")
                group = q.hasExtension("App::GroupExtension")
            except Exception:                            # noqa: BLE001
                geo, group = False, False
            if geo and not group:
                untested.append(q.Label)
            continue
        memo = _shape_memo(doc, q)
        if memo is not None:
            sh, sig = memo
        else:
            try:
                sh = _world_shape(q)
            except Exception:                            # noqa: BLE001
                untested.append(q.Label)
                continue
            if sh.isNull():
                state = list(getattr(q, "State", []) or [])
                if is_link or "Invalid" in state or "Error" in state:
                    untested.append(q.Label)
                continue
            if not sh.countElement("Face"):
                continue
            try:
                sig = _shape_sig(sh)
            except Exception:                            # noqa: BLE001
                untested.append(q.Label)                 # will not tessellate
                continue
            _shape_memo(doc, q, (sh, sig))
        key = ("shape", q.Name) + sig
        pending = _SIG_TRIS.pop(id(sh), None)
        if pending is not None and pending[0] is sh:
            _remember(_TESS_CACHE, key, pending[1])
        obs.append({"obj": q, "label": q.Label, "shape": sh, "solids": tuple(sh.Solids),
                    "key": key})
    return obs, untested


# R122: _shape_sig reads the volume, area and every vertex of a shape: 0.6 s
# for the 16069-face board solid, paid on EVERY check (warm ones too). An
# object's Shape property returns the same TShape until the shape is
# reassigned, recomputed to something else or moved (measured: isSame True
# on two reads; False after reassign, a changed recompute or a new
# Placement). So the world shape and its signature are memoised per object
# and reused only while the object's own Shape isSame() the one they were
# computed from AND its parent placement is unchanged. The memo holds that
# Shape, so its TShape cannot be freed and its identity reused.
_SHAPE_MEMO = {}


def _shape_memo(doc, q, value=None):
    """Get (value None) or store the (world shape, signature) of q."""
    raw = getattr(q, "Shape", None)
    if raw is None or q.TypeId.startswith("App::Link"):
        return None
    try:
        gp = q.getGlobalPlacement() if hasattr(q, "getGlobalPlacement") else q.Placement
        key = (doc.Name, q.Name)
        where = _r6(_matrix(gp))
    except Exception:                                    # noqa: BLE001
        return None
    if value is not None:
        _remember(_SHAPE_MEMO, key, (raw, where, value))
        return None
    hit = _SHAPE_MEMO.get(key)
    if hit is None or hit[1] != where:
        return None
    try:
        same = hit[0].isSame(raw)
    except Exception:                                    # noqa: BLE001
        same = False
    return hit[2] if same else None


def _label_now(rec):
    """The obstacle's label as it is NOW (R100) — never a cached copy."""
    try:
        return rec["obj"].Label
    except Exception:                                    # noqa: BLE001
        return rec["label"]                              # object gone mid-check


def _tessellate(sh):
    """World triangles (n,3,3) of a Part shape at TESS_TOL."""
    pts, fac = sh.tessellate(TESS_TOL)
    if not fac:
        return np.zeros((0, 3, 3))
    P = np.array([[p.x, p.y, p.z] for p in pts])
    return P[np.array(fac)]


# R149: _shape_sig used to read sh.Volume, sh.Area and every B-rep vertex:
# 0.88 s for the 16069-face board solid, on top of the 0.5 s tessellation
# check() pays for every Part obstacle anyway (_obstacle_tris). The moments
# are now taken over the tessellation, which contains every B-rep vertex
# (and more points besides), so any vertex that moves still changes them;
# area and volume come from the same triangles. The triangles are handed to
# _obstacles through _SIG_TRIS so the shape is tessellated once, not twice.
_SIG_TRIS = {}


def _shape_sig(sh):
    """Geometric cache key of a WORLD shape. Not hashCode(): Part.getShape()
    returns a new TShape (new hash) on every call — measured. Counts, volume,
    area and bbox alone are NOT enough: moving a window inside a plate keeps
    all of them and changed the verdict (measured PASS cached vs FAIL fresh),
    so the first and second moments of the tessellation points (every B-rep
    vertex among them) are included — any vertex that moves changes them.
    Raises what sh.tessellate() raises."""
    bb = sh.BoundBox
    T = _tessellate(sh)
    _remember(_SIG_TRIS, id(sh), (sh, T))       # sh held: its id cannot be reused
    V = T.reshape(-1, 3) if len(T) else np.zeros((1, 3))
    if len(T):
        cr = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        area = 0.5 * float(np.linalg.norm(cr, axis=1).sum())
        vol = float((cr * T[:, 0]).sum()) / 6.0
    else:
        area = vol = 0.0
    # countElement, not len(sh.Faces): same counts without building a Python
    # list of every face (0.29 s vs 0.03 s on the 16069-face board solid, R122).
    # R149: only the face count - each countElement type builds its own
    # sub-shape map (7-10 ms each on that solid, measured), and the edges
    # and vertices are already covered by the tessellation moments below.
    return (sh.countElement("Face"),
            round(vol, 4), round(area, 4), len(T),
            _r6([bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax]),
            _r6(V.sum(0)), _r6((V * V).sum(0)), _r6((V[:, [0, 0, 1]] * V[:, [1, 2, 2]]).sum(0)))


def _obstacle_tris(rec):
    """World triangles (n,3,3) of one obstacle record."""
    if "local" in rec:
        T = _tris(rec["local"]).reshape(-1, 3)
        return _xf(rec["world"], T).reshape(-1, 3, 3)
    hit = _TESS_CACHE.get(rec["key"])
    if hit is not None:
        return hit
    return _remember(_TESS_CACHE, rec["key"], _tessellate(rec["shape"]))


# ------------------------------------------------------------ the test
def _columns(sig, feat, axes):
    """(all, body) swept columns of a module in its OWN frame, along local
    axes (e1, e2, d). Memoised: a module seated on any port of any board
    placement has the same local axes, so warm() can pre-build them."""
    key = (sig, _r6(np.array(axes)))
    hit = _COL_CACHE.get(key)
    if hit is not None:
        CACHE_STATS["hit"] += 1
        return hit
    CACHE_STATS["miss"] += 1
    e1, e2, d = (_v(a) for a in axes)
    body = feat["body_tris"]
    both = np.concatenate([body, feat["pin_tris"]])
    col_body = _Column(body, e1, e2, d)
    col_all = _Column(both, e1, e2, d, base=(col_body, feat["pin_tris"]))
    for c in (col_body, col_all):
        del c._raw                                       # pre-erosion copies: not kept
    return _remember(_COL_CACHE, key, (col_all, col_body))


ESCAPE_MAX = 2.0       # mm, cap of the lateral escape search (_Column.lateral_escape)
ESCAPE_PROBE = 4096    # seat-hit points walked per batch, deepest first (R122)


def _escape_maxima(col, Ps, depth):
    """(max lateral escape, max penetration = min(axial depth, lateral
    escape)) over the seat-hit points Ps: the only two numbers reported.

    R122: a deep collision has 10^5 points and lateral_escape walks each up
    to 40 cells in 4 directions (5 s of one check, measured). The points are
    walked in batches and the walk skips every point that cannot change
    either maximum. R149: that test uses a per-point UPPER BOUND on the
    lateral escape (_Column.escape_bound: the distance to cells wholly
    outside the column's mask, never less than the walk's own answer), not
    only the cap ESCAPE_MAX: a point whose bound is <= the best lateral
    escape so far, and whose min(depth, bound) is <= the best penetration
    so far, cannot raise either. Before R149 the walk stopped only once the
    lateral maximum reached the cap, so a module pushed 1 mm into the PCB
    (lateral maximum 1.0 mm) walked all 462,196 points: 2.2 s of a 3 s
    check (measured). Points are walked in order of min(depth, bound),
    highest first. Exact: the same two numbers as walking every point."""
    ub = col.escape_bound(Ps, ESCAPE_MAX)
    key = np.minimum(depth, ub)
    order = np.argsort(-key, kind="stable")
    lat_max = pen_max = -np.inf
    rest = order
    while len(rest):
        # maxima only grow: a point useless now stays useless
        rest = rest[(ub[rest] > lat_max) | (key[rest] > pen_max)]
        if not len(rest):
            break
        idx, rest = rest[:ESCAPE_PROBE], rest[ESCAPE_PROBE:]
        lat = col.lateral_escape(Ps[idx], ESCAPE_MAX)
        lat_max = max(lat_max, float(lat.max()))
        pen_max = max(pen_max, float(np.minimum(depth[idx], lat).max()))
    return lat_max, pen_max


def _hits(T, col, lo_box, hi_box, s_out):
    """(seat hit, path hit) of obstacle triangles T (module frame) against a
    column; each is a dict of numbers or None."""
    if len(T) == 0:
        return None, None
    reach = col.reach_box(s_out)
    if reach is None:
        return None, None
    lo_box, hi_box = np.maximum(lo_box, reach[0]), np.minimum(hi_box, reach[1])
    if np.any(lo_box > hi_box):
        return None, None
    tl, th = T.min(1), T.max(1)
    keep = np.all(th >= lo_box, 1) & np.all(tl <= hi_box, 1)
    if not keep.any():
        return None, None
    # only points inside the box can meet the column (it lies within the
    # module's swept envelope, 0.5 mm inside the box), so blocks of big
    # triangles outside it are never generated (R122)
    P = _sample(T[keep], box=(lo_box, hi_box))
    inside, lo, hi, a = col.lookup(P)
    if not inside.any():
        return None, None
    s_in = inside & (a > lo + AXIAL_TOL) & (a < hi - AXIAL_TOL)
    p_in = inside & (a > lo - s_out + AXIAL_TOL) & (a < hi - AXIAL_TOL) & ~s_in
    seat_hit = path_hit = None
    if s_in.any():
        depth = np.minimum(a[s_in] - lo[s_in], hi[s_in] - a[s_in])
        lat_max, pen_max = _escape_maxima(col, P[s_in], depth)
        seat_hit = {"points": int(s_in.sum()),
                    "max_axial_depth_mm": round(float(depth.max()), 3),
                    "max_lateral_depth_mm": round(lat_max, 3),
                    "max_penetration_mm": round(pen_max, 3)}
    if p_in.any():
        # distance before the seat at which this obstacle is first met
        first = hi[p_in] - a[p_in]
        path_hit = {"points": int(p_in.sum()),
                    "met_mm_before_seat": round(float(first.max()), 3)}
    return seat_hit, path_hit


# R122: OCCT's point classifier (Shape.isInside, the distToShape class of
# call) costs per FACE. On a solid sewn from a mesh — the 14-port board STL
# as a Part solid has 16069 faces — one check ran for minutes (the dogfood
# harness saw a 10 min stall on distToShape against exactly that solid).
# Solids with more faces than CLASSIFY_FACES are classified on their own
# triangles instead: parity of hits along a fixed, deliberately non-axis
# ray (a mesh-derived solid is planar triangles, so its triangles ARE its
# faces). Solids with fewer faces keep the exact OCCT classifier.
# The threshold is low on purpose: OCCT costs ~0.06 ms per point per face
# here (4000-point volume grid: 0.3 s at 6 faces, 2 s at 31, 7.6 s at 106,
# measured), while the triangle test agreed with it on every point tried
# (0 of 500 disagreements per solid at 6..106 faces, 0 of 1500 at 367 faces,
# plates with drilled holes, curved faces tessellated at TESS_TOL). A Part
# case of 31 faces colliding with a module cost 5.8 s of isInside with the
# old threshold of 256 (review, round 4).
CLASSIFY_FACES = 8
_RAY = np.array([0.5773502, 0.5773519, 0.5773486])
_RAY = _RAY / np.linalg.norm(_RAY)
_SOLID_INFO = {}


def _solid_info(rec):
    """Per solid of a Part obstacle record: its bbox, face count and (for a
    solid over CLASSIFY_FACES faces) its world triangles. Memoised on the
    record's key (Name + geometric signature), so the per-face work — even
    len(solid.Faces) costs 0.3 s on the 16069-face board solid, measured —
    is paid once per shape, not once per module or per query."""
    hit = _SOLID_INFO.get(rec["key"])
    if hit is not None:
        return hit
    out = []
    n_shape = rec["key"][2]                    # face count, from _shape_sig
    single = len(rec["solids"]) == 1 and rec["shape"].ShapeType == "Solid"
    for s in rec["solids"]:
        # a shape that IS one solid has the shape's face count (R149: saves
        # building another sub-shape map, ~10 ms on the board solid)
        nf = n_shape if single else s.countElement("Face")
        bb = s.BoundBox
        info = {"solid": s, "faces": nf,
                "bbox": (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax),
                "tris": None}
        if nf > CLASSIFY_FACES:
            if len(rec["solids"]) == 1 and nf == n_shape:
                T = _obstacle_tris(rec)        # the shape IS this solid
            else:
                pts, fac = s.tessellate(TESS_TOL)
                T = (np.array([[q.x, q.y, q.z] for q in pts])[np.array(fac)]
                     if fac else np.zeros((0, 3, 3)))
            info["tris"] = _RayGrid(T)
        out.append(info)
    return _remember(_SOLID_INFO, rec["key"], out)


class _RayGrid(object):
    """Closed triangle surface prepared for point-in-solid by the parity of
    ray hits along _RAY: triangles bucketed on a 2-D grid across the ray,
    so each point meets only the few triangles over its own cell."""

    def __init__(self, T):
        self.T = T
        d = _RAY
        u = np.cross(d, [1.0, 0.0, 0.0])
        self.u = u / np.linalg.norm(u)
        self.w = np.cross(d, self.u)
        self.v0 = T[:, 0]
        self.e1 = T[:, 1] - self.v0
        self.e2 = T[:, 2] - self.v0
        self.pv = np.cross(d, self.e2)
        self.det = (self.e1 * self.pv).sum(1)
        good = np.flatnonzero(np.abs(self.det) > 1e-12)
        if not len(good):
            self.cells = None
            return
        T2 = np.stack([T[good] @ self.u, T[good] @ self.w], -1)     # (m, 3, 2)
        lo2, hi2 = T2.min(1), T2.max(1)
        self.o = lo2.min(0)
        span = np.maximum(hi2.max(0) - self.o, 1e-9)
        self.n = max(1, int(np.sqrt(len(good))))                    # cells per axis
        self.h = span / self.n
        c0 = np.clip(((lo2 - self.o) / self.h).astype(np.int64), 0, self.n - 1)
        c1 = np.clip(((hi2 - self.o) / self.h).astype(np.int64), 0, self.n - 1)
        ni, nj = c1[:, 0] - c0[:, 0] + 1, c1[:, 1] - c0[:, 1] + 1
        cnt = ni * nj
        t = np.repeat(np.arange(len(good)), cnt)
        off = np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        cell = (c0[t, 0] + off // nj[t]) * self.n + (c0[t, 1] + off % nj[t])
        order = np.argsort(cell, kind="stable")
        self.cells = cell[order]
        self.tri = good[t[order]]
        self.start = np.searchsorted(self.cells, np.arange(self.n * self.n), "left")
        self.end = np.searchsorted(self.cells, np.arange(self.n * self.n), "right")

    def inside(self, P):
        P = np.asarray(P, float).reshape(-1, 3)
        out = np.zeros(len(P), bool)
        if self.cells is None or not len(P):
            return out
        P2 = np.stack([P @ self.u, P @ self.w], -1)
        c = np.floor((P2 - self.o) / self.h).astype(np.int64)
        ok = np.all((c >= 0) & (c < self.n), 1)
        idx = np.flatnonzero(ok)
        if not len(idx):
            return out
        flat = c[idx, 0] * self.n + c[idx, 1]
        st, en = self.start[flat], self.end[flat]
        cnt = en - st
        pi = np.repeat(idx, cnt)
        k = np.repeat(st, cnt) + (np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt))
        ti = self.tri[k]
        d = _RAY
        sv = P[pi] - self.v0[ti]
        inv = 1.0 / self.det[ti]
        a = (sv * self.pv[ti]).sum(1) * inv
        q = np.cross(sv, self.e1[ti])
        b = (q @ d) * inv
        t = (q * self.e2[ti]).sum(1) * inv
        hit = (a >= 0) & (b >= 0) & (a + b <= 1) & (t > 0)
        out[:] = np.bincount(pi[hit], minlength=len(P)) % 2 == 1
        return out


def _classify(info, Pw):
    """(len(Pw),) bool: world points strictly inside one solid (_solid_info
    entry): OCCT's classifier for a solid of <= CLASSIFY_FACES faces, the
    ray-parity test on its triangles above that."""
    Pw = np.asarray(Pw, float).reshape(-1, 3)
    x0, y0, z0, x1, y1, z1 = info["bbox"]
    inb = ((Pw[:, 0] > x0) & (Pw[:, 0] < x1) & (Pw[:, 1] > y0)
           & (Pw[:, 1] < y1) & (Pw[:, 2] > z0) & (Pw[:, 2] < z1))
    out = np.zeros(len(Pw), bool)
    if not inb.any():
        return out
    if info["tris"] is not None:
        out[inb] = info["tris"].inside(Pw[inb])
        return out
    s = info["solid"]
    for k in np.flatnonzero(inb):
        out[k] = s.isInside(App.Vector(*[float(x) for x in Pw[k]]), 1e-6, False)
    return out


def _inside_solids(rec, Pw):
    """True when any world point of Pw lies strictly inside any solid of
    the obstacle record rec."""
    return any(_classify(info, Pw).any() for info in _solid_info(rec))


def _solid_overlap_volume(rec, col, Mw, lo, hi, budget=4000):
    """Grid estimate (mm3) of solid-obstacle material inside the module's
    column envelope. The module is treated as FILLED along the slide axis
    (as the column is), so for a hollow module this over-reports; it is a
    size for the report, the verdict does not depend on it."""
    Minv = np.linalg.inv(Mw)
    vol = 0.0
    for info in _solid_info(rec):
        x0, y0, z0, x1, y1, z1 = info["bbox"]
        C = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)])
        C = _xf(Minv, C)
        slo, shi = np.maximum(lo, C.min(0)), np.minimum(hi, C.max(0))
        ext = shi - slo
        if np.any(ext <= 0):
            continue
        h = max(0.1, (float(np.prod(ext)) / 20000.0) ** (1.0 / 3.0))
        G = None
        for _ in range(6):                               # coarsen until within budget
            ticks = [np.arange(slo[k] + h / 2.0, shi[k], h) for k in range(3)]
            cell = h ** 3
            if any(len(tk) == 0 for tk in ticks):        # region thinner than a cell
                ticks = [np.array([(slo[k] + shi[k]) / 2.0]) for k in range(3)]
                cell = float(np.prod(ext))
            G = np.stack(np.meshgrid(*ticks, indexing="ij"), -1).reshape(-1, 3)
            ins, clo, chi, a = col.lookup(G)
            ins &= (a >= clo) & (a <= chi)
            n = int(ins.sum())
            if n <= budget:
                break
            h *= (n / float(budget)) ** (1.0 / 3.0)
        k = int(_classify(info, _xf(Mw, G[ins])).sum())
        vol += k * cell
    return round(vol, 1)


def _board_tri_boxes(board):
    """(centroid, bbox lo, bbox hi) of every board obstacle triangle, in the
    board frame. Computed once per measured board (R149: obs.mean(1) alone
    was paid per module)."""
    hit = board.get("_tri_boxes")
    if hit is None:
        obs = board["obstacle_tris"]
        hit = board["_tri_boxes"] = (obs.mean(1), obs.min(1), obs.max(1))
    return hit


def _is_fitted_after(obj, fitted_after):
    """True when obj is named (by Name or Label) in the fitted-after set."""
    if not fitted_after:
        return False
    try:
        return obj.Name in fitted_after or obj.Label in fitted_after
    except Exception:                                    # noqa: BLE001
        return False                                     # object gone mid-check


def _evaluate(sig, feat, Mw, ps, Bm, s_out, board, obstacles, untested, skip=None,
              fitted_after=None):
    """All three checks for one module at world matrix Mw on ports ps.

    Works in the MODULE's own frame: obstacles are brought to it, so the
    module's columns are reusable across placements (_columns). Board hits
    are memoised on the module placement RELATIVE to the board; every other
    obstacle on (module key, obstacle key). Returns fresh dicts.

    fitted_after (R136): Names/Labels of parts fitted AFTER the modules (an
    end cap, a lid). They are not there while a module slides in, so their
    path hits do not count against slide_path — they are reported under
    slide_path["ignored_fitted_after"], never dropped silently. They are
    still obstacles in their closed position for seated and interference.
    The hit cache is unchanged: the option is applied at report time."""
    Binv = np.linalg.inv(Bm)
    res = {"seated": _check_seated(Mw, feat, ps, Binv)}
    R = Mw[:3, :3]
    d = Bm[:3, :3] @ _v(ps[0].insert_dir)
    e2 = Bm[:3, :3] @ _v(ps[0].up)
    e1 = np.cross(e2, d)
    axes = tuple(R.T @ v for v in (e1, e2, d))
    col_all, col_body = _columns(sig, feat, axes)
    allP = np.concatenate([feat["body_tris"], feat["pin_tris"]]).reshape(-1, 3)
    env_lo, env_hi = allP.min(0), allP.max(0)
    back = allP - axes[2] * s_out                        # swept backwards along -d
    lo_box = np.minimum(env_lo, back.min(0)) - 0.5
    hi_box = np.maximum(env_hi, back.max(0)) + 0.5
    s_key = round(float(s_out), 6)
    a_key = _r6(np.array(axes))

    found = []                                           # (label, seat hit, path hit, fitted after)
    Mrel = Binv @ Mw
    bkey = ("board", sig, tuple(sorted(p.number for p in ps)), _r6(Mrel), s_key, a_key)
    bres = _HIT_CACHE.get(bkey)
    if bres is None:
        CACHE_STATS["miss"] += 1
        # The module's own socket(s) — housing + fork contacts — are tested
        # against the module BODY only: pins are meant to enter them.
        obs = board["obstacle_tris"]
        cen, tlo, thi = _board_tri_boxes(board)
        # R149: only board triangles that can reach the module's box are
        # brought into the module frame (was all 246k, twice, per module).
        # The box's 8 corners in the board frame bound it there, so every
        # triangle that meets the box is kept; _hits then applies its own
        # module-frame box test to the survivors, in their original order.
        C = np.array([[x, y, z] for x in (lo_box[0], hi_box[0])
                      for y in (lo_box[1], hi_box[1]) for z in (lo_box[2], hi_box[2])])
        C = _xf(Mrel, C)
        near = np.all(thi >= C.min(0) - 0.01, 1) & np.all(tlo <= C.max(0) + 0.01, 1)
        is_own = np.zeros(len(obs), bool)
        for p in ps:
            is_own |= (board["obstacle_is_socket"]
                       & np.all(cen >= _v(p.socket_lo) - 0.01, 1)
                       & np.all(cen <= _v(p.socket_hi) + 0.01, 1))
        to_local = np.linalg.inv(Mrel)
        bres = []
        for label, mask, col in (("board", ~is_own & near, col_all),
                                 ("board:own socket", is_own & near, col_body)):
            T = _xf(to_local, obs[mask].reshape(-1, 3)).reshape(-1, 3, 3)
            bres.append((label,) + _hits(T, col, lo_box, hi_box, s_out))
        _remember(_HIT_CACHE, bkey, bres)
    else:
        CACHE_STATS["hit"] += 1
    found.extend(r + (False,) for r in bres)             # the board is never fitted after

    mkey = (sig, _r6(Mw), s_key, a_key)
    Minv = np.linalg.inv(Mw)
    for rec in obstacles:
        if skip is not None and rec["obj"] is skip:
            continue
        # Keyed on the obstacle's Name + geometry (rec["key"]) only; the
        # LABEL is read now, at report time (R100): a relabel must neither
        # re-measure nor report the old name ("X [previous build]", D43).
        key = (mkey, rec["key"])
        h = _HIT_CACHE.get(key)
        if h is None:
            CACHE_STATS["miss"] += 1
            T = _xf(Minv, _obstacle_tris(rec).reshape(-1, 3)).reshape(-1, 3, 3)
            sh, ph = _hits(T, col_all, lo_box, hi_box, s_out)
            if rec["solids"]:
                if sh is None:
                    # a solid that swallows the module whole has no surface
                    # inside it; test module points for containment
                    body = feat["body_tris"].reshape(-1, 3)
                    idx = np.linspace(0, len(body) - 1, min(64, len(body))).astype(int)
                    pts = np.vstack([body[idx], body.mean(0)[None, :]])
                    if _inside_solids(rec, _xf(Mw, pts)):
                        sh = {"points": 0, "module_inside_solid": True}
                if sh is not None:
                    sh["approx_volume_mm3"] = _solid_overlap_volume(
                        rec, col_all, Mw, env_lo, env_hi)
            h = _remember(_HIT_CACHE, key, (sh, ph))
        else:
            CACHE_STATS["hit"] += 1
        found.append((_label_now(rec),) + h + (_is_fitted_after(rec["obj"], fitted_after),))

    seat_hits = {lab: dict(sh) for lab, sh, _, _ in found if sh is not None}
    path_hits = {lab: dict(ph) for lab, _, ph, fa in found if ph is not None and not fa}
    ignored = {lab: dict(ph) for lab, _, ph, fa in found if ph is not None and fa}
    untested = list(untested or [])
    # an unreadable part declared fitted after is not on the slide path either;
    # it still makes interference CANNOT DETERMINE
    fa = set(fitted_after or ())
    untested_path = [u for u in untested if u not in fa]

    def why(u):
        return "could not test against %s (no readable geometry)" % ", ".join(u)

    def verdict(hits, u):
        return FAIL if hits else (CANNOT if u else PASS)

    res["interference"] = {"verdict": verdict(seat_hits, untested), "hits": seat_hits,
                           "untested": untested,
                           "method": "swept column along port axis, %.2f mm cells, "
                                     "1-cell erosion, axial tol %.2f" % (CELL, AXIAL_TOL)}
    res["slide_path"] = {"verdict": verdict(path_hits, untested_path), "hits": path_hits,
                         "untested": untested_path, "travel_mm": round(float(s_out), 3)}
    if fa:
        res["slide_path"]["fitted_after"] = sorted(fa)
        res["slide_path"]["ignored_fitted_after"] = ignored
    if res["interference"]["verdict"] == CANNOT:
        res["interference"]["why"] = why(untested)
    if res["slide_path"]["verdict"] == CANNOT:
        res["slide_path"]["why"] = why(untested_path)
    return res


def first_why(res):
    """One line saying why a module's checks did not all PASS, or None."""
    for k in CHECKS:
        r = res.get(k) or {}
        v = r.get("verdict")
        if v == PASS:
            continue
        if v == CANNOT or "hits" not in r and "ports" not in r:
            return r.get("why") or "%s: cannot determine" % k
        if k == "seated":
            for p in r.get("ports") or []:
                if p.get("why"):
                    return "port %d: %s" % (p["port"], p["why"][0])
            return r.get("why") or "not seated"
        hits = r.get("hits") or {}
        if hits:
            lab = sorted(hits)[0]
            if k == "interference":
                return "collides with %s" % lab
            return "%s is in the way as it slides in" % lab
    return None


@_few_blas_threads
def check(doc, only=None, fitted_after=None):
    """Per Atech module: {'seated', 'interference', 'slide_path'} each a dict
    with 'verdict' in PASS / FAIL / CANNOT DETERMINE plus the numbers.

    only: iterable of object Names to CHECK. Every other object still counts
    as an obstacle; it is just not itself checked. Obstacles are every
    visible object (Part shapes included, R66) — see _obstacles(). If any
    visible object's geometry cannot be read, interference and slide path
    say CANNOT DETERMINE (unless something else already FAILs).

    fitted_after (R136): iterable of object Names or Labels of parts fitted
    AFTER the modules (end caps, a lid), so a case can be closed. slide_path
    ignores them (their would-be hits are listed under
    slide_path["ignored_fitted_after"]); seated and interference still test
    them where they are, in their closed position. Undeclared, every part
    blocks the slide path.

    Memoised (S20): a repeated check of an unchanged document reuses every
    measured number; moving or editing anything changes its cache key."""
    only = set(only) if only is not None else None
    if isinstance(fitted_after, str):
        fitted_after = [fitted_after]
    fitted_after = frozenset(fitted_after or ())
    if fitted_after and doc is not None:
        # a part declared by Name is also known by its Label, and vice versa:
        # unreadable parts are reported (untested) by Label only
        both = set(fitted_after)
        for q in doc.Objects:
            try:
                if q.Name in fitted_after or q.Label in fitted_after:
                    both.update((q.Name, q.Label))
            except Exception:                            # noqa: BLE001
                continue
        fitted_after = frozenset(both)
    results = {}
    b = board_object(doc, create=False)
    try:
        board = measure_board()
    except AtechPortError as exc:
        board = None
        berr = str(exc)
    meshes = [o for o in doc.Objects
              if o.TypeId == "Mesh::Feature" and getattr(o, "AtechRole", None) != "board"]
    obstacles = untested = None
    for o in meshes:
        if only is not None and o.Name not in only:
            continue
        res = {}
        results[o.Name] = res
        if getattr(o, "AtechRole", None) != "module":
            for k in CHECKS:
                res[k] = {"verdict": CANNOT, "why": "not an Atech-seated module "
                                                   "(no AtechPorts): its port is unknown"}
            continue
        if b is None or board is None:
            for k in CHECKS:
                res[k] = {"verdict": CANNOT, "why": "no board in document" if b is None else berr}
            continue
        try:
            sig, feat = _feat_for(_local_mesh(o), o.AtechModule)
        except NoConnector as exc:
            for k in CHECKS:
                res[k] = {"verdict": CANNOT, "why": str(exc)}
            continue
        if obstacles is None:
            obstacles, untested = _obstacles(doc, b)
        ps = [port(int(n)) for n in o.AtechPorts]
        res.update(_evaluate(sig, feat, _matrix(o.Placement), ps, _matrix(b.Placement),
                             float(o.AtechSlideOut), board, obstacles, untested, skip=o,
                             fitted_after=fitted_after))
    return results


# ------------------------------------------------------------ pairing (R65)
def pair_for(doc, module_name, port_n, reserved=None):
    """Ports for a two-connector module picked on port_n: port_n plus a free
    neighbour in the same column whose TRIAL check (seated, interference,
    slide path — against everything already in doc) is all PASS. Nothing is
    added to doc. Of several passing pairs the one whose headers land most
    flush wins. A one-connector module gets port_n back.

    Raises PortSpecError kind="no_pair" when no free, unreserved neighbour
    exists, kind="pair_fails" (info: pairs, why) when every candidate pair
    fails its own check. Never returns a pair the check would FAIL."""
    reserved = RESERVED if reserved is None else reserved
    sig, feat = _module_entry(module_name)
    n_conn = len(feat["groups"])
    if n_conn == 1:
        return int(port_n)
    if n_conn != 2:
        raise PortSpecError("%s has %d connectors; pair_for handles two"
                            % (module_name, n_conn), kind="port_count",
                            module=module_name, connectors=n_conn, ports=[port_n])
    p0 = port(int(port_n))
    col = sorted((q for q in ports().values() if q.edge == p0.edge),
                 key=lambda q: q.row_centre)
    i = [q.number for q in col].index(p0.number)
    occ = occupied(doc) if doc is not None else {}
    b = board_object(doc, create=False) if doc is not None else None
    Bm = _matrix(b.Placement) if b is not None else np.eye(4)
    board = measure_board()
    obstacles, untested = _obstacles(doc, b)
    d_world = Bm[:3, :3] @ _v(p0.insert_dir)
    tried, cands = [], []
    for j in (i - 1, i + 1):
        if not 0 <= j < len(col):
            continue
        q = col[j]
        if q.number in occ or q.number in reserved or p0.number in reserved:
            continue
        pair = tuple(sorted((p0.number, q.number)))
        try:
            pl, info = seated_placement(module_name, pair,
                                        b.Placement if b is not None else None, feat)
        except PortSpecError as exc:
            tried.append((pair, str(exc)))
            continue
        Mw = _matrix(pl)
        res = _evaluate(sig, feat, Mw, [port(n) for n in pair], Bm,
                        _slide_out(feat, Mw, d_world, Bm), board, obstacles, untested)
        if any(res[k]["verdict"] != PASS for k in CHECKS):
            tried.append((pair, first_why(res)))
            continue
        cands.append((max(info["short_of_mouth_mm"].values()), pair))
    if cands:
        return min(cands)[1]
    if not tried:
        raise PortSpecError("a two-connector module needs port %d and a free neighbour "
                            "in the same column" % p0.number, kind="no_pair",
                            module=module_name, port=p0.number)
    raise PortSpecError("%s on port %d: every candidate pair fails its check: %s"
                        % (module_name, p0.number, tried), kind="pair_fails",
                        module=module_name, port=p0.number,
                        pairs=[list(p) for p, _ in tried], why=tried[0][1])


# ------------------------------------------------------------ API card (S21)
_CARD_CALLS = ("board_object", "seat", "pair_for", "remove", "occupied", "bbox",
               "slide", "check", "port_table", "warm")


def _fmt(x):
    return "%.2f" % (round(float(x), 2) + 0.0)


def _axis_word(v):
    k = int(np.argmax(np.abs(v)))
    return ("+" if v[k] > 0 else "-") + "XYZ"[k]


def _mouth_plane(p):
    """'x=8.27': the mouth as a plane in board coordinates (port_table()
    stores it as a coordinate along insert_dir, i.e. signed)."""
    d = p["insert_dir"]
    k = int(np.argmax(np.abs(d)))
    return "%s=%s" % ("xyz"[k], _fmt(p["mouth"] * (1 if d[k] > 0 else -1)))


def api_card():
    """A short (2-3 KB) plain-text card of the Atech API and the board frame,
    GENERATED from port_table(), the measured module meshes and the call
    signatures, so it cannot drift from the code. Each module row names its
    working face (R165) from working_faces(), with the board-frame axis of
    "up" and of "out" per port edge. What docs/ATECH_ASSEMBLY.md
    lists as OPEN is printed as OPEN, never filled in."""
    import inspect
    table = port_table()
    # Extents of the board as DRAWN and checked (R197: the GLB triangles),
    # not of the STL, whose central frame stops 0.51 mm short.
    P = measure_board()["obstacle_tris"].reshape(-1, 3)
    (x0, y0, z0), (x1, y1, z1) = P.min(0).tolist(), P.max(0).tolist()
    up = table[1]["up"]
    L = ["ATECH API CARD (generated; mm)",
         "BOARD FRAME (board at identity; modules follow the board Placement)",
         "  extents x %s..%s y %s..%s z %s..%s" % tuple(_fmt(v) for v in (x0, x1, y0, y1, z0, z1)),
         "  %s is up: modules sit on that face; housings stand on y=%s"
         % (_axis_word(up), _fmt(table[1]["pcb_y"])),
         "  ports 1-6 left edge slide %s; 9-14 right edge slide %s; "
         "7 top edge slides %s; 8 bottom edge slides %s"
         % (_axis_word(table[1]["insert_dir"]), _axis_word(table[9]["insert_dir"]),
            _axis_word(table[7]["insert_dir"]), _axis_word(table[8]["insert_dir"])),
         "PORTS (slide = way the module travels to seat; it stops at the mouth)",
         "  port edge   slide housing x       housing z        mouth"]
    for n, p in table.items():
        lo, hi = p["housing_lo"], p["housing_hi"]
        L.append("  %-4d %-6s %-5s %s..%s  %s..%s  %s"
                 % (n, p["edge"], _axis_word(p["insert_dir"]), _fmt(lo[0]), _fmt(hi[0]),
                    _fmt(lo[2]), _fmt(hi[2]), _mouth_plane(p)))
    names = sorted(f[:-4] for f in os.listdir(STL_DIR)
                   if f.endswith(".stl") and f[:-4] != BOARD_NAME)
    L.append("MODULES (measured: row x up x slide; conn = ports taken;")
    L.append("  face = working face (mesh): up = %s; out = toward the port's "
             "edge: %s)" % (_axis_word(up), "; ".join(
                 "%s %s" % (k, _axis_word(-_v(table[n0]["insert_dir"])))
                 for k, n0 in (("1-6", 1), ("9-14", 9), ("7", 7), ("8", 8)))))
    unseatable = []
    for n in names:
        try:
            f = measure_module(n)
        except UndefinedByLibrary:
            unseatable.append(n)
            continue
        P = np.concatenate([f["body_tris"], f["pin_tris"]]).reshape(-1, 3)
        dims = [float((P @ ax).max() - (P @ ax).min()) for ax in (f["r"], f["u"], f["d"])]
        face = ",".join(
            q["word"] + ("" if q["section_mm"] is None else " (%sx%s part %s proud)" % (
                _fmt(q["section_mm"][0]), _fmt(q["section_mm"][1]), _fmt(q["proud_mm"])))
            for q in f["faces"])
        L.append("  %-15s %sx%sx%s conn %d face %s"
                 % (n, _fmt(dims[0]), _fmt(dims[1]), _fmt(dims[2]), len(f["groups"]), face))
    if unseatable:
        L.append("  %s: no pin header: cannot be seated (OPEN)"
                 % ", ".join(unseatable))
    L.append("CALLS (import atech_ports as ap)")
    for c in _CARD_CALLS:
        L.append("  ap.%s%s" % (c, inspect.signature(globals()[c])))
    L.append("  seat() is idempotent and returns a Mesh::Feature (no .Shape: use "
             "ap.bbox). 2-connector modules take a port tuple; ap.pair_for picks "
             "one whose check PASSes.")
    L.append("  ap.check(doc, fitted_after={\"End_Cap_L\", \"End_Cap_R\"}) closes a "
             "case: parts fitted after the modules (caps, lid; Name or Label) do not "
             "block slide_path but still count for interference. Undeclared, "
             "every part blocks the slide path.")
    L.append("EXAMPLE")
    L.append('  light = ap.seat(doc, "light", 2)')
    L.append('  screen = ap.seat(doc, "screen", ap.pair_for(doc, "screen", 9))')
    L.append("  bb = ap.bbox(light)  # world App.BoundBox")
    off = []
    for edge in ("left", "right"):
        col = [(n, p) for n, p in table.items() if p["edge"] == edge]
        mouths = [round(p["mouth"], 2) for _, p in col]
        ref = max(set(mouths), key=mouths.count)
        off += ["%d %+.2f" % (n, round(p["mouth"], 2) - ref) for n, p in col
                if abs(round(p["mouth"], 2) - ref) > 0.005]
    L.append("OPEN (unknown; do not assume)")
    L.append("  pin-1 end of the row and the pin order (two sources disagree)")
    L.append("  ports 8, 12 as module slots (reserved now: %s)"
             % (", ".join("%d %s" % kv for kv in sorted(RESERVED.items())) or "none"))
    if off:
        L.append("  mouths off their column (%s): real board or export artefact; "
                 "pairs across them can fail" % ", ".join(off))
    L.append("  retention, contact force, per-pin current")
    return "\n".join(L) + "\n"
