# Changelog

All notable changes to Atech Atelier are listed here. Versions follow
[Semantic Versioning](https://semver.org). Before 1.0.0, any release may
change behaviour.

## [0.1.0] - unreleased (preview)

The first public preview.

### What it is

- Atech Atelier is the official FreeCAD 1.1.3 Linux AppImage, unmodified,
  with the Atech workbench, branding and module library added. No FreeCAD
  source file is patched or recompiled. The image lists every file Atech
  added, removed or changed, measured against the upstream image, in
  `ATECH_CHANGES.txt` under `usr/share/doc/`.
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
