# Changelog

All notable changes to Atech Atelier are listed here. Versions follow
[Semantic Versioning](https://semver.org). Before 1.0.0, any release may
change behaviour.

## [0.1.1] - 2026-10-04 (preview)

Credits and licence notices corrected. No change to the bundled components:
the same pinned FreeCAD 1.1.3 image.

### Credits corrected

- Licence texts now shipped that 0.1.0 lacked, each taken from the
  component's official repository at the version in the image: the AppImage
  type-2 runtime (MIT), libfuse (LGPL-2.1), squashfuse (BSD-2-Clause), musl
  (MIT) and the FreeType License, alongside the Coin3D, SoQt, PCL,
  Xerces-C, zstd, LGPL-3.0 and GPL-3.0 texts.
- The AppImage runtime is now pinned to the exact file 0.1.0 carried
  (type2-runtime commit 8f39b89) instead of being fetched at pack time.
- Source code is attached to every release from 0.1.1 on: the FreeCAD 1.1.3
  source archive and this repository's source at the release tag.

- FreeCAD's licence is now stated as FreeCAD states it: "LGPL2+" (the GNU
  LGPL version 2 or any later version), from its `LICENSE.html` and About
  banner, noting that its repository `LICENSE` file is the LGPL 2.1 text
  and many source files carry SPDX LGPL-2.1-or-later. The 0.1.0 binary's
  notices said "LGPL-2.1-or-later" without this context (About box, NOTICE,
  CREDITS.md, README, `ATECH_CHANGES.txt`, AppStream metainfo).
- FreeCAD's copyright line is now upstream's own banner, verbatim:
  "(C) 2001-2026 FreeCAD contributors" (Jürgen Riegel credited as the
  person who started FreeCAD in 2001).
- "Atech Atelier is FreeCAD" is now "Atech Atelier is built on FreeCAD".
- "Unmodified" now says what is unmodified: FreeCAD's program files.
  Atech changes AppRun, the icon and the desktop/AppStream entries, and
  adds a branding file (CREDITS, NOTICE, README, metainfo, CHANGELOG).
- Added the FreeCAD Project Association: the FreeCAD logo is its registered
  trademark (Benelux); not endorsed by or affiliated with the FreeCAD
  project or the FPA. Also not endorsed by or affiliated with Anthropic.
- The About box comment no longer claims the LGPL forbids implying
  endorsement; that comes from the FPA's trademark and brand guidelines.
- AppStream: `project_license` is documented as covering Atech's own files
  only.
- Newly credited bundled components: CalculiX, FFmpeg, x264, x265 (all
  GPL-2.0-or-later), GNU Readline (GPL-3.0), IfcOpenShell
  (LGPL-3.0-or-later), Netgen inside SMESH, the components FreeCAD compiles
  in (KDL, libarea, Ondsel Solver, PyCXX, Zipios++), and the other copyleft
  packages (pythonocc-core, CGAL, MPFR/GMP/MPC, MySQL client, libgfortran).
- Newly credited Atech additions: the AppImage type-2 runtime (MIT) and the
  libraries it statically links (libfuse 3.15.0, squashfuse 0.5.2, musl,
  libzstd, zlib); the theme files derived from FreeCAD's (LGPL2+, modified
  by Atech); opencode (MIT, not bundled, optional engine).
- Corrected licence entries: Qt (LGPL-3.0 for the modules FreeCAD uses;
  some shipped modules are GPL-3.0 only), PySide6 (LGPL-3.0 OR GPL-2.0 OR
  GPL-3.0), SMESH (LGPL-2.1-or-later, linked 9.9.0.0), Gmsh (copyright and
  how FreeCAD runs it), Pivy (notice in its `__init__.py`), FreeType (FTL,
  dual-licensed with GPL-2.0-or-later) with the FTL credit sentence.
- Licence texts now shipped in `usr/share/doc/atech-atelier/third_party/`:
  Coin3D, SoQt, Point Cloud Library, Xerces-C (Apache-2.0), libzstd, and
  the GNU LGPL v3 and GPL v3.
- FreeCADMCP is described as what it is: an optional XML-RPC server, off by
  default, that Atech Atelier's own agent does not use.
- Lucide: copyright year added (2026); the icon path data is from older
  Lucide releases (e.g. tag 0.400.0), not from the commit the licence was
  fetched at; "chat" is Feather's. Feather: both copyright notices given
  (2013-present per Lucide's licence, 2013-2023 in Feather's own).
- The UI font fallback order is stated exactly.
- appimagetool: version 1.9.1 (git 8c8c91f) recorded; it was listed as
  "not determined".
- `SOURCE_OFFER.txt`: the package count (326, not "roughly 300"), the
  feedstock names (often not `<package>-feedstock`), no claim that
  anaconda.org links each build's source archive, an "AppImage runtime"
  section, and a full written-offer text used once a contact is set. Until
  then the file says plainly that it carries no written offer. When a
  contact was set, the old text also appended the contact address after
  the offer; fixed.
- `ATECH_CHANGES.txt` records the change date.
- `LICENSE-models.md`: copyright year (2026), the CC BY-NC 4.0 conditions
  (keep notices, link the licence, indicate changes) and a modification
  mark in the suggested attribution.
- The licences grant no right to use the Atech names or logos except to say
  where the software comes from.

## [0.1.0] - 2026-10-03 (preview; published 23:31 UTC)

The first public preview.

### What it is

- Atech Atelier is the official FreeCAD 1.1.3 Linux AppImage with FreeCAD's
  program files unmodified. Atech changes only AppRun, the icon and the
  desktop/AppStream entries, and adds the Atech workbench, branding and
  module library (every change is listed in `ATECH_CHANGES.txt` under
  `usr/share/doc/`).
- Linux x86_64 only, as a single AppImage.

### Added

- A chat panel: describe a part in plain language. The agent writes a
  FreeCAD script, runs it, measures the result and shows it in the 3D view.
  The model stays an ordinary FreeCAD model you can edit.
- Three agent engines, chosen in Agent Settings: Claude Code (the default,
  and the one this release is tested with), a local OpenCode server, or a
  provider API token.
- The Atech module library: the 14-port board and its plug-in modules, with
  their meshes bundled in the image. The Modules page and the
  Atech > New Project menu place them.
- A light and a dark theme, generated from one set of brand colour tokens.
- Credits for FreeCAD and every bundled open-source component, with the
  location of each licence text inside the image.

### Licences

- Atech's code: GNU LGPL v2.1 or later (`LICENSE`).
- Atech board and module models and `presets.yaml`: CC BY-NC 4.0
  (`LICENSE-models.md`).
- FreeCAD and its bundled libraries keep their own licences (`CREDITS.md`).

### Known limits

- Preview quality. Settings and file locations may change before 1.0.0.
- No automatic updates.
