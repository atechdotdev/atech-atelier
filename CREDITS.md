# Atech Atelier, powered by FreeCAD — credits

Atech Atelier exists because other people built, and gave away, the hard parts.
This page thanks them and says exactly what we use, under which licence, in
which version, and where the licence text sits inside the app.

Every version below was **measured** from the shipped image (0.1.0 on
FreeCAD 1.1.3, measured before the product took the name Atech Atelier; the
rename changed no component), not copied from a website. How each one was measured
is in the table at the end. Paths such as `usr/share/doc/...` are relative to
the root of the AppImage (run it with `--appimage-extract` to browse them).

---

## FreeCAD — the foundation

**Atech Atelier is FreeCAD.** Every solid, every sketch, every measurement and
the whole application window come from [FreeCAD](https://www.freecad.org), the
open-source parametric 3D modeller built by Jürgen Riegel, Werner Mayer, Yorik
van Havre and thousands of contributors since 2001. Atech adds a workbench, a
theme and a name on top, plus the extras listed below. Thank you to the FreeCAD project and its community.

| | |
|---|---|
| What we ship | the official FreeCAD **1.1.3** Linux AppImage. FreeCAD's program files are **unmodified**: no FreeCAD source file is patched or recompiled. Atech changes only the AppImage's launcher script (`AppRun`), its icon and its desktop/AppStream entries, and adds its own files; every change is listed in `ATECH_CHANGES.txt` |
| Upstream image | `FreeCAD_1.1.3-Linux-x86_64-py311.AppImage`, sha256 `3a853eb69ee595f779f2255dbf80a765926981d8ff68903cefee4dfb03a8f5ef`, from the FreeCAD tag 1.1.3 (commit `145529fe741292ff0b3977a01195bf0247425794`) |
| Licence | **LGPL-2.0-or-later**. FreeCAD's own licence page (`usr/share/doc/FreeCAD/LICENSE.html`) says "LGPL2+" and ships the text of the GNU Library General Public License, version 2. © Jürgen Riegel, who started FreeCAD in 2001, and the FreeCAD contributors |
| Licence text in the app | `usr/share/doc/FreeCAD/LICENSE.html` |
| Its own library list | `usr/share/doc/FreeCAD/ThirdPartyLibraries.html` |
| What Atech changed | `usr/share/doc/atech-atelier/ATECH_CHANGES.txt` lists every added, removed or changed file, measured against the upstream image |
| Source code | `usr/share/doc/atech-atelier/SOURCE_OFFER.txt` |

Atech Atelier is **not** endorsed by, affiliated with, or a product of the
FreeCAD project. "FreeCAD" is the FreeCAD project's name; we use it only to say
truthfully what we are built on.

### How the FreeCAD binaries were built

We repackage the FreeCAD team's own release build. That build was made with
[rattler-build](https://github.com/prefix-dev/rattler-build) and
[pixi](https://pixi.sh) from [conda-forge](https://conda-forge.org) packages:
the FreeCAD libraries carry the path of that build's rattler-build/pixi
environment on the FreeCAD project's GitHub Actions runner, and
`packages.txt` at the root of the image lists **326 bundled packages** — 324
from conda-forge, `ifcopenshell` from the `freecad` channel, and FreeCAD itself.
Thanks to the conda-forge community, whose feedstocks
(`https://github.com/conda-forge/<package>-feedstock`) hold the recipe and
source of every one of them.

---

## Libraries that come with FreeCAD

These ship inside the FreeCAD image exactly as upstream built them. The list
below names the ones Atech Atelier leans on most; `packages.txt` has all 326.

| Component | What it does for us | Licence | Version we ship | Licence text in the app | Link |
|---|---|---|---|---|---|
| **Open CASCADE Technology (OCCT)** | the geometry kernel: every solid, boolean, volume and interference check | LGPL-2.1 with the Open CASCADE exception | 7.8.1 | `usr/share/doc/opencascade/LICENSE_LGPL_21.txt`, `OCCT_LGPL_EXCEPTION.txt` | https://dev.opencascade.org |
| **Qt 6** | the whole user interface | LGPL-3.0 | 6.8.3 | named in `ThirdPartyLibraries.html`; no Qt licence file ships in the image (LGPL-3 text: `usr/share/doc/mpfr/COPYING.LESSER`) | https://www.qt.io |
| **PySide6 / Shiboken6** (Qt for Python) | our workbench, chat and dialogs are PySide6 code | LGPL-3.0 / GPL-2.0 (per `ThirdPartyLibraries.html`) | 6.8.3 / 6.8.3 | named in `ThirdPartyLibraries.html` | https://wiki.qt.io/Qt_for_Python |
| **Coin3D** | the 3D scene graph behind the viewport | BSD-3-Clause | 4.0.3 (`libCoin.so.80.0.3`) | named in `ThirdPartyLibraries.html` | https://coin3d.github.io |
| **SoQt** | binds Coin3D to Qt | BSD-3-Clause (upstream `COPYING`, © Kongsberg Oil & Gas Technologies AS) — *no licence file in the image* | 1.6.3 (`libSoQt.so.20.6.3`) | none in the image | https://github.com/coin3d/soqt |
| **Pivy** | Python bindings to Coin3D, used by our viewport code | ISC-style permissive licence (upstream `LICENSE`, © 2002-2007 Systems in Motion) — *no licence file in the image* | 0.6.9 | none in the image | https://github.com/coin3d/pivy |
| **Python** | the language FreeCAD and all of Atech's code run in | PSF License | 3.11.14 (conda-forge build) | `usr/lib/python3.11/LICENSE.txt` | https://www.python.org |
| **NumPy** | numerics in the agent kit's checks (`check.py`) | BSD-3-Clause | 1.26.4 | `usr/lib/python3.11/site-packages/numpy-1.26.4.dist-info/LICENSE.txt` | https://numpy.org |
| **matplotlib** | bundled by FreeCAD (plots); ships the DejaVu fonts below | Matplotlib License (PSF-based) | 3.10.8 | `usr/lib/python3.11/site-packages/matplotlib-3.10.8.dist-info/LICENSE` | https://matplotlib.org |
| **PyYAML** | reads the Atech module library (`presets.yaml`) | MIT | 6.0.3 | `usr/lib/python3.11/site-packages/pyyaml-6.0.3.dist-info/licenses/` | https://pyyaml.org |
| **Boost** | C++ foundations throughout FreeCAD | Boost Software License 1.0 | 1.86.0 | named in `ThirdPartyLibraries.html` | https://www.boost.org |
| **VTK** | FEM and mesh visualisation | BSD-3-Clause | 9.3.1 | `usr/share/licenses/VTK/` | https://vtk.org |
| **Xerces-C** | XML parsing (FreeCAD documents, parameters) | Apache-2.0 | 3.3.0 | named in `ThirdPartyLibraries.html` | https://xerces.apache.org/xerces-c |
| **Eigen** | linear algebra | MPL-2.0 | 3.4.0 | named in `ThirdPartyLibraries.html` | https://eigen.tuxfamily.org |
| **zlib** | compression (`.FCStd` files are zip archives) | zlib License | 1.3.2 | named in `ThirdPartyLibraries.html` | https://zlib.net |
| **FreeType** | font rendering, including text on models | FreeType License | 2.14.3 | named in `ThirdPartyLibraries.html` | https://freetype.org |
| **Salome SMESH** | meshing | LGPL-2.1 | 9.9.0.0 in `packages.txt`; `ThirdPartyLibraries.html` says 9.8.0.2 (the two disagree) | named in `ThirdPartyLibraries.html` | https://www.salome-platform.org |
| **Gmsh** | FEM meshing | GPL-2.0-or-later with an exception | 4.15.0 | `usr/share/doc/gmsh/LICENSE.txt` | https://gmsh.info |
| **Point Cloud Library** | point-cloud import | BSD-3-Clause | 1.15.0 | named in `ThirdPartyLibraries.html` | https://pointclouds.org |
| **fcgear** (in FreeCAD's PartDesign) | the involute generator behind the agent kit's `spur_gear()`: real gear teeth | LGPL-2.0-or-later, © 2014 David Douard, © 2023 Jonas Bähr | ships with FreeCAD 1.1.3; no separate version | header of `usr/Mod/PartDesign/fcgear/involute.py` | https://github.com/FreeCAD/FreeCAD/tree/main/src/Mod/PartDesign/fcgear |

---

## What Atech adds to the image

| Component | What we use it for | Licence | Version we ship | Licence text in the app | Link |
|---|---|---|---|---|---|
| **FreeCADMCP** (the FreeCAD addon half of freecad-mcp, by neka-nat) | the RPC server that lets the agent drive the running FreeCAD | MIT, © 2025 Shirokuma (k tanaka) | commit `adc8e52dd940e5ed602d0f5b850705e5cf38d780`, **modified by Atech** (patches ship in `usr/share/doc/atech-atelier/third_party/FreeCADMCP-patches/`) | `usr/Mod/FreeCADMCP/LICENSE`, `usr/share/doc/atech-atelier/third_party/LICENSE.FreeCADMCP` | https://github.com/neka-nat/freecad-mcp |
| **Lucide** | icon outlines, inlined in our stylesheet code | ISC, © Lucide Icons and Contributors | path data from lucide commit `66d8f9fc394b8530377e5f6112f0b8908ba01280` | `usr/share/doc/atech-atelier/third_party/LICENSE.Lucide` | https://lucide.dev |
| **Feather** | the icons Lucide derives from Feather | MIT, © 2013-present Cole Bemis | licence fetched at feather commit `3dc050d97405062eba78aa57115c0a15c63abdaa` | `usr/share/doc/atech-atelier/third_party/LICENSE.Feather` | https://feathericons.com |

---

## Used by Atech, supplied by FreeCAD or by your system

| Component | What we use it for | Licence | Version | Licence text | Link |
|---|---|---|---|---|---|
| **DejaVu fonts** | `DejaVuSans.ttf` is the font the build sandbox offers model scripts for text on parts; the UI falls back to DejaVu Sans / Sans Mono when our brand fonts are absent | Bitstream Vera Fonts licence; DejaVu changes public domain; Arev glyphs © Tavmjong Bah | your system's copy first (on the reference machine: Ubuntu `fonts-dejavu-core`, "Version 2.37"); else FreeCAD's `usr/fonts/DejaVuSans.ttf`, "Version 2.37"; matplotlib's copies are "Version 2.35" | `usr/lib/python3.11/site-packages/matplotlib/mpl-data/fonts/ttf/LICENSE_DEJAVU` | https://dejavu-fonts.github.io |
| **bubblewrap** (`bwrap`) | isolates each design build: read-only root, no network, no view of your home | LGPL-2.0-or-later | **not bundled** — used from your system if installed (reference machine: 0.9.0, Ubuntu package 0.9.0-1ubuntu0.1) | your system's `/usr/share/doc/bubblewrap/copyright` | https://github.com/containers/bubblewrap |

## Build tooling (not in the app)

| Component | What we use it for | Licence | Version | Link |
|---|---|---|---|---|
| **appimagetool** (AppImage project) | repacks the branded tree into the `.AppImage`; it also embeds the AppImage type-2 runtime, which does ship inside every image | MIT (appimagetool and type2-runtime upstream `LICENSE`) | version not determined: appimagetool was not installed on the build machine that produced the current tree, so it has not been run yet | https://github.com/AppImage/appimagetool |

## Required external tool: Claude Code

The chat panel drives **Claude Code** (the `claude` command-line tool by
Anthropic, https://claude.com/claude-code), which you install and sign in to
yourself. It is a **proprietary** Anthropic product, **not** open source,
and **not** included in Atech Atelier: we run your installed copy, under
Anthropic's own terms. Without it the chat has no agent; the rest of FreeCAD
works as usual.

---

## Atech's own code and models

Decided 2026-10-03 (ADR-006):

| What | Licence | Licence text in the app |
|---|---|---|
| Atech's code: the `AcadAgent` workbench, the branding and the build scripts | LGPL-2.1-or-later | `usr/share/doc/atech-atelier/LICENSE` |
| the Atech board and module 3D models, and `presets.yaml` | CC BY-NC 4.0 (non-commercial use, with credit to Atech) | `usr/Mod/AcadAgent/data/models/LICENSE-models.md`, `usr/share/doc/atech-atelier/LICENSE-models.md` |

The two licences are separate and each covers only its own files.

---

## How the versions were measured

| Component | Version | Measured with |
|---|---|---|
| FreeCAD | 1.1.3 (commit 145529fe) | `FreeCAD.Version()` under the bundled `freecadcmd`; `freecadcmd --version` |
| OCCT | 7.8.1 | `Part.OCC_VERSION`; `libTKernel.so.7.8.1` |
| Python | 3.11.14 | `sys.version` under `freecadcmd` |
| Qt | 6.8.3 | `PySide6.QtCore.qVersion()`; `libQt6Core.so.6.8.3` |
| PySide6 / Shiboken6 | 6.8.3 / 6.8.3 | `PySide6.__version__`, `shiboken6.__version__` |
| Pivy | 0.6.9 | `pivy.__version__` |
| Coin3D | 4.0.3 | `pivy.coin` version under `freecadcmd`; `packages.txt`; `libCoin.so.80.0.3` |
| SoQt | 1.6.3 | `packages.txt` (`soqt6`); `libSoQt.so.20.6.3` |
| NumPy | 1.26.4 | `numpy.__version__` |
| matplotlib | 3.10.8 | `matplotlib.__version__` |
| PyYAML | 6.0.3 | `yaml.__version__` |
| zlib | 1.3.2 | `zlib.ZLIB_RUNTIME_VERSION`; `libz.so.1.3.2` |
| Boost | 1.86.0 | `libboost_system.so.1.86.0`; `packages.txt` |
| VTK | 9.3.1 | `libvtkCommonCore-9.3.so`; `packages.txt` |
| Xerces-C | 3.3.0 | `libxerces-c-3.3.so`; `packages.txt` |
| Eigen | 3.4.0 | `packages.txt`; `ThirdPartyLibraries.html` |
| FreeType | 2.14.3 | `packages.txt`; `libfreetype.so.6.20.6` |
| SMESH | 9.9.0.0 / 9.8.0.2 | `packages.txt` / `ThirdPartyLibraries.html` (they disagree) |
| Gmsh | 4.15.0 | `packages.txt` |
| PCL | 1.15.0 | `packages.txt` |
| DejaVu Sans | 2.37 (FreeCAD `usr/fonts`), 2.35 (matplotlib) | the font's own name table (`FT2Font.get_sfnt()`, name id 5) |
| FreeCADMCP | adc8e52d | `branding/vendor/freecad-mcp/UPSTREAM` |
| bubblewrap (host) | 0.9.0 | `bwrap --version`, `dpkg -s bubblewrap` |
| appimagetool | not determined | not on the build machine's PATH |
