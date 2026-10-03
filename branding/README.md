# Atech Atelier — branded FreeCAD distribution

Product name **Atech Atelier** (ADR-005, owner 2026-10-03; previously
"Atech Studio"). Licences, repository and version: ADR-006.

Upstream FreeCAD 1.1.3 (no FreeCAD source patched or recompiled), plus our
branding, our theme, the `AcadAgent` addon, the Atech module library and the
FreeCADMCP bridge, shipped as one application.

This implements ADR-003 §2 ("own the distribution") under ADR-004's two-surface
split: **VS Code authors, FreeCAD points.** This tree is the FreeCAD half.

## Build

```bash
./build_appimage.sh --tree-only      # build + verify, no repack (no appimagetool needed)
./build_appimage.sh                  # …and repack into dist/AtechAtelier-<version>-x86_64.AppImage
./build_appimage.sh -i /path/to/FreeCAD.AppImage -o /tmp/out.AppImage
./build_appimage.sh --help           # every option
```

Output goes to `dist/` (gitignored — the extracted tree is 3.1 GB); pass
`--build-dir DIR` to build elsewhere (**the build dir is wiped**, so never
point it at a tree someone else is using). Run the built tree directly with
`dist/build/squashfs-root/AppRun`.

### Build dependencies

| what | why |
|---|---|
| bash, coreutils, tar, `patch`, `sha256sum` | the build script |
| python3 with **numpy, Pillow, scipy** (PyYAML optional) | `brand/tools/` trace the logo and generate the theme |
| **inkscape** (CLI) | `brand/tools/trace.py` rasterises the traced SVG to check it against the source PNG |
| curl | only when no upstream AppImage is passed and none is cached |
| the Atech module library (`atech-artifacts` checkout) | bundled meshes; `--artifacts DIR` or `$ATECH_ARTIFACTS`, default `../../atech-artifacts` from the repo |
| `desktop-file-validate`, `appstreamcli` (optional) | validate the desktop entry and metainfo; reported as CANNOT DETERMINE when absent |
| `appimagetool` (optional) | repack, found via `$APPIMAGETOOL` or `PATH` and **never downloaded** by the build; without it the build stops at the verified tree with exit 3 |
| `zsyncmake` (optional) | lets appimagetool write the `.zsync` delta file next to the image |

Everything else comes from the repo:

| input | where | pinned how |
|---|---|---|
| upstream FreeCAD AppImage | `upstream.env` | URL + sha256 (checked against the GitHub release digest); any other file is refused |
| logo artwork | `brand/assets/source/` | vendored PNGs, provenance and sha256 in `SOURCE` |
| FreeCADMCP addon | `vendor/freecad-mcp/` | pristine copy at a pinned commit + `patches/` (see its README) |
| reference model (crane BREPs) | `cockpit/fixtures/crane/build_crane.py` | **regenerated** each build with the extracted `freecadcmd` (~50 s); `--crane-from DIR` copies prebuilt ones |
| third-party licence texts | `third_party/` | fetched at the commits named in `NOTICE.third_party` |

### The gate

The build **verifies itself** and exits non-zero if anything did not take:
`verify_tree.py` runs under the built tree's `freecadcmd` with `env -i` and an
**empty temporary HOME**, and asserts on what the running kernel and the
addon report rather than on the files we just copied. Rules:

- no `sys.path` entry outside the image;
- every path the addon resolves (module library, meshes, `ATECH_ASSEMBLY.md`,
  reference model) must lie **inside** the image; a dev fallback that
  resolves on the build host is a FAIL;
- missing module library, assembly doc or reference model = FAIL;
- missing `LICENSE`/`LICENSE-models.md`/`NOTICE` = FAIL (see below), and
  `LICENSE-models.md` must also sit next to the bundled models;
- the previous product name in a desktop entry, the metainfo, a
  branding.xml value or a file name the build controls = FAIL;
- after the gate ran, the tree is re-measured: anything it changed fails
  the build.

`tests/test_verify_sabotage.sh <squashfs-root>` removes each required piece
in turn and requires the gate to name it. Exit 3 with `CANNOT DETERMINE`
means the tree built but `appimagetool` was absent — never a soft pass.

