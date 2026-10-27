"""shell — the Atech AI CAD window, laid over FreeCAD's main window.

What it builds while the agent workbench is active (and takes down again on
deactivate, so other workbenches get FreeCAD's normal chrome). The sidebar
itself - chat transcript, workspace, Claude session, running turn - is built
ONCE and only hidden on deactivate (R18): deleting it took its running
worker QThreads with it and aborted FreeCAD.

    top bar     the menu bar restyled as a 44 px app bar: mark + wordmark on
                the left, the menus, quick actions on the right. The menus
                stay real FreeCAD menus, so every command and shortcut works.
                On macOS the menu bar is the native one, which draws no
                corner widgets: there the wordmark, Terminal and Settings
                live in the sidebar header instead (R300, sidebar_chrome).
    sidebar     ONE left dock: brand row (macOS), the project picker with
                Terminal / Settings, the hardware switch, 3D CAD | Atech
                modules. 3D CAD is the chat under a collapsible Parts panel
                (FreeCAD's own tree + property view, re-parented, R301).
    view bar    a floating pill over the 3D view: fit, fit selection,
                standard views, perspective, wireframe, a slot for the
                Measure / Section / Export tools, spin, full-screen 3D,
                add-view-to-chat, and ask-about-this-view (R303).
    home        the project grid, examples and drop target shown in the
                viewport when no document is open (R308, HomeView).
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
import time
import traceback

from PySide6 import QtCore, QtGui, QtWidgets

# navbar at module level: _hardware_switch() (R280) uses it outside the
# Sidebar's own local import, and raised NameError there (switch missing).
from . import chrome, navbar, style

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
#ProjectPicker {{
    background: {panel}; border: 1px solid {line}; border-radius: 18px;
    padding: 7px 14px; min-height: 20px; text-align: left;
    color: {text}; font-family: {UI}; font-size: 13px; font-weight: 600;
}}
#ProjectPicker:hover {{ background: {hover}; border-color: {line_strong}; }}
#ProjectPicker::menu-indicator {{ image: none; width: 0; }}
#PartsBtn {{
    background: {track}; border: 1px solid {line}; border-radius: 18px;
}}
#PartsBtn:hover {{ background: {hover}; }}
#PartsBtn:checked {{ background: {btn_bg}; border-color: {btn_bg}; }}

#SideBrand {{ background: transparent; }}
#SideWordmark {{ color: {text}; font-family: 'Sen', {UI}; font-size: 15px; font-weight: 700; }}
#SideIconBtn {{
    background: transparent; border: 1px solid transparent; border-radius: 18px;
}}
#SideIconBtn:hover {{ background: {hover}; border-color: {line}; }}
#SideIconBtn:focus {{ border-color: {accent}; }}
#SideIconBtn::menu-indicator {{ image: none; width: 0; }}
#PartsHead {{ background: {panel}; border-top: 1px solid {line}; border-bottom: 1px solid {line}; }}
#PartsToggle {{
    background: transparent; border: none; border-radius: 6px; text-align: left;
    padding: 4px 6px; color: {muted}; font-family: {UI}; font-size: 11px;
    font-weight: 600; letter-spacing: 0.4px;
}}
#PartsToggle:hover {{ color: {text}; background: {hover}; }}
#PartsToggle:focus {{ color: {text}; }}
#CadSplit::handle {{ background: {line}; height: 1px; }}
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
#VBtn::menu-indicator {{ image: none; width: 0; }}
#VBtn:focus, #VPrimary:focus {{ border: 1px solid {accent}; }}
"""

HOME_QSS = """
#HomeView {{ background: transparent; }}
#HomeView[dropping="true"] {{ border: 2px dashed {accent}; border-radius: 18px; }}
#HomeScroll, #HomeInner {{ background: transparent; border: none; }}
#HomeTitle {{ color: {text}; font-family: 'Sen', {UI}; font-size: 22px; font-weight: 700; }}
#HomeSection {{ color: {muted}; font-family: {UI}; font-size: 11px; font-weight: 600;
    letter-spacing: 0.5px; }}
#HomeNote {{ color: {muted}; font-family: {UI}; font-size: 12px; }}
#HomeSearch {{
    background: {input_bg}; color: {text}; border: 1px solid {input_border};
    border-radius: 16px; padding: 6px 12px 6px 4px; min-height: 20px;
    font-family: {UI}; font-size: 13px;
}}
#HomeSearch:focus {{ border-color: {line_strong}; }}
#HomeBtn {{
    background: {panel}; color: {text}; border: 1px solid {line}; border-radius: 16px;
    padding: 0 14px; min-height: 32px; max-height: 32px; font-family: {UI};
    font-size: 12px; font-weight: 600;
}}
#HomeBtn:hover {{ background: {hover}; border-color: {line_strong}; }}
#HomeBtn:focus {{ border-color: {accent}; }}
#ProjectCard {{ background: {panel}; border: 1px solid {line}; border-radius: 16px; }}
#ProjectCard:hover {{ border-color: {line_strong}; background: {card}; }}
#ProjectCard:focus, #StartCard:focus {{ border: 1px solid {accent}; }}
#Thumb {{ background: {bubble}; border-radius: 10px; }}
#Chip {{
    background: {bubble}; color: {text}; border-radius: 9px; padding: 1px 8px;
    font-family: {UI}; font-size: 10px; font-weight: 600;
}}
#EmptyCredit {{ color: {muted}; font-family: {UI}; font-size: 11px; }}
#CardTitle {{ color: {text}; font-family: {UI}; font-size: 13px; font-weight: 600; }}
#CardSub {{ color: {muted}; font-family: {UI}; font-size: 12px; }}
#CardIcon {{ background: {bubble}; border-radius: 10px; }}
#StartCard {{ background: {panel}; border: 1px solid {line}; border-radius: 16px; }}
#StartCard:hover {{ border-color: {line_strong}; background: {card}; }}
"""

HINT_QSS = """
#OrbitHint {{ background: {panel}; border: 1px solid {line}; border-radius: 16px; }}
#HintTitle {{ color: {text}; font-family: {UI}; font-size: 13px; font-weight: 600; }}
#HintAction {{ color: {text}; font-family: {UI}; font-size: 12px; font-weight: 600; }}
#HintHow {{ color: {muted}; font-family: {UI}; font-size: 12px; }}
#HintBtn {{
    background: {btn_bg}; color: {btn_text}; border: none; border-radius: 14px;
    padding: 0 14px; min-height: 28px; max-height: 28px; font-family: {UI};
    font-size: 12px; font-weight: 600;
}}
#HintBtn:hover {{ background: {btn_bg_hover}; }}
#HintLink {{
    background: transparent; color: {muted}; border: none; padding: 0 8px;
    min-height: 28px; font-family: {UI}; font-size: 12px;
}}
#HintLink:hover {{ color: {text}; }}
"""

SHEET_QSS = """
#AtechSheet {{ background: {panel}; }}
#SheetTitle {{ color: {text}; font-family: {UI}; font-size: 16px; font-weight: 700; }}
#SheetSection {{ color: {muted}; font-family: {UI}; font-size: 11px; font-weight: 600;
    letter-spacing: 0.5px; }}
#SheetText {{ color: {text}; font-family: {UI}; font-size: 13px; }}
#SheetSub {{ color: {muted}; font-family: {UI}; font-size: 12px; }}
#KeyCap {{
    background: {bubble}; color: {text}; border: 1px solid {line}; border-radius: 6px;
    padding: 2px 8px; font-family: {MONO}; font-size: 12px;
}}
#AtechSheet QRadioButton {{ color: {text}; font-family: {UI}; font-size: 13px; spacing: 8px; }}
#SheetBtn {{
    background: {btn_bg}; color: {btn_text}; border: none; border-radius: 15px;
    padding: 0 16px; min-height: 30px; max-height: 30px; font-family: {UI};
    font-size: 12px; font-weight: 600;
}}
#SheetBtn:hover {{ background: {btn_bg_hover}; }}
#SheetLink {{
    background: transparent; color: {muted}; border: 1px solid {line}; border-radius: 15px;
    padding: 0 14px; min-height: 30px; max-height: 30px; font-family: {UI}; font-size: 12px;
}}
#SheetLink:hover {{ color: {text}; background: {hover}; }}
#AtechSheet QScrollArea, #SheetInner {{ background: transparent; border: none; }}
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
        # Reachable and usable from the keyboard (Tab, then Return / Space).
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAccessibleName(title)
        self.setAccessibleDescription(sub)
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

    def keyPressEvent(self, ev):                       # noqa: N802
        if ev.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter,
                        QtCore.Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(ev)


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
        self.cards[1].clicked.connect(lambda: _new_project())   # R383
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
            style.PRODUCT + ', powered by FreeCAD \u00b7 <a href="credits" '
            'style="color:%s; text-decoration:none;">Credits</a>'
            % style.tokens()["accent"])
        pm = style.logo_pixmap(40)
        if pm is not None:
            self.mark.setPixmap(pm)
        for c in self.cards:
            c.restyle()
        self._fit = None            # the mark's height is known only now
        self._fit_height(self.height())


# ------------------------------------------------------------ home (R308)
HOME_RECENT_MAX = 10           # PRD Opening 3: recents, up to 10
OPEN_EXT = (".fcstd",)
#: Opened as a NEW project that imports the file (PRD Opening 4).
IMPORT_EXT = (".step", ".stp", ".stl", ".3mf", ".iges", ".igs", ".brep", ".brp")
_PEEK = {}                     # (realpath, mtime, size) -> (thumb bytes, hw)

#: "Start from an example" (PRD Opening 6): agent_kit/examples/<key>.py.
EXAMPLES = (
    ("toy_car", "Toy car", "A chunky 4x4 around the Atech board, with "
     "driven wheels and lights.", "car"),
    ("desk_robot", "Desk robot", "A little robot whose face is a screen.",
     "bot"),
    ("smart_speaker", "Smart speaker", "A round speaker with a light ring "
     "and buttons.", "speaker"),
)


#: Home's card icon per default project (R456), by example key.
EXAMPLE_ICONS = {"toy_car": "car", "desk_robot": "bot",
                 "smart_speaker": "speaker", "bedside_lamp": "sun",
                 "handheld_console": "keyboard", "alarm_clock": "bell",
                 "desk_fan": "rotate", "weather_station": "monitor",
                 "rc_tank": "car",
                 "smart_planter": "tree",
                 "pet_feeder": "cube",
                 "video_doorbell": "bell",
                 "mini_arcade": "monitor",
                 "music_box": "speaker",
                 "parking_sensor": "car",
                 "desk_organizer": "layers",
                 "photo_frame": "camera",
                 "metronome": "bell",
                 "macro_pad": "keyboard",
                 "rover": "car",
                 "air_monitor": "sparkles",
                 "motion_light": "moon",
                 "arm_dock": "cpu",
                 "balance_bot": "bot"}


def example_entries():
    """Home's "Start from an example" row as [(key, title, subtitle, icon,
    shipped)]: the default projects this installation ships (R456,
    default_projects.entries(); a card opens a fresh copy with
    open_default), else - no default projects here, e.g. a source tree -
    EXAMPLES, built from agent_kit/examples/ by open_example."""
    try:
        from . import default_projects
        rows = default_projects.entries()
    except Exception as exc:                           # noqa: BLE001
        _log("default projects: %r" % (exc,))
        rows = []
    if rows:
        return [(k or t, t, sub or "A ready-made Atech project.",
                 EXAMPLE_ICONS.get(k, "cube"), True) for t, k, sub in rows]
    return [(k, t, sub, ico, False) for k, t, sub, ico in EXAMPLES
            if example_path(k) is not None]


def open_default(title):
    """R456: a fresh copy of the shipped default project `title` (its own
    project id and starter chat), opened as a new project. Returns the
    copy's path, or None (said in a notice)."""
    _leave_home()
    try:
        from . import default_projects
        path = default_projects.new_from_default(title)
    except Exception as exc:                           # noqa: BLE001
        _notify("Could not start from the example",
                "The details are in the Report view.", exc)
        return None
    if path is None:
        _notify("Example not available",
                "The %s project is not in this installation." % title.lower())
        return None
    _refresh_home()
    return path


def _first(row, *keys):
    for k in keys:
        v = row.get(k) if isinstance(row, dict) else getattr(row, k, None)
        if v not in (None, ""):
            return v
    return None


