#!/usr/bin/env python3
"""macOS bundle identity for build_macos.sh: Info.plist and the app icon.

    macos_bundle.py plist <Info.plist> <version> <icon.icns name>
    macos_bundle.py icns  <icon.svg> <out.icns>          (run with a python
                                                          that has PySide6)

plist rewrites FreeCAD's Info.plist in place so the bundle is Atech
Atelier's, not FreeCAD's:

  - CFBundleIdentifier, CFBundleName, CFBundleDisplayName: the product
    (APP_ID and PRODUCT below; the gate, verify_tree.py, carries its own copy);
  - the version (root VERSION) in CFBundleShortVersionString and
    CFBundleVersion;
  - CFBundleIconFile: the Atech icon;
  - NSHumanReadableCopyright: Atech, "powered by FreeCAD", FreeCAD's own
    copyright banner and licence;
  - document types stay (the app opens .FCStd and friends) but at
    LSHandlerRank Alternate and without LSIsAppleDefaultForType, so
    installing Atech Atelier never takes .FCStd from an installed FreeCAD;
  - FreeCAD's exported UTI (org.freecad.fcstd) becomes an IMPORTED
    declaration: the type is FreeCAD's to define, not ours.

CFBundleExecutable stays "FreeCAD": the binary is FreeCAD's, unmodified
apart from the code signature that build_macos.sh replaces.

icns renders the SVG at every iconset size with Qt's SVG renderer (the
bundled FreeCAD's PySide6, so the build needs no Inkscape or ImageMagick)
and packs them with iconutil.
"""
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile

PRODUCT = "Atech Atelier"
APP_ID = "dev.atech.Atelier"
COPYRIGHT = ("© 2026 Atech. %s, powered by FreeCAD. FreeCAD: (C) 2001-2026 "
             "FreeCAD contributors, LGPL2+. Not endorsed by or affiliated "
             "with the FreeCAD project or the FreeCAD Project Association."
             % PRODUCT)


def stamp_plist(pl, version, icon):
    pl["CFBundleIdentifier"] = APP_ID
    pl["CFBundleName"] = PRODUCT
    pl["CFBundleDisplayName"] = PRODUCT
    pl["CFBundleShortVersionString"] = version
    pl["CFBundleVersion"] = version
    pl["CFBundleIconFile"] = icon
    pl["CFBundleGetInfoString"] = "%s %s, powered by FreeCAD" % (PRODUCT, version)
    pl["CFBundleLongVersionString"] = version
    pl["NSHumanReadableCopyright"] = COPYRIGHT
    for d in pl.get("CFBundleDocumentTypes") or []:
        d.pop("LSIsAppleDefaultForType", None)
        d["LSHandlerRank"] = "Alternate"
    exported = pl.pop("UTExportedTypeDeclarations", None)
    if exported:
        imported = pl.setdefault("UTImportedTypeDeclarations", [])
        ids = {t.get("UTTypeIdentifier") for t in imported}
        imported.extend(t for t in exported if t.get("UTTypeIdentifier") not in ids)
    return pl


def cmd_plist(path, version, icon):
    with open(path, "rb") as fh:
        pl = plistlib.load(fh)
    stamp_plist(pl, version, icon)
    with open(path, "wb") as fh:
        plistlib.dump(pl, fh)


# iconutil's names: icon_<n>x<n>[@2x].png
ICONSET = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
           (256, 1), (256, 2), (512, 1), (512, 2)]


def cmd_icns(svg, out):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtSvg
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])  # noqa: F841
    renderer = QtSvg.QSvgRenderer(svg)
    if not renderer.isValid():
        sys.exit("FAIL cannot read %s" % svg)
    tmp = tempfile.mkdtemp(prefix="atech-iconset-")
    try:
        iconset = os.path.join(tmp, "atech.iconset")
        os.mkdir(iconset)
        for size, scale in ICONSET:
            px = size * scale
            img = QtGui.QImage(px, px, QtGui.QImage.Format_ARGB32)
            img.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(img)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            renderer.render(p, QtCore.QRectF(0, 0, px, px))
            p.end()
            name = "icon_%dx%d%s.png" % (size, size, "@2x" if scale == 2 else "")
            if not img.save(os.path.join(iconset, name), "PNG"):
                sys.exit("FAIL could not write %s" % name)
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    if len(argv) == 4 and argv[0] == "plist":
        cmd_plist(*argv[1:])
    elif len(argv) == 3 and argv[0] == "icns":
        cmd_icns(*argv[1:])
    else:
        sys.stderr.write(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
