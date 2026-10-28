#!/usr/bin/env bash
#
# build_macos.sh — assemble "Atech Atelier.app" and its disk image from the
# official FreeCAD macOS release plus our branding and our addon. The macOS
# twin of build_appimage.sh: the same payload, the same gate (verify_tree.py),
# the same measured ATECH_CHANGES.txt.
#
# We compile no FreeCAD source. FreeCAD.app's layout already matches the
# AppImage's: AppHomePath is Contents/Resources/ (bin/, Mod/, share/), so
# every file goes where build_appimage.sh puts it under usr/. On top of that
# the build rewrites Contents/Info.plist (identity, icon, version), adds the
# Atech icon, and replaces the bundle's code signature (any added file breaks
# FreeCAD's seal). The exact list is MEASURED at the end
# (Contents/Resources/share/doc/atech-atelier/ATECH_CHANGES.txt).
#
# Usage (on a Mac):
#   ./build_macos.sh [--arch arm64|x86_64] [-i FreeCAD.dmg] [-o out.dmg]
#                    [--app-only] [--build-dir DIR] [--artifacts DIR]
#                    [--crane-from DIR] [--brand-from-repo] [--dev-unlicensed]
#
#   --arch A         arm64 (Apple silicon) or x86_64 (Intel). Default: this Mac's.
#   -i FILE          the upstream FreeCAD DMG. Default: downloaded from the
#                    pinned URL in upstream.env into
#                    ${XDG_CACHE_HOME:-~/.cache}/atech-atelier-build/. Either
#                    way its sha256 must match upstream.env, and the
#                    FreeCAD.app inside must carry the FreeCAD Project
#                    Association's valid Developer ID signature.
#   -o FILE          the disk image. Default:
#                    dist/AtechAtelier-<version>-macOS-<arch>.dmg
#   --app-only       build, verify and sign the .app; no disk image.
#   --build-dir DIR  where to assemble (default dist/build-macos-<arch>). WIPED.
#   --artifacts DIR  the Atech module library (as build_appimage.sh).
#   --crane-from DIR copy the reference-model BREPs instead of regenerating.
#   --brand-from-repo  use the committed brand/assets SVGs without re-running
#                    the logo trace gate (brand/tools/build_brand.py), which
#                    needs Inkscape. Without this flag and without Inkscape
#                    the build fails. The stylesheets, theme and template are
#                    regenerated either way.
#   --dev-unlicensed as build_appimage.sh: NOT RELEASABLE, never packed.
#
# Signing, notarization (environment):
#   ATECH_MAC_SIGN_IDENTITY  a "Developer ID Application: ..." identity in the
#                    keychain. Empty (default): ad-hoc signature. An ad-hoc app
#                    runs on the Mac that built it and when installed by
#                    install.sh (which verifies SHA256SUMS first), but a
#                    browser download of it is blocked by Gatekeeper.
#   ATECH_NOTARY_PROFILE     a `xcrun notarytool store-credentials` profile.
#                    Set (with a Developer ID identity): the disk image is
#                    notarized by Apple and the ticket stapled to it.
#   ATECH_SOURCE_CONTACT     as build_appimage.sh.
#
# Outputs next to the disk image: SHA256SUMS (shasum -a 256 format, which
# `sha256sum -c` and `shasum -a 256 -c` both read).
#
# Requires: macOS, bash, python3, hdiutil, ditto, codesign, iconutil, shasum,
# curl (only to download), patch, tar; inkscape unless --brand-from-repo.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"

# shellcheck source=upstream.env
. "$HERE/upstream.env"

[[ "$(uname -s)" == Darwin ]] || { echo "FAIL: build_macos.sh runs on macOS (use build_appimage.sh on Linux)" >&2; exit 2; }

ARCH="$(uname -m)"
UPSTREAM=""
OUT=""
BUILD=""
ARTIFACTS="${ATECH_ARTIFACTS:-$REPO}"
CRANE_FROM=""
APP_ONLY=0
BRAND_FROM_REPO=0
DEV_UNLICENSED=0
APP_ID="dev.atech.Atelier"
PRODUCT="Atech Atelier"
DOC_NAME="atech-atelier"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch)            ARCH="$2"; shift 2 ;;
    -i|--input)        UPSTREAM="$2"; shift 2 ;;
    -o|--output)       OUT="$2"; shift 2 ;;
    --build-dir)       BUILD="$2"; shift 2 ;;
    --artifacts)       ARTIFACTS="$2"; shift 2 ;;
    --crane-from)      CRANE_FROM="$2"; shift 2 ;;
    --app-only)        APP_ONLY=1; shift ;;
    --brand-from-repo) BRAND_FROM_REPO=1; shift ;;
    --dev-unlicensed)  DEV_UNLICENSED=1; shift ;;
    -h|--help)         sed -n '2,57p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

say()  { printf '  %-34s %s\n' "$1" "$2"; }
fail() { echo "FAIL: $*" >&2; exit 1; }
sha256() { shasum -a 256 "$1" | cut -d' ' -f1; }

case "$ARCH" in
  arm64)  UPSTREAM_URL="$MACOS_ARM64_URL";  UPSTREAM_SHA256="$MACOS_ARM64_SHA256" ;;
  x86_64) UPSTREAM_URL="$MACOS_X86_64_URL"; UPSTREAM_SHA256="$MACOS_X86_64_SHA256" ;;
  *) fail "--arch must be arm64 or x86_64, got $ARCH" ;;
esac
for t in hdiutil ditto codesign iconutil shasum python3 patch tar; do
  command -v "$t" >/dev/null 2>&1 || fail "$t not found"
done

