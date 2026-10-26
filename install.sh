#!/usr/bin/env bash
#
# Atech AI CAD (formerly Atech Atelier) installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/atechdotdev/atech-atelier/main/install.sh | bash
#
# Or download this file, read it, and run it:  bash install.sh [options]
#
# What it does, and nothing more:
#   1. finds the newest release on GitHub (or the one you name) that has a
#      build for this computer: macOS Apple silicon or Intel (.dmg), or
#      Linux x86_64 (.AppImage);
#   2. downloads it and that release's SHA256SUMS over HTTPS, and refuses to
#      go on unless the file's sha256 is listed there and matches;
#   3. installs it for you, without sudo:
#        macOS  the app into /Applications (or ~/Applications
#               when /Applications is not writable). The app's code
#               signature is verified before it is copied.
#        Linux  the AppImage into ~/.local/share/atech-atelier/, a launcher
#               entry and icon for your desktop, and the command
#               ~/.local/bin/atech-atelier;
#   4. checks for Claude Code (the chat runs on it) and tells you what is
#      missing. It never installs Claude Code unless you say so
#      (--with-claude, or "y" at the prompt).
# Nothing is sent anywhere except the downloads from github.com (and, only
# with your yes, Anthropic's Claude Code installer from claude.ai).
#
# Options:
#   --version X.Y.Z   install that release instead of the newest one
#   --file PATH       install a file you already downloaded; SHA256SUMS must
#                     sit next to it (or pass --sha256 HEX)
#   --sha256 HEX      the expected sha256 for --file
#   --dir DIR         install location (macOS: the folder for the .app;
#                     Linux: the folder for the AppImage)
#   --with-claude     also install Claude Code if it is missing
#   --no-claude       do not check for Claude Code
#   --uninstall       remove the app (your designs, chats and settings stay)
#   -y, --yes         do not ask questions
#   -h, --help
#
# Environment: ATECH_REPO (default atechdotdev/atech-atelier).

set -euo pipefail

# Everything runs from main(), at the very end: a download cut short can
# never run half a script.
main() {
  REPO="${ATECH_REPO:-atechdotdev/atech-atelier}"
  # The product's display name, taken from what is installed: the app in
  # the disk image, or the AppImage's file name (AtechAICAD-* is "Atech AI
  # CAD", the name from 0.1.2 on; AtechAtelier-* the earlier "Atech Atelier").
  # Every build carries the same id, APP_ID.
  PRODUCT="Atech AI CAD"
  APP_ID="dev.atech.Atelier"
  VERSION=""
  FILE=""
  SHA=""
  DIR=""
  CLAUDE="ask"
  UNINSTALL=0
  YES=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --version)     VERSION="${2#v}"; shift 2 ;;
      --file)        FILE="$2"; shift 2 ;;
      --sha256)      SHA="$2"; shift 2 ;;
      --dir)         DIR="$2"; shift 2 ;;
      --with-claude) CLAUDE="yes"; shift ;;
      --no-claude)   CLAUDE="no"; shift ;;
      --uninstall)   UNINSTALL=1; shift ;;
      -y|--yes)      YES=1; shift ;;
      -h|--help)     sed -n '2,41p' "${BASH_SOURCE[0]:-$0}" 2>/dev/null \
                       || echo "See https://github.com/$REPO#install"; exit 0 ;;
      *) die "unknown option: $1 (try --help)" ;;
    esac
  done

  OS="$(uname -s)"
  ARCH="$(uname -m)"
  case "$OS" in
    Darwin)
      case "$ARCH" in
        arm64)  ;;
        x86_64) # An Intel build running under Rosetta reports x86_64.
                if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)" = 1 ]; then
                  ARCH=arm64
                fi ;;
        *) die "this Mac's processor ($ARCH) is not supported" ;;
      esac
      ASSET_RE="Atech(Atelier|AICAD)-[0-9][^/\"]*-macOS-$ARCH\\.dmg"
      ;;
    Linux)
      [ "$ARCH" = x86_64 ] || die "Linux builds are x86_64 only for now (this is $ARCH)"
      ASSET_RE="Atech(Atelier|AICAD)-[0-9][^/\"]*-x86_64\\.AppImage"
      ;;
    *) die "$OS is not supported (macOS and Linux are)" ;;
  esac

  if [ "$UNINSTALL" = 1 ]; then
    uninstall
    exit 0
  fi

  TMP="$(mktemp -d "${TMPDIR:-/tmp}/atech-install.XXXXXX")"
  trap 'cleanup' EXIT INT TERM

  if [ -n "$FILE" ]; then
    [ -f "$FILE" ] || die "no such file: $FILE"
    ASSET="$FILE"
    NAME="$(basename "$FILE")"
    if [ -z "$SHA" ]; then
      SUMS="$(dirname "$FILE")/SHA256SUMS"
      [ -f "$SUMS" ] || die "no SHA256SUMS next to $FILE (or pass --sha256 HEX)"
      SHA="$(expected_sha "$SUMS" "$NAME")"
    fi
  else
    need curl
    say "Looking for $PRODUCT${VERSION:+ $VERSION} for $(platform_name) on github.com/$REPO"
    URL="$(find_asset_url)" || die "no $(platform_name) build found in the releases of github.com/$REPO${VERSION:+ (version $VERSION)}"
    NAME="$(basename "$URL")"
    say "Downloading $NAME"
    fetch "$(dirname "$URL")/SHA256SUMS" "$TMP/SHA256SUMS" \
      || die "this release has no SHA256SUMS, so its download cannot be verified; not installing"
    SHA="$(expected_sha "$TMP/SHA256SUMS" "$NAME")"
    ASSET="$TMP/$NAME"
    fetch "$URL" "$ASSET" || die "download failed: $URL"
  fi

  case "$NAME" in AtechAtelier-*) PRODUCT="Atech Atelier" ;; AtechAICAD-*) PRODUCT="Atech AI CAD" ;; esac
  printf '%s' "$SHA" | grep -Eq '^[0-9a-f]{64}$' || die "not a sha256: $SHA"
  GOT="$(sha256_of "$ASSET")"
  [ "$GOT" = "$SHA" ] || die "checksum mismatch for $NAME
    expected $SHA
    got      $GOT
  The download is damaged or is not the published file. Nothing was installed."
  say "Verified sha256 $GOT"

  case "$OS" in
    Darwin) install_macos ;;
    Linux)  install_linux ;;
  esac
  check_claude
  echo
  say "Done."
}

