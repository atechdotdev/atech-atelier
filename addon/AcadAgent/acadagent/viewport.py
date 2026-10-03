"""viewport — make the 3D view worth looking at, and spinnable.

The branded build shipped with a dead black viewport occupying ~80% of the
window: correct behaviour (no document is open) presented as a blank screen.

FreeCAD's own 3D view already orbits, spins and zooms — it is a Coin3D/OCCT
view over the real B-rep, which is strictly better than a mesh in a browser.
Qt WebEngine is NOT shipped in the AppImage (`from PySide6 import
QtWebEngineWidgets` raises ImportError; the .py beside it is a FreeCAD
compatibility stub), so an embedded three.js viewer would mean bundling
Chromium. Measured 2026-09-24 — see the verification record.

So this module does not build a viewer. It gives the existing one something to
show, a brand-consistent background, and one-key standard views.

Everything here is VIEW-ONLY. It opens documents and moves the camera; it
never creates, edits or measures geometry. Numbers come from `bin/cad`.
"""
import os
import glob
import json

import FreeCAD
import FreeCADGui


# The reference machine: the repo's measured crane fixture ("lift 2.0 kg
# through 400 mm at 250 mm reach"). Parts are .brep, written by
# cockpit/fixtures/crane. Users see it as "the sample crane".
#
# The addon runs from TWO locations: the repo during development, and
# usr/Mod/AcadAgent inside the built AppImage. A single repo-relative path is
# correct in one and silently wrong in the other — measured: it resolved to 0
# parts from the bundle. So search candidates and take the first that exists.
_REL = os.path.join("cockpit", "fixtures", "crane", "build")


def _candidate_roots(file=None):
    """Where the fixture may live. The addon's REAL location is used (R55):
    a dev install symlinks ~/.local/share/FreeCAD/Mod/AcadAgent to the repo's
    addon/AcadAgent, and walking up from the symlink's abspath lands in the
    user's FreeCAD data dir, not the repo - the sample crane then read as
    missing. The link's own location is kept as a later candidate for a
    bundle whose fixtures sit beside the link."""
    file = file or __file__
    roots = []
    # 1. explicit override, for a bundle installed away from the repo
    env = os.environ.get("ATECH_FIXTURES")
    if env:
        roots.append(env)
    for here in (os.path.dirname(os.path.realpath(file)),
                 os.path.dirname(os.path.abspath(file))):
        # 2. addon living in the repo: acadagent/ -> AcadAgent/ -> addon/ -> repo
        # 3. addon bundled in the AppImage: a copy shipped beside the addon
        #    (usr/Mod/AcadAgent/fixtures); walking out to a sibling checkout
        #    is NOT valid.
        for cand in (os.path.normpath(os.path.join(here, "..", "..", "..")),
                     os.path.normpath(os.path.join(here, ".."))):
            if cand not in roots:
                roots.append(cand)
    # No hard-coded developer checkout: a bundle that ships without the
    # fixture says so (ATECH_FIXTURES points it at one), R27.
    return roots


def _crane_build_dir():
    """First existing fixtures dir, or None. A missing fixture stays missing."""
    for root in _candidate_roots():
        cand = os.path.join(root, _REL)
        if os.path.isdir(cand):
            return cand
        # allow a bundled copy placed directly beside the addon
        flat = os.path.join(root, "fixtures", "crane", "build")
        if os.path.isdir(flat):
            return flat
    return None

# Atech Atelier brand, matching docs/prd/assets/atech_studio.html and the theme
# tokens. The gradient is the page background, so viewport and chrome agree.
_BG_TOP = (0.09, 0.10, 0.15)     # #171A26
_BG_BOTTOM = (0.06, 0.06, 0.09)  # #0F1017
_AXIS_INK = (0.96, 0.96, 0.96)  # #F5F5F5, the dark text token: reads on the fallback ground


def _gui():
    """The Gui module, or None in console mode. Never assume a GUI."""
    try:
        import FreeCADGui as g
        return g if g.getMainWindow() is not None else None
    except Exception:
        return None


# Every preference apply_view_theme() writes, with its parameter type. These
# are the user's GLOBAL view preferences, shared by every workbench, so they
# are snapshotted before the first write and put back on deactivate and at
# quit (R31). The chosen defaults below are the owner's product decision and
# are left as they are; only the restore is new.
_VIEW_GROUP = "User parameter:BaseApp/Preferences/View"
_OWN = "User parameter:BaseApp/Preferences/Mod/AcadAgent"
_SNAP_KEY = "ViewPrefsSnapshot"
# Background values this addon left in place on restore because the user
# had none of their own (R108), JSON {key: value}. A snapshot taken later
# reads them as "absent" again, so they never pass for the user's choice.
_SEEDED_KEY = "ViewBackgroundSeeded"
# AxisLetterColor (R161) belongs with the ground: the corner axis letters
# are drawn straight onto it, so a dark ground kept for Part (R108) keeps
# its light letters too. FreeCAD's default is black (View3DSettings.cpp:
# GetUnsigned("AxisLetterColor", 0x00000000)); on the dark ground that is
# MEASURED 1.07:1 in GUI shots r5_11 and r6_21 - round 5 had it as well.
BACKGROUND_KEYS = ("Gradient", "BackgroundColor", "BackgroundColor2",
                   "BackgroundColor3", "AxisLetterColor")
VIEW_KEYS = (
    ("Gradient", "Bool"), ("BackgroundColor", "Unsigned"),
    ("BackgroundColor2", "Unsigned"), ("BackgroundColor3", "Unsigned"),
    ("AxisLetterColor", "Unsigned"),
    ("NavigationStyle", "String"), ("OrbitStyle", "Int"),
    ("RotationMode", "Int"), ("ZoomAtCursor", "Bool"), ("ZoomStep", "Float"),
    ("InvertZoom", "Bool"), ("ShowNaviCube", "Bool"), ("AntiAliasing", "Int"),
)
# GetContents() type names, MEASURED in Base/ParameterPy.cpp (FreeCAD 1.1).
_KIND_OF = {"Boolean": "Bool", "Integer": "Int", "Unsigned Long": "Unsigned",
            "Float": "Float", "String": "String"}
