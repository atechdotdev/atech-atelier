"""AcadAgent - AI agent workbench for FreeCAD."""
import os
import sys

__version__ = "0.1.0"
PRODUCT = "Atech Atelier"


def fallback_data_root():
    """The product's user data folder when FreeCAD cannot be asked (no
    FreeCAD module: tests, the eval harness). FreeCAD itself names it after
    branding.xml's ExeName: ~/Library/Application Support/<name> on macOS
    (MEASURED with FreeCAD 1.1.3), ~/.local/share/<name> elsewhere."""
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/" + PRODUCT)
    return os.path.expanduser("~/.local/share/" + PRODUCT)


def macos_bundle():
    """The .app bundle this addon runs from (realpath), else None. Only on
    macOS. FreeCAD's macOS binary puts the bundle's own bin/ and every
    Mod/<name>/ folder in front of PATH (MEASURED, FreeCAD 1.1.3), so a
    child the user or the agent runs would find the bundle's python and pip
    first; strip_bundle_paths() takes them out again."""
    if sys.platform != "darwin":
        return None
    p = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
    while p and p != os.path.dirname(p):
        if p.endswith(".app"):
            return p
        p = os.path.dirname(p)
    return None


def strip_bundle_paths(env, top=None):
    """`env` (a dict, changed in place and returned) without the entries of
    list variables that point into the bundle `top` (default macos_bundle()).
    Only those entries go; a variable left empty is removed."""
    top = (top or macos_bundle() or "").rstrip("/")
    if not top:
        return env
    root = top + "/"
    for k, v in list(env.items()):
        parts = v.split(os.pathsep)
        keep = [x for x in parts if not (x == top or x.startswith(root))]
        if len(keep) == len(parts):
            continue
        if any(keep):
            env[k] = os.pathsep.join(keep)
        else:
            env.pop(k)
    return env
