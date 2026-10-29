"""shelf - off-the-shelf parts (Arduino, Raspberry Pi, servos, batteries,
switches, sensors...) from the FreeCAD Parts Library, installed into the
user's own parts (user_parts.py).

SOURCE
    github.com/FreeCAD/FreeCAD-library at REVISION, CC BY 3.0: "each Part is
    copyrighted by and should be attributed to its respective author(s)",
    found in the git history (LICENSE-Assets). Only a CURATED list is
    offered: shelf_index.json, written by build_shelf_index.py, holds for
    each part its STEP path, git blob id and size (checked on download),
    the size MEASURED from its mesh, its authors from the git history, a
    picture drawn from its mesh (shelf_pictures/), and what we say about it
    (description, wiring, notes for the agent).

INSTALL
    download the STEP (HTTPS, git blob id and size checked) -> tessellate it
    in a child freecadcmd (shelf_step2stl.py; in-process when none is
    given) -> user_parts.import_part(extra={"shelf": ...}): the part keeps
    its source, revision, blob id, authors and attribution.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "shelf_index.json")
CONVERTER = os.path.join(HERE, "shelf_step2stl.py")
REPO = "FreeCAD/FreeCAD-library"
REVISION = "f5ca01cdcaa2f69b9295a6382719c2d90628780c"
LICENCE = "CC BY 3.0"
SOURCE = "the FreeCAD Parts Library (github.com/FreeCAD/FreeCAD-library)"
PREFIX = "ots_"
TIMEOUT = 300

#: what the dialog's category filter offers, in order: key -> label
GROUPS = (("boards", "Boards"), ("sensors", "Sensors"), ("motors", "Motors and servos"),
          ("power", "Power"), ("controls", "Buttons and switches"),
          ("displays", "Lights and displays"), ("connectors", "Connectors"),
          ("mechanical", "Mechanical"))


class ShelfError(Exception):
    pass


# ------------------------------------------------------------------ HTTP
def _get(url, timeout=TIMEOUT):
    import simready                      # its certifi context and retries
    if not url.startswith("https://"):
        raise ShelfError("refusing a non-HTTPS URL: %s" % url)
    return simready._retrying(url, timeout)


def file_url(path, rev=REVISION):
    return "https://raw.githubusercontent.com/%s/%s/%s" % (
        REPO, rev, urllib.parse.quote(path))


def page_url(path, rev=REVISION):
    return "https://github.com/%s/blob/%s/%s" % (REPO, rev, urllib.parse.quote(path))


def blob_id(data):
    """git's id of a file's bytes (what the tree API lists)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def fetch(path, git_oid, size, dest, rev=REVISION):
    """Download repo file `path` to dest, checked against its blob id and
    size; the problem as a ShelfError, nothing left behind."""
    with _get(file_url(path, rev)) as r:
        data = r.read()
    if len(data) != size:
        raise ShelfError("%s: %d bytes, the library lists %d - not installed"
                         % (path, len(data), size))
    got = blob_id(data)
    if got != git_oid:
        raise ShelfError("%s: blob id %s, expected %s - not installed"
                         % (path, got[:12], git_oid[:12]))
    with open(dest, "wb") as fh:
        fh.write(data)
    return dest


# ----------------------------------------------------------------- index
_INDEX = None


def index():
    """The shipped index: {revision, parts: {key: entry}}."""
    global _INDEX
    if _INDEX is None:
        if not os.path.isfile(INDEX):
            raise ShelfError("the off-the-shelf parts index is missing from "
                             "this installation")
        with open(INDEX, encoding="utf-8") as fh:
            _INDEX = json.load(fh)
    return _INDEX


def check_key(key):
    if not re.match(r"^[a-z][a-z0-9_]{1,40}$", key or "") or key not in index()["parts"]:
        raise ShelfError("%r is not an off-the-shelf part" % (key,))
    return key


def label(key):
    return (index()["parts"].get(key) or {}).get("display_name") or key


def search(query="", group=None, limit=500):
    """[(key, entry)] matching every word of `query` (name, description,
    group), optionally one GROUPS key. By group, then name."""
    words = [w for w in re.split(r"\W+", (query or "").lower()) if w]
    order = [g for g, _ in GROUPS]
    out = []
    for key, e in index()["parts"].items():
        if group and e.get("group") != group:
            continue
        hay = " ".join((key.replace("_", " "), e.get("display_name", ""),
                        e.get("description", ""), e.get("group", ""))).lower()
        if any(w not in hay for w in words):
            continue
        out.append((key, e))
    out.sort(key=lambda kv: (order.index(kv[1]["group"]) if kv[1].get("group") in order
                             else 99, kv[1].get("display_name", kv[0]).lower()))
    return out[:limit]