# FreeCAD's own fallback when NavigationStyle is absent (View3DSettings.cpp:
# GetASCII("NavigationStyle", CADNavigationStyle)).
_FREECAD_DEFAULT_NAV = "Gui::CADNavigationStyle"


def _contents(p):
    """{name: (kind, value)} of a parameter group, kinds as in VIEW_KEYS."""
    rows = p.GetContents() or []
    return {name: (_KIND_OF.get(kind), val) for kind, name, val in rows}


def snapshot_view_prefs():
    """Record the user's values for VIEW_KEYS before we write any of them.

    A snapshot already stored (a session that never restored: crash or
    kill) is the truth and is kept; re-reading the group
    then would record our own values as the user's. Absent keys are stored
    as None so restore removes them instead of inventing a value.

    R180: a kept snapshot written by an older build lacks the keys that
    joined VIEW_KEYS since (AxisLetterColor, R161). That build never wrote
    them, so the group still holds the user's own value: record it now,
    before apply_view_theme() overwrites it, or restore has nothing to
    give back and our value stays in the user's global prefs for good."""
    try:
        own = FreeCAD.ParamGet(_OWN)
        kept = saved_view_prefs() if own.GetString(_SNAP_KEY, "") else None
        if own.GetString(_SNAP_KEY, "") and kept is None:
            return False                  # unreadable: leave it untouched
        missing = [(k, kind) for k, kind in VIEW_KEYS
                   if kept is None or k not in kept]
        if not missing:
            return False
        have = _contents(FreeCAD.ParamGet(_VIEW_GROUP))
        seeded = _seeded(own)
        snap = dict(kept or {})
        for key, kind in missing:
            got = have.get(key)
            snap[key] = [kind, got[1]] if got and got[0] == kind else None
            if snap[key] is not None and key in seeded \
                    and seeded[key] == got[1]:
                snap[key] = None          # ours, left by a dark restore
        own.SetString(_SNAP_KEY, json.dumps(snap, sort_keys=True))
        return kept is None
    except Exception as exc:                           # noqa: BLE001
        FreeCAD.Console.PrintLog("Atech: view prefs not snapshotted (%s)\n" % exc)
        return False


def _seeded(own):
    try:
        raw = own.GetString(_SEEDED_KEY, "")
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except Exception:                                  # noqa: BLE001
        return {}


def _dark():
    try:
        from . import style
        return style.mode() == "dark"
    except Exception:                                  # noqa: BLE001
        return False


def saved_view_prefs():
    try:
        raw = FreeCAD.ParamGet(_OWN).GetString(_SNAP_KEY, "")
        data = json.loads(raw) if raw else None
        return data if isinstance(data, dict) else None
    except Exception:                                  # noqa: BLE001
        return None


def restore_view_prefs(clear=True):
    """Put the user's view preferences back. Returns True when a snapshot
    was applied. `clear=False` keeps the snapshot; deactivate and quit
    both clear it (a snapshot kept past a clean quit goes stale)."""
    snap = saved_view_prefs()
    if snap is None:
        return False
    try:
        p = FreeCAD.ParamGet(_VIEW_GROUP)
        own = FreeCAD.ParamGet(_OWN)
        have = _contents(p)
        # R108: a background the user never set is FreeCAD's built-in
        # light blue-violet gradient once removed - a bright hole in a dark
        # app (Part after a dark-mode switch). In dark mode such keys keep
        # the Studio's dark values instead; recorded in _SEEDED_KEY so the
        # next snapshot does not mistake them for the user's. A background
        # the user DID set is always given back.
        keep_bg = _dark() and all(snap.get(k) is None
                                  for k in BACKGROUND_KEYS)
        seeded = {}
        for key, kind in VIEW_KEYS:
            # R180: a snapshot written before `key` joined VIEW_KEYS
            # (AxisLetterColor, R161) has no entry for it at all - that is
            # "not recorded", not "the user had none". Removing it would
            # throw away the user's own value; leave it alone.
            if key not in snap:
                continue
            entry = snap.get(key)
            if entry is None:
                if keep_bg and key in BACKGROUND_KEYS \
                        and have.get(key, (None,))[0] == kind:
                    seeded[key] = have[key][1]
                    continue
                getattr(p, "Rem" + kind)(key)
            else:
                getattr(p, "Set" + kind)(key, entry[1])
        if seeded:
            own.SetString(_SEEDED_KEY, json.dumps(seeded, sort_keys=True))
        else:
            own.RemString(_SEEDED_KEY)
        if clear:
            own.RemString(_SNAP_KEY)
    except Exception as exc:                           # noqa: BLE001
        FreeCAD.Console.PrintWarning("Atech: view prefs not restored (%s)\n" % exc)
        return False
    nav = snap.get("NavigationStyle")
    g = _gui()
    if g is not None:
        try:
            _apply_nav_to_open_views(g, nav[1] if nav else _FREECAD_DEFAULT_NAV)
        except Exception as exc:                       # noqa: BLE001
            FreeCAD.Console.PrintLog("Atech: nav style not restored (%s)\n" % exc)
    return True


