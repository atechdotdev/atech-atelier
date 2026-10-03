"""style — the Atech Atelier design system for everything this addon draws.

ONE token table per mode, copied from brand/tokens.py (which is itself ported
from the atech.dev frontend). The addon ships alone inside the AppImage, so it
cannot import brand/; tests/test_style_tokens.py holds the two tables equal.

The mode follows the theme the user picked when its name says dark or light,
and the application palette's Window lightness otherwise (mode()), so the
panel, the shell and FreeCAD's own chrome can never disagree about light and
dark again.

Visual language, taken from the atech.dev project page rather than invented:
rounded-2xl surfaces, a soft sunken composer, one round black (light) / white
(dark) primary button, hairline borders, Inter for UI, Geist Mono for every
measured number.
"""
from PySide6 import QtCore, QtGui, QtSvg

# --------------------------------------------------------------- tokens
# SOURCED: brand/tokens.py LIGHT / DARK / STATUS. Keep in step.
LIGHT = {
    "base": "#f5f5f5", "panel": "#ffffff", "sunken": "#f9fafb",
    "line": "#e5e7eb", "line_strong": "#d1d5db",
    "text": "#111827", "muted": "#6b7280", "dim": "#9ca3af",
    "btn_bg": "#000000", "btn_bg_hover": "#1a1a1a", "btn_text": "#ffffff",
    "input_bg": "#ffffff", "input_border": "#e5e7eb", "hover": "#f3f4f6",
    "ok": "#387e4f", "fail": "#cc3d28", "warn": "#92691a", "accent": "#07805e",
}
DARK = {
    "base": "#111111", "panel": "#1a1a1a", "sunken": "#0d0d0d",
    "line": "#2a2a2a", "line_strong": "#333333",
    "text": "#f5f5f5", "muted": "#a0a0a0", "dim": "#666666",
    "btn_bg": "#f5f5f5", "btn_bg_hover": "#ffffff", "btn_text": "#111111",
    "input_bg": "#1a1a1a", "input_border": "#2a2a2a", "hover": "#222222",
    "ok": "#6bbd85", "fail": "#e0705f", "warn": "#e0b052", "accent": "#0ff2b2",
}

# Derived surfaces. AUTHORED: the website builds these from rgba() over its
# background (bg-black/[0.03], rgba(235,235,235,0.85)); Qt QSS has no alpha
# compositing we can trust across platforms, so they are pre-blended here.
LIGHT.update({"bubble": "#f3f4f6", "card": "#fafafa", "composer": "#efefef",
              "track": "#eeeeef", "view_top": "#fbfbfb", "view_bot": "#e4e5e8"})
DARK.update({"bubble": "#222222", "card": "#161616", "composer": "#1f1f1f",
             "track": "#0d0d0d", "view_top": "#1c1c1e", "view_bot": "#0b0b0c"})

FONT_UI = "Inter"
FONT_MONO = "Geist Mono"
FONT_DISPLAY = "Sen"
UI_FAMILIES = ("Inter", "Segoe UI", "Cantarell", "DejaVu Sans")
MONO_FAMILIES = ("Geist Mono", "JetBrains Mono", "DejaVu Sans Mono",
                 "Liberation Mono", "Noto Sans Mono")
_PICKED = {}


def _pick(families):
    """First installed family, quoted for QSS. MEASURED: a QSS fallback list
    ('Geist Mono', ..., monospace) did NOT fall through on this Qt - the
    measurement table rendered proportional and its columns wobbled. So
    resolve against the font database and hand QSS exactly one name."""
    if families not in _PICKED:
        have = set(QtGui.QFontDatabase.families())
        name = next((f for f in families if f in have), families[-1])
        _PICKED[families] = "'%s'" % name
    return _PICKED[families]


def _theme_name():
    try:
        import FreeCAD
        g = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/MainWindow")
        return g.GetString("Theme").lower(), g.GetString("StyleSheet").lower()
    except Exception:                                  # noqa: BLE001
        return "", ""


