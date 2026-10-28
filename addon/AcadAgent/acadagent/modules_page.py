"""modules_page — add and remove Atech modules on the 14-port board.

The sidebar's third page. Everything geometric comes from
projects/atech_ports.py, which measures the ports off the shipped meshes;
this file only draws and dispatches:

    board map   the 14 ports laid out from the MEASURED port table (edge and
                position along the edge), occupied ones filled, click to pick
    port panel  the picked port: its edge and slide direction, what sits in
                it (Remove), or the module list (Add)
    add         atech_ports.seat() places the module at its seated position;
                it is then animated in along its real insertion axis from
                clear of the board, and atech_ports.check() is shown
    remove      animated out along the same axis, then atech_ports.remove()

    move/swap   (R300) "Move or swap", then pick an empty port (move) or one
                holding a module with as many ports (swap): atech_ports.move/
                swap, one undo step, the object (and its colour) kept
    re-seat     (R301) atech_ports.stale_modules() is polled with the page;
                when the board (or a cabled module) moved, a banner offers
                "Re-seat all" (atech_ports.reseat_all)
    cables      (R302) cabled modules show a cable icon and length, "Connected
                by cable", a plug on the map, and "Remake cable" when stale
    by cable    "Connect by cable" adds the module OFF the board, clear of it
                beyond the picked port, wired to it by atech_ports.cable(): a
                module that must leave the board (a sensor at the front, a
                light in a nose); move it, then "Remake cable"
    power       (R303) Check all warns when no USB-C module is on the board
    hover/undo  (R304) port tooltips (port_tooltip) and "Added X · Undo"
    free parts  (R305) parts with no pin header or no port (N20 wheel,
                NEMA 17) placed by hand beside the board (projects.place_free_part)
    derived     a module whose presets.yaml entry has `derived` (no Atech CAD:
                the simready dataset's shell + placeholder parts) says so on
                its button

A module with two connectors takes the picked port and a free neighbour in
the same column whose trial check passes (atech_ports.pair_for); if neither
does, the page says so instead of adding a module its own check would FAIL.
Only modules with a measurable pin header are offered, and a port listed in
atech_ports.RESERVED (empty until the owner decides) offers none. Anything the library cannot do is said in a sentence that uses
the module's display name (describe_error), never replaced by a guess and
never shown as a raw exception with internal slugs or paths; the raw text
goes to the Report view.
"""
import html
import json
import math
import os
import sys
import time

from PySide6 import QtCore, QtGui, QtWidgets

from . import style

SLIDE_MS = 450
SLIDE_STEPS = 18

# R86: the first frame waits until the new document's 3D view has its final
# size AND the first module has finished sliding in. A fresh document's view
# is created at a provisional size and laid out over the next event-loop
# turns; fitting before that left the board clipped at the bottom and
# off-centre (GUI r2_26..28, still clipped 4 s later) while a second fit
# framed it. Round 3 still saw it (D2): the only fit landed at 120 ms, mid-
# slide, around a module still sticking out of the board, and the view kept
# changing after. So a FirstFrame plan polls the view size and fits whenever
# (view size, slide finished) changes and the size has held still for
# FRAME_SETTLE_TICKS polls: a provisional fit as soon as the view settles (so
# the slide-in is not watched from FreeCAD's default camera), the real one
# once the module is seated, and again if the view is resized before
# FRAME_MAX_MS. After that the user's camera is never moved by the page.
FRAME_POLL_MS = 40
FRAME_SETTLE_TICKS = 3
FRAME_MAX_MS = 2500


def frame_decision(sizes, waited_ms, ticks=FRAME_SETTLE_TICKS,
                   max_ms=FRAME_MAX_MS):
    """'frame' or 'wait' for the first fit, given the view sizes polled so far
    (newest last; None = no view yet). Frames when the last `ticks` sizes are
    one real (w, h > 1) size, or when max_ms is up whatever the view says."""
    if waited_ms >= max_ms:
        return "frame"
    last = list(sizes[-ticks:])
    if len(last) < ticks or last[-1] is None:
        return "wait"
    w, h = last[-1]
    if w <= 1 or h <= 1 or any(s != last[-1] for s in last):
        return "wait"
    return "frame"


class FirstFrame(object):
    """The first-frame plan of ONE document (R86). Pure: no Qt, no FreeCAD.

    step(size, waited_ms) is called every FRAME_POLL_MS with the view's
    size (None = no view) and returns 'frame', 'wait' or 'stop'. It frames
    whenever the view is settled and (size, slide finished) differs from
    what the last fit saw, so a fit made mid-slide or before a resize is
    always followed by one on the final scene. At max_ms it frames once
    more if the view never settled after the slide ended, then stops."""

    def __init__(self, ticks=FRAME_SETTLE_TICKS, max_ms=FRAME_MAX_MS):
        self.ticks, self.max_ms = ticks, max_ms
        self.sizes = []
        self.slid = False
        self.fitted = None              # (size, slid) the last fit saw
        self.stopped = False

    def slide_done(self):
        self.slid = True

    def step(self, size, waited_ms):
        if self.stopped:
            return "stop"
        self.sizes.append(size)
        if waited_ms >= self.max_ms:
            self.stopped = True
            final = self.fitted is not None and self.fitted[1] == self.slid
            return "stop" if final else "frame"
        if frame_decision(self.sizes, 0, self.ticks, float("inf")) != "frame":
            return "wait"
        key = (tuple(size), self.slid)
        if key == self.fitted:
            return "wait"
        self.fitted = key
        return "frame"


def _doc_uid(doc):
    """The document's Uid (new for every document, unlike its Name: a fresh
    "Atech_Project" reuses a closed one's Name, R102), or None for no /
    a closed document."""
    if doc is None:
        return None
    try:
        return str(doc.Uid)
    except Exception:                                  # noqa: BLE001
        return None


def _open_uids():
    try:
        import FreeCAD
        return {u for u in (_doc_uid(d) for d in FreeCAD.listDocuments().values())
                if u is not None}
    except Exception:                                  # noqa: BLE001
        return set()


def _view_size(dname):
    """(w, h) of the 3D view of document dname, or None."""
    try:
        import FreeCADGui
        gd = FreeCADGui.getDocument(dname)
        w, h = gd.ActiveView.getSize()
        return int(w), int(h)
    except Exception:                                  # noqa: BLE001
        return None


class _DocWatch(object):
    """FreeCAD document observer that refreshes the page when a document is
    closed, created or activated (R103). Holds the page weakly, and defers
    the refresh one event-loop turn: while slotDeletedDocument runs, the
    dying document is still open (and may still be the active one)."""

    def __init__(self, page):
        import weakref
        self._page = weakref.ref(page)

    def _poke(self, closing=None):
        page = self._page()
        if page is None:
            return
        if closing is not None:
            page._closing.add(closing)
        QtCore.QTimer.singleShot(0, page._on_documents_changed)

    def slotDeletedDocument(self, doc):                # noqa: N802
        self._poke(_doc_uid(doc))

    def slotCreatedDocument(self, doc):                # noqa: N802
        self._poke()

    def slotActivateDocument(self, doc):               # noqa: N802
        self._poke()