def apply_view_theme():
    """Brand the 3D view and make mouse orbit / scroll-zoom behave well.

    Every key below was read out of FreeCAD's own View3DSettings.cpp rather
    than guessed — a wrong preference name is silently ignored, which looks
    exactly like a setting that had no effect.

    These are global preferences: snapshot_view_prefs() records the user's
    values first, and shell.uninstall() / quit put them back (R31).

    Report-only: never raises into startup.
    """
    g = _gui()
    if g is None:
        return False
    snapshot_view_prefs()
    try:
        p = FreeCAD.ParamGet(_VIEW_GROUP)
        have = _contents(p)

        def put(kind, key, val):
            # Write only a value that differs (S23): every Set notifies
            # FreeCAD's parameter observers, and a restyle (theme flip,
            # every activation) used to rewrite all twelve - AntiAliasing
            # included, which re-reads the multisampling setup for nothing.
            if have.get(key) != (kind, val):
                getattr(p, "Set" + kind)(key, val)

        # --- brand background (Gradient is a bool; View3DSettings.cpp:393)
        # Follows the app's light/dark mode (style.py), so the viewport is
        # the same material as the chrome around it rather than a dark hole
        # in a light window.
        top, bot, ink = _BG_TOP, _BG_BOTTOM, _AXIS_INK
        try:
            from . import style
            t = style.tokens()
            top, bot = _hex(t["view_top"]), _hex(t["view_bot"])
            ink = _hex(t["text"])
        except Exception:                              # noqa: BLE001
            pass
        put("Bool", "Gradient", True)
        put("Unsigned", "BackgroundColor", _pack(top))
        put("Unsigned", "BackgroundColor2", _pack(top))
        put("Unsigned", "BackgroundColor3", _pack(bot))
        # R161: the X/Y/Z letters of the corner axis follow the text token,
        # so they read on either ground (FreeCAD re-colours open views on
        # this parameter's change: View3DSettings.cpp OnChange).
        put("Unsigned", "AxisLetterColor", _pack(ink))

        # --- mouse: drag to spin, scroll to zoom
        # Gesture style: left-drag orbits, right-drag pans, wheel zooms, a
        # plain click still selects. CAD style (FreeCAD's default) needs
        # middle+left held together to orbit, which reads as "can't move it".
        put("String", "NavigationStyle", NAV_STYLE)  # Python API is SetString; SetASCII is the C++ name
        # Trackball-style free orbit (OrbitStyle enum, View3DSettings.cpp:294).
        put("Int", "OrbitStyle", 1)
        # Rotate about the point under the cursor, not the origin — otherwise a
        # drag swings a large model off-screen and reads as "spinning is broken".
        put("Int", "RotationMode", 2)
        # Wheel zooms toward the cursor rather than the view centre.
        put("Bool", "ZoomAtCursor", True)
        put("Float", "ZoomStep", 0.2)
        # MEASURED: with InvertZoom False, wheel-up zoomed OUT (view scale went
        # 2077 mm -> 6897 mm). True gives wheel-up = zoom in, which is the
        # convention every other 3D tool uses. FreeCAD's own default is True.
        put("Bool", "InvertZoom", True)

        # --- discoverability: the nav cube advertises that the view rotates.
        put("Bool", "ShowNaviCube", True)
        # Antialiasing is an INT enum (Gui::AntiAliasing), not a bool.
        # 3 = MSAA4x (Multisample.h:48). "UseAntialiasing" is not a real key.
        # It only takes effect for views opened afterwards, so it is written
        # once, never re-written by a theme apply (S23).
        put("Int", "AntiAliasing", 3)
        _apply_nav_to_open_views(g)
        return True
    except Exception as exc:
        FreeCAD.Console.PrintWarning("Atech: view theme not applied (%s)\n" % exc)
        return False


NAV_STYLE = "Gui::GestureNavigationStyle"


def _apply_nav_to_open_views(g, nav=NAV_STYLE):
    """The NavigationStyle preference is read only when a view is created, so
    views already open (the reference model at startup) keep the old style
    unless they are switched explicitly."""
    for doc_name in list(FreeCAD.listDocuments()):
        gdoc = g.getDocument(doc_name)
        if gdoc is None:
            continue
        for view in gdoc.mdiViewsOfType("Gui::View3DInventor"):
            try:
                view.setNavigationType(nav)
            except Exception as exc:                   # noqa: BLE001
                FreeCAD.Console.PrintLog("Atech: nav style not set (%s)\n" % exc)


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _pack(rgb):
    """(r,g,b) floats 0..1 -> FreeCAD's packed RGBA uint32."""
    r, g, b = (max(0, min(255, int(round(c * 255)))) for c in rgb)
    return (r << 24) | (g << 16) | (b << 8) | 255


def crane_parts():
    """The .brep files of the reference machine, or [] if not built.

    Absent stays absent: if the fixture has never been built there is nothing
    to show, and we say so rather than substituting a box.
    """
    d = _crane_build_dir()
    if d is None:
        return []
    # R90: the build dir is never cleaned, so a glob also picks up parts an
    # EARLIER crane design wrote there. MEASURED on the repo fixture: 12 of
    # 36 .brep files (2026-08-22) are not in the current parts.json, and
    # one of them, tip_sheave, sits 163.64 mm from every current part - the
    # sheave that floated away in GUI shot r2_06. parts.json is the build's
    # own manifest (build_crane.py writes it with the .brep files), so when
    # it is readable it decides; without it, the glob is all there is.
    listed = _manifest_breps(d)
    if listed is not None:
        return sorted(f for f in listed if os.path.isfile(f))
    return sorted(glob.glob(os.path.join(d, "*.brep")))


def _manifest_breps(d):
    """Paths of the .brep files the build's parts.json lists, or None when
    there is no usable manifest (absent, unreadable, or naming no brep)."""
    try:
        with open(os.path.join(d, "parts.json"), encoding="utf-8") as fh:
            parts = json.load(fh).get("parts")
        names = [os.path.basename(p["brep"]) for p in parts
                 if isinstance(p, dict) and isinstance(p.get("brep"), str)]
    except Exception:                                  # noqa: BLE001
        return None
    return [os.path.join(d, n) for n in names] or None