def palette_is_dark(pal=None):
    """True/False from the Window colour's lightness, None without an app.

    HSL lightness below 128 of 255 reads as a dark window; that is the same
    test Qt's own style hints use for colour-scheme guesses."""
    try:
        if pal is None:
            app = QtGui.QGuiApplication.instance()
            if app is None:
                return None
            pal = app.palette()
        return pal.color(QtGui.QPalette.Window).lightness() < 128
    except Exception:                                  # noqa: BLE001
        return None


def mode():
    """'dark' or 'light', following what FreeCAD actually paints.

    FreeCAD 1.1 colours come from the THEME (token set), not only from the
    .qss file: MEASURED on a real profile, StyleSheet=FreeCAD.qss with
    Theme="Atech Atelier Dark" paints a dark app, and reading the file name
    alone put a light panel into it. So a theme that NAMES its mode decides.

    A theme that does not (Classic, a custom theme, none at all) is judged
    by the application palette's Window lightness (R34): a dark Classic
    profile used to get light panels because its name has no "dark" in it.
    The stylesheet file name is the last resort."""
    theme, sheet = _theme_name()
    if "dark" in theme:
        return "dark"
    if "light" in theme:
        return "light"
    dark = palette_is_dark()
    if dark is not None:
        return "dark" if dark else "light"
    return "dark" if "dark" in sheet else "light"


def tokens(m=None):
    return DARK if (m or mode()) == "dark" else LIGHT


def qss(template, m=None, **extra):
    """Fill {token} placeholders. Braces in QSS are doubled in templates.
    `extra` supplies non-colour values a template needs (an icon path)."""
    t = dict(tokens(m))
    t.update(UI=_pick(UI_FAMILIES), MONO=_pick(MONO_FAMILIES))
    t.update(extra)
    # Upstream FreeCAD.qss gives every QPushButton a min-width, which
    # stretched the round send button to 104 px and the view bar past the
    # viewport (measured on a real profile). Our stylesheets sit closer to
    # our widgets than the app's, so this reset wins for everything we draw.
    return template.format(**t) + RESET


RESET = """
QPushButton { min-width: 0px; }
"""


# ---------------------------------------------------------------- icons
# Lucide-style strokes (24 px grid, 2 px stroke), inlined so nothing is
# fetched at runtime. currentColor is substituted per mode at render time.
#
# SOURCE AND LICENCE (R05, R62). The path data in PATHS is taken from Lucide
# (https://github.com/lucide-icons/lucide, ISC, (c) Lucide Icons and
# Contributors), some of it simplified; Lucide's icons derive in part from
# Feather (https://github.com/feathericons/feather, MIT, (c) 2013-present
# Cole Bemis). "stop" (a filled square) and "tree" (two columns of lines)
# are plain shapes drawn for this file. Both licence texts ship in the
# AppImage at usr/share/doc/atech-atelier/third_party/LICENSE.Lucide and
# LICENSE.Feather, listed in NOTICE.third_party (branding/third_party/ in
# the repo). An icon added here must come from Lucide or be drawn here.
_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round" '
        'stroke-linejoin="round">{body}</svg>')

