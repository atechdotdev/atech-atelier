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


def verdict_words(key, result, name_of=None):
    """(sentence, colour token) for one check result dict."""
    v = result.get("verdict") if isinstance(result, dict) else result
    words = CHECK_WORDS[key]
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


def _doc(create=True):
    import FreeCAD
    doc = FreeCAD.ActiveDocument
    if doc is None and create:
        doc = FreeCAD.newDocument("Atech_Project")
    return doc


# ------------------------------------------------------------- board map
class BoardMap(QtWidgets.QWidget):
    """The board drawn from the measured port table. Emits the picked port."""

    picked = QtCore.Signal(int)

    BOARD_X, BOARD_Z = 60.0, 120.0      # board STL frame extents (mm)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(360)
        self.setMouseTracking(True)
        self.ports = {}                 # n -> Port
        self.occupied = {}              # n -> short label
        self.selected = None
        self.hover = None
        self._rects = {}

    def sizeHint(self):                                 # noqa: N802
        return QtCore.QSize(320, 380)

    def set_state(self, ports, occupied, selected):
        self.ports, self.occupied, self.selected = ports, occupied, selected
        self.update()

    def _geometry(self):
        """Board rect in widget pixels, portrait, -Z (top edge) up."""
        pad = 22
        h = self.height() - 2 * pad
        w = h * self.BOARD_X / self.BOARD_Z
        x0 = (self.width() - w) / 2.0
        return QtCore.QRectF(x0, pad, w, h)

    def _slot(self, p, b):
        """Pixel rect of port p: its MEASURED housing box (board frame X, Z),
        scaled onto the board drawing. Pushed a little outboard so the slot
        reads as an opening on the edge the module comes from."""
        sx = b.width() / self.BOARD_X
        sz = b.height() / self.BOARD_Z
        lo, hi = p.housing_lo, p.housing_hi
        r = QtCore.QRectF(b.left() + lo[0] * sx, b.top() + lo[2] * sz,
                          (hi[0] - lo[0]) * sx, (hi[2] - lo[2]) * sz)
        out = QtCore.QPointF(p.outward[0], p.outward[2]) * 6.0
        return r.translated(out)

    def paintEvent(self, _ev):                         # noqa: N802
        t = style.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        b = self._geometry()
        p.setPen(QtGui.QPen(QtGui.QColor(t["line_strong"]), 1))
        p.setBrush(QtGui.QColor(t["card"]))
        p.drawRoundedRect(b, 10, 10)
        f = QtGui.QFont(style.FONT_UI)
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QtGui.QColor(t["dim"]))
        p.drawText(b, QtCore.Qt.AlignCenter, "14-port\nboard")
        self._rects = {}
        for n, port in sorted(self.ports.items()):
            r = self._slot(port, b)
            self._rects[n] = r
            occ = n in self.occupied
            sel = n == self.selected
            fill = t["btn_bg"] if occ else t["panel"]
            p.setBrush(QtGui.QColor(fill))
            pen = QtGui.QPen(QtGui.QColor(
                t["accent"] if sel else (t["text"] if n == self.hover else
                                         t["line_strong"])), 2 if sel else 1)
            p.setPen(pen)
            p.drawRoundedRect(r, 5, 5)
            p.setPen(QtGui.QColor(t["btn_text"] if occ else t["muted"]))
            fb = QtGui.QFont(style.FONT_UI)
            fb.setPixelSize(10)
            fb.setBold(True)
            p.setFont(fb)
            p.drawText(r, QtCore.Qt.AlignCenter, str(n))
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
            self.setToolTip("Port %d%s" % (h, (" · " + html.escape(self.occupied[h]))
                                           if h in self.occupied else " · empty")
                            if h else "")
            self.setCursor(QtCore.Qt.PointingHandCursor if h else
                           QtCore.Qt.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, ev):                   # noqa: N802
        h = self._hit(ev.position())
        if h is not None:
            self.picked.emit(h)