def _as_time(v):
    """Seconds since the epoch from a number, a datetime or an ISO string."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        import datetime
        if isinstance(v, datetime.datetime):
            return v.timestamp()
        return datetime.datetime.fromisoformat(str(v)).timestamp()
    except Exception:                                  # noqa: BLE001
        return None


def normalize_projects(rows, exists=os.path.isfile):
    """Rows from projects_store.list_projects() (W1) or the recent-files
    fallback, as [{path, name, mtime, thumb, electronics}]: newest first,
    one per real path, files that no longer exist dropped. Dicts and
    objects are both read, under the field names either source may use."""
    out, seen = [], set()
    for r in rows or ():
        path = _first(r, "path", "file", "file_path", "FileName")
        if not path:
            continue
        path = str(path)
        real = os.path.realpath(path)
        if real in seen or not exists(path):
            continue
        seen.add(real)
        mtime = _as_time(_first(r, "mtime", "modified", "last_edited",
                                "edited", "updated"))
        if mtime is None:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0.0
        name = _first(r, "name", "title", "label")
        hw = _first(r, "electronics", "has_electronics", "hardware", "atech")
        out.append({"path": path,
                    "name": str(name) if name else
                    os.path.splitext(os.path.basename(path))[0],
                    "mtime": mtime,
                    "thumb": _first(r, "thumbnail", "thumb", "thumbnail_path"),
                    "electronics": bool(hw) if hw is not None else None})
    out.sort(key=lambda d: -d["mtime"])
    return out


def recent_paths(limit=HOME_RECENT_MAX):
    """FreeCAD's recent files, most recent first: existing files only, one
    entry per REAL path (/tmp/x and /private/tmp/x are one file)."""
    out, seen = [], set()
    try:
        import FreeCAD
        grp = FreeCAD.ParamGet(navbar.RECENT_PARAM)
        n = max(grp.GetInt("RecentFiles", 0) or 0, 10)
        for i in range(n):
            p = grp.GetString("MRU%d" % i, "")
            if not p or not os.path.isfile(p):
                continue
            real = os.path.realpath(p)
            if real not in seen:
                seen.add(real)
                out.append(p)
    except Exception as exc:                           # noqa: BLE001
        _log("recent files: %r" % (exc,))
    return out[:limit]


def _fcstd_peek(path):
    """(thumbnail PNG bytes or None, has Atech hardware) of a .FCStd, read
    from the zip without opening the document; cached per file version."""
    try:
        st = os.stat(path)
    except OSError:
        return None, False
    key = (os.path.realpath(path), st.st_mtime, st.st_size)
    if key in _PEEK:
        return _PEEK[key]
    thumb, hw = None, False
    if path.lower().endswith(".fcstd"):
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                if "thumbnails/Thumbnail.png" in names:
                    thumb = z.read("thumbnails/Thumbnail.png")
                if "Document.xml" in names:
                    with z.open("Document.xml") as fh:
                        hw = b"AtechRole" in fh.read()
        except (OSError, zipfile.BadZipFile, KeyError, RuntimeError):
            pass
    _PEEK[key] = (thumb, hw)
    return thumb, hw


def fallback_projects(limit=HOME_RECENT_MAX):
    """The Home grid without W1's project store: FreeCAD's recent files."""
    rows = []
    for p in recent_paths(limit):
        _thumb, hw = _fcstd_peek(p)
        rows.append({"path": p, "electronics": hw})
    return rows


def home_projects():
    """([project rows], source): source is "store" (projects_store, W1) or
    "recent" (the fallback). A store that is missing or raises falls back."""
    try:
        from . import projects_store                   # W1, built in parallel
        rows = projects_store.list_projects()
        return normalize_projects(rows), "store"
    except Exception as exc:                           # noqa: BLE001
        if not isinstance(exc, ImportError):
            _log("projects_store: %r" % (exc,))
    return normalize_projects(fallback_projects()), "recent"


def edited_text(mtime, now=None):
    """'Edited 5 min ago' and so on, in plain words."""
    import time
    if not mtime:
        return ""
    now = time.time() if now is None else now
    d = max(0, now - mtime)
    if d < 60:
        return "Edited just now"
    if d < 3600:
        return "Edited %d min ago" % (d // 60)
    if d < 86400:
        return "Edited %d h ago" % (d // 3600)
    if d < 2 * 86400:
        return "Edited yesterday"
    if d < 7 * 86400:
        return "Edited %d days ago" % (d // 86400)
    return "Edited " + time.strftime("%-d %b %Y" if os.name != "nt"
                                     else "%d %b %Y", time.localtime(mtime))


def example_path(key):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "agent_kit", "examples", key + ".py")
    return p if os.path.isfile(p) else None


def droppable(paths):
    """The dropped files Atech opens: .FCStd, and STEP/STL/3MF/IGES/BREP
    as new projects importing them."""
    return [p for p in paths if p and os.path.isfile(p)
            and p.lower().endswith(OPEN_EXT + IMPORT_EXT)]


def _event_paths(ev):
    try:
        md = ev.mimeData()
        if md is None or not md.hasUrls():
            return []
        return [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
    except Exception:                                  # noqa: BLE001
        return []


class ProjectCard(QtWidgets.QFrame):
    """One saved project on Home: thumbnail, name, when it was edited, and
    an Electronics chip when it holds Atech hardware."""

    clicked = QtCore.Signal()
    W, H = 210, 150
    THUMB = (186, 72)

    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.row = row
        self.setObjectName("ProjectCard")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WA_Hover, True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setFixedSize(self.W, self.H)
        self.setToolTip(row["path"])
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)
        self.thumb = QtWidgets.QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setFixedSize(*self.THUMB)
        self.thumb.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.thumb)
        self.name = QtWidgets.QLabel()
        self.name.setObjectName("CardTitle")
        fm = QtGui.QFontMetrics(self.name.font())
        self.name.setText(fm.elidedText(row["name"], QtCore.Qt.ElideRight,
                                        self.W - 24))
        lay.addWidget(self.name)
        meta = QtWidgets.QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(6)
        self.edited = QtWidgets.QLabel(edited_text(row.get("mtime")))
        self.edited.setObjectName("CardSub")
        meta.addWidget(self.edited)
        meta.addStretch(1)
        self.chip = QtWidgets.QLabel("Electronics")
        self.chip.setObjectName("Chip")
        self.chip.setToolTip("Built around the Atech board and modules")
        self.chip.setVisible(bool(row.get("electronics")))
        meta.addWidget(self.chip)
        lay.addLayout(meta)
        lay.addStretch(1)
        self.setAccessibleName("Open project %s" % row["name"])
        self.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
        self.setAccessibleDescription(" ".join(x for x in (
            self.edited.text(), "Electronics" if row.get("electronics") else "")
            if x))
        self._pm = None

    def thumbnail(self):
        """The project's picture: the store's (path or PNG bytes), else the
        thumbnail FreeCAD saved inside the .FCStd. None when there is none."""
        if self._pm is not None:
            return self._pm
        src = self.row.get("thumb")
        pm = QtGui.QPixmap()
        if isinstance(src, (bytes, bytearray)):
            pm.loadFromData(bytes(src))
        elif isinstance(src, str) and os.path.isfile(src):
            pm.load(src)
        if pm.isNull():
            data, _hw = _fcstd_peek(self.row["path"])
            if data:
                pm.loadFromData(data)
        self._pm = None if pm.isNull() else pm
        return self._pm

    def restyle(self):
        pm = self.thumbnail()
        if pm is None:
            self.thumb.setPixmap(style.icon("cube", style.tokens()["dim"], 26)
                                 .pixmap(26, 26))
            return
        dpr = style.pixel_scale()
        w, h = self.THUMB
        sc = pm.scaled(w * dpr, h * dpr, QtCore.Qt.KeepAspectRatio,
                       QtCore.Qt.SmoothTransformation)
        sc.setDevicePixelRatio(dpr)
        self.thumb.setPixmap(sc)

    def mouseReleaseEvent(self, ev):                   # noqa: N802
        if ev.button() == QtCore.Qt.LeftButton and self.rect().contains(ev.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(ev)

    def keyPressEvent(self, ev):                       # noqa: N802
        if ev.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter,
                        QtCore.Qt.Key_Space):
            self.clicked.emit()
            return
        if ev.key() == QtCore.Qt.Key_Menu:
            self.show_menu(self.mapToGlobal(self.rect().center()))
            return
        super().keyPressEvent(ev)

    def menu(self):
        """R385: the card's own menu: Open, Rename..., Duplicate, Show in
        Finder, Move to Trash... (the picker's "This project" actions, for
        a project that is not open)."""
        m = QtWidgets.QMenu(self)
        m.setAccessibleName("Project %s" % self.row["name"])
        for key, text in HOME_CARD_ACTIONS:
            if key == "-":
                m.addSeparator()
                continue
            a = m.addAction(text)
            a.setObjectName("home_" + key)
            a.triggered.connect(
                lambda _=False, k=key: _safe(
                    lambda: home_card_action(k, self.row["path"], self)))
        return m

    def show_menu(self, pos):
        m = self.menu()
        self._menu = m
        m.popup(pos)
        return m

    def contextMenuEvent(self, ev):                    # noqa: N802
        self.show_menu(ev.globalPos())
        ev.accept()


#: (key, menu text) of a Home project card's menu (R385); "-" a line.
HOME_CARD_ACTIONS = (("open", "Open"), ("-", ""), ("rename", "Rename\u2026"),
                     ("duplicate", "Duplicate"),
                     ("reveal", "Show in Finder"), ("-", ""),
                     ("trash", "Move to Trash\u2026"))


def home_card_action(key, path, parent=None, ask=None, confirm=None):
    """Run one Home card action on the project at `path`. `ask(title,
    label, default)` and `confirm(title, text, ok)` are the prompts (tests
    pass their own). Returns the action's result; a ProjectError or a file
    error is shown in plain words and returns None."""
    from . import projects_store
    ask = ask or (lambda t, l, d: navbar._ask_name(parent, t, l, d))
    confirm = confirm or (lambda t, x, ok: navbar._confirm(parent, t, x, ok))
    stem = os.path.splitext(os.path.basename(path))[0]
    try:
        if key == "open":
            return open_project_path(path)
        if key == "rename":
            name = ask("Rename project", "New name:", stem)
            if name is None or projects_store.clean_name(name) == stem:
                return None
            out = projects_store.rename_project(path, name)
        elif key == "duplicate":
            out = projects_store.duplicate_project(path)
        elif key == "reveal":
            return projects_store.reveal_in_finder(path)
        elif key == "trash":
            if not confirm("Move to Trash",
                           "Move \u201c%s\u201d to the Trash? Its chat is "
                           "deleted with it. You can get the file back from "
                           "the Trash." % stem, "Move to Trash"):
                return None
            out = projects_store.trash_project(path)
        else:
            raise KeyError(key)
    except projects_store.ProjectError as exc:
        _notify("That did not work", str(exc))
        return None
    except OSError as exc:
        _notify("That did not work", "The file could not be changed: %s."
                % (exc.strerror or exc))
        return None
    _refresh_home()
    return out


def _refresh_home():
    ov = _S.get("overlay")
    home = getattr(ov, "empty", None) if ov is not None else None
    if isinstance(home, HomeView):
        try:
            home.refresh()
        except RuntimeError:
            pass


class _ClickFilter(QtCore.QObject):
    """Calls fn() on a left click released over the watched widget."""

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def eventFilter(self, obj, ev):                    # noqa: N802
        if ev.type() == QtCore.QEvent.MouseButtonRelease \
                and ev.button() == QtCore.Qt.LeftButton:
            try:
                self._fn()
            except Exception as exc:                   # noqa: BLE001
                _log("click: %r" % (exc,))
            return True
        return False


class HomeView(QtWidgets.QWidget):
    """Home: shown in the viewport when no project is open (R308).

    The header (mark, product name, search, Open file), the project grid
    ("New project" first, then saved projects newest first, from
    projects_store.list_projects() or FreeCAD's recent files), "Start from
    an example" cards, and the credit line. Files dropped on it open.

    For the start-card tests of the old EmptyView, `cards` (the action and
    example cards), columns_for() and _layout_cards() keep their meaning."""

    MAX_COLS = 5
    GAP = 12
    MARGIN = 32

    def keyPressEvent(self, ev):                       # noqa: N802
        """R801: Esc on Home (opened over a project) goes back to it."""
        if ev.key() == QtCore.Qt.Key_Escape and home_open():
            show_home(False)
            return
        super().keyPressEvent(ev)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeView")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setAcceptDrops(True)
        self.setAccessibleName("Home")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setObjectName("HomeScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)
        inner = QtWidgets.QWidget()
        inner.setObjectName("HomeInner")
        v = QtWidgets.QVBoxLayout(inner)
        m = self.MARGIN
        v.setContentsMargins(m, 28, m, 24)
        v.setSpacing(0)

        head = QtWidgets.QHBoxLayout()
        head.setSpacing(10)
        self.mark = QtWidgets.QLabel()
        head.addWidget(self.mark)
        self.title = QtWidgets.QLabel(style.PRODUCT)
        self.title.setObjectName("HomeTitle")
        head.addWidget(self.title)
        head.addStretch(1)
        self.search = QtWidgets.QLineEdit()
        self.search.setObjectName("HomeSearch")
        self.search.setPlaceholderText("Search projects")
        self.search.setAccessibleName("Search projects")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(220)
        self._search_act = None
        self.search.textChanged.connect(self.apply_filter)
        head.addWidget(self.search)
        self.btn_open = QtWidgets.QPushButton("Open file\u2026")
        self.btn_open.setObjectName("HomeBtn")
        self.btn_open.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_open.setAccessibleName("Open file")
        self.btn_open.setToolTip("Open a .FCStd project, or STEP / STL / 3MF "
                                 "as a new project. You can also drop files here.")
        self.btn_open.clicked.connect(lambda: _open_file())
        head.addWidget(self.btn_open)
        v.addLayout(head)
        v.addSpacing(22)

        self.sec_projects = QtWidgets.QLabel("YOUR PROJECTS")
        self.sec_projects.setObjectName("HomeSection")
        v.addWidget(self.sec_projects)
        v.addSpacing(10)
        self.grid = QtWidgets.QGridLayout()
        self.grid.setSpacing(self.GAP)
        self.grid.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        v.addLayout(self.grid)
        v.addSpacing(8)
        self.note = QtWidgets.QLabel()
        self.note.setObjectName("HomeNote")
        self.note.setWordWrap(True)
        v.addWidget(self.note)
        v.addSpacing(22)
        self.sec_examples = QtWidgets.QLabel("START FROM AN EXAMPLE")
        self.sec_examples.setObjectName("HomeSection")
        v.addWidget(self.sec_examples)
        v.addSpacing(10)
        self.ex_grid = QtWidgets.QGridLayout()
        self.ex_grid.setSpacing(self.GAP)
        self.ex_grid.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        v.addLayout(self.ex_grid)
        v.addSpacing(26)
        c = QtWidgets.QLabel()
        c.setObjectName("EmptyCredit")
        c.setOpenExternalLinks(False)
        c.linkActivated.connect(_open_credits)
        v.addWidget(c)
        self.credit = c
        v.addStretch(1)
        self.scroll.setWidget(inner)
        outer.addWidget(self.scroll)

        self.new_card = ClickCard("file-plus", "New project",
                                  "An empty design to build into.")
        self.new_card.clicked.connect(lambda: _new_project())
        self.example_cards = []
        for key, title, sub, ico, shipped in example_entries():
            card = ClickCard(ico, title, sub)
            card.setAccessibleName("Start from the %s example" % title.lower())
            card.example_key = key
            card.default_title = title if shipped else None
            if shipped:
                card.clicked.connect(lambda _=False, t=title: open_default(t))
            else:
                card.clicked.connect(lambda _=False, k=key: open_example(k))
            self.example_cards.append(card)
        self.crane_card = ClickCard("cube", "Sample crane",
                                    "Open a measured crane assembly.")
        self.crane_card.clicked.connect(_open_reference)
        self.cards = [self.new_card] + self.example_cards + [self.crane_card]
        self.project_cards = []
        self.rows = []
        self.source = None
        self._cols = None
        self._has_crane = None
        self._filter = ""
        self.refresh_cards()
        self.refresh()

    # -- compatibility with the start-card layout (EmptyView, R34)
    def shown_cards(self):
        return [c for c in self.cards
                if c is not self.crane_card or self._has_crane]

    def columns_for(self, width):
        """As many 210 px cards as fit beside each other (12 px gaps, the
        page's margins), 1 to MAX_COLS."""
        avail = width - 2 * self.MARGIN + self.GAP
        return max(1, min(self.MAX_COLS, avail // (210 + self.GAP)))

    def refresh_cards(self):
        """The sample crane card only when this installation has it (R55)."""
        try:
            from . import viewport
            has = bool(viewport.crane_parts())
        except Exception as exc:                       # noqa: BLE001
            _log("crane parts: %r" % (exc,))
            has = False
        if has == self._has_crane:
            return
        self._has_crane = has
        self._relayout()

    def _layout_cards(self, cols):
        if cols == self._cols:
            return
        self._cols = cols
        self._relayout()

    def _relayout(self):
        cols = self._cols or 3
        for c in self.cards + self.project_cards:
            self.grid.removeWidget(c)
            self.ex_grid.removeWidget(c)
        shown = [self.new_card] + [c for c in self.project_cards
                                   if self._matches(c)]
        for i, c in enumerate(shown):
            self.grid.addWidget(c, i // cols, i % cols)
            c.setVisible(True)
        for c in self.project_cards:
            if c not in shown:
                c.setVisible(False)
        ex = list(self.example_cards) + ([self.crane_card] if self._has_crane else [])
        for i, c in enumerate(ex):
            self.ex_grid.addWidget(c, i // cols, i % cols)
            c.setVisible(True)
        if not self._has_crane:
            self.crane_card.setVisible(False)
        self.sec_examples.setVisible(bool(ex))
        for c in self.cards:
            c.set_compact(cols < 3)
        self._sync_note(len(shown) - 1)

    # -- data
    def _matches(self, card):
        f = self._filter
        return not f or f in card.row["name"].casefold()

    def apply_filter(self, text):
        self._filter = (text or "").strip().casefold()
        self._relayout()

    def _sync_note(self, n_shown):
        if self._filter and not n_shown:
            txt = "No project matches \u201c%s\u201d." % self.search.text().strip()
        elif not self.rows:
            txt = ("No saved projects yet. Start a new one, open a file or "
                   "drop it here, or start from an example below.")
        else:
            txt = ""
        self.note.setText(txt)
        self.note.setVisible(bool(txt))

    def refresh(self):
        """Re-read the projects. Cheap enough for 100 projects (the zip
        peeks are cached per file version)."""
        try:
            rows, self.source = home_projects()
        except Exception as exc:                       # noqa: BLE001
            _log("home projects: %r" % (exc,))
            rows, self.source = [], None
        old = {c.row["path"]: c for c in self.project_cards}
        keep = []
        for r in rows:
            c = old.pop(r["path"], None)
            if c is not None and c.row == r:
                keep.append(c)
                continue
            if c is not None:
                old[r["path"]] = c
            c = ProjectCard(r)
            c.clicked.connect(lambda _=False, p=r["path"]: open_project_path(p))
            c.restyle()
            keep.append(c)
        for c in old.values():
            self.grid.removeWidget(c)
            c.hide()
            c.deleteLater()
        self.rows = rows
        self.project_cards = keep
        self._relayout()
        return rows

    # -- events
    def showEvent(self, ev):                           # noqa: N802
        super().showEvent(ev)
        QtCore.QTimer.singleShot(0, self._refresh_if_shown)

    def _refresh_if_shown(self):
        try:
            if self.isVisible():
                self.refresh()
        except RuntimeError:
            pass

    def resizeEvent(self, ev):                         # noqa: N802
        self._layout_cards(self.columns_for(ev.size().width()))
        super().resizeEvent(ev)

    def _set_dropping(self, on):
        if bool(self.property("dropping")) != on:
            self.setProperty("dropping", on)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

    def dragEnterEvent(self, ev):                      # noqa: N802
        if droppable(_event_paths(ev)):
            ev.acceptProposedAction()
            self._set_dropping(True)
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):                       # noqa: N802
        if droppable(_event_paths(ev)):
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def dragLeaveEvent(self, ev):                      # noqa: N802
        self._set_dropping(False)
        super().dragLeaveEvent(ev)

    def dropEvent(self, ev):                           # noqa: N802
        self._set_dropping(False)
        paths = droppable(_event_paths(ev))
        if paths:
            ev.acceptProposedAction()
            open_paths(paths)
        else:
            ev.ignore()

    def restyle(self):
        self.refresh_cards()
        self.setStyleSheet(style.qss(HOME_QSS))
        t = style.tokens()
        self.credit.setText(
            style.PRODUCT + ', powered by FreeCAD \u00b7 <a href="credits" '
            'style="color:%s; text-decoration:none;">Credits</a>' % t["accent"])
        pm = style.logo_pixmap(26)
        if pm is not None:
            self.mark.setPixmap(pm)
        if self._search_act is not None:
            self.search.removeAction(self._search_act)
        self._search_act = self.search.addAction(
            style.icon("search", t["dim"], 14),
            QtWidgets.QLineEdit.LeadingPosition)
        for c in self.cards + self.project_cards:
            c.restyle()


class OrbitHint(QtWidgets.QFrame):
    """First-run card over the 3D view (R305): how to orbit, pan and zoom
    with the navigation style in use. "Got it" hides it for good."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("OrbitHint")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setAccessibleName("How to move around the model")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        self.title = QtWidgets.QLabel("Move around your model")
        self.title.setObjectName("HintTitle")
        lay.addWidget(self.title)
        self.rows = QtWidgets.QGridLayout()
        self.rows.setHorizontalSpacing(14)
        self.rows.setVerticalSpacing(4)
        lay.addLayout(self.rows)
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.btn_style = QtWidgets.QPushButton("Change style\u2026")
        self.btn_style.setObjectName("HintLink")
        self.btn_style.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_style.clicked.connect(lambda: open_appearance())
        btns.addWidget(self.btn_style)
        self.btn_ok = QtWidgets.QPushButton("Got it")
        self.btn_ok.setObjectName("HintBtn")
        self.btn_ok.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_ok.clicked.connect(self.dismiss)
        btns.addWidget(self.btn_ok)
        lay.addLayout(btns)
        self.setVisible(False)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QtGui.QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)
        self.fill()

    def fill(self):
        from . import viewport
        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        info = viewport.nav_info()
        self.title.setText("Move around your model (%s)" % info["label"])
        for i, (action, how) in enumerate(info["how"]):
            a = QtWidgets.QLabel(action)
            a.setObjectName("HintAction")
            h = QtWidgets.QLabel(how)
            h.setObjectName("HintHow")
            self.rows.addWidget(a, i, 0)
            self.rows.addWidget(h, i, 1)
        self.adjustSize()

    @staticmethod
    def wanted():
        from . import viewport
        return not viewport.orbit_hint_seen()

    def dismiss(self):
        from . import viewport
        viewport.set_orbit_hint_seen(True)
        self.hide()

    def restyle(self):
        self.setStyleSheet(style.qss(HINT_QSS))
        self.adjustSize()


#: R303: view-bar slots for tools other workstreams provide. Their buttons
#: sit between the view toggles and Spin, in this order; a key not listed
#: here goes after them. See register_view_tool().
TOOL_ORDER = ("measure", "section", "show", "explode", "dims", "shape", "colour",
              "export", "share")
_TOOLS = {}
#: R380: the slot shows two groups, inspect | output, with a thin line
#: between them. A key in neither group joins the last one.
#: R701: Show and hide and Exploded view are ways of looking, so they sit
#: with Measure and Section; Dimensions edits, as Colour does.
TOOL_GROUPS = (("measure", "section", "show", "explode"),
               ("dims", "colour", "export", "share"))
#: R380: the view-bar level (ViewBar.set_level) from which a tool's button
#: leaves the bar for the "More tools" menu; a key not listed goes at 2.
#: Measure and Section stay (they also have M and Shift+S).
TOOL_DROP_LEVEL = {"share": 1, "dims": 1, "explode": 2, "colour": 2,
                   "export": 2, "measure": 99, "section": 99, "show": 99}
#: Lucide "ellipsis", for the More tools button (as navbar adds "save").
style.PATHS.setdefault("more", '<circle cx="12" cy="12" r="1"/>'
                       '<circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>')


def register_view_tool(key, factory=None, run=None, label=None, restyle=None):
    """Put a tool on the view bar and/or behind its shortcut (R303).

    key      "measure", "section", "export"... (TOOL_ORDER) or another name
    factory  callable(view_bar) -> QWidget (a callable taking no argument
             is called without one): the button shown in the bar. A
             QAbstractButton without an objectName gets the bar's look
    run      callable(), what the shortcut does (M for measure, Shift+S
             for section); None leaves the built-in fallback
    label    the name for the shortcut sheet
    restyle  callable(widget), run on every light/dark restyle

    Safe to call before or after the shell is installed: a live bar mounts
    the button at once, the next one on install."""
    _TOOLS[key] = {"factory": factory, "run": run, "label": label,
                   "restyle": restyle}
    ov = _S.get("overlay")
    if ov is not None:
        try:
            ov.bar.mount_tools()
            ov.place()
        except RuntimeError:
            pass
    return True


def unregister_view_tool(key):
    _TOOLS.pop(key, None)
    ov = _S.get("overlay")
    if ov is not None:
        try:
            ov.bar.mount_tools()
        except RuntimeError:
            pass


def run_tool(key, fallback=None):
    """The registered tool's run(), else `fallback` (a FreeCAD command
    name). True when something ran."""
    entry = _TOOLS.get(key) or {}
    fn = entry.get("run")
    if fn is not None:
        _safe(fn)
        return True
    if fallback:
        try:
            import FreeCADGui
            FreeCADGui.runCommand(fallback)
            return True
        except Exception as exc:                       # noqa: BLE001
            _log("%s: %r" % (fallback, exc))
    return False


def click_tool(key):
    """Press the live view bar's `key` tool button (a checkable one, such
    as Measure, toggles its card). True when there was one to press; the
    button works from the More tools menu too, hidden or not."""
    ov = _S.get("overlay")
    if ov is None:
        return False
    try:
        w = ov.bar._tool_widgets.get(key)
        if w is None or not _alive(w):
            return False
        w.click()
        return True
    except RuntimeError:
        return False


def _w4_button(bar, key):
    """One of W4's view-bar buttons (export_tools.view_bar_buttons builds
    the four together, sharing their dialogs), made once per bar."""
    btns = getattr(bar, "_w4", None)
    if btns is None or not all(_alive(b) for b in btns.values()):
        from . import export_tools
        btns = export_tools.view_bar_buttons(bar)
        bar._w4 = btns
    return btns[key]


def _w4_restyle(w):
    from . import export_tools
    export_tools.restyle_buttons({"tool": w})


#: (key, label) of the tools Atech itself puts on the view bar (R380).
BUILTIN_TOOLS = (("measure", "Measure"), ("section", "Section view"),
                 ("colour", "Colour"), ("explode", "Exploded view"),
                 ("export", "Export for print"),
                 ("share", "Save a share image"))
#: R700/R701: Show and hide (visibility.py) and Dimensions (dimensions.py).
EDIT_TOOLS = (("show", "Show and hide"), ("dims", "Dimensions"),
              ("shape", "Edit shapes"))


def _measure_button(bar, key):
    from . import measure
    return (measure.make_measure_button if key == "measure"
            else measure.make_section_button)(bar)


_FALLBACK = {"measure": "Std_Measure", "section": "Std_ToggleClipPlane"}


def _press(key):
    """M / Shift+S: press the bar's button; with no bar (or no button)
    FreeCAD's own command for it, when there is one."""
    if click_tool(key):
        return True
    cmd = _FALLBACK.get(key)
    if cmd:
        try:
            import FreeCADGui
            FreeCADGui.runCommand(cmd)
            return True
        except Exception as exc:                       # noqa: BLE001
            _log("%s: %r" % (cmd, exc))
    return False


def register_builtin_tools():
    """R380: Measure and Section (measure.py, W3) and Colour, Exploded
    view, Export for print and Share image (export_tools.py, W4) on the
    view bar, M and Shift+S pressing the same buttons. Registered when the
    shell module loads; nothing is imported until a bar is built, and a
    factory that fails leaves only its own button out (mount_tools logs
    it; M / Shift+S then fall back to FreeCAD's Std_Measure /
    Std_ToggleClipPlane through run_tool)."""
    for key, label in BUILTIN_TOOLS[:2]:
        register_view_tool(key, lambda bar, k=key: _measure_button(bar, k),
                           run=lambda k=key: _press(k), label=label)
    for key, label in BUILTIN_TOOLS[2:]:
        register_view_tool(key, lambda bar, k=key: _w4_button(bar, k),
                           run=lambda k=key: _press(k), label=label,
                           restyle=_w4_restyle)
    for key, label in EDIT_TOOLS:
        register_view_tool(key, lambda bar, k=key: _edit_button(bar, k),
                           run=lambda k=key: _press(k), label=label)
    return [k for k, _l in BUILTIN_TOOLS + EDIT_TOOLS]


def _edit_button(bar, key):
    if key == "show":
        from . import visibility
        return visibility.view_bar_button(bar)
    if key == "shape":
        from . import manual_edit
        return manual_edit.view_bar_button(bar)
    from . import dimensions
    return dimensions.view_bar_button(bar)


def _wants_arg(fn):
    """True when `fn` has a required positional parameter (the view bar)."""
    import inspect
    try:
        ps = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.default is p.empty and p.kind in (p.POSITIONAL_ONLY,
                                                   p.POSITIONAL_OR_KEYWORD)
               for p in ps)


class ViewBar(QtWidgets.QFrame):
    """The floating pill over the 3D view."""

    MAX_LEVEL = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ViewBar")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setAccessibleName("View controls")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(2)
        self._icons = []
        self._wire = {}                 # sub-window -> wireframe on (per view)

        from . import viewport
        self.btn_fit = self._btn("", "fit", "Fit the model to the view",
                                 viewport.fit_all, name="Fit all")
        lay.addWidget(self.btn_fit)
        self.btn_fit_sel = self._btn(
            "", "focus", "Fit the selection to the view (nothing selected: "
            "everything)", viewport.fit_selection, name="Fit selection")
        lay.addWidget(self.btn_fit_sel)
        self._named = [self._sep()]
        for label, fn in (("Iso", viewport.axonometric), ("Front", viewport.view_front),
                          ("Top", viewport.view_top), ("Right", viewport.view_right)):
            self._named.append(self._btn(label, None, "%s view" % label, fn))
        for w in self._named:
            lay.addWidget(w)
        # Rear / Left / Bottom (R303), and every named view again, so a
        # narrow bar that drops the named buttons still reaches them all.
        self.btn_views = self._btn("", "chevron-down",
                                   "More views: rear, left, bottom", None,
                                   name="More views")
        self.views_menu = QtWidgets.QMenu(self.btn_views)
        self.views_menu.setAccessibleName("Views")
        for label, fn in (("Isometric", viewport.axonometric),
                          ("Front", viewport.view_front),
                          ("Top", viewport.view_top),
                          ("Right", viewport.view_right),
                          ("Rear", viewport.view_rear),
                          ("Left", viewport.view_left),
                          ("Bottom", viewport.view_bottom)):
            act = self.views_menu.addAction(label)
            act.triggered.connect(lambda _=False, f=fn: _safe(f))
        self.btn_views.setMenu(self.views_menu)
        lay.addWidget(self.btn_views)
        lay.addWidget(self._sep())
        self.btn_persp = self._btn("", "perspective",
                                   "Perspective camera (off: orthographic)",
                                   None, name="Perspective")
        self.btn_persp.setCheckable(True)
        self.btn_persp.toggled.connect(self._on_persp)
        lay.addWidget(self.btn_persp)
        self.btn_wire = self._btn("", "wire", "Wireframe (off: shaded)", None,
                                  name="Wireframe")
        self.btn_wire.setCheckable(True)
        self.btn_wire.toggled.connect(self._on_wire)
        lay.addWidget(self.btn_wire)
        # The tool slot (R303): Measure, Section, Export from other modules.
        self._tool_sep = self._sep()
        lay.addWidget(self._tool_sep)
        self.tool_slot = QtWidgets.QHBoxLayout()
        self.tool_slot.setContentsMargins(0, 0, 0, 0)
        self.tool_slot.setSpacing(2)
        lay.addLayout(self.tool_slot)
        self._tool_widgets = {}
        self._group_sep = self._sep()
        self._group_sep.hide()
        # R380: tools a narrow bar drops are one click away here.
        self.btn_more_tools = self._btn("", "more", "More tools", None,
                                        name="More tools")
        self.more_menu = QtWidgets.QMenu(self.btn_more_tools)
        self.more_menu.setAccessibleName("More tools")
        self.more_menu.aboutToShow.connect(self._fill_more_tools)
        self.btn_more_tools.setMenu(self.more_menu)
        self.btn_more_tools.hide()
        lay.addWidget(self.btn_more_tools)
        lay.addWidget(self._sep())
        self.btn_spin = self._btn("", "rotate", "Spin the model", None,
                                  name="Spin")
        self.btn_spin.setCheckable(True)
        self.btn_spin.toggled.connect(self._on_spin)
        lay.addWidget(self.btn_spin)
        self.btn_full = self._btn("", "maximize",
                                  "Full-screen 3D: hide the sidebar", None,
                                  name="Full-screen 3D")
        self.btn_full.setCheckable(True)
        self.btn_full.toggled.connect(self._on_full)
        lay.addWidget(self.btn_full)
        self.btn_shot = self._btn("", "camera", "Add this view to the chat",
                                  _add_view, name="Add this view to the chat")
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
        # Dropped last, at level 3, in a very narrow viewport.
        self._secondary = [self.btn_fit_sel, self.btn_persp, self.btn_wire,
                           self.btn_spin]
        self.level = 0
        self.mount_tools()

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QtGui.QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)

    def _btn(self, text, icon_name, tip, fn, name=None):
        b = QtWidgets.QPushButton(text)
        b.setObjectName("VBtn")
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.setAccessibleName(name or text or tip)
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

    def _on_persp(self, on):
        from . import viewport
        _safe(lambda: viewport.set_perspective(on))

    def _on_wire(self, on):
        from . import viewport
        _safe(lambda: viewport.set_wireframe(on))
        sw = self._active_sub()
        if sw is not None:
            self._wire[sw] = on

    def _on_full(self, on):
        set_focus_view(on)

    def _active_sub(self):
        try:
            mdi = self.parent()
            return mdi.activeSubWindow() if isinstance(mdi, QtWidgets.QMdiArea) \
                else None
        except RuntimeError:
            return None

    def sync_view(self):
        """Show the ACTIVE view's camera and draw style: both are per view,
        so switching documents must not leave the other view's state lit."""
        from . import viewport
        cam = None
        try:
            cam = viewport.camera_type()
        except Exception:                              # noqa: BLE001
            pass
        for b, on in ((self.btn_persp, cam == "Perspective" if cam else None),
                      (self.btn_wire, bool(self._wire.get(self._active_sub())))):
            if on is None:
                continue
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
        live = set()
        try:
            mdi = self.parent()
            live = set(mdi.subWindowList()) if isinstance(mdi, QtWidgets.QMdiArea) else set()
        except RuntimeError:
            pass
        for sw in [k for k in self._wire if k not in live]:
            self._wire.pop(sw, None)

    def mount_tools(self):
        """(Re)build the tool slot from the registry, in TOOL_ORDER."""
        keys = [k for k in TOOL_ORDER if k in _TOOLS] + \
            sorted(k for k in _TOOLS if k not in TOOL_ORDER)
        for k in list(self._tool_widgets):
            if k not in keys or _TOOLS[k].get("factory") is None:
                w = self._tool_widgets.pop(k)
                self.tool_slot.removeWidget(w)
                w.hide()
                w.deleteLater()
        for k in keys:
            fac = _TOOLS[k].get("factory")
            if fac is None or k in self._tool_widgets:
                continue
            try:
                w = fac(self) if _wants_arg(fac) else fac()
            except Exception as exc:                   # noqa: BLE001
                _log("view tool %s: %r" % (k, exc))
                continue
            if w is None:
                continue
            if isinstance(w, QtWidgets.QAbstractButton) and not w.objectName():
                w.setObjectName("VBtn")
                w.setCursor(QtCore.Qt.PointingHandCursor)
                w.setMinimumHeight(30)
            if not w.accessibleName():
                w.setAccessibleName(_TOOLS[k].get("label") or k.title())
            w.setProperty("atechTool", k)
            self._tool_widgets[k] = w
        self.tool_slot.removeWidget(self._group_sep)
        first = set(TOOL_GROUPS[0])
        placed_sep = False
        for k in keys:                                 # in order
            w = self._tool_widgets.get(k)
            if w is not None:
                if not placed_sep and k not in first and any(
                        j in self._tool_widgets for j in first):
                    self.tool_slot.addWidget(self._group_sep)
                    placed_sep = True
                self.tool_slot.removeWidget(w)
                self.tool_slot.addWidget(w)
        self._group_sep.setProperty("atechPlaced", placed_sep)
        self._tool_sep.setVisible(bool(self._tool_widgets))
        self._apply_tool_level()
        self.adjustSize()

    def tool_label(self, key):
        """The plain name of a tool (its registry label, else its button's
        accessible name)."""
        entry = _TOOLS.get(key) or {}
        w = self._tool_widgets.get(key)
        return entry.get("label") or (w.accessibleName() if w is not None
                                      else key.title())

    def dropped_tools(self):
        """Keys of the tools the current level moved into More tools."""
        return [k for k in [k for k in TOOL_ORDER if k in self._tool_widgets]
                + sorted(k for k in self._tool_widgets if k not in TOOL_ORDER)
                if self.level >= TOOL_DROP_LEVEL.get(k, 2)]

    def _apply_tool_level(self):
        """R380: at a narrow level the less used tools leave the bar for
        the More tools menu; the group line shows only between two
        visible groups."""
        dropped = set(self.dropped_tools())
        for k, w in self._tool_widgets.items():
            w.setVisible(k not in dropped)
        first = set(TOOL_GROUPS[0])
        shown = [k for k in self._tool_widgets if k not in dropped]
        self._group_sep.setVisible(
            bool(self._group_sep.property("atechPlaced"))
            and any(k in first for k in shown)
            and any(k not in first for k in shown))
        self.btn_more_tools.setVisible(bool(dropped))

    def _fill_more_tools(self):
        """The More tools menu: one entry per dropped tool, which presses
        that tool's own button (so a toggle stays in step)."""
        self.more_menu.clear()
        for k in self.dropped_tools():
            w = self._tool_widgets.get(k)
            if w is None:
                continue
            act = self.more_menu.addAction(self.tool_label(k))
            try:
                act.setIcon(w.icon())
            except Exception:                          # noqa: BLE001
                pass
            if getattr(w, "isCheckable", lambda: False)():
                act.setCheckable(True)
                act.setChecked(w.isChecked())
            act.triggered.connect(lambda _=False, b=w: b.click())
        return [a.text() for a in self.more_menu.actions()]

    def tools(self):
        return [self._tool_widgets[k] for k in
                [k for k in TOOL_ORDER if k in self._tool_widgets]
                + sorted(k for k in self._tool_widgets if k not in TOOL_ORDER)]

    def set_level(self, level):
        """0 full; 1 the Ask button shows its icon only, and Exploded view
        and Share image move into More tools; 2 the named views
        (Iso/Front/Top/Right) go as well (all stay in More views), and so
        do Colour and Export; 3 fit selection, perspective, wireframe and
        spin go too. For narrow viewports (R34, R303, R380)."""
        if level == self.level:
            return
        self.level = level
        self.btn_ask.setText("" if level >= 1 else icon_label(ASK_TEXT))
        for w in self._named:
            w.setVisible(level < 2)
        for w in self._secondary:
            w.setVisible(level < 3)
        self._apply_tool_level()
        self.adjustSize()

    def set_full(self, on):
        """Reflect the full-screen 3D state without re-triggering it."""
        self.btn_full.blockSignals(True)
        self.btn_full.setChecked(bool(on))
        self.btn_full.blockSignals(False)
        self.btn_full.setToolTip("Show the sidebar again" if on
                                 else "Full-screen 3D: hide the sidebar")
        self._paint_full()

    def _paint_full(self):
        t = style.tokens()
        self.btn_full.setIcon(style.icon(
            "minimize" if self.btn_full.isChecked() else "maximize",
            t["muted"], 16))

    def restyle(self):
        self.setStyleSheet(style.qss(VIEWBAR_QSS))
        t = style.tokens()
        for b, n in self._icons:
            b.setIcon(style.icon(n, t["muted"], 16))
        self._paint_full()
        self.btn_ask.setIcon(style.icon("sparkles", t["btn_text"], 14))
        for k, w in list(self._tool_widgets.items()):
            fn = (_TOOLS.get(k) or {}).get("restyle")
            try:
                if fn is not None:
                    fn(w)
                elif w.property("atech_icon") in style.PATHS:
                    w.setIcon(style.icon(w.property("atech_icon"), t["muted"], 16))
            except Exception as exc:                   # noqa: BLE001
                _log("view tool restyle %s: %r" % (k, exc))
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
        # R308: Home (projects, examples, drop target) replaces the old
        # three-card start page; that page stays as the fallback should
        # Home fail to build, so the viewport is never left blank.
        try:
            self.empty = HomeView(mdi)
        except Exception as exc:                       # noqa: BLE001
            _log("home view: %r" % (exc,))
            self.empty = EmptyView(mdi)
        self.hint = OrbitHint(mdi)
        self._queued = False
        self._key = None
        self._dead = False
        self._boxes = []
        self._on_docs = on_docs
        mdi.installEventFilter(self)
        mdi.viewport().installEventFilter(self)   # sub-windows live here
        mdi.subWindowActivated.connect(self._queue)
        mdi.subWindowActivated.connect(self._on_sub)
        self.place()

    def _on_sub(self, *_):
        # A project brought to the front (opened from Home, picked in the
        # project menu) means the user is back in the 3D view.
        _leave_home()
        try:
            self.bar.sync_view()
        except Exception as exc:                       # noqa: BLE001
            _log("view bar sync: %r" % (exc,))

    def eventFilter(self, obj, ev):                    # noqa: N802
        t = ev.type()
        if t in (QtCore.QEvent.ChildAdded, QtCore.QEvent.ChildRemoved):
            # Only widgets (sub-windows, panels) move the bar. Qt's style
            # animations are QObject children of the MDI area too, started
            # by a repaint: counting them made place() -> repaint ->
            # animation -> place() spin ~700 times a second (measured).
            try:
                ch = ev.child()
                if ch is not None and not ch.isWidgetType():
                    return False
            except RuntimeError:
                return False
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
        home = not has_doc or home_open()          # R801: Home mode
        free = self.free_rect(vp) if not home else vp
        key = (vp.x(), vp.y(), vp.width(), vp.height(), has_doc, home,
               free.x(), free.width(), free.height())
        if not force and key == self._key:
            return
        self._key = key
        self.bar.setVisible(not home)
        self.empty.setVisible(home)
        show_hint = not home and self.hint.wanted()
        self.hint.setVisible(show_hint)
        if self._on_docs is not None:
            try:
                self._on_docs()
            except Exception as exc:                   # noqa: BLE001
                _log("docs hook: %r" % (exc,))
        if not home:
            avail = max(0, free.width() - 24)
            # Icons only in a small viewport (R84): the pill spanned the
            # whole view at 900x600 and covered the model.
            first = 2 if vp.width() < PILL_ICONS_PX else 0
            for level in range(first, ViewBar.MAX_LEVEL + 1):
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
            if show_hint:
                hs = self.hint.sizeHint()
                hw = min(hs.width(), max(0, free.width() - 24))
                self.hint.setGeometry(free.x() + (free.width() - hw) // 2,
                                      free.y() + 16, hw, hs.height())
                self.hint.raise_()
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
        for slot in (self._queue, self._on_sub):
            try:
                self.mdi.subWindowActivated.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        for w in (self.bar, self.empty, self.hint):
            w.hide()
            w.deleteLater()
        self.deleteLater()


