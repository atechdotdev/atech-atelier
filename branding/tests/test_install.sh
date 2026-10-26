#!/usr/bin/env bash
#
# test_install.sh — drive install.sh end to end against a stand-in release,
# with a throwaway HOME, on the platform it runs on (macOS or Linux):
#
#   1. a good file + SHA256SUMS installs, and the installed app is the file;
#   2. a file whose sha256 differs from SHA256SUMS is refused, nothing installed;
#   3. a file SHA256SUMS does not list is refused;
#   4. macOS: an app whose signature no longer verifies is refused;
#   5. --uninstall removes what 1 installed.
#
# The stand-in on macOS is a real disk image holding a tiny ad-hoc-signed
# "Atech Atelier.app" (bundle id dev.atech.Atelier); on Linux a shell script
# named like the AppImage. No network, no Claude Code (--no-claude).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL="$(cd "$HERE/../.." && pwd)/install.sh"
T="$(mktemp -d "${TMPDIR:-/tmp}/atech-install-test.XXXXXX")"
T="$(cd "$T" && pwd -P)"
trap 'rm -rf "$T"' EXIT
export HOME="$T/home"
mkdir -p "$HOME"
unset XDG_DATA_HOME
fails=0
ok()  { echo "  ok    $*"; }
bad() { echo "  FAIL  $*"; fails=$((fails + 1)); }
sum() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }

make_app() {  # make_app <dir> [marker]
  local app="$1/Atech Atelier.app"
  mkdir -p "$app/Contents/MacOS"
  cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>dev.atech.Atelier</string>
  <key>CFBundleName</key><string>Atech Atelier</string>
  <key>CFBundleExecutable</key><string>FreeCAD</string>
  <key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
PLIST
  printf '#!/bin/sh\necho %s\n' "${2:-stand-in}" > "$app/Contents/MacOS/FreeCAD"
  chmod +x "$app/Contents/MacOS/FreeCAD"
  codesign --force --sign - "$app" 2>/dev/null
}

case "$(uname -s)" in
  Darwin)
    ARCH="$(uname -m)"
    NAME="AtechAtelier-9.9.9-macOS-$ARCH.dmg"
    mkdir -p "$T/stage" "$T/rel"
    make_app "$T/stage"
    hdiutil create -quiet -volname "Atech Atelier" -srcfolder "$T/stage" -fs HFS+ -format UDZO "$T/rel/$NAME"
    # A broken one: a file added after signing.
    mkdir -p "$T/stage2"
    make_app "$T/stage2"
    echo extra > "$T/stage2/Atech Atelier.app/Contents/MacOS/added-after-signing"
    hdiutil create -quiet -volname "Atech Atelier" -srcfolder "$T/stage2" -fs HFS+ -format UDZO "$T/rel/broken-$NAME"
    DEST="$T/Applications"
    INSTALLED="$DEST/Atech Atelier.app"
    ;;
  Linux)
    NAME="AtechAtelier-9.9.9-x86_64.AppImage"
    mkdir -p "$T/rel"
    printf '#!/bin/sh\necho stand-in\n' > "$T/rel/$NAME"
    DEST="$T/apps"
    INSTALLED="$DEST/AtechAtelier.AppImage"
    ;;
esac
( cd "$T/rel" && sum "$NAME" > SHA256SUMS )

echo "install.sh, $(uname -s):"
# 1. good
if out="$(bash "$INSTALL" --file "$T/rel/$NAME" --dir "$DEST" --no-claude 2>&1)"; then
  if [[ -e "$INSTALLED" ]]; then ok "installs a verified file"; else bad "reported success, nothing at $INSTALLED"; fi
else
  bad "a good file was refused: $out"
fi
if [[ "$(uname -s)" == Darwin ]]; then
  codesign --verify --deep --strict "$INSTALLED" 2>/dev/null && ok "installed app verifies" || bad "installed app does not verify"
  left=("$DEST"/* "$DEST"/.[!.]*)
  left=("${left[@]/#$DEST\/\*/}"); left=("${left[@]/#$DEST\/.\[\!.\]\*/}")
  [[ "$(printf '%s' "${left[@]}")" == "$INSTALLED" ]] && ok "no staging leftovers" || bad "leftovers in $DEST: ${left[*]}"
else
  grep -q "Exec=" "$HOME/.local/share/applications/dev.atech.Atelier.desktop" && ok "desktop entry written" || bad "no desktop entry"
  [[ -x "$HOME/.local/bin/atech-atelier" ]] && ok "launcher command written" || bad "no ~/.local/bin/atech-atelier"
fi

# 2. tampered
cp "$T/rel/$NAME" "$T/tampered-$NAME"
printf 'x' >> "$T/tampered-$NAME"
mkdir -p "$T/t2"; mv "$T/tampered-$NAME" "$T/t2/$NAME"; cp "$T/rel/SHA256SUMS" "$T/t2/"
if out="$(bash "$INSTALL" --file "$T/t2/$NAME" --dir "$T/dest2" --no-claude 2>&1)"; then
  bad "a tampered file was installed"
else
  grep -q "checksum mismatch" <<<"$out" && [[ ! -e "$T/dest2" || -z "$(ls -A "$T/dest2")" ]] \
    && ok "refuses a tampered file" || bad "tampered: wrong refusal: $out"
fi

# 3. not listed
mkdir -p "$T/t3"; cp "$T/rel/$NAME" "$T/t3/other-$NAME"; cp "$T/rel/SHA256SUMS" "$T/t3/"
if out="$(bash "$INSTALL" --file "$T/t3/other-$NAME" --dir "$T/dest3" --no-claude 2>&1)"; then
  bad "an unlisted file was installed"
else
  grep -q "does not list" <<<"$out" && ok "refuses a file SHA256SUMS does not list" || bad "unlisted: wrong refusal: $out"
fi

# 4. broken signature (macOS)
if [[ "$(uname -s)" == Darwin ]]; then
  mkdir -p "$T/t4"; cp "$T/rel/broken-$NAME" "$T/t4/$NAME"; ( cd "$T/t4" && sum "$NAME" > SHA256SUMS )
  if out="$(bash "$INSTALL" --file "$T/t4/$NAME" --dir "$T/dest4" --no-claude 2>&1)"; then
    bad "an app with a broken signature was installed"
  else
    grep -q "signature does not verify" <<<"$out" && [[ ! -e "$T/dest4/Atech Atelier.app" ]] \
      && ok "refuses an app whose signature does not verify" || bad "broken signature: wrong refusal: $out"
  fi
fi

# 5. uninstall
if bash "$INSTALL" --uninstall --dir "$DEST" --yes >/dev/null 2>&1 && [[ ! -e "$INSTALLED" ]]; then
  ok "uninstalls"
else
  bad "uninstall left $INSTALLED"
fi

if [[ "$fails" -eq 0 ]]; then echo "INSTALL_TESTS_OK"; else echo "INSTALL_TESTS_FAILED ($fails)"; exit 1; fi
