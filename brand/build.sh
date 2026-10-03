#!/usr/bin/env bash
# Rebuild and verify every Atech Atelier brand asset.
#
#   brand/tokens.py                   colour, ported from the frontend
#   brand/assets/source/atech_*_black.png geometry, the real logo artwork
#                                     (vendored from the atech.dev frontend)
#        |
#        +-- build_brand.py     -> icon / logo / splash SVGs, light + dark
#        +-- build_qss.py       -> AtechLight.qss / AtechDark.qss
#        +-- build_theme.py     -> Atech Atelier {Light,Dark}.yaml
#        +-- build_template.py  -> atech_user_template.built.cfg
#
# Nothing in brand/assets/ is edited by hand. Every generator carries a gate
# that can fail, and test_brand_sabotage.sh proves each one actually does.
#
# Usage:  bash brand/build.sh [--check]
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-}"
ARGS=()
[ "$MODE" = "--check" ] && ARGS=(--check)

echo "=== brand assets (geometry + colour) ==="
python3 brand/tools/build_brand.py "${ARGS[@]}"
echo
echo "=== stylesheets ==="
python3 brand/tools/build_qss.py "${ARGS[@]}"
echo
echo "=== theme parameters ==="
python3 brand/tools/build_theme.py "${ARGS[@]}"
echo
echo "=== first-run preferences ==="
python3 brand/tools/build_template.py "${ARGS[@]}"
echo
echo "=== branding.xml ==="
python3 branding/check_branding_xml.py branding/branding.xml
echo
echo "all brand gates passed"
