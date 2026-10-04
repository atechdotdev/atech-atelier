# Atech Atelier, powered by FreeCAD — credits

Atech Atelier exists because other people built, and gave away, the hard parts.
This page thanks them and says exactly what we use, under which licence, in
which version, and where the licence text sits inside the app.

Every version below was **measured** from the shipped image, not copied from a
website: the 0.1.0 image on FreeCAD 1.1.3 (some of it measured before the
product took the name Atech Atelier; the rename changed no component). 0.1.1
corrects these credits and adds licence texts; it builds on the same pinned
upstream FreeCAD image, so the bundled components are the same. How each
version was measured is in the table at the end. Paths such as
`usr/share/doc/...` are relative to the root of the AppImage (run it with
`--appimage-extract` to browse them).

---

## FreeCAD — the foundation

**Atech Atelier is built on FreeCAD.** Every solid, every sketch, every
measurement and the whole application window come from
[FreeCAD](https://www.freecad.org), the open-source parametric 3D modeller
started by Jürgen Riegel in 2001 and built since by Werner Mayer, Yorik van
Havre and thousands of other contributors. Atech adds a workbench, a theme and
a name on top, plus the extras listed below. Thank you to the FreeCAD project
and its community.

| | |
|---|---|
| What we ship | the official FreeCAD **1.1.3** Linux AppImage, with FreeCAD's program files **unmodified**: no FreeCAD source file is patched or recompiled. Atech changes only the AppImage's launcher script (`AppRun`), its icon and its desktop/AppStream entries, and adds its own files (among them a FreeCAD branding file, `usr/bin/branding.xml`, which sets the name and the About text); every change is listed in `ATECH_CHANGES.txt` |
| Upstream image | `FreeCAD_1.1.3-Linux-x86_64-py311.AppImage`, sha256 `3a853eb69ee595f779f2255dbf80a765926981d8ff68903cefee4dfb03a8f5ef`, from the FreeCAD tag 1.1.3 (commit `145529fe741292ff0b3977a01195bf0247425794`) |
| Copyright | "(C) 2001-2026 FreeCAD contributors" (FreeCAD 1.1.3's own About banner, verbatim) |
| Licence | the GNU LGPL, version 2 or (at your option) any later version: **"LGPL2+"**, as FreeCAD states it in its licence page (`usr/share/doc/FreeCAD/LICENSE.html`: "The FreeCAD application is licensed under the terms of the LGPL2+ license") and its About banner ("FreeCAD is free and open-source software licensed under the terms of LGPL2+ license"). SPDX writes LGPL2+ as `LGPL-2.0-or-later`. FreeCAD's repository `LICENSE` file is the LGPL 2.1 text, and many of its source files carry `SPDX-License-Identifier: LGPL-2.1-or-later` (1027 of the 1533 Python files FreeCAD ships under `usr/Mod`) |
| Licence text in the app | `usr/share/doc/FreeCAD/LICENSE.html` (the GNU Library General Public License, version 2) |
| Its own library list | `usr/share/doc/FreeCAD/ThirdPartyLibraries.html` |
| What Atech changed | `usr/share/doc/atech-atelier/ATECH_CHANGES.txt` lists every added, removed or changed file, measured against the upstream image |
| Source code | `usr/share/doc/atech-atelier/SOURCE_OFFER.txt` |

Atech Atelier is **not** endorsed by, affiliated with, or a product of the
FreeCAD project or the FreeCAD Project Association. The FreeCAD logo is a
registered trademark (Benelux) of the FreeCAD Project Association AISBL (FPA),
which holds the rights over commercial use of the FreeCAD name and logo. We
use the name only to say what Atech Atelier is built on.

### How the FreeCAD binaries were built

We repackage the FreeCAD team's own release build. That build was made with
[rattler-build](https://github.com/prefix-dev/rattler-build) and
[pixi](https://pixi.sh) from [conda-forge](https://conda-forge.org) packages:
the FreeCAD libraries carry the path of that build's rattler-build/pixi
environment on the FreeCAD project's GitHub Actions runner, and
`packages.txt` at the root of the image lists **326 bundled packages**: 324
from conda-forge, `ifcopenshell` from the `freecad` channel, and FreeCAD itself.
Thanks to the conda-forge community. A package's recipe, with its upstream
source URL and sha256, lives in the conda-forge feedstock that builds it,
which is often named after the source project rather than the package (for
example `qt6-main` is built by `conda-forge/qt-main-feedstock`, `libboost` by
`boost-feedstock`, `vtk-base` by `vtk-feedstock`, `soqt6` by
`soqt-feedstock`).

---

## Libraries that come with FreeCAD

These ship inside the FreeCAD image exactly as upstream built them. The list
below names the ones Atech Atelier leans on most and the ones with notable
licence terms; `packages.txt` lists all 326 conda packages. FreeCAD also
compiles in KDL, libarea, Ondsel Solver, PyCXX and Zipios++, which are listed
with their licences in `usr/share/doc/FreeCAD/ThirdPartyLibraries.html`.

Where licence texts are: FreeCAD's own list is
`usr/share/doc/FreeCAD/ThirdPartyLibraries.html`; every bundled package is
listed in `packages.txt` at the image root; the licence texts that ship are in
`usr/share/doc/<package>/`, `usr/share/licenses/` and
`usr/lib/python3.11/site-packages/*.dist-info/`, and Atech adds the texts that
were missing under `usr/share/doc/atech-atelier/third_party/`.

| Component | What it does for us | Licence | Version we ship | Licence text in the app | Link |
|---|---|---|---|---|---|
| **Open CASCADE Technology (OCCT)** | the geometry kernel: every solid, boolean, volume and interference check | LGPL-2.1 with the Open CASCADE exception | 7.8.1 | `usr/share/doc/opencascade/LICENSE_LGPL_21.txt`, `OCCT_LGPL_EXCEPTION.txt` | https://dev.opencascade.org |
| **Qt 6** | the whole user interface | LGPL-3.0-only for the modules FreeCAD uses (open-source Qt is offered under LGPL-3.0 or GPL; some modules shipped in the image, such as Qt Qml Compiler and Qt Wayland Compositor, are GPL-3.0 only in open-source Qt) | 6.8.3 | no Qt licence file ships with FreeCAD; GNU LGPL v3 and GNU GPL v3 texts: `usr/share/doc/atech-atelier/third_party/LICENSE.LGPL-3.0`, `LICENSE.GPL-3.0` (also `usr/share/doc/mpfr/COPYING.LESSER`, `COPYING`) | https://www.qt.io |
| **PySide6 / Shiboken6** (Qt for Python) | our workbench, chat and dialogs are PySide6 code | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only (we use it under LGPL-3.0; FreeCAD's `ThirdPartyLibraries.html` says "LGPL version 3 / GPL version 2") | 6.8.3 / 6.8.3 | no PySide licence file in the image; LGPL-3 / GPL-3 texts as for Qt | https://wiki.qt.io/Qt_for_Python |
| **Coin3D** | the 3D scene graph behind the viewport | BSD-3-Clause, © Kongsberg Oil & Gas Technologies AS | 4.0.3 (`libCoin.so.80.0.3`) | `usr/share/doc/atech-atelier/third_party/LICENSE.Coin3D` | https://coin3d.github.io |
| **SoQt** | binds Coin3D to Qt | BSD-3-Clause, © Kongsberg Oil & Gas Technologies AS | 1.6.3 (`libSoQt.so.20.6.3`; conda-forge package `soqt6`, feedstock `conda-forge/soqt-feedstock`) | `usr/share/doc/atech-atelier/third_party/LICENSE.SoQt` | https://github.com/coin3d/soqt |
| **Pivy** | Python bindings to Coin3D, used by our viewport code | ISC-style permissive licence (© 2002-2007 Systems in Motion / 2002-2008 Kongsberg SIM) | 0.6.9 | no separate licence file; the permission notice is in the header of `usr/lib/python3.11/site-packages/pivy/__init__.py` | https://github.com/coin3d/pivy |
| **Python** | the language FreeCAD and all of Atech's code run in | PSF License | 3.11.14 (conda-forge build) | `usr/lib/python3.11/LICENSE.txt` | https://www.python.org |
| **NumPy** | numerics in the agent kit's checks (`check.py`) | BSD-3-Clause | 1.26.4 | `usr/lib/python3.11/site-packages/numpy-1.26.4.dist-info/LICENSE.txt` | https://numpy.org |
| **matplotlib** | bundled by FreeCAD (plots); ships the DejaVu fonts below | Matplotlib License (PSF-based) | 3.10.8 | `usr/lib/python3.11/site-packages/matplotlib-3.10.8.dist-info/LICENSE` | https://matplotlib.org |
| **PyYAML** | reads the Atech module library (`presets.yaml`) | MIT | 6.0.3 | `usr/lib/python3.11/site-packages/pyyaml-6.0.3.dist-info/licenses/` | https://pyyaml.org |
| **Boost** | C++ foundations throughout FreeCAD | Boost Software License 1.0 | 1.86.0 | named in `ThirdPartyLibraries.html` | https://www.boost.org |
| **VTK** | FEM and mesh visualisation | BSD-3-Clause | 9.3.1 | `usr/share/licenses/VTK/` | https://vtk.org |
| **Xerces-C** | XML parsing (FreeCAD documents, parameters) | Apache-2.0 | 3.3.0 | `usr/share/doc/atech-atelier/third_party/LICENSE.Xerces-C` | https://xerces.apache.org/xerces-c |
| **Eigen** | linear algebra | MPL-2.0 | 3.4.0 | named in `ThirdPartyLibraries.html` | https://eigen.tuxfamily.org |
| **zlib** | compression (`.FCStd` files are zip archives) | zlib License | 1.3.2 | named in `ThirdPartyLibraries.html` | https://zlib.net |
| **FreeType** | font rendering, including text on models | FreeType License (FTL); FreeType is dual-licensed FTL or GPL-2.0-or-later and is used here under the FTL | 2.14.3 | see the FTL credit below; FTL text: `usr/share/doc/atech-atelier/third_party/LICENSE.FreeType-FTL` (docs/FTL.TXT at FreeType tag VER-2-14-3) | https://freetype.org |
| **Salome SMESH** | meshing | LGPL-2.1-or-later | 9.9.0.0 (the conda-forge package FreeCAD links at run time: `MeshPart.so` needs `libSMESH.so`; FreeCAD's `ThirdPartyLibraries.html` lists 9.8.0.2), together with the Netgen mesher it bundles (`libnglib4smesh.so`, `libNETGENPlugin.so`; LGPL-2.1) | LGPL-2.1 text: `usr/share/doc/opencascade/LICENSE_LGPL_21.txt` | https://www.salome-platform.org |
| **Gmsh** | FEM meshing, which FreeCAD runs as a separate program (`usr/bin/gmsh`, `usr/lib/libgmsh.so.4.15.0`) | GPL-2.0-or-later with the Gmsh exception, © 1997-2025 Christophe Geuzaine and Jean-François Remacle | 4.15.0 | `usr/share/doc/gmsh/LICENSE.txt` | https://gmsh.info |
| **CalculiX** (`ccx`) | the FEM solver that FreeCAD's FEM workbench runs as a separate program | GPL-2.0-or-later (conda-forge's metadata), © 1998-2025 Guido Dhondt | 2.23 | GPL-2 text: `usr/share/doc/gmsh/LICENSE.txt` (after the Gmsh exception) | http://www.calculix.de |
| **FFmpeg** | video encode/decode for VTK's movie export (`libvtkIOFFMPEG`) | GPL-2.0-or-later (conda-forge's GPL build, linked with x264 and x265) | 7.1.1 | GPL-2 text: `usr/share/doc/gmsh/LICENSE.txt` (after the Gmsh exception) | https://ffmpeg.org |
| **x264** | H.264 encoder used by FFmpeg | GPL-2.0-or-later | 0.164.3095 (conda package `1!164.3095`) | as FFmpeg | https://www.videolan.org/developers/x264.html |
| **x265** | HEVC encoder used by FFmpeg | GPL-2.0-or-later | 3.5 | as FFmpeg | https://www.x265.org |
| **GNU Readline** | line editing for the bundled Python's `readline` module | GPL-3.0 (conda-forge declares GPL-3.0-only) | 8.3 | GPL-3 text: `usr/share/doc/atech-atelier/third_party/LICENSE.GPL-3.0` (also `usr/share/doc/mpfr/COPYING`) | https://tiswww.case.edu/php/chet/readline/rltop.html |
| **IfcOpenShell** | IFC import/export for FreeCAD's BIM workbench | LGPL-3.0-or-later, © Thomas Krijnen and contributors | 0.8.4 (from the FreeCAD project's `freecad` conda channel) | no IfcOpenShell licence file ships; LGPL-3 text: `usr/share/doc/atech-atelier/third_party/LICENSE.LGPL-3.0` | https://ifcopenshell.org |
| **Point Cloud Library** | point-cloud import | BSD-3-Clause | 1.15.0 | `usr/share/doc/atech-atelier/third_party/LICENSE.PCL` | https://pointclouds.org |
| **fcgear** (in FreeCAD's PartDesign) | the involute generator behind the agent kit's `spur_gear()`: real gear teeth | LGPL-2.0-or-later, © 2014 David Douard, © 2023 Jonas Bähr | ships with FreeCAD 1.1.3; no separate version | header of `usr/Mod/PartDesign/fcgear/involute.py` | https://github.com/FreeCAD/FreeCAD/tree/main/src/Mod/PartDesign/fcgear |

**FreeType credit.** Portions of this software are copyright © 2026 The
FreeType Project (https://freetype.org). All rights reserved. Atech Atelier is
based in part on the work of the FreeType Team.

**Other copyleft packages in the image** include pythonocc-core (LGPL-3.0),
CGAL (GPL-3.0-or-later / LGPL-3.0-or-later, texts in `usr/share/doc/CGAL/`),
MPFR/GMP/MPC (LGPL-3.0, `usr/share/doc/mpfr/`), Netgen as built into SMESH
(LGPL-2.1), the MySQL client library (GPL-2.0 per conda-forge's metadata; no
licence text ships) and libgfortran (GPL-3.0 with the GCC Runtime Library
Exception; the exception text is in `usr/share/licenses/libgfortran/`).
`packages.txt` lists every package.

---

## What Atech adds to the image

| Component | What we use it for | Licence | Version we ship | Licence text in the app | Link |
|---|---|---|---|---|---|
| **FreeCADMCP** (the FreeCAD addon half of freecad-mcp, by neka-nat) | an optional XML-RPC server, off by default, that lets an external MCP client (for example the freecad-mcp MCP server) drive the running FreeCAD. Atech Atelier's own chat agent does not use it | MIT, © 2025 Shirokuma (k tanaka) | commit `adc8e52dd940e5ed602d0f5b850705e5cf38d780`, **modified by Atech** (patches ship in `usr/share/doc/atech-atelier/third_party/FreeCADMCP-patches/`) | `usr/Mod/FreeCADMCP/LICENSE`, `usr/share/doc/atech-atelier/third_party/LICENSE.FreeCADMCP` | https://github.com/neka-nat/freecad-mcp |
| **Lucide** | icon outlines, inlined in our stylesheet code | ISC, Copyright (c) 2026 Lucide Icons and Contributors | path data from Lucide (mostly older Lucide releases, e.g. as in tag 0.400.0, some simplified; "chat" is Feather's message-square; "stop" and "tree" drawn by Atech); licence text fetched at lucide commit `66d8f9fc394b8530377e5f6112f0b8908ba01280` | `usr/share/doc/atech-atelier/third_party/LICENSE.Lucide` | https://lucide.dev |
| **Feather** | the icons Lucide derives from Feather, and "chat" | MIT. Feather-derived icons: © 2013-present Cole Bemis (as stated in `LICENSE.Lucide`); Feather's own LICENSE reads © 2013-2023 Cole Bemis (`LICENSE.Feather`) | licence fetched at feather commit `3dc050d97405062eba78aa57115c0a15c63abdaa` | `usr/share/doc/atech-atelier/third_party/LICENSE.Feather` | https://feathericons.com |
| **Theme files derived from FreeCAD's** | `usr/share/Gui/Stylesheets/overlay/Atech Overlay.qss` and `usr/share/Gui/Stylesheets/parameters/Atech Atelier Light.yaml` / `Atech Atelier Dark.yaml` | derived from FreeCAD 1.1.3's `Freecad Overlay.qss` and `FreeCAD Light.yaml` / `FreeCAD Dark.yaml`: FreeCAD's licence ("LGPL2+"), © the FreeCAD contributors, modified by Atech | built with each release | `usr/share/doc/FreeCAD/LICENSE.html` | https://github.com/FreeCAD/FreeCAD |
| **AppImage type-2 runtime** | the launcher embedded at the start of the `.AppImage` file, which mounts and starts the image | MIT, © 2004-23 probonopd. It statically contains, as it declares itself: libfuse 3.15.0 (LGPL-2.1), squashfuse 0.5.2 (BSD-2-Clause), musl libc, libzstd and zlib (each under the licence at the URL the runtime prints) | AppImage/type2-runtime commit `8f39b89` (the runtime's own string); pinned from 0.1.1 to the exact file 0.1.0 carried | in `usr/share/doc/atech-atelier/third_party/`: `LICENSE.type2-runtime` (at commit 8f39b89), `LICENSE.libfuse-LGPL-2.1` (fuse-3.15.0), `LICENSE.squashfuse` (0.5.2), `LICENSE.musl` (COPYRIGHT at v1.2.5; the runtime's musl version is not determined), `LICENSE.zstd` (text from zstd 1.5.7; the runtime's zstd version is not determined) | https://github.com/AppImage/type2-runtime |

---

## Used by Atech, supplied by FreeCAD or by your system

| Component | What we use it for | Licence | Version | Licence text | Link |
|---|---|---|---|---|---|
| **DejaVu fonts** | `DejaVuSans.ttf` is the font the build sandbox offers model scripts for text on parts. The UI uses the first installed of Inter, Segoe UI, Cantarell, DejaVu Sans (mono: Geist Mono, JetBrains Mono, DejaVu Sans Mono, Liberation Mono, Noto Sans Mono); no brand fonts are bundled | Bitstream Vera Fonts licence; DejaVu changes public domain; Arev glyphs © Tavmjong Bah | your system's copy first (on the reference machine: Ubuntu `fonts-dejavu-core`, "Version 2.37"); else FreeCAD's `usr/fonts/DejaVuSans.ttf`, "Version 2.37"; matplotlib's copies are "Version 2.35" | `usr/lib/python3.11/site-packages/matplotlib/mpl-data/fonts/ttf/LICENSE_DEJAVU` | https://dejavu-fonts.github.io |
| **bubblewrap** (`bwrap`) | isolates each design build: read-only root, no network, no view of your home | LGPL-2.0-or-later | **not bundled** — used from your system if installed (reference machine: 0.9.0, Ubuntu package 0.9.0-1ubuntu0.1) | your system's `/usr/share/doc/bubblewrap/copyright` | https://github.com/containers/bubblewrap |
| **opencode** (the `opencode` CLI) | an optional alternative agent engine (a running `opencode serve` on 127.0.0.1:4096). AppRun starts one from `~/.npm-global/bin/opencode` (or `$ATECH_AGENT_BIN`) only when `ATECH_AGENT_AUTOSTART=1` is set (off by default), and stops what it started on exit | MIT, Copyright (c) 2025 opencode | **not bundled** | upstream `LICENSE` | https://github.com/sst/opencode |

## Build tooling (not in the app)

| Component | What we use it for | Licence | Version | Link |
|---|---|---|---|---|
| **appimagetool** (AppImage project) | repacks the branded tree into the `.AppImage`; it also embeds the AppImage type-2 runtime (above), which ships inside every image | MIT, © 2004-25 Simon Peter and the AppImage Team (its licence does not apply to the contents of AppImages) | `appimagetool-1.9.1-x86_64.AppImage` (continuous build, git 8c8c91f, build 296, sha256 `ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0`) | https://github.com/AppImage/appimagetool |

## Required external tool: Claude Code

The chat panel drives **Claude Code** (the `claude` command-line tool by
Anthropic, https://claude.com/claude-code), which you install and sign in to
yourself. It is a **proprietary** Anthropic product, **not** open source,
and **not** included in Atech Atelier: we run your installed copy, under
Anthropic's own terms. Atech Atelier is not endorsed by or affiliated with
Anthropic. Without it the chat has no agent; the rest of FreeCAD works as
usual.

---

## Atech's own code and models

Decided 2026-10-03 (ADR-006):

| What | Licence | Licence text in the app |
|---|---|---|
| Atech's code: the `AcadAgent` workbench, the branding and the build scripts | LGPL-2.1-or-later | `usr/share/doc/atech-atelier/LICENSE` |
| the Atech board and module 3D models, and `presets.yaml` | CC BY-NC 4.0 (non-commercial use; credit Atech, keep the notices, link the licence, say if you changed them) | `usr/Mod/AcadAgent/data/models/LICENSE-models.md`, `usr/share/doc/atech-atelier/LICENSE-models.md` |

The two licences are separate and each covers only its own files. Neither
grants any right to use the names "Atech" or "Atech Atelier" or the Atech
logos except to describe where the software comes from.

---

## How the versions were measured

| Component | Version | Measured with |
|---|---|---|
| FreeCAD | 1.1.3 (commit 145529fe) | `FreeCAD.Version()` under the bundled `freecadcmd`; `freecadcmd --version` |
| FreeCAD copyright banner | "(C) 2001-2026 FreeCAD contributors" | `src/Gui/MainGui.cpp` at tag 1.1.3 (`"(C) 2001-{} FreeCAD contributors"`, year from the build date, `FreeCAD.Version()` build date 2026/07/25) |
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
| FreeType | 2.14.3 | `packages.txt`; `libfreetype.so.6.20.6`; credit year 2026 from FreeType 2.14.3's `freetype.h` ("Copyright (C) 1996-2026") |
| SMESH | 9.9.0.0 / 9.8.0.2 | `packages.txt` / `ThirdPartyLibraries.html` (they disagree); `readelf -d usr/lib/MeshPart.so` |
| Gmsh | 4.15.0 | `packages.txt`; `usr/share/doc/gmsh/CREDITS.txt` for the copyright |
| CalculiX | 2.23 | `packages.txt`; `strings usr/bin/ccx` ("CalculiX Version 2.23, Copyright(C) 1998-2025 Guido Dhondt") |
| FFmpeg / x264 / x265 | 7.1.1 / 1!164.3095 / 3.5 | `packages.txt` (FFmpeg build string `gpl_...`); `readelf -d usr/lib/libavcodec.so.61` |
| GNU Readline | 8.3 | `packages.txt`; `libreadline.so.8.3` |
| IfcOpenShell | 0.8.4 | `ifcopenshell.version` under `freecadcmd`; `packages.txt` (channel `freecad`) |
| PCL | 1.15.0 | `packages.txt` |
| FreeCAD SPDX headers | 1027 of 1533 | `grep -l "SPDX-License-Identifier: LGPL-2.1-or-later"` over the `.py` files under `usr/Mod`, excluding Atech's `AcadAgent` and `FreeCADMCP` |
| AppImage type-2 runtime | commit 8f39b89; libfuse 3.15.0; squashfuse 0.5.2 | `strings` over the runtime (the first 944632 bytes) of the 0.1.0 AppImage |
| DejaVu Sans | 2.37 (FreeCAD `usr/fonts`), 2.35 (matplotlib) | the font's own name table (`FT2Font.get_sfnt()`, name id 5) |
| FreeCADMCP | adc8e52d | `branding/vendor/freecad-mcp/UPSTREAM` |
| bubblewrap (host) | 0.9.0 | `bwrap --version`, `dpkg -s bubblewrap` |
| appimagetool | 1.9.1 (git 8c8c91f, build 296) | `ATECH_CHANGES.txt` "Packed by" line of the 0.1.0 image |

### Where Atech's added licence texts come from

| File in `usr/share/doc/atech-atelier/third_party/` | Taken from |
|---|---|
| `LICENSE.Coin3D` | `COPYING` from the conda-forge `coin3d` 4.0.10 package (upstream Coin3D's `COPYING`, BSD-3-Clause, © Kongsberg Oil & Gas Technologies AS) |
| `LICENSE.SoQt` | `COPYING` from the conda-forge `soqt6` 1.6.3 package |
| `LICENSE.PCL` | `LICENSE.txt` from the conda-forge `pcl` 1.15.1 package |
| `LICENSE.Xerces-C` | `LICENSE` from the conda-forge `xerces-c` 3.3.0 package (the Apache License 2.0) |
| `LICENSE.zstd` | `LICENSE` from the conda-forge `zstd` 1.5.7 package |
| `LICENSE.LGPL-3.0`, `LICENSE.GPL-3.0` | `usr/share/doc/mpfr/COPYING.LESSER` and `COPYING` from the image itself (the GNU LGPL v3 and GPL v3 texts) |