VERSION="$(python3 "$HERE/release_meta.py" version)" \
  || fail "$REPO/VERSION is not a valid version"
OUT="${OUT:-$REPO/dist/$(python3 "$HERE/release_meta.py" dmgname "$ARCH")}"
BUILD="${BUILD:-$REPO/dist/build-macos-$ARCH}"
APP="$BUILD/$PRODUCT.app"
CONTENTS="$APP/Contents"
RES="$CONTENTS/Resources"            # FreeCAD's AppHomePath on macOS
SIGN_ID="${ATECH_MAC_SIGN_IDENTITY:-}"

echo "$PRODUCT $VERSION — macOS $ARCH build"

# ------------------------------------------------------ 0. the pinned upstream
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/atech-atelier-build"
mkdir -p "$CACHE"
if [[ -z "$UPSTREAM" ]]; then
  UPSTREAM="$CACHE/$(basename "$UPSTREAM_URL")"
  if [[ ! -f "$UPSTREAM" ]]; then
    say "downloading" "$UPSTREAM_URL"
    curl -fL --retry 3 -o "$UPSTREAM.part" "$UPSTREAM_URL" \
      || fail "could not download $UPSTREAM_URL"
    mv "$UPSTREAM.part" "$UPSTREAM"
  fi
fi
[[ -f "$UPSTREAM" ]] || fail "upstream DMG not found: $UPSTREAM"
GOT_SHA="$(sha256 "$UPSTREAM")"
[[ "$GOT_SHA" == "$UPSTREAM_SHA256" ]] || fail "upstream sha256 mismatch:
  file   $UPSTREAM
  got    $GOT_SHA
  pinned $UPSTREAM_SHA256 (branding/upstream.env)"
say "upstream" "$UPSTREAM"
say "upstream sha256" "$GOT_SHA (matches pin)"

# Copying FreeCAD.app out of the compressed image takes minutes (MEASURED
# 7.5 min, arm64, 2026-10-17), so the extracted app is cached by the DMG's
# sha256 and cloned (APFS copy-on-write) into each build.
PRISTINE="$CACHE/FreeCAD-$ARCH-${GOT_SHA:0:16}.app"
if [[ ! -d "$PRISTINE" ]]; then
  MNT="$(mktemp -d "${TMPDIR:-/tmp}/atech-fc-dmg.XXXXXX")"
  hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$MNT" "$UPSTREAM" >/dev/null \
    || fail "could not mount $UPSTREAM"
  rm -rf "$PRISTINE.part"
  if ! ditto "$MNT/FreeCAD.app" "$PRISTINE.part"; then
    hdiutil detach -quiet "$MNT" || true
    fail "could not copy FreeCAD.app out of the image"
  fi
  hdiutil detach -quiet "$MNT" || hdiutil detach -force -quiet "$MNT" || true
  rmdir "$MNT" 2>/dev/null || true
  mv "$PRISTINE.part" "$PRISTINE"
fi
# What we build on must be exactly what the FreeCAD Project Association
# signed: a valid seal (no file added, removed or changed) and their team.
codesign --verify --deep --strict "$PRISTINE" 2>/dev/null \
  || fail "upstream FreeCAD.app does not verify (codesign --verify --deep --strict); delete $PRISTINE and retry"
UP_TEAM="$(codesign -dv "$PRISTINE" 2>&1 | sed -n 's/^TeamIdentifier=//p')"
[[ "$UP_TEAM" == "$MACOS_UPSTREAM_TEAM_ID" ]] \
  || fail "upstream FreeCAD.app is signed by team '$UP_TEAM', not $MACOS_UPSTREAM_TEAM_ID"
say "upstream signature" "valid, team $UP_TEAM (FreeCAD Project Association)"

# Inputs that must exist before we spend time copying (as build_appimage.sh).
if [[ ! -f "$ARTIFACTS/models/presets.yaml" && -f "$ARTIFACTS/presets.yaml" ]]; then
  ARTIFACTS="$(cd "$ARTIFACTS/.." && pwd)"
fi
PRESETS="$ARTIFACTS/models/presets.yaml"
BOARD_GLB="$ARTIFACTS/models/glb/frame-2.glb"
ASSEMBLY_MD="$REPO/docs/ATECH_ASSEMBLY.md"
for f in "$PRESETS" "$BOARD_GLB" "$ASSEMBLY_MD" \
         "$REPO/projects/atech_ports.py" "$REPO/projects/atech_modules.py"; do
  [[ -f "$f" ]] || fail "required input missing: $f"
done
LICENSE_FILES=(LICENSE LICENSE.GPL-3.0 LICENSE-ATTRIBUTION.md LICENSE-models.md NOTICE)
if [[ "$DEV_UNLICENSED" != 1 ]]; then
  for f in "${LICENSE_FILES[@]}"; do
    [[ -f "$REPO/$f" ]] || fail "root $f is missing. For a local development build pass --dev-unlicensed."
  done
  grep -q 'GNU LESSER GENERAL PUBLIC LICENSE' "$REPO/LICENSE" \
    && grep -q 'Version 3, 29 June 2007' "$REPO/LICENSE" \
    || fail "root LICENSE is not the LGPL v3 text (R722)"
  grep -q 'section 7(b)' "$REPO/LICENSE-ATTRIBUTION.md" \
    || fail "root LICENSE-ATTRIBUTION.md lacks the credit term (R722)"
  grep -q 'CC BY-NC 4.0' "$REPO/LICENSE-models.md" \
    || fail "root LICENSE-models.md does not name CC BY-NC 4.0 (ADR-006)"
