# verify_tree.py — the build gate. Runs INSIDE the built tree's freecadcmd:
#
#   env -i HOME=<empty temp dir> PATH=/usr/bin:/bin \
#       <tree>/usr/bin/freecadcmd branding/verify_tree.py
#
# A branded build that silently failed to brand looks exactly like success,
# so assert on the values the running kernel reports — not on our own files.
#
# HONESTY RULES (release PRD R09):
#   * No sys.path entry outside the image. Everything asserted here must be
#     found through AppHomePath, so a file present only in the developer's
#     checkout cannot pass for a file present in the image.
#   * Every path the addon resolves at runtime (module library, meshes,
#     ATECH_ASSEMBLY.md, reference model) must lie INSIDE the image. A dev
#     fallback that resolves on the build host is a FAIL, not an OK.
#   * Missing library / assembly doc / reference model = FAIL, never
#     CANNOT DETERMINE.
#
# freecadcmd exits 0 even when this script raises, so the verdict is the
# VERIFY_FAILURES=<n> line, which the caller greps for. Environment:
#   ATECH_VERIFY_DEV_UNLICENSED=1   LICENSE/LICENSE-models.md/NOTICE may be
#                                   absent (dev build)
import os
import re
import sys

# The release identity (ADR-005, ADR-006). Typed ONCE here; every check below
# derives its paths from these, and the build script carries its own copy, so
# a rename done on one side only fails this gate.
PRODUCT = "Atech Atelier"
APP_ID = "dev.atech.Atelier"
DOC_NAME = "atech-atelier"
PROJECT_LICENSE = "LGPL-2.1-or-later AND CC-BY-NC-4.0"
OLD_NAMES = ("Atech Studio", "atech-studio", "dev.atech.Studio", "AtechStudio")

# The embedded interpreter ignores PYTHONDONTWRITEBYTECODE (measured); stop
# our own imports from writing __pycache__ into the tree we are judging.
sys.dont_write_bytecode = True

import FreeCAD

c = FreeCAD.ConfigDump()
home = os.path.realpath(c.get("AppHomePath", ""))
bad = []
DEV_UNLICENSED = os.environ.get("ATECH_VERIFY_DEV_UNLICENSED") == "1"


def row(kind, what, ok, fail_text="FAIL", ok_text="OK", key=None):
    print("  %-16s %-22s %s" % (kind, what, ok_text if ok else fail_text))
    if not ok:
        bad.append(key or "%s:%s" % (kind, what))
    return ok


def inside(path):
    """True when `path` resolves inside the image (AppHomePath)."""
    if not path:
        return False
    p = os.path.realpath(path)
    return p == home or p.startswith(home + os.sep)


# ------------------------------------------------------------ sys.path
# MEASURED 2026-09-25: freecadcmd does not exec a .py argument, it IMPORTS it
# (module name = file stem) after appending the file's directory to sys.path.
# Run from the checkout, that put branding/ -- a repo directory -- on the
# path of the gate that promises "no sys.path entry outside the image".
# Drop our own directory, then require every remaining entry to be inside
# the image or under $HOME (the empty temporary HOME the build passes, whose
# Macro dirs FreeCAD adds itself).
_own_dir = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [p for p in sys.path
               if os.path.realpath(p or os.curdir) != _own_dir]
_user_home = os.path.realpath(os.environ.get("HOME") or "/nonexistent")
_outside = [p for p in sys.path
            if not inside(p or os.curdir)
            and not os.path.realpath(p or os.curdir).startswith(_user_home + os.sep)]
row("sys.path", "%d entries" % len(sys.path), not _outside,
    "FAIL (outside the image: %s)" % ", ".join(_outside[:3]), key="sys-path")


# ------------------------------------------------------------ branding
want = {"Application": PRODUCT, "WindowTitle": PRODUCT,
        "ExeName": PRODUCT, "ExeVendor": "Atech",
        "DesktopFileName": APP_ID,
        "StartWorkbench": "AcadAgentWorkbench",
        "UserParameterTemplate": "bin/atech_user_template.cfg"}
for k, v in sorted(want.items()):
    got = c.get(k, "<ABSENT>")
    row(k, got, got == v, "FAIL (want %r)" % v, key=k)

