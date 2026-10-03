"""shell — the Atech Atelier window, laid over FreeCAD's main window.

What it builds while the agent workbench is active (and takes down again on
deactivate, so other workbenches get FreeCAD's normal chrome). The sidebar
itself - chat transcript, workspace, Claude session, running turn - is built
ONCE and only hidden on deactivate (R18): deleting it took its running
worker QThreads with it and aborted FreeCAD.

    top bar     the menu bar restyled as a 44 px app bar: mark + wordmark on
                the left, the menus, quick actions on the right. The menus
                stay real FreeCAD menus, so every command and shortcut works.
    sidebar     ONE left dock with a segmented Chat | Model switch. The Model
                page is FreeCAD's own tree + property view, re-parented, not
                re-implemented.
    view bar    a floating pill over the 3D view: fit, standard views, spin,
                add-view-to-chat, and ask-about-this-view.
    empty state centred in the viewport when no document is open.
    tasks       FreeCAD's Tasks dock, pinned to the right instead of floating
                over the model.

Nothing here touches geometry. Styles come from style.py's tokens.

Upkeep is event-driven (S03): toolbars re-hide on their own Show event
(chrome.py), the status mark on the status bar's ChildAdded, the overlay on
MDI resize / sub-window changes, the Tasks panel on the TaskView stack
changing. A slow safety tick (SAFETY_TICK_MS) backs them up.
"""
import os
import sys
import traceback

from PySide6 import QtCore, QtGui, QtWidgets

from . import chrome, style

SIDEBAR_NAME = "AtechSidebar"
SIDEBAR_WIDTH = 380
SIDEBAR_NARROW = 300        # the sidebar below SMALL_WINDOW_PX (R84)
SMALL_WINDOW_PX = 1000
PILL_ICONS_PX = 600         # below this viewport width the pill is icons only
SAFETY_TICK_MS = 3000       # was a 600 ms poll doing everything (S03)
NARROW_PX = 700             # below this the start cards wrap (R34)

_QUIT_HOOKED = False
_S = {}          # the live chrome: what we changed this activation, to restore
_KEEP = {}       # built once and kept across switches: dock, body, chat (R18)


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[AcadAgent shell] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def _one_write_excepthook(etype, value, tb):
    """sys.excepthook that writes a traceback in ONE sys.stderr.write (R172).

    Under the GUI, sys.stderr is FreeCAD's OutputStderr: every write() is
    one Console error, and every Console error is one entry on the status
    bar's notification bell. CPython's own hook writes a traceback in
    pieces - MEASURED on the bundled Python 3.11 / PySide6 6.8.3: an
    exception in a Qt slot is 25 writes, 8 of them non-blank ("Traceback",
    each File line, the source line, "^", the type, ":", the message),
    so each slot error put 8 fragments on the bell. Dogfood S4-2's 32 were
    4 such tracebacks (raised in the dogfood harness's own build hook; the
    GUI's stderr for that cycle holds no Studio warning or error). One write = one bell entry holding the whole
    traceback; the Report view text is unchanged."""
    try:
        sys.stderr.write("".join(traceback.format_exception(etype, value, tb)))
    except Exception:                                  # noqa: BLE001
        sys.__excepthook__(etype, value, tb)


def hook_tracebacks():
    """Install _one_write_excepthook. Idempotent. Another addon's hook is
    left alone (returns False): it was set on purpose and replacing it
    would silently change its behaviour."""
    if sys.excepthook is _one_write_excepthook:
        return True
    if sys.excepthook is not sys.__excepthook__:
        return False
    sys.excepthook = _one_write_excepthook
    return True


def unhook_tracebacks():
    """Undo hook_tracebacks() on uninstall, so a deactivated Studio leaves
    FreeCAD's Python as it found it. Only our own hook is removed."""
    if sys.excepthook is _one_write_excepthook:
        sys.excepthook = sys.__excepthook__
        return True
    return False


def _mw():
    import FreeCADGui
    return FreeCADGui.getMainWindow()


def _find_dock(mw, *names):
    for n in names:
        d = mw.findChild(QtWidgets.QDockWidget, n)
        if d is not None:
            return d
    return None


# ------------------------------------------------------------------- QSS
TOPBAR_QSS = """
QMenuBar {{
    background: {panel}; border: none; border-bottom: 1px solid {line};
    padding: 6px 10px; font-family: {UI}; font-size: 13px; color: {muted};
    min-height: 32px;
}}
QMenuBar::item {{ background: transparent; padding: 6px 10px; border-radius: 8px; color: {muted}; }}
QMenuBar::item:selected {{ background: {hover}; color: {text}; }}
QMenuBar::item:pressed {{ background: {hover}; color: {text}; }}
QMenu {{
    background: {panel}; border: 1px solid {line}; border-radius: 10px;
    padding: 6px; font-family: {UI}; font-size: 13px; color: {text};
}}
QMenu::item {{ padding: 6px 28px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {hover}; color: {text}; }}
QMenu::item:disabled {{ color: {dim}; }}
QMenu::separator {{ height: 1px; background: {line}; margin: 5px 8px; }}
#Wordmark {{ color: {text}; font-family: 'Sen', {UI}; font-size: 15px; font-weight: 700; }}
#PoweredBy {{ color: {muted}; font-family: {UI}; font-size: 11px; }}
#Divider {{ background: {line}; }}
#TopBtn {{
    background: transparent; border: none; border-radius: 8px;
    padding: 6px 10px; color: {muted}; font-family: {UI}; font-size: 12px;
}}
#TopBtn:hover {{ background: {hover}; color: {text}; }}
#TopBtn:checked {{ background: {hover}; color: {text}; }}
#TopBtn::menu-indicator {{ image: none; width: 0; }}
"""

SIDEBAR_QSS = """
#SidebarBody {{ background: {panel}; border-right: 1px solid {line}; }}
#Segment {{ background: {track}; border-radius: 10px; }}
#SegBtn {{
    background: transparent; border: none; border-radius: 8px;
    color: {muted}; font-family: {UI}; font-size: 12px; font-weight: 600;
    padding: 6px 10px;
}}
#SegBtn:hover {{ color: {text}; }}
#SegBtn:checked {{ background: {panel}; color: {text}; border: 1px solid {line}; }}

#ModelPage {{ background: {panel}; }}
#ModelHint {{ color: {muted}; font-family: {UI}; font-size: 12px; }}
#ModelPage QTreeView, #ModelPage QTreeWidget {{
    background: {panel}; border: none; font-family: {UI}; font-size: 13px;
    color: {text}; outline: 0; show-decoration-selected: 0;
}}
#ModelPage QTreeView::item {{ padding: 4px 2px; border-radius: 6px; }}
#ModelPage QTreeView::item:hover {{ background: {hover}; }}
#ModelPage QTreeView::item:selected {{ background: {bubble}; color: {text}; }}
#ModelPage QHeaderView::section {{
    background: {panel}; color: {dim}; border: none;
    border-bottom: 1px solid {line}; padding: 6px 8px; font-size: 11px;
}}
#ModelPage QSplitter::handle {{ background: {line}; height: 1px; }}
#ModelPage QTabBar::tab {{
    background: transparent; color: {muted}; border: none; padding: 7px 12px;
    font-family: {UI}; font-size: 12px; margin: 0;
}}
#ModelPage QTabBar::tab:selected {{ color: {text}; border-bottom: 2px solid {text}; }}
#ModelPage QTabWidget::pane {{ border: none; border-top: 1px solid {line}; }}
#ModelPage QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
#ModelPage QScrollBar::handle:vertical {{ background: {line_strong}; border-radius: 3px; min-height: 30px; }}
#ModelPage QScrollBar::add-line, #ModelPage QScrollBar::sub-line {{ height: 0; width: 0; }}
"""

VIEWBAR_QSS = """
#ViewBar {{ background: {panel}; border: 1px solid {line}; border-radius: 21px; }}
#VBtn {{
    background: transparent; border: none; border-radius: 15px;
    padding: 0 11px; min-height: 30px; max-height: 30px;
    color: {muted}; font-family: {UI}; font-size: 12px; font-weight: 500;
}}
#VBtn:hover {{ background: {hover}; color: {text}; }}
#VBtn:checked {{ background: {hover}; color: {text}; }}
#VSep {{ background: {line}; }}
#VPrimary {{
    background: {btn_bg}; color: {btn_text}; border: none; border-radius: 15px;
    padding: 0 14px 0 11px; min-height: 30px; max-height: 30px;
    font-family: {UI}; font-size: 12px; font-weight: 600;
}}
#VPrimary:hover {{ background: {btn_bg_hover}; }}
"""

EMPTY_QSS = """
#EmptyView {{ background: transparent; }}
#EmptyTitle {{ color: {text}; font-family: {UI}; font-size: 24px; font-weight: 600; }}
#EmptySub {{ color: {muted}; font-family: {UI}; font-size: 13px; }}
#EmptyCredit {{ color: {muted}; font-family: {UI}; font-size: 11px; }}
#StartCard {{
    background: {panel}; border: 1px solid {line}; border-radius: 16px;
}}
#StartCard:hover {{ border-color: {line_strong}; background: {card}; }}
#CardTitle {{ color: {text}; font-family: {UI}; font-size: 13px; font-weight: 600; }}
#CardSub {{ color: {muted}; font-family: {UI}; font-size: 12px; }}
#CardIcon {{ background: {bubble}; border-radius: 10px; }}
"""