# ------------------------------------------------------------------ page
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
        ol.addWidget(self.btn_remove)
        ol.addStretch(1)
        self.occ_row.hide()
        lay.addWidget(self.occ_row)

        self.list_label = QtWidgets.QLabel("ADD A MODULE")
        self.list_label.setObjectName("MSection")
        self.list_label.hide()
        lay.addWidget(self.list_label)
        self.grid = QtWidgets.QGridLayout()
        self.grid.setSpacing(6)
        lay.addLayout(self.grid)
        lay.addStretch(1)
        self._module_btns = []

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.refresh)
        # Keyed by document Uid, never by Name: a fresh "Atech_Project"
        # reuses a closed one's Name (R102).
        self._framed = set()            # doc Uids whose first frame started
        self._plans = {}                # doc Uid -> FirstFrame still polling
        self._verdict_uid = None        # doc Uid the verdicts shown are about
        self._last_check = None         # (doc, Name, only, result) on screen (R175)
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
                      self.notice):
                w.hide()
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
            b = QtWidgets.QPushButton("%s\n%s mm" % (
                sp.get("display_name") or name, sub or "—"))
            b.setObjectName("MModule")
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.setToolTip(sp.get("description") or name)
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
        self.map.set_state(self._ports, labels, self._selected)
        self._sync_list(occ, first)
        mods = {o.Name for o in occ.values()}
        self.meta.setText("%d module%s on %d port%s" % (
            len(mods), "" if len(mods) == 1 else "s",
            len(occ), "" if len(occ) == 1 else "s") if occ else
            "No modules on the board yet")
        self._sync_panel(occ)

    def _sync_list(self, occ, first):
        key = [(n, occ[n].Name) for n in sorted(first.values())]
        if key == getattr(self, "_list_key", None):
            return
        self._list_key = key
        for w in self._on_rows:
            w.deleteLater()
        self._on_rows = []
        self.on_label.setVisible(bool(key))
        for n, name in key:
            o = occ[n]
            ports = ", ".join(str(p) for p in sorted(o.AtechPorts))
            b = QtWidgets.QPushButton("%s   ·   port%s %s" % (
                self._short(o), "s" if len(o.AtechPorts) > 1 else "", ports))
            b.setObjectName("MRow")
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=n: self.pick(k))
            self.on_list.addWidget(b)
            self._on_rows.append(b)

    def _short(self, obj):
        sp = self._specs.get(getattr(obj, "AtechModule", ""), {})
        return sp.get("display_name") or getattr(obj, "AtechModule", obj.Label)

    # ---------------------------------------------------------- selection
    def pick(self, n):
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
            for w in (self.occ_row, self.list_label):
                w.hide()
            for b in self._module_btns:
                b.hide()
            return
        port = self._ports[n]
        axis = {"left": "slides in from the left", "right":
                "slides in from the right", "top": "slides in from the top",
                "bottom": "slides in from the bottom"}.get(port.edge, port.edge)
        self.port_title.setText("Port %d" % n)
        if n in occ:
            # The title already says "Port n" and the verdicts below name
            # nothing again (R60): say only what is new here.
            o = occ[n]
            others = sorted(int(p) for p in o.AtechPorts if int(p) != n)
            self.port_sub.setText("%s · %s%s" % (
                self._short(o), axis,
                (" · also on port%s %s" % ("s" if len(others) > 1 else "",
                                           ", ".join(str(p) for p in others)))
                if others else ""))
            self.occ_row.show()
            self.list_label.hide()
            for b in self._module_btns:
                b.hide()
        elif n in self._reserved:
            self.port_sub.setText("Reserved for %s · no module can be added "
                                  "here." % self._reserved[n])
            self.occ_row.hide()
            self.list_label.hide()
            for b in self._module_btns:
                b.hide()
        else:
            self.port_sub.setText("Empty · %s edge · a module %s and stops "
                                  "when its pins are seated." % (port.edge, axis))
            self.occ_row.hide()
            self.list_label.show()
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
            FreeCAD.setActiveTransaction("Add %s" % name)
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
                      lambda: self._after_add(doc, oname))

    def _after_add(self, doc, oname):
        plan = self._plans.get(_doc_uid(doc))
        if plan is not None:
            plan.slide_done()           # the next settled poll frames the seated board
        self.refresh()
        if doc.getObject(oname) is not None:
            self._show_check(doc=doc, only=oname)

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
            res = ports_mod.check(doc, only=[only] if only else None)
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
            label = self._short(o) if o is not None else name
            cells, whys = [], []
            for key in CHECK_ORDER:
                r = verdicts.get(key) or {}
                text, tok = verdict_words(key, r, name_of)
                cells.append("<span style='color:%s;font-weight:600'>%s</span>"
                             % (t[tok], html.escape(text)))
                why = fail_why(key, r, name_of)
                if why:
                    whys.append("<span style='color:%s'>%s</span>"
                                % (t["muted"], html.escape(why)))
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
    def _offer_undo(self, doc, txn, shown):
        self._undo = (doc, doc.Name, txn, shown)
        self.undo_text.setText("Removed %s  ·" % shown)
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
            self._show_error("%s can no longer be put back from here, because "
                             "the document has changed since. Use Edit > Undo "
                             "instead." % shown)
            return
        try:
            doc.undo()
            doc.recompute()
        except Exception as exc:                       # noqa: BLE001
            _log("undo remove: %r" % (exc,))
            self._show_failure(exc, action="putting back")
            return
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
        self.map.update()