for rel in ("bin/branding.xml", "bin/atech_icon.svg", "bin/atech_logo.svg",
            "bin/atech_splash.svg", "bin/atech_user_template.cfg",
            "bin/atech_icon-dark.svg", "bin/atech_logo-dark.svg",
            "bin/atech_splash-dark.svg",
            "share/Gui/Stylesheets/AtechLight.qss",
            "share/Gui/Stylesheets/AtechDark.qss",
            "share/Gui/Stylesheets/parameters/%s Dark.yaml" % PRODUCT,
            "share/Gui/Stylesheets/parameters/%s Light.yaml" % PRODUCT,
            "share/Gui/Stylesheets/FreeCAD.qss",
            "Mod/AcadAgent/InitGui.py"):
    row("asset", rel, os.path.isfile(os.path.join(home, rel)),
        "FAIL (missing)", key=rel)

# The addon's own commands must actually be wired into the workbench. A bundle
# can contain every file and still register nothing — measured: an edit that
# silently no-opped left viewport.py present and its toolbar absent.
init = os.path.join(home, "Mod", "AcadAgent", "InitGui.py")
try:
    with open(init, encoding="utf-8") as fh:
        src = fh.read()
    # Deliberately NOT asserting a toolbar: chrome.py hides the toolbar rows
    # and every command is reached from the menu.
    for token in ("AcadAgent_OpenReference", "AcadAgent_SpinView",
                  "AcadAgent_FitView", "viewport.apply_view_theme",
                  "AcadAgent_Terminal", "AcadAgent_AskView", "appendMenu"):
        row("workbench", token, token in src, "FAIL (not wired)",
            key="wiring:" + token)
except Exception as e:                                   # noqa: BLE001
    row("workbench", "InitGui.py", False, "FAIL (%s)" % e, key="wiring")

# ------------------------------------------------ what must NOT ship (R40)
addon = os.path.join(home, "Mod", "AcadAgent")
junk = []
for dp, dns, fns in os.walk(addon):
    for d in dns:
        if d in ("tests", "__pycache__") or d.endswith("_cache"):
            junk.append(os.path.relpath(os.path.join(dp, d), home))
row("no dev files", "tests/, caches", not junk,
    "FAIL (%s)" % ", ".join(sorted(junk)[:3]), key="dev-files")