def open_reference_model(doc_name="SampleCrane"):
    """Load the reference machine into a document and frame it.

    Returns (doc, n_parts, skipped). Raises RuntimeError only when there is
    nothing to load, so the caller can tell the user the truth.
    """
    import Part

    files = crane_parts()
    if not files:
        raise RuntimeError(
            "the sample crane is not included in this installation"
        )

    doc = FreeCAD.newDocument(doc_name)
    made, skipped = 0, []
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        try:
            shape = Part.Shape()
            shape.read(f)
            # A shape that read but is empty would display as nothing while
            # counting as a part. Check, don't assume.
            if shape.isNull() or not shape.Solids:
                skipped.append(name)
                continue
            obj = doc.addObject("Part::Feature", name)
            obj.Shape = shape
            made += 1
        except Exception as exc:
            skipped.append("%s (%s)" % (name, exc))

    doc.recompute()
    if made == 0:
        FreeCAD.closeDocument(doc.Name)
        raise RuntimeError("no part of the sample crane could be loaded")

    _style_document(doc)
    _mark_unmodified(doc)
    iso_and_fit()
    return doc, made, skipped


def _mark_unmodified(doc):
    """R196: the sample opened as "SampleCrane : 1*" (GUI r9_04).

    The cause is FreeCAD's, and it is by design: the App document is clean
    after the load (MEASURED headless: doc.isTouched() False, no object
    touched), but Gui::Document::setModified(true) runs on every new object,
    on every property change and on every touch (tools/freecad-src
    src/Gui/Document.cpp slotNewObject / slotChangedObject /
    slotTouchedObject), so a document built in code always reads unsaved.
    Nothing the user did is unsaved here - it is a copy of the fixture -
    so clear the GUI flag once loading and styling are done. Their first
    edit sets it again the normal way, and closing the untouched sample no
    longer asks to save it."""
    g = _gui()
    if g is None:
        return False
    try:
        gdoc = g.getDocument(doc.Name)
        if gdoc is None:
            return False
        gdoc.Modified = False
        return not gdoc.Modified
    except Exception as exc:                           # noqa: BLE001
        try:
            FreeCAD.Console.PrintLog("Atech: sample left modified (%s)\n" % exc)
        except Exception:                              # noqa: BLE001
            pass
        return False


def _style_document(doc):
    """Brand-consistent part colours. View-only; no geometry is touched."""
    g = _gui()
    if g is None:
        return
    # Atech ink/brand ramp: neutral bodies, brand blue for moving parts so the
    # drivetrain reads at a glance.
    moving = ("gear", "pinion", "screw", "nut", "carriage", "sheave",
              "motor", "ring", "hook", "rope", "cable")
    for obj in doc.Objects:
        try:
            vo = obj.ViewObject
            if vo is None:
                continue
            low = obj.Name.lower()
            if any(k in low for k in moving):
                vo.ShapeColor = (0.35, 0.64, 1.00)   # #5AA2FF
            else:
                vo.ShapeColor = (0.62, 0.64, 0.72)   # neutral steel
            vo.Transparency = 0
        except Exception:
            continue


# ----------------------------------------------------------------- camera
# Thin wrappers over FreeCAD's own view commands. They exist so the panel and
# the menu share one call path, and so each one no-ops safely without a view.

def _view():
    g = _gui()
    if g is None:
        return None
    try:
        return g.ActiveDocument.ActiveView if g.ActiveDocument else None
    except Exception:
        return None


def _send(cmd):
    v = _view()
    if v is None:
        return False
    try:
        getattr(v, cmd)()
        return True
    except Exception:
        return False