class Sidebar(QtWidgets.QWidget):
    """The sidebar head - brand row (where the menu bar cannot show it),
    the project picker with Terminal and Settings, the hardware switch,
    then 3D CAD | Atech modules - over a stack (studio.atech.dev's navbar
    and Simple / Advanced control; see navbar.py).

    3D CAD is the chat under a collapsible Parts panel (R301): FreeCAD's
    own tree + property view, so the parts and the chat are on screen
    together and a selection in the 3D view lights up in the tree.
    show_page(idx) keeps its meaning: 0 the chat (Parts as it was), 1 the
    chat with Parts open, 2 the Atech modules."""

    PAGE_CHAT, PAGE_MODEL, PAGE_MODULES = 0, 1, 2
    PARTS_SHARE = 0.42          # of the 3D CAD page, when Parts first opens

    def __init__(self, chat, model_widget, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarBody")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        from . import navbar
        head = QtWidgets.QWidget()
        hv = QtWidgets.QVBoxLayout(head)
        hv.setContentsMargins(12, 12, 12, 8)
        hv.setSpacing(10)
        # R300: the wordmark, Terminal and Settings, where the macOS native
        # menu bar (which draws no corner widgets) would otherwise lose them.
        self.brand = QtWidgets.QWidget()
        self.brand.setObjectName("SideBrand")
        bl = QtWidgets.QHBoxLayout(self.brand)
        bl.setContentsMargins(2, 0, 0, 0)
        bl.setSpacing(8)
        self.brand_mark = QtWidgets.QLabel()
        bl.addWidget(self.brand_mark)
        self.brand_word = QtWidgets.QLabel(style.PRODUCT)
        self.brand_word.setObjectName("SideWordmark")
        self.brand_word.setAccessibleName(style.PRODUCT)
        bl.addWidget(self.brand_word)
        bl.addStretch(1)
        hv.addWidget(self.brand)
        # R801: the logo is the way Home (all projects), as on a website.
        self.brand.setCursor(QtCore.Qt.PointingHandCursor)
        self.brand.setToolTip("Home: all your projects (Ctrl+0)")
        self.brand.setAccessibleName("Home")
        self._home_click = _ClickFilter(toggle_home, self.brand)
        self.brand.installEventFilter(self._home_click)
        prow = QtWidgets.QHBoxLayout()
        prow.setContentsMargins(0, 0, 0, 0)
        prow.setSpacing(4)
        self.picker = navbar.ProjectPicker(
            on_new=lambda: _new_project(),
            on_open_file=lambda: _open_file())
        # W1's picker row (picker + Save) when this build has it.
        row_fn = getattr(navbar, "picker_row", None)
        self.picker_row = None
        if callable(row_fn):
            try:
                self.picker_row = row_fn(self.picker)
            except Exception as exc:                   # noqa: BLE001
                _log("picker row: %r" % (exc,))
        prow.addWidget(self.picker_row or self.picker, 1)
        self.btn_terminal = self._icon_btn("Terminal", "Open a terminal")
        self.btn_terminal.clicked.connect(lambda: _open_terminal())
        prow.addWidget(self.btn_terminal)
        self.btn_settings = self._icon_btn(
            "Settings", "Settings, appearance and keyboard shortcuts")
        self.btn_settings.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.btn_settings.setMenu(settings_menu(self.btn_settings))
        prow.addWidget(self.btn_settings)
        hv.addLayout(prow)
        # R280: Only CAD | CAD + electronics, at the top of the sidebar. Not
        # in the menu bar's corner: on macOS the native menu bar draws no
        # corner widgets, so it would never show there.
        self.hw_switch = _hardware_switch()
        if self.hw_switch is not None:
            hv.addWidget(self.hw_switch)
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.tabs = navbar.PillTabs(["3D CAD", "Atech modules"])
        self.tabs.changed.connect(self._on_tab)
        row.addWidget(self.tabs, 1)
        self.btn_parts = QtWidgets.QToolButton()
        self.btn_parts.setObjectName("PartsBtn")
        self.btn_parts.setCheckable(True)
        self.btn_parts.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_parts.setIconSize(QtCore.QSize(16, 16))
        self.btn_parts.setFixedSize(36, 36)
        self.btn_parts.setToolTip("Parts: show or hide the part tree above "
                                  "the chat")
        self.btn_parts.setAccessibleName("Parts")
        self.btn_parts.toggled.connect(self._on_parts)
        row.addWidget(self.btn_parts)
        hv.addLayout(row)
        lay.addWidget(head)
        self.header_chrome = None
        self.set_header_chrome(False)
        # The picker names the ACTIVE document. It follows FreeCAD's
        # document events and the MDI area's window changes (R302); the
        # shell's slow safety tick backs that up - no 800 ms poll.

        self.stack = QtWidgets.QStackedWidget()
        self.chat = chat
        self.cad_page = QtWidgets.QWidget()
        cv = QtWidgets.QVBoxLayout(self.cad_page)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        self.parts_head = QtWidgets.QWidget()
        self.parts_head.setObjectName("PartsHead")
        self.parts_head.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        ph = QtWidgets.QHBoxLayout(self.parts_head)
        ph.setContentsMargins(8, 3, 8, 3)
        self.parts_toggle = QtWidgets.QToolButton()
        self.parts_toggle.setObjectName("PartsToggle")
        self.parts_toggle.setText("PARTS")
        self.parts_toggle.setCheckable(True)
        self.parts_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self.parts_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.parts_toggle.setIconSize(QtCore.QSize(12, 12))
        self.parts_toggle.setAccessibleName("Parts panel")
        self.parts_toggle.setToolTip("Show or hide the part tree")
        self.parts_toggle.toggled.connect(self.set_parts_open)
        ph.addWidget(self.parts_toggle)
        ph.addStretch(1)
        # R700/R701: the two hand controls, where the parts are listed.
        self.parts_links = {}
        for key, text, tip in (
                ("show", "Show and hide", "Show, hide, isolate and explode "
                 "the parts"),
                ("dims", "Dimensions", "Change the model's numbers by hand "
                 "(D)")):
            b = QtWidgets.QToolButton()
            b.setObjectName("PartsToggle")
            b.setText(text)
            b.setToolTip(tip)
            b.setAccessibleName(text)
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key, w=b: _safe(
                lambda: self._parts_link(k, w)))
            ph.addWidget(b)
            self.parts_links[key] = b
        cv.addWidget(self.parts_head)
        self.cad_split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.cad_split.setObjectName("CadSplit")
        self.cad_split.setChildrenCollapsible(False)
        self.cad_split.setHandleWidth(1)
        cv.addWidget(self.cad_split, 1)
        self.model_page = QtWidgets.QWidget()
        self.model_page.setObjectName("ModelPage")
        self.model_page.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.model_page.setMinimumHeight(90)
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
        self.cad_split.addWidget(self.model_page)
        self.cad_split.addWidget(chat)
        self.cad_split.setStretchFactor(0, 0)
        self.cad_split.setStretchFactor(1, 1)
        self._parts_open = False
        self._parts_sizes = None
        self.model_page.setVisible(False)
        self.stack.addWidget(self.cad_page)
        from .modules_page import ModulesPage
        self.modules_page = ModulesPage()
        self.stack.addWidget(self.modules_page)
        lay.addWidget(self.stack, 1)
        self.sync_model_hint()

    @staticmethod
    def _parts_link(key, anchor):
        if key == "show":
            from . import visibility
            return visibility.show_popover(anchor)
        return _open_dimensions()

    def _icon_btn(self, name, tip):
        b = QtWidgets.QToolButton()
        b.setObjectName("SideIconBtn")
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setIconSize(QtCore.QSize(16, 16))
        b.setFixedSize(36, 36)
        b.setToolTip(tip)
        b.setAccessibleName(name)
        b.setFocusPolicy(QtCore.Qt.TabFocus)
        return b

    def set_header_chrome(self, on):
        """Show the brand row and the Terminal / Settings buttons in the
        sidebar head (R300): on where the menu bar's corners are not drawn
        (macOS), off where the top bar already carries them (Linux)."""
        on = bool(on)
        if on == self.header_chrome:
            return
        self.header_chrome = on
        for w in (self.brand, self.btn_terminal, self.btn_settings):
            w.setVisible(on)

    def _on_tab(self, i):
        self.show_page(self.PAGE_MODULES if i == 1 else self.PAGE_CHAT)

    def _on_parts(self, on):
        self.set_parts_open(on)

    def parts_open(self):
        return self._parts_open

    def set_parts_open(self, on):
        """Open or collapse the Parts panel above the chat (R301)."""
        on = bool(on)
        for b in (self.btn_parts, self.parts_toggle):
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
        self._paint_parts_toggle()
        if on == self._parts_open:
            return
        if not on:
            sizes = self.cad_split.sizes()
            if len(sizes) == 2 and all(sizes):
                self._parts_sizes = sizes
        self._parts_open = on
        self.model_page.setVisible(on)
        if on:
            sizes = self._parts_sizes
            if not sizes:
                total = max(self.cad_split.height(), 400)
                top = int(total * self.PARTS_SHARE)
                sizes = [top, total - top]
            self.cad_split.setSizes(sizes)
        self.sync_model_hint()

    def toggle_parts(self):
        """Cmd+P: from the Atech modules tab, go to 3D CAD with Parts open."""
        if self.tabs.index() == 1:
            self.show_page(self.PAGE_MODEL)
        else:
            self.set_parts_open(not self._parts_open)

    def _paint_parts_toggle(self):
        try:
            t = style.tokens()
            self.parts_toggle.setIcon(style.icon(
                "chevron-down" if self._parts_open or self.parts_toggle.isChecked()
                else "chevron-right", t["muted"], 12))
        except AttributeError:          # during __init__, before _parts_open
            pass

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
        modules = idx == self.PAGE_MODULES
        self.tabs.set_index(1 if modules else 0)
        self.btn_parts.setVisible(not modules)
        if idx == self.PAGE_MODEL:
            self.set_parts_open(True)
        self.stack.setCurrentWidget(self.modules_page if modules
                                    else self.cad_page)
        self.sync_model_hint()

    def page(self):
        """The page shown, as show_page() numbers them."""
        if self.stack.currentWidget() is self.modules_page:
            return self.PAGE_MODULES
        return self.PAGE_MODEL if self._parts_open else self.PAGE_CHAT

    def restyle(self):
        self.setStyleSheet(style.qss(SIDEBAR_QSS))
        t = style.tokens()
        pm = style.logo_pixmap(18)
        if pm is not None:
            self.brand_mark.setPixmap(pm)
        self.btn_terminal.setIcon(style.icon("terminal", t["muted"], 16))
        self.btn_settings.setIcon(style.icon("settings", t["muted"], 16))
        self._paint_parts_toggle()
        ico = QtGui.QIcon()
        ico.addPixmap(style.icon("layers", t["text"], 16).pixmap(16, 16),
                      QtGui.QIcon.Normal, QtGui.QIcon.Off)
        ico.addPixmap(style.icon("layers", t["btn_text"], 16).pixmap(16, 16),
                      QtGui.QIcon.Normal, QtGui.QIcon.On)
        self.btn_parts.setIcon(ico)
        self.tabs.update()
        self.picker.refresh()
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