fi
BRANDING_XML="$HERE/branding.xml"
if grep -q -e 'Atech CAD' -e 'atech-cad' -e 'AtechCAD' "$BRANDING_XML"; then
  fail "$BRANDING_XML carries the stale Atech CAD branding set (brand/, R45)"
fi

# ------------------------------------------------------------ 1. the bundle
rm -rf "$BUILD"; mkdir -p "$BUILD"
# App Management (macOS 13+) refuses writes into a protected app bundle with
# "Operation not permitted". MEASURED on macOS 26.6: once macOS has
# registered the cached FreeCAD.app, its ROOT folder carries com.apple.macl,
# and a copy of the whole bundle (clone, ditto or rename) carries it too, so
# every write into the copy fails (2026-10-20). The marker sits on the root
# folder only, so the build makes a fresh root and clones Contents/ into it:
# the copy verifies, keeps FreeCAD's own signature attributes (e.g. on
# Contents/packages.txt) and is writable. Done under a name without .app,
# renamed last (2026-10-17: a copy straight to a new *.app path failed too).
rm -rf "$BUILD/bundle.tmp"
mkdir -p "$BUILD/bundle.tmp"
cp -Rc "$PRISTINE/Contents" "$BUILD/bundle.tmp/Contents" 2>/dev/null \
  || { rm -rf "$BUILD/bundle.tmp/Contents"; ditto "$PRISTINE/Contents" "$BUILD/bundle.tmp/Contents"; } \
  || fail "could not copy the upstream bundle"
mv "$BUILD/bundle.tmp" "$APP"
[[ -x "$RES/bin/freecadcmd" ]] || fail "no Contents/Resources/bin/freecadcmd in the bundle"
# MEASURED 2026-10-20: RUNNING a program from the copied bundle (freecadcmd
# --version) makes macOS put com.apple.macl on it, and from then on every
# write into it fails. So nothing runs from the bundle being built until it
# is signed (step 6): the build's own FreeCAD runs (version, reference
# model, icon, bytecode) use RUNNER, a second, throwaway copy that is never
# written to; only read-only checks run from the bundle, after signing.
RUNNER="$BUILD/FreeCAD-runner.app"
mkdir -p "$BUILD/runner.tmp"
cp -Rc "$PRISTINE/Contents" "$BUILD/runner.tmp/Contents" 2>/dev/null \
  || ditto "$PRISTINE/Contents" "$BUILD/runner.tmp/Contents" || fail "could not copy the runner"
mv "$BUILD/runner.tmp" "$RUNNER"
RUN="$RUNNER/Contents/Resources/bin"
say "bundle" "$APP ($(du -sh "$APP" | cut -f1))"
python3 "$HERE/tree_changes.py" snapshot "$CONTENTS" "$BUILD/upstream_manifest.json" 2>/dev/null \
  || fail "could not snapshot the upstream bundle"
say "upstream snapshot" "$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$BUILD/upstream_manifest.json") files"

# An empty HOME AND an empty FreeCAD user folder for every freecadcmd we run:
# FreeCAD on macOS takes its user folders from the account, not from $HOME
# (MEASURED), so FREECAD_USER_HOME keeps the builder's own
# ~/Library/Application Support and ~/Library/Preferences untouched.
SCRATCH_HOME="$(mktemp -d "${TMPDIR:-/tmp}/atech-build-home.XXXXXX")"
SCRATCH_HOME="$(cd "$SCRATCH_HOME" && pwd -P)"
trap 'rm -rf "$SCRATCH_HOME"' EXIT
fc_clean() {
  env -i HOME="$SCRATCH_HOME" FREECAD_USER_HOME="$SCRATCH_HOME" \
         PATH=/usr/bin:/bin LANG=en_US.UTF-8 PYTHONDONTWRITEBYTECODE=1 "$@"
}
# Bytecode the build itself leaves behind is removed: every .pyc absent from
# KEEP_MANIFEST (the upstream snapshot, then also the .pyc step 3d compiles).
KEEP_MANIFEST="$BUILD/upstream_manifest.json"
prune_pyc() {
  python3 "$HERE/tree_changes.py" prune-bytecode "$CONTENTS" "$KEEP_MANIFEST" >/dev/null \
    || fail "could not prune build-time bytecode"
}
UPSTREAM_VER="$(cd "$SCRATCH_HOME" && fc_clean "$RUN/freecadcmd" --version 2>/dev/null | head -1 || true)"
prune_pyc
say "upstream version" "${UPSTREAM_VER:-unknown}"

# ------------------------------------------------- 2. branding + assets
if command -v inkscape >/dev/null 2>&1; then
  ( cd "$REPO" && python3 brand/tools/build_brand.py ) || fail "brand asset generation failed"
elif [[ "$BRAND_FROM_REPO" == 1 ]]; then
  for k in icon logo splash; do for m in light dark; do
    [[ -s "$REPO/brand/assets/atech_$k-$m.svg" ]] || fail "brand/assets/atech_$k-$m.svg missing"
  done; done
  say "brand marks" "committed brand/assets SVGs (--brand-from-repo: trace gate NOT run)"
else
  fail "inkscape not found: the logo trace gate (brand/tools/build_brand.py) needs it.
  Install it (brew install --cask inkscape) or pass --brand-from-repo."
fi
( cd "$REPO" && python3 brand/tools/build_qss.py \
               && python3 brand/tools/build_theme.py \
                    --upstream "$RES/share/Gui/Stylesheets/parameters" \
               && python3 brand/tools/build_template.py ) \
  || fail "brand asset generation failed"

