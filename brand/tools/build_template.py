#!/usr/bin/env python3
"""Fill the first-run parameter template's accent colours from the tokens.

branding/assets/atech_user_template.cfg carries ACCENT1/2/3 placeholders;
this writes branding/assets/atech_user_template.built.cfg with them
replaced by RGBA-packed uint32 values derived from brand/tokens.py.

The packing is 0xRRGGBBAA. VERIFIED arithmetically rather than assumed:
the file's own previous values were documented as 1520631807 = #5AA2FF and
2590769151 = #9A6BFF, and only the RGBA packing reproduces both
(0x5aa2ffff and 0x9a6bffff). ARGB, ABGR and BGRA all disagree. Checking a
documented pair against four candidate encodings is a comparison the file
cannot win by agreeing with itself (CLAUDE.md P2).

Run:  python3 brand/tools/build_template.py [--check]
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAND)
sys.path.insert(0, BRAND)

import tokens

SRC = os.path.join(ROOT, "branding", "assets", "atech_user_template.cfg")
OUT = os.path.join(ROOT, "branding", "assets",
                   "atech_user_template.built.cfg")

# The documented pair that fixes the packing. If a FreeCAD upgrade ever
# changes the encoding, this assertion is what notices.
KNOWN = {"#5aa2ff": 1520631807, "#9a6bff": 2590769151}


def pack(hex_colour, alpha=0xFF):
    """#rrggbb -> RGBA-packed uint32, the encoding FreeCAD's Themes use."""
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (r << 24) | (g << 16) | (b << 8) | alpha


for _c, _v in KNOWN.items():
    assert pack(_c) == _v, (
        f"RGBA packing no longer reproduces the documented value for {_c}: "
        f"expected {_v}, computed {pack(_c)}")


def render(mode="light"):
    p = tokens.palette(mode)
    with open(SRC, encoding="utf-8") as fh:
        text = fh.read()
    # 1 = the accent proper; 2 = the pure site accent, kept as the secondary
    # so the gradient's identity survives where FreeCAD blends the two;
    # 3 = the mode's strong border, for the tertiary chrome accent.
    subs = {
        "ACCENT1": pack(p["accent"]),
        "ACCENT2": pack(p["accent_pure"]),
        "ACCENT3": pack(p["line_strong"]),
    }
    for k, v in subs.items():
        text = text.replace(f'Value="{k}"', f'Value="{v}"')
    return text, subs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--mode", default="light", choices=sorted(tokens.MODES))
    args = ap.parse_args()

    text, subs = render(args.mode)

    leftover = re.findall(r'Value="(ACCENT\d)"', text)
    if leftover:
        sys.exit(f"FAIL unreplaced placeholders: {', '.join(leftover)}")

    p = tokens.palette(args.mode)
    for name, val, src in (("ThemeAccentColor1", subs["ACCENT1"], p["accent"]),
                           ("ThemeAccentColor2", subs["ACCENT2"],
                            p["accent_pure"]),
                           ("ThemeAccentColor3", subs["ACCENT3"],
                            p["line_strong"])):
        print(f"[ OK ] {name} = {val:<11} 0x{val:08x}  {src}")

    if args.check:
        if not os.path.exists(OUT):
            sys.exit(f"FAIL missing {os.path.relpath(OUT, ROOT)}")
        with open(OUT, encoding="utf-8") as fh:
            if fh.read() != text:
                sys.exit(f"FAIL {os.path.relpath(OUT, ROOT)} is stale — "
                         "re-run brand/tools/build_template.py")
        print(f"[ OK ] {os.path.relpath(OUT, ROOT)} matches the tokens")
        return

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"[ OK ] wrote {os.path.relpath(OUT, ROOT)} ({args.mode})")


if __name__ == "__main__":
    main()