CHROME_QSS = """
QMdiArea {{ background: {base}; }}
QMdiArea QTabBar {{ background: {panel}; border: none; border-top: 1px solid {line}; }}
QMdiArea QTabBar::tab {{
    background: transparent; color: {muted}; border: none; border-radius: 8px;
    padding: 5px 12px; margin: 5px 2px; font-family: {UI}; font-size: 12px;
}}
QMdiArea QTabBar::tab:selected {{ background: {hover}; color: {text}; }}
QMdiArea QTabBar::tab:hover {{ color: {text}; }}
QMdiArea QTabBar::close-button {{
    image: url("{close_icon}"); subcontrol-position: right; margin-left: 6px;
    border-radius: 4px; padding: 1px;
}}
QMdiArea QTabBar::close-button:hover {{ background: {line}; }}
"""

MAIN_QSS = """
QMainWindow::separator {{ background: {line}; width: 1px; height: 1px; }}
QMainWindow::separator:hover {{ background: {line_strong}; }}
"""

STATUS_BTN_QSS = """
QPushButton {{
    background: transparent; border: none; border-radius: 6px; color: {muted};
    font-family: {UI}; font-size: 11px; padding: 2px 8px; min-height: 20px;
}}
QPushButton:hover {{ background: {hover}; color: {text}; }}
QPushButton::menu-indicator {{ image: none; width: 0; }}
"""

STATUS_H = 27          # 26 px min/max-height in STATUS_QSS + 1 px top border
STATUS_QSS = """
QStatusBar {{
    background: {panel}; border-top: 1px solid {line}; color: {muted};
    font-family: {UI}; font-size: 11px; min-height: 26px; max-height: 26px;
}}
QStatusBar QLabel {{ color: {muted}; font-size: 11px; }}
QStatusBar QPushButton, QStatusBar QToolButton {{
    background: transparent; border: none; color: {muted}; font-size: 11px; padding: 2px 8px;
}}
QStatusBar QPushButton:hover, QStatusBar QToolButton:hover {{ color: {text}; }}
QStatusBar::item {{ border: none; }}
"""


# ---------------------------------------------------------------- widgets
ASK_TEXT = "Ask about this view"


def icon_label(text):
    """Label for a button that also has an icon. Qt's style leaves 2-3 px
    between icon and text (measured on the Workbench / Terminal buttons,
    R59); one leading space brings it to the 5-6 px the rest of the chrome
    uses. The accessible name stays the bare text."""
    return (" " + text) if text else ""


class _NoMnemonicStyle(QtWidgets.QProxyStyle):
    """Menu titles without the underlined accelerator letter; Alt still
    works, the underline is just not drawn in an app bar."""

    def styleHint(self, hint, opt=None, widget=None, ret=None):  # noqa: N802
        if hint == QtWidgets.QStyle.SH_UnderlineShortcut:
            return 0
        return super().styleHint(hint, opt, widget, ret)