def attribution(entry):
    who = ", ".join(entry.get("authors") or []) or "its authors"
    return '"%s" by %s, from %s, %s' % (entry.get("display_name"), who, SOURCE, LICENCE)


# --------------------------------------------------------------- install
def tessellate(step, stl, freecadcmd=None, timeout=900):
    """STEP -> STL. In a child freecadcmd when given (the app passes the
    bundled one), else in this process (tests and scripts under FreeCAD).
    Returns {"triangles", "size_mm"}."""
    if not freecadcmd:
        import user_parts
        mesh = user_parts.read_mesh(step)
        mesh.write(stl)
        bb = mesh.BoundBox
        return {"triangles": int(mesh.CountFacets),
                "size_mm": [bb.XLength, bb.YLength, bb.ZLength]}
    env = dict(os.environ, SHELF_IN=step, SHELF_OUT=stl,
               QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([freecadcmd, CONVERTER], env=env, capture_output=True,
                         text=True, timeout=timeout)
    m = re.search(r"^SHELF_STL=(.*)$", out.stdout or "", re.M)
    rep = json.loads(m.group(1)) if m else {
        "error": "the mesher printed no result (exit %s): %s"
                 % (out.returncode, (out.stderr or out.stdout or "")[-300:])}
    if rep.get("error"):
        raise ShelfError("could not mesh the STEP file: %s" % rep["error"])
    return rep


def part_name(key):
    return PREFIX + key


def install(key, progress=None, freecadcmd=None, replace=False):
    """Download, check, mesh and file off-the-shelf part `key` as a user
    part. Returns (part name, user_parts entry)."""
    import user_parts
    check_key(key)
    e = index()["parts"][key]
    rev = index()["revision"]
    name = part_name(key)
    if name in user_parts.specs() and not replace:
        return name, user_parts.specs()[name]
    tmp = tempfile.mkdtemp(prefix="shelf_")
    try:
        if progress:
            progress("Downloading %s (%.1f MB)" % (e["display_name"], e["bytes"] / 1e6), None)
        step = fetch(e["path"], e["git_oid"], e["bytes"],
                     os.path.join(tmp, key + os.path.splitext(e["path"])[1].lower()), rev)
        if progress:
            progress("Meshing %s" % e["display_name"], None)
        stl = os.path.join(tmp, name + ".stl")
        rep = tessellate(step, stl, freecadcmd)
        sp = user_parts.import_part(
            stl, name=name, display_name=e["display_name"],
            category=e["category"], description=e.get("description", ""),
            agent_notes=e.get("agent_notes", ""),
            electrical=e.get("electrical") or None,
            licence=LICENCE, source_url=page_url(e["path"], rev),
            recentre=True, replace=replace,
            extra={"shelf": {"key": key, "path": e["path"], "revision": rev,
                             "git_oid": e["git_oid"], "authors": e.get("authors") or [],
                             "attribution": attribution(e),
                             "triangles": rep.get("triangles")}})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if progress:
        progress("Installed %s" % sp["display_name"], 1.0)
    return name, sp


def installed():
    """{key: part name} of the off-the-shelf parts in the user's parts."""
    import user_parts
    out = {}
    for n, sp in user_parts.specs().items():
        k = (sp.get("shelf") or {}).get("key")
        if k:
            out[k] = n
    return out


def has_picture(entry):
    return bool(entry.get("picture") or entry.get("thumb"))


def thumbnail(key, dest_dir):
    """The part's picture: the one shipped with Atelier (drawn from its mesh
    by build_shelf_index.py), else the library's own (downloaded, cached in
    dest_dir); None when there is neither."""
    check_key(key)
    e = index()["parts"][key]
    if e.get("picture"):
        p = os.path.realpath(os.path.join(HERE, e["picture"]))
        if p.startswith(os.path.join(HERE, "shelf_pictures") + os.sep) and os.path.isfile(p):
            return p
    if not e.get("thumb"):
        return None
    p = os.path.join(dest_dir, "shelf_" + key + ".png")
    if not os.path.isfile(p):
        os.makedirs(dest_dir, exist_ok=True)
        with _get(file_url(e["thumb"], index()["revision"]), 60) as r:
            data = r.read()
        if not data.startswith(b"\x89PNG"):
            raise ShelfError("%s: the picture is not a PNG" % key)
        with open(p, "wb") as fh:
            fh.write(data)
    return p