# ------------------------------------------- the addon, from the image only
# Only the image's own addon directory goes on sys.path. The previous gate
# also inserted the developer's repo checkout, which made "module library
# OK" true on the build host and false on every other machine.
sys.path.insert(0, addon)
try:
    from acadagent import theme, viewport, claude_cli, vision, terminal
    row("addon import", "acadagent.theme", bool(theme.PANEL_QSS))

    # Reference model: must be found, and found INSIDE the image.
    d = viewport._crane_build_dir()
    n = len(viewport.crane_parts())
    if d is None or not n:
        row("reference model", "0 parts", False, "FAIL (not bundled)",
            key="reference-model")
    else:
        row("reference model", "%d parts" % n, inside(d),
            "FAIL (resolves outside the image: %s)" % d,
            key="reference-model")

    # The screenshot round trip needs the claude CLI. On a build host with an
    # empty HOME it is legitimately absent — this is the one CANNOT DETERMINE.
    ok = claude_cli.available()
    print("  %-16s %-22s %s" % ("claude cli", claude_cli.find_claude() or "not found",
                                "OK" if ok else "CANNOT DETERMINE (not installed)"))
    row("vision views", ",".join(vision.STANDARD_VIEWS), True)
    row("terminal", "ansi strip",
        terminal.strip_ansi("\x1b[31mred\x1b[0m") == "red")

    from acadagent import engine as _eng
    names = [e[0] for e in _eng.ENGINES]
    row("agent engines", ",".join(names),
        "claude" in names and "opencode" in names and "api" in names,
        "FAIL (missing an engine)", key="engines")

    # ATECH_ASSEMBLY.md: the agent's seating rules. Missing = FAIL.
    from acadagent import build as _build
    doc = _build.assembly_doc()
    row("assembly doc", "ATECH_ASSEMBLY.md",
        doc is not None and inside(doc),
        "FAIL (%s)" % ("missing" if doc is None
                       else "resolves outside the image: %s" % doc),
        key="assembly-doc")

    # Module library: must be bundled, resolve inside the image, and BUILD.
    from acadagent import projects as _proj
    pd = _proj._builder_dir()
    row("module library", "projects/",
        pd is not None and inside(pd),
        "FAIL (%s)" % ("missing" if pd is None
                       else "resolves outside the image: %s" % pd),
        key="library-dir")
    if pd is not None and inside(pd) and _proj.library_available():
        import atech_modules as _am
        import atech_ports as _ap
        for mod, attrs in ((_am, ("__file__", "STL_DIR", "PRESETS")),
                           (_ap, ("__file__", "STL_DIR", "BOARD_STL", "BOARD_GLB"))):
            for a in attrs:
                p = getattr(mod, a, None)
                if p is None and a != "__file__":
                    continue                    # renamed upstream: not ours to assert
                row("library path", "%s.%s" % (mod.__name__, a), inside(p),
                    "FAIL (resolves outside the image: %s)" % p,
                    key="library-path:%s.%s" % (mod.__name__, a))
        keys = _proj.project_keys()
        row("module library", "%d project(s)" % len(keys), bool(keys),
            "FAIL (no projects)", key="projects")
        for k in keys:
            try:
                _doc, rep = _am.build_named(k, doc_name="gate_%s" % k)
                placed = len(rep.get("placed") or [])
                ov = rep.get("overlaps") or []
                row("project", "%s: %d placed" % (k, placed),
                    placed > 0 and not ov,
                    "FAIL (%s)" % ("no modules" if not placed
                                   else "overlap %s" % ov),
                    key="project:" + k)
            except Exception as e:                       # noqa: BLE001
                row("project", k, False, "FAIL (%s)" % e, key="project:" + k)
    else:
        row("module library", "specs()", False,
            "FAIL (library not available from the image)", key="library")

    # The Credits dialog (Help -> Credits) reads CREDITS.md through the
    # addon's own resolver. Asked of the ADDON, not of our path list: if the
    # doc directory is renamed on one side only, the dialog shows "Credits
    # not found" while every file exists.
    from acadagent import credits as _cr
    _cp = _cr.credits_path()
    _want_cp = os.path.join(home, "share", "doc", DOC_NAME, "CREDITS.md")
    row("credits dialog", "CREDITS.md",
        _cp is not None and os.path.realpath(_cp) == os.path.realpath(_want_cp),
        "FAIL (addon resolves %s; the image ships %s)"
        % (_cp, os.path.relpath(_want_cp, home)), key="credits-dialog")
except Exception as e:                                   # noqa: BLE001
    row("addon import", "acadagent", False, "FAIL (%s)" % e, key="addon")

# ---------------------------------------------------------- FreeCADMCP
mcp = os.path.join(home, "Mod", "FreeCADMCP")
row("mcp addon", "FreeCADMCP",
    os.path.isfile(os.path.join(mcp, "rpc_server", "settings.py")),
    "FAIL (not bundled)", key="mcp-addon")
# Public build keeps the RPC server OFF (R10): the default is upstream's False
# and nothing seeds a settings file. Asserted on the SHIPPED default, not on
# anybody's home directory.
try:
    sys.path.insert(0, mcp)
    from rpc_server import settings as _mcps
    auto = _mcps._DEFAULT_SETTINGS.get("auto_start_rpc")
    row("mcp autostart", "default=%s" % auto, auto is False,
        "FAIL (RPC would start by default)", key="mcp-autostart")
    remote = _mcps._DEFAULT_SETTINGS.get("remote_enabled")
    row("mcp scope", "remote_enabled=%s" % remote, remote is False,
        "FAIL (exposed)", key="mcp-exposed")
except Exception as e:                                   # noqa: BLE001
    row("mcp autostart", "settings", False, "FAIL (%s)" % e, key="mcp-settings")

# ------------------------------------------------ notices and docs (R01-R06)
top = os.path.dirname(home)                  # squashfs-root
doc_dir = os.path.join(home, "share", "doc", DOC_NAME)
for rel in ("README.md", "CREDITS.md", "ATECH_CHANGES.txt", "SOURCE_OFFER.txt",
            "third_party/NOTICE.third_party",
            "third_party/LICENSE.FreeCADMCP", "third_party/LICENSE.Lucide",
            "third_party/LICENSE.Feather"):
    row("doc", rel, os.path.isfile(os.path.join(doc_dir, rel)),
        "FAIL (missing)", key="doc:" + rel)