### Version, update channel, signing (R39)

`VERSION` at the **repository root** is the only place the version is written
(`0.1.0`, the first public preview, ADR-006). `branding/VERSION` is retired.
`release_meta.py` stamps it into the output file name, `X-AppImage-Version`
in both desktop files, the metainfo `<release version= date=>` (date from
`$SOURCE_DATE_EPOCH`, else the built commit's date) and the `Version` line of
`ATECH_CHANGES.txt`; the gate fails unless all four agree. A repack also
writes `SHA256SUMS` next to the image (`sha256sum -c` format; the image and,
when written, its `.zsync`) and re-checks it.

| variable | effect |
|---|---|
| `APPIMAGETOOL` | path to appimagetool (else `PATH`). Absent: exit 3, CANNOT DETERMINE |
| `ATECH_UPDATE_INFO` | unset: `gh-releases-zsync\|atechdotdev\|atech-atelier\|latest\|AtechAtelier-*x86_64.AppImage.zsync` (the **proposed** public repo, ADR-006), embedded only when this appimagetool lists `-u`; set to another value to override; set empty for none |
| `ATECH_SIGN_KEY` | empty (default): unsigned, and the build prints `SKIPPED: unsigned image`. Set: `appimagetool --sign --sign-key <id>` |
| `ATECH_SCREENSHOT_URLS` | space-separated `https://…png\|jpg` for the AppStream `<screenshots>`; empty: a `SCREENSHOTS: PLACEHOLDER` comment and a WARN line |
| `ATECH_SOURCE_CONTACT` | written-offer contact in `SOURCE_OFFER.txt` |

Nothing here creates a repository, pushes or uploads a release. That is an
outward action for the owner.

### AppRun environment snapshot (R61)

Upstream's AppRun exports `QT_QPA_PLATFORM=xcb`, `PYTHONHOME`, a bundled
`SSL_CERT_FILE` and more, which a terminal or agent child would inherit. The
build inserts a block at the very top of AppRun (`apprun_env.py`, names
measured from AppRun's own `export` lines) that records the caller's values
before any of that runs: `ATECH_APPRUN_SET` lists the names, and
`ATECH_PRE_APPRUN_<NAME>` holds the caller's value for each one that was set.
`apprun_env.restore()` is the reference consumer: put each listed name back,
or remove it when there is no `ATECH_PRE_APPRUN_` twin. The addon's
`terminal.clean_env()` should apply the same rule.

### Licence (ADR-006)

Atech's code is **LGPL-2.1-or-later** (root `LICENSE`, the verbatim LGPL v2.1
text); the Atech module models and `presets.yaml` are **CC BY-NC 4.0** (root
`LICENSE-models.md`). The build installs `LICENSE`, `LICENSE-models.md`,
`NOTICE` and `CREDITS.md` into `usr/share/doc/atech-atelier/`, puts
`LICENSE-models.md` next to the models in `usr/Mod/AcadAgent/data/models/`,
checks the contents (LGPL v2.1 heading, "CC BY-NC 4.0"), and **fails when any
is absent**. The metainfo's `project_license` is
`LGPL-2.1-or-later AND CC-BY-NC-4.0`: both kinds ship, so a conjunction.
For local work,
`--dev-unlicensed --tree-only` builds and verifies a tree marked
**NOT RELEASABLE** and never repacks it.

### What the image says about itself

`usr/share/doc/atech-atelier/` in the built tree:

| file | content |
|---|---|
| `ATECH_CHANGES.txt` | upstream URL, sha256, FreeCAD commit, and the **measured** list of added / removed / modified files (`tree_changes.py` diffs the tree against a snapshot taken right after extraction) |
| `SOURCE_OFFER.txt` | where the source of FreeCAD and its ~300 bundled libraries is; the written-offer contact comes from `$ATECH_SOURCE_CONTACT` (not set yet — owner) |
| `third_party/` | FreeCADMCP (MIT, modified, with the applied patches), Lucide (ISC), Feather (MIT) |
| `README.md`, `CREDITS.md`, `LICENSE`, `LICENSE-models.md`, `NOTICE` | the root files |

Desktop integration uses one reverse-DNS id, `dev.atech.Atelier`, for the
desktop file (root and `usr/share/applications/`, from the template
`dev.atech.Atelier.desktop`), the AppStream metainfo (`usr/share/metainfo/`,
from `dev.atech.Atelier.metainfo.xml`), the icon, `.DirIcon` and
branding.xml's `DesktopFileName`. FreeCAD's own desktop entry and metainfo are
removed (its hicolor PNG icons and MIME package stay; nothing presents them).

### Profile migration (ADR-005)

Renaming `ExeName` moves the user-data and config folders. AppRun copies
`~/.local/share/Atech Studio` and `~/.config/Atech Studio` (XDG variables
honoured) to the `Atech Atelier` names **only when the new folder does not
exist**, never moving or editing the old ones, and rewrites old absolute
paths and the old theme name in the copy's `user.cfg`/`system.cfg`.
`ATECH_MIGRATE=0` turns it off. Source `apprun_migrate_block.sh`, tests
`tests/test_apprun_migrate.py`.

### MCP bridge

FreeCADMCP ships with the RPC server **off** (upstream default). Nothing is
written to any home directory. Whether the public build ships the bridge and
whether it autostarts is an owner decision (release PRD R10). `--mcp-guard`
applies the prepared token + Origin + Content-Type + Host guard
(`vendor/freecad-mcp/optional/`, tested by `tests/test_mcp_auth.py`).

## Brand assets are GENERATED — do not hand-edit

Every icon, logo, splash, stylesheet and theme file is generated from two
sources of truth:

    brand/tokens.py                   colour, ported from the atech.dev frontend
    brand/assets/source/atech_*_black.png  geometry, the real logo artwork
                                      (vendored from the frontend repo)

```bash
bash ../brand/build.sh            # regenerate everything
bash ../brand/build.sh --check    # verify without writing (CI)
bash ../brand/tools/test_brand_sabotage.sh   # prove the gates can fail
```

`build_appimage.sh` runs the generators itself before installing, so a stale
asset cannot ship.

This replaced a hand-drawn identity that was not Atech's: a blue-to-purple
gradient chevron "A" whose colours appear nowhere in the frontend. The real
mark is monochrome. See `docs/verification/2026-09-24_brand_port.md`.

### Light and dark

Both modes ship. `branding.xml` can name only one stylesheet and only as a
fallback (`StartupProcess.cpp:533` reads the user preference first), so both
sheets install to `share/Gui/Stylesheets/` and the mode is chosen by the
`MainWindow/StyleSheet` preference seeded in `atech_user_template.cfg`.
**Light is the default**, matching the website. Switch by setting that
preference to `AtechDark.qss` and `MainWindow/Theme` to `Atech Atelier Dark`.

`auto` (follow the OS) is NOT implemented — Qt does not follow
`prefers-color-scheme` for free.

## What is where

| file | role |
|---|---|
| `branding.xml` | the branding descriptor. Installed to `usr/bin/`, read by FreeCAD at startup |
| `assets/theme/Atech Atelier {Light,Dark}.yaml` | **the colours**, generated by `brand/tools/build_theme.py`, with token parity against upstream's own `FreeCAD.qss` |
| `assets/atech_user_template.cfg` | first-run defaults: theme, accent, workbench, no setup wizard |
| `assets/atech_{icon,logo,splash}.svg` | window icon · statusbar logo · splash |
| `build_appimage.sh` | assembles the distribution |
| `verify_tree.py` | the gate, run inside the built tree |
| `tree_changes.py` | snapshot / diff / bytecode prune of the tree |
| `upstream.env` | the pinned upstream AppImage |
| `vendor/freecad-mcp/` | pinned FreeCADMCP + patches |
| `third_party/` | third-party notice and licence texts |
| `dev.atech.Atelier.desktop`, `dev.atech.Atelier.metainfo.xml` | desktop entry and AppStream metainfo templates |
| `release_meta.py` | reads the root `VERSION` and stamps it, the release and the screenshots (R39) |
| `apprun_migrate_block.sh`, `apprun_agent_block.sh` | the two blocks inserted before AppRun's launch line |
| `apprun_env.py` | the pre-AppRun environment snapshot and its reference `restore()` (R61) |
| `tests/` | plain python3: `test_tree_changes.py`, `test_mcp_auth.py`, `test_release_meta.py`, `test_apprun_env.py`, `test_apprun_migrate.py`, `test_apprun_agent_block.py`, `test_theme_tokens.py` (needs a built tree or `tools/freecad-src`, else skips), `test_case_collisions.py`. Image python: `render_toolbutton_menu.py`. Built tree: `test_verify_sabotage.sh` |

### `brand/` holds two branding sets — only one is built (R45)

`brand/tokens.py`, `brand/tools/` and the `atech_*` assets are the live
generators for this build. `brand/branding.xml`, `brand/assets/AtechCAD.qss`,
`brand/assets/atech-cad*` and `brand/build/{install,verify}.sh` are the
retired **"Atech CAD"** set (old name, dead NOTICE and GitHub links).
`build_appimage.sh` installs only `branding/branding.xml`, refuses a
descriptor carrying the Atech CAD names, and checks the installed copy is
byte-identical; the gate fails on any Atech CAD asset in the image;
`brand/build/install.sh` refuses to run unless `ATECH_LEGACY_BRAND=1`.

Owner decision, not taken here:

- **archive** — move the retired files to `brand/legacy-atech-cad/` with a
  README saying they are not built. Keeps the history readable in-tree;
  costs nothing but a directory.
- **delete** — `git rm` them. Git history keeps them; the tree loses files
  that `docs/verification/2026-09-24_brand_port.md` still names (its palette
  table lists `brand/assets/AtechCAD.qss`).

Either way `brand/tokens.py`, `brand/tools/` and the `atech_*` assets stay.

Palette is taken verbatim from `docs/prd/assets/atech_studio.html` so the two
surfaces cannot drift.

## Three things to know before changing anything

**1. Theme is tokens, not a stylesheet.** FreeCAD 1.1 resolves a parametrized
stylesheet through `replaceVariablesInQss()`. To restyle, edit the YAML —
`PrimaryColor` drives most of the surface. A hand-written `.qss` fights the
token system and loses; one was written and deleted for this reason.

**2. User preference beats branding.** `setStyleSheet()` reads the user's
`MainWindow/StyleSheet` preference first and only falls back to the branding
value when it is empty (`StartupProcess.cpp:533`). This is why the first build
shipped light-themed: the first-run wizard wrote that preference. Defaults are
therefore seeded via `<UserParameterTemplate>` — which applies on **first run
only**.

> **Iterating on design?** Wipe the profile between runs or you are looking at a
> stale one and will conclude your edit did nothing:
> ```bash
> rm -rf ~/.config/"Atech Atelier" ~/.local/share/"Atech Atelier" ~/.cache/"Atech Atelier"
> ```

**3. `ExeName` is load-bearing twice.** It names the user-data directory
(`~/.local/share/<ExeName>/v1-1/`) **and** it is a display string — it fills the
Start page's "Welcome to %1". Consequences: an addon installed in the user's
*FreeCAD* `Mod` dir is **not** read by a branded build, so `AcadAgent` ships
bundled inside the image; and a lowercase slug greets users with
"Welcome to atech-atelier".

## Licensing

FreeCAD is LGPL-2.0-or-later ("LGPL2+") and **no FreeCAD source file is patched or
recompiled**. The build writes `usr/share/doc/atech-atelier/ATECH_CHANGES.txt`
into the image with the pinned upstream, a measured list of every file
added, removed or modified (AppRun is modified), preserved copyright, a
pointer to corresponding source, and an explicit non-endorsement statement.
The list is generated, so it cannot go stale.

## Evidence

`docs/verification/2026-09-24_atech_studio_branding.md` (written under the
previous name) — every claim here was
measured, including the two screenshots showing the three defects that a green
gate did not catch, and what fixed them. Re-run it when you change this tree.