PATHS = {
    "arrow-up": '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="{c}" stroke="none"/>',
    "chat": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "tree": '<path d="M3 5h8"/><path d="M3 12h8"/><path d="M3 19h8"/>'
            '<path d="M15 5h6"/><path d="M15 12h6"/><path d="M15 19h6"/>',
    "layers": '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/>'
              '<path d="m2 12 10 5 10-5"/>',
    "fit": '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/>'
           '<path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/>'
           '<rect x="8" y="8" width="8" height="8" rx="1"/>',
    "cube": '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8'
            'a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>'
            '<path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
    "rotate": '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    "sparkles": '<path d="M12 3l1.9 5.8L20 10.7l-5.8 1.9L12 18.5l-1.9-5.9L4 10.7'
                'l6.1-1.9z"/><path d="M19 3v4"/><path d="M21 5h-4"/>',
    "camera": '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0'
              ' 2-2V9a2 2 0 0 0-2-2h-3z"/><circle cx="12" cy="13" r="3"/>',
    "terminal": '<path d="m4 17 6-6-6-6"/><path d="M12 19h8"/>',
    "settings": '<path d="M12.2 2h-.4a2 2 0 0 0-2 2v.2a2 2 0 0 1-1 1.7l-.4.3a2 2 0 0 1-2 0'
                'l-.2-.1a2 2 0 0 0-2.7.7l-.2.4a2 2 0 0 0 .7 2.7l.2.1a2 2 0 0 1 1 1.7v.5'
                'a2 2 0 0 1-1 1.8l-.2.1a2 2 0 0 0-.7 2.7l.2.4a2 2 0 0 0 2.7.7l.2-.1a2 2 0'
                ' 0 1 2 0l.4.3a2 2 0 0 1 1 1.7v.2a2 2 0 0 0 2 2h.4a2 2 0 0 0 2-2v-.2a2 2 0'
                ' 0 1 1-1.7l.4-.3a2 2 0 0 1 2 0l.2.1a2 2 0 0 0 2.7-.7l.2-.4a2 2 0 0 0-.7'
                '-2.7l-.2-.1a2 2 0 0 1-1-1.8v-.5a2 2 0 0 1 1-1.7l.2-.1a2 2 0 0 0 .7-2.7'
                'l-.2-.4a2 2 0 0 0-2.7-.7l-.2.1a2 2 0 0 1-2 0l-.4-.3a2 2 0 0 1-1-1.7V4'
                'a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    "folder": '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9'
              'l-.8-1.2A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2z"/>',
    "file-plus": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/>'
                 '<path d="M14 2v5h5"/><path d="M12 12v6"/><path d="M9 15h6"/>',
    "ruler": '<path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0'
             'L2.7 8.7a2.4 2.4 0 0 1 0-3.4l2.6-2.6a2.4 2.4 0 0 1 3.4 0z"/>'
             '<path d="m14.5 12.5 2-2"/><path d="m11.5 9.5 2-2"/>'
             '<path d="m8.5 6.5 2-2"/><path d="m17.5 15.5 2-2"/>',
    "menu": '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/>'
           '<path d="m4.9 4.9 1.4 1.4"/><path d="m17.7 17.7 1.4 1.4"/><path d="M2 12h2"/>'
           '<path d="M20 12h2"/><path d="m6.3 17.7-1.4 1.4"/><path d="m19.1 4.9-1.4 1.4"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
            '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "mouse": '<rect x="5" y="2" width="14" height="20" rx="7"/><path d="M12 6v4"/>',
}


def pixel_scale():
    """Raster scale for icons: ceil of the highest screen devicePixelRatio,
    never below 2. A fixed 2x blurred at 250-300 % (R34)."""
    import math
    dpr = 1.0
    try:
        app = QtGui.QGuiApplication.instance()
        if app is not None:
            for sc in app.screens():
                dpr = max(dpr, float(sc.devicePixelRatio()))
    except Exception:                                  # noqa: BLE001
        pass
    return max(2, int(math.ceil(dpr - 1e-6)))