def _new_project():
    """Home's and the picker's "New project": W1's named-project flow
    (navbar.new_project_flow: asks a name, saves into the projects folder)
    when this build has it, else an empty document."""
    _leave_home()
    fn = getattr(navbar, "new_project_flow", None)
    if callable(fn):
        try:
            fn(_mw_or_none())
            return
        except Exception as exc:                       # noqa: BLE001
            _notify("Could not create the project",
                    "The details are in the Report view.", exc)
            return
    _new_document()


# ------------------------------------------------- open / switch (R302)
def _norm(path):
    try:
        return os.path.normcase(os.path.realpath(path))
    except (OSError, TypeError, ValueError):
        return path


def _open_doc_named_by_path(path):
    """The open document saved at `path` (real path compared), or None."""
    try:
        import FreeCAD
        want = _norm(path)
        for name, d in FreeCAD.listDocuments().items():
            fn = getattr(d, "FileName", "") or ""
            if fn and _norm(fn) == want:
                return name
    except Exception as exc:                           # noqa: BLE001
        _log("open docs: %r" % (exc,))
    return None


def pick_subwindow(subs, name, label, doc_of):
    """The sub-window showing document `name` (R302), or None.

    The old match (navbar.activate_document) took the first window whose
    TITLE started with the label, so two documents with one label (the
    same file name in two folders, "Unnamed" twice) switched to the wrong
    one. Here `doc_of(sw)` reports each window's document Name; windows
    whose title starts with the label are asked first, so the usual case
    asks once. A window whose document cannot be told is skipped."""
    label = label or ""

    def titled(sw):
        try:
            t = sw.windowTitle()
        except RuntimeError:
            return False
        return bool(label) and (t.startswith(label + " :")
                                or t.startswith(label + " ") or t == label)
    order = [sw for sw in subs if titled(sw)] + \
        [sw for sw in subs if not titled(sw)]
    for sw in order:
        try:
            if doc_of(sw) == name:
                return sw
        except Exception:                              # noqa: BLE001
            continue
    return None