def _log(msg):
    try:
        FreeCAD.Console.PrintLog("Atech viewport: %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


# ---- vector math (pure: tested headless without a view) ----------------
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b, k=1.0):
    return (a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _unit(a):
    n = _dot(a, a) ** 0.5
    if n < 1e-12:
        raise ValueError("zero vector")
    return (a[0] / n, a[1] / n, a[2] / n)


def look_quaternion(look, up=(0.0, 0.0, 1.0)):
    """Camera orientation (x, y, z, w) that looks along `look` with world
    `up` kept up. Coin cameras look down their -Z with +Y up.

    FreeCAD's setViewDirection() uses the SHORTEST rotation from -Z to the
    direction, which leaves the roll to chance: the Modules page's first
    frame came up with Z pointing down (dogfood D13). This keeps the roll."""
    zc = _unit((-look[0], -look[1], -look[2]))          # camera back
    if abs(_dot(_unit(up), zc)) > 0.999:               # looking straight
        up = (0.0, 1.0, 0.0)                           # along up: use +Y
    xc = _unit(_cross(up, zc))                          # right
    yc = _cross(zc, xc)                                 # true up
    m00, m01, m02 = xc[0], yc[0], zc[0]
    m10, m11, m12 = xc[1], yc[1], zc[1]
    m20, m21, m22 = xc[2], yc[2], zc[2]
    tr = m00 + m11 + m22
    if tr > 0:
        s = (tr + 1.0) ** 0.5 * 2
        w, x = 0.25 * s, (m21 - m12) / s
        y, z = (m02 - m20) / s, (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = (1.0 + m00 - m11 - m22) ** 0.5 * 2
        w, x = (m21 - m12) / s, 0.25 * s
        y, z = (m01 + m10) / s, (m02 + m20) / s
    elif m11 > m22:
        s = (1.0 + m11 - m00 - m22) ** 0.5 * 2
        w, x = (m02 - m20) / s, (m01 + m10) / s
        y, z = 0.25 * s, (m12 + m21) / s
    else:
        s = (1.0 + m22 - m00 - m11) ** 0.5 * 2
        w, x = (m10 - m01) / s, (m02 + m20) / s
        y, z = (m12 + m21) / s, 0.25 * s
    return (x, y, z, w)


def rotate(q, v):
    """Rotate vector v by unit quaternion q = (x, y, z, w)."""
    x, y, z, w = q
    u = (x, y, z)
    t = _cross(u, v)
    t = (2 * t[0], 2 * t[1], 2 * t[2])
    return _add(_add(v, t, w), _cross(u, t))


# Breath around a fitted model, as a fraction of its bounding sphere's
# radius (R82). The sphere fit alone touched the band's top and bottom
# exactly: a tall part (a vase, D8) sat flush against the window edge and
# the pill, and read as clipped.
FIT_MARGIN = 0.04


def fit_camera(center, radius, look, up, width, height, reserve=0.0,
               ortho=True, height_angle=0.785398, margin=0.0):
    """Where the camera goes to frame a sphere with the bottom `reserve`
    fraction of the view kept free for the floating view bar (R82).

    FreeCAD's ViewFit centres the model in the WHOLE view, so the pill
    covered its bottom and a tall part was clipped (dogfood D8). Here the
    sphere fits the band above the pill and is centred in that band.

    `up` need not be perpendicular to `look` (world Z for an iso view is
    not): the band shift runs along the SCREEN's up, the part of `up`
    perpendicular to `look`. Shifting along world Z moved an iso model only
    cos(35.3 deg) = 0.82 of the way, back under the bar (measured with
    Coin's projection, test_shell_round3).

    `margin` grows the sphere by that fraction of its radius, so the model
    keeps a breath from the band's edges (fit_view passes FIT_MARGIN).

    Returns (position, size): size is the orthographic camera's `height`,
    or the perspective camera's focal distance."""
    radius = radius * (1.0 + max(0.0, margin))
    look = _unit(look)
    up = _sub(up, tuple(c * _dot(up, look) for c in look))
    up = _unit(up) if _dot(up, up) > 1e-12 else _unit(
        _cross(look, (1.0, 0.0, 0.0)) if abs(look[0]) < 0.9
        else _cross(look, (0.0, 1.0, 0.0)))
    aspect = float(width) / float(height) if height else 1.0
    aspect = max(aspect, 1e-6)
    band = max(0.2, 1.0 - reserve)                     # usable fraction
    # visible world height needed: the sphere's diameter must fit the band
    # vertically and the full width horizontally.
    vis_h = max(2.0 * radius / band, 2.0 * radius / aspect)
    # FreeCAD's cameras use ADJUST_CAMERA: in a view taller than wide Coin
    # widens the volume by 1/aspect itself, so the camera's own height is
    # the visible WIDTH there.
    cam_h = vis_h if aspect >= 1.0 else vis_h * aspect
    if ortho:
        size = cam_h
        dist = radius * 2.0 + 1.0
        # centre of the band sits reserve/2 of the view height above
        # centre: move the camera DOWN by that much so the model rides up.
        shift = reserve / 2.0 * vis_h
    else:
        dist, shift = _perspective_fit(radius, reserve, aspect, height_angle)
        size = dist
    pos = _add(_add(center, look, -dist), up, -shift)
    return pos, size


def _perspective_fit(radius, reserve, aspect, height_angle):
    """(distance, downward shift) for a perspective camera: the sphere's
    tangent cone must fit the band vertically and the view horizontally.
    A sphere seen in perspective spans MORE than its diameter at the centre
    distance (the near side is closer), so this solves for the cone, not
    the diameter; measured with Coin's own projection in the verification."""
    import math
    t = math.tan(height_angle / 2.0)
    tv = t if aspect >= 1.0 else t / aspect            # per unit distance
    th = tv * aspect
    lo_ndc = -1.0 + 2.0 * reserve                      # band: lo_ndc..1
    top, bot = math.atan(tv), math.atan(lo_ndc * tv)
    side = math.atan(th)
    dist = radius / math.sin(max(1e-3, min((top - bot) / 2.0, side)))
    for _ in range(60):
        yc = reserve                                   # band centre (NDC)
        centre = math.atan(yc * tv)
        half = math.asin(min(1.0, radius / dist))
        if centre + half <= top and centre - half >= bot and half <= side:
            break
        dist *= 1.03
    return dist, reserve * dist * tv


def points_in_view(norm_pts, reserve=0.0, slack=0.0):
    """True when every point, in normalised screen coords (0..1, y up from
    the bottom), lies inside the view above the reserved bottom band."""
    for p in norm_pts:
        x, y = p[0], p[1]
        if x < -slack or x > 1 + slack or y < reserve - slack or y > 1 + slack:
            return False
    return True


def bbox_corners(lo, hi):
    return [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1])
            for z in (lo[2], hi[2])]


# ---- the live camera ---------------------------------------------------
def _reserve():
    """Fraction of the 3D view's height the view bar covers, from the shell
    (0.0 when the shell is not installed)."""
    try:
        from . import shell
        return float(shell.view_reserve())
    except Exception:                                  # noqa: BLE001
        return 0.0


def _coin():
    from pivy import coin
    return coin


def _camera(v):
    cam = v.getCameraNode()
    coin = _coin()
    ortho = cam.isOfType(coin.SoOrthographicCamera.getClassTypeId())
    return cam, ortho


def _size(v):
    try:
        w, h = v.getSize()
        if w > 0 and h > 0:
            return float(w), float(h)
    except Exception:                                  # noqa: BLE001
        pass
    return 1.0, 1.0


def _cam_axes(cam):
    coin = _coin()
    rot = cam.orientation.getValue()
    look = rot.multVec(coin.SbVec3f(0, 0, -1)).getValue()
    up = rot.multVec(coin.SbVec3f(0, 1, 0)).getValue()
    return tuple(look), tuple(up)