BA="$REPO/brand/assets"
install -m 0644 "$BRANDING_XML" "$RES/bin/branding.xml"
cmp -s "$BRANDING_XML" "$RES/bin/branding.xml" || fail "installed bin/branding.xml is not branding/branding.xml"
install -m 0644 "$BA/atech_icon-light.svg"    "$RES/bin/atech_icon.svg"
install -m 0644 "$BA/atech_logo-light.svg"    "$RES/bin/atech_logo.svg"
install -m 0644 "$BA/atech_splash-light.svg"  "$RES/bin/atech_splash.svg"
install -m 0644 "$BA/atech_icon-dark.svg"     "$RES/bin/atech_icon-dark.svg"
install -m 0644 "$BA/atech_logo-dark.svg"     "$RES/bin/atech_logo-dark.svg"
install -m 0644 "$BA/atech_splash-dark.svg"   "$RES/bin/atech_splash-dark.svg"
install -m 0644 "$HERE/assets/atech_user_template.built.cfg" "$RES/bin/atech_user_template.cfg"
say "branding.xml + assets" "installed to Resources/bin/ (light + dark)"
QSSDIR="$RES/share/Gui/Stylesheets"
[[ -d "$QSSDIR/overlay" && -d "$QSSDIR/parameters" ]] || fail "upstream stylesheet dirs missing under $QSSDIR"
install -m 0644 "$BA/AtechLight.qss" "$QSSDIR/AtechLight.qss"
install -m 0644 "$BA/AtechDark.qss"  "$QSSDIR/AtechDark.qss"
install -m 0644 "$BA/Atech Overlay.qss" "$QSSDIR/overlay/Atech Overlay.qss"
install -m 0644 "$HERE/assets/theme/$PRODUCT Light.yaml" "$QSSDIR/parameters/$PRODUCT Light.yaml"
install -m 0644 "$HERE/assets/theme/$PRODUCT Dark.yaml"  "$QSSDIR/parameters/$PRODUCT Dark.yaml"
say "stylesheets + theme" "AtechLight/Dark.qss, Atech Overlay.qss, $PRODUCT Light/Dark"

# --------------------------------------------------------------- 3. the addon
AA="$RES/Mod/AcadAgent"
rm -rf "$AA"
tar -C "$REPO/addon" --exclude=tests --exclude=__pycache__ \
    --exclude='.*_cache' --exclude='*.pyc' --exclude='.DS_Store' -cf - AcadAgent \
  | tar -C "$RES/Mod" -xf -
say "addon bundled" "Mod/AcadAgent ($(find "$AA" -name '*.py' | wc -l | tr -d ' ') py files, no tests/caches)"

mkdir -p "$AA/projects" "$AA/data/models/stl" "$AA/data/models/glb" "$AA/docs"
install -m 0644 "$REPO/projects/atech_ports.py" "$REPO/projects/atech_modules.py" \
  "$REPO/projects/user_parts.py" "$AA/projects/"
install -m 0644 "$PRESETS" "$AA/data/models/presets.yaml"
if [[ -f "$REPO/LICENSE-models.md" ]]; then
  install -m 0644 "$REPO/LICENSE-models.md" "$AA/data/models/LICENSE-models.md"
elif [[ "$DEV_UNLICENSED" != 1 ]]; then
  fail "root LICENSE-models.md missing"
fi
install -m 0644 "$BOARD_GLB" "$AA/data/models/glb/frame-2.glb"
# The board and module GLBs the 3D view draws them from (the studio.atech.dev
# look, acadagent/board_look.py; display only, the STLs still measure).
n_glb=0
for g in "$ARTIFACTS"/models/glb/*.glb; do
  install -m 0644 "$g" "$AA/data/models/glb/$(basename "$g")"
  n_glb=$((n_glb + 1))
done
[[ -f "$ARTIFACTS/models/glb/SOURCE.md" ]] \
  && install -m 0644 "$ARTIFACTS/models/glb/SOURCE.md" "$AA/data/models/glb/SOURCE.md"
install -m 0644 "$ASSEMBLY_MD" "$AA/docs/ATECH_ASSEMBLY.md"
n_stl=0
while IFS= read -r f; do
  [[ -n "$f" ]] || continue
  src="$ARTIFACTS/models/stl/$f"
  [[ -f "$src" ]] || fail "presets.yaml names $f but $src does not exist"
  install -m 0644 "$src" "$AA/data/models/stl/$f"
  n_stl=$((n_stl + 1))
done < <(sed -n 's/^[[:space:]]*file:[[:space:]]*\([^[:space:]#]*\).*/\1/p' "$PRESETS" | sort -u)
[[ "$n_stl" -gt 0 ]] || fail "presets.yaml names no meshes ($PRESETS)"
ART_REV="$(git -C "$ARTIFACTS" rev-parse HEAD 2>/dev/null || echo "not a git checkout")"
say "module library" "$n_stl meshes + $n_glb GLBs, $(du -sh "$AA/data" | cut -f1)"

