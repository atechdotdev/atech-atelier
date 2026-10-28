"""simready — install parts from NVIDIA's SimReady assets
(huggingface.co/datasets/nvidia/simready-assets, CC BY 4.0) into the user's
parts library (user_parts.py).

WHAT HAPPENS ON INSTALL
    1. The asset's file list is read at the index's pinned dataset revision.
       Only what the geometry needs is downloaded (the root USD and its
       payloads: no textures, no thumbnails), each file checked against the
       hash the Hub records for it (sha256 for LFS files, the git blob id for
       the rest). A file that does not match is refused.
    2. USD is read by Pixar's usd-core in a CHILD Python process
       (simready_usd2stl.py): pxr never loads into Atelier itself. usd-core is
       not part of the app (it is ~230 MB installed); ensure_usd() installs
       one pinned version once, into the user data folder, from wheels whose
       sha256 is written in this file (USD_WHEELS).
    3. The meshes that are drawn (purpose default/render, visible, instance
       proxies included) are triangulated in world space, converted to mm and
       turned Y-up (Atelier's frame: x, z, -y for a Z-up stage), and written
       as one STL.
    4. user_parts.import_part() measures it and files it, with the licence,
       the attribution CC BY requires, and the dataset revision and file
       hashes it came from.

WHAT IS NOT TAKEN FROM THE DATASET
    Materials, physics and articulation. A part arrives as one rigid mesh.
    The dataset's own extents and mass are kept as its declaration; the size
    Atelier uses is measured from the mesh.

This module imports neither FreeCAD nor pxr.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

DATASET = "nvidia/simready-assets"
HUB = "https://huggingface.co"
HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "simready_index.json")
CONVERTER = os.path.join(HERE, "simready_usd2stl.py")
LICENCE = "CC BY 4.0"
ATTRIBUTION = ("%s by NVIDIA, from the NVIDIA SimReady Assets dataset "
               "(huggingface.co/datasets/nvidia/simready-assets), CC BY 4.0. "
               "Converted to a mesh by Atech Atelier (materials and physics "
               "not kept).")
TIMEOUT = 120

#: usd-core, pinned: one version, and the sha256 of each wheel the app can
#: use (CPython 3.11, the app's Python), copied from PyPI on 2026-10-28.
#: pip --require-hashes refuses any other file. A new version means new
#: hashes here, never fetched at run time.
USD_CORE = "usd-core==26.8"
USD_DIR_NAME = "usd-core-26.8"
USD_WHEELS = {
    "usd_core-26.8-cp311-none-macosx_10_15_universal2.whl":
        "781ddef732e3a6d300a5fa2d0c5b8af103aa8589a88c4af77ac6608f39293880",
    "usd_core-26.8-cp311-none-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl":
        "53ebbc130108c7e0e7b4af9a4fe3bdac2ae084a12db13496a50f895db527382e",
    "usd_core-26.8-cp311-none-win_amd64.whl":
        "d39cef20efdfc29473e92887487bb8c10c45e966c492b5356d32a52724c3578f",
}

#: Words that make an asset "electrical" for the browser's filter. A filter,
#: not a claim: the dataset says nothing about wiring.
ELECTRICAL = re.compile(
    r"electr|battery|sensor|camera|motor|fan|led|light|lamp|switch|button|"
    r"speaker|display|screen|monitor|cable|fuse|relay|circuit|pcb|robot|"
    r"charger|power|plug|socket_[ab]|usb|detector|alarm|keyboard|mouse|"
    r"computer|phone|terminal|outlet|bulb|scanner|siren|clock|heater|"
    r"multimeter|analyzer|kiosk|printer", re.I)


class SimReadyError(RuntimeError):
    """An asset that cannot be listed, downloaded, checked or converted."""


# ------------------------------------------------------------------ hub
_SSL = None


def _ssl_context():
    """Certificates for HTTPS. The app's Python is built with a CA path from
    its build machine, so certifi's bundle (shipped with it) is used when
    present; else the system default."""
    global _SSL
    if _SSL is None:
        import ssl
        try:
            import certifi
            _SSL = ssl.create_default_context(cafile=certifi.where())
        except Exception:                              # noqa: BLE001
            _SSL = ssl.create_default_context()
    return _SSL


def _get(url, timeout=TIMEOUT):
    if not url.startswith("https://"):
        raise SimReadyError("refusing a non-HTTPS URL: %s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "AtechAtelier"})
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())


def _json(url):
    with _retrying(url) as r:
        return json.load(r)


def _retrying(url, timeout=TIMEOUT, tries=6):
    """_get, waiting and retrying when the Hub says 429 (rate limit) or 5xx:
    its Retry-After when given, else 2, 4, 8... s."""
    import time
    import urllib.error
    for k in range(tries):
        try:
            return _get(url, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and exc.code < 500 or k == tries - 1:
                raise
            try:
                wait = float(exc.headers.get("Retry-After") or 0)
            except (TypeError, ValueError):
                wait = 0
            time.sleep(min(max(wait, 2 ** (k + 1)), 120))


def latest_revision():
    """The commit sha of the dataset's main branch now."""
    return _json("%s/api/datasets/%s/revision/main" % (HUB, DATASET))["sha"]