PAGE_QSS = """
#ModulesPage {{ background: {panel}; }}
#ModulesPage QLabel {{ font-family: {UI}; }}
#MTitle {{ color: {text}; font-size: 13px; font-weight: 600; }}
#MMeta {{ color: {dim}; font-size: 11px; }}
#MSection {{ color: {dim}; font-size: 10px; font-weight: 600; letter-spacing: 1px; }}
#MPortTitle {{ color: {text}; font-size: 15px; font-weight: 600; }}
#MPortSub {{ color: {muted}; font-size: 12px; }}
#MModule {{
    background: {panel}; color: {text}; border: 1px solid {line};
    border-radius: 10px; padding: 8px 10px; text-align: left;
    font-family: {UI}; font-size: 12px;
}}
#MModule:hover {{ background: {hover}; border-color: {line_strong}; }}
#MModule:disabled {{ color: {dim}; }}
#MRow {{
    background: transparent; color: {text}; border: none; border-radius: 8px;
    padding: 6px 8px; text-align: left; font-family: {UI}; font-size: 12px;
}}
#MRow:hover {{ background: {hover}; }}
#MPrimary {{
    background: {btn_bg}; color: {btn_text}; border: none; border-radius: 13px;
    padding: 0 14px; min-height: 26px; max-height: 26px; font-weight: 600;
    font-family: {UI}; font-size: 12px;
}}
#MPrimary:hover {{ background: {btn_bg_hover}; }}
#MGhost {{
    background: {panel}; color: {text}; border: 1px solid {line};
    border-radius: 13px; padding: 0 12px; min-height: 26px; max-height: 26px;
    font-family: {UI}; font-size: 12px;
}}
#MGhost:hover {{ background: {hover}; }}
#MGhost:disabled {{ color: {dim}; }}
#MVerdictPass {{ color: {ok}; font-size: 11px; font-weight: 600; }}
#MVerdictFail {{ color: {fail}; font-size: 11px; font-weight: 600; }}
#MVerdictUnknown {{ color: {warn}; font-size: 11px; font-weight: 600; }}
#MError {{ color: {fail}; font-size: 12px; }}
#MNotice {{ color: {muted}; font-size: 12px; }}
#MWarn {{ color: {warn}; font-size: 12px; font-weight: 600; }}
#MLink {{
    background: transparent; color: {accent}; border: none; padding: 0 4px;
    font-family: {UI}; font-size: 12px; font-weight: 600;
}}
#MLink:hover {{ text-decoration: underline; }}
#MScroll, #MScroll > QWidget > QWidget {{ background: {panel}; border: none; }}
"""


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[AcadAgent modules] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def _report(msg):
    """Unexpected failures: to the Report view, where the page says they are."""
    try:
        import FreeCAD
        FreeCAD.Console.PrintWarning("Atech modules: %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def _remove_observer(watch):
    try:
        import FreeCAD
        FreeCAD.removeDocumentObserver(watch)
    except Exception:                                  # noqa: BLE001
        pass


class LibraryMissing(RuntimeError):
    """projects/ (atech_ports.py, atech_modules.py) is not in this install."""


# ------------------------------------------------------- words for users
# Pure functions, no Qt and no FreeCAD: projects/tests/test_library_and_
# messages.py runs them headless against the library's real exceptions.
MISSING_LIBRARY = ("Atech modules are missing from this installation. "
                   "Reinstall Atech Atelier.")


def display_name(module, specs=None):
    """The library's display name for a module slug; the slug only when the
    library has none (then it is at least not a Python repr)."""
    sp = (specs or {}).get(module) or {}
    return sp.get("display_name") or str(module or "This module")


def _ports_words(ns):
    ns = sorted(int(n) for n in ns)
    if not ns:
        return "those ports"
    if len(ns) == 1:
        return "port %d" % ns[0]
    return "ports %s and %d" % (", ".join(str(n) for n in ns[:-1]), ns[-1])


def describe_error(exc, module=None, port=None, specs=None, action="adding"):
    """One sentence for the user about exc. `module` / `port` are what the
    page was doing when it failed; the exception's own `info` (set by
    atech_ports) wins where it has the facts. Dispatches on class NAME so
    this needs no import of the library it is describing."""
    kinds = {c.__name__ for c in type(exc).__mro__}
    info = getattr(exc, "info", None) or {}
    mod = info.get("module") or module
    name = display_name(mod, specs) if mod else "This module"
    kind = info.get("kind")
    if "LibraryMissing" in kinds or str(exc) == MISSING_LIBRARY:
        return MISSING_LIBRARY
    if "PortOccupied" in kinds:
        ns = info.get("ports") or ([port] if port is not None else [])
        holders = [display_name(h, specs) for h in info.get("holders") or []]
        who = holders[0] if len(set(holders)) == 1 else "another module"
        where = _ports_words(ns).capitalize() if ns else "That port"
        verb = "hold" if len(ns) > 1 else "holds"
        return "%s already %s %s. Remove it first." % (where, verb, who)
    if "PortEmpty" in kinds:
        n = info.get("port", port)
        return ("Port %d is empty, so there is nothing to remove." % n
                if n is not None else "That port is empty.")
    if "UnknownPort" in kinds:
        n = info.get("port", port)
        return ("The board has no port %s." % n if n is not None
                else "The board has no such port.")
    if "PortSpecError" in kinds:
        if kind == "port_miss":
            return ("%s does not line up with port %d (it is off by %.2f mm), "
                    "so it cannot be seated there. Try a neighbouring port."
                    % (name, info.get("port"), info.get("miss_mm", 0.0)))
        if kind == "port_axis":
            return ("%s would need %s, but they face different edges of the "
                    "board. Pick ports in the same column."
                    % (name, _ports_words(info.get("ports") or [])))
        if kind == "port_twice":
            return "The same port was picked twice."
        if kind == "port_count":
            c = info.get("connectors") or 0
            return ("%s has %d connectors, so it needs %d ports side by side."
                    % (name, c, c) if c > 1 else
                    "%s has one connector, so it takes one port." % name)
        if kind == "pair_fails":
            return ("%s plugs into two ports, and with port %d it would not "
                    "seat cleanly next to either free neighbour, so it was "
                    "not added. Try another port."
                    % (name, info.get("port", port)))
        if kind == "no_pair":
            return ("%s plugs into two ports: port %d and a free port next to "
                    "it in the same column. Free a neighbour or pick another "
                    "port." % (name, info.get("port", port)))
        return "%s cannot be seated on the ports picked." % name
    if "NoConnector" in kinds:
        return ("%s has no pin header, so it cannot be seated on a port."
                % name)
    if "KeyError" in kinds:
        key = exc.args[0] if exc.args else mod
        return ("%s is not in the Atech module library."
                % display_name(key, specs) if key else
                "That module is not in the Atech module library.")
    if kind == "no_mesh":
        return ("The 3D model of %s is missing from this installation. "
                "Reinstall Atech Atelier." % name)
    if kinds & {"UndefinedByLibrary", "GeometryMismatch", "SpecError"}:
        return ("The Atech module library in this installation could not be "
                "read. Reinstall Atech Atelier.")
    return ("Something went wrong while %s %s. The details are in the "
            "Report view." % (action, name if mod else "the module"))


# Plain words for the three checks atech_ports.check() runs. Colour key
# is a style token; the verdict strings are atech_ports.PASS/FAIL/CANNOT.
CHECK_WORDS = {
    "seated": {"PASS": "Fully seated", "FAIL": "Not fully seated",
               None: "Can't tell if it is seated"},
    "interference": {"PASS": "Touches nothing", "FAIL": "Collides with %s",
                     None: "Can't tell if it collides"},
    "slide_path": {"PASS": "Slides in freely", "FAIL": "Something is in the "
                   "way as it slides in: %s", None: "Can't tell if the way "
                   "in is clear"},
}
CHECK_ORDER = ("seated", "interference", "slide_path")


# R302: a cabled module is not seated on its port, its cable's plug is; and
# it never slides in. "Fully seated" / "Slides in freely" would be untrue.
CABLED_WORDS = {
    "seated": {"PASS": "Connected by cable", "FAIL": "Cable not connected",
               None: "Can't tell if the cable is connected"},
    "interference": CHECK_WORDS["interference"],
    "slide_path": {"PASS": "On a cable, nothing slides in",
                   "FAIL": "On a cable, nothing slides in",
                   None: "On a cable, nothing slides in"},
}
CABLED_ORDER = ("seated", "interference")
CABLE_REMADE_WHY = ("The board or the module moved after its cable was made. "
                    "Use Remake cable.")


def verdict_words(key, result, name_of=None, cabled=False):
    """(sentence, colour token) for one check result dict. cabled: the
    module is on a cable (AtechJoint "cable"), R302."""
    v = result.get("verdict") if isinstance(result, dict) else result
    words = (CABLED_WORDS if cabled else CHECK_WORDS)[key]
    if v == "PASS":
        return words["PASS"], "ok"
    if v == "FAIL":
        hits = (result.get("hits") if isinstance(result, dict) else None) or {}
        who = []
        for label in sorted(hits):
            # atech_ports.check() names board obstacles "board" and
            # "board:own socket"; anything else is a document label.
            w = ("the board" if label == "board" or label.startswith("board:")
                 else (name_of(label) if name_of else label))
            if w not in who:
                who.append(w)
        text = words["FAIL"]
        if "%s" in text:
            text = text % (" and ".join(who) if who else "something")
        return text, "fail"
    return words[None], "warn"


def fail_why(key, result, name_of=None):
    """The first reason under a FAIL, in a short plain line; None when the
    result is not a FAIL or carries no reason. Numbers come straight from
    atech_ports.check(); nothing is rounded into a nicer story."""
    if not isinstance(result, dict) or result.get("verdict") != "FAIL":
        return None
    if key == "seated" and "make the cable again" in str(result.get("why") or ""):
        return CABLE_REMADE_WHY
    if key == "seated":
        for p in result.get("ports") or []:
            if p.get("why"):
                return "Port %s: %s" % (p.get("port", "?"), p["why"][0])
        return result.get("why")
    hits = result.get("hits") or {}
    if not hits:
        return None
    label = sorted(hits)[0]
    h = hits[label] or {}
    who = ("the board" if label == "board" or label.startswith("board:")
           else (name_of(label) if name_of else label))
    if key == "interference":
        if h.get("module_inside_solid"):
            return "It sits inside %s." % who
        text = "Overlaps %s by up to %.2f mm" % (who, h.get("max_penetration_mm", 0.0))
        if h.get("approx_volume_mm3"):
            text += " (about %g mm3)" % h["approx_volume_mm3"]
        return text + "."
    return ("Meets %s %.1f mm before it is seated."
            % (who, h.get("met_mm_before_seat", 0.0)))


# ------------------------------------------- power, ports, cables (R300+)
#: The module that powers the board (presets.yaml name). R303: every
#: product needs one; Check all says so when the board has none.
POWER_MODULE = "usbc"


def power_warning(modules):
    """The power-rule sentence for a board carrying `modules` (presets.yaml
    names, one per module), or None: no warning on an empty board (there is
    nothing to power yet) or when a USB-C module is among them."""
    mods = [m for m in modules if m]
    if not mods or POWER_MODULE in mods:
        return None
    return ("No USB-C module on the board, so nothing can power it. Add a "
            "USB-C module (it usually goes on port 8).")


EDGE_WORDS = {"left": "slides in from the left", "right":
              "slides in from the right", "top": "slides in from the top",
              "bottom": "slides in from the bottom"}


def port_tooltip(n, edge=None, occupant=None, others=(), cable_mm=None,
                 reserved=None):
    """R304: the plain-text hover line for port n of the board map.
    occupant: display name of the module on it (None = empty); others: the
    other ports a two-port module also takes; cable_mm: the module is on a
    cable of that length (0/None with occupant = seated); reserved: why
    no module can go there. The pin order of a port is not published (OPEN
    in the library), so the line never names pins."""
    head = "Port %d" % n + (" · %s edge" % edge if edge else "")
    if occupant:
        if cable_mm is not None:
            what = "%s on a %d mm cable" % (occupant, round(cable_mm))
        else:
            what = "%s, seated" % occupant
        also = ""
        if others:
            ns = sorted(int(p) for p in others)
            also = " · also on port%s %s" % ("s" if len(ns) > 1 else "",
                                              ", ".join(str(p) for p in ns))
        return "%s · %s%s" % (head, what, also)
    if reserved:
        return "%s · reserved for %s" % (head, reserved)
    return "%s · empty · a module %s" % (head, EDGE_WORDS.get(edge, "slides in"))


def cable_words(lengths_mm):
    """'Connected by cable · 182 mm' for a module's cable lengths (one per
    connector; two cables are summed and counted)."""
    ls = [float(v) for v in lengths_mm or [] if v is not None]
    if not ls:
        return "Connected by cable"
    if len(ls) == 1:
        return "Connected by cable · %d mm" % round(ls[0])
    return "Connected by %d cables · %d mm in all" % (len(ls), round(sum(ls)))


def stale_sentence(n_seated, n_cabled):
    """R301: what the page says when modules no longer match the board, or
    None when everything matches."""
    if not n_seated and not n_cabled:
        return None
    parts = []
    if n_seated:
        parts.append("%d module%s no longer in %s port%s" % (
            n_seated, " is" if n_seated == 1 else "s are",
            "its" if n_seated == 1 else "their", "" if n_seated == 1 else "s"))
    if n_cabled:
        parts.append("%d cable%s no longer reach%s %s module%s" % (
            n_cabled, "" if n_cabled == 1 else "s", "es" if n_cabled == 1 else "",
            "its" if n_cabled == 1 else "their", "" if n_cabled == 1 else "s"))
    lead = ("The board has moved" if n_seated else
            "A cabled module or the board has moved")
    return "%s: %s. Re-seat all puts them back." % (lead, " and ".join(parts))


def move_action(moving_ports, target, occ_at_target=None):
    """R300: what clicking port `target` does while a module on
    `moving_ports` is being moved. occ_at_target: (Name, its ports) of the
    module on target, or None. Returns ("move", target), ("swap", Name),
    ("cancel", None) for its own port, or ("refuse", sentence)."""
    moving_ports = [int(p) for p in moving_ports]
    if target in moving_ports:
        return "cancel", None
    if occ_at_target is None:
        return "move", int(target)
    name, ports_ = occ_at_target
    if len(ports_) != len(moving_ports):
        return ("refuse", "Only modules that take the same number of ports can "
                "swap. Pick an empty port, or move the other module first.")
    return "swap", name


def cable_icon(color, size=16):
    """A small ribbon-cable icon (plug, curved ribbon, socket) drawn in
    `color`, for rows of cabled modules (R302). No image file."""
    pm = QtGui.QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    c = QtGui.QColor(color)
    p.setPen(QtGui.QPen(c, 1.6, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    path = QtGui.QPainterPath(QtCore.QPointF(3.5, size * 0.72))
    path.cubicTo(QtCore.QPointF(size * 0.45, size * 0.72),
                 QtCore.QPointF(size * 0.55, size * 0.28),
                 QtCore.QPointF(size - 3.5, size * 0.28))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawPath(path)
    p.setBrush(c)
    p.setPen(QtCore.Qt.NoPen)
    p.drawRoundedRect(QtCore.QRectF(0.5, size * 0.72 - 2.5, 4, 5), 1, 1)
    p.drawRoundedRect(QtCore.QRectF(size - 4.5, size * 0.28 - 2.5, 4, 5), 1, 1)
    p.end()
    return QtGui.QIcon(pm)


def check_all_block(label, where, body, muted):
    """One module's block in the "Check all" list (R160): its own heading
    (name, then its ports) and a gap below it, so modules never run
    together and no port heading claims them."""
    head = "<b>%s</b>" % html.escape(label)
    if where:
        head += " <span style='color:%s'>· %s</span>" % (muted, html.escape(where))
    return ("<p style='margin-top:0px; margin-bottom:%dpx'>%s<br>%s</p>"
            % (CHECK_ALL_GAP_PX, head, body))


CHECK_ALL_GAP_PX = 10


#: projects.FREE_ROLE, repeated so the page can be imported without FreeCAD
FREE_ROLE = "part"


def free_part_tooltip(sp, shown):
    """The tooltip of a free-part button: its description, and for a part
    the user imported, that it is theirs and what they said about wiring."""
    text = (sp or {}).get("description") or shown
    if (sp or {}).get("user"):
        text += "\nYour part (not an Atech module; no Atech firmware)."
        e = sp.get("electrical") or {}
        bits = [str(e[k]) for k in ("interface", "connectors", "wiring") if e.get(k)]
        if e.get("voltage_v") is not None:
            bits.insert(1 if bits else 0, "%sV" % e["voltage_v"])
        if bits:
            text += "\nWiring: " + "; ".join(bits)
        text += "\nRight-click to remove it from your parts."
    return text


def _lib():
    """(atech_ports, atech_modules) from this installation's projects/
    folder (installed bundle or dev checkout; projects._builder_dir).
    Raises LibraryMissing when this installation has none."""
    from . import projects
    d = projects._builder_dir()
    if d is None:
        raise LibraryMissing(MISSING_LIBRARY)
    if d not in sys.path:
        sys.path.insert(0, d)
    import atech_modules
    import atech_ports
    return atech_ports, atech_modules


FITTED_AFTER = "fitted_after"
INTENT_FILE = "intent.json"


def _fitted_value(data):
    """intent.json's "fitted_after" as a list of names ([] when missing or
    malformed - never a guess)."""
    v = data.get(FITTED_AFTER) if isinstance(data, dict) else None
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)):
        return []
    return [str(n) for n in v if isinstance(n, str) and n.strip()]


def _intent_of_script(code):
    """The INTENT = {...} literal of a build script (an example forked as
    model.py carries its intent.json there), or None."""
    import ast
    try:
        tree = ast.parse(code or "")
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "INTENT" for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except (ValueError, SyntaxError, TypeError):
                return None
    return None


def fitted_after(doc):
    """R517: the agent-built parts doc's design fits AFTER the modules go in
    (intent.json "fitted_after": a closed case's end caps, a lid), as
    labels. atech_ports.check() judges the slide paths without them, as the
    agent's own ./check and Studio's build gate do - without this, every
    module of a closed product showed "Something is in the way as it slides
    in" on this page although the build passed.

    Read from, in order: the intent.json of the document's chat (its
    workspace, through the sessions record of its project id), the INTENT
    literal of the newest agent build script in the document, the
    intent.json saved in the project file. Only names of agent-built parts
    still in the document count; [] when nothing declares any."""
    if doc is None:
        return []
    parts = {}
    newest, newest_n = None, -1
    try:
        for o in doc.Objects:
            if getattr(o, "AtechAgentBuilt", False) and not getattr(o, "AtechRole", None) \
                    and not getattr(o, "AtechCableModule", None):
                parts[o.Name] = o.Label
                parts.setdefault(o.Label, o.Label)
                n = int(getattr(o, "AtechAgentBuild", 0) or 0)
                if n > newest_n and getattr(o, "AtechAgentScript", ""):
                    newest, newest_n = o, n
    except Exception:                                  # noqa: BLE001
        return []
    if not parts:
        return []
    names = None
    try:
        from . import projects_store as ps
        rec = ps.load_sessions().get(ps.doc_key(doc) or "")
        ws = rec.get("ws") if isinstance(rec, dict) else None
        if isinstance(ws, str) and os.path.isfile(os.path.join(ws, INTENT_FILE)):
            with open(os.path.join(ws, INTENT_FILE), encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and FITTED_AFTER in data:
                names = _fitted_value(data)
    except Exception as exc:                           # noqa: BLE001
        _log("fitted_after (chat): %r" % (exc,))
    if names is None and newest is not None:
        data = _intent_of_script(getattr(newest, "AtechAgentScript", ""))
        if isinstance(data, dict) and FITTED_AFTER in data:
            names = _fitted_value(data)
    if names is None:
        try:
            from . import projects_store as ps
            bundle = ps.read_doc_chat(doc)
            raw = ((bundle or {}).get("files") or {}).get(INTENT_FILE)
            if raw:
                data = json.loads(raw.decode("utf-8"))
                if isinstance(data, dict) and FITTED_AFTER in data:
                    names = _fitted_value(data)
        except Exception as exc:                       # noqa: BLE001
            _log("fitted_after (file): %r" % (exc,))
    out = []
    for n in names or ():
        lab = parts.get(n)
        if lab and lab not in out:
            out.append(lab)
    return out


#: what marks an object as the agent build's (build._ensure_props)
AGENT_PROPS = (("App::PropertyBool", "AtechAgentBuilt"),
               ("App::PropertyString", "AtechAgentScript"),
               ("App::PropertyString", "AtechAgentBuildId"),
               ("App::PropertyInteger", "AtechAgentBuild"))


def cable_owners(doc, mod):
    """{port: (label, {prop: value})} of the agent build marks on mod's
    cables now (R512), for keep_cable_owners after a remake."""
    out = {}
    try:
        ports_mod, _ = _lib()
        for c in ports_mod.cables_of(doc, mod):
            if not getattr(c, "AtechAgentBuilt", False):
                continue
            out[int(getattr(c, "AtechCablePort", 0) or 0)] = (
                c.Label, {p: getattr(c, p) for _t, p in AGENT_PROPS
                          if p in c.PropertiesList})
    except Exception as exc:                           # noqa: BLE001
        _log("cable owners: %r" % (exc,))
    return out


def keep_cable_owners(doc, mod, owners):
    """R512: a remade cable of an agent-built module is still the build's:
    the old cable's marks and label go onto the new one on the same port.
    Without this the next build kept the remade cable as the USER's (two
    cables on one module, the old one stale, overlapping the new one).
    Returns how many cables were marked."""
    if not owners:
        return 0
    n = 0
    try:
        ports_mod, _ = _lib()
        for c in ports_mod.cables_of(doc, mod):
            rec = owners.get(int(getattr(c, "AtechCablePort", 0) or 0))
            if rec is None:
                continue
            label, props = rec
            for typ, p in AGENT_PROPS:
                if p in props:
                    if p not in c.PropertiesList:
                        c.addProperty(typ, p, "Atech", "")
                    setattr(c, p, props[p])
            if label:
                c.Label = label
            n += 1
    except Exception as exc:                           # noqa: BLE001
        _log("keep cable owners: %r" % (exc,))
    return n


def fitted_note(labels):
    """R517: the line under a check that used the design's fitted-after parts."""
    shown = ", ".join(labels[:4]) + (" and %d more" % (len(labels) - 4)
                                     if len(labels) > 4 else "")
    return ("Slide paths checked before %s go on (the design fits %s after "
            "the modules)." % (shown, "it" if len(labels) == 1 else "them"))


def check_doc(ports_mod, doc, only=None):
    """atech_ports.check() on doc as the agent's build judged it: with the
    design's fitted-after parts (R517) when it declares any and the library
    takes them. Returns (result, fitted labels)."""
    fa = fitted_after(doc)
    kw = {}
    if fa:
        import inspect
        try:
            if FITTED_AFTER in inspect.signature(ports_mod.check).parameters:
                kw[FITTED_AFTER] = fa
        except (TypeError, ValueError):
            pass
    return ports_mod.check(doc, only=only, **kw), list(kw.get(FITTED_AFTER) or ())


def _doc(create=True):
    import FreeCAD
    doc = FreeCAD.ActiveDocument
    if doc is None and create:
        doc = FreeCAD.newDocument("Atech_Project")
    return doc


# ------------------------------------------------------------- board map
# Studio's board (studio.atech.dev): the same plan-view pictures, the same
# cells. SPRITE_DIR holds studio's board_sprites (see its SOURCE.md); CELLS is
# studio's board_geometry("14port_board") for the 14-port board: each port's
# cell centre [x, z] in mm from the board centre (x right, z toward the
# bottom edge, port 1 top-left) and the edge its module faces. A module is
# drawn with its sprite's origin (its connector) on the cell centre, turned
# so the sprite's up (the module's outer face) points outward; a two-port
# module sits on the mean of its cells and faces its first port's edge.
SPRITE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "board_sprites")
SPRITE_PX_PER_MM = 8.0
BOARD_SPRITE = "frame-2"
CELL_MM = (19.5, 20.0)                  # a port cell: across, along the column
CELLS = {
    1: ((-19.5, -49.99), (-1, 0)), 2: ((-19.5, -30.0), (-1, 0)),
    3: ((-19.5, -10.0), (-1, 0)), 4: ((-19.5, 10.0), (-1, 0)),
    5: ((-19.5, 29.99), (-1, 0)), 6: ((-19.5, 49.99), (-1, 0)),
    7: ((0.0, -49.99), (0, -1)), 8: ((0.0, 49.99), (0, 1)),
    9: ((19.5, -49.99), (1, 0)), 10: ((19.5, -30.0), (1, 0)),
    11: ((19.5, -10.0), (1, 0)), 12: ((19.5, 10.0), (1, 0)),
    13: ((19.5, 29.99), (1, 0)), 14: ((19.5, 49.99), (1, 0)),
}
#: presets.yaml module name -> studio sprite (studio hw_models.MODULE_SLUG).
SPRITE_FOR = {
    "button": "button", "light": "led-grid", "usbc": "usb-c",
    "screen": "screen", "speaker": "speaker", "dc_motor": "dc-motor",
    "orientation": "orientation-sensor", "temp_humidity": "temp-sensor",
    "distance_sensor": "distance-sensor", "knob": "knob",
    "microphone": "microphone",
}
_SPRITES = {}


def _manifest():
    if "_manifest" not in _SPRITES:
        try:
            with open(os.path.join(SPRITE_DIR, "MANIFEST.json"), encoding="utf-8") as fh:
                _SPRITES["_manifest"] = json.load(fh).get("sprites", {})
        except (OSError, ValueError):
            _SPRITES["_manifest"] = {}
    return _SPRITES["_manifest"]


def sprite(name):
    """(QPixmap, (origin_x, origin_y) px) for a studio sprite, or None."""
    if name not in _SPRITES:
        rec = _manifest().get(name) or {}
        pm = QtGui.QPixmap(os.path.join(SPRITE_DIR, rec.get("file") or (name + ".png")))
        _SPRITES[name] = None if pm.isNull() else (
            pm, tuple(rec.get("origin_px") or (pm.width() / 2.0, pm.height() / 2.0)))
    return _SPRITES[name]


def module_pose(ports):
    """(centre [x, z] mm from the board centre, outward [x, z]) of a module
    seated on `ports` (studio's rule), or None when no port is a cell."""
    cells = [CELLS[n] for n in ports if n in CELLS]
    if not cells:
        return None
    x = sum(c[0][0] for c in cells) / len(cells)
    z = sum(c[0][1] for c in cells) / len(cells)
    return (x, z), cells[0][1]


def outward_angle(outward):
    """Degrees (Qt, clockwise) turning a sprite's up (-z) to `outward`."""
    return math.degrees(math.atan2(outward[0], -outward[1]))


class BoardMap(QtWidgets.QWidget):
    """The Atech board as studio.atech.dev draws it: the board's own plan
    view, each placed module's picture seated in its port, port numbers from
    the artwork. Click a port to pick it. Emits the picked port."""

    picked = QtCore.Signal(int)

    BOARD_X, BOARD_Z = 60.0, 120.0      # board extents (mm)
    #: Room around the board for modules that reach past its edge (the DC
    #: motor's 28.7 mm is the longest; studio's sprites, measured).
    MARGIN_X, MARGIN_Z = 30.0, 22.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(360)
        self.setMouseTracking(True)
        self.setAccessibleName("Atech board map")
        self.setAccessibleDescription("The 14 ports of the board. Click a port "
                                      "to pick it.")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.ports = {}                 # n -> Port
        self.occupied = {}              # n -> short label
        #: object name -> (module, (ports...)[, joint]); joint "cable" = R302
        self.modules = {}
        self.tips = {}                  # n -> hover line (port_tooltip, R304)
        self.moving = ()                # ports of the module being moved (R300)
        self.selected = None
        self.hover = None
        self._rects = {}

    def sizeHint(self):                                 # noqa: N802
        return QtCore.QSize(320, 400)

    def set_state(self, ports, occupied, selected, modules=None, tips=None,
                  moving=()):
        self.ports, self.occupied, self.selected = ports, occupied, selected
        self.modules = dict(modules or {})
        self.tips = dict(tips or {})
        self.moving = tuple(moving or ())
        self.update()

    def tip_for(self, n):
        """The hover line for port n (R304): the page's port_tooltip, or the
        short form when the page gave none."""
        if n is None:
            return ""
        if n in self.tips:
            return self.tips[n]
        return "Port %d%s" % (n, (" · " + self.occupied[n]) if n in self.occupied
                              else " · empty")

    def _draw_cable_plug(self, p, mports, module, t):
        """R302: a cabled module is NOT in its port; only its cable's plug
        is. Each of its ports shows a plug and a ribbon leaving the board,
        dashed, never the module's picture."""
        f = QtGui.QFont(style.FONT_UI)
        f.setPixelSize(9)
        f.setBold(True)
        for n in mports:
            r = self._cell(n)
            if r is None:
                continue
            (_x, _z), out = CELLS[n]
            c = r.center()
            s = self._scale()
            plug = QtCore.QRectF(-3.0 * s, -2.2 * s, 6.0 * s, 4.4 * s)
            p.save()
            p.translate(c)
            p.rotate(outward_angle(out))
            p.setPen(QtGui.QPen(QtGui.QColor(t["line_strong"]), 1))
            p.setBrush(QtGui.QColor("#d9d9d4"))
            p.drawRoundedRect(plug, 1.5, 1.5)
            pen = QtGui.QPen(QtGui.QColor("#d9d9d4"), max(2.0, 2.2 * s),
                             QtCore.Qt.DashLine, QtCore.Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QtCore.QPointF(0, -2.2 * s), QtCore.QPointF(0, -14.0 * s))
            p.restore()
        cells = [self._cell(n) for n in mports if self._cell(n) is not None]
        if cells:
            p.setFont(f)
            p.setPen(QtGui.QColor("#ffffff"))
            r0 = cells[0]
            p.drawText(r0.adjusted(0, r0.height() * 0.45, 0, 0),
                       QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop, module[:8])

    def _scale(self):
        """px per mm, fitting the board and its margins."""
        return max(0.5, min(self.width() / (self.BOARD_X + 2 * self.MARGIN_X),
                            self.height() / (self.BOARD_Z + 2 * self.MARGIN_Z)))

    def _centre(self):
        return QtCore.QPointF(self.width() / 2.0, self.height() / 2.0)

    def _px(self, x, z):
        s, c = self._scale(), self._centre()
        return QtCore.QPointF(c.x() + x * s, c.y() + z * s)

    def _cell(self, n):
        if n not in CELLS:
            return None
        (x, z), _o = CELLS[n]
        s = self._scale()
        w, h = CELL_MM[0] * s, CELL_MM[1] * s
        c = self._px(x, z)
        return QtCore.QRectF(c.x() - w / 2.0, c.y() - h / 2.0, w, h)

    def _draw_sprite(self, p, name, centre, angle):
        sp = sprite(name)
        if sp is None:
            return False
        pm, (ox, oy) = sp
        k = self._scale() / SPRITE_PX_PER_MM
        p.save()
        p.translate(centre)
        p.rotate(angle)
        p.scale(k, k)
        p.drawPixmap(QtCore.QPointF(-ox, -oy), pm)
        p.restore()
        return True

    def paintEvent(self, _ev):                         # noqa: N802
        t = style.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        s = self._scale()
        board = QtCore.QRectF(self._px(-self.BOARD_X / 2, -self.BOARD_Z / 2),
                              QtCore.QSizeF(self.BOARD_X * s, self.BOARD_Z * s))
        # A soft shadow under the board, as the 3D view lights it.
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 28))
        p.drawRoundedRect(board.translated(0, 3), 4 * s, 4 * s)
        if not self._draw_sprite(p, BOARD_SPRITE, self._centre(), 0.0):
            p.setBrush(QtGui.QColor("#3a3a3a"))
            p.drawRoundedRect(board, 4 * s, 4 * s)
        # Modules, each once (a two-port module spans its cells).
        f = QtGui.QFont(style.FONT_UI)
        f.setPixelSize(10)
        f.setBold(True)
        for _name, rec in sorted(self.modules.items()):
            module, mports = rec[0], rec[1]
            if len(rec) > 2 and rec[2] == "cable":
                self._draw_cable_plug(p, mports, module, t)
                continue
            pose = module_pose(mports)
            if pose is None:
                continue
            (x, z), out = pose
            c = self._px(x, z)
            if not self._draw_sprite(p, SPRITE_FOR.get(module, ""), c, outward_angle(out)):
                # No picture (a module studio has no model for): its cells,
                # labelled, so it is never silently missing.
                rect = QtCore.QRectF()
                for n in mports:
                    r = self._cell(n)
                    if r is not None:
                        rect = rect.united(r) if not rect.isNull() else r
                p.setPen(QtGui.QPen(QtGui.QColor(t["line_strong"]), 1))
                p.setBrush(QtGui.QColor("#94a3b8"))
                p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 3, 3)
                p.setFont(f)
                p.setPen(QtGui.QColor("#111827"))
                p.drawText(rect, QtCore.Qt.AlignCenter, module[:6])
        # Ports: the artwork carries the numbers; hover and the pick are rings.
        self._rects = {}
        for n in sorted(self.ports):
            r = self._cell(n)
            if r is None:
                continue
            self._rects[n] = r
            sel, hov = n == self.selected, n == self.hover
            if n in self.moving:
                # R300: the module being moved, dashed in the accent colour
                p.setBrush(QtCore.Qt.NoBrush)
                p.setPen(QtGui.QPen(QtGui.QColor(t["accent"]), 2.0,
                                    QtCore.Qt.DashLine))
                p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 4, 4)
            if not (sel or hov):
                continue
            ring = r.adjusted(2, 2, -2, -2)
            p.setBrush(QtGui.QColor(255, 255, 255, 40 if hov else 0))
            p.setPen(QtGui.QPen(QtGui.QColor(t["accent"] if sel else "#ffffff"),
                                2.5 if sel else 1.5))
            p.drawRoundedRect(ring, 4, 4)
        p.end()

    def _hit(self, pos):
        for n, r in self._rects.items():
            if r.adjusted(-4, -4, 4, 4).contains(pos):
                return n
        return None

    def mouseMoveEvent(self, ev):                      # noqa: N802
        h = self._hit(ev.position())
        if h != self.hover:
            self.hover = h
            # Tooltips auto-detect rich text: escape the module name.
            tip = self.tip_for(h)
            self.setToolTip(html.escape(tip) if h else "")
            if h:
                self.setAccessibleDescription(tip)
            self.setCursor(QtCore.Qt.PointingHandCursor if h else
                           QtCore.Qt.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, ev):                   # noqa: N802
        h = self._hit(ev.position())
        if h is not None:
            self.picked.emit(h)

    def keyPressEvent(self, ev):                       # noqa: N802
        """Keyboard: arrows step through the ports, Return or Space picks
        the one under the ring (its hover line is the accessible
        description)."""
        ns = sorted(self.ports) or sorted(CELLS)
        k = ev.key()
        cur = self.hover if self.hover in ns else (
            self.selected if self.selected in ns else None)
        if k in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Right,
                 QtCore.Qt.Key_Up, QtCore.Qt.Key_Left):
            step = 1 if k in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Right) else -1
            i = ns.index(cur) + step if cur is not None else 0
            self.hover = ns[i % len(ns)]
            tip = self.tip_for(self.hover)
            self.setToolTip(html.escape(tip))
            self.setAccessibleDescription(tip)
            self.update()
            return
        if k in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter,
                 QtCore.Qt.Key_Space) and cur is not None:
            self.picked.emit(cur)
            return
        super().keyPressEvent(ev)