def icon(name, color, size=18, stroke=2.0, scale=None):
    """Render a named stroke icon to a crisp QIcon at the screen's scale."""
    body = PATHS[name].replace("{c}", color)
    svg = _SVG.format(c=color, w=stroke, body=body).encode("utf-8")
    ren = QtSvg.QSvgRenderer(QtCore.QByteArray(svg))
    scale = int(scale or pixel_scale())
    img = QtGui.QImage(size * scale, size * scale,
                       QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    ren.render(p)
    p.end()
    pm = QtGui.QPixmap.fromImage(img)
    pm.setDevicePixelRatio(scale)
    return QtGui.QIcon(pm)


def _logo_file(m):
    import os
    import sys
    names = ["atech_icon-dark.svg", "atech_icon.svg"] if m == "dark" \
        else ["atech_icon.svg", "atech_icon-light.svg"]
    dirs = [os.path.dirname(sys.executable)]
    try:
        import FreeCAD
        dirs.append(os.path.join(FreeCAD.getHomePath(), "bin"))
    except Exception:                                  # noqa: BLE001
        pass
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None


_LOGO_CACHE = {}


def logo_pixmap(height=20, m=None):
    """The Atech mark, WITHOUT its app-icon tile, cropped to the glyph.

    Source: usr/bin/atech_icon*.svg, generated by brand/tools/build_brand.py.
    That file is an app icon (a rounded tile around the mark); inside the UI
    the tile reads as a stray button, so its <rect> is dropped before render.
    """
    m = m or mode()
    scale = pixel_scale()
    key = (height, m, scale)
    if key in _LOGO_CACHE:
        return _LOGO_CACHE[key]
    path = _logo_file(m)
    if path is None:
        return None
    import re
    with open(path, encoding="utf-8") as fh:
        svg = fh.read()
    svg = re.sub(r"<rect\b[^>]*/>", "", svg, count=1)
    ren = QtSvg.QSvgRenderer(QtCore.QByteArray(svg.encode("utf-8")))
    big = 256
    img = QtGui.QImage(big, big, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)
    pa = QtGui.QPainter(img)
    pa.setRenderHint(QtGui.QPainter.Antialiasing)
    ren.render(pa)
    pa.end()
    # crop to opaque pixels
    xs, ys = [], []
    for y in range(0, big, 2):
        for x in range(0, big, 2):
            if QtGui.qAlpha(img.pixel(x, y)) > 20:
                xs.append(x)
                ys.append(y)
    if xs:
        img = img.copy(QtCore.QRect(min(xs), min(ys), max(xs) - min(xs) + 2,
                                    max(ys) - min(ys) + 2))
    img = img.scaledToHeight(height * scale, QtCore.Qt.SmoothTransformation)
    pm = QtGui.QPixmap.fromImage(img)
    pm.setDevicePixelRatio(scale)
    _LOGO_CACHE[key] = pm
    return pm


# ------------------------------------------------------------- terminal
# Shared by terminal.py (the pty widget) and terminal_dock.py (its header).
# Follows the mode like everything else: a light terminal in a light window,
# so the bottom dock reads as part of the app, not a pasted-in console.
TERMINAL_QSS = """
#TermOut {{
    background: {sunken}; color: {text}; border: none;
    font-family: {MONO}; font-size: 12px; padding: 6px 10px;
    selection-background-color: {line_strong};
}}
#TermRow {{ background: {panel}; border-top: 1px solid {line}; }}
#TermHead {{ background: {panel}; border-top: 1px solid {line}; border-bottom: 1px solid {line}; }}
#TermInput {{
    background: {composer}; color: {text}; border: 1px solid {line};
    border-radius: 10px; padding: 6px 10px; font-family: {MONO}; font-size: 12px;
}}
#TermInput:focus {{ border-color: {line_strong}; }}
#TermBtn {{
    background: {panel}; color: {text}; border: 1px solid {line};
    border-radius: 13px; padding: 0 12px; min-height: 26px; max-height: 26px;
    font-family: {UI}; font-size: 12px;
}}
#TermBtn:hover {{ background: {hover}; border-color: {line_strong}; }}
#TermBtn:disabled {{ color: {dim}; }}
#TermTitle {{ color: {text}; font-family: {UI}; font-size: 12px; font-weight: 600; }}
#TermStatus {{ color: {dim}; font-family: {MONO}; font-size: 11px; }}
#TermClose {{ background: transparent; border: none; border-radius: 6px; }}
#TermClose:hover {{ background: {hover}; }}
"""