# ------------------------------------------------------------------ helpers
if [ -t 2 ]; then B=$'\033[1m' Y=$'\033[33m' R=$'\033[31m' N=$'\033[0m'; else B="" Y="" R="" N=""; fi
say()  { printf '%s==>%s %s\n' "$B" "$N" "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf '%swarning:%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%serror:%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 is required"; }

cleanup() {
  if [ -n "${MNT:-}" ] && [ -d "$MNT" ]; then
    hdiutil detach -quiet "$MNT" 2>/dev/null || hdiutil detach -force -quiet "$MNT" 2>/dev/null || true
  fi
  [ -n "${TMP:-}" ] && rm -rf "$TMP"
}

bundle_id() {  # the CFBundleIdentifier of an .app, or nothing
  [ -f "$1/Contents/Info.plist" ] || return 0
  /usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$1/Contents/Info.plist" 2>/dev/null || true
}

platform_name() {
  case "$OS" in
    Darwin) [ "$ARCH" = arm64 ] && echo "macOS (Apple silicon)" || echo "macOS (Intel)" ;;
    *)      echo "Linux x86_64" ;;
  esac
}

# HTTPS only, TLS 1.2+, follow GitHub's redirects to its download host.
fetch() {
  curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$2" "$1"
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

# The sha256 listed for NAME in a sha256sum-format file, or die.
expected_sha() {
  local line
  line="$(awk -v n="$2" '{f=$2; sub(/^\*/, "", f); if (f == n) {print $1; exit}}' "$1")"
  [ -n "$line" ] || die "SHA256SUMS does not list $2; not installing"
  printf '%s' "$line"
}

# The download URL of this platform's asset: in the named release, or the
# newest release that has one (prereleases included: every Atech release so
# far is a preview).
find_asset_url() {
  local api="https://api.github.com/repos/$REPO/releases" json
  if [ -n "$VERSION" ]; then api="$api/tags/v$VERSION"; else api="$api?per_page=20"; fi
  json="$TMP/releases.json"
  fetch "$api" "$json" || return 1
  grep -Eo '"browser_download_url"[[:space:]]*:[[:space:]]*"https://github\.com/[^"]+"' "$json" \
    | sed -E 's/.*"(https:[^"]+)"$/\1/' \
    | grep -E "/$ASSET_RE\$" | head -n 1 | grep . || return 1
}

ask() {  # ask "question" -> 0 for yes
  [ "$YES" = 1 ] && return 0
  [ -r /dev/tty ] || return 1
  local a
  printf '%s [y/N] ' "$1" > /dev/tty
  read -r a < /dev/tty || return 1
  case "$a" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

# ------------------------------------------------------------------ macOS
mac_dest() {
  if [ -n "$DIR" ]; then echo "$DIR"
  elif [ -w /Applications ]; then echo /Applications
  else echo "$HOME/Applications"; fi
}

install_macos() {
  need hdiutil; need ditto; need codesign
  MNT="$TMP/mnt"
  mkdir -p "$MNT"
  hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$MNT" "$ASSET" >/dev/null \
    || die "could not open the disk image $NAME"
  local src="" a
  for a in "$MNT"/*.app; do
    [ "$(bundle_id "$a")" = "$APP_ID" ] && { src="$a"; break; }
  done
  [ -n "$src" ] || die "the disk image holds no app with the id $APP_ID; not installing"
  PRODUCT="$(basename "$src" .app)"
  # Every file in the bundle must be the one that was signed.
  codesign --verify --deep --strict "$src" 2>/dev/null \
    || die "the app's code signature does not verify; not installing"
  local who
  who="$(codesign -dv "$src" 2>&1 | sed -n 's/^Authority=//p' | head -n 1)"
  say "Code signature valid: ${who:-ad-hoc (the download was checked against SHA256SUMS above)}"

  local dest
  dest="$(mac_dest)"
  mkdir -p "$dest"
  local app="$dest/$PRODUCT.app"
  # Atech Atelier renamed: the old name's app is the same program; replace it.
  local old
  for old in "$dest"/*.app; do
    if [ "$old" != "$app" ] && [ "$(bundle_id "$old")" = "$APP_ID" ]; then
      note "Replacing the earlier $(basename "$old")"
      rm -rf "$old" || die "could not remove $old"
    fi
  done
  if [ -d "$app" ] && pgrep -f "$app/Contents/MacOS/" >/dev/null 2>&1; then
    die "$PRODUCT is running. Quit it, then run the installer again."
  fi
  say "Installing to $app"
  # Copy beside it under a name that is not an .app, then swap: macOS refuses
  # a copy straight to a new *.app path from a process without App Management
  # rights, and an interrupted copy never leaves a half app in place.
  local stage="$dest/.atech-atelier-install.$$"
  rm -rf "$stage"
  ditto "$src" "$stage" || { rm -rf "$stage"; die "could not copy the app to $dest"; }
  if [ -d "$app" ]; then
    rm -rf "$app" || { rm -rf "$stage"; die "could not replace the old $app (macOS may ask you to allow Terminal to manage apps: System Settings > Privacy & Security > App Management)"; }
  fi
  mv "$stage" "$app" || { rm -rf "$stage"; die "could not move the app into place"; }
  codesign --verify --deep --strict "$app" 2>/dev/null || die "the installed app does not verify"
  hdiutil detach -quiet "$MNT" 2>/dev/null || true
  MNT=""
  note "Open it from Launchpad or Applications, or run: open -a \"$app\""
}

# ------------------------------------------------------------------ Linux
linux_dest() { echo "${DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/atech-atelier}"; }

install_linux() {
  local dest data apps icons bin img
  dest="$(linux_dest)"
  data="${XDG_DATA_HOME:-$HOME/.local/share}"
  apps="$data/applications"
  icons="$data/icons/hicolor/scalable/apps"
  bin="$HOME/.local/bin"
  img="$dest/AtechAtelier.AppImage"
  mkdir -p "$dest" "$apps" "$icons" "$bin"
  say "Installing to $img"
  install -m 0755 "$ASSET" "$img.new" && mv -f "$img.new" "$img"
  printf '%s  %s\n' "$GOT" "$NAME" > "$dest/INSTALLED"

  # The icon, taken from the image itself (needs no FUSE).
  ( cd "$TMP" && "$img" --appimage-extract "$APP_ID.svg" >/dev/null 2>&1 ) || true
  if [ -f "$TMP/squashfs-root/$APP_ID.svg" ]; then
    install -m 0644 "$TMP/squashfs-root/$APP_ID.svg" "$icons/$APP_ID.svg"
  fi

  # Without FUSE an AppImage cannot mount itself; it can still run by
  # extracting to a temporary folder first (slower start).
  local run="\"$img\""
  if ! command -v fusermount >/dev/null 2>&1 && ! command -v fusermount3 >/dev/null 2>&1; then
    run="env APPIMAGE_EXTRACT_AND_RUN=1 \"$img\""
    warn "FUSE is not installed, so $PRODUCT will extract itself on every start (slower)."
    note "To fix: install FUSE (Debian/Ubuntu: sudo apt install fuse3)."
  fi
  cat > "$apps/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$PRODUCT
GenericName=CAD Application
Comment=Parametric CAD with a built-in design agent
Exec=$run %F
TryExec=$img
Terminal=false
Icon=$APP_ID
Categories=Graphics;3DGraphics;Engineering;
StartupWMClass=$PRODUCT
MimeType=application/x-extension-fcstd;model/step;model/iges;model/stl;
DESKTOP
  printf '#!/bin/sh\nexec %s "$@"\n' "$run" > "$bin/atech-atelier"
  chmod 0755 "$bin/atech-atelier"
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" >/dev/null 2>&1 || true
  note "Start it from your applications menu, or run: atech-atelier"
  case ":$PATH:" in *":$bin:"*) ;; *) note "($bin is not on your PATH; the menu entry works anyway.)" ;; esac
  if ! command -v bwrap >/dev/null 2>&1; then
    warn "bubblewrap is not installed: design scripts will run without a sandbox."
    note "To isolate them (recommended): sudo apt install bubblewrap  (or your distribution's package)"
  fi
}

# ------------------------------------------------------------------ uninstall
uninstall() {
  case "$OS" in
    Darwin)
      local app="" d a
      for d in ${DIR:+"$DIR"} /Applications "$HOME/Applications"; do
        for a in "$d"/*.app; do
          [ "$(bundle_id "$a")" = "$APP_ID" ] && { app="$a"; break 2; }
        done
      done
      [ -n "$app" ] || die "no installed app with the id $APP_ID found (pass --dir)"
      PRODUCT="$(basename "$app" .app)"
      ask "Remove $app?" || die "cancelled"
      rm -rf "$app"
      say "Removed $app"
      note "Your designs and settings are kept in ~/Library/Application Support/$PRODUCT"
      note "and ~/Library/Preferences/$PRODUCT; delete those folders to remove them too."
      ;;
    Linux)
      local data dest
      data="${XDG_DATA_HOME:-$HOME/.local/share}"
      dest="$(linux_dest)"
      rm -f "$dest/AtechAtelier.AppImage" "$dest/INSTALLED" "$data/applications/$APP_ID.desktop" \
            "$data/icons/hicolor/scalable/apps/$APP_ID.svg" "$HOME/.local/bin/atech-atelier"
      rmdir "$dest" 2>/dev/null || true
      say "Removed the app"
      note "Your designs and settings are kept in $data/<app name> and ~/.config/<app name>;"
      note "delete those folders to remove them too."
      ;;
  esac
}

# ------------------------------------------------------------------ Claude Code
find_claude() {
  local c
  for c in "$HOME/.local/bin/claude" "$(command -v claude 2>/dev/null || true)" \
           /opt/homebrew/bin/claude /usr/local/bin/claude "$HOME/.claude/local/claude"; do
    [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

check_claude() {
  [ "$CLAUDE" = no ] && return 0
  echo
  local c
  if c="$(find_claude)"; then
    say "Claude Code found: $c ($("$c" --version 2>/dev/null | head -n 1))"
  else
    say "Claude Code is not installed. The chat runs on it (a Claude account that includes Claude Code is needed)."
    if [ "$CLAUDE" = yes ] || ask "Install Claude Code now with Anthropic's installer (curl -fsSL https://claude.ai/install.sh | bash)?"; then
      fetch https://claude.ai/install.sh "$TMP/claude-install.sh" || die "could not download Anthropic's installer"
      bash "$TMP/claude-install.sh" || die "Anthropic's installer failed"
      c="$(find_claude)" || { warn "Claude Code was installed but not found; open a new terminal and run: claude --version"; return 0; }
    else
      note "Install it later with:  curl -fsSL https://claude.ai/install.sh | bash"
      note "(see https://code.claude.com/docs/en/setup)"
      return 0
    fi
  fi
  if "$c" auth status >/dev/null 2>&1; then
    note "Signed in. Open $PRODUCT and type what you want to build."
  else
    note "Next: sign in once with:  claude auth login"
    note "(or open $PRODUCT; the chat shows the same step with a Retry button)."
  fi
}

main "$@"