# ------------------------------------------------------------------ page
#: Where "Connect by cable" puts a module: this far (mm) past the port's
#: mouth, plus half the module's own size, so it is clear of the board.
CABLED_CLEAR_MM = 40.0


def _axis_word(v):
    """'+X' ... '-Z' of the world axis nearest the vector v."""
    k = max(range(3), key=lambda i: abs(v[i]))
    return ("+" if v[k] > 0 else "-") + "XYZ"[k]


def cabled_placement(ports_mod, name, port, board_placement):
    """World placement of a module connected by cable to `port`: outside
    the board past the port's mouth (CABLED_CLEAR_MM + half the module's
    measured size), at the board's height, working face up as on the board
    and its pins toward the port, so the ribbon runs straight in."""
    import FreeCAD
    v = FreeCAD.Vector
    d = v(*port.insert_dir)
    # row_centre, mouth and pcb_y are the port's coordinates along its own
    # orthonormal axes (row, insertion, up), so this is the mouth's centre.
    mouth = (v(*port.row_dir) * port.row_centre + d * port.mouth
             + v(*port.up) * port.pcb_y)
    feat = ports_mod.measure_module(name)
    import numpy as np
    P = np.concatenate([feat["body_tris"], feat["pin_tris"]]).reshape(-1, 3)
    half = float((P.max(0) - P.min(0)).max()) / 2.0
    at_board = mouth - d * (CABLED_CLEAR_MM + half)
    at = board_placement.multVec(at_board)
    rot = board_placement.Rotation
    up_w = rot.multVec(v(0, 1, 0))
    d_w = rot.multVec(d)
    return ports_mod.module_placement(name, (at.x, at.y, at.z),
                                      face=_axis_word(up_w), cable=_axis_word(d_w))


class ModulesPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModulesPage")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._ports = {}
        self._specs = {}
        self._seatable = {}             # module -> connector count (measured)
        self._reserved = {}             # port -> reason (atech_ports.RESERVED)
        self._selected = None
        self._anim = None
        self._error = None
        self._unavailable = None        # sentence while the library is unusable

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setObjectName("MScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        inner = QtWidgets.QWidget()
        scroll.setWidget(inner)
        lay = QtWidgets.QVBoxLayout(inner)
        lay.setContentsMargins(16, 6, 16, 16)
        lay.setSpacing(8)

        head = QtWidgets.QHBoxLayout()
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(1)
        self.title = QtWidgets.QLabel("Atech board")
        self.title.setObjectName("MTitle")
        self.meta = QtWidgets.QLabel("")
        self.meta.setObjectName("MMeta")
        self.meta.setTextFormat(QtCore.Qt.PlainText)
        col.addWidget(self.title)
        col.addWidget(self.meta)
        head.addLayout(col, 1)
        self.btn_check = QtWidgets.QPushButton("Check all")
        self.btn_check.setObjectName("MGhost")
        self.btn_check.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_check.clicked.connect(self._check_all)
        # R206: no module is known to be seated until the first refresh
        # (after _load), so it starts disabled rather than Qt's enabled.
        self.btn_check.setEnabled(False)
        head.addWidget(self.btn_check)
        lay.addLayout(head)

        # R301: the board moved (or a cabled module did) and modules no
        # longer match it: say so, and offer to put every one back.
        self.stale_row = QtWidgets.QWidget()
        self.stale_row.setObjectName("MStale")
        sl = QtWidgets.QVBoxLayout(self.stale_row)
        sl.setContentsMargins(0, 2, 0, 4)
        sl.setSpacing(4)
        self.stale_text = QtWidgets.QLabel("")
        self.stale_text.setObjectName("MWarn")
        self.stale_text.setWordWrap(True)
        self.stale_text.setTextFormat(QtCore.Qt.PlainText)
        sl.addWidget(self.stale_text)
        srow = QtWidgets.QHBoxLayout()
        self.btn_reseat = QtWidgets.QPushButton("Re-seat all")
        self.btn_reseat.setObjectName("MPrimary")
        self.btn_reseat.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_reseat.setAccessibleName("Re-seat all modules")
        self.btn_reseat.setToolTip("Seat every module on its port where the board "
                                   "is now, and remake cables that no longer reach")
        self.btn_reseat.clicked.connect(self._reseat_all)
        srow.addWidget(self.btn_reseat)
        srow.addStretch(1)
        sl.addLayout(srow)
        self.stale_row.hide()
        lay.addWidget(self.stale_row)
        self._stale = {"seated": [], "cabled": [], "unknown": {}}

        self.map = BoardMap()
        self.map.picked.connect(self.pick)
        lay.addWidget(self.map)

        self.on_label = QtWidgets.QLabel("ON THE BOARD")
        self.on_label.setObjectName("MSection")
        # Hidden until a module is on the board (_sync_list): shown by
        # default it held a row above "Pick a port" on the empty board
        # until the first refresh, so the heading's y depended on state (R207).
        self.on_label.hide()
        lay.addWidget(self.on_label)
        self.on_list = QtWidgets.QVBoxLayout()
        self.on_list.setSpacing(2)
        lay.addLayout(self.on_list)
        self._on_rows = []

        # "Check all" results: every module on the board, each under its own
        # name and ports, in their own section - never under the selected
        # port's heading, which is about one port only (R160).
        self.all_label = QtWidgets.QLabel("CHECK ALL")
        self.all_label.setObjectName("MSection")
        self.all_label.hide()
        lay.addWidget(self.all_label)
        self.all_verdicts = QtWidgets.QLabel("")
        self.all_verdicts.setObjectName("MAllVerdicts")
        self.all_verdicts.setWordWrap(True)
        self.all_verdicts.setTextFormat(QtCore.Qt.RichText)
        self.all_verdicts.hide()
        lay.addWidget(self.all_verdicts)
        lay.addSpacing(8)

        self.port_title = QtWidgets.QLabel("Pick a port")
        self.port_title.setObjectName("MPortTitle")
        self.port_sub = QtWidgets.QLabel(
            "Click a numbered slot on the board to add or remove a module.")
        self.port_sub.setObjectName("MPortSub")
        self.port_sub.setWordWrap(True)
        # Module names are data, not markup (QLabel auto-detects rich text).
        self.port_title.setTextFormat(QtCore.Qt.PlainText)
        self.port_sub.setTextFormat(QtCore.Qt.PlainText)
        lay.addWidget(self.port_title)
        lay.addWidget(self.port_sub)

        self.err = QtWidgets.QLabel("")
        self.err.setObjectName("MError")
        self.err.setWordWrap(True)
        self.err.setTextFormat(QtCore.Qt.PlainText)
        self.err.hide()
        lay.addWidget(self.err)

        self.notice = QtWidgets.QLabel("")
        self.notice.setObjectName("MNotice")
        self.notice.setWordWrap(True)
        self.notice.setTextFormat(QtCore.Qt.PlainText)
        self.notice.hide()
        lay.addWidget(self.notice)

        # "Removed <name> · Undo" — Remove acts at once, so it can be taken
        # back from the same place (the removal is one undo transaction).
        self.undo_row = QtWidgets.QWidget()
        ul = QtWidgets.QHBoxLayout(self.undo_row)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.setSpacing(4)
        self.undo_text = QtWidgets.QLabel("")
        self.undo_text.setObjectName("MPortSub")
        self.undo_text.setTextFormat(QtCore.Qt.PlainText)
        self.btn_undo = QtWidgets.QPushButton("Undo")
        self.btn_undo.setObjectName("MLink")
        self.btn_undo.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_undo.clicked.connect(self._undo_remove)
        ul.addWidget(self.undo_text)
        ul.addWidget(self.btn_undo)
        ul.addStretch(1)
        self.undo_row.hide()
        lay.addWidget(self.undo_row)
        self._undo = None               # (doc, doc.Name, transaction, name)

        self.verdicts = QtWidgets.QLabel("")
        self.verdicts.setWordWrap(True)
        self.verdicts.setTextFormat(QtCore.Qt.RichText)
        self.verdicts.hide()
        lay.addWidget(self.verdicts)

        self.occ_row = QtWidgets.QWidget()
        ol = QtWidgets.QHBoxLayout(self.occ_row)
        ol.setContentsMargins(0, 4, 0, 4)
        self.btn_remove = QtWidgets.QPushButton("Remove")
        # Secondary, not primary: removing is not the page's main action.
        self.btn_remove.setObjectName("MGhost")
        self.btn_remove.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_remove.setAccessibleName("Remove this module")
        ol.addWidget(self.btn_remove)
        # R300: move to another port, or swap with the module there
        self.btn_move = QtWidgets.QPushButton("Move or swap")
        self.btn_move.setObjectName("MGhost")
        self.btn_move.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_move.setAccessibleName("Move this module to another port")
        self.btn_move.setToolTip("Then pick an empty port to move it there, or a "
                                 "port with another module to swap the two")
        self.btn_move.clicked.connect(self._start_move)
        ol.addWidget(self.btn_move)
        # R302: a cable made for another board or module placement
        self.btn_recable = QtWidgets.QPushButton("Remake cable")
        self.btn_recable.setObjectName("MGhost")
        self.btn_recable.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_recable.setAccessibleName("Remake this module's cable")
        self.btn_recable.setToolTip("Make the cable again for the board and the "
                                    "module where they are now")
        self.btn_recable.clicked.connect(self._remake_cable)
        self.btn_recable.hide()
        ol.addWidget(self.btn_recable)
        ol.addStretch(1)
        self.occ_row.hide()
        lay.addWidget(self.occ_row)

        # R300: while a module is being moved: what to do, and Cancel
        self.move_row = QtWidgets.QWidget()
        ml = QtWidgets.QHBoxLayout(self.move_row)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(4)
        self.move_text = QtWidgets.QLabel("")
        self.move_text.setObjectName("MPortSub")
        self.move_text.setWordWrap(True)
        self.move_text.setTextFormat(QtCore.Qt.PlainText)
        self.btn_move_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_move_cancel.setObjectName("MLink")
        self.btn_move_cancel.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_move_cancel.setAccessibleName("Cancel moving")
        self.btn_move_cancel.clicked.connect(self._cancel_move)
        ml.addWidget(self.move_text, 1)
        ml.addWidget(self.btn_move_cancel)
        self.move_row.hide()
        lay.addWidget(self.move_row)
        self._moving = None             # (doc Uid, object Name) being moved

        self.list_label = QtWidgets.QLabel("ADD A MODULE")
        self.list_label.setObjectName("MSection")
        self.list_label.hide()
        lay.addWidget(self.list_label)
        # Off the board: the module goes clear of the board beyond the port
        # and a ribbon cable wires it to the port (atech_ports.cable).
        self.by_cable = QtWidgets.QCheckBox("Connect by cable, off the board")
        self.by_cable.setObjectName("MPortSub")
        self.by_cable.setAccessibleName("Connect the module by cable, off the board")
        self.by_cable.setToolTip("The module is placed beside the board, past this "
                                 "port, with a ribbon cable to the port. Move it "
                                 "where the design needs it, then Remake cable.")
        self.by_cable.hide()
        lay.addWidget(self.by_cable)
        self.grid = QtWidgets.QGridLayout()
        self.grid.setSpacing(6)
        lay.addLayout(self.grid)
        self._module_btns = []

        # R305: library parts with no pin header (the knob) or no port at
        # all (N20 wheel, NEMA 17 stepper): placed by hand beside the board.
        lay.addSpacing(6)
        self.free_label = QtWidgets.QLabel("PARTS WITHOUT A PORT")
        self.free_label.setObjectName("MSection")
        self.free_label.hide()
        lay.addWidget(self.free_label)
        self.free_sub = QtWidgets.QLabel(
            "These plug into no port. They are placed beside the board; move "
            "them where the design needs them.")
        self.free_sub.setObjectName("MPortSub")
        self.free_sub.setWordWrap(True)
        self.free_sub.hide()
        lay.addWidget(self.free_sub)
        self.free_grid = QtWidgets.QGridLayout()
        self.free_grid.setSpacing(6)
        lay.addLayout(self.free_grid)
        self.free_list = QtWidgets.QVBoxLayout()
        self.free_list.setSpacing(2)
        lay.addLayout(self.free_list)
        # Parts that are not Atech modules (user_parts.py): a board, a
        # battery, a motor from another maker, imported from STEP or STL.
        self.import_btn = QtWidgets.QPushButton("Import part…")
        self.import_btn.setObjectName("MLink")
        self.import_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.import_btn.setAccessibleName("Import a part that is not an Atech module")
        self.import_btn.setToolTip(
            "Add your own part from a STEP or STL file: an Arduino, a battery, "
            "a servo. Its size is measured; the agent designs around it.")
        self.import_btn.clicked.connect(lambda _=False: self._import_part())
        self.import_btn.hide()
        lay.addWidget(self.import_btn, 0, QtCore.Qt.AlignLeft)
        self._free_btns = []
        self._free_rows = []
        self._free_names = []
        lay.addStretch(1)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.refresh)
        # Keyed by document Uid, never by Name: a fresh "Atech_Project"
        # reuses a closed one's Name (R102).
        self._framed = set()            # doc Uids whose first frame started
        self._plans = {}                # doc Uid -> FirstFrame still polling
        self._verdict_uid = None        # doc Uid the verdicts shown are about
        self._last_check = None         # (doc, Name, only, result) on screen (R175)
        self._fitted = []               # R517: the fitted-after parts the last check used
        self._closing = set()           # doc Uids being closed right now
        self._loaded = False
        self._watch = None
        try:
            import FreeCAD
            self._watch = _DocWatch(self)
            FreeCAD.addDocumentObserver(self._watch)
            self.destroyed.connect(
                lambda _=None, w=self._watch: _remove_observer(w))
        except Exception as exc:                       # noqa: BLE001
            _log("document observer: %r" % (exc,))

    def showEvent(self, ev):                           # noqa: N802
        # Measuring the board (GLB + STL) costs ~0.75 s; pay it only when
        # the page is first opened, not at every app start (review finding).
        super().showEvent(ev)
        if not self._loaded:
            self._loaded = True
            QtCore.QTimer.singleShot(0, self._load)
        else:
            # the document may have closed while the page was hidden (R103)
            self.refresh()
        self._timer.start(1500)

    def hideEvent(self, ev):                           # noqa: N802
        super().hideEvent(ev)
        self._timer.stop()

    # ------------------------------------------------------------ data
    def _load(self):
        try:
            ports_mod, modules_mod = _lib()
            self._ports = ports_mod.ports()
            self._specs = {n: modules_mod.spec(n)
                           for n in modules_mod.modules_of("module")}
            # Offer only modules that can be seated: measured ONCE here
            # (a module whose mesh has no pin header, e.g. the knob, would
            # only ever fail). R65.
            self._seatable = ports_mod.seatable(sorted(self._specs))
            self._reserved = dict(getattr(ports_mod, "RESERVED", {}) or {})
            # R305: parts that plug into no port, placed by hand
            from . import projects
            self._free_names = projects.free_parts(seatable=self._seatable)
            for n in self._free_names:
                self._specs.setdefault(n, modules_mod.spec(n))
        except Exception as exc:                       # noqa: BLE001
            _log("library: %r" % (exc,))
            msg = describe_error(exc, action="loading")
            if msg.startswith("Something went wrong"):
                _report("loading the module library: %r" % (exc,))
            self._show_unavailable(msg)
            self._loaded = False        # retry on the next show
            return
        self._show_unavailable(None)
        self._build_module_buttons()
        self._build_free_buttons()
        self.refresh()

    def _show_unavailable(self, msg):
        """msg: why the board cannot be shown (None = it can). While the
        library is unusable the board map, its lists and Check all are
        hidden — an empty board map would read as "no ports"."""
        self._unavailable = msg
        for w in (self.map, self.btn_check, self.port_title, self.port_sub):
            w.setVisible(msg is None)
        if msg is not None:
            self.on_label.hide()
            # Through _hide_verdicts so the kept result goes too: a restyle
            # must not bring verdicts back over an unusable library (R175).
            self._hide_verdicts()
            for w in (self.occ_row, self.list_label, self.undo_row,
                      self.notice, self.stale_row, self.move_row,
                      self.free_label, self.free_sub):
                w.hide()
            for b in self._free_btns + self._free_rows:
                b.hide()
            self.meta.setText("")
            self._show_error(msg)
        else:
            self.err.hide()

    def _build_module_buttons(self):
        for b in self._module_btns:
            b.deleteLater()
        self._module_btns = []
        offered = [(n, sp) for n, sp in self._specs.items() if n in self._seatable]
        for i, (name, sp) in enumerate(sorted(
                offered, key=lambda kv: kv[1].get("display_name", kv[0]))):
            dims = sp.get("dimensions_mm") or {}
            sub = " × ".join("%g" % dims[k] for k in ("x", "z", "y") if k in dims)
            derived = sp.get("derived")
            b = QtWidgets.QPushButton("%s\n%s mm%s" % (
                sp.get("display_name") or name, sub or "—",
                " · derived" if derived else ""))
            b.setObjectName("MModule")
            b.setCursor(QtCore.Qt.PointingHandCursor)
            tip = sp.get("description") or name
            if derived:
                tip += "\n\nDerived model, not Atech CAD: " + derived
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, n=name: self._add(n))
            self.grid.addWidget(b, i // 2, i % 2)
            self._module_btns.append(b)

    def _current(self):
        """The active document, or None — also None while it is being
        closed (the observer runs before FreeCAD drops it, R103)."""
        doc = _doc(create=False)
        uid = _doc_uid(doc)
        if uid is None or uid in self._closing:
            return None
        return doc

    def _on_documents_changed(self):
        """A document was closed, created or activated (R103): forget what
        the page showed about a document that is no longer the active one,
        and redraw from the document that is."""
        self._closing &= _open_uids()
        open_uids = _open_uids() - self._closing
        self._framed &= open_uids
        for uid in [u for u in self._plans if u not in open_uids]:
            del self._plans[uid]
        if self._undo is not None and _doc_uid(self._undo[0]) not in open_uids:
            self._clear_undo()
        # Only once the library is loaded: the observer runs from app start,
        # and refresh() imports atech_ports — a cost showEvent defers until
        # the page is first opened (its _load ends in a refresh anyway).
        if self._ports:
            self.refresh()

    def _occupied(self):
        doc = self._current()
        if doc is None:
            return {}
        try:
            ports_mod, _ = _lib()
            return ports_mod.occupied(doc)
        except Exception:                              # noqa: BLE001
            return {}

    def refresh(self):
        if self._unavailable is not None:
            return
        doc = self._current()
        uid = _doc_uid(doc)
        # R103: verdicts are about one document; hide them once it is not
        # the active one any more (closed, or another one picked).
        if self._verdict_uid is not None and self._verdict_uid != uid:
            self._verdict_uid = None
            self._hide_verdicts()
            self.notice.hide()
        if self._moving is not None and (self._moving[0] != uid or doc is None
                                         or doc.getObject(self._moving[1]) is None):
            self._cancel_move()
        occ = self._occupied()
        # R107: nothing to check without a document; R206: nor on a board
        # with no module seated - enabled by the first add, disabled again
        # when the last module comes off.
        self.btn_check.setEnabled(bool(occ))
        self.btn_check.setToolTip(
            "Check every module on the board" if occ else
            "Open or create a document first" if doc is None else
            "Add a module to the board first")
        labels = {n: self._short(o) for n, o in occ.items()}
        # a two-port module is named once, on its first port
        first = {}
        for n, o in sorted(occ.items()):
            first.setdefault(o.Name, n)
        mods = {}
        for n, o in sorted(occ.items()):
            key, ports, joint = mods.get(o.Name, (getattr(o, "AtechModule", "") or o.Label,
                                                  [], self._joint(o)))
            ports.append(n)
            mods[o.Name] = (key, ports, joint)
        moving = ()
        if self._moving is not None and doc is not None:
            mo = doc.getObject(self._moving[1])
            moving = tuple(int(p) for p in getattr(mo, "AtechPorts", []) or [])
        self.map.set_state(self._ports, labels, self._selected,
                           {k: (m, tuple(ps), j) for k, (m, ps, j) in mods.items()},
                           tips=self._tips(occ), moving=moving)
        self._sync_list(occ, first)
        self._sync_free(doc)
        self._sync_stale(doc, occ)
        mods = {o.Name for o in occ.values()}
        self.meta.setText("%d module%s on %d port%s" % (
            len(mods), "" if len(mods) == 1 else "s",
            len(occ), "" if len(occ) == 1 else "s") if occ else
            "No modules on the board yet")
        self._sync_panel(occ)

    @staticmethod
    def _joint(o):
        return "cable" if getattr(o, "AtechJoint", None) == "cable" else "seat"

    def _cables(self, o):
        """[length mm] of a cabled module's cables (R302), [] otherwise."""
        if self._joint(o) != "cable":
            return []
        try:
            ports_mod, _ = _lib()
            return [float(getattr(c, "AtechCableLength", 0.0) or 0.0)
                    for c in ports_mod.cables_of(o.Document, o)]
        except Exception:                              # noqa: BLE001
            return []

    def _tips(self, occ):
        """{port: hover line} for the board map (R304)."""
        out = {}
        for n, prt in self._ports.items():
            o = occ.get(n)
            edge = getattr(prt, "edge", None)
            if o is None:
                out[n] = port_tooltip(n, edge, reserved=self._reserved.get(n))
                continue
            others = [int(p) for p in o.AtechPorts if int(p) != n]
            ls = self._cables(o)
            out[n] = port_tooltip(n, edge, self._short(o), others,
                                  cable_mm=(sum(ls) if ls else
                                            (0.0 if self._joint(o) == "cable" else None)))
        return out

    def _sync_stale(self, doc, occ):
        """R301: the board-moved detector. Shows the Re-seat all banner while
        any module no longer matches the board."""
        stale = {"seated": [], "cabled": [], "unknown": {}}
        if doc is not None and occ:
            try:
                ports_mod, _ = _lib()
                stale = ports_mod.stale_modules(doc)
            except Exception as exc:                   # noqa: BLE001
                _log("stale: %r" % (exc,))
        self._stale = stale
        text = (None if self._anim is not None else
                stale_sentence(len(stale["seated"]), len(stale["cabled"])))
        self.stale_text.setText(text or "")
        self.btn_reseat.setEnabled(self._anim is None)
        self.stale_row.setVisible(bool(text))

    def _sync_list(self, occ, first):
        key = [(n, occ[n].Name, self._joint(occ[n]),
                tuple(round(v) for v in self._cables(occ[n])))
               for n in sorted(first.values())]
        if key == getattr(self, "_list_key", None):
            return
        self._list_key = key
        for w in self._on_rows:
            w.deleteLater()
        self._on_rows = []
        self.on_label.setVisible(bool(key))
        icon = cable_icon(style.tokens()["muted"])
        for n, _name, joint, lengths in key:
            o = occ[n]
            ports = ", ".join(str(p) for p in sorted(o.AtechPorts))
            where = "port%s %s" % ("s" if len(o.AtechPorts) > 1 else "", ports)
            if joint == "cable":
                where += "   ·   %s" % cable_words(lengths).replace(
                    "Connected by", "by")
            b = QtWidgets.QPushButton("%s   ·   %s" % (self._short(o), where))
            if joint == "cable":
                b.setIcon(icon)
            b.setObjectName("MRow")
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.setAccessibleName("%s, %s%s" % (
                self._short(o), where.replace("   ·   ", ", "), ""))
            b.clicked.connect(lambda _=False, k=n: self.pick(k))
            self.on_list.addWidget(b)
            self._on_rows.append(b)

    def _short(self, obj):
        sp = self._specs.get(getattr(obj, "AtechModule", ""), {})
        return sp.get("display_name") or getattr(obj, "AtechModule", obj.Label)

    # ---------------------------------------------------------- selection
    def pick(self, n):
        if self._moving is not None:
            # R300: the pick is where the module goes
            self._move_to(n)
            return
        self._selected = n
        self._hide_verdicts()
        self.err.hide()
        self.notice.hide()
        self.refresh()
        # R185: an occupied port shows its module's verdict line, the same
        # line an add ends on — also after Check all, which the hide above
        # clears. A fresh check, never a kept result the document may have
        # outgrown. Not mid-slide: the pose then is not the seated one.
        if self._anim is None and self._unavailable is None:
            o = self._occupied().get(n)
            if o is not None:
                self._show_check(doc=o.Document, only=o.Name)

    def _sync_panel(self, occ):
        n = self._selected
        if n is None or n not in self._ports:
            for w in (self.occ_row, self.list_label, self.by_cable):
                w.hide()
            for b in self._module_btns:
                b.hide()
            return
        port = self._ports[n]
        axis = EDGE_WORDS.get(port.edge, port.edge)
        self.port_title.setText("Port %d" % n)
        if n in occ:
            # The title already says "Port n" and the verdicts below name
            # nothing again (R60): say only what is new here.
            o = occ[n]
            others = sorted(int(p) for p in o.AtechPorts if int(p) != n)
            cabled = self._joint(o) == "cable"
            how = cable_words(self._cables(o)) if cabled else axis
            self.port_sub.setText("%s · %s%s" % (
                self._short(o), how,
                (" · also on port%s %s" % ("s" if len(others) > 1 else "",
                                           ", ".join(str(p) for p in others)))
                if others else ""))
            self.occ_row.show()
            busy = self._anim is not None
            for b in (self.btn_remove, self.btn_move):
                b.setEnabled(not busy)
            self.btn_move.setVisible(self._moving is None)
            self.btn_recable.setVisible(cabled and o.Name in self._stale["cabled"])
            self.btn_recable.setEnabled(not busy)
            self.list_label.hide()
            self.by_cable.hide()
            for b in self._module_btns:
                b.hide()
        elif n in self._reserved:
            self.port_sub.setText("Reserved for %s · no module can be added "
                                  "here." % self._reserved[n])
            self.occ_row.hide()
            self.list_label.hide()
            self.by_cable.hide()
            for b in self._module_btns:
                b.hide()
        else:
            self.port_sub.setText("Empty · %s edge · a module %s and stops "
                                  "when its pins are seated." % (port.edge, axis))
            self.occ_row.hide()
            self.list_label.show()
            self.by_cable.show()
            self.by_cable.setEnabled(self._anim is None)
            for b in self._module_btns:
                b.show()
                b.setEnabled(self._anim is None)

    # ------------------------------------------------------------ actions
    def _pair_for(self, name, n):
        """Port pair for a two-connector module: n and a free, unreserved
        neighbour in the same column whose TRIAL check is all PASS
        (atech_ports.pair_for — it adds nothing to the document). No such
        pair -> PortSpecError, said in a plain sentence by describe_error.
        Never a pair the page's own check would then FAIL (R65)."""
        ports_mod, _ = _lib()
        return ports_mod.pair_for(_doc(create=False), name, n,
                                  reserved=self._reserved)

    def _add(self, name):
        n = self._selected
        if n is None or self._anim is not None or n in self._reserved:
            return
        if self.by_cable.isChecked():
            self._add_cabled(name)
            return
        self.err.hide()
        self.notice.hide()
        self._clear_undo()
        import FreeCAD
        try:
            ports_mod, _ = _lib()
            doc = _doc()
            feat = ports_mod.measure_module(name)
            arg = n if len(feat["groups"]) == 1 else self._pair_for(name, n)
            # One undo step for the add (it may also create the board).
            txn = "Add %s" % name
            FreeCAD.setActiveTransaction(txn)
            try:
                obj = ports_mod.seat(doc, name, arg)
            finally:
                FreeCAD.closeActiveTransaction()
            try:
                obj.ViewObject.ShapeColor = (0.35, 0.64, 1.00)
            except Exception:                          # noqa: BLE001
                pass
        except Exception as exc:                       # noqa: BLE001
            _log("seat %s on %s: %r" % (name, n, exc))
            self._show_failure(exc, module=name, port=n, action="adding")
            return
        self._first_frame(doc)
        oname = obj.Name
        self._animate(obj, obj.AtechSlideOut, 0.0,
                      lambda: self._after_add(doc, oname, txn))

    def _add_cabled(self, name):
        """Add `name` off the board, wired to the picked port: placed by
        cabled_placement (clear of the board past the port), cabled by
        atech_ports.cable, one undo step. A two-connector module takes the
        same port pair a seated one would (pair_for)."""
        n = self._selected
        self.err.hide()
        self.notice.hide()
        self._clear_undo()
        import FreeCAD
        try:
            ports_mod, _ = _lib()
            doc = _doc()
            feat = ports_mod.measure_module(name)
            arg = n if len(feat["groups"]) == 1 else self._pair_for(name, n)
            txn = "Add %s by cable" % name
            FreeCAD.setActiveTransaction(txn)
            try:
                board = ports_mod.board_object(doc)
                pl = cabled_placement(ports_mod, name, self._ports[n], board.Placement)
                obj, _cables = ports_mod.cable(doc, name, arg, pl)
            finally:
                FreeCAD.closeActiveTransaction()
            try:
                obj.ViewObject.ShapeColor = (0.35, 0.64, 1.00)
            except Exception:                          # noqa: BLE001
                pass
        except Exception as exc:                       # noqa: BLE001
            _log("cable %s to %s: %r" % (name, n, exc))
            self._show_failure(exc, module=name, port=n, action="adding")
            return
        self._first_frame(doc)
        plan = self._plans.get(_doc_uid(doc))
        if plan is not None:
            plan.slide_done()           # nothing slides in: frame it now
        self._after_add(doc, obj.Name, txn)

    def _after_add(self, doc, oname, txn=None):
        plan = self._plans.get(_doc_uid(doc))
        if plan is not None:
            plan.slide_done()           # the next settled poll frames the seated board
        self.refresh()
        o = doc.getObject(oname)
        if o is not None:
            self._show_check(doc=doc, only=oname)
            if txn:
                # R304: "Added <name> · Undo", like Remove's row
                shown = self._short(o)
                self._offer_undo(doc, txn, shown, "Added %s" % shown)

    def _remove(self):
        n = self._selected
        occ = self._occupied()
        if n not in occ or self._anim is not None:
            return
        obj = occ[n]
        doc, oname = obj.Document, obj.Name
        module = getattr(obj, "AtechModule", "")
        shown = self._short(obj)
        self.err.hide()
        self.notice.hide()
        self._clear_undo()

        def done():
            import FreeCAD
            try:
                ports_mod, _ = _lib()
                o = doc.getObject(oname)
                if o is not None:
                    # back to the seat first, so Undo restores it seated,
                    # not at the slid-out animation pose
                    ports_mod.slide(o, 0.0)
                    txn = "Remove %s" % o.Label
                    FreeCAD.setActiveTransaction(txn)
                    try:
                        ports_mod.remove(doc, n)
                    finally:
                        FreeCAD.closeActiveTransaction()
                    self._offer_undo(doc, txn, shown)
            except Exception as exc:                   # noqa: BLE001
                _log("remove port %s: %r" % (n, exc))
                self._show_failure(exc, module=module, port=n,
                                   action="removing")
            self._hide_verdicts()
            self.refresh()
        self._animate(obj, 0.0, obj.AtechSlideOut, done)

    # ------------------------------------------------- move and swap (R300)
    def _start_move(self):
        """Move mode: the next port picked on the map is where the selected
        module goes (empty port), or whom it swaps with (occupied port)."""
        n = self._selected
        o = self._occupied().get(n)
        if o is None or self._anim is not None:
            return
        self.err.hide()
        self.notice.hide()
        self._clear_undo()
        self._moving = (_doc_uid(o.Document), o.Name)
        self.move_text.setText(
            "Moving %s. Pick an empty port to move it there, or a port with "
            "another module to swap the two." % self._short(o))
        self.move_row.show()
        self.refresh()

    def _cancel_move(self):
        self._moving = None
        self.move_row.hide()
        self.btn_move.setVisible(True)
        self.map.moving = ()
        self.map.update()

    def _target_ports(self, ports_mod, o, n):
        """Port sets o could take with port n picked: [n] for one connector;
        for two, n with each same-column neighbour that is free or o's own,
        each a tuple; [] when there is none."""
        k = len(o.AtechPorts)
        if k == 1:
            return [(n,)]
        p0 = self._ports.get(n)
        if p0 is None:
            return []
        col = sorted((q for q in self._ports.values() if q.edge == p0.edge),
                     key=lambda q: q.row_centre)
        i = [q.number for q in col].index(n)
        occ = ports_mod.occupied(o.Document)
        out = []
        for j in (i - 1, i + 1):
            if 0 <= j < len(col):
                m = col[j].number
                if m in self._reserved:
                    continue
                if m not in occ or occ[m].Name == o.Name:
                    out.append(tuple(sorted((n, m))))
        return out

    def _move_to(self, n):
        """The pick in move mode (R300): move, swap, cancel or refuse."""
        doc = self._current()
        if doc is None or self._moving is None or self._anim is not None:
            self._cancel_move()
            return
        uid, oname = self._moving
        o = doc.getObject(oname)
        if o is None or _doc_uid(doc) != uid:
            self._cancel_move()
            return
        occ = self._occupied()
        tgt = occ.get(n)
        act, arg = move_action(o.AtechPorts, n, (tgt.Name, list(tgt.AtechPorts))
                               if tgt is not None and tgt.Name != o.Name else None)
        if act == "cancel":
            self._cancel_move()
            self.refresh()
            return
        if act == "refuse":
            self._show_error(arg)
            return
        if act == "move" and n in self._reserved:
            self._show_error("Port %d is reserved for %s, so no module can go "
                             "there." % (n, self._reserved[n]))
            return
        self.err.hide()
        shown = self._short(o)
        import FreeCAD
        try:
            ports_mod, _ = _lib()
            if act == "swap":
                other = self._short(tgt)
                txn = "Swap %s and %s" % (o.Label, tgt.Label)
                FreeCAD.setActiveTransaction(txn)
                try:
                    ports_mod.swap(doc, o, tgt)
                finally:
                    FreeCAD.closeActiveTransaction()
                text = "Swapped %s and %s" % (shown, other)
            else:
                txn = "Move %s" % o.Label
                cands = self._target_ports(ports_mod, o, n)
                if not cands:
                    raise ports_mod.PortSpecError(
                        "no free neighbour", kind="no_pair",
                        module=o.AtechModule, port=n)
                done, last = None, None
                for ps in cands:
                    # each try is its own transaction; a pair whose check
                    # fails is rolled back (abort) before the next is tried
                    FreeCAD.setActiveTransaction(txn)
                    ok = False
                    try:
                        ports_mod.move(doc, o, ps if len(ps) > 1 else ps[0])
                        res = check_doc(ports_mod, doc, only=[o.Name])[0].get(o.Name, {})
                        ok = len(cands) == 1 or all(
                            (v or {}).get("verdict") == ports_mod.PASS
                            for v in res.values())
                        last = None if ok else ports_mod.first_why(res)
                    except Exception as exc:           # noqa: BLE001
                        last = exc
                    finally:
                        FreeCAD.closeActiveTransaction(not ok)
                    if ok:
                        done = ps
                        break
                if done is None:
                    if isinstance(last, Exception):
                        raise last
                    raise ports_mod.PortSpecError(
                        "every pair fails: %s" % last, kind="pair_fails",
                        module=o.AtechModule, port=n)
                text = "Moved %s to port%s %s" % (
                    shown, "s" if len(done) > 1 else "",
                    " and ".join(str(p) for p in sorted(done)))
        except Exception as exc:                       # noqa: BLE001
            _log("move %s to %s: %r" % (oname, n, exc))
            self._show_failure(exc, module=getattr(o, "AtechModule", None),
                               port=n, action="moving")
            self._cancel_move()
            self.refresh()
            return
        self._cancel_move()
        self._selected = n
        self._hide_verdicts()
        self.refresh()
        self._show_check(doc=doc, only=o.Name)
        self._offer_undo(doc, txn, shown, text)

    # --------------------------------------- re-seat and cables (R301/R302)
    def _reseat_all(self):
        doc = self._current()
        if doc is None or self._anim is not None:
            return
        self.err.hide()
        self.notice.hide()
        self._clear_undo()
        import FreeCAD
        txn = "Re-seat modules"
        try:
            ports_mod, _ = _lib()
            FreeCAD.setActiveTransaction(txn)
            try:
                owners = {}
                for name in ports_mod.stale_modules(doc)["cabled"]:
                    m = doc.getObject(name)
                    if m is not None:
                        owners[name] = (m, cable_owners(doc, m))
                rep = ports_mod.reseat_all(doc)
                for m, own in owners.values():          # R512
                    keep_cable_owners(doc, m, own)
            finally:
                FreeCAD.closeActiveTransaction()
        except Exception as exc:                       # noqa: BLE001
            _log("reseat all: %r" % (exc,))
            self._show_failure(exc, action="re-seating")
            return
        n = len(rep["reseated"]) + len(rep["recabled"])
        self.refresh()
        if rep["failed"]:
            names = [self._short(doc.getObject(k)) if doc.getObject(k) else k
                     for k in sorted(rep["failed"])]
            _report("re-seat all: %r" % (rep["failed"],))
            self._show_error("%s could not be put back. The details are in the "
                             "Report view." % " and ".join(names))
        if n:
            self._show_check(doc=doc, only=None)
            parts = []
            if rep["reseated"]:
                k = len(rep["reseated"])
                parts.append("re-seated %d module%s" % (k, "" if k == 1 else "s"))
            if rep["recabled"]:
                k = len(rep["recabled"])
                parts.append("remade %d cable%s" % (k, "" if k == 1 else "s"))
            self._offer_undo(doc, txn, "", " and ".join(parts).capitalize())

    def _remake_cable(self):
        o = self._occupied().get(self._selected)
        if o is None or self._joint(o) != "cable" or self._anim is not None:
            return
        doc = o.Document
        shown = self._short(o)
        self.err.hide()
        self._clear_undo()
        import FreeCAD
        txn = "Remake cable of %s" % o.Label
        try:
            ports_mod, _ = _lib()
            FreeCAD.setActiveTransaction(txn)
            try:
                owners = cable_owners(doc, o)
                ports_mod.remake_cable(doc, o)
                keep_cable_owners(doc, o, owners)      # R512
            finally:
                FreeCAD.closeActiveTransaction()
        except Exception as exc:                       # noqa: BLE001
            _log("remake cable %s: %r" % (o.Name, exc))
            self._show_failure(exc, module=getattr(o, "AtechModule", None),
                               action="remaking the cable of")
            return
        self.refresh()
        self._show_check(doc=doc, only=o.Name)
        self._offer_undo(doc, txn, shown, "Remade the cable of %s" % shown)

    # ------------------------------------------------- free parts (R305)
    def _build_free_buttons(self):
        for b in self._free_btns:
            b.deleteLater()
        self._free_btns = []
        names = sorted(self._free_names, key=lambda n: display_name(n, self._specs))
        for i, name in enumerate(names):
            sp = self._specs.get(name) or {}
            dims = sp.get("dimensions_mm") or {}
            sub = " × ".join("%g" % dims[k] for k in ("x", "z", "y") if k in dims)
            shown = display_name(name, self._specs)
            mine = bool(sp.get("user"))
            b = QtWidgets.QPushButton("%s\n%s mm%s" % (
                shown, sub or "—", " · your part" if mine else ""))
            b.setObjectName("MModule")
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.setToolTip(free_part_tooltip(sp, shown))
            b.setAccessibleName("Add %s beside the board" % shown)
            b.clicked.connect(lambda _=False, n=name: self._add_free(n))
            if mine:
                b.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                b.customContextMenuRequested.connect(
                    lambda _pos, n=name, w=b: self._user_part_menu(n, w))
            self.free_grid.addWidget(b, i // 2, i % 2)
            self._free_btns.append(b)
        vis = bool(names) and self._unavailable is None
        self.free_label.setVisible(vis)
        self.free_sub.setVisible(vis)
        self.import_btn.setVisible(self._unavailable is None)

    def _import_part(self):
        """R750: Import part... - a part that is not an Atech module."""
        from . import import_part
        try:
            _lib()
            dlg = import_part.ImportPartDialog(
                self, on_done=lambda n: self._imported(n))
        except Exception as exc:                       # noqa: BLE001
            _log("import part: %r" % (exc,))
            self._show_failure(exc, action="importing")
            return
        if dlg is not None:
            dlg.exec()

    def _imported(self, name):
        self._load()
        sp = self._specs.get(name) or {}
        shown = display_name(name, self._specs)
        if name in self._seatable:
            text = ("%s has an Atech header: it is in the module list and "
                    "seats on a port." % shown)
        else:
            text = ("%s is in your parts. Add it beside the board, or ask the "
                    "agent to build around it." % shown)
        if sp.get("mesh_note"):
            text += " Note: %s." % sp["mesh_note"]
        self.notice.setText(text)
        self.notice.show()

    def _user_part_menu(self, name, widget):
        menu = QtWidgets.QMenu(widget)
        act = menu.addAction("Remove from your parts")
        if menu.exec(QtGui.QCursor.pos()) is not act:
            return
        shown = display_name(name, self._specs)
        ok = QtWidgets.QMessageBox.question(
            self, "Remove part",
            "Remove %s from your parts? Copies already in a design stay." % shown)
        if ok != QtWidgets.QMessageBox.Yes:
            return
        try:
            import user_parts
            user_parts.remove_part(name)
        except Exception as exc:                       # noqa: BLE001
            _log("remove user part %s: %r" % (name, exc))
            self._show_failure(exc, action="removing")
            return
        self._specs.pop(name, None)
        self._load()

    def _sync_free(self, doc):
        from . import projects
        try:
            placed = projects.placed_free_parts(doc)
        except Exception:                              # noqa: BLE001
            placed = []
        key = [(o.Name, o.Label) for o in placed]
        if key == getattr(self, "_free_key", None):
            return
        self._free_key = key
        for w in self._free_rows:
            w.deleteLater()
        self._free_rows = []
        for o in placed:
            row = QtWidgets.QWidget()
            rl = QtWidgets.QHBoxLayout(row)
            rl.setContentsMargins(8, 0, 0, 0)
            rl.setSpacing(4)
            shown = self._short(o)
            lab = QtWidgets.QLabel("%s   ·   placed by hand" % shown)
            lab.setObjectName("MPortSub")
            lab.setTextFormat(QtCore.Qt.PlainText)
            rm = QtWidgets.QPushButton("Remove")
            rm.setObjectName("MLink")
            rm.setCursor(QtCore.Qt.PointingHandCursor)
            rm.setAccessibleName("Remove %s" % shown)
            rm.clicked.connect(lambda _=False, k=o.Name: self._remove_free(k))
            rl.addWidget(lab, 1)
            rl.addWidget(rm)
            self.free_list.addWidget(row)
            self._free_rows.append(row)

    def _add_free(self, name):
        if self._anim is not None:
            return
        self.err.hide()
        self.notice.hide()
        self._clear_undo()
        import FreeCAD
        from . import projects
        txn = "Add %s" % name
        try:
            _lib()
            doc = _doc()
            FreeCAD.setActiveTransaction(txn)
            try:
                obj = projects.place_free_part(doc, name)
            finally:
                FreeCAD.closeActiveTransaction()
            try:
                obj.ViewObject.ShapeColor = (0.55, 0.60, 0.72)
            except Exception:                          # noqa: BLE001
                pass
        except Exception as exc:                       # noqa: BLE001
            _log("free part %s: %r" % (name, exc))
            self._show_failure(exc, module=name, action="adding")
            return
        self._first_frame(doc)
        self.refresh()
        shown = display_name(name, self._specs)
        self._offer_undo(doc, txn, shown, "Added %s" % shown)

    def _remove_free(self, oname):
        doc = self._current()
        o = doc.getObject(oname) if doc is not None else None
        if o is None or self._anim is not None:
            return
        shown = self._short(o)
        self._clear_undo()
        import FreeCAD
        txn = "Remove %s" % o.Label
        try:
            FreeCAD.setActiveTransaction(txn)
            try:
                doc.removeObject(oname)
                doc.recompute()
            finally:
                FreeCAD.closeActiveTransaction()
        except Exception as exc:                       # noqa: BLE001
            _log("remove free part %s: %r" % (oname, exc))
            self._show_failure(exc, action="removing")
            return
        self.refresh()
        self._offer_undo(doc, txn, shown)

    def _animate(self, obj, start, end, done):
        """Slide along the measured prismatic axis: start -> end mm out."""
        _, _ = _lib()
        import atech_ports
        step = {"i": 0}
        doc, oname = obj.Document, obj.Name
        tm = QtCore.QTimer(self)
        self._anim = tm
        self._sync_panel(self._occupied())

        def tick():
            step["i"] += 1
            k = min(1.0, step["i"] / float(SLIDE_STEPS))
            k = 1 - (1 - k) ** 3               # ease out
            # The object (or its document) can be deleted mid-slide; look it
            # up by name every tick instead of holding a dead reference.
            try:
                live = doc.getObject(oname)
            except Exception:                          # noqa: BLE001
                live = None
            if live is None:
                k = 1.0
            else:
                try:
                    atech_ports.slide(live, start + (end - start) * k)
                except Exception as exc:               # noqa: BLE001
                    _log("slide: %r" % (exc,))
                    k = 1.0
            if k >= 1.0:
                tm.stop()
                self._anim = None
                if live is not None:
                    try:
                        atech_ports.slide(live, end)
                    except Exception:                  # noqa: BLE001
                        pass
                try:
                    done()
                except Exception as exc:               # noqa: BLE001
                    _log("after slide: %r" % (exc,))
                self.refresh()
        tm.timeout.connect(tick)
        tm.start(max(10, SLIDE_MS // SLIDE_STEPS))

    def _first_frame(self, doc):
        """Frame the board the first time a module goes on in a document:
        once its view has settled, and again once the module is seated or
        the view resized (FirstFrame, R86). Keyed by the document's Uid, so
        a fresh document that reuses a closed one's Name is framed too, even
        when the close and the re-open both happened before this runs
        (R102)."""
        open_uids = _open_uids() - self._closing
        self._framed &= open_uids
        for k in [u for u in self._plans if u not in open_uids]:
            del self._plans[k]
        uid = _doc_uid(doc)
        if uid is None or uid in self._framed:
            return
        self._framed.add(uid)
        plan = FirstFrame()
        self._plans[uid] = plan
        dname = doc.Name
        t0 = time.monotonic()
        tm = QtCore.QTimer(self)

        def finish():
            tm.stop()
            tm.deleteLater()
            if self._plans.get(uid) is plan:
                del self._plans[uid]

        def tick():
            try:
                import FreeCAD
                live = FreeCAD.listDocuments().get(dname)
            except Exception:                          # noqa: BLE001
                live = None
            if _doc_uid(live) != uid or self._plans.get(uid) is not plan:
                finish()                # closed, or replaced by a same-Name one
                return
            size = _view_size(dname)
            waited = (time.monotonic() - t0) * 1000.0
            act = plan.step(size, waited)
            if act == "frame":
                _log("frame: view %s after %.0f ms (seated: %s)"
                     % (size, waited, plan.slid))
                self._frame_now(dname)
            if act == "stop" or plan.stopped:
                finish()
        tm.timeout.connect(tick)
        tm.start(FRAME_POLL_MS)

    def _frame_now(self, dname):
        """Point the view of document dname at its board and fit. Skipped
        when that document is gone or is no longer the active one (the fit
        acts on the ACTIVE view)."""
        try:
            import FreeCAD
            import FreeCADGui
            doc = FreeCAD.listDocuments().get(dname)
            gd = FreeCADGui.ActiveDocument
            if doc is None or gd is None or gd.Document.Name != dname:
                _log("frame: %s not active any more; skipped" % dname)
                return
            from . import projects
            ports_mod, _ = _lib()
            b = ports_mod.board_object(doc, create=False)
            if not projects.frame_board(b.Placement if b is not None else None):
                _log("frame: no 3D view to point")
        except Exception as exc:                       # noqa: BLE001
            _log("frame: %r" % (exc,))

    def _check_all(self):
        self.err.hide()
        self.notice.hide()
        if self._current() is None:
            self.btn_check.setEnabled(False)     # R107: stale click, no document
            return
        if not self._occupied():
            # Say so, rather than a button that silently does nothing.
            self._hide_verdicts()
            self.notice.setText("No modules on the board yet. Pick a port "
                                "on the board to add one.")
            self.notice.show()
            return
        self._show_check(only=None)

    def _show_check(self, doc=None, only=None):
        doc = doc or self._current()
        if doc is None or _doc_uid(doc) is None:
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            ports_mod, _ = _lib()
            res, self._fitted = check_doc(ports_mod, doc, only=[only] if only else None)
        except Exception as exc:                       # noqa: BLE001
            _log("check: %r" % (exc,))
            self._show_failure(exc, action="checking")
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self._render_check(doc, only, res)

    def _render_check(self, doc, only, res, m=None):
        """Draw a check result in the current theme's colours (or mode m).
        The result is kept, so restyle() redraws it after a theme switch
        instead of leaving the old theme's colours baked in (R175)."""
        t = style.tokens(m)

        def name_of(label):
            try:
                objs = doc.getObjectsByLabel(label)
            except Exception:                          # noqa: BLE001
                objs = []
            return self._short(objs[0]) if objs else label

        rows = []
        for name, verdicts in sorted(res.items(), key=lambda kv: self._check_key(doc, kv[0])):
            if only and name != only:
                continue
            o = doc.getObject(name)
            if getattr(o, "AtechRole", None) == FREE_ROLE:
                continue                # R305: a free part has no port to check
            label = self._short(o) if o is not None else name
            cabled = o is not None and self._joint(o) == "cable"
            cells, whys = [], []
            for key in (CABLED_ORDER if cabled else CHECK_ORDER):
                r = verdicts.get(key) or {}
                text, tok = verdict_words(key, r, name_of, cabled=cabled)
                cells.append("<span style='color:%s;font-weight:600'>%s</span>"
                             % (t[tok], html.escape(text)))
                why = fail_why(key, r, name_of)
                if why:
                    whys.append("<span style='color:%s'>%s</span>"
                                % (t["muted"], html.escape(why)))
            if cabled:
                ls = self._cables(o)
                if ls:
                    cells.append("<span style='color:%s'>%s</span>" % (
                        t["muted"], html.escape(cable_words(ls).split(" · ", 1)[-1])))
            body = " &nbsp;·&nbsp; ".join(cells)
            if whys:
                body += "<br>" + "<br>".join(whys)
            if only:
                # After an add the port panel above already names the
                # module (R60).
                rows.append(body)
                continue
            ports = sorted(int(p) for p in getattr(o, "AtechPorts", []) or [])
            where = ("port%s %s" % ("s" if len(ports) > 1 else "",
                                    ", ".join(str(p) for p in ports))) if ports else ""
            rows.append(check_all_block(label, where, body, t["muted"]))
        if not only:
            # R303: the power rule heads Check all
            warn = power_warning(self._board_modules(doc))
            if warn:
                rows.insert(0, "<p style='margin-top:0px; margin-bottom:%dpx; "
                            "color:%s; font-weight:600'>%s</p>"
                            % (CHECK_ALL_GAP_PX, t["warn"], html.escape(warn)))
        fitted = [lab for lab in (getattr(self, "_fitted", None) or ())]
        if fitted and rows:
            # R517: say which parts the slide paths were judged without
            rows.append("<span style='color:%s'>%s</span>" % (
                t["muted"], html.escape(fitted_note(fitted))))
        self._hide_verdicts()
        if not rows:
            return
        target = self.verdicts if only else self.all_verdicts
        target.setText("<br>".join(rows) if only else "".join(rows))
        target.setStyleSheet("color:%s; font-size:12px;" % t["muted"])
        target.show()
        self.all_label.setVisible(not only)
        self._verdict_uid = _doc_uid(doc)
        self._last_check = (doc, doc.Name, only, res)

    @staticmethod
    def _board_modules(doc):
        """presets.yaml names of the modules on doc's board, one per module."""
        seen, out = set(), []
        try:
            ports_mod, _ = _lib()
            occ = ports_mod.occupied(doc)
        except Exception:                              # noqa: BLE001
            return out
        for o in occ.values():
            if o.Name not in seen:
                seen.add(o.Name)
                out.append(getattr(o, "AtechModule", "") or "")
        return out

    @staticmethod
    def _check_key(doc, name):
        """Check-all order: by the module's first port, then name."""
        o = doc.getObject(name)
        ports = sorted(int(p) for p in getattr(o, "AtechPorts", []) or []) if o else []
        return (ports[0] if ports else 999, name)

    def _hide_verdicts(self):
        self._last_check = None
        for w in (self.verdicts, self.all_label, self.all_verdicts):
            w.hide()

    def _rerender_check(self, m=None):
        """restyle() half of R175: redraw the verdicts on screen from the
        kept result (no new check), provided its document is still open
        and still the one the verdicts are about."""
        last = getattr(self, "_last_check", None)
        if last is None:
            return
        doc, dname, only, res = last
        try:
            import FreeCAD
            live = FreeCAD.listDocuments().get(dname)
        except Exception:                              # noqa: BLE001
            live = None
        if live is None or _doc_uid(live) != self._verdict_uid:
            self._hide_verdicts()
            return
        try:
            self._render_check(live, only, res, m)
        except Exception as exc:                       # noqa: BLE001
            _log("restyle verdicts: %r" % (exc,))

    # ------------------------------------------------------------ undo
    def _offer_undo(self, doc, txn, shown, text=None):
        """The inline Undo row for the newest page action (Remove; R304
        Add; R300 Move/Swap; R301 Re-seat all), one undo transaction each.
        text: what the row says (default "Removed <shown>")."""
        self._undo = (doc, doc.Name, txn, shown)
        self.undo_text.setText("%s  ·" % (text or ("Removed %s" % shown)))
        self.btn_undo.setAccessibleName("Undo: %s" % (text or ("Removed %s" % shown)))
        self.undo_row.show()

    def _clear_undo(self):
        self._undo = None
        self.undo_row.hide()

    def _undo_remove(self):
        if self._undo is None or self._anim is not None:
            return
        doc, dname, txn, shown = self._undo
        self._clear_undo()
        import FreeCAD
        try:
            live = FreeCAD.listDocuments().get(dname)
            # UndoNames is newest first (measured under freecadcmd 1.1.3).
            ok = live is not None and list(doc.UndoNames[:1]) == [txn]
        except Exception:                              # noqa: BLE001
            ok = False
        if not ok:
            # Something else was done since; undoing now would undo THAT.
            self._show_error("That can no longer be undone from here, because "
                             "the document has changed since. Use Edit > Undo "
                             "instead.")
            return
        try:
            doc.undo()
            doc.recompute()
        except Exception as exc:                       # noqa: BLE001
            _log("undo remove: %r" % (exc,))
            self._show_failure(exc, action="putting back")
            return
        self._hide_verdicts()
        self.refresh()

    def _show_failure(self, exc, module=None, port=None, action="adding"):
        msg = describe_error(exc, module=module, port=port,
                             specs=self._specs, action=action)
        if msg.startswith("Something went wrong"):
            _report("%s: %r" % (action, exc))
        if msg == MISSING_LIBRARY:
            self._show_unavailable(msg)
            self._loaded = False        # look again on the next show
            return
        self._show_error(msg)

    def _show_error(self, text):
        self.err.setText(text)
        self.err.show()

    def restyle(self):
        self.setStyleSheet(style.qss(PAGE_QSS))
        self._rerender_check()
        # the cable icon is drawn in the theme's colour: draw the rows again
        self._list_key = None
        if self._ports and self._unavailable is None:
            self.refresh()
        self.map.update()
