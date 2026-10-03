#!/usr/bin/env python3
"""Generate AtechLight.qss and AtechDark.qss, then verify them.

The verification is the point, and it is built to satisfy CLAUDE.md P2:
a check must compare against something that CANNOT agree with it by
construction. So it does not re-render the template and diff — that would
be the generator agreeing with itself. It re-reads the written files as
text, extracts every colour literal with a regex, and tests membership in
the token whitelist. A colour typed into the template by hand, or left
behind from the old palette, fails regardless of what the generator thinks.

Run:  python3 brand/tools/build_qss.py [--check]
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAND)
sys.path.insert(0, HERE)
sys.path.insert(0, BRAND)

import qss
import tokens

ASSETS = os.path.join(BRAND, "assets")
OUT = {"light": "AtechLight.qss", "dark": "AtechDark.qss"}

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def verify(path, mode):
    """Re-read `path` as text and check it against the token table.

    Two independent checks, because the first one alone has a hole:

    1. MEMBERSHIP — every colour literal is in this mode's token table.
       Catches a foreign colour (the old #5AA2FF brand, a hand-typed hex).

    2. ROLE — the sheet matches, property by property, what the template
       renders for this mode. Membership CANNOT catch a colour that is
       valid in this mode but used in the wrong place, and that is not a
       hypothetical: #f5f5f5 is light's `base` AND dark's `text`, so
       pasting the dark text colour into the light sheet passes a pure
       membership test. MEASURED: it did, until this check existed.

    Check 2 compares against a re-render, which is the generator agreeing
    with itself — so it is deliberately NOT the only check. Check 1 is the
    independent one (regex over text vs. a table neither the template nor
    the writer can influence), and check 2 only adds ordering//role
    information that check 1 structurally cannot see.
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    # Only the rules, not the comment header — the header documents the
    # palette and legitimately names colours in prose.
    body = re.sub(r"/\*.*?\*/", "", text, flags=re.S)

    allowed = {c.lower() for c in tokens.palette(mode).values()
               if isinstance(c, str) and c.startswith("#")}
    found = {m.group(0).lower() for m in HEX.finditer(body)}
    stray = sorted(found - allowed)

    # A colour from the OTHER mode is the specific failure this catches:
    # it means a literal was copied rather than templated.
    other = "dark" if mode == "light" else "light"
    other_allowed = {c.lower() for c in tokens.palette(other).values()
                     if isinstance(c, str) and c.startswith("#")}
    crossed = sorted(set(stray) & other_allowed)

    # ROLE: the ordered sequence of colour literals must match the template.
    expect = [m.group(0).lower() for m in HEX.finditer(
        re.sub(r"/\*.*?\*/", "", qss.render(mode), flags=re.S))]
    actual = [m.group(0).lower() for m in HEX.finditer(body)]
    misplaced = [(i, e, a) for i, (e, a) in enumerate(zip(expect, actual))
                 if e != a]
    if len(expect) != len(actual):
        misplaced.append((-1, f"{len(expect)} literals",
                          f"{len(actual)} literals"))

    return {
        "colours_used": len(found),
        "stray": stray,
        "cross_mode": crossed,
        "misplaced": misplaced,
        "ok": not stray and not misplaced,
    }


def verify_overlay(path):
    """Re-read the overlay sheet: present, current, and free of hex colours."""
    if not os.path.exists(path):
        return {"ok": False, "why": "missing"}
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    body = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    literals = sorted({m.group(0).lower() for m in HEX.finditer(body)})
    if literals:
        return {"ok": False, "why": "%d hex colour(s), use theme tokens: %s"
                % (len(literals), ", ".join(literals))}
    if text != qss.render_overlay():
        return {"ok": False, "why": "stale (differs from qss.render_overlay)"}
    return {"ok": True,
            "tokens": len(set(re.findall(r"@([A-Za-z0-9_]+)", body)))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the sheets already on disk; write nothing")
    args = ap.parse_args()

    os.makedirs(ASSETS, exist_ok=True)
    failed = False

    for mode, name in sorted(OUT.items()):
        path = os.path.join(ASSETS, name)
        rel = os.path.relpath(path, ROOT)

        if not args.check:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(qss.render(mode))
            print(f"[ OK ] wrote {rel}")
        elif not os.path.exists(path):
            print(f"[FAIL] missing {rel}")
            failed = True
            continue

        v = verify(path, mode)
        if v["ok"]:
            print(f"[ OK ] {rel:28} {v['colours_used']:2d} colours, "
                  f"all in the {mode} token table")
        else:
            failed = True
            if v["stray"]:
                print(f"[FAIL] {rel:28} {len(v['stray'])} colour(s) not in "
                      f"the {mode} token table: {', '.join(v['stray'])}")
                if v["cross_mode"]:
                    print(f"       {len(v['cross_mode'])} of them belong to "
                          f"the OTHER mode — a literal was copied, not "
                          f"templated: {', '.join(v['cross_mode'])}")
            if v["misplaced"]:
                print(f"[FAIL] {rel:28} {len(v['misplaced'])} colour(s) in "
                      f"the wrong role:")
                for i, e, a in v["misplaced"][:5]:
                    where = f"literal #{i}" if i >= 0 else "length"
                    print(f"       {where}: expected {e}, found {a}")

    # The overlay sheet (R88) is mode-free: every colour must be an @Token
    # the theme resolves, so a hex literal in it is a colour that cannot
    # follow the mode. Checked on the file as written, like the sheets above.
    path = os.path.join(ASSETS, qss.OVERLAY_NAME)
    rel = os.path.relpath(path, ROOT)
    if not args.check:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(qss.render_overlay())
        print(f"[ OK ] wrote {rel}")
    v = verify_overlay(path)
    if v["ok"]:
        print(f"[ OK ] {rel:28} {v['tokens']:2d} tokens, no colour literals")
    else:
        failed = True
        print(f"[FAIL] {rel:28} {v['why']}")

    if failed:
        sys.exit("FAIL stylesheet verification")


if __name__ == "__main__":
    main()