def activate_document(name):
    """Bring document `name` (its Name, never its label) to the front: its
    3D view becomes the active MDI window and the chat follows (R302).

    navbar.activate_document(name) (the picker) calls this (R384).
    Returns True when a window was found."""
    import FreeCAD
    import FreeCADGui
    doc = FreeCAD.getDocument(name)
    try:
        FreeCAD.setActiveDocument(name)
    except Exception as exc:                           # noqa: BLE001
        _log("setActiveDocument: %r" % (exc,))
    mdi = _mw().centralWidget()
    if not isinstance(mdi, QtWidgets.QMdiArea):
        return False
    before = mdi.activeSubWindow()

    def doc_of(sw):
        # Activating a sub-window makes its document FreeCAD's active GUI
        # document synchronously (MainWindow::onWindowActivated).
        if sw is not mdi.activeSubWindow():
            mdi.setActiveSubWindow(sw)
        g = FreeCADGui.activeDocument()
        return g.Document.Name if g is not None else None

    sw = pick_subwindow(mdi.subWindowList(), name,
                        getattr(doc, "Label", ""), doc_of)
    if sw is not None:
        if mdi.activeSubWindow() is not sw:
            mdi.setActiveSubWindow(sw)
        return True
    if before is not None and mdi.activeSubWindow() is not before:
        mdi.setActiveSubWindow(before)            # nothing found: undo probes
    return False