models_dir = os.path.join(home, "Mod", "AcadAgent", "data", "models")
for kind, d, rel in (("doc", doc_dir, "LICENSE"),
                     ("doc", doc_dir, "LICENSE-models.md"),
                     ("doc", doc_dir, "NOTICE"),
                     ("models", models_dir, "LICENSE-models.md")):
    present = os.path.isfile(os.path.join(d, rel))
    if not present and DEV_UNLICENSED:
        print("  %-16s %-22s %s" % (kind, rel, "ABSENT (dev build, NOT RELEASABLE)"))
    else:
        row(kind, rel, present, "FAIL (missing; ADR-006 release file)",
            key="%s:%s" % (kind, rel))
# The contents, not only the names: LICENSE is the LGPL v2.1 text, and the
# models notice names its licence (ADR-006).
def _read(p):
    try:
        with open(p, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


if os.path.isfile(os.path.join(doc_dir, "LICENSE")):
    _t = _read(os.path.join(doc_dir, "LICENSE"))
    row("licence", "LICENSE is LGPL-2.1",
        "GNU LESSER GENERAL PUBLIC LICENSE" in _t
        and "Version 2.1, February 1999" in _t,
        "FAIL (not the LGPL v2.1 text)", key="licence:lgpl")
for _d in (doc_dir, models_dir):
    _p = os.path.join(_d, "LICENSE-models.md")
    if os.path.isfile(_p):
        row("licence", "%s/LICENSE-models.md" % os.path.basename(_d),
            "CC BY-NC 4.0" in _read(_p),
            "FAIL (does not name CC BY-NC 4.0)",
            key="licence:models:" + os.path.relpath(_p, home))
if os.path.isfile(os.path.join(doc_dir, "NOTICE")):
    _n = _read(os.path.join(doc_dir, "NOTICE"))
    row("licence", "NOTICE is final",
        "PROPOSED root NOTICE" not in _n and "NOT the release NOTICE" not in _n,
        "FAIL (still the draft header of branding/NOTICE.proposed)",
        key="licence:notice-draft")
lic = os.path.join(mcp, "LICENSE")
try:
    with open(lic, encoding="utf-8") as fh:
        ok = "Shirokuma" in fh.read()
except OSError:
    ok = False
row("mcp licence", "Mod/FreeCADMCP/LICENSE", ok, "FAIL (missing MIT text)",
    key="mcp-licence")

# ------------------------------------------------ desktop integration (R38)
upstream_ids = [p for p in ("share/applications/org.freecad.FreeCAD.desktop",
                            "share/metainfo/org.freecad.FreeCAD.metainfo.xml",
                            "../org.freecad.FreeCAD.desktop")
                if os.path.exists(os.path.join(home, p))]
row("desktop", "no upstream entries", not upstream_ids,
    "FAIL (%s)" % ", ".join(upstream_ids), key="upstream-desktop")
DESKTOP_SHARE = os.path.join(home, "share", "applications", APP_ID + ".desktop")
DESKTOP_ROOT = os.path.join(top, APP_ID + ".desktop")
METAINFO = os.path.join(home, "share", "metainfo", APP_ID + ".metainfo.xml")
for p in (DESKTOP_SHARE, METAINFO):
    row("desktop", os.path.basename(p), os.path.isfile(p),
        "FAIL (missing)", key="desktop:" + os.path.relpath(p, home))
row("desktop", "root .desktop", os.path.isfile(DESKTOP_ROOT),
    "FAIL (missing)", key="desktop:root")

# The AppImage runtime and appimaged need: one top-level .desktop, an icon at
# the top level whose basename is Icon=, and .DirIcon resolving to it.
_root_desktops = sorted(f for f in os.listdir(top) if f.endswith(".desktop"))
row("desktop", "one top-level .desktop", _root_desktops == [APP_ID + ".desktop"],
    "FAIL (%s)" % _root_desktops, key="desktop:root-unique")
_dt = _read(DESKTOP_ROOT)
_icon = re.search(r"^Icon=(.+)$", _dt, re.M) if _dt else None
_icon = _icon.group(1).strip() if _icon else None
row("desktop", "Icon=%s" % _icon,
    _icon == APP_ID and os.path.isfile(os.path.join(top, APP_ID + ".svg")),
    "FAIL (want Icon=%s with %s.svg at the top level)" % (APP_ID, APP_ID),
    key="desktop:icon")
_di = os.path.join(top, ".DirIcon")
row("desktop", ".DirIcon",
    os.path.islink(_di) and os.readlink(_di) == APP_ID + ".svg"
    and os.path.isfile(_di),
    "FAIL (want a link to %s.svg)" % APP_ID, key="desktop:diricon")
for _name, _p in (("root", DESKTOP_ROOT), ("share", DESKTOP_SHARE)):
    _t = _read(_p)
    row("desktop", "Name= (%s)" % _name,
        re.search(r"^Name=%s$" % re.escape(PRODUCT), _t, re.M) is not None,
        "FAIL (Name is not %s)" % PRODUCT, key="desktop:name:" + _name)

# AppStream: the id, the launchable and the licence the owner decided.
try:
    import xml.etree.ElementTree as _ET
    _mi = _ET.parse(METAINFO).getroot()
    _got = {"id": (_mi.findtext("id") or "").strip(),
            "name": (_mi.findtext("name") or "").strip(),
            "project_license": (_mi.findtext("project_license") or "").strip(),
            "launchable": (_mi.findtext("launchable") or "").strip()}
    _exp = {"id": APP_ID, "name": PRODUCT, "project_license": PROJECT_LICENSE,
            "launchable": APP_ID + ".desktop"}
    for _k in sorted(_exp):
        row("metainfo", "%s=%s" % (_k, _got[_k])[:22], _got[_k] == _exp[_k],
            "FAIL (want %r)" % _exp[_k], key="metainfo:" + _k)
except Exception as e:                                   # noqa: BLE001
    row("metainfo", "parse", False, "FAIL (%s)" % e, key="metainfo")

# The previous product name must not survive in any file name the build
# controls: the top level, the doc dir, the desktop/metainfo dirs, the themes.
_stale_names = []
for _d in (top, os.path.join(home, "share", "doc"),
           os.path.join(home, "share", "applications"),
           os.path.join(home, "share", "metainfo"),
           os.path.join(home, "share", "icons", "hicolor", "scalable", "apps"),
           os.path.join(home, "share", "Gui", "Stylesheets", "parameters")):
    try:
        for _f in os.listdir(_d):
            if any(o in _f for o in OLD_NAMES):
                _stale_names.append(os.path.relpath(os.path.join(_d, _f), top))
    except OSError:
        pass
for _p in (DESKTOP_ROOT, DESKTOP_SHARE, METAINFO,
           os.path.join(home, "bin", "branding.xml")):
    _t = _read(_p)
    if _p.endswith("branding.xml"):
        _t = re.sub(r"<!--.*?-->", "", _t, flags=re.S)   # history in comments is fine
    for o in OLD_NAMES:
        if o in _t:
            _stale_names.append("%s mentions %r" % (os.path.relpath(_p, top), o))
row("rename", "no previous name", not _stale_names,
    "FAIL (%s)" % ", ".join(sorted(_stale_names)[:3]), key="old-name")

# ------------------------------------------------ personal data (public launch)
# Nothing Atech adds may carry the builder's identity: a home path, an e-mail.
# MEASURED 2026-10-04: ATECH_CHANGES.txt shipped "/home/<builder>/..." for the
# module library. Generic patterns always apply; the build adds its own $HOME
# and git e-mail through ATECH_VERIFY_FORBID (newline-separated). Bytes are
# scanned, so a path baked into a mesh or BREP is caught too. /home/runner/
# is upstream FreeCAD's CI path, quoted in CREDITS.md.
_pii_re = re.compile(rb"/home/(?!runner/)[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/"
                     rb"|/tmp/claude-|@gmail\.com")
_forbid = [s.strip().encode() for s in
           os.environ.get("ATECH_VERIFY_FORBID", "").split("\n")
           if len(s.strip()) >= 6]
_pii_roots = [os.path.join(home, "Mod", "AcadAgent"),
              os.path.join(home, "Mod", "FreeCADMCP"), doc_dir,
              os.path.join(home, "bin", "branding.xml"),
              os.path.join(home, "bin", "atech_user_template.cfg"),
              os.path.join(top, "AppRun"), DESKTOP_ROOT, DESKTOP_SHARE, METAINFO]
_pii_hits, _pii_n = [], 0
for _r in _pii_roots:
    _files = ([_r] if os.path.isfile(_r) else
              [os.path.join(dp, f) for dp, _dn, fs in os.walk(_r) for f in fs])
    for _p in _files:
        if os.path.islink(_p) or not os.path.isfile(_p):
            continue
        _pii_n += 1
        try:
            with open(_p, "rb") as fh:
                _b = fh.read()
        except OSError:
            continue
        if _pii_re.search(_b) or any(f in _b for f in _forbid):
            _pii_hits.append(os.path.relpath(_p, top))
row("personal data", "%d files" % _pii_n, _pii_n > 0 and not _pii_hits,
    "FAIL (%s)" % (", ".join(sorted(_pii_hits)[:3]) or "nothing scanned"),
    key="personal-data")

# ------------------------------------------------ one version (R39)
# VERSION is not in the image, so the check is that every place the build
# stamped agrees with every other -- and that none was skipped.
_re = re
_versions = {}
for _name, _p in (("desktop:root", DESKTOP_ROOT), ("desktop:share", DESKTOP_SHARE)):
    _m = _re.search(r"^X-AppImage-Version=(\S+)$", _read(_p), _re.M)
    _versions[_name] = _m.group(1) if _m else None
_m = _re.search(r'<release version="([^"]+)" date="\d{4}-\d{2}-\d{2}"',
                _read(METAINFO))
_versions["metainfo"] = _m.group(1) if _m else None
_m = _re.search(r"^Version\s+(\S+)$",
                _read(os.path.join(doc_dir, "ATECH_CHANGES.txt")),
                _re.M)
_versions["changes"] = _m.group(1) if _m else None
_vals = set(_versions.values())
row("version", "%s" % (sorted(v for v in _vals if v) or ["<none>"])[0],
    None not in _vals and len(_vals) == 1,
    "FAIL (%s)" % ", ".join("%s=%s" % kv for kv in sorted(_versions.items())),
    key="version")

# ------------------------------------------------ stale Atech CAD set (R45)
_stale = [p for p in ("share/Gui/Stylesheets/AtechCAD.qss",
                      "share/pixmaps/atech-cad.svg",
                      "share/pixmaps/atech-cad-logo.svg",
                      "share/pixmaps/atech-cad-splash.png")
          if os.path.exists(os.path.join(home, p))]
if "Atech CAD" in _read(os.path.join(home, "bin", "branding.xml")):
    _stale.append("bin/branding.xml names Atech CAD")
row("branding", "no Atech CAD assets", not _stale,
    "FAIL (%s)" % ", ".join(_stale), key="stale-brand")

# ------------------------------------------------ AppRun env snapshot (R61)
_apprun = _read(os.path.join(top, "AppRun"))
_snap = "# --- Atech: pre-AppRun environment snapshot (release PRD R61) ---"
_first_export = _apprun.find("\nexport ")
row("apprun", "env snapshot first",
    _snap in _apprun and 0 <= _apprun.find(_snap) < _first_export,
    "FAIL (missing, or after an upstream export)", key="apprun-env-snapshot")
# ADR-005: the profile copy from the previous name runs before FreeCAD, and
# before the backend block creates the new data folder for its log.
_mig = _apprun.find("\natech_migrate_tree()")
_agent = _apprun.find("\natech_cleanup()")
_launch = _apprun.find('\n"${MAIN}" "$@"')
row("apprun", "profile migration",
    0 <= _mig < _agent < _launch and 'ATECH_NEW_NAME="%s"' % PRODUCT in _apprun,
    "FAIL (missing, misplaced, or not migrating to %r)" % PRODUCT,
    key="apprun-migration")
row("apprun", "backend log dir",
    "/%s/v1-1\"" % PRODUCT in _apprun,
    "FAIL (agent log dir is not under %s)" % PRODUCT, key="apprun-logdir")

# ------------------------------------------------------------ template
tpl = os.path.join(home, "bin", "atech_user_template.cfg")
import xml.etree.ElementTree as ET
try:
    root = ET.parse(tpl).getroot()
    texts = {e.get("Name"): (e.text or e.get("Value")) for e in root.iter()
             if e.tag in ("FCText", "FCBool", "FCUInt")}
    for k, v in [("Theme", PRODUCT + " Light"),
                 ("StyleSheet", "AtechLight.qss"),
                 ("AutoloadModule", "AcadAgentWorkbench"),
                 ("FirstStart2024", "0"),
                 ("OverlayActiveStyleSheet", "Atech Overlay.qss")]:
        row("template", "%s=%s" % (k, texts.get(k)), texts.get(k) == v,
            "FAIL (want %r)" % v, key="template:" + k)
    # R88: the right overlay panel starts opaque. Looked up by PATH, since
    # "Transparent" is a common name and texts{} is keyed by name only.
    _or = root.find(".//FCParamGroup[@Name='BaseApp']/FCParamGroup"
                    "[@Name='MainWindow']/FCParamGroup[@Name='DockWindows']"
                    "/FCParamGroup[@Name='OverlayRight']/FCBool"
                    "[@Name='Transparent']")
    row("template", "OverlayRight opaque",
        _or is not None and _or.get("Value") == "0",
        "FAIL (BaseApp/MainWindow/DockWindows/OverlayRight/Transparent "
        "not seeded 0)", key="template:overlay-opaque")
    # R88: FreeCAD resolves the overlay sheet name on the "overlay:" path and,
    # when the file is absent, uses its own fallback NAME as the sheet text,
    # i.e. no overlay styling at all. The named file must ship.
    _ov = texts.get("OverlayActiveStyleSheet") or ""
    row("template", "overlay sheet ships",
        bool(_ov) and os.path.isfile(os.path.join(
            home, "share", "Gui", "Stylesheets", "overlay", _ov)),
        "FAIL (share/Gui/Stylesheets/overlay/%s missing)" % _ov,
        key="template:overlay-file")
except Exception as e:                                   # noqa: BLE001
    row("template", "parse", False, "FAIL (%s)" % e, key="template")

# The theme must reference upstream's sheet, and must not silently lose tokens.
theme_p = os.path.join(home, "share", "Gui", "Stylesheets", "parameters",
                       PRODUCT + " Dark.yaml")
up_p = os.path.join(home, "share", "Gui", "Stylesheets", "parameters",
                    "FreeCAD Dark.yaml")


def _keys(p):
    ks = set()
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#")[0]
            if ":" in line and not line.startswith((" ", "\t")):
                ks.add(line.split(":", 1)[0].strip())
    return ks


try:
    missing = _keys(up_p) - _keys(theme_p)
    row("theme tokens", "%d keys" % len(_keys(theme_p)), not missing,
        "FAIL (missing %s)" % sorted(missing)[:4], key="theme-tokens")
except Exception as e:                                   # noqa: BLE001
    row("theme tokens", "compare", False, "FAIL (%s)" % e, key="theme-tokens")

# R52: every @Token any shipped sheet requests -- the overlay sheet included,
# which OverlayManager resolves too -- must be defined by BOTH Atech themes,
# or FreeCAD logs "Requested non-existent style parameter token" on every
# reload. ThemeAccentColor1..3 come from BuiltInParameterSource
# (StyleParameters/ParameterManager.h:283), not from a YAML.
import glob
import re
_sd = os.path.join(home, "share", "Gui", "Stylesheets")
_tok = re.compile(r"@([A-Za-z0-9_]+)")
try:
    _want = set()
    for _q in ([os.path.join(_sd, "FreeCAD.qss")]
               + glob.glob(os.path.join(_sd, "overlay", "*.qss"))
               + glob.glob(os.path.join(_sd, "Atech*.qss"))):
        with open(_q, encoding="utf-8") as fh:
            _want |= set(_tok.findall(re.sub(r"/\*.*?\*/", "", fh.read(),
                                             flags=re.S)))
    _want -= {"ThemeAccentColor1", "ThemeAccentColor2", "ThemeAccentColor3"}
    for _mode in ("Light", "Dark"):
        _tp = os.path.join(_sd, "parameters", "%s %s.yaml" % (PRODUCT, _mode))
        _gap = sorted(_want - _keys(_tp))
        row("theme tokens", "sheets vs %s" % _mode, not _gap,
            "FAIL (undefined %s)" % _gap[:4], key="theme-refs:" + _mode)
except Exception as e:                                   # noqa: BLE001
    row("theme tokens", "sheet refs", False, "FAIL (%s)" % e,
        key="theme-refs")

print("VERIFY_FAILURES=%d" % len(bad))
for b in bad:
    print("VERIFY_FAILED %s" % b)