def list_remote(rev="main"):
    """Every asset folder name at `rev` (the tree API is paged)."""
    url = "%s/api/datasets/%s/tree/%s" % (HUB, DATASET, rev)
    names = []
    while url:
        with _retrying(url) as r:
            names += [x["path"] for x in json.load(r) if x["type"] == "directory"]
            m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link") or "")
        url = m.group(1) if m else None
    return names


def check_asset_name(name):
    """Asset names come from the index or the user: never a path."""
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,127}$", name or ""):
        raise SimReadyError("%r is not a SimReady asset name" % (name,))
    return name


def asset_files(name, rev):
    """[{path, size, sha256 | git_oid}] of every file of asset `name`."""
    check_asset_name(name)
    url = "%s/api/datasets/%s/tree/%s/%s?recursive=true" % (
        HUB, DATASET, rev, urllib.parse.quote(name))
    out = []
    for x in _json(url):
        if x.get("type") != "file":
            continue
        f = {"path": x["path"], "size": int(x.get("size") or 0)}
        lfs = x.get("lfs") or {}
        if lfs.get("oid"):
            f["sha256"] = lfs["oid"]
        else:
            f["git_oid"] = x.get("oid")
        out.append(f)
    if not out:
        raise SimReadyError("%s has no files at revision %s" % (name, rev[:12]))
    return out


def file_url(path, rev):
    return "%s/datasets/%s/resolve/%s/%s" % (
        HUB, DATASET, rev, urllib.parse.quote(path))


def is_root_usd(name, path):
    """The asset's root layer: a .usd/.usda directly in <name>/simready_usd/."""
    return bool(re.match(r"^%s/simready_usd/[^/]+\.usda?$" % re.escape(name), path))


def needed(name, path):
    """True for a file the geometry needs: USD layers under simready_usd/,
    never textures, material sources or thumbnails."""
    rel = path[len(name) + 1:] if path.startswith(name + "/") else path
    if not rel.startswith("simready_usd/"):
        return False
    if re.search(r"(^|/)(Textures|source_assets|\.thumbs)/", rel):
        return False
    return rel.endswith((".usd", ".usda", ".usdc"))


def _safe_join(root, rel):
    p = os.path.realpath(os.path.join(root, rel))
    if not p.startswith(os.path.realpath(root) + os.sep):
        raise SimReadyError("refusing a file outside the asset: %r" % rel)
    return p


def _verify(path, f):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) != f["size"]:
        return "size %d, the Hub says %d" % (len(data), f["size"])
    if f.get("sha256"):
        got = hashlib.sha256(data).hexdigest()
        return None if got == f["sha256"] else "sha256 %s, expected %s" % (
            got[:12], f["sha256"][:12])
    if f.get("git_oid"):
        got = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        return None if got == f["git_oid"] else "blob id %s, expected %s" % (
            got[:12], f["git_oid"][:12])
    return "the Hub gives no hash for it"


def download(name, rev, dest, progress=None):
    """Download the files asset `name` needs into dest/<name>/, each checked.
    Returns (root USD path, [{path, sha256|git_oid}])."""
    files = [f for f in asset_files(name, rev) if needed(name, f["path"])]
    roots = [f for f in files if is_root_usd(name, f["path"])]
    if not roots:
        raise SimReadyError("%s has no root USD file" % name)
    total = sum(f["size"] for f in files) or 1
    done = 0
    for f in files:
        p = _safe_join(dest, f["path"])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with _retrying(file_url(f["path"], rev)) as r, open(p, "wb") as fh:
            shutil.copyfileobj(r, fh, 1 << 16)
        bad = _verify(p, f)
        if bad:
            raise SimReadyError("%s: %s - not installed" % (f["path"], bad))
        done += f["size"]
        if progress:
            progress("Downloading %s" % name, done / total)
    prov = [{k: v for k, v in f.items() if k in ("path", "sha256", "git_oid")}
            for f in files]
    return _safe_join(dest, roots[0]["path"]), prov


# ------------------------------------------------------------- the index
_INDEX = None


def index():
    """The shipped index (build_simready_index.py): {revision, assets}."""
    global _INDEX
    if _INDEX is None:
        if not os.path.isfile(INDEX):
            raise SimReadyError("the SimReady index is missing from this "
                                "installation")
        with open(INDEX, encoding="utf-8") as fh:
            _INDEX = json.load(fh)
    return _INDEX