def open_file(path):
    """R391: open a file the way the user means it. A .FCStd project opens
    with FreeCAD.openDocument: FreeCADGui.open() in FreeCAD 1.1.3 does not
    open .FCStd at all - it only logs "File type 'fcstd' not supported"
    and raises nothing (MEASURED in the real app: Home cards, Recent
    entries and dropped projects opened nothing). Anything else (STEP, STL,
    3MF) is imported by FreeCADGui.open as before."""
    if str(path).lower().endswith(".fcstd"):
        import FreeCAD
        return FreeCAD.openDocument(path)
    import FreeCADGui
    return FreeCADGui.open(path)


def open_project_path(path):
    """Open a saved project from Home: switch to it when it is open already."""
    _leave_home()
    name = _open_doc_named_by_path(path)
    try:
        if name is not None:
            activate_document(name)
            return name
        open_file(path)
        return True
    except Exception as exc:                           # noqa: BLE001
        _notify("Could not open the project",
                "%s could not be opened. The details are in the Report view."
                % os.path.basename(path), exc)
        return None


def _doc_name_for(stem):
    """A FreeCAD document Name from a file stem: letters, digits, _ only,
    not starting with a digit (FreeCAD rewrites anything else anyway)."""
    import re
    n = re.sub(r"[^0-9A-Za-z_]", "_", stem or "") or "Imported"
    return ("_" + n) if n[0].isdigit() else n


def open_path(path):
    """Open one dropped or chosen file (PRD Opening 4): a .FCStd as itself;
    STEP / STL / 3MF / IGES / BREP as a NEW project importing it, named
    after the file. Returns the document Name, or None on failure."""
    _leave_home()
    low = path.lower()
    if low.endswith(OPEN_EXT):
        r = open_project_path(path)
        if r is True:
            try:
                import FreeCAD
                d = FreeCAD.ActiveDocument
                return d.Name if d is not None else None
            except Exception:                          # noqa: BLE001
                return None
        return r
    if not low.endswith(IMPORT_EXT):
        return None
    stem = os.path.splitext(os.path.basename(path))[0]
    try:
        import FreeCAD
        import FreeCADGui
        doc = FreeCAD.newDocument(_doc_name_for(stem))
        doc.Label = stem
        FreeCADGui.insert(path, doc.Name)
        try:
            doc.recompute()
        except Exception:                              # noqa: BLE001
            pass
        try:
            from . import viewport
            viewport.iso_and_fit()
        except Exception:                              # noqa: BLE001
            pass
        return doc.Name
    except Exception as exc:                           # noqa: BLE001
        _notify("Could not import the file",
                "%s could not be imported. The details are in the Report "
                "view." % os.path.basename(path), exc)
        return None


def open_paths(paths):
    """Open every droppable file in `paths`; returns the documents opened."""
    out = []
    for p in droppable(paths):
        r = open_path(p)
        if r:
            out.append(r)
    return out


class DropFilter(QtCore.QObject):
    """Files dropped anywhere on the window that FreeCAD's own 3D view does
    not take (Home, the sidebar, the empty MDI area) open through
    open_path(), so STEP / STL / 3MF become new projects (R309)."""

    def eventFilter(self, obj, ev):                    # noqa: N802
        t = ev.type()
        if t in (QtCore.QEvent.DragEnter, QtCore.QEvent.DragMove):
            if droppable(_event_paths(ev)):
                ev.acceptProposedAction()
                return True
        elif t == QtCore.QEvent.Drop:
            paths = droppable(_event_paths(ev))
            if paths:
                ev.acceptProposedAction()
                QtCore.QTimer.singleShot(0, lambda p=paths: open_paths(p))
                return True
        return False


# --------------------------------------------------- examples (R310)
_EXAMPLE_RUNS = []