def _scene_sphere(v):
    """Bounding sphere of what the view draws (what FreeCAD's own viewAll
    measures), or None for an empty scene."""
    coin = _coin()
    w, h = _size(v)
    act = coin.SoGetBoundingBoxAction(coin.SbViewportRegion(int(w), int(h)))
    act.apply(v.getSceneGraph())
    box = act.getBoundingBox()
    if box.isEmpty():
        return None
    lo, hi = box.getMin().getValue(), box.getMax().getValue()
    c = tuple((a + b) / 2.0 for a, b in zip(lo, hi))
    r = _dot(_sub(hi, lo), _sub(hi, lo)) ** 0.5 / 2.0
    return (c, r) if r > 0 else None


def fit_view(v, reserve=None):
    """Frame the scene in view `v`, keeping the camera's direction, with
    room for the view bar. Returns True when the camera was moved."""
    coin = _coin()
    reserve = _reserve() if reserve is None else reserve
    sph = _scene_sphere(v)
    if sph is None:
        return False
    cam, ortho = _camera(v)
    look, up = _cam_axes(cam)
    w, h = _size(v)
    ha = 0.785398 if ortho else float(cam.heightAngle.getValue())
    pos, size = fit_camera(sph[0], sph[1], look, up, w, h, reserve,
                           ortho=ortho, height_angle=ha, margin=FIT_MARGIN)
    cam.position.setValue(coin.SbVec3f(*pos))
    if ortho:
        cam.height.setValue(size)
        cam.focalDistance.setValue(sph[1] * (1.0 + FIT_MARGIN) * 2.0 + 1.0)
    else:
        cam.focalDistance.setValue(size)
    return True


def fit_all(reserve=None):
    """Fit everything, leaving the view bar's band free (R82). Falls back to
    FreeCAD's own ViewFit when the camera cannot be driven directly."""
    g = _gui()
    if g is None:
        return False
    v = _view()
    if v is not None:
        try:
            if fit_view(v, reserve):
                return True
        except Exception as exc:                       # noqa: BLE001
            _log("own fit failed, using ViewFit (%r)" % (exc,))
    try:
        g.SendMsgToActiveView("ViewFit")
        return True
    except Exception:
        return False


def in_view(v, objs, reserve=None):
    """True/False: do the objects' bounding boxes lie inside the current
    view volume, above the view bar's band? None when it cannot be told."""
    lo, hi = _objs_bounds(objs)
    if lo is None:
        return None
    coin = _coin()
    reserve = _reserve() if reserve is None else reserve
    cam, _ortho = _camera(v)
    w, h = _size(v)
    vv = cam.getViewVolume(w / h)
    if w < h:                                          # ADJUST_CAMERA
        vv.scale(h / w)
    pts = [vv.projectToScreen(coin.SbVec3f(*p)).getValue()
           for p in bbox_corners(lo, hi)]
    return points_in_view(pts, reserve)


def _shape_of(o):
    for attr in ("Shape", "Mesh"):
        s = getattr(o, attr, None)
        if s is not None:
            try:
                if s.isNull():
                    continue
            except Exception:                          # noqa: BLE001
                pass
            return s
    return None


def _objs_bounds(objs):
    lo, hi = None, None
    for o in objs or ():
        s = _shape_of(o)
        if s is None:
            continue
        try:
            bb = s.BoundBox
            a = (bb.XMin, bb.YMin, bb.ZMin)
            b = (bb.XMax, bb.YMax, bb.ZMax)
        except Exception:                              # noqa: BLE001
            continue
        if not all(abs(c) < 1e12 for c in a + b):
            continue                                   # empty BoundBox
        lo = a if lo is None else tuple(min(p, q) for p, q in zip(lo, a))
        hi = b if hi is None else tuple(max(p, q) for p, q in zip(hi, b))
    return lo, hi


def _global_placement(o):
    """o's placement in WORLD coordinates (parent containers applied), or
    its own Placement when the object cannot say, or None."""
    pl = getattr(o, "Placement", None)
    if pl is None:
        return None
    try:
        gp = o.getGlobalPlacement()
        if gp is not None:
            return gp
    except Exception:                                  # noqa: BLE001
        pass
    return pl


def _world_centre(o):
    """World centre of o's own bounds. A Mesh/Shape carries only o's own
    Placement, so its bounds are in the parent container's frame: mapped
    here by the containers' placement. None when unreadable."""
    s = _shape_of(o)
    if s is None:
        return None
    try:
        bb = s.BoundBox
        c = ((bb.XMin + bb.XMax) / 2.0, (bb.YMin + bb.YMax) / 2.0,
             (bb.ZMin + bb.ZMax) / 2.0)
        if not all(abs(x) < 1e12 for x in c):
            return None
        pl = getattr(o, "Placement", None)
        gp = _global_placement(o)
        if pl is None or gp is None:
            return c
        w = gp.multiply(pl.inverse()).multVec(type(pl.Base)(*c))
        return (w.x, w.y, w.z)
    except Exception:                                  # noqa: BLE001
        return None


def _local_frame(o):
    """(world centre, world unit normal) of a plate-like object from its
    UNPLACED bounds and its Placement: the normal is the local axis of least
    extent, turned by the placement's rotation. None when the object has no
    placement or shape to read (a console stand-in) - the caller then falls
    back to world bounds.

    R155 (D50 partial regression): the world box of a TILTED board is no
    plate - a 60 x 6.5 x 120 board turned 15 deg about X bounds at
    60 x 37.3 x 117.6 - and comparing module and board box centres along a
    world axis picked the wrong side (measured headless: -15 and 165 deg
    looked at the back). The placement says which way the board faces.

    The placement is the GLOBAL one (parent App::Part containers applied):
    a board in a Part that is itself tilted has an identity own Placement
    and its own Mesh/Shape in the Part's frame (measured headless in the
    R155 review: a Part turned 165 deg about X looked at the back)."""
    pl = _global_placement(o)
    s = _shape_of(o)
    if pl is None or s is None or not hasattr(s, "copy"):
        return None
    try:
        local = s.copy()
        local.Placement = type(pl)()                   # identity
        bb = local.BoundBox
        lo = (bb.XMin, bb.YMin, bb.ZMin)
        hi = (bb.XMax, bb.YMax, bb.ZMax)
        if not all(abs(c) < 1e12 for c in lo + hi):
            return None
        ext = _sub(hi, lo)
        axis = min(range(3), key=lambda i: ext[i])
        vec = type(pl.Base)
        e = [0.0, 0.0, 0.0]
        e[axis] = 1.0
        n = pl.Rotation.multVec(vec(*e))
        c = pl.multVec(vec(*[(a + b) / 2.0 for a, b in zip(lo, hi)]))
        return (c.x, c.y, c.z), _unit((n.x, n.y, n.z))
    except Exception as exc:                           # noqa: BLE001
        _log("board frame: %r" % (exc,))
        return None