def label(name):
    """'power_battery_9v_a01' -> 'Power battery 9v (a01)'."""
    m = re.match(r"^(.*?)_([a-z]\d\d)$", name)
    base, var = (m.group(1), m.group(2)) if m else (name, "")
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", base).replace("_", " ").split()
    text = " ".join(words)
    text = text[:1].upper() + text[1:].lower() if text else name
    return "%s (%s)" % (text, var) if var else text


def is_electrical(name):
    """By its name; packaging (box_printer_*: paper boxes) never counts."""
    return bool(ELECTRICAL.search(name)) and not re.match(
        r"^(box|crate|pallet|pack|container)_", name)


def search(query="", electrical=False, max_mm=None, limit=200):
    """[(name, entry)] from the index matching every word of `query`
    (in the name or its label), optionally only electrical ones and only
    those whose largest side is at most max_mm. Smallest first."""
    words = [w for w in re.split(r"\W+", (query or "").lower()) if w]
    out = []
    for name, e in index()["assets"].items():
        hay = (name + " " + label(name)).lower().replace("_", " ")
        if any(w not in hay for w in words):
            continue
        if electrical and not is_electrical(name):
            continue
        size = e.get("size_mm")
        if max_mm is not None and (not size or max(size) > max_mm):
            continue
        out.append((name, e))
    out.sort(key=lambda kv: (max(kv[1].get("size_mm") or [1e9]), kv[0]))
    return out[:limit]


def to_library_extents(ext, mpu, up):
    """Dataset extents (stage units) -> [x, y, z] mm in Atelier's frame."""
    s = float(mpu) * 1000.0
    x, y, z = (abs(float(v)) * s for v in ext)
    return [round(v, 1) for v in ((x, z, y) if str(up).upper() == "Z" else (x, y, z))]


# ------------------------------------------------------------- usd-core
def python_exe():
    """A plain Python that can run the converter: the app's own bin/python
    (FreeCAD's sys.executable is the FreeCAD binary), else this one."""
    cands = []
    try:
        import FreeCAD
        cands.append(os.path.join(FreeCAD.getHomePath(), "bin", "python"))
    except Exception:                                  # noqa: BLE001
        pass
    exe = sys.executable or ""
    cands += [os.path.join(os.path.dirname(exe), "python"),
              os.path.join(os.path.dirname(exe), "python3")]
    if os.path.basename(exe).startswith("python"):
        cands.append(exe)
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise SimReadyError("no Python to read USD files with")


def usd_dir():
    """Where usd-core is installed for Atelier ($ATELIER_USD_DIR overrides)."""
    env = (os.environ.get("ATELIER_USD_DIR") or "").strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    import user_parts
    d = user_parts.parts_dir()
    if not d:
        raise SimReadyError("no user data folder for USD support")
    return os.path.join(os.path.dirname(d), "pylibs", USD_DIR_NAME)


def _child_env(extra=None):
    env = dict(os.environ)
    paths = [p for p in (extra or [])] + [usd_dir()]
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def usd_available(python=None):
    """True when the converter's Python can import pxr."""
    try:
        r = subprocess.run([python or python_exe(), "-I", "-c",
                            "import sys; sys.path[:0] = %r; import pxr.Usd"
                            % ([usd_dir()],)],
                           capture_output=True, timeout=60)
        return r.returncode == 0
    except Exception:                                  # noqa: BLE001
        return False


def ensure_usd(progress=None, python=None):
    """Install the pinned usd-core into usd_dir() once (pip, wheels only,
    hash-checked). Returns the folder."""
    python = python or python_exe()
    d = usd_dir()
    if usd_available(python):
        return d
    if progress:
        progress("Installing USD support (once, about 40 MB)", None)
    hashes = sorted(USD_WHEELS.values())
    tmp = tempfile.mkdtemp(prefix="atelier_usd_")
    try:
        req = os.path.join(tmp, "requirements.txt")
        with open(req, "w") as fh:
            fh.write("%s %s\n" % (USD_CORE, " ".join("--hash=sha256:%s" % h
                                                      for h in hashes)))
        stage = os.path.join(tmp, "site")
        r = subprocess.run(
            [python, "-I", "-m", "pip", "install", "--quiet", "--no-deps",
             "--only-binary", ":all:", "--require-hashes", "--no-cache-dir",
             "--disable-pip-version-check", "--target", stage, "-r", req],
            capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            raise SimReadyError("could not install USD support: %s"
                                % (r.stderr or r.stdout).strip()[-600:])
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.move(stage, d)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not usd_available(python):
        raise SimReadyError("USD support was installed but does not load")
    return d


def convert(root_usd, out_stl, python=None, timeout=600):
    """root USD -> binary STL in mm, Y up (simready_usd2stl.py in a child
    Python). Returns the converter's report (triangles, size_mm, units...)."""
    python = python or python_exe()
    r = subprocess.run([python, "-I", CONVERTER, root_usd, out_stl, usd_dir()],
                       capture_output=True, text=True, timeout=timeout,
                       env=_child_env())
    line = [ln for ln in (r.stdout or "").splitlines()
            if ln.startswith("SIMREADY_STL=")]
    if r.returncode != 0 or not line:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-6:]
        raise SimReadyError("could not convert %s: %s"
                            % (os.path.basename(root_usd), " | ".join(tail)))
    rep = json.loads(line[-1].split("=", 1)[1])
    if rep.get("error"):
        raise SimReadyError(rep["error"])
    return rep