def _example_intent(path):
    """The example's INTENT = {...} literal (its intent.json), or None."""
    import ast
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "INTENT" for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def open_example(key):
    """"Start from an example": a NEW project built from
    agent_kit/examples/<key>.py, the way the agent's own build runs a
    model.py (sandboxed, polled from a timer, never blocking the GUI).

    The chat panel may take over (W6): when it has start_from_example(path,
    title), that is called instead, so the chat's workspace holds the
    example and the agent resumes from it. Returns the PendingBuild, the
    panel's result, or None."""
    _leave_home()
    title = next((t for k, t, _s, _i in EXAMPLES if k == key), key)
    path = example_path(key)
    if path is None:
        _notify("Example not available",
                "The %s example is not in this installation." % title.lower())
        return None
    p = chat_panel()
    hook = getattr(p, "start_from_example", None) if p is not None else None
    if callable(hook):
        try:
            return hook(path, title)
        except Exception as exc:                       # noqa: BLE001
            _notify("Could not start from the example",
                    "The details are in the Report view.", exc)
            return None
    try:
        import json
        import FreeCAD
        from . import build
        doc = FreeCAD.newDocument(_doc_name_for(title.replace(" ", "_")))
        doc.Label = title
        ws = build.new_workspace()
        with open(path, encoding="utf-8") as fh:
            code = fh.read()
        with open(os.path.join(ws, build.SCRIPT), "w", encoding="utf-8") as fh:
            fh.write(code)
        intent = _example_intent(path)
        if intent is not None:
            with open(os.path.join(ws, "intent.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(intent, fh)
        try:
            build.prepare_workspace(ws, reset_intent=False, doc=doc)
        except Exception as exc:                       # noqa: BLE001
            _log("example workspace: %r" % (exc,))
        pending = build.start(ws, [build.SCRIPT],
                              previous={"uid": build._doc_key(doc)})
    except Exception as exc:                           # noqa: BLE001
        _notify("Could not start from the example",
                "The details are in the Report view.", exc)
        return None
    if pending is None:
        _notify("Could not start from the example",
                "The example had nothing to build.")
        return None
    _watch_example(pending, title)
    return pending


def _watch_example(pending, title, interval=150):
    timer = QtCore.QTimer()
    timer.setInterval(interval)
    _EXAMPLE_RUNS.append(timer)

    def tick():
        try:
            res = pending.poll()
        except Exception as exc:                       # noqa: BLE001
            timer.stop()
            _EXAMPLE_RUNS.remove(timer)
            _notify("The %s example did not build" % title.lower(),
                    "The details are in the Report view.", exc)
            return
        if res is None:
            return
        timer.stop()
        if timer in _EXAMPLE_RUNS:
            _EXAMPLE_RUNS.remove(timer)
        if getattr(res, "ok", False):
            try:
                from . import viewport
                viewport.iso_and_fit()
            except Exception:                          # noqa: BLE001
                pass
        else:
            _notify("The %s example did not build" % title.lower(),
                    (getattr(res, "error", "") or "The details are in the "
                     "Report view.")[:400])
    timer.timeout.connect(tick)
    timer.start()
    return timer


# --------------------------------------------- full-screen 3D (R303)
def set_focus_view(on):
    """Full-screen 3D: hide the sidebar so the model has the window, or
    bring it back. The view bar's button and Cmd+Shift+F toggle it."""
    dock = _S.get("dock")
    if dock is None:
        return False
    on = bool(on)
    _S["focus_view"] = on
    try:
        dock.setVisible(not on)
    except RuntimeError:
        return False
    ov = _S.get("overlay")
    if ov is not None:
        ov.bar.set_full(on)
        ov._queue()
    return True


def focus_view():
    return bool(_S.get("focus_view"))


# --------------------------------------------------- shortcuts (R307)
#: (id, key sequence, what it does, section). Ctrl is Cmd on macOS (Qt maps
#: it). M and Shift+S do not fire while typing: a text field takes them.
SHORTCUTS = (
    ("focus_chat", "Ctrl+L", "Type in the chat", "Atech"),
    ("tab_cad", "Ctrl+1", "3D CAD tab", "Atech"),
    ("tab_modules", "Ctrl+2", "Atech modules tab", "Atech"),
    ("parts", "Ctrl+P", "Show or hide the Parts panel", "Atech"),
    ("measure", "M", "Measure", "Atech"),
    ("section", "Shift+S", "Section view", "Atech"),
    # R701: the view's everyday controls. Single keys, as M: a text field
    # takes them while typing.
    ("hide", "H", "Hide the selected parts", "Atech"),
    ("isolate", "I", "Show only the selected parts", "Atech"),
    ("show_all", "Shift+H", "Show every part again", "Atech"),
    ("see_through", "T", "See-through on the selected parts, or solid again",
     "Atech"),
    ("explode", "E", "Exploded view, or put the parts back", "Atech"),
    ("dims", "D", "Change the model's dimensions by hand", "Atech"),
    ("shape", "R", "Edit shapes: add shapes, type exact sizes, holes", "Atech"),
    ("home", "Ctrl+0", "Home: all your projects (Esc goes back)", "Atech"),
    ("ask", "Ctrl+Shift+A", "Ask about this view", "Atech"),
    ("full", "Ctrl+Shift+F", "Full-screen 3D (hide the sidebar)", "Atech"),
    ("sheet", "Ctrl+/", "Show these shortcuts", "Atech"),
)
#: FreeCAD's own, listed on the sheet (they keep working: the menus are
#: FreeCAD's). Measured in the audit's probe of the menus.
FREECAD_KEYS = (
    ("Ctrl+N", "New document"), ("Ctrl+O", "Open"), ("Ctrl+S", "Save"),
    ("Ctrl+Shift+S", "Save as"), ("Ctrl+Z", "Undo"), ("Ctrl+Y", "Redo"),
    ("V, F", "Fit all"), ("V, S", "Fit selection"),
    ("0", "Isometric view"), ("1 / 3 / 2", "Front / Right / Top view"),
    ("4 / 6 / 5", "Rear / Left / Bottom view"),
    ("V, O / V, P", "Orthographic / perspective"),
    ("Space", "Show or hide the selected part"), ("F11", "Full screen"),
)


def _shortcut_fn(sid):
    def focus_chat():
        p = show_chat()
        f = getattr(p, "focus_composer", None)
        if callable(f):
            f()
            return
        inp = getattr(p, "input", None)
        (inp or p).setFocus(QtCore.Qt.ShortcutFocusReason)

    def tab(i):
        body = _S.get("body")
        if body is not None:
            if focus_view():
                set_focus_view(False)
            body.show_page(body.PAGE_MODULES if i else body.PAGE_CHAT)

    def parts():
        body = _S.get("body")
        if body is not None:
            if focus_view():
                set_focus_view(False)
            body.toggle_parts()

    return {
        "focus_chat": focus_chat,
        "tab_cad": lambda: tab(0),
        "tab_modules": lambda: tab(1),
        "parts": parts,
        "measure": lambda: run_tool("measure", "Std_Measure"),
        "section": lambda: run_tool("section", "Std_ToggleClipPlane"),
        "ask": _ask_view,
        "full": lambda: set_focus_view(not focus_view()),
        "sheet": open_shortcut_sheet,
        "hide": lambda: _visibility_key("key_hide"),
        "isolate": lambda: _visibility_key("key_isolate"),
        "show_all": lambda: _visibility_key("key_show_all"),
        "see_through": lambda: _visibility_key("key_see_through"),
        "explode": lambda: _visibility_key("key_explode"),
        "dims": _open_dimensions,
        "shape": _open_shape_editor,
        "home": toggle_home,
    }[sid]


def _visibility_key(name):
    from . import visibility
    return getattr(visibility, name)()


def _open_dimensions():
    from . import dimensions
    return dimensions.open_dialog(_mw_or_none())


def _open_shape_editor():
    from . import manual_edit
    return manual_edit.open_editor(_mw_or_none())


# ------------------------------------------------------- Home mode (R801)
#: Home (the projects page) used to show only when no document was open: to
#: see your other projects you had to close the one you were in. Home mode
#: shows it over the 3D view with projects still open. The sidebar's logo
#: and Ctrl+0 toggle it; opening any project from it, or Esc, leaves it.
_HOME = {"on": False}


def home_open():
    return bool(_HOME["on"])


def show_home(on=True):
    """Show Home over the 3D view (on) or go back to the 3D view."""
    on = bool(on)
    if on == _HOME["on"]:
        return on
    _HOME["on"] = on
    ov = _S.get("overlay")
    if ov is not None:
        try:
            if on:
                _refresh_home()
            ov.place()
            if on:
                ov.empty.setFocusPolicy(QtCore.Qt.StrongFocus)
                ov.empty.setFocus(QtCore.Qt.OtherFocusReason)
        except RuntimeError:
            pass
    return on


def toggle_home():
    return show_home(not home_open())


def _leave_home():
    if home_open():
        show_home(False)


def _keys_of(act):
    try:
        return list(act.shortcuts())
    except RuntimeError:
        return []


def _install_shortcuts(mw):
    """One QShortcut per SHORTCUTS row on the main window. A FreeCAD menu
    action bound to the same key (Ctrl+P is Print) would make both
    ambiguous so NEITHER fires: such a key is taken off that action while
    Atech is active, and given back by _remove_shortcuts()."""
    taken = []
    ours = {QtGui.QKeySequence(k) for _i, k, _t, _s in SHORTCUTS}
    for act in mw.findChildren(QtGui.QAction):
        keys = _keys_of(act)
        if not keys:
            continue
        keep = [k for k in keys if k not in ours]
        if len(keep) != len(keys):
            taken.append((act, keys))
            act.setShortcuts(keep)
    scs = {}
    for sid, key, _text, _sec in SHORTCUTS:
        sc = QtGui.QShortcut(QtGui.QKeySequence(key), mw)
        sc.setContext(QtCore.Qt.WindowShortcut)
        sc.activated.connect(lambda i=sid: _safe(_shortcut_fn(i)))
        scs[sid] = sc
    _S["shortcuts"] = scs
    _S["shortcuts_taken"] = taken
    return scs


def _remove_shortcuts():
    for sc in (_S.get("shortcuts") or {}).values():
        try:
            sc.setEnabled(False)
            sc.deleteLater()
        except RuntimeError:
            pass
    for act, keys in _S.get("shortcuts_taken") or ():
        try:
            act.setShortcuts(keys)
        except RuntimeError:
            pass
    _S.pop("shortcuts", None)
    _S.pop("shortcuts_taken", None)


def key_text(key):
    """A key sequence as this platform writes it (\u2318L on macOS)."""
    if ", " in key or " / " in key:
        return key                       # "V, F" or "1 / 3 / 2": as written
    return QtGui.QKeySequence(key).toString(QtGui.QKeySequence.NativeText) or key


def _sheet_dialog(title, parent=None):
    dlg = QtWidgets.QDialog(parent or _mw_or_none())
    dlg.setObjectName("AtechSheet")
    dlg.setAttribute(QtCore.Qt.WA_StyledBackground, True)
    dlg.setWindowTitle(title)
    dlg.setAccessibleName(title)
    dlg.setStyleSheet(style.qss(SHEET_QSS))
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.setContentsMargins(22, 20, 22, 18)
    lay.setSpacing(12)
    t = QtWidgets.QLabel(title)
    t.setObjectName("SheetTitle")
    lay.addWidget(t)
    return dlg, lay


def _mw_or_none():
    try:
        return _mw()
    except Exception:                                  # noqa: BLE001
        return None


def _sheet_section(lay, title):
    lbl = QtWidgets.QLabel(title.upper())
    lbl.setObjectName("SheetSection")
    lay.addWidget(lbl)


def _sheet_rows(lay, rows, caps=True):
    g = QtWidgets.QGridLayout()
    g.setHorizontalSpacing(16)
    g.setVerticalSpacing(6)
    for i, (key, text) in enumerate(rows):
        k = QtWidgets.QLabel(key)
        k.setObjectName("KeyCap" if caps else "SheetSub")
        k.setAlignment(QtCore.Qt.AlignCenter)
        d = QtWidgets.QLabel(text)
        d.setObjectName("SheetText")
        d.setAccessibleName("%s: %s" % (text, key))
        g.addWidget(d, i, 0)
        g.addWidget(k, i, 1, QtCore.Qt.AlignRight)
    lay.addLayout(g)


def shortcut_rows():
    """[(section, [(key text, what)])] for the shortcut sheet: Atech's own,
    the mouse in the navigation style in use, then FreeCAD's essentials."""
    from . import viewport
    atech = [(key_text(k), (_TOOLS.get(i) or {}).get("label") or t
              if i in ("measure", "section") else t)
             for i, k, t, _s in SHORTCUTS]
    info = viewport.nav_info()
    mouse = [(how, what) for what, how in info["how"]]
    fc = [(key_text(k), t) for k, t in FREECAD_KEYS]
    return [("Atech", atech), ("Mouse (%s)" % info["label"], mouse),
            ("FreeCAD", fc)]


def open_shortcut_sheet(parent=None):
    """Cmd+/ : every shortcut on one sheet (R307)."""
    dlg, lay = _sheet_dialog("Keyboard shortcuts", parent)
    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
    inner = QtWidgets.QWidget()
    inner.setObjectName("SheetInner")
    il = QtWidgets.QVBoxLayout(inner)
    il.setContentsMargins(0, 0, 8, 0)
    il.setSpacing(10)
    # The rows' real height is known only once the sheet's QSS has
    # polished them: without this the scroll area squeezed the last rows
    # onto each other (seen in an offscreen grab).
    il.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
    for sec, rows in shortcut_rows():
        if rows:
            _sheet_section(il, sec)
            _sheet_rows(il, rows, caps=not sec.startswith("Mouse"))
    il.addStretch(1)
    scroll.setWidget(inner)
    lay.addWidget(scroll, 1)
    row = QtWidgets.QHBoxLayout()
    row.addStretch(1)
    ok = QtWidgets.QPushButton("Done")
    ok.setObjectName("SheetBtn")
    ok.setDefault(True)
    ok.clicked.connect(dlg.accept)
    row.addWidget(ok)
    lay.addLayout(row)
    dlg.resize(460, 620)
    _S["sheet"] = dlg
    dlg.show()
    return dlg


# ------------------------------------- appearance & navigation (R304/306)
def appearance_panel(parent=None):
    """The Theme (Light / Dark / System) and Navigation style controls as
    one widget, for this module's own dialog and for the integrator to
    embed in settings.py's dialog. Changes apply at once."""
    from . import viewport
    w = QtWidgets.QWidget(parent)
    w.setObjectName("AppearancePanel")
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    _sheet_section(lay, "Theme")
    themes = list(style.THEMES)
    w.theme = navbar.PillTabs([style.THEME_LABELS[t] for t in themes])
    w.theme.setAccessibleName("Theme")
    w.theme.set_icons([style.icon(n, style.tokens()["muted"], 14)
                       for n in ("sun", "moon", "monitor")])
    cur = style.theme_choice() or style.mode()
    w.theme.set_index(themes.index(cur) if cur in themes else 0, animate=False)
    w.theme.changed.connect(lambda i: _set_theme(themes[i]))
    lay.addWidget(w.theme)
    note = QtWidgets.QLabel("System follows your Mac's Light or Dark "
                            "appearance." if sys.platform == "darwin" else
                            "System follows your desktop's light or dark "
                            "setting.")
    note.setObjectName("SheetSub")
    note.setWordWrap(True)
    lay.addWidget(note)
    lay.addSpacing(6)
    _sheet_section(lay, "Navigation style")
    group = QtWidgets.QButtonGroup(w)
    w.nav_buttons = {}
    current = viewport.nav_style()
    styles = list(viewport.NAV_STYLES)
    if all(s_["cls"] != current for s_ in styles):
        styles.append(viewport.nav_info(current))      # theirs, from Preferences
    for s_ in styles:
        rb = QtWidgets.QRadioButton("%s \u2014 %s" % (s_["label"], s_["blurb"]))
        rb.setAccessibleName("%s navigation" % s_["label"])
        rb.setChecked(s_["cls"] == current)
        rb.toggled.connect(lambda on, c=s_["cls"]: on and _set_nav(c, w))
        group.addButton(rb)
        lay.addWidget(rb)
        w.nav_buttons[s_["cls"]] = rb
    w.how = QtWidgets.QLabel()
    w.how.setObjectName("SheetSub")
    w.how.setWordWrap(True)
    lay.addWidget(w.how)
    _fill_how(w)
    again = QtWidgets.QPushButton("Show the mouse guide again")
    again.setObjectName("SheetLink")
    again.setCursor(QtCore.Qt.PointingHandCursor)
    again.clicked.connect(_show_hint_again)
    row = QtWidgets.QHBoxLayout()
    row.addWidget(again)
    row.addStretch(1)
    lay.addLayout(row)
    return w


def _fill_how(w):
    from . import viewport
    info = viewport.nav_info()
    w.how.setText("  \u00b7  ".join("%s: %s" % (a, h) for a, h in info["how"]))


def _set_theme(choice):
    try:
        style.apply_theme_choice(choice)
    except Exception as exc:                           # noqa: BLE001
        _log("theme: %r" % (exc,))
    if _S:
        restyle()


def _set_nav(cls, panel=None):
    from . import viewport
    try:
        viewport.set_nav_style(cls, live=bool(_S))
    except Exception as exc:                           # noqa: BLE001
        _log("nav style: %r" % (exc,))
    if panel is not None:
        _fill_how(panel)
    ov = _S.get("overlay")
    if ov is not None:
        ov.hint.fill()
        ov.place()


def _show_hint_again():
    from . import viewport
    viewport.set_orbit_hint_seen(False)
    ov = _S.get("overlay")
    if ov is not None:
        ov.hint.fill()
        ov.place()


def open_appearance(parent=None):
    dlg, lay = _sheet_dialog("Appearance & navigation", parent)
    panel = appearance_panel(dlg)
    lay.addWidget(panel)
    lay.addStretch(1)
    row = QtWidgets.QHBoxLayout()
    row.addStretch(1)
    ok = QtWidgets.QPushButton("Done")
    ok.setObjectName("SheetBtn")
    ok.setDefault(True)
    ok.clicked.connect(dlg.accept)
    row.addWidget(ok)
    lay.addLayout(row)
    dlg.resize(520, 440)
    _S["appearance"] = dlg
    dlg.show()
    return dlg


def settings_menu(parent=None):
    """The gear's menu (sidebar head and top bar): agent settings,
    appearance and navigation, the shortcut sheet, switching workbench
    (on macOS the top bar's Workbench button is not drawn) and credits."""
    menu = QtWidgets.QMenu(parent)
    menu.setAccessibleName("Settings")

    def fill():
        menu.clear()
        menu.addAction("Agent settings\u2026", lambda: _open_settings())
        menu.addAction("Appearance & navigation\u2026",
                       lambda: open_appearance())
        a = menu.addAction("Keyboard shortcuts", lambda: open_shortcut_sheet())
        a.setShortcut(QtGui.QKeySequence("Ctrl+/"))
        a.setShortcutVisibleInContextMenu(True)
        menu.addSeparator()
        wb = menu.addMenu("Switch workbench")
        wb.aboutToShow.connect(lambda m=wb: _fill_workbench_menu(m))
        menu.addAction("Credits & open-source licences",
                       lambda: _open_credits())
    menu.aboutToShow.connect(fill)
    fill()
    return menu


def sidebar_chrome(mw=None, env=None):
    """True when the wordmark, Terminal and Settings belong in the sidebar
    head (R300): the menu bar is the native one (macOS), which draws no
    corner widgets. ATECH_SIDEBAR_CHROME=1/0 forces it either way."""
    env = os.environ if env is None else env
    v = (env.get("ATECH_SIDEBAR_CHROME") or "").strip()
    if v in ("0", "1"):
        return v == "1"
    try:
        mw = mw or _mw()
        return bool(mw.menuBar().isNativeMenuBar())
    except Exception:                                  # noqa: BLE001
        return sys.platform == "darwin"


# ------------------------------------------- right-click menu (R381)
#: (command id, menu text, tooltip, action key) of the Atech commands the
#: 3D view's right-click menu offers next to Hide / Isolate / Show all /
#: See-through (inspect_tools). EXPORT_COMMANDS go in their own submenu.
TOOL_COMMANDS = (
    ("Atech_Colour", "Colour\u2026", "Change the colour or see-through of "
     "the selected parts", "colour"),
    ("Atech_Measure", "Measure", "Measure distances, angles, sizes and "
     "walls (M)", "measure"),
    ("Atech_Section", "Section view", "Cut the model open to look inside "
     "(Shift+S)", "section"),
    ("Atech_Dimensions", "Dimensions\u2026", "Change the model's numbers by "
     "hand and rebuild (D)", "dims"),
)
EXPORT_COMMANDS = (
    ("Atech_ExportForPrint", "Export for print\u2026", "Save STL, 3MF or "
     "STEP files for a 3D printer", "export"),
    ("Atech_ExplodedView", "Exploded view\u2026", "Spread the parts apart "
     "to see how they fit", "explode"),
    ("Atech_BillOfMaterials", "Bill of materials\u2026", "Printed parts and "
     "Atech hardware, with a CSV export", "bom"),
    ("Atech_ShareImage", "Save a share image", "A 1920 x 1080 picture in "
     "Pictures, also copied", "share"),
    ("Atech_ReviewSheet", "Save a review sheet", "Six views of the model "
     "on one picture", "sheet"),
)
EXPORT_MENU = "Export and share"
_KEEP_DIALOGS = []      # dialogs opened from the menus stay referenced


def _keep_dialog(d):
    _KEEP_DIALOGS[:] = [x for x in _KEEP_DIALOGS if _alive(x)][-7:] + [d]
    return d


def _active_doc():
    try:
        import FreeCAD
        return FreeCAD.ActiveDocument
    except Exception:                                  # noqa: BLE001
        return None


def _say_at_cursor(text):
    try:
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), text)
    except Exception:                                  # noqa: BLE001
        pass
    _log(text)


def run_command_action(key):
    """What one TOOL_COMMANDS / EXPORT_COMMANDS entry does. The view bar's
    own button is pressed when it is there, so the card, the dialog and
    the button's checked state stay one thing."""
    from . import export_tools
    parent = _mw_or_none()
    if key in ("measure", "section"):
        _press(key)
        return key
    if key == "colour":
        m = _keep_dialog(export_tools.ColourMenu(parent))
        m.popup(QtGui.QCursor.pos())
        return m
    if key == "export" and click_tool(key):
        return key
    if key == "dims":
        return _open_dimensions()
    if key == "export":
        return _keep_dialog(export_tools.ExportDialog(parent)).show()
    if key == "explode":
        return _keep_dialog(export_tools.ExplodeDialog(parent)).show()
    if key == "bom":
        return _keep_dialog(export_tools.BomDialog(parent)).show()
    if key == "share":
        path, msg = export_tools.share_now(parent)
        _say_at_cursor(msg)
        return path
    if key == "sheet":
        from . import capture
        path = capture.share_sheet(_active_doc())
        _say_at_cursor("Review sheet saved to %s" % path)
        return path
    raise KeyError(key)