# iso-like camera side: right (+X), front (-Y), above (+Z)
_ISO_SIDE = (0.6, -0.6, 0.5)


def module_face_direction(doc):
    """Camera POSITION direction that looks at the modules' side of an Atech
    board, or None when the document has no board (or no seated module to
    tell the side). Dogfood D30: the board stands in X/Z, its modules face
    +Y, and the default isometric showed the back of every product.

    The board's normal comes from its placement (R155), so a tilted board
    is looked at from the front too: the returned direction d always has
    d . n_modules = 1 (the camera looks against the module normal). For a
    board whose normal is a world axis this is the iso side with that axis
    replaced by +-1, exactly as before."""
    boards, mods = [], []
    for o in getattr(doc, "Objects", None) or ():
        role = getattr(o, "AtechRole", None)
        if role == "board":
            boards.append(o)
        elif role == "module":
            mods.append(o)
    blo, bhi = _objs_bounds(boards)
    mlo, mhi = _objs_bounds(mods)
    if blo is None or mlo is None:
        return None
    mc = [(a + b) / 2.0 for a, b in zip(mlo, mhi)]
    frame = _local_frame(boards[0]) if len(boards) == 1 else None
    if frame is None:
        ext = _sub(bhi, blo)
        axis = min(range(3), key=lambda i: ext[i])      # board normal
        bc = [(a + b) / 2.0 for a, b in zip(blo, bhi)]
        n = [0.0, 0.0, 0.0]
        n[axis] = 1.0
    else:
        bc, n = frame
        # the module centres in the board frame's (world) coordinates
        cs = [c for c in (_world_centre(m) for m in mods) if c is not None]
        if cs:
            mc = [sum(c[i] for c in cs) / len(cs) for i in range(3)]
    side = _dot(_sub(mc, bc), n)
    if abs(side) < 1e-6:
        return None
    if side < 0:
        n = (-n[0], -n[1], -n[2])
    # the iso side with its component along the normal replaced by the
    # modules' side: d = n + (iso - (iso . n) n)
    d = _add(n, _add(_ISO_SIDE, n, -_dot(_ISO_SIDE, n)))
    return tuple(0.0 if abs(x) < 1e-12 else round(x, 12) for x in d)


def look_from(x, y, z, v=None):
    """Put the camera on the (x, y, z) side of the model, looking at it,
    with world Z up. False when there is no view to turn."""
    v = v or _view()
    if v is None:
        return False
    try:
        coin = _coin()
        cam, _o = _camera(v)
        q = look_quaternion((-x, -y, -z))
        cam.orientation.setValue(coin.SbRotation(*q))
        return True
    except Exception as exc:                           # noqa: BLE001
        _log("look_from: %r" % (exc,))
    try:
        v.setViewDirection((-x, -y, -z))
        return True
    except Exception:                                  # noqa: BLE001
        return False


_FACED = set()     # documents whose Atech module face has been shown once


def _doc_key(doc):
    try:
        return doc.Name
    except Exception:                                  # noqa: BLE001
        return id(doc)


def frame_if_needed(objs, first=False, doc=None):
    """Move the camera only when it has to (S23).

    The first build of a chat turns to a useful angle - the module face of
    an Atech board when the document has one (R82), isometric otherwise -
    and fits. A board that arrives in a LATER build (the first preview had
    none yet) gets the same turn once per document: without it the product
    stayed on the iso view of its back (dogfood D50). Later builds (live
    previews) otherwise keep the user's camera unless the new model leaves
    the view volume or slides under the view bar: the old fit on every
    preview yanked the camera back while the user orbited.

    Returns True when the camera moved."""
    v = _view()
    if v is None:
        return False
    doc = doc if doc is not None else getattr(FreeCAD, "ActiveDocument",
                                              None)
    face = None
    if doc is not None and (first or _doc_key(doc) not in _FACED):
        try:
            face = module_face_direction(doc)
        except Exception as exc:                       # noqa: BLE001
            _log("module face: %r" % (exc,))
    if face is not None and look_from(*face, v=v):
        _FACED.add(_doc_key(doc))
        fit_all()
        return True
    if first:
        iso_and_fit()
        return True
    try:
        inside = in_view(v, objs)
    except Exception as exc:                           # noqa: BLE001
        _log("in_view: %r" % (exc,))
        inside = None
    if inside is False:
        fit_all()
        return True
    return False                  # inside, or cannot tell: leave it alone


# ---- Atech meshes: two-sided lighting (R108) ---------------------------
# MEASURED headless (freecadcmd, Mesh module) on the library's
# motherboard_14_port.stl: 16,069 facets in 111 separate shells, 185 open
# edges and 59 non-manifold edges (47 and 40 of them in the middle opening),
# 28 duplicate facets, self-intersecting. The facets are uniformly oriented
# (countNonUniformOrientedFacets = 0), so the black triangles are the
# MODEL's open shells seen from behind, not tessellation: a Mesh::Feature is
# drawn as stored. FreeCAD lights a mesh from one side unless
# Mod/Mesh/TwoSideRendering is set (both strings in MeshGui.so 1.1.3), and a
# one-sided back face renders black. The view property below lights both
# sides of the board and module meshes only - a document view setting, not
# the user's global Mesh preference, and never the geometry.
ATECH_MESH_ROLES = ("board", "module")


