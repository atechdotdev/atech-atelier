# Contributing to Atech Atelier

Atech Atelier is FreeCAD 1.1.3 with the Atech design-agent workbench built
in. It ships as one Linux x86_64 AppImage. This guide covers how the
repository is laid out, how to build and test it, and the rules that keep
the build honest.

## What lives where

| path | what it is |
|---|---|
| `addon/AcadAgent/` | the workbench: chat panel, agent engines, build/apply, shell. Ships inside the image |
| `addon/AcadAgent/tests/` | the addon's tests. Never shipped |
| `branding/` | the distribution: `build_appimage.sh`, the build gate `verify_tree.py`, `branding.xml`, desktop and metainfo files, third-party notices, the vendored FreeCAD MCP bridge (`vendor/freecad-mcp/`, MIT) |
| `brand/` | brand generators: `tokens.py` (colours) and `tools/` (icons, stylesheets, theme parameters). Their output in `brand/assets/` is generated. Do not edit it by hand |
| `projects/` | the Atech module library readers bundled with the addon |
| `models/` | the Atech board and module meshes and `presets.yaml`. Licensed CC BY-NC 4.0, see `models/LICENSE.md` |
| `cockpit/fixtures/crane/` | the generator for the reference model the build bundles |
| `docs/ATECH_ASSEMBLY.md` | how Atech modules seat on a board |
| `VERSION` | the release version, read by the build and the release workflow |

## Setting up

You need Linux x86_64, Python 3.11 or newer, and git. To build the image you
also need `inkscape`, `patch`, and the Python packages `numpy`, `Pillow`,
`scipy` and `PyYAML`. `appimagetool`, `desktop-file-validate` and
`appstreamcli` are optional: without them the build skips that step and
reports it as CANNOT DETERMINE.

The build downloads the pinned FreeCAD 1.1.3 AppImage (about 820 MB) and
refuses any file whose sha256 differs from `branding/upstream.env`. You can
pass a copy you already have with `-i FILE`.

```bash
./branding/build_appimage.sh --tree-only
dist/build/squashfs-root/AppRun          # run the tree you just built
```

The module models come from `models/` in this repository. To use another
copy of the library, pass `--artifacts DIR` or set `ATECH_ARTIFACTS`. DIR can
be the folder holding `models/` or the `models/` folder itself.

## Running the checks

Plain Python, no FreeCAD needed. This is what CI runs (`.github/workflows/ci.yml`):

```bash
cd addon/AcadAgent/tests
python3 -m unittest -v test_claude_cli test_engine test_build_apply \
    test_client_parse test_eval_harness test_ws_chat_cli test_build_ws
cd -
python3 -m unittest -v addon/AcadAgent/tests/test_style_tokens.py
python3 branding/tests/test_overlay_sheet.py
bash brand/build.sh --check              # brand generators, verify only
```

The Qt tests need `PySide6-Essentials==6.8.3` and run offscreen:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -v \
    -s addon/AcadAgent/tests -p 'test_shell_*.py'
```

Tests that need FreeCAD's own `freecadcmd` skip without it. To run them,
build the tree first (`--tree-only` is enough): they look for
`dist/build/squashfs-root/usr/bin/freecadcmd`, and some accept another path
in `ATECH_FREECADCMD`. Set `ATECH_REQUIRE_FREECADCMD=1` to make them fail instead of skip. A skip is
reported as a skip and never counts as a pass.

## Rules that matter

**Measure, do not assert.** A claim about the product, such as a size, a
count or a behaviour, comes from running something and reading the number.
A check must compare against something that cannot agree with it by
construction, such as upstream's own files, a validator or a rendered pixel.
It must not compare against another value written in the same change.

**Every check must be able to fail.** When you add a gate, show it failing
once: break the thing it guards, watch it fail, then restore it. Several
tests here have such a sabotage case. Keep them.

**`freecadcmd` exits 0 even when the script raised.** Never trust its exit
code. Scripts run under it print an explicit marker line (for example
`VERIFY_FAILURES=0`), and callers look for that line.

**Three verdicts.** PASS, FAIL or CANNOT DETERMINE. A missing tool or a
missing input is CANNOT DETERMINE or a skip, never a quiet pass.

**Upstream stays unmodified.** No FreeCAD source file is patched or
recompiled. The build adds files, replaces the desktop entry and extends
AppRun. It writes a measured list of every difference into the image
(`ATECH_CHANGES.txt` under `usr/share/doc/`). If your change alters the
image, that list will show it.

**Generated files are regenerated, not edited.** Change `brand/tokens.py` or
the generator in `brand/tools/`, then run `bash brand/build.sh`.

**No personal or machine-specific data.** Tracked files must not contain
absolute home-directory paths, usernames, e-mail addresses, tokens or local
tool paths. Use paths relative to the repository, or environment variables
with a documented default.

**File names must not differ only in letter case.** macOS and Windows
clones would lose one of them. `branding/tests/test_case_collisions.py`
checks this.

**Only use artwork you have the right to use.** No third-party trademarks,
logos or branded product replicas in examples, fixtures or screenshots.

## Changes and pull requests

- Keep each change to one concern. Say in the description what you measured
  and how (the command and its result).
- Add or extend a test where the code can be tested headless.
- Run the checks above before you open the pull request.
- The maintainers decide irreversible product choices, such as licences,
  releases and the update channel.

## Licence

By contributing you agree that your contribution is licensed under the same
terms as the file you change:

- Atech's code (everything outside `models/`, except the third-party files
  below): GNU LGPL v2.1 or later, see `LICENSE`.
- Module models and `presets.yaml` in `models/`: CC BY-NC 4.0, see
  `LICENSE-models.md`.
- Third-party files keep their own licences: the FreeCAD MCP bridge in
  `branding/vendor/freecad-mcp/` is MIT (its `LICENSE` file), and the other
  bundled components are listed with their licences in
  `branding/third_party/NOTICE.third_party` and `CREDITS.md`.

FreeCAD itself is LGPL-2.1-or-later. Atech Atelier is not endorsed by,
affiliated with, or a product of the FreeCAD project.