# ---------------------------------------------------------------- install
def part_name(asset):
    """The user-parts name of a SimReady asset: 'sr_' + its lowercased name,
    cut to user_parts' 48 characters."""
    import user_parts
    return ("sr_" + user_parts.slug(asset))[:48].rstrip("_")


def guess_category(asset):
    a = asset.lower()
    if re.search(r"battery|charger|power|outlet|fuse", a):
        return "power"
    if re.search(r"motor|fan|pump", a):
        return "motor"
    if re.search(r"bolt|nut|screw|bearing|extrusion|seal|belt|wheel|washer", a):
        return "mechanical"
    return "electronics" if is_electrical(asset) else "mechanical"


def install(asset, progress=None, rev=None, python=None, replace=False):
    """Download, check, convert and file SimReady asset `asset` as a user
    part. Returns (part name, user_parts entry)."""
    import user_parts
    check_asset_name(asset)
    idx = index()
    entry = idx["assets"].get(asset)
    if entry is None and rev is None:
        raise SimReadyError("%s is not in the SimReady index" % asset)
    rev = rev or idx["revision"]
    name = part_name(asset)
    if name in user_parts.specs() and not replace:
        return name, user_parts.specs()[name]
    python = python or python_exe()
    ensure_usd(progress, python)
    tmp = tempfile.mkdtemp(prefix="simready_")
    try:
        root, files = download(asset, rev, tmp, progress)
        if progress:
            progress("Converting %s" % asset, None)
        stl = os.path.join(tmp, name + ".stl")
        rep = convert(root, stl, python)
        shown = label(asset)
        sp = user_parts.import_part(
            stl, name=name, display_name=shown,
            category=guess_category(asset),
            description="%s from NVIDIA SimReady (a mesh of the real object; "
                        "not an Atech module)." % shown,
            agent_notes=("A mesh of NVIDIA's SimReady model, made for "
                         "simulation, not from a datasheet: its size can "
                         "differ from the real part by millimetres. Where a "
                         "fit matters (a battery bay, a snap, a bore), ask "
                         "for or use the real part's datasheet numbers and "
                         "give the pocket clearance."),
            licence=LICENCE,
            source_url="%s/datasets/%s/tree/%s/%s" % (HUB, DATASET, rev, asset),
            recentre=True, replace=replace,
            extra={"simready": {
                "asset": asset, "revision": rev, "files": files,
                "attribution": ATTRIBUTION % shown,
                "dataset_size_mm": (entry or {}).get("size_mm"),
                "mass_kg": (entry or {}).get("mass_kg"),
                "wikidata": (entry or {}).get("qcode"),
                "converted": {k: rep.get(k) for k in
                              ("triangles", "meshes", "meters_per_unit", "up_axis")},
            }})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if progress:
        progress("Installed %s" % sp["display_name"], 1.0)
    return name, sp


def installed():
    """{asset: part name} of the SimReady assets in the user's parts."""
    import user_parts
    out = {}
    for n, sp in user_parts.specs().items():
        a = (sp.get("simready") or {}).get("asset")
        if a:
            out[a] = n
    return out


def thumbnail(asset, dest_dir):
    """Download the asset's thumbnail PNG (cached in dest_dir); its path, or
    None when the index names none."""
    check_asset_name(asset)
    e = index()["assets"].get(asset) or {}
    if not e.get("thumb"):
        return None
    p = os.path.join(dest_dir, asset + ".png")
    if not os.path.isfile(p):
        os.makedirs(dest_dir, exist_ok=True)
        with _retrying(file_url("%s/%s" % (asset, e["thumb"]), index()["revision"]),
                  timeout=60) as r:
            data = r.read()
        if not data.startswith(b"\x89PNG"):
            raise SimReadyError("%s: the thumbnail is not a PNG" % asset)
        with open(p, "wb") as fh:
            fh.write(data)
    return p