def two_side_meshes(doc):
    """Light the Atech board/module meshes of `doc` from both sides.
    Returns how many view objects changed (0 in a console session).

    A view property change marks the GUI document modified: a saved
    document opened and left untouched would then ask "save changes?" on
    close because of a lighting mode the user never chose. The flag is put
    back when it was clear before (review of R108)."""
    n = 0
    gdoc, was = None, None
    try:
        gdoc = _gui().getDocument(doc.Name)
        was = bool(gdoc.Modified)
    except Exception:                                  # noqa: BLE001
        gdoc = None
    for o in getattr(doc, "Objects", None) or ():
        try:
            if getattr(o, "AtechRole", None) not in ATECH_MESH_ROLES:
                continue
            if getattr(o, "TypeId", "") != "Mesh::Feature":
                continue
            vo = getattr(o, "ViewObject", None)
            if vo is None or not hasattr(vo, "Lighting"):
                continue
            if vo.Lighting != "Two side":
                vo.Lighting = "Two side"
                n += 1
        except Exception as exc:                       # noqa: BLE001
            _log("two-side lighting on %s: %r"
                 % (getattr(o, "Name", "?"), exc))
    if n and gdoc is not None and was is False:
        try:
            gdoc.Modified = False
        except Exception:                              # noqa: BLE001
            pass
    return n


# ---- tessellation (S23, implements S05) --------------------------------
# MEASURED headless with the view provider's own formula (speed plan S12,
# docs/prd/release_prd.md S05): the 14-object car went 11,472 -> 6,396
# triangles (44 -> 30 ms) at 1.0 / 40 deg; gears cost the same whatever
# the Deviation because their face count dominates, so a dense object keeps
# FreeCAD's 28.5 deg at the end of the turn.
PREVIEW_MESH = (1.0, 40.0)        # (Deviation %, AngularDeflection deg)
FINAL_MESH = (0.2, 20.0)
DENSE_FACES = 200
DENSE_ANGLE = 28.5


def mesh_quality_for(n_faces, final):
    if not final:
        return PREVIEW_MESH
    if n_faces > DENSE_FACES:
        return (FINAL_MESH[0], DENSE_ANGLE)
    return FINAL_MESH


def set_mesh_quality(objs, final=False, gui=None):
    """Coarse tessellation for live previews, finer for the end-of-turn
    build. GUI only (a console session has no view provider); touches only
    view properties, never geometry. Returns how many objects changed."""
    if (gui if gui is not None else _gui()) is None:
        return 0
    n = 0
    for o in objs or ():
        vo = getattr(o, "ViewObject", None)
        if vo is None or not hasattr(vo, "Deviation") \
                or not hasattr(vo, "AngularDeflection"):
            continue
        try:
            faces = len(o.Shape.Faces)
        except Exception:                              # noqa: BLE001
            faces = 0
        dev, ang = mesh_quality_for(faces, final)
        try:
            changed = False
            if abs(float(vo.Deviation) - dev) > 1e-9:
                vo.Deviation = dev
                changed = True
            if abs(_deg(vo.AngularDeflection) - ang) > 1e-6:
                vo.AngularDeflection = ang
                changed = True
            n += changed
        except Exception as exc:                       # noqa: BLE001
            _log("mesh quality on %s: %r" % (getattr(o, "Name", "?"), exc))
    return n


def _deg(q):
    """AngularDeflection is a PropertyAngle: a Quantity in degrees."""
    try:
        return float(q.Value)
    except AttributeError:
        return float(q)


def axonometric():
    return _send("viewAxonometric")


def _animation_ms():
    """How long FreeCAD animates a standard-view turn, 0 when it does not.
    A fit made while the turn animates is overwritten by its later frames."""
    try:
        p = FreeCAD.ParamGet(_VIEW_GROUP)
        if not p.GetBool("UseNavigationAnimations", True):
            return 0
        return max(0, int(p.GetInt("AnimationDuration", 500))) + 60
    except Exception:                                  # noqa: BLE001
        return 0


def iso_and_fit():
    """Isometric, then fit (in that order: a fit before the turn is framed
    for the old direction). Waits out FreeCAD's view animation."""
    ok = axonometric()
    ms = _animation_ms() if ok else 0
    if ms:
        try:
            from PySide6 import QtCore
            QtCore.QTimer.singleShot(ms, fit_all)
            return True
        except Exception:                              # noqa: BLE001
            pass
    return fit_all()


def set_direction(x, y, z):
    """Point the camera along an explicit view direction (the direction it
    LOOKS), keeping world Z up.

    FreeCAD's named views are fine for a cube-ish part, but an assembly whose
    interesting axis is also its thinnest one renders edge-on under Isometric.
    Returns False rather than pretending when there is no view.
    """
    return look_from(-x, -y, -z)


def view_front():
    return _send("viewFront")


def view_top():
    return _send("viewTop")


def view_right():
    return _send("viewRight")


def spin(enable=True):
    """Start/stop FreeCAD's own continuous rotation ('spin it around').

    Uses the animation API when present. Returns False rather than pretending
    when the running FreeCAD does not expose it.
    """
    v = _view()
    if v is None:
        return False
    try:
        if enable:
            # startAnimating(axis..., velocity) — the axis is world Z so the
            # model turns like a turntable.
            v.startAnimating(0.0, 0.0, 1.0, 0.004)
        else:
            v.stopAnimating()
        return True
    except Exception:
        return False
