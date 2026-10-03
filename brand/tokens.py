"""Atech brand tokens — the single source of truth for Atech Atelier.

PORTED, NOT INVENTED. Every colour below is copied verbatim from the
atech.dev frontend at frontend/src/app/globals.css, which is the live
brand. The desktop shell exists beside that website on the same screen;
a value that differs from it is a bug, not a design choice.

Provenance, measured 2026-09-24:

  frontend/src/app/globals.css   :root {...}  -> LIGHT
  frontend/src/app/globals.css   .dark {...}  -> DARK
  frontend/src/lib/contexts/ThemeContext.tsx  -> light | dark | auto,
                                                 seeded 'light' on first run

The frontend switches modes with a `.dark` class on <html>. Qt has no
cascade to switch, so the same token table is instead rendered into two
stylesheets — see brand/tools/build_brand.py. One table, two outputs,
so the palettes cannot drift. The previous hand-maintained AtechCAD.qss
admitted this problem in its own header ("If you change a colour, change
both") and that is exactly the drift this module removes.

Do not add a colour here that is not in the frontend. If the desktop app
genuinely needs one the website does not have (Qt's pass/fail states are
the only such case today), mark it AUTHORED and say why.
"""

# --------------------------------------------------------------------------
# Surfaces and text. SOURCED: globals.css.
# --------------------------------------------------------------------------
LIGHT = {
    # surfaces
    "base":   "#f5f5f5",   # --background
    "panel":  "#ffffff",   # --surface-primary / --card-bg
    "sunken": "#f9fafb",   # --surface-secondary
    "line":   "#e5e7eb",   # --border-light / --card-border
    "line_strong": "#d1d5db",  # --border-medium
    # text
    "text":   "#111827",   # --text-primary
    "muted":  "#6b7280",   # --text-secondary
    "dim":    "#9ca3af",   # --text-muted
    # controls
    "btn_bg":        "#000000",  # --button-primary-bg
    "btn_bg_hover":  "#1a1a1a",  # --button-primary-bg-hover
    "btn_text":      "#ffffff",  # --button-primary-text
    "input_bg":      "#ffffff",  # --input-bg
    "input_border":  "#e5e7eb",  # --input-border
    "hover":         "#f3f4f6",  # --glass-bg-hover
}

DARK = {
    "base":   "#111111",   # --background
    "panel":  "#1a1a1a",   # --surface-secondary / --card-bg
    "sunken": "#0d0d0d",   # AUTHORED: globals.css has no surface below
                           # --background in dark. Qt needs one for sunken
                           # wells (text edits, the viewport gutter); this is
                           # --background darkened, not a new hue.
    "line":   "#2a2a2a",   # --card-border / --border-medium
    "line_strong": "#333333",  # --glass-border-strong
    "text":   "#f5f5f5",   # --text-primary
    "muted":  "#a0a0a0",   # --text-secondary
    "dim":    "#666666",   # --text-muted
    "btn_bg":        "#f5f5f5",  # --button-primary-bg
    "btn_bg_hover":  "#ffffff",  # --button-primary-bg-hover
    "btn_text":      "#111111",  # --button-primary-text
    "input_bg":      "#1a1a1a",  # --input-bg
    "input_border":  "#2a2a2a",  # --input-border
    "hover":         "#222222",  # --glass-bg-hover
}

# --------------------------------------------------------------------------
# Accent. SOURCED, but deliberately reduced.
#
# The frontend's only chromatic content in the whole sheet is one hero
# gradient (globals.css:651):
#     120deg, #0ff2b2, #22d3ee, #6366f1, #a855f7, #22d3ee, #0ff2b2
# We take its first stop as a FLAT colour and drop the gradient. A gradient
# in a CAD window competes with the geometry, which is the only thing on
# screen that carries information. One accent, used on focus and the active
# tool, is the entire accent budget.
# --------------------------------------------------------------------------
ACCENT = "#0ff2b2"

# --------------------------------------------------------------------------
# Status. AUTHORED — the website has no pass/fail vocabulary because it has
# no gates to report.
#
# The DARK values are carried over unchanged from the previous
# brand/assets/AtechCAD.qss, so existing screenshots stay valid.
#
# The LIGHT values are NOT the same colours. MEASURED 2026-09-24: the
# dark-mode status palette does not survive the port to a light background —
# on #f5f5f5 it lands at contrast 2.08 (ok), 2.90 (fail) and 1.83 (warn),
# i.e. unreadable, because it was picked for a dark-only app. These carry
# gate verdicts, so illegible is not an option. Each light value holds the
# dark one's hue and saturation and walks lightness down to the first point
# that clears WCAG AA 4.5:1 on #f5f5f5 — measured 4.52 for all four.
#
# CLAUDE.md R5: fail must be louder than pass. Preserved in both modes.
# --------------------------------------------------------------------------
STATUS = {
    "light": {"ok": "#387e4f", "fail": "#cc3d28", "warn": "#92691a",
              "accent": "#07805e"},
    "dark":  {"ok": "#6bbd85", "fail": "#e0705f", "warn": "#e0b052",
              "accent": "#0ff2b2"},
}

MODES = {"light": LIGHT, "dark": DARK}

# --------------------------------------------------------------------------
# Type. SOURCED: frontend/src/app/layout.tsx (next/font/google).
# Qt resolves these by family name and falls back silently if absent, so the
# AppImage ships them — see branding/build_appimage.sh.
# --------------------------------------------------------------------------
FONT_DISPLAY = "Sen"        # wordmark, dock titles
FONT_BODY = "Inter"         # all UI text
FONT_MONO = "Geist Mono"    # measurements — load-bearing, every number this
                            # app prints is a measured dimension

FONT_STACK_BODY = f"'{FONT_BODY}', 'Segoe UI', system-ui, sans-serif"
FONT_STACK_DISPLAY = f"'{FONT_DISPLAY}', '{FONT_BODY}', system-ui, sans-serif"
FONT_STACK_MONO = f"'{FONT_MONO}', 'DejaVu Sans Mono', monospace"


def palette(mode):
    """Return the token dict for `mode`, with accent and status folded in."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {sorted(MODES)}")
    p = dict(MODES[mode])
    p.update(STATUS[mode])
    p["accent_pure"] = ACCENT
    return p


def all_colours():
    """Every colour this brand is allowed to use. The verifier's whitelist."""
    seen = set()
    for mode in MODES:
        seen.update(v for v in palette(mode).values() if v.startswith("#"))
    return seen