CRANE_DST="$AA/fixtures/crane/build"
mkdir -p "$CRANE_DST"
if [[ -n "$CRANE_FROM" ]]; then
  compgen -G "$CRANE_FROM/*.brep" >/dev/null || fail "no .brep in --crane-from $CRANE_FROM"
  cp "$CRANE_FROM"/*.brep "$CRANE_DST/"
  say "reference model" "copied from $CRANE_FROM"
else
  CRANE_OUT="$BUILD/crane"
  mkdir -p "$CRANE_OUT"
  CRANE_LOG="$(cd "$SCRATCH_HOME" && fc_clean CRANE_OUT="$CRANE_OUT" "$RUN/freecadcmd" \
                 "$REPO/cockpit/fixtures/crane/build_crane.py" 2>&1 || true)"
  prune_pyc
  CRANE_RES="$(grep '^FCRESULT ' <<<"$CRANE_LOG" | tail -1 || true)"
  [[ -n "$CRANE_RES" ]] || { tail -20 <<<"$CRANE_LOG" >&2; fail "crane build printed no FCRESULT"; }
  grep -q '"all_valid": true' <<<"$CRANE_RES" || fail "crane build has invalid parts: $CRANE_RES"
  compgen -G "$CRANE_OUT/*.brep" >/dev/null || fail "crane build wrote no .brep"
  cp "$CRANE_OUT"/*.brep "$CRANE_DST/"
  say "reference model" "regenerated: ${CRANE_RES#FCRESULT }"
fi

# R450: the default projects the app comes with. make_default_projects.py
# builds each showcase example with the production build (the BUNDLED addon
# and module library, run by RUNNER's freecadcmd like the crane above) into
# Mod/AcadAgent/default_projects/ + manifest.json; default_projects.py
# copies them into the user's projects folder on the first run.
DP_DST="$AA/default_projects"
rm -rf "$DP_DST"; mkdir -p "$DP_DST"
DP_LOG="$(cd "$SCRATCH_HOME" && fc_clean "$RUN/freecadcmd" "$HERE/make_default_projects.py" \
            --pass "$AA/acadagent/agent_kit/examples" "$DP_DST" 2>&1 || true)"
prune_pyc
DP_RES="$(grep -a -o 'DEFAULT_PROJECTS=[0-9]*/[0-9]*' <<<"$DP_LOG" | tail -1 || true)"
[[ -n "$DP_RES" ]] || { tail -20 <<<"$DP_LOG" >&2; fail "default projects: no DEFAULT_PROJECTS line"; }
grep -a -o '\[defaults\] SKIP.*' <<<"$DP_LOG" >&2 || true
DP_OK="${DP_RES#DEFAULT_PROJECTS=}"; DP_OK="${DP_OK%%/*}"
[[ "$DP_OK" -ge 6 ]] || fail "default projects: only ${DP_RES#DEFAULT_PROJECTS=} built (6 needed)"
say "default projects" "${DP_RES#DEFAULT_PROJECTS=} built, $(du -sh "$DP_DST" | cut -f1)"