class ClickCard(QtWidgets.QFrame):
    clicked = QtCore.Signal()

    def __init__(self, icon_name, title, sub, parent=None):
        super().__init__(parent)
        self.setObjectName("StartCard")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WA_Hover, True)
        self.setFixedSize(210, 150)
        self._compact = False
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(4)
        self.ico = QtWidgets.QLabel()
        self.ico.setObjectName("CardIcon")
        self.ico.setFixedSize(36, 36)
        self.ico.setAlignment(QtCore.Qt.AlignCenter)
        self._icon_name = icon_name
        lay.addWidget(self.ico)
        self._gap = QtWidgets.QSpacerItem(0, 10)
        lay.addItem(self._gap)
        t = QtWidgets.QLabel(title)
        t.setObjectName("CardTitle")
        lay.addWidget(t)
        s = QtWidgets.QLabel(sub)
        s.setObjectName("CardSub")
        s.setWordWrap(True)
        lay.addWidget(s)
        lay.addStretch(1)

    def set_compact(self, on):
        """Short card for small viewports: no icon tile, 100 px tall."""
        if on == self._compact:
            return
        self._compact = on
        self.ico.setVisible(not on)
        self._gap.changeSize(0, 0 if on else 10)
        # changeSize() does not invalidate the layout's cached geometry:
        # without this the 10 px gap stays at 0 after a compact -> full
        # round trip (title 10 px too high) until something else relayouts.
        self.layout().invalidate()
        self.setFixedSize(210, 100 if on else 150)

    def restyle(self):
        self.ico.setPixmap(style.icon(self._icon_name,
                                      style.tokens()["text"], 18).pixmap(18, 18))

    def mouseReleaseEvent(self, ev):                   # noqa: N802
        if ev.button() == QtCore.Qt.LeftButton and self.rect().contains(ev.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(ev)


class EmptyView(QtWidgets.QWidget):
    """Centred in the viewport when nothing is open: the first move."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EmptyView")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(0)
        lay.addStretch(1)
        self.mark = QtWidgets.QLabel()
        self.mark.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.mark)
        self._sp_mark = QtWidgets.QSpacerItem(0, 18)
        lay.addItem(self._sp_mark)
        t = QtWidgets.QLabel("Start a design")
        t.setObjectName("EmptyTitle")
        t.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(t)
        self.title = t
        self._sp_sub = QtWidgets.QSpacerItem(0, 6)
        lay.addItem(self._sp_sub)
        s = QtWidgets.QLabel("Open a model, or describe one to the agent on the left.")
        s.setObjectName("EmptySub")
        s.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(s)
        self.sub = s
        self._sp_cards = QtWidgets.QSpacerItem(0, 28)
        lay.addItem(self._sp_cards)
        self._fit = None
        self.grid = QtWidgets.QGridLayout()
        self.grid.setSpacing(12)
        self.grid.setAlignment(QtCore.Qt.AlignCenter)
        self.cards = [
            ClickCard("cube", "Sample crane",
                      "Open a measured crane assembly."),
            ClickCard("file-plus", "New document", "An empty model to build into."),
            ClickCard("folder", "Open file", "FCStd, STEP, IGES or BREP."),
        ]
        self._cols = None
        self._has_crane = None
        lay.addLayout(self.grid)
        lay.addSpacing(18)
        c = QtWidgets.QLabel()
        c.setObjectName("EmptyCredit")
        c.setAlignment(QtCore.Qt.AlignCenter)
        c.setOpenExternalLinks(False)
        c.linkActivated.connect(_open_credits)
        lay.addWidget(c)
        self.credit = c
        lay.addStretch(2)
        self.cards[0].clicked.connect(_open_reference)
        self.cards[1].clicked.connect(_new_document)
        self.cards[2].clicked.connect(_open_file)
        self.refresh_cards()

    def shown_cards(self):
        return [c for c in self.cards if c is not self.cards[0]
                or self._has_crane]

    def refresh_cards(self):
        """Offer the sample crane only when this installation has it (R55):
        a card that can only answer 'not available' is a broken promise."""
        try:
            from . import viewport
            has = bool(viewport.crane_parts())
        except Exception as exc:                       # noqa: BLE001
            _log("crane parts: %r" % (exc,))
            has = False
        if has == self._has_crane:
            return
        self._has_crane = has
        cols, self._cols = self._cols or 3, None
        self._layout_cards(cols)
        # AFTER the layout has parented the card: setVisible(True) on a
        # parentless widget (the first call, from __init__) shows it as a
        # top-level window of its own.
        self.cards[0].setVisible(has)
        self._fit = None
        self._fit_height(self.height())

    def columns_for(self, width):
        """3 cards in a row from NARROW_PX up; below it, as many 210 px
        cards as fit (12 px gaps, 12 px margins), and short cards."""
        if width >= NARROW_PX:
            return 3
        return max(1, min(3, (width - 24 + 12) // (210 + 12)))

    def _layout_cards(self, cols):
        if cols == self._cols:
            return
        self._cols = cols
        for c in self.cards:
            self.grid.removeWidget(c)
        shown = self.shown_cards()
        per_row = max(1, min(cols, len(shown)))
        for i, c in enumerate(shown):
            self.grid.addWidget(c, i // per_row, i % per_row)
        for c in self.cards:
            c.set_compact(cols < 3)
        self._fit = None

    def _fit_height(self, h):
        """A short viewport (terminal open at 900x600: ~245 px) cannot hold
        the mark, the subtitle and two rows of fixed-size cards; squeezed,
        the second row drew over the first (GUI round 4). Drop the mark,
        then the subtitle, then whole card rows that do not fit — the same
        actions stay in the File menu and the chat's own buttons."""
        shown = self.shown_cards()
        if not shown:
            return
        per_row = max(1, min(self._cols or 3, len(shown)))
        rows = (len(shown) + per_row - 1) // per_row
        card_h = shown[0].height()
        m = self.layout().contentsMargins()
        avail = h - m.top() - m.bottom()
        head = self.title.sizeHint().height()
        mark_h = self.mark.sizeHint().height() + 18
        sub_h = 6 + self.sub.sizeHint().height() + 28

        def need(r, mark, sub):
            return (head + (mark_h if mark else 0) + (sub_h if sub else 12)
                    + r * card_h + max(0, r - 1) * self.grid.spacing())

        mark = need(rows, True, True) <= avail
        sub = mark or need(rows, False, True) <= avail
        fit = rows
        while fit > 0 and need(fit, mark, sub) > avail:
            fit -= 1
        key = (mark, sub, fit, per_row, len(shown))
        if key == self._fit:
            return
        self._fit = key
        self.mark.setVisible(mark)
        self._sp_mark.changeSize(0, 18 if mark else 0)
        self.sub.setVisible(sub)
        self._sp_sub.changeSize(0, 6 if sub else 0)
        self._sp_cards.changeSize(0, 28 if sub else 12)
        for i, c in enumerate(shown):
            c.setVisible(i < fit * per_row)
        self.layout().invalidate()

    def resizeEvent(self, ev):                         # noqa: N802
        self._layout_cards(self.columns_for(ev.size().width()))
        self._fit_height(ev.size().height())
        super().resizeEvent(ev)

    def restyle(self):
        self.refresh_cards()
        self.setStyleSheet(style.qss(EMPTY_QSS))
        self.credit.setText(
            'Atech Atelier, powered by FreeCAD \u00b7 <a href="credits" '
            'style="color:%s; text-decoration:none;">Credits</a>'
            % style.tokens()["accent"])
        pm = style.logo_pixmap(40)
        if pm is not None:
            self.mark.setPixmap(pm)
        for c in self.cards:
            c.restyle()
        self._fit = None            # the mark's height is known only now
        self._fit_height(self.height())


class ViewBar(QtWidgets.QFrame):
    """The floating pill over the 3D view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ViewBar")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(2)
        self._icons = []

        from . import viewport
        self.btn_fit = self._btn("", "fit", "Fit the model to the view", viewport.fit_all)
        lay.addWidget(self.btn_fit)
        self._named = [self._sep()]
        for label, fn in (("Iso", viewport.axonometric), ("Front", viewport.view_front),
                          ("Top", viewport.view_top), ("Right", viewport.view_right)):
            self._named.append(self._btn(label, None, "%s view" % label, fn))
        for w in self._named:
            lay.addWidget(w)
        lay.addWidget(self._sep())
        self.btn_spin = self._btn("", "rotate", "Spin the model", None)
        self.btn_spin.setCheckable(True)
        self.btn_spin.toggled.connect(self._on_spin)
        lay.addWidget(self.btn_spin)
        self.btn_shot = self._btn("", "camera", "Add this view to the chat", _add_view)
        lay.addWidget(self.btn_shot)
        lay.addSpacing(4)
        self.btn_ask = QtWidgets.QPushButton(icon_label(ASK_TEXT))
        self.btn_ask.setAccessibleName(ASK_TEXT)
        self.btn_ask.setObjectName("VPrimary")
        self.btn_ask.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_ask.setIconSize(QtCore.QSize(14, 14))
        self.btn_ask.setToolTip("Capture the view and ask the agent about it")
        self.btn_ask.clicked.connect(_ask_view)
        lay.addWidget(self.btn_ask)
        self.level = 0

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QtGui.QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)

    def _btn(self, text, icon_name, tip, fn):
        b = QtWidgets.QPushButton(text)
        b.setObjectName("VBtn")
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.setIconSize(QtCore.QSize(16, 16))
        if icon_name:
            self._icons.append((b, icon_name))
            b.setFixedWidth(34)
        if fn is not None:
            b.clicked.connect(lambda _=False, f=fn: _safe(f))
        return b

    def _sep(self):
        s = QtWidgets.QFrame()
        s.setObjectName("VSep")
        s.setFixedSize(1, 18)
        return s

    def _on_spin(self, on):
        from . import viewport
        _safe(lambda: viewport.spin(on))

    def set_level(self, level):
        """0 full; 1 the Ask button shows its icon only; 2 the named views
        (Iso/Front/Top/Right) go as well. For narrow viewports (R34)."""
        if level == self.level:
            return
        self.level = level
        self.btn_ask.setText("" if level >= 1 else icon_label(ASK_TEXT))
        for w in self._named:
            w.setVisible(level < 2)
        self.adjustSize()

    def restyle(self):
        self.setStyleSheet(style.qss(VIEWBAR_QSS))
        t = style.tokens()
        for b, n in self._icons:
            b.setIcon(style.icon(n, t["muted"], 16))
        self.btn_ask.setIcon(style.icon("sparkles", t["btn_text"], 14))
        self.adjustSize()


class Overlay(QtCore.QObject):
    """Keeps the view bar and empty state positioned over the MDI area."""

    _EVENTS = (QtCore.QEvent.Resize, QtCore.QEvent.Show,
               QtCore.QEvent.ChildAdded, QtCore.QEvent.ChildRemoved)

    _BOX_EVENTS = (QtCore.QEvent.Show, QtCore.QEvent.Hide,
                   QtCore.QEvent.Resize, QtCore.QEvent.Move)

    def __init__(self, mdi, on_docs=None):
        super().__init__(mdi)
        self.mdi = mdi
        self.bar = ViewBar(mdi)
        self.empty = EmptyView(mdi)
        self._queued = False
        self._key = None
        self._dead = False
        self._boxes = []
        self._on_docs = on_docs
        mdi.installEventFilter(self)
        mdi.viewport().installEventFilter(self)   # sub-windows live here
        mdi.subWindowActivated.connect(self._queue)
        self.place()

    def eventFilter(self, obj, ev):                    # noqa: N802
        t = ev.type()
        if t in self._EVENTS or (obj in self._boxes and t in self._BOX_EVENTS):
            self._queue()
        return False

    def overlay_boxes(self):
        """FreeCAD's overlay panels (Gui::OverlayTabWidget): Tasks, Report
        view... drawn OVER the 3D view. Each is watched once, so the bar
        moves when one opens or closes (R58)."""
        try:
            win = self.mdi.window()
            found = [w for w in win.findChildren(QtWidgets.QTabWidget)
                     if w.metaObject().className() == "Gui::OverlayTabWidget"]
        except RuntimeError:
            return []
        for b in found:
            if b not in self._boxes:
                b.installEventFilter(self)
                self._boxes.append(b)
        return found

    def free_rect(self, vp):
        """The part of the viewport (MDI coordinates) not covered by a
        visible overlay panel. A panel on the right pulls the right edge in,
        and so on; a top panel leaves the bar alone."""
        left, right = vp.left(), vp.right()
        bottom = vp.bottom()
        cx = vp.center().x()
        for b in self.overlay_boxes():
            try:
                if not b.isVisible() or b.width() <= 0:
                    continue
                tl = self.mdi.mapFromGlobal(b.mapToGlobal(QtCore.QPoint(0, 0)))
                r = QtCore.QRect(tl, b.size())
            except RuntimeError:
                continue
            if not r.intersects(vp):
                continue
            if r.width() >= vp.width() * 0.8 and r.top() > vp.center().y():
                bottom = min(bottom, r.top() - 1)      # a bottom panel
            elif r.center().x() >= cx:
                right = min(right, r.left() - 1)
            else:
                left = max(left, r.right() + 1)
        if right - left < 120:                         # nothing sensible
            left, right = vp.left(), vp.right()        # left: use it all
        return QtCore.QRect(QtCore.QPoint(left, vp.top()),
                            QtCore.QPoint(right, bottom))

    def _queue(self, *_):
        if not self._queued:
            self._queued = True
            QtCore.QTimer.singleShot(0, self.place)

    def place(self, force=True):
        """Position the bar / empty state. The safety tick passes
        force=False and returns early when nothing it depends on moved."""
        self._queued = False
        if self._dead:                                 # a queued place()
            return                                     # after dispose()
        try:
            vp = self.mdi.viewport().geometry()
        except RuntimeError:                           # torn down
            return
        has_doc = bool(self.mdi.subWindowList())
        free = self.free_rect(vp) if has_doc else vp
        key = (vp.x(), vp.y(), vp.width(), vp.height(), has_doc,
               free.x(), free.width(), free.height())
        if not force and key == self._key:
            return
        self._key = key
        self.bar.setVisible(has_doc)
        self.empty.setVisible(not has_doc)
        if self._on_docs is not None:
            try:
                self._on_docs()
            except Exception as exc:                   # noqa: BLE001
                _log("docs hook: %r" % (exc,))
        if has_doc:
            avail = max(0, free.width() - 24)
            # Icons only in a small viewport (R84): the pill spanned the
            # whole view at 900x600 and covered the model.
            first = 2 if vp.width() < PILL_ICONS_PX else 0
            for level in range(first, 3):
                self.bar.set_level(level)
                self.bar.adjustSize()
                if self.bar.sizeHint().width() <= avail:
                    break
            sz = self.bar.sizeHint()
            w = min(sz.width(), avail) if avail else sz.width()
            self.bar.setGeometry(free.x() + (free.width() - w) // 2,
                                 free.y() + free.height() - sz.height() - 18,
                                 w, sz.height())
            self.bar.raise_()
        else:
            self.empty.setGeometry(vp)
            self.empty.raise_()

    def reserve(self):
        """Fraction of the viewport's height, from the bottom, that the bar
        covers (plus an 8 px breath), for fit_all (R82). 0.0 without a bar."""
        try:
            if not self.bar.isVisible():
                return 0.0
            vp = self.mdi.viewport().geometry()
            if vp.height() <= 0:
                return 0.0
            px = vp.y() + vp.height() - self.bar.geometry().top() + 8
            return max(0.0, min(0.5, px / float(vp.height())))
        except RuntimeError:
            return 0.0

    def dispose(self):
        """Take the view bar and empty state down (on deactivate)."""
        self._dead = True
        for obj in [self.mdi, self.mdi.viewport()] + self._boxes:
            try:
                obj.removeEventFilter(self)
            except RuntimeError:
                pass
        try:
            self.mdi.subWindowActivated.disconnect(self._queue)
        except (RuntimeError, TypeError):
            pass
        for w in (self.bar, self.empty):
            w.hide()
            w.deleteLater()
        self.deleteLater()


class Sidebar(QtWidgets.QWidget):
    """Segmented Chat | Model switch over a stack."""

    def __init__(self, chat, model_widget, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarBody")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(head)
        hl.setContentsMargins(12, 12, 12, 8)
        seg = QtWidgets.QFrame()
        seg.setObjectName("Segment")
        sl = QtWidgets.QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        self.group = QtWidgets.QButtonGroup(self)
        self.btn_chat = self._seg("Chat", 0)
        self.btn_model = self._seg("Model", 1)
        self.btn_modules = self._seg("Modules", 2)
        sl.addWidget(self.btn_chat)
        sl.addWidget(self.btn_model)
        sl.addWidget(self.btn_modules)
        hl.addWidget(seg, 1)
        lay.addWidget(head)

        self.stack = QtWidgets.QStackedWidget()
        self.chat = chat
        self.stack.addWidget(chat)
        self.model_page = QtWidgets.QWidget()
        self.model_page.setObjectName("ModelPage")
        self.model_page.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._model_lay = QtWidgets.QVBoxLayout(self.model_page)
        self._model_lay.setContentsMargins(4, 0, 4, 0)
        # R57: with no document the tree is an empty pane; say why.
        self.model_hint = QtWidgets.QLabel(
            "No document is open.\nOpen a file or start a new document, "
            "and its parts are listed here.")
        self.model_hint.setObjectName("ModelHint")
        self.model_hint.setAlignment(QtCore.Qt.AlignCenter)
        self.model_hint.setWordWrap(True)
        self.model_hint.setContentsMargins(24, 24, 24, 24)
        self._model_lay.addWidget(self.model_hint, 1)
        self._has_doc = None
        self.model_widget = None
        if model_widget is not None:
            self.set_model_widget(model_widget)
        self.stack.addWidget(self.model_page)
        from .modules_page import ModulesPage
        self.modules_page = ModulesPage()
        self.stack.addWidget(self.modules_page)
        lay.addWidget(self.stack, 1)
        self.btn_chat.setChecked(True)
        self.group.idClicked.connect(self.stack.setCurrentIndex)
        self.group.idClicked.connect(lambda _i: self.sync_model_hint())
        self.sync_model_hint()

    def _seg(self, text, idx):
        b = QtWidgets.QPushButton(icon_label(text))
        b.setAccessibleName(text)
        b.setObjectName("SegBtn")
        b.setCheckable(True)
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setIconSize(QtCore.QSize(14, 14))
        self.group.addButton(b, idx)
        return b

    def set_model_widget(self, w):
        """Host FreeCAD's tree + property view on the Model page."""
        self.model_widget = w
        self._model_lay.addWidget(w, 1)
        # QDockWidget.setWidget() hid it on the way out; bring it back.
        w.show()
        # GUI r9_07: FreeCAD splits tree / properties about 50:50, so the
        # 25-part sample crane scrolled after 13 rows above an empty
        # property editor. Give the tree two thirds while hosted here;
        # take_model_widget() hands FreeCAD its own split back.
        self._model_split = None
        try:
            sp = w.findChild(QtWidgets.QSplitter)
            if sp is not None and sp.orientation() == QtCore.Qt.Vertical \
                    and sp.count() == 2:
                old = sp.sizes()
                total = sum(old) or 780
                sp.setSizes([total * 2 // 3, total - total * 2 // 3])
                # At startup the window is not shown yet and the split
                # reads [0, 0] (measured r9): hand back FreeCAD's even
                # split then, never the two thirds set here.
                self._model_split = (sp, old if sum(old) else None)
        except Exception as exc:                       # noqa: BLE001
            _log("model split: %r" % (exc,))
        self._has_doc = None
        self.sync_model_hint()

    def take_model_widget(self):
        """Release it (the caller re-parents it back into FreeCAD's dock)."""
        w, self.model_widget = self.model_widget, None
        split = getattr(self, "_model_split", None)
        self._model_split = None
        if split is not None:
            try:
                sp, old = split
                if not old:
                    # Hidden now too, sizes [0, 0]: equal weights, which
                    # QSplitter scales to its height once it is shown.
                    total = sum(sp.sizes()) or 2
                    old = [total // 2, total - total // 2]
                sp.setSizes(old)
            except RuntimeError:                       # splitter deleted
                pass
        if w is not None:
            self._model_lay.removeWidget(w)
            w.show()                   # it may have been hidden behind the hint
        return w

    def sync_model_hint(self):
        """Hint instead of an empty tree while no document is open (R57)."""
        try:
            import FreeCAD
            has = bool(FreeCAD.listDocuments())
        except Exception:                              # noqa: BLE001
            has = True                                 # cannot tell: no hint
        if has == self._has_doc:
            return
        self._has_doc = has
        self.model_hint.setVisible(not has)
        if self.model_widget is not None:
            self.model_widget.setVisible(has)

    def show_page(self, idx):
        self.group.button(idx).setChecked(True)
        self.stack.setCurrentIndex(idx)
        self.sync_model_hint()

    def restyle(self):
        self.setStyleSheet(style.qss(SIDEBAR_QSS))
        t = style.tokens()
        self.btn_chat.setIcon(style.icon("chat", t["text"], 14))
        self.btn_model.setIcon(style.icon("layers", t["text"], 14))
        self.btn_modules.setIcon(style.icon("cube", t["text"], 14))
        self.chat.restyle()
        self.modules_page.restyle()


# -------------------------------------------------------------- actions
def _safe(fn):
    try:
        fn()
    except Exception as exc:                           # noqa: BLE001
        _log("action failed: %r" % (exc,))


def _sentence(exc):
    s = ("%s" % (exc,)).strip().rstrip(".")
    return (s[:1].upper() + s[1:] + ".") if s else ""


def _notify(title, body, exc=None):
    """A start card or top-bar action failed: say so in the chat, in words
    (R27). The raw exception goes to the Report view and the notice's
    collapsed detail, never into the title."""
    if exc is not None:
        _log("%s: %r" % (title, exc))
    p = chat_panel()
    if p is None:
        return
    try:
        if _S:
            show_chat()
        p.show_notice(title, body,
                      detail=("%s" % (exc,)) if exc is not None else None)
    except Exception as exc2:                          # noqa: BLE001
        _log("notice failed: %r" % (exc2,))


def _open_reference():
    from . import viewport
    try:
        viewport.open_reference_model()
    except RuntimeError as exc:
        # viewport raises RuntimeError only with a user-facing reason.
        _notify("Sample crane not available", _sentence(exc))
    except Exception as exc:                           # noqa: BLE001
        _notify("Could not open the sample crane",
                "Loading it failed. The details are in the Report view.", exc)


def _new_document():
    try:
        import FreeCAD
        FreeCAD.newDocument()
    except Exception as exc:                           # noqa: BLE001
        _notify("Could not create a document",
                "FreeCAD refused a new document. The details are in the "
                "Report view.", exc)


def _open_file():
    try:
        import FreeCADGui
        FreeCADGui.runCommand("Std_Open")
    except Exception as exc:                           # noqa: BLE001
        _notify("Could not open the file dialog",
                "The details are in the Report view.", exc)


def _add_view():
    p = chat_panel()
    if p is not None:
        show_chat()
        p._on_capture()


def _ask_view():
    """The view bar's primary button: the question is asked IN THE CHAT
    (R95), with the view captured into the chat workspace as an inline
    shot - not in the Terminal dock, whose transcript users never see."""
    from . import vision
    try:
        vision.ask_in_chat(panel=show_chat())
    except Exception as exc:                           # noqa: BLE001
        _notify("Could not ask about this view",
                "The details are in the Report view.", exc)


def _open_terminal():
    from . import terminal_dock
    try:
        terminal_dock.ensure_terminal()
    except Exception as exc:                           # noqa: BLE001
        _notify("Could not open a terminal",
                "The details are in the Report view.", exc)


def keep_workspaces():
    """The open chat's workspace folders, which 'Clear old chat workspaces'
    must never delete (R69). () when there is no chat panel yet."""
    p = chat_panel()
    if p is None:
        return ()
    try:
        return tuple(w for w in (p.workspaces() or ()) if w)
    except Exception as exc:                           # noqa: BLE001
        _log("workspaces: %r" % (exc,))
        return ()


def _open_settings():
    from . import settings
    try:
        settings.open_dialog(chat_panel(), keep_workspaces=keep_workspaces())
    except Exception as exc:                           # noqa: BLE001
        _notify("Could not open settings",
                "The details are in the Report view.", exc)


def _fill_workbench_menu(menu):
    """Every workbench, by its menu name, so switching out of Atech needs no
    toolbar (R30: the menubar-corner selector is FreeCAD's, and ours sits
    in that corner while Atech is active)."""
    menu.clear()
    try:
        import FreeCADGui
        wbs = FreeCADGui.listWorkbenches()
        cur = FreeCADGui.activeWorkbench().name()
    except Exception as exc:                           # noqa: BLE001
        _log("workbench list: %r" % (exc,))
        return
    for label, key in workbench_rows(wbs):
        act = menu.addAction(label)
        act.setCheckable(True)
        act.setChecked(key == cur)
        act.triggered.connect(lambda _=False, k=key: _activate_workbench(k))


# Not offered in the Workbench menu (R83, dogfood D29): FreeCAD's empty
# "<none>" workbench, and developer tools. FreeCADMCP's workbench is listed
# here while R10 (whether MCP ships) is the owner's open decision; drop it
# from this set if it ships. Keys are listWorkbenches() class names.
HIDDEN_WORKBENCHES = frozenset((
    "NoneWorkbench",               # "<none>"
    "TestWorkbench",               # "Test Framework"
    "FreeCADMCPAddonWorkbench",    # "MCP Addon" (R10 undecided)
))


def workbench_rows(wbs):
    """(label, key) for the Workbench menu, sorted by label, without the
    hidden ones."""
    rows = []
    for key, wb in wbs.items():
        label = getattr(wb, "MenuText", "") or key
        if key in HIDDEN_WORKBENCHES or label.strip() == "<none>":
            continue
        rows.append((label, key))
    return sorted(rows)


def _activate_workbench(key):
    try:
        import FreeCADGui
        FreeCADGui.activateWorkbench(key)
    except Exception as exc:                           # noqa: BLE001
        _notify("Could not switch workbench",
                "The details are in the Report view.", exc)


# ----------------------------------------------------------------- top bar
def _open_credits(_link=None):
    from . import credits
    credits.open_dialog()


def _build_topbar(mw):
    mb = mw.menuBar()
    # FreeCAD's own corner widgets (its menubar toolbar areas, which can hold
    # the workbench selector) are kept and put back on uninstall (R30).
    old = {c: mb.cornerWidget(c)
           for c in (QtCore.Qt.TopLeftCorner, QtCore.Qt.TopRightCorner)}
    left = QtWidgets.QWidget()
    ll = QtWidgets.QHBoxLayout(left)
    ll.setContentsMargins(8, 0, 12, 0)
    ll.setSpacing(9)
    mark = QtWidgets.QLabel()
    word = QtWidgets.QLabel("Atech Atelier")
    word.setObjectName("Wordmark")
    ll.addWidget(mark)
    ll.addWidget(word)
    powered = QtWidgets.QLabel("powered by FreeCAD")
    powered.setObjectName("PoweredBy")
    powered.setToolTip("Credits & open-source licences: Help menu")
    ll.addWidget(powered)
    div = QtWidgets.QFrame()
    div.setObjectName("Divider")
    div.setFixedSize(1, 18)
    ll.addSpacing(8)
    ll.addWidget(div)

    right = QtWidgets.QWidget()
    rl = QtWidgets.QHBoxLayout(right)
    rl.setContentsMargins(0, 0, 6, 0)
    rl.setSpacing(2)
    btns = []
    for text, icon_name, tip, fn in (
            ("Workbench", "layers", "Switch workbench", None),
            ("Terminal", "terminal", "Open a terminal", _open_terminal),
            ("", "settings", "Agent settings", _open_settings)):
        b = QtWidgets.QPushButton(icon_label(text))
        b.setAccessibleName(text or tip)
        b.setObjectName("TopBtn")
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.setIconSize(QtCore.QSize(15, 15))
        if fn is not None:
            b.clicked.connect(fn)
        else:
            menu = QtWidgets.QMenu(b)
            menu.aboutToShow.connect(lambda m=menu: _fill_workbench_menu(m))
            b.setMenu(menu)
        rl.addWidget(b)
        btns.append((b, icon_name))

    for w in (left, right):
        w.setFixedHeight(44)
    for w in old.values():
        if w is not None:
            w.hide()
    mb.setCornerWidget(left, QtCore.Qt.TopLeftCorner)
    mb.setCornerWidget(right, QtCore.Qt.TopRightCorner)
    left.show()
    right.show()
    try:
        st = _NoMnemonicStyle(QtWidgets.QApplication.style().name())
        mb.setStyle(st)
    except Exception as exc:                           # noqa: BLE001
        st = None
        _log("menubar style: %r" % (exc,))
    return {"left": left, "right": right, "mark": mark, "btns": btns,
            "style": st, "old_corners": old, "old_style": None}


def _restore_topbar(mw, tb):
    mb = mw.menuBar()
    for corner, w in tb.get("old_corners", {}).items():
        try:
            mb.setCornerWidget(w, corner)
            if w is not None:
                w.show()
        except RuntimeError:                           # FreeCAD deleted it
            mb.setCornerWidget(None, corner)
    for key in ("left", "right"):
        w = tb.get(key)
        if w is not None:
            w.hide()
            w.deleteLater()
    if tb.get("style") is not None:
        # None = "use the application style". Passing QApplication.style()
        # (a QStyleSheetStyle under a theme) SIGSEGVed in setStyle_helper on
        # the switch to Part, and a later grab() crashed in QMenu::event on
        # the freed proxy (measured 2/2, r1 GUI check). The proxy is kept
        # alive for the session: menus may still hold it until repolished.
        mb.setStyle(None)
        _KEEP.setdefault("old_styles", []).append(tb["style"])


def _restyle_topbar(tb):
    mw = _mw()
    mw.menuBar().setStyleSheet(style.qss(TOPBAR_QSS))
    tb["left"].setStyleSheet(style.qss(TOPBAR_QSS))
    tb["right"].setStyleSheet(style.qss(TOPBAR_QSS))
    pm = style.logo_pixmap(20)
    if pm is not None:
        tb["mark"].setPixmap(pm)
    t = style.tokens()
    for b, n in tb["btns"]:
        b.setIcon(style.icon(n, t["muted"], 15))


# ----------------------------------------------------------------- watcher
class _Watch(QtCore.QObject):
    """One event filter for the event-driven upkeep (S03). Each watched
    object maps to the event types that matter and a callback; callbacks
    are coalesced and run once on the next event-loop pass."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._map = {}
        self._queued = set()

    def watch(self, obj, types, fn):
        self._map[id(obj)] = (obj, frozenset(types), fn)
        obj.installEventFilter(self)

    def unwatch_all(self):
        for obj, _types, _fn in self._map.values():
            try:
                obj.removeEventFilter(self)
            except RuntimeError:
                pass
        self._map.clear()

    def queue(self, fn):
        if fn not in self._queued:
            self._queued.add(fn)
            QtCore.QTimer.singleShot(0, lambda f=fn: self._run(f))

    def _run(self, fn):
        self._queued.discard(fn)
        if _S:
            try:
                fn()
            except Exception as exc:                   # noqa: BLE001
                _log("upkeep: %r" % (exc,))

    def eventFilter(self, obj, ev):                    # noqa: N802
        entry = self._map.get(id(obj))
        if entry is not None and ev.type() in entry[1]:
            self.queue(entry[2])
        return False


def _check_theme():
    """Restyle only when the light/dark decision actually changed (R34):
    our own restyle() fires StyleChange too, and must not loop."""
    if _S and style.mode() != _S.get("mode"):
        _log("theme changed to %s" % style.mode())
        restyle()


def _on_window_event():
    _check_theme()
    _fit_sidebar()
    # A style sheet reload that keeps the mode (no restyle) re-shows the
    # dead sub-windows too (GUI round 5: dark -> dark left the start page on
    # #efefef until the safety tick). Cheap: a walk of the MDI children.
    _hide_dead_subwindows()


def sidebar_width_for(window_width):
    """380 px, or 300 px in a window narrower than 1000 px (R84): at
    900x600 the fixed 380 px took 42 % of the window."""
    return SIDEBAR_NARROW if window_width < SMALL_WINDOW_PX else SIDEBAR_WIDTH


def _fit_sidebar(force=False):
    """Resize the sidebar when the window crosses SMALL_WINDOW_PX (only
    then, so a width the user dragged to is kept otherwise)."""
    dock = _S.get("dock")
    if dock is None:
        return
    mw = _mw()
    want = sidebar_width_for(mw.width())
    if not force and _S.get("sidebar_want") == want:
        return
    _S["sidebar_want"] = want
    # The chat panel asks for 320 px (panel.py), which would hold the dock
    # above 300; its layout itself needs about 210 (measured
    # minimumSizeHint 207 px). Lower the floor to the target, keep theirs.
    chat = _S.get("chat")
    if chat is not None:
        try:
            floor = _KEEP.setdefault("chat_min_width", chat.minimumWidth())
            chat.setMinimumWidth(min(floor, want))
        except RuntimeError:
            pass
    if want == SIDEBAR_NARROW and not force and dock.width() <= want:
        return                                        # already narrower

    def resize():
        if _S.get("dock") is not dock or _S.get("sidebar_want") != want:
            return
        try:
            mw.resizeDocks([dock], [want], QtCore.Qt.Horizontal)
        except Exception as exc:                       # noqa: BLE001
            _log("resizeDocks: %r" % (exc,))
    resize()
    # again once the lowered minimum has reached the layout (measured: the
    # same-pass call stopped at the old 320 px floor)
    QtCore.QTimer.singleShot(0, resize)


def _on_docs_changed():
    body = _S.get("body")
    if body is not None:
        body.sync_model_hint()
    # A view opening or closing is when FreeCAD shows the Tasks overlay
    # without a dialog (R48), whether or not its panel existed at install.
    w = _S.get("watch")
    if w is not None:
        w.queue(_sync_tasks)


def view_reserve():
    """Fraction of the 3D view's height the floating view bar covers, from
    the bottom; viewport.fit_all() keeps it free (R82)."""
    ov = _S.get("overlay")
    return ov.reserve() if ov is not None else 0.0


def _hide_model_dock():
    # FreeCAD restores a saved layout that shows the Model dock; its widget
    # lives in our sidebar now, so the dock would be an empty black panel.
    md = _S.get("model_dock")
    if md is not None and md.isVisible():
        md.hide()


def _on_model_dock_visible(visible):
    w = _S.get("watch")
    if visible and w is not None:
        w.queue(_hide_model_dock)


def _task_view(tasks):
    """FreeCAD's TaskView: a QStackedWidget that changes page whenever a task
    dialog opens or closes (TaskView.cpp showDialog/removeDialog)."""
    for w in tasks.findChildren(QtWidgets.QStackedWidget):
        if w.metaObject().className().endswith("TaskView"):
            return w
    return None


def _on_task_view_changed(*_):
    w = _S.get("watch")
    if w is not None:
        w.queue(_sync_tasks)


# ------------------------------------------------------------------ public
def installed():
    return bool(_S)


def _alive(obj):
    try:
        obj.objectName()
        return True
    except RuntimeError:
        return False


def _ensure_sidebar(mw):
    """The dock, sidebar and chat panel: built once, then reused (R18)."""
    if _KEEP and not _alive(_KEEP["dock"]):
        _KEEP.clear()
    if not _KEEP:
        from .panel import AgentPanel
        chat = AgentPanel()
        body = Sidebar(chat, None)
        dock = QtWidgets.QDockWidget("Atech", mw)
        dock.setObjectName(SIDEBAR_NAME)
        dock.setTitleBarWidget(QtWidgets.QWidget())
        dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        dock.setWidget(body)
        _KEEP.update(dock=dock, body=body, chat=chat)
    return _KEEP["dock"]


def install():
    """Build the shell. Idempotent: a second call just restyles.

    The sidebar is built (or reused) BEFORE any FreeCAD dock is touched, and
    a failure part-way hands everything back through uninstall(), so a
    broken install can no longer leave the Model tree stolen (R18)."""
    hook_tracebacks()                   # R172: one bell entry per traceback
    if _S:
        restyle()
        return _S["dock"]
    mw = _mw()

    # any dock from the previous layout (tabbed Chat) goes
    old = mw.findChild(QtWidgets.QDockWidget, "AcadAgentPanel")
    if old is not None:
        mw.removeDockWidget(old)
        old.deleteLater()

    dock = _ensure_sidebar(mw)
    body = _KEEP["body"]
    _S.update(dock=dock, body=body, chat=_KEEP["chat"])
    try:
        _install_chrome(mw, dock, body)
    except Exception as exc:
        _log("install failed, handing the window back: %r" % (exc,))
        try:
            uninstall()
        except Exception as exc2:                      # noqa: BLE001
            _log("uninstall after failed install: %r" % (exc2,))
        raise
    return dock


def _install_chrome(mw, dock, body):
    watch = _Watch(dock)
    _S["watch"] = watch

    model_dock = _find_dock(mw, "Model", "Combo View")
    _S["model_dock"] = model_dock
    if model_dock is not None:
        # isHidden(), not isVisible(): install() runs from Activated() at
        # startup, before the main window is shown, when isVisible() is False
        # for every widget - measured r1: Part then came up with no Model tree
        # on every switch, and each re-install re-recorded the False.
        _S["model_visible"] = not model_dock.isHidden()
        w = model_dock.widget()
        if w is not None and body.model_widget is None:
            placeholder = QtWidgets.QWidget()
            model_dock.setWidget(placeholder)
            _S["model_placeholder"] = placeholder
            _S["model_widget"] = w
            body.set_model_widget(w)
        model_dock.hide()
        model_dock.toggleViewAction().setEnabled(False)
        model_dock.visibilityChanged.connect(_on_model_dock_visible)

    mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
    dock.show()
    # The sidebar runs full height; a bottom dock (the terminal) spans the
    # viewport only, the way an editor's panel does.
    _S["corner"] = mw.corner(QtCore.Qt.BottomLeftCorner)
    mw.setCorner(QtCore.Qt.BottomLeftCorner, QtCore.Qt.LeftDockWidgetArea)
    _fit_sidebar(force=True)

    # Tasks: shown while a task dialog runs, collapsed otherwise; its state
    # before Atech is recorded and put back on uninstall (R32).
    tasks = _find_dock(mw, "Tasks")
    _S["tasks"] = tasks
    if tasks is not None:
        _S["tasks_visible"] = not tasks.isHidden()
        box = _overlay_of(tasks)
        _S["tasks_box_visible"] = box.isVisible() if box is not None else None
        _S["dialog"] = None            # unknown: the first sync acts once
        tv = _task_view(tasks)
        if tv is not None:
            tv.currentChanged.connect(_on_task_view_changed)
            tv.widgetRemoved.connect(_on_task_view_changed)
            _S["task_view"] = tv

    mdi = mw.centralWidget()
    _S["mdi_qss"] = mdi.styleSheet() if mdi is not None else ""
    _S["status_qss"] = mw.statusBar().styleSheet()
    _S["status_minmax"] = (mw.statusBar().minimumHeight(),
                           mw.statusBar().maximumHeight())
    _S["menubar_qss"] = mw.menuBar().styleSheet()
    _S["main_qss"] = mw.styleSheet()
    if isinstance(mdi, QtWidgets.QMdiArea):
        _S["overlay"] = Overlay(mdi, on_docs=_on_docs_changed)
    _S["topbar"] = _build_topbar(mw)

    # Event-driven upkeep (S03), backed by a slow safety tick.
    watch.watch(mw.statusBar(), (QtCore.QEvent.ChildAdded,), _status_upkeep)
    watch.watch(mw, (QtCore.QEvent.ApplicationPaletteChange,
                     QtCore.QEvent.PaletteChange,
                     QtCore.QEvent.StyleChange,
                     QtCore.QEvent.Resize), _on_window_event)
    if tasks is not None:
        box = _overlay_of(tasks)
        if box is not None:
            # R48: FreeCAD shows the Tasks overlay when the first 3D view
            # opens, with no dialog; collapse it then, not on the next tick.
            watch.watch(box, (QtCore.QEvent.Show,), _sync_tasks)
    timer = QtCore.QTimer(dock)
    timer.timeout.connect(_tick)
    timer.start(SAFETY_TICK_MS)
    _S["timer"] = timer

    _hook_quit()
    chrome.snapshot()
    chrome.hide_toolbars()
    restyle()
    _sync_tasks()


def _hook_quit():
    global _QUIT_HOOKED
    if not _QUIT_HOOKED:
        QtWidgets.QApplication.instance().aboutToQuit.connect(_on_quit)
        _QUIT_HOOKED = True


def join_workers(timeout_ms=3000):
    """Stop and WAIT for every worker thread the chat owns. Qt aborts the
    process when a QThread is destroyed while running, so nothing that owns
    one may be deleted before this returns True."""
    ok = True
    try:
        from . import claude_cli
        if claude_cli.ClaudeRun.shutdown_all(timeout_ms) is False:
            ok = False
    except Exception as exc:                           # noqa: BLE001
        _log("shutdown_all: %r" % (exc,))
    chat = _KEEP.get("chat")
    if chat is None or not _alive(chat):
        return ok
    threads = list(chat.findChildren(QtCore.QThread))
    for name in ("_chat", "_health", "_runner", "_run"):
        th = getattr(chat, name, None)
        if isinstance(th, QtCore.QThread) and th not in threads:
            threads.append(th)
    for th in threads:
        try:
            if not th.isRunning():
                continue
            cancel = getattr(th, "cancel", None)
            if callable(cancel):
                cancel()
            th.requestInterruption()
            th.quit()
            if not th.wait(timeout_ms):
                ok = False
        except RuntimeError:                           # already deleted
            pass
    return ok


def teardown(timeout_ms=3000):
    """Destroy the sidebar for good (not used on a workbench switch).

    Joins the chat's workers first; if one will not stop, the sidebar is
    kept, hidden, rather than deleting a running thread's parent."""
    uninstall()
    if not _KEEP:
        return True
    if not join_workers(timeout_ms):
        _log("teardown: a worker is still running; sidebar kept")
        return False
    dock = _KEEP["dock"]
    try:
        _mw().removeDockWidget(dock)
        dock.deleteLater()
    except RuntimeError:
        pass
    _KEEP.clear()
    return True


def _on_quit():
    """aboutToQuit: join every thread we own and put the user's settings
    back. FreeCAD saved the window (and our hidden toolbars) in closeEvent,
    which runs before this, so the write-back here is what is persisted
    (MainWindow.cpp closeEvent -> saveWindowSettings -> ToolBarManager::
    saveState), and nothing writes the Toolbars or View groups after
    aboutToQuit (Application.cpp runEventLoop: the loop has returned). So
    the write-back here is final and the snapshots are CLEARED: a snapshot
    kept past a clean quit went stale and, on the next activation, undid
    whatever the user changed meanwhile in another workbench. Only a crash
    (no aboutToQuit) leaves one behind, which is the case it exists for."""
    try:
        from . import terminal_dock
        terminal_dock.shutdown()
    except Exception as exc:                           # noqa: BLE001
        _log("terminal shutdown: %r" % (exc,))
    join_workers(3000)
    if _S:
        try:
            chrome.write_back(clear=True)
        except Exception as exc:                       # noqa: BLE001
            _log("toolbars at quit: %r" % (exc,))
        try:
            from . import viewport
            viewport.restore_view_prefs(clear=True)
        except Exception as exc:                       # noqa: BLE001
            _log("view prefs at quit: %r" % (exc,))


# ------------------------------------------------------------------ icons
_ICON_DIR = []


def _private_dir(d):
    """True when `d` is (now) a real directory owned by us - not a symlink,
    not a file someone planted there."""
    import stat
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
        st = os.lstat(d)
    except OSError:
        return False
    if not stat.S_ISDIR(st.st_mode):
        return False
    return not hasattr(os, "getuid") or st.st_uid == os.getuid()


def _icon_dir():
    """Per-user icon cache (R33): FreeCAD's user cache path, else Qt's cache
    location, else a fresh private mkdtemp. Never a shared, predictable
    /tmp name another user could pre-create or plant a symlink in."""
    if _ICON_DIR and os.path.isdir(_ICON_DIR[0]):
        return _ICON_DIR[0]
    cands = []
    try:
        import FreeCAD
        cands.append(os.path.join(FreeCAD.getUserCachePath(), "AtechAtelier",
                                  "icons"))
    except Exception:                                  # noqa: BLE001
        pass
    loc = QtCore.QStandardPaths.writableLocation(
        QtCore.QStandardPaths.CacheLocation)
    if loc:
        cands.append(os.path.join(loc, "atech-atelier-icons"))
    for d in cands:
        if _private_dir(d):
            _ICON_DIR[:] = [d]
            return d
    import tempfile
    d = tempfile.mkdtemp(prefix="atech-atelier-icons-")
    _ICON_DIR[:] = [d]
    return d


def _write_png(pm, path):
    """Atomic write that never follows a symlink planted at `path`:
    render to a private temp file beside it, then os.replace() over the
    name (replace swaps the directory entry, it does not write through)."""
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".png", dir=os.path.dirname(path))
    os.close(fd)
    try:
        if not pm.save(tmp, "PNG"):
            raise OSError("could not write %s" % tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _icon_file(name, color, size=14):
    """Render an icon to a PNG QSS can point at (url() takes files only).

    Writes the 1x file plus @Nx variants up to the screen's scale; Qt picks
    the @Nx file itself on a high-DPI screen (R34)."""
    d = _icon_dir()
    base = "%s-%s" % (name, color.lstrip("#"))
    path = os.path.join(d, base + ".png")
    scale = style.pixel_scale()
    for n in range(1, scale + 1):
        p = path if n == 1 else os.path.join(d, "%s@%dx.png" % (base, n))
        if os.path.isfile(p) and not os.path.islink(p):
            continue
        try:
            pm = style.icon(name, color, size, 2.0, scale=n).pixmap(
                size * n, size * n)
            _write_png(pm, p)
        except OSError as exc:
            _log("icon cache: %r" % (exc,))
    return path.replace("\\", "/")


def _overlay_of(w):
    p = w.parent()
    while p is not None:
        if p.metaObject().className() == "Gui::OverlayTabWidget":
            return p
        p = p.parent()
    return None


def _hide_status_mark():
    """The status-bar brand mark duplicates the top bar's and vanishes on the
    dark ground (dark glyph, no tile). FreeCAD adds it after startup, so this
    runs when the status bar gains a child (and on the safety tick)."""
    sb = _mw().statusBar()
    hidden = _S.setdefault("status_hidden", [])
    for lbl in sb.findChildren(QtWidgets.QLabel):
        pm = lbl.pixmap()
        # A mark uninstall() left hidden (dark mode) is remembered on the
        # widget itself: _S does not survive a Part round trip, and an
        # invisible label would otherwise never be given back in light.
        ours = bool(lbl.property("atechStatusMark"))
        if pm is not None and not pm.isNull() and lbl.width() > 40 \
                and (lbl.isVisible() or ours):
            lbl.hide()
            lbl.setProperty("atechStatusMark", True)
            if lbl not in hidden:
                hidden.append(lbl)


def _style_status_buttons():
    """Our look on every status-bar button, including ones FreeCAD adds
    after install (its notification button arrives after startup). A
    button styled only on the NEXT activation made the bar change height
    across a Part round trip (R59); the bar's height is also pinned."""
    sb = _mw().statusBar()
    q = _S.get("status_btn_qss")
    if q is None:
        q = _S["status_btn_qss"] = style.qss(STATUS_BTN_QSS)
    saved = _S.setdefault("status_btns", {})
    for b in sb.findChildren(QtWidgets.QPushButton):
        if b not in saved:
            saved[b] = b.styleSheet()
        if b.styleSheet() != q:
            b.setStyleSheet(q)


_NOTIFY_IDLE = {}   # FreeCAD's idle notification icon, first sighting (R59)


def _icon_image(ic):
    return ic.pixmap(16, 16).toImage()


def _freecad_icon_image(name):
    """FreeCAD's own rendering of a named icon (FreeCADGui.getIcon), or None
    when it cannot say. `InTray_missed_notifications` is the notification
    button's alert icon (both names are strings in libFreeCADGui.so 1.1.3)."""
    try:
        import FreeCADGui
        ic = FreeCADGui.getIcon(name)
    except Exception:                                  # noqa: BLE001
        return None
    if ic is None or ic.isNull():
        return None
    return _icon_image(ic)


def _brand_notification_icon():
    """FreeCAD's notification button carries a coloured FreeCAD tray icon,
    the one off-brand glyph left in the chrome (R59). Its idle icon is
    swapped for a bell in the muted token colour. When FreeCAD switches it
    to another state icon (missed notifications) that one is left showing;
    ours comes back when FreeCAD returns it to the idle icon."""
    sb = _mw().statusBar()
    btn = None
    for b in sb.findChildren(QtWidgets.QPushButton):
        # FreeCAD 1.1.3's NotificationArea has no Q_OBJECT of its own: its
        # metaObject says "QPushButton" (measured, GUI r2), so the class
        # name alone never matched. Its objectName is "notificationArea".
        if b.objectName() == "notificationArea" or \
                b.metaObject().className().endswith("NotificationArea"):
            btn = b
            break
    if btn is None:
        return
    st = _S.setdefault("notify", {})
    if st.get("btn") is not btn:
        st.clear()
        # The idle icon is the one seen FIRST (at startup), kept across
        # installs: re-reading it on a Part round trip while FreeCAD shows
        # its missed-notifications icon would take that for idle and cover
        # the alert with our bell.
        if _NOTIFY_IDLE.get("btn") is not btn:
            # Startup warnings can leave the ALERT icon showing at the first
            # sighting; taken for idle it would be covered by the bell for
            # the whole session. Wait for FreeCAD's idle icon instead.
            missed = _freecad_icon_image("InTray_missed_notifications")
            if missed is not None and _icon_image(btn.icon()) == missed:
                st.clear()
                return
            _NOTIFY_IDLE.update(btn=btn, orig=btn.icon(),
                                idle=_icon_image(btn.icon()))
        st.update(btn=btn, orig=_NOTIFY_IDLE["orig"],
                  idle=_NOTIFY_IDLE["idle"])
    cur, ours = btn.icon(), st.get("ours")
    if ours is not None and cur.cacheKey() == ours.cacheKey():
        if st.get("mode") == style.mode():
            return
    elif _icon_image(cur) != st["idle"]:
        return                         # a state icon: FreeCAD's to show
    ours = style.icon("bell", style.tokens()["muted"], 16)
    st.update(ours=ours, mode=style.mode())
    btn.setIcon(ours)


def _restore_notification_icon():
    st = _S.get("notify") or {}
    btn, ours = st.get("btn"), st.get("ours")
    if btn is None or ours is None:
        return
    try:
        if btn.icon().cacheKey() == ours.cacheKey():
            btn.setIcon(st["orig"])
    except RuntimeError:
        pass


def _brand_nav_icon():
    """FreeCAD's navigation-style indicator carries a black mouse glyph that
    vanishes on the dark status bar (GUI r2 screenshot). The style name is
    in its text, so a token-coloured mouse loses nothing. Re-applied when
    FreeCAD sets its own icon again (a nav-style change) or the mode flips;
    the original is put back on uninstall."""
    sb = _mw().statusBar()
    btn = sb.findChild(QtWidgets.QPushButton, "NavigationIndicator")
    if btn is None:
        return
    st = _S.setdefault("navicon", {})
    ours = st.get("ours")
    if st.get("btn") is btn and ours is not None \
            and btn.icon().cacheKey() == ours.cacheKey() \
            and st.get("mode") == style.mode():
        return
    if st.get("btn") is not btn or ours is None \
            or btn.icon().cacheKey() != ours.cacheKey():
        st.update(btn=btn, orig=btn.icon())        # FreeCAD's current icon
    ours = style.icon("mouse", style.tokens()["muted"], 16)
    st.update(ours=ours, mode=style.mode())
    btn.setIcon(ours)


def _restore_nav_icon():
    st = _S.get("navicon") or {}
    btn, ours = st.get("btn"), st.get("ours")
    if btn is None or ours is None:
        return
    try:
        if btn.icon().cacheKey() == ours.cacheKey():
            btn.setIcon(st["orig"])
    except RuntimeError:
        pass


def _pin_status_height():
    """The QSS min/max-height alone did not hold at startup: measured 37 px
    (min 0, max unset) on first install, 27 after a Part round trip, so the
    bar - and the composer above it - jumped 10 px (GUI r2, R59). FreeCAD's
    late theme load re-polishes the bar and drops the QSS limits, so the
    pin is re-applied by the upkeep, not once."""
    sb = _mw().statusBar()
    if sb.minimumHeight() != STATUS_H or sb.maximumHeight() != STATUS_H:
        sb.setFixedHeight(STATUS_H)


def _status_upkeep():
    _pin_status_height()
    _hide_status_mark()
    _style_status_buttons()
    _brand_notification_icon()
    _brand_nav_icon()


def _only_tasks(box, tasks):
    """True when the overlay panel holds the Tasks dock alone. Toggling a
    panel that also holds Report view / Python console would hide those
    too (R32), so only a Tasks-only panel is ever toggled."""
    try:
        return box.count() <= 1
    except Exception:                                  # noqa: BLE001
        return False


def _sync_tasks():
    """Show Tasks while a task dialog runs, collapse it otherwise - acting
    only on a TRANSITION (R32): of activeDialog, or of the Tasks panel itself
    appearing. The old 600 ms tick fired FreeCAD's overlay toggle whenever
    the panel's visibility disagreed, which in auto-hide mode meant every
    tick. FreeCAD first shows the Tasks overlay when a 3D view opens - after
    install() synced with no view - so a panel that APPEARS without a dialog
    is collapsed too (measured r1: the strip otherwise stayed over the model
    for the whole session)."""
    t = _S.get("tasks")
    if t is None:
        return
    try:
        import FreeCADGui
        active = bool(FreeCADGui.Control.activeDialog())
    except Exception as exc:                           # noqa: BLE001
        _log("tasks: %r" % (exc,))
        return
    try:
        box = _overlay_of(t)
        shown = (box if box is not None else t).isVisible()
        # "appeared" is a False -> True of the OBSERVED state; a panel that
        # stays shown (auto-hide re-showing it, or a toggle FreeCAD ignored)
        # is not a new transition, so an idle tick never loops a command.
        appeared = shown and not _S.get("tasks_seen", False)
        _S["tasks_seen"] = shown
        if active == _S.get("dialog") and not (appeared and not active):
            return
        _S["dialog"] = active
        if box is None:
            # plain dock (overlay mode off): show/hide the dock itself
            if t.isVisible() != active:
                t.setVisible(active)
                _S["tasks_touched"] = True
            return
        # FreeCAD 1.1 docks Tasks as an overlay panel and keeps its title
        # strip on screen with nothing in it, over the model. Hiding the
        # widget loses a tug-of-war with the overlay manager (measured: it
        # re-shows within a second), so drive FreeCAD's OWN toggle.
        side = box.objectName().replace("Overlay", "")    # Right, Left, ...
        if side not in ("Left", "Right", "Top", "Bottom"):
            return
        if not _only_tasks(box, t):
            return
        if box.isVisible() != active:
            FreeCADGui.runCommand("Std_DockOverlayToggle" + side)
            _S["tasks_touched"] = True
    except Exception as exc:                           # noqa: BLE001
        _log("tasks: %r" % (exc,))


def _restore_tasks():
    t = _S.get("tasks")
    if t is None or not _S.get("tasks_touched"):
        return
    try:
        box = _overlay_of(t)
        if box is None:
            t.setVisible(bool(_S.get("tasks_visible")))
            return
        want = _S.get("tasks_box_visible")
        side = box.objectName().replace("Overlay", "")
        if want is not None and box.isVisible() != want and \
                side in ("Left", "Right", "Top", "Bottom"):
            import FreeCADGui
            FreeCADGui.runCommand("Std_DockOverlayToggle" + side)
    except Exception as exc:                           # noqa: BLE001
        _log("tasks restore: %r" % (exc,))


def _hide_dead_subwindows():
    """FreeCAD keeps a closed document's QMdiSubWindow as an empty child of
    the MDI viewport (no widget, out of subWindowList()). Any style sheet
    change - a light/dark switch included - shows it again, and its light
    frame then covers the start page: in dark mode the title and logo were
    white on #efefef (measured, round 3). Hidden again here; never deleted,
    it is FreeCAD's object.

    Only a sub-window that is BOTH out of subWindowList() and widgetless is
    touched: a live one (listed) or one still holding a view is FreeCAD's
    to show. Called after every sheet restyle() and uninstall() set, and on
    the safety tick. Returns how many it hid (R109).

    restyle() also queues one deferred pass (QTimer.singleShot(0)), which
    can run after the main window is gone (R148): a torn-down window or MDI
    area is 0, never a RuntimeError out of a timer slot."""
    n = 0
    try:
        mw = _mw()
        mdi = mw.centralWidget() if mw is not None else None
        if not isinstance(mdi, QtWidgets.QMdiArea):
            return 0
        live = set(mdi.subWindowList())
        for c in mdi.viewport().children():
            if (isinstance(c, QtWidgets.QMdiSubWindow) and c.isVisible()
                    and c not in live and c.widget() is None):
                c.hide()
                n += 1
    except RuntimeError:                               # torn down
        pass
    return n


def _light_atech_meshes():
    """Two-sided lighting on the active document's Atech board/module
    meshes (R108: black back faces through the board's open shells).
    Cheap when nothing changed: one property read per Atech mesh."""
    try:
        import FreeCAD
        doc = FreeCAD.ActiveDocument
    except Exception:                                  # noqa: BLE001
        return
    if doc is None:
        return
    try:
        from . import viewport
        viewport.two_side_meshes(doc)
    except Exception as exc:                           # noqa: BLE001
        _log("mesh lighting: %r" % (exc,))


def _tick():
    """Safety net behind the event-driven upkeep; every step is idempotent
    and cheap when nothing changed."""
    _hide_dead_subwindows()
    chrome.hide_now()
    _status_upkeep()
    _light_atech_meshes()
    _hide_model_dock()
    ov = _S.get("overlay")
    if ov is not None:
        ov.place(force=False)
    body = _S.get("body")
    if body is not None:
        # a document opened with no new MDI window (Start page already
        # open) changes no Overlay key; the hint follows on the tick (R57)
        body.sync_model_hint()
    _sync_tasks()


def restyle():
    """Re-read the mode and repaint every surface we own."""
    if not _S:
        return
    mw = _mw()
    _S["mode"] = style.mode()
    _restyle_topbar(_S["topbar"])
    _S["body"].restyle()
    mdi = mw.centralWidget()
    if mdi is not None:
        mdi.setStyleSheet(style.qss(
            CHROME_QSS, close_icon=_icon_file("x", style.tokens()["muted"])))
    sb = mw.statusBar()
    sb.setStyleSheet(style.qss(STATUS_QSS))
    _S.pop("status_btn_qss", None)          # the mode may have changed
    _status_upkeep()
    mw.setStyleSheet(style.qss(MAIN_QSS))
    _hide_dead_subwindows()          # the sheets above re-showed them
    ov = _S.get("overlay")
    if ov is not None:
        ov.bar.restyle()
        ov.empty.restyle()
        ov.place()
    try:
        from . import viewport
        viewport.apply_view_theme()
    except Exception as exc:                           # noqa: BLE001
        _log("view theme: %r" % (exc,))
    # GUI round 5: Std_ReloadStyleSheet re-shows the dead sub-windows AFTER
    # this restyle has run (visible straight after the command returns), so
    # the hide above came too early and the start page sat on #efefef until
    # the 3 s safety tick - in dark mode a white title on light grey.
    # MEASURED: 2-3 s of #efefef before, correct by 150 ms with this pass.
    QtCore.QTimer.singleShot(0, _hide_dead_subwindows)


def uninstall():
    """Give FreeCAD its window back. The sidebar (and the chat inside it,
    with any turn still running) is hidden, not deleted (R18)."""
    unhook_tracebacks()                 # install() hooks before its _S check
    if not _S:
        return
    mw = _mw()
    timer = _S.get("timer")
    if timer is not None:
        timer.stop()
        timer.deleteLater()
    watch = _S.get("watch")
    if watch is not None:
        watch.unwatch_all()
        watch.deleteLater()
    tv = _S.get("task_view")
    if tv is not None:
        for sig in (tv.currentChanged, tv.widgetRemoved):
            try:
                sig.disconnect(_on_task_view_changed)
            except (RuntimeError, TypeError):
                pass

    md, body = _S.get("model_dock"), _S.get("body")
    if md is not None:
        try:
            md.visibilityChanged.disconnect(_on_model_dock_visible)
        except (RuntimeError, TypeError):
            pass
        w = body.take_model_widget() \
            if body is not None and _S.get("model_widget") is not None else None
        if w is not None:
            md.setWidget(w)
            w.show()
        ph = _S.get("model_placeholder")
        if ph is not None:
            ph.deleteLater()
        md.toggleViewAction().setEnabled(True)
        md.setVisible(bool(_S.get("model_visible", True)))

    ov = _S.get("overlay")
    if ov is not None:
        ov.dispose()
    tb = _S.get("topbar")
    if tb is not None:
        _restore_topbar(mw, tb)
    if "menubar_qss" in _S:
        mw.menuBar().setStyleSheet(_S["menubar_qss"])
    if "status_qss" in _S:
        mw.statusBar().setStyleSheet(_S["status_qss"])
    if "status_minmax" in _S:
        lo, hi = _S["status_minmax"]
        mw.statusBar().setMinimumHeight(lo)
        mw.statusBar().setMaximumHeight(hi)
    # The branding mark is one dark-ink logo (branding.xml ProgramLogo has a
    # single value): on the dark ground it is a near-invisible navy smudge
    # in Part's status bar (GUI round 4). Give it back only in light mode.
    dark = style.mode() == "dark"
    for lbl in _S.get("status_hidden", []):
        try:
            lbl.setVisible(not dark)
        except RuntimeError:
            pass
    for b, q in _S.get("status_btns", {}).items():
        try:
            b.setStyleSheet(q)
        except RuntimeError:
            pass
    _restore_notification_icon()
    _restore_nav_icon()
    if "main_qss" in _S:
        mw.setStyleSheet(_S["main_qss"])
    if mw.centralWidget() is not None and "mdi_qss" in _S:
        mw.centralWidget().setStyleSheet(_S["mdi_qss"])
    # The two sheets just put back re-show a closed document's dead
    # sub-window exactly as restyle()'s do (R109): over Part's empty area.
    _hide_dead_subwindows()
    if "corner" in _S:
        mw.setCorner(QtCore.Qt.BottomLeftCorner, _S["corner"])
    _restore_tasks()
    dock = _S.get("dock")
    if dock is not None and _alive(dock):
        mw.removeDockWidget(dock)       # hides it; the chat lives on
    chrome.restore_toolbars()
    try:
        from . import viewport
        viewport.restore_view_prefs()
    except Exception as exc:                           # noqa: BLE001
        _log("view prefs: %r" % (exc,))
    _S.clear()


def chat_panel():
    return _S.get("chat") or _KEEP.get("chat")


def show_chat():
    if not _S:
        install()
    _S["body"].show_page(0)
    _S["dock"].show()
    return _S["chat"]


def show_modules():
    if not _S:
        install()
    _S["body"].show_page(2)


def show_model():
    if not _S:
        install()
    _S["body"].show_page(1)