def command_enabled(key, doc=None, selection=None):
    """Pure (tests pass doc / selection): whether an Atech menu command
    makes sense now. Every one needs an open document; Colour also needs
    a selected part."""
    if doc is None:
        return False
    if key == "colour":
        return bool(selection)
    return True


class _AtechCommand(object):
    def __init__(self, text, tip, key):
        self.text, self.tip, self.key = text, tip, key

    def GetResources(self):                            # noqa: N802
        return {"MenuText": self.text, "ToolTip": self.tip}

    def Activated(self):                               # noqa: N802
        _safe(lambda: run_command_action(self.key))

    def IsActive(self):                                # noqa: N802
        try:
            sel = []
            if self.key == "colour":
                import FreeCADGui
                sel = FreeCADGui.Selection.getSelection()
            return bool(_S) and command_enabled(self.key, _active_doc(), sel)
        except Exception:                              # noqa: BLE001
            return False


def register_commands(gui=None):
    """Add the Atech menu commands to FreeCAD once (they stay registered;
    IsActive is False while Atech is not the active workbench)."""
    if gui is None:
        import FreeCADGui as gui
    have = set(gui.listCommands())
    added = []
    for cid, text, tip, key in TOOL_COMMANDS + EXPORT_COMMANDS:
        if cid not in have:
            gui.addCommand(cid, _AtechCommand(text, tip, key))
            added.append(cid)
    return added


def context_menu(workbench, recipient, gui=None):
    """R381: the right-click menu of the 3D view ("View") and the part tree
    ("Tree"): Hide / Isolate / Show all / See-through, then Colour,
    Measure and Section, then an "Export and share" submenu. Installed on
    the Atech workbench by _install_context_menu(); InitGui's
    Workbench.ContextMenu may call it directly instead."""
    if recipient not in ("View", "Tree"):
        return False
    from . import inspect_tools
    if gui is not False:
        inspect_tools.register_commands()
        register_commands(gui)
    workbench.appendContextMenu("", ["Separator"]
                                + list(inspect_tools.CONTEXT_COMMANDS))
    tools = [c[0] for c in TOOL_COMMANDS]
    if recipient == "Tree":
        tools = ["Atech_Colour"]
    workbench.appendContextMenu("", ["Separator"] + tools)
    workbench.appendContextMenu(EXPORT_MENU, [c[0] for c in EXPORT_COMMANDS])
    return True


def _atech_workbench():
    try:
        import FreeCADGui
        try:
            return FreeCADGui.getWorkbench("AcadAgentWorkbench")
        except Exception:                              # noqa: BLE001
            return FreeCADGui.activeWorkbench()
    except Exception:                                  # noqa: BLE001
        return None


def _install_context_menu(wb=None):
    """FreeCAD asks a Python workbench's ContextMenu(recipient) each time
    a right-click menu opens. The Atech workbench class has none, so the
    shell gives its instance one while Atech is active (and takes it off
    on uninstall). A class that defines its own is left alone."""
    wb = wb if wb is not None else _atech_workbench()
    if wb is None:
        return False
    if "ContextMenu" in type(wb).__dict__:
        return False
    try:
        wb.ContextMenu = lambda recipient, _wb=wb: _safe(
            lambda: context_menu(_wb, recipient))
    except Exception as exc:                           # noqa: BLE001
        _log("context menu: %r" % (exc,))
        return False
    _S["context_wb"] = wb
    return True


def _remove_context_menu():
    wb = _S.pop("context_wb", None)
    if wb is not None:
        try:
            del wb.ContextMenu
        except Exception:                              # noqa: BLE001
            pass


# ------------------------------------------- document events (R302)
class _DocObserver(object):
    """FreeCAD App document observer: the picker, the parts hint and Home
    follow document creation, deletion, relabel, activation and saves
    (was an 800 ms poll of the picker)."""

    def __init__(self, fn):
        self._fn = fn

    def _ping(self, *_a):
        try:
            QtCore.QTimer.singleShot(0, self._fn)
        except Exception:                              # noqa: BLE001
            pass

    slotCreatedDocument = slotRelabelDocument = _ping
    slotFinishSaveDocument = _ping

    def slotDeletedDocument(self, doc):                 # noqa: N802
        """R516: FreeCAD is closing `doc` (Close All closes one after the
        other, activating each next one in between). Note it, so the safety
        tick leaves every view alone until the closing is over, and refresh
        the picker afterwards (queued: never inside FreeCAD's close)."""
        _closing_now()
        self._ping()

    def slotActivateDocument(self, doc):                # noqa: N802
        self._ping()
        # R516: queued by Name + Uid, never with the document object: Close
        # All activates each next document and then closes it before the
        # event loop runs, so the queued call must find the document again
        # (or that it is gone) instead of using the one it was given.
        key = _doc_ref(doc)
        if key is None:
            return
        try:
            QtCore.QTimer.singleShot(0, lambda k=key: _note_opened(_live_doc(k)))
        except Exception:                              # noqa: BLE001
            pass

    def slotStartSaveDocument(self, doc, _filename=None):  # noqa: N802
        """R382: an exploded view is display only; never saved. Runs
        before FreeCAD writes the file (synchronously, not queued)."""
        _before_save(doc)


_BASED = set()          # documents whose hand-edit baseline was checked
#: R516: how long after FreeCAD starts closing a document the safety tick
#: leaves the 3D views alone (Close All closes the rest within this)
CLOSING_QUIET_S = 1.0
_CLOSING = [0.0]        # monotonic time of the last document close


def _closing_now():
    _CLOSING[0] = time.monotonic()


def closing_documents():
    """R516: True while FreeCAD is (or was a moment ago) closing documents."""
    return time.monotonic() - _CLOSING[0] < CLOSING_QUIET_S


def _modal_up():
    """R516: a modal dialog (Save changes?, a file dialog) is open."""
    try:
        app = QtWidgets.QApplication.instance()
        return app is not None and app.activeModalWidget() is not None
    except RuntimeError:
        return False


def _doc_ref(doc):
    """(Name, Uid) of a live document, or None for no / a closed one."""
    try:
        return str(doc.Name), str(doc.Uid)
    except Exception:                                  # noqa: BLE001
        return None


def _live_doc(ref):
    """The open document `ref` (_doc_ref) names, or None when it was closed
    meanwhile (or its Name now belongs to another document)."""
    if not ref:
        return None
    try:
        import FreeCAD
        doc = FreeCAD.listDocuments().get(ref[0])
        if doc is not None and str(doc.Uid) == ref[1]:
            return doc
    except Exception:                                  # noqa: BLE001
        pass
    return None


def _before_save(doc):
    try:
        from . import export_tools
        export_tools.restore_exploded(doc)
    except Exception as exc:                           # noqa: BLE001
        _log("exploded view before save: %r" % (exc,))


def _note_opened(doc):
    """R382: once per document, record its agent parts' values as built
    (export_tools.ensure_base), so hand edits made in a file opened from
    disk are told apart from the build at the next agent build. Only a
    file built before hand edits were tracked has parts missing. R516:
    nothing for no document (the activation's queued call passes None when
    the document was closed meanwhile, _live_doc)."""
    if doc is None:
        return None
    try:
        key = (doc.Name, getattr(doc, "FileName", ""))
    except Exception:                                  # noqa: BLE001
        return None
    if key in _BASED:
        return None
    _BASED.add(key)
    try:
        from . import export_tools
        return export_tools.ensure_base(doc)
    except Exception as exc:                           # noqa: BLE001
        _log("hand-edit baseline: %r" % (exc,))
        return None


def _docs_event():
    if not _S:
        return
    body = _S.get("body")
    if body is not None:
        try:
            body.picker.refresh()
        except Exception as exc:                       # noqa: BLE001
            _log("picker: %r" % (exc,))
        body.sync_model_hint()
    ov = _S.get("overlay")
    if ov is not None:
        ov._queue()
        try:
            if ov.empty.isVisible() and hasattr(ov.empty, "refresh") \
                    and isinstance(ov.empty, HomeView):
                ov.empty.refresh()
        except RuntimeError:
            pass


def _on_color_scheme(*_a):
    """macOS switched Light / Dark: with the System theme chosen, FreeCAD's
    own theme follows, and so does every Atech surface (R306)."""
    if not _S or style.theme_choice() != "system":
        return
    try:
        style.apply_theme_choice("system")
    except Exception as exc:                           # noqa: BLE001
        _log("system theme: %r" % (exc,))
    _check_theme()


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
    word = QtWidgets.QLabel(style.PRODUCT)
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
            ("", "settings", "Settings, appearance and keyboard shortcuts",
             settings_menu)):
        b = QtWidgets.QPushButton(icon_label(text))
        b.setAccessibleName(text or "Settings")
        b.setObjectName("TopBtn")
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.setIconSize(QtCore.QSize(15, 15))
        if fn is settings_menu:
            b.setMenu(settings_menu(b))
        elif fn is not None:
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


def _hardware_switch():
    """R280: the sidebar's "Only CAD | CAD + electronics" switch. It stores
    hw_mode, which the next chat turn's prompt reads (build.board_default):
    CAD only builds plain CAD, CAD + electronics builds the request as a
    real product custom-fitted around the Atech board and modules."""
    try:
        from . import hw_mode
        sw = navbar.PillTabs([hw_mode.LABELS[m] for m in hw_mode.MODES])
        sw.setObjectName("HardwareSwitch")
        sw.setAccessibleName("What the agent builds")
        sw.setToolTip("Only CAD: plain 3D designs.\n"
                      "CAD + electronics: designs built around the Atech "
                      "board and modules, fitted to them.\n"
                      "Applies from your next message.")
        sw.set_index(hw_mode.MODES.index(hw_mode.get()), animate=False)

        def chosen(i):
            if not hw_mode.set(hw_mode.MODES[i]):
                _log("hardware mode: could not save settings")
        sw.changed.connect(chosen)
        return sw
    except Exception as exc:                           # noqa: BLE001
        _log("hardware switch: %r" % (exc,))
        return None


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
        try:
            body.picker.refresh()          # R302: a window came or went
        except Exception as exc:                       # noqa: BLE001
            _log("picker: %r" % (exc,))
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
    _install_context_menu()                                    # R381
    _S["topbar"] = _build_topbar(mw)
    # R300: on macOS (native menu bar) the top bar's corners are not drawn;
    # the sidebar head carries the wordmark, Terminal and Settings there.
    _S["sidebar_chrome"] = sidebar_chrome(mw)
    body.set_header_chrome(_S["sidebar_chrome"])
    _install_shortcuts(mw)                                     # R307
    drops = DropFilter(dock)                                   # R309
    _S["drops"] = drops
    for w in (mw, dock):
        w.installEventFilter(drops)
    _S["drop_accept"] = mw.acceptDrops()
    mw.setAcceptDrops(True)
    _hook_docs()                                               # R302
    try:
        hints = QtGui.QGuiApplication.styleHints()
        hints.colorSchemeChanged.connect(_on_color_scheme)      # R306
        _S["scheme_hooked"] = hints
    except Exception as exc:                           # noqa: BLE001
        _log("colour scheme: %r" % (exc,))

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


def _hook_docs():
    """Register one FreeCAD document observer while Atech is active."""
    try:
        import FreeCAD
        add = getattr(FreeCAD, "addDocumentObserver", None)
        if add is None:
            return False
        obs = _DocObserver(_docs_event)
        add(obs)
        _S["doc_observer"] = obs
        return True
    except Exception as exc:                           # noqa: BLE001
        _log("document observer: %r" % (exc,))
        return False


def _unhook_docs():
    obs = _S.pop("doc_observer", None)
    if obs is None:
        return
    try:
        import FreeCAD
        FreeCAD.removeDocumentObserver(obs)
    except Exception as exc:                           # noqa: BLE001
        _log("document observer removal: %r" % (exc,))


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
    _closing_now()                                      # R516
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
    Cheap when nothing changed: one property read per Atech mesh. R516:
    never while documents are being closed (Close All, quit) or a modal
    dialog (FreeCAD's "Save changes?") runs its own event loop: the view
    objects of a closing document are on their way out."""
    if closing_documents() or _modal_up():
        return
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
        # backup for the document events (R302): cheap, and a no-op when
        # the title did not change
        try:
            body.picker.refresh()
        except Exception as exc:                       # noqa: BLE001
            _log("picker: %r" % (exc,))
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
    mw.setStyleSheet(style.qss(MAIN_QSS, reset=False))     # R390
    _hide_dead_subwindows()          # the sheets above re-showed them
    ov = _S.get("overlay")
    if ov is not None:
        ov.bar.restyle()
        ov.empty.restyle()
        ov.hint.restyle()
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

    _remove_shortcuts()
    _unhook_docs()
    _remove_context_menu()
    hints = _S.get("scheme_hooked")
    if hints is not None:
        try:
            hints.colorSchemeChanged.disconnect(_on_color_scheme)
        except (RuntimeError, TypeError):
            pass
    drops = _S.get("drops")
    if drops is not None:
        for w in (mw, _S.get("dock")):
            try:
                if w is not None:
                    w.removeEventFilter(drops)
            except RuntimeError:
                pass
        if "drop_accept" in _S:
            mw.setAcceptDrops(_S["drop_accept"])
    for key in ("sheet", "appearance"):
        dlg = _S.get(key)
        if dlg is not None:
            try:
                dlg.close()
            except RuntimeError:
                pass
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
        if _S.get("focus_view"):
            dock.setVisible(True)       # full-screen 3D ends with Atech
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
    if focus_view():
        set_focus_view(False)
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


register_builtin_tools()                               # R380, at import