MCP_V="$HERE/vendor/freecad-mcp"
MCP_STAGE="$BUILD/mcp-stage"
rm -rf "$MCP_STAGE"; mkdir -p "$MCP_STAGE"
cp -r "$MCP_V/addon" "$MCP_STAGE/"
MCP_SERIES=("$MCP_V"/patches/*.patch)
for p in "${MCP_SERIES[@]}"; do
  patch -p1 -s -d "$MCP_STAGE" < "$p" || fail "FreeCADMCP patch does not apply: $(basename "$p")"
done
find "$MCP_STAGE" -name '*.orig' -delete
rm -rf "$RES/Mod/FreeCADMCP"
tar -C "$MCP_STAGE/addon" --exclude=__pycache__ --exclude='*.pyc' -cf - FreeCADMCP | tar -C "$RES/Mod" -xf -
install -m 0644 "$MCP_V/LICENSE" "$RES/Mod/FreeCADMCP/LICENSE"
MCP_COMMIT="$(sed -n 's/^commit=//p' "$MCP_V/UPSTREAM")"
say "mcp addon bundled" "Mod/FreeCADMCP @ ${MCP_COMMIT:0:12} + ${#MCP_SERIES[@]} patch(es), RPC off by default"

# --------------------------------------------- 3d. no bytecode in the bundle
# FreeCAD ships .pyc for the modules it imports itself, not for the rest of
# the standard library, and its addons load in directory order, so the first
# import of e.g. ast or threading writes __pycache__ INTO the app. That
# breaks the code-signature seal (MEASURED 2026-10-17: 20 .pyc written by one
# freecadcmd run of the addon). A .pth line runs when Python's site module
# starts, before any FreeCAD code: from then on nothing is written. The only
# module imported earlier that upstream does not precompile is the
# encodings package (MEASURED: encodings/ascii), so it is compiled here, as
# unchecked-hash .pyc that stay valid whatever the files' timestamps.
PY_LIB="$(cd "$RES/lib" && ls -d python3.* | head -1)"
SITE="$RES/lib/$PY_LIB/site-packages"
[[ -d "$SITE" ]] || fail "no site-packages in the bundle ($SITE)"
printf '%s\n' \
  "# Atech Atelier (branding/build_macos.sh): never write bytecode into the signed app bundle." \
  "import sys; sys.dont_write_bytecode = True" > "$SITE/atech-no-bytecode.pth"
prune_pyc
( cd "$SCRATCH_HOME" && fc_clean "$RUN/python" -I -m compileall -q \
    --invalidation-mode unchecked-hash "$RES/lib/$PY_LIB/encodings" >/dev/null ) \
  || fail "could not precompile the encodings package"
python3 "$HERE/tree_changes.py" snapshot "$CONTENTS" "$BUILD/keep_manifest.json" 2>/dev/null \
  || fail "could not snapshot the bundle"
KEEP_MANIFEST="$BUILD/keep_manifest.json"
say "bytecode" "site-packages/atech-no-bytecode.pth; encodings precompiled"

# ------------------------------------------------ 4. bundle identity (macOS)
# The icon is rendered by the bundle's own Python/PySide6 (no Inkscape).
ICNS_NAME="atech.icns"
( cd "$SCRATCH_HOME" && fc_clean QT_QPA_PLATFORM=offscreen "$RUN/python" -I \
    "$HERE/macos_bundle.py" icns "$BA/atech_icon-light.svg" "$RES/$ICNS_NAME" ) \
  || fail "could not render $ICNS_NAME"
prune_pyc
python3 "$HERE/macos_bundle.py" plist "$CONTENTS/Info.plist" "$VERSION" "$ICNS_NAME" \
  || fail "could not stamp Info.plist"
plutil -lint "$CONTENTS/Info.plist" >/dev/null || fail "Info.plist does not lint"
say "Info.plist" "$APP_ID, $PRODUCT $VERSION, icon $ICNS_NAME, .FCStd at rank Alternate"

# ------------------------------------------- 5. notices, licences, README
DOC="$RES/share/doc/$DOC_NAME"
mkdir -p "$DOC/third_party/FreeCADMCP-patches"
install -m 0644 "$REPO/README.md" "$DOC/README.md"
[[ -f "$REPO/CREDITS.md" ]] || fail "root CREDITS.md missing"
install -m 0644 "$REPO/CREDITS.md" "$DOC/CREDITS.md"
grep -q '^## FreeCAD' "$DOC/CREDITS.md" || fail "CREDITS.md has no FreeCAD section"
for f in "${LICENSE_FILES[@]}"; do
  if [[ -f "$REPO/$f" ]]; then install -m 0644 "$REPO/$f" "$DOC/$f"
  elif [[ "$DEV_UNLICENSED" != 1 ]]; then fail "root $f missing"; fi
done
sed -e "s|@FREECADMCP_COMMIT@|$MCP_COMMIT|" -e "s|@DOC_NAME@|$DOC_NAME|g" \
    "$HERE/third_party/NOTICE.third_party" > "$DOC/third_party/NOTICE.third_party"
install -m 0644 "$MCP_V/LICENSE" "$DOC/third_party/LICENSE.FreeCADMCP"
install -m 0644 "$HERE/third_party/LICENSE.Lucide" "$HERE/third_party/LICENSE.Feather" "$DOC/third_party/"
for p in "${MCP_SERIES[@]}"; do install -m 0644 "$p" "$DOC/third_party/FreeCADMCP-patches/"; done
# The licence texts the bundled libraries need and the upstream bundle lacks
# (as build_appimage.sh, minus the AppImage runtime's, which is not here).
for f in LICENSE.Coin3D LICENSE.SoQt LICENSE.PCL LICENSE.Xerces-C LICENSE.zstd \
         LICENSE.LGPL-3.0 LICENSE.GPL-3.0 LICENSE.FreeType-FTL; do
  [[ -s "$HERE/third_party/$f" ]] || fail "branding/third_party/$f missing"
  install -m 0644 "$HERE/third_party/$f" "$DOC/third_party/$f"
done
say "credits, licences, notices" "share/doc/$DOC_NAME/"

if [[ -n "${ATECH_SOURCE_CONTACT:-}" ]]; then
  WRITTEN_OFFER="For at least three years from the date of this release, Atech will give anyone who asks, at $ATECH_SOURCE_CONTACT, the complete corresponding source code of every GPL- or LGPL-licensed component in this application (including FreeCAD $FREECAD_TAG, commit $FREECAD_COMMIT), on a medium customarily used for software interchange, for no more than the cost of physically performing the distribution."
else
  WRITTEN_OFFER="None. Instead of a written offer, the corresponding source is distributed with this release (see \"Source distributed with this release\" above)."
fi
cat > "$DOC/SOURCE_OFFER.txt" <<OFFER
$PRODUCT for macOS — where to get the source code
==================================================

This application contains FreeCAD and the packages it bundles
(Contents/packages.txt lists them, with versions, build strings and
channels), many under the LGPL or GPL. FreeCAD's own list of its libraries
and licences is in Contents/Resources/share/doc/FreeCAD/, and CREDITS.md
(Contents/Resources/share/doc/$DOC_NAME/CREDITS.md) lists the main ones.

Source distributed with this release
  The complete corresponding source of the copyleft components is published
  on the release page this disk image is downloaded from:
    https://github.com/atechdotdev/atech-atelier/releases/tag/v$VERSION
  including FreeCAD's own source archive (freecad_source_$FREECAD_TAG.tar.gz).
  Atech's own source is the release's "Source code" archive and the
  repository https://github.com/atechdotdev/atech-atelier at tag v$VERSION.

FreeCAD
  The FreeCAD part of this application is the official macOS release, with
  FreeCAD's program files unmodified:
    $UPSTREAM_URL
    sha256 $UPSTREAM_SHA256
  built from FreeCAD tag $FREECAD_TAG, commit
    https://github.com/FreeCAD/FreeCAD/tree/$FREECAD_COMMIT

Bundled libraries
  Contents/packages.txt names every bundled package (conda-forge). The recipe
  of each, including its upstream source URL and sha256, is in the
  conda-forge feedstock that built it.

Atech's additions
  Listed, measured against the upstream bundle, in
  Contents/Resources/share/doc/$DOC_NAME/ATECH_CHANGES.txt. Atech's code is
  LGPL-3.0-or-later with a credit term (LICENSE, LICENSE-ATTRIBUTION.md);
  the Atech module models and presets.yaml are
  CC BY-NC 4.0 (LICENSE-models.md).

Written offer
  $WRITTEN_OFFER
OFFER

# ATECH_CHANGES is generated from a diff against the pristine snapshot. It
# sits inside the signed bundle, so it is written BEFORE signing; signing
# then changes exactly the two files named below, which step 8 asserts.
if [[ -n "$SIGN_ID" ]]; then SIGNED_BY="Developer ID: $SIGN_ID"; else SIGNED_BY="ad-hoc (no Developer ID)"; fi
CHANGES="$DOC/ATECH_CHANGES.txt"
{
  cat <<NOTICE
$PRODUCT — changes relative to upstream FreeCAD (macOS)
$(printf '%*s' "$(( ${#PRODUCT} + 46 ))" '' | tr ' ' '=')

Version          $VERSION
Architecture     $ARCH

Upstream image   $UPSTREAM_URL
  sha256         $UPSTREAM_SHA256
  FreeCAD        tag $FREECAD_TAG, commit $FREECAD_COMMIT
  version string ${UPSTREAM_VER:-unknown}
  signed by      Developer ID Application: The FreeCAD project association ($MACOS_UPSTREAM_TEAM_ID), notarized
Built by         branding/build_macos.sh from the $PRODUCT sources
                 (commit $(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)$(git -C "$REPO" diff --quiet HEAD 2>/dev/null || echo ", with uncommitted changes"))
Module library   $(basename "$ARTIFACTS") @ $ART_REV
FreeCADMCP       $MCP_COMMIT + ${#MCP_SERIES[@]} Atech patch(es)
Signed           $SIGNED_BY

FreeCAD: (C) 2001-2026 FreeCAD contributors (started by Jürgen Riegel in
2001). FreeCAD is free and open-source software licensed under the terms of
LGPL2+ license (the GNU LGPL version 2 or any later version). $PRODUCT is
NOT endorsed by, affiliated with, or a product of the FreeCAD project or the
FreeCAD Project Association.

FreeCAD's program files are unmodified: no FreeCAD source file is patched or
recompiled, and no FreeCAD library or program is changed. Atech rewrites
Contents/Info.plist (name, identifier, version, icon, copyright; FreeCAD's
document types kept at rank Alternate) and adds its own files. The lists
below are MEASURED: every file was compared (sha256, or link target) with
the same path in the unmodified upstream bundle, before signing.

Code signature: adding files breaks FreeCAD's seal, so the bundle is
re-signed after this file is written. That replaces the signature embedded
in Contents/MacOS/FreeCAD (its code is unchanged) and rewrites
Contents/_CodeSignature/CodeResources; both are MODIFIED in the shipped
bundle in addition to the list below. Every other program and library keeps
the FreeCAD Project Association's own signature.

Corresponding source: Contents/Resources/share/doc/$DOC_NAME/SOURCE_OFFER.txt

NOTICE
  python3 "$HERE/tree_changes.py" diff "$CONTENTS" "$BUILD/upstream_manifest.json"
} > "$BUILD/ATECH_CHANGES.txt" || fail "could not generate ATECH_CHANGES"
install -m 0644 "$BUILD/ATECH_CHANGES.txt" "$CHANGES"
python3 "$HERE/tree_changes.py" diff "$CONTENTS" "$BUILD/upstream_manifest.json" \
  | grep -v "^  Resources/share/doc/$DOC_NAME/ATECH_CHANGES.txt\$" > "$BUILD/changes.before_verify"
say "ATECH_CHANGES" "$(grep -E '^(ADDED|REMOVED|MODIFIED) ' "$CHANGES" | tr '\n' ' ')"

# ------------------------------------------------------------------ 6. sign
# Only the outer bundle is re-signed, never --deep: every nested program and
# library keeps the FreeCAD Project Association's Developer ID signature,
# which stays valid because none of them is touched. The entitlements are
# upstream's minus get-task-allow (a debugging entitlement notarization
# refuses): disable-library-validation, so our main executable may load
# libraries signed by another team.
ENT="$BUILD/entitlements.plist"
cat > "$ENT" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.cs.disable-library-validation</key>
  <true/>
</dict>
</plist>
PLIST
# Only the quarantine flag goes. Never `xattr -c`: FreeCAD's signature of
# Contents/packages.txt (not code) lives in that file's extended attributes
# (MEASURED: clearing them fails the signing with "code object is not signed
# at all, In subcomponent: .../Contents/packages.txt").
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
if [[ -n "$SIGN_ID" ]]; then
  codesign --force --sign "$SIGN_ID" --options runtime --timestamp \
           --entitlements "$ENT" "$APP" || fail "codesign failed ($SIGN_ID)"
  say "signature" "Developer ID: $SIGN_ID (hardened runtime, timestamped)"
else
  codesign --force --sign - --options runtime --entitlements "$ENT" "$APP" \
    || fail "ad-hoc codesign failed"
  say "signature" "ad-hoc (set ATECH_MAC_SIGN_IDENTITY for a Developer ID)"
fi
codesign --verify --deep --strict "$APP" || fail "the signed bundle does not verify"
python3 "$HERE/tree_changes.py" diff "$CONTENTS" "$BUILD/upstream_manifest.json" \
  | grep -v "^  Resources/share/doc/$DOC_NAME/ATECH_CHANGES.txt\$" > "$BUILD/changes.after_sign"
python3 - "$BUILD/changes.before_verify" "$BUILD/changes.after_sign" <<'PY' \
  || fail "signing changed more than the main executable's signature and CodeResources"
import sys
def parse(p):
    out, sec = {}, None
    for ln in open(p, encoding="utf-8"):
        if ln[:1] not in " \n":
            sec = ln.split(" ")[0]
        elif ln.startswith("  ") and ln.strip() != "(none)":
            out.setdefault(sec, set()).add(ln.strip())
    return out
a, b = parse(sys.argv[1]), parse(sys.argv[2])
want = {"MacOS/FreeCAD", "_CodeSignature/CodeResources"}
extra = {(s, p) for s in set(a) | set(b) for p in b.get(s, set()) ^ a.get(s, set())}
ok = extra == {("MODIFIED", p) for p in want}
print("  signing changed: %s" % sorted(extra), file=sys.stderr) if not ok else None
sys.exit(0 if ok else 1)
PY
say "signature changed" "MacOS/FreeCAD (signature), _CodeSignature/CodeResources only"

# ---------------------------------------------------------------- 7. verify
# Read-only from here on (see RUNNER above): the gate runs the SIGNED
# bundle's own freecadcmd, and the bundle is then re-measured; any change
# (bytecode included) fails the build instead of being cleaned up.
echo "verifying the built bundle:"
VERIFY_ENV=()
[[ "$DEV_UNLICENSED" == 1 ]] && VERIFY_ENV+=(ATECH_VERIFY_DEV_UNLICENSED=1)
VERIFY_ENV+=("ATECH_VERIFY_FORBID=$(cd "$HOME" && pwd -P)
$(git -C "$REPO" config user.email 2>/dev/null || true)")
mkdir -p "$SCRATCH_HOME/gate"
install -m 0644 "$HERE/verify_tree.py" "$SCRATCH_HOME/gate/verify_tree.py"
VERIFY_OUT="$(cd "$SCRATCH_HOME" && fc_clean "${VERIFY_ENV[@]}" \
                "$RES/bin/freecadcmd" "$SCRATCH_HOME/gate/verify_tree.py" 2>&1 || true)"
echo "$VERIFY_OUT" | sed -n '/^  /p;/^VERIFY_FAILURES/p;/^VERIFY_FAILED/p'
grep -q '^VERIFY_FAILURES=0$' <<<"$VERIFY_OUT" || fail "branding verification did not pass"
python3 "$HERE/tree_changes.py" diff "$CONTENTS" "$BUILD/upstream_manifest.json" \
  | grep -v "^  Resources/share/doc/$DOC_NAME/ATECH_CHANGES.txt\$" > "$BUILD/changes.after_verify"
diff -u "$BUILD/changes.after_sign" "$BUILD/changes.after_verify" >&2 \
  || fail "verification changed the bundle (bytecode written into it?)"
codesign --verify --deep --strict "$APP" || fail "the gate broke the bundle's signature"
echo "verify OK"

# Smoke test the SIGNED bundle: its own freecadcmd starts, imports the addon
# from inside the bundle, and leaves the seal intact (step 3d; a
# __pycache__ written here would break the signature on the user's Mac).
SMOKE="$(cd "$SCRATCH_HOME" && fc_clean "$RES/bin/freecadcmd" -c \
  "import sys; sys.path.insert(0, FreeCAD.getHomePath() + 'Mod/AcadAgent'); from acadagent import sandbox; print('SMOKE', sandbox.isolation())" 2>&1 || true)"
grep -q '^SMOKE seatbelt$' <<<"$SMOKE" || { echo "$SMOKE" | tail -5 >&2; fail "signed bundle smoke test failed (want sandbox isolation 'seatbelt')"; }
codesign --verify --deep --strict "$APP" || fail "running the bundle broke its signature (bytecode written into it?)"
say "smoke test" "freecadcmd + addon import OK, isolation=seatbelt, seal intact"

if [[ "$DEV_UNLICENSED" == 1 ]]; then
  echo; echo "NOT RELEASABLE: built with --dev-unlicensed."
  echo "App for local use only: $APP"; exit 0
fi
if [[ "$APP_ONLY" == 1 ]]; then
  echo; echo "PASS (app only): $APP"; exit 0
fi

# -------------------------------------------------------------- 8. disk image
STAGE="$BUILD/dmg-stage"
rm -rf "$STAGE"; mkdir -p "$STAGE"
mkdir -p "$STAGE/bundle.tmp" && ditto "$APP/Contents" "$STAGE/bundle.tmp/Contents" \
  && mv "$STAGE/bundle.tmp" "$STAGE/$PRODUCT.app" \
  || fail "could not stage the app for the disk image"
ln -s /Applications "$STAGE/Applications"
mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
rm -f "$OUT"
hdiutil create -quiet -volname "$PRODUCT" -srcfolder "$STAGE" -fs HFS+ \
        -format UDZO -imagekey zlib-level=9 -ov "$OUT" || fail "hdiutil create failed"
rm -rf "$STAGE"
if [[ -n "$SIGN_ID" ]]; then
  codesign --force --sign "$SIGN_ID" --timestamp "$OUT" || fail "could not sign the disk image"
fi
say "disk image" "$OUT ($(du -h "$OUT" | cut -f1))"

if [[ -n "${ATECH_NOTARY_PROFILE:-}" ]]; then
  [[ -n "$SIGN_ID" ]] || fail "ATECH_NOTARY_PROFILE needs a Developer ID (ATECH_MAC_SIGN_IDENTITY)"
  xcrun notarytool submit "$OUT" --keychain-profile "$ATECH_NOTARY_PROFILE" --wait \
    || fail "notarization failed (xcrun notarytool log <id> --keychain-profile $ATECH_NOTARY_PROFILE)"
  xcrun stapler staple "$OUT" || fail "could not staple the notarization ticket"
  spctl -a -t open --context context:primary-signature -vv "$OUT" \
    || fail "Gatekeeper does not accept the notarized disk image"
  say "notarization" "accepted by Apple, ticket stapled"
else
  say "notarization" "SKIPPED (ATECH_NOTARY_PROFILE unset): a browser download will be blocked by Gatekeeper; install.sh works"
fi

( cd "$(dirname "$OUT")" && shasum -a 256 "$(basename "$OUT")" > SHA256SUMS \
    && shasum -a 256 -c --quiet SHA256SUMS ) \
  || fail "could not write or re-check $(dirname "$OUT")/SHA256SUMS"
say "SHA256SUMS" "$(dirname "$OUT")/SHA256SUMS"
echo "PASS"
